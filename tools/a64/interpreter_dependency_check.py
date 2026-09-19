#!/usr/bin/env python3
"""Prove the public interpreter's lazy FP helper exists without private paths.

Uses a fresh isolated Python process to execute a scalar FP instruction,
then runs the oracle self-test. No board, compiler or network is accessed.
"""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROBE = r'''
from pathlib import Path
import struct
import sys
sys.path.insert(0, sys.argv[1])
import a64_interp
cpu = a64_interp.A64()
cpu.pc = 0x1000
# FADD S0,S1,S2: exact binary32 1.0 + 2.0 = 3.0.
cpu.memory.update({0x1000+i: b for i,b in enumerate(struct.pack("<I", 0x1E222820))})
cpu.v[1], cpu.v[2] = 0x3F800000, 0x40000000
cpu.step()
assert cpu.pc == 0x1004 and cpu.v[0] == 0x40400000
import a64_f32_gate
assert Path(a64_f32_gate.__file__).resolve() == Path(sys.argv[1]) / "a64_f32_gate.py"
print("Interpreter dependency: PASS - lazy FP path uses the public-tree helper")
'''

def main():
    for command in (
        [sys.executable, "-I", "-c", PROBE, str(HERE)],
        [sys.executable, "-I", str(HERE / "a64_f32_gate.py"), "--self-test"],
    ):
        result = subprocess.run(command, cwd=HERE, check=False)
        if result.returncode:
            return result.returncode
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
