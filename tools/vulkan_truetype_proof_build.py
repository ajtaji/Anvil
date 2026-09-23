#!/usr/bin/env python3
"""Build a returning Vulkan TrueType proof with a licensed embedded fixture.

Font binaries and generated source stay under _work; this is a diagnostic
payload builder, not a repository font asset installer.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetProof.pi4"
SCENE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAcceptanceScene.pbi"
FONT = ROOT / "_work/truetype-fonts-20260918/abel/Abel-Regular.ttf"
LICENSE = ROOT / "_work/truetype-fonts-20260918/abel/OFL.txt"
OUT = ROOT / "_work/vulkan-truetype-proof-20260918"
EXPORT = OUT / "clean-export"

OVERLAY = (
    "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4",
    "Anvil/Graphics/Vulkan/vk_v3d_shader.pi4",
    "Anvil/Graphics/truetype.pbi",
    "Anvil/Graphics/truetype_metrics.pbi",
    "Anvil/Graphics/truetype_cmap.pbi",
    "Anvil/Graphics/truetype_outlines.pbi",
    "Anvil/Graphics/truetype_raster.pbi",
    "Anvil/Graphics/truetype_kern.pbi",
    "Anvil/Graphics/truetype_gpos.pbi",
    "Anvil/Graphics/truetype_layout.pbi",
    "Anvil/Graphics/truetype_slots.pbi",
    "Anvil/Graphics/truetype_renderer.pbi",
    "RaspberryPi4/Board/board.pi4",
    "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetProof.pi4",
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"expected one {label} anchor, got {text.count(old)}")
    return text.replace(old, new, 1)


def emit_font_data(data: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for offset in range(0, len(data), 24):
        rows.append("  Data.a " + ",".join(str(b) for b in data[offset:offset + 24]))
    target.write_text(
        f"#TT_FONT_BYTES = {len(data)}\nDataSection\n  ttFontStart:\n" + "\n".join(rows)
        + "\n  ttFontEnd:\n"
        + "  ttSampleUtf8:\n  Data.a 79,195,169,195,133,32,65,86,65,84,65,82,0\n"
        + "EndDataSection\n",
        encoding="utf-8",
        newline="\n",
    )


def build_sources() -> tuple[Path, Path, dict[str, object]]:
    data = FONT.read_bytes()
    license_text = LICENSE.read_text(encoding="utf-8")
    if "SIL OPEN FONT LICENSE" not in license_text:
        raise SystemExit("Abel fixture license is missing or unexpected")
    sha = hashlib.sha256(data).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "OFL.txt").write_text(license_text, encoding="utf-8", newline="\n")
    data_include = OUT / "abel_font_data.pbi"
    emit_font_data(data, data_include)

    scene = SCENE.read_text(encoding="utf-8")
    # One full-surface box and three strings. The string has ten codepoints,
    # nine visible outlines (space is empty), and eight unique glyphs.
    for name, value in {
        "NVWA_EXPECT_BOX_CALLS": 1,
        "NVWA_EXPECT_TEXT_CALLS": 3,
        "NVWA_EXPECT_GLYPH_QUADS": 27,
        "NVWA_EXPECT_QUADS": 28,
        "NVWA_EXPECT_DRAWS": 4,
        "NVWA_EXPECT_VERTICES": 168,
        "NVWA_EXPECT_SCISSOR_CALLS": 0,
    }.items():
        scene, count = re.subn(rf"(?m)^#{name}\s*=\s*\d+\s*$", f"#{name} = {value}", scene)
        if count != 1:
            raise SystemExit(f"could not set exact TT scene ledger: {name}")
    start = scene.index("Procedure.i NvwaCompose()")
    end = scene.index("EndProcedure", start) + len("EndProcedure")
    compose = '''Procedure.i NvwaCompose()
  If NeonDrawBackendActive() = 0
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf
  If NeonVkChromeBox(0, 0, #NVWA_WIDTH, #NVWA_HEIGHT, Neon_C_Bg) <> #NEON_VK_CHROME_OK
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf
  If NeonVkChromeTrueTypeText(16, 48, 150, ?ttSampleUtf8, Neon_C_Text) <> #NEON_VK_CHROME_OK
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf
  If NeonVkChromeTrueTypeText(24, 48, 230, ?ttSampleUtf8, Neon_C_Acc) <> #NEON_VK_CHROME_OK
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf
  If NeonVkChromeTrueTypeText(40, 48, 340, ?ttSampleUtf8, Neon_C_Text) <> #NEON_VK_CHROME_OK
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf
  ProcedureReturn #NVWA_OK
EndProcedure'''
    scene = scene[:start] + compose + scene[end:]
    # This specimen does not use immediate-mode widgets, so there is no
    # measurement pass. Keep the same lifecycle call in the payload.
    pstart = scene.index("Procedure.i NvwaPrime()")
    pend = scene.index("EndProcedure", pstart) + len("EndProcedure")
    scene = scene[:pstart] + '''Procedure.i NvwaPrime()
  If NeonDrawBackendActive() <> 0 : ProcedureReturn #NVWA_ERR_NO_BACKEND : EndIf
  If Neon_SurfaceW() <> #NVWA_WIDTH Or Neon_SurfaceH() <> #NVWA_HEIGHT
    ProcedureReturn #NVWA_ERR_GEOMETRY
  EndIf
  ProcedureReturn #NVWA_OK
EndProcedure''' + scene[pend:]
    scene = replace_once(
        scene,
        "If NeonVkChromeDrawCount() <> #NVWA_EXPECT_DRAWS Or NeonVkChromeVertexCount() <> #NVWA_EXPECT_VERTICES",
        "If NeonVkChromeDrawCount() <> #NVWA_EXPECT_DRAWS Or NeonVkChromeVertexCount() <> #NVWA_EXPECT_VERTICES",
        "TrueType scene minimum geometry assertion",
    )
    scene_path = OUT / "vulkanTrueTypeScene.pbi"
    scene_path.write_text(scene, encoding="utf-8", newline="\n")

    proof = BASE.read_text(encoding="utf-8")
    proof = proof.replace(
        'XIncludeFile "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAcceptanceScene.pbi"',
        f'XIncludeFile "{scene_path.relative_to(ROOT).as_posix()}"',
    )
    proof = replace_once(
        proof,
        'XIncludeFile "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetProof.pi4"',
        'XIncludeFile "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetProof.pi4"',
        "unused safeguard",
    ) if False else proof
    proof = replace_once(
        proof,
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"',
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"\n'
        + f'XIncludeFile "{data_include.relative_to(ROOT).as_posix()}"',
        "font data include",
    )
    proof = replace_once(
        proof,
        "#NW_REPORT_WORDS      = 64\n#NW_REPORT_BYTES      = #NW_REPORT_WORDS * 4",
        "#NW_REPORT_WORDS      = 111\n#NW_REPORT_BYTES      = #NW_REPORT_WORDS * 4",
        "extended report length",
    )
    proof = replace_once(proof, "#NW_S_RESERVED        = 62\n#NW_S_TAIL            = 63",
                         "#NW_S_TT_COLD_RASTER = 62\n#NW_S_TT_COLD_UPLOAD = 63\n#NW_S_TT_WARM_RASTER = 64\n#NW_S_TT_WARM_UPLOAD = 65\n#NW_S_TT_WARM_HITS = 66\n#NW_S_TT_FONT_BYTES = 67\n#NW_S_TT_COVERAGE_16 = 68\n#NW_S_TT_COVERAGE_24 = 69\n#NW_S_TT_COVERAGE_40 = 70\n#NW_S_CREATE_STAGE = 71\n#NW_S_CREATE_FAULT = 72\n#NW_S_CREATE_FAULT_TEXT = 73\n#NW_S_WARM_16_RC = 74\n#NW_S_WARM_24_RC = 75\n#NW_S_WARM_40_RC = 76\n#NW_S_LAYOUT_RC = 77\n#NW_S_LAYOUT_ERROR = 78\n#NW_S_TT_DRAW_STAGE = 79\n#NW_S_TT_UNITS = 80\n#NW_S_TT_COUNT = 81\n#NW_S_TT_LINES = 82\n#NW_S_TT_MEASURED = 83\n#NW_S_TT_METRICS_OPEN = 84\n#NW_S_SUBMIT_STAGE = 85\n#NW_S_SUBMIT_RC = 86\n#NW_S_VK_FAULT = 87\n#NW_S_VK_FAULT_TEXT = 88\n#NW_S_NATIVE_ERROR = 89\n#NW_S_V3D_ERROR = 90\n#NW_S_RENDER_MMU_CTL = 91\n#NW_S_RENDER_VIO_ADDR = 92\n#NW_S_RENDER_VIO_ID = 93\n#NW_S_RENDER_ERR_STAT = 94\n#NW_S_RENDER_PCS = 95\n#NW_S_LIVE_MMU_CTL = 96\n#NW_S_LIVE_VIO_ADDR = 97\n#NW_S_ATLAS_ADDRESS = 98\n#NW_S_ATLAS_SIZE = 99\n#NW_S_ATLAS_MEMORY_ADDRESS = 100\n#NW_S_ATLAS_MEMORY_SIZE = 101\n#NW_S_UPLOAD_MEMORY_ADDRESS = 102\n#NW_S_UPLOAD_MEMORY_SIZE = 103\n#NW_S_VERTEX_MEMORY_ADDRESS = 104\n#NW_S_VERTEX_MEMORY_SIZE = 105\n#NW_S_LAST_RECORD = 108\n#NW_S_LAST_RECORD_BYTES = 109\n#NW_S_TAIL = 110", "TT report slots")
    proof = replace_once(
        proof,
        "  nwPut(#NW_S_FAULT_COUNT, AnvilVkFaultCount())\n  nwPut(#NW_S_FAULT_TEXT, AnvilVkFaultText())\n",
        "  nwPut(#NW_S_FAULT_COUNT, AnvilVkFaultCount())\n"
        + "  nwPut(#NW_S_FAULT_TEXT, nvcCreateFaultText)\n"
        + "  nwPut(#NW_S_CREATE_STAGE, nvcCreateStage)\n"
        + "  nwPut(#NW_S_CREATE_FAULT, nvcCreateFaultCode)\n"
        + "  nwPut(#NW_S_CREATE_FAULT_TEXT, nvcCreateFaultText)\n",
        "preserve original adapter fault for diagnostics",
    )
    proof = replace_once(
        proof,
        "  Define mapped.i\n",
        "  Define mapped.i\n  Define ttRaster0.i, ttUpload0.i, ttHit0.i, ttColdRaster.i, ttColdUpload.i, ttWarmRaster.i, ttWarmUpload.i, ttWarmHits.i, ttWarmOk.i\n  Define ttCoverage16.i, ttCoverage24.i, ttCoverage40.i\n  Define ttWarm16Rc.i, ttWarm24Rc.i, ttWarm40Rc.i\n",
        "TT counter locals",
    )
    proof = replace_once(
        proof,
        "  nwPut(#NW_S_TAIL, #NW_TAIL)\n",
        "  nwPut(#NW_S_TAIL, #NW_TAIL)\n"
        + "  nwPut(#NW_S_TT_FONT_BYTES, #TT_FONT_BYTES)\n"
        ,
        "initialize TT report font length",
    )
    proof = replace_once(
        proof,
        "  nwSeedProbes()\n  TimerInit()\n",
        "  nwSeedProbes()\n"
        + "  If AnvilTrueTypeSlotLoad(0, ?ttFontStart, #TT_FONT_BYTES) = 0\n"
        + "    ProcedureReturn nwReturn(#NW_ERR_SCENE)\n  EndIf\n"
        + "  If AnvilTrueTypeSlotSelect(0) = 0\n"
        + "    AnvilTrueTypeSlotDeselect()\n    ProcedureReturn nwReturn(#NW_ERR_SCENE)\n  EndIf\n"
        + "  TimerInit()\n",
        "load Abel after report initialization",
    )
    warm_lines = []
    for height in (16, 24, 40):
        variable = {16: "ttWarm16Rc", 24: "ttWarm24Rc", 40: "ttWarm40Rc"}[height]
        warm_lines.append(f'  {variable} = NeonVkChromeWarmTrueTypeText({height}, ?ttSampleUtf8)')
        warm_lines.append(f'  If {variable} < 0 : ttWarmOk = 0 : EndIf')
    cold_capture = '''  ttColdRaster = AnvilTrueTypeRasterCount() - ttRaster0
  ttColdUpload = NeonVkChromeAtlasUploadCount() - ttUpload0
  ttHit0 = NeonVkChromeTTCacheHits()
  ttRaster0 = AnvilTrueTypeRasterCount()
  ttUpload0 = NeonVkChromeAtlasUploadCount()
'''
    proof = replace_once(
        proof,
        "  adapterMade = 1\n",
        "  adapterMade = 1\n"
        + "  ttWarmOk = 1\n  ttRaster0 = AnvilTrueTypeRasterCount()\n  ttUpload0 = NeonVkChromeAtlasUploadCount()\n"
        + "\n".join(warm_lines) + "\n"
        + cold_capture + "\n".join(warm_lines) + "\n"
        + "  ttWarmRaster = AnvilTrueTypeRasterCount() - ttRaster0\n"
        + "  ttWarmUpload = NeonVkChromeAtlasUploadCount() - ttUpload0\n"
        + "  ttWarmHits = NeonVkChromeTTCacheHits() - ttHit0\n",
        "cold/warm TrueType prewarm",
    )
    proof = replace_once(
        proof,
        "  ttWarmHits = NeonVkChromeTTCacheHits() - ttHit0\n",
        "  ttWarmHits = NeonVkChromeTTCacheHits() - ttHit0\n"
        + "  nwPut(#NW_S_WARM_16_RC, ttWarm16Rc)\n"
        + "  nwPut(#NW_S_WARM_24_RC, ttWarm24Rc)\n"
        + "  nwPut(#NW_S_WARM_40_RC, ttWarm40Rc)\n"
        + "  nwPut(#NW_S_TT_COLD_RASTER, ttColdRaster)\n"
        + "  nwPut(#NW_S_TT_COLD_UPLOAD, ttColdUpload)\n"
        + "  nwPut(#NW_S_TT_WARM_RASTER, ttWarmRaster)\n"
        + "  nwPut(#NW_S_TT_WARM_UPLOAD, ttWarmUpload)\n"
        + "  nwPut(#NW_S_TT_WARM_HITS, ttWarmHits)\n"
        + "  If ttWarmOk = 0 Or ttWarm16Rc <> 10 Or ttWarm24Rc <> 10 Or ttWarm40Rc <> 10\n"
        + "    nwPut(#NW_S_STEP, 8)\n"
        + "    NeonVkChromeDestroy()\n"
        + "    vkDeviceWaitIdle(dev)\n"
        + "    vkDestroyFramebuffer(dev, framebuffer, 0)\n"
        + "    vkDestroyRenderPass(dev, renderPass, 0)\n"
        + "    vkDestroyImageView(dev, view, 0)\n"
        + "    vkDestroyImage(dev, image, 0)\n"
        + "    vkFreeMemory(dev, memory, 0)\n"
        + "    vkDestroyCommandPool(dev, pool, 0)\n"
        + "    vkDestroyDevice(dev, 0)\n"
        + "    vkDestroyInstance(inst, 0)\n"
        + "    NeonShutdown()\n"
        + "    ProcedureReturn nwReturn(#NW_ERR_SCENE)\n"
        + "  EndIf\n",
        "fail closed and clean up when TT warm-up fails",
    )
    proof = replace_once(
        proof,
        "  nwPut(#NW_S_PRESENT_PENDING, NeonVkChromePresentPending())\n",
        "  nwPut(#NW_S_PRESENT_PENDING, NeonVkChromePresentPending())\n"
        + "  nwPut(#NW_S_TT_COLD_RASTER, ttColdRaster)\n"
        + "  nwPut(#NW_S_TT_COLD_UPLOAD, ttColdUpload)\n"
        + "  nwPut(#NW_S_TT_WARM_RASTER, ttWarmRaster)\n"
        + "  nwPut(#NW_S_TT_WARM_UPLOAD, ttWarmUpload)\n"
        + "  nwPut(#NW_S_TT_WARM_HITS, ttWarmHits)\n"
        + "  nwPut(#NW_S_WARM_16_RC, ttWarm16Rc)\n"
        + "  nwPut(#NW_S_WARM_24_RC, ttWarm24Rc)\n"
        + "  nwPut(#NW_S_WARM_40_RC, ttWarm40Rc)\n"
        + "  nwPut(#NW_S_LAYOUT_RC, nvcTTLayoutRc)\n"
        + "  nwPut(#NW_S_LAYOUT_ERROR, nvcTTLayoutError)\n"
        + "  nwPut(#NW_S_TT_DRAW_STAGE, nvcTTErrorStage)\n"
        + "  nwPut(#NW_S_TT_UNITS, nvcTTUnitsProbe)\n"
        + "  nwPut(#NW_S_TT_COUNT, nvcTTCountProbe)\n"
        + "  nwPut(#NW_S_TT_LINES, nvcTTLinesProbe)\n"
        + "  nwPut(#NW_S_TT_MEASURED, nvcTTMeasuredProbe)\n"
        + "  nwPut(#NW_S_TT_METRICS_OPEN, nvcTTMetricsStateProbe)\n"
        + "  nwPut(#NW_S_SUBMIT_STAGE, nvcSubmitStage)\n"
        + "  nwPut(#NW_S_SUBMIT_RC, nvcSubmitRc)\n"
        + "  nwPut(#NW_S_VK_FAULT, AnvilVkFaultCode())\n"
        + "  nwPut(#NW_S_VK_FAULT_TEXT, AnvilVkFaultText())\n"
        + "  nwPut(#NW_S_NATIVE_ERROR, avkBackendLastNativeError())\n"
        + "  nwPut(#NW_S_V3D_ERROR, V3dError())\n"
        + "  nwPut(#NW_S_RENDER_MMU_CTL, V3dRenderMmuCtl())\n"
        + "  nwPut(#NW_S_RENDER_VIO_ADDR, V3dRenderVioAddr())\n"
        + "  nwPut(#NW_S_RENDER_VIO_ID, V3dRenderVioId())\n"
        + "  nwPut(#NW_S_RENDER_ERR_STAT, V3dRenderErrStat())\n"
        + "  nwPut(#NW_S_RENDER_PCS, V3dRenderPcs())\n"
        + "  nwPut(#NW_S_LIVE_MMU_CTL, V3dMmuCtlNow())\n"
        + "  nwPut(#NW_S_LIVE_VIO_ADDR, V3dMmuVioAddrNow())\n"
        + "  nwPut(#NW_S_ATLAS_ADDRESS, AnvilVkImageAddress(nvcAtlasImage))\n"
        + "  nwPut(#NW_S_ATLAS_SIZE, AnvilVkImageSize(nvcAtlasImage))\n"
        + "  nwPut(#NW_S_ATLAS_MEMORY_ADDRESS, AnvilVkMemoryAddress(nvcAtlasMemory))\n"
        + "  nwPut(#NW_S_ATLAS_MEMORY_SIZE, AnvilVkMemorySize(nvcAtlasMemory))\n"
        + "  nwPut(#NW_S_UPLOAD_MEMORY_ADDRESS, AnvilVkMemoryAddress(nvcUploadMemory))\n"
        + "  nwPut(#NW_S_UPLOAD_MEMORY_SIZE, AnvilVkMemorySize(nvcUploadMemory))\n"
        + "  nwPut(#NW_S_VERTEX_MEMORY_ADDRESS, AnvilVkMemoryAddress(nvcVertexMemory))\n"
        + "  nwPut(#NW_S_VERTEX_MEMORY_SIZE, AnvilVkMemorySize(nvcVertexMemory))\n"
        + "  nwPut(#NW_S_LAST_RECORD, AnvilVkV3dLastShaderRecord())\n"
        + "  nwPut(#NW_S_LAST_RECORD_BYTES, AnvilVkV3dLastShaderRecordBytes())\n",
        "TT counters in report",
    )
    proof = replace_once(
        proof,
        "  nwCapturePixels(imageBase, imagePitch)\n",
        "  nwCapturePixels(imageBase, imagePitch)\n"
        + "  ttCoverage16 = nwCountDifferent(imageBase, imagePitch, 40, 135, 360, 205)\n"
        + "  ttCoverage24 = nwCountDifferent(imageBase, imagePitch, 40, 205, 420, 320)\n"
        + "  ttCoverage40 = nwCountDifferent(imageBase, imagePitch, 40, 310, 560, 470)\n"
        + "  nwPut(#NW_S_TT_COVERAGE_16, ttCoverage16)\n"
        + "  nwPut(#NW_S_TT_COVERAGE_24, ttCoverage24)\n"
        + "  nwPut(#NW_S_TT_COVERAGE_40, ttCoverage40)\n",
        "coverage readback",
    )
    proof = replace_once(
        proof,
        "Procedure nwCapturePixels(base.i, pitch.i)\n",
        "Procedure.i nwCountDifferent(base.i, pitch.i, x0.i, y0.i, x1.i, y1.i)\n"
        "  Define x.i, y.i, reference.i, count.i\n"
        "  reference = PeekL(base + y0 * pitch + x0 * 4)\n"
        "  For y = y0 To y1 - 1\n"
        "    For x = x0 To x1 - 1\n"
        "      If PeekL(base + y * pitch + x * 4) <> reference : count + 1 : EndIf\n"
        "    Next\n  Next\n  ProcedureReturn count\nEndProcedure\n\n"
        "Procedure nwCapturePixels(base.i, pitch.i)\n",
        "coverage readback helper",
    )
    proof = replace_once(
        proof,
        "  If nwGet(#NW_S_DRAW_ACTUAL) <> #NVWA_EXPECT_DRAWS Or nwGet(#NW_S_VERTEX_ACTUAL) <> #NVWA_EXPECT_VERTICES",
        "  If nwGet(#NW_S_DRAW_ACTUAL) <> #NVWA_EXPECT_DRAWS Or nwGet(#NW_S_VERTEX_ACTUAL) <> #NVWA_EXPECT_VERTICES",
        "payload geometry floor",
    )
    proof = proof.replace("  NeonVkChromeDestroy()\n", "  NeonVkChromeDestroy()\n  AnvilTrueTypeSlotDeselect()\n")
    proof = re.sub(
        r"(?m)^(\s*)ProcedureReturn nwReturn\(",
        r"\1AnvilTrueTypeSlotDeselect()\n\1ProcedureReturn nwReturn(",
        proof,
    )
    proof = replace_once(
        proof,
        "  If nwGet(#NW_S_READY_AFTER) <> 0 Or NeonDrawBackendActive() <> 0\n    AnvilTrueTypeSlotDeselect()\n    ProcedureReturn nwReturn(#NW_ERR_ADAPTER)\n  EndIf\n"
        "  AnvilTrueTypeSlotDeselect()\n  ProcedureReturn nwReturn(#NW_OK)",
        "  If nwGet(#NW_S_READY_AFTER) <> 0 Or NeonDrawBackendActive() <> 0\n    AnvilTrueTypeSlotDeselect()\n    ProcedureReturn nwReturn(#NW_ERR_ADAPTER)\n  EndIf\n"
        "  If ttWarmOk = 0 Or ttColdRaster <> 24 Or ttColdUpload <> 3 Or ttWarmRaster <> 0 Or ttWarmUpload <> 0 Or ttWarmHits <> 30\n"
        "    AnvilTrueTypeSlotDeselect()\n    ProcedureReturn nwReturn(#NW_ERR_COUNTS)\n  EndIf\n"
        "  If ttCoverage16 < 1 Or ttCoverage24 < 1 Or ttCoverage40 < 1\n"
        "    AnvilTrueTypeSlotDeselect()\n    ProcedureReturn nwReturn(#NW_ERR_PIXELS)\n  EndIf\n"
        "  AnvilTrueTypeSlotDeselect()\n  ProcedureReturn nwReturn(#NW_OK)",
        "cold/warm and coverage proof assertions",
    )
    proof = replace_once(
        proof,
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"',
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"',
        "duplicate-safeguard",
    ) if False else proof
    proof_path = OUT / "vulkanTrueTypeProof.pi4"
    proof_path.write_text(proof, encoding="utf-8", newline="\n")
    manifest = {
        "family": "Abel",
        "font": str(FONT.relative_to(ROOT)).replace("\\", "/"),
        "license": str(LICENSE.relative_to(ROOT)).replace("\\", "/"),
        "font_sha256": sha,
        "font_bytes": len(data),
        "font_source_url": "https://github.com/google/fonts/tree/main/ofl/abel",
        "license_sha256": hashlib.sha256(license_text.encode("utf-8")).hexdigest(),
        "proof_source": str(proof_path.relative_to(ROOT)).replace("\\", "/"),
        "scene_source": str(scene_path.relative_to(ROOT)).replace("\\", "/"),
        "data_include": str(data_include.relative_to(ROOT)).replace("\\", "/"),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return proof_path, scene_path, manifest


def make_clean_export() -> Path:
    """Archive HEAD, overlay only the reviewed TT proof dependencies, and record hashes."""
    if EXPORT.exists():
        shutil.rmtree(EXPORT)
    EXPORT.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"], cwd=ROOT,
        check=True, capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
        tf.extractall(EXPORT, filter="data")
    overlay_records = []
    for relative in OVERLAY:
        source = ROOT / relative
        if not source.is_file():
            raise SystemExit(f"required clean-export overlay is missing: {relative}")
        target = EXPORT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        payload = target.read_bytes()
        overlay_records.append({
            "path": relative,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    for relative in (
        "_work/vulkan-truetype-proof-20260918/vulkanTrueTypeProof.pi4",
        "_work/vulkan-truetype-proof-20260918/vulkanTrueTypeScene.pbi",
        "_work/vulkan-truetype-proof-20260918/abel_font_data.pbi",
        "_work/vulkan-truetype-proof-20260918/OFL.txt",
    ):
        source = ROOT / relative
        target = EXPORT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    record = {"base_commit": commit, "overlay": overlay_records,
              "excluded_dirty_backend": "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"}
    (EXPORT / "_work/vulkan-truetype-proof-20260918/source-provenance.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return EXPORT


def compile_for_board(compiler: Path, root: Path, source: Path, image: Path, load_addr: int):
    import os
    from truetype_t1_check import base

    environment = os.environ.copy()
    environment["PMF_ROOT"] = str(root)
    result = subprocess.run(
        [str(compiler), "--compile", str(source), "-t", "pi4", "--entry-returns",
         "--load-addr", hex(load_addr), "--stack-addr", hex(0x03000000),
         "-s", "-o", str(image)],
        cwd=root, env=environment, capture_output=True, text=True,
    )
    if result.returncode or not image.exists():
        raise SystemExit(result.stdout + result.stderr)
    return base.parse_symbols(image), image.read_bytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", required=True, type=Path)
    ap.add_argument("--clean-export", action="store_true")
    ap.add_argument("--load-addr", default="0x600000", help="link address; use a free map window")
    args = ap.parse_args()
    try:
        load_addr = int(args.load_addr, 0)
    except ValueError:
        raise SystemExit("--load-addr must be an integer (for example 0x600000)")
    proof, _scene, manifest = build_sources()
    source_root = ROOT
    source_path = proof
    image = OUT / "vulkanTrueTypeProof.img"
    if args.clean_export:
        source_root = make_clean_export()
        source_path = source_root / proof.relative_to(ROOT)
        image = source_root / "_work/vulkan-truetype-proof-20260918/vulkanTrueTypeProof.img"
    symbols, blob = compile_for_board(args.compiler.resolve(), source_root, source_path, image, load_addr)
    report_address = symbols.get("global_nwreport")
    if report_address is None:
        raise SystemExit("compiler symbol map is missing global_nwreport")
    manifest["payload_bytes"] = len(blob)
    manifest["payload_sha256"] = hashlib.sha256(blob).hexdigest()
    container = Path(str(image) + ".pmf")
    container_data = container.read_bytes()
    manifest["payload_container_bytes"] = len(container_data)
    manifest["payload_container_sha256"] = hashlib.sha256(container_data).hexdigest()
    if container_data[:8] != b"PMFBOOT\x00" or struct.unpack_from("<I", container_data, 8)[0] != 2:
        raise SystemExit("compiled payload has no supported PMF v2 header")
    load, entry, image_bytes, bss_base, bss_bytes = struct.unpack_from("<QQQQQ", container_data, 16)
    stack = struct.unpack_from("<Q", container_data, 104)[0]
    low_lo, low_hi = 0x00600000, 0x07EFFFFF
    image_hi = load + image_bytes - 1
    bss_hi = bss_base + bss_bytes - 1 if bss_bytes else bss_base - 1
    if load != load_addr or entry < load or entry > image_hi:
        raise SystemExit("PMF image/entry range disagrees with requested link address")
    if load < low_lo or image_hi > low_hi or bss_base < low_lo or bss_hi > low_hi:
        raise SystemExit("PMF image or BSS falls outside the mapped low payload window")
    if bss_bytes and not (image_hi < bss_base or bss_hi < load):
        raise SystemExit("PMF image and BSS ranges overlap")
    if bss_bytes and bss_base <= stack <= bss_hi:
        raise SystemExit("PMF stack top overlaps the static BSS range")
    manifest["image_range"] = [f"{load:08X}", f"{image_hi:08X}"]
    manifest["bss_range"] = [f"{bss_base:08X}", f"{bss_hi:08X}"]
    manifest["stack_top"] = f"{stack:08X}"
    manifest["report_address"] = report_address
    manifest["report_trace_bytes"] = 444
    manifest["load_address"] = load_addr
    manifest["main_offset"] = symbols["main"]
    manifest["build_source_root"] = str(source_root)
    manifest["build_base_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    manifest["clean_export"] = args.clean_export
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.clean_export:
        provenance_path = source_root / "_work/vulkan-truetype-proof-20260918/source-provenance.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        generated = []
        for relative in (
            "_work/vulkan-truetype-proof-20260918/vulkanTrueTypeProof.pi4",
            "_work/vulkan-truetype-proof-20260918/vulkanTrueTypeScene.pbi",
            "_work/vulkan-truetype-proof-20260918/abel_font_data.pbi",
            "_work/vulkan-truetype-proof-20260918/OFL.txt",
        ):
            payload = (source_root / relative).read_bytes()
            generated.append({"path": relative, "bytes": len(payload),
                              "sha256": hashlib.sha256(payload).hexdigest()})
        provenance["generated_sources"] = generated
        provenance["font_sha256"] = manifest["font_sha256"]
        provenance["license_sha256"] = manifest["license_sha256"]
        provenance["payload_sha256"] = manifest["payload_sha256"]
        provenance["payload_container_sha256"] = manifest["payload_container_sha256"]
        provenance["report_address"] = report_address
        provenance["report_trace_bytes"] = 444
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        shutil.copy2(OUT / "manifest.json", source_root / "_work/vulkan-truetype-proof-20260918/manifest.json")
    print(json.dumps({"proof": str(proof), "image": str(image), **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
