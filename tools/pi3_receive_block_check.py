#!/usr/bin/env python3
"""Route and emitted-protocol check for Pi3's shared serial `receive`/`b` command."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zlib

import pi3_gate_build

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "RaspberryPi3" / "Board" / "board.pi3"
SOURCE = ROOT / "RaspberryPi3" / "Tests" / "receive_block_gate.pi3"
XFER = ROOT / "Anvil" / "Core" / "xfer.pbi"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0x7000000
CONTROL, STREAM, DEST = 0x06000000, 0x06000100, 0x00500000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def route_source_check() -> int:
    source = BOARD.read_text(encoding="utf-8").lower()
    require('xincludeFile "anvil/core/xfer.pbi"'.lower() in source,
            "board.pi3 does not include the shared serial receiver")
    require('elseif wordis("receive") <> 0 or letteris(98) <> 0' in source,
            "board.pi3 is missing receive/b command dispatch")
    require('cmdblock()' in source, "receive/b route does not call CmdBlock")
    require('elseif wordis("srecord") <> 0 or wordis("loads") <> 0 or letteris(108) <> 0' in source,
            "board.pi3 S-record route/alias is missing")
    require("#cap_net      = 0" in source, "Pi3 network capability unexpectedly enabled")
    return 5


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_receive_a64", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load A64 interpreter {INTERP}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def extract_cmdblock() -> str:
    source = XFER.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^Procedure\s+CmdBlock\(\)\s*\n.*?^EndProcedure\s*$", source)
    require(match is not None, "shared xfer.pbi CmdBlock procedure not found")
    body = match.group(0)
    # Route observable output into fixture sinks while retaining the exact
    # production validation, receive, checksum, and state-update logic.
    names = {"PrintN": "GatePrintN", "PrintNl": "GatePrintNl",
             "PrintDec": "GatePrintDec", "PutAddr": "GatePutAddr",
             "PutHex8": "GatePutHex8", "Print": "GatePrint"}
    lines = []
    for line in body.splitlines():
        call = re.match(r"^(\s*)(PrintN|PrintNl|PrintDec|PutAddr|PutHex8|Print)\s*\(.*\)(\s*(?:;.*)?)$", line)
        if call:
            line = call.group(1) + names[call.group(2)] + "()" + call.group(3)
        lines.append(line)
    body = "\n".join(lines)
    return body


def compile_fixture(compiler: Path, out: Path):
    image = out / "receive-block.img"
    fixture = out / "receive-block.pi3"
    text = SOURCE.read_text(encoding="utf-8")
    marker = ";@@CMD_BLOCK@@"
    require(text.count(marker) == 1, "receive fixture insertion point missing/duplicated")
    fixture.write_text(text.replace(marker, extract_cmdblock()), encoding="utf-8")
    cmd = [str(compiler), "--compile", str(fixture), "-t", "pi3",
           "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
           hex(STACK), "-s", "-o", str(image)]
    def run_compile() -> None:
        result = subprocess.run(cmd, cwd=ROOT,
                                env=dict(os.environ, PMF_ROOT=str(ROOT)),
                                capture_output=True, text=True)
        if result.returncode or not image.is_file():
            raise SystemExit("receive block fixture compile failed\n" + result.stdout + result.stderr)

    # The actual input is a generated Tests fixture, never board.pi3; the
    # shared helper keeps future changes to this command count-aware.
    pi3_gate_build.compile_counted(
        run_compile, fixture, image, compiler=compiler,
        by="pi3_receive_block_check", root=ROOT)
    sym_path = Path(str(image) + ".sym")
    if not sym_path.is_file():
        raise SystemExit("compiler omitted receive block fixture symbols")
    symbols = {k.lower(): int(v, 0) for k, v in
               (line.split("=", 1) for line in sym_path.read_text().splitlines() if "=" in line)}
    return image.read_bytes(), symbols


def write32(memory, address: int, value: int) -> None:
    for i, byte in enumerate((value & 0xFFFFFFFF).to_bytes(4, "little")):
        memory[address + i] = byte


def read32(memory, address: int) -> int:
    return sum(memory.get(address + i, 0) << (8 * i) for i in range(4))


class Run:
    def __init__(self, a64, image: bytes, symbols: dict[str, int], operation: int,
                 payload: bytes, expected_crc: int):
        class CPU(a64.A64):
            pass
        self.cpu = CPU()
        for i, byte in enumerate(image):
            self.cpu.memory[LOAD + i] = byte
        for i in range(0x100):
            self.cpu.memory[CONTROL + i] = 0
        write32(self.cpu.memory, CONTROL, operation)
        write32(self.cpu.memory, CONTROL + 0x10, expected_crc)
        for i, byte in enumerate(payload):
            self.cpu.memory[STREAM + i] = byte
        self.symbols = symbols

    def call(self, limit: int = 2_000_000) -> int:
        self.cpu.pc = LOAD + self.symbols["main"]
        self.cpu.sp = STACK
        self.cpu.x[30] = RETURN
        for step in range(limit):
            if self.cpu.pc == RETURN:
                return step
            self.cpu.step()
        raise AssertionError("CmdBlock fixture exceeded instruction budget")

    def global_value(self, name: str) -> int:
        return read32(self.cpu.memory, self.symbols["global_" + name])


def emitted_cases(a64, image, symbols) -> tuple[int, int]:
    checks = steps = 0
    payload = bytes((i * 37 + 11) & 0xFF for i in range(65))
    want = zlib.crc32(payload) & 0xFFFFFFFF

    success = Run(a64, image, symbols, 1, payload, want)
    steps += success.call()
    require(bytes(success.cpu.memory.get(DEST + i, 0) for i in range(len(payload))) == payload,
            "complete receive did not store every binary byte")
    require(success.global_value("gate_acks") == 17,
            "success acknowledgement cadence differs from b protocol")
    require(success.global_value("gate_flushes") == 1 and
            success.global_value("gbytes") == len(payload) and
            success.global_value("gfail") == 0 and
            success.global_value("gbad") == 0 and
            success.global_value("ghaveentry") == 1,
            "successful receive state/flush is incomplete")
    checks += 3

    timeout = Run(a64, image, symbols, 2, payload, 0)
    steps += timeout.call()
    require(timeout.global_value("gate_acks") == 1 and
            timeout.global_value("gate_printn") > 0,
            "partial receive timeout contract is wrong")
    require(timeout.global_value("gbytes") == 7 and
            timeout.global_value("gfail") == 1 and
            timeout.global_value("ghaveentry") == 0 and
            timeout.global_value("gate_flushes") == 0,
            "partial timeout incorrectly admits or flushes an incomplete image")
    require(bytes(timeout.cpu.memory.get(DEST + i, 0) for i in range(7)) == payload[:7],
            "timeout did not preserve the exact received prefix")
    checks += 3

    mismatch = Run(a64, image, symbols, 3, payload, want)
    steps += mismatch.call()
    require(mismatch.global_value("gbad") == 1 and
            mismatch.global_value("ghaveentry") == 0,
            "CRC mismatch was not refused")
    checks += 1

    overlap = Run(a64, image, symbols, 4, payload, 0)
    steps += overlap.call()
    require(overlap.global_value("gate_rx_calls") == 0 and
            overlap.global_value("gate_acks") == 0 and
            overlap.global_value("gbytes") == 0,
            "monitor-overlapping address was not rejected before transfer")
    checks += 1
    return checks, steps


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", type=Path, required=True)
    args = ap.parse_args()
    compiler = args.compiler.resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    checks = route_source_check()
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-receive-") as tmp:
        image, symbols = compile_fixture(compiler, Path(tmp))
        if "main" not in symbols:
            raise SystemExit("compiler omitted receive fixture Main")
        emitted, steps = emitted_cases(load_interpreter(), image, symbols)
    print(f"PASS: {checks + emitted} Pi3 receive-route/protocol assertions / {steps:,} A64 instructions")
    print("  shared receive/b route; 65-byte binary/CRC success; timeout; checksum refusal; monitor-range refusal")


if __name__ == "__main__":
    main()
