"""Run the production Pi4 font reflow procedure in the A64 model.

The fixture extracts ScreenRebuildAtGeometry from screen_cmd.pi4 and stubs
only its hardware effects. A font-only change must preserve Vulkan callback
ownership and not clear or present an intermediate CPU frame.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from a64_interp import A64


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "RaspberryPi4" / "Board" / "screen_cmd.pi4"
FIXTURE = ROOT / "tools" / "a64" / "font_reflow_check.pi4"
LOAD = 0x200000
STACK = 0x400000
RESULT = 0x300000
RETURN = 0x7FF00000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=os.environ.get("PMF_COMPILER"), required="PMF_COMPILER" not in os.environ)
    parser.add_argument("--mutate", action="store_true", help="prove the gate rejects a CPU callback after font reflow")
    args = parser.parse_args()

    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("Procedure ScreenRebuildAtGeometry(fontOnly.i)")
    end = source.index("\nEndProcedure", start) + len("\nEndProcedure")
    procedure = source[start:end]
    if args.mutate:
        original = "ConSetRenderer(@VulkanConsolePump)"
        if procedure.count(original) != 1:
            raise AssertionError("cannot locate the unique Vulkan reflow callback")
        procedure = procedure.replace(original, "ConSetRenderer(@ConPaintDma)")
    fixture = FIXTURE.read_text(encoding="utf-8")
    if fixture.count("__REBUILD__") != 1:
        raise AssertionError("fixture has no unique procedure insertion point")

    with tempfile.TemporaryDirectory(prefix="anvil-font-reflow-") as directory:
        temp = Path(directory)
        test_source = temp / "reflow.pi4"
        test_source.write_text(fixture.replace("__REBUILD__", procedure), encoding="utf-8")
        image = temp / "reflow.img"
        command = [str(args.compiler), "--compile", str(test_source), "-t", "pi4",
                   "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                   "--entry-returns", "-o", str(image)]
        result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        if result.returncode or "pmfc: OK" not in result.stdout or not image.is_file():
            raise RuntimeError("fixture compile failed:\n" + result.stdout)

        cpu = A64()
        for index, byte in enumerate(image.read_bytes()):
            cpu.memory[LOAD + index] = byte
        cpu.pc = LOAD
        cpu.sp = STACK
        cpu.x[30] = RETURN
        for steps in range(300000):
            if cpu.pc == RETURN:
                break
            cpu.step()
        else:
            raise RuntimeError("font reflow exceeded its execution bound")
        status = sum(cpu.memory.get(RESULT + index, 0) << (8 * index) for index in range(8))
        if args.mutate:
            if status != 1:
                raise AssertionError(f"mutated font reflow returned {status}, expected callback failure 1")
            print(f"PASS: CPU-callback regression rejected after {steps} A64 steps")
            return 0
        if status:
            raise AssertionError(f"font reflow fixture returned failure {status} after {steps} A64 steps")
        print(f"PASS: font reflow preserves Vulkan callback and presents no partial CPU frame ({steps} A64 steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
