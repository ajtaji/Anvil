"""Build a matched Pi 4 particle diagnostic with backend subphase timers."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from pmf_compiler import resolve_compiler
from neon_vk_particle_prepare_split_build import check_container, replace_once, sha
from neon_vk_particle_end_split_build import instrument_chrome, instrument_core


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs/neon-particle-backend-split-desk-20261003"
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
BACKEND = ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
PARTICLES = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"
CSD = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4"
CORE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileCore.pi4"


def procedure(source: str, signature: str) -> str:
    start = source.index(signature + "\n")
    end = source.index("EndProcedure\n", start) + len("EndProcedure\n")
    return source[start:end]


def instrument_neon(source: str) -> str:
    original = procedure(source, "Procedure neon_BuildCoordinateTables(physW.i, physH.i, cx.i, cy.i)")
    measured = replace_once(original, "  Protected n.i\n", "  Protected n.i, diagMark.i\n  diagMark = Micros()\n")
    measured = replace_once(measured,
        "  Wend\nEndProcedure\n",
        "  Wend\n  nbiCoordUs = nbiCoordUs + Micros() - diagMark\n  nbiCoordCalls = nbiCoordCalls + 1\nEndProcedure\n")
    return replace_once(source, original,
        "; Diagnostic counters exist only in this generated Neon include.\n"
        "Global nbiCoordUs.i, nbiCoordCalls.i\n" + measured)


def instrument_backend(source: str) -> str:
    original = procedure(source, "Procedure.i avkBackendSubmitDraw(*payload)")
    measured = replace_once(original,
        "  Define sc.AvkV3dNormalizedScissor\n",
        """  Define sc.AvkV3dNormalizedScissor
  Define diagStart.i, diagMark.i, diagCoordBefore.i, diagCallsBefore.i
  diagStart = Micros()
  nbiTotalUs = 0 : nbiPreUs = 0 : nbiCacheUs = 0
  nbiTargetRebindUs = 0 : nbiTargetCoordUs = 0 : nbiTargetCoordCalls = 0
  nbiBeginUs = 0 : nbiEmitUs = 0 : nbiEndUs = 0
  nbiRestoreRebindUs = 0 : nbiRestoreCoordUs = 0 : nbiRestoreCoordCalls = 0
""")
    measured = replace_once(measured,
        "    vertexCacheRanges = avkV3dCleanCacheIntervals()\n",
        """    nbiPreUs = Micros() - diagStart
    diagMark = Micros()
    vertexCacheRanges = avkV3dCleanCacheIntervals()
    nbiCacheUs = Micros() - diagMark
