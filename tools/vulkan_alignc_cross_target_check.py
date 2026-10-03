#!/usr/bin/env python3
"""Check Vulkan C-layout ABI and no-backend linking on AArch64 boards."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "Anvil" / "Graphics" / "Vulkan" / "Tests"
CASES = (("pi3", 0x00400000, 0x03000000),
         ("rockpi4c", 0x02000000, 0x05000000),
         ("pi4", 0x00400000, 0x03000000),
         ("unoq", 0x70000000, 0x68000000))
RETURN_ADDRESS = 0xDEAD0000


def interpreter():
    path = ROOT / "tools" / "a64" / "a64_interp.py"
    spec = importlib.util.spec_from_file_location("anvil_alignc_a64", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load AArch64 interpreter: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_case(compiler: Path, work: Path, source: Path, target: str,
                 load: int | None = None, stack: int | None = None,
                 pmf_root: Path = ROOT):
    stem = f"{source.stem}_{target}"
    image = work / f"{stem}.img"
    log = work / f"{stem}.log"
    if image.exists():
        image.unlink()
    command = [str(compiler), "--compile", str(source), "-t", target]
    if load is not None and stack is not None:
        command += ["--load-addr", hex(load), "--stack-addr", hex(stack),
                    "--entry-returns"]
    command += ["-o", str(image), "-s"]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(pmf_root)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            check=False)
    log.write_text(result.stdout, encoding="utf-8")
    return result.returncode, image, result.stdout


def run_a64(a64, image: Path, load: int, stack: int,
            max_steps: int = 100_000) -> tuple[int, int]:
    cpu = a64.A64()
    for index, byte in enumerate(image.read_bytes()):
        cpu.memory[load + index] = byte
    a64.attach_symbols(cpu, image, load)
    cpu.pc, cpu.sp, cpu.x[30] = load, stack, RETURN_ADDRESS
    for steps in range(max_steps):
        if cpu.pc == RETURN_ADDRESS:
            return cpu.x[0] & 0xFFFFFFFFFFFFFFFF, steps
        cpu.step()
    raise RuntimeError(f"{image.name} did not return in {max_steps:,} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--compiler-root", type=Path,
                        help="Compiler install root holding non-AArch64 intrinsics")
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    a64 = interpreter()
    count = 0
    for target, load, stack in CASES:
        source = TESTS / f"vulkan_alignc_abi.{target}"
        code, image, output = compile_case(args.compiler, args.work, source,
                                           target, load, stack)
        if code or not image.is_file() or "pmfc: OK" not in output:
            raise RuntimeError(f"{target} ABI compile failed; see {image.with_suffix('.log')}")
        result, steps = run_a64(a64, image, load, stack)
        if result:
            raise RuntimeError(f"{target} Vulkan ABI check {result} failed")
        print(f"{target}: 12 Vulkan size/offset checks passed in {steps} A64 instructions")
        count += 12

        if target != "pi4":
            source = TESTS / f"vulkan_none_{target}.{target}"
            code, image, output = compile_case(args.compiler, args.work,
                                               source, target, load, stack)
            if code or not image.is_file() or "pmfc: OK" not in output:
                raise RuntimeError(f"{target} no-backend link failed; see {image.with_suffix('.log')}")
            print(f"{target}: no-backend API compiled and linked ({image.stat().st_size} bytes)")
            count += 1
            if target in ("pi3", "unoq"):
                result, steps = run_a64(a64, image, load, stack, 5_000_000)
                if result:
                    raise RuntimeError(f"{target} no-backend returned {result}; expected incompatible driver")
                print(f"{target}: no-backend API refused device in {steps} A64 instructions")
                count += 1

    source = TESTS / "vulkan_alignc_negative.pico2"
    code, image, output = compile_case(args.compiler, args.work, source,
                                       "rp2350", pmf_root=args.compiler_root or args.compiler.parent)
    if code == 0 or image.exists() or "#PB_Structure_AlignC currently requires an AArch64 target" not in output:
        raise RuntimeError("pico2 did not reject AlignC with the expected diagnostic")
    print("pico2: non-AArch64 AlignC refusal passed")
    count += 1
    print(f"PASS: {count} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
