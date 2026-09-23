#!/usr/bin/env python3
"""Exact emitted-code gate for the Pi 4 V3D cache batch owner layer.

The canonical compiler builds the production v3d.pi4 through the isolated
gate. The A64 interpreter observes DC CIVAC and DSB/ISB; no instruction may
touch MMIO. Mutants must be rejected by the same exact trace and result
oracle. This is a desk gate and makes no hardware claim.
"""
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
GATE = ROOT / "RaspberryPi4/Tests/v3d_cache_batch_emitted_gate.pi4"
CORE = ROOT / "RaspberryPi4/Lib/v3d.pi4"
LIBS = ("uart.pi4", "timer.pi4", "safety.pi4", "mailbox.pi4", "v3dqpu.pi4", "v3d.pi4")
LOAD, BSS, STACK, STACK_BYTES = 0x400000, 0x800000, 0x3000000, 0x10000
RETURN = 0xDEAD0000
MASK = (1 << 64) - 1

EXPECTED_RESULTS = (1, 1, 1, 1, 3, 1, 0, MASK, 1, 1, 1, 0, MASK,
                    1, 0, MASK, 1, 0, MASK)
EXPECTED_EVENTS = (
    ("civac", 0x00100000), ("civac", 0x00100040),
    ("civac", 0x00100100), ("civac", 0x100000040),
    ("dsb sy", None), ("isb", None),
    ("civac", 0), ("dsb sy", None), ("isb", None),
    ("civac", 0x00100200), ("civac", 0x00100240),
    ("dsb sy", None), ("isb", None),
)

