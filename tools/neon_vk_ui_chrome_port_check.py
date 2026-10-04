"""Run the Pi 4 emitted drawing gate and compile the full Vulkan composition."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMPILER = Path(r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe")
GATE = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_ui_chrome_gate.pi4"
FULL = ROOT / "Anvil/Graphics/Vulkan/Tests/neon_vk_ui_chrome_full_compile.pi4"

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/a64"))
import neon_vk_chrome_acceptance_check as chrome_gate  # noqa: E402


def compile_pi4(source: Path, image: Path) -> None:
    env = dict(os.environ, PMF_ROOT=str(ROOT))
    run = subprocess.run(
        [str(COMPILER), "--compile", str(source), "-t", "pi4", "-s",
         "--entry-returns", "--load-addr", "0x400000", "--bss-addr", "0x800000",
         "--stack-addr", "0x3000000", "-o", str(image)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180,
    )
    if run.returncode or "pmfc: OK" not in run.stdout or not image.is_file():
        raise AssertionError(f"Pi 4 compile failed for {source.name}:\n{run.stdout}\n{run.stderr}")


def main() -> int:
    if not COMPILER.is_file():
        raise SystemExit(f"compiler not found: {COMPILER}")
    with tempfile.TemporaryDirectory(prefix="neon-vk-ui-chrome-") as temp:
        work = Path(temp)
        emitted = work / "ui_gate.img"
        compile_pi4(GATE, emitted)
        a64 = chrome_gate.load_interpreter(ROOT / "tools/a64/a64_interp.py")
        base = a64.A64

        class FloatingPointA64(base):
            def __init__(self):
                super().__init__()
                self.enable_system_registers(el=2)

        a64.A64 = FloatingPointA64
        result, steps = chrome_gate.execute(a64, emitted, 1_000_000)
        if result != 0:
            raise AssertionError(f"drawing assertion {result} failed after {steps:,} emitted A64 instructions")
        compile_pi4(FULL, work / "ui_full.img")
        print(f"PASS: 27 drawing assertions in {steps:,} emitted A64 instructions; full Pi 4 Vulkan composition compiled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
