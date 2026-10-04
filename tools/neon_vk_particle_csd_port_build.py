#!/usr/bin/env python3
"""Build a returning Pi 4 proof of the Neon particle adapter's CSD route."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdModuleProof.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

PORT_PARTICLES = r'''Procedure.i ngpBuildParticles()
  Define i.i, x.i, y.i, angle.f, r.f, g.f, b.f
  If NeonVkPortCanvas(#NGP_W, #NGP_H, #NGP_W, #NGP_H) <> #NEON_OK : ProcedureReturn 2 : EndIf
  If NeonVkPortCamera(0.0, 0.0, 1.0) <> #NEON_OK : ProcedureReturn 3 : EndIf
  For i = 0 To #NGP_ITEMS - 1
    x = (i % 4) * 32 + 15 : y = (i / 4) * 16 + 8
    angle = 0.0
    If i % 4 = 1 : angle = 0.25 : EndIf
    If i % 4 = 3 : angle = -0.20 : EndIf
    r = MathFFromInt((i * 29 + 97) & 255) / 255.0
    g = MathFFromInt((i * 43 + 59) & 255) / 255.0
    b = MathFFromInt((i * 67 + 31) & 255) / 255.0
    If NeonVkPortParticleAdd(MathFFromInt(x), MathFFromInt(y), 10.0, angle, r, g, b, 1.0) <> #NEON_OK
      ProcedureReturn 4
    EndIf
  Next
  ProcedureReturn 0
EndProcedure'''

PORT_SNAPSHOT = r'''Procedure ngpSnapshotParticles()
  Define i.i, c.i
  ; Prepare fills the camera fields. Snapshot only after that step, while
  ; keeping the expected CPU geometry separate from CSD input/output memory.
  For i = 0 To #NGP_ITEMS - 1
    For c = 0 To SizeOf(NvcParticle) - 1
      PokeA(@ngpParticles[i] + c, PeekA(@nvpParticleItems[i] + c))
    Next
  Next
EndProcedure'''


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("source anchor changed: " + old[:80])
    return text.replace(old, new, 1)


def build_source() -> str:
    text = SOURCE.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    marker = 'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4"'
    text = replace_once(text, marker, marker + '\n'
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pi4"\n'
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_port.pi4"\n'
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particle_csd_port.pi4"')
    start = text.index("Procedure ngpBuildParticles()")
    end = text.index("EndProcedure", start) + len("EndProcedure")
    text = text[:start] + PORT_PARTICLES + "\n\n" + PORT_SNAPSHOT + text[end:]
    text = replace_once(text, "rc = NeonVkParticleCsdCreate(#NGP_ITEMS)",
                        "If NeonVkPortParticleInit(1) <> #NEON_OK : ProcedureReturn ngpFinish(40) : EndIf\n"
                        "  rc = NeonVkPortParticlesGpuCreate(#NGP_ITEMS)")
    text = replace_once(text, "  ngpBuildParticles()",
                        "  If ngpBuildParticles() <> 0 : ProcedureReturn ngpFinish(40) : EndIf")
    text = replace_once(text, "rc = NeonVkParticleCsdPrepare(@ngpParticles[0], #NGP_ITEMS)",
                        "rc = NeonVkPortParticlesGpuPrepare()\n  ngpSnapshotParticles()")
    text = replace_once(text, "rc = NeonVkParticleCsdDraw()",
                        "rc = NeonVkPortParticlesGpuDrawPrepared()")
    text = replace_once(text, "If NeonVkParticleCsdRelease() <> #NVPC_OK",
                        "If NeonVkPortParticlesGpuRelease() <> #NVPC_OK")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--compiler", type=Path, default=COMPILER)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    src = args.out / "vulkanNeonParticleCsdPortProof.pi4"
    img = args.out / "vulkanNeonParticleCsdPortProof.img"
    src.write_text(build_source(), encoding="utf-8", newline="\n")
    cmd = [str(args.compiler), "--compile", str(src), "-t", "pi4", "-s",
           "--entry-returns", "--load-addr", "0x800000", "--bss-addr", "0x2000000",
           "--stack-addr", "0x4000000", "-o", str(img)]
    run = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                         capture_output=True, text=True)
    (args.out / "compiler.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    if run.returncode or not img.is_file():
        raise RuntimeError("Pi 4 proof did not compile; see compiler.log")
    container = Path(str(img) + ".pmf")
    for path in (img, container):
        print("%s %d SHA256 %s" % (path.name, path.stat().st_size,
                                   hashlib.sha256(path.read_bytes()).hexdigest().upper()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
