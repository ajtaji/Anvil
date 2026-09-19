#!/usr/bin/env python3
"""Desk gate for the renderer-neutral Neon lifecycle dispatch seam."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
FIXTURE = ROOT / "RaspberryPi4/Tests/neon_lifecycle_dispatch_compile.pi4"

class GateError(Exception):
    pass

def require(text: str, token: str) -> None:
    if token not in text:
        raise GateError(f"missing required token: {token}")

def validate(neon: str, fixture: str) -> None:
    for token in (
        "Procedure.i NeonLifecycleInstall(initProc.i, beginProc.i, endProc.i, shutdownProc.i)",
        "Procedure.i NeonLifecycleUseNative()",
        "Procedure.i NeonLifecycleBackend()",
        "gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL",
        "r = gNeonLifecycleInit()",
        "r = gNeonLifecycleBegin(colour)",
        "r = gNeonLifecycleEnd()",
        "r = gNeonLifecycleShutdown()",
        "If NeonDrawBackendActive() = 0",
        "NeonDrawBackendClear()",
    ):
        require(neon, token)
    init = neon[neon.index("Procedure.i NeonInit()"):neon.index("; The address of the default attribute block")]
    begin = neon[neon.index("Procedure.i NeonFrameBegin(colour.i)"):neon.index("Procedure.i NeonFrameEnd()")]
    end = neon[neon.index("Procedure.i NeonFrameEnd()"):neon.index("; ======================================================================\n;  THE VERTEX ARRAY", neon.index("Procedure.i NeonFrameEnd()"))]
    shutdown = neon[neon.index("Procedure.i NeonShutdown()"):neon.index("Procedure.i NeonFrameBegin(colour.i)")]
    require(init, "If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL")
    require(begin, "If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL")
    require(end, "If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL")
    require(shutdown, "If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL")
    if init.index("r = gNeonLifecycleInit()") > init.index("gNeonReady = 1"):
        raise GateError("external init publishes ready before callback")
    if begin.index("r = gNeonLifecycleBegin(colour)") > begin.index("neon_inFrame = 1"):
        raise GateError("external begin publishes frame before callback")
    if end.index("r = gNeonLifecycleEnd()") > end.rindex("neon_inFrame = 0"):
        raise GateError("external end clears frame before callback")
    if shutdown.index("r = gNeonLifecycleShutdown()") > shutdown.index("\n    gNeonReady = 0"):
        raise GateError("external shutdown clears ready before callback")
    for token in ("NeonLifecycleInstall(@LifecycleInit", "NeonDrawBackendInstall(@LifecycleBox", "NeonInit()", "NeonFrameBegin(", "NeonFrameEnd()", "NeonShutdown()", "NeonLifecycleUseNative()"):
        require(fixture, token)
    external_init = init[init.index("If gNeonLifecycleMode = #NEON_BACKEND_EXTERNAL"):init.index("\n  If neon_arena")]
    if "V3dOwnershipClaim" in external_init or "V3dInit()" in external_init:
        raise GateError("external dispatch recursively claims native V3D")

def self_test(neon: str, fixture: str) -> int:
    muts = [
        ("ready before init callback", neon.replace("    r = gNeonLifecycleInit()\n", "    gNeonReady = 1\n    r = gNeonLifecycleInit()\n", 1)),
        ("frame before begin callback", neon.replace("    r = gNeonLifecycleBegin(colour)\n", "    neon_inFrame = 1\n    r = gNeonLifecycleBegin(colour)\n", 1)),
        ("shutdown ready before callback", neon.replace("    r = gNeonLifecycleShutdown()\n", "    gNeonReady = 0\n    r = gNeonLifecycleShutdown()\n", 1)),
        ("fixture omits native reselect", fixture.replace("  If NeonLifecycleUseNative() <> #NEON_OK", "  If #NEON_OK <> #NEON_OK", 1)),
        ("fixture omits primitive family", fixture.replace("  ProcedureReturn NeonDrawBackendInstall(@LifecycleBox", "  ProcedureReturn #NEON_OK : ; omitted family", 1)),
    ]
    rejected = 0
    for name, text in muts:
        try:
            validate(neon, text) if name.startswith("fixture") else validate(text, fixture)
        except (GateError, ValueError):
            rejected += 1
        else:
            raise GateError(f"mutation survived: {name}")
    return rejected

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    neon = NEON.read_text(encoding="utf-8")
    fixture = FIXTURE.read_text(encoding="utf-8")
    validate(neon, fixture)
    if args.self_test:
        print(f"PASS: lifecycle dispatch; {self_test(neon, fixture)} hostile mutations rejected")
    else:
        print("PASS: lifecycle dispatch source and compile fixture contract")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
