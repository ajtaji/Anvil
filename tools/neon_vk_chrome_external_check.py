"""Emitted-code desk gate for Chrome's optional external particle vertex seam."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
PARTICLES = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402


FIXTURE = r'''
#NEON_VK_CHROME_OK = 0
#NEON_VK_CHROME_ERR_ARGS = -21201
#NEON_VK_CHROME_ERR_STATE = -21202
#NEON_VK_CHROME_ERR_CAPACITY = -21203
#NEON_VK_CHROME_VERTEX_BYTES = 24
#ANVIL_VK_OK = 0
#VK_SUCCESS = 0
#NVC_PATH_NONE = 0
Global nvcError.i
Global nvcReady.i : Global nvcInFrame.i : Global nvcFrameAbortable.i
Global nvcExternalProducerAttached.i : Global nvcExternalProducerQuarantined.i
Global nvcCommand.i : Global nvcDevice.i : Global nvcVertexMemory.i
Global nvcVertexBuffer.i : Global nvcMapped.i
Global nvcVertices.i : Global nvcExternalVertices.i : Global nvcDrawCount.i
Global nvcMaxQuads.i : Global nvcMaxVertexQuads.i
Global nvcGridBatchActive.i : Global nvcGridBatchFirst.i
Global nvcBoxBatchActive.i : Global nvcBoxBatchFirst.i : Global nvcBoxBatchCount.i
Global nvcRetainedBatchActive.i : Global nvcRetainedBatchCount.i
Global nvcPathKind.i : Global nvcPathCount.i : Global nvcPathError.i
Global nvcSubmitStage.i : Global nvcSubmitRc.i
Global nvcParticlePrepared.i : Global nvcParticleSet.i : Global nvcParticleCount.i
Global nvcParticleTargetGeneration.i : Global nvcTargetGeneration.i
Global nvcParticleLogicalW.i : Global nvcParticleLogicalH.i
Global nvcLogicalW.i : Global nvcLogicalH.i
Global nvcParticleUploaded.i : Global nvcParticleStageSafe.i
Global nvcTestFault.i : Global nvcTestBindFault.i : Global nvcTestDrawFault.i
Global nvcTestRestoreFault.i : Global nvcTestResetFault.i
Global nvcTestIdleFault.i : Global nvcTestIdleCount.i
Global nvcTestBindCount.i : Global nvcTestDrawCount.i : Global nvcTestResetCount.i
Global nvcTestUnmapCount.i : Global nvcTestBytes.i
Global Dim nvcTestBindings.i[8]

Procedure.i AnvilVkFaultCode()
  ProcedureReturn nvcTestFault
EndProcedure
Procedure AnvilVkFaultClear()
  nvcTestFault = 0
EndProcedure
Procedure.i AnvilVkBufferSize(buffer.i)
  If buffer = 77 : ProcedureReturn nvcTestBytes : EndIf
  ProcedureReturn 0
EndProcedure
Procedure vkCmdBindVertexBuffers(command.i, firstBinding.i, bindingCount.i, *buffers, *offsets)
  nvcTestBindings[nvcTestBindCount] = PeekI(*buffers)
  nvcTestBindCount = nvcTestBindCount + 1
  If PeekI(*buffers) = 77 And nvcTestBindFault <> 0 : nvcTestFault = -91 : EndIf
  If PeekI(*buffers) = 11 And nvcTestRestoreFault <> 0 : nvcTestFault = -92 : EndIf
EndProcedure
Procedure.i nvcDrawSet(first.i, count.i, colour.i, descriptor.i)
  nvcTestDrawCount = nvcTestDrawCount + 1
  If first <> 0 Or count <> 12 Or colour <> $FFFFFFFF Or descriptor <> 19
    ProcedureReturn -93
  EndIf
  nvcDrawCount = nvcDrawCount + 1
  If nvcTestDrawFault <> 0 : nvcTestFault = -94 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i vkResetCommandBuffer(command.i, flags.i)
  nvcTestResetCount = nvcTestResetCount + 1
  If nvcTestResetFault <> 0 : ProcedureReturn -95 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i vkDeviceWaitIdle(device.i)
  nvcTestIdleCount = nvcTestIdleCount + 1
  If nvcTestIdleFault <> 0 : ProcedureReturn -97 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure vkUnmapMemory(device.i, memory.i)
  nvcTestUnmapCount = nvcTestUnmapCount + 1
EndProcedure

; @PRODUCTION_PROCEDURES@

Procedure nvcTestFrame()
  nvcReady = 1 : nvcInFrame = 1 : nvcFrameAbortable = 1
  nvcExternalProducerAttached = 1 : nvcExternalProducerQuarantined = 0
  nvcDevice = 2 : nvcCommand = 3 : nvcVertexMemory = 4 : nvcVertexBuffer = 11
  nvcMapped = 1234 : nvcMaxQuads = 5 : nvcMaxVertexQuads = 4
  nvcParticlePrepared = 1 : nvcParticleSet = 19 : nvcParticleCount = 2
  nvcTargetGeneration = 8 : nvcParticleTargetGeneration = 8
  nvcLogicalW = 64 : nvcLogicalH = 64
  nvcParticleLogicalW = 64 : nvcParticleLogicalH = 64
  nvcParticleUploaded = 1 : nvcParticleStageSafe = 1
  nvcVertices = 6 : nvcDrawCount = 1 : nvcTestBytes = 288
  nvcTestBindCount = 0 : nvcTestDrawCount = 0
  nvcTestBindFault = 0 : nvcTestDrawFault = 0 : nvcTestRestoreFault = 0
  nvcTestFault = 0
EndProcedure

Procedure.i Main()
  nvcReady = 1
  If NeonVkChromeExternalProducerAttach() <> 0 : ProcedureReturn 1 : EndIf
  If NeonVkChromeExternalProducerAttach() <> #NEON_VK_CHROME_ERR_STATE : ProcedureReturn 2 : EndIf
  If NeonVkChromeExternalProducerQuarantine() <> 0 : ProcedureReturn 3 : EndIf
  If NeonVkChromeExternalProducerDetach() <> #NEON_VK_CHROME_ERR_STATE : ProcedureReturn 4 : EndIf
  If NeonVkChromeExternalProducerUnquarantine() <> 0 : ProcedureReturn 5 : EndIf
  nvcTestIdleFault = 1
  If NeonVkChromeExternalProducerDetach() <> -97 Or nvcExternalProducerAttached <> 1 : ProcedureReturn 29 : EndIf
  nvcTestIdleFault = 0
  If NeonVkChromeExternalProducerDetach() <> 0 : ProcedureReturn 6 : EndIf
  If NeonVkChromeExternalProducerQuarantine() <> #NEON_VK_CHROME_ERR_STATE : ProcedureReturn 7 : EndIf

  nvcTestFrame()
  If NeonVkChromeParticlesDrawExternal(77, 12) <> 0 : ProcedureReturn 8 : EndIf
  If nvcTestBindCount <> 2 Or nvcTestBindings[0] <> 77 Or nvcTestBindings[1] <> 11 : ProcedureReturn 9 : EndIf
  If nvcTestDrawCount <> 1 Or nvcDrawCount <> 2 Or nvcVertices <> 6 Or nvcExternalVertices <> 12 : ProcedureReturn 10 : EndIf
  If NeonVkChromeVertexCount() <> 18 : ProcedureReturn 11 : EndIf
  If NeonVkChromeParticlesDrawExternal(77, 10) <> #NEON_VK_CHROME_ERR_ARGS Or nvcTestBindCount <> 2 : ProcedureReturn 12 : EndIf
  If NeonVkChromeParticlesDrawExternal(11, 12) <> #NEON_VK_CHROME_ERR_ARGS Or nvcTestBindCount <> 2 : ProcedureReturn 30 : EndIf
  nvcTestBytes = 287
  If NeonVkChromeParticlesDrawExternal(77, 12) <> #NEON_VK_CHROME_ERR_CAPACITY Or nvcTestBindCount <> 2 : ProcedureReturn 13 : EndIf
  nvcTestBytes = 288
  If NeonVkChromeAbort() <> 0 Or nvcInFrame <> 0 Or nvcMapped <> 0 : ProcedureReturn 14 : EndIf
  If nvcTestResetCount <> 1 Or nvcTestUnmapCount <> 1 Or NeonVkChromeVertexCount() <> 0 : ProcedureReturn 15 : EndIf
  If NeonVkChromeAbort() <> #NEON_VK_CHROME_ERR_STATE : ProcedureReturn 16 : EndIf

  nvcTestFrame() : nvcTestBindFault = 1
  If NeonVkChromeParticlesDrawExternal(77, 12) <> -91 : ProcedureReturn 17 : EndIf
  If nvcTestDrawCount <> 0 Or nvcInFrame <> 0 Or nvcFrameAbortable <> 0 : ProcedureReturn 18 : EndIf
  nvcTestFrame() : nvcTestDrawFault = 1
  If NeonVkChromeParticlesDrawExternal(77, 12) <> -94 : ProcedureReturn 19 : EndIf
  If nvcTestBindCount <> 2 Or nvcTestBindings[1] <> 11 Or nvcInFrame <> 0 : ProcedureReturn 20 : EndIf
  nvcTestFrame() : nvcTestRestoreFault = 1
  If NeonVkChromeParticlesDrawExternal(77, 12) <> -92 Or nvcInFrame <> 0 : ProcedureReturn 21 : EndIf
  nvcTestFrame() : nvcFrameAbortable = 0
  If NeonVkChromeAbort() <> #NEON_VK_CHROME_ERR_STATE : ProcedureReturn 22 : EndIf
  nvcTestFrame() : nvcExternalProducerAttached = 0
  If NeonVkChromeParticlesDrawExternal(77, 12) <> #NEON_VK_CHROME_ERR_STATE Or nvcTestBindCount <> 0 : ProcedureReturn 23 : EndIf
  nvcTestFrame() : nvcTestBindFault = 1 : nvcTestResetFault = 1
  If NeonVkChromeParticlesDrawExternal(77, 12) <> -95 : ProcedureReturn 24 : EndIf
  If nvcInFrame <> 1 Or nvcFrameAbortable <> 1 Or nvcMapped <> 1234 : ProcedureReturn 25 : EndIf
  nvcTestResetFault = 0
  If NeonVkChromeAbort() <> 0 : ProcedureReturn 26 : EndIf
  nvcTestFrame() : nvcTestFault = -96
  If NeonVkChromeParticlesDrawExternal(77, 12) <> -96 : ProcedureReturn 27 : EndIf
  If nvcTestBindCount <> 0 Or nvcInFrame <> 0 : ProcedureReturn 28 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def main() -> int:
    chrome = CHROME.read_text(encoding="utf-8-sig")
    particles = PARTICLES.read_text(encoding="utf-8-sig")
    names = ("nvcFail", "NeonVkChromeVertexCount", "NeonVkChromeAbort",
             "NeonVkChromeExternalProducerAttach", "NeonVkChromeExternalProducerQuarantine",
             "NeonVkChromeExternalProducerUnquarantine", "NeonVkChromeExternalProducerDetach")
    source = "\n\n".join(gate.procedure_body(chrome, name) for name in names)
    source += "\n\n" + gate.procedure_body(particles, "NeonVkChromeParticlesDrawExternal")
    if "nvcExternalProducerAttached <> 0 Or nvcExternalProducerQuarantined <> 0" not in gate.procedure_body(chrome, "NeonVkChromeDestroy"):
        raise AssertionError("Destroy lacks the external producer ownership guard")
    for name in ("NeonVkChromeBegin", "NeonVkChromeRebind"):
        if "nvcExternalProducerQuarantined <> 0" not in gate.procedure_body(chrome, name):
            raise AssertionError(f"{name} lacks the CSD quarantine guard")
    if "nvcExternalProducerQuarantined <> 0" not in gate.procedure_body(particles, "NeonVkChromeParticlesPrepare"):
        raise AssertionError("particle Prepare lacks the CSD quarantine guard")
    with tempfile.TemporaryDirectory(prefix="neon-vk-external-") as temp:
        path = Path(temp) / "external.pi4"
        image = Path(temp) / "external.img"
        path.write_text(FIXTURE.replace("; @PRODUCTION_PROCEDURES@", source), encoding="utf-8")
        run = subprocess.run(
            [str(COMPILER), "--compile", str(path), "-t", "pi4", "-s", "--entry-returns",
             "--load-addr", "0x400000", "--bss-addr", "0x800000", "--stack-addr", "0x3000000",
             "-o", str(image)], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode or not image.is_file():
            raise AssertionError(f"external seam compile failed:\n{run.stdout}\n{run.stderr}")
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        result, steps = gate.execute(a64, image, 1_000_000)
        if result:
            raise AssertionError(f"external seam assertion {result} failed after {steps:,} instructions")
        print(f"PASS: Chrome external particle seam ({steps:,} emitted A64 instructions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
