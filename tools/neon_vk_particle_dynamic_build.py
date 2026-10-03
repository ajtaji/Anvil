"""Build matched returning Pi 4 CPU/CSD particle-motion diagnostics."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from pmf_compiler import resolve_compiler
from neon_vk_particle_prepare_split_build import check_container, replace_once


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs/neon-particle-dynamic-desk-20261003"
CORE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileCore.pi4"
SOURCE_FILES = (
    ROOT / "RaspberryPi4/Lib/neon.pi4",
    ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4",
    ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4",
    ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4",
    ROOT / "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4",
    CORE,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def procedure(source: str, signature: str) -> str:
    start = source.index(signature + "\n")
    end = source.index("EndProcedure\n", start) + len("EndProcedure\n")
    return source[start:end]


def dynamic_core(source: str) -> str:
    source = replace_once(source,
        "; Shared implementation for matched CPU and CSD 10k returning profiles.",
        "; Matched CPU/CSD 10k returning profile with deterministic per-frame motion.")
    source = replace_once(source, "; 64 little-endian report words, 256 bytes; x0 returns @ngpReport[0].",
                          "; 128 little-endian report words, 512 bytes; x0 returns @ngpReport[0].")
    source = replace_once(source, "Global Dim ngpReport.l[64]", "Global Dim ngpReport.l[128]")
    source = replace_once(source, "  ngpReport[63] = #NGP_TAIL\n  ; UART writes",
                          "  ngpReport[63] = #NGP_TAIL : ngpReport[127] = #NGP_TAIL\n  ; UART writes")
    source = replace_once(source, "  ngpReport[63] = #NGP_TAIL\n  ProcedureReturn @ngpReport[0]",
                          "  ngpReport[63] = #NGP_TAIL : ngpReport[127] = #NGP_TAIL\n  ProcedureReturn @ngpReport[0]")
    original = procedure(source, "Procedure.i ngpCheckPixels()")
    final_check = """Procedure.i ngpCheckPixels()
  Define i.i, x.i, y.i
  ngpReport[25] = ngpPixel(0, 0)
  ngpReport[26] = ngpPixel(6, 3)
  ngpReport[27] = ngpPixel(798, 3)
  ngpReport[28] = ngpPixel(6, 795)
  ngpReport[29] = ngpPixel(798, 795)
  For i = 0 To #NGP_ITEMS - 1
    If (i & 255) = 0 And (Micros() - ngpStart) > #NGP_PIXEL_BUDGET_US
      ngpReport[1] = 34 : ProcedureReturn 0
    EndIf
    x = (i % 100) * 8 + 4 : y = (i / 100) * 8 + 1
    If ngpPixel(x + 2, y + 2) <> $FF00FF00 : ngpReport[30] = ngpReport[30] + 1 : EndIf
    If ngpPixel(x - 1, y + 2) <> $FF000000 : ngpReport[30] = ngpReport[30] + 1 : EndIf
  Next
  ProcedureReturn Bool(ngpReport[30] = 0)
EndProcedure

; Check every grid cell before advancing to the next moving frame. A black
; probe at the old leading edge proves that the last frame was cleared.
Procedure.i ngpCheckFramePixels(frame.i)
  Define i.i, x.i, y.i, t0.i
  t0 = Micros()
  ngpReport[68 + frame] = frame
  ngpReport[80 + frame] = ngpPixel(frame + 3, 3)
  ngpReport[84 + frame] = ngpPixel(frame, 3)
  ngpReport[88 + frame] = ngpPixel(795 + frame, 795)
  For i = 0 To #NGP_ITEMS - 1
    If (i & 255) = 0 And (Micros() - ngpStart) > #NGP_PIXEL_BUDGET_US
      ngpReport[1] = 34 : ProcedureReturn 0
    EndIf
    x = (i % 100) * 8 + 1 + frame : y = (i / 100) * 8 + 1
    If ngpPixel(x + 2, y + 2) <> $FF00FF00 : ngpReport[72 + frame] = ngpReport[72 + frame] + 1 : EndIf
    If ngpPixel(x - 1, y + 2) <> $FF000000 : ngpReport[72 + frame] = ngpReport[72 + frame] + 1 : EndIf
    ngpReport[76 + frame] = ngpReport[76 + frame] + 1
  Next
  ngpReport[92 + frame] = Micros() - t0
  ProcedureReturn Bool(ngpReport[72 + frame] = 0)
EndProcedure
"""
    source = replace_once(source, original, final_check)
    anchor = "EndProcedure\n\nProcedure.i Main()\n"
    motion = """EndProcedure

Procedure ngpMoveParticles(frame.i)
  Define i.i
  For i = 0 To #NGP_ITEMS - 1
    ngpParticles[i]\\x = (i % 100) * 8 + 1 + frame
  Next
EndProcedure

