"""Build direct native font Vulkan qualification in returning payload-owned RAM."""
from pathlib import Path
import os,subprocess,json,hashlib,sys,argparse,re
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--carets',action='store_true');a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 name='RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4'
 original=(r/name).read_bytes();s=original.decode('utf-8-sig')
 for before,after in [('#NW_ARENA             = $0A000000','#NW_ARENA             = $05000000'),('#NW_SURFACE           = $06000000','#NW_SURFACE           = $03000000'),('#NW_WINDOW            = $063E8000','#NW_WINDOW            = $033E8000'),('#NW_BANNER0           = $07000000','#NW_BANNER0           = $04000000'),('#NW_BANNER90          = $07060000','#NW_BANNER90          = $04060000'),('#NW_BANNER270         = $07100000','#NW_BANNER270         = $04100000'),('#NW_BANNER_CHANGED    = $071A0000','#NW_BANNER_CHANGED    = $041A0000'),('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 17')]:
  assert s.count(before)==1,before;s=s.replace(before,after)
 s='#ANVIL_VULKAN_BACKEND=1\nXIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "RaspberryPi4/Monitor/anvil_boot_ttf.pi4"\n'+s
 inc='XIncludeFile "RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4"';assert s.count(inc)==1
 s=s.replace(inc,inc+'\nXIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"')
 s=s.replace('  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 : adapterDraws = 128 : adapterQuads = 512 : EndIf','  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 Or #NW_PROOF_MODE = 17 : adapterDraws = 128 : adapterQuads = 512 : EndIf')
 anchor='  ; The shipped adapter allocates all resident resources here';assert s.count(anchor)==1
 s=s.replace(anchor,'''  If AnvilTrueTypeSlotLoad(0,?anvilBootTtf,#ANVIL_BOOT_TTF_BYTES)=0 Or AnvilTrueTypeSlotSelect(0)=0
    vkDestroyFramebuffer(dev,framebuffer,0) : vkDestroyRenderPass(dev,renderPass,0)
    vkDestroyImageView(dev,view,0) : vkDestroyImage(dev,image,0) : vkFreeMemory(dev,memory,0)
    vkDestroyCommandPool(dev,pool,0) : vkDestroyDevice(dev,0) : vkDestroyInstance(inst,0) : NeonShutdown()
    ProcedureReturn nwReturn(#NW_ERR_ADAPTER)
  EndIf
'''+anchor)
 anchor='Procedure.i Main()';assert s.count(anchor)==1
 s=s.replace(anchor,'XIncludeFile "RaspberryPi4/Tests/Vulkan/'+('neon_font_caret.pbi' if a.carets else 'neon_font_snap.pbi')+'"\nProcedure.i SceneDiagnosticMain()')
 anchor='  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures';assert s.count(anchor)==1
 s=s.replace(anchor,'  If #NW_PROOF_MODE = 17\n    rc=NfpFrame(imageBase,imagePitch,framebuffer)\n    nwPut(#NW_S_SCENE_RC,rc)\n  ElseIf #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures')
 anchor='  ProcedureReturn nwReturn(#NW_OK)\nEndProcedure';assert s.count(anchor)==1
 s=s.replace(anchor,'  If #NW_PROOF_MODE=17 And nwGet(#NW_S_SCENE_RC)<>0 : ProcedureReturn nwReturn(#NW_ERR_SCENE) : EndIf\n'+anchor)
 if a.carets:
  anchor='  NeonStateReset()';assert s.count(anchor)==1
  s=s.replace(anchor,anchor+'\n  rc=NfpNativeTextSuccess(#NW_SURFACE,#NW_SURFACE_PITCH)\n  If rc<>0 : NeonShutdown() : ProcedureReturn nwReturn(#NW_ERR_SCENE) : EndIf')
 s+='''
Procedure.i Main(services.i)
  Protected report.i,i.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  report=SceneDiagnosticMain()
  If report=0 : ProcedureReturn 199 : EndIf
  NfpRetired(report)
  For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
  If PeekL($E1C00004)<>0 : ProcedureReturn PeekL($E1C00004) : EndIf
  ProcedureReturn nfpFailure
EndProcedure
'''
 pending=[(s,None)];inputs={};missing=[]
 while pending:
  text,owner=pending.pop(0)
  for spelling in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',text):
   p=r/spelling.replace('\\','/')
   if not p.is_file() and owner:p=(r/owner).parent/spelling
   p=p.resolve();assert p.is_relative_to(r)
   n=p.relative_to(r).as_posix()
   if n in inputs or n in missing:continue
   assert len(inputs)+len(missing)<256
   if not p.is_file():missing.append(n);continue
   blob=p.read_bytes();inputs[n]=hashlib.sha256(blob).hexdigest();pending.append((blob.decode('utf-8-sig'),n))
 assert not missing,missing
 inputs[name]=hashlib.sha256(original).hexdigest()
 for n in (['tools/neon_font_caret_expected.json','tools/neon_font_caret_proportional.json'] if a.carets else ['tools/neon_font_snap_cases.json']):inputs[n]=hashlib.sha256((r/n).read_bytes()).hexdigest()
 (d/'proof.pi4').write_text(s,encoding='utf8',newline='\n')
 compiler=resolve_compiler(a.compiler)
 q=subprocess.run([str(compiler),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-2000:]);assert q.returncode==0
 assert inputs=={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in inputs}
 ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges.pop('heap')
 ranges.update(report=['0xe1c00000','0xe1c03fff'],pixels=['0xe2400000','0xe245a01f'],surface=['0x03000000','0x033e7fff'],gpu_window=['0x033e8000','0x03fe7fff'],banners=['0x04000000','0x041fdbff'],neon_arena=['0x05000000','0x05ffffff'])
 if a.carets:
  ranges['native_text_pixels']=['0xe2500000','0xe251001f']
  ranges['native_text_workload']=['0xe2520000','0xe2520fff']
  ranges['native_text_tables']=['0xe2530000','0xe2532fff']
 items=[(n,*(int(v,16) for v in pair)) for n,pair in ranges.items()]
 for i,(n,first,last) in enumerate(items):
  assert first<=last,n
  for other,of,ol in items[i+1:]:assert last<of or ol<first,n+' overlaps '+other
 p=d/'proof.img.pmf'
 (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),carets=a.carets,scope='Actual native Vulkan font and optional caret query qualification; CPU copies GPU attachment crops; no input actuation',executed=False),indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
