#!/usr/bin/env python3
"""Emitted real-module test for TrueType resident slot lifetime and parser restore."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi4/Tests/truetype_slots_gate.pi4"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 50_000_000
META, FONT_BASE, MAGIC = 0x0F000000, 0x10000000, 0x54534C54
MODULES = (
    "Anvil/Graphics/truetype.pbi",
    "Anvil/Graphics/truetype_metrics.pbi",
    "Anvil/Graphics/truetype_cmap.pbi",
    "Anvil/Graphics/truetype_outlines.pbi",
    "Anvil/Graphics/truetype_kern.pbi",
    "Anvil/Graphics/truetype_gpos.pbi",
    "Anvil/Graphics/truetype_slots.pbi",
    "RaspberryPi4/Tests/truetype_slots_gate.pi4",
    "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
    "Boards/Raspberry_Pi_4.board",
)


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


def font_memory(path: Path):
    font = path.read_bytes()
    if len(font) < 1 or len(font) > 1_048_576:
        raise SystemExit(f"font size outside slot contract: {path} ({len(font)})")
    if len(font) < 12:
        raise SystemExit(f"font is truncated: {path}")
    count = struct.unpack_from(">H", font, 4)[0]
    units = None
    for index in range(count):
        tag, checksum, offset, length = struct.unpack_from(">4sIII", font, 12 + index * 16)
        if tag == b"head" and length >= 20 and offset <= len(font) and length <= len(font) - offset:
            units = struct.unpack_from(">H", font, offset + 18)[0]
            break
    if units is None:
        raise SystemExit(f"font has no bounded head table: {path}")
    metadata = struct.pack("<3I", MAGIC, len(font), units)
    memory = {META + i: value for i, value in enumerate(metadata)}
    memory.update({FONT_BASE + i: value for i, value in enumerate(font)})
    return memory


def run_entry(symbols, blob, extra):
    cpu = base.load_interp(base.INTERP).A64()
    cpu.sp = STACK
    cpu.memory = {LOAD + i: value for i, value in enumerate(blob)}
    cpu.memory.update(extra)
    cpu.pc = LOAD + symbols["main"]
    cpu.x[30] = base.RETURN_PC
    for steps in range(LIMIT):
        if cpu.pc == base.RETURN_PC:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"TrueType slot gate exceeded {LIMIT} instructions")


def mutant_rejected(compiler: Path, temp: Path, extra):
    stage = temp / "mutant"
    for rel in MODULES:
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    module = stage / "Anvil/Graphics/truetype_slots.pbi"
    text = module.read_text()
    anchor = "If slot = anvil_tts_selected And AnvilTrueTypeSlotParserBound() <> 0"
    if anchor not in text:
        raise SystemExit("same-slot stale-parser mutant anchor missing")
    module.write_text(text.replace(anchor, "If slot = anvil_tts_selected", 1))
    image = temp / "truetype_slots_mutant.img"
    symbols, blob = compile_gate(compiler, stage,
                                 stage / "RaspberryPi4/Tests/truetype_slots_gate.pi4", image)
    result, _ = run_entry(symbols, blob, extra)
    return result != 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--font", type=Path,
                        default=ROOT / "_work/truetype-fonts-20260918/abel/Abel-Regular.ttf")
    args = parser.parse_args()
    compiler = args.compiler
    if not Path(compiler).is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    font = args.font.expanduser().resolve()
    if not font.is_file():
        raise SystemExit(f"independent real TTF required: {font}")
    extra = font_memory(font)
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-slots-") as tmp_name:
        temp = Path(tmp_name)
        symbols, blob = compile_gate(Path(compiler).resolve(), ROOT, GATE,
                                     temp / "truetype_slots.img")
        result, steps = run_entry(symbols, blob, extra)
        if result:
            raise SystemExit(f"TrueType slot lifecycle gate failed assertion {result}")
        if not mutant_rejected(Path(compiler).resolve(), temp, extra):
            raise SystemExit("same-slot stale-parser mutant was not rejected")
        print(f"PASS: emitted real TrueType slot lifecycle on {font.name}; 33 assertions, {steps} interpreted instructions")
        print("PASS: bad candidate preserves selected parser; stale same-slot select reopens; unload/replacement advance generations")
        print("PASS: same-slot stale-parser source mutant rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
