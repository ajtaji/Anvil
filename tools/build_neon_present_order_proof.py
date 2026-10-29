#!/usr/bin/env python3
"""Compile exact console presentation/teardown bodies with controlled providers.

The full-pump tail is exact, while drawing and failover are explicit spies.
No GPU, DMA or renderer is linked or executed. Snapshot selection is explicit.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
from neon_vk_chrome_acceptance_check import procedure_body

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True)
 ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True);ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--snapshot-root',type=Path,help='Explicit old source tree for a negative reproduction; no automatic fallback.')
 a=ap.parse_args();r=Path(__file__).resolve().parents[1];base=a.snapshot_root.resolve() if a.snapshot_root else r
 d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
 chrome=(base/'Anvil/Graphics/Vulkan/neon_vk_chrome.pi4').read_text(encoding='utf8')
 console=(base/'RaspberryPi4/Board/vulkan_console.pi4').read_text(encoding='utf8')
 names=['nvcFail','NeonVkChromePresentPending','NeonVkChromePresentConsume']
 bodies=[procedure_body(chrome,n) for n in names]
 new='Procedure.i NeonVkChromePresentValidate()' in chrome
 if new:bodies.append(procedure_body(chrome,'NeonVkChromePresentValidate'))
 bodies.extend(procedure_body(console,n) for n in ['avcPumpBannerOnly','VulkanConsoleDestroy'])
 if new:bodies.append(procedure_body(console,'avcPresentRenderedFrame'))
 pump=procedure_body(console,'VulkanConsolePump');start=pump.index('  rc = NeonVkChromeError()');stop=pump.index('  avcFramePresented = 1',start)
 tail=pump[start:stop]
 bodies.append('Procedure.i CpFullTail()\n Define rc.i,endRc.i,st1.i,st2.i\n'+tail+' ProcedureReturn 1\nEndProcedure')
 production='\n\n'.join(bodies)
 calls=set(re.findall(r'\b(\w+)\s*\(',production))
 input_procedures=set(re.findall(r'^Procedure(?:\.[A-Za-z])?\s+(\w+)\s*\(',chrome+'\n'+console,re.M))
 globals_=sorted((set(re.findall(r'\b(?:nvc|avc)[A-Z]\w*\b',production))-calls-input_procedures)|{'avcDisplayCopyPending','nvcFramebuffer','nvcTargetGeneration'})
 arrays=set(re.findall(r'\b((?:nvc|avc)\w+)\[',production));assert arrays=={'avcClear','avcStatBanner'},arrays
 decl='\n'.join('Global '+n+'.i' for n in globals_ if n not in arrays)+'\nGlobal *gV3dWaitIdle\nGlobal Dim avcClear.l[4]\nGlobal Dim avcStatBanner.i[3]\n'
 const='#VK_SUCCESS=0\n'
 for source,names in [(chrome,['NEON_VK_CHROME_ERR_STATE','NEON_VK_CHROME_OK']),(console,['AVC_ERR_CHROME','AVC_ERR_PRESENT'])]:
  for n in names:
   values=re.findall(r'^#'+n+r'\s*=\s*([^;\r\n]+)',source,re.M);assert len(values)==1,n
   const+='#'+n+'='+values[0].strip()+'\n'
 decl+='Global Dim gBannerClockText.a[1024]\n'
 providers='''
Procedure.i ScrFrameRestore() : ProcedureReturn 1 : EndProcedure
Procedure.i AnvilTrueTypeSlotSelected() : ProcedureReturn -1 : EndProcedure
Procedure.i NeonVkChromeWarmTrueTypeText(height.i,text.i) : ProcedureReturn 0 : EndProcedure
Procedure.i Ticks() : cpTicks=cpTicks+1 : ProcedureReturn cpTicks : EndProcedure
Procedure.i LogoHeight() : ProcedureReturn 8 : EndProcedure
Procedure avcGpuWaitIdle() : EndProcedure
Procedure.i NeonVkChromeRebind(f.i,lw.i,lh.i,pw.i,ph.i,pitch.i,rotation.i)
 If f=2000 : CpEvent(10) : nvcFramebuffer=f : ProcedureReturn 0 : EndIf
 If f<>1000 : cpFault=cpFault+1 : ProcedureReturn -1 : EndIf
 CpEvent(9) : cpMainRebinds=cpMainRebinds+1
 If cpMainRebindRc=0 : nvcFramebuffer=f : EndIf
 ProcedureReturn cpMainRebindRc
EndProcedure
Procedure.i NeonVkChromeBegin(*clear) : CpEvent(11) : ProcedureReturn cpBeginRc : EndProcedure
Procedure.i avcRenderBanner() : CpEvent(12) : ProcedureReturn cpRenderRc : EndProcedure
Procedure.i NeonVkChromeError() : ProcedureReturn cpDrawRc : EndProcedure
Procedure.i NeonVkChromeEnd()
 CpEvent(13) : cpPending=1 : ProcedureReturn 0
EndProcedure
Procedure.i nvdPresentPending() : ProcedureReturn cpPending : EndProcedure
Procedure.i nvdPresentMatches(target.i,f.i)
 CpEvent(2) : cpMatches=cpMatches+1
 If target<>nvcTargetGeneration Or f<>nvcFramebuffer : cpFault=cpFault+1 : EndIf
 ProcedureReturn Bool(cpPending=1 And cpValidateOk=1)
EndProcedure
Procedure.i nvdPresentConsume(target.i,f.i)
 CpEvent(4) : cpConsumes=cpConsumes+1
 If target<>nvcTargetGeneration Or f<>nvcFramebuffer : cpFault=cpFault+1 : EndIf
 If cpConsumeOk<>0 : cpPending=0 : EndIf
 ProcedureReturn cpConsumeOk
EndProcedure
Procedure.i DmaReady() : ProcedureReturn cpReady : EndProcedure
Procedure.i DmaQuarantined() : CpEvent(14) : ProcedureReturn cpQuarantine : EndProcedure
Procedure.i DmaQuiescent() : CpEvent(15) : ProcedureReturn cpQuiet : EndProcedure
Procedure CpCopySeen()
 cpCopyCalls=cpCopyCalls+1 : cpCopySawPending=cpPending : cpCopySawTarget=nvcFramebuffer
EndProcedure
Procedure.i avcCopyToDisplay() : CpEvent(3) : CpCopySeen() : ProcedureReturn cpCopyOk : EndProcedure
Procedure.i avcCopyBannerToDisplay(src.i,pitch.i,band.i)
 If band<>0
  CpEvent(5) : If src<>3000 Or pitch<>256 : cpFault=cpFault+1 : EndIf
 Else
  CpEvent(6) : If src<>4000 Or pitch<>256 : cpFault=cpFault+1 : EndIf
 EndIf
 CpCopySeen() : ProcedureReturn cpCopyOk
EndProcedure
Procedure.i avcFailover(reason.i)
 CpEvent(7) : cpFailovers=cpFailovers+1
 If reason<>#AVC_ERR_CHROME And reason<>#AVC_ERR_PRESENT : cpFault=cpFault+1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i vkDeviceWaitIdle(device.i) : CpEvent(16) : cpIdleCalls=cpIdleCalls+1 : ProcedureReturn 0 : EndProcedure
Procedure.i NeonVkChromeDestroyChecked() : CpEvent(17) : cpPending=0 : ProcedureReturn 0 : EndProcedure
Procedure NeonVkChromeLogoSource(a.i,b.i,c.i)
 If a<>0 Or b<>0 Or c<>0 : cpFault=cpFault+1 : EndIf
EndProcedure
Procedure avcDestroyBannerTarget() : CpEvent(18) : cpBannerReleases=cpBannerReleases+1 : EndProcedure
'''
 for name in ['Framebuffer','RenderPass','ImageView','Image','CommandPool']:
  providers+='Procedure vkDestroy'+name+'(device.i,handle.i,alloc.i)\n If handle<>0 : cpReleases=cpReleases+1 : EndIf\nEndProcedure\n'
 providers+='''
Procedure vkFreeMemory(device.i,handle.i,alloc.i) : If handle<>0 : cpReleases=cpReleases+1 : EndIf : EndProcedure
Procedure vkDestroyDevice(handle.i,alloc.i) : If handle<>0 : cpReleases=cpReleases+1 : EndIf : EndProcedure
Procedure vkDestroyInstance(handle.i,alloc.i) : If handle<>0 : cpReleases=cpReleases+1 : EndIf : EndProcedure
'''
 reset='Procedure CpReset()\n Define i.i\n'+'\n'.join(' '+n+'=0' for n in globals_ if n not in arrays)+'\n'
 reset+='''
 For i=0 To 15 : cpEvents[i]=0 : Next
 cpPending=0 : cpCopyOk=1 : cpConsumeOk=1 : cpValidateOk=1 : cpBeginRc=0 : cpRenderRc=0 : cpDrawRc=0
 cpMainRebindRc=0 : cpReady=1 : cpQuarantine=0 : cpQuiet=1 : cpCopySawPending=-1 : cpCopySawTarget=-1
 cpCopyCalls=0 : cpConsumes=0 : cpMatches=0 : cpMainRebinds=0 : cpFailovers=0 : cpBannerReleases=0
 cpIdleCalls=0 : cpReleases=0 : cpEventsUsed=0
 avcFramebuffer=1000 : avcBanFramebuffer=2000 : avcBanReady=1
 avcLogicalW=64 : avcLogicalH=64 : avcWidth=64 : avcHeight=64 : avcPitch=256
 avcBanW=64 : avcBanH=8 : avcBanPitch=256 : avcBanBase=3000 : avcImageBase=4000 : avcImagePitch=256
 nvcFramebuffer=1000 : nvcTargetGeneration=7
EndProcedure
'''
 defined=set(re.findall(r'^Procedure(?:\.[A-Za-z])?\s+(\w+)\(',production+'\n'+providers,re.M))
 assert calls-defined=={'Bool'},calls-defined
 fixture_path=r/'RaspberryPi4/Tests/neon_present_order_proof.pbi'
 fixture=fixture_path.read_text(encoding='utf8')
 assert fixture.count('; @CP_COMPOSITION@')==1
 source=const+f'#CP_REPORT=${layout["report"]:08X}\n'+fixture.replace('; @CP_COMPOSITION@',decl+providers+production+'\n'+reset)
 source+='''
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#CP_REPORT+i,0) : Next
 rc=ConsolePresentOrderProof()
 PokeI(#CP_REPORT,$43504F50) : PokeI(#CP_REPORT+8,rc)
 PokeI(#CP_REPORT+16,#PMF_CHIP) : PokeI(#CP_REPORT+24,14)
 PokeI(#CP_REPORT+32,cpFault) : PokeI(#CP_REPORT+40,1)
 PokeI(#CP_REPORT+56,$504F5043)
 ProcedureReturn rc
EndProcedure
'''
 (d/'proof.pbi').write_text(source,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(r)
 q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,
 '--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=env,
 capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
 (d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1000:],flush=True);assert q.returncode==0
 ranges=check_linked_layout(layout,q.stdout+q.stderr);image=d/'proof.img.pmf'
 (d/'identity.json').write_text(json.dumps(dict(target=a.target,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
 checked_ranges=ranges,old_snapshot=bool(a.snapshot_root),source_root=str(base),cases=14,controlled_providers=True,
 executed=False,gpu_execution=False,dma_execution=False,full_pump_scope='exact tail after drawing, not entire pump',
 source_hashes={str(base/'Anvil/Graphics/Vulkan/neon_vk_chrome.pi4'):hashlib.sha256((base/'Anvil/Graphics/Vulkan/neon_vk_chrome.pi4').read_bytes()).hexdigest(),
 str(base/'RaspberryPi4/Board/vulkan_console.pi4'):hashlib.sha256((base/'RaspberryPi4/Board/vulkan_console.pi4').read_bytes()).hexdigest()},
 fixture_source=fixture_path.relative_to(r).as_posix(),fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 body_sha256=[hashlib.sha256(b.encode()).hexdigest() for b in bodies],tail_sha256=hashlib.sha256(tail.encode()).hexdigest()),indent=2),encoding='utf8')
if __name__=='__main__':main()
