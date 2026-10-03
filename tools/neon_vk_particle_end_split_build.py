"""Build an 800x800 returning particle End timing diagnostic."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from pmf_compiler import resolve_compiler
from neon_vk_particle_prepare_split_build import check_container, replace_once, sha


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs/neon-particle-end-split-desk-20261003"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
PARTICLES = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"
BACKEND = ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
CORE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileCore.pi4"
CSD = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4"


def procedure(source: str, name: str) -> str:
    start = source.index(f"Procedure.i {name}()\n")
    end = source.index("EndProcedure\n", start) + len("EndProcedure\n")
    return source[start:end]


def instrument_chrome(source: str) -> str:
    original = procedure(source, "nvcSubmitAndWait")
    measured = replace_once(original, "  Define rc.i\n", "  Define rc.i, diagMark.i\n")
    measured = replace_once(
        measured,
        "  nvcSubmitStage = 2 : nvcSubmitRc = #VK_SUCCESS\n",
        "  nveResetUs = 0 : nveSubmitUs = 0 : nveFenceUs = 0\n  nvcSubmitStage = 2 : nvcSubmitRc = #VK_SUCCESS\n",
    )
    measured = replace_once(
        measured,
        "  rc = vkResetFences(nvcDevice, 1, @fenceHandle)\n",
        "  diagMark = Micros()\n  rc = vkResetFences(nvcDevice, 1, @fenceHandle)\n  nveResetUs = Micros() - diagMark\n",
    )
    measured = replace_once(
        measured,
        "    rc = vkQueueSubmit(nvcQueue, 1, @si, nvcFence)\n",
        "    diagMark = Micros()\n    rc = vkQueueSubmit(nvcQueue, 1, @si, nvcFence)\n    nveSubmitUs = Micros() - diagMark\n    nveSubmitCalls = nveSubmitCalls + 1\n",
    )
    measured = replace_once(
        measured,
        "    rc = vkWaitForFences(nvcDevice, 1, @fenceHandle, 1, #NEON_VK_CHROME_WAIT_NS)\n",
        "    diagMark = Micros()\n    rc = vkWaitForFences(nvcDevice, 1, @fenceHandle, 1, #NEON_VK_CHROME_WAIT_NS)\n    nveFenceUs = Micros() - diagMark\n",
    )
    source = replace_once(source, original,
        """; Diagnostic counters belong only to this generated Chrome copy.
Global nveResetUs.i, nveSubmitUs.i, nveFenceUs.i, nveSubmitCalls.i
Global nveEndPreUs.i, nveEndPostUs.i, nveEndTotalUs.i
""" + measured)

    original = procedure(source, "NeonVkChromeEnd")
    measured = replace_once(original, "  Define rc.i\n", "  Define rc.i, diagStart.i, diagMark.i\n  diagStart = Micros()\n  nveEndPreUs = 0 : nveEndPostUs = 0 : nveEndTotalUs = 0\n")
    measured = replace_once(
        measured,
        "  If rc = #VK_SUCCESS : rc = nvcSubmitAndWait() : EndIf\n  nvcInFrame = 0\n",
        "  nveEndPreUs = Micros() - diagStart\n  If rc = #VK_SUCCESS : rc = nvcSubmitAndWait() : EndIf\n  diagMark = Micros()\n  nvcInFrame = 0\n",
    )
    measured = replace_once(
        measured,
        "  ProcedureReturn #VK_SUCCESS\nEndProcedure\n",
        "  nveEndPostUs = Micros() - diagMark\n  nveEndTotalUs = Micros() - diagStart\n  ProcedureReturn #VK_SUCCESS\nEndProcedure\n",
    )
    return replace_once(source, original, measured)


def instrument_core(source: str) -> str:
    source = replace_once(source,
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"',
        'XIncludeFile "runs/neon-particle-end-split-desk-20261003/neon_vk_chrome.diag.pi4"')
    source = replace_once(source, "Global Dim ngpReport.l[64]", "Global Dim ngpReport.l[128]")
    source = replace_once(source, "  ngpReport[63] = #NGP_TAIL\n  ; UART writes",
        "  ngpReport[63] = #NGP_TAIL : ngpReport[127] = #NGP_TAIL\n  ; UART writes")
    source = replace_once(source, "  ngpReport[63] = #NGP_TAIL\n  ProcedureReturn @ngpReport[0]",
        "  ngpReport[63] = #NGP_TAIL : ngpReport[127] = #NGP_TAIL\n  ProcedureReturn @ngpReport[0]")
    source = replace_once(source, "  Define binBefore.i, renderBefore.i\n",
        "  Define binBefore.i, renderBefore.i, submitBefore.i\n")
    source = replace_once(source,
        "  ngpReport[0] = #NGP_MAGIC : ngpReport[63] = #NGP_TAIL\n",
        """  ngpReport[0] = #NGP_MAGIC : ngpReport[63] = #NGP_TAIL
  ngpReport[64] = $454E4453 : ngpReport[65] = 1
  ngpReport[66] = #NGP_SAMPLES : ngpReport[127] = #NGP_TAIL
