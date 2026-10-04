#!/usr/bin/env python3
"""Emitted-A64 gate for the Pi 4 queue-facing compute backend seam."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "Anvil/Graphics/Vulkan/vk_foundation.pbi"
BACKEND = ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
sys.path.insert(0, str(ROOT / "tools"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402
from pmf_compiler import TRACKED_COMPILER, resolve_compiler  # noqa: E402

FIXTURE = r'''
#ANVIL_VK_JOB_DONE = 0
#ANVIL_VK_GPU_LEASE_QUEUE = 1
#ANVIL_VK_GPU_LEASE_EXTERNAL = 2
#V3D_OK = 0
#V3DQ_OK = 0
#V3D_ERR_CSD_ARGS = 23
#AVK_V3D_COMPUTE_CODE_BYTES = 1296
#AVK_V3D_COMPUTE_UNIFORM_BYTES = 32
#AVK_V3D_COMPUTE_SCRATCH_BYTES = 4096
#AVK_V3D_COMPUTE_ERR = -23501
Structure AvkComputeIr Align #PB_Structure_AlignC
  valid.i
EndStructure
; @CONTRACT@
; @CSD_TYPES@
; @COMPUTE_CODE_TYPE@
Global avkV3dWindowBase.i, avkV3dWindowBytes.i, avkV3dGpuLease.i, avkV3dJobs.i
Global testLower.i, testConfigure.i, testSubmit.i, testLowerRc.i, testConfigureRc.i, testSubmitRc.i
Global testOrder.i, testGroups.i
Global Dim testSteps.i[4]

Procedure testMark(step.i)
  testSteps[testOrder] = step
  testOrder = testOrder + 1
EndProcedure

Procedure.i AnvilVkV3dComputeLower(*ir.AvkComputeIr, codeAddr.i, codeCapacity.i, uniformAddr.i, uniformCapacity.i, inputBase.i, inputBytes.i, outputBase.i, outputBytes.i, *out.AnvilVkV3dComputeCode)
  testMark(1) : testLower = testLower + 1
  If *ir = 0 Or codeAddr <> $20001000 Or codeCapacity <> 1296 Or uniformAddr <> $20001510 Or uniformCapacity <> 32
    ProcedureReturn #AVK_V3D_COMPUTE_ERR
  EndIf
  If inputBase <> $20003000 Or inputBytes < 768 Or outputBase <> $20004000 Or outputBytes < 2304
    ProcedureReturn #AVK_V3D_COMPUTE_ERR
  EndIf
  If testLowerRc <> 0 : ProcedureReturn testLowerRc : EndIf
  *out\codeBytes = 1296 : *out\uniformBytes = 32
  ProcedureReturn #V3DQ_OK
EndProcedure

Procedure.i AnvilVkV3dCsdConfigure(*plan.AnvilVkV3dCsdPlan, *result.AnvilVkV3dCsdResult)
  testMark(2) : testConfigure = testConfigure + 1
  testGroups = *plan\groupsX
  If *plan\codeBase <> $20001000 Or *plan\codeBytes <> 1296 Or *plan\uniformBase <> $20001510 Or *plan\uniformBytes <> 32 Or *plan\inputBase <> $20003000 Or *plan\outputBase <> $20004000 Or *plan\groupsY <> 1 Or *plan\groupsZ <> 1 Or *plan\workgroupSize <> 16 Or *plan\workgroupsPerSupergroup <> 1 Or *plan\timeoutUs <> 1000000 Or *result = 0
    ProcedureReturn #V3D_ERR_CSD_ARGS
  EndIf
  ProcedureReturn testConfigureRc
EndProcedure

Procedure.i AnvilVkV3dCsdSubmit(*result.AnvilVkV3dCsdResult)
  testMark(3) : testSubmit = testSubmit + 1
  If testSubmitRc <> 0
    *result\native = 25 : *result\waited = 1
    *result\doneBefore = 1 : *result\doneAfter = 1
    ProcedureReturn -1
  EndIf
  *result\native = 0 : *result\waited = 1
  *result\doneBefore = 1 : *result\doneAfter = 2
  ProcedureReturn #V3D_OK
EndProcedure

; @PRODUCTION@

Procedure testReset()
  testLower = 0 : testConfigure = 0 : testSubmit = 0
  testLowerRc = 0 : testConfigureRc = 0 : testSubmitRc = 0
  testOrder = 0 : testGroups = 0
EndProcedure

Procedure.i Main()
  Define job.AnvilVkBackendComputeJob, result.AnvilVkBackendComputeResult, ir.AvkComputeIr
  avkV3dWindowBase = $20000000 : avkV3dWindowBytes = $10000
  ir\valid = 1 : job\ir = @ir
  job\scratchBase = $20001000 : job\scratchBytes = 4096
  job\inputBase = $20003000 : job\inputBytes = 768
  job\outputBase = $20004000 : job\outputBytes = 4096 : job\outputWrittenBytes = 2304
  job\groupsX = 1 : job\timeoutUs = 1000000
  If avkBackendComputeScratchBytes() <> 4096 : ProcedureReturn 1 : EndIf
  If avkBackendSubmitCompute(@job, 0) <> -1 Or testLower <> 0 : ProcedureReturn 2 : EndIf
  If avkBackendSubmitCompute(@job, @result) <> -1 Or result\mayHaveLaunched <> 0 Or testLower <> 0 : ProcedureReturn 3 : EndIf
  If avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_EXTERNAL) = 0 : ProcedureReturn 4 : EndIf
  If avkBackendSubmitCompute(@job, @result) <> -1 Or result\mayHaveLaunched <> 0 Or testLower <> 0 : ProcedureReturn 5 : EndIf
  If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_EXTERNAL) = 0 Or avkBackendGpuLeaseAcquire(#ANVIL_VK_GPU_LEASE_QUEUE) = 0 : ProcedureReturn 6 : EndIf

  job\scratchBase = job\inputBase
  If avkBackendSubmitCompute(@job, @result) <> -1 Or testLower <> 0 Or testConfigure <> 0 Or result\mayHaveLaunched <> 0 : ProcedureReturn 7 : EndIf
  job\scratchBase = $20010000
  If avkBackendSubmitCompute(@job, @result) <> -1 Or testLower <> 0 Or testConfigure <> 0 : ProcedureReturn 8 : EndIf
  job\scratchBase = $20001000 : job\outputBase = job\inputBase
  If avkBackendSubmitCompute(@job, @result) <> -1 Or testLower <> 0 Or testConfigure <> 0 : ProcedureReturn 9 : EndIf
  job\outputBase = $20004000 : job\outputWrittenBytes = 2305
  If avkBackendSubmitCompute(@job, @result) <> -1 Or testLower <> 0 Or testConfigure <> 0 : ProcedureReturn 10 : EndIf
  job\outputWrittenBytes = 2304

  testReset() : testLowerRc = #AVK_V3D_COMPUTE_ERR
  If avkBackendSubmitCompute(@job, @result) <> -1 Or result\mayHaveLaunched <> 0 Or result\complete <> 0 Or result\native <> #AVK_V3D_COMPUTE_ERR Or testLower <> 1 Or testConfigure <> 0 Or testSubmit <> 0 : ProcedureReturn 11 : EndIf
  testReset() : testConfigureRc = #V3D_ERR_CSD_ARGS
  If avkBackendSubmitCompute(@job, @result) <> -1 Or result\mayHaveLaunched <> 0 Or result\complete <> 0 Or result\native <> #V3D_ERR_CSD_ARGS Or testLower <> 1 Or testConfigure <> 1 Or testSubmit <> 0 : ProcedureReturn 12 : EndIf
  testReset() : testSubmitRc = 1
  If avkBackendSubmitCompute(@job, @result) <> -1 Or result\mayHaveLaunched <> 1 Or result\complete <> 0 Or result\native <> 25 Or result\waited <> 1 Or testLower <> 1 Or testConfigure <> 1 Or testSubmit <> 1 Or avkV3dJobs <> 0 : ProcedureReturn 13 : EndIf
  If testOrder <> 3 Or testSteps[0] <> 1 Or testSteps[1] <> 2 Or testSteps[2] <> 3 : ProcedureReturn 14 : EndIf
  testReset()
  If avkBackendSubmitCompute(@job, @result) <> #ANVIL_VK_JOB_DONE Or result\mayHaveLaunched <> 1 Or result\complete <> 1 Or result\native <> 0 Or result\waited <> 1 Or result\doneBefore <> 1 Or result\doneAfter <> 2 Or avkV3dJobs <> 1 : ProcedureReturn 15 : EndIf
  If testOrder <> 3 Or testSteps[0] <> 1 Or testSteps[1] <> 2 Or testSteps[2] <> 3 : ProcedureReturn 16 : EndIf
  testReset() : job\groupsX = 2 : job\inputBytes = 1536 : job\outputBytes = 8192 : job\outputWrittenBytes = 4608
  If avkBackendSubmitCompute(@job, @result) <> #ANVIL_VK_JOB_DONE Or testGroups <> 2 Or avkV3dJobs <> 2 : ProcedureReturn 17 : EndIf
  If avkBackendGpuLeaseRelease(#ANVIL_VK_GPU_LEASE_QUEUE) = 0 : ProcedureReturn 18 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def section(source: str, start: str, end: str) -> str:
    first = source.index(start)
    last = source.index(end, first) + len(end)
    return source[first:last]


def main() -> int:
    foundation = FOUNDATION.read_text(encoding="utf-8-sig")
    backend = BACKEND.read_text(encoding="utf-8-sig")
    contract = section(foundation, "Structure AnvilVkBackendComputeJob", "EndStructure\n\nDeclare.i avkBackendComputeScratchBytes()")
    contract = contract.rsplit("\n\nDeclare.i", 1)[0]
    csd = section(backend, "Structure AnvilVkV3dCsdPlan", "#AVK_V3D_CSD_MAX_WORKGROUPS = 65535")
    code = section(backend, "Structure AnvilVkV3dComputeCode", "EndStructure")
    names = ("avkBackendGpuLeaseAcquire", "avkBackendGpuLeaseRelease", "avkV3dCsdInside",
             "avkV3dCsdOverlap", "avkBackendComputeScratchBytes", "avkBackendSubmitCompute")
    procedures = "\n\n".join(gate.procedure_body(backend, name) for name in names)
    source_text = (FIXTURE.replace("; @CONTRACT@", contract)
                          .replace("; @CSD_TYPES@", csd)
                          .replace("; @COMPUTE_CODE_TYPE@", code)
                          .replace("; @PRODUCTION@", procedures))
    compiler = Path(resolve_compiler(str(TRACKED_COMPILER)))
    with tempfile.TemporaryDirectory(prefix="anvil-pi4-compute-submit-") as tmp:
        source = Path(tmp) / "compute_submit.pi4"
        image = Path(tmp) / "compute_submit.img"
        source.write_text(source_text, encoding="utf-8")
        run = subprocess.run(
            [str(compiler), "--compile", str(source), "-t", "pi4", "-s", "--entry-returns",
             "--load-addr", "0x400000", "--bss-addr", "0x800000", "--stack-addr", "0x3000000",
             "-o", str(image)], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True, timeout=120,
        )
        if run.returncode or not image.is_file():
            raise AssertionError(f"queue-facing compute seam did not compile:\n{run.stdout}\n{run.stderr}")
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        result, steps = gate.execute(a64, image, 1_000_000)
        if result:
            raise AssertionError(f"queue-facing compute assertion {result} failed after {steps:,} A64 instructions")
    print(f"PASS: Pi 4 queue-facing compute seam ({steps:,} emitted A64 instructions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
