"""Real Zentaji input, focus/service lifetime and cancellation; no driver mocks."""
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
XIncludeFile "Anvil/Core/input_events.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "Zentaji/Board/memory.pbi"
XIncludeFile "Anvil/Core/memrange.pbi"
XIncludeFile "Anvil/Core/rxbreak.pbi"
XIncludeFile "Zentaji/Board/input.pbi"
Global ziTestReady.i,ziTestCount.i
Global Dim report.q[24]
Procedure TestWait(delta.i)
 Protected end.i=Ticks()+delta
 While Ticks()<end : HwPromptIdleWait() : Wend
EndProcedure
Procedure.i TestPoll(context.i)
 Protected n.i,i.i,rc.i
 For n=1 To 128
  rc=InputServiceCall(#NUI_POLL,context,$200080,SizeOf(NativeInputEvent))
  If rc<>1 : ProcedureReturn rc : EndIf
  If NativeInputEventValid($200080)<>1 : ProcedureReturn 999 : EndIf
  For i=0 To 40 Step 8 : PokeQ($220000+ziTestCount*48+i,PeekQ($200080+i)) : Next
  ziTestCount=ziTestCount+1
 Next
 ProcedureReturn 998
EndProcedure
Procedure.i Main(table.i,source.i,context.i)
 Protected phase.i=PeekQ($700000),handle.i,i.i,rc.i
 If ZentajiMemoryBind(context)<>1 : ProcedureReturn 1 : EndIf
 If ZentajiMemoryTextInit(table)<>1 : ProcedureReturn 2 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(2000)<>1 Or UartAttach()<>1 Or ZentajiInputStart()<>1 : ProcedureReturn 3 : EndIf
 ; Seed an unclaimed lane; neither admission nor polling may change rumble.
 PokeQ(#ZEN_INPUT+$120,$12345678)
 report[0]=InputServiceCall(#NUI_QUERY,0,$200100,SizeOf(NativeInputApi))
 report[1]=InputServiceCall(#NUI_QUERY,0,0,SizeOf(NativeInputApi))
 report[2]=InputServiceCall(#NUI_QUERY,0,context,SizeOf(NativeInputApi))
 report[3]=InputServiceCall(#NUI_QUERY,0,zenMemoryTextBase,SizeOf(NativeInputApi))
 report[4]=InputServiceCall(#NUI_QUERY,0,$7FFFFFFFFFFFFFE0,SizeOf(NativeInputApi))
 report[5]=InputServiceCall(#NUI_QUERY,0,$200101,SizeOf(NativeInputApi))
 report[6]=InputServiceCall(#NUI_QUERY,0,$200100,SizeOf(NativeInputApi)-1)
 If phase=1 : ziTestReady=1 : TestWait(500000) : EndIf
 If InputServiceEnter()<>0 : ProcedureReturn 4 : EndIf
 PokeQ($200000,3)
 handle=InputServiceCall(#NUI_OPEN,0,$200000,SizeOf(NativeInputOpenRequest))
 If handle<>1 : ProcedureReturn 5 : EndIf
 report[7]=handle : report[8]=InputFocusGeneration()
 report[9]=InputServiceCall(#NUI_OPEN,0,$200000,SizeOf(NativeInputOpenRequest))
 report[10]=InputServiceCall(#NUI_POLL,handle+1,$200080,SizeOf(NativeInputEvent))
 report[11]=InputServiceCall(#NUI_POLL,handle,$200081,SizeOf(NativeInputEvent))
 If phase=1 : ziTestReady=2 : Else : ziTestReady=1 : EndIf
 TestWait(500000)
 If phase=3
  PokeQ(#ZEN_INPUT+$B0,1)
  report[12]=InputServiceCall(#NUI_POLL,handle,$200080,SizeOf(NativeInputEvent))
  report[13]=InputServiceLeave() : report[14]=InputServiceState()
  PokeQ(#ZEN_INPUT+$B0,0)
  report[15]=InputServiceRecover() : report[16]=InputServiceState()
  ProcedureReturn 42
 ElseIf phase=4
  PokeQ(#ZEN_DISPLAY+$48,1) : TestWait(2000000)
 ElseIf phase=6
  ZentajiInputKeys() : report[12]=PeekQ(#ZEN_INPUT+$48)
  report[13]=InputServiceCall(#NUI_CLOSE,handle,0,0)
  report[14]=PeekQ(#ZEN_INPUT+$48) : report[15]=ziBlocked[4]
  ProcedureReturn 42
 EndIf
 report[12]=TestPoll(handle)
 If phase=2
  report[13]=ziBlocked[4] : ziTestReady=2 : TestWait(500000)
  report[14]=TestPoll(handle)
 ElseIf phase=5
  report[13]=InputServiceCall(#NUI_FLUSH,handle,0,0)
  report[14]=TestPoll(handle)
 ElseIf phase=7
  report[13]=InputServiceCall(#NUI_CLOSE,handle,0,0)
  ZentajiInputPromptResume() : ziTestReady=2 : TestWait(500000)
  report[14]=OutBreakByte() : report[15]=OutBreakByte()
  ProcedureReturn 42
 ElseIf phase=9
  report[13]=InputServiceCall(#NUI_CLOSE,handle,0,0)
  ZentajiInputPromptResume() : ziTestReady=2 : TestWait(500000)
  report[14]=AnvilPromptInput(#APS_KEYBOARD) : report[15]=InputEventsQueued()
  report[16]=OutBreakByte() : report[17]=OutBreakByte()
  ProcedureReturn 42
 EndIf
 report[17]=ziTestCount
 report[18]=InputServiceCall(#NUI_CLOSE,handle,0,0)
 report[19]=InputServiceCall(#NUI_POLL,handle,$200080,SizeOf(NativeInputEvent))
 report[20]=InputServiceLeave() : report[21]=InputServiceState()
 report[22]=InputFocus() : report[23]=ZentajiInputHardwareOwned()
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);ap.add_argument('--case');a=ap.parse_args()
    cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zasm_ref as A
    import zexpack
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-input-') as tmp:
        td=Path(tmp);src=td/'input.zentaji';image=td/'input.zex';src.write_text(SOURCE,encoding='utf-8')
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();org,body=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,body)+body
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        checked=0
        for phase,name in enumerate(('events','held-fence','hardware-overflow','quarantine-recovery','geometry-change','explicit-flush','bounded-pump','command-cancel','numlock-release','queued-prompt')):
            if a.case and a.case!=name:continue
            m=I.Fixture(ram_size=8<<20,cores=2,display_modes=[(320,160,60000),(640,480,60000)]);m.load_image(wrapped)
            struct.pack_into('<Q',m.ram,0x700000,phase);m.ram[:32]=b'\xCC'*32
            assert not L.capture(m,str(td));script=[];seen=set()
            m.observe_ram=ref.sym['GLOBAL_ZITESTREADY']
            m.read_witness=(I.DEV+0xA0080,I.DEV+0xA00A8,tuple(ref.sym['GLOBAL_'+name] for name in ('ZIFENCING','ZIOWNED','GINGEN','NUIGENERATION')))
            def operator(observed):
                core=observed.cores[0]
                ready=struct.unpack_from('<Q',observed.ram,ref.sym['GLOBAL_ZITESTREADY'])[0]
                if ready==0 or ready in seen:return
                seen.add(ready);tick=max(observed.time,core.cr[I.CR['CYCLE']])+100
                def feed(kind,*fields):
                    m.input_feed(tick,kind,*fields);script.append((tick,kind,fields))
                if phase==0:
                    for fields in [(4,1,0,0,97),(4,1,0,1,97),(4,0,0,0,0),(80,1,0,0,0),(80,0,0,0,0),(224,1,2,0,0),(6,1,2,0,3),(6,0,2,0,0),(224,0,0,0,0),(5,1,0,0,233),(5,0,0,0,0)]:feed('key',*fields)
                    feed('mouse',-5,200,21,-2)
                    feed('pad',0,1,1,0,0,0,0,0,0);feed('pad',0,1,2,0,0,0,0,0,0)
                elif phase==1:
                    fields=[(4,1,0,0,97),(225,1,1,0,0)] if ready==1 else [(4,1,1,1,65),(4,0,1,0,0),(225,0,0,0,0),(5,1,0,0,98),(5,0,0,0,0)]
                    for f in fields:feed('key',*f)
                    feed('mouse',10 if ready==1 else 12,20 if ready==1 else 25,1 if ready==1 else 2,9 if ready==1 else 3)
                elif phase==2:
                    fields=[(4,1,0,1,97)]*257 if ready==1 else [(4,0,0,0,0),(5,1,0,0,98),(5,0,0,0,0)]
                    for f in fields:feed('key',*f)
                elif phase==6:
                    for _ in range(100):feed('key',4,1,0,0,0)
                elif phase==7 and ready==2:
                    feed('key',224,1,2,0,0);feed('key',6,1,2,0,3)
                elif phase==8:
                    for fields in [(89,1,0,0,0),(89,0,32,0,0),(90,1,0,0,0),(90,1,32,1,50),(90,0,32,0,0)]:feed('key',*fields)
                elif phase==9 and ready==2:
                    feed('key',20,1,0,0,113);feed('key',20,0,0,0,0)
            m=runner.operate(m,operator,3000000,td);c=m.cores[0]
            for row in m.read_witness:
                fencing,owned,generation,delivered=row[5:]
                assert not owned or fencing or generation==delivered,('mouse consumed before cancellation',name,row)
            if phase in (0,1):assert m.read_witness,('missing native mouse read observations',name)
            assert c.state=='HALTED' and c.r[1]==42,(name,c.state,c.r[1])
            report=struct.unpack_from('<24q',m.ram,ref.sym['GLOBAL_REPORT'])
            assert report[:12]==(0,-22400,-22400,-22400,-22400,-22400,-22400,1,report[8],-22402,-22401,-22400),(name,report)
            assert struct.unpack_from('<4iQ',m.ram,0x200100)==(0x4E495331,1,0,32,3)
            assert m.ram[:32]==b'\xCC'*32 and m.fields['input'][5]==0x12345678 and m.fields['input'][1]==0
            if phase in (0,1,2,4,5,8):
                assert report[18:]==(0,-22401,0,0,0,1),(name,report)
                trace=[struct.unpack_from('<8iq2i',m.ram,0x220000+i*48) for i in range(report[17])]
                events=[row[:8] for row in trace]
                for row in trace:assert row[8]>0 and row[9]>=report[8] and row[10]==0,(name,row)
                text=lambda code,mods=0:(1,1,code,mods,-1,-1,0,0)
                key=lambda code,value,mods=0:(7,1,code,mods,-1,-1,0,value)
                if phase==0:
                    typed=[text(97),text(97),(2,1,4,0,-1,-1,0,0),(3,1,4,0,-1,-1,0,0),(2,1,10,2,-1,-1,0,0)]
                    device=[key(4,1),key(4,0),key(80,1),key(80,0),key(224,1,2),key(6,1,2),key(6,0,2),key(224,0),key(5,1),key(5,0),(5,4,0,0,0,159,5,0),(6,4,0,0,0,159,5,-2)]
                    expected=[]
                    for i in range(max(len(typed),len(device))):
                        if i<len(typed):expected.append(typed[i])
                        if i<len(device):expected.append(device[i])
                    assert events==expected,(name,events,expected)
                    assert m.fields['input'][3] & 12==12 and m.fields['input'][4]==2
                elif phase==1:
                    assert events==[text(98),key(5,1),key(5,0),(5,4,0,0,12,25,2,0),(6,4,0,0,12,25,2,3)],events
                elif phase==2:
                    assert events==[(4,1,2,0,-1,-1,0,0),text(98),key(5,1),key(5,0)] and report[13]==1,(events,report)
                elif phase==4:assert events==[(4,1,4,0,-1,-1,0,0)] and report[12]==-22401,(events,report)
                elif phase==5:assert events==[(4,1,7,0,-1,-1,0,0)],events
                elif phase==8:
                    assert events==[(2,1,7,0,-1,-1,0,0),key(89,1),(3,1,7,0,-1,-1,0,0),key(89,0),(2,1,12,0,-1,-1,0,0),key(90,1),(3,1,12,0,-1,-1,0,0),key(90,0),text(50)],events
            elif phase==3:assert report[12:17]==(-22404,-22404,2,0,0),report
            elif phase==6:assert report[12:16]==(68,0,0,1),report
            elif phase==7:assert report[13:16]==(0,3,-1),report
            elif phase==9:assert report[13:18]==(0,256,2,113,-1),report
            cfg=td/'machine.txt'
            out=run([L.EXE,cfg,'--max','3000000','--ram',td/'final.bin'])
            assert (td/'final.bin').read_bytes()==m.ram,name
            I.assert_same_state(out,m)
            assert m.cores[1].state=='PARKED'
            checked+=1
            print('PASS input '+name+': actual hardware/shared NUI/focus/cancellation, independent event/bounds oracle, complete native CPU/RAM/device digest',flush=True)
        assert checked,'no input component case matched'


if __name__=='__main__':main()
