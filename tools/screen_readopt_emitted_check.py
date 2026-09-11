#!/usr/bin/env python3
"""Execute the actual HVS live-list state machine with stubbed MMIO leaves."""
from __future__ import annotations
import argparse, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import tcp_multiif_emitted_check as emitted
ROOT=Path(__file__).resolve().parents[1]; PRODUCT=ROOT/'RaspberryPi4/Lib/hvs.pi4'; FIX=ROOT/'RaspberryPi4/Tests/screen_readopt_emitted_gate.pi4'; SURFACE=ROOT/'RaspberryPi4/Tests/screen_readopt_surface_emitted_gate.pi4'; SCREEN=ROOT/'RaspberryPi4/Board/screen_source.pi4'
def proc(s,n):
 m=re.search(rf'(?ms)^Procedure(?:\.i)? {n}\([^\n]*\).*?^EndProcedure\s*$',s)
 if not m: m=re.search(rf'(?m)^Procedure(?:\.i)? {n}\([^\n]*EndProcedure\s*$',s)
 if not m: raise SystemExit('screen readopt emitted gate: missing '+n)
 return m.group(0)
def run(a64,pmfc,text,stem):
 with tempfile.TemporaryDirectory(prefix='anvil-readopt-') as td:
  d=Path(td); exe=d/pmfc.name; shutil.copy2(pmfc,exe); src=d/'gate.pi4'; src.write_text(text,encoding='utf-8'); img=d/(stem+'.img'); env=os.environ.copy(); env['PMF_ROOT']=str(ROOT)
  r=subprocess.run([str(exe),str(src),'-t','pi4','--load-addr',hex(emitted.LOAD),'--stack-addr',hex(emitted.STACK),'--entry-returns','-o',str(img),'-s'],cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if r.returncode or 'pmfc: OK' not in r.stdout: raise SystemExit('screen readopt emitted gate: compile failed\n'+r.stdout)
  return emitted.execute(a64,img)
def main():
 p=argparse.ArgumentParser(); p.add_argument('--pmfc',default=os.environ.get('PMFC')); p.add_argument('--interp',default=os.environ.get('PMF_A64_INTERP')); a=p.parse_args()
 pmfc=emitted.required_path(a.pmfc,'PMFC'); a64=emitted.load_interpreter(emitted.required_path(a.interp,'PMF_A64_INTERP'))
 s=PRODUCT.read_text(encoding='utf-8'); f=FIX.read_text(encoding='utf-8')
 body='\n\n'.join(proc(s,n) for n in ('HvsMirror','HvsFlipBegin','HvsFlipResolve','HvsFlipPending'))
 f=f.replace('; @@BODY@@',body)
 result,steps=run(a64,pmfc,f,'gate')
 if result: print(f'screen_readopt_emitted_check: FAIL assertion {result} after {steps:,} instructions'); return 1
 anchor='  If HvsDlistActive() <> hvs_flip_at\n    ProcedureReturn 0\n  EndIf'
 if f.count(anchor)!=1: raise SystemExit('screen readopt emitted gate: resolve anchor not unique')
 mutant=f.replace(anchor,'  ; active-list qualification removed',1)
 mr,ms=run(a64,pmfc,mutant,'no_active_qualifier')
 if mr==0: print('screen_readopt_emitted_check: FAIL active-list mutant survived'); return 1
 ss=SCREEN.read_text(encoding='utf-8'); sf=SURFACE.read_text(encoding='utf-8').replace('; @@BODY@@','\n\n'.join(proc(ss,n) for n in ('ScrDsiReadoptBegin','ScrDsiReadoptResolve')))
 sr,ssteps=run(a64,pmfc,sf,'surface')
 if sr: print(f'screen_readopt_emitted_check: FAIL surface assertion {sr} after {ssteps:,} instructions'); return 1
 print(f'screen_readopt_emitted_check: PASS - actual mirror/pending/late-adoption bodies and all 16 surface transitions, {steps:,}/{ssteps:,} instructions; qualifier mutant rejected in {ms:,}')
 return 0
if __name__=='__main__': sys.exit(main())
