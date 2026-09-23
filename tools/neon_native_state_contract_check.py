#!/usr/bin/env python3
"""Freeze native Neon refusal, counter, culling, and surface-state semantics."""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
FIXTURE = ROOT / "RaspberryPi4/Tests/neon_native_state_contract.pi4"
LIBS = ("uart.pi4", "timer.pi4", "safety.pi4", "mailbox.pi4", "display.pi4", "v3dqpu.pi4", "v3d.pi4", "neon.pi4")
LOAD = 0x00400000
STACK = 0x03000000
STACK_BYTES = 0x00100000
LOADER_LR = 0xDEAD0000

ERRORS = {
    "#NEON_ERR_VERTS": 7, "#NEON_ERR_RECORDS": 8, "#NEON_ERR_LIST": 9,
    "#NEON_ERR_NOFRAME": 10, "#NEON_ERR_INFRAME": 11,
}


def source_gate(text: str) -> int:
    checks = [
        "If gNeonReady = 0",
        "neon_err = #NEON_ERR_ARENA",
        "If neon_inFrame <> 0",
        "neon_err = #NEON_ERR_INFRAME",
        "If neon_inFrame = 0",
        "neon_err = #NEON_ERR_NOFRAME",
        "neon_nDraws   = 0",
        "neon_nVerts   = 0",
        "neon_nBoxes   = 0",
        "neon_nGlyphs  = 0",
        "neon_nRuns    = 0",
        "neon_nClipped = 0",
        "neon_nTDraws  = 0",
        "neon_nTVerts  = 0",
        "neon_nTGlyphs = 0",
        "If (neon_nVerts + 6) > #NEON_MAX_VERTS",
        "If (neon_nTVerts + 6) > #NEON_MAX_TVERTS",
        "If (x + w) <= 0 Or x >= neon_w Or (y + h) <= 0 Or y >= neon_h",
        "If neon_clipOn <> 0",
        "neon_nClipped = neon_nClipped + 1",
        "If w <= 0 Or h <= 0",
        "If Neon_A(colour) = 0",
        "neon_nBoxes = neon_nBoxes + 1",
        "neon_nGlyphs = neon_nGlyphs + 1",
        "neon_nRuns = neon_nRuns + neon_GlyphRects",
        "neon_nTGlyphs = neon_nTGlyphs + 1",
        "neon_nTVerts  = base + 6",
        "ProcedureReturn neon_TexDraw(first, count, colour)",
        "ProcedureReturn neon_Draw(#NEON_PRIM_TRIS, first, count, colour)",
        "If neon_fanFirst < 0",
        "If neon_lineFirst < 0",
        "Procedure.i Neon_SurfaceW()",
        "Procedure.i Neon_SurfacePhysicalW()",
        "Procedure.i Neon_SurfaceRotation()",
        "Procedure.i Neon_SurfacePitch()",
        "Procedure.i Neon_CapacityPhysicalW()",
        "Procedure.i Neon_CapacityPhysicalH()",
    ]
    missing = [needle for needle in checks if needle not in text]
    missing += [name for name, value in ERRORS.items() if not re.search(rf"{re.escape(name)}\s*=\s*{value}\b", text)]
    if missing:
        raise AssertionError("native state contract missing: " + missing[0])
    if text.count("neon_nBoxes = neon_nBoxes + 1") != 1:
        raise AssertionError("box counter unit is not exactly one accepted box")
    if text.count("neon_nGlyphs = neon_nGlyphs + 1") < 1 or "neon_nGlyphs = neon_nGlyphs + 2" in text:
        raise AssertionError("flat glyph counter unit drifted")
    return len(checks) + 2


def fixture_gate(text: str) -> int:
    required = (
        'XIncludeFile "RaspberryPi4/Lib/neon.pi4"',
        "Procedure.i Main()",
        "CONTRACT error codes:",
        "CONTRACT counters:",
        "CONTRACT culling:",
        "CONTRACT box vertex-capacity preflight atomicity:",
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise AssertionError("fixture missing: " + missing[0])
    return len(required)


def mutate_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError("mutation anchor drifted: " + old)
    return text.replace(old, new, 1)


def self_test(source: str) -> int:
    mutants = (
        ("changed error", "#NEON_ERR_NOFRAME   = 10", "#NEON_ERR_NOFRAME   = 99"),
        ("partial counter advance", "neon_nBoxes = neon_nBoxes + 1", "neon_nBoxes = neon_nBoxes + 2"),
        ("changed counter unit", "neon_nGlyphs = neon_nGlyphs + 1", "neon_nGlyphs = neon_nGlyphs + 2"),
        ("culling drift", "If (x + w) <= 0 Or x >= neon_w Or (y + h) <= 0 Or y >= neon_h", "If (x + w) < 0 Or x > neon_w Or (y + h) < 0 Or y > neon_h"),
    )
    for label, old, new in mutants:
        mutated = mutate_once(source, old, new)
        try:
            source_gate(mutated)
        except AssertionError:
            continue
        raise AssertionError("hostile mutation escaped: " + label)
    return len(mutants)


def required_path(value: str | None, name: str) -> Path:
    if not value:
        raise SystemExit(f"neon native state gate: set {name} or pass --{name[4:].lower()}")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"neon native state gate: {name} not found: {path}")
    return path


