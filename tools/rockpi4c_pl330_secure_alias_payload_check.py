#!/usr/bin/env python3
"""Contract and emitted audit for the RK3399 secure-alias PL330 probe."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/pl330_secure_alias_payload.rockpi4c"
LOAD = 0x03A4BBD8
BSS = 0x03AD0000
STACK = 0x03E40000

UART_LSR = 0xFF1A0014
UART_THR = 0xFF1A0000
SDMAC0 = 0xFFFC0000
SDMAC1 = 0xFFFD0000
OFFSETS = (0x000, 0xE00, 0xE14, 0xFE0, 0xFE4, 0xFE8, 0xFEC,
           0xFF0, 0xFF4, 0xFF8, 0xFFC)
EXPECTED_READS = [UART_LSR] + [base + offset for base in (SDMAC0, SDMAC1)
                               for offset in OFFSETS]


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def emitted_mmio(assembly: str) -> tuple[list[int], list[int]]:
    constants: dict[str, int] = {}
    reads: list[int] = []
    writes: list[int] = []
    for raw in assembly.splitlines():
        line = raw.strip().lower()
        match = re.fullmatch(r"movz (x\d+), #(\d+)(?:, lsl #(\d+))?", line)
        if match:
            register, value, shift = match.groups()
            constants[register] = int(value) << int(shift or 0)
            continue
        match = re.fullmatch(r"movk (x\d+), #(\d+), lsl #(\d+)", line)
        if match:
            register, value, shift = match.groups()
            if register in constants:
                amount = int(shift)
                mask = 0xFFFF << amount
                constants[register] = ((constants[register] & ~mask) |
                                       (int(value) << amount))
            continue
        match = re.fullmatch(r"(ldr|str) w\d+, \[(x\d+)\]", line)
        if match and match.group(2) in constants:
            operation, address_register = match.groups()
            address = constants[address_register]
            if address >= 0xF0000000:
                (reads if operation == "ldr" else writes).append(address)
            continue
        match = re.fullmatch(r"mov (x\d+), (x\d+)", line)
        if match:
            destination, source = match.groups()
            if source in constants:
                constants[destination] = constants[source]
            else:
                constants.pop(destination, None)
            continue
        match = re.match(r"(?:mov|add|sub|and|orr|eor|ldr) (x\d+),", line)
        if match:
            constants.pop(match.group(1), None)
    return reads, writes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--assembly", type=Path)
    parser.add_argument("--pmf", type=Path)
    parser.add_argument("--symbols", type=Path)
    args = parser.parse_args()

    source = SOURCE.read_text(encoding="utf-8")
    lower = source.lower()
    need("pmf:load $03a4bbd8" in lower, "payload is not linked to live stage")
    need('"' not in source and "datasection" not in lower and "data.s" not in lower,
         "payload gained string/data-section telemetry")
    need("#alias_uart_spins = 1000000" in lower, "UART polling is unbounded")
    need(re.findall(r"pokel\(([^,]+),", lower) == ["#alias_uart2_thr"],
         "non-UART source MMIO write present")
    need("$ff6d0000" not in lower and "$ff6e0000" not in lower,
         "normal-world DMAC aperture reintroduced")
    for forbidden in ("#alias_cru", "#alias_pmu", "#alias_sgrf", "rockcru"):
        need(forbidden not in lower, f"control-plane token present: {forbidden}")

    positions: list[int] = []
    for stem in ("#alias_sdmac0", "#alias_sdmac1"):
        for offset in ("$000", "$e00", "$e14", "$fe0", "$fe4", "$fe8",
                       "$fec", "$ff0", "$ff4", "$ff8", "$ffc"):
            token = f"peekl({stem}+{offset})"
            need(lower.count(token) == 1, f"read must occur once: {token}")
            positions.append(lower.index(token))
    need(positions == sorted(positions), "secure-alias source read order changed")
    need("aliastx(83)" in lower and "aliastx(48)" in lower and "aliastx(49)" in lower,
         "S0/S1 positional markers changed")
    need("(pid & $fffff)<>$41330" in lower and "cid<>$b105f00d" in lower,
         "PrimeCell identity contract changed")
    print("rockpi4c PL330 secure-alias payload source contract: PASS")

    data: bytes | None = None
    if args.binary:
        data = args.binary.read_bytes()
        need(0 < len(data) <= 4 * 1024 * 1024 and len(data) % 4 == 0,
             "binary extent/alignment violates live stage")
        print(f"  bytes={len(data)} crc32={zlib.crc32(data) & 0xffffffff:08X}")
        print(f"  sha256={hashlib.sha256(data).hexdigest().upper()}")

    if args.assembly:
        assembly = args.assembly.read_text(encoding="utf-8")
        reads, writes = emitted_mmio(assembly)
        need(reads == EXPECTED_READS,
             f"emitted MMIO reads differ: {[hex(value) for value in reads]}")
        need(writes == [UART_THR],
             f"emitted MMIO writes differ: {[hex(value) for value in writes]}")
        need("__str_lit_" not in assembly, "emitted image gained string literals")
        print("  emitted MMIO allowlist/order: PASS")

    if args.pmf:
        need(data is not None, "--pmf requires --binary")
        pmf = args.pmf.read_bytes()
        need(len(pmf) == len(data) + 128 and pmf[:8] == b"PMFBOOT\0",
             "PMF v2 extent/magic differs")
        version, header_bytes = struct.unpack_from("<II", pmf, 8)
        load, entry, image_bytes, bss_base, bss_bytes = struct.unpack_from(
            "<QQQQQ", pmf, 16)
        flags, reserved = struct.unpack_from("<II", pmf, 56)
        arch, target = struct.unpack_from("<II", pmf, 96)
        stack = struct.unpack_from("<Q", pmf, 104)[0]
        need((version, header_bytes) == (2, 128), "PMF is not v2/128")
        need((load, entry, image_bytes) == (LOAD, LOAD, len(data)),
             "PMF load/entry/image extent differs")
        need((bss_base, bss_bytes, stack) == (BSS, 0, STACK),
             "PMF BSS/stack differs")
        need((flags, reserved, arch, target) == (1, 0, 1, 3399),
             "PMF returning AArch64/RK3399 identity differs")
        need(pmf[64:96] == hashlib.sha256(data).digest() and pmf[128:] == data,
             "PMF digest/payload differs")
        print("  PMF v2 placement/digest: PASS")

    if args.symbols:
        need(data is not None, "--symbols requires --binary")
        symbols = {}
        for line in args.symbols.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                symbols[name.strip().lower()] = int(value.strip(), 0)
        need(symbols.get("__image_end__") == len(data), "symbol image extent differs")
        need(symbols.get("__bss_start__") == BSS and
             symbols.get("__bss_end__") == BSS, "symbol BSS placement differs")
        need(symbols.get("_start") == 0, "entry symbol differs")
        main_offset = symbols.get("main", -1)
        need(0 <= main_offset < len(data) and main_offset % 4 == 0,
             "Main symbol is outside the image")
        need(not any(name.startswith("__str_lit_") for name in symbols),
             "symbol table gained string literals")
        print("  symbols/image/BSS: PASS")


if __name__ == "__main__":
    main()
