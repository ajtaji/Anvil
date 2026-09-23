#!/usr/bin/env python3
"""Build a returning GPU comparison for glyph 19 through text and grid paths."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import vulkan_truetype_proof_build as base
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

OUT = ROOT / "_work/vulkan-truetype-grid-diff-cap1024-20260919"


def one(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"expected one {label} anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def generated_source_hashes() -> dict[str, str]:
    names = ("vulkanTrueTypeProof.pi4", "vulkanTrueTypeScene.pbi",
             "abel_font_data.pbi", "OFL.txt")
    return {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
            for name in names}


def build_sources() -> tuple[Path, dict]:
    base.OUT = OUT
    proof_path, scene_path, manifest = base.build_sources()
    scene = scene_path.read_text(encoding="utf-8")
    for name, value in {
        "NVWA_WIDTH": 512, "NVWA_HEIGHT": 512,
        "NVWA_EXPECT_BOX_CALLS": 0, "NVWA_EXPECT_TEXT_CALLS": 1,
        "NVWA_EXPECT_GLYPH_QUADS": 1, "NVWA_EXPECT_QUADS": 2,
        "NVWA_EXPECT_DRAWS": 2, "NVWA_EXPECT_VERTICES": 12,
        "NVWA_EXPECT_SCISSOR_CALLS": 0,
    }.items():
        scene, count = re.subn(rf"(?m)^#{name}\s*=\s*\d+\s*$", f"#{name} = {value}", scene)
        if count != 1:
            raise SystemExit(f"missing scene constant {name}")
    scene_path.write_text(scene, encoding="utf-8", newline="\n")

    data_path = OUT / "abel_font_data.pbi"
    data = data_path.read_text(encoding="utf-8")
    data = one(data, "  ttFontEnd:\n", "  ttFontEnd:\n  ttZeroUtf8:\n  Data.a 48,0\n", "zero specimen")
    data_path.write_text(data, encoding="utf-8", newline="\n")

    proof = proof_path.read_text(encoding="utf-8")
    proof = proof.replace("#NW_SURFACE_PITCH     = 3200", "#NW_SURFACE_PITCH     = 2048")
    proof = proof.replace("#NW_SURFACE_BYTES     = 4096000", "#NW_SURFACE_BYTES     = 1048576")
    proof = one(proof, "  If NeonInit() <> #NEON_OK\n",
        "  ; Keep the 512x512 color target, but reserve capacity for the 512x1024 atlas.\n"
        "  If NeonRenderCapacity(1024, 1024) <> #NEON_OK\n"
        "    ProcedureReturn nwReturn(#NW_ERR_NEON)\n  EndIf\n"
        "  If NeonInit() <> #NEON_OK\n", "raise sampled-image capacity")
    proof = one(proof, "Global Dim nwProbeY.i[12]\n",
        "Global Dim nwProbeY.i[12]\nGlobal Dim nwDiffRaw.a[9216]\nGlobal Dim nwDiffMeta.l[16]\nGlobal Dim nwdGlyphs.l[1]\n",
        "raw comparison buffers")
    proof = one(proof, "  nwPut(#NW_S_STEP, 0)\n",
        "  nwdGlyphs[0] = 19\n  nwPut(#NW_S_STEP, 0)\n  nwPut(62, @nwDiffRaw[0]) : nwPut(63, @nwDiffMeta[0])\n",
        "report buffer pointers")

    start = proof.index("  ; Bind the display owner's DMA path")
    end = proof.index("  ; Destroy the production adapter first", start)
    replacement = """  ; Warm the exact same Abel glyph at one size through both cache paths.
  nwPut(#NW_S_STEP, 5)
  rc = NeonVkChromeWarmTrueTypeText(16, ?ttZeroUtf8)
  nwPut(75, rc) : nwPut(76, NeonVkChromeError())
  nwPut(#NW_S_STEP, 6)
  If rc <> 1
    ProcedureReturn nwReturn(#NW_ERR_SCENE)
  EndIf
  nwdGlyphs[0] = 19
  rc = NeonVkChromeGridWarm(@nwdGlyphs[0], 1, 16)
  nwPut(77, rc) : nwPut(78, NeonVkChromeError())
  nwPut(#NW_S_STEP, 7)
  If rc <> 1
    ProcedureReturn nwReturn(#NW_ERR_SCENE)
  EndIf
  Define rot.i, method.i, row.i, col.i, cropX.i, cropY.i
  Define Dim clearDiff.l[4]
  clearDiff[0] = 0 : clearDiff[1] = 0 : clearDiff[2] = 0 : clearDiff[3] = $3F800000
  For rot = 0 To 1
    If rot = 0
      rc = NeonVkChromeRebind(framebuffer, 512, 512, 512, 512, imagePitch, 0)
    Else
      rc = NeonVkChromeRebind(framebuffer, 512, 512, 512, 512, imagePitch, 90)
    EndIf
    nwPut(79, rc) : nwPut(80, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK : ProcedureReturn nwReturn(#NW_ERR_SCENE) : EndIf
    rc = NeonVkChromeBegin(@clearDiff[0])
    nwPut(81, rc) : nwPut(82, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    ; Text baseline 62 and fixed-cell origin 64/64 yield the same raster top.
    rc = NeonVkChromeTrueTypeText(16, 64, 62, ?ttZeroUtf8, $FFFFFFFF)
    nwPut(83, rc) : nwPut(84, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    rc = NeonVkChromeGridBatchBegin()
    nwPut(85, rc) : nwPut(86, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    rc = NeonVkChromeGridBatchReserve(1, 1)
    nwPut(87, rc) : nwPut(88, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    rc = NeonVkChromeGridGlyphAppend(19, 16, 160, 64, 8, 16)
    nwPut(89, rc) : nwPut(90, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    rc = NeonVkChromeGridBatchFlush($FFFFFFFF)
    nwPut(91, rc) : nwPut(92, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    rc = NeonVkChromeGridBatchEnd()
    nwPut(93, rc) : nwPut(94, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    rc = NeonVkChromeEnd()
    nwPut(97, rc) : nwPut(98, NeonVkChromeError())
    If rc <> #NEON_VK_CHROME_OK : ProcedureReturn nwReturn(#NW_ERR_SCENE) : EndIf
    rc = NeonVkChromePresentConsume()
    nwPut(95, rc) : nwPut(96, NeonVkChromeError())
    nwPut(#NW_S_STEP, 8 + rot)
    If rc <> 1
      ProcedureReturn nwReturn(#NW_ERR_SCENE)
    EndIf
    If NeonVkChromeDrawCount() <> 2 Or NeonVkChromeVertexCount() <> 12
      ProcedureReturn nwReturn(#NW_ERR_COUNTS)
    EndIf
    For method = 0 To 1
      If rot = 0
        If method = 0 : cropX = 56 : cropY = 56 : Else : cropX = 152 : cropY = 56 : EndIf
      Else
        If method = 0 : cropX = 426 : cropY = 56 : Else : cropX = 426 : cropY = 152 : EndIf
      EndIf
      For row = 0 To 23
        For col = 0 To 23
          nwDiffRaw[(rot * 2 + method) * 2304 + row * 96 + col * 4 + 0] = PeekA(imageBase + (cropY + row) * imagePitch + (cropX + col) * 4 + 0)
          nwDiffRaw[(rot * 2 + method) * 2304 + row * 96 + col * 4 + 1] = PeekA(imageBase + (cropY + row) * imagePitch + (cropX + col) * 4 + 1)
          nwDiffRaw[(rot * 2 + method) * 2304 + row * 96 + col * 4 + 2] = PeekA(imageBase + (cropY + row) * imagePitch + (cropX + col) * 4 + 2)
          nwDiffRaw[(rot * 2 + method) * 2304 + row * 96 + col * 4 + 3] = PeekA(imageBase + (cropY + row) * imagePitch + (cropX + col) * 4 + 3)
        Next
      Next
    Next
    nwDiffMeta[rot * 4 + 0] = rot * 90
    nwDiffMeta[rot * 4 + 1] = NeonVkChromeDrawCount()
    nwDiffMeta[rot * 4 + 2] = NeonVkChromeVertexCount()
    nwDiffMeta[rot * 4 + 3] = NeonVkChromeTTCacheHits()
    nwPut(65 + rot, NeonVkChromeError())
  Next
  nwPut(#NW_S_DRAW_ACTUAL, 2) : nwPut(#NW_S_VERTEX_ACTUAL, 12)
  nwPut(#NW_S_SCENE_RC, #NVWA_OK)
  nwPut(#NW_S_PRESENT_PENDING, NeonVkChromePresentPending())
  nwPut(67, AnvilTrueTypeRasterCount())
  nwPut(68, NeonVkChromeAtlasUploadCount())
  nwPut(69, NeonVkChromeTTCacheHits())
  nwPut(70, imagePitch)
  nwPut(71, 512) : nwPut(72, 512)
  nwPut(73, 24) : nwPut(74, 24)
    """
    proof = proof[:start] + replacement + proof[end:]
    proof = proof.replace("  DisplayUseDma(0)\n  DisplayFlush()\n  delay(#NW_SHOW_MS)\n", "")
    proof = proof.replace("  nwCapturePixels(imageBase, imagePitch)\n", "")
    # The stock final scene checks are not applicable to this two-draw diagnostic.
    old = "  If ttWarmOk = 0 Or ttColdRaster <> 24 Or ttColdUpload <> 3 Or ttWarmRaster <> 0 Or ttWarmUpload <> 0 Or ttWarmHits <> 30\n"
    if old in proof:
        proof = proof.replace(old, "  If NeonVkChromePresentPending() <> 0\n", 1)
    proof = one(proof,
        "  If ttCoverage16 < 1 Or ttCoverage24 < 1 Or ttCoverage40 < 1\n    AnvilTrueTypeSlotDeselect()\n    ProcedureReturn nwReturn(#NW_ERR_PIXELS)\n  EndIf\n",
        "  If nwDiffMeta[1] <> 2 Or nwDiffMeta[2] <> 12 Or nwDiffMeta[5] <> 2 Or nwDiffMeta[6] <> 12\n    AnvilTrueTypeSlotDeselect()\n    ProcedureReturn nwReturn(#NW_ERR_COUNTS)\n  EndIf\n",
        "replace old raster coverage assertion")
    proof_path.write_text(proof, encoding="utf-8", newline="\n")
    manifest.update({
        "diagnostic": "same Abel glyph 19 via normal text and grid paths at rotations 0 and 90",
        "raw_global": "nwDiffRaw; four tightly packed 24x24 BGRA crops in order rot0 text/grid, rot90 text/grid",
        "raw_bytes": 9216,
        "metadata_global": "nwDiffMeta[16]",
        "target": "512x512 square",
    })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return proof_path, manifest


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", required=True, type=Path)
    ap.add_argument("--load-addr", default="0x600000")
    ap.add_argument("--out", type=Path, required=True,
                    help="new, unused output directory; existing paths are never overwritten")
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    load_addr = int(args.load_addr, 0)
    OUT = args.out if args.out.is_absolute() else ROOT / args.out
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite existing output path: {OUT}")
    source, manifest = build_sources()
    compiled_sources = generated_source_hashes()
    image = OUT / "vulkanTrueTypeGridDiff.img"
    symbols, blob = base.compile_for_board(args.compiler.resolve(), ROOT, source, image, load_addr)
    if generated_source_hashes() != compiled_sources:
        raise SystemExit("generated proof sources changed during compilation; artifact is not source-pinned")
    pmf_path = Path(str(image) + ".pmf")
    pmf = pmf_path.read_bytes()
    if pmf[:8] != b"PMFBOOT\x00" or struct.unpack_from("<I", pmf, 8)[0] != 2:
        raise SystemExit("missing PMF v2 header")
    load, entry, image_bytes, bss_base, bss_bytes = struct.unpack_from("<QQQQQ", pmf, 16)
    stack = struct.unpack_from("<Q", pmf, 104)[0]
    image_hi = load + image_bytes - 1
    bss_hi = bss_base + bss_bytes - 1 if bss_bytes else bss_base - 1
    safe_lo, safe_hi = 0x00600000, 0x07EFFFFF
    if load != load_addr or entry < load or entry > image_hi or load < safe_lo or image_hi > safe_hi:
        raise SystemExit("image/entry outside requested safe payload mapping")
    if bss_bytes and (bss_base < safe_lo or bss_hi > safe_hi or not (image_hi < bss_base or bss_hi < load)):
        raise SystemExit("BSS is out of range or overlaps image")
    if bss_bytes and bss_base <= stack <= bss_hi:
        raise SystemExit("stack overlaps BSS")
    names = ("global_nwdiffraw", "global_nwdiffmeta", "global_nwdglyphs", "global_nwreport")
    if any(name not in symbols for name in names):
        raise SystemExit("symbol map is missing a diagnostic buffer")
    manifest.update({
        "generated_source_sha256": compiled_sources,
        "compiled_source_sha256": compiled_sources,
        "payload_bytes": len(blob), "payload_sha256": hashlib.sha256(blob).hexdigest(),
        "container_bytes": len(pmf), "container_sha256": hashlib.sha256(pmf).hexdigest(),
        "image": str(image), "container": str(pmf_path),
        "image_range": [f"{load:08X}", f"{image_hi:08X}"],
        "bss_range": [f"{bss_base:08X}", f"{bss_hi:08X}"], "bss_bytes": bss_bytes,
        "stack_top": f"{stack:08X}", "symbols": {name: symbols[name] for name in names},
    })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
