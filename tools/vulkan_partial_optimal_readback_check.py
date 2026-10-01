#!/usr/bin/env python3
"""Run the focused public Vulkan optimal-readback rectangle fixture on A64."""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "RaspberryPi4" / "Tests" / "vulkan_partial_optimal_readback_gate.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
RETURN = 0xDEAD0000
MMIO = 0xFC000000
REPORT = 0x06000000


def u64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + index, 0) << (8 * index) for index in range(8))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True, type=pathlib.Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("vpr_a64_interp", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load interpreter: {INTERP}")
    a64 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = a64
    spec.loader.exec_module(a64)

    with tempfile.TemporaryDirectory(prefix="vulkan-partial-readback-") as work:
        image = pathlib.Path(work) / "gate.img"
        command = [str(args.compiler), "--compile", SOURCE.relative_to(ROOT).as_posix(),
                   "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                timeout=120, check=False)
        output = result.stdout + result.stderr
        if result.returncode != 0 or not image.is_file() or "pmfc: OK" not in output:
            raise SystemExit(f"compiler failed (exit {result.returncode}):\n{output}")
        cpu = a64.A64()
        for index, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + index] = byte
        a64.attach_symbols(cpu, image, LOAD)
        cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, RETURN

        def guard(address: int, write: bool) -> None:
            if address >= MMIO:
                kind = "write" if write else "read"
                raise AssertionError(f"unexpected MMIO {kind} at {address:#x}")

        def load(address: int, size: int) -> int:
            cpu.align_guard(address, size, False)
            guard(address, False)
            return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(size))

        def store(address: int, value: int, size: int) -> None:
            cpu.align_guard(address, size, True)
            guard(address, True)
            for i in range(size):
                cpu.memory[address + i] = (value >> (8 * i)) & 0xFF

        cpu.load, cpu.store = load, store
        for steps in range(20_000_000):
            if cpu.pc == RETURN:
                checks, failures = u64(cpu, REPORT), u64(cpu, REPORT + 8)
                if failures or cpu.x[0] or checks < 18:
                    raise SystemExit(f"FAIL: {checks} checks, {failures} failures, x0={cpu.x[0]}")
                print(f"vulkan_partial_optimal_readback_check: PASS - {checks} public-entry checks "
                      f"over {steps:,} executed A64 instructions, no MMIO")
                return 0
            cpu.step()
        raise SystemExit("fixture exceeded 20,000,000 A64 instructions")


if __name__ == "__main__":
    raise SystemExit(main())
