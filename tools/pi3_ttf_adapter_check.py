"""Emitted real-font test for the Pi 3 offscreen TrueType console adapter."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi3_gate_build  # noqa: E402
import truetype_slots_check as slots  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi3/Tests/pi3_ttf_adapter_gate.pi3"
STUBS = ROOT / "RaspberryPi3/Board/pi3stubs.pi3"
FRAMEBUFFER = ROOT / "RaspberryPi3/Lib/framebuffer.pbi"
LOAD, STACK, LIMIT = 0x00400000, 0x03000000, 100_000_000


def extract(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.[A-Za-z]+)?\s+{re.escape(name)}\s*\(.*?^EndProcedure\s*$",
        source,
    )
    if not match:
        raise SystemExit(f"production procedure not found: {name}")
    return match.group(0)


def make_fixture(path: Path) -> None:
    stub = STUBS.read_text(encoding="utf-8")
    fb = FRAMEBUFFER.read_text(encoding="utf-8")
    procs = [
        extract(stub, "Pi3ScreenBuildTrueTypeCell"),
        extract(stub, "Pi3ScreenDrawTrueType"),
        extract(stub, "Pi3ScreenDrawGlyph"),
        extract(fb, "Pi3FbPack"),
    ]
    fixture = GATE.read_text(encoding="utf-8")
    for marker, body in (
        ("; @@PI3_TTF_ADAPTER_PROCS@@", "\n\n".join(procs)),
        ("; @@PI3_TTF_PACK@@", ""),
    ):
        if fixture.count(marker) != 1:
            raise SystemExit(f"adapter fixture marker missing/duplicated: {marker}")
        fixture = fixture.replace(marker, body, 1)
    fixture = fixture.replace("#TTA_FONT_BYTES = $00100000", f"#TTA_FONT_BYTES = {FONT_SIZE}")
    path.write_text(fixture, encoding="utf-8")


FONT_SIZE = 0


def compile_fixture(compiler: Path, source: Path, image: Path):
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    def do_compile() -> None:
        result = subprocess.run(
            [str(compiler), "--compile", str(source), "-t", "pi3", "--entry-returns",
             "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-s", "-o", str(image)],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        if result.returncode or not image.exists():
            raise SystemExit("Pi3 TrueType adapter fixture compile failed\n" + result.stdout + result.stderr)

    pi3_gate_build.compile_counted(
        do_compile, source, image, compiler=compiler,
        by="tools/pi3_ttf_adapter_check.py", root=ROOT,
    )
    return slots.base.parse_symbols(image), image.read_bytes()


def run(symbols, blob, extra):
    cpu = slots.base.load_interp(slots.base.INTERP).A64()
    cpu.sp = STACK
    cpu.memory = {LOAD + offset: byte for offset, byte in enumerate(blob)}
    cpu.memory.update(extra)
    cpu.pc = LOAD + symbols["main"]
    cpu.x[30] = slots.base.RETURN_PC
    for count in range(LIMIT):
        if cpu.pc == slots.base.RETURN_PC:
            return cpu.x[0], count, cpu
        cpu.step()
    raise SystemExit(f"Pi3 TrueType adapter gate exceeded {LIMIT} instructions")


def main() -> int:
    global FONT_SIZE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--font", type=Path,
                        default=ROOT / "RaspberryPi3/Data/fonts/CourierPrime-Regular.ttf")
    args = parser.parse_args()
    compiler = args.compiler.expanduser().resolve()
    font = args.font.expanduser().resolve()
    if not compiler.is_file() or not font.is_file():
        raise SystemExit("compiler or packaged Courier Prime fixture is missing")
    FONT_SIZE = font.stat().st_size
    if FONT_SIZE > 1_048_576:
        raise SystemExit("font exceeds the resident slot size contract")
    # The production draw body consumes offscreen base/pitch/width/height and
    # never obtains or writes a scanout pointer. Runtime sentinel checks below
    # independently verify that separation.
    draw = extract(STUBS.read_text(encoding="utf-8"), "Pi3ScreenDrawTrueType")
    if "Pi3FbBase()" in draw or "Pi3FbScanoutBase" in draw:
        raise SystemExit("draw adapter must use its offscreen base parameter, not scanout")
    with tempfile.TemporaryDirectory(prefix="pi3-ttf-adapter-") as name:
        temp = Path(name)
        source, image = temp / "adapter.pi3", temp / "adapter.img"
        make_fixture(source)
        symbols, blob = compile_fixture(compiler, source, image)
        extra = slots.font_memory(font)
        result, steps, cpu = run(symbols, blob, extra)
        if result:
            if result in (42, 43):
                diag = {}
                for name in ("actual", "expected", "alpha", "x", "y", "fg", "bg", "clear", "draw_rc"):
                    key = f"global_tta_debug_{name}"
                    if key in symbols:
                        at = symbols[key]
                        diag[name] = sum(cpu.memory.get(at + off, 0) << (off * 8) for off in range(4))
                diag["render_symbol"] = symbols.get("global_tta_render")
                if "global_tta_debug_addr" in symbols:
                    at = symbols["global_tta_debug_addr"]
                    diag["render_addr"] = sum(cpu.memory.get(at + off, 0) << (off * 8) for off in range(4))
                raise SystemExit(f"Pi3 TrueType adapter emitted gate failed case {result}; steps={steps}; pixel={diag}")
            raise SystemExit(f"Pi3 TrueType adapter emitted gate failed case {result}; steps={steps}")
        print(f"Pi3 TrueType adapter PASS: emitted Main=0, {steps:,} instructions, font={FONT_SIZE} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
