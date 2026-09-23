#!/usr/bin/env python3
"""Emitted gate for Neon's public contiguous GPU mapped-range contract."""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate, run_entry, ROOT  # noqa: E402

GATE = ROOT / "RaspberryPi4/Tests/neon_gpu_range_gate.pi4"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-neon-gpu-range-") as folder:
        image = Path(folder) / "neon_gpu_range.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        result, steps = run_entry(symbols, blob)
        if result:
            raise SystemExit(f"Neon GPU range emitted gate failed case {result}")
        print(f"PASS: Neon GPU mapped-range gate, 23 cases, {steps} interpreted instructions")
        print("PASS: not-ready rejection, framebuffer and extra heap ranges, signed overflow, gaps, and overruns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
