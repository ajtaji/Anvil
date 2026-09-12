"""Real emitted incoming-CNR/reset/stop proof; no silicon-cause claim.

Removed-readiness mutant preserves the original baseline defect (premature
HCRST). Model explicitly supplies an initially halted/not-ready controller.
"""
import pathlib,re,sys,tempfile,subprocess,os,argparse,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as base
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args()
source=(base.ROOT/'RaspberryPi4/Lib/xhci.pi4').read_text()
names='USBSTS USBCMD STS_HALT STS_CNR STS_EINT IMAN CMD_RUN CMD_RESET ERR_HALT ERR_RESET ERR_CNR TMO_HALT_MS TMO_RESET_MS'.split()
constants='\n'.join(re.search(r'(?m)^#XHCI_'+n+r'\s*=.*$',source).group() for n in names)
bodies='\n'.join(re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\([^\n]*\).*?^EndProcedure',source).group() for n in ('xh_Deadline','xh_Expired','xh_WaitReady','xh_Halt','xh_Reset','XhciStop'))
model='''
Global xh_op.i=4096
Global xh_ir.i=8192
Global xh_ready.i=1
Global mode.i=MODE_VALUE
Global premature.i
Global writes.i
Global ticks.i
Global failure.i
Global xh_hz.i=1000000
Global trace.i
Global tracefault.i
Global tracecount.i
Procedure xh_Trace(p.i)
 trace=p
 PokeI($06000100+tracecount*8,p)
 tracecount=tracecount+1
EndProcedure
Procedure.i Cold()
  If mode=0 : ProcedureReturn 1 : EndIf
  ProcedureReturn ticks<4000 And mode=1
EndProcedure
Procedure.i xh_Rd(b.i,off.i)
  If b=xh_op And off=#XHCI_USBSTS
    If Cold()<>0 : ProcedureReturn #XHCI_STS_HALT | #XHCI_STS_CNR : EndIf
    ProcedureReturn #XHCI_STS_HALT
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure xh_Wr(b.i,off.i,value.i)
  writes=writes+1
  If off=0 And (value & 2)<>0 And trace<>6 : tracefault=tracefault+1 : EndIf
  If (b<>xh_op Or off<>#XHCI_USBSTS) And Cold()<>0 : premature=premature+1 : EndIf
EndProcedure
Procedure.i xh_Fail(reason.i)
  failure=reason
  ProcedureReturn 0
EndProcedure
Procedure.i xh_Ticks()
  ticks=ticks+1000
  ProcedureReturn ticks
EndProcedure
'''
main='''
Procedure.i Main()
 PokeI($06000000,xh_Reset())
 XhciStop()
 PokeI($06000008,premature)
 PokeI($06000010,writes)
 PokeI($06000018,xh_ready)
 PokeI($06000020,failure)
 PokeI($06000028,tracefault)
 PokeI($06000030,tracecount)
 ProcedureReturn 0
EndProcedure
'''
a64=base.load_interpreter(base.INTERP)
def run(work,mode,body=bodies):
 src=work/'fixture.pi4';image=work/'fixture.img'
 src.write_text(constants+model.replace('MODE_VALUE',str(mode))+body+main)
 env=os.environ.copy();env['PMF_ROOT']=str(base.ROOT)
 r=subprocess.run([args.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-o',str(image)],cwd=base.ROOT,env=env,capture_output=True,text=True)
 if r.returncode or not image.exists():raise SystemExit(r.stdout+r.stderr)
 cpu=a64.A64()
 for n,b in enumerate(image.read_bytes()):cpu.memory[base.LOAD+n]=b
 cpu.pc=base.LOAD;cpu.sp=base.STACK;cpu.x[30]=base.RETURN_PC
 for n in range(500000):
  if cpu.pc==base.RETURN_PC:break
  cpu.step()
 else:raise AssertionError('fixture did not terminate')
 out=[base.u64(cpu,base.OUT+8*i) for i in range(6)]
 assert out[5]==0,('reset write before marker',out)
 trace=[base.u64(cpu,base.OUT+0x100+i*8) for i in range(base.u64(cpu,base.OUT+0x30))]
 expected=[1,2]*2 if mode==0 else [1,3,4,5,6,7,8,9,11,12,14]*2
 assert trace==expected,('trace sequence',mode,trace)
 assert out[1]==0,('premature operational/runtime write',mode,out)
 assert out[3]==0,('ready retained on stop',out)
 if mode==0:assert out[0]==0 and out[2]==0 and out[4]==14,out
 else:assert out[0]==1 and out[2]>=3 and out[4]==0,out
 return n
with tempfile.TemporaryDirectory(prefix='xhci-initial-cnr-') as temp:
 work=pathlib.Path(temp);steps=sum(run(work,m) for m in range(3))
 mutants=[('original missing incoming readiness',bodies.replace('  If xh_WaitReady() = 0\n    ProcedureReturn 0\n  EndIf','',1)),('cleanup ignores failed reset',bodies.replace('  If xh_Reset() = 0\n    ProcedureReturn\n  EndIf','  xh_Reset()',1))]
 for label,body in mutants:
  assert body!=bodies,label
  try:run(work,0,body)
  except AssertionError:pass
  else:raise AssertionError('mutant survived: '+label)
 try:run(work,2,bodies.replace('  xh_Trace(6)','  xh_Trace(5)',1))
 except AssertionError:pass
 else:raise AssertionError('missing pre-write marker mutant survived')
 print('PASS: 3 initial-CNR/ready cases with exact trace order;',steps,'instructions; 3 readiness/cleanup/marker mutants rejected')
 print('Compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
