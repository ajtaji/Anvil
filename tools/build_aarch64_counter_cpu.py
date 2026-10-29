"""Build a returning physical test of shared counter and event sampling."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def procedure(text,name):
    m=re.search(r'(?ms)^Procedure(?:Naked)?(?:\.[iq])? '+re.escape(name)+r'\(.*?^EndProcedure',text)
    assert m,name
    return m[0]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args();r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Hal/aarch64_counter.pbi','RaspberryPi4/Lib/timer.pi4','RaspberryPi4/Examples/Diagnostics/pi4PromptWfeProbe.pi4','RockPi4C/Lib/idle_timer.pbi','RaspberryPi3/Lib/sdio.pi3','RaspberryPi5/Board/board.pi4']
    counter,timer,probe,idle,sdio,pi5=[(r/n).read_text(encoding='utf8') for n in names]
    s=counter+'\n'+ '\n'.join(x for x in timer.splitlines() if not x.startswith('XIncludeFile'))+'\n'
    for name in ['ProbeControl','ProbeSetControl']:s+=procedure(probe,name)+'\n'
    for name in ['Pi3SdioTicks','Pi3SdioTickHz']:s+=procedure(sdio,name)+'\n'
    s+=procedure(idle,'RockIdleTimerWait')+'\nGlobal gP5Ticks.q\n'+procedure(pi5,'P5Ticks')+'\n'
    s+='''Procedure.i Main(services.i)
 Define i.i,hz.i,previous.i,current.i,oldControl.i,configured.i,delta.i
 Define minimum.i,maximum.i,sample.i,result.i,ready.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$434E5431)
 hz=A64CounterFrequency() : PokeI($E1C00008,hz)
 If hz<>54000000 : ProcedureReturn 1 : EndIf
 ready=TimerInit() : PokeI($E1C00010,ready)
 If ready=0 : ProcedureReturn 2 : EndIf
 previous=A64CounterRead()
 For i=0 To 127
  current=A64CounterReadOrdered()
  If current<previous : ProcedureReturn 3 : EndIf
  previous=Pi3SdioTicks()
  If previous<current : ProcedureReturn 4 : EndIf
  current=P5Ticks()
  If current<previous Or current<>gP5Ticks : ProcedureReturn 5 : EndIf
  previous=Ticks()
  If previous<current : ProcedureReturn 6 : EndIf
 Next
 If Pi3SdioTickHz()<>hz Or TickHz()<>hz : ProcedureReturn 7 : EndIf
 PokeI($E1C00018,128)
 previous=Micros()
 ready=delayMicroseconds(1000)
 delta=Micros()-previous
 PokeI($E1C00020,ready) : PokeI($E1C00028,delta)
 If ready=0 Or delta<1000 Or delta>100000 : ProcedureReturn 8 : EndIf
 oldControl=ProbeControl()
 configured=(oldControl & $FFFFFFFFFFFFFF03) | $F4
 ProbeSetControl(configured)
 minimum=hz : maximum=0 : result=0
 If (ProbeControl() & $FC)<>$F4
  result=9
 Else
  For i=0 To 31
   previous=A64CounterReadOrdered()
   delta=RockIdleTimerWait()
   current=A64CounterReadOrdered()
   sample=A64CounterWaitEventSample()
   If delta<=0 Or delta>hz/100 Or current-previous<delta Or sample<current
    result=10 : Break
   EndIf
   If delta<minimum : minimum=delta : EndIf
   If delta>maximum : maximum=delta : EndIf
  Next
 EndIf
 ProbeSetControl(oldControl)
 PokeI($E1C00030,oldControl) : PokeI($E1C00038,ProbeControl())
 PokeI($E1C00040,i) : PokeI($E1C00048,minimum) : PokeI($E1C00050,maximum)
 If ProbeControl()<>oldControl : ProcedureReturn 11 : EndIf
 PokeI($E1C00058,result)
 ProcedureReturn result
EndProcedure
'''
    p=d/'proof.pi4';p.write_text(s,encoding='utf8');c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(p),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1600:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    p=d/'proof.img.pmf';(d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names}),indent=2),encoding='utf8')
if __name__=='__main__':main()
