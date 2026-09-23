#!/usr/bin/env python3
"""Contract, placement and emitted-address audit for the SDMAC0 DMA proof."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/pl330_secure_dma_proof.rockpi4c"
DRIVER = ROOT / "RockPi4C/Lib/dma_pl330.pbi"
LOAD = 0x03A4BBD8
BSS = 0x03AD0000
STACK = 0x03E40000
SDMAC0 = 0xFFFC0000
FORBIDDEN_DMA = (0xFF6D0000, 0xFF6E0000, 0xFFFD0000)


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def procedure(source: str, name: str) -> str:
    found = re.search(
        rf"(?ims)^Procedure(?:\.i)?\s+{re.escape(name)}\b.*?^EndProcedure\s*$",
        source,
    )
    need(found is not None, f"missing {name}")
    return found.group(0)


def constants_in_assembly(assembly: str) -> set[int]:
    """Collect full-width constants materialized by adjacent MOVZ/MOVK ops."""
    registers: dict[str, int] = {}
    values: set[int] = set()
    for raw in assembly.splitlines():
        line = raw.strip().lower()
        match = re.fullmatch(r"movz (x\d+), #(\d+)(?:, lsl #(\d+))?", line)
        if match:
            register, value, shift = match.groups()
            registers[register] = int(value) << int(shift or 0)
            values.add(registers[register])
            continue
        match = re.fullmatch(r"movk (x\d+), #(\d+), lsl #(\d+)", line)
        if match:
            register, value, shift = match.groups()
            if register in registers:
                amount = int(shift)
                mask = 0xFFFF << amount
                registers[register] = ((registers[register] & ~mask) |
                                       (int(value) << amount))
                values.add(registers[register])
            continue
        match = re.match(r"(?:mov|add|sub|and|orr|eor|ldr) (x\d+),", line)
        if match:
            registers.pop(match.group(1), None)
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--assembly", type=Path)
    parser.add_argument("--pmf", type=Path)
    parser.add_argument("--symbols", type=Path)
    args = parser.parse_args()

    source = SOURCE.read_text(encoding="utf-8")
    driver = DRIVER.read_text(encoding="utf-8")
    lower = source.lower()
    driver_lower = driver.lower()
    main_source = procedure(source, "Main").lower()
    run = procedure(driver, "RockDmaPl330RunProgram").lower()
    kill = procedure(driver, "RockDmaPl330Kill").lower()

    for token in (
        "pmf:load $03a4bbd8",
          "#proof_words = 128",
        "#proof_bytes = #proof_words*4",
        "global dim proof_fill.l(#proof_words-1)",
        "rock_watchdog_active=1",
        "rockdmapl330init()",
        "rockdmapl330fill32(@proof_fill(0),#proof_fill,#proof_bytes)",
        "(proof_fill(index) & $ffffffff)<>#proof_fill",
        "rockdmapl330copy(@proof_dest(0),@proof_source(0),#proof_copy_bytes)",
        "(proof_dest(index) & $ffffffff)<>($5a000000 | index)",
        'proofline(" dma_fault_ds=",rock_dma_pl330_fault_ds)',
        'proofline(" dma_fault_dpc=",rock_dma_pl330_fault_dpc)',
        'proofline(" dma_fault_fsm=",rock_dma_pl330_fault_fsm)',
        'proofline(" dma_fault_fsc=",rock_dma_pl330_fault_fsc)',
        'proofline(" dma_fault_ftm=",rock_dma_pl330_fault_ftm)',
        'proofline(" dma_fault_cs0=",rock_dma_pl330_fault_cs0)',
        'proofline(" dma_fault_ftc0=",rock_dma_pl330_fault_ftc0)',
        'proofline(" dma_fault_cpc0=",rock_dma_pl330_fault_cpc0)',
        'proofline(" dma_fault_sa0=",rock_dma_pl330_fault_sa0)',
        'proofline(" dma_fault_da0=",rock_dma_pl330_fault_da0)',
        'proofline(" dma_fault_cc0=",rock_dma_pl330_fault_cc0)',
        'proofline(" dma_program_address=",rock_dma_pl330_program_address)',
        'proofline(" dma_program_bytes=",rock_dma_pl330_program_bytes)',
        "proofprogramline()",
    ):
        need(token in lower, f"missing proof contract token: {token}")
    call_order = [main_source.find("rockdmapl330init()"),
                  main_source.find("rockdmapl330fill32("),
                  main_source.find("rockdmapl330copy(")]
    need(all(value >= 0 for value in call_order) and call_order == sorted(call_order),
         "init/fill/copy order changed")
    need("rockwatchdogarm(" not in lower,
         "payload must adopt the monitor deadman without reprogramming it")
    need("#rock_dma_pl330_base = $fffc0000" in driver_lower,
         "production driver is not using silicon-proven SDMAC0")
    need("rockdmapl330secureadmission" not in driver_lower and
         "rockcrureset(" not in driver_lower,
         "production driver regained an SGRF/reset admission experiment")
    need("$00414104" not in driver_lower and "fixedsource" not in driver_lower,
         "production driver regained the silicon-failing fixed source")
    need("#rock_dma_pl330_fill_seed_bytes = 256" in driver_lower and
         "rockdmapl330copy(destination+completed,destination,copybytes)" in driver_lower,
         "production fill no longer uses bounded nonoverlapping copies")
    for value in ("$ff6d0000", "$ff6e0000", "$fffd0000"):
        need(value not in lower and value not in driver_lower,
             f"proof owns forbidden DMA aperture {value}")
    for token in ("#rock_dma_pl330_job_timeout_us", "rockdmapl330kill()"):
        need(token in run, f"DMA job failure lost bounded cleanup: {token}")
    need("rockdmapl330debugexecute(#rock_dma_pl330_cmd_kill,0,0)" in kill and
         "#rock_dma_pl330_debug_timeout_us" in kill,
         "channel-0 KILL is missing or unbounded")

    print("rockpi4c SDMAC0 DMA proof source contract: PASS")
    print("  private 512-byte doubling fill and 1024-byte DMA blit")
    print("  monitor deadman adopted; production job timeout and bounded KILL retained")

    data: bytes | None = None
    if args.binary:
        data = args.binary.read_bytes()
        need(0 < len(data) <= 4 * 1024 * 1024 and len(data) % 4 == 0,
             "binary extent/alignment violates live stage")
        print(f"  bytes={len(data)} crc32={zlib.crc32(data) & 0xffffffff:08X}")
        print(f"  sha256={hashlib.sha256(data).hexdigest().upper()}")

    if args.assembly:
        constants = constants_in_assembly(args.assembly.read_text(encoding="utf-8"))
        need(SDMAC0 in constants, "emitted image does not materialize SDMAC0")
        need(not any(address in constants for address in FORBIDDEN_DMA),
             "emitted image materializes a forbidden normal/DMAC1 aperture")
        print("  emitted DMA aperture allowlist: PASS")

    if args.pmf:
        need(data is not None, "--pmf requires --binary")
        pmf = args.pmf.read_bytes()
        need(len(pmf) == len(data) + 128, "PMF extent differs")
        need(pmf[:8] == b"PMFBOOT\0", "PMF magic differs")
        version, header_bytes = struct.unpack_from("<II", pmf, 8)
        load, entry, image_bytes, bss, bss_bytes = struct.unpack_from(
            "<QQQQQ", pmf, 16)
        flags, reserved = struct.unpack_from("<II", pmf, 56)
        arch, target = struct.unpack_from("<II", pmf, 96)
        stack = struct.unpack_from("<Q", pmf, 104)[0]
        need((version, header_bytes) == (2, 128), "PMF is not v2/128")
        need((load, entry, image_bytes) == (LOAD, LOAD, len(data)),
             "PMF load/entry/image extent differs")
        need(bss == BSS and 0 < bss_bytes <= 0x20000 and bss + bss_bytes < STACK,
             "PMF BSS placement is not bounded below the payload stack")
        need((flags, reserved, arch, target, stack) == (1, 0, 1, 3399, STACK),
             "PMF returning RK3399/stack contract differs")
        need(pmf[64:96] == hashlib.sha256(data).digest(),
             "PMF digest differs from flat binary")
        need(pmf[112:128] == bytes(16) and pmf[128:] == data,
             "PMF reserved bytes or payload differ")
        print("  PMF v2 placement/digest: PASS")

    if args.symbols:
        need(data is not None, "--symbols requires --binary")
        symbols: dict[str, int] = {}
        for line in args.symbols.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                symbols[name.strip().lower()] = int(value.strip(), 0)
        need(symbols.get("__image_end__") == len(data), "symbol image extent differs")
        need(symbols.get("__bss_start__") == BSS, "symbol BSS start differs")
        bss_end = symbols.get("__bss_end__", 0)
        need(BSS < bss_end < STACK, "symbol BSS end overlaps stack")
        need(symbols.get("_start") == 0, "entry symbol differs")
        main_offset = symbols.get("main", -1)
        need(0 <= main_offset < len(data) and main_offset % 4 == 0,
             "Main symbol is outside the image")
        proof_fill = symbols.get("global_proof_fill", 0)
        need(BSS <= proof_fill <= bss_end - 512 and proof_fill % 8 == 0,
             "private proof buffer placement differs")
        need("global_rock_dma_pl330_fill_block" not in symbols,
             "production fill still reserves a dedicated 64 KiB BSS buffer")
        print("  symbols/private proof buffer: PASS")


if __name__ == "__main__":
    main()
