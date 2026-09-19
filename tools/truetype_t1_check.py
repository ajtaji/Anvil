"""Emitted T1 TrueType metrics gate and source bounds mutant."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi4/Tests/truetype_t1_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
STEP_LIMIT = 30_000_000
REAL_META = 0x0F000000
REAL_BASE = 0x10000000
REAL_MAGIC = 0x54543152


def compile_gate(compiler: Path, root: Path, source: Path, image: Path):
    env = os.environ.copy()
    env["PMF_ROOT"] = str(root)
    result = subprocess.run(
        [str(compiler), "--compile", str(source), "-t", "pi4",
         "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
         hex(STACK), "-s", "-o", str(image)],
        cwd=root, env=env, capture_output=True, text=True,
    )
    if result.returncode or not image.exists():
        raise SystemExit(result.stdout + result.stderr)
    return base.parse_symbols(image), image.read_bytes()


def run_entry(symbols, blob, extra_memory=None, entry="main") -> tuple[int, int]:
    cpu = base.load_interp(base.INTERP).A64()
    cpu.sp = STACK
    cpu.memory = {LOAD + i: b for i, b in enumerate(blob)}
    if extra_memory:
        cpu.memory.update(extra_memory)
    cpu.pc = LOAD + symbols[entry.lower()]
    cpu.x[30] = base.RETURN_PC
    for steps in range(STEP_LIMIT):
        if cpu.pc == base.RETURN_PC:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"T1 gate exceeded {STEP_LIMIT} instructions")


def font_fixture(path: Path):
    data = path.read_bytes()
    if len(data) < 12:
        raise SystemExit(f"font is truncated: {path}")
    count = struct.unpack_from(">H", data, 4)[0]
    tables = {}
    for index in range(count):
        at = 12 + index * 16
        tag, checksum, offset, length = struct.unpack_from(">4sIII", data, at)
        if offset > len(data) or length > len(data) - offset:
            raise SystemExit(f"font table {tag!r} is out of bounds: {path}")
        tables[tag] = (offset, length)
    head, _ = tables[b"head"]
    maxp, _ = tables[b"maxp"]
    hhea, _ = tables[b"hhea"]
    hmtx, _ = tables[b"hmtx"]
    units = struct.unpack_from(">H", data, head + 18)[0]
    loca = struct.unpack_from(">h", data, head + 50)[0]
    glyphs = struct.unpack_from(">H", data, maxp + 4)[0]
    asc, desc = struct.unpack_from(">hh", data, hhea + 4)
    metrics = struct.unpack_from(">H", data, hhea + 34)[0]
    chosen = (0, max(0, metrics - 1), glyphs - 1)
    entries = []
    for glyph in chosen:
        if glyph < metrics:
            advance, lsb = struct.unpack_from(">Hh", data, hmtx + glyph * 4)
        else:
            advance = struct.unpack_from(">H", data, hmtx + (metrics - 1) * 4)[0]
            lsb = struct.unpack_from(">h", data, hmtx + metrics * 4 + (glyph - metrics) * 2)[0]
        entries.extend((glyph, advance, lsb))
    meta = struct.pack("<4I4i", REAL_MAGIC, len(data), units, glyphs, loca, asc, desc, metrics)
    meta += struct.pack("<9i", *entries)
    memory = {REAL_META + i: byte for i, byte in enumerate(meta)}
    memory.update({REAL_BASE + i: byte for i, byte in enumerate(data)})
    return memory, units, glyphs


def source_mutant(compiler: Path, tmp: Path) -> bool:
    stage = tmp / "mutant"
    for rel in (
        "Anvil/Graphics/truetype.pbi",
        "Anvil/Graphics/truetype_metrics.pbi",
        "RaspberryPi4/Tests/truetype_t1_gate.pi4",
        "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
        "Boards/Raspberry_Pi_4.board",
    ):
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    module = stage / "Anvil/Graphics/truetype_metrics.pbi"
    text = module.read_text()
    anchor = "If need>hmtxLength"
    if anchor not in text:
        raise SystemExit("T1 hmtx bounds mutant anchor missing")
    module.write_text(text.replace(anchor, "If need<hmtxLength", 1))
    image = tmp / "truetype_t1_mutant.img"
    symbols, blob = compile_gate(
        compiler, stage, stage / "RaspberryPi4/Tests/truetype_t1_gate.pi4", image
    )
    result, _ = run_entry(symbols, blob)
    return result != 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--font", action="append", default=[])
    args = parser.parse_args()
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-t1-") as tmp_name:
        tmp = Path(tmp_name)
        image = tmp / "truetype_t1.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        result, steps = run_entry(symbols, blob)
        if result != 0:
            raise SystemExit(f"T1 emitted gate failed case {result}")
        if not source_mutant(compiler, tmp):
            raise SystemExit("T1 weakened hmtx bounds mutant was not rejected")
        print(f"PASS: T1 metrics gate; 45 cases, {steps} interpreted instructions")
        print("PASS: signed metrics, hmtx tail advance, optional OS/2 and table refusals")
        print("PASS: hmtx length source mutant rejected")
        fonts = [Path(name).expanduser().resolve() for name in args.font]
        if not fonts:
            corpus = ROOT / "_work/truetype-fonts-20260918"
            fonts = [corpus / "abel/Abel-Regular.ttf", corpus / "courierprime/CourierPrime-Regular.ttf"]
        valid_fonts = [path for path in fonts if path.is_file()]
        if valid_fonts:
            for path in valid_fonts:
                extra, units, glyphs = font_fixture(path)
                result, font_steps = run_entry(symbols, blob, extra, "tt1realfont")
                if result != 0:
                    raise SystemExit(f"T1 real-font gate failed case {result}: {path}")
                print(f"PASS: independent TTF metrics {path.name}: UPEM={units}, glyphs={glyphs}, {font_steps} instructions")
        else:
            print("SKIP: no independent TTF fixture supplied or present in the local font corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
