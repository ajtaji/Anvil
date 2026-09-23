#!/usr/bin/env python3
"""Source, emitted, and A64 runtime gate for the Neon Vulkan lifecycle binder."""
from __future__ import annotations
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
BINDER = ROOT / "Anvil/Graphics/Vulkan/neon_vk_lifecycle.pi4"
FIXTURE = ROOT / "RaspberryPi4/Tests/neon_vk_lifecycle_binder_gate.pi4"
# The raw, unvalidated path; resolved through the shared, validating
# resolver (forum 977) lazily in compile_and_run(), not at import time, so
# --self-test (which never compiles) still runs without a compiler present.
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
INTERP = ROOT / "tools/a64/a64_interp.py"
LOAD = 0x00400000
STACK = 0x03000000
RETURN = 0xDEAD0000

class GateError(Exception):
    pass

def require(text: str, token: str) -> None:
    if token not in text:
        raise GateError(f"missing required token: {token}")

def validate(binder: str, fixture: str) -> None:
    for token in (
        "Structure NeonVkLifecycleConfig",
        "Procedure.i NeonVkLifecycleConfigure(*cfg.NeonVkLifecycleConfig)",
        "Procedure.i nvlInit()",
        "Procedure.i nvlBegin(colour.i)",
        "Procedure.i nvlEnd()",
        "Procedure.i nvlShutdown()",
        "r = NeonVkChromeCreate(nvlPhysical, nvlDevice, nvlQueue, nvlCommandPool, nvlRenderPass, nvlFramebuffer, nvlWidth, nvlHeight, nvlMaxQuads)",
        "NeonVkChromeDestroy()",
        "nvlClear[0] = neon_F32Byte(Neon_R(colour))",
        "nvlClear[1] = neon_F32Byte(Neon_G(colour))",
        "nvlClear[2] = neon_F32Byte(Neon_B(colour))",
        "nvlClear[3] = neon_F32Byte(Neon_A(colour))",
        "NeonVkChromeBegin(@nvlClear[0])",
        "NeonVkChromeEnd()",
        "NeonLifecycleInstall(@nvlInit, @nvlBegin, @nvlEnd, @nvlShutdown)",
    ):
        require(binder, token)
    init = binder[binder.index("Procedure.i nvlInit()"):binder.index("Procedure.i nvlBegin")]
    require(init, "NeonVkChromeDestroy()")
    if init.index("If r <> 0") > init.index("NeonVkChromeDestroy()"):
        raise GateError("failed create does not roll back before returning")
    if binder.index("NeonLifecycleInstall(@nvlInit") < binder.index("nvlConfigured = 1"):
        pass
    else:
        raise GateError("binder publishes configuration before lifecycle install")
    if binder.index("NeonVkChromeDestroy()") > binder.index("Procedure.i nvlBegin"):
        raise GateError("unexpected destroy placement")
    for token in ("fakeCreateRc = 7", "If NeonInit() <> #NEON_ERR_BACKEND", "fakeDestroyCount <> 1", "fakeClear0 <> neon_F32Byte", "NeonDrawBackendActive() <> 0", "NeonVkLifecycleConfigured() <> 0"):
        require(fixture, token)

def compile_and_run() -> int:
    compiler = resolve_compiler(str(COMPILER))
    with tempfile.TemporaryDirectory(prefix="neon_vk_lifecycle_") as td:
        work = Path(td)
        image = work / "gate.img"
        run = subprocess.run([compiler, "--compile", str(FIXTURE), "-t", "pi4", "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "--entry-returns", "-o", str(image), "-s"], cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)}, capture_output=True, text=True, timeout=120)
        if run.returncode or not image.is_file():
            raise GateError("fixture compile failed\n" + run.stdout + run.stderr)
        dbg = Path(str(image) + ".dbg")
        entry = None
        for line in dbg.read_text(encoding="utf-8-sig").splitlines():
            f = line.split("|")
            if len(f) >= 4 and f[0] == "1" and f[2].lower() == "main":
                entry = LOAD + int(f[1])
                break
        if entry is None:
            raise GateError("fixture has no Main entry")
        spec = importlib.util.spec_from_file_location("nvl_a64", INTERP)
        if spec is None or spec.loader is None:
            raise GateError("cannot load A64 interpreter")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        cpu = mod.A64()
        blob = image.read_bytes()
        cpu.memory = {LOAD + i: b for i, b in enumerate(blob)}
        cpu.pc = entry
        cpu.sp = STACK
        cpu.x[30] = RETURN
        for _ in range(3_000_000):
            if cpu.pc == RETURN:
                return cpu.x[0]
            cpu.step()
        raise GateError("A64 fixture did not return")

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    binder = BINDER.read_text(encoding="utf-8")
    fixture = FIXTURE.read_text(encoding="utf-8")
    validate(binder, fixture)
    if args.self_test:
        muts = [
            ("missing rollback", binder.replace("    NeonVkChromeDestroy()\n    ProcedureReturn #NEON_ERR_BACKEND", "    ; omitted rollback\n    ProcedureReturn #NEON_ERR_BACKEND", 1)),
            ("wrong clear alpha", binder.replace("nvlClear[3] = neon_F32Byte(Neon_A(colour))", "nvlClear[3] = neon_F32Byte(Neon_R(colour))", 1)),
            ("missing lifecycle install", binder.replace("  r = NeonLifecycleInstall(@nvlInit, @nvlBegin, @nvlEnd, @nvlShutdown)", "  r = #NEON_OK", 1)),
            ("fixture skips failed init", fixture.replace("If NeonInit() <> #NEON_ERR_BACKEND", "If #NEON_OK <> #NEON_ERR_BACKEND", 1)),
        ]
        rejected = 0
        for name, text in muts:
            try:
                validate(text if name != "fixture skips failed init" else binder, fixture if name != "fixture skips failed init" else text)
            except (GateError, ValueError):
                rejected += 1
            else:
                raise GateError(f"mutation survived: {name}")
        print(f"PASS: Vulkan lifecycle binder; {rejected} hostile mutations rejected")
    else:
        result = compile_and_run()
        if result != 0:
            raise GateError(f"emitted binder fixture returned {result}")
        print("PASS: Vulkan lifecycle binder source, emitted compile, and A64 runtime")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
