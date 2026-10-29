#!/usr/bin/env python3
"""Compile exact teardown bodies with controlled Vulkan/resource providers.

No GPU/driver or emulator is linked or executed. Case reset only initializes
independent controlled inputs, not production recovery. Live-map checks are
required before any hardware entry. Helpers below model release notifications,
not the implementation of resource-freeing APIs or GPU/device-idle behavior.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
from neon_teardown_proof_check import expected_rows

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--target',choices=['pi4','pi3','unoq','rockpi4c'],required=True);a=ap.parse_args()
r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);layout=state_proof_layout(a.target)
spec=[('Anvil/Graphics/Vulkan/neon_vk_chrome.pi4',['nvcFail','NeonVkChromeDestroyChecked','NeonVkChromeDestroy','nvcLifecycleShutdown']),('Anvil/Graphics/Vulkan/neon_vk_lifecycle.pbi',['nvlShutdown']),('RaspberryPi4/Board/vulkan_console.pi4',['VulkanConsoleDestroy'])]
bodies=[];hashes={};sources={}
for rel,names in spec:
 raw=(r/rel).read_bytes();s=raw.decode('utf-8-sig');sources[rel]=hashlib.sha256(raw).hexdigest()
 for name in names:
  matches=list(re.finditer(r'^Procedure(?:\.i)? '+name+r'\([^\n]*\n.*?^EndProcedure',s,re.M|re.S));assert len(matches)==1,name
  body=matches[0].group(0);bodies.append(body);hashes[name]=hashlib.sha256(body.encode()).hexdigest()
production='\n\n'.join(bodies)
calls=set(re.findall(r'\b(\w+)\s*\(',production))
globals_=sorted(set(re.findall(r'\b(nvc[A-Z]\w*|nvlConfigured|avc[A-Z]\w*)\b',production))-calls)
arrays=set(re.findall(r'\b(nvc\w+)\[',production))
assert arrays=={'nvcImageSpriteSets','nvcImageSpriteViews','nvcImageSpriteImages','nvcImageSpriteMemories','nvcImageSpriteWidths','nvcImageSpriteHeights','nvcImageSpriteGenerations','nvcTTIndex'}
const='''#VK_SUCCESS=0
#NEON_OK=0
#NEON_ERR_BACKEND=16
#NEON_VK_CHROME_ERR_STATE=-21202
#NVC_MULTI_SPRITE_MAX=16
#NVC_TT_INDEX_SIZE=1024
#NVC_PATH_NONE=0
'''
chrome=(r/spec[0][0]).read_text(encoding='utf8')
for name,wanted in [('NEON_VK_CHROME_ERR_STATE','-21202'),('NVC_MULTI_SPRITE_MAX','16'),('NVC_TT_INDEX_SIZE','1024'),('NVC_PATH_NONE','0')]:
 values=re.findall(r'^#'+name+r'\s*=\s*([^;\r\n]+)',chrome,re.M);assert len(values)==1 and values[0].strip()==wanted,name
decl='\n'.join('Global '+v+'.i' for v in globals_ if v not in arrays)+'\n'
decl+='\n'.join('Global Dim '+v+'.i['+('1024' if v=='nvcTTIndex' else '17')+']' for v in sorted(arrays))+'\n'
providers='''
Procedure.i ScrFrameRestore() : ProcedureReturn 1 : EndProcedure
Procedure.i DmaQuarantined() : ProcedureReturn 0 : EndProcedure
Procedure.i DmaQuiescent() : ProcedureReturn 1 : EndProcedure
Procedure.i vkDeviceWaitIdle(device.i)
 acdIdleCalls=acdIdleCalls+1
 If acdIdleCalls=1 : ProcedureReturn acdFirstRc : EndIf
 ProcedureReturn acdLaterRc
EndProcedure
Procedure.i nvdWsiRollback()
 acdRollbackCalls=acdRollbackCalls+1
 ProcedureReturn acdRollbackRc
EndProcedure
Procedure nvdPresentClear() : acdPresentClears=acdPresentClears+1 : EndProcedure
Procedure NeonDrawBackendClear() : acdDrawClears=acdDrawClears+1 : EndProcedure
Procedure.i NeonDrawBackendActive() : ProcedureReturn nvcHooksInstalled : EndProcedure
Procedure.i NeonVkChromePresentPending() : ProcedureReturn 0 : EndProcedure
Procedure NeonVkChromeLogoSource(a.i,b.i,c.i) : EndProcedure
Procedure avcDestroyBannerTarget() : acdBannerReleases=acdBannerReleases+1 : EndProcedure
Procedure vkUnmapMemory(device.i,memory.i) : acdUnmaps=acdUnmaps+1 : EndProcedure
Procedure nvcImageSpriteRelease(set.i,view.i,image.i,memory.i)
 If set<>0 Or view<>0 Or image<>0 Or memory<>0 : acdReleases=acdReleases+1 : EndIf
EndProcedure
Procedure nvcParticlePaletteRelease() : EndProcedure
Procedure nvcOutlineRelease() : EndProcedure
Procedure nvcLineStreamRelease() : EndProcedure
Procedure nvcBudgetReset() : EndProcedure
Procedure vkFreeCommandBuffers(device.i,pool.i,count.i,*cmd)
 If count>0 And PeekI(*cmd)<>0 : acdReleases=acdReleases+1 : EndIf
EndProcedure
'''
for name in ['Buffer','Pipeline','PipelineLayout','DescriptorPool','DescriptorSetLayout','Sampler','ImageView','Image','Fence','CommandPool','Framebuffer','RenderPass']:
 providers+='Procedure vkDestroy'+name+'(device.i,handle.i,alloc.i)\n If handle<>0 : acdReleases=acdReleases+1 : EndIf\nEndProcedure\n'
providers+='''
Procedure vkFreeMemory(device.i,handle.i,alloc.i)
 If handle<>0 : acdReleases=acdReleases+1 : EndIf
EndProcedure
Procedure vkDestroyDevice(handle.i,alloc.i)
 If handle<>0 : acdReleases=acdReleases+1 : EndIf
EndProcedure
Procedure vkDestroyInstance(handle.i,alloc.i)
 If handle<>0 : acdReleases=acdReleases+1 : EndIf
EndProcedure
'''
defined=set(re.findall(r'^Procedure(?:\.i)? (\w+)\(',production+'\n'+providers,re.M));assert calls-defined=={'Bool'},calls-defined
reset='Procedure AcdReset()\n Define i.i\n'
reset+='\n'.join(' '+v+'=0' for v in globals_ if v not in arrays)+'\n'
for v in sorted(arrays):reset+=' For i=0 To '+('1023' if v=='nvcTTIndex' else '16')+' : '+v+'[i]=0 : Next\n'
reset+=''' acdIdleCalls=0 : acdFirstRc=0 : acdLaterRc=0 : acdReleases=0
 acdPresentClears=0 : acdDrawClears=0 : acdBannerReleases=0
 acdRollbackCalls=0 : acdRollbackRc=0 : acdUnmaps=0
 nvcMapped=0
 nvcDevice=201 : nvcCommand=102 : nvcVertexMemory=103 : nvcVertexBuffer=104
 nvcCommandPool=105 : nvcFence=106 : nvcPipeline=107
 nvcFramePending=1 : nvcSubmitNoWait=1 : nvcReady=1 : nvcHooksInstalled=1 : nvlConfigured=1
 avcDevice=201 : avcPool=202 : avcFramebuffer=203 : avcReady=1
EndProcedure
'''
fixture=(r/'RaspberryPi4/Tests/neon_vk_teardown_proof.pbi').read_text(encoding='utf8');assert fixture.count('; @ACD_CONTROLLED_COMPOSITION@')==1
text=const+f'#ACD_REPORT=${layout["report"]:08X}\n'+fixture.replace('; @ACD_CONTROLLED_COMPOSITION@',decl+providers+production+'\n'+reset)
text+='\nDataSection\n'
for i,row in enumerate(expected_rows(),1):text+=' acdWant'+str(i)+':\n Data.i '+','.join(map(str,row))+'\n'
text+='''EndDataSection
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 8191 : PokeA(#ACD_REPORT+i,0) : Next
 rc=TeardownProof()
 PokeI(#ACD_REPORT,$41434450) : PokeI(#ACD_REPORT+8,rc)
 PokeI(#ACD_REPORT+16,#PMF_CHIP) : PokeI(#ACD_REPORT+24,acdRecords)
 PokeI(#ACD_REPORT+32,acdFailures) : PokeI(#ACD_REPORT+40,2)
 PokeI(#ACD_REPORT+56,$50444341)
 ProcedureReturn rc
EndProcedure
'''
(d/'proof.pbi').write_text(text,encoding='utf8');env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=env,capture_output=True,text=True,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
(d/'compile.txt').write_text(q.stdout+q.stderr,encoding='utf8');print((q.stdout+q.stderr)[-1000:]);assert q.returncode==0
ranges=check_linked_layout(layout,q.stdout+q.stderr);ranges['report'][1]=hex(layout['report']+8191)
items=[(k,int(v[0],16),int(v[1],16)) for k,v in ranges.items()]
for i,(name,lo,hi) in enumerate(items):
 for other,ol,oh in items[i+1:]:assert hi<ol or oh<lo,name+' overlaps '+other
 if name=='report':assert hi <= (0xe1c01fff if a.target=='pi4' else max(x[1] for x in layout['windows']))
image=d/'proof.img.pmf'
(d/'identity.json').write_text(json.dumps(dict(target=a.target,report_bytes=8192,bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),source_hashes=sources,production_body_hashes=hashes,checked_ranges=ranges,controlled_provider=True,executed=False,scope='Exact production bodies with controlled integer state/providers; no GPU, real resource-release helpers or native driver.'),indent=2))
