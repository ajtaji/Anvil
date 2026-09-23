#!/usr/bin/env python3
"""Desk gate for the bounded Neon/V3D ownership handoff seam."""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3D = ROOT / "RaspberryPi4/Lib/v3d.pi4"
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
FIXTURE = ROOT / "RaspberryPi4/Tests/neon_v3d_ownership_lifecycle.pi4"
CACHE = ROOT / "RaspberryPi4/Board/cache.pi4"
CONSOLE = ROOT / "RaspberryPi4/Board/v3d_console.pi4"

class GateError(Exception): pass

def require(text: str, token: str) -> None:
    if token not in text:
        raise GateError(f"missing required token: {token}")

def validate(v3d: str, neon: str, fixture: str, cache: str, console: str) -> None:
    for token in ("#V3D_CLE_CTCS_CTRSTA", "Procedure.i v3d_CleResetThread(off.i)", "Procedure.i v3d_AsbStop(off.i)", "Procedure.i V3dOwnershipHardwareReset()", "Procedure.i V3dOwnershipReset()", "Procedure.i V3dOwnershipClaim()", "Procedure.i V3dOwnershipRelease()"):
        require(v3d, token)
    reset = v3d[v3d.index("Procedure.i V3dOwnershipReset()"):v3d.index("Procedure.i V3dOwnershipClaim()") ]
    require(v3d, "v3d_CleResetThread(#V3D_CLE_CT0CS)")
    require(v3d, "v3d_CleResetThread(#V3D_CLE_CT1CS)")
    require(v3d, "v3d_targetedReset = 1")
    require(v3d, "#V3D_CLE_CTCS_CTRUN")
    require(v3d, "#V3D_CLE_CTCS_CTSUBS")
    require(v3d, "#V3D_CLE_CTCS_CTERR")
    clean_mask = "(#V3D_CLE_CTCS_CTRSTA | #V3D_CLE_CTCS_CTRUN | #V3D_CLE_CTCS_CTERR)"
    if v3d.count(clean_mask) != 3:
        raise GateError("CT reset success mask must exclude benign CTSUBS in helper and both threads")
    for line in v3d.splitlines():
        if "V3dCoreRead" in line and "CTCS_CTSUBS" in line and "#V3D_CLE_CTCS_CTRSTA" in line:
            raise GateError("CTSUBS incorrectly treated as a reset failure bit")
    require(v3d, "#V3D_CTL_INT_CLR")
    require(reset, "If V3dMmuOff() <> #V3D_OK")
    require(reset, "If V3dOwnershipHardwareReset() <> #V3D_OK")
    if reset.index("If V3dMmuOff() <> #V3D_OK") > reset.index("v3d_targetedReset = 1"):
        raise GateError("reset publishes success before MMU hardware handback")
    if reset.index("If V3dOwnershipHardwareReset() <> #V3D_OK") > reset.index("v3d_targetedReset = 1"):
        raise GateError("reset publishes success before PM/ASB hardware reset")
    full = v3d[v3d.index("Procedure.i V3dOwnershipHardwareReset()"):v3d.index("Procedure.i V3dOwnershipReset()")]
    for token in ("v3d_AsbStop(#V3D_ASB_V3D_S_CTRL)", "v3d_AsbStop(#V3D_ASB_V3D_M_CTRL)", "#V3D_MBX_STATE_OFF", "#V3D_MBX_STATE_ON", "V3dPmWrite(#V3D_PM_GRAFX, g & (~#V3D_PM_V3DRSTN))", "V3dPmWrite(#V3D_PM_GRAFX, g | #V3D_PM_V3DRSTN)", "v3d_AsbEnable(#V3D_ASB_V3D_M_CTRL)", "v3d_AsbEnable(#V3D_ASB_V3D_S_CTRL)", "V3dReadIdent()", "r = V3dCheckIdent()"):
        require(full, token)
    if not (full.index("v3d_AsbStop(#V3D_ASB_V3D_S_CTRL)") < full.index("v3d_AsbStop(#V3D_ASB_V3D_M_CTRL") < full.index("#V3D_MBX_STATE_OFF, 1)") < full.index("V3dPmWrite(#V3D_PM_GRAFX, g & (~#V3D_PM_V3DRSTN))") < full.index("#V3D_MBX_STATE_ON, 1)") < full.index("V3dPmWrite(#V3D_PM_GRAFX, g | #V3D_PM_V3DRSTN)") < full.index("v3d_AsbEnable(#V3D_ASB_V3D_M_CTRL)")):
        raise GateError("full reset order drift")
    for token in ("v3d_havePool = 0", "v3d_tfuHaveSrc = 0", "v3d_tfuHaveDst = 0", "v3d_csdHaveGrid = 0", "v3d_csdHaveCode = 0", "v3d_clOpen = 0", "v3d_shrecOk = 0"):
        require(v3d, token)
    require(v3d, "V3dReadIdent()")
    require(v3d, "v3d_owner = 1")
    require(v3d, "v3d_generation = v3d_generation + 1")
    require(v3d, "If v3d_mmuOn <> 0")
    require(v3d, "v3d_owner = 0")
    claim_start = v3d.index("Procedure.i V3dOwnershipClaim()")
    claim = v3d[claim_start:v3d.index("\nEndProcedure", claim_start)]
    release_start = v3d.index("Procedure.i V3dOwnershipRelease()")
    release = v3d[release_start:v3d.index("\nEndProcedure", release_start)]
    if claim.index("r = V3dOwnershipReset()") > claim.index("v3d_owner = 1"):
        raise GateError("claim publishes ownership before reset")
    if release.count("\n  v3d_owner = 0") != 1 or release.index("If v3d_mmuOn <> 0") > release.index("r = V3dOwnershipReset()") or release.index("r = V3dOwnershipReset()") > release.rindex("v3d_owner = 0"):
        raise GateError("release order is not MMU-off, reset, publish-free")
    reset = v3d[v3d.index("Procedure.i V3dOwnershipReset()"):v3d.index("Procedure.i V3dOwnershipClaim()") ]
    if "TOP_GR_BRIDGE" in reset or "V3D_BRIDGE_BASE" in reset:
        raise GateError("Pi4 seam guessed an unprovided bridge MMIO base")
    init = neon[neon.index("Procedure.i NeonInit()"):neon.index("; The address of the default attribute block")]
    shut = neon[neon.index("Procedure.i NeonShutdown()"):neon.index("; ======================================================================\n;  THE FRAME", neon.index("Procedure.i NeonShutdown()"))]
    if init.index("r = V3dInit()") > init.index("r = V3dOwnershipClaim()"):
        raise GateError("NeonInit claims before V3dInit")
    require(shut, "r = V3dOwnershipRelease()")
    rel = shut.index("r = V3dOwnershipRelease()")
    for line in shut[:rel].splitlines():
        if line.strip().startswith("gNeonReady") and "=" in line:
            raise GateError("shutdown publishes not-ready before release")
    if rel > shut.index("gNeonReady   = 0"):
        raise GateError("shutdown did not publish not-ready after release")
    for token in ("V3dOwnershipClaim()", "V3dOwnershipRelease()", "Procedure Main()"):
        require(fixture, token)

    run_start = cache.index("Procedure RunAt(a.i)")
    run = cache[run_start:cache.index("\nEndProcedure", run_start)]
    for token in ("V3dConPayloadSuspend()", "CallAddr()", "ShotTakeArm()", "DmaChannelReset()", "V3dConPayloadResume(v3dState)"):
        require(run, token)
    if not (run.index("V3dConPayloadSuspend()") < run.index("CallAddr()") < run.index("ShotTakeArm()") < run.index("DmaChannelReset()") < run.index("V3dConPayloadResume(v3dState)")):
        raise GateError("RunAt ownership/screenshot/DMA/resume order drift")

    invalidate_start = console.index("Procedure.i V3dConInvalidate()")
    invalidate = console[invalidate_start:console.index("\nEndProcedure", invalidate_start)]
    suspend_start = console.index("Procedure.i V3dConPayloadSuspend()")
    suspend = console[suspend_start:console.index("\nEndProcedure", suspend_start)]
    resume_start = console.index("Procedure.i V3dConPayloadResume(state.i)")
    resume = console[resume_start:console.index("\nEndProcedure", resume_start)]
    require(invalidate, "If NeonShutdown() <> #NEON_OK")
    require(suspend, "If V3dConInvalidate() = 0")
    require(resume, "If V3dConActivate() <> 0")

