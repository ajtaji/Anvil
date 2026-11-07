"""Actual shared ReadLine, parser, scheduler and message log on Zentaji."""
import argparse
from collections import deque
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
#CAP_TOUCH=0
#CAP_PWM=0
#CAP_NET=0
IncludeFile "Zentaji/Board/console.pbi"
IncludeFile "Anvil/Core/state.pbi"
IncludeFile "Anvil/Core/input_events.pbi"
IncludeFile "Anvil/Core/text_edit.pbi"
Global gScreen.i,gKbdH.i,gMouseTried.i,gBootTicks.i
Global testScreen.i,testWork.i,testClaims.i,testLogLines.i,testReports.i
Procedure MouseTick() : testWork=testWork+1 : EndProcedure
Procedure TouchTick() : EndProcedure
Procedure MouseTryAttach() : gMouseTried=1 : EndProcedure
Procedure ScreenServiceTick()
 testScreen=testScreen+1
 If testReports And testScreen=1 : PrintN("background notice") : EndIf
EndProcedure
Procedure NetDhcpTick() : testWork=testWork+1 : EndProcedure
Procedure FanTick() : testWork=testWork+1 : EndProcedure
Procedure HwTempSampleTick() : EndProcedure
Procedure NetConsoleRearm() : EndProcedure
Procedure NetConsolePump() : testWork=testWork+1 : EndProcedure
Procedure NetConsoleLlTick() : EndProcedure
Procedure TcpTick() : EndProcedure
Procedure NetConsoleClaimLocal() : testClaims=testClaims+1 : EndProcedure
Procedure.i NetConsoleGetc() : ProcedureReturn -1 : EndProcedure
Procedure.i KeyboardChar() : ProcedureReturn 0 : EndProcedure
Procedure.i OutBreak() : ProcedureReturn 0 : EndProcedure
Procedure.i TestWifi(op.i) : testWork=testWork+1 : ProcedureReturn 0 : EndProcedure
Procedure TestLogLine(*text,n.i,no.i) : testLogLines=testLogLines+1 : EndProcedure
IncludeFile "Anvil/Core/messages.pbi"
IncludeFile "Anvil/Core/parse.pbi"
Procedure.i Main(scenario.i)
 Dim ev.a[#AIE_EVSZ]
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(2000)<>1 Or UartAttach()<>1 : ProcedureReturn 1 : EndIf
 WifiMaintenanceBind(@TestWifi)
 *gMsgLineHook=@TestLogLine
 MessagesStart()
 ; The byte translator intentionally ignores serial Tab. Model a normalized
 ; keyboard Tab through the production event API to test editor refusal.
 If scenario=2
  InputFocusSet(#AIF_COMMAND_LINE)
  If InputEventInit(@ev[0],#AIE_KEY_DOWN,#AIS_TOUCH_KEYBOARD,#AIK_TAB,0)<>#AIE_OK : ProcedureReturn 13 : EndIf
  If InputEventsPush(@ev[0])<>#AIE_OK : ProcedureReturn 14 : EndIf
 EndIf
 If scenario=4 Or scenario>=20 : testReports=1 : EndIf
 Print("pmf> ")
 ReadLine()
 If scenario=0
  If gLineLen<>2 Or gLine[0]<>97 Or gLine[1]<>67 : ProcedureReturn 2 : EndIf
  Print("pmf> ") : ReadLine()
  gPos=0 : gWordAt=0 : SkipWord() : gWordLen=gPos
  If WordIs("hello")<>1 Or WordIs("hell")<>0 : ProcedureReturn 3 : EndIf
  If ParseHex()<>$FEDCBA9876543210 Or gParseOk<>1 : ProcedureReturn 4 : EndIf
 ElseIf scenario=1
  If TextEditCancelled()<>1 Or gLineLen<>0 : ProcedureReturn 5 : EndIf
 ElseIf scenario=2
  If gLineLen<>2 Or gLine[0]<>65 Or gLine[1]<>66 Or MessagesTotal()<>1 Or testLogLines<>2 Or gMsgKept<>2 : ProcedureReturn 6 : EndIf
 ElseIf scenario=3
  If gLineLen<>#LINE_MAX Or gLineTrunc<>1 : ProcedureReturn 7 : EndIf
 ElseIf scenario=4
  If gLineLen<>32 Or testWork<2 Or testScreen<2 Or MessagesTotal()<>1 : ProcedureReturn 8 : EndIf
 ElseIf scenario>=20
  If gLineLen<>2 Or gLine[0]<>79 Or gLine[1]<>75 Or MessagesTotal()<>1 : ProcedureReturn 9 : EndIf
  If scenario=21 And (testWork<100 Or testScreen<10 Or AnvilCpuUsagePercent()<0) : ProcedureReturn 10 : EndIf
 EndIf
 If UartMessageDepth()<>0 Or UartMessageLost()<>0 Or ZentajiConsoleDrain()<>1 : ProcedureReturn 11 : EndIf
 If scenario=0 And testClaims<>29 : ProcedureReturn 12 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    import zen_sleep_check as S
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    incoming={0:b'ab\x08C\r\nHELLO FEDCBA9876543210\r',1:b'Hi\x03',2:b'AB\r',3:b'x'*1105+b'\r',4:b'x'*32+b'\r',20:b'OK\r',21:b'OK\r'}
    expected={0:b'pmf> ab\x08 \x08C\r\npmf> HELLO FEDCBA9876543210\r\n',1:b'pmf> Hi\r\n',2:b'pmf> AB\r\n',4:b'pmf> '+b'x'*32+b'\r\n',20:b'pmf> OK\r\n',21:b'pmf> OK\r\n'}
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-zen-readline-') as tmp:
        td=Path(tmp);src=td/'prompt.zentaji';image=td/'prompt.zex';src.write_text(SOURCE,encoding='utf-8')
        out=run([cc,'--compile',src,'-o',image]);assert 'is READ but never' not in out,out
        ref=A.Asm();org,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        def machine(scenario):
            m=I.Machine(ram_size=1<<20,display_modes=[(1,1,60000)]);m.load_image(image.read_bytes());c=m.cores[0];c.r[1]=scenario;c.r[255]=0xF0000
            for reg in range(128,253):c.r[reg]=0x10000+reg*13
            for reg in range(32,64):c.v[reg]=sum((reg*100+j)<<(64*j) for j in range(8))
            m.serial[0].incoming=[(200000000 if scenario==21 else 0,b) for b in incoming[scenario]]
            return m
        def states(out):return [s for s in out.splitlines() if s.startswith('STATE ')]
        def match(m,native,scenario):
            c=m.cores[0];assert c.state=='HALTED' and c.r[1]==42,(scenario,c.state,c.r[1],{k:int.from_bytes(m.ram[ref.sym['GLOBAL_'+k.upper()]:ref.sym['GLOBAL_'+k.upper()]+8],'little') for k in ['gLineLen','gMsgNo','gMsgKept','testLogLines']},bytes(m.serial[0].out)[-600:])
            assert (td/'final.bin').read_bytes()==m.ram,scenario
            assert states(native)[0][6:].split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1],scenario
            output=bytes(m.serial[0].out)
            if scenario==3:
                assert output.startswith(b'pmf> '+b'x'*1100+b'\r\n!! that line was longer than 1100 characters.'),output[-600:]
                assert b'DROPPED as you typed' in output and output.endswith(b'line echoed above. Nothing has been done with it yet.\r\n'),output[-600:]
            else:assert output==expected[scenario],(scenario,output,expected[scenario])
            if scenario==2:
                at=ref.sym['GLOBAL_GMSGTEXT'];assert m.ram[at:at+14]==b'input error 7:',bytes(m.ram[at:at+32])
            serial=[s.split(' ',1)[1] for s in native.splitlines() if s.startswith('SERIAL0 ')]
            assert serial[0]==output.hex().upper(),scenario
            assert c.r[128:253]==[0x10000+r*13 for r in range(128,253)] and c.r[255]==0xF0000,scenario
            assert c.v[32:]==[sum((r*100+j)<<(64*j) for j in range(8)) for r in range(32,64)],scenario
        for scenario in range(5):
            m=machine(scenario);assert not L.capture(m,str(td));native=run([L.EXE,td/'machine.txt','--max','4000000','--ram',td/'final.bin']);m.run(4000000);match(m,native,scenario)
        print('PASS 5 real ReadLine/parser/input/editor/scheduler/message-log cases: cross-line CRLF, exact editing output, case-insensitive word/full-width hex parse, Ctrl-C, tab refusal off the prompt, bounded truncation and fair background service')
        results=[]
        for scenario in (20,21):
            m=machine(scenario);assert not L.capture(m,str(td));rec=td/'recorded.txt'
            live,wall,cpu=S.run([str(zt/('zenwin.exe' if os.name=='nt' else 'zenwin')),str(td/'machine.txt'),'--headless','--live','--mute','--record',str(rec),'--max','4000000'],timeout=30)
            native=run([L.EXE,rec,'--max','4000000','--ram',td/'final.bin']);assert states(live)==states(native)
            m.clock_samples=deque((int(s.split()[1][1:],16),int(s.split()[2]),int(s.split()[3]) if len(s.split())>3 else -1) for s in rec.read_text().splitlines() if s.startswith('clock '))
            m.clock_complete=True;m.run(4000000);match(m,native,scenario);results.append((wall,cpu))
        wall=results[1][0]-results[0][0];cpu=max(0,results[1][1]-results[0][1]);assert wall>=1.8 and cpu<0.4,(wall,cpu)
        print(f'PASS actual shared ReadLine live: startup-adjusted wall={wall:.6f}s cpu={cpu:.6f}s; active services/messages, real timer/WFI, exact recorded native/twin replay')


if __name__=='__main__':main()
