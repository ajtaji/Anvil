#!/usr/bin/env python3
"""Compile exact Chrome grid-batch procedures into a bounded CPU-only gate."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
TEMPLATE = ROOT / "RaspberryPi4/Tests/vulkan_grid_batch_gate.pi4"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_slots_check import compile_gate, run_entry  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

PROCEDURES = (
    "NeonVkChromeGridBatchBegin",
    "NeonVkChromeGridBatchReserve",
    "NeonVkChromeGridGlyphAppend",
    "NeonVkChromeGridBatchFlush",
    "NeonVkChromeGridBatchEnd",
)


def body(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.[A-Za-z]+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure\s*$",
        source,
    )
    if not match:
        raise SystemExit(f"missing production Chrome procedure {name}")
    return match.group(0)


def make_fixture(stage: Path, mutant: str | None = None) -> Path:
    source = CHROME.read_text(encoding="utf-8")
    if mutant == "uv":
        old = "u1 = neon_F32Ratio(nvcTTX[entry] + nvcTTW[entry], nvcAtlasW)"
        new = "u1 = neon_F32Ratio(nvcTTX[entry] + glyphW, nvcAtlasW)"
        if source.count(old) != 1:
            raise SystemExit("grid UV mutant anchor missing or ambiguous")
        source = source.replace(old, new, 1)
    elif mutant == "capacity":
        old = "nvcVertices > (nvcMaxVertexQuads - neededQuads) * 6"
        new = "nvcVertices > (#NEON_VK_CHROME_MAX_VERTEX_QUADS - neededQuads) * 6"
        if source.count(old) != 1:
            raise SystemExit("grid capacity mutant anchor missing or ambiguous")
        source = source.replace(old, new, 1)

    gate = TEMPLATE.read_text(encoding="utf-8")
    marker = ";@@GRID_BATCH_PROCS@@"
    if gate.count(marker) != 1:
        raise SystemExit("grid batch fixture insertion marker missing or duplicated")
    gate = gate.replace(marker, "\n\n".join(body(source, name) for name in PROCEDURES), 1)
    rel = Path("RaspberryPi4/Tests/vulkan_grid_batch_emitted.pi4")
    target = stage / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(gate, encoding="utf-8")
    for name in ("Boards/Raspberry_Pi_4.board", "RaspberryPi4/Intrinsics/bcm2711_hardware.def"):
        dst = stage / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dst)
    return target


def compile_and_run(compiler: Path, stage: Path, image: Path, mutant: str | None = None) -> tuple[int, int]:
    emitted = make_fixture(stage, mutant)
    symbols, blob = compile_gate(compiler, stage, emitted, image)
    return run_entry(symbols, blob, b"")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = args.compiler.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-vulkan-grid-batch-") as temp_name:
        temp = Path(temp_name)
        result, steps = compile_and_run(compiler, temp / "base", temp / "grid.img")
        if result:
            raise SystemExit(f"Chrome grid batch emitted gate failed case {result}")
        for mutant in ("uv", "capacity"):
            mutant_result, _ = compile_and_run(
                compiler, temp / mutant, temp / f"grid_{mutant}.img", mutant
            )
            if mutant_result == 0:
                raise SystemExit(f"grid batch {mutant} mutant was not rejected")
        print(f"PASS: exact Chrome grid batch emitted gate; 29 assertion cases, {steps} interpreted instructions")
        print("PASS: full-glyph fit/translation, intact UV extents, zero-area/cache-miss refusal, atomic reserve, two-color flush")
        print("PASS: 20,480-cell grid fits the 20,992-quad buffer within two draw segments")
        print("PASS: UV-extent and create-capacity mutants were rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
