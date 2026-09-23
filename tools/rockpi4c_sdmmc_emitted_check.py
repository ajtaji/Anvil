#!/usr/bin/env python3
"""Run emitted RK3399 DW-MSHC procedures with mocked register MMIO."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "RockPi4C" / "Tests" / "sdmmc_emitted.rockpi4c"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, BSS, STACK, RETURN = 0x02000000, 0x02800000, 0x05000000, 0x06000000
BASE = 0xFE320000
CMD, ARG, RESP0, INTSTS, STATUS, DATA = 0x02C, 0x028, 0x030, 0x044, 0x048, 0x200
CMD_DONE, DTO, RTO, RCRC = 4, 8, 1 << 8, 1 << 6
BUFFER = 0x10000000


def compile_image(compiler: Path, work: Path):
    image = work / "sdmmc-emitted.img"
    result = subprocess.run(
        [str(compiler), "--compile", str(FIXTURE), "-t", "rockpi4c",
         "--board", "Boards/ROCK_Pi_4C.board", "--entry-returns",
         "--load-addr", hex(LOAD), "--bss-addr", hex(BSS),
         "--stack-addr", hex(STACK), "-S", "-o", str(image), "--no-bump"],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True,
    )
    if result.returncode or not image.is_file():
        raise SystemExit("SD/MMC emitted fixture compile failed\n" + result.stdout + result.stderr)
    symfile = Path(str(image) + ".sym")
    if not symfile.is_file():
        raise SystemExit("compiler omitted SD/MMC fixture symbol map")
    symbols = {k.lower(): int(v, 0) for k, v in
               (line.split("=", 1) for line in symfile.read_text().splitlines() if "=" in line)}
    return image.read_bytes(), symbols


def load_a64():
    spec = importlib.util.spec_from_file_location("rockpi4c_sdmmc_a64", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load A64 interpreter: {INTERP}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MockMachine:
    def __init__(self, a64, blob, symbols, *, irq=None, response=None,
                 fifo_word=0x04030201):
        self.cpu = a64.A64()
        self.cpu.memory.update({LOAD + i: b for i, b in enumerate(blob)})
        self.symbols = symbols
        self.original_load, self.original_store = self.cpu.load, self.cpu.store
        self.irq = irq
        self.response = response
        self.fifo_word = fifo_word
        self.commands = []
        self.command_index = -1
        self.irq_reads = 0
        self.data_reads = 0
        self.writes = []
        self.accesses = []
        self.cpu.enable_system_registers(el=3)
        self.cpu.cntpct = 0
        # A short deterministic timebase keeps timeout paths bounded in-model.
        self.cpu.cntpct_per_instruction = 10
        self.put("rock_timer_frequency", 24_000_000)

        def load(address, size):
            if BASE <= address < BASE + 0x1000:
                self.accesses.append(("r", address, size))
                off = address - BASE
                if off == INTSTS:
                    if self.irq is None:
                        return CMD_DONE
                    if isinstance(self.irq, tuple):
                        result = self.irq[min(self.irq_reads, len(self.irq) - 1)]
                        self.irq_reads += 1
                        return result
                    return self.irq
                if off == STATUS:
                    if self.commands and (self.commands[-1] & 0x3F) in (17, 18):
                        return (128 << 17)
                    return 0
                if off == RESP0:
                    if isinstance(self.response, tuple):
                        idx = max(0, min(self.command_index, len(self.response) - 1))
                        return self.response[idx]
                    return self.response or 0
                if off == DATA:
                    self.data_reads += 1
                    return self.fifo_word
                if off == CMD:
                    return 0
            return self.original_load(address, size)

        def store(address, value, size):
            if BASE <= address < BASE + 0x1000:
                value &= 0xFFFFFFFF
                self.accesses.append(("w", address, size))
                self.writes.append((address, value, size))
                off = address - BASE
                if off == CMD:
                    self.commands.append(value)
                    self.command_index += 1
                    self.irq_reads = 0
                return
            self.original_store(address, value, size)

        self.cpu.load, self.cpu.store = load, store

    def put(self, name, value):
        self.cpu.raw_store(self.symbols["global_" + name.lower()], value, 8)

    def get(self, name):
        return self.cpu.raw_load(self.symbols["global_" + name.lower()], 8)

    def call(self, name, *args, limit=500_000):
        self.cpu.pc = LOAD + self.symbols[name.lower()]
        self.cpu.sp, self.cpu.x[30] = STACK, RETURN
        for i in range(8):
            self.cpu.x[i] = args[i] if i < len(args) else 0
        for steps in range(limit):
            if self.cpu.pc == RETURN:
                return self.cpu.x[0], steps
            self.cpu.step()
        raise AssertionError(f"{name} exceeded {limit:,} A64 instructions")


def cases(a64, blob, symbols):
    required = ("rock_sd_command", "rock_sd_r1ok", "rock_sd_carddata", "rocksdflush",
                "rocksdreadblocks", "rocksdwriteblocks",
                "global_rock_timer_frequency", "global_rock_sd_blocks",
                "global_rock_sd_highcapacity", "global_rock_sd_rca", "global_rock_sd_ready")
    missing = [name for name in required if name not in symbols]
    if missing:
        raise SystemExit("compiler omitted SD/MMC model entry points: " + ", ".join(missing))
    total, steps = 0, 0

    # A successful response is surfaced through RESP0 and followed by R1
    # validation. An R1 card error is a completed command but must be refused.
    m = MockMachine(a64, blob, symbols, irq=CMD_DONE, response=0)
    result, n = m.call("rock_sd_command", 13, 0, 0xC0)
    steps += n
    assert result == 1 and m.call("rock_sd_r1ok")[0] == 1
    assert m.get("rock_sd_lastintstatus") == CMD_DONE
    total += 3
    m = MockMachine(a64, blob, symbols, irq=CMD_DONE, response=1 << 31)
    assert m.call("rock_sd_command", 13, 0, 0xC0)[0] == 1
    assert m.call("rock_sd_r1ok")[0] == 0
    assert m.get("rock_sd_lastresponse0") == 1 << 31
    total += 3

    # Hardware RTO and response CRC status bits are command failures, not
    # timeouts; the emitted function preserves the failing raw RINTSTS value.
    for bit in (RTO, RCRC):
        m = MockMachine(a64, blob, symbols, irq=bit)
        result, n = m.call("rock_sd_command", 13, 0, 0xC0)
        steps += n
        assert result == 0 and m.get("rock_sd_lastintstatus") == bit
        total += 2

    # Frozen/no-event command deadline is bounded by the architectural timer.
    m = MockMachine(a64, blob, symbols, irq=0)
    result, n = m.call("rock_sd_command", 13, 0, 0xC0)
    steps += n
    assert result == 0 and n < 500_000
    total += 2

    # A sector read drains all 128 FIFO words, then accepts DTO only after the
    # final word has reached byte 512; data bytes are checked in caller memory.
    m = MockMachine(a64, blob, symbols, irq=(CMD_DONE, 0, DTO), response=0)
    m.put("rock_sd_blocks", 1)
    m.put("rock_sd_highCapacity", 1)
    result, n = m.call("rock_sd_carddata", 17, 0, 1, BUFFER)
    steps += n
    assert result == 1 and m.data_reads == 128, (result, m.data_reads)
    assert bytes(m.cpu.raw_load(BUFFER + i, 1) for i in range(8)) == bytes.fromhex("0102030401020304")
    assert m.get("rock_sd_lastintstatus") == DTO, (m.get("rock_sd_lastintstatus"), m.irq_reads, [c & 0x3F for c in m.commands], m.accesses[-20:])
    total += 4

    # Four contiguous sectors stay one controller request: CMD18 receives all
    # 2048 bytes through the PIO FIFO, then an explicit CMD12 terminates it.
    m = MockMachine(a64, blob, symbols,
                    irq=(CMD_DONE, 0, 0, 0, 0, 0, 0, DTO), response=0)
    m.put("rock_sd_blocks", 4)
    m.put("rock_sd_highCapacity", 1)
    result, n = m.call("rock_sd_carddata", 18, 0, 4, BUFFER, limit=1_500_000)
    steps += n
    assert result == 1 and m.data_reads == 512, (result, m.data_reads, m.irq_reads, [c & 0x3F for c in m.commands], m.get("rock_sd_error"), m.get("rock_sd_lastintstatus"))
    assert [command & 0x3F for command in m.commands] == [18, 12]
    assert bytes(m.cpu.raw_load(BUFFER + i, 1) for i in range(8)) == bytes.fromhex("0102030401020304")
    total += 4

    # CMD13 polling covers a write-busy PRG response followed by ready TRAN.
    m = MockMachine(a64, blob, symbols, irq=CMD_DONE,
                    response=(0x7 << 9, 0x100 | 0x800))
    m.put("rock_sd_ready", 1)
    m.put("rock_sd_rca", 0x1234)
    result, n = m.call("rocksdflush")
    steps += n
    assert result == 1 and len(m.commands) == 2, (result, m.commands)
    assert all((command & 0x3F) == 13 for command in m.commands)
    total += 3

    # Exercise the actual ranged write callback, not just its private PIO
    # helper: CMD24 data leaves the FIFO and CMD13 drains PRG to ready TRAN.
    m = MockMachine(a64, blob, symbols, irq=(CMD_DONE, 0, DTO),
                    response=(0, 0x7 << 9, 0x100 | 0x800))
    m.put("rock_sd_ready", 1)
    m.put("rock_sd_blocks", 1)
    m.put("rock_sd_highCapacity", 1)
    m.put("rock_sd_rca", 0x1234)
    for i in range(512):
        m.cpu.raw_store(BUFFER + i, (i % 4) + 1, 1)
    result, n = m.call("rocksdwriteblocks", 0, 1, BUFFER)
    steps += n
    data_writes = [value for address, value, _ in m.writes if address == BASE + DATA]
    assert result == 1 and len(data_writes) == 128 and data_writes[0] == 0x04030201
    assert [command & 0x3F for command in m.commands] == [24, 13, 13]
    total += 4

    # The ranged callback preserves the same four-sector write as CMD25,
    # explicitly stops it, and waits for the card to return ready/TRAN once.
    m = MockMachine(a64, blob, symbols,
                    irq=(CMD_DONE, 0, 0, 0, 0, DTO),
                    response=(0, 0, 0x100 | 0x800))
    m.put("rock_sd_ready", 1)
    m.put("rock_sd_blocks", 4)
    m.put("rock_sd_highCapacity", 1)
    m.put("rock_sd_rca", 0x1234)
    for i in range(4 * 512):
        m.cpu.raw_store(BUFFER + i, (i % 4) + 1, 1)
    result, n = m.call("rocksdwriteblocks", 0, 4, BUFFER, limit=1_500_000)
    steps += n
    data_writes = [value for address, value, _ in m.writes if address == BASE + DATA]
    assert result == 1 and len(data_writes) == 512 and data_writes[0] == 0x04030201
    assert [command & 0x3F for command in m.commands] == [25, 12, 13]
    total += 4

    # Bounds are checked before any SD-controller MMIO, including arithmetic
    # overflow attempts and empty ranges.
    for lba, count in ((-1, 1), (0, 0), (0x7FFFFFFFFFFFFFFF, 2), (1, 2)):
        m = MockMachine(a64, blob, symbols)
        m.put("rock_sd_ready", 1)
        m.put("rock_sd_blocks", 2)
        result, n = m.call("rocksdreadblocks", lba, count, BUFFER)
        assert result == 0 and not m.accesses, (lba, count, result, m.accesses[:4])
        steps += n
        total += 1
    return total, steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="rockpi4c-sdmmc-") as tmp:
        blob, symbols = compile_image(compiler, Path(tmp))
        total, steps = cases(load_a64(), blob, symbols)
    print(f"PASS: {total} emitted SD/MMC register assertions / {steps:,} A64 instructions")
    print("  command/R1/error/deadline, single and 4-block PIO, CMD12 stop, DTO and CMD13 ready")


if __name__ == "__main__":
    main()
