"""Run Anvil's actual Zentaji timer/WFI backend and shared scheduler.

Device timers, CPU instructions, frequency and IRQ admission are real emulated
hardware. Only unrelated service lanes and queued-input providers are adapters.
This is a backend proof, not a complete Anvil boot or visible-input proof.
"""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler

ROOT=Path(__file__).resolve().parents[1]

SOURCE=r'''
#CAP_TOUCH=0
#CAP_NET=0
#CAP_PWM=0
Global testSerial.i=0
Global testInput.i=0
Global testWork.i=0
Procedure UartMessageBegin() : EndProcedure
Procedure UartMessageEnd() : EndProcedure
Procedure.i UartReadReady() : ProcedureReturn testSerial : EndProcedure
Procedure.i InputEventsQueued() : ProcedureReturn testInput : EndProcedure
Procedure MouseTick() : testWork=testWork+1 : EndProcedure
Procedure TouchTick() : EndProcedure
Procedure ScreenServiceTick() : testWork=testWork+1 : EndProcedure
Procedure WifiMaintenanceTick() : EndProcedure
Procedure NetDhcpTick() : EndProcedure
Procedure FanTick() : testWork=testWork+1 : EndProcedure
Procedure HwTempSampleTick() : EndProcedure
Procedure NetConsoleRearm() : EndProcedure
Procedure NetConsolePump() : EndProcedure
Procedure NetConsoleLlTick() : EndProcedure
Procedure TcpTick() : testWork=testWork+1 : EndProcedure
IncludeFile "Zentaji/Board/prompt_idle.pbi"
IncludeFile "Anvil/Core/prompt_scheduler.pbi"

Procedure.i Main(scenario.i)
Protected other.i
Protected before.q
Protected status.i
Protected deadline.q
If ZenCpuCoreId()=0 : other=#ZEN_IDLE_TIMERS+$1040 : Else : other=#ZEN_IDLE_TIMERS+$1000 : EndIf
; These writes model the board's explicit IRQ/timer reservation, not backend code.
PokeQ(#ZEN_IDLE_INTC+$120,3)
PokeQ(#ZEN_IDLE_INTC+$F008,$80000002)
PokeQ(#ZEN_IDLE_TIMER,$12345678)
PokeQ(#ZEN_IDLE_TIMERS+$140,$22334455)
PokeQ(#ZEN_IDLE_TIMERS+$148,77)
PokeQ(other,$33445566)
If scenario=1 : PokeQ(#ZEN_IDLE_TIMER+$10,1) : EndIf
If scenario=2 : PokeQ(#ZEN_IDLE_TIMER+$08,17) : EndIf
If scenario=3 : PokeQ(#ZEN_IDLE_TIMER+$28,1) : EndIf
If scenario=4 : PokeQ(#ZEN_IDLE_INTC+$F008,$80000000) : EndIf
If scenario=5 : PokeQ(#ZEN_IDLE_INTC+$F010,3) : EndIf
If scenario=6 : PokeQ(#ZEN_IDLE_INTC+$120,$103) : EndIf
If scenario=7 : PokeQ(#ZEN_IDLE_INTC+$120,0) : EndIf
If scenario>=1 And scenario<=7
  If ZentajiPromptIdlePrepare(2000)<>0 Or zenIdleOwner<>-1 : ProcedureReturn 1 : EndIf
  HwPromptIdleWait()
  If PeekQ(#ZEN_IDLE_TIMER)<>$12345678 : ProcedureReturn 2 : EndIf
  If scenario=1 And PeekQ(#ZEN_IDLE_TIMER+$10)<>1 : ProcedureReturn 3 : EndIf
  If scenario=2 And PeekQ(#ZEN_IDLE_TIMER+$08)<>17 : ProcedureReturn 4 : EndIf
  If scenario=3 And PeekQ(#ZEN_IDLE_TIMER+$18)<>2 : ProcedureReturn 5 : EndIf
  ProcedureReturn 42
EndIf
If scenario=8 Or scenario=9
  If scenario=8 : status=49 : Else : status=2001 : EndIf
  If ZentajiPromptIdlePrepare(status)<>0 Or zenIdleOwner<>-1 : ProcedureReturn 6 : EndIf
  ProcedureReturn 42
EndIf
If ZentajiPromptIdlePrepare(2000)<>1 Or HwPromptIdleReady()<>1 : ProcedureReturn 7 : EndIf
If ZentajiPromptIdlePrepare(2000)<>0 : ProcedureReturn 8 : EndIf
If scenario=10
  PokeQ(#ZEN_IDLE_TIMER+$10,1)
  If HwPromptIdleReady()<>0 : ProcedureReturn 9 : EndIf
  HwPromptIdleWait()
  If PeekQ(#ZEN_IDLE_TIMER+$10)<>1 Or ZentajiPromptIdleRelease()<>0 : ProcedureReturn 10 : EndIf
  ProcedureReturn 42
EndIf
If scenario=11
  zenIdleOwner=1-ZenCpuCoreId()
  If HwPromptIdleReady()<>0 : ProcedureReturn 11 : EndIf
  HwPromptIdleWait()
  If PeekQ(#ZEN_IDLE_TIMER+$30)<>0 : ProcedureReturn 12 : EndIf
  zenIdleOwner=ZenCpuCoreId()
EndIf
If scenario=12
  PokeQ(#ZEN_IDLE_INTC+$F008,$80000000)
  If HwPromptIdleReady()<>0 Or ZentajiPromptIdleRelease()<>1 : ProcedureReturn 13 : EndIf
  ProcedureReturn 42
EndIf
If scenario=13
  testSerial=1 : AnvilSchedulerIdleIfSafe() : testSerial=0
  testInput=1 : AnvilSchedulerIdleIfSafe() : testInput=0
  If PeekQ(#ZEN_IDLE_TIMER+$30)<>0 : ProcedureReturn 14 : EndIf
ElseIf scenario=14
  ; Another pending IRQ must wake immediately and remain pending afterwards.
  PokeQ(#ZEN_IDLE_INTC+$4E0,$103)
  PokeQ(#ZEN_IDLE_INTC+$4E8,1<<ZenCpuCoreId())
  PokeQ(#ZEN_IDLE_INTC+$4F0,1)
  AnvilSchedulerIdleIfSafe()
  If (PeekQ(#ZEN_IDLE_INTC+$F000)&$80000000)=0 Or PeekQ(#ZEN_IDLE_TIMER+$30)<>0 : ProcedureReturn 15 : EndIf
ElseIf scenario=20 Or scenario=21
  If scenario=20 : deadline=Ticks() : Else : deadline=Ticks()+2*TickHz() : EndIf
  While Ticks()<deadline
    AnvilPromptServiceOne()
    AnvilSchedulerIdleIfSafe()
  Wend
  If scenario=21 And (testWork<10 Or PeekQ(#ZEN_IDLE_TIMER+$30)=0) : ProcedureReturn 16 : EndIf
Else
  If scenario=15 : ZenCpuIrqEnable() : EndIf
  status=ZenCpuStatus()
  before=Ticks()
  AnvilPromptServiceOne()
  AnvilSchedulerIdleIfSafe()
  If Ticks()<=before Or PeekQ(#ZEN_IDLE_TIMER+$30)<>1 : ProcedureReturn 17 : EndIf
  If ZenCpuStatus()<>status : ProcedureReturn 18 : EndIf
  If scenario=15 : ZenCpuIrqDisable() : EndIf
EndIf
If PeekQ(#ZEN_IDLE_TIMER)<>$12345678 Or PeekQ(#ZEN_IDLE_TIMER+$10)<>0 Or PeekQ(#ZEN_IDLE_TIMER+$18)<>0 : ProcedureReturn 19 : EndIf
If PeekQ(#ZEN_IDLE_TIMERS+$140)<>$22334455 Or PeekQ(#ZEN_IDLE_TIMERS+$148)<>77 Or PeekQ(other)<>$33445566 : ProcedureReturn 20 : EndIf
If PeekQ(#ZEN_IDLE_INTC+$120)<>3 Or PeekQ(#ZEN_IDLE_INTC+$F010)<>0 Or PeekQ(#ZEN_IDLE_INTC+$F008)<>$80000002 : ProcedureReturn 21 : EndIf
If ZentajiPromptIdleRelease()<>1 Or HwPromptIdleReady()<>0 : ProcedureReturn 22 : EndIf
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
    runtime=ROOT/'Anvil/Kernel/Zentaji/zen_cpu.pbi'
    dep=next(d for d in json.loads((ROOT/'PROVENANCE.json').read_text())['runtime_dependencies'] if d['path']==runtime.relative_to(ROOT).as_posix())
    assert hashlib.sha256(runtime.read_bytes()).hexdigest()==dep['sha256']
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='anvil-zen-idle-') as tmp:
        td=Path(tmp);src=td/'idle.zentaji';image=td/'idle.zex'
        src.write_text(SOURCE,encoding='utf-8');run([cc,'--compile',src,'-o',image])
        asm=Path(str(image)+'.asm').read_text(encoding='utf-8-sig')
        ref=A.Asm();org,data=ref.assemble(asm)
        assert image.read_bytes()==zexpack.header(org,org,data)+data
        def machine(scenario,owner=0):
            m=I.Machine(ram_size=1<<20,cores=2,display_modes=[(1,1,60000)])
            m.load_image(image.read_bytes())
            pc=m.cores[0].pc;m.cores[0].state='PARKED'
            c=m.cores[owner];c.pc=pc;c.state='RUNNING';c.r[255]=0xF0000;c.r[1]=scenario
            for reg in range(128,253):c.r[reg]=0x10000+reg*13
            for reg in range(32,64):c.v[reg]=sum((reg*100+j)<<(64*j) for j in range(8))
            return m
        def states(output):return [s for s in output.splitlines() if s.startswith('STATE ')]
        def match(m,native,owner):
            assert m.cores[owner].r[1]==42,(owner,m.cores[owner].r[1])
            assert (td/'final.bin').read_bytes()==m.ram
            expected=L.state_line(m,0,-1).split(' ',1)[1]
            assert len(states(native))==1 and states(native)[0][6:].split(' ',1)[1]==expected
        for owner in (0,1):
            for scenario in range(16):
                m=machine(scenario,owner);c=m.cores[owner]
                kept=list(c.r[128:253]);vectors=list(c.v[32:])
                assert not L.capture(m,str(td))
                native=run([L.EXE,td/'machine.txt','--max','1000000','--ram',td/'final.bin'])
                m.run(1000000)
                try:match(m,native,owner)
                except AssertionError as e:raise AssertionError((scenario,owner,native[-1500:])) from e
                assert c.r[128:253]==kept and c.v[32:]==vectors and c.r[255]==0xF0000
        print('PASS 32 actual backend/shared-scheduler native/twin state/RAM cases: cores0/1, reservation/admission, deadline and early wake, IE preservation, input/work, other timers and refusal without overwrites')
        results=[]
        for scenario in (20,21):
            m=machine(scenario);assert not L.capture(m,str(td));rec=td/'recorded.txt'
            live,wall,cpu=S.run([str(zt/('zenwin.exe' if os.name=='nt' else 'zenwin')),str(td/'machine.txt'),'--headless','--live','--mute','--record',str(rec),'--max','1000000'],timeout=30)
            native=run([L.EXE,rec,'--max','1000000','--ram',td/'final.bin'])
            assert states(live)==states(native)
            m.clock_samples=deque((int(s.split()[1][1:],16),int(s.split()[2]),int(s.split()[3]) if len(s.split())>3 else -1) for s in rec.read_text().splitlines() if s.startswith('clock '))
            m.clock_complete=True;m.run(1000000);match(m,native,0)
            results.append((wall,cpu))
        wall=results[1][0]-results[0][0];cpu=max(0,results[1][1]-results[0][1])
        assert wall>=1.8,(wall,cpu)
        assert cpu<0.4,(wall,cpu)
        print(f'PASS actual Anvil idle backend live: startup-adjusted wall={wall:.6f}s cpu={cpu:.6f}s; bounded per-core timer/WFI, active service lanes, exact recorded native/twin replay')


if __name__=='__main__':main()
