#!/usr/bin/env python3
"""Compile and execute Anvil's resumable PBKDF2/WPA2 known-answer gate."""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "pbkdf2_step_emitted_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
RETURN_PC = 0xDEAD0000
CALIBRATION_LIMIT = 5_000_000
PROGRESS_POLL = 250_000
CAP_SLICES = 600  # 512 WPA slices + 17 RFC slices/noise + conservative margin

CALIBRATION = r'''XIncludeFile "RaspberryPi4/Lib/sha1.pi4"
XIncludeFile "RaspberryPi4/Lib/hmacsha1.pi4"
XIncludeFile "RaspberryPi4/Lib/pbkdf2.pi4"
Global Dim calOut.a[32]
Procedure.i Main()
  Define s.i
  If Wpa2PskStepBegin(?calPw, 8, ?calSsid, 4, @calOut[0]) <> #PBKDF2_STEP_RUNNING
    ProcedureReturn 1
  EndIf
  s = Pbkdf2Step(16)
  If s <> #PBKDF2_STEP_RUNNING : ProcedureReturn 2 : EndIf
  If pbkdf2StepBlock <> 1 Or pbkdf2StepIter <> 16 Or pbkdf2StepOff <> 0
    ProcedureReturn 3
  EndIf
  ProcedureReturn 0
EndProcedure
DataSection
  calPw: Data.a 112,97,115,115,119,111,114,100
  calSsid: Data.a 73,69,69,69
EndDataSection
'''


def required_path(value: str | None, label: str) -> pathlib.Path:
    if not value:
        raise SystemExit(f"PBKDF2 step gate: pass --{label.lower()} or set {label}")
    path = pathlib.Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"PBKDF2 step gate: {label} not found: {path}")
    return path


def load_interpreter(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("anvil_pbkdf2_step_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"PBKDF2 step gate: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_symbols(image: pathlib.Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in pathlib.Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            out[name.strip().lower()] = int(value.strip())
    return out


def u64(memory: dict[int, int], address: int) -> int:
    return sum(memory.get(address + i, 0) << (8 * i) for i in range(8))


def compile_probe(pmfc: pathlib.Path, source: pathlib.Path, image: pathlib.Path) -> None:
    command = [
        str(pmfc), str(source.relative_to(ROOT)).replace("\\", "/") if source.is_relative_to(ROOT) else str(source),
        "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            check=False)
    if result.returncode != 0 or not image.is_file():
        raise SystemExit("PBKDF2 step gate: compile failed\n" + result.stdout)


def fresh_cpu(a64, image: pathlib.Path):
    cpu = a64.A64()
    for offset, byte in enumerate(image.read_bytes()):
        cpu.memory[LOAD + offset] = byte
    symbols = a64.attach_symbols(cpu, image, LOAD)
    cpu.pc = LOAD
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    return cpu, symbols


def execute_bounded(a64, image: pathlib.Path, limit: int) -> tuple[int, int]:
    cpu, _ = fresh_cpu(a64, image)
    for steps in range(limit):
        if cpu.pc == RETURN_PC:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"PBKDF2 step calibration did not return within {limit:,} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    parser.add_argument("--calibrate-only", action="store_true",
                        help="measure one 16-PRF slice and print the derived full-run ceiling")
    args = parser.parse_args()
    pmfc = required_path(args.pmfc, "PMFC")
    a64 = load_interpreter(required_path(args.interp, "PMF_A64_INTERP"))

    with tempfile.TemporaryDirectory(prefix="anvil-pbkdf2-step-") as temporary:
        work = pathlib.Path(temporary)
        calibration_source = work / "pbkdf2_step_calibration.pi4"
        calibration_source.write_text(CALIBRATION, encoding="utf-8", newline="\n")
        calibration_image = work / "pbkdf2_step_calibration.img"
        compile_probe(pmfc, calibration_source, calibration_image)
        calibration_rc, calibration_steps = execute_bounded(a64, calibration_image, CALIBRATION_LIMIT)
        if calibration_rc != 0:
            raise SystemExit(f"PBKDF2 step calibration failed code {calibration_rc}")
        step_limit = calibration_steps * CAP_SLICES
        print("pbkdf2_step_emitted_check: calibration - one 16-PRF WPA slice "
              f"{calibration_steps:,} instructions; justified ceiling {step_limit:,}", flush=True)
        if args.calibrate_only:
            return 0

        image = work / "pbkdf2_step.img"
        compile_probe(pmfc, PROBE, image)
        cpu, symbols = fresh_cpu(a64, image)
        raw_symbols = parse_symbols(image)
        started = time.monotonic()
        last_checkpoint = 0
        for steps in range(step_limit):
            if cpu.pc == RETURN_PC:
                if cpu.x[0] != 0:
                    print(f"pbkdf2_step_emitted_check: FAIL code {cpu.x[0]}")
                    return 1
                print("pbkdf2_step_emitted_check: PASS - 14 assertions, "
                      "RFC257 + IEEE WPA2, 17/512 slices, "
                      f"{steps:,} emitted A64 instructions")
                return 0
            cpu.step()
            if steps and steps % PROGRESS_POLL == 0:
                phase = u64(cpu.memory, raw_symbols["global_stepgatephase"])
                if phase == 2:
                    block = u64(cpu.memory, raw_symbols["global_pbkdf2stepblock"])
                    iteration = u64(cpu.memory, raw_symbols["global_pbkdf2stepiter"])
                    completed = max(0, (block - 1) * 4096 + iteration)
                    checkpoint = completed // (64 * 16)
                    if checkpoint > last_checkpoint:
                        last_checkpoint = checkpoint
                        print("pbkdf2_step_emitted_check: progress - "
                              f"{checkpoint * 64}/512 WPA slices, {steps:,} instructions, "
                              f"{time.monotonic() - started:.1f}s", flush=True)

        state = u64(cpu.memory, raw_symbols["global_pbkdf2stepstate"])
        block = u64(cpu.memory, raw_symbols["global_pbkdf2stepblock"])
        iteration = u64(cpu.memory, raw_symbols["global_pbkdf2stepiter"])
        offset = u64(cpu.memory, raw_symbols["global_pbkdf2stepoff"])
        calls = u64(cpu.memory, raw_symbols["global_stepgatecalls"])
        phase = u64(cpu.memory, raw_symbols["global_stepgatephase"])
        raise SystemExit("PBKDF2 step gate: bounded ceiling exhausted: "
                         f"phase={phase} Main calls={calls} state={state} block={block} "
                         f"iteration={iteration} destination_offset={offset} "
                         f"pc={symbols.where(cpu.pc)} ceiling={step_limit:,}")


if __name__ == "__main__":
    raise SystemExit(main())
