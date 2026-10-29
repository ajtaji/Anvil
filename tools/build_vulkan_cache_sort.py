"""Build the production cache-interval sort as a returning RAM-only proof."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_cache_sort_check import CASES,layout
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    name='RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4';blob=(r/name).read_bytes();s=blob.decode('utf8')
    decl=re.search(r'(?ms)^Structure AvkV3dCacheInterval.*?^EndStructure',s)[0]
    code=decl+'\nGlobal Dim avkV3dCacheInterval.AvkV3dCacheInterval[92160]\nGlobal avkV3dCacheIntervalCount.i\n'
    for n in ['avkV3dIntervalAfter','avkV3dIntervalSwap','avkV3dIntervalSift','avkV3dIntervalSort']:
        matches=re.findall(r'(?ms)^Procedure(?:\.i)? '+n+r'\(.*?^EndProcedure',s);assert len(matches)==1
        code+=matches[0]+'\n'
    code+=r'''
Procedure.i Main(services.i)
 Define i.i,n.i,mode.i,first.i,last.i,out.i
 For i=0 To 2097151 : PokeA($E1C00000+i,$A5) : Next
'''
    for at,n,mode in layout():
        code+=f' n={n} : mode={mode} : out=$E1C00000+{at}\n'
        code+=r'''
 avkV3dCacheIntervalCount=n
 For i=0 To n-1
  Select mode
   Case 0 : first=1+i*32
   Case 1 : first=1+(n-1-i)*32
   Case 2 : first=1+((i*73)%n)*32
   Case 3 : first=1+(i % 7)*64
   Case 4 : first=100
  EndSelect
  last=first+1+i % 1024
  If mode=4 : last=100+n-i : EndIf
  avkV3dCacheInterval[i]\firstByte=first
  avkV3dCacheInterval[i]\endByte=last
 Next
 If n<92160
  avkV3dCacheInterval[n]\firstByte=$12345678
  avkV3dCacheInterval[n]\endByte=$12345690
 EndIf
 avkV3dIntervalSort()
 PokeI(out,n) : PokeI(out+8,mode)
 If n<92160
  PokeI(out+16,avkV3dCacheInterval[n]\firstByte)
  PokeI(out+24,avkV3dCacheInterval[n]\endByte)
 Else
  PokeI(out+16,0) : PokeI(out+24,0)
 EndIf
 For i=0 To n-1
  PokeI(out+32+i*16,avkV3dCacheInterval[i]\firstByte)
  PokeI(out+40+i*16,avkV3dCacheInterval[i]\endByte)
 Next
'''
    code+=f' PokeI($E1C00000,$53525431)\n PokeI($E1C00008,{len(CASES)})\n ProcedureReturn 0\nEndProcedure\n'
    (d/'proof.pi4').write_text(code,encoding='utf8')
    c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1500:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1dfffff']}
    p=d/'proof.img.pmf'
    (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={name:hashlib.sha256(blob).hexdigest()},compiler_sha256=hashlib.sha256(Path(c).read_bytes()).hexdigest()),indent=2),encoding='utf8')
if __name__=='__main__':main()
