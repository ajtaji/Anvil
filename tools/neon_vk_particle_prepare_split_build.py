"""Build a returning Pi 4 timing payload from diagnostic-only source copies."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs/neon-particle-prepare-split-desk-20261003"
PARTICLES = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
CORE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileCore.pi4"
LOAD = 0x00800000
BSS = 0x02000000
STACK = 0x04000000
MONITOR_END = 0x00800000
SURFACE = (0x06000000, 0x063E8000)
WINDOW = (0x063E8000, 0x073E8000)
ARENA = (0x0A000000, 0x0B000000)


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected one source anchor: {old[:90]!r}")
    return source.replace(old, new)


def instrument_particles(source: str) -> str:
    source = replace_once(
        source,
        "; Prepare validates the whole list before changing retained state or staging.",
        """; Diagnostic timers are present only in this generated include.
Global nvcParticleDiagValidationUs.i, nvcParticleDiagIdleUs.i
Global nvcParticleDiagCopyUs.i, nvcParticleDiagUploadUs.i
Global nvcParticleDiagTotalUs.i, nvcParticleDiagUploadCalls.i
Global nvcParticleDiagReuseCalls.i

; Prepare validates the whole list before changing retained state or staging.""",
    )
    source = replace_once(source, "  Define i.i, rc.i, reusePalette.i\n", "  Define i.i, rc.i, reusePalette.i, diagMark.i, diagEntry.i\n")
    source = replace_once(
        source,
        "  Define *candidate.NvcParticleCorners\n  If nvcReady = 0",
        "  Define *candidate.NvcParticleCorners\n  diagEntry = Micros()\n  If nvcReady = 0",
    )
    source = replace_once(
        source,
        "  ; The retained items describe the last successful upload. Compare packed\n",
        """  nvcParticleDiagValidationUs = 0 : nvcParticleDiagIdleUs = 0
  nvcParticleDiagCopyUs = 0 : nvcParticleDiagUploadUs = 0
  nvcParticleDiagTotalUs = 0
  ; The retained items describe the last successful upload. Compare packed
""",
    )
    source = replace_once(
        source,
        "  For i = 0 To count - 1\n    *p = *particles + i * SizeOf(NvcParticle)\n    If nvcParticleCornerBank = 0\n",
        "  diagMark = Micros()\n  For i = 0 To count - 1\n    *p = *particles + i * SizeOf(NvcParticle)\n    If nvcParticleCornerBank = 0\n",
    )
    source = replace_once(
        source,
        "    If reusePalette <> 0 And *p\\colour <> nvcParticleItems[i]\\colour\n      reusePalette = 0\n    EndIf\n  Next\n  If nvcParticleImage = 0\n",
        "    If reusePalette <> 0 And *p\\colour <> nvcParticleItems[i]\\colour\n      reusePalette = 0\n    EndIf\n  Next\n  nvcParticleDiagValidationUs = Micros() - diagMark\n  If nvcParticleImage = 0\n",
    )
    source = replace_once(
        source,
        "  rc = vkDeviceWaitIdle(nvcDevice)\n  If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf\n  ; The previous draw has completed",
        "  diagMark = Micros()\n  rc = vkDeviceWaitIdle(nvcDevice)\n  nvcParticleDiagIdleUs = Micros() - diagMark\n  If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf\n  ; The previous draw has completed",
    )
    source = replace_once(
        source,
        "  nvcParticlePrepared = 0\n  For i = 0 To count - 1\n    *p = *particles + i * SizeOf(NvcParticle)\n    nvcParticleItems[i]\\x =",
        "  nvcParticlePrepared = 0\n  diagMark = Micros()\n  For i = 0 To count - 1\n    *p = *particles + i * SizeOf(NvcParticle)\n    nvcParticleItems[i]\\x =",
    )
    source = replace_once(
        source,
        "    i = nvcParticleUploadNow()\n    If i <> #VK_SUCCESS : ProcedureReturn nvcFail(i) : EndIf\n  EndIf\n  nvcParticleCount = count",
        """    nvcParticleDiagCopyUs = Micros() - diagMark
    diagMark = Micros()
    i = nvcParticleUploadNow()
    nvcParticleDiagUploadUs = Micros() - diagMark
    nvcParticleDiagUploadCalls = nvcParticleDiagUploadCalls + 1
    If i <> #VK_SUCCESS : ProcedureReturn nvcFail(i) : EndIf
  Else
    nvcParticleDiagCopyUs = Micros() - diagMark
    nvcParticleDiagReuseCalls = nvcParticleDiagReuseCalls + 1
  EndIf
  nvcParticleCount = count""",
    )
    source = replace_once(
        source,
        "  nvcParticleLogicalW = nvcLogicalW : nvcParticleLogicalH = nvcLogicalH\n  nvcError = 0\n  ProcedureReturn #NEON_VK_CHROME_OK\nEndProcedure\n\n; Cache the exact software",
        "  nvcParticleLogicalW = nvcLogicalW : nvcParticleLogicalH = nvcLogicalH\n  nvcParticleDiagTotalUs = Micros() - diagEntry\n  nvcError = 0\n  ProcedureReturn #NEON_VK_CHROME_OK\nEndProcedure\n\n; Cache the exact software",
    )
    return source


def instrument_core(source: str) -> str:
    source = replace_once(
        source,
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"',
        'XIncludeFile "runs/neon-particle-prepare-split-desk-20261003/neon_vk_chrome.diag.pi4"',
    )
    source = replace_once(source, "Global Dim ngpReport.l[64]", "Global Dim ngpReport.l[128]")
    source = replace_once(
        source,
        "  ngpReport[63] = #NGP_TAIL\n  ; UART writes",
        "  ngpReport[63] = #NGP_TAIL : ngpReport[127] = #NGP_TAIL\n  ; UART writes",
    )
    source = replace_once(
        source,
        "  ngpReport[63] = #NGP_TAIL\n  ProcedureReturn @ngpReport[0]",
        "  ngpReport[63] = #NGP_TAIL : ngpReport[127] = #NGP_TAIL\n  ProcedureReturn @ngpReport[0]",
    )
    source = replace_once(
        source,
        "  ngpReport[0] = #NGP_MAGIC : ngpReport[63] = #NGP_TAIL\n",
        """  ngpReport[0] = #NGP_MAGIC : ngpReport[63] = #NGP_TAIL
  ngpReport[64] = $50534D50 : ngpReport[65] = 1
  ngpReport[66] = #NGP_SAMPLES : ngpReport[127] = #NGP_TAIL
