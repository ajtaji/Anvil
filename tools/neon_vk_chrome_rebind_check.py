#!/usr/bin/env python3
"""Compile and execute the resident chrome rebind transaction gate."""
from __future__ import annotations
import argparse, os, re, subprocess, tempfile, sys
from pathlib import Path
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
GATE = ROOT / "RaspberryPi4/Tests/neon_vk_chrome_rebind_gate.pi4"
DEFAULT = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0xDEAD0000

def body(text: str) -> str:
    match = re.search(r"(?ms)^Procedure\.i NeonVkChromeRebind\(.*?^EndProcedure\s*", text)
    if not match:
        raise AssertionError("NeonVkChromeRebind procedure missing")
    return match.group(0)

def proc_body(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^Procedure(?:\.i)? {re.escape(name)}\(.*?^EndProcedure\s*", text)
    if not match:
        raise AssertionError(f"{name} procedure missing")
    return match.group(0)

def run(compiler: Path, source: str, work: Path, name: str) -> int:
    src, image = work / f"{name}.pi4", work / f"{name}.img"
    src.write_text(source, encoding="utf-8")
    p = subprocess.run([str(compiler), "--compile", str(src), "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "--entry-returns", "-o", str(image), "-s"], cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)}, capture_output=True, text=True, timeout=120)
    if p.returncode or not image.is_file() or image.stat().st_size == 0:
        raise AssertionError("fixture compile failed\n" + p.stdout + p.stderr)
    entries = {}
    for line in Path(str(image) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        f = line.split("|")
        if len(f) >= 4 and f[0] == "1" and f[1].isdigit(): entries[f[2].lower()] = LOAD + int(f[1])
    if "main" not in entries: raise AssertionError("Main entry missing")
    spec = __import__("importlib.util").util.spec_from_file_location("a64_rebind", ROOT / "tools/a64/a64_interp.py")
    mod = __import__("importlib.util").util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    cpu = mod.A64(); cpu.memory = {LOAD + i: b for i, b in enumerate(image.read_bytes())}; cpu.pc, cpu.sp, cpu.x[30] = entries["main"], STACK, RETURN
    for _ in range(2_000_000):
        if cpu.pc == RETURN: return cpu.x[0]
        cpu.step()
    raise AssertionError("fixture did not return")

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--compiler", type=Path, default=DEFAULT); ap.add_argument("--mutate", action="store_true"); a = ap.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    if not a.compiler.is_file(): raise AssertionError(f"compiler not found: {a.compiler}")
    production = SOURCE.read_text(encoding="utf-8")
    gate = GATE.read_text(encoding="utf-8")
    gate = gate.replace("\n@PRODUCTION_REBIND@\n", "\n" + body(production) + "\n")
    gate = gate.replace("@PRODUCTION_VERTEX@", proc_body(production, "nvcVertex"))
    gate = gate.replace("@PRODUCTION_SCISSOR@", proc_body(production, "NeonVkChromeScissorSet"))
    for needle in ("nvdPresentPending() <> 0", "nvdWsiEnabled() <> 0", "nvcLogicalH - y", "nvcLogicalW - x", "nvcLogicalH - (y0 + spanY)", "nvcLogicalW - (x0 + spanX)"):
        if needle not in production: raise AssertionError(f"rotation/rebind anchor missing: {needle}")
    with tempfile.TemporaryDirectory(prefix="anvil-rebind-") as t:
        work = Path(t)
        if run(a.compiler, gate, work, "baseline") != 0: raise AssertionError("baseline rebind gate failed")
        if a.mutate:
            bad = gate.replace("pitch < physicalW * 4", "pitch < physicalW * 3")
            if run(a.compiler, bad, work, "overflow_mutant") == 0: raise AssertionError("overflow mutation was accepted")
            bad = gate.replace("tx = nvcLogicalH - y : ty = x", "tx = nvcLogicalH + y : ty = x")
            if run(a.compiler, bad, work, "rotation_mutant") == 0: raise AssertionError("rotation mutation was accepted")
            bad = gate.replace("nvcWidth = logicalW : nvcHeight = logicalH", "nvcWidth = physicalW : nvcHeight = physicalH")
            if run(a.compiler, bad, work, "logical_extent_mutant") == 0: raise AssertionError("physical logical-extent mutation was accepted")
    print("neon_vk_chrome_rebind_check: PASS")
    print("  emitted lifecycle, geometry, rotation and failure-atomic mutation checks: PASS")
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except (AssertionError, OSError) as e: print(f"neon_vk_chrome_rebind_check: FAIL - {e}"); raise SystemExit(1)
