#!/usr/bin/env python3
"""Contract check for the first RK3399 GPU-infrastructure live payload."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/gpu_infrastructure_payload.rockpi4c"

READS = [
    ("PWRDN_CON", 0xFF310014),
    ("PWRDN_ST", 0xFF310018),
    ("IDLE_REQ", 0xFF310060),
    ("IDLE_ST", 0xFF310064),
    ("IDLE_ACK", 0xFF310068),
    ("CLKSEL13", 0xFF760134),
    ("CLKGATE13", 0xFF760334),
    ("CLKGATE30", 0xFF760378),
    ("SOFTRST18", 0xFF760448),
]
UART_LSR = 0xFF1A0014
UART_THR = 0xFF1A0000


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
    need("datasection" not in lower and "data.s" not in lower and '"' not in source,
         "payload gained string/data-section telemetry")
    need("$ff9a" not in lower, "payload contains a GPU-aperture address")

    read_positions = []
    for name, address in READS:
        constant = f"$%08x" % address
        need(constant in lower, f"missing {name} address {address:#010x}")
        matches = list(re.finditer(rf"peekl\(#gpu_infra_{name.lower()}\)", lower))
        need(len(matches) == 1, f"{name} must be read exactly once")
        read_positions.append(matches[0].start())
    need(read_positions == sorted(read_positions), "infrastructure read order changed")

    peek_tokens = re.findall(r"peekl\(([^)]+)\)", lower)
    expected_peeks = ["#gpu_infra_uart2_lsr"] + [
        f"#gpu_infra_{name.lower()}" for name, _ in READS
    ]
    need(sorted(set(peek_tokens)) == sorted(expected_peeks),
         f"unexpected MMIO read expression(s): {sorted(set(peek_tokens))}")
    poke_tokens = re.findall(r"pokel\(([^,]+),", lower)
    need(poke_tokens == ["#gpu_infra_uart2_thr"],
         f"unexpected MMIO write expression(s): {poke_tokens}")
    need("#gpu_infra_uart_spins = 1000000" in lower, "UART poll lost its bound")
    for token in ("gpuinfratx(71)", "gpuinfratx(48)",
                  "procedurereturn $47503000 | refusal"):
        need(token in lower, f"wire/return contract lost: {token}")

    print("rockpi4c GPU infrastructure payload contract: PASS")
    print("  load 0x03A4BBD8; GPU aperture absent; PMU/CRU reads fixed")
    print("  sole MMIO write: UART2 THR 0xFF1A0000")
    if args.binary:
        data = args.binary.read_bytes()
        need(len(data) >= 4 and len(data) <= 4 * 1024 * 1024 and len(data) % 4 == 0,
             "binary violates payload extent/alignment")
        print(f"  binary bytes={len(data)} crc32={zlib.crc32(data) & 0xffffffff:08X}")
        print(f"  sha256={hashlib.sha256(data).hexdigest().upper()}")
    if args.assembly:
        constants: dict[str, int] = {}
        reads: list[int] = []
        writes: list[int] = []
        for raw in args.assembly.read_text(encoding="utf-8").splitlines():
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
                address = constants[match.group(2)]
                if address >= 0xF0000000:
                    (reads if match.group(1) == "ldr" else writes).append(address)
                continue
            match = re.match(r"(?:mov|add|sub|and|orr|eor|ldr) (x\d+),", line)
            if match:
                constants.pop(match.group(1), None)
        expected_reads = [UART_LSR] + [address for _, address in READS]
        need(reads == expected_reads,
             f"emitted MMIO reads differ: {[hex(value) for value in reads]}")
        need(writes == [UART_THR],
             f"emitted MMIO writes differ: {[hex(value) for value in writes]}")
        print("  emitted MMIO audit: PASS")
    if args.pmf:
        need(args.binary is not None, "--pmf requires --binary")
        pmf = args.pmf.read_bytes()
        need(len(pmf) == len(data) + 128, "PMF v2 extent differs from flat image")
        need(pmf[:8] == b"PMFBOOT\0", "PMF magic differs")
        version, header_bytes = struct.unpack_from("<II", pmf, 8)
        load, entry, image_bytes, bss_base, bss_bytes = struct.unpack_from(
            "<QQQQQ", pmf, 16)
        flags = struct.unpack_from("<I", pmf, 56)[0]
        arch, target = struct.unpack_from("<II", pmf, 96)
        stack = struct.unpack_from("<Q", pmf, 104)[0]
        need((version, header_bytes) == (2, 128), "PMF is not v2/128")
        need((load, entry, image_bytes) == (0x03A4BBD8, 0x03A4BBD8, len(data)),
             "PMF load, entry or image length differs")
        need((bss_base, bss_bytes, stack) == (0x10000000, 0, 0x12000000),
             "PMF BSS/stack placement differs")
        need(flags == 1 and arch == 1 and target == 3399,
             "PMF is not returning AArch64/RK3399")
        need(pmf[64:96] == hashlib.sha256(data).digest(),
             "PMF embedded image digest differs")
        need(pmf[128:] == data, "PMF payload differs from flat binary")
        print("  PMF v2 placement: load=entry=0x03A4BBD8 "
              "bss=0x10000000+0 stack=0x12000000 flags=returns")
    if args.symbols:
        need(args.binary is not None, "--symbols requires --binary")
        symbols = {}
        for line in args.symbols.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                symbols[name.strip().lower()] = int(value.strip(), 0)
        expected = {
            "__image_start__": 0,
            "__image_end__": len(data),
            "__bss_start__": 0x10000000,
            "__bss_end__": 0x10000000,
            "_start": 0,
        }
        for name, value in expected.items():
            need(symbols.get(name) == value,
                 f"symbol {name} differs: {symbols.get(name)!r}")
        for name in ("gpuinfratx", "gpuinfrahex32", "gpuinfraword", "main"):
            value = symbols.get(name, -1)
            need(0 <= value < len(data) and value % 4 == 0,
                 f"invalid procedure symbol {name}={value}")
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        instructions = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(data, 0x03A4BBD8))
        need(len(instructions) * 4 == len(data), "flat binary is not all A64 instructions")
        adrp_targets = [int(ins.op_str.split("#", 1)[1], 0)
                        for ins in instructions if ins.mnemonic == "adrp"]
        need(adrp_targets == [0x10000000, 0x10000000],
             f"ADRP relocation differs: {[hex(value) for value in adrp_targets]}")
        main_address = 0x03A4BBD8 + symbols["main"]
        need(any(ins.mnemonic == "bl" and
                 int(ins.op_str.lstrip("#"), 0) == main_address
                 for ins in instructions[:32]), "startup BL does not reach linked Main")
        print("  symbols/decoded placement: PASS; ADRP targets 0x10000000")


if __name__ == "__main__":
    main()
