#!/usr/bin/env python3
"""Build the physical Pi4 production float-port capacity proof; never boots it."""
from pathlib import Path
import os,subprocess,argparse,json,hashlib,sys
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--compiler');a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=True)
helper=(r/'RaspberryPi4/Tests/neon_port_capacity_gpu_proof.pbi').read_text(encoding='utf8')
s=(r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8')
s=s.replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1).replace('#NW_WINDOW_BYTES      = $00C00000','#NW_WINDOW_BYTES      = $01400000').replace('#NW_MAP_SPAN          = $00FE8000','#NW_MAP_SPAN          = $017E8000')
at=s.index('Procedure.i Main()');s=s[:at]+helper+'\n'+s[at:];s=s.replace('Procedure.i Main()','Procedure.i LineStreamDiagnosticMain()',1)
s=s.replace('  ; Destroy the production adapter first:','  PokeI($E1C01000,NpcGpuProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n  ; Destroy the production adapter first:',1)
s+='''
Procedure.i Main(services.i)
 Define report.i,i.i,n.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=LineStreamDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 PokeI($E1C01188,NpcGpuMemory())
 n=0 : For i=1 To #ANVIL_VK_MAX_BUFFERS : If avkBufLive[i]<>0 : n=n+1 : EndIf : Next : PokeI($E1C01190,n)
 n=0 : For i=1 To #ANVIL_VK_MAX_PIPELINES : If avkPipeLive[i]<>0 : n=n+1 : EndIf : Next : PokeI($E1C01198,n)
 n=0 : For i=1 To #ANVIL_VK_MAX_LAYOUTS : If avkLayLive[i]<>0 : n=n+1 : EndIf : Next : PokeI($E1C011A0,n)
 If PeekL($E1C00004)<>0 : ProcedureReturn 1000+PeekL($E1C00004) : EndIf
 ProcedureReturn PeekI($E1C01000)
EndProcedure
'''
(d/'proof.pi4').write_text('EnableFloatingPoint\n'+s,encoding='utf8')
env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW,env=env)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1600:]);assert q.returncode==0
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2))

i=json.loads((d/'identity.json').read_text());names=['Anvil/Graphics/Vulkan/neon_vk_port.pbi','Anvil/Graphics/Vulkan/neon_vk_chrome.pbi','Anvil/Graphics/Vulkan/neon_vk_line_stream.pbi','Anvil/Graphics/Vulkan/neon_vk_outline.pbi','Anvil/Graphics/neon_frontend.pbi','Anvil/Math/float32.pbi','RaspberryPi4/Tests/neon_port_capacity_gpu_proof.pbi','RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4'];i['source_hashes']={str(r/n):hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names};(d/'identity.json').write_text(json.dumps(i,indent=2))
