"""Execute Chrome's particle Prepare control flow in emitted A64."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PARTICLES = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402


FIXTURE = r'''
#VK_SUCCESS = 0
#NEON_VK_CHROME_OK = 0
#NEON_VK_CHROME_ERR_ARGS = -21201
#NEON_VK_CHROME_ERR_STATE = -21202
#NVC_PARTICLE_MAX = 4
#NVC_PARTICLE_PALETTE_W = 4
#NVC_PARTICLE_PALETTE_H = 2
#NEON_VK_CHROME_ATLAS_PAD = 64
Structure NvcParticle
  x.i : y.i : width.i : height.i : colour.i : angleQ16.i
  cameraX.i : cameraY.i : zoomQ16.i : ignoreCamera.i
EndStructure
Structure NvcParticleCorners
  x0.i : y0.i : x1.i : y1.i : x2.i : y2.i : x3.i : y3.i
EndStructure
Global nvcReady.i : Global nvcInFrame.i : Global nvcExternalProducerQuarantined.i
Global nvcDevice.i : Global nvcError.i : Global nvcTargetGeneration.i
Global nvcLogicalW.i : Global nvcLogicalH.i
Global nvcParticleImage.i : Global nvcParticleSet.i : Global nvcParticleMapped.i
Global nvcParticleStageSafe.i : Global nvcParticleUploaded.i
Global nvcParticlePrepared.i : Global nvcParticleCount.i : Global nvcParticleCornerBank.i
Global nvcParticleTargetGeneration.i : Global nvcParticleLogicalW.i : Global nvcParticleLogicalH.i
Global Dim nvcParticleItems.NvcParticle[#NVC_PARTICLE_MAX]
Global Dim nvcParticleCornersA.NvcParticleCorners[#NVC_PARTICLE_MAX]
Global Dim nvcParticleCornersB.NvcParticleCorners[#NVC_PARTICLE_MAX]
Global Dim testStage.a[128]
Global Dim testItems.NvcParticle[4]
Global testCreates.i : Global testUploads.i : Global testIdles.i
Global testUploadFail.i : Global testIdleFail.i : Global testGeometryFail.i

Procedure.i nvcFail(code.i)
  nvcError = code
  ProcedureReturn code
EndProcedure
Procedure.i nvdPresentPending()
  ProcedureReturn 0
EndProcedure
Procedure.i nvcParticleGeometry(*p.NvcParticle, *candidate.NvcParticleCorners)
  If testGeometryFail <> 0 Or *p\width < 1 : ProcedureReturn 0 : EndIf
  *candidate\x0 = *p\x + *p\cameraX
  ProcedureReturn 1
EndProcedure
Procedure.i nvcParticlePaletteCreate()
  testCreates = testCreates + 1
  nvcParticleImage = 101 : nvcParticleSet = 102
  nvcParticleMapped = @testStage[0]
  nvcParticleStageSafe = 1 : nvcParticleUploaded = 0
  ProcedureReturn 0
EndProcedure
Procedure nvcParticlePaletteRelease()
  nvcParticleImage = 0 : nvcParticleSet = 0 : nvcParticleMapped = 0
  nvcParticleStageSafe = 0 : nvcParticleUploaded = 0
  nvcParticlePrepared = 0 : nvcParticleCount = 0
EndProcedure
Procedure.i vkDeviceWaitIdle(device.i)
  testIdles = testIdles + 1
  If testIdleFail <> 0 : ProcedureReturn -88 : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i nvcParticleUploadNow()
  testUploads = testUploads + 1
  nvcParticleStageSafe = 0
  If testUploadFail <> 0 : ProcedureReturn -77 : EndIf
  nvcParticleStageSafe = 1 : nvcParticleUploaded = 1
  ProcedureReturn 0
EndProcedure

; @PRODUCTION_PREPARE@

Procedure.i Main()
  nvcReady = 1 : nvcDevice = 1
  nvcLogicalW = 64 : nvcLogicalH = 64 : nvcTargetGeneration = 7
  testItems[0]\x = 4 : testItems[0]\width = 2 : testItems[0]\height = 2
  testItems[0]\colour = $FF112233 : testItems[0]\zoomQ16 = 65536
  testItems[1]\x = 8 : testItems[1]\width = 2 : testItems[1]\height = 2
  testItems[1]\colour = $80123456 : testItems[1]\zoomQ16 = 65536

  If NeonVkChromeParticlesPrepare(@testItems[0], 2) <> 0 : ProcedureReturn 1 : EndIf
  If testCreates <> 1 Or testUploads <> 1 Or nvcParticleCount <> 2 Or nvcParticleCornerBank <> 1 : ProcedureReturn 2 : EndIf
  If (PeekL(nvcParticleMapped + 64) & $FFFFFFFF) <> $FF112233 : ProcedureReturn 3 : EndIf
  If (PeekL(nvcParticleMapped + 68) & $FFFFFFFF) <> $80123456 : ProcedureReturn 20 : EndIf
  If PeekL(nvcParticleMapped + 72) <> 0 : ProcedureReturn 21 : EndIf

  ; Changed positions and camera retain exact colors and the uploaded image.
  testItems[0]\x = 17 : testItems[0]\cameraX = 3
  nvcTargetGeneration = 8
  If NeonVkChromeParticlesPrepare(@testItems[0], 2) <> 0 : ProcedureReturn 4 : EndIf
  If testUploads <> 1 Or nvcParticleItems[0]\x <> 17 Or nvcParticleItems[0]\cameraX <> 3 Or nvcParticleCornerBank <> 0 Or nvcParticleTargetGeneration <> 8 : ProcedureReturn 5 : EndIf
  If nvcParticleCornersA[0]\x0 <> 20 : ProcedureReturn 6 : EndIf

  ; One changed slot forces a complete new transfer.
  testItems[1]\colour = $7F123456
  If NeonVkChromeParticlesPrepare(@testItems[0], 2) <> 0 Or testUploads <> 2 : ProcedureReturn 7 : EndIf
  If (PeekL(nvcParticleMapped + 68) & $FFFFFFFF) <> $7F123456 : ProcedureReturn 8 : EndIf

  ; Count changes cannot reuse the old zero-tail layout.
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> 0 Or testUploads <> 3 : ProcedureReturn 9 : EndIf
  If PeekL(nvcParticleMapped + 68) <> 0 Or nvcParticleCount <> 1 : ProcedureReturn 10 : EndIf

  ; A geometry refusal preserves the last successful palette snapshot.
  testGeometryFail = 1
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> #NEON_VK_CHROME_ERR_ARGS Or testUploads <> 3 : ProcedureReturn 11 : EndIf
  testGeometryFail = 0
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> 0 Or testUploads <> 3 : ProcedureReturn 12 : EndIf

  ; Idle refusal occurs before retained state changes; retry may reuse.
  testIdleFail = 1
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> -88 Or testUploads <> 3 : ProcedureReturn 13 : EndIf
  testIdleFail = 0
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> 0 Or testUploads <> 3 : ProcedureReturn 14 : EndIf

  ; A failed upload poisons staging. Retry requires palette recreation.
  testItems[0]\colour = $FF445566 : testUploadFail = 1
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> -77 Or testUploads <> 4 Or nvcParticleStageSafe <> 0 Or nvcParticlePrepared <> 0 : ProcedureReturn 15 : EndIf
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> #NEON_VK_CHROME_ERR_STATE Or testUploads <> 4 : ProcedureReturn 16 : EndIf
  nvcParticlePaletteRelease() : testUploadFail = 0
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> 0 Or testCreates <> 2 Or testUploads <> 5 : ProcedureReturn 17 : EndIf

  ; Recreation also requires upload even when the colors are identical.
  nvcParticlePaletteRelease()
  If NeonVkChromeParticlesPrepare(@testItems[0], 1) <> 0 Or testCreates <> 3 Or testUploads <> 6 : ProcedureReturn 18 : EndIf
  If nvcParticleItems[0]\colour <> $FF445566 Or nvcParticlePrepared <> 1 : ProcedureReturn 19 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def main() -> int:
    source = PARTICLES.read_text(encoding="utf-8-sig")
    body = gate.procedure_body(source, "NeonVkChromeParticlesPrepare")
    with tempfile.TemporaryDirectory(prefix="neon-vk-palette-reuse-") as temp:
        path = Path(temp) / "palette_reuse.pi4"
        image = Path(temp) / "palette_reuse.img"
        path.write_text(FIXTURE.replace("; @PRODUCTION_PREPARE@", body), encoding="utf-8")
        run = subprocess.run(
            [str(COMPILER), "--compile", str(path), "-t", "pi4", "-s", "--entry-returns",
             "--load-addr", "0x400000", "--bss-addr", "0x800000", "--stack-addr", "0x3000000",
             "-o", str(image)], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode or not image.is_file():
            raise AssertionError(f"palette reuse compile failed:\n{run.stdout}\n{run.stderr}")
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        result, steps = gate.execute(a64, image, 1_000_000)
        if result:
            raise AssertionError(f"palette reuse assertion {result} failed after {steps:,} instructions")
        print(f"PASS: Chrome particle palette reuse ({steps:,} emitted A64 instructions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
