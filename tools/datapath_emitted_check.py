#!/usr/bin/env python3
"""Build and execute the data:/ path-resolution gate (Anvil/Core/datapath.pbi)."""
from __future__ import annotations
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "datapath_emitted_gate.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x400000
STACK = 0x3000000


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_datapath_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"datapath gate: cannot load interpreter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def symbols(path: Path) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, raw = line.split("=", 1)
            if name in ("__bss_start__", "__bss_end__"):
                values[name] = int(raw, 0)
    return values["__bss_start__"], values["__bss_end__"]


def build(compiler: Path, work: Path) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    shutil.copytree(ROOT / "Boards", work / "Boards")
    image = work / "datapath_gate.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [str(staged), "--compile", str(PROBE), "-t", "pi4",
               "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
               "--entry-returns", "-o", str(image), "-s"]
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or not image.is_file() or "COMPILER ERROR" in run.stdout:
        raise SystemExit("datapath gate: compile failed\n" + run.stdout)
    return image


def execute(a64, image: Path) -> tuple[int, int]:
    blob = image.read_bytes()
    bss_lo, bss_hi = symbols(image.with_suffix(image.suffix + ".sym"))
    ranges = ((LOAD, LOAD + len(blob)), (bss_lo, bss_hi), (STACK - 0x100000, STACK + 16))
    writable = ((bss_lo, bss_hi), (STACK - 0x100000, STACK + 16))
    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = 0x7FFF0000

    def within(rs, addr, size):
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in rs)

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if not within(ranges, addr, size):
            raise SystemExit(f"datapath gate: read escaped admitted memory at ${addr:X}+{size}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if not within(writable, addr, size):
            raise SystemExit(f"datapath gate: write escaped admitted memory at ${addr:X}+{size}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    limit = 20_000_000
    for step in range(limit):
        if cpu.pc == 0x7FFF0000:
            return cpu.x[0], step
        cpu.step()
    raise SystemExit(f"datapath gate: no return within {limit:,} emitted instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=str(INTERP))
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        raise SystemExit("datapath gate: pass --compiler or set PMF_COMPILER")
    compiler = Path(args.compiler).resolve()
    interp = Path(args.interp).resolve()
    with tempfile.TemporaryDirectory(prefix="anvil-datapath-") as td:
        image = build(compiler, Path(td))
        result, steps = execute(load_interpreter(interp), image)
    if result:
        print(f"datapath_emitted_check: FAIL case {result} after {steps:,} emitted A64 instructions")
        return 1
    print(f"datapath_emitted_check: PASS - 10 cases in {steps:,} emitted A64 instructions")
    print("  default and unset data.path are partition 1's root; set to 2:/ joins with one")
    print("  separator; spaces kept; other paths untouched; self-reference and overflow refused")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
