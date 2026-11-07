"""Actual serial-0 transport and shared input/editor on Zentaji hardware."""
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
IncludeFile "Zentaji/Board/console.pbi"
IncludeFile "Anvil/Core/state.pbi"
IncludeFile "Anvil/Core/input_events.pbi"
IncludeFile "Anvil/Core/text_edit.pbi"
Procedure.i PrepareIdle()
  PokeQ(#ZEN_IDLE_INTC+$120,3)
  PokeQ(#ZEN_IDLE_INTC+$F008,2)
  ProcedureReturn ZentajiPromptIdlePrepare(2000)
EndProcedure
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
  If scenario=0
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
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    import zen_sleep_check as S
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    expected={0:'Zentaji café'.encode()+b'\r\n\0\xff',2:b'ab\x08 \x08C',10:b'A',12:b'Hi',13:b'AB'}
    incoming={1:b'\0\x7f\xff',2:b'ab\x08C\r\n',4:b'Q',6:b'Q',8:b'AB',9:b'AB',12:b'Hi\x03',13:b'A\r\nB\r',20:b'Q',21:b'Q'}
    with tempfile.TemporaryDirectory(prefix='anvil-zen-console-') as tmp:
        td=Path(tmp);src=td/'console.zentaji';image=td/'console.zex'
        src.write_text(SOURCE,encoding='utf-8');out=run([cc,'--compile',src,'-o',image])
        assert "'gLastCR' is READ" not in out,out
        asm=Path(str(image)+'.asm').read_text(encoding='utf-8-sig');ref=A.Asm();org,data=ref.assemble(asm)
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        def machine(scenario):
            m=I.Machine(ram_size=1<<20,display_modes=[(1,1,60000)]);m.load_image(image.read_bytes());c=m.cores[0]
            c.r[1]=scenario;c.r[255]=0xF0000
            for reg in range(128,253):c.r[reg]=0x10000+reg*13
            for reg in range(32,64):c.v[reg]=sum((reg*100+j)<<(64*j) for j in range(8))
            when={4:500000,21:200000000}.get(scenario,0)
            m.serial[0].incoming=[(when,b) for b in incoming.get(scenario,b'')]
            return m
        def states(out):return [s for s in out.splitlines() if s.startswith('STATE ')]
        def match(m,native,scenario):
            assert m.cores[0].r[1]==42,(scenario,m.cores[0].state,hex(m.cores[0].pc),hex(m.cores[0].r[1]),{k:hex(v) for k,v in m.cores[0].cr.items()},bytes(m.serial[0].out),native[-1200:])
            assert (td/'final.bin').read_bytes()==m.ram,scenario
            assert states(native)[0][6:].split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1],scenario
            want=expected.get(scenario,b'')
            assert bytes(m.serial[0].out)==want,(scenario,bytes(m.serial[0].out),want)
            serial=[s.split(' ',1)[1] for s in native.splitlines() if s.startswith('SERIAL0 ')]
            assert (serial[0] if serial else '')==want.hex().upper(),(scenario,serial,want)
        for scenario in range(14):
            m=machine(scenario);c=m.cores[0];kept=list(c.r[128:253]);vectors=list(c.v[32:])
            assert not L.capture(m,str(td))
            native=run([L.EXE,td/'machine.txt','--max','2000000','--ram',td/'final.bin']);m.run(2000000)
            match(m,native,scenario)
            assert c.r[128:253]==kept and c.v[32:]==vectors and c.r[255]==0xF0000
        print('PASS 14 actual console/input/editor native/twin state/RAM/output cases: byte/UTF8, nondestructive ready, CRLF/edit/cancel, bounded pressure/drain, baud/adoption/detach, DMA ownership and timer-backed input')
        results=[]
        for scenario in (20,21):
            m=machine(scenario);assert not L.capture(m,str(td));rec=td/'recorded.txt'
            live,wall,cpu=S.run([str(zt/('zenwin.exe' if os.name=='nt' else 'zenwin')),str(td/'machine.txt'),'--headless','--live','--mute','--record',str(rec),'--max','2000000'],timeout=30)
            native=run([L.EXE,rec,'--max','2000000','--ram',td/'final.bin'])
            assert states(live)==states(native)
            m.clock_samples=deque((int(s.split()[1][1:],16),int(s.split()[2]),int(s.split()[3]) if len(s.split())>3 else -1) for s in rec.read_text().splitlines() if s.startswith('clock '))
            m.clock_complete=True;m.run(2000000);match(m,native,scenario);results.append((wall,cpu))
        wall=results[1][0]-results[0][0];cpu=max(0,results[1][1]-results[0][1])
        assert wall>=1.8 and cpu<0.4,(wall,cpu)
        print(f'PASS real console blocking RX live: startup-adjusted wall={wall:.6f}s cpu={cpu:.6f}s; timed input wakes the real backend, exact recorded native/twin replay')


if __name__=='__main__':main()
