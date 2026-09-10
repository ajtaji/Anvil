#!/usr/bin/env python3
"""Execute the actual bounded touch visual diagnostic against stub leaves."""
from __future__ import annotations
import argparse, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import tcp_multiif_emitted_check as emitted
ROOT=Path(__file__).resolve().parents[1]; PRODUCT=ROOT/'RaspberryPi4/Board/touch_visual_test.pi4'; FIX=ROOT/'RaspberryPi4/Tests/touch_visual_emitted_gate.pi4'
def proc(s,n):
 m=re.search(rf'(?ms)^Procedure(?:\.i)? {n}\([^\n]*\).*?^EndProcedure\s*$',s)
 if not m: raise SystemExit(f'touch visual gate: missing {n}')
 return m.group(0)
def run(a64,pmfc,text,stem):
 with tempfile.TemporaryDirectory(prefix='anvil-touch-visual-') as td:
  d=Path(td); exe=d/pmfc.name; shutil.copy2(pmfc,exe); src=d/'gate.pi4'; src.write_text(text,encoding='utf-8'); img=d/(stem+'.img'); env=os.environ.copy(); env['PMF_ROOT']=str(ROOT)
  r=subprocess.run([str(exe),str(src),'-t','pi4','--load-addr',hex(emitted.LOAD),'--stack-addr',hex(emitted.STACK),'--entry-returns','-o',str(img),'-s'],cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if r.returncode or 'pmfc: OK' not in r.stdout: raise SystemExit('touch visual gate: compile failed\n'+r.stdout)
  return emitted.execute(a64,img)
def main():
 p=argparse.ArgumentParser(); p.add_argument('--pmfc',default=os.environ.get('PMFC')); p.add_argument('--interp',default=os.environ.get('PMF_A64_INTERP')); a=p.parse_args()
 pmfc=emitted.required_path(a.pmfc,'PMFC'); a64=emitted.load_interpreter(emitted.required_path(a.interp,'PMF_A64_INTERP'))
 s=PRODUCT.read_text(encoding='utf-8'); f=FIX.read_text(encoding='utf-8')
 const='\n'.join(x for x in s.splitlines() if x.startswith('#TOUCH_VISUAL_'))
 body='\n\n'.join(proc(s,n) for n in ('TouchVisualColour','TouchVisualMarker','TouchVisualHeader','TouchVisualTest'))
 body=re.sub(r'(?<![A-Za-z])PrintN\(', 'GatePrintN(', body)
 body=re.sub(r'(?<![A-Za-z])PrintDec\(', 'GatePrintDec(', body)
 body=re.sub(r'(?<![A-Za-z])Print\(', 'GatePrint(', body)
 f=f.replace('; @@CONSTANTS@@',const).replace('; @@BODY@@',body)
 result,steps=run(a64,pmfc,f,'gate')
 if result: print(f'touch_visual_emitted_check: FAIL assertion {result} after {steps:,} instructions'); return 1
 mutant=f.replace('    ScrPresentAll()','    ; presentation removed',1)
 mutation_result,mutation_steps=run(a64,pmfc,mutant,'no_present')
 if mutation_result==0: print('touch_visual_emitted_check: FAIL presentation deletion mutant survived'); return 1
 print(f'touch_visual_emitted_check: PASS - ten IDs, motion/release, presentation, exits and restoration, {steps:,} instructions; deletion mutant rejected in {mutation_steps:,}'); return 0
if __name__=='__main__': sys.exit(main())