""")
    measured = replace_once(measured,
        "  rc = NeonHardwareRebindSurface(*first\\targetBase, *first\\width, *first\\height, *first\\pitch, *first\\targetBytes, #V3D_OFMT_RGBA8, 0)\n  If rc = #NEON_OK\n    rc = NeonHardwareFrameBegin(*first\\clearBgra)\n",
        r"""  diagCoordBefore = nbiCoordUs : diagCallsBefore = nbiCoordCalls
  diagMark = Micros()
  rc = NeonHardwareRebindSurface(*first\targetBase, *first\width, *first\height, *first\pitch, *first\targetBytes, #V3D_OFMT_RGBA8, 0)
  nbiTargetRebindUs = Micros() - diagMark
  nbiTargetCoordUs = nbiCoordUs - diagCoordBefore
  nbiTargetCoordCalls = nbiCoordCalls - diagCallsBefore
  If rc = #NEON_OK
    diagMark = Micros()
    rc = NeonHardwareFrameBegin(*first\clearBgra)
    nbiBeginUs = Micros() - diagMark
""")
    measured = replace_once(measured,
        "  If rc = #NEON_OK And liveDraws > 0\n    ; NeonFrameBegin emitted",
        "  diagMark = Micros()\n  If rc = #NEON_OK And liveDraws > 0\n    ; NeonFrameBegin emitted")
    measured = replace_once(measured,
        "  ; V3dBclFinish refuses an errored list before submit. Calling End after an\n",
        "  nbiEmitUs = Micros() - diagMark\n  ; V3dBclFinish refuses an errored list before submit. Calling End after an\n")
    measured = replace_once(measured,
        "    endRc = NeonHardwareFrameEnd()\n",
        "    diagMark = Micros()\n    endRc = NeonHardwareFrameEnd()\n    nbiEndUs = Micros() - diagMark\n")
    measured = replace_once(measured,
        "  restoreRc = NeonHardwareRebindSurface(oldBase, oldW, oldH, oldPitch, oldBytes, oldFormat, oldRotation)\n  If restoreRc",
        """  diagCoordBefore = nbiCoordUs : diagCallsBefore = nbiCoordCalls
  diagMark = Micros()
  restoreRc = NeonHardwareRebindSurface(oldBase, oldW, oldH, oldPitch, oldBytes, oldFormat, oldRotation)
  nbiRestoreRebindUs = Micros() - diagMark
  nbiRestoreCoordUs = nbiCoordUs - diagCoordBefore
  nbiRestoreCoordCalls = nbiCoordCalls - diagCallsBefore
  If restoreRc""")
    measured = replace_once(measured,
        "  ProcedureReturn #ANVIL_VK_JOB_DONE\nEndProcedure\n",
        "  nbiTotalUs = Micros() - diagStart\n  ProcedureReturn #ANVIL_VK_JOB_DONE\nEndProcedure\n")
    globals_source = """; Diagnostic counters exist only in this generated backend include.
Global nbiTotalUs.i, nbiPreUs.i, nbiCacheUs.i
Global nbiTargetRebindUs.i, nbiTargetCoordUs.i, nbiTargetCoordCalls.i
Global nbiBeginUs.i, nbiEmitUs.i, nbiEndUs.i
Global nbiRestoreRebindUs.i, nbiRestoreCoordUs.i, nbiRestoreCoordCalls.i
"""
    return replace_once(source, original, globals_source + measured)


def instrument_matched_core(source: str) -> str:
    source = instrument_core(source)
    source = replace_once(source,
        'XIncludeFile "RaspberryPi4/Lib/neon.pi4"',
        'XIncludeFile "runs/neon-particle-backend-split-desk-20261003/neon.diag.pi4"')
    source = replace_once(source,
        'XIncludeFile "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"',
        'XIncludeFile "runs/neon-particle-backend-split-desk-20261003/vk_v3d_backend.diag.pi4"')
    source = replace_once(source,
        'XIncludeFile "runs/neon-particle-end-split-desk-20261003/neon_vk_chrome.diag.pi4"',
        'XIncludeFile "runs/neon-particle-backend-split-desk-20261003/neon_vk_chrome.diag.pi4"')
    source = replace_once(source, "Global Dim ngpReport.l[128]", "Global Dim ngpReport.l[192]")
    source = replace_once(source,
        "; 64 little-endian report words, 256 bytes; x0 returns @ngpReport[0].",
        "; 192 little-endian report words, 768 bytes; x0 returns @ngpReport[0].")
    tail = "ngpReport[63] = #NGP_TAIL : ngpReport[127] = #NGP_TAIL"
    if source.count(tail) != 2:
        raise ValueError("expected unsafe and normal report tails")
    source = source.replace(tail, tail + " : ngpReport[191] = #NGP_TAIL")
    source = replace_once(source,
        "  ngpReport[66] = #NGP_SAMPLES : ngpReport[127] = #NGP_TAIL\n",
        """  ngpReport[66] = #NGP_SAMPLES : ngpReport[127] = #NGP_TAIL
  ngpReport[128] = $4253504E : ngpReport[129] = 1
  ngpReport[130] = #NGP_SAMPLES : ngpReport[191] = #NGP_TAIL
""")
    source = replace_once(source,
        "      ngpReport[91 + sample] = nveEndTotalUs\n      ngpReport[97 + sample]",
        """      ngpReport[91 + sample] = nveEndTotalUs
      ngpReport[131 + sample] = nbiTotalUs
      ngpReport[134 + sample] = nbiPreUs
      ngpReport[137 + sample] = nbiCacheUs
      ngpReport[140 + sample] = nbiTargetRebindUs
      ngpReport[143 + sample] = nbiTargetCoordUs
      ngpReport[146 + sample] = nbiBeginUs
      ngpReport[149 + sample] = nbiEmitUs
      ngpReport[152 + sample] = nbiEndUs
      ngpReport[155 + sample] = nbiRestoreRebindUs
      ngpReport[158 + sample] = nbiRestoreCoordUs
      ngpReport[161 + sample] = nbiTargetCoordCalls
      ngpReport[164 + sample] = nbiRestoreCoordCalls
      ngpReport[97 + sample]""")
    source = replace_once(source,
        "      ngpReport[109] = nveSubmitCalls - submitBefore\n",
        """      ngpReport[109] = nveSubmitCalls - submitBefore
      ngpReport[167] = nbiTotalUs : ngpReport[168] = nbiPreUs
      ngpReport[169] = nbiCacheUs : ngpReport[170] = nbiTargetRebindUs
      ngpReport[171] = nbiTargetCoordUs : ngpReport[172] = nbiBeginUs
      ngpReport[173] = nbiEmitUs : ngpReport[174] = nbiEndUs
      ngpReport[175] = nbiRestoreRebindUs : ngpReport[176] = nbiRestoreCoordUs
      ngpReport[177] = nbiTargetCoordCalls : ngpReport[178] = nbiRestoreCoordCalls
""")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = resolve_compiler(args.compiler)
    OUT.mkdir(parents=True, exist_ok=True)
    neon_path = OUT / "neon.diag.pi4"
    backend_path = OUT / "vk_v3d_backend.diag.pi4"
    chrome_path = OUT / "neon_vk_chrome.diag.pi4"
    core_path = OUT / "vulkanNeonParticleMatchedProfileCore.diag.pi4"
    entry_path = OUT / "vulkanNeonParticleBackendSplit800.pi4"
    neon_path.write_text(instrument_neon(NEON.read_text(encoding="utf-8-sig")), encoding="utf-8")
    backend_path.write_text(instrument_backend(BACKEND.read_text(encoding="utf-8-sig")), encoding="utf-8")
    chrome_path.write_text(instrument_chrome(CHROME.read_text(encoding="utf-8-sig")), encoding="utf-8")
    core_path.write_text(instrument_matched_core(CORE.read_text(encoding="utf-8-sig")), encoding="utf-8")
    entry_path.write_text('; Returning diagnostic: matched CSD backend split.\n#NMP_GPU = 1\n'
        'XIncludeFile "runs/neon-particle-backend-split-desk-20261003/vulkanNeonParticleMatchedProfileCore.diag.pi4"\n', encoding="utf-8")
    image_path = OUT / "vulkanNeonParticleBackendSplit800.img"
    command = [compiler, "--compile", str(entry_path), "-t", "pi4", "-s", "--entry-returns",
               "--load-addr", "0x800000", "--bss-addr", "0x2000000", "--stack-addr", "0x4000000",
               "-o", str(image_path)]
    result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            text=True, capture_output=True)
    (OUT / "compiler.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode or not image_path.is_file():
        raise SystemExit(f"compile failed; inspect {OUT / 'compiler.log'}")
    image = image_path.read_bytes()
    container_path = Path(str(image_path) + ".pmf")
    container = container_path.read_bytes()
    loader = check_container(container, image)
    symbols = Path(str(image_path) + ".sym").read_text(encoding="utf-8", errors="replace")
    report_lines = [line for line in symbols.splitlines() if line.startswith("global_ngpreport=")]
    if len(report_lines) != 1:
        raise ValueError("report symbol missing or ambiguous")
    report_address = int(report_lines[0].split("=", 1)[1])
    if not (loader["bss_base"] <= report_address and report_address + 768 <= loader["bss_base"] + loader["bss_bytes"]):
        raise ValueError("report lies outside BSS")
    manifest = {
        "execution": "desk compiled only; board not run",
        "source": str(entry_path.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p.read_bytes())
                          for p in (neon_path, backend_path, chrome_path, core_path, entry_path)},
        "production_source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p.read_bytes())
                                     for p in (NEON, BACKEND, CHROME, PARTICLES, CSD, CORE)},
        "compiler": str(compiler), "compile_command": command,
        "image_sha256": sha(image), "image_bytes": len(image),
        "container_sha256": sha(container), "container_bytes": len(container),
        "container": str(container_path.relative_to(ROOT)).replace("\\", "/"),
        "loader": loader, "report_symbol": "global_ngpreport",
        "report_address": report_address, "report_address_hex": f"0x{report_address:08X}",
        "report_bytes": 768, "report_tail_words": [63, 127, 191],
        "checker": "python tools/neon_vk_particle_backend_split_check.py REPORT.BIN",
        "checker_sha256": sha((ROOT / "tools/neon_vk_particle_backend_split_check.py").read_bytes()),
        "unsafe_policy": "Failed submit, failed idle, or lost CSD spins without teardown until the armed deadman resets",
        "board_prerequisite": "Confirm live monitor/memory map and arm a 15-second deadman before load/run",
    }
    (OUT / "safety-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: compiled {image_path.name} ({len(image):,} bytes)")
    print(f"PMFBOOT SHA-256 {sha(container)}")
    print(f"Report 0x{report_address:08X}; manifest {OUT / 'safety-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
