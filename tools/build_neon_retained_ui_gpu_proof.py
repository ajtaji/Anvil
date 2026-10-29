from pathlib import Path
import os,subprocess,json,hashlib,sys
import argparse,re
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description='Compile retained UI against actual Pi4 Vulkan; never boot or emulate it.')
ap.add_argument('--truetype',action='store_true',help='Mixed retained TrueType faces, sizes and Unicode.')
ap.add_argument('--font-setup-only',action='store_true',help='Isolate font registry validation; no glyph warming or frame rendering.')
ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args();r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
assert not a.font_setup_only or a.truetype,'font setup requires --truetype'
s=(r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf-8-sig')
s='EnableFloatingPoint\n#ANVIL_VULKAN_BACKEND=1\n#NRG_FONT_KIND='+str(int(a.truetype))+'\n'+s
s='#NRG_FONT_SETUP_ONLY='+str(int(a.font_setup_only))+'\n'+s
if a.truetype:
    s='XIncludeFile "RaspberryPi4/Monitor/anvil_boot_ttf.pi4"\nXIncludeFile "RaspberryPi4/Tests/Vulkan/neon_retained_probe_font.pbi"\n'+s
assert s.count('#NW_PROOF_MODE        = 0')==1
s=s.replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 16')

s=s.replace('  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 : adapterDraws = 128 : adapterQuads = 512 : EndIf','  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 Or #NW_PROOF_MODE = 16 : adapterDraws = 128 : adapterQuads = 512 : EndIf')
inc='XIncludeFile "RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4"';assert s.count(inc)==1;s=s.replace(inc,inc+'\nXIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"')
if a.truetype:
    anchor='  ; The shipped adapter allocates all resident resources here'
    assert s.count(anchor)==1
    load='  If AnvilTrueTypeSlotLoad(0,?anvilBootTtf,#ANVIL_BOOT_TTF_BYTES)=0 Or AnvilTrueTypeSlotLoad(1,?nrgProbeFont,#NRG_PROBE_FONT_BYTES)=0 Or AnvilTrueTypeSlotSelect(0)=0\n    vkDestroyFramebuffer(dev,framebuffer,0) : vkDestroyRenderPass(dev,renderPass,0)\n    vkDestroyImageView(dev,view,0) : vkDestroyImage(dev,image,0) : vkFreeMemory(dev,memory,0)\n    vkDestroyCommandPool(dev,pool,0) : vkDestroyDevice(dev,0) : vkDestroyInstance(inst,0) : NeonShutdown()\n    ProcedureReturn nwReturn(#NW_ERR_ADAPTER)\n  EndIf\n'
    s=s.replace(anchor,load+anchor)
anchor='Procedure.i Main()';assert s.count(anchor)==1
s=s.replace(anchor,'XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_retained_ui_gpu_proof.pbi"\nProcedure.i SceneDiagnosticMain()')
anchor='  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures'
assert s.count(anchor)==1
s=s.replace(anchor,'  If #NW_PROOF_MODE = 16\n    rc=NrgFrame(imageBase,imagePitch,framebuffer)\n    nwPut(#NW_S_SCENE_RC,rc)\n  ElseIf #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures')
assert s.count('  ProcedureReturn nwReturn(#NW_OK)\nEndProcedure')==1
s=s.replace('  ProcedureReturn nwReturn(#NW_OK)\nEndProcedure','  If #NW_PROOF_MODE = 16 And nwGet(#NW_S_SCENE_RC)<>0 : ProcedureReturn nwReturn(#NW_ERR_SCENE) : EndIf\n  ProcedureReturn nwReturn(#NW_OK)\nEndProcedure')
s+='\nProcedure.i Main(services.i)\n Define report.i,i.i\n For i=0 To 4095 : PokeA($E1C00000+i,0) : Next\n report=SceneDiagnosticMain()\n If report=0 : ProcedureReturn 199 : EndIf\n NrgRetired(report)\n For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next\n ProcedureReturn PeekL($E1C00004)\nEndProcedure\n'
def literal_inputs(source):
    # Follow only paths explicitly named by this composition. No filesystem
    # enumeration. Resolve local includes against their declaring source.
    pending=[(source,None)];seen={};missing=[]
    while pending:
        text,owner=pending.pop(0)
        for spelling in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^\"]+)"',text):
            spelling=spelling.replace('\\','/')
            path=r/spelling
            if not path.is_file() and owner is not None:path=(r/owner).parent/spelling
            path=path.resolve();assert path.is_relative_to(r),'include leaves source root'
            name=path.relative_to(r).as_posix()
            if name in seen or name in missing:continue
            assert len(seen)+len(missing)<256,'literal dependency bound'
            if not path.is_file():missing.append(name);continue
            blob=path.read_bytes();seen[name]=hashlib.sha256(blob).hexdigest()
            pending.append((blob.decode('utf-8-sig'),name))
    return seen,missing

(d/'proof.pi4').write_text(s,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(r)
inputs_before,missing=literal_inputs(s)

q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],capture_output=True,text=True,encoding='utf8',env=env,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-2000:]);assert q.returncode==0
sys.path.insert(0,str(r/'tools'));from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
ranges=check_linked_layout(state_proof_layout('pi4'),q.stdout+q.stderr)
# The generic CPU proof's hypothetical heap is not used here. Record the
# actual disjoint surface/window/capture/arena ownership of this GPU program.
ranges.pop('heap')
ranges.update(surface=['0x06000000','0x063e7fff'],gpu_window=['0x063e8000','0x06fe7fff'],capture0=['0x07000000','0x073e7fff'],capture1=['0x07400000','0x077e7fff'],neon_arena=['0x0a000000','0x0affffff'])
items=[(name,*(int(v,16) for v in pair)) for name,pair in ranges.items()]
for i,(name,first,last) in enumerate(items):
    assert first<=last,name
    for other,of,ol in items[i+1:]:assert last<of or ol<first,name+' overlaps '+other

inputs_after,missing_after=literal_inputs(s)
assert inputs_before==inputs_after and missing==missing_after,'source changed during compilation'
inputs_after['RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4']=hashlib.sha256((r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_bytes()).hexdigest()
p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(variant='font-setup-only' if a.font_setup_only else ('truetype' if a.truetype else 'bitmap'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs_after,literal_missing=missing,dependency_scope="Literal include graph; no directory enumeration",executed=False),indent=2),encoding='utf8')
