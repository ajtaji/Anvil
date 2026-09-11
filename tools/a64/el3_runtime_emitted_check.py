#!/usr/bin/env python3
"""Compile and execute Anvil's real EL2/EL3 runtime-selection procedures.

This is an emitted-code test, not a silicon MMU model. It proves that one
image reads CurrentEL and selects the matching SCTLR bank. It deliberately
does not claim that writing SCTLR changes translation in the interpreter.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "el3_runtime_emitted_gate.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
OUT = 0x06000000
RETURN_PC = 0xDEAD0000
STEP_LIMIT = 2_000_000

SCTLR_EL2 = 0xD51C1000
SCTLR_EL3 = 0xD51E1000
STUB_SCTLR = 0x30C50830


def required_path(value: str | None, label: str) -> pathlib.Path:
    if not value:
        raise SystemExit("EL3 runtime gate: pass --%s or set %s" %
                         (label.lower(), label))
    path = pathlib.Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit("EL3 runtime gate: %s not found: %s" % (label, path))
    return path


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_el3_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit("EL3 runtime gate: cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(compiler: pathlib.Path, work: pathlib.Path) -> pathlib.Path:
    image = work / "el3_runtime.img"
    cmd = [
        str(compiler), "--compile", str(PROBE.relative_to(ROOT)).replace("\\", "/"),
        "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    result = subprocess.run(
        cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0 or not image.is_file():
        raise SystemExit("EL3 runtime gate: compile failed\n" + result.stdout)
    return image


def u64(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + i, 0) << (8 * i) for i in range(8))


def execute(a64, image: pathlib.Path, el: int, sctlr2: int, sctlr3: int):
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    a64.attach_symbols(cpu, image, LOAD)
    cpu.enable_system_registers(
        el=el, preset={SCTLR_EL2: sctlr2, SCTLR_EL3: sctlr3})
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    for steps in range(STEP_LIMIT):
        if cpu.pc == RETURN_PC:
            values = [u64(cpu, OUT + i * 8) for i in range(7)]
            banks = [cpu.sysreg(SCTLR_EL2), cpu.sysreg(SCTLR_EL3)]
            return values, banks, steps
        cpu.step()
    raise SystemExit("EL3 runtime gate: probe did not return")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP")
                        or str(INTERP))
    args = parser.parse_args()
    compiler = required_path(args.compiler, "PMF_COMPILER")
    interpreter = load_interpreter(required_path(args.interp, "PMF_A64_INTERP"))

    # Bit 0 differs so MmuEnabled independently proves it used the same bank.
    cases = (
        (2, STUB_SCTLR, STUB_SCTLR | 1,
         [2, 0, STUB_SCTLR, 0, 1, STUB_SCTLR | 1, STUB_SCTLR],
         [STUB_SCTLR, STUB_SCTLR | 1]),
        (3, STUB_SCTLR | 1, STUB_SCTLR,
         [3, 1, STUB_SCTLR, 0, 1, STUB_SCTLR | 1, STUB_SCTLR],
         [STUB_SCTLR | 1, STUB_SCTLR]),
        (2, STUB_SCTLR | 1, STUB_SCTLR,
         [2, 0, STUB_SCTLR | 1, 1, 0, STUB_SCTLR | 1, STUB_SCTLR],
         [STUB_SCTLR, STUB_SCTLR]),
        (3, STUB_SCTLR, STUB_SCTLR | 1,
         [3, 1, STUB_SCTLR | 1, 1, 0, STUB_SCTLR | 1, STUB_SCTLR],
         [STUB_SCTLR, STUB_SCTLR]),
    )
    total_steps = 0
    with tempfile.TemporaryDirectory(prefix="anvil-el3-runtime-") as temporary:
        image = build(compiler, pathlib.Path(temporary))
        for el, sctlr2, sctlr3, expected, expected_banks in cases:
            got, banks, steps = execute(interpreter, image, el, sctlr2, sctlr3)
            total_steps += steps
            if got != expected or banks != expected_banks:
                print("el3_runtime_emitted_check: FAIL EL%d values %r/%r "
                      "banks %r/%r" %
                      (el, got, expected, banks, expected_banks))
                return 1
    print("el3_runtime_emitted_check: PASS - 36 checks, %d emitted A64 instructions" %
          total_steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
