"""Compare emitted Chrome particle Prepare geometry and instruction work."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from pmf_compiler import resolve_compiler
import neon_vk_chrome_acceptance_check as emitted


ROOT = Path(__file__).resolve().parent.parent
PARTICLES = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"

FIXTURE = r'''
#VK_SUCCESS = 0
#NEON_VK_CHROME_OK = 0
#NEON_VK_CHROME_ERR_ARGS = -21201
#NEON_VK_CHROME_ERR_STATE = -21202
#NVC_PARTICLE_MAX = 1000
#NVC_PARTICLE_PALETTE_W = 1000
#NVC_PARTICLE_PALETTE_H = 1
#NVC_SPRITE_Q8_LIMIT = 1500000
#NVC_SPRITE_MAX_ANGLE_Q16 = 6588400
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
Global nvcPhysicalW.i : Global nvcPhysicalH.i
Global nvcParticleImage.i : Global nvcParticleSet.i : Global nvcParticleMapped.i
Global nvcParticleStageSafe.i : Global nvcParticleUploaded.i
Global nvcParticlePrepared.i : Global nvcParticleCount.i : Global nvcParticleCornerBank.i
Global nvcParticleTargetGeneration.i : Global nvcParticleLogicalW.i : Global nvcParticleLogicalH.i
Global Dim nvcParticleItems.NvcParticle[#NVC_PARTICLE_MAX]
Global Dim nvcParticleCornersA.NvcParticleCorners[#NVC_PARTICLE_MAX]
Global Dim nvcParticleCornersB.NvcParticleCorners[#NVC_PARTICLE_MAX]
Global Dim testStage.a[8192]
Global Dim testItems.NvcParticle[#NVC_PARTICLE_MAX]

Procedure.i nvcFail(code.i)
  nvcError = code
  ProcedureReturn code
EndProcedure
Procedure.i nvdPresentPending()
  ProcedureReturn 0
EndProcedure
Procedure nvcSpriteTrigQ16(angle.i, *cos, *sin)
  PokeI(*cos, 65536) : PokeI(*sin, 0)
EndProcedure
Procedure nvcSpriteCornerQ8(cx.i, cy.i, x.i, y.i, cosine.i, sine.i, *outX, *outY)
  PokeI(*outX, cx + x) : PokeI(*outY, cy + y)
EndProcedure
Procedure.i nvcParticlePaletteCreate()
  ProcedureReturn -1
EndProcedure
Procedure nvcParticlePaletteRelease()
EndProcedure
Procedure.i vkDeviceWaitIdle(device.i)
  ProcedureReturn 0
EndProcedure
Procedure.i nvcParticleUploadNow()
  ProcedureReturn 0
EndProcedure

; @GEOMETRY@
; @PREPARE@
; @MAIN@
'''

SEMANTIC_MAIN = r'''
Procedure.i TestOne(x.i, y.i, width.i, height.i, zoom.i, ignore.i)
  Define expected.NvcParticleCorners
  Define p.NvcParticle
  Define valid.i, rc.i, i.i
  p\x = x : p\y = y : p\width = width : p\height = height
  p\angleQ16 = 0 : p\colour = $FF228844
  p\cameraX = 20000 : p\cameraY = -20000
  p\zoomQ16 = zoom : p\ignoreCamera = ignore
  valid = nvcParticleGeometry(@p, @expected)
  nvcReady = 1 : nvcInFrame = 0 : nvcExternalProducerQuarantined = 0
  nvcDevice = 1 : nvcParticleImage = 1 : nvcParticleSet = 1
  nvcParticleMapped = @testStage[0]
  nvcParticleStageSafe = 1 : nvcParticleUploaded = 1
  nvcParticlePrepared = 1 : nvcParticleCount = 1 : nvcParticleCornerBank = 0
  nvcParticleItems[0]\colour = p\colour : nvcParticleItems[0]\x = 12345
  rc = NeonVkChromeParticlesPrepare(@p, 1)
  If valid = 0
    If rc <> #NEON_VK_CHROME_ERR_ARGS Or nvcParticleItems[0]\x <> 12345 Or nvcParticleCornerBank <> 0 Or nvcParticlePrepared <> 1
      ProcedureReturn 1
    EndIf
  Else
    If rc <> 0 Or nvcParticleItems[0]\x <> x Or nvcParticleCornerBank <> 1
      ProcedureReturn 2
    EndIf
    For i = 0 To 7
      If PeekI(@nvcParticleCornersB[0] + i * SizeOf(.i)) <> PeekI(@expected + i * SizeOf(.i))
        ProcedureReturn 3
      EndIf
    Next
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i Main()
  Define i.i, rc.i, x.i, y.i, w.i, h.i
  nvcLogicalW = 800 : nvcLogicalH = 800
  nvcPhysicalW = 800 : nvcPhysicalH = 800
  If TestOne(1, 1, 4, 4, 65536, 1) <> 0 : ProcedureReturn 1 : EndIf
  If TestOne(796, 793, 4, 4, 0, -1) <> 0 : ProcedureReturn 2 : EndIf
  If TestOne(-5859, -5859, 1, 1, -99, 1) <> 0 : ProcedureReturn 3 : EndIf
  If TestOne(-5860, 0, 1, 1, 0, 1) <> 0 : ProcedureReturn 4 : EndIf
  If TestOne(5858, 0, 1, 1, 0, 1) <> 0 : ProcedureReturn 5 : EndIf
  If TestOne(5859, 0, 1, 1, 0, 1) <> 0 : ProcedureReturn 6 : EndIf
  If TestOne(0, 5859, 1, 1, 0, 1) <> 0 : ProcedureReturn 7 : EndIf
  If TestOne(0, -5860, 1, 1, 0, 1) <> 0 : ProcedureReturn 8 : EndIf
  If TestOne(0, 0, 4096, 4096, 0, 1) <> 0 : ProcedureReturn 9 : EndIf
  If TestOne(2000, 0, 4096, 1, 0, 1) <> 0 : ProcedureReturn 10 : EndIf
  If TestOne(0, 0, 0, 4, 0, 1) <> 0 : ProcedureReturn 11 : EndIf
  If TestOne(0, 0, 4097, 4, 0, 1) <> 0 : ProcedureReturn 12 : EndIf
  If TestOne(16384, 0, 1, 1, 0, 1) <> 0 : ProcedureReturn 13 : EndIf
  If TestOne(-16385, 0, 1, 1, 0, 1) <> 0 : ProcedureReturn 14 : EndIf
  ; Deterministic moving positions and sizes straddle both Q8 limits.
  For i = 0 To 127
    x = (i * 193) % 12001 - 6000
    y = (i * 307) % 12001 - 6000
    w = (i % 7) + 1 : h = (i % 11) + 1
    If TestOne(x, y, w, h, i - 64, 1) <> 0 : ProcedureReturn 20 + i : EndIf
  Next
  ; A late fast-path refusal must preserve the prior retained list and bank.
  nvcParticlePrepared = 1 : nvcParticleCount = 2 : nvcParticleCornerBank = 0
  nvcParticleItems[0]\x = 111 : nvcParticleItems[1]\x = 222
  nvcParticleItems[0]\colour = $FF228844 : nvcParticleItems[1]\colour = $FF228844
  testItems[0]\x = 10 : testItems[0]\y = 10
  testItems[0]\width = 4 : testItems[0]\height = 4
  testItems[0]\colour = $FF228844 : testItems[0]\angleQ16 = 0
  testItems[0]\ignoreCamera = 1
  testItems[1]\x = 5860 : testItems[1]\y = 10
  testItems[1]\width = 4 : testItems[1]\height = 4
  testItems[1]\colour = $FF228844 : testItems[1]\angleQ16 = 0
  testItems[1]\ignoreCamera = 1
  If NeonVkChromeParticlesPrepare(@testItems[0], 2) <> #NEON_VK_CHROME_ERR_ARGS : ProcedureReturn 180 : EndIf
  If nvcParticleItems[0]\x <> 111 Or nvcParticleItems[1]\x <> 222 Or nvcParticleCornerBank <> 0 Or nvcParticlePrepared <> 1 : ProcedureReturn 181 : EndIf
  testItems[1]\x = 20
  If NeonVkChromeParticlesPrepare(@testItems[0], 2) <> 0 : ProcedureReturn 182 : EndIf
  If nvcParticleItems[0]\x <> 10 Or nvcParticleItems[1]\x <> 20 Or nvcParticleCornerBank <> 1 : ProcedureReturn 183 : EndIf
  nvcLogicalW = 0
  If TestOne(1, 1, 4, 4, 65536, 1) <> 0 : ProcedureReturn 200 : EndIf
  ProcedureReturn 0
EndProcedure
'''

PERF_MAIN = r'''
Procedure.i Main()
  Define i.i
  nvcLogicalW = 800 : nvcLogicalH = 800
  nvcPhysicalW = 800 : nvcPhysicalH = 800
  nvcReady = 1 : nvcDevice = 1
  nvcParticleImage = 1 : nvcParticleSet = 1 : nvcParticleMapped = @testStage[0]
  nvcParticleStageSafe = 1 : nvcParticleUploaded = 1
  nvcParticlePrepared = 1 : nvcParticleCount = #NVC_PARTICLE_MAX
  For i = 0 To #NVC_PARTICLE_MAX - 1
    testItems[i]\x = (i % 100) * 8 + 2
    testItems[i]\y = (i / 100) * 8 + 1
    testItems[i]\width = 4 : testItems[i]\height = 4
    testItems[i]\colour = $FF00FF00
    testItems[i]\zoomQ16 = 65536 : testItems[i]\ignoreCamera = 1
    nvcParticleItems[i]\colour = $FF00FF00
  Next
  If NeonVkChromeParticlesPrepare(@testItems[0], #NVC_PARTICLE_MAX) <> 0 : ProcedureReturn 1 : EndIf
  If nvcParticleCornerBank <> 1 Or nvcParticleCornersB[999]\x0 <> (794 * 256) : ProcedureReturn 2 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def source_with(geometry: str, prepare: str, main: str) -> str:
    return FIXTURE.replace("; @GEOMETRY@", geometry).replace("; @PREPARE@", prepare).replace("; @MAIN@", main)


def reference_prepare(current: str) -> str:
    """Reconstruct the pre-fast-path call for an independent work comparison."""
    viewport = ("  If nvcLogicalW < 1 Or nvcLogicalH < 1 Or nvcLogicalW > 8192 Or nvcLogicalH > 8192 "
                "Or nvcPhysicalW < 1 Or nvcPhysicalH < 1 Or nvcPhysicalW > 8192 Or nvcPhysicalH > 8192\n"
                "    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_ARGS)\n"
                "  EndIf\n")
    if current.count(viewport) != 1:
        raise AssertionError("viewport precheck not found exactly once")
    baseline = current.replace(viewport, "", 1)
    first = "    If *p\\angleQ16 = 0 And *p\\ignoreCamera <> 0\n"
    after = "    If reusePalette <> 0 And *p\\colour <> nvcParticleItems[i]\\colour\n"
    if baseline.count(first) != 1 or baseline.count(after) != 1:
        raise AssertionError("axis fast-path splice is ambiguous")
    start = baseline.index(first)
    end = baseline.index(after, start)
    return (baseline[:start]
            + "    If nvcParticleGeometry(*p, *candidate) = 0\n"
              "      ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_ARGS)\n"
              "    EndIf\n"
            + baseline[end:])


def run(compiler: str, name: str, source: str, work: Path, a64) -> int:
    source_path = work / f"{name}.pi4"
    image = work / f"{name}.img"
    source_path.write_text(source, encoding="utf-8")
    result = subprocess.run([compiler, "--compile", str(source_path), "-t", "pi4", "-s", "--entry-returns",
                             "--load-addr", "0x400000", "--bss-addr", "0x800000", "--stack-addr", "0x3000000",
                             "-o", str(image)], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            text=True, capture_output=True)
    if result.returncode or not image.is_file():
        raise AssertionError(f"{name} compile failed:\n{result.stdout}\n{result.stderr}")
    rc, steps = emitted.execute(a64, image, 6_000_000)
    if rc:
        raise AssertionError(f"{name} returned assertion {rc} after {steps:,} steps")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = resolve_compiler(args.compiler)
    current = PARTICLES.read_text(encoding="utf-8-sig")
    geometry = emitted.procedure_body(current, "nvcParticleGeometry")
    current_prepare = emitted.procedure_body(current, "NeonVkChromeParticlesPrepare")
    baseline_prepare = reference_prepare(current_prepare)
    a64 = emitted.load_interpreter(ROOT / "tools/a64/a64_interp.py")
    with tempfile.TemporaryDirectory(prefix="neon-vk-particle-axis-") as temp:
        work = Path(temp)
        semantic = run(compiler, "axis_semantics", source_with(geometry, current_prepare, SEMANTIC_MAIN), work, a64)
        old_steps = run(compiler, "axis_baseline", source_with(geometry, baseline_prepare, PERF_MAIN), work, a64)
        new_steps = run(compiler, "axis_fast", source_with(geometry, current_prepare, PERF_MAIN), work, a64)
    if new_steps >= old_steps:
        raise AssertionError(f"fast path did not reduce emitted work: old={old_steps}, new={new_steps}")
    print(f"PASS: exact axis geometry and refusal parity ({semantic:,} A64 steps)")
    print(f"PASS: 1000 moving items, emitted work {old_steps:,} -> {new_steps:,} steps ({100 * (old_steps - new_steps) / old_steps:.1f}% less)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
