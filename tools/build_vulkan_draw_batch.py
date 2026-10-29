# Physical CPU proof of closed draw compaction and refusal boundaries.
from pathlib import Path
import argparse,re,json,hashlib,subprocess,os
from pmf_compiler import resolve_compiler
from build_vulkan_viewport_packets import proc,struct

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Graphics/Vulkan/vk_draw_batch.pbi','Anvil/Graphics/Vulkan/vk_foundation.pbi','RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4']
 helper,foundation,backend=[(r/n).read_text(encoding='utf8') for n in names]
 draw=struct(foundation,'AnvilVkBackendDraw');fields=re.findall(r'(?m)^\s+(\w+)\.i\b',draw);assert len(fields)*8>0
 s='#VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST=3\n#ANVIL_VK_RENDER_OP_DRAW=0\n#ANVIL_VK_RENDER_OP_CLEAR_RECT=1\n#ANVIL_VK_MAX_RECORDED_DRAWS=8\n'
 for n in ['AnvilVkBackendDraw','AnvilVkBackendDrawList','AnvilVkBackendBinding','AnvilVkBackendSampledImage']:s+=struct(foundation,n)+'\n'
 s+='\n'.join(line for line in helper.splitlines() if not line.startswith('XIncludeFile'))+'\n'
 s+='Global Dim avkV3dBatchDraw.AnvilVkBackendDraw[8]\nGlobal avkV3dBatchList.AnvilVkBackendDrawList\nProcedure.i AnvilVkPipelineTopology(pipe.i) : ProcedureReturn 3 : EndProcedure\n'
 s+=proc(backend,'avkV3dCompactDraws')+'\n'
 s+=r'''Global a.AnvilVkBackendDraw,b.AnvilVkBackendDraw
Global Dim bindA.i[4]
Global Dim bindB.i[4]
Global Dim pushA.l[4]
Global Dim pushB.l[4]
Global sampleA.AnvilVkBackendSampledImage,sampleB.AnvilVkBackendSampledImage
Global Dim input.AnvilVkBackendDraw[7]
Procedure InitPair()
 Define i.i
 For i=0 To SizeOf(AnvilVkBackendDraw)-8 Step 8 : PokeI(@a+i,0) : PokeI(@b+i,0) : Next
 a\pipeline=1 : a\targetBase=$3000000 : a\targetBytes=4096 : a\width=32 : a\height=32 : a\pitch=128
 a\bindingCount=2 : a\bindings=@bindA[0] : a\vertexCount=6 : a\maxVertex=5
 a\sampleMask=1 : a\blendMode=1 : a\viewportW=32 : a\viewportH=32 : a\scissorW=32 : a\scissorH=32
 a\pushBase=@pushA[0] : a\pushBytes=16 : a\sampledImage=@sampleA : a\instanceCount=1
 For i=0 To 3 : bindA[i]=100+i : bindB[i]=100+i : pushA[i]=200+i : pushB[i]=200+i : Next
 For i=0 To SizeOf(AnvilVkBackendSampledImage)-8 Step 8 : PokeI(@sampleA+i,300+i) : PokeI(@sampleB+i,300+i) : Next
 For i=0 To SizeOf(AnvilVkBackendDraw)-8 Step 8 : PokeI(@b+i,PeekI(@a+i)) : Next
 b\firstVertex=6 : b\maxVertex=11 : b\bindings=@bindB[0] : b\pushBase=@pushB[0] : b\sampledImage=@sampleB
EndProcedure
Procedure SaveResult(index.i,result.i)
 PokeI($E1C00100+index*8,result)
EndProcedure
Procedure.i Main(services.i)
 Define i.i,k.i,list.AnvilVkBackendDrawList,*result.AnvilVkBackendDrawList
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$42415431)
 PokeI($E1C00008,SizeOf(AnvilVkBackendDraw))
 InitPair() : SaveResult(0,AnvilVkDrawCanMerge(@a,@b,3))
'''
 count=1
 skipped={'bindings','vertexCount','firstVertex','maxVertex','pushBase','sampledImage'}
 for field in fields:
  if field in skipped:continue
  s+=f' InitPair() : b\\{field}=b\\{field}+1 : SaveResult({count},AnvilVkDrawCanMerge(@a,@b,3))\n';count+=1
 for field,limit,width in [('bindB',4,8),('pushB',4,4),('sampleB',13,8)]:
  for i in range(limit):
   addr=f'@{field}[0]+{i*width}' if field!='sampleB' else f'@sampleB+{i*width}'
   s+=f' InitPair() : PokeA({addr},PeekA({addr}) ! 1) : SaveResult({count},AnvilVkDrawCanMerge(@a,@b,3))\n';count+=1
 for change,topology in [('b\\vertexCount=5',3),('b\\firstVertex=5',3),('b\\firstVertex=7',3),('a\\vertexCount=$7FFFFFFE : b\\vertexCount=6',3),('',4),('',5),('a\\pushBase=0',3),('a\\bindings=0',3),('a\\sampledImage=0',3)]:
  s+=' InitPair() : '+(change+' : ' if change else '')+f'SaveResult({count},AnvilVkDrawCanMerge(@a,@b,{topology}))\n';count+=1
 s+=f' PokeI($E1C00010,{count})\n'
 s+=r''' InitPair()
 For k=0 To 6
  For i=0 To SizeOf(AnvilVkBackendDraw)-8 Step 8 : PokeI(@input[k]+i,PeekI(@a+i)) : Next
  input[k]\firstVertex=k*6 : input[k]\maxVertex=k*6+5
 Next
 input[2]\kind=1
 input[4]\sampleMask=0
 For i=0 To SizeOf(AnvilVkBackendDraw)*7-8 Step 8 : PokeI($E1C01000+i,PeekI(@input[0]+i)) : Next
 list\drawCount=7 : list\draws=@input[0]
 *result=avkV3dCompactDraws(@list)
 PokeI($E1C00018,*result\drawCount)
 For i=0 To SizeOf(AnvilVkBackendDraw)*7-8 Step 8 : PokeI($E1C02000+i,PeekI(@input[0]+i)) : Next
 For i=0 To SizeOf(AnvilVkBackendDraw)*(*result\drawCount)-8 Step 8 : PokeI($E1C03000+i,PeekI(*result\draws+i)) : Next
 ProcedureReturn 0
EndProcedure
'''
 source=d/'proof.pi4';source.write_text(s,encoding='utf8');c=resolve_compiler(a.compiler)
 q=subprocess.run([str(c),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
 p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},case_count=count,fields=fields),indent=2),encoding='utf8')
if __name__=='__main__':main()