""",
    )
    source = replace_once(
        source,
        "    ngpReport[11] = rc\n    If (Micros() - ngpStart) > #NGP_FRAME_BUDGET_US",
        """    ngpReport[11] = rc
    If frame = 0
      ngpReport[86] = nvcParticleDiagValidationUs
      ngpReport[87] = nvcParticleDiagIdleUs
      ngpReport[88] = nvcParticleDiagCopyUs
      ngpReport[89] = nvcParticleDiagUploadUs
      ngpReport[90] = nvcParticleDiagTotalUs
      CompilerIf #NMP_GPU
        ngpReport[91] = nvpcLastPaletteUs
      CompilerEndIf
    EndIf
    If (Micros() - ngpStart) > #NGP_FRAME_BUDGET_US""",
    )
    source = replace_once(
        source,
        "      sample = frame - #NGP_WARMUP\n      ngpReport[16 + sample] = Micros() - t0\n",
        """      sample = frame - #NGP_WARMUP
      ngpReport[16 + sample] = Micros() - t0
      ngpReport[67 + sample] = nvcParticleDiagValidationUs
      ngpReport[70 + sample] = nvcParticleDiagIdleUs
      ngpReport[73 + sample] = nvcParticleDiagCopyUs
      ngpReport[76 + sample] = nvcParticleDiagUploadUs
      ngpReport[79 + sample] = nvcParticleDiagTotalUs
""",
    )
    source = replace_once(
        source,
        "  ngpReport[33] = V3dMmuFaultsNow()\n",
        """  ngpReport[82] = nvcParticleDiagUploadCalls
  ngpReport[83] = nvcParticleDiagReuseCalls
  ngpReport[84] = nvcParticleUploaded
  ngpReport[85] = nvcParticleStageSafe
  ngpReport[33] = V3dMmuFaultsNow()
""",
    )
    return source


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_container(container: bytes, image: bytes) -> dict:
    if len(container) < 128 or container[:8] != b"PMFBOOT\x00":
        raise ValueError("missing PMFBOOT header")
    version, header_bytes = struct.unpack_from("<II", container, 8)
    load, entry, image_bytes, bss, bss_bytes = struct.unpack_from("<QQQQQ", container, 16)
    flags = struct.unpack_from("<I", container, 56)[0]
    arch, target = struct.unpack_from("<II", container, 96)
    if version != 2 or header_bytes != 128 or target != 2711 or arch != 1 or flags != 1:
        raise ValueError(f"unexpected PMFBOOT header: {(version, target, arch)}")
    if load != LOAD or entry != LOAD or image_bytes != len(image) or bss != BSS:
        raise ValueError("load, entry, image, or BSS disagrees with build")
    if container[128:] != image or container[64:96] != hashlib.sha256(image).digest():
        raise ValueError("container image or digest disagrees with linked image")
    if any(container[60:64]) or any(container[112:128]):
        raise ValueError("PMFBOOT reserved bytes are not zero")
    stack = struct.unpack_from("<Q", container, 104)[0]
    if stack != STACK:
        raise ValueError("unexpected stack")
    ranges = {
        "monitor_reserved": [0x00200000, MONITOR_END],
        "image": [load, load + image_bytes],
        "bss": [bss, bss + bss_bytes],
        "stack_reserved": [0x03000000, stack],
        "surface": list(SURFACE),
        "vulkan_window": list(WINDOW),
        "neon_arena": list(ARENA),
    }
    intervals = list(ranges.items())
    for index, (name_a, (start_a, end_a)) in enumerate(intervals):
        if start_a >= end_a:
            raise ValueError(f"empty range {name_a}")
        for name_b, (start_b, end_b) in intervals[index + 1:]:
            if start_a < end_b and start_b < end_a:
                raise ValueError(f"overlapping ranges: {name_a}, {name_b}")
    return {"format": "PMFBOOT v2", "load": load, "entry": entry,
            "image_bytes": image_bytes, "bss_base": bss, "bss_bytes": bss_bytes,
            "stack_top": stack, "ranges_half_open": ranges, "flags": flags}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = resolve_compiler(args.compiler)
    OUT.mkdir(parents=True, exist_ok=True)
    particle_path = OUT / "neon_vk_particles.diag.pi4"
    chrome_path = OUT / "neon_vk_chrome.diag.pi4"
    core_path = OUT / "vulkanNeonParticleMatchedProfileCore.diag.pi4"
    entry_path = OUT / "vulkanNeonParticlePrepareSplit.pi4"
    particle_path.write_text(instrument_particles(PARTICLES.read_text(encoding="utf-8-sig")), encoding="utf-8")
    chrome_path.write_text(replace_once(CHROME.read_text(encoding="utf-8-sig"),
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"',
        'XIncludeFile "runs/neon-particle-prepare-split-desk-20261003/neon_vk_particles.diag.pi4"'), encoding="utf-8")
    core_path.write_text(instrument_core(CORE.read_text(encoding="utf-8-sig")), encoding="utf-8")
    entry_path.write_text('; Returning diagnostic: instrumented matched CSD profile.\n#NMP_GPU = 1\n'
        'XIncludeFile "runs/neon-particle-prepare-split-desk-20261003/vulkanNeonParticleMatchedProfileCore.diag.pi4"\n', encoding="utf-8")
    image_path = OUT / "vulkanNeonParticlePrepareSplit.img"
    command = [compiler, "--compile", str(entry_path), "-t", "pi4", "-s", "--entry-returns",
               "--load-addr", hex(LOAD), "--bss-addr", hex(BSS), "--stack-addr", hex(STACK),
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
    symbols = symbols_path.read_text(encoding="utf-8", errors="replace") if symbols_path.exists() else ""
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
                          for p in (particle_path, chrome_path, core_path, entry_path)},
        "production_source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p.read_bytes())
                                     for p in (PARTICLES, CHROME, CORE)},
        "compiler": str(compiler), "compile_command": command,
        "image_sha256": sha(image), "image_bytes": len(image),
        "container_sha256": sha(container), "container_bytes": len(container),
        "loader": loader, "report_symbol": "global_ngpreport",
        "report_address": report_address, "report_address_hex": f"0x{report_address:08X}",
        "report_bytes": 512, "report_tail_words": [63, 127],
        "checker_sha256": sha((ROOT / "tools/neon_vk_particle_prepare_split_check.py").read_bytes()),
        "checker": "python tools/neon_vk_particle_prepare_split_check.py REPORT.BIN",
        "unsafe_policy": "Failed submit, failed device idle, or lost CSD spins without teardown until the armed deadman resets",
        "board_prerequisite": "Confirm live monitor/memory map and arm a 15-second deadman before load/run",
    }
    (OUT / "safety-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: compiled {image_path.name} ({len(image):,} bytes)")
    print(f"PMFBOOT SHA-256 {sha(container)}")
    print(f"Manifest: {OUT / 'safety-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
