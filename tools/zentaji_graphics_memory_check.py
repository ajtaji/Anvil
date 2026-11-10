"""Protected boot graphics arena, payload exclusion and real native GPU clear."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
XIncludeFile "Zentaji/Board/graphics_queue.pbi"
XIncludeFile "Zentaji/Board/graphics_display.pbi"
Global phase.i
Global Dim report.q[16]
Global Dim command.q[8]
Global queue.ZentajiGraphicsQueue
Procedure.i Main(table.i,source.i,context.i)
 Protected bytes.i=$2000000,top.i,base.i,n.i,index.i
 If ZentajiMemoryGraphicsInit(8192)<>0 : ProcedureReturn 1 : EndIf
 If ZentajiMemoryBind(context)<>1 : ProcedureReturn 2 : EndIf
 If phase=1 And ZentajiMemoryTextInit(table)<>1 : ProcedureReturn 3 : EndIf
 top=HwPayHi(0)+1
 Select phase
  Case 7,8,9,10 : bytes=$100000
  Case 2 : bytes=8193
  Case 4 : bytes=8191
  Case 5 : bytes=(top&-4096)-zenMemoryPayload-4096
  Case 6 : bytes=(top&-4096)-zenMemoryPayload-4095
 EndSelect
 report[0]=ZentajiMemoryGraphicsInit(bytes)
 report[1]=zenMemoryGraphicsBase : report[2]=zenMemoryGraphicsBytes
 report[3]=HwPayHi(0) : report[4]=HwMonRegions()
 report[5]=ZentajiMemoryGraphicsInit(8192)
 report[6]=ZentajiMemoryTextInit(table)
 If report[0]=0 : ProcedureReturn 42 : EndIf
 base=zenMemoryGraphicsBase : index=3+Bool(zenMemoryTextBase<>0)
 report[7]=HwMonRegionLo(index) : report[8]=HwMonRegionHi(index)
 report[9]=InPayload(base,top-1) : report[10]=HitsMonitor(base,top-1)
 report[11]=InPayload(zenMemoryPayload,base-1)
 report[12]=InPayload(base-1,base) : report[13]=PayloadTop(base)
 If ZentajiGraphicsBind(@queue,15,base,4096,base,2048,base+2048)<>1 : ProcedureReturn 4 : EndIf
 If ZentajiGraphicsBegin(@queue)<>1 : ProcedureReturn 5 : EndIf
 command[0]=1 : command[1]=base+4096
 PokeL(@command[0]+16,64) : PokeW(@command[0]+20,16) : PokeW(@command[0]+22,16) : PokeA(@command[0]+24,2)
 If phase>=7
  PokeL(@command[0]+16,1280) : PokeW(@command[0]+20,320) : PokeW(@command[0]+22,160)
 EndIf
 If ZentajiGraphicsAppend(@queue,@command[0])<>1 : ProcedureReturn 6 : EndIf
 For n=0 To 7 : command[n]=0 : Next
 command[0]=$105 : PokeL(@command[0]+8,$FF336699)
 If ZentajiGraphicsAppend(@queue,@command[0])<>1 Or ZentajiGraphicsSubmit(@queue)<>1 : ProcedureReturn 7 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(1000)<>1 Or ZentajiGraphicsWait(@queue,250000)<>1 : ProcedureReturn 8 : EndIf
 report[14]=PeekQ(queue\fence)
 If phase>=7
  If ZentajiGraphicsDisplayStart(base)<>0 : ProcedureReturn 14 : EndIf
  If ZentajiGraphicsDisplayStart(base+4096)<>1 : ProcedureReturn 10 : EndIf
  If ZentajiGraphicsDisplayPresent(@queue,-1)<>0 Or ZentajiGraphicsDisplayPresent(@queue,zgdBuffers)<>0 : ProcedureReturn 15 : EndIf
  If ZentajiGraphicsDisplayPresent(@queue,0)<>1 : ProcedureReturn 11 : EndIf
  If ZentajiGraphicsDisplayRelease()<>0 : ProcedureReturn 12 : EndIf
  If phase=9
   If ZentajiGraphicsDisplayWait(1)<>0 Or zgdPending<>1 Or ZentajiGraphicsDisplayRelease()<>0 : ProcedureReturn 16 : EndIf
  Else
   If ZentajiGraphicsDisplayWait(250000)<>1 Or zgdSequence<>1 : ProcedureReturn 13 : EndIf
  EndIf
  If phase=8
   PokeQ(#ZEN_GFX_DISPLAY+$70,zgdPitch+4)
   If ZentajiGraphicsDisplayPoll()<>-1 Or zgdLost<>1 Or ZentajiGraphicsDisplayRelease()<>0 : ProcedureReturn 17 : EndIf
   If PeekQ(#ZEN_GFX_DISPLAY+$70)<>zgdPitch+4 : ProcedureReturn 18 : EndIf
  ElseIf phase=10
   If ZentajiGraphicsDisplayRelease()<>1 Or InPayload(base,top-1)<>0 : ProcedureReturn 19 : EndIf
  EndIf
 EndIf
 If ZentajiGraphicsRelease(@queue)<>1 : ProcedureReturn 9 : EndIf
 report[15]=InPayload(base,top-1)
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve()
    sys.path.insert(0,str(zt))
    import zen_native_fixture as F
    import zasm_ref as A
    def run(argv):
        p=subprocess.run([str(x) for x in argv],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-graphics-memory-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex'
        src.write_text(SOURCE,encoding='utf-8');run([cc,'--compile',src,'-o',image])
        ref=A.Asm();ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/'zasm.exe',source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        for phase,ram in ((0,64<<20),(1,64<<20),(2,(8<<20)+123),(3,2<<20),(4,8<<20),(5,8<<20),(6,8<<20),(7,8<<20),(8,8<<20),(9,8<<20),(10,8<<20)):
            m=F.Fixture(ram_size=ram,cores=2,display_modes=[(320,160,1 if phase==9 else 60000)])
            m.load_image(wrapped);struct.pack_into('<q',m.ram,ref.sym['GLOBAL_PHASE'],phase)
            stage=(meta['image_end']+4095)&-4096
            bottom=(ram&-16)-(1<<20)-meta['stack_bytes']
            text=4096 if phase==1 else 0
            top=bottom-text
            requested={7:1<<20,8:1<<20,9:1<<20,10:1<<20,2:8193,4:8191,5:(top&-4096)-stage-4096,6:(top&-4096)-stage-4095}.get(phase,32<<20)
            size=(requested+4095)&-4096
            admitted=phase not in (3,4,6)
            base=(top&-4096)-size if admitted else 0
            if admitted:
                m.ram[base-8:base]=b'GUARDLOW'
                m.ram[base+size-8:base+size]=b'GUARDEND'
            assert not F.capture(m,str(td))
            out=run([zt/'zenemu.exe',td/'machine.txt','--max','2000000','--ram',td/'final.bin'])
            end=next(x for x in out.splitlines() if x.startswith('END '))
            assert ' exit=2A ' in end,(phase,end)
            final=(td/'final.bin').read_bytes();got=struct.unpack_from('<16q',final,ref.sym['GLOBAL_REPORT'])
            expected=[int(admitted),base,size if admitted else 0,base-1 if admitted else top-1,3+int(text>0)+int(admitted),0,0]
            assert list(got[:7])==expected,(phase,got,expected)
            if admitted:
                index=3+int(text>0)
                assert got[7:]==(base,top-1,0,index+1,1,0,0,1,0),(phase,got)
                assert final[base+4096:base+5120]==struct.pack('<I',0xFF336699)*256,phase
                assert final[base-8:base]==b'GUARDLOW' and final[base+size-8:base+size]==b'GUARDEND',phase
            if phase==7:
                import zlib
                headless=run([zt/'zenwin.exe',td/'machine.txt','--headless','--max','2000000'])
                frames=[line for line in headless.splitlines() if line.startswith('FRAME ')]
                expected_crc=zlib.crc32(struct.pack('<I',0x00336699)*(320*160))
                assert any(('%08X'%expected_crc).lower() in line.lower() for line in frames),(frames,hex(expected_crc))
                print('PASS native GPU to display: latched scanout, timer/WFI wait, exact independently calculated frame CRC',flush=True)
            print('PASS graphics arena phase %d: immutable bounds, staging exclusion%s'%(phase,', actual GPU pixels/fence/guards' if admitted else ', atomic refusal'),flush=True)


if __name__=='__main__':main()
