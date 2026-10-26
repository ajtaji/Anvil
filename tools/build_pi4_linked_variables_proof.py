#!/usr/bin/env python3
"""Build a returning physical Pi 4 linked-variable reservation proof.

Only the copied map's data-base/minimum constants move to a safe test layout.
Production procedures and guards remain unchanged. Never executes an emulator.
"""
from pathlib import Path
import os,subprocess,json,hashlib,argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--variant',choices=['small','large'],required=True)
ap.add_argument('--compiler')
args=ap.parse_args();variant=args.variant
r=Path(__file__).resolve().parents[1]
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
m=(r/'RaspberryPi4/Board/memmap.pi4').read_text(encoding='utf8').replace('#MON_DATA_LO    = $0D000000','#MON_DATA_LO    = $02000000',1).replace('#MON_DATA_HI    = $0DFFFFFF','#MON_DATA_HI    = $02FFFFFF',1)
(d/'relocated-memmap.pi4').write_text(m,encoding='utf8')
size=65536 if variant=='small' else 17*1024*1024
s='''LoadAddress $01000000
BssAddress $02000000
StackAddress $04F00000
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/timer.pi4"
XIncludeFile "RaspberryPi4/Lib/safety.pi4"
XIncludeFile "'''+(d/'relocated-memmap.pi4').resolve().as_posix()+'''"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
Global Dim mapProofPad.a['''+str(size)+''']
NoClear Global mapProofKeep.i
Procedure.i Main(services.i)
 Define i.i,e.i,hi.i,checks.i
 For i=0 To 255 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$3150414D)
 e=MonDataEnd() : hi=HwMonDataHi()
 PokeI($E1C00008,e) : PokeI($E1C00010,hi)
 PokeI($E1C00018,@mapProofPad[0]) : PokeI($E1C00020,@mapProofKeep)
 PokeI($E1C00028,HwMonRegionLo(1)) : PokeI($E1C00030,HwMonRegionHi(1))
 If e<=@mapProofKeep Or e<=@mapProofPad['''+str(size-1)+'''] : ProcedureReturn 10 : EndIf
 checks=checks+1
 If hi < e-1 Or (hi+1)%$100000<>0 Or hi<$02FFFFFF : ProcedureReturn 11 : EndIf
 checks=checks+1
 If HitsMonitor($02000000,$02000000)<>2 : ProcedureReturn 12 : EndIf
 checks=checks+1
 If HitsMonitor(e-1,e-1)<>2 : ProcedureReturn 13 : EndIf
 checks=checks+1
 If HitsMonitor(hi,hi)<>2 : ProcedureReturn 14 : EndIf
 checks=checks+1
 If HitsMonitor(hi+1,hi+1)<>0 : ProcedureReturn 15 : EndIf
 checks=checks+1
 If HitsMonitor(hi,hi+1)<>2 : ProcedureReturn 16 : EndIf
 checks=checks+1
 If InPayload(e-1,e-1)<>0 Or InPayload(hi,hi)<>0 : ProcedureReturn 17 : EndIf
 checks=checks+1
 If InPayload(hi+1,hi+1)<>1 : ProcedureReturn 18 : EndIf
 checks=checks+1
 PokeI($E1C00038,checks) : PokeI($E1C00040,1)
 ProcedureReturn 0
EndProcedure
'''
(d/'proof.pi4').write_text(s,encoding='utf8');exe=Path(resolve_compiler(args.compiler));env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(exe),'--compile',str((d/'proof.pi4').resolve()),'-t','pi4','--entry-returns','--wants-services','-o',str((d/'proof.img').resolve())],capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW,env=env);(d/'compile.txt').write_text(q.stdout+q.stderr);print((q.stdout+q.stderr)[-1700:]);assert q.returncode==0
(d/'identity.json').write_text(json.dumps(dict(bytes=(d/'proof.img.pmf').stat().st_size,sha256=hashlib.sha256((d/'proof.img.pmf').read_bytes()).hexdigest()),indent=2))
