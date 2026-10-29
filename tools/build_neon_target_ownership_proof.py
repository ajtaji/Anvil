#!/usr/bin/env python3
"""Compile production target ownership guards with controlled present/WSI providers.

Never boots, polls, or emulates a board. Other targets are prospective CPU-only
compositions, not hardware drivers. Resolve live map/ownership before entry.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True)
ap.add_argument('--mutate-busy-guards',action='store_true',help='Restore the old busy-state guards in a private candidate; never runs it.')
a=ap.parse_args();root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
owner=root/'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi';raw=owner.read_bytes();source=raw.decode('utf-8-sig')
names=['nvcFail','NeonVkChromeWsiAttach','NeonVkChromeRebind']
bodies=[];identities={}
for name in names:
 matches=list(re.finditer(r'^Procedure\.i '+name+r'\([^\n]*\n.*?^EndProcedure',source,re.M|re.S))
 assert len(matches)==1,'Production body missing or ambiguous: '+name
 body=matches[0].group(0);identities[name]=hashlib.sha256(body.encode()).hexdigest()
 bodies.append(body)
production='\n\n'.join(bodies)
assert production.count('nvdWsiAttach(')==1
production=production.replace('AnvilVkFramebufferTargetCheck(','TofTargetCheck(')
production=production.replace('nvdWsiAttach(','TofAttach(').replace('nvdPresentPending(','TofPresentPending(').replace('nvdWsiEnabled(','TofWsiEnabled(')
if a.mutate_busy_guards:
 for predicate in [' Or nvcFramePending <> 0',' Or nvcFrameAbortable <> 0']:
  assert production.count(predicate)==2
  production=production.replace(predicate,'')
 head,tail=production.split('Procedure.i NeonVkChromeRebind(',1)
 assert head.count(' Or nvcInFrame <> 0')==1
 production=head.replace(' Or nvcInFrame <> 0','')+'Procedure.i NeonVkChromeRebind('+tail
constant_names=['NEON_VK_CHROME_ERR_STATE','NEON_VK_CHROME_ERR_ARGS','NVC_MAX_GENERATION']
constants=['#VK_SUCCESS = 0']
for name in constant_names:
 m=re.findall(r'^#'+name+r'\s*=\s*([^;\r\n]+)',source,re.M);assert len(m)==1
 constants.append('#'+name+' = '+m[0].strip())
layout=state_proof_layout(a.target)
fixture=(root/'Anvil/Graphics/Vulkan/Tests/neon_target_ownership_proof.pbi').read_text(encoding='utf8')
assert fixture.count('; @TOF_PRODUCTION_PROCEDURES@')==1
text='\n'.join(constants)+f'\n#TOF_REPORT = ${layout["report"]:08X}\n'
text+=fixture.replace('; @TOF_PRODUCTION_PROCEDURES@',production)
text+='''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#TOF_REPORT+i,0) : Next
 rc=TargetOwnershipProof()
 PokeI(#TOF_REPORT,$544F4650) : PokeI(#TOF_REPORT+8,rc)
 PokeI(#TOF_REPORT+16,#PMF_CHIP) : PokeI(#TOF_REPORT+24,tofRecords)
 PokeI(#TOF_REPORT+32,tofFailures) : PokeI(#TOF_REPORT+40,2)
 PokeI(#TOF_REPORT+56,$50464F54)
 ProcedureReturn rc
EndProcedure
'''
(out/'proof.pbi').write_text(text,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(root)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(out/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(out/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
(out/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1000:]);assert q.returncode==0
ranges=check_linked_layout(layout,q.stdout+q.stderr);image=out/'proof.img.pmf'
(out/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(raw).hexdigest(),production_body_hashes=identities,dependency_redirections={'nvdWsiAttach':'TofAttach','nvdPresentPending':'TofPresentPending','nvdWsiEnabled':'TofWsiEnabled','AnvilVkFramebufferTargetCheck':'TofTargetCheck'},mutated_busy_guards=a.mutate_busy_guards,checked_ranges=ranges,controlled_provider=True,executed=False),indent=2))
