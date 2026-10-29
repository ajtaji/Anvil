#!/usr/bin/env python3
"""Build physical indexed-outline ownership, capacity and refusal proofs; never boots them."""
from pathlib import Path
import os,subprocess,argparse,json,hashlib,sys,re
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--compiler',required=True)
ap.add_argument('--case',choices=['smoke','mutable','full','quota','atomic','combined-vertices','heap-refusal','pipeline-refusal'],required=True)
ap.add_argument('--mutate-closure',action='store_true',help='Build an intentionally overwritten closing edge; does not run it. Expected mutable-probe return739.')
ap.add_argument('--without-native-fan',action='store_true',help='Withhold only native fan capability in a private backend; exercises the shared indexed triangle-list fill fallback.')
a=ap.parse_args()
if a.mutate_closure and a.case!='mutable': ap.error('--mutate-closure requires --case mutable')
if a.without_native_fan and a.case!='combined-vertices': ap.error('--without-native-fan requires --case combined-vertices')
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
name={'heap-refusal':'full','pipeline-refusal':'pipeline_refusal','combined-vertices':'combined_vertices'}.get(a.case,a.case)
helper=(r/('RaspberryPi4/Tests/neon_outline_'+name+'_proof.pbi')).read_text(encoding='utf8')
heap_bytes=0x01B18000 if a.case=='combined-vertices' else (26 if a.case in ('full','quota','atomic') else 20)*1048576
assert 0x063e8000+heap_bytes-1<=0x07efffff
s=(r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8')
s=s.replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1).replace('#NW_WINDOW_BYTES      = $00C00000','#NW_WINDOW_BYTES      = $01400000').replace('#NW_MAP_SPAN          = $00FE8000','#NW_MAP_SPAN          = $017E8000')
s=s.replace('$01400000','$'+format(heap_bytes,'08X')).replace('$017E8000','$'+format(0x3E8000+heap_bytes,'08X'))
stack=0x4f00000
if a.without_native_fan and a.case=='combined-vertices':
 # The full outline+text fallback stores an additional 12 bytes per point
 # in triangle indices. This diagnostic uses a separate measured RAM layout,
 # not a production heap increase or an overlap with the old 04F stack.
 heap_bytes=31*1048576;stack=0x5f00000
 s=s.replace('#NW_SURFACE           = $06000000','#NW_SURFACE           = $03000000',1)
 s=s.replace('#NW_WINDOW            = $063E8000','#NW_WINDOW            = $033E8000',1)
 s=s.replace('#NW_WINDOW_BYTES      = $01B18000','#NW_WINDOW_BYTES      = $01F00000',1)
 s=s.replace('#NW_MAP_SPAN          = $01F00000','#NW_MAP_SPAN          = $022E8000',1)
 assert 0x033e8000+heap_bytes<=stack-1048576
if a.without_native_fan:
 backend=(r/'RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4').read_text(encoding='utf8')
 needle=' | #ANVIL_VK_CAP_TRIANGLE_FAN';assert backend.count(needle)==1
 (d/'masked_backend.pi4').write_text(backend.replace(needle,'',1),encoding='utf8')
 needle='RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4';assert s.count(needle)==1
 s=s.replace(needle,(d/'masked_backend.pi4').as_posix(),1)
at=s.index('Procedure.i Main()');s=s[:at]+helper+'\n'+s[at:];s=s.replace('Procedure.i Main()','Procedure.i LineStreamDiagnosticMain()',1)
s=s.replace('  ; Destroy the production adapter first:','  PokeI($E1C01000,streamProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n  ; Destroy the production adapter first:',1)
if a.without_native_fan and a.case=='combined-vertices':
 needle='  PokeI($E1C01000,streamProof('
 s=s.replace(needle,'  PokeI($E1C016C0,#NW_SURFACE) : PokeI($E1C016C8,#NW_WINDOW) : PokeI($E1C016D0,#NW_WINDOW_BYTES)\n  PokeI($E1C016D8,$05F00000) : PokeI($E1C016E0,avkBackendCaps() & #ANVIL_VK_CAP_TRIANGLE_FAN)\n'+needle,1)
s+='''
Procedure.i Main(services.i)
 Define report.i,i.i,n.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=LineStreamDiagnosticMain()
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
if a.case=='pipeline-refusal':
 pipeline=(r/'Anvil/Graphics/Vulkan/vk_pipeline.pbi').read_text(encoding='utf8')
 needle='#ANVIL_VK_MAX_PIPELINES = 5';assert pipeline.count(needle)==1
 (d/'limited_pipeline.pbi').write_text(pipeline.replace(needle,'#ANVIL_VK_MAX_PIPELINES = 4',1),encoding='utf8')
 api=(r/'Anvil/Graphics/Vulkan/vk_api.pbi').read_text(encoding='utf8')
 needle='Anvil/Graphics/Vulkan/vk_pipeline.pbi';assert api.count(needle)==1
 (d/'limited_api.pbi').write_text(api.replace(needle,(d/'limited_pipeline.pbi').as_posix()),encoding='utf8')
 needle='Anvil/Graphics/Vulkan/vk_api.pbi';assert s.count(needle)==1
 s=s.replace(needle,(d/'limited_api.pbi').as_posix())
if a.mutate_closure:
 outline=(r/'Anvil/Graphics/Vulkan/neon_vk_outline.pbi').read_text(encoding='utf8')
 for needle,changed in [('nvcOutlineMapped + nvcOutlineClosingBase + nvcOutlineClosingsUsed * 24','nvcOutlineMapped + nvcOutlineClosingBase'),('nvcOutlineClosingBase / 4 + nvcOutlineClosingsUsed * 6','nvcOutlineClosingBase / 4')]:
  assert outline.count(needle)==1;outline=outline.replace(needle,changed,1)
 (d/'mutant_outline.pbi').write_text(outline,encoding='utf8')
 chrome=(r/'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi').read_text(encoding='utf8')
 needle='Anvil/Graphics/Vulkan/neon_vk_outline.pbi';assert chrome.count(needle)==1
 (d/'mutant_chrome.pi4').write_text(chrome.replace(needle,(d/'mutant_outline.pbi').as_posix()),encoding='utf8')
 needle='Anvil/Graphics/Vulkan/neon_vk_chrome.pbi';assert s.count(needle)==1
 s=s.replace(needle,(d/'mutant_chrome.pi4').as_posix())
(d/'proof.pi4').write_text(s,encoding='utf8')
env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr',hex(stack),'--entry-returns','--wants-services','-o',str(d/'proof.img')],capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW,env=env)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1600:]);assert q.returncode==0
if a.without_native_fan and a.case=='combined-vertices':
 ranges=re.findall(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',q.stdout+q.stderr);assert len(ranges)==1
 assert 0x1000000<=int(ranges[0][0],16)<=int(ranges[0][1],16)<0x03000000
 assert '#NW_MAP_SPAN          = $022E8000' in s and '#NW_WINDOW_BYTES      = $01F00000' in s
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),without_native_fan=a.without_native_fan,stack=hex(stack),heap_bytes=heap_bytes),indent=2))
