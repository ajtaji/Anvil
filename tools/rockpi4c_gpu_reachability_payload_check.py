#!/usr/bin/env python3
"""Contract and emitted-placement check for the RK3399 Mali reachability payload."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/gpu_reachability_payload.rockpi4c"
LOAD = 0x03A4BBD8
BSS = 0x10000000
STACK = 0x12000000
UART_LSR = 0xFF1A0014
UART_THR = 0xFF1A0000
INFRA_READS = [
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
GPU_READS = [
    ("GPU_ID", 0xFF9A0000),
    ("MMU_FEATURES", 0xFF9A0014),
    ("AS_PRESENT", 0xFF9A0018),
    ("JS_PRESENT", 0xFF9A001C),
    ("GPU_STATUS", 0xFF9A0034),
    ("JOB_INT_JS_STATE", 0xFF9A1010),
    ("MMU_INT_STAT", 0xFF9A200C),
]


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def emitted_mmio(assembly: Path) -> tuple[list[int], list[int]]:
    constants: dict[str, int] = {}
    reads: list[int] = []
    writes: list[int] = []
    for raw in assembly.read_text(encoding="utf-8").splitlines():
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
    return reads, writes


def emulate(data: bytes, infra: dict[int, int]) -> tuple[int, bytes, list[int], list[int]]:
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X0, UC_ARM64_REG_X30

    gpu = {
        0xFF9A0000: 0x08600002,
        0xFF9A0014: 0x00002828,
        0xFF9A0018: 0x000000FF,
        0xFF9A001C: 0x00000007,
        0xFF9A0034: 0x00000000,
        0xFF9A1010: 0x00000000,
        0xFF9A200C: 0x00000000,
    }
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    code_page = LOAD & ~0xFFF
    code_bytes = ((LOAD + len(data) - code_page + 0xFFF) // 0x1000) * 0x1000
    uc.mem_map(code_page, code_bytes)
    uc.mem_write(LOAD, data)
    uc.mem_map(STACK - 0x10000, 0x10000)
    for base, extent in ((0xFF1A0000, 0x1000), (0xFF310000, 0x1000),
                         (0xFF760000, 0x1000), (0xFF9A0000, 0x10000)):
        uc.mem_map(base, extent)
    for address, value in infra.items():
        uc.mem_write(address, struct.pack("<I", value))
    for address, value in gpu.items():
        uc.mem_write(address, struct.pack("<I", value))
    uc.mem_write(UART_LSR, struct.pack("<I", 0x20))

    output = bytearray()
    hardware_reads: list[int] = []
    hardware_writes: list[int] = []

    def on_read(_uc, _access, address, size, _value, _user):
        if address >= 0xF0000000:
            need(size == 4, f"modeled MMIO read width differs at {address:#x}")
            hardware_reads.append(address)

    def on_write(_uc, _access, address, size, value, _user):
        if address >= 0xF0000000:
            need(size == 4, f"modeled MMIO write width differs at {address:#x}")
            hardware_writes.append(address)
            need(address == UART_THR, f"modeled forbidden MMIO write {address:#x}")
            output.append(value & 0xFF)

    uc.hook_add(UC_HOOK_MEM_READ, on_read)
    uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
    return_address = 0x20000000
    uc.reg_write(UC_ARM64_REG_SP, 0x05000000)
    uc.reg_write(UC_ARM64_REG_X30, return_address)
    uc.emu_start(LOAD, return_address, count=2_000_000)
    need(uc.reg_read(UC_ARM64_REG_SP) == 0x05000000,
         "returning startup did not restore caller SP")
    return (uc.reg_read(UC_ARM64_REG_X0), bytes(output), hardware_reads,
            hardware_writes)


def modeled_cases(data: bytes) -> None:
    baseline_values = [
        0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
        0x00008361, 0x00000000, 0x00000000, 0x00000000,
    ]
    baseline = dict(zip((address for _, address in INFRA_READS), baseline_values))
    gpu_values = [0x08600002, 0x00002828, 0x000000FF, 0x00000007,
                  0x00000000, 0x00000000, 0x00000000]
    rc, output, reads, writes = emulate(data, baseline)
    expected = ("G1 " + "".join(f"{value:08X} " for value in baseline_values) +
                "00000000 " + "".join(f"{value:08X} " for value in gpu_values) +
                "00000000\r\n").encode("ascii")
    need(rc == 0x47512000, f"valid modeled return differs: {rc:#x}")
    need(output == expected, "valid modeled positional telemetry differs")
    need([address for address in reads if address != UART_LSR] ==
         [address for _, address in INFRA_READS + GPU_READS],
         "valid modeled MMIO read order differs")
    need(writes == [UART_THR] * len(expected), "valid modeled UART writes differ")

    mutations = [
        (0, 0x00008000, 0), (1, 0x00008000, 1),
        (2, 0x00000001, 2), (3, 0x00000001, 3),
        (4, 0x00000001, 4), (6, 0x00000001, 5),
        (7, 0x00000100, 6), (8, 0x00000007, 7),
        (5, (baseline_values[5] & ~0xE0) | (5 << 5), 8),
    ]
    for value_index, changed, refusal_index in mutations:
        values = list(baseline_values)
        values[value_index] = changed
        state = dict(zip((address for _, address in INFRA_READS), values))
        rc, output, reads, writes = emulate(data, state)
        bit = 1 << refusal_index
        expected = ("G1 " + "".join(f"{value:08X} " for value in values) +
                    f"{bit:08X}\r\n").encode("ascii")
        need(rc == 0x47511000 | bit,
             f"refusal {refusal_index} return differs: {rc:#x}")
        need(output == expected, f"refusal {refusal_index} telemetry differs")
        need([address for address in reads if address != UART_LSR] ==
             [address for _, address in INFRA_READS],
             f"refusal {refusal_index} reached the GPU aperture")
        need(writes == [UART_THR] * len(expected),
             f"refusal {refusal_index} UART writes differ")
    print("  emitted execution model: valid T860 path + 9 causal pre-GPU refusals PASS")


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
    need("pokel(#gpu_reach_uart2_thr" in lower, "UART TX write missing")
    poke_tokens = re.findall(r"pokel\(([^,]+),", lower)
    need(poke_tokens == ["#gpu_reach_uart2_thr"],
         f"unexpected source MMIO writes: {poke_tokens}")

    positions = []
    for name, address in INFRA_READS + GPU_READS:
        need(f"$%08x" % address in lower, f"missing {name} address")
        found = list(re.finditer(rf"peekl\(#gpu_reach_{name.lower()}\)", lower))
        need(len(found) == 1, f"{name} must be read exactly once")
        positions.append(found[0].start())
    need(positions == sorted(positions), "MMIO source order changed")
    first_gpu = lower.index("gpuId=PeekL".lower())
    gate = lower.index("if infrarefusal<>0")
    zero_word = lower.index("if gpureachword(infrarefusal)=0")
    barrier = lower.index("dsb sy", zero_word)
    need(gate < zero_word < barrier < first_gpu,
         "GPU read is not dominated by refusal and barrier")
    peek_tokens = set(re.findall(r"peekl\(([^)]+)\)", lower))
    expected = {"#gpu_reach_uart2_lsr"} | {
        f"#gpu_reach_{name.lower()}" for name, _ in INFRA_READS + GPU_READS
    }
    need(peek_tokens == expected, f"unexpected source MMIO reads: {peek_tokens}")
    need("#gpu_reach_uart_spins = 1000000" in lower, "UART polling is unbounded")

    print("rockpi4c Mali reachability payload source contract: PASS")
    if args.binary:
        data = args.binary.read_bytes()
        need(4 <= len(data) <= 4 * 1024 * 1024 and len(data) % 4 == 0,
             "binary extent/alignment differs")
        print(f"  bytes={len(data)} crc32={zlib.crc32(data) & 0xffffffff:08X}")
        print(f"  sha256={hashlib.sha256(data).hexdigest().upper()}")
        modeled_cases(data)
    if args.assembly:
        reads, writes = emitted_mmio(args.assembly)
        wanted_reads = [UART_LSR] + [address for _, address in INFRA_READS + GPU_READS]
        need(reads == wanted_reads,
             f"emitted MMIO reads differ: {[hex(value) for value in reads]}")
        need(writes == [UART_THR],
             f"emitted MMIO writes differ: {[hex(value) for value in writes]}")
        print("  emitted MMIO allowlist/order: PASS")
    if args.pmf:
        need(args.binary is not None, "--pmf requires --binary")
        pmf = args.pmf.read_bytes()
        need(len(pmf) == len(data) + 128 and pmf[:8] == b"PMFBOOT\0",
             "PMF v2 extent/magic differs")
        version, header_bytes = struct.unpack_from("<II", pmf, 8)
        load, entry, image_bytes, bss_base, bss_bytes = struct.unpack_from(
            "<QQQQQ", pmf, 16)
        flags = struct.unpack_from("<I", pmf, 56)[0]
        arch, target = struct.unpack_from("<II", pmf, 96)
        stack = struct.unpack_from("<Q", pmf, 104)[0]
        need((version, header_bytes) == (2, 128), "PMF is not v2/128")
        need((load, entry, image_bytes) == (LOAD, LOAD, len(data)),
             "PMF load/entry/image extent differs")
        need((bss_base, bss_bytes, stack) == (BSS, 0, STACK),
             "PMF BSS/stack differs")
        need(flags == 1 and arch == 1 and target == 3399,
             "PMF returning AArch64/RK3399 identity differs")
        need(pmf[64:96] == hashlib.sha256(data).digest() and pmf[128:] == data,
             "PMF digest/payload differs")
        print("  PMF v2 placement/digest: PASS")
    if args.symbols:
        need(args.binary is not None, "--symbols requires --binary")
        symbols = {}
        for line in args.symbols.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                symbols[name.strip().lower()] = int(value.strip(), 0)
        for name, value in {
            "__image_start__": 0, "__image_end__": len(data),
            "__bss_start__": BSS, "__bss_end__": BSS, "_start": 0,
        }.items():
            need(symbols.get(name) == value, f"symbol {name} differs")
        for name in ("gpureachtx", "gpureachhex32", "gpureachword",
                     "gpureachnewline", "main"):
            value = symbols.get(name, -1)
            need(0 <= value < len(data) and value % 4 == 0,
                 f"invalid procedure symbol {name}")
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        instructions = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(data, LOAD))
        need(len(instructions) * 4 == len(data), "binary is not wholly A64")
        adrp_targets = [int(ins.op_str.split("#", 1)[1], 0)
                        for ins in instructions if ins.mnemonic == "adrp"]
        need(adrp_targets == [BSS, BSS], "ADRP relocation differs")
        main_address = LOAD + symbols["main"]
        need(any(ins.mnemonic == "bl" and
                 int(ins.op_str.lstrip("#"), 0) == main_address
                 for ins in instructions[:32]), "startup BL misses linked Main")
        print("  symbols/full A64 decode/ADRP/startup BL: PASS")


if __name__ == "__main__":
    main()
