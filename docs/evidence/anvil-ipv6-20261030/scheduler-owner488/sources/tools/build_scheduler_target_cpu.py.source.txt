"""Physical named cooperative dispatch, queue order and ownership checks."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Kernel/Scheduler/scheduler.pbi','Anvil/Kernel/Scheduler/cooperative_a64.pbi']
 steps=[];cases=[]
 def check(name,expr,want):
  steps.append(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def code(s):steps.append(s)
 check('configure','ScConfigure(@TaskA,@Main-@TaskA)',1)
 code('a=ScCreate(@TaskA,101) : b=ScCreate(@TaskB,202) : c=ScCreate(@TaskC,303)')
 check('three contexts','Bool(a>0 And b>0 And c>0)',1)
 code('hook=2')
 check('select second context','Bool(ScRunHandle(b)=b)',1)
 code('hook=0')
 check('only selected context ran','count',1);check('selected trace','trace[0]',20)
 check('first remains ready','SchedState(a)',1);check('third remains ready','SchedState(c)',1)
 check('nested context refusal','nested',1);check('busy state claim refusal','busy',1)
 check('FIFO first preserved','Bool(ScRunOne()=a)',1)
 check('FIFO first trace','trace[1]',10)
 code('hook=2')
 check('resume named context','Bool(ScRunHandle(b)=b)',1)
 code('hook=0')
 check('local survives yield','localGood',1);check('named wait trace','trace[2]',21)
 check('waiting state','SchedState(b)',3);check('waiting refusal','ScRunHandle(b)',0)
 check('no fallback on waiting','count',3)
 check('FIFO third preserved','Bool(ScRunOne()=c)',1);check('third result','ScResult(c)',303)
 check('completed refusal','ScRunHandle(c)',0);check('no completed fallback','count',4)
 check('FIFO yielded first','Bool(ScRunOne()=a)',1);check('first result','ScResult(a)',101)
 check('empty ready queue','ScRunOne()',0)
 check('wake named context','SchedWake(7,1)',1)
 code('hook=2')
 check('resume after wake','Bool(ScRunHandle(b)=b)',1)
 code('hook=0')
 check('second result','ScResult(b)',202);check('all hook observations owned','hookGood',3)
 check('all trace events','count',6)
 for i,n in enumerate([20,10,21,30,11,22]):check('complete trace '+str(i),f'trace[{i}]',n)
 code('foreign=SchedCreate()')
 check('foreign context refusal','ScRunHandle(foreign)',0);check('foreign remains ready','SchedState(foreign)',1)
 check('foreign cancellation','SchedCancel(foreign)',1);check('foreign reap','SchedReap(foreign)',1)
 check('owned reap','ScReap(b)',1)
 code('replacement=ScCreate(@TaskC,404)')
 check('slot reused with new generation','Bool(replacement<>b And replacement%32=b%32)',1)
 check('stale context refusal','ScRunHandle(b)',0);check('stale state claim refusal','SchedTake(b)',0)
 check('replacement remains ready','SchedState(replacement)',1)
 check('zero refusal','ScRunHandle(0)',0);check('negative refusal','ScRunHandle(-1)',0)
 check('refusals did not execute replacement','count',6)
 code('PokeI(ScStack(SchedSlot(replacement)),0)')
 check('guarded dispatch names failed task','Bool(ScRunHandle(replacement)=replacement)',1)
 check('guard failure result','ScResult(replacement)',-1);check('guard prevented execution','count',6)
 check('guarded task terminal','SchedState(replacement)',4)
 check('guarded task reap','ScReap(replacement)',1)
 check('first reap','ScReap(a)',1);check('third reap','ScReap(c)',1)
 check('ready queue empty','sched_count',0);check('wait queue empty','sched_waitcount',0)
 check('no running task','sched_running',0);check('no active context','sc_active',0)
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global a.i,b.i,c.i,hook.i,count.i,nested.i,busy.i,localGood.i,hookGood.i
Global Dim trace.i[16]
Procedure Add(value.i)
 trace[count]=value : count=count+1
EndProcedure
Procedure.i TaskA()
 Define value.i
 value=ScArgument() : Add(10)
 If ScYield()=0 : ProcedureReturn -1 : EndIf
 Add(11) : ProcedureReturn value
EndProcedure
Procedure.i TaskB()
 Define value.i
 value=ScArgument()
 If hook=2 : hookGood=hookGood+1 : EndIf
 nested=Bool(ScRunHandle(a)=0) : busy=Bool(SchedTake(a)=0)
 Add(20)
 If ScYield()=0 : ProcedureReturn -2 : EndIf
 localGood=Bool(value=202)
 If hook=2 : hookGood=hookGood+1 : EndIf
 Add(21)
 If ScWait(7,500)=0 : ProcedureReturn -3 : EndIf
 If hook=2 : hookGood=hookGood+1 : EndIf
 Add(22) : ProcedureReturn value
EndProcedure
Procedure.i TaskC()
 Add(30) : ProcedureReturn ScArgument()
EndProcedure
Procedure.i Main()
 Define i.i,foreign.i,replacement.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$55445331)
'''+f'PokeI($E1C00008,{len(cases)})\n'+'\n'.join(steps)+'\nProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();names.append('tools/build_scheduler_target_cpu.py')
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
