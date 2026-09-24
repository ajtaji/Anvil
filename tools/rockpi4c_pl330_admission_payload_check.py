#!/usr/bin/env python3
"""Contract and emitted audit for the bounded RK3399 DMAC0 admission probe."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/pl330_secure_admission_payload.rockpi4c"
LOAD = 0x03A4BBD8
BSS = 0x03AD0000
STACK = 0x03E40000

UART_USR = 0xFF1A007C
UART_LSR = 0xFF1A0014
UART_THR = 0xFF1A0000
DDR_MST22 = 0xFF330058
SOC8 = 0xFF338020
SOC9 = 0xFF338024
SOC10 = 0xFF338028
SOFTRST10 = 0xFF760428

EXPECTED_WRITES = [
    (UART_THR, None),
    (DDR_MST22, 0x00010001),
    (SOC8, 0xFFFF0000),
    (SOC9, 0xFFFF0000),
    (SOC10, 0xFFFF0000),
    (SOFTRST10, 0x00080008),
    (SOFTRST10, 0x00080000),
]

EXPECTED_READS = [
    UART_USR, UART_LSR,
    0xFF760080, 0xFF760084, 0xFF760088, 0xFF76008C,
    0xFF6D0FE0, 0xFF6D0FE4, 0xFF6D0FE8, 0xFF6D0FEC,
    0xFF6D0FF0, 0xFF6D0FF4, 0xFF6D0FF8, 0xFF6D0FFC,
    0xFF76015C, 0xFF76031C, 0xFF760364, SOFTRST10,
    SOC8, SOC9, SOC10, DDR_MST22,
    SOC8, SOC9, SOC10, DDR_MST22,
    SOFTRST10,
    0xFF6D0000, 0xFF6D0004, 0xFF6D0100, 0xFF6D0104,
    0xFF6D0E00, 0xFF6D0E14,
]


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def emitted_mmio(assembly: str) -> tuple[list[int], list[tuple[int, int | None]]]:
    constants: dict[str, int] = {}
    reads: list[int] = []
    writes: list[tuple[int, int | None]] = []
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
        match = re.fullmatch(r"(ldr|str) (w\d+), \[(x\d+)\]", line)
        if match and match.group(3) in constants:
            operation, value_register, address_register = match.groups()
            address = constants[address_register]
            if address >= 0xF0000000:
                if operation == "ldr":
                    reads.append(address)
                else:
                    source = "x" + value_register[1:]
                    writes.append((address, constants.get(source)))
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
    for token in (
        "pmf:load $03a4bbd8",
        "#admit_ddr0_secure_mask = $00010001",
        "#admit_secure_mask = $ffff0000",
        "#admit_dmac0_reset_assert = $00080008",
        "#admit_dmac0_reset_release = $00080000",
        "#admit_hold_us = 5",
        "rocktimerwaitus(#admit_hold_us)",
        "pid=0 and cid=0",
        "(pid & $fffff)<>$41330",
        "cid<>$b105f00d",
    ):
        need(token in lower, f"missing admission contract token: {token}")
    need("#admit_dmac1" not in lower and "$ff6e" not in lower and
         "$00100010" not in lower,
         "probe gained DMAC1 ownership")
    need("00010001" in lower and "ffff0000" in lower,
         "official TF-A security masks changed")

    pokes = re.findall(r"(?im)^\s*pokel\(([^\r\n]+)\)\s*$", source)
    expected_pokes = [
        "#ADMIT_SGRF+#ADMIT_DDR_MST22,#ADMIT_DDR0_SECURE_MASK",
        "#ADMIT_SGRF+#ADMIT_SOC_CON8,#ADMIT_SECURE_MASK",
        "#ADMIT_SGRF+#ADMIT_SOC_CON9,#ADMIT_SECURE_MASK",
        "#ADMIT_SGRF+#ADMIT_SOC_CON10,#ADMIT_SECURE_MASK",
        "#ADMIT_CRU+#ADMIT_SOFTRST10,#ADMIT_DMAC0_RESET_ASSERT",
        "#ADMIT_CRU+#ADMIT_SOFTRST10,#ADMIT_DMAC0_RESET_RELEASE",
    ]
    need(pokes == expected_pokes, f"source MMIO writes differ: {pokes}")
    assert_at = lower.index("pokel(#admit_cru+#admit_softrst10,#admit_dmac0_reset_assert)")
    wait_at = lower.index("held=rocktimerwaitus(#admit_hold_us)")
    release_at = lower.index("pokel(#admit_cru+#admit_softrst10,#admit_dmac0_reset_release)")
    need(assert_at < wait_at < release_at, "reset assert/wait/release order changed")
    between = lower[assert_at:release_at]
    need("procedurereturn" not in between,
         "software can return while DMAC0 reset remains asserted")
    need(lower.count("rocktimerwaitus(") == 1,
         "probe gained an unreviewed wait")
    need("rockcrufield" not in lower and "rockcrugate" not in lower,
         "probe must observe clocks without changing them")
    for code in range(1, 12):
        need(f"#admit_err_" in lower and f"$3300ae{code:02x}" in lower,
             f"return code 0x3300AE{code:02X} is missing")

    print("rockpi4c PL330 admission payload source contract: PASS")
    print("  only DMAC0 TF-A security masks and reset 163 assert/release are owned")
    print("  five-us wait bounded; no return exists before unconditional release")

    data: bytes | None = None
    if args.binary:
        data = args.binary.read_bytes()
        need(0 < len(data) <= 4 * 1024 * 1024 and len(data) % 4 == 0,
             "binary extent/alignment violates live stage")
        print(f"  binary bytes={len(data)} crc32={zlib.crc32(data) & 0xffffffff:08X}")
        print(f"  sha256={hashlib.sha256(data).hexdigest().upper()}")

    if args.assembly:
        reads, writes = emitted_mmio(args.assembly.read_text(encoding="utf-8"))
        need(reads == EXPECTED_READS,
             f"emitted MMIO reads differ: {[hex(value) for value in reads]}")
        need(writes == EXPECTED_WRITES,
             "emitted MMIO writes differ: " +
             repr([(hex(address), None if value is None else hex(value))
                   for address, value in writes]))
        print("  emitted MMIO values/order: PASS")

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
        need(bss == BSS and 0 < bss_bytes <= 0x1000,
             "PMF BSS placement differs")
        need((flags, reserved, arch, target, stack) == (1, 0, 1, 3399, STACK),
             "PMF returning RK3399/stack contract differs")
        need(pmf[64:96] == hashlib.sha256(data).digest(),
             "PMF digest differs from flat binary")
        need(pmf[112:128] == bytes(16) and pmf[128:] == data,
             "PMF reserved bytes or payload differ")
        print("  PMF v2 placement: PASS")

    if args.symbols:
        need(data is not None, "--symbols requires --binary")
        symbols = {}
        for line in args.symbols.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                symbols[name.strip().lower()] = int(value.strip(), 0)
        need(symbols.get("__image_end__") == len(data), "symbol image extent differs")
        need(symbols.get("__bss_start__") == BSS, "symbol BSS start differs")
        bss_end = symbols.get("__bss_end__", 0)
        need(BSS < bss_end <= BSS + 0x1000, "symbol BSS end differs")
        need(symbols.get("_start") == 0, "entry symbol differs")
        main_offset = symbols.get("main", -1)
        need(0 <= main_offset < len(data) and main_offset % 4 == 0,
             "Main symbol is outside the image")
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        instructions = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(data, LOAD))
        targets = []
        for instruction in instructions:
            if instruction.mnemonic == "adrp":
                targets.append(int(instruction.op_str.split("#", 1)[1], 0))
        need(set(targets) == {0x03A4D000, BSS},
             f"ADRP targets differ: {[hex(value) for value in sorted(set(targets))]}")
        main_address = LOAD + main_offset
        need(any(instruction.mnemonic == "bl" and
                 int(instruction.op_str.lstrip("#"), 0) == main_address
                 for instruction in instructions[:32]),
             "startup does not call linked Main")
        print("  symbols/ADRP relocation: PASS")


if __name__ == "__main__":
    main()
