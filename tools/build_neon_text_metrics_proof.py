#!/usr/bin/env python3
"""Compile shared-only metric queries; never enters or emulates hardware."""
from pathlib import Path
import argparse,os,subprocess,json,hashlib
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
from neon_text_metrics_contract import cases
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--mutate-width-bound',action='store_true',help='Compile a private source-negative omitting the legacy width bound; expected one failed observation. Never executes it.');a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
source=(r/'Anvil/Graphics/Tests/neon_text_metrics_proof.pbi').read_text(encoding='utf8');actions,values,_=cases();assert source.count('; @METRIC_CASES@')==1;source=source.replace('; @METRIC_CASES@',actions)
if a.mutate_width_bound:
 front=(r/'Anvil/Graphics/neon_frontend.pbi').read_text(encoding='utf8');needle='    If i > 4096\n      Break\n    EndIf\n';assert front.count(needle)==1
 p=d/'unbounded_width.pbi';p.write_text(front.replace(needle,''),encoding='utf8');source=source.replace('Anvil/Graphics/neon_frontend.pbi',p.as_posix())
source=f'#MM_REPORT=${layout["report"]:08X}\n'+source+'''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#MM_REPORT+i,0) : Next
 rc=SharedTextMetricsProof()
 PokeI(#MM_REPORT,$4E4D5450) : PokeI(#MM_REPORT+8,rc)
 PokeI(#MM_REPORT+16,#PMF_CHIP) : PokeI(#MM_REPORT+24,mmChecks)
 PokeI(#MM_REPORT+32,mmFailures) : PokeI(#MM_REPORT+40,1)
 PokeI(#MM_REPORT+56,$50544D4E)
 ProcedureReturn rc
EndProcedure
'''
(d/'proof.pbi').write_text(source,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1000:]);assert q.returncode==0
ranges=check_linked_layout(layout,q.stdout+q.stderr);image=d/'proof.img.pmf'
(d/'identity.json').write_text(json.dumps(dict(target=a.target,planned_observations=len(values),bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),checked_ranges=ranges,executed=False,mutated_width_bound=a.mutate_width_bound,shared_only=True),indent=2))
