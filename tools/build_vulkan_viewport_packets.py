# Build a returning CPU check of viewport packet sizing and emission.
from pathlib import Path
import argparse,re,json,hashlib,subprocess,os
from pmf_compiler import resolve_compiler

def proc(text,name):
 m=re.search(r'(?ms)^Procedure(?:\.i)? '+re.escape(name)+r'\(.*?^EndProcedure',text);assert m,name
 return m[0]
def struct(text,name):
 m=re.search(r'(?ms)^Structure '+name+r'\b.*?^EndStructure',text);assert m,name
 return m[0]
# (x,y,w,h,mask,clear). All non-clear records have a full-surface scissor.
BASE=(0,0,80,60,1,0)
CASES=[
 [BASE], [BASE,BASE], [BASE,(1,0,80,60,1,0)], [BASE,(0,1,80,60,1,0)],
 [BASE,(2,3,80,60,1,0),(0,0,80,60,1,0)],
 [BASE,(0,0,81,60,1,0),(0,0,81,61,1,0)],
 [BASE,(8,9,40,30,0,0),BASE],
 [BASE,(8,9,40,30,0,0),(8,9,40,30,1,0)],
 [BASE,(0,0,1,1,1,1),BASE],
 [(8,9,40,30,0,0),(0,0,1,1,1,1),(8,9,40,30,1,0)],
 [(0,0,32767,32767,1,0),(32766,32766,1,1,1,0)],
 [BASE,(1,0,78,60,1,0),(1,0,78,60,1,0),(1,1,78,58,1,0)],
]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--previous',type=Path,required=True);a=ap.parse_args()
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 names=['RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4','RaspberryPi4/Lib/Vulkan/vk_v3d_shader.pi4','Anvil/Graphics/Vulkan/vk_foundation.pbi']
 backend,shader,foundation=[(r/n).read_text(encoding='utf8') for n in names];old=a.previous.read_text(encoding='utf8')
 s='#ANVIL_VK_RENDER_OP_CLEAR_RECT=1\n#ANVIL_VK_BLEND_SRC_OVER=1\n#AVKQ_F_ZERO=0\n'
 for name in ['AnvilVkBackendDraw','AnvilVkBackendDrawList']:s+=struct(foundation,name)+'\n'
 for name in ['AvkV3dNormalizedScissor','AvkV3dViewportState']:s+=struct(backend,name)+'\n'
 s+=proc(shader,'avkqF32FromInt')+'\n'
 for name in ['avkV3dNormalizeScissor','avkV3dDrawViewportHalfWidthFine','avkV3dDrawViewportHalfHeightFine','avkV3dDrawViewportOffsetXFine','avkV3dDrawViewportOffsetYFine','avkV3dDrawViewportHalfWidthBits','avkV3dDrawViewportHalfHeightBits','avkV3dViewportTransition']:s+=proc(backend,name)+'\n'
 s+='Procedure.i AnvilVkV3dVaryingComponents(pipe.i) : ProcedureReturn 4 : EndProcedure\n'
 s+=proc(backend,'avkV3dListPacketBytes')+'\n'+proc(old,'avkV3dListPacketBytes').replace('avkV3dListPacketBytes(','PreviousPacketBytes(')+'\n'
 emit=proc(backend,'avkBackendSubmitDraw');begin=emit.index('        If avkV3dViewportTransition(');end=emit.index('        EndIf',begin)+len('        EndIf');block=emit[begin:end]
 s+='''Global Dim records.AnvilVkBackendDraw[8]
Global row.i,eventCount.i
Procedure V3dClClipperXyScaling(w.i,h.i)
 PokeI(row+64+eventCount*32,w) : PokeI(row+72+eventCount*32,h)
EndProcedure
Procedure V3dClViewportOffset(x.i,coarseX.i,y.i,coarseY.i)
 PokeI(row+80+eventCount*32,x) : PokeI(row+88+eventCount*32,y)
 eventCount=eventCount+1
EndProcedure
Procedure EmitViewports(count.i)
 Define viewport.AvkV3dViewportState,viewportTransitions.i,i.i,*d.AnvilVkBackendDraw
 For i=0 To count-1
  *d=@records[i]
  If *d\\kind=#ANVIL_VK_RENDER_OP_CLEAR_RECT
   viewport\\valid=0
  ElseIf *d\\sampleMask<>0
'''.replace('\\\\','\\')+block+'''
  EndIf
 Next
 PokeI(row+16,viewportTransitions)
EndProcedure
Procedure SetRecord(i.i,x.i,y.i,w.i,h.i,mask.i,clear.i)
 records[i]\\kind=clear : records[i]\\pipeline=1
 records[i]\\width=32767 : records[i]\\height=32767
 records[i]\\viewportX=x : records[i]\\viewportY=y : records[i]\\viewportW=w : records[i]\\viewportH=h
 records[i]\\sampleMask=mask : records[i]\\scissorW=32767 : records[i]\\scissorH=32767
 records[i]\\instanceCount=1
EndProcedure
Procedure RunRow(index.i,count.i)
 Define list.AnvilVkBackendDrawList
 row=$E1C00100+index*512 : eventCount=0
 list\\drawCount=count : list\\draws=@records[0]
 PokeI(row,avkV3dListPacketBytes(@list)) : PokeI(row+8,PreviousPacketBytes(@list))
 EmitViewports(count)
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 8191 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$56505431)
'''.replace('\\\\','\\')
 for idx,case in enumerate(CASES):
  for i,values in enumerate(case):s+=' SetRecord('+','.join(map(str,(i,*values)))+')\n'
  s+=f' RunRow({idx},{len(case)})\n'
 s+=' ProcedureReturn 0\nEndProcedure\n'
 source=d/'proof.pi4';source.write_text(s,encoding='utf8');c=resolve_compiler(a.compiler)
 q=subprocess.run([str(c),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c01fff']}
 p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names}),indent=2),encoding='utf8')
if __name__=='__main__':main()