def mutated_rejected(v3d: str, neon: str, fixture: str, cache: str, console: str) -> int:
    reset_start = v3d.index("Procedure.i V3dOwnershipReset()")
    reset_end = v3d.index("Procedure.i V3dOwnershipClaim()")
    reset = v3d[reset_start:reset_end]
    reset_without_guard = reset.replace("  r = v3d_CleResetThread(#V3D_CLE_CT0CS)", "  ; removed", 1)
    muts = [
        ("missing CT0 reset", v3d[:reset_start] + reset_without_guard + v3d[reset_end:]),
        ("missing CT1 reset", v3d.replace("  r = v3d_CleResetThread(#V3D_CLE_CT1CS)", "  ; omitted", 1)),
        ("missing PM/ASB reset", v3d.replace("  If V3dOwnershipHardwareReset() <> #V3D_OK", "  ; removed full reset", 1)),
        ("missing exact identity check", v3d[:v3d.index("Procedure.i V3dOwnershipHardwareReset()")] + v3d[v3d.index("Procedure.i V3dOwnershipHardwareReset()"):].replace("  r = V3dCheckIdent()", "  r = #V3D_OK", 1)),
        ("master bridge before slave", v3d.replace("  If v3d_AsbStop(#V3D_ASB_V3D_S_CTRL) = 0\n    v3d_err = #V3D_ERR_ASB_SLAVE\n    ProcedureReturn #V3D_ERR_OWNER_RESET\n  EndIf\n  If v3d_AsbStop(#V3D_ASB_V3D_M_CTRL)", "  If v3d_AsbStop(#V3D_ASB_V3D_M_CTRL) = 0\n    v3d_err = #V3D_ERR_ASB_MASTER\n    ProcedureReturn #V3D_ERR_OWNER_RESET\n  EndIf\n  If v3d_AsbStop(#V3D_ASB_V3D_S_CTRL)", 1)),
        ("CTSUBS treated as failure", v3d.replace("(#V3D_CLE_CTCS_CTRSTA | #V3D_CLE_CTCS_CTRUN | #V3D_CLE_CTCS_CTERR)", "(#V3D_CLE_CTCS_CTRSTA | #V3D_CLE_CTCS_CTRUN | #V3D_CLE_CTCS_CTSUBS | #V3D_CLE_CTCS_CTERR)", 1)),
        ("claim before reset", v3d[:v3d.index("Procedure.i V3dOwnershipClaim()")] + v3d[v3d.index("Procedure.i V3dOwnershipClaim()"):].replace("  r = V3dOwnershipReset()\n  If r <> #V3D_OK", "  v3d_owner = 1\n  r = V3dOwnershipReset()\n  If r <> #V3D_OK", 1)),
        ("release before mmu off", v3d.replace("  If v3d_mmuOn <> 0", "  v3d_owner = 0\n  If v3d_mmuOn <> 0", 1)),
        ("neon clears ready before release", neon[:neon.index("Procedure.i NeonShutdown()")] + neon[neon.index("Procedure.i NeonShutdown()"):].replace("  r = V3dOwnershipRelease()", "  gNeonReady = 0\n  r = V3dOwnershipRelease()", 1)),
        ("fixture omits exact claim", fixture.replace("  rc = V3dOwnershipClaim()", "  ; omitted", 1)),
        ("monitor omits pre-entry suspend", cache.replace("  v3dState = V3dConPayloadSuspend()", "  v3dState = 0", 1)),
        ("monitor resumes before screenshot", cache.replace("  If ShotTakeArm() <> 0", "  V3dConPayloadResume(v3dState)\n  If ShotTakeArm() <> 0", 1)),
        ("console ignores shutdown failure", console.replace("    If NeonShutdown() <> #NEON_OK", "    If #NEON_OK <> #NEON_OK", 1)),
    ]
    rejected = 0
    for name, text in muts:
        try:
            if name.startswith("neon"):
                validate(v3d, text, fixture, cache, console)
            elif name == "fixture omits exact claim":
                validate(v3d, neon, text, cache, console)
            elif name.startswith("monitor"):
                validate(v3d, neon, fixture, text, console)
            elif name.startswith("console"):
                validate(v3d, neon, fixture, cache, text)
            else:
                validate(text, neon, fixture, cache, console)
        except (GateError, ValueError):
            rejected += 1
        else:
            raise GateError(f"mutation survived: {name}")
    return rejected

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.parse_args(argv)
    v3d, neon, fixture, cache, console = (
        path.read_text(encoding="utf-8") for path in (V3D, NEON, FIXTURE, CACHE, CONSOLE)
    )
    validate(v3d, neon, fixture, cache, console)
    if ap.parse_args(argv).self_test:
        n = mutated_rejected(v3d, neon, fixture, cache, console)
        print(f"PASS: ownership seam; {n} hostile mutations rejected")
    else:
        print("PASS: ownership seam source and compile fixture contract")
    return 0

if __name__ == "__main__": raise SystemExit(main())
