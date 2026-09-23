#!/usr/bin/env python3
"""Emitted test for Unicode/kerning-aware Neon widget measurement callbacks."""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_slots_check import compile_gate, font_memory, run_entry, ROOT  # noqa: E402

GATE = ROOT / "RaspberryPi4/Tests/neon_measure_backend_gate.pi4"
NEON = ROOT / "RaspberryPi4/Lib/neon.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
OWNER = ROOT / "RaspberryPi4/Board/vulkan_console.pi4"
MODULES = (
    "Anvil/Graphics/truetype.pbi",
    "Anvil/Graphics/truetype_metrics.pbi",
    "Anvil/Graphics/truetype_cmap.pbi",
    "Anvil/Graphics/truetype_outlines.pbi",
    "Anvil/Graphics/truetype_kern.pbi",
    "Anvil/Graphics/truetype_gpos.pbi",
    "Anvil/Graphics/truetype_layout.pbi",
    "Anvil/Graphics/truetype_raster.pbi",
    "Anvil/Graphics/truetype_slots.pbi",
    "RaspberryPi4/Tests/neon_measure_backend_gate.pi4",
    "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
    "Boards/Raspberry_Pi_4.board",
)
NEON_PROCS = (
    "neon_MeasureWidthUnbound", "neon_MeasureLineHeightUnbound",
    "NeonMeasureBackendInstall", "NeonMeasureBackendClear",
    "NeonMeasureBackendActive", "NeonDrawBackendClear",
    "neon_FontScaleOf", "Neon_CharWidth", "Neon_LineHeight",
    "NeonBitmapLineHeight", "Neon_TextWidth", "Neon_TextRight",
    "Neon_TextCentre",
)
CHROME_PROCS = (
    "nvcTTFontHeightFor", "NeonVkChromeFontPixelHeight",
    "NeonVkChromeMeasureWidth", "NeonVkChromeMeasureLineHeight",
    "NeonVkChromeFontHeightSet",
)


def procedure_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.[A-Za-z]+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure\s*$",
        source,
    )
    if not match:
        raise SystemExit(f"production procedure not found: {name}")
    return match.group(0)


def font_oracle(path: Path) -> dict[str, int]:
    vendored = ROOT / "_work/fonttools-20260918"
    if vendored.is_dir():
        sys.path.insert(0, str(vendored))
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise SystemExit("fontTools is required for the independent width oracle") from exc
    font = TTFont(BytesIO(path.read_bytes()), lazy=False)
    cmap = font.getBestCmap() or {}
    glyph_order = font.getGlyphOrder()
    gids = {name: index for index, name in enumerate(glyph_order)}
    if not all(cp in cmap for cp in (0x41, 0x56, 0xE9)):
        raise SystemExit("Abel fixture must map A, V, and e-acute")
    advances = font["hmtx"].metrics
    a_name, v_name, eacute_name = cmap[0x41], cmap[0x56], cmap[0xE9]
    kern_units = 0
    if "kern" in font:
        for table in font["kern"].kernTables:
            kern_units += table.kernTable.get((a_name, v_name), 0)
    units = font["head"].unitsPerEm
    a_units, v_units = advances[a_name][0], advances[v_name][0]
    ae_units = a_units + advances[eacute_name][0]
    pair_units = a_units + v_units + kern_units
    ceil_px = lambda value, px: (value * px + units - 1) // units
    values = {
        "upem": units,
        "kern_av": kern_units,
        "a_16": ceil_px(a_units, 16),
        "v_16": ceil_px(v_units, 16),
        "av_16": ceil_px(pair_units, 16),
        "ae_16": ceil_px(ae_units, 16),
        "av_12": ceil_px(pair_units, 12),
        "av_32": ceil_px(pair_units, 32),
        "av_10": ceil_px(pair_units, 10),
    }
    if values != {"upem": 2048, "kern_av": -41, "a_16": 8, "v_16": 8,
                  "av_16": 15, "ae_16": 15, "av_12": 11, "av_32": 30,
                  "av_10": 10}:
        raise SystemExit(f"unexpected pinned Abel width oracle: {values}")
    return values


