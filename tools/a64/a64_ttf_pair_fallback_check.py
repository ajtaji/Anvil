"""Compile and run the real TrueType layout with two pair-parser outcomes.

The fixture requires a loud error on actual pair lookup failure. It also
requires a valid GPOS no-match (success with untouched output) to discard
stale pair values and retain the two measured advances.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from a64_interp import A64


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tools" / "a64" / "ttf_pair_fallback_check.pi4"
LOAD = 0x200000
STACK = 0x400000
RESULT = 0x300000
RETURN = 0x7FF00000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=os.environ.get("PMF_COMPILER"), required="PMF_COMPILER" not in os.environ)
    parser.add_argument("--layout-source", type=Path, default=ROOT / "Anvil" / "Graphics" / "truetype_layout.pbi")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="anvil-ttf-pair-") as directory:
        temp = Path(directory)
        fixture = temp / "pair.pi4"
        text = FIXTURE.read_text(encoding="utf-8")
        expected = 'XIncludeFile "Anvil/Graphics/truetype_layout.pbi"'
        if text.count(expected) != 1:
            raise AssertionError("fixture has no unique layout include")
        source = args.layout_source.resolve().as_posix()
        fixture.write_text(text.replace(expected, f'XIncludeFile "{source}"'), encoding="utf-8")
        image = temp / "pair.img"
        command = [str(args.compiler), "--compile", str(fixture), "-t", "pi4",
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
        for steps in range(200000):
            if cpu.pc == RETURN:
                break
            cpu.step()
        else:
            raise RuntimeError("layout fixture exceeded its execution bound")
        status = sum(cpu.memory.get(RESULT + index, 0) << (8 * index) for index in range(8))
        if status:
            raise AssertionError(f"layout fixture returned failure {status} after {steps} A64 steps")
        print(f"PASS: compiled A64 layout kept a zero-advance combining mark, ignored stale no-match values, and refused invalid pair data ({steps} steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
