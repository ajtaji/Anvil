"""Execute actual board hook with named UI/UART leaves; no device access."""
import pathlib,re,sys,tempfile,subprocess,os,argparse
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as base
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args()
source=(base.ROOT/'RaspberryPi4/Board/cursor_input.pi4').read_text()
body=re.search(r'(?ms)^Procedure UsbPhaseWord\(\).*?^EndProcedure',source).group()
constants='\n'.join(re.findall(r'(?m)^#BPH_XHCI.*$',source))
stub='''
#XHCI_PH_DONE=9
Global gBootLog.i=1
Global mark.i
Procedure MonPhaseMark(p.i)
 mark=p
EndProcedure
Procedure.i XhciPhase() : ProcedureReturn 5 : EndProcedure
Procedure.i XhciPhaseText(p.i) : ProcedureReturn 0 : EndProcedure
Procedure UartWriteStr(p.i) : EndProcedure
Procedure UartWrite(p.i) : EndProcedure
Procedure UartDrain() : EndProcedure
Procedure ScreenServiceTick()
 PokeI($06000000,mark)
EndProcedure
'''
main='''
Procedure.i Main()
 UsbPhaseWord()
 PokeI($06000008,mark)
 ProcedureReturn 0
EndProcedure
'''
a64=base.load_interpreter(base.INTERP)
def run(work,text):
 src=work/'phase.pi4';img=work/'phase.img';src.write_text(constants+stub+text+main)
 env=os.environ.copy();env['PMF_ROOT']=str(base.ROOT)
 r=subprocess.run([args.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-o',str(img)],cwd=base.ROOT,env=env,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 c=a64.A64();c.memory.update({base.LOAD+i:b for i,b in enumerate(img.read_bytes())});c.pc=base.LOAD;c.sp=base.STACK;c.x[30]=base.RETURN_PC
 for i in range(100000):
  if c.pc==base.RETURN_PC:break
  c.step()
 else:raise RuntimeError('execution budget')
 assert [base.u64(c,base.OUT+i*8) for i in range(2)]==[0x905,0xa05]
with tempfile.TemporaryDirectory(prefix='xhci-phase-') as temp:
 work=pathlib.Path(temp);run(work,body)
 for line in ('  MonPhaseMark(#BPH_XHCI_SCREEN_ENTER | XhciPhase())','  MonPhaseMark(#BPH_XHCI_SCREEN_EXIT | XhciPhase())'):
  assert line in body
  try:run(work,body.replace(line,''))
  except AssertionError:pass
  else:raise AssertionError('removed phase guard survived')
print('PASS actual UI hook order; both missing-marker mutations rejected')