""")
    source = replace_once(source,
        "    binBefore = V3dBinJobs() : renderBefore = V3dRenderJobs()\n    ngpVulkanSubmitted = 1 : t0 = Micros()\n",
        """    binBefore = V3dBinJobs() : renderBefore = V3dRenderJobs()
    submitBefore = nveSubmitCalls
    ngpVulkanSubmitted = 1 : t0 = Micros()
""")
    source = replace_once(source,
        "    ngpVulkanSubmitted = 0\n    ngpReport[31] = ngpReport[31] + V3dBinJobs() - binBefore\n",
        """    ngpVulkanSubmitted = 0
    If frame >= #NGP_WARMUP
      sample = frame - #NGP_WARMUP
      ngpReport[67 + sample] = nveEndPreUs
      ngpReport[70 + sample] = nveResetUs
      ngpReport[73 + sample] = nveSubmitUs
      ngpReport[76 + sample] = nveFenceUs
      ngpReport[79 + sample] = nveEndPostUs
      ngpReport[82 + sample] = Neon_UsClean()
      ngpReport[85 + sample] = Neon_UsBin()
      ngpReport[88 + sample] = Neon_UsRender()
      ngpReport[91 + sample] = nveEndTotalUs
      ngpReport[97 + sample] = nveSubmitCalls - submitBefore
    Else
      ngpReport[100] = nveEndPreUs : ngpReport[101] = nveResetUs
      ngpReport[102] = nveSubmitUs : ngpReport[103] = nveFenceUs
      ngpReport[104] = nveEndPostUs : ngpReport[105] = Neon_UsClean()
      ngpReport[106] = Neon_UsBin() : ngpReport[107] = Neon_UsRender()
      ngpReport[108] = nveEndTotalUs
      ngpReport[109] = nveSubmitCalls - submitBefore
    EndIf
    ngpReport[31] = ngpReport[31] + V3dBinJobs() - binBefore
""")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = resolve_compiler(args.compiler)
    OUT.mkdir(parents=True, exist_ok=True)
    chrome_path = OUT / "neon_vk_chrome.diag.pi4"
    core_path = OUT / "vulkanNeonParticleMatchedProfileCore.diag.pi4"
    entry_path = OUT / "vulkanNeonParticleEndSplit800.pi4"
    chrome_path.write_text(instrument_chrome(CHROME.read_text(encoding="utf-8-sig")), encoding="utf-8")
    core_path.write_text(instrument_core(CORE.read_text(encoding="utf-8-sig")), encoding="utf-8")
    entry_path.write_text('; Returning diagnostic: 800x800 matched CSD End split.\n#NMP_GPU = 1\n'
        'XIncludeFile "runs/neon-particle-end-split-desk-20261003/vulkanNeonParticleMatchedProfileCore.diag.pi4"\n', encoding="utf-8")
    image_path = OUT / "vulkanNeonParticleEndSplit800.img"
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
    symbols_path = Path(str(image_path) + ".sym")
    symbols = symbols_path.read_text(encoding="utf-8", errors="replace")
    report_lines = [line for line in symbols.splitlines() if line.startswith("global_ngpreport=")]
    if len(report_lines) != 1:
        raise ValueError("report symbol missing or ambiguous")
    report_address = int(report_lines[0].split("=", 1)[1])
    if not (loader["bss_base"] <= report_address and report_address + 512 <= loader["bss_base"] + loader["bss_bytes"]):
        raise ValueError("report lies outside BSS")
    manifest = {
        "execution": "desk compiled only; board not run",
        "source": str(entry_path.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p.read_bytes())
                          for p in (chrome_path, core_path, entry_path)},
        "production_source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p.read_bytes())
                                     for p in (CHROME, PARTICLES, BACKEND, CORE, CSD)},
        "compiler": str(compiler), "compile_command": command,
        "image_sha256": sha(image), "image_bytes": len(image),
        "container_sha256": sha(container), "container_bytes": len(container),
        "container": str(container_path.relative_to(ROOT)).replace("\\", "/"),
        "loader": loader, "report_symbol": "global_ngpreport",
        "report_address": report_address, "report_address_hex": f"0x{report_address:08X}",
        "report_bytes": 512, "report_tail_words": [63, 127],
        "checker": "python tools/neon_vk_particle_end_split_check.py REPORT.BIN",
        "checker_sha256": sha((ROOT / "tools/neon_vk_particle_end_split_check.py").read_bytes()),
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
