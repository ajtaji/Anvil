#!/usr/bin/env python3
"""Compile and execute the software Vulkan backend fixture on A64 targets."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Anvil/Graphics/Vulkan/vk_backend_software_test.pi4"
CASES = (("pi3", 0x00400000, 0x08000000),
         ("rockpi4c", 0x02000000, 0x09000000),
         ("unoq", 0x70000000, 0x68000000))
RETURN = 0xDEAD0000


def interpreter():
    path = ROOT / "tools/a64/a64_interp.py"
    spec = importlib.util.spec_from_file_location("anvil_vk_software_a64", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_case(compiler: Path, work: Path, target: str, load: int, stack: int) -> Path:
    image = work / f"vk-software-{target}.img"
    command = [str(compiler), "--compile", str(SOURCE), "-t", target,
               "--load-addr", hex(load), "--stack-addr", hex(stack),
               "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            check=False)
    (work / f"vk-software-{target}.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode or not image.is_file() or "pmfc: OK" not in result.stdout:
        raise RuntimeError(f"{target} compile failed; see {work / f'vk-software-{target}.log'}")
    return image


def run_case(a64, image: Path, load: int, stack: int) -> int:
    symbols = dict(line.split("=", 1) for line in
                   Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines()
                   if "=" in line)
    zero_loop = load + int(symbols["__a64_bss_zero"])
    zero_done = load + int(symbols["__a64_bss_done"])
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[load + offset] = byte
    a64.attach_symbols(cpu, image, load)
    cpu.pc, cpu.sp, cpu.x[30] = load, stack, RETURN
    skipped = False
    for steps in range(8_000_000):
        if cpu.pc == RETURN:
            if not skipped or cpu.x[0] != 0:
                raise RuntimeError(f"{image.name} returned {cpu.x[0]} after {steps} steps")
            return steps
        if cpu.pc == zero_loop:
            # Sparse interpreter memory already reads as zero. Skip only the
            # compiler's 64 MiB zero-fill loop; execute all later startup.
            cpu.pc = zero_done
            skipped = True
        cpu.step()
    raise RuntimeError(f"{image.name} did not return: {cpu.locate(cpu.pc)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--work", type=Path,
                        help="keep images, symbols and compiler logs here")
    args = parser.parse_args()
    a64 = interpreter()

    def check(work: Path) -> None:
        work.mkdir(parents=True, exist_ok=True)
        for target, load, stack in CASES:
            image = compile_case(args.compiler.resolve(), work, target, load, stack)
            steps = run_case(a64, image, load, stack)
            print(f"{target}: software clear, rectangle and triangle pixel checks passed "
                  f"in {steps:,} A64 instructions ({image.stat().st_size:,} image bytes)")

    if args.work:
        check(args.work.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="anvil-vk-software-") as name:
            check(Path(name))
    print("PASS: software backend on Pi 3, ROCK Pi 4C and UNO Q targets (desk only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
