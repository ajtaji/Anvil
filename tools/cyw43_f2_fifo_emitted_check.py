#!/usr/bin/env python3
"""Compile and execute the CYW43 function-2 fixed-FIFO transfer gate."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "cyw43_f2_fifo_emitted_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 8_000_000


def required_path(value: str | None, env_name: str) -> Path:
    if not value:
        raise SystemExit(f"cyw43 F2 FIFO gate: set {env_name} or pass its option")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"cyw43 F2 FIFO gate: {env_name} file not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_cyw43_f2_fifo_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cyw43 F2 FIFO gate: cannot load interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def symbol_bounds(sym_path: Path) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in sym_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, raw = line.split("=", 1)
        if name in ("__bss_start__", "__bss_end__"):
            values[name] = int(raw, 0)
    try:
        return values["__bss_start__"], values["__bss_end__"]
    except KeyError as exc:
        raise SystemExit("cyw43 F2 FIFO gate: compiler symbol map has no BSS bounds") from exc


def build(compiler: Path, work: Path) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    image = work / "cyw43_f2_fifo_gate.img"
    command = [str(staged), "--compile", PROBE.relative_to(ROOT).as_posix(), "-t", "pi4",
               "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(command, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("cyw43 F2 FIFO gate: compile failed\n" + run.stdout)
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit("cyw43 F2 FIFO gate: compiler omitted image or symbol map")
    return image


def execute(a64, image: Path) -> tuple[int, int]:
    blob = image.read_bytes()
    bss_lo, bss_hi = symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    image_range = (LOAD, LOAD + len(blob))
    bss_range = (bss_lo, bss_hi)
    stack_range = (STACK - STACK_BYTES, STACK + 16)
    readable = (image_range, bss_range, stack_range)
    writable = (bss_range, stack_range)

    def contains(ranges: tuple[tuple[int, int], ...], addr: int, size: int) -> bool:
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if not contains(readable, addr, size):
            raise SystemExit(f"cyw43 F2 FIFO gate: read outside image/BSS/stack at ${addr:08X}+{size}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if not contains(writable, addr, size):
            raise SystemExit(f"cyw43 F2 FIFO gate: write outside BSS/stack at ${addr:08X}+{size}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"cyw43 F2 FIFO gate: no return in {STEP_LIMIT} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = required_path(args.interp, "PMF_A64_INTERP")
    a64 = load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-cyw43-f2-fifo-") as temporary:
        image = build(compiler, Path(temporary))
        result, steps = execute(a64, image)
    if result:
        print(f"cyw43_f2_fifo_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"cyw43_f2_fifo_emitted_check: PASS - 21 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
