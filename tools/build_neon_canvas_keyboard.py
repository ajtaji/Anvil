"""Build native canvas UI and physical display qualification in returning payload-owned RAM."""
from pathlib import Path
import os,subprocess,json,hashlib,sys,argparse,re
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 name='RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4'
 original=(r/name).read_bytes();s=original.decode('utf-8-sig')
 for before,after in [('#NW_ARENA             = $0A000000','#NW_ARENA             = $05000000'),('#NW_SURFACE           = $06000000','#NW_SURFACE           = $03000000'),('#NW_WINDOW            = $063E8000','#NW_WINDOW            = $033E8000'),('#NW_BANNER0           = $07000000','#NW_BANNER0           = $04000000'),('#NW_BANNER90          = $07060000','#NW_BANNER90          = $04060000'),('#NW_BANNER270         = $07100000','#NW_BANNER270         = $04100000'),('#NW_BANNER_CHANGED    = $071A0000','#NW_BANNER_CHANGED    = $041A0000'),('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 20')]:
  assert s.count(before)==1,before;s=s.replace(before,after)
 s=s.replace('#NW_WINDOW_BYTES      = $00C00000','#NW_WINDOW_BYTES      = $01000000').replace('#NW_MAP_SPAN          = $00FE8000','#NW_MAP_SPAN          = $013E8000')
 s='#ANVIL_VULKAN_BACKEND=1\nXIncludeFile "RaspberryPi4/Monitor/anvil_boot_ttf.pi4"\n'+s
 inc='XIncludeFile "RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4"';assert s.count(inc)==1
 s=s.replace(inc,inc+'\nXIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"')
 s=s.replace('  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 : adapterDraws = 128 : adapterQuads = 512 : EndIf','  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 Or #NW_PROOF_MODE = 20 : adapterDraws = 128 : adapterQuads = 512 : EndIf')
 anchor='Procedure.i Main()';assert s.count(anchor)==1
 s=s.replace(anchor,'XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_canvas_keyboard.pbi"\nProcedure.i SceneDiagnosticMain()')
 anchor='  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures';assert s.count(anchor)==1
 s=s.replace(anchor,'  If #NW_PROOF_MODE = 20\n    rc=NcdFrame(dev,renderPass,framebuffer,imageBase,imagePitch)\n    nwPut(#NW_S_SCENE_RC,rc)\n  ElseIf #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures')
 anchor='  ProcedureReturn nwReturn(#NW_OK)\nEndProcedure';assert s.count(anchor)==1
 s=s.replace(anchor,'  If #NW_PROOF_MODE=20 And nwGet(#NW_S_SCENE_RC)<>0 : ProcedureReturn nwReturn(#NW_ERR_SCENE) : EndIf\n'+anchor)
 anchor='  nwPut(#NW_S_STEP, 8)\n  NeonVkChromeDestroy()';assert s.count(anchor)==1
 s=s.replace(anchor,'  nwPut(#NW_S_STEP, 8)\n  rc=NeonVkChromeDestroyChecked()\n  If rc<>0 : ProcedureReturn nwReturn(#NW_ERR_ADAPTER) : EndIf')
 s+='''
Procedure.i Main(services.i)
  Protected report.i,i.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$4E434431) : PokeI($E1C00008,2)
  NcdClear[3]=$3F800000
  report=SceneDiagnosticMain()
  If report=0 : ProcedureReturn 199 : EndIf
  PokeI($E1C00020,PeekL(report+4))
  PokeI($E1C00028,AnvilVkFaultCode()) : PokeI($E1C00030,AnvilVkFaultCount())
  If PeekL(report+4)<>0 : ProcedureReturn PeekL(report+4) : EndIf
  ProcedureReturn NcdFailure
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
 inputs['tools/neon_canvas_keyboard_cases.json']=hashlib.sha256((r/'tools/neon_canvas_keyboard_cases.json').read_bytes()).hexdigest()
 (d/'proof.pi4').write_text(s,encoding='utf8',newline='\n')
 compiler=resolve_compiler(a.compiler)
 q=subprocess.run([str(compiler),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=200,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-2000:]);assert q.returncode==0
 assert inputs=={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in inputs}
 ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges.pop('heap')
 ranges.update(report=['0xe1c00000','0xe1c03fff'],surface=['0x03000000','0x033e7fff'],gpu_window=['0x033e8000','0x043e7fff'],neon_arena=['0x05000000','0x05ffffff'])
 items=[(n,*(int(v,16) for v in pair)) for n,pair in ranges.items()]
 for i,(n,first,last) in enumerate(items):
  assert first<=last,n
  for other,of,ol in items[i+1:]:assert last<of or ol<first,n+' overlaps '+other
 p=d/'proof.img.pmf'
 (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),scope='Existing native widget scene, fixed canvas, linear final pass and physical DSI DMA. Private heap16MiB matches resident heap size; no product heap change. No input or CRT.',executed=False),indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
