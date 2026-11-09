"""Execute the production cell-text service with independent cell/status oracles."""
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

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
XIncludeFile "Zentaji/Board/text_service.pbi"
Global ztTestCount.i
Procedure Check(actual.i,expected.i)
 If actual<>expected And PeekQ($600000)=0 : PokeQ($600000,ztTestCount+1) : PokeQ($600100,actual) : PokeQ($600108,expected) : EndIf
 ztTestCount=ztTestCount+1
EndProcedure
Procedure WaitFrame()
 Protected deadline.i=Ticks()+2000000
 While Ticks()<deadline : HwPromptIdleWait() : Wend
EndProcedure
Procedure.i Main(table.i,source.i,context.i)
 Protected phase.i=PeekQ($700000),handle.i,second.i,n.i,w.i,h.i,base.i
 Protected *write.NativeTextWriteRequest=$200080,*fill.NativeTextFillRequest=$200080
 Protected *cursor.NativeTextCursorRequest=$200080,*scroll.NativeTextScrollRequest=$200080
 If ZentajiMemoryBind(context)<>1 : ProcedureReturn 1 : EndIf
 ZentajiMemoryTextInit(table)
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 Check(ZentajiPromptIdlePrepare(2000),1)
 Check(ZentajiTextServiceStart(),Bool(phase<>5))
 If phase=5
  Check(TextServiceEnter(),0)
  Check(TextServiceCall(#NTX_QUERY,0,$200000,SizeOf(NativeTextApi)),#NTX_ERR_UNBOUND)
  Check(TextServiceLeave(),0)
  PokeQ($600008,ztTestCount) : ProcedureReturn 42
 EndIf
 If phase=6
  PokeQ(#ZEN_TEXT+$60,0) : WaitFrame()
 ElseIf phase=9
  PokeQ(#ZEN_DISPLAY+$48,1) : WaitFrame()
 EndIf
 Check(TextServiceCall(#NTX_OPEN,0,$200040,SizeOf(NativeTextOpenRequest)),#NTX_ERR_STATE)
 Check(TextServiceCall(#NTX_QUERY,0,$200000,SizeOf(NativeTextApi)),0)
 Check(PeekL($200000),#NTX_MAGIC) : Check(PeekQ($200010),1)
 Check(PeekQ($200018),4096) : Check(PeekQ($200020),@TextServiceCall)
 Check(TextServiceEnter(),0)
 handle=TextServiceCall(#NTX_OPEN,0,$200040,SizeOf(NativeTextOpenRequest)) : Check(handle,1)
 w=PeekQ($200040) : h=PeekQ($200048) : base=zenTextCells
 PokeQ($600010,w) : PokeQ($600018,h) : PokeQ($600020,base) : PokeQ($600028,zenTextCapacity)
 If phase=0 Or phase=7
  If phase=7 : PokeQ(#ZEN_TEXT+$98,3) : EndIf
  *fill\x=1 : *fill\y=1 : *fill\width=5 : *fill\height=4 : *fill\cell=$02010058
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),0)
  For n=0 To 7 : PokeL($200100+n*4,$04030041+n) : Next
  *write\x=2 : *write\y=2 : *write\width=3 : *write\height=2 : *write\cells=$200100 : *write\stride=5
  Check(TextServiceCall(#NTX_WRITE,handle,$200080,SizeOf(NativeTextWriteRequest)),0)
  *scroll\top=1 : *scroll\bottom=5 : *scroll\lines=1 : *scroll\cell=$0605002E
  Check(TextServiceCall(#NTX_SCROLL,handle,$200080,SizeOf(NativeTextScrollRequest)),0)
  *scroll\top=2 : *scroll\bottom=6 : *scroll\lines=-1 : *scroll\cell=$0807002D
  Check(TextServiceCall(#NTX_SCROLL,handle,$200080,SizeOf(NativeTextScrollRequest)),0)
  *cursor\x=4 : *cursor\y=3 : *cursor\style=2
  Check(TextServiceCall(#NTX_CURSOR,handle,$200080,SizeOf(NativeTextCursorRequest)),0)
  Check(UartAttach(),1) : UartWrite(90)
  Check(ZentajiTextOwned(),1)
  Check(TextServiceCall(#NTX_PRESENT,handle,0,0),0)
 ElseIf phase=1
  Check(TextServiceCall(#NTX_FILL,handle,0,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  Check(TextServiceCall(#NTX_FILL,handle,$200081,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  Check(TextServiceCall(#NTX_FILL,handle,$7FFFFFFFFFFFFFF8,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  Check(TextServiceCall(#NTX_FILL,handle,$200080,0),#NTX_ERR_ARGS)
  Check(TextServiceCall(#NTX_FILL,handle,base,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  *fill\x=-1 : *fill\y=0 : *fill\width=1 : *fill\height=1 : *fill\cell=32
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  *fill\x=0 : *fill\width=0
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  *fill\width=w+1
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  *fill\width=1 : *fill\cell=$100000000
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  *write\x=0 : *write\y=0 : *write\width=1 : *write\height=2 : *write\cells=$200100 : *write\stride=$7FFFFFFFFFFFFFFF
  Check(TextServiceCall(#NTX_WRITE,handle,$200080,SizeOf(NativeTextWriteRequest)),#NTX_ERR_ARGS)
  *write\stride=1 : *write\cells=base
  Check(TextServiceCall(#NTX_WRITE,handle,$200080,SizeOf(NativeTextWriteRequest)),#NTX_ERR_ARGS)
  *write\cells=$200101
  Check(TextServiceCall(#NTX_WRITE,handle,$200080,SizeOf(NativeTextWriteRequest)),#NTX_ERR_ARGS)
  *write\cells=$7FFFFFFFFFFFFFFC
  Check(TextServiceCall(#NTX_WRITE,handle,$200080,SizeOf(NativeTextWriteRequest)),#NTX_ERR_ARGS)
  *cursor\x=0 : *cursor\y=0 : *cursor\style=4
  Check(TextServiceCall(#NTX_CURSOR,handle,$200080,SizeOf(NativeTextCursorRequest)),#NTX_ERR_ARGS)
  *scroll\top=0 : *scroll\bottom=h+1 : *scroll\lines=1 : *scroll\cell=32
  Check(TextServiceCall(#NTX_SCROLL,handle,$200080,SizeOf(NativeTextScrollRequest)),#NTX_ERR_ARGS)
 ElseIf phase=2
  Check(TextServiceEnter(),#NTX_ERR_BUSY)
  Check(TextServiceCall(#NTX_OPEN,0,$200040,SizeOf(NativeTextOpenRequest)),#NTX_ERR_BUSY)
  Check(TextServiceCall(#NTX_CLOSE,99,0,0),#NTX_ERR_STATE)
  Check(TextServiceCall(#NTX_CLOSE,handle,$200080,0),#NTX_ERR_ARGS)
  Check(TextServiceCall(#NTX_CLOSE,handle,0,0),0)
  Check(TextServiceCall(#NTX_CLOSE,handle,0,0),#NTX_ERR_STATE)
  second=TextServiceCall(#NTX_OPEN,0,$200040,SizeOf(NativeTextOpenRequest)) : Check(second,2)
  Check(TextServiceCall(#NTX_CLOSE,handle,0,0),#NTX_ERR_STATE)
  Check(TextServiceLeave(),0) : Check(zenTextApplication,0)
  Check(TextServiceEnter(),0)
  handle=TextServiceCall(#NTX_OPEN,0,$200040,SizeOf(NativeTextOpenRequest)) : Check(handle,3)
 ElseIf phase=3
  PokeQ(#ZEN_DISPLAY+$48,1) : WaitFrame()
  *fill\x=0 : *fill\y=0 : *fill\width=1 : *fill\height=1 : *fill\cell=65
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),#NTX_ERR_GEOMETRY)
  Check(TextServiceCall(#NTX_CLOSE,handle,0,0),0)
  handle=TextServiceCall(#NTX_OPEN,0,$200040,SizeOf(NativeTextOpenRequest)) : Check(handle,2)
  w=PeekQ($200040) : h=PeekQ($200048)
  PokeQ($600010,w) : PokeQ($600018,h)
  *fill\x=w-1 : *fill\y=h-1 : *fill\width=1 : *fill\height=1 : *fill\cell=$FFFE2500
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),0)
 ElseIf phase=9
  *fill\x=w-1 : *fill\y=h-1 : *fill\width=1 : *fill\height=1 : *fill\cell=$02010058
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),0)
  PokeQ(#ZEN_DISPLAY+$48,0) : WaitFrame()
  Check(TextServiceCall(#NTX_CLOSE,handle,0,0),0)
  PokeQ(#ZEN_DISPLAY+$48,1) : WaitFrame()
 ElseIf phase=4
  PokeQ(#ZEN_TEXT+$48,0)
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),#NTX_ERR_PROVIDER)
  Check(TextServiceLeave(),#NTX_ERR_PROVIDER)
  Check(TextServiceEnter(),#NTX_ERR_PROVIDER)
  PokeQ($600008,ztTestCount) : ProcedureReturn 42
 ElseIf phase=6
  *fill\x=0 : *fill\y=0 : *fill\width=w : *fill\height=18 : *fill\cell=65
  Check(TextServiceCall(#NTX_FILL,handle,$200080,SizeOf(NativeTextFillRequest)),#NTX_ERR_ARGS)
  *write\x=0 : *write\y=0 : *write\width=w : *write\height=18 : *write\cells=$200100 : *write\stride=w
  Check(TextServiceCall(#NTX_WRITE,handle,$200080,SizeOf(NativeTextWriteRequest)),#NTX_ERR_ARGS)
 ElseIf phase=8
  Check(TextServiceCall(#NTX_PRESENT,handle,0,0),#NTX_ERR_TIMEOUT)
 EndIf
 For n=0 To w*h-1 : PokeL($610000+n*4,PeekL(base+n*4)) : Next
 PokeQ($600030,PeekQ(#ZEN_TEXT+$78)) : PokeQ($600038,PeekQ(#ZEN_TEXT+$80))
 PokeQ($600040,PeekQ(#ZEN_TEXT+$88)) : PokeQ($600048,PeekQ(#ZEN_TEXT+$98))
 WaitFrame()
 Check(TextServiceLeave(),0) : Check(zenTextApplication,0) : Check(ZentajiTextOwned(),1)
 Check(TextServiceCall(#NTX_CLOSE,handle,0,0),#NTX_ERR_STATE)
 If phase=10 : Check(UartAttach(),1) : UartWrite(89) : WaitFrame() : EndIf
 PokeQ($600008,ztTestCount)
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    ap.add_argument('--case');a=ap.parse_args()
    cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zasm_ref as A
    import zexpack
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    checked=0
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-text-api-') as tmp:
        td=Path(tmp);src=td/'text.zentaji';out=td/'text.zex';src.write_text(SOURCE,encoding='utf-8')
        run([cc,'--compile',src,'-o',out])
        ref=A.Asm();org,body=ref.assemble(Path(str(out)+'.asm').read_text(encoding='utf-8-sig'))
        assert out.read_bytes()==zexpack.header(org,org,body)+body
        image,_,_,_=B.pack(out.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(out)+'.zmap').read_text(encoding='utf-8-sig')))
        for phase,name in enumerate(('drawing','invalid-requests','lifetime','geometry','damaged-owner','no-grid','bounded-write','origin-ring','present-timeout','shrink-clear-growth','diagnostic-resume')):
            if a.case and a.case!=name:continue
            modes=[(1,1,60000)] if phase==5 else ([(320,160,1000)] if phase==8 else ([(1920,1080,60000)] if phase==6 else [(320,160,60000),(640,480,60000)]))
            m=I.Fixture(ram_size=8<<20,cores=2,display_modes=modes);m.load_image(image)
            struct.pack_into('<Q',m.ram,0x700000,phase)
            capacity=(max((w//fw)*(h//fh)*4 for w,h,_ in modes for fw,fh in [(8,16),(12,24),(16,32)])+4095)&-4096
            base=(8<<20)-(1<<20)-65536-capacity
            struct.pack_into('<I',m.ram,base-4,0x12345678);struct.pack_into('<I',m.ram,base+capacity,0x76543210)
            assert not L.capture(m,str(td))
            m=runner.execute(m,4000000,td);c=m.cores[0];frames=list(m.frames)
            assert c.state=='HALTED' and c.exit==42,(name,c.state,c.exit,struct.unpack_from('<2q',m.ram,0x600000))
            assert struct.unpack_from('<Q',m.ram,0x600000)[0]==0,(name,struct.unpack_from('<Q',m.ram,0x600000),struct.unpack_from('<2q',m.ram,0x600100))
            assert struct.unpack_from('<Q',m.ram,0x600008)[0]>=4,name
            assert struct.unpack_from('<I',m.ram,base-4)[0]==0x12345678,name
            assert struct.unpack_from('<I',m.ram,base+capacity)[0]==0x76543210,name
            if phase not in (4,5):
                w,h,b,cap=struct.unpack_from('<4q',m.ram,0x600010)
                assert (b,cap)==(base,capacity),name
                assert (w,h)==((80,30) if phase in (3,9) else ((240,67) if phase==6 else (40,10))),name
                expected=[0x70020]*(w*h)
                if phase in (0,7):
                    for y in range(1,5):expected[y*w+1:y*w+6]=[0x2010058]*5
                    expected[2*w+2:2*w+5]=[0x4030041+i for i in range(3)]
                    expected[3*w+2:3*w+5]=[0x4030041+i for i in range(5,8)]
                    before=expected[:]
                    for y in range(1,5):expected[y*w:(y+1)*w]=before[(y+1)*w:(y+2)*w] if y<4 else [0x605002e]*w
                    before=expected[:]
                    for y in range(2,6):expected[y*w:(y+1)*w]=before[(y-1)*w:y*w] if y>2 else [0x807002d]*w
                    assert struct.unpack_from('<4q',m.ram,0x600030)==(4,3,2,3 if phase==7 else 0),name
                    assert bytes(m.serial[0].out)==b'Z',name
                    if phase==7:expected=expected[-3*w:]+expected[:-3*w]
                if phase==3:expected[-1]=0xfffe2500
                got=list(struct.unpack_from('<%dI'%(w*h),m.ram,0x610000))
                assert got==expected,(name,[(n,x,y) for n,(x,y) in enumerate(zip(got,expected)) if x!=y][:8])
                cleared=[0x70020]*(w*h)
                if phase==10:
                    cleared[0]=0x70059
                    assert bytes(m.serial[0].out)==b'Y' and m.fields['textcursor'][0]==1 and m.fields['textcursor'][1]==0,name
                assert list(struct.unpack_from('<%dI'%(w*h),m.ram,base))==cleared,name
                assert m.fields['textmeta'][1]==0 and m.fields['text'][3]==0 and m.fields['textmeta'][2]==0x101,name
            if phase==4:assert m.fields['text'][2]==0 and m.fields['textmeta'][0]==1,name
            if phase==5:assert m.fields['textmeta'][0]==0 and m.fields['textmeta'][3]==0,name
            native=run([L.EXE,td/'machine.txt','--max','4000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram,name
            I.assert_same_state(native,m)
            assert m.cores[1].state=='PARKED'
            if phase in (0,3,7,10):
                win=run([zt/('zenwin.exe' if os.name=='nt' else 'zenwin'),td/'machine.txt','--headless','--max','4000000'])
                assert [s for s in win.splitlines() if s.startswith('FRAME ')]==frames,name
            checked+=1;print('PASS native text API '+name+': actual provider/lifetime, independent cells/bounds, full native state/RAM'+(' and exact headless frames' if phase in (0,3,7,10) else ''),flush=True)
    assert checked>0,'no matching case'


if __name__=='__main__':main()
