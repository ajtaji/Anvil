#!/usr/bin/env python3
"""Build a physical Pi 4 triangle-fan/fallback proof; never executes it.

Eight captures at four rotations, tight-buffer refusal and clean teardown.
Fault flags change only private diagnostic copies. Omitted restoration must
be rejected by the complete-pixel checker, even though the payload returns.
"""
from pathlib import Path
import subprocess,os,json,hashlib,argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--compiler')
group=ap.add_mutually_exclusive_group()
group.add_argument('--mask-fan-capability',action='store_true')
group.add_argument('--omit-restoration',action='store_true')
args=ap.parse_args()
variant='fallback' if args.mask_fan_capability else 'no-restore' if args.omit_restoration else 'candidate'
r=Path(__file__).resolve().parents[1]
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
helper='''Procedure fanProofCapture(base.i,pitch.i,frame.i)
 Define x.i,y.i,px.i,py.i
 For y=0 To 63
  For x=0 To 63
   If nvcRotation=90 : px=nvcLogicalH-1-y : py=x
   ElseIf nvcRotation=180 : px=nvcLogicalW-1-x : py=nvcLogicalH-1-y
   ElseIf nvcRotation=270 : px=y : py=nvcLogicalW-1-x
   Else : px=x : py=y : EndIf
   PokeL($E2400000+frame*16384+(y*64+x)*4,PeekL(base+py*pitch+px*4))
  Next
 Next
EndProcedure
Procedure.i fanProofLiveMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure
Procedure.i fanTopologyProof(phys.i,dev.i,queue.i,pool.i,renderPass.i,framebuffer.i,base.i,pitch.i)
 Define ia.VkPipelineInputAssemblyStateCreateInfo
 Define mode.i,turn.i,path.i,rotation.i,lw.i,lh.i,quads.i,rc.i,verts.i,draws.i,freeRows.i,i.i
 mode=Bool((avkBackendCaps() & #ANVIL_VK_CAP_TRIANGLE_FAN)<>0)
 PokeI($E1C01008,mode)
 ia__F__sType=#VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO : ia__F__topology=#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN
 rc=avkPipeCheckInputAssembly(@ia) : PokeI($E1C01030,rc)
 If (mode=1 And rc<>0) Or (mode=0 And rc<>#ANVIL_VK_ERR_UNSUPPORTED) : ProcedureReturn 241 : EndIf
 NeonVkChromeDestroy()
 SafetyWatchdogStart(15)
 For turn=0 To 3
  rotation=turn*90 : lw=800 : lh=1280
  If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  For path=0 To 1
   SafetyWatchdogPet()
   quads=64
   If path=1 : quads=1 : EndIf
   rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,renderPass,framebuffer,800,1280,4,quads)
   If rc<>0 : ProcedureReturn 242 : EndIf
   If Bool(nvcFanPipeline<>0)<>mode : ProcedureReturn 243 : EndIf
   If mode<>0
    If AnvilVkPipelineTopology(avkPipeSlot(nvcFanPipeline))<>#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN : ProcedureReturn 244 : EndIf
    PokeI($E1C01048,avkV3dPrimitiveMode(avkPipeSlot(nvcFanPipeline)))
   EndIf
   rc=NeonVkChromeRebind(framebuffer,lw,lh,800,1280,pitch,rotation)
   If rc=0 : rc=NeonVkChromeBegin(@nwClear[0]) : EndIf
   If rc<>0 : ProcedureReturn 245 : EndIf
   If path=0 : rc=Neon_Box(0,0,4,4,Neon_RGBA(255,0,0,255)) : EndIf
   If rc=0 : rc=NeonFanBegin() : EndIf
   NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(16,28) : NeonFanPoint(4,28)
   If rc=0 : rc=NeonFanEnd(Neon_RGBA(0,255,0,255)) : EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 246 : EndIf
   If path=0
    rc=NeonVkChromeBoxBatchBegin()
    If rc=0 : rc=Neon_Box(32,32,8,8,Neon_RGBA(0,0,255,255)) : EndIf
    If rc=0 : rc=Neon_Box(48,32,8,8,Neon_RGBA(0,0,255,255)) : EndIf
    If rc=0 : rc=NeonVkChromeBoxBatchEnd() : EndIf
    If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 247 : EndIf
    PokeI($E1C01018,nvcVertices)
    If nvcVertices<>23 Or nvcDrawCount<>3 : NeonVkChromeAbort() : ProcedureReturn 248 : EndIf
   Else
    verts=nvcVertices : draws=nvcDrawCount : freeRows=avkRecordedDrawFreeCount
    For i=0 To 15 : PokeA(nvcMapped+verts*24+i,$A5) : Next
    rc=NeonFanBegin()
    NeonFanPoint(4,4) : NeonFanPoint(28,4) : NeonFanPoint(28,28) : NeonFanPoint(16,28) : NeonFanPoint(4,28)
    rc=NeonFanEnd(Neon_RGBA(255,0,0,255))
    If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>verts Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>freeRows : NeonVkChromeAbort() : ProcedureReturn 249 : EndIf
    For i=0 To 15
     If PeekA(nvcMapped+verts*24+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 250 : EndIf
    Next
    PokeI($E1C01020,verts) : PokeI($E1C01028,quads*6)
    If verts<>5 Or draws<>1 : NeonVkChromeAbort() : ProcedureReturn 251 : EndIf
   EndIf
   rc=NeonVkChromeEnd()
   If rc<>0 : ProcedureReturn 252 : EndIf
   If NeonVkChromePresentConsume()<>1 : ProcedureReturn 253 : EndIf
   fanProofCapture(base,pitch,turn*2+path)
   PokeI($E1C01010,turn*2+path+1)
   NeonVkChromeDestroy()
   If nvcDevice<>0 Or nvcFanPipeline<>0 Or fanProofLiveMemory()<>1 : ProcedureReturn 254 : EndIf
  Next
 Next
 ProcedureReturn 0
EndProcedure
'''.replace('__F__',chr(92))
(d/'helper.pi4').write_text(helper,encoding='utf8')
s=(r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8').replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1)
if variant=='fallback':
 b=(r/'RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4').read_text(encoding='utf8');assert b.count(' | #ANVIL_VK_CAP_TRIANGLE_FAN')==1;b=b.replace(' | #ANVIL_VK_CAP_TRIANGLE_FAN','',1);f=d/'masked-backend.pi4';f.write_text(b,encoding='utf8');s=s.replace('RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4',f.resolve().as_posix(),1)
if variant=='no-restore':
 adapter=(r/'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi').read_text(encoding='utf8')
 needle='      vkCmdBindPipeline(nvcCommand, #VK_PIPELINE_BIND_POINT_GRAPHICS, nvcPipeline)'
 assert adapter.count(needle)==1
 adapter=adapter.replace(needle,'      ; Diagnostic control: deliberately omit topology restoration.',1)
 f=d/'no-restore-adapter.pi4';f.write_text(adapter,encoding='utf8')
 s=s.replace('Anvil/Graphics/Vulkan/neon_vk_chrome.pbi',f.resolve().as_posix(),1)
at=s.index('Procedure.i Main()');s=s[:at]+helper+'\n'+s[at:];s=s.replace('Procedure.i Main()','Procedure.i FanDiagnosticMain()',1)
s=s.replace('  ; Destroy the production adapter first:','  PokeI($E1C01000,fanTopologyProof(phys,dev,queue,pool,renderPass,framebuffer,imageBase,imagePitch))\n  ; Destroy the production adapter first:',1)
s+='''
Procedure.i Main(services.i)
 Define report.i,i.i,live.i,pipes.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=FanDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 PokeI($E1C01038,fanProofLiveMemory())
 For i=1 To #ANVIL_VK_MAX_PIPELINES : If avkPipeLive[i]<>0 : pipes=pipes+1 : EndIf : Next
 PokeI($E1C01040,pipes)
 If PeekL($E1C00004)<>0 : ProcedureReturn 1000+PeekL($E1C00004) : EndIf
 ProcedureReturn PeekI($E1C01000)
EndProcedure
''';(d/'proof.pi4').write_text(s,encoding='utf8')
exe=Path(resolve_compiler(args.compiler));env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(exe),'--compile',str((d/'proof.pi4').resolve()),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str((d/'proof.img').resolve())],capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW,env=env);(d/'compile.txt').write_text(q.stdout+q.stderr);print((q.stdout+q.stderr)[-950:]);assert q.returncode==0
(d/'identity.json').write_text(json.dumps(dict(bytes=(d/'proof.img.pmf').stat().st_size,sha256=hashlib.sha256((d/'proof.img.pmf').read_bytes()).hexdigest()),indent=2))
