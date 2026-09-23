#!/usr/bin/env python3
"""Compile and execute the real PBKDF2 progress/KAT probe in Anvil's A64 model."""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "pbkdf2_progress_emitted_gate.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
RETURN_PC = 0xDEAD0000
STEP_LIMIT = 70_000_000


def required_path(value: str | None, label: str) -> pathlib.Path:
    if not value:
        raise SystemExit("PBKDF2 progress gate: pass --%s or set %s" %
                         (label.lower(), label))
    path = pathlib.Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit("PBKDF2 progress gate: %s not found: %s" % (label, path))
    return path


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_pbkdf2_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit("PBKDF2 progress gate: cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP")
                        or str(INTERP))
    args = parser.parse_args()
    compiler = required_path(args.compiler, "PMF_COMPILER")
    a64 = load_interpreter(required_path(args.interp, "PMF_A64_INTERP"))

    with tempfile.TemporaryDirectory(prefix="anvil-pbkdf2-progress-") as temporary:
        image = pathlib.Path(temporary) / "pbkdf2_progress.img"
        command = [
            str(compiler), "--compile", str(PROBE.relative_to(ROOT)).replace("\\", "/"),
            "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
            "--entry-returns", "-o", str(image), "-s",
        ]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(ROOT)
        result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        if result.returncode != 0 or not image.is_file():
            raise SystemExit("PBKDF2 progress gate: compile failed\n" + result.stdout)

        cpu = a64.A64()
        for offset, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + offset] = byte
        a64.attach_symbols(cpu, image, LOAD)
        cpu.pc = LOAD
        cpu.sp = STACK
        cpu.x[30] = RETURN_PC
        for steps in range(STEP_LIMIT):
            if cpu.pc == RETURN_PC:
                if cpu.x[0] != 0:
                    print("pbkdf2_progress_emitted_check: FAIL code %d" % cpu.x[0])
                    return 1
                print("pbkdf2_progress_emitted_check: PASS - known answer, "
                      "identical callback output, exact 2/257 cadence; "
                      "%d emitted A64 instructions" % steps)
                return 0
            cpu.step()
    raise SystemExit("PBKDF2 progress gate: probe did not return within %d instructions"
                     % STEP_LIMIT)


if __name__ == "__main__":
    raise SystemExit(main())
