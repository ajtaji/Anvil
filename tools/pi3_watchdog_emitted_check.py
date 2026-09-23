#!/usr/bin/env python3
"""Emitted regression gate for the Pi 3 watchdog ownership seam."""
from __future__ import annotations
import argparse, pathlib, re, subprocess, tempfile, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "a64"))
import a64_core_worker_check as base
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT = pathlib.Path(__file__).resolve().parents[1]

def replace_proc(text: str, header: str, body: str) -> str:
    start = text.index(header); end = text.index("\nEndProcedure", start) + len("\nEndProcedure")
    return text[:start] + body + text[end:]

def fixture(mutant: bool = False) -> str:
    wd = (ROOT / "RaspberryPi3/Lib/update_watchdog.pbi").read_text(encoding="utf-8")
    wd = replace_proc(wd, "Procedure.i p3uwRead(address.i)", r'''Procedure.i p3uwRead(address.i)
  ProcedureReturn gate_reg
EndProcedure''')
    wd = replace_proc(wd, "Procedure p3uwWrite(address.i, value.i)", r'''Procedure p3uwWrite(address.i, value.i)
  gate_writes + 1
  If address = $3F10001C
    If (value & $30) = $20 : gate_reg = $20 : Else : gate_reg = 0 : EndIf
  EndIf
EndProcedure''')
    if mutant:
        wd = wd.replace("If completed<=pi3_update_watchdog_completed : ProcedureReturn 0 : EndIf",
                        "If completed<0 : ProcedureReturn 0 : EndIf")
    sd = (ROOT / "RaspberryPi3/Lib/sdhost.pbi").read_text(encoding="utf-8")
    pieces=[]
    for name in ("Pi3SdSetProgressHook", "Pi3SdProgress", "Pi3SdReadBlocks"):
        start=sd.index("Procedure.i "+name+"(")
        end=sd.index("\nEndProcedure",start)+len("\nEndProcedure")
        pieces.append(sd[start:end])
    sd="\n".join(pieces)
    return r'''XIncludeFile "RaspberryPi3/Lib/timer.pbi"
Global gate_reg.i
Global gate_writes.i
Global gate_now.i
Global p3sd_progress_handler.i = @GateSdProgress
Global gate_reads.i
Global gate_notifications.i
Global gate_fail_read.i
Global gate_fail_notify.i
Procedure.i Pi3SdReadBlock(lba.i, buffer.i)
  gate_reads=gate_reads+1
  If gate_reads=gate_fail_read : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i GateSdProgress(completed.i)
  If completed<>512 : ProcedureReturn 0 : EndIf
  gate_notifications=gate_notifications+1
  If gate_notifications=gate_fail_notify : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
Global pi3_up_mounted.i
Global pi3_up_receiving.i
Global pi3_up_loaded.i
Global pi3_up_active.i
Global Dim pi3_up_record.l[256]
#PI3_UPDATE_TRIED = 2
#PI3_UPDATE_CONFIRMED = 3
Procedure.i p3sdContext() : ProcedureReturn 1 : EndProcedure
Procedure.i Pi3UpdateResetReady() : ProcedureReturn 1 : EndProcedure
''' + sd + '\n' + wd + r'''
Procedure.i Main()
  Protected before.i
  pi3_up_mounted=0 : pi3_up_active=0 : gate_reg=0 : gate_writes=0 : gate_now=10
  If Pi3UpdateWatchdogArmEarly()=0 : ProcedureReturn 1 : EndIf
  before=gate_writes
  If Pi3UpdateWatchdogProgress(1)=0 Or gate_writes<=before : ProcedureReturn 2 : EndIf
  before=gate_writes
  If Pi3UpdateWatchdogProgress(1)<>0 Or gate_writes<>before : ProcedureReturn 3 : EndIf
  If Pi3UpdateWatchdogProgress(0)<>0 : ProcedureReturn 4 : EndIf
  If Pi3UpdateWatchdogStopEarly()=0 : ProcedureReturn 5 : EndIf
  pi3_up_mounted=1
  If Pi3UpdateWatchdogArmWindow()=0 : ProcedureReturn 6 : EndIf
  pi3_up_loaded=4
  If Pi3UpdateWatchdogBeginTrial()=0 : ProcedureReturn 7 : EndIf
  before=gate_writes
  If Pi3UpdateWatchdogProgress(2)<>0 Or gate_writes<>before : ProcedureReturn 8 : EndIf
  If Pi3UpdateWatchdogBeginTrial()<>0 Or gate_writes<>before : ProcedureReturn 9 : EndIf
  Pi3SdSetProgressHook(@GateSdProgress)
  If Pi3SdReadBlocks(100,3,$2000000)<>1 Or gate_reads<>3 Or gate_notifications<>3 : ProcedureReturn 10 : EndIf
  gate_reads=0 : gate_notifications=0 : gate_fail_read=2
  If Pi3SdReadBlocks(100,3,$2000000)<>0 Or gate_reads<>2 Or gate_notifications<>1 : ProcedureReturn 11 : EndIf
  gate_reads=0 : gate_notifications=0 : gate_fail_read=0 : gate_fail_notify=2
  If Pi3SdReadBlocks(100,3,$2000000)<>0 Or gate_reads<>2 Or gate_notifications<>2 : ProcedureReturn 12 : EndIf
  Pi3SdSetProgressHook(0)
  gate_reads=0 : gate_notifications=0
  If Pi3SdReadBlocks(100,3,$2000000)<>1 Or gate_reads<>3 Or gate_notifications<>0 : ProcedureReturn 13 : EndIf
  ProcedureReturn 0
EndProcedure
'''

def run_case(compiler: str, source_text: str, root: pathlib.Path) -> int:
    with tempfile.TemporaryDirectory(prefix="pi3-wdt-gate-") as td:
        src=pathlib.Path(td)/"wdt.pi3"; image=pathlib.Path(td)/"wdt.img"; src.write_text(source_text, encoding="utf-8")
        r=subprocess.run([compiler,"--compile",str(src),"-t","pi3","--entry-returns","--load-addr",hex(base.LOAD),"--stack-addr",hex(base.STACK),"-s","-o",str(image)],cwd=root,capture_output=True,text=True)
        if r.returncode or not image.exists(): raise RuntimeError("watchdog gate compile failed\n"+r.stdout+r.stderr)
        sym=base.parse_symbols(image); blob=image.read_bytes(); interp=base.load_interp(base.INTERP); cpu=interp.A64(); cpu.sp=base.STACK
        for i,b in enumerate(blob): cpu.memory[base.LOAD+i]=b
        cpu.pc=base.LOAD+sym["main"]; cpu.x[30]=base.RETURN_PC
        for _ in range(5_000_000):
            if cpu.pc==base.RETURN_PC: break
            cpu.step()
        else: raise RuntimeError("watchdog gate interpreter timeout")
        return cpu.x[0]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--compiler", required=True); args=ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    try:
        result = run_case(args.compiler, fixture(), ROOT)
        if result != 0: raise SystemExit(f"watchdog gate FAIL: case {result}")
        mutant_result = run_case(args.compiler, fixture(mutant=True), ROOT)
        if mutant_result == 0: raise SystemExit("watchdog gate mutant unexpectedly passed")
    except RuntimeError as e:
        raise SystemExit(str(e))
    print("PASS: emitted watchdog ownership rejects duplicate/backward tokens, revokes feeds at trial handoff, reports only completed SD sectors, and catches unconditional-feed mutant")
    return 0
if __name__=="__main__": raise SystemExit(main())
