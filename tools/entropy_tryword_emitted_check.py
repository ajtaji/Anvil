#!/usr/bin/env python3
"""Emit and execute the shipped one-word nonblocking RNG200 seam."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted

ROOT = Path(__file__).resolve().parents[1]
ENTROPY = ROOT / "RaspberryPi4" / "Lib" / "entropy.pi4"


def procedure(source: str, name: str) -> str:
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines)
                  if line.startswith((f"Procedure {name}(", f"Procedure.i {name}("))), None)
    if first is None:
        raise SystemExit(f"entropy try-word gate: production procedure {name} not found")
    last = next(i for i in range(first + 1, len(lines)) if lines[i] == "EndProcedure")
    return "\n".join(lines[first:last + 1])


def probe_source() -> str:
    body = procedure(ENTROPY.read_text(encoding="utf-8"), "EntropyTryWord")
    return r'''
EnableExplicit
#ENTROPY_OK = 1
#ENTROPY_ERR_HEALTH = -2
#ENTROPY_ERR_OFF = -3
#ENTROPY_ERR_ARG = -4
#ENTROPY_READY_BITS = 16
#RNG_FIFO_DATA_OFF = $20
Global entWordsRead.i
Global entHealthStops.i
Global gate_enabled.i
Global gate_bits.i
Global gate_healthy.i
Global gate_fifo.i
Global gate_data.i
Global gate_dataReads.i
Global gate_healthReads.i
Global gate_fifoReads.i
Global gate_word.i
Global Dim gate_guard.a[12]
Procedure.i EntropyEnabled() : ProcedureReturn gate_enabled : EndProcedure
Procedure.i EntropyTotalBits() : ProcedureReturn gate_bits : EndProcedure
Procedure.i EntropyHealthy() : gate_healthReads=gate_healthReads+1 : ProcedureReturn gate_healthy : EndProcedure
Procedure.i EntropyFifoCount() : gate_fifoReads=gate_fifoReads+1 : ProcedureReturn gate_fifo : EndProcedure
Procedure.i EntropyReg(off.i) : gate_dataReads=gate_dataReads+1 : ProcedureReturn gate_data : EndProcedure
''' + "\n" + body + r'''
Procedure GateReset()
  gate_enabled=1 : gate_bits=17 : gate_healthy=1 : gate_fifo=1
  gate_data=$12345678 : gate_dataReads=0 : gate_healthReads=0 : gate_fifoReads=0
  gate_word=0 : entWordsRead=0 : entHealthStops=0
EndProcedure
Procedure.i Main()
  Define i.i
  GateReset()
  If EntropyTryWord(0) <> #ENTROPY_ERR_ARG Or gate_dataReads <> 0 : ProcedureReturn 1 : EndIf
  GateReset() : gate_enabled=0
  If EntropyTryWord(@gate_word) <> #ENTROPY_ERR_OFF Or gate_healthReads <> 0 : ProcedureReturn 2 : EndIf
  GateReset() : gate_bits=16
  If EntropyTryWord(@gate_word) <> 0 Or gate_healthReads <> 1 Or gate_fifoReads <> 0 : ProcedureReturn 3 : EndIf
  GateReset() : gate_healthy=0
  If EntropyTryWord(@gate_word) <> #ENTROPY_ERR_HEALTH Or entHealthStops <> 1 Or gate_dataReads <> 0 : ProcedureReturn 4 : EndIf
  GateReset() : gate_fifo=0
  If EntropyTryWord(@gate_word) <> 0 Or gate_fifoReads <> 1 Or gate_dataReads <> 0 : ProcedureReturn 5 : EndIf
  GateReset()
  If EntropyTryWord(@gate_word) <> #ENTROPY_OK : ProcedureReturn 6 : EndIf
  If gate_word <> gate_data Or entWordsRead <> 1 Or gate_dataReads <> 1 : ProcedureReturn 7 : EndIf
  gate_data=$89ABCDEF
  If EntropyTryWord(@gate_word) <> #ENTROPY_OK Or gate_word <> gate_data : ProcedureReturn 8 : EndIf
  If entWordsRead <> 2 Or gate_dataReads <> 2 : ProcedureReturn 9 : EndIf
  ; Recovery writes the eighth SNonce word at the end of a 32-byte buffer.
  ; Prove the production seam stores exactly four bytes and preserves both
  ; neighboring sentinels rather than relying on a naturally wide `.i` slot.
  GateReset()
  For i=0 To 11 : gate_guard[i]=$A5 : Next
  If EntropyTryWord(@gate_guard[4]) <> #ENTROPY_OK : ProcedureReturn 10 : EndIf
  For i=0 To 3 : If gate_guard[i] <> $A5 : ProcedureReturn 10 : EndIf : Next
  For i=8 To 11 : If gate_guard[i] <> $A5 : ProcedureReturn 10 : EndIf : Next
  If PeekL(@gate_guard[4]) <> gate_data : ProcedureReturn 10 : EndIf
  ProcedureReturn 0
EndProcedure
'''


def build(compiler: Path, work: Path, probe: Path) -> Path:
    staged = work / compiler.name
    shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir():
        shutil.copytree(ROOT / "Boards", work / "Boards")
    image = work / "entropy_tryword_gate.img"
    cmd = [str(staged), "--compile", str(probe), "-t", "pi4",
           "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK),
           "--entry-returns", "-o", str(image), "-s"]
    env = os.environ.copy(); env["PMF_ROOT"] = str(ROOT)
    run = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit("entropy try-word gate: compile failed\n" + run.stdout)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    a64 = emitted.load_interpreter(emitted.required_path(args.interp, "PMF_A64_INTERP"))
    with tempfile.TemporaryDirectory(prefix="anvil-entropy-tryword-") as temporary:
        work = Path(temporary)
        probe = work / "entropy_tryword_gate.pi4"
        probe.write_text(probe_source(), encoding="utf-8", newline="\n")
        result, steps = emitted.execute(a64, build(compiler, work, probe))
    if result:
        print(f"entropy_tryword_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
        return 1
    print(f"entropy_tryword_emitted_check: PASS - 10 assertions, {steps:,} A64 instructions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
