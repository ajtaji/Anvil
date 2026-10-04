"""Compile and execute the Neon particle-call adapter without board access."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_port_gate.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
PARTICLES = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"
PRODUCTION = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonPortBmpProof.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402


TEST_BODY = r'''
#NVC_PARTICLE_MAX = 10000
#NEON_VK_CHROME_OK = 0
#NVC_SPRITE_Q8_LIMIT = 1500000
#NVC_SPRITE_TAU_Q16 = 411775
#NVC_SPRITE_PI_Q16 = 205887
#NVC_SPRITE_HALF_PI_Q16 = 102944
#NVC_SPRITE_MAX_ANGLE_Q16 = 6588400
Structure NvcParticle
  x.i : y.i : width.i : height.i : colour.i : angleQ16.i
  cameraX.i : cameraY.i : zoomQ16.i : ignoreCamera.i
EndStructure
Structure NvcParticleCorners
  x0.i : y0.i : x1.i : y1.i : x2.i : y2.i : x3.i : y3.i
EndStructure
Global nvcLogicalW.i
Global nvcLogicalH.i
Global nvcPhysicalW.i
Global nvcPhysicalH.i
Global Dim nvcSpriteAtanQ16.i[16]
Global nvcSpriteAtanReady.i
Global nvpParticleTestPrepareCalls.i
Global nvpParticleTestDrawCalls.i
Global nvpParticleTestCount.i
Global nvpParticleTestPrepareRc.i
Global nvpParticleTestDrawRc.i
Global Dim nvpParticleTestSnapshot.NvcParticle[3]
Global Dim nvpParticleTestCorners.NvcParticleCorners[3]

; @PRODUCTION_PARTICLE_GEOMETRY@

Procedure.i NeonVkChromeParticlesPrepare(*items.NvcParticle, count.i)
  Protected i.i
  nvpParticleTestPrepareCalls = nvpParticleTestPrepareCalls + 1
  nvpParticleTestCount = count
  If nvpParticleTestPrepareRc <> 0 : ProcedureReturn nvpParticleTestPrepareRc : EndIf
  For i = 0 To count - 1
    If i < 3
      If nvcParticleGeometry(*items, @nvpParticleTestCorners[i]) = 0 : ProcedureReturn -66 : EndIf
      nvpParticleTestSnapshot[i]\x = *items\x : nvpParticleTestSnapshot[i]\y = *items\y
      nvpParticleTestSnapshot[i]\width = *items\width : nvpParticleTestSnapshot[i]\height = *items\height
      nvpParticleTestSnapshot[i]\colour = *items\colour : nvpParticleTestSnapshot[i]\angleQ16 = *items\angleQ16
      nvpParticleTestSnapshot[i]\cameraX = *items\cameraX : nvpParticleTestSnapshot[i]\cameraY = *items\cameraY
      nvpParticleTestSnapshot[i]\zoomQ16 = *items\zoomQ16 : nvpParticleTestSnapshot[i]\ignoreCamera = *items\ignoreCamera
    EndIf
    *items = *items + SizeOf(NvcParticle)
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i NeonVkChromeParticlesDrawPrepared()
  nvpParticleTestDrawCalls = nvpParticleTestDrawCalls + 1
  ProcedureReturn nvpParticleTestDrawRc
EndProcedure

XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_port.pi4"

Procedure.i Main()
  Protected calls.i
  If NeonVkPortParticleAdd(10.0, 20.0, 4.0, 0.0, 1.0, 0.0, 0.0, 1.0) <> #NEON_VK_PORT_ERR_PARTICLE_STATE : ProcedureReturn 1 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_STATE : ProcedureReturn 2 : EndIf
  If NeonVkPortParticleInit(0) <> #NEON_VK_PORT_ERR_PARTICLE_ARGS : ProcedureReturn 36 : EndIf
  If NeonVkPortParticleInit(1) <> 0 : ProcedureReturn 3 : EndIf
  If NeonVkPortParticleAdd(10.0, 20.0, 4.0, 0.0, 1.0, 0.0, 0.0, 1.0) <> 0 : ProcedureReturn 4 : EndIf
  If NeonVkPortParticleAdd(30.0, 40.0, 6.0, 0.5, 0.0, 0.5, 1.0, 0.25) <> 0 : ProcedureReturn 5 : EndIf
  If nvpParticleCount <> 2 : ProcedureReturn 6 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE : ProcedureReturn 7 : EndIf
  If NeonVkPortParticlesPrepare() <> #NEON_VK_PORT_ERR_PARTICLE_STATE : ProcedureReturn 8 : EndIf
  If NeonVkPortCanvas(64, 64, 64, 64) <> 0 : ProcedureReturn 9 : EndIf
  nvcLogicalW = 64 : nvcLogicalH = 64
  nvcPhysicalW = 64 : nvcPhysicalH = 64
  If NeonVkPortCamera(2.0, 4.0, 1.5) <> 0 : ProcedureReturn 10 : EndIf
  If NeonVkPortParticlesPrepare() <> 0 Or nvpParticleTestPrepareCalls <> 1 Or nvpParticleTestCount <> 2 : ProcedureReturn 11 : EndIf
  If nvpParticleTestSnapshot[0]\x <> 8 Or nvpParticleTestSnapshot[0]\y <> 18 Or nvpParticleTestSnapshot[0]\width <> 4 Or nvpParticleTestSnapshot[0]\height <> 4 : ProcedureReturn 12 : EndIf
  If nvpParticleTestSnapshot[0]\colour <> $FFFF0000 Or nvpParticleTestSnapshot[0]\angleQ16 <> 0 : ProcedureReturn 13 : EndIf
  If nvpParticleTestSnapshot[1]\x <> 27 Or nvpParticleTestSnapshot[1]\y <> 37 Or nvpParticleTestSnapshot[1]\width <> 6 Or nvpParticleTestSnapshot[1]\height <> 6 : ProcedureReturn 14 : EndIf
  If nvpParticleTestSnapshot[1]\angleQ16 <> 32768 Or nvpParticleTestSnapshot[1]\colour <> $400080FF : ProcedureReturn 15 : EndIf
  If nvpParticleTestSnapshot[0]\cameraX <> 2 Or nvpParticleTestSnapshot[0]\cameraY <> 4 Or nvpParticleTestSnapshot[0]\zoomQ16 <> 98304 Or nvpParticleTestSnapshot[0]\ignoreCamera <> 0 : ProcedureReturn 16 : EndIf
  If nvpParticleTestSnapshot[1]\cameraX <> 2 Or nvpParticleTestSnapshot[1]\cameraY <> 4 Or nvpParticleTestSnapshot[1]\zoomQ16 <> 98304 : ProcedureReturn 17 : EndIf
  If nvpParticleTestCorners[0]\x0 < -1808 Or nvpParticleTestCorners[0]\x0 > -1776 Or nvpParticleTestCorners[0]\x1 < -272 Or nvpParticleTestCorners[0]\x1 > -240 : ProcedureReturn 37 : EndIf
  If nvpParticleTestCorners[0]\y0 < 1264 Or nvpParticleTestCorners[0]\y0 > 1296 Or nvpParticleTestCorners[0]\y2 < 2800 Or nvpParticleTestCorners[0]\y2 > 2832 : ProcedureReturn 39 : EndIf
  If nvpParticleTestCorners[1]\x0 >= nvpParticleTestCorners[1]\x1 Or nvpParticleTestCorners[1]\x2 >= nvpParticleTestCorners[1]\x0 Or nvpParticleTestCorners[1]\y0 >= nvpParticleTestCorners[1]\y2 : ProcedureReturn 38 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> 0 Or NeonVkPortParticlesDrawPrepared() <> 0 Or nvpParticleTestDrawCalls <> 2 : ProcedureReturn 18 : EndIf
  If NeonVkPortCamera(3.0, 4.0, 1.5) <> 0 : ProcedureReturn 19 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE Or nvpParticleTestDrawCalls <> 2 : ProcedureReturn 20 : EndIf
  If NeonVkPortParticlesPrepare() <> 0 Or nvpParticleTestSnapshot[0]\cameraX <> 3 : ProcedureReturn 21 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> 0 Or nvpParticleTestDrawCalls <> 3 : ProcedureReturn 22 : EndIf
  If NeonVkPortParticleAdd(50.0, 50.0, 8.0, 0.0, 1.0, 1.0, 1.0, 1.0) <> 0 : ProcedureReturn 23 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE : ProcedureReturn 24 : EndIf
  nvpParticleTestPrepareRc = -77
  If NeonVkPortParticlesPrepare() <> -77 Or nvpParticlePrepared <> 0 : ProcedureReturn 25 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE : ProcedureReturn 26 : EndIf
  nvpParticleTestPrepareRc = 0
  If NeonVkPortParticlesPrepare() <> 0 Or nvpParticleTestCount <> 3 Or nvpParticleTestSnapshot[2]\x <> 46 : ProcedureReturn 27 : EndIf
  nvpParticleTestDrawRc = -88
  If NeonVkPortParticlesDrawPrepared() <> -88 : ProcedureReturn 28 : EndIf
  nvpParticleTestDrawRc = 0
  If NeonVkPortParticleClear() <> 0 Or nvpParticleCount <> 0 : ProcedureReturn 29 : EndIf
  calls = nvpParticleTestDrawCalls
  If NeonVkPortParticlesDrawPrepared() <> 0 Or nvpParticleTestDrawCalls <> calls : ProcedureReturn 30 : EndIf
  calls = nvpParticleTestPrepareCalls
  If NeonVkPortParticlesPrepare() <> 0 Or nvpParticleTestPrepareCalls <> calls : ProcedureReturn 31 : EndIf
  If NeonVkPortParticleAdd(1.0, 1.0, 0.1, 0.0, 1.0, 1.0, 1.0, 1.0) <> #NEON_VK_PORT_ERR_PARTICLE_ARGS : ProcedureReturn 32 : EndIf
  If NeonVkPortParticleAdd(1.0, 1.0, 5.0, 101.0, 1.0, 1.0, 1.0, 1.0) <> #NEON_VK_PORT_ERR_PARTICLE_ARGS : ProcedureReturn 33 : EndIf
  nvpParticleCount = #NVC_PARTICLE_MAX
  If NeonVkPortParticleAdd(1.0, 1.0, 5.0, 0.0, 1.0, 1.0, 1.0, 1.0) <> #NEON_VK_PORT_ERR_PARTICLE_CAPACITY : ProcedureReturn 34 : EndIf
  If NeonVkPortParticleInit(1) <> 0 Or nvpParticleCount <> 0 : ProcedureReturn 35 : EndIf
  ProcedureReturn 0
EndProcedure
'''


GPU_STUBS = r'''
#NVPC_OK = 0
Global nvpGpuCreateCalls.i, nvpGpuPrepareCalls.i, nvpGpuDrawCalls.i, nvpGpuReleaseCalls.i
Global nvpGpuPrepareRc.i, nvpGpuDrawRc.i, nvpGpuCount.i, nvpGpuCameraX.i
Procedure.i NeonVkParticleCsdCreate(capacity.i)
  nvpGpuCreateCalls = nvpGpuCreateCalls + 1
  If capacity <> 8 : ProcedureReturn -1 : EndIf
  ProcedureReturn #NVPC_OK
EndProcedure
Procedure.i NeonVkParticleCsdPrepare(*items.NvcParticle, count.i)
  nvpGpuPrepareCalls = nvpGpuPrepareCalls + 1
  nvpGpuCount = count
  If count > 0 : nvpGpuCameraX = *items\cameraX : EndIf
  ProcedureReturn nvpGpuPrepareRc
EndProcedure
Procedure.i NeonVkParticleCsdDraw()
  nvpGpuDrawCalls = nvpGpuDrawCalls + 1
  ProcedureReturn nvpGpuDrawRc
EndProcedure
Procedure.i NeonVkParticleCsdRelease()
  nvpGpuReleaseCalls = nvpGpuReleaseCalls + 1
  ProcedureReturn #NVPC_OK
EndProcedure
'''

GPU_ASSERTS = r'''
  If NeonVkPortParticleAdd(10.0, 20.0, 4.0, 0.0, 1.0, 0.0, 0.0, 1.0) <> 0 : ProcedureReturn 41 : EndIf
  If NeonVkPortParticlesGpuCreate(8) <> 0 Or nvpGpuCreateCalls <> 1 : ProcedureReturn 42 : EndIf
  If NeonVkPortParticlesGpuPrepare() <> 0 Or nvpGpuPrepareCalls <> 1 Or nvpGpuCount <> 1 Or nvpGpuCameraX <> 3 : ProcedureReturn 43 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE : ProcedureReturn 44 : EndIf
  If NeonVkPortParticlesGpuDrawPrepared() <> 0 Or nvpGpuDrawCalls <> 1 : ProcedureReturn 45 : EndIf
  If NeonVkPortCamera(4.0, 4.0, 1.5) <> 0 : ProcedureReturn 46 : EndIf
  If NeonVkPortParticlesGpuDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE Or nvpGpuDrawCalls <> 1 : ProcedureReturn 47 : EndIf
  nvpGpuPrepareRc = -77
  If NeonVkPortParticlesGpuPrepare() <> -77 Or nvpParticlePrepared <> 0 : ProcedureReturn 48 : EndIf
  If NeonVkPortParticlesGpuDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE : ProcedureReturn 49 : EndIf
  nvpGpuPrepareRc = 0
  If NeonVkPortParticlesGpuPrepare() <> 0 Or nvpGpuCameraX <> 4 : ProcedureReturn 50 : EndIf
  nvpGpuDrawRc = -88
  If NeonVkPortParticlesGpuDrawPrepared() <> -88 : ProcedureReturn 51 : EndIf
  nvpGpuDrawRc = 0
  If NeonVkPortParticlesPrepare() <> 0 : ProcedureReturn 52 : EndIf
  If NeonVkPortParticlesGpuDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE : ProcedureReturn 53 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> 0 : ProcedureReturn 54 : EndIf
  If NeonVkPortParticlesGpuRelease() <> 0 Or nvpGpuReleaseCalls <> 1 : ProcedureReturn 55 : EndIf
  If NeonVkPortParticlesDrawPrepared() <> #NEON_VK_PORT_ERR_PARTICLE_PREPARE : ProcedureReturn 56 : EndIf
'''


def main() -> int:
    if not COMPILER.is_file():
        raise SystemExit(f"compiler not found: {COMPILER}")
    prelude, separator, _ = GATE.read_text(encoding="utf-8-sig").partition(
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"'
    )
    if not separator:
        raise AssertionError("port gate prelude changed")
    geometry_marker = "; @PRODUCTION_PARTICLE_GEOMETRY@"
    if TEST_BODY.count(geometry_marker) != 1:
        raise AssertionError("particle geometry marker missing or duplicated")
    chrome = CHROME.read_text(encoding="utf-8-sig")
    particles = PARTICLES.read_text(encoding="utf-8-sig")
    geometry = "\n\n".join(
        gate.procedure_body(chrome, name)
        for name in ("nvcSpriteTrigQ16", "nvcSpriteCornerQ8")
    ) + "\n\n" + gate.procedure_body(particles, "nvcParticleGeometry")
    emitted_gate = TEST_BODY.replace(geometry_marker, geometry)
    with tempfile.TemporaryDirectory(prefix="neon-vk-particles-") as temp:
        source = Path(temp) / "neon_vk_particle_port_gate.pi4"
        image = Path(temp) / "neon_vk_particle_port_gate.img"
        source.write_text(prelude + emitted_gate, encoding="utf-8")
        run = subprocess.run(
            [str(COMPILER), "--compile", str(source), "-t", "pi4", "-s",
             "--entry-returns", "--load-addr", "0x400000", "--bss-addr", "0x800000",
             "--stack-addr", "0x3000000", "-o", str(image)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode or not image.is_file():
            raise AssertionError(f"particle port compilation failed:\n{run.stdout}\n{run.stderr}")
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        base = a64.A64

        class FloatingPointA64(base):
            def __init__(self):
                super().__init__()
                self.enable_system_registers(el=2)

        a64.A64 = FloatingPointA64
        result, steps = gate.execute(a64, image, 3_000_000)
        if result:
            raise AssertionError(f"particle port assertion {result} failed after {steps:,} instructions")
        print(f"PASS: Neon Vulkan particle port ({steps:,} emitted A64 instructions)")
        marker = 'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"'
        gpu_body = emitted_gate.replace(marker, GPU_STUBS + '\n' + marker, 1)
        gpu_body = gpu_body.replace(
            'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_port.pi4"',
            'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_port.pi4"\n'
            'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_csd_port.pi4"', 1)
        end_marker = ('  If NeonVkPortParticleInit(1) <> 0 Or nvpParticleCount <> 0 : ProcedureReturn 35 : EndIf\n'
                      '  ProcedureReturn 0\nEndProcedure\n')
        if gpu_body.count(end_marker) != 1:
            raise AssertionError("particle gate Main end changed")
        gpu_body = gpu_body.replace(end_marker, end_marker.replace('  ProcedureReturn 0\n',
                                                              GPU_ASSERTS + '  ProcedureReturn 0\n'), 1)
        gpu_source = Path(temp) / "neon_vk_particle_gpu_port_gate.pi4"
        gpu_image = Path(temp) / "neon_vk_particle_gpu_port_gate.img"
        gpu_source.write_text(prelude + gpu_body, encoding="utf-8")
        run = subprocess.run(
            [str(COMPILER), "--compile", str(gpu_source), "-t", "pi4", "-s",
             "--entry-returns", "--load-addr", "0x400000", "--bss-addr", "0x800000",
             "--stack-addr", "0x3000000", "-o", str(gpu_image)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode or not gpu_image.is_file():
            raise AssertionError(f"GPU particle port compilation failed:\n{run.stdout}\n{run.stderr}")
        result, steps = gate.execute(a64, gpu_image, 3_000_000)
        if result:
            raise AssertionError(f"GPU particle port assertion {result} failed after {steps:,} instructions")
        print(f"PASS: CPU/GPU particle route isolation ({steps:,} emitted A64 instructions)")
        production = PRODUCTION.read_text(encoding="utf-8-sig")
        marker = 'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"'
        if production.count(marker) != 1:
            raise AssertionError("production include point changed")
        production_source = Path(temp) / "neon_vk_particle_production_include.pi4"
        production_image = Path(temp) / "neon_vk_particle_production_include.img"
        production_source.write_text(
            production.replace(marker, marker + '\nXIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_port.pi4"'),
            encoding="utf-8",
        )
        run = subprocess.run(
            [str(COMPILER), "--compile", str(production_source), "-t", "pi4", "-s",
             "--entry-returns", "--load-addr", "0x800000", "--bss-addr", "0x2000000",
             "--stack-addr", "0x4000000", "-o", str(production_image)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode:
            raise AssertionError(f"production include compilation failed:\n{run.stdout}\n{run.stderr}")
        for _ in range(50):
            if production_image.is_file():
                break
            time.sleep(0.1)
        if not production_image.is_file():
            raise AssertionError("production include linker did not emit an image")
        print("PASS: particle adapter compiles with the real Vulkan/Neon composition")
        csd_proof = (ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdModuleProof.pi4").read_text(encoding="utf-8-sig")
        marker = 'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4"'
        if csd_proof.count(marker) != 1:
            raise AssertionError("CSD production include point changed")
        csd_source = Path(temp) / "neon_vk_particle_gpu_production_include.pi4"
        csd_image = Path(temp) / "neon_vk_particle_gpu_production_include.img"
        csd_source.write_text(csd_proof.replace(marker, marker + '\n'
            'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"\n'
            'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_port.pi4"\n'
            'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_csd_port.pi4"'), encoding="utf-8")
        run = subprocess.run(
            [str(COMPILER), "--compile", str(csd_source), "-t", "pi4", "-s",
             "--entry-returns", "--load-addr", "0x800000", "--bss-addr", "0x2000000",
             "--stack-addr", "0x4000000", "-o", str(csd_image)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode or not csd_image.is_file():
            raise AssertionError(f"GPU port + production CSD composition failed:\n{run.stdout}\n{run.stderr}")
        print("PASS: GPU particle adapter compiles with the real Pi 4 CSD backend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
