#!/usr/bin/env python3
"""Build controlled-provider shared lifecycle CPU proof; never executes hardware."""
from pathlib import Path
import argparse,os,subprocess,json,hashlib
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True);ap.add_argument('--mutate-frame-guard',action='store_true',help='Build a controlled-provider negative omitting the prepared hardware-frame guard; expected return4, never boots automatically.');a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
load,stack,report=(layout[k] for k in ['load','stack','report'])
s=f'#LCP_REPORT = ${report:08X}\n'+(r/'RaspberryPi4/Tests/neon_lifecycle_shared_proof.pbi').read_text(encoding='utf8')+'''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 8191 : PokeA(#LCP_REPORT+i,0) : Next
 rc=SharedLifecycleProof()
 PokeI(#LCP_REPORT,$4E4C4650) : PokeI(#LCP_REPORT+8,rc)
 PokeI(#LCP_REPORT+16,#PMF_CHIP) : PokeI(#LCP_REPORT+24,lcpRecords)
 PokeI(#LCP_REPORT+32,lcpFailures) : PokeI(#LCP_REPORT+40,2)
 PokeI(#LCP_REPORT+56,$50464C4E)
 ProcedureReturn rc
EndProcedure
'''
if a.mutate_frame_guard:
 lifecycle=(r/'Anvil/Graphics/neon_lifecycle.pbi').read_text(encoding='utf8')
 needle=' Or (NeonHardwareLifecycleFlags() & #NEON_NATIVE_LIFECYCLE_FRAME) <> 0';assert lifecycle.count(needle)==1
 private=d/'missing_frame_guard.pbi';private.write_text(lifecycle.replace(needle,'',1),encoding='utf8')
 needle='Anvil/Graphics/neon_lifecycle.pbi';assert s.count(needle)==1;s=s.replace(needle,private.as_posix(),1)
(d/'proof.pbi').write_text(s,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(load),'--stack-addr',hex(stack),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1200:]);assert q.returncode==0
ranges=check_linked_layout(layout,q.stdout+q.stderr);ranges['report'][1]=hex(report+8191)
items=[(k,int(v[0],16),int(v[1],16)) for k,v in ranges.items()]
for i,(name,lo,hi) in enumerate(items):
 for other,ol,oh in items[i+1:]:assert hi<ol or oh<lo,name+' overlaps '+other
 if name=='report':assert report+8191<= (0xe1c01fff if a.target=='pi4' else max(x[1] for x in layout['windows']))
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(target=a.target,load=hex(load),stack=hex(stack),report=hex(report),report_bytes=8192,checked_ranges=ranges,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),executed=False,controlled_provider=True,mutated_frame_guard=a.mutate_frame_guard),indent=2))
