"""Compile and execute the Anvil-only Neon Vulkan font-handle gate."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_font_port_gate.pi4"
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as gate  # noqa: E402


def main() -> int:
    if not COMPILER.is_file():
        raise SystemExit(f"compiler not found: {COMPILER}")
    with tempfile.TemporaryDirectory(prefix="neon-vk-font-port-") as temp:
        image = Path(temp) / "font_gate.img"
        env = dict(os.environ, PMF_ROOT=str(ROOT))
        run = subprocess.run(
            [str(COMPILER), "--compile", str(SOURCE), "-t", "pi4", "-s",
             "--entry-returns", "--load-addr", "0x400000", "--bss-addr", "0x800000",
             "--stack-addr", "0x3000000", "-o", str(image)],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        if run.returncode or not image.is_file():
            raise AssertionError(f"font port compilation failed:\n{run.stdout}\n{run.stderr}")
        a64 = gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        base = a64.A64

        class FloatingPointA64(base):
            def __init__(self):
                super().__init__()
                self.enable_system_registers(el=2)

        a64.A64 = FloatingPointA64
        result, steps = gate.execute(a64, image, 1_000_000)
        if result != 0:
            raise AssertionError(f"font port assertion {result} failed after {steps:,} instructions")
        print(f"PASS: Neon Vulkan font handle, metrics and placement ({steps:,} emitted A64 instructions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
