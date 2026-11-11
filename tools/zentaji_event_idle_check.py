"""Native prompt event wakes, bounded timer and exact interrupt ownership restore."""
import argparse,json,os,subprocess,sys,tempfile
from pathlib import Path
from pmf_compiler import resolve_compiler
from zentaji_idle_check import SOURCE as BASE
ROOT=Path(__file__).resolve().parents[1]
SOURCE=BASE.split('Procedure.i Main(scenario.i)')[0]+r'''
Global testRebind.i=-1
Procedure TestActiveIdleWait()
 testRebind=AnvilPromptIdleWaitBind(0)
 ZentajiPromptEventIdleWait()
EndProcedure
Procedure.i Main(scenario.i)
 Protected before.q,elapsed.q,status.i,config.q,route.q,inputEnable.q,serialEnable.q
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 PokeQ(#ZEN_IDLE_TIMER,$12345678)
 If ZentajiPromptIdlePrepare(2000)<>1 : ProcedureReturn 1 : EndIf
 If AnvilPromptIdleWaitBind(@ZentajiPromptEventIdleWait)<>1 : ProcedureReturn 2 : EndIf
 If scenario=6 : config=$103 : PokeQ(#ZEN_IDLE_INTC+$200,config) : EndIf
 If scenario=7 : route=1<<ZenCpuCoreId() : PokeQ(#ZEN_IDLE_INTC+$208,route) : EndIf
 If scenario=8 : inputEnable=4 : PokeQ(#ZEN_IDLE_INPUT+$20,inputEnable) : EndIf
 If scenario=9 : serialEnable=4 : PokeQ(#ZEN_IDLE_SERIAL+$20,serialEnable) : EndIf
 If scenario=10 : AnvilPromptIdleWaitBind(0) : EndIf
 If scenario=11 : ZenCpuIrqEnable() : EndIf
 If scenario=12
  If PeekQ(#ZEN_IDLE_SERIAL+$48)<>65 Or PeekQ(#ZEN_IDLE_SERIAL+$50)<>0 Or (PeekQ(#ZEN_IDLE_SERIAL+$18)&1)=0 : ProcedureReturn 14 : EndIf
 EndIf
 If scenario=13 : AnvilPromptIdleWaitBind(@TestActiveIdleWait) : EndIf
 status=ZenCpuStatus() : before=Ticks()
 AnvilSchedulerIdleIfSafe()
 elapsed=Ticks()-before
 If ZenCpuStatus()<>status : ProcedureReturn 3 : EndIf
 If scenario=11 : ZenCpuIrqDisable() : EndIf
 If scenario=0 Or scenario>=11
  If elapsed<TickHz()*16/1000 Or elapsed>TickHz()*18/1000 Or PeekQ(#ZEN_IDLE_TIMER+$30)<>1 : ProcedureReturn 4 : EndIf
  If scenario=12 And (PeekQ(#ZEN_IDLE_SERIAL+$18)&1)<>0 : ProcedureReturn 15 : EndIf
  If scenario=13 And testRebind<>0 : ProcedureReturn 16 : EndIf
 ElseIf scenario<=5
  If elapsed>=TickHz()/100 Or PeekQ(#ZEN_IDLE_TIMER+$30)<>0 : ProcedureReturn 5 : EndIf
  If scenario=1 Or scenario=4
   If PeekQ(#ZEN_IDLE_SERIAL+$50)<>1 Or PeekQ(#ZEN_IDLE_SERIAL+$48)<>65 : ProcedureReturn 6 : EndIf
  ElseIf scenario=2 Or scenario=5
   If PeekQ(#ZEN_IDLE_INPUT+$48)<>1 Or (PeekQ(#ZEN_IDLE_INPUT+$18)&1)=0 : ProcedureReturn 7 : EndIf
  ElseIf scenario=3
   If PeekQ(#ZEN_IDLE_INPUT+$80)<>11 Or PeekQ(#ZEN_IDLE_INPUT+$88)<>12 Or (PeekQ(#ZEN_IDLE_INPUT+$18)&2)=0 : ProcedureReturn 8 : EndIf
  EndIf
 Else
  If elapsed<TickHz()*2/1000 Or elapsed>TickHz()*4/1000 Or PeekQ(#ZEN_IDLE_TIMER+$30)<>1 : ProcedureReturn 9 : EndIf
 EndIf
 If PeekQ(#ZEN_IDLE_INTC+$200)<>config Or PeekQ(#ZEN_IDLE_INTC+$208)<>route Or PeekQ(#ZEN_IDLE_INTC+$2C0)<>0 Or PeekQ(#ZEN_IDLE_INTC+$2C8)<>0 : ProcedureReturn 10 : EndIf
 If PeekQ(#ZEN_IDLE_INTC+$F008)<>2 Or PeekQ(#ZEN_IDLE_INTC+$F010)<>0 Or PeekQ(#ZEN_IDLE_SERIAL+$20)<>serialEnable Or PeekQ(#ZEN_IDLE_INPUT+$20)<>inputEnable : ProcedureReturn 11 : EndIf
 If PeekQ(#ZEN_IDLE_TIMER)<>$12345678 Or PeekQ(#ZEN_IDLE_TIMER+$10)<>0 Or PeekQ(#ZEN_IDLE_TIMER+$18)<>0 : ProcedureReturn 12 : EndIf
 If ZentajiPromptIdleRelease()<>1 : ProcedureReturn 13 : EndIf
 ProcedureReturn 42
EndProcedure
'''

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True);a=ap.parse_args()
 sys.path.insert(0,str(a.zen_tools.resolve()));import zentaji_native as I
 cc=resolve_compiler(a.compiler)
 with I.NativeRunner() as runner,tempfile.TemporaryDirectory(prefix='anvil-event-idle-') as tmp:
  td=Path(tmp);src=td/'event.zentaji';image=td/'event.zex';src.write_text(SOURCE)
  built=subprocess.run([str(cc),'--compile',str(src),'-o',str(image)],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True,timeout=120)
  assert built.returncode==0,built.stdout+built.stderr
  for owner in (0,1):
   for scenario in range(14):
    m=I.Fixture(ram_size=1<<20,cores=2,display_modes=[(1,1,60000)]);m.load_image(image.read_bytes())
    pc=m.cores[0].pc;m.cores[0].state='PARKED';c=m.cores[owner];c.pc=pc;c.state='RUNNING';c.r[255]=0xF0000;c.r[1]=scenario
    when=0 if scenario in (4,5,12) else 500000
    if scenario in (1,4,12):m.serial_feed(0,b'A',when)
    if scenario in (2,5):m.input_feed(when,'key',4,1,0,0,97)
    if scenario==3:m.input_feed(when,'mouse',11,12,0,0)
    observed=runner.execute(m,1000000,td);c=observed.cores[owner]
    assert c.state=='HALTED' and c.r[1]==42,(owner,scenario,c.state,c.r[1],observed.output[-1500:])
    print('PASS core',owner,'scenario',scenario,flush=True)
 print('PASS 28 native event-idle cases: timer, serial/key/mouse wake, queued input, foreign ownership, legacy wait, IE restoration, stale RX and active rebind refusal')
if __name__=='__main__':main()
