#!/usr/bin/env python3
"""Compile and execute the production VC4 RCL builder in a bounded A64 model."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi3" / "Tests" / "vc4_render_gate.pi3"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0x7000000
EXPECTED_RCL_BYTES = 39
EXPECTED_TARGET_BYTES = 64 * 64 * 4


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_vc4_render_a64", INTERP)
    require(spec is not None and spec.loader is not None, "cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_symbols(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        try:
            out[key.lower()] = int(value, 0)
        except ValueError:
            continue
    return out


def build(compiler: Path, directory: Path):
    image = directory / "vc4-render-gate.img"
    command = [
        str(compiler), "--compile", str(SOURCE), "-t", "pi3",
        "--entry-returns", "--load-addr", hex(LOAD),
        "--stack-addr", hex(STACK), "-s", "-o", str(image),
    ]
    result = subprocess.run(
        command, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True,
    )
    require(result.returncode == 0 and image.is_file(),
            "VC4 render gate compile failed\n" + result.stdout + result.stderr)
    symbols = parse_symbols(Path(str(image) + ".sym"))
    require("main" in symbols, "compiler omitted Main symbol")
    return image.read_bytes(), symbols


def execute(a64, blob: bytes, symbols: dict[str, int]) -> tuple[int, int]:
    bss_lo = symbols.get("__bss_start__")
    bss_hi = symbols.get("__bss_end__")
    require(bss_lo is not None and bss_hi is not None and bss_hi >= bss_lo,
            "compiler omitted a usable BSS range")
    code = (LOAD, LOAD + len(blob))
    bss = (bss_lo, bss_hi)
    stack = (STACK - 0x10000, STACK)

    def allowed(address: int, size: int) -> bool:
        return size > 0 and any(lo <= address and address + size <= hi
                                for lo, hi in (code, bss, stack))

    class Bounded(a64.A64):
        def load(self, address: int, size: int):
            self.align_guard(address, size, False)
            require(allowed(address, size), f"read outside image/BSS/stack at {address:#x}")
            return super().load(address, size)

        def store(self, address: int, value: int, size: int):
            self.align_guard(address, size, True)
            require(bss[0] <= address and address + size <= bss[1] or
                    stack[0] <= address and address + size <= stack[1],
                    f"write outside BSS/stack at {address:#x}")
            return super().store(address, value, size)

    cpu = Bounded()
    cpu.memory.update({LOAD + offset: value for offset, value in enumerate(blob)})
    cpu.pc = LOAD + symbols["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN
    for steps in range(300_000):
        if cpu.pc == RETURN:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError("VC4 builder gate did not return within 300k instructions")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compiler", type=Path,
        default=Path(os.environ.get(
            "PMF_COMPILER",
            r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe",
        )),
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pi3-vc4-render-") as temporary:
        image, symbols = build(args.compiler, Path(temporary))
        result, steps = execute(load_interpreter(), image, symbols)
    require(result == 0, f"production RCL/extent assertions returned {result}")
    print(f"PASS: VC4 production RCL builder; {EXPECTED_RCL_BYTES}-byte RCL, "
          f"{EXPECTED_TARGET_BYTES}-byte target, bounded extents, {steps} A64 steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
