#!/usr/bin/env python3
"""Emitted CPU-only cache gate using exact Chrome cache procedure bodies."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_slots_check import compile_gate, font_memory, run_entry, ROOT  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

GATE = ROOT / "RaspberryPi4/Tests/truetype_chrome_cache_gate.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
MODULES = (
    "Anvil/Graphics/truetype.pbi",
    "Anvil/Graphics/truetype_metrics.pbi",
    "Anvil/Graphics/truetype_cmap.pbi",
    "Anvil/Graphics/truetype_outlines.pbi",
    "Anvil/Graphics/truetype_kern.pbi",
    "Anvil/Graphics/truetype_gpos.pbi",
    "Anvil/Graphics/truetype_raster.pbi",
    "Anvil/Graphics/truetype_slots.pbi",
    "RaspberryPi4/Tests/truetype_chrome_cache_gate.pi4",
    "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
    "Boards/Raspberry_Pi_4.board",
)
PROCEDURES = (
    "nvcFail",
    "nvcTTCacheFind",
    "nvcTTCacheClear",
    "nvcTTAddGlyph",
    "NeonVkChromeWarmTrueTypeText",
    "NeonVkChromeTTCacheReset",
)


def procedure_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.[A-Za-z]+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure\s*$",
        source,
    )
    if not match:
        raise SystemExit(f"production Chrome procedure not found: {name}")
    return match.group(0)


def make_fixture(stage: Path, mutant: str | None = None) -> Path:
    for rel in MODULES:
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    chrome = stage / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
    chrome.parent.mkdir(parents=True, exist_ok=True)
    source = CHROME.read_text()
    if mutant == "generation":
        anchor = "nvcTTSlot[i] = slot And nvcTTGen[i] = generation And nvcTTHeight[i] = pixelHeight And nvcTTGlyph[i] = glyph"
        if anchor not in source:
            raise SystemExit("Chrome cache generation-key mutant anchor missing")
        source = source.replace(anchor,
                                "nvcTTSlot[i] = slot And nvcTTHeight[i] = pixelHeight And nvcTTGlyph[i] = glyph",
                                1)
    elif mutant == "wrap":
        anchor = "  nvcTTNextY = y\n"
        if source.count(anchor) != 1:
            raise SystemExit("Chrome atlas wrap-row mutant anchor missing or duplicated")
        source = source.replace(anchor, "", 1)
    chrome.write_text(source)
    bodies = "\n\n".join(procedure_body(source, name) for name in PROCEDURES)
    gate = (stage / "RaspberryPi4/Tests/truetype_chrome_cache_gate.pi4").read_text()
    anchor = ";@@NVC_CACHE_PROCS@@"
    if gate.count(anchor) != 1:
        raise SystemExit("Chrome cache gate procedure insertion marker is missing or duplicated")
    gate = gate.replace(anchor, bodies, 1)
    generated = stage / "RaspberryPi4/Tests/truetype_chrome_cache_emitted.pi4"
    generated.write_text(gate)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--font", type=Path,
                        default=ROOT / "_work/truetype-fonts-20260918/abel/Abel-Regular.ttf")
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = Path(args.compiler).expanduser().resolve()
    font = args.font.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    if not font.is_file():
        raise SystemExit(f"independent real TTF required: {font}")
    extra = font_memory(font)
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-chrome-cache-") as temp_name:
        temp = Path(temp_name)
        stage = temp / "base"
        stage.mkdir()
        source = make_fixture(stage)
        symbols, blob = compile_gate(compiler, stage, source,
                                     temp / "truetype_chrome_cache.img")
        result, steps = run_entry(symbols, blob, extra)
        if result:
            raise SystemExit(f"Chrome cache emitted gate failed case {result}")
        mutant_stage = temp / "mutant-generation"
        mutant_stage.mkdir()
        mutant_source = make_fixture(mutant_stage, mutant="generation")
        mutant_symbols, mutant_blob = compile_gate(compiler, mutant_stage, mutant_source,
                                                    temp / "truetype_chrome_cache_mutant_generation.img")
        mutant_result, _ = run_entry(mutant_symbols, mutant_blob, extra)
        if mutant_result == 0:
            raise SystemExit("cache key omitting slot generation was not rejected")
        wrap_stage = temp / "mutant-wrap"
        wrap_stage.mkdir()
        wrap_source = make_fixture(wrap_stage, mutant="wrap")
        wrap_symbols, wrap_blob = compile_gate(compiler, wrap_stage, wrap_source,
                                                temp / "truetype_chrome_cache_mutant_wrap.img")
        wrap_result, _ = run_entry(wrap_symbols, wrap_blob, extra)
        if wrap_result == 0:
            raise SystemExit("atlas shelf-wrap row-loss mutant was not rejected")
        checks = GATE.read_text().count("tcCheck(") - 1
        print(f"PASS: real Abel Chrome cache emitted gate; {checks} checks, {steps} interpreted instructions")
        print("PASS: size/slot/generation keys, cache hits, atomic capacity refusal, reset and one dirty upload")
        print("PASS: shelf-wrap row persistence and pixel-retention checks")
        print("PASS: source mutants omitting slot generation and wrapped-row persistence were rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
