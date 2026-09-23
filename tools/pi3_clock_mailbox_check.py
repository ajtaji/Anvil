#!/usr/bin/env python3
"""Emitted mailbox clock setter/readback contract gate for Pi 3."""
from __future__ import annotations
import argparse, pathlib, re, subprocess, tempfile
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = pathlib.Path(__file__).resolve().parents[1]

def procedure(text: str, name: str) -> str:
    start = text.index("Procedure.i " + name)
    end = text.index("\nEndProcedure", start) + len("\nEndProcedure")
    return text[start:end]

def fixture() -> str:
    mailbox = (ROOT / "RaspberryPi3/Lib/mailbox.pbi").read_text()
    old = procedure(mailbox, "Pi3MailboxCall(buffer.i, bytes.i)")
    fake = r'''Procedure.i Pi3MailboxCall(buffer.i, bytes.i)
  Protected tag.i : Protected id.i : Protected rate.i
  gate_calls + 1
  tag=PeekL(buffer+8) : id=PeekL(buffer+20)
  If gate_mode>=20
    If id<>3 And id<>4 : gate_bad=1 : ProcedureReturn 0 : EndIf
    If tag=$38002
      If bytes<>36 Or PeekL(buffer+12)<>12 Or PeekL(buffer+16)<>12 Or PeekL(buffer+28)<>0 Or PeekL(buffer+32)<>0 : gate_bad=1 : ProcedureReturn 0 : EndIf
      rate=400000000 : If id=3 : rate=1200000000 : EndIf
      If PeekL(buffer+24)<>rate : gate_bad=1 : ProcedureReturn 0 : EndIf
      gate_sets+1
    Else
      If bytes<>32 Or PeekL(buffer+12)<>8 Or PeekL(buffer+16)<>4 : gate_bad=1 : ProcedureReturn 0 : EndIf
      If tag=$30004
        rate=400000000 : If id=3 : rate=1200000000 : EndIf
      ElseIf tag=$30047
        If gate_mode=21 : ProcedureReturn 0 : EndIf
        rate=399000000 : If id=3 : rate=1199000000 : EndIf
      ElseIf tag=$30002
        rate=400000000 : If id=3 : rate=1200000000 : EndIf
      Else
        gate_bad=1 : ProcedureReturn 0
      EndIf
    EndIf
    PokeL(buffer+16,$80000008) : PokeL(buffer+24,rate)
    ProcedureReturn 1
  EndIf
  If tag=$38002
    If bytes<>36 Or PeekL(buffer+12)<>12 Or PeekL(buffer+16)<>12 Or id<>4 Or PeekL(buffer+24)<>400000000 Or PeekL(buffer+28)<>0 Or PeekL(buffer+32)<>0 : gate_bad=1 : EndIf
  EndIf
  If bytes <> 36 And gate_mode = 10 : gate_bad = 1 : EndIf
  If gate_mode = 1 : ProcedureReturn 0 : EndIf
  If gate_mode = 2 : PokeL(buffer + 8, $38003) : ProcedureReturn 1 : EndIf
  If gate_mode = 3 : PokeL(buffer + 8, $38002) : PokeL(buffer + 12, 12) : PokeL(buffer + 16, $80000008) : PokeL(buffer + 20, 99) : ProcedureReturn 1 : EndIf
  If gate_mode = 4 : PokeL(buffer + 8, $38002) : PokeL(buffer + 12, 12) : PokeL(buffer + 16, $80000008) : PokeL(buffer + 20, 4) : PokeL(buffer + 24, 0) : ProcedureReturn 1 : EndIf
  If gate_mode = 5 : PokeL(buffer + 8, $38002) : PokeL(buffer + 12, 12) : PokeL(buffer + 16, $80000008) : PokeL(buffer + 20, 4) : PokeL(buffer + 24, 399000000) : ProcedureReturn 1 : EndIf
  If gate_mode = 10 : PokeL(buffer + 8, $38002) : PokeL(buffer + 12, 12) : PokeL(buffer + 16, $80000008) : PokeL(buffer + 20, 4) : PokeL(buffer + 24, 400000000) : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure'''
    mailbox = mailbox.replace(old, fake, 1)
    primitive = (ROOT / "RaspberryPi3/Board/pi3_boot_primitives.pbi").read_text()
    # The fixture exercises mailbox helpers directly; the primitive file adds
    # the stock-clock API and its public readback getters.
    return '''XIncludeFile "RaspberryPi3/Lib/timer.pbi"\nGlobal gate_mode.i\nGlobal gate_calls.i\nGlobal gate_bad.i\nGlobal gate_sets.i\n''' + mailbox + "\n" + primitive + r'''
Procedure.i Main()
  Protected bad.i
  gate_mode=10 : If Pi3ClockSetRate(4,400000000,0)<>400000000 : bad=bad|1 : EndIf
  gate_mode=1 : If Pi3ClockSetRate(4,400000000,0)<>0 : bad=bad|2 : EndIf
  gate_mode=2 : If Pi3ClockSetRate(4,400000000,0)<>0 : bad=bad|4 : EndIf
  gate_mode=3 : If Pi3ClockSetRate(4,400000000,0)<>0 : bad=bad|8 : EndIf
  gate_mode=4 : If Pi3ClockSetRate(4,400000000,0)<>0 : bad=bad|16 : EndIf
  gate_mode=5 : If Pi3ClockSetRate(4,400000000,0)<>399000000 : bad=bad|32 : EndIf
  gate_mode=1 : If Pi3ClockMeasuredRate(4)>=0 : bad=bad|128 : EndIf
  gate_mode=10 : If Pi3ClockSetRate(4,4294967296,0)<>0 : bad=bad|256 : EndIf
  gate_mode=20 : gate_sets=0
  If Pi3BootSetStockClocks()<>1 Or gate_sets<>2 Or Pi3BootStockClockIsMeasured()<>1 Or Pi3BootStockArmActual()<>1199000000 Or Pi3BootStockCoreActual()<>399000000 : bad=bad|512 : EndIf
  gate_mode=21 : gate_sets=0
  If Pi3BootSetStockClocks()<>1 Or gate_sets<>2 Or Pi3BootStockClockIsMeasured()<>0 Or Pi3BootStockArmActual()<>1200000000 Or Pi3BootStockCoreActual()<>400000000 : bad=bad|1024 : EndIf
  If gate_bad<>0 Or gate_calls<6 : bad=bad|64 : EndIf
  ProcedureReturn bad
EndProcedure
'''

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--compiler", required=True); args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    with tempfile.TemporaryDirectory(prefix="pi3-clock-gate-") as td:
        src = pathlib.Path(td) / "clock.pi3"; image = pathlib.Path(td) / "clock.img"
        src.write_text(fixture(), encoding="utf-8")
        cmd = [args.compiler, "--compile", str(src), "-t", "pi3", "--entry-returns", "--load-addr", hex(base.LOAD), "--stack-addr", hex(base.STACK), "-s", "-o", str(image)]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode or not image.exists():
            raise SystemExit("clock mailbox gate compile failed\n" + r.stdout + r.stderr)
        sym = base.parse_symbols(image); blob = image.read_bytes(); interp = base.load_interp(base.INTERP); cpu = interp.A64()
        cpu.sp = base.STACK
        for i, b in enumerate(blob): cpu.memory[base.LOAD + i] = b
        cpu.pc = base.LOAD + sym["main"]; cpu.x[30] = base.RETURN_PC
        for steps in range(2000000):
            if cpu.pc == base.RETURN_PC: break
            cpu.step()
        else: raise SystemExit("clock mailbox gate interpreter timeout")
        if cpu.x[0] != 0: raise SystemExit(f"clock mailbox gate FAIL: mask {cpu.x[0]}")
        print("PASS: emitted clock mailbox setter rejects wrong tag/id/error/zero, preserves request capacity 12, accepts clamp readback")
        return 0
if __name__ == "__main__": raise SystemExit(main())
