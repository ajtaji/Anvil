#!/usr/bin/env python3
"""Gate the Pi 3 DWC2/LAN9514 foundation without claiming hardware proof."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST_TEST = ROOT / "RaspberryPi3" / "Tests" / "usb_foundation_host.pb"
EMITTED_TEST = ROOT / "RaspberryPi3" / "Tests" / "usb_protocol.pi3"
INTERPRETER = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x02000000
STACK = 0x03000000
ARGS = 0x06000000
RETURN_PC = 0xDEAD0000


def require(path: str, label: str) -> pathlib.Path:
    result = pathlib.Path(path).expanduser().resolve()
    if not result.is_file():
        raise SystemExit(f"Pi 3 USB foundation gate: {label} not found: {result}")
    return result


def run_checked(command: list[str], cwd: pathlib.Path, env=None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            check=False)
    if result.returncode:
        raise SystemExit("Pi 3 USB foundation gate: command failed\n" + result.stdout)
    return result.stdout


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_usb_a64", INTERPRETER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Pi 3 USB foundation gate: cannot load {INTERPRETER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def put64(cpu, address: int, value: int) -> None:
    for offset in range(8):
        cpu.memory[address + offset] = (value >> (offset * 8)) & 0xFF


def execute(a64, image: pathlib.Path, operation: int, values: tuple[int, ...]) -> tuple[int, int]:
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    put64(cpu, ARGS, operation)
    for index, value in enumerate(values):
        put64(cpu, ARGS + 8 + index * 8, value)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    for steps in range(2_000_000):
        if cpu.pc == RETURN_PC:
            return cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise SystemExit(f"Pi 3 USB foundation gate: operation {operation} did not return")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--purebasic", default=os.environ.get("PB_COMPILER") or
                        r"C:\Users\rajta\AppData\Local\Programs\PureBasic\Compilers\pbcompiler.exe")
    args = parser.parse_args()
    if not args.compiler:
        raise SystemExit("Pi 3 USB foundation gate: pass --compiler or set PMF_COMPILER.")
    compiler = require(args.compiler, "unified IDE compiler")
    purebasic = require(args.purebasic, "host PureBasic compiler")

    with tempfile.TemporaryDirectory(prefix="anvil-pi3-usb-") as temp_name:
        temp = pathlib.Path(temp_name)
        host_exe = temp / "usb_foundation_host.exe"
        run_checked([str(purebasic), "/CONSOLE", "/QUIET", "/EXE", str(host_exe),
                     str(HOST_TEST)], ROOT)
        run_checked([str(host_exe)], ROOT)

        image = temp / "usb_protocol.img"
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        run_checked([
            str(compiler), "--compile", str(EMITTED_TEST.relative_to(ROOT)).replace("\\", "/"),
            "-t", "pi3", "--entry-returns", "--load-addr", hex(LOAD),
            "--stack-addr", hex(STACK), "-o", str(image), "-s",
        ], ROOT, env)

        a64 = load_interpreter()
        cases = (
            (1, (7, 0x83, 64), (7 << 22) | (2 << 18) | (3 << 11) | 0x8000 | 64),
            (2, (65535, 512, 2), 65535 | (128 << 19) | (2 << 29)),
            (6, (), 1),
            (7, (1, 0xC0200000, 64), (1 << 64) - 12),
            (8, (0x113F, 0x1000, 0), 0x1111),
            (8, (4, 0x1000, 0), 0x1000),
            (8, (0x1004, 0x100, 0x1000), 0x100),
        )
        total_steps = 0
        for operation, values, expected in cases:
            actual, steps = execute(a64, image, operation, values)
            total_steps += steps
            if actual != expected:
                raise SystemExit(
                    f"Pi 3 USB foundation gate: operation {operation} returned "
                    f"0x{actual:016x}, expected 0x{expected:016x}")

        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        print(f"PASS: host protocol/state cases and {len(cases)} emitted A64 cases; "
              f"{total_steps} instructions")
        print(f"Emitted image: {len(image.read_bytes())} bytes; SHA256 {digest}")
        print(f"Compiler SHA256: {hashlib.sha256(compiler.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
