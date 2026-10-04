"""Compile and execute the production TrueType text transform without a board."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_scaled_text_gate.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402


def main() -> int:
    production = CHROME.read_text(encoding="utf-8-sig")
    source = GATE.read_text(encoding="utf-8-sig")
    marker = "; @PRODUCTION_TEXT_TRANSFORM@"
    if source.count(marker) != 1:
        raise AssertionError("text transform marker missing or duplicated")
    names = ("nvcTTRoundDiv", "nvcTTTextMapped", "NeonVkChromeTextMapped")
    source = source.replace(marker, "\n\n".join(gate.procedure_body(production, name) for name in names))
    with tempfile.TemporaryDirectory(prefix="neon-vk-scaled-text-") as temp:
        path = Path(temp)
        test_source = path / "neon_vk_scaled_text_gate.pi4"
        image = path / "neon_vk_scaled_text_gate.img"
        test_source.write_text(source, encoding="utf-8")
        run = subprocess.run(
            [str(COMPILER), "--compile", str(test_source), "-t", "pi4", "-s",
             "--entry-returns", "--load-addr", "0x400000", "--bss-addr", "0x800000",
             "--stack-addr", "0x3000000", "-o", str(image)],
            cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if run.returncode or not image.is_file():
            raise AssertionError("scaled text compilation failed:\n" + run.stdout + run.stderr)
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        base = a64.A64

        class FloatingPointA64(base):
            def __init__(self):
                super().__init__()
                self.enable_system_registers(el=2)

        a64.A64 = FloatingPointA64
        result, steps = gate.execute(a64, image, 1_000_000)
        if result != 0:
            raise AssertionError(f"scaled text assertion {result} failed after {steps:,} instructions")
        print(f"PASS: production TrueType glyph transform and preflight ({steps:,} emitted A64 instructions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
