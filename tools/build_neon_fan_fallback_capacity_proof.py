#!/usr/bin/env python3
"""Build a physical direct indexed-fan capacity proof; never boots it."""
from pathlib import Path
import os,subprocess,sys,json,hashlib,argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--compiler',required=True);ap.add_argument('--lifetime',action='store_true',help='Build multiple-fan, atomic-refusal and abort/reuse proof instead of full point capacity.');a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
old=0;helper_name='neon_fan_fallback_lifetime_proof.pbi' if a.lifetime else 'neon_fan_fallback_capacity_proof.pbi';helper=(r/'RaspberryPi4/Tests'/helper_name).read_text(encoding='utf8')
s=(r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8')
s=s.replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1).replace('#NW_WINDOW_BYTES      = $00C00000','#NW_WINDOW_BYTES      = $01A00000').replace('#NW_MAP_SPAN          = $00FE8000','#NW_MAP_SPAN          = $01DE8000')
b=(r/'RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4').read_text(encoding='utf8');needle=' | #ANVIL_VK_CAP_TRIANGLE_FAN';assert b.count(needle)==1
(d/'masked_backend.pi4').write_text(b.replace(needle,'',1),encoding='utf8');s=s.replace('RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4',(d/'masked_backend.pi4').as_posix(),1)
at=s.index('Procedure.i Main()');s=s[:at]+'#FAN_EXPECT_OLD_REFUSAL = '+str(old)+'\n'+helper+'\n'+s[at:]
s=s.replace('Procedure.i Main()','Procedure.i FanCapacityDiagnosticMain()',1)
needle='  ; Destroy the production adapter first:';assert s.count(needle)==1
s=s.replace(needle,'  PokeI($E1C01000,streamProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n'+needle,1)
s+='''
Procedure.i Main(services.i)
 Define report.i,i.i,n.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=FanCapacityDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 PokeI($E1C01188,streamMemory())
 n=0 : For i=1 To #ANVIL_VK_MAX_BUFFERS : If avkBufLive[i]<>0 : n=n+1 : EndIf : Next : PokeI($E1C01190,n)
 n=0 : For i=1 To #ANVIL_VK_MAX_PIPELINES : If avkPipeLive[i]<>0 : n=n+1 : EndIf : Next : PokeI($E1C01198,n)
 n=0 : For i=1 To #ANVIL_VK_MAX_LAYOUTS : If avkLayLive[i]<>0 : n=n+1 : EndIf : Next : PokeI($E1C011A0,n)
 If PeekL($E1C00004)<>0 : ProcedureReturn 1000+PeekL($E1C00004) : EndIf
 ProcedureReturn PeekI($E1C01000)
EndProcedure
'''
(d/'proof.pi4').write_text(s,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(r)
exe=str(resolve_compiler(a.compiler))
q=subprocess.run([exe,'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1200:]);assert q.returncode==0
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),lifetime=a.lifetime,helper=helper_name),indent=2))
