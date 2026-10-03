"""Compile and interpret the Pi 4 Neon coordinate-table reuse gate."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from pmf_compiler import resolve_compiler
import display_pipeline_emitted_check as emitted


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "RaspberryPi4/Tests/neon_coordinate_reuse_gate.pi4"
OUT = ROOT / "runs/neon-coordinate-reuse-gate"
BASE = 0x06300000
X_TABLE = 0x06100000
Y_TABLE = 0x06200000
RECORD_WORDS = 16


def ratio(num: int, den: int) -> int:
    """Independent integer transcription of the original exact-ratio path."""
    if den == 0 or num == 0:
        return 0
    negative = (num < 0) != (den < 0)
    num, den = abs(num), abs(den)
    bias = 40 if num < 4_194_304 else 31
    mantissa = (num << bias) // den
    if mantissa == 0:
        return 0
    highest = mantissa.bit_length() - 1
    exponent = highest - bias
    if highest > 23:
        shift = highest - 23
        mantissa = (mantissa + (1 << (shift - 1))) >> shift
        if mantissa >> 24:
            mantissa >>= 1
            exponent += 1
    elif highest < 23:
        mantissa <<= 23 - highest
    exponent += 127
    if exponent <= 0:
        return 0
    if exponent > 254:
        exponent, mantissa = 254, 0x7FFFFF
    return ((0x80000000 if negative else 0) | (exponent << 23) | (mantissa & 0x7FFFFF)) & 0xFFFFFFFF


def expected_table(dim: int) -> list[int]:
    centre = dim // 2
    return [ratio(n - dim - centre, centre) for n in range(dim * 3)]


def table_hash(values: list[int]) -> int:
    value = 2166136261
    for entry in values:
        value = (value * 33 + entry) & 0xFFFFFFFF
    return value


def build(compiler: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    image = OUT / "neon_coordinate_reuse_gate.img"
    command = [resolve_compiler(compiler), "--compile", str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
               "-t", "pi4", "-s", "--entry-returns", "--load-addr", "0x400000",
               "--stack-addr", "0x3000000", "-o", str(image)]
    result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            text=True, capture_output=True)
    if result.returncode or not image.is_file():
        raise RuntimeError("gate compile failed:\n" + result.stdout + result.stderr)
    return image


def verify(cpu, code: int, steps: int) -> None:
    if code != 0:
        raise AssertionError(f"gate returned {code}")
    tables = {dim: expected_table(dim) for dim in (8, 800, 1280, 4097)}
    hashes = {dim: table_hash(values) for dim, values in tables.items()}
    # (rc, active, spare, builds, reuses, physical, logical, rotation, ready, V3D height)
    cases = [
        (0, (800, 1280), (0, 0), 0, 0, (800, 1280), (800, 1280), 0, 1, 1280),
        (0, (800, 800), (800, 1280), 1, 0, (800, 800), (800, 800), 0, 1, 800),
        (0, (800, 1280), (800, 800), 1, 1, (800, 1280), (800, 1280), 0, 1, 1280),
        (0, (800, 800), (800, 1280), 1, 2, (800, 800), (800, 800), 0, 1, 800),
        (2, (800, 800), (800, 1280), 1, 2, (800, 800), (800, 800), 0, 1, 800),
        (4, (800, 800), (800, 1280), 1, 2, (800, 800), (800, 800), 0, 1, 800),
        (0, (800, 1280), (800, 800), 1, 3, (800, 1280), (1280, 800), 90, 1, 1280),
        (0, (4097, 8), (800, 1280), 2, 3, (800, 1280), (1280, 800), 90, 1, 1280),
        (0, (800, 1280), (0, 0), 2, 4, (800, 1280), (1280, 800), 90, 1, 1280),
        (0, (0, 0), (0, 0), 2, 4, (800, 1280), (1280, 800), 90, 0, 1280),
    ]
    for stage, (rc, active, spare, builds, reuses, physical, logical, rotation, ready, v3d_h) in enumerate(cases):
        actual = tuple(emitted.u32(cpu, BASE + stage * RECORD_WORDS * 4 + i * 4)
                       for i in range(RECORD_WORDS))
        hx = hashes[active[0]] if active[0] else 2166136261
        hy = hashes[active[1]] if active[1] else 2166136261
        expected = (rc, *active, *spare, builds, reuses, hx, hy, *physical,
                    *logical, rotation, ready, v3d_h)
        if actual != expected:
            raise AssertionError(f"stage {stage}:\nactual   {actual}\nexpected {expected}")
    if emitted.u32(cpu, BASE - 4) != 0x43525247:
        raise AssertionError("missing gate tail")
    # The final active pair retains every bit after the oversized fallback
    # and arena invalidation. Hashes above check every intermediate pair.
    for address, values in ((X_TABLE, tables[800]), (Y_TABLE, tables[1280])):
        for index, expected in enumerate(values):
            if emitted.u32(cpu, address + 4 * index) != expected:
                raise AssertionError(f"table bit mismatch at {address:08X}+{index * 4}")
    print(f"PASS: exact coordinate bits, alternating reuse, rollback, rotation, oversized fallback, arena invalidation ({steps:,} A64 steps)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    image = build(args.compiler)
    interpreter = emitted.load_interpreter(emitted.locate_interpreter())
    cpu, code, steps = emitted.execute(interpreter, image)
    verify(cpu, code, steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
