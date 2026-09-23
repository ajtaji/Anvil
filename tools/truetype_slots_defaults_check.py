#!/usr/bin/env python3
"""Fast emitted defaults/init test for the TrueType slot settings seam."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_slots_check import compile_gate, run_entry, ROOT  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

GATE = ROOT / "RaspberryPi4/Tests/truetype_slots_defaults_gate.pi4"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-slot-defaults-") as folder:
        image = Path(folder) / "truetype_slot_defaults.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        result, steps = run_entry(symbols, blob, {})
        if result:
            raise SystemExit(f"TrueType slot defaults gate failed check {result}")
        print(f"PASS: slot defaults/init emitted gate, 12 checks, {steps} interpreted instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
