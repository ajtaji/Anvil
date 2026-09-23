"""Emitted T0 gate for the memory-backed sfnt table directory reader."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "RaspberryPi4/Tests/truetype_t0_gate.pi4"
LOAD = 0x00400000
STACK = 0x03000000
STEP_LIMIT = 30_000_000


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


def run_main(interpreter, symbols, blob) -> tuple[int, int]:
    cpu = interpreter.A64()
    cpu.sp = STACK
    cpu.memory = {LOAD + i: b for i, b in enumerate(blob)}
    cpu.pc = LOAD + symbols["main"]
    cpu.x[30] = base.RETURN_PC
    for steps in range(STEP_LIMIT):
        if cpu.pc == base.RETURN_PC:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"T0 gate exceeded {STEP_LIMIT} instructions")


def compile_source_mutant(compiler: Path, root: Path, tmp: Path) -> bool:
    """Compile a deliberately weakened bounds check and require the gate to catch it."""
    stage = tmp / "mutant"
    for rel in ("Anvil/Graphics/truetype.pbi", "RaspberryPi4/Tests/truetype_t0_gate.pi4",
                "RaspberryPi4/Intrinsics/bcm2711_hardware.def", "Boards/Raspberry_Pi_4.board"):
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    parser = stage / "Anvil/Graphics/truetype.pbi"
    source = parser.read_text()
    needle = "length > bytes - offset"
    if needle not in source:
        raise SystemExit("T0 mutant anchor missing")
    parser.write_text(source.replace(needle, "length < bytes - offset", 1))
    image = tmp / "truetype_t0_mutant.img"
    symbols, blob = compile_gate(compiler, stage, stage / "RaspberryPi4/Tests/truetype_t0_gate.pi4", image)
    result, _ = run_main(base.load_interp(base.INTERP), symbols, blob)
    return result != 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-t0-") as tmp:
        image = Path(tmp) / "truetype_t0.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        result, steps = run_main(base.load_interp(base.INTERP), symbols, blob)
        if result != 0:
            raise SystemExit(f"T0 emitted gate failed case {result}")
        if not compile_source_mutant(compiler, ROOT, Path(tmp)):
            raise SystemExit("T0 source mutant was not rejected by the emitted gate")
        print(f"PASS: T0 sfnt/first-TTC and lifecycle gate; {steps} interpreted instructions")
        print("PASS: checksums, table bounds, overlap, duplicate tags, TTC offsets and stale-state clearing")
        print("PASS: weakened table-bounds source mutant is rejected")
        print("No metrics, cmap, outlines, rasterisation or renderer claim is made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
