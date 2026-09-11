#!/usr/bin/env python3
"""Compile and execute the optional CYW43 receive-readiness telemetry gate."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Tests" / "cyw43_rx_readiness_emitted_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000
STEP_LIMIT = 8_000_000


def required_path(value: str | None, env_name: str) -> Path:
    if not value:
        raise SystemExit(f"CYW43 readiness gate: set {env_name} or pass its option")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"CYW43 readiness gate: {env_name} file not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_cyw43_ready_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"CYW43 readiness gate: cannot load interpreter: {path}")
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
        raise SystemExit("CYW43 readiness gate: compiler symbol map has no BSS bounds") from exc


def build(compiler: Path, work: Path, source_root: Path = ROOT, probe: Path = PROBE) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir():
        shutil.copytree(boards, work / "Boards")
    image = work / "cyw43_rx_readiness_gate.img"
    command = [
        str(staged), "--compile", probe.relative_to(source_root).as_posix(), "-t", "pi4",
        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
        "--entry-returns", "-o", str(image), "-s",
    ]
    env = os.environ.copy()
    env["PMF_ROOT"] = str(source_root)
    run = subprocess.run(
        command, cwd=source_root, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("CYW43 readiness gate: compile failed\n" + run.stdout)
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit("CYW43 readiness gate: compiler omitted image or symbol map")
    return image


def procedure_bounds(source: str, name: str) -> tuple[int, int]:
    marker = f"Procedure.i {name}("
    first = source.find(marker)
    if first < 0:
        raise SystemExit(f"CYW43 readiness gate: procedure {name} not found")
    last = source.find("\nEndProcedure", first)
    if last < 0:
        raise SystemExit(f"CYW43 readiness gate: procedure {name} has no end")
    return first, last + len("\nEndProcedure")


def build_guard_mutant(compiler: Path, work: Path, name: str) -> Path:
    root = work / f"{name.lower()}-mutant"
    lib = root / "RaspberryPi4" / "Lib"
    tests = root / "RaspberryPi4" / "Tests"
    lib.mkdir(parents=True)
    tests.mkdir(parents=True)
    shutil.copy2(ROOT / "keywords.def", root / "keywords.def")
    shutil.copytree(
        ROOT / "RaspberryPi4" / "Intrinsics",
        root / "RaspberryPi4" / "Intrinsics",
    )
    source_path = ROOT / "RaspberryPi4" / "Lib" / "cyw43.pi4"
    source = source_path.read_text(encoding="utf-8")
    first, last = procedure_bounds(source, name)
    body = source[first:last]
    old = "If cyw43_RxIrqGenerationOwned() <> 0"
    if body.count(old) != 1:
        raise SystemExit(
            f"CYW43 readiness gate: mutant {name} expected one guard, "
            f"found {body.count(old)}"
        )
    body = body.replace(old, "If 0 <> 0", 1)
    source = source[:first] + body + source[last:]
    (lib / "cyw43.pi4").write_text(source, encoding="utf-8", newline="\n")
    shutil.copy2(ROOT / "RaspberryPi4" / "Lib" / "cyw43_rx_glom.pi4", lib)
    probe = tests / PROBE.name
    shutil.copy2(PROBE, probe)
    return build(compiler, root, root, probe)

def build_busy_mutant(compiler: Path, work: Path) -> Path:
    """The observer without its re-entry guard.

    The probe cannot observe from inside the callback - that is a loop
    through the operation pointer and the backend refuses it - so the
    guard is killed from the other end: with the test gone, the gate's
    hand-armed observation walks straight into the device operations
    instead of being counted as nested and returning zero.
    """
    root = work / "busy-mutant"
    lib = root / "RaspberryPi4" / "Lib"; tests = root / "RaspberryPi4" / "Tests"
    lib.mkdir(parents=True); tests.mkdir(parents=True)
    shutil.copy2(ROOT / "keywords.def", root / "keywords.def")
    shutil.copytree(ROOT / "RaspberryPi4" / "Intrinsics", root / "RaspberryPi4" / "Intrinsics")
    source = (ROOT / "RaspberryPi4/Lib/cyw43.pi4").read_text(encoding="utf-8")
    old = "  If cyw43_rxIrqBusy <> 0"
    if source.count(old) != 1:
        raise SystemExit("CYW43 readiness gate: re-entry guard mutation site drifted")
    (lib / "cyw43.pi4").write_text(source.replace(old, "  If 0 <> 0", 1), encoding="utf-8", newline="\n")
    shutil.copy2(ROOT / "RaspberryPi4/Lib/cyw43_rx_glom.pi4", lib)
    probe = tests / PROBE.name; shutil.copy2(PROBE, probe)
    return build(compiler, root, root, probe)


# THE SCRATCH MUTATION GIVES THE QUIET CLASSIFICATION A LIFE LONGER THAN ONE
# CALL. It used to be "delete the `quietNonempty = 0` reset", and on 2026-09-11
# that stopped being a defect anybody can write: automatic storage moved into
# the invocation's own frame, so a value cannot survive a return and deleting
# the reset changes nothing this probe can observe. A negative control that
# cannot fail is not a control - it is a permanent red that teaches nothing.
#
# What checks 98 and 100 actually refuse is a classification that is SHARED
# between calls, so that is what the mutation builds: file-scope storage and no
# per-call reset, which is what this scratch would look like if somebody moved
# it out of the procedure. Verified to be caught, and to be caught for the
# right reason - the mutant returns 98, the queued frame inheriting the
# preceding wire frame's quiet classification.
SCRATCH_MUTATION = (
    ("Global cyw43_rxIrqPrevNext.i = 0",
     "Global cyw43_rxIrqPrevNext.i = 0\nGlobal quietNonempty.i = 0"),
    ("  Define quietNonempty.i\n", ""),
    ("  quietNonempty = 0\n", ""),
)


def build_scratch_mutant(compiler: Path, work: Path) -> Path:
    root = work / "scratch-mutant"
    lib = root / "RaspberryPi4" / "Lib"; tests = root / "RaspberryPi4" / "Tests"
    lib.mkdir(parents=True); tests.mkdir(parents=True)
    shutil.copy2(ROOT / "keywords.def", root / "keywords.def")
    shutil.copytree(ROOT / "RaspberryPi4" / "Intrinsics", root / "RaspberryPi4" / "Intrinsics")
    source = (ROOT / "RaspberryPi4/Lib/cyw43.pi4").read_text(encoding="utf-8")
    for old, new in SCRATCH_MUTATION:
        if source.count(old) != 1:
            raise SystemExit(
                "CYW43 readiness gate: scratch mutation site drifted: " + old.strip())
        source = source.replace(old, new, 1)
    (lib / "cyw43.pi4").write_text(source, encoding="utf-8", newline="\n")
    shutil.copy2(ROOT / "RaspberryPi4/Lib/cyw43_rx_glom.pi4", lib)
    probe = tests / PROBE.name; shutil.copy2(PROBE, probe)
    return build(compiler, root, root, probe)


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
            raise SystemExit(
                f"CYW43 readiness gate: read outside image/BSS/stack at ${addr:08X}+{size}"
            )
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if not contains(writable, addr, size):
            raise SystemExit(
                f"CYW43 readiness gate: write outside BSS/stack at ${addr:08X}+{size}"
            )
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    ticks = 0
    plain_step = a64.A64.step.__get__(cpu)
    for steps in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu.x[0], steps
        ticks += 1
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:  # mrs Xt,cntfrq_el0
            cpu.x[ins & 31] = 54_000_000
            cpu.pc += 4
        elif (ins & 0xFFFFFFE0) == 0xD53BE020:  # mrs Xt,cntpct_el0
            cpu.x[ins & 31] = ticks
            cpu.pc += 4
        else:
            plain_step()
    raise SystemExit(f"CYW43 readiness gate: no return in {STEP_LIMIT} instructions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = required_path(args.compiler, "PMF_COMPILER")
    interp = required_path(args.interp, "PMF_A64_INTERP")
    a64 = load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-cyw43-ready-") as temporary:
        work = Path(temporary)
        image = build(compiler, work)
        result, steps = execute(a64, image)
        expected = {
            "Cyw43EnumerateCores": 81,
            "Cyw43ReadRamInfo": 82,
            "Cyw43UploadFirmware": 83,
            "Cyw43UploadNvram": 84,
        }
        mutant_steps = 0
        for name, want in expected.items():
            mutant = build_guard_mutant(compiler, work, name)
            mutant_result, used = execute(a64, mutant)
            mutant_steps += used
            if mutant_result != want:
                print(
                    f"cyw43_rx_readiness_emitted_check: FAIL {name} guard "
                    f"mutant returned {mutant_result}, expected {want}"
                )
                return 1
        scratch = build_scratch_mutant(compiler, work)
        scratch_result, scratch_steps = execute(a64, scratch)
        if scratch_result == 0:
            print("cyw43_rx_readiness_emitted_check: FAIL shared-scratch mutant survived")
            return 1
        busy = build_busy_mutant(compiler, work)
        busy_result, busy_steps = execute(a64, busy)
        if busy_result != 106:
            print(
                "cyw43_rx_readiness_emitted_check: FAIL re-entry guard mutant "
                f"returned {busy_result}, expected 106"
            )
            return 1
    if result:
        print(
            f"cyw43_rx_readiness_emitted_check: FAIL assertion {result} "
            f"after {steps:,} A64 instructions"
        )
        return 1
    print(
        f"cyw43_rx_readiness_emitted_check: PASS - 111 labeled assertions, "
        f"{steps:,} A64 instructions; four generation-guard mutants, the "
        f"shared-scratch mutant and the re-entry-guard mutant rejected in "
        f"{mutant_steps + scratch_steps + busy_steps:,} instructions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
