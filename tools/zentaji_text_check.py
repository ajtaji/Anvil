"""Compile the real text/memory/console backends; prove RAM ownership and frames."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
Global Dim context.q[18]
Global Dim report.q[14]
Procedure MainWait()
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 PokeQ(#ZEN_IDLE_TIMER,Ticks()+2000000) : PokeQ(#ZEN_IDLE_TIMER+$10,3)
 ZenCpuWait()
 PokeQ(#ZEN_IDLE_TIMER+$10,0) : PokeQ(#ZEN_IDLE_TIMER+$18,1)
EndProcedure
Procedure.i Main(phase.i)
 Protected ram.i=PeekQ($FFFF000000010018),top.i,bottom.i,n.i,bytes.i,offset.i
 offset=Bool((@context[0]&15)<>0)
 top=(ram&-16)-$100000 : bottom=top-65536
 context[offset+0]=#ZEN_BOOT_MAGIC : context[offset+1]=2 : context[offset+2]=128
 context[offset+3]=$FFFF000000010000 : context[offset+4]=PeekA($FFFF000000010023) : context[offset+5]=ram
 context[offset+7]=bottom : context[offset+8]=top : context[offset+9]=8192
 context[offset+10]=4096 : context[offset+11]=0 : context[offset+12]=4096
 context[offset+13]=$100000 : context[offset+14]=65536 : context[offset+15]=12288
 If phase=1 : context[offset+13]=bottom-4096 : EndIf
 If ZentajiMemoryBind(@context[offset+0])<>1 : ProcedureReturn 1 : EndIf
 report[0]=ZentajiTextRequired(context[offset+3])
 report[1]=ZentajiMemoryTextInit(context[offset+3])
 report[2]=zenMemoryTextBase : report[3]=zenMemoryTextBytes
 report[4]=HwPayHi(0) : report[5]=HwMonRegions()
 report[6]=ZentajiMemoryTextInit(context[offset+3])
 If report[1]=0 : ProcedureReturn 42 : EndIf
 report[7]=InPayload(zenMemoryTextBase,zenMemoryStackBottom-1)
 report[8]=HitsMonitor(zenMemoryTextBase,zenMemoryStackBottom-1)
 report[9]=InPayload(zenMemoryPayload,zenMemoryTextBase-1)
 ; Sentinels straddle the entire reservation, including its growth capacity.
 If (PeekL(zenMemoryTextBase-4)&$FFFFFFFF)<>$12345678 Or (PeekL(zenMemoryStackBottom)&$FFFFFFFF)<>$76543210 : ProcedureReturn 5 : EndIf
 If UartAttach()<>1 : ProcedureReturn 2 : EndIf
 If phase=2
  If ZentajiTextRelease()<>1 : ProcedureReturn 3 : EndIf
  PokeQ(#ZEN_DISPLAY+$48,1) : PokeQ(#ZEN_TEXT+$60,0)
  MainWait()
  report[10]=ZentajiTextResume()
 ElseIf phase=3
  PokeQ(#ZEN_TEXT+$48,0)
  report[10]=ZentajiTextOwned()
  ProcedureReturn 42
 ElseIf phase=4
  If ZentajiTextRelease()<>1 : ProcedureReturn 4 : EndIf
  PokeQ(#ZEN_DISPLAY+$10,1)
  report[10]=ZentajiTextResume()
  ProcedureReturn 42
 ElseIf phase=5
  ; Exercise hardware wrapping/scroll, not a software grid emulation.
  For n=0 To PeekQ(#ZEN_TEXT+$58)+1
   UartWrite(65+n) : UartWrite(13) : UartWrite(10)
  Next
  report[10]=ZentajiTextOwned()
  MainWait()
  ProcedureReturn 42
 ElseIf phase=6
  ; Grow while the monitor retains ownership: newly exposed cells are blank.
  PokeQ(#ZEN_DISPLAY+$48,1) : PokeQ(#ZEN_TEXT+$60,0)
  MainWait()
  report[10]=ZentajiTextOwned()
 Else
  report[10]=ZentajiTextOwned()
 EndIf
 UartWrite(65) : UartWrite($C3) : UartWrite($A9)
 UartWrite($E2) : UartWrite($82) : UartWrite($AC)
 UartWrite($F0) : UartWrite($9F) : UartWrite($98) : UartWrite($80)
 UartWrite($ED) : UartWrite($A0) : UartWrite($80)
 UartWrite($E0) : UartWrite($80) : UartWrite($80)
 UartWrite($C3) : UartWrite(13) : UartWrite(66) : UartWrite(10)
 UartWrite(9) : UartWrite(67) : UartWrite(8) : UartWrite(68) : UartWrite(7)
 report[11]=ZentajiTextOwned()
 report[12]=PeekL(zenMemoryTextBase-4)&$FFFFFFFF
 report[13]=PeekL(zenMemoryStackBottom)&$FFFFFFFF
 MainWait()
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);a=ap.parse_args()
    cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-text-') as tmp:
        td=Path(tmp);src=td/'text.zentaji';image=td/'text.zex';src.write_text(SOURCE,encoding='utf-8')
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();org,body=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,body)+body
        for name,phase,modes in [('native',0,[(320,160,60000),(640,480,60000)]),('small-ram',1,[(320,160,60000),(640,480,60000)]),('mode-font-growth',2,[(320,160,60000),(640,480,60000)]),('stolen-cells',3,[(320,160,60000)]),('live-foreign-display',4,[(320,160,60000)]),('hardware-scroll',5,[(320,160,60000)]),('retained-growth',6,[(320,160,60000),(640,480,60000)]),('zero-grid',0,[(1,1,60000)])]:
            m=I.Fixture(ram_size=4<<20,cores=2,display_modes=modes);m.load_image(image.read_bytes());m.cores[0].r[1]=phase
            required=max((w//fw)*(h//fh)*4 for w,h,_ in modes for fw,fh in [(8,16),(12,24),(16,32)])
            capacity=(required+4095)&-4096;base=(4<<20)-(1<<20)-65536-capacity
            struct.pack_into('<I',m.ram,base-4,0x12345678)
            struct.pack_into('<I',m.ram,(4<<20)-(1<<20)-65536,0x76543210)
            assert not L.capture(m,str(td))
            m=runner.execute(m,2000000,td);c=m.cores[0];frames=list(m.frames)
            assert c.state=='HALTED' and c.exit==42,(name,c.state,c.exit,ref.sym['GLOBAL_CONTEXT'],struct.unpack_from('<16q',m.ram,ref.sym['GLOBAL_CONTEXT']))
            got=struct.unpack_from('<14q',m.ram,ref.sym['GLOBAL_REPORT'])
            assert got[0]==required,(name,got,required)
            active=name not in ('small-ram','zero-grid')
            assert got[1]==int(active) and got[6]==0,(name,got)
            if active:
                capacity=(required+4095)&-4096;base=(4<<20)-(1<<20)-65536-capacity
                assert got[2:10]==(base,capacity,base-1,4,0,0,4,1),(name,got)
                assert got[10]==int(phase not in (3,4)),(name,got)
                assert struct.unpack_from('<I',m.ram,base-4)[0]==0x12345678
                assert struct.unpack_from('<I',m.ram,(4<<20)-(1<<20)-65536)[0]==0x76543210
                if phase in (0,2,5,6):
                    assert m.fields['textmeta'][1]==0 and frames,(name,m.fields['textmeta'][1],frames)
                    cols,rows=m.fields['text'][0],m.fields['text'][1]
                    cells=list(struct.unpack_from('<%dI'%(cols*rows),m.ram,base))
                    expected=[0x70020]*(cols*rows)
                    if phase==5:
                        for row in range(rows-1):expected[row*cols]=0x70000|65+row+3
                    else:
                        assert bytes(m.serial[0].out)==bytes([65,0xC3,0xA9,0xE2,0x82,0xAC,0xF0,0x9F,0x98,0x80,0xED,0xA0,0x80,0xE0,0x80,0x80,0xC3,13,66,10,9,67,8,68,7]),name
                        expected[:7]=[0x70000|v for v in (66,0xE9,0x20AC,0xFFFD,0xFFFD,0xFFFD,0xFFFD)]
                        expected[cols+8]=0x70044
                        assert got[11:]==(1,0x12345678,0x76543210)
                    assert cells==expected,(name,[(i,x,y) for i,(x,y) in enumerate(zip(cells,expected)) if x!=y][:10])
            else:
                assert got[2:4]==(0,0) and got[5]==3 and m.fields['textmeta'][0]==0 and m.fields['textmeta'][3]==0,(name,got)
            out=run([L.EXE,td/'machine.txt','--max','2000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram,name
            I.assert_same_state(out,m)
            assert m.cores[1].state=='PARKED'
            if phase in (0,2,6) and active:
                out=run([zt/'zenwin.exe',td/'machine.txt','--headless','--max','2000000'])
                assert [line for line in out.splitlines() if line.startswith('FRAME ')]==frames,name
            print('PASS text '+name+': actual compiled console/memory HAL, independent cell/protection oracle, full native state/RAM'+(' and headless frame hashes' if phase in (0,2,6) and active else ''),flush=True)


if __name__=='__main__':main()
