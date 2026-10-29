"""Build a returning CPU proof from the production uniform-copy procedures."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler',required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();r=Path(__file__).resolve().parents[1];d=a.out.resolve()
    d.mkdir(parents=True,exist_ok=False)
    name='RaspberryPi4/Lib/Vulkan/vk_v3d_shader.pi4'
    blob=(r/name).read_bytes();owner=blob.decode('utf8')
    names=['avkqF32FromInt','avkqPoke32','avkqCopyClosedUniformWords','avkqCloneLiveFragmentTemplate','avkqCloneDynamicViewportUniforms']
    functions=[]
    for n in names:
        matches=re.findall(r'(?ms)^Procedure(?:\.i)? '+n+r'\(.*?^EndProcedure',owner)
        assert len(matches)==1,n
        functions.append(matches[0])
    consts=['#VK_SUCCESS=0','#ANVIL_VK_ERR_ARGS=-20001','#AVKQ_CODE_SLOT=2048']
    for n in ['AVKQ_F_ZERO','AVKQ_OFF_UNIF_CS','AVKQ_OFF_UNIF_VS','AVKQ_OFF_UNIF_FS','AVKQ_DRAW_OFF_UNIF_CS','AVKQ_DRAW_OFF_UNIF_VS','AVKQ_DRAW_OFF_UNIF_FS','AVKQ_DRAW_UNIF_CS_BYTES','AVKQ_DRAW_UNIF_VS_BYTES']:
        consts.append(re.search(r'(?m)^#'+n+r'\s*=.*$',owner)[0])
    arrays=['avkqDrawTemplateBytes','avkqDrawUsesDynamicViewport','avkqCsUniformWords','avkqVsUniformWords']
    source='\n'.join(consts+['Global Dim '+n+'.i[2]' for n in arrays]+functions)
    source+='''
Procedure.i Main(services.i)
 Define i.i,n.i,k.i,base.i,rc.i,width.i,height.i,cs.i,vs.i
 For i=0 To 262143 : PokeA($E1C00000+i,$A5) : Next
 For i=0 To 8191 : PokeA($E1C3C000+i,(i*37+11)&255) : Next
 For i=0 To 32767 : PokeL($E1C00200+i*4,avkqF32FromInt(i*128)) : Next
 k=0
 For i=0 To 23
  For n=-1 To 1
   PokeL($E1C20200+k*4,avkqF32FromInt((1<<i)+n)) : k=k+1
  Next
 Next
 PokeL($E1C20320,avkqF32FromInt(-1))
 PokeL($E1C20324,avkqF32FromInt(16777216))
 PokeL($E1C20328,avkqF32FromInt(16777215))
 For i=1 To 64
  base=$E1C21000+(i-1)*1024
  avkqDrawTemplateBytes[1]=i*4
  avkqCloneLiveFragmentTemplate(1,$E1C3C000,base+64)
 Next
 For i=0 To 23
  base=$E1C21000+(64+i)*1024
  cs=4+(i%7) : vs=32-(i%7) : width=1+i*1424 : height=32767-i*1424
  avkqDrawUsesDynamicViewport[1]=1
  Select i
   Case 16 : width=0
   Case 17 : height=32768
   Case 18 : cs=3
   Case 19 : vs=33
   Case 20 : width=-1
   Case 21 : height=-1
   Case 22 : width=32767 : height=1 : cs=32 : vs=4
   Case 23 : width=0 : height=0 : avkqDrawUsesDynamicViewport[1]=0
  EndSelect
  avkqCsUniformWords[1]=cs : avkqVsUniformWords[1]=vs
  rc=avkqCloneDynamicViewportUniforms(1,$E1C3C000,base+64,width,height)
  PokeI(base,rc)
 Next
 PokeI($E1C00000,$554E4931)
 PokeI($E1C00008,88)
 ProcedureReturn 0
EndProcedure
'''
    (d/'proof.pi4').write_text(source,encoding='utf8')
    c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c3ffff']}
    p=d/'proof.img.pmf'
    (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_hashes={name:hashlib.sha256(blob).hexdigest()},checked_ranges=ranges,compiler_sha256=hashlib.sha256(Path(c).read_bytes()).hexdigest()),indent=2),encoding='utf8')
if __name__=='__main__':main()
