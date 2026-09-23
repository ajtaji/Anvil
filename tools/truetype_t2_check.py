"""Emitted T2 cmap/UTF-8 gate."""
from __future__ import annotations
import argparse
from pathlib import Path
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate, run_entry, ROOT  # noqa: E402

GATE = ROOT / "RaspberryPi4/Tests/truetype_t2_gate.pi4"
REAL_META = 0x0F000000
REAL_BASE = 0x10000000
REAL_MAGIC = 0x54543252

def font_fixture(path: Path):
    vendored = ROOT / "_work/fonttools-20260918"
    if vendored.is_dir():
        sys.path.insert(0, str(vendored))
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise SystemExit("fontTools is required for the independent cmap oracle") from exc
    data = path.read_bytes()
    font = TTFont(io.BytesIO(data), lazy=False)
    best = font.getBestCmap() or {}
    order = font.getGlyphOrder()
    glyph_ids = {name: index for index, name in enumerate(order)}
    candidates = (0x41, 0x61, 0x20, 0xE9, 0x3B1, 0x2014, 0x1F600, 0x4E2D)
    pairs = [(cp, glyph_ids[best[cp]]) for cp in candidates if cp in best][:8]
    if not pairs:
        raise SystemExit(f"font has no selected cmap samples: {path}")
    meta = __import__("struct").pack("<3I", REAL_MAGIC, len(data), len(pairs))
    meta += b"".join(__import__("struct").pack("<2I", cp, gid) for cp, gid in pairs)
    memory = {REAL_META + i: byte for i, byte in enumerate(meta)}
    memory.update({REAL_BASE + i: byte for i, byte in enumerate(data)})
    return memory, len(pairs)

def source_mutant(compiler: Path, tmp: Path) -> bool:
    stage = tmp / "mutant"
    for rel in (
        "Anvil/Graphics/truetype.pbi", "Anvil/Graphics/truetype_metrics.pbi",
        "Anvil/Graphics/truetype_cmap.pbi", "RaspberryPi4/Tests/truetype_t2_gate.pi4",
        "RaspberryPi4/Intrinsics/bcm2711_hardware.def", "Boards/Raspberry_Pi_4.board",
    ):
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    module = stage / "Anvil/Graphics/truetype_cmap.pbi"
    text = module.read_text()
    anchor = "If count>capacity"
    if anchor not in text:
        raise SystemExit("T2 output-capacity mutant anchor missing")
    module.write_text(text.replace(anchor, "If count<capacity", 1))
    image = tmp / "truetype_t2_mutant.img"
    symbols, blob = compile_gate(compiler, stage, stage / "RaspberryPi4/Tests/truetype_t2_gate.pi4", image)
    result, _ = run_entry(symbols, blob)
    return result != 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-t2-") as temp:
        temp = Path(temp)
        image = temp / "truetype_t2.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        result, steps = run_entry(symbols, blob)
        if result:
            raise SystemExit(f"T2 emitted gate failed case {result}")
        if not source_mutant(compiler, temp):
            raise SystemExit("T2 weakened output-capacity mutant was not rejected")
        print(f"PASS: T2 emitted cmap/UTF-8 gate; structural refusals + mapping cases, {steps} interpreted instructions")
        print("PASS: format 4/12 mapping, malformed segment/group order and bounds, strict UTF-8, capacity atomicity")
        print("PASS: weakened UTF-8 output-capacity mutant rejected")
        fonts = [ROOT / "_work/truetype-fonts-20260918/abel/Abel-Regular.ttf",
                 ROOT / "_work/truetype-fonts-20260918/acme/Acme-Regular.ttf"]
        for font in fonts:
            if not font.is_file():
                continue
            extra, samples = font_fixture(font)
            result, font_steps = run_entry(symbols, blob, extra, "tt2realfont")
            if result:
                raise SystemExit(f"T2 fontTools cmap comparison failed case {result}: {font}")
            print(f"PASS: fontTools cmap comparison {font.name}: {samples} codepoints, {font_steps} interpreted instructions")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
