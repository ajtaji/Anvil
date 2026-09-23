#!/usr/bin/env python3
"""Build a no-GPU returning PMF for native Neon TrueType measurement checks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "a64"))
import a64_core_worker_check as a64  # noqa: E402
import neon_measure_backend_check as measure  # noqa: E402

LOAD = 0x00600000
STACK = 0x03000000
STACK_RESERVE = 0x00100000
LOW_HI = 0x07EFFFFF
FONT = ROOT / "_work/truetype-fonts-20260918/abel/Abel-Regular.ttf"
MAGIC = 0x4E4D4E41  # "ANMN" little-endian
REPORT_WORDS = 24


def emit_font_data(font: bytes) -> str:
    rows = ["  Data.a " + ",".join(str(b) for b in font[i:i + 24])
            for i in range(0, len(font), 24)]
    return (f"#NMG_FONT_BYTES = {len(font)}\nDataSection\n  nmgFontStart:\n"
            + "\n".join(rows) + "\n  nmgFontEnd:\nEndDataSection\n")


def generated_source(stage: Path, font: bytes) -> Path:
    source = measure.make_fixture(stage)
    text = source.read_text(encoding="utf-8")
    text = text.replace("#NMG_META = $0F000000\n#NMG_BASE = $10000000\n", "")
    text = text.replace("#NMG_MAGIC = $54534C54\n", "")
    anchor = "Global Dim mngAV.a[3]"
    if text.count(anchor) != 1:
        raise SystemExit("measurement report global insertion anchor missing/duplicated")
    text = text.replace(anchor, "Global Dim nmgReport.l[24]\nGlobal nmgRaster0.i, nmgCount0.i, nmgHits0.i, nmgMisses0.i, nmgUploads0.i\nGlobal nmgAV16.i, nmgA16.i, nmgV16.i, nmgAe16.i, nmgMulti16.i, nmgAV12.i, nmgAV32.i\nGlobal nmgLH16.i, nmgLH12.i, nmgRight12.i, nmgCentre12.i\n" + anchor, 1)
    insertion = "; The font is an immutable payload image span, not an external RAM fixture.\n" + emit_font_data(font)
    text = text.replace("Procedure mngCheck(ok.i)", insertion + "\nProcedure mngCheck(ok.i)", 1)
    old = '''  If PeekL(#NMG_META)<>#NMG_MAGIC : ProcedureReturn 90 : EndIf
  bytes=PeekL(#NMG_META+4)
  If bytes<1 Or bytes>#ANVIL_TTS_MAX_BYTES : ProcedureReturn 91 : EndIf'''
    new = '''  bytes=#NMG_FONT_BYTES
  If bytes<1 Or bytes>#ANVIL_TTS_MAX_BYTES : ProcedureReturn 91 : EndIf'''
    if old not in text:
        raise SystemExit("could not replace fixed metadata address with embedded font length")
    text = text.replace(old, new, 1)
    if "AnvilTrueTypeSlotLoad(0,#NMG_BASE,bytes)" not in text:
        raise SystemExit("fixed font base anchor missing")
    text = text.replace("AnvilTrueTypeSlotLoad(0,#NMG_BASE,bytes)",
                        "AnvilTrueTypeSlotLoad(0,?nmgFontStart,bytes)", 1)
    text = text.replace("  nvcTTFontPixels=16 : nvcError=0\n", "  nvcTTFontPixels=16 : nvcError=0\n")
    text = text.replace("  neon_fontScale[0]=1 : neon_fontScale[1]=1 : neon_fontScale[2]=2 : neon_fontScale[3]=1\n", "  neon_fontScale[0]=1 : neon_fontScale[1]=1 : neon_fontScale[2]=2 : neon_fontScale[3]=1\n  nmgRaster0=AnvilTrueTypeRasterCount() : nmgCount0=nvcTTCount : nmgHits0=nvcTTCacheHits : nmgMisses0=nvcTTCacheMisses : nmgUploads0=nvcStubUploadCount\n", 1)
    replacements = {
        "mngCheck(Neon_TextWidth(#NEON_FONT_UI,@mngAV[0])=15)": "nmgAV16=Neon_TextWidth(#NEON_FONT_UI,@mngAV[0]) : mngCheck(nmgAV16=15)",
        "mngCheck(Neon_TextWidth(#NEON_FONT_UI,@mngA[0])=8)": "nmgA16=Neon_TextWidth(#NEON_FONT_UI,@mngA[0]) : mngCheck(nmgA16=8)",
        "mngCheck(Neon_TextWidth(#NEON_FONT_UI,@mngV[0])=8)": "nmgV16=Neon_TextWidth(#NEON_FONT_UI,@mngV[0]) : mngCheck(nmgV16=8)",
        "mngCheck(Neon_TextWidth(#NEON_FONT_UI,@mngAe[0])=15)": "nmgAe16=Neon_TextWidth(#NEON_FONT_UI,@mngAe[0]) : mngCheck(nmgAe16=15)",
        "mngCheck(Neon_TextWidth(#NEON_FONT_UI,@mngMultiline[0])=15)": "nmgMulti16=Neon_TextWidth(#NEON_FONT_UI,@mngMultiline[0]) : mngCheck(nmgMulti16=15)",
        "mngCheck(Neon_LineHeight(#NEON_FONT_UI)=18)": "nmgLH16=Neon_LineHeight(#NEON_FONT_UI) : mngCheck(nmgLH16=18)",
        "mngCheck(Neon_TextWidth(#NEON_FONT_MONO,@mngAV[0])=30)": "nmgAV32=Neon_TextWidth(#NEON_FONT_MONO,@mngAV[0]) : mngCheck(nmgAV32=30)",
        "mngCheck(Neon_TextWidth(#NEON_FONT_UI,@mngAV[0])=11)": "nmgAV12=Neon_TextWidth(#NEON_FONT_UI,@mngAV[0]) : mngCheck(nmgAV12=11)",
        "mngCheck(Neon_LineHeight(#NEON_FONT_UI)=14)": "nmgLH12=Neon_LineHeight(#NEON_FONT_UI) : mngCheck(nmgLH12=14)",
        "mngCheck(mngTextCalls=1 And mngTextX=89 And mngTextY=7)": "mngCheck(mngTextCalls=1 And mngTextX=89 And mngTextY=7) : nmgRight12=mngTextX",
        "mngCheck(mngTextCalls=2 And mngTextX=44 And mngTextY=9)": "mngCheck(mngTextCalls=2 And mngTextX=44 And mngTextY=9) : nmgCentre12=mngTextX",
    }
    for old_text, new_text in replacements.items():
        if text.count(old_text) != 1:
            raise SystemExit(f"native result capture anchor missing/duplicated: {old_text}")
        text = text.replace(old_text, new_text, 1)
    marker = "  If mngFails<>0 : ProcedureReturn mngFirstFailure : EndIf\n  ProcedureReturn 0"
    report = '''  nmgReport[0]=#NMG_NATIVE_MAGIC : nmgReport[1]=mngChecks : nmgReport[2]=mngFails : nmgReport[3]=mngFirstFailure
  nmgReport[4]=AnvilTrueTypeUnitsPerEm() : nmgReport[5]=AnvilTrueTypeGlyphCount()
  nmgReport[6]=nmgAV16 : nmgReport[7]=nmgA16 : nmgReport[8]=nmgV16 : nmgReport[9]=nmgAe16 : nmgReport[10]=nmgMulti16
  nmgReport[11]=nmgAV12 : nmgReport[12]=nmgAV32 : nmgReport[13]=nmgLH16 : nmgReport[14]=nmgLH12
  nmgReport[15]=nmgRight12 : nmgReport[16]=nmgCentre12
  nmgReport[17]=AnvilTrueTypeRasterCount()-nmgRaster0 : nmgReport[18]=nvcTTCount-nmgCount0
  nmgReport[19]=nvcTTCacheHits-nmgHits0 : nmgReport[20]=nvcTTCacheMisses-nmgMisses0 : nmgReport[21]=nvcStubUploadCount-nmgUploads0
  nmgReport[22]=AnvilTrueTypeSlotSelected() : nmgReport[23]=AnvilTrueTypeSlotParserBound()
  If mngFails<>0 : ProcedureReturn mngFirstFailure : EndIf
  ProcedureReturn 0'''
    if text.count(marker) != 1:
        raise SystemExit("native report insertion anchor missing/duplicated")
    text = text.replace(marker, report, 1)
    text = text.replace("#NMG_FONT_BYTES =", f"#NMG_NATIVE_MAGIC = ${MAGIC:08X}\n#NMG_FONT_BYTES =", 1)
    source.write_text(text, encoding="utf-8", newline="\n")
    return source


def compile_pmf(compiler: Path, stage: Path, source: Path, image: Path) -> tuple[dict[str, int], bytes, bytes]:
    import os
    env = os.environ.copy()
    env["PMF_ROOT"] = str(stage)
    result = subprocess.run(
        [str(compiler), "--compile", str(source), "-t", "pi4", "--entry-returns",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)],
        cwd=stage, env=env, capture_output=True, text=True,
    )
    (image.parent / "compiler.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (image.parent / "compiler.stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode or not image.is_file():
        raise SystemExit(result.stdout + result.stderr)
    return a64.parse_symbols(image), image.read_bytes(), Path(str(image) + ".pmf").read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.expanduser().resolve()
    out = args.out.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing output: {out}")
    if not FONT.is_file():
        raise SystemExit(f"pinned Abel font missing: {FONT}")
    font = FONT.read_bytes()
    if len(font) != 35220 or hashlib.sha256(font).hexdigest() != "8809dcad25318225052f88333e208c5aad4adcb7b2c934c135735ec19aa410b4":
        raise SystemExit("Abel font differs from the pinned 35,220-byte specimen")
    out.mkdir(parents=True)
    stage = out / "source"
    stage.mkdir()
    source = generated_source(stage, font)
    image = out / "neonMeasureNative.img"
    symbols, blob, pmf = compile_pmf(compiler, stage, source, image)
    if pmf[:8] != b"PMFBOOT\x00" or struct.unpack_from("<I", pmf, 8)[0] != 2:
        raise SystemExit("compiler did not produce a supported PMF v2")
    flags = struct.unpack_from("<I", pmf, 56)[0]
    arch = struct.unpack_from("<I", pmf, 96)[0]
    target = struct.unpack_from("<I", pmf, 100)[0]
    if not (flags & 1) or arch != 1 or target != 2711 or any(pmf[112:128]):
        raise SystemExit("PMF must be returning AArch64/BCM2711 with no external resources")
    load, entry, image_bytes, bss_base, bss_bytes = struct.unpack_from("<QQQQQ", pmf, 16)
    stack = struct.unpack_from("<Q", pmf, 104)[0]
    image_hi = load + image_bytes - 1
    bss_hi = bss_base + bss_bytes - 1 if bss_bytes else bss_base - 1
    stack_lo = stack - STACK_RESERVE
    if load != LOAD or entry < load or entry > image_hi or image_hi > LOW_HI:
        raise SystemExit("PMF image/entry is outside the low-payload window")
    if bss_bytes and (bss_base < LOAD or bss_hi > LOW_HI or not (image_hi < bss_base or bss_hi < load)):
        raise SystemExit("PMF BSS is outside the low window or overlaps image")
    if bss_bytes and not (bss_hi < stack_lo or stack < bss_base):
        raise SystemExit("PMF BSS overlaps reserved stack window")
    font_start_offset = symbols.get("nmgfontstart")
    font_end_offset = symbols.get("nmgfontend")
    report = symbols.get("global_nmgreport")
    if font_start_offset is None or font_end_offset is None or report is None:
        raise SystemExit("symbols missing embedded font or native report labels")
    # Data labels are image-relative offsets in .sym; globals are absolute.
    font_start = load + font_start_offset
    font_end = load + font_end_offset
    font_hi = font_start + len(font) - 1
    font_offset = font_start - load
    if font_end < font_hi + 1 or font_end - (load + font_offset) > len(font) + 16:
        raise SystemExit("embedded font end label does not bound the declared font bytes")
    if not (load <= font_start <= font_hi <= image_hi):
        raise SystemExit("embedded font is outside compiled image range")
    if blob[font_offset:font_offset + len(font)] != font:
        raise SystemExit("compiled payload font bytes differ from pinned Abel")
    if bss_bytes and not (bss_base <= report and report + REPORT_WORDS * 4 - 1 <= bss_hi):
        raise SystemExit("report array is outside compiled BSS range")
    if not (image_hi < stack_lo or stack < load):
        raise SystemExit("compiled image overlaps reserved stack window")
    manifest = {
        "purpose": "native no-GPU TrueType widget measurement acceptance",
        "source_identity": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "load_address": f"0x{load:08X}", "entry_address": f"0x{entry:08X}",
        "image_range": [f"0x{load:08X}", f"0x{image_hi:08X}"],
        "bss_range": [f"0x{bss_base:08X}", f"0x{bss_hi:08X}"],
        "stack_top": f"0x{stack:08X}", "stack_reserved_range": [f"0x{stack_lo:08X}", f"0x{stack:08X}"],
        "pmf_arch": arch, "pmf_target": target, "pmf_flags": flags,
        "embedded_font_range": [f"0x{font_start:08X}", f"0x{font_hi:08X}"],
        "embedded_font_bytes": len(font), "embedded_font_sha256": hashlib.sha256(font).hexdigest(),
        "report_address": f"0x{report:08X}", "report_words": REPORT_WORDS,
        "main_address": f"0x{load + symbols['main']:08X}",
        "image_bytes": len(blob), "image_sha256": hashlib.sha256(blob).hexdigest(),
        "pmf_bytes": len(pmf), "pmf_sha256": hashlib.sha256(pmf).hexdigest(),
        "fixture_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "font_table_procedure_sources": {
            "neon.pi4": hashlib.sha256(measure.NEON.read_bytes()).hexdigest(),
            "neon_vk_chrome.pi4": hashlib.sha256(measure.CHROME.read_bytes()).hexdigest(),
            "measure_gate": hashlib.sha256(measure.GATE.read_bytes()).hexdigest(),
        },
        "no_gpu": True,
        "expected_report_words": {
            "magic": f"0x{MAGIC:08X}", "check_count": 55, "upem": 2048,
            "glyph_count": 259, "AV_width_16": 15, "A_width_16": 8, "V_width_16": 8,
            "AplusEacute_pair_width_16": 15, "multiline_max_width_16": 15, "AV_width_12": 11,
            "AV_width_mono_32": 30, "line_height_UI_16": 18, "line_height_UI_12": 14,
            "right_origin_at_12px": 89, "centre_origin_at_12px": 44,
            "raster_cache_upload_deltas": [0, 0, 0, 0, 0],
        },
    }
    manifest["host_gate_reference"] = {
        "status": "PASS; see existing emitted gate record",
        "gate_log": "_work/neon-measure-backend-20260919/gate.txt",
        "note": "This new PMF must still be executed on the board; no native result is implied by the host gate.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