def load_interpreter(path: Path):
    spec = importlib.util.spec_from_file_location("anvil_neon_state_a64", path)
    if spec is None or spec.loader is None:
        raise SystemExit("neon native state gate: cannot load interpreter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(compiler: Path, work: Path, source: str, fixture_text: str | None = None) -> Path:
    root = work / "native_state"
    for directory in ("RaspberryPi4/Lib", "RaspberryPi4/Tests", "RaspberryPi4/Intrinsics", "Anvil/Core"):
        (root / directory).mkdir(parents=True)
    for item in LIBS:
        original = ROOT / "RaspberryPi4/Lib" / item
        (root / "RaspberryPi4/Lib" / item).write_text(source if item == "neon.pi4" else original.read_text(encoding="utf-8-sig"), encoding="utf-8")
    (root / "RaspberryPi4/Tests" / FIXTURE.name).write_text(fixture_text if fixture_text is not None else FIXTURE.read_text(encoding="utf-8-sig"), encoding="utf-8")
    shutil.copy2(ROOT / "RaspberryPi4/Intrinsics/bcm2711_hardware.def", root / "RaspberryPi4/Intrinsics/bcm2711_hardware.def")
    shutil.copy2(ROOT / "Anvil/Core/console_style.pbi", root / "Anvil/Core/console_style.pbi")
    image = root / "native_state.img"
    env = os.environ.copy(); env["PMF_ROOT"] = str(root)
    run = subprocess.run([str(compiler), "--compile", str(root / "RaspberryPi4/Tests" / FIXTURE.name), "-t", "pi4", "-s", "--entry-returns", "--load-addr", hex(LOAD), "--bss-addr", "0x800000", "--stack-addr", hex(STACK), "-o", str(image)], cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=180)
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise AssertionError("compile failed\n" + run.stdout)
    return image


def symbol_bounds(image: Path):
    values = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key.strip() in ("__bss_start__", "__bss_end__"): values[key.strip()] = int(value.strip(), 0)
    return values["__bss_start__"], values["__bss_end__"]


def execute(a64, image: Path):
    blob = image.read_bytes(); bss = symbol_bounds(image); code = (LOAD, LOAD + len(blob)); stack = (STACK - STACK_BYTES, STACK + 16)
    def contains(ranges, addr, size): return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)
    cpu = a64.A64(); cpu.memory = {LOAD + i: byte for i, byte in enumerate(blob)}; a64.attach_symbols(cpu, image, LOAD); cpu.pc = LOAD; cpu.sp = STACK; cpu.x[30] = LOADER_LR
    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if not contains((code, bss, stack), addr, size): raise AssertionError(f"read outside image/BSS/stack: {addr:#x}+{size}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))
    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if not contains((bss, stack), addr, size): raise AssertionError(f"write outside BSS/stack: {addr:#x}+{size}")
        for i in range(size): cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF
    cpu.load = load; cpu.store = store
    for steps in range(20_000_000):
        if cpu.pc == LOADER_LR: return cpu.x[0], steps
        cpu.step()
    raise AssertionError("fixture did not return")


def emitted_mutation_gate(compiler: Path, a64, source: str):
    baseline_fixture = FIXTURE.read_text(encoding="utf-8-sig")
    mutants = (
        ("no-frame error", "Neon_Box(1, 1, 2, 2, $FFFFFFFF) <> #NEON_ERR_NOFRAME", "Neon_Box(1, 1, 2, 2, $FFFFFFFF) <> #NEON_OK", 1),
        ("culling counter", "Neon_Clipped() <> 1", "Neon_Clipped() <> 2", 6),
        ("accepted box unit", "nscBoxCount <> 1", "nscBoxCount <> 2", 12),
        ("box vertex-capacity atomicity", "neon_nBoxes <> 0", "neon_nBoxes <> 1", 10),
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="anvil-neon-state-mutants-") as tmp:
        for label, old, new, expected in mutants:
            mutated = mutate_once(baseline_fixture, old, new)
            image = build(compiler, Path(tmp) / label.replace(" ", "_"), source, mutated)
            verdict, steps = execute(a64, image)
            if verdict != expected:
                raise AssertionError(f"emitted mutation escaped ({label}): verdict {verdict}, expected {expected}")
            results.append((label, verdict, steps))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    source = NEON.read_text(encoding="utf-8-sig")
    source_checks = source_gate(source)
    fixture_checks = fixture_gate(FIXTURE.read_text(encoding="utf-8-sig"))
    mutations = self_test(source)
    if args.self_test and (not args.compiler or not args.interp):
        print(f"neon_native_state_contract_check: PASS - {source_checks} source checks, {fixture_checks} fixture checks, {mutations} hostile source mutations rejected; emitted run not requested")
        return 0
    compiler = Path(resolve_compiler(args.compiler))
    interp = required_path(args.interp, "PMF_A64_INTERP")
    a64 = load_interpreter(interp)
    with tempfile.TemporaryDirectory(prefix="anvil-neon-state-") as tmp:
        image = build(compiler, Path(tmp), source)
        result, steps = execute(a64, image)
        if result != 0: raise AssertionError(f"baseline fixture returned verdict {result}")
        emitted = emitted_mutation_gate(compiler, a64, source) if args.self_test else []
    details = ", ".join(f"{label}={verdict} ({used:,} steps)" for label, verdict, used in emitted)
    print(f"neon_native_state_contract_check: PASS - {source_checks} source checks, {fixture_checks} fixture checks, {mutations} hostile mutations rejected, emitted verdict=0 ({steps:,} steps)" + ("; emitted mutants: " + details if details else ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print("neon_native_state_contract_check: FAIL - " + str(exc))
        raise SystemExit(1)
