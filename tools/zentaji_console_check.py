"""Actual serial-0 transport and shared input/editor on Zentaji hardware."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]

SOURCE=r'''
IncludeFile "Zentaji/Board/console.pbi"
IncludeFile "Anvil/Core/state.pbi"
IncludeFile "Anvil/Core/input_events.pbi"
IncludeFile "Anvil/Core/text_edit.pbi"
Procedure.i ScreenProportionalAdvance(previous.i,c.i) : ProcedureReturn 8*65536 : EndProcedure
IncludeFile "Anvil/Core/console_grid.pbi"
Procedure.i PrepareIdle()
  PokeQ(#ZEN_IDLE_INTC+$120,3)
  PokeQ(#ZEN_IDLE_INTC+$F008,2)
  ProcedureReturn ZentajiPromptIdlePrepare(2000)
EndProcedure
Global testDrained.i,testDrainCalls.i
Procedure TestConsoleDrain()
 Protected c.i
 testDrainCalls=testDrainCalls+1
 Repeat
  c=UartMessageGet()
  If c<0 : Break : EndIf
  PokeA($D0000+testDrained,c) : testDrained=testDrained+1
 ForEver
EndProcedure
Procedure TestConsoleHoldDrain() : testDrainCalls=testDrainCalls+1 : EndProcedure
Procedure.i EditedLine()
  Dim ev.a[#AIE_EVSZ]
  Protected c.i,kind.i,rc.i
  TextEditBegin()
  While TextEditDone()=0
    c=UartRead()
    If c<0 : ProcedureReturn 0 : EndIf
    If InputFeedByte(#AIS_PHYSICAL,c)<>#AIE_OK : ProcedureReturn 0 : EndIf
    While InputEventsPop(@ev[0])<>0
      kind=PeekL(@ev[0]+#AIE_EV_KIND)
      If kind=#AIE_TEXT
        rc=TextEditInsert(PeekL(@ev[0]+#AIE_EV_CODE))
      ElseIf kind=#AIE_KEY_DOWN
        rc=TextEditKey(PeekL(@ev[0]+#AIE_EV_CODE))
      Else
        rc=#AIE_OK
      EndIf
      If rc<>#AIE_OK : ProcedureReturn 0 : EndIf
    Wend
  Wend
  ProcedureReturn 1
EndProcedure
Procedure.i Main(scenario.i)
  Protected n.i,start.q,c.i
  If scenario=7
    PokeQ(#ZEN_CONSOLE+$60,1)
    PokeQ(#ZEN_CONSOLE+$68,$D0000)
    PokeQ(#ZEN_CONSOLE+$70,8192)
    If UartAttach()<>0 Or UartRunning()<>0 Or (PeekQ(#ZEN_CONSOLE+$08)&16)=0 : ProcedureReturn 1 : EndIf
    ProcedureReturn 42
  EndIf
  If scenario=9
    PokeQ(#ZEN_CONSOLE+$60,1)
    PokeQ(#ZEN_CONSOLE+$20,$31)
    PokeQ(#ZEN_CONSOLE+$40,90)
  EndIf
  If scenario=11
    If UartInitClk(0,123)<>0 Or UartRunning()<>0 : ProcedureReturn 2 : EndIf
    If UartInitClk(115200,TickHz())<>1 Or PeekQ(#ZEN_CONSOLE+$60)<>115200 : ProcedureReturn 3 : EndIf
    If UartInit(-1)<>0 Or PeekQ(#ZEN_CONSOLE+$60)<>115200 : ProcedureReturn 4 : EndIf
    ProcedureReturn 42
  EndIf
  If UartAttach()<>1 Or UartRunning()<>1 : ProcedureReturn 5 : EndIf
  If scenario=22
    UartMirror(1) : UartAuxMirror(1)
    UartScreenStyle(#UART_SCREEN_STYLE_PROMPT) : UartWrite(65)
    UartScreenStyle(#UART_SCREEN_STYLE_NORMAL) : UartWrite(0) : UartWrite(255)
    UartMessageSetDrain(@TestConsoleDrain) : UartMessageBegin() : UartWrite(66) : UartWriteNl() : UartMessageEnd()
    If testDrained<>3 Or PeekA($D0000)<>66 Or UartMirrorCount()<>3 Or (uart_auxHead-uart_auxTail)<>3 : ProcedureReturn 150 : EndIf
    If UartMirrorGet()<>65 Or UartMirrorReadStyle()<>1 : ProcedureReturn 151 : EndIf
    If UartMirrorGet()<>0 Or UartMirrorReadStyle()<>0 : ProcedureReturn 152 : EndIf
    If UartMirrorGet()<>255 Or UartMirrorReadStyle()<>0 Or UartMirrorGet()<>-1 : ProcedureReturn 153 : EndIf
    If UartAuxGet()<>65 Or UartAuxGet()<>0 Or UartAuxGet()<>255 Or UartAuxGet()<>-1 : ProcedureReturn 154 : EndIf
  ElseIf scenario=23
    UartMirror(1) : UartAuxMirror(1)
    For n=0 To 8192 : UartWrite(n&255) : Next
    If UartMirrorCount()<>8191 Or (uart_auxHead-uart_auxTail)<>8191 Or UartMirrorLost()<>2 Or uart_auxLost<>2 : ProcedureReturn 155 : EndIf
    For n=0 To 8190
      If UartMirrorGet()<>(n&255) Or UartAuxGet()<>(n&255) : ProcedureReturn 156 : EndIf
    Next
  ElseIf scenario=24
    UartMirror(1) : UartAuxMirror(1)
    If UartInit(1)<>1 : ProcedureReturn 157 : EndIf
    For n=1 To 4096 : PokeQ(#ZEN_CONSOLE+$40,85) : Next
    UartWrite(33)
    If UartDropped()<>1 Or UartMirrorCount()<>0 Or (uart_auxHead-uart_auxTail)<>0 : ProcedureReturn 158 : EndIf
  ElseIf scenario=25
    ConGridInit(6,3) : UartMirror(1) : UartMirrorSetDrain(@ConMirrorDrain)
    For n=0 To 10000 : UartWrite(65) : Next
    ConDrainRing()
    If UartMirrorLost()<>0 Or UartMirrorCount()<>0 Or UartDropped()<>0 : ProcedureReturn 159 : EndIf
    For n=0 To 5
      If ConGridCell(0,n)<>65 Or ConGridCell(1,n)<>65 : ProcedureReturn 160 : EndIf
    Next
    If ConGridCell(2,4)<>65 Or ConGridCell(2,5)<>32 Or ConGridCurC()<>5 Or ConGridCurR()<>2 : ProcedureReturn 161 : EndIf
  ElseIf scenario=26
    UartMirror(1) : UartWrite(65) : UartMirror(0) : UartAuxMirror(1) : UartWrite(66)
    If UartMirrorCount()<>0 Or (uart_auxHead-uart_auxTail)<>1 : ProcedureReturn 162 : EndIf
    UartMirror(1) : UartScreenStyle(999) : UartWrite(67)
    If UartMirrorGet()<>67 Or UartMirrorReadStyle()<>0 Or UartAuxGet()<>66 Or UartAuxGet()<>67 : ProcedureReturn 163 : EndIf
    UartAuxMirror(0)
    If (uart_auxHead-uart_auxTail)<>0 Or UartMirrorLost()<>0 Or uart_auxLost<>0 : ProcedureReturn 164 : EndIf
  ElseIf scenario=14
    UartMessageBegin() : UartWrite(65) : UartMessageEnd()
    If UartMessageBytes()<>0 Or UartMessageActive()<>0 Or UartMessageDepth()<>0 : ProcedureReturn 34 : EndIf
  ElseIf scenario=15
    UartMessageSetDrain(@TestConsoleDrain)
    UartMessageBegin() : UartWrite(65) : UartMessageBegin() : UartWrite(66) : UartMessageEnd()
    If UartMessageDepth()<>1 Or testDrainCalls<>0 Or testDrained<>0 : ProcedureReturn 35 : EndIf
    UartWriteNl()
    If testDrainCalls<>1 Or testDrained<>4 Or PeekL($D0000)<>$0A0D4241 : ProcedureReturn 36 : EndIf
    UartMessageEnd() : UartWrite(67)
    If testDrainCalls<>2 Or UartMessageBytes()<>4 Or UartMessageLost()<>0 : ProcedureReturn 37 : EndIf
  ElseIf scenario=16
    UartMessageSetDrain(@TestConsoleHoldDrain) : UartMessageBegin()
    For n=1 To 8200 : UartWrite(n&255) : Next
    UartMessageEnd()
    If UartMessageBytes()<>8200 Or UartMessageLost()<>9 Or testDrainCalls<1 : ProcedureReturn 38 : EndIf
    For n=1 To 8191
      If UartMessageGet()<>(n&255) : ProcedureReturn 39 : EndIf
    Next
    If UartMessageGet()<>-1 : ProcedureReturn 40 : EndIf
  ElseIf scenario=17
    UartMessageSetDrain(@TestConsoleDrain) : UartMessageBegin() : UartWrite(66)
    UartMessageAbandon() : UartWrite(70) : UartMessageEnd()
    If UartMessageDepth()<>0 Or testDrainCalls<>0 Or UartMessageGet()<>66 : ProcedureReturn 41 : EndIf
  ElseIf scenario=18
    UartMessageSetDrain(@TestConsoleDrain) : UartMessageBegin() : UartWrite(65)
    UartMessageSetDrain(0) : UartWrite(66) : UartMessageEnd()
    If testDrained<>0 Or UartMessageBytes()<>1 Or UartMessageActive()<>0 : ProcedureReturn 147 : EndIf
    UartMessageSetDrain(@TestConsoleDrain) : UartMessageBegin() : UartMessageEnd()
    If testDrained<>1 Or PeekA($D0000)<>65 Or testDrainCalls<>1 : ProcedureReturn 43 : EndIf
  ElseIf scenario=19
    UartMessageSetDrain(@TestConsoleHoldDrain) : UartMessageBegin()
    For n=1 To 7000 : UartWrite(n&255) : Next
    For n=1 To 6000
      If UartMessageGet()<>(n&255) : ProcedureReturn 44 : EndIf
    Next
    For n=7001 To 13000 : UartWrite(n&255) : Next
    UartMessageEnd()
    For n=6001 To 13000
      If UartMessageGet()<>(n&255) : ProcedureReturn 45 : EndIf
    Next
    If UartMessageGet()<>-1 Or UartMessageLost()<>0 Or UartMessageBytes()<>13000 : ProcedureReturn 46 : EndIf
  ElseIf scenario=0
    UartWriteStr("Zentaji café") : UartWriteNl() : UartWrite(0) : UartWrite(255)
    If ZentajiConsoleDrain()<>1 Or UartDropped()<>0 : ProcedureReturn 6 : EndIf
  ElseIf scenario=1
    If UartReadReady()<>1 Or UartReadReady()<>1 Or PeekQ(#ZEN_CONSOLE+$50)<>3 : ProcedureReturn 7 : EndIf
    If UartReadWait(0)<>-1 Or PeekQ(#ZEN_CONSOLE+$50)<>3 : ProcedureReturn 8 : EndIf
    If UartReadWait(1)<>0 Or UartRead()<>127 Or UartReadWait(2)<>255 : ProcedureReturn 9 : EndIf
    If UartReadReady()<>0 Or UartReadWait(-1)<>-1 : ProcedureReturn 10 : EndIf
  ElseIf scenario=2 Or scenario=12 Or scenario=13
    If EditedLine()<>1 : ProcedureReturn 11 : EndIf
    If scenario=2
      If gLineLen<>2 Or gLine[0]<>97 Or gLine[1]<>67 Or TextEditCaret()<>2 Or TextEditCancelled()<>0 : ProcedureReturn 12 : EndIf
    ElseIf scenario=12
      If TextEditCancelled()<>1 Or gLineLen<>0 : ProcedureReturn 13 : EndIf
    Else
      If gLineLen<>1 Or gLine[0]<>65 : ProcedureReturn 14 : EndIf
      If EditedLine()<>1 Or gLineLen<>1 Or gLine[0]<>66 Or UartReadReady()<>0 : ProcedureReturn 15 : EndIf
    EndIf
  ElseIf scenario=3
    If UartRead()<>-1 Or ZentajiConsoleFaults()<>1 : ProcedureReturn 16 : EndIf
  ElseIf scenario=4 Or scenario=20 Or scenario=21
    If PrepareIdle()<>1 : ProcedureReturn 17 : EndIf
    c=UartRead()
    If c<>81 Or ZentajiConsoleFaults()<>0 : ProcedureReturn 18 : EndIf
    If ZentajiPromptIdleRelease()<>1 : ProcedureReturn 19 : EndIf
  ElseIf scenario=5
    If UartInit(1)<>1 : ProcedureReturn 20 : EndIf
    For n=1 To 4096 : PokeQ(#ZEN_CONSOLE+$40,85) : Next
    PokeQ(#ZEN_CONSOLE+$40,1)
    UartWrite(33)
    If UartDropped()<>2 Or PeekQ(#ZEN_CONSOLE+$98)<>1 Or PeekQ(#ZEN_CONSOLE+$58)<>0 : ProcedureReturn 21 : EndIf
    If ZentajiConsoleDrain()<>0 Or ZentajiConsoleFaults()<>1 : ProcedureReturn 22 : EndIf
    UartOff()
    PokeQ(#ZEN_CONSOLE+$40,2)
    If UartDropped()<>2 Or PeekQ(#ZEN_CONSOLE+$98)<>2 : ProcedureReturn 23 : EndIf
  ElseIf scenario=6
    If UartInit(1)<>1 : ProcedureReturn 24 : EndIf
    UartWrite(65)
    If UartInit(0)<>0 Or PeekQ(#ZEN_CONSOLE+$60)<>1 : ProcedureReturn 25 : EndIf
    UartOff() : UartWrite(66)
    If UartRunning()<>0 Or UartDropped()<>1 Or PeekQ(#ZEN_CONSOLE+$50)<>1 : ProcedureReturn 26 : EndIf
    If UartAttach()<>1 Or UartReadWait(1)<>81 Or PeekQ(#ZEN_CONSOLE+$58)<>4095 : ProcedureReturn 27 : EndIf
  ElseIf scenario=8
    PokeQ(#ZEN_CONSOLE+$78,$D0000)
    PokeQ(#ZEN_CONSOLE+$80,3)
    If UartReadReady()<>0 Or UartReadWait(4096)<>-1 Or UartRead()<>-1 : ProcedureReturn 28 : EndIf
    If PeekQ(#ZEN_CONSOLE+$90)<>0 Or PeekQ(#ZEN_CONSOLE+$50)<>2 Or PeekA($D0000)<>0 Or PeekA($D0001)<>0 : ProcedureReturn 29 : EndIf
  ElseIf scenario=9
    If UartAttach()<>1 Or PeekQ(#ZEN_CONSOLE+$60)<>1 Or PeekQ(#ZEN_CONSOLE+$20)<>$31 Or PeekQ(#ZEN_CONSOLE+$58)<>4095 Or PeekQ(#ZEN_CONSOLE+$50)<>2 : ProcedureReturn 30 : EndIf
  ElseIf scenario=10
    If PrepareIdle()<>1 Or UartInit(1000)<>1 : ProcedureReturn 31 : EndIf
    start=Ticks() : UartWrite(65)
    If ZentajiConsoleDrain()<>1 Or Ticks()-start<TickHz()/100 : ProcedureReturn 32 : EndIf
    If UartDropped()<>0 Or ZentajiConsoleFaults()<>0 : ProcedureReturn 33 : EndIf
  EndIf
  ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve()
    sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zasm_ref as A
    import zexpack
    import zen_sleep_check as S
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    expected={0:'Zentaji café'.encode()+b'\r\n\0\xff',2:b'ab\x08 \x08C',10:b'A',12:b'Hi',13:b'AB',14:b'A',15:b'C',17:b'F',18:b'B',22:b'A\0\xff',23:bytes(n&255 for n in range(8193)),25:b'A'*10001,26:b'ABC'}
    incoming={1:b'\0\x7f\xff',2:b'ab\x08C\r\n',4:b'Q',6:b'Q',8:b'AB',9:b'AB',12:b'Hi\x03',13:b'A\r\nB\r',20:b'Q',21:b'Q'}
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-zen-console-') as tmp:
        td=Path(tmp);src=td/'console.zentaji';image=td/'console.zex'
        src.write_text(SOURCE,encoding='utf-8');out=run([cc,'--compile',src,'-o',image])
        assert "'gLastCR' is READ" not in out,out
        asm=Path(str(image)+'.asm').read_text(encoding='utf-8-sig');ref=A.Asm();org,data=ref.assemble(asm)
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        def machine(scenario):
            m=I.Fixture(ram_size=1<<20,display_modes=[(1,1,60000)]);m.load_image(image.read_bytes());c=m.cores[0]
            c.r[1]=scenario;c.r[255]=0xF0000
            for reg in range(128,253):c.r[reg]=0x10000+reg*13
            for reg in range(32,64):c.v[reg]=sum((reg*100+j)<<(64*j) for j in range(8))
            when={4:500000,21:200000000}.get(scenario,0)
            m.serial[0].incoming=[(when,b) for b in incoming.get(scenario,b'')]
            return m
        def states(out):return [s for s in out.splitlines() if s.startswith('STATE ')]
        def match(m,native,scenario):
            assert m.cores[0].r[1]==42,(scenario,m.cores[0].state,hex(m.cores[0].pc),hex(m.cores[0].r[1]),{k:hex(v) for k,v in m.cores[0].cr.items()},len(m.serial[0].out),bytes(m.serial[0].out)[-96:],native[-1200:])
            assert (td/'final.bin').read_bytes()==m.ram,scenario
            I.assert_same_state(native,m)
            want=expected.get(scenario,b'')
            assert bytes(m.serial[0].out)==want,(scenario,len(m.serial[0].out),len(want),bytes(m.serial[0].out)[-96:],want[-96:])
            serial=[s.split(' ',1)[1] for s in native.splitlines() if s.startswith('SERIAL0 ')]
            assert (serial[0] if serial else '')==want.hex().upper(),(scenario,[(len(s),s[-192:]) for s in serial],len(want),want[-96:])
        for scenario in (*range(20),22,23,24,25,26):
            budget={23:16000000,25:20000000}.get(scenario,4000000)
            m=machine(scenario);c=m.cores[0];kept=list(c.r[128:253]);vectors=list(c.v[32:])
            assert not L.capture(m,str(td))
            native=run([L.EXE,td/'machine.txt','--max',str(budget),'--ram',td/'final.bin']);m=runner.execute(m,budget,td);c=m.cores[0]
            match(m,native,scenario)
            assert c.r[128:253]==kept and c.v[32:]==vectors and c.r[255]==0xF0000
        print('PASS 25 actual console/input/editor/message-routing native state/RAM/output cases, including shared screen/aux byte/style fan-out, diversion exclusion, drop-newest overflow, refused-write exclusion, reset and lossless UART-to-model draining')
        results=[]
        for scenario in (20,21):
            m=machine(scenario);assert not L.capture(m,str(td));rec=td/('recorded%d.txt'%scenario)
            live,wall,cpu=S.run([str(zt/('zenwin.exe' if os.name=='nt' else 'zenwin')),str(td/'machine.txt'),'--headless','--live','--mute','--record',str(rec),'--max','4000000'],timeout=30)
            native=run([L.EXE,rec,'--max','4000000','--ram',td/'final.bin'])
            assert states(live)==states(native)
            observed=runner.execute_config(rec,4000000,td);match(observed,native,scenario);results.append((wall,cpu))
        wall=results[1][0]-results[0][0];cpu=max(0,results[1][1]-results[0][1])
        assert wall>=1.8 and cpu<0.4,(wall,cpu)
        print(f'PASS real console blocking RX live: startup-adjusted wall={wall:.6f}s cpu={cpu:.6f}s; timed input wakes the real backend, exact recorded native replay')


if __name__=='__main__':main()
