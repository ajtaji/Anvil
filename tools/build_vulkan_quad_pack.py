"""Build production quad writers with the uncached shared ratio converter."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from vulkan_quad_pack_check import CASES,RECTS,UVS
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    name='Anvil/Graphics/Vulkan/neon_vk_chrome.pbi';blob=(r/name).read_bytes();owner=blob.decode('utf8')
    source='XIncludeFile "Anvil/Graphics/float_bits.pbi"\n'
    for n in ['NEON_VK_CHROME_VERTEX_BYTES','NEON_VK_CHROME_F_ONE']:
        source+=re.search(r'(?m)^#'+n+r'\s*=.*$',owner)[0]+'\n'
    source+='''
Global nvcMapped.i,nvcRotation.i,nvcLogicalW.i,nvcLogicalH.i,nvcPhysicalW.i,nvcPhysicalH.i
; Exercise the actual ratio converter directly; the unchanged table cache is
; covered by the paired rendering test, not this isolated writer proof.
Procedure.i nvcClipXBits2(x2.i)
 ProcedureReturn GraphicsF32RatioBits(x2-nvcPhysicalW,nvcPhysicalW)
EndProcedure
Procedure.i nvcClipYBits2(y2.i)
 ProcedureReturn GraphicsF32RatioBits(y2-nvcPhysicalH,nvcPhysicalH)
EndProcedure
'''
    for n in ['nvcVertex','nvcQuad']:
        matches=re.findall(r'(?ms)^Procedure '+n+r'\(.*?^EndProcedure',owner);assert len(matches)==1
        source+=matches[0]+'\n'
    source+='Procedure.i Main(services.i)\n Define i.i\n For i=0 To 32767 : PokeA($E1C00000+i,$A5) : Next\n nvcLogicalW=64 : nvcLogicalH=32\n'
    for i,(rot,align,j) in enumerate(CASES):
        w,h=(32,64) if rot in (90,270) else (64,32)
        source+=f' nvcRotation={rot} : nvcPhysicalW={w} : nvcPhysicalH={h}\n nvcMapped=$E1C00000+{512+i*512+64+align}\n'
        source+=' nvcQuad(3,'+','.join(str(x) for x in (*RECTS[j],*UVS[j]))+')\n'
    source+=f' PokeI($E1C00000,$51554131)\n PokeI($E1C00008,{len(CASES)})\n ProcedureReturn 0\nEndProcedure\n'
    (d/'proof.pi4').write_text(source,encoding='utf8')
    c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1500:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c07fff']}
    p=d/'proof.img.pmf';inputs={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in [name,'Anvil/Graphics/float_bits.pbi']}
    (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs,compiler_sha256=hashlib.sha256(Path(c).read_bytes()).hexdigest()),indent=2),encoding='utf8')
if __name__=='__main__':main()
