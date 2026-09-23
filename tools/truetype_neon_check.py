"""Emitted scalar-vs-NEON TrueType coverage conversion gate."""
from __future__ import annotations
import argparse
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate, run_entry, ROOT  # noqa: E402

GATE=ROOT/"RaspberryPi4/Tests/truetype_neon_gate.pi4"

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--compiler",required=True)
    args=parser.parse_args()
    compiler=Path(args.compiler).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-neon-") as folder:
        image=Path(folder)/"truetype_neon.img"
        symbols,blob=compile_gate(compiler,ROOT,GATE,image)
        result,steps=run_entry(symbols,blob)
        if result:
            raise SystemExit(f"NEON coverage emitted gate failed case {result}")
        print(f"PASS: scalar/NEON coverage conversion; counts 0..16, vector lengths 0..63, tails and canaries; {steps} interpreted instructions")
        print("PASS: invalid count and undersized capacity reject atomically")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
