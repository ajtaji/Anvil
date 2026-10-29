"""Build physical CPU state-cache transition proof from production procedures."""
from pathlib import Path
import argparse,re,json,hashlib,subprocess,os
from pmf_compiler import resolve_compiler
from build_vulkan_viewport_packets import proc

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Graphics/Vulkan/neon_vk_chrome.pbi'];chrome=(r/names[0]).read_text(encoding='utf8')
 s=r"""#NEON_VK_CHROME_ERR_STATE=201
#NEON_VK_CHROME_ERR_CAPACITY=202
#NEON_VK_CHROME_OK=0
#VK_PIPELINE_BIND_POINT_GRAPHICS=0
#VK_SHADER_STAGE_FRAGMENT_BIT=16
Structure Offset
 x.l
 y.l
EndStructure
Structure Extent
 width.l
 height.l
EndStructure
Structure VkRect2D
 offset.Offset
 extent.Extent
EndStructure
Global nvcCommand.i,nvcBoxBatchActive.i,nvcDrawCount.i,nvcMaxQuads.i,nvcVertices.i,nvcMaxVertexQuads.i
Global nvcViewportX.i,nvcViewportY.i,nvcViewportW.i,nvcViewportH.i,nvcPhysicalW.i,nvcPhysicalH.i
Global nvcClipX.i,nvcClipY.i,nvcClipW.i,nvcClipH.i,nvcInFrame.i
Global faults.i,scCalls.i,setCalls.i,tintCalls.i,injectFault.i,lastX.i,lastW.i,lastSet.i,lastLayout.i,lastColour.i
Procedure.i nvcFail(rc.i) : ProcedureReturn rc : EndProcedure
Procedure.i AnvilVkFaultCount() : ProcedureReturn faults : EndProcedure
Procedure vkCmdSetScissor(cmd.i,first.i,count.i,*sc.VkRect2D)
 scCalls=scCalls+1 : lastX=*sc\offset\x : lastW=*sc\extent\width
 If injectFault<>0 : faults=faults+1 : injectFault=0 : EndIf
EndProcedure
Procedure vkCmdBindDescriptorSets(cmd.i,point.i,layout.i,first.i,count.i,*sets,dc.i,dp.i)
 setCalls=setCalls+1 : lastSet=PeekI(*sets) : lastLayout=layout
EndProcedure
Procedure nvcTint(colour.i,*push) : PokeL(*push,colour) : EndProcedure
Procedure vkCmdPushConstants(cmd.i,layout.i,stages.i,off.i,bytes.i,*push)
 tintCalls=tintCalls+1 : lastColour=PeekL(*push) & $FFFFFFFF
EndProcedure
"""
 begin=chrome.index('Global nvcStateScissorValid');end=chrome.index('EndProcedure',begin)+len('EndProcedure')
 s+=chrome[begin:end]+'\n'+proc(chrome,'nvcDrawState')+'\n'
 s+=r"""
Procedure Save(index.i,rc.i)
 Define p.i
 p=$E1C00100+index*80
 PokeI(p,rc) : PokeI(p+8,scCalls) : PokeI(p+16,setCalls) : PokeI(p+24,tintCalls)
 PokeI(p+32,faults) : PokeI(p+40,lastX) : PokeI(p+48,lastW)
 PokeI(p+56,lastSet) : PokeI(p+64,lastLayout) : PokeI(p+72,lastColour)
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$53434131) : PokeI($E1C00008,20)
 nvcMaxQuads=100 : nvcMaxVertexQuads=100 : nvcInFrame=1
 nvcPhysicalW=64 : nvcPhysicalH=64 : nvcViewportW=64 : nvcViewportH=64 : nvcClipW=64 : nvcClipH=64
 Save(0,nvcDrawState($11223344,1,1))
 Save(1,nvcDrawState($11223344,1,1))
 Save(2,nvcDrawState($22334455,1,1))
 nvcClipX=4 : Save(3,nvcDrawState($22334455,1,1))
 nvcClipW=32 : Save(4,nvcDrawState($22334455,1,1))
 Save(5,nvcDrawState($22334455,2,1))
 Save(6,nvcDrawState($22334455,2,2))
 Save(7,nvcDrawState($22334455,0,2))
 Save(8,nvcDrawState($22334455,2,2))
 faults=faults+1 : Save(9,nvcDrawState($22334455,2,2))
 injectFault=1 : nvcClipX=5 : Save(10,nvcDrawState($22334455,2,2))
 Save(11,nvcDrawState($22334455,2,2))
 nvcInFrame=0 : Save(12,nvcDrawState($22334455,2,2))
 Save(13,nvcDrawState($22334455,2,2))
 nvcInFrame=1 : nvcDrawStateInvalidate() : Save(14,nvcDrawState($22334455,2,2))
 nvcViewportX=8 : nvcViewportW=32 : Save(15,nvcDrawState($22334455,2,2))
 nvcBoxBatchActive=1 : Save(16,nvcDrawState($33445566,3,3))
 nvcBoxBatchActive=0 : nvcDrawCount=100 : Save(17,nvcDrawState($33445566,3,3))
 nvcDrawCount=0 : nvcVertices=601 : Save(18,nvcDrawState($33445566,3,3))
 nvcVertices=0 : Save(19,nvcDrawState($33445566,3,3))
 ProcedureReturn 0
EndProcedure
"""
 source=d/'proof.pi4';source.write_text(s,encoding='utf8');c=resolve_compiler(a.compiler)
 q=subprocess.run([str(c),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
 p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},case_count=20),indent=2),encoding='utf8')
if __name__=='__main__':main()
