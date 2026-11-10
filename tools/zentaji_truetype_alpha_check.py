"""Actual shared TrueType scalar/default/optional alpha callback on Zentaji."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''XIncludeFile "Anvil/Graphics/truetype_renderer.pbi"
Global Dim report.q[8]
Global Dim coverage.a[20]
Global calls.i
Procedure.i Custom(buffer.i,count.i,capacity.i)
 calls=calls+1
 If count<>1 Or capacity<>19 : ProcedureReturn -1 : EndIf
 PokeA(buffer,201) : ProcedureReturn 77
EndProcedure
Procedure.i Main()
 Protected i.i
 coverage[0]=37 : coverage[18]=91
 report[0]=AnvilTrueTypeCoverageCountsToAlpha(0,0,0)
 For i=0 To 16 : coverage[i+1]=i : Next
 coverage[8]=17
 report[1]=AnvilTrueTypeCoverageCountsToAlpha(@coverage[1],17,17)
 If report[1]<>0 : ProcedureReturn 1 : EndIf
 For i=0 To 16
  If i=7
   If coverage[i+1]<>17 : ProcedureReturn 2 : EndIf
  Else
   If coverage[i+1]<>i : ProcedureReturn 3 : EndIf
  EndIf
 Next
 If AnvilTrueTypeRasterAlphaHandlerSet(@Custom)<>1 : ProcedureReturn 4 : EndIf
 report[2]=AnvilTrueTypeCoverageCountsToAlpha(@coverage[1],1,19)
 If report[2]<>77 Or coverage[1]<>201 Or calls<>1 : ProcedureReturn 5 : EndIf
 If AnvilTrueTypeCoverageCountsToAlpha(0,1,19)<>0 Or calls<>1 : ProcedureReturn 6 : EndIf
 If AnvilTrueTypeCoverageCountsToAlpha(@coverage[1],-1,19)<>0 Or calls<>1 : ProcedureReturn 7 : EndIf
 If AnvilTrueTypeCoverageCountsToAlpha(@coverage[1],20,19)<>0 Or calls<>1 : ProcedureReturn 8 : EndIf
 If AnvilTrueTypeRasterAlphaHandlerSet(0)<>1 : ProcedureReturn 9 : EndIf
 For i=0 To 16 : coverage[i+1]=i : Next
 report[3]=AnvilTrueTypeCoverageCountsToAlpha(@coverage[1],17,17)
 report[4]=calls
 If coverage[0]<>37 Or coverage[18]<>91 : ProcedureReturn 10 : EndIf
 ProcedureReturn 42
EndProcedure
'''
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    args=ap.parse_args();cc=resolve_compiler(args.compiler);zt=args.zen_tools.resolve()
    sys.path.insert(0,str(zt));import zen_native_fixture as F;import zasm_ref as A;import zexpack
    def run(argv):
        p=subprocess.run([str(v) for v in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-5000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='zen-tt-alpha-') as tmp:
        td=Path(tmp);src=td/'alpha.zentaji';image=td/'alpha.zex';src.write_text(SOURCE)
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();origin,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(origin,origin,data)+data
        machine=F.Fixture(ram_size=16<<20);machine.load_image(image.read_bytes());machine.write(td)
        result=run([zt/'zenemu.exe',td/'machine.txt','--max','2000000','--ram',td/'final.bin'])
        end=next(line for line in result.splitlines() if line.startswith('END '))
        ram=(td/'final.bin').read_bytes();report=struct.unpack_from('<8q',ram,ref.sym['GLOBAL_REPORT'])
        assert ' exit=2A ' in end,(end,report)
        assert report[:5]==(1,0,77,1,1),report
        want=bytes([37,0,16,32,48,64,80,96,112,128,143,159,175,191,207,223,239,255,91])
        at=ref.sym['GLOBAL_COVERAGE'];assert ram[at:at+len(want)]==want
    print('PASS native shared TrueType alpha interface: all17 exact levels, invalid input unchanged, custom signature/arguments/return, bounded refusals, reset-to-scalar and guards')
if __name__=='__main__':main()
