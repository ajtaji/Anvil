"""Emitted T3 short-loca and composite outline gate."""
from __future__ import annotations
import argparse
import io
import math
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate, run_entry, ROOT  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

GATE = ROOT / "RaspberryPi4/Tests/truetype_t3_gate.pi4"
REAL_META = 0x0F000000
REAL_BASE = 0x10000000
REAL_MAGIC = 0x54543352

def source_mutant(compiler: Path, temp: Path) -> bool:
    stage = temp / "mutant"
    for rel in (
        "Anvil/Graphics/truetype.pbi", "Anvil/Graphics/truetype_metrics.pbi",
        "Anvil/Graphics/truetype_outlines.pbi", "RaspberryPi4/Tests/truetype_t3_gate.pi4",
        "RaspberryPi4/Intrinsics/bcm2711_hardware.def", "Boards/Raspberry_Pi_4.board",
    ):
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    module = stage / "Anvil/Graphics/truetype_outlines.pbi"
    text = module.read_text()
    anchor = "anvil_tto_U16(*anvil_tto_locaData+glyph*2)*2"
    mutant = "(anvil_tto_U8(*anvil_tto_locaData+glyph*2+1)*256+anvil_tto_U8(*anvil_tto_locaData+glyph*2))*2"
    if anchor not in text:
        raise SystemExit("T3 short-loca endian mutant anchor missing")
    module.write_text(text.replace(anchor, mutant, 1))
    image = temp / "truetype_t3_mutant.img"
    symbols, blob = compile_gate(compiler, stage, stage / "RaspberryPi4/Tests/truetype_t3_gate.pi4", image)
    result, _ = run_entry(symbols, blob)
    return result != 0

def font_fixture(path: Path):
    vendored = ROOT / "_work/fonttools-20260918"
    if vendored.is_dir():
        sys.path.insert(0, str(vendored))
    from fontTools.ttLib import TTFont
    import struct
    data = path.read_bytes()
    font = TTFont(io.BytesIO(data), lazy=False)
    glyf = font["glyf"]
    order = font.getGlyphOrder()
    candidates = []
    for glyph_id, name in enumerate(order):
        item = glyf[name]
        composite = bool(getattr(item, "components", None))
        if composite or getattr(item, "numberOfContours", 0) >= 2:
            try:
                coordinates, ends, flags = item.getCoordinates(glyf)
            except Exception:
                continue
            if coordinates:
                candidates.append((0 if composite else 1, glyph_id, coordinates, ends, flags, name))
                if composite:
                    break
    if not candidates:
        raise SystemExit(f"no composite/multicontour outline found in {path}")
    _, glyph_id, coordinates, ends, flags, name = min(candidates, key=lambda entry: entry[0])
    def round_half_away(value: float) -> int:
        return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)
    points = [(round_half_away(x), round_half_away(y), int(bool(flag & 1))) for (x, y), flag in zip(coordinates, flags)]
    meta = struct.pack("<5I", REAL_MAGIC, len(data), glyph_id, len(points), len(ends))
    meta += b"".join(struct.pack("<3i", *point) for point in points)
    meta += b"".join(struct.pack("<I", int(end)) for end in ends)
    memory = {REAL_META + i: byte for i, byte in enumerate(meta)}
    memory.update({REAL_BASE + i: byte for i, byte in enumerate(data)})
    return memory, name, len(points), len(ends)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-t3-") as temp:
        image = Path(temp) / "truetype_t3.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        result, steps = run_entry(symbols, blob)
        if result:
            raise SystemExit(f"T3 emitted gate failed case {result}")
        if not source_mutant(compiler, Path(temp)):
            raise SystemExit("T3 little-endian short-loca mutant was not rejected")
        print(f"PASS: T3 emitted short-loca/composite gate; 12 assertions, {steps} interpreted instructions")
        print("PASS: big-endian short loca, simple point deltas, signed-byte XY offset, transformed point attachment")
        print("PASS: cycle, conflicting transforms and point-capacity refusals")
        print("PASS: little-endian short-loca mutant rejected")
        fonts = [ROOT / "_work/truetype-fonts-20260918/abel/Abel-Regular.ttf",
                 ROOT / "_work/truetype-fonts-20260918/bangers/Bangers-Regular.ttf"]
        for font in fonts:
            if not font.is_file():
                print(f"SKIP: missing T3 oracle font {font.name}")
                continue
            extra, glyph_name, point_count, contour_count = font_fixture(font)
            result, font_steps = run_entry(symbols, blob, extra, "main")
            if result:
                raise SystemExit(f"T3 fontTools coordinate comparison failed case {result}: {glyph_name}")
            print(f"PASS: fontTools outline coordinates {font.name} {glyph_name}: {point_count} points, {contour_count} contours, {font_steps} instructions")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