Procedure.i Main()
"""
    source = replace_once(source, anchor, motion)
    source = replace_once(source,
        "  ngpReport[0] = #NGP_MAGIC : ngpReport[63] = #NGP_TAIL\n",
        "  ngpReport[0] = #NGP_MAGIC : ngpReport[63] = #NGP_TAIL\n"
        "  ngpReport[64] = $44594E50 : ngpReport[65] = 1\n"
        "  ngpReport[66] = #NGP_WARMUP + #NGP_SAMPLES : ngpReport[127] = #NGP_TAIL\n")
    source = replace_once(source,
        "    If vkDeviceWaitIdle(ngpDev) <> #VK_SUCCESS : ProcedureReturn ngpUnsafe(40) : EndIf\n"
        "    t0 = Micros()\n",
        "    If vkDeviceWaitIdle(ngpDev) <> #VK_SUCCESS : ProcedureReturn ngpUnsafe(40) : EndIf\n"
        "    t0 = Micros() : ngpMoveParticles(frame)\n"
        "    ngpReport[100 + frame] = Micros() - t0\n"
        "    t0 = Micros()\n")
    source = replace_once(source,
        "    If frame >= #NGP_WARMUP : ngpReport[43 + sample] = Micros() - frameStart : EndIf\n"
        "    ngpReport[8] = frame + 1\n",
        "    If frame >= #NGP_WARMUP : ngpReport[43 + sample] = Micros() - frameStart : EndIf\n"
        "    rc = ngpCheckFramePixels(frame)\n"
        "    If rc = 0\n"
        "      If ngpReport[1] = 34 : ProcedureReturn ngpFinish(34) : EndIf\n"
        "      ProcedureReturn ngpFinish(37)\n"
        "    EndIf\n"
        "    ngpReport[8] = frame + 1\n")
    return source


def build_one(compiler: str, entry: Path) -> dict:
    image = entry.with_suffix(".img")
    command = [compiler, "--compile", str(entry), "-t", "pi4", "-s", "--entry-returns",
               "--load-addr", "0x800000", "--bss-addr", "0x2000000", "--stack-addr", "0x4000000",
               "-o", str(image)]
    result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            capture_output=True, text=True)
    entry.with_suffix(".compiler.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode or not image.is_file():
        raise RuntimeError(f"compile failed: {entry}; inspect compiler log")
    image_bytes = image.read_bytes()
    container = Path(str(image) + ".pmf")
    container_bytes = container.read_bytes()
    loader = check_container(container_bytes, image_bytes)
    symbols = Path(str(image) + ".sym").read_text(encoding="utf-8", errors="replace")
    report_lines = [line for line in symbols.splitlines() if line.startswith("global_ngpreport=")]
    if len(report_lines) != 1:
        raise ValueError("report symbol missing or ambiguous")
    report = int(report_lines[0].split("=", 1)[1])
    if not loader["bss_base"] <= report or report + 512 > loader["bss_base"] + loader["bss_bytes"]:
        raise ValueError("report lies outside BSS")
    return {
        "entry": str(entry.relative_to(ROOT)).replace("\\", "/"),
        "entry_sha256": sha(entry.read_bytes()),
        "image": str(image.relative_to(ROOT)).replace("\\", "/"),
        "image_bytes": len(image_bytes), "image_sha256": sha(image_bytes),
        "container": str(container.relative_to(ROOT)).replace("\\", "/"),
        "container_bytes": len(container_bytes), "container_sha256": sha(container_bytes),
        "report_address_hex": f"0x{report:08X}", "report_bytes": 512,
        "loader": loader, "compile_command": command,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = resolve_compiler(args.compiler)
    OUT.mkdir(parents=True, exist_ok=True)
    core = OUT / "vulkanNeonParticleDynamicCore.pi4"
    core.write_text(dynamic_core(CORE.read_text(encoding="utf-8-sig")), encoding="utf-8")
    builds = {}
    for label, gpu in (("cpu", 0), ("csd", 1)):
        entry = OUT / f"vulkanNeonParticleDynamic{label.upper()}.pi4"
        entry.write_text(f"; Matched returning Pi 4 10k dynamic particle {label} profile.\n"
                         f"#NMP_GPU = {gpu}\n"
                         'XIncludeFile "runs/neon-particle-dynamic-desk-20261003/vulkanNeonParticleDynamicCore.pi4"\n',
                         encoding="utf-8")
        builds[label] = build_one(compiler, entry)
    manifest = {
        "execution": "desk compiled only; board not run",
        "source": str(core.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": sha(core.read_bytes()),
        "production_source_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path.read_bytes())
                                     for path in SOURCE_FILES},
        "compiler": compiler, "builds": builds,
        "report": "512 little-endian bytes; x0 points to report on safe return",
        "checker": "python tools/neon_vk_particle_dynamic_check.py REPORT.BIN [OTHER_REPORT.BIN]",
        "checker_sha256": sha((ROOT / "tools/neon_vk_particle_dynamic_check.py").read_bytes()),
        "unsafe_policy": "Failed submit, failed idle, or lost CSD spins without teardown until the armed deadman resets",
        "board_prerequisite": "Confirm live monitor/memory map and arm a 15-second deadman before load/run",
    }
    (OUT / "safety-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for label, build in builds.items():
        print(f"PASS: {label} image {build['image_bytes']:,} bytes; PMF SHA-256 {build['container_sha256']}; report {build['report_address_hex']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
