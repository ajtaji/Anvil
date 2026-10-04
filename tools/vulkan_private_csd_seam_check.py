#!/usr/bin/env python3
"""Emitted-A64 gate for the Pi 4 private CSD backend transaction."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
PRODUCER = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4"
API = ROOT / "Anvil/Graphics/Vulkan/vk_api.pbi"
sys.path.insert(0, str(ROOT / "tools"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402
from pmf_compiler import TRACKED_COMPILER, resolve_compiler  # noqa: E402

FIXTURE = r'''
#V3D_OK = 0
#V3D_ERR_CSD_ARGS = 23
#V3D_ERR_CSD_BUSY = 24
#V3D_ERR_CSD_TIMEOUT = 25
#V3D_ERR_NOINIT = 11
#V3D_ERR_MMU_OFF = 17
#V3D_CSD_CFG5_FLAG_MASK = 7
#ANVIL_VK_GPU_LEASE_QUEUE = 1
#ANVIL_VK_GPU_LEASE_EXTERNAL = 2
Global avkV3dWindowBase.i, avkV3dWindowBytes.i
Global avkV3dGpuLease.i = 0
Global v3d_ready.i = 1, v3d_mmuOn.i = 1
Global testBegin.i, testCode.i, testUniform.i, testOutput.i
Global testSubmit.i, testWait.i, testCache.i
Global testOrder.i
Global Dim testSteps.i[16]
Global testBeginRc.i, testSubmitRc.i, testWaitRc.i, testCleanRc.i
Global testDoneAfter.i = 2
Global testInputBase.i, testInputBytes.i, testOutputBase.i, testOutputBytes.i
Global testGroups.i, testTimeout.i
Global testLeaseErrors.i

Procedure testMark(step.i)
  testSteps[testOrder] = step
  testOrder = testOrder + 1
EndProcedure

Procedure.i V3dCsdBegin(x.i, y.i, z.i, size.i, perSg.i)
  testMark(1)
  testBegin = testBegin + 1
  testGroups = x
  If y <> 1 Or z <> 1 Or size <> 16 Or perSg <> 1 : ProcedureReturn #V3D_ERR_CSD_ARGS : EndIf
  ProcedureReturn testBeginRc
EndProcedure
Procedure.i V3dCsdCode(base.i, bytes.i, flags.i)
  testMark(2)
  testCode = testCode + 1
  If base <> $20001000 Or bytes <> 64 Or flags <> 0 : ProcedureReturn #V3D_ERR_CSD_ARGS : EndIf
  ProcedureReturn #V3D_OK
EndProcedure
Procedure.i V3dCsdUniforms(base.i, bytes.i)
  testMark(3)
  testUniform = testUniform + 1
  If base <> $20002000 Or bytes <> 32 : ProcedureReturn #V3D_ERR_CSD_ARGS : EndIf
  ProcedureReturn #V3D_OK
EndProcedure
Procedure V3dCsdOutput(base.i, bytes.i)
  testMark(4)
  testOutput = testOutput + 1
  testOutputBase = base : testOutputBytes = bytes
EndProcedure
Procedure V3dCacheRange(base.i, bytes.i)
  If testCache = 0 : testMark(5) : Else : testMark(11) : EndIf
  testCache = testCache + 1
  If testCache = 1
    testInputBase = base : testInputBytes = bytes
  Else
    testOutputBase = base : testOutputBytes = bytes
  EndIf
EndProcedure
Procedure.i V3dCsdSubmit()
  testMark(6)
  testSubmit = testSubmit + 1
  ProcedureReturn testSubmitRc
EndProcedure
Procedure.i V3dCsdWait(timeout.i)
  testMark(7)
  testWait = testWait + 1 : testTimeout = timeout
  ProcedureReturn testWaitRc
EndProcedure
Procedure.i V3dCsdCleanResult()
  testMark(10)
  ProcedureReturn testCleanRc
EndProcedure
Procedure.i V3dCsdDoneBefore()
  testMark(8)
  ProcedureReturn 1
EndProcedure
Procedure.i V3dCsdDoneAfter()
  testMark(9)
  ProcedureReturn testDoneAfter
EndProcedure

; @PRODUCTION_CSD@

Procedure testReset()
  If avkBackendGpuLeaseState() = #ANVIL_VK_GPU_LEASE_EXTERNAL
    If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL) = 0 : testLeaseErrors = testLeaseErrors + 1 : EndIf
  EndIf
  If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL) = 0 : testLeaseErrors = testLeaseErrors + 1 : EndIf
  testBegin = 0 : testCode = 0 : testUniform = 0 : testOutput = 0
  testSubmit = 0 : testWait = 0 : testCache = 0
  testBeginRc = 0 : testSubmitRc = 0 : testWaitRc = 0 : testCleanRc = 0
  testDoneAfter = 2 : testInputBase = 0 : testInputBytes = 0
  testOutputBase = 0 : testOutputBytes = 0 : testGroups = 0 : testTimeout = 0
  testOrder = 0
EndProcedure

Procedure testPlan(*p.AnvilVkV3dCsdPlan)
  *p\codeBase = $20001000 : *p\codeBytes = 64 : *p\codeFlags = 0
  *p\uniformBase = $20002000 : *p\uniformBytes = 32
  *p\inputBase = $20003000 : *p\inputBytes = 768
  *p\outputBase = $20004000 : *p\outputBytes = 4096 : *p\outputWrittenBytes = 2304
  *p\groupsX = 1 : *p\groupsY = 1 : *p\groupsZ = 1
  *p\workgroupSize = 16 : *p\workgroupsPerSupergroup = 1 : *p\timeoutUs = 1000000
EndProcedure

Procedure.i Main()
  Define p.AnvilVkV3dCsdPlan, r.AnvilVkV3dCsdResult, i.i
  avkV3dWindowBase = $20000000 : avkV3dWindowBytes = $10000
  testPlan(@p)
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or avkV3dCsdConfigured <> 0 Or testBegin <> 0 : ProcedureReturn 39 : EndIf
  If AnvilVkV3dCsdSubmit(@r) <> -1 Or testSubmit <> 0 : ProcedureReturn 40 : EndIf
  testReset() : testPlan(@p)
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 : ProcedureReturn 1 : EndIf
  If testBegin <> 1 Or testCode <> 1 Or testUniform <> 1 Or testOutput <> 1 Or testCache <> 1 Or testGroups <> 1 : ProcedureReturn 2 : EndIf
  If testInputBase <> p\inputBase Or testInputBytes <> p\inputBytes Or testOutputBase <> p\outputBase Or testOutputBytes <> p\outputBytes : ProcedureReturn 3 : EndIf
  If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL) = 0 : ProcedureReturn 41 : EndIf
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or avkV3dCsdConfigured <> 1 Or avkV3dCsdLeaseOwner <> #ANVIL_VK_GPU_LEASE_EXTERNAL Or testBegin <> 1 : ProcedureReturn 42 : EndIf
  AnvilVkV3dCsdCancel()
  If avkV3dCsdConfigured <> 1 Or avkV3dCsdLeaseOwner <> #ANVIL_VK_GPU_LEASE_EXTERNAL : ProcedureReturn 48 : EndIf
  If AnvilVkV3dCsdSubmit(@r) <> -1 Or avkV3dCsdConfigured <> 1 Or avkV3dCsdLeaseOwner <> #ANVIL_VK_GPU_LEASE_EXTERNAL Or testSubmit <> 0 : ProcedureReturn 43 : EndIf
  If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_QUEUE) = 0 : ProcedureReturn 44 : EndIf
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or avkV3dCsdConfigured <> 1 Or avkV3dCsdLeaseOwner <> #ANVIL_VK_GPU_LEASE_EXTERNAL Or testBegin <> 1 : ProcedureReturn 50 : EndIf
  AnvilVkV3dCsdCancel()
  If avkV3dCsdConfigured <> 1 Or avkV3dCsdLeaseOwner <> #ANVIL_VK_GPU_LEASE_EXTERNAL : ProcedureReturn 49 : EndIf
  If AnvilVkV3dCsdSubmit(@r) <> -1 Or avkV3dCsdConfigured <> 1 Or avkV3dCsdLeaseOwner <> #ANVIL_VK_GPU_LEASE_EXTERNAL Or testSubmit <> 0 : ProcedureReturn 45 : EndIf
  If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_QUEUE) = 0 Or avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL) = 0 : ProcedureReturn 46 : EndIf
  If AnvilVkV3dCsdSubmit(@r) <> 0 : ProcedureReturn 4 : EndIf
  If testSubmit <> 1 Or testWait <> 1 Or testTimeout <> p\timeoutUs Or testCache <> 2 Or testOutputBytes <> p\outputWrittenBytes : ProcedureReturn 5 : EndIf
  If r\native <> 0 Or r\waited <> 1 Or r\doneBefore <> 1 Or r\doneAfter <> 2 : ProcedureReturn 6 : EndIf
  If testOrder <> 11 : ProcedureReturn 21 : EndIf
  For i = 0 To 10
    If testSteps[i] <> i + 1 : ProcedureReturn 22 : EndIf
  Next
  If AnvilVkV3dCsdSubmit(@r) <> -1 Or testSubmit <> 1 : ProcedureReturn 7 : EndIf

  testReset() : testPlan(@p) : p\inputBase = p\outputBase
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 8 : EndIf
  testReset() : testPlan(@p) : p\uniformBase = p\codeBase + 32
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 23 : EndIf
  testReset() : testPlan(@p) : p\outputBase = $2000FFF0
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 : ProcedureReturn 9 : EndIf
  testReset() : testPlan(@p)
  avkV3dWindowBase = $FFFF0000 : avkV3dWindowBytes = $10000
  p\codeBase = $FFFF1000 : p\uniformBase = $FFFF2000 : p\inputBase = $FFFF3000
  p\outputBase = $FFFFFFF0 : p\outputBytes = 64 : p\outputWrittenBytes = 64
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 24 : EndIf
  avkV3dWindowBase = $20000000 : avkV3dWindowBytes = $10000
  testReset() : testPlan(@p) : p\outputWrittenBytes = 4097
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 : ProcedureReturn 10 : EndIf
  testReset() : testPlan(@p) : p\codeFlags = 8
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 : ProcedureReturn 11 : EndIf
  testReset() : testPlan(@p) : p\groupsX = 65535 : p\groupsY = 65535 : p\groupsZ = 65535
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 25 : EndIf
  testReset() : testPlan(@p) : p\workgroupSize = 256
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 26 : EndIf
  testReset() : testPlan(@p) : p\workgroupsPerSupergroup = 17
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 27 : EndIf
  testReset() : testPlan(@p)
  If AnvilVkV3dCsdConfigure(@p, 0) <> #V3D_ERR_CSD_ARGS Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 28 : EndIf
  testReset() : testPlan(@p) : v3d_ready = 0
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_NOINIT Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 37 : EndIf
  v3d_ready = 1 : v3d_mmuOn = 0
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_MMU_OFF Or testBegin <> 0 Or testSubmit <> 0 Or testCache <> 0 : ProcedureReturn 38 : EndIf
  v3d_mmuOn = 1
  testReset() : testPlan(@p) : testBeginRc = #V3D_ERR_CSD_ARGS
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testCode <> 0 Or testCache <> 0 Or testSubmit <> 0 : ProcedureReturn 12 : EndIf

  testReset() : testPlan(@p)
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 : ProcedureReturn 19 : EndIf
  AnvilVkV3dCsdCancel()
  If AnvilVkV3dCsdSubmit(@r) <> -1 Or testSubmit <> 0 : ProcedureReturn 20 : EndIf
  AnvilVkV3dCsdCancel()
  If AnvilVkV3dCsdSubmit(@r) <> -1 Or testSubmit <> 0 : ProcedureReturn 29 : EndIf
  testReset() : testPlan(@p)
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 : ProcedureReturn 30 : EndIf
  p\inputBase = p\outputBase
  If AnvilVkV3dCsdConfigure(@p, @r) <> #V3D_ERR_CSD_ARGS Or testBegin <> 1 : ProcedureReturn 31 : EndIf
  If AnvilVkV3dCsdSubmit(@r) <> -1 Or testSubmit <> 0 : ProcedureReturn 32 : EndIf
  testReset() : testPlan(@p)
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 : ProcedureReturn 33 : EndIf
  If AnvilVkV3dCsdSubmit(0) <> -1 Or testSubmit <> 0 : ProcedureReturn 34 : EndIf
  testReset() : testPlan(@p) : p\groupsX = 2
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 Or testGroups <> 2 : ProcedureReturn 35 : EndIf
  If AnvilVkV3dCsdSubmit(@r) <> 0 Or testSubmit <> 1 Or testCache <> 2 : ProcedureReturn 36 : EndIf

  testReset() : testPlan(@p) : testSubmitRc = #V3D_ERR_CSD_BUSY
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 Or AnvilVkV3dCsdSubmit(@r) <> -1 : ProcedureReturn 13 : EndIf
  If r\native <> #V3D_ERR_CSD_BUSY Or r\waited <> 0 Or testWait <> 0 Or testCache <> 1 : ProcedureReturn 14 : EndIf
  testReset() : testPlan(@p) : testWaitRc = #V3D_ERR_CSD_TIMEOUT
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 Or AnvilVkV3dCsdSubmit(@r) <> -1 : ProcedureReturn 15 : EndIf
  If r\native <> #V3D_ERR_CSD_TIMEOUT Or r\waited <> 1 Or r\doneBefore <> 1 Or r\doneAfter <> 2 Or testCache <> 1 : ProcedureReturn 16 : EndIf
  testReset() : testPlan(@p) : testCleanRc = #V3D_ERR_CSD_TIMEOUT
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 Or AnvilVkV3dCsdSubmit(@r) <> -1 Or testCache <> 1 : ProcedureReturn 17 : EndIf
  testReset() : testPlan(@p) : testDoneAfter = 1
  If AnvilVkV3dCsdConfigure(@p, @r) <> 0 Or AnvilVkV3dCsdSubmit(@r) <> -1 Or testCache <> 1 : ProcedureReturn 18 : EndIf
  If testLeaseErrors <> 0 Or avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL) = 0 Or avkBackendGpuLeaseState() <> 0 : ProcedureReturn 47 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def main() -> int:
    backend = BACKEND.read_text(encoding="utf-8-sig")
    producer = PRODUCER.read_text(encoding="utf-8-sig")
    api = API.read_text(encoding="utf-8-sig")
    start = backend.index("Structure AnvilVkV3dCsdPlan")
    end_marker = "#AVK_V3D_CSD_MAX_WORKGROUPS = 65535"
    end = backend.index(end_marker, start)
    declarations = backend[start:end + len(end_marker)]
    names = ("avkBackendGpuLeaseAcquire", "avkBackendGpuLeaseRelease", "avkBackendGpuLeaseQuarantine", "avkBackendGpuLeaseState",
             "avkV3dCsdInside", "avkV3dCsdOverlap", "AnvilVkV3dCsdConfigure", "AnvilVkV3dCsdCancel", "AnvilVkV3dCsdSubmit")
    body = declarations + "\n\n" + "\n\n".join(gate.procedure_body(backend, name) for name in names)
    prepare = gate.procedure_body(producer, "NeonVkParticleCsdPrepare")
    ordered = ("avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL)",
               "AnvilVkV3dCsdConfigure(@csd, @result)", "NeonVkChromeExternalProducerQuarantine()",
               "AnvilVkV3dCsdSubmit(@result)", "NeonVkChromeExternalProducerUnquarantine()")
    if [prepare.index(item) for item in ordered] != sorted(prepare.index(item) for item in ordered):
        raise AssertionError("producer lease/configuration/Chrome quarantine/submission order changed")
    submit = prepare.index("AnvilVkV3dCsdSubmit(@result)")
    if prepare.rfind("avkBackendGpuLeaseQuarantine(#ANVIL_VK_GPU_LEASE_EXTERNAL)") <= submit:
        raise AssertionError("uncertain CSD submission does not quarantine the shared GPU lease")
    if prepare.rfind("avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL)") <= submit:
        raise AssertionError("proven CSD completion does not release the shared GPU lease")
    if "V3dCsd" in prepare.replace("AnvilVkV3dCsd", "") or "V3dCacheRange" in prepare:
        raise AssertionError("producer bypasses the private backend CSD transaction")
    if "NeonVkChromeExternalProducer" in body:
        raise AssertionError("backend depends on Chrome quarantine")
    if ("If rc <> #NEON_VK_CHROME_OK\n    AnvilVkV3dCsdCancel()\n"
            "    avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL)" not in prepare):
        raise AssertionError("producer does not cancel configuration and release its lease when Chrome quarantine refuses")
    queue = gate.procedure_body(api, "vkGetPhysicalDeviceQueueFamilyProperties")
    if "#VK_QUEUE_COMPUTE_BIT" in queue:
        raise AssertionError("private CSD was advertised as public compute")
    compiler = Path(resolve_compiler(str(TRACKED_COMPILER)))
    with tempfile.TemporaryDirectory(prefix="anvil-private-csd-") as tmp:
        source = Path(tmp) / "private_csd.pi4"
        image = Path(tmp) / "private_csd.img"
        source.write_text(FIXTURE.replace("; @PRODUCTION_CSD@", body), encoding="utf-8")
        run = subprocess.run(
            [str(compiler), "--compile", str(source), "-t", "pi4", "-s", "--entry-returns",
             "--load-addr", "0x400000", "--bss-addr", "0x800000", "--stack-addr", "0x3000000",
             "-o", str(image)], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True, timeout=120,
        )
        if run.returncode or not image.is_file():
            raise AssertionError(f"private CSD fixture did not compile:\n{run.stdout}\n{run.stderr}")
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        result, steps = gate.execute(a64, image, 1_000_000)
        if result:
            raise AssertionError(f"private CSD assertion {result} failed after {steps:,} A64 instructions")
    print(f"PASS: private Pi 4 CSD seam ({steps:,} emitted A64 instructions; no public compute bit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