MUTANTS = (
    ("a batch pays a barrier for every range",
     "  V3dCacheLines(addr, len)\n  v3d_cacheBatchRanges = v3d_cacheBatchRanges + 1",
     "  V3dCacheLines(addr, len)\n  V3dBarrier()\n  v3d_cacheBatchRanges = v3d_cacheBatchRanges + 1"),
    ("batch completion loses its only barrier",
     "  If ranges > 0\n    V3dBarrier()\n  EndIf",
     "  If ranges > 0\n    ; mutation removed completion\n  EndIf"),
    ("the full-width cache-walk end is truncated",
     "    ldr  x10, [x10]\n    cmp  x9, x10",
     "    ldr  w10, [x10]\n    cmp  x9, x10"),
    ("wrapped exclusive ends are accepted",
     "  If e <= addr\n    v3d_cacheBatchValid = 0",
     "  If e = addr\n    v3d_cacheBatchValid = 0"),
    ("a poisoned transaction reports success",
     "  If valid = 0\n    ProcedureReturn -1\n  EndIf",
     "  If valid < 0\n    ProcedureReturn -1\n  EndIf"),
    ("the legacy one-range API loses its barrier",
     "    a = a + #V3D_CACHE_LINE\n  Wend\n  V3dBarrier()\nEndProcedure\n\n; ----------------------------------------------------------------------\n;  V3dCacheBatchBegin",
     "    a = a + #V3D_CACHE_LINE\n  Wend\nEndProcedure\n\n; ----------------------------------------------------------------------\n;  V3dCacheBatchBegin"),
)


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("a64_interp", path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load A64 interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor is not unique: " + old.splitlines()[0])
    return text.replace(old, new, 1)


def build(compiler: Path, work: Path, name: str, core_text: str):
    root = work / name
    libdir = root / "RaspberryPi4/Lib"
    testdir = root / "RaspberryPi4/Tests"
    core_dir = root / "Anvil/Core"
    libdir.mkdir(parents=True)
    testdir.mkdir(parents=True)
    core_dir.mkdir(parents=True)
    for item in LIBS:
        source = ROOT / "RaspberryPi4/Lib" / item
        (libdir / item).write_text(core_text if item == "v3d.pi4" else source.read_text(encoding="utf-8-sig"), encoding="utf-8")
    shutil.copy2(GATE, testdir / GATE.name)
    shutil.copy2(ROOT / "Anvil/Core/console_style.pbi", core_dir / "console_style.pbi")
    image = root / (name + ".img")
    result = subprocess.run([
        str(compiler), "--compile", str(testdir / GATE.name), "-t", "pi4", "-s",
        "--entry-returns", "--load-addr", hex(LOAD), "--bss-addr", hex(BSS),
        "--stack-addr", hex(STACK), "-o", str(image),
    ], cwd=root, capture_output=True, text=True, timeout=120)
    if result.returncode or not image.is_file():
        raise AssertionError(name + " compile failed\n" + result.stdout + result.stderr)
    symbols = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            symbols[key.strip().lower()] = int(value.strip(), 0)
    entries = {}
    for line in Path(str(image) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("|")
        if len(fields) >= 4 and fields[0] == "1" and fields[1].isdigit():
            entries[fields[2].lower()] = LOAD + int(fields[1])
    if "main" not in entries or "global_vcbresult" not in symbols:
        raise AssertionError("missing exact emitted entry/result symbols")
    return image.read_bytes(), symbols, entries


class GuardError(RuntimeError):
    pass


def execute(a64, product):
    blob, symbols, entries = product
    bss = (symbols["__bss_start__"], symbols["__bss_end__"])
    code = (LOAD, LOAD + len(blob))
    stack = (STACK - STACK_BYTES, STACK)
    events = []

    def contains(spans, addr, size):
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in spans)

    class Observed(a64.A64):
        def fetch(self, addr):
            if addr & 3 or not contains((code,), addr, 4):
                raise GuardError("instruction fetch outside exact image")
            return super().fetch(addr)

        def load(self, addr, size):
            self.align_guard(addr, size, False)
            if not contains((code, bss, stack), addr, size):
                raise GuardError(f"data read outside image/BSS/stack: {addr:#x}")
            return super().load(addr, size)

        def store(self, addr, value, size):
            self.align_guard(addr, size, True)
            if not contains((bss, stack), addr, size):
                raise GuardError(f"data write outside BSS/stack: {addr:#x}")
            return super().store(addr, value, size)

        def step(self):
            ins = self.fetch(self.pc)
            if ins & 0xFFF80000 == 0xD5080000:
                key = (((ins >> 16) & 7) << 12 | ((ins >> 12) & 15) << 8 |
                       ((ins >> 8) & 15) << 4 | (ins >> 5) & 7)
                if key != 0x37E1:
                    raise AssertionError(f"unexpected SYS maintenance operation {key:#x}")
                events.append(("civac", self.x[ins & 31]))
            elif ins == 0xD5033F9F:
                events.append(("dsb sy", None))
            elif ins == 0xD5033FDF:
                events.append(("isb", None))
            super().step()

    cpu = Observed()
    cpu.memory = {LOAD + i: byte for i, byte in enumerate(blob)}
    cpu.sp, cpu.pc, cpu.x[30] = STACK, entries["main"], RETURN
    for steps in range(2_000_000):
        if cpu.pc == RETURN:
            break
        cpu.step()
    else:
        raise AssertionError("emitted gate failed to return")
    result_base = symbols["global_vcbresult"]
    results = tuple(cpu.load(result_base + i * 8, 8) for i in range(len(EXPECTED_RESULTS)))
    return tuple(events), results, steps


def oracle(a64, product):
    events, results, steps = execute(a64, product)
    if events != EXPECTED_EVENTS:
        raise AssertionError("maintenance/barrier trace differs\nexpected=" + repr(EXPECTED_EVENTS) + "\nactual=" + repr(events))
    if results != EXPECTED_RESULTS:
        raise AssertionError("batch result vector differs\nexpected=" + repr(EXPECTED_RESULTS) + "\nactual=" + repr(results))
    return steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", type=Path, default=Path(os.environ.get("PMF_COMPILER", r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")))
    parser.add_argument("--interpreter", type=Path, default=ROOT / "tools/a64/a64_interp.py")
    parser.add_argument("--no-mutate", action="store_true")
    args = parser.parse_args()
    core = CORE.read_text(encoding="utf-8-sig")
    a64 = load_interpreter(args.interpreter)
    checks = 0
    with tempfile.TemporaryDirectory(prefix="v3d-cache-batch-") as td:
        work = Path(td)
        steps = oracle(a64, build(args.compiler, work, "baseline", core))
        checks += len(EXPECTED_EVENTS) + len(EXPECTED_RESULTS)
        if not args.no_mutate:
            for index, (why, old, new) in enumerate(MUTANTS):
                mutant = replace_once(core, old, new)
                try:
                    oracle(a64, build(args.compiler, work, f"mutant-{index}", mutant))
                except AssertionError:
                    checks += 1
                else:
                    raise AssertionError("gate accepted mutant: " + why)
    print(f"PASS: V3D cache batch {checks} exact checks, {steps} A64 steps, {len(MUTANTS)} hostile mutants rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