def static_contract() -> int:
    neon = NEON.read_text(encoding="utf-8")
    chrome = CHROME.read_text(encoding="utf-8")
    owner = OWNER.read_text(encoding="utf-8")
    clear_body = procedure_body(neon, "NeonDrawBackendClear")
    install_body = procedure_body(neon, "NeonDrawBackendInstall")
    create_body = procedure_body(chrome, "NeonVkChromeCreateWithCapacities")
    text_body = procedure_body(chrome, "NeonVkChromeText")
    warm_body = procedure_body(owner, "avcWarmGrid")
    requirements = (
        ("NeonDrawBackendClear detaches measure callbacks", "NeonMeasureBackendClear()" in clear_body),
        ("draw-backend install resets old measurement callbacks", "NeonMeasureBackendClear()" in install_body),
        ("Chrome installs measurements after draw backend", create_body.find("NeonDrawBackendInstall(") < create_body.find("NeonMeasureBackendInstall(")),
        ("Chrome draw and measure share per-face height resolver", "nvcTTFontHeightFor(font)" in text_body),
        ("keyboard warm uses draw pixel height, not line-box height", "height = NeonVkChromeFontPixelHeight(#NEON_FONT_MONO)" in warm_body),
        ("UI fallback raster size uses raw bitmap line height", "NeonBitmapLineHeight(#NEON_FONT_UI)" in warm_body),
    )
    for label, ok in requirements:
        if not ok:
            raise SystemExit(f"measurement source contract failed: {label}")
    width_body = procedure_body(chrome, "NeonVkChromeMeasureWidth")
    height_body = procedure_body(chrome, "NeonVkChromeMeasureLineHeight")
    for forbidden in ("AnvilTrueTypeRasterizeGlyph", "nvcTTAddGlyph", "nvcAtlasUploadWarm", "NeonVkChromeBegin"):
        if forbidden in width_body or forbidden in height_body:
            raise SystemExit(f"measurement callback must not draw/raster/upload: {forbidden}")
    return len(requirements) + 4


def make_fixture(stage: Path, mutant: bool = False) -> Path:
    for rel in MODULES:
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    neon_source = NEON.read_text(encoding="utf-8")
    bodies = [procedure_body(neon_source, name) for name in NEON_PROCS]
    if mutant:
        index = NEON_PROCS.index("Neon_TextWidth")
        anchor = "If measured >= 0 : ProcedureReturn measured : EndIf"
        if bodies[index].count(anchor) != 1:
            raise SystemExit("measurement dispatch mutant anchor missing or duplicated")
        bodies[index] = bodies[index].replace(anchor, "If measured > 999999 : ProcedureReturn measured : EndIf", 1)
    chrome_source = CHROME.read_text(encoding="utf-8")
    bodies.extend(procedure_body(chrome_source, name) for name in CHROME_PROCS)
    gate = (stage / "RaspberryPi4/Tests/neon_measure_backend_gate.pi4").read_text(encoding="utf-8")
    marker = ";@@NMG_PROCS@@"
    if gate.count(marker) != 1:
        raise SystemExit("measurement gate insertion marker missing or duplicated")
    gate = gate.replace(marker, "\n\n".join(bodies), 1)
    generated = stage / "RaspberryPi4/Tests/neon_measure_backend_emitted.pi4"
    generated.write_text(gate, encoding="utf-8")
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--font", type=Path,
                        default=ROOT / "_work/truetype-fonts-20260918/abel/Abel-Regular.ttf")
    args = parser.parse_args()
    compiler = Path(args.compiler).expanduser().resolve()
    font = args.font.expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    if not font.is_file():
        raise SystemExit(f"pinned Abel fixture is required: {font}")
    oracle = font_oracle(font)
    static_checks = static_contract()
    extra = font_memory(font)
    with tempfile.TemporaryDirectory(prefix="anvil-neon-measure-") as temp_name:
        temp = Path(temp_name)
        stage = temp / "base"
        stage.mkdir()
        source = make_fixture(stage)
        symbols, blob = compile_gate(compiler, stage, source, temp / "neon_measure.img")
        result, steps = run_entry(symbols, blob, extra)
        if result:
            raise SystemExit(f"measurement emitted gate failed case {result}")
        mutant_stage = temp / "mutant"
        mutant_stage.mkdir()
        mutant_source = make_fixture(mutant_stage, mutant=True)
        mutant_symbols, mutant_blob = compile_gate(compiler, mutant_stage, mutant_source,
                                                    temp / "neon_measure_mutant.img")
        mutant_result, _ = run_entry(mutant_symbols, mutant_blob, extra)
        if mutant_result == 0:
            raise SystemExit("disabled measurement dispatch mutant was not rejected")
    checks = (GATE.read_text(encoding="utf-8").count("mngCheck(") - 1) + static_checks
    print(f"PASS: Neon measurement emitted gate; {checks} assertions, {steps} interpreted instructions")
    print(f"PASS: pinned Abel fontTools widths {oracle}; AV kerning included, UTF-8 and multiline maxima match")
    print("PASS: proportional right/centre origins, pixel-height/line-box parity, keyboard warm key, and bitmap fallback")
    print("PASS: measurement leaves raster/cache/upload counters unchanged; disabled-dispatch mutant rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
