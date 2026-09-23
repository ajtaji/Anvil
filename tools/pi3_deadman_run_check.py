#!/usr/bin/env python3
"""Compile and run exact Pi3 deadman command/RunAt/watchdog bodies."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pi3_gate_build

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi3" / "Tests" / "deadman_run_gate.pi3"
BOARD = ROOT / "RaspberryPi3" / "Board" / "board.pi3"
STUBS = ROOT / "RaspberryPi3" / "Board" / "pi3stubs.pi3"
HW = ROOT / "RaspberryPi3" / "Board" / "hw_board.pi3"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0x7000000


def need(test: bool, message: str) -> None:
    if not test:
        raise AssertionError(message)


def body(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    need(match is not None, f"production {label} body not found in {path}")
    return match.group(0)


def generated_source() -> str:
    gate = GATE.read_text(encoding="utf-8")
    start = body(HW, r"^Procedure\.i Pi3MonDeadmanStart\(seconds\.i\).*?^EndProcedure$", "Pi3MonDeadmanStart")
    stop = body(HW, r"^Procedure\.i Pi3MonDeadmanStop\(\).*?^EndProcedure$", "Pi3MonDeadmanStop")
    refresh = body(HW, r"^Procedure\.i Pi3MonDeadmanRefresh\(seconds\.i\).*?^EndProcedure$", "Pi3MonDeadmanRefresh")
    # The compiler's real PeekL/PokeL intrinsics cannot be redefined as
    # procedures. Redirect only the extracted MMIO calls to the fixture's
    # register model; all production branches and arithmetic stay exact.
    start = re.sub(r"\bPeekL\(", "GatePeekL(", start)
    start = re.sub(r"\bPokeL\(", "GatePokeL(", start)
    stop = re.sub(r"\bPeekL\(", "GatePeekL(", stop)
    stop = re.sub(r"\bPokeL\(", "GatePokeL(", stop)
    refresh = re.sub(r"\bPeekL\(", "GatePeekL(", refresh)
    refresh = re.sub(r"\bPokeL\(", "GatePokeL(", refresh)
    command = body(BOARD, r"^Procedure CmdPi3Deadman\(\).*?^EndProcedure$", "CmdPi3Deadman")
    # Console output is outside the behavior under test; avoid colliding with
    # compiler built-ins while keeping every control-flow branch intact.
    command = re.sub(r"\bPrintN\(", "GatePrintN(", command)
    command = re.sub(r"\bPrintDec\(", "GatePrintDec(", command)
    command = re.sub(r"\bPrint\(", "GatePrint(", command)
    run_at = body(STUBS, r"^Procedure RunAt\(a\.i\).*?^EndProcedure$", "RunAt")
    run_at = re.sub(r"\bPrintN\(", "GatePrintN(", run_at)
    run_at = re.sub(r"\bPrintDec\(", "GatePrintDec(", run_at)
    run_at = re.sub(r"\bPrint\(", "GatePrint(", run_at)
    bodies = "\n\n".join((
        command,
        run_at,
        start,
        stop,
        refresh,
    ))
    need(gate.count(";@@DEADMAN_PROCS@@") == 1,
         "deadman fixture marker missing or duplicated")
    return gate.replace(";@@DEADMAN_PROCS@@", bodies)


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_deadman_a64", INTERP)
    need(spec is not None and spec.loader is not None, "cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_gate(compiler: Path, directory: Path) -> tuple[bytes, dict[str, int]]:
    source = directory / GATE.name
    image = directory / "pi3_deadman_run_gate.img"
    source.write_text(generated_source(), encoding="utf-8")
    command = [str(compiler), "--compile", str(source), "-t", "pi3",
               "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
               hex(STACK), "-s", "-o", str(image)]
    def run_compile() -> None:
        result = subprocess.run(command, cwd=ROOT,
                                env=dict(os.environ, PMF_ROOT=str(ROOT)),
                                capture_output=True, text=True)
        if result.returncode or not image.is_file():
            raise SystemExit("Pi3 deadman emitted gate compile failed\n" +
                             result.stdout + result.stderr)

    # Count only if the compiler's actual input is a production board entry.
    # Here it is the generated isolated fixture in this temporary directory.
    pi3_gate_build.compile_counted(
        run_compile, source, image, compiler=compiler,
        by="pi3_deadman_run_check", root=ROOT)
    syms: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        try:
            syms[name.lower()] = int(value, 0)
        except ValueError:
            pass
    return image.read_bytes(), syms


def run_image(a64, image: bytes, syms: dict[str, int]) -> tuple[int, int]:
    need("main" in syms, "compiler omitted fixture Main")

    class CPU(a64.A64):
        pass

    cpu = CPU()
    for offset, value in enumerate(image):
        cpu.memory[LOAD + offset] = value
    bss_start = syms.get("__bss_start__", 0)
    bss_end = syms.get("__bss_end__", bss_start)
    for address in range(bss_start, bss_end):
        cpu.memory[address] = 0
    cpu.pc = LOAD + syms["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN
    for steps in range(1, 500000):
        if cpu.pc == RETURN:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError("Pi3 deadman gate exceeded 500000 instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    need(compiler.is_file(), f"compiler not found: {compiler}")
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="pi3-deadman-gate-") as temporary:
        image, syms = compile_gate(compiler, Path(temporary))
        result, steps = run_image(a64, image, syms)
    need(result == 0, f"emitted Pi3 deadman assertion {result} failed")
    print(f"PASS: exact Pi3 deadman command/RunAt/watchdog bodies, 29 assertions / {steps:,} A64 instructions")
    print("  external watchdog untouched; failed arm rolls back; entry only after positive arm; only owned stop; command bounds and one-shot consumption")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
