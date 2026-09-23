"""Real emitted incoming-CNR/reset/stop proof; no silicon-cause claim.

Removed-readiness mutant preserves the original baseline defect (premature
HCRST). Model explicitly supplies an initially halted/not-ready controller.

Two further controllers: one that is running with USBSTS.HCE set and never
halts (xHCI 1.2 section 4.24.1 - the reset path must record the refusal,
skip marker 3, issue HCRST anyway and say it was forced), and one whose
registers read all-ones (a device off the bus - it must be refused as
XHCI_ERR_GONE on the first read, not waited out as Controller Not Ready).
Both are spec-derived models; neither behaviour has been observed on silicon.
"""
import pathlib,re,sys,tempfile,subprocess,os,argparse,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as base
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
source=(base.ROOT/'RaspberryPi4/Lib/xhci.pi4').read_text()
names='USBSTS USBCMD STS_HALT STS_CNR STS_EINT STS_HCE IMAN CMD_RUN CMD_RESET CMD_EIE CMD_HSEIE CMD_EWE ERR_NONE ERR_HALT ERR_RESET ERR_CNR ERR_GONE ERR_HCE TMO_HALT_MS TMO_RESET_MS TMO_RESET_LONG_MS'.split()
constants='\n'.join(re.search(r'(?m)^#XHCI_'+n+r'\s*=.*$',source).group() for n in names)
bodies='\n'.join(re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\([^\n]*\).*?^EndProcedure',source).group() for n in ('xh_Deadline','xh_Expired','xh_ElapsedMs','xh_WaitReady','xh_Halt','xh_Reset','XhciStop'))
model='''
; ---- the wait ledger the production bodies account into ----------------
; Not inert: XhciAccountWait counts, and the fixture asserts the count.
#XHCI_W_HALT      =  0
#XHCI_W_HCRST     =  1
#XHCI_W_CNR       =  2
#XHCI_W_RUN       =  3
#XHCI_W_ADOPT     =  4
#XHCI_W_PORTPWR   =  5
#XHCI_W_PORTRESET =  6
#XHCI_W_CMD       =  7
#XHCI_W_XFER      =  8
#XHCI_W_CTRL      =  9
#XHCI_W_BULK      = 10
#XHCI_W_HUBRESET  = 11
#XHCI_W_HUBRECOV  = 12
#XHCI_W_HUBPGOOD  = 13
#XHCI_W_HUBSETTLE = 14
#XHCI_W_HUBDEB    = 15
#XHCI_W_MSCCONF   = 16
#XHCI_W_MSCREADY  = 17
#XHCI_W_MSCRESET  = 18
#XHCI_W_PORTDEB   = 19
#XHCI_W_PORTRCVY  = 20
#XHCI_W_SETADDR   = 21
#XHCI_W_N         = 22
Global Dim gateWaitRow.i[#XHCI_W_N]
Procedure.i XhciWaitMark()
  ProcedureReturn 0
EndProcedure
Procedure XhciAccountWait(site.i, t0.i)
  If site >= 0 And site < #XHCI_W_N
    gateWaitRow[site] = gateWaitRow[site] + 1
  EndIf
EndProcedure
Procedure XhciAccountBulkBytes(n.i)
EndProcedure
Procedure.i GateWaitVisits(site.i)
  If site < 0 Or site >= #XHCI_W_N
    ProcedureReturn -1
  EndIf
  ProcedureReturn gateWaitRow[site]
EndProcedure
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
Global xh_err.i
Global xh_haltSts0.i
Global xh_haltCmd0.i
Global xh_haltCmdW.i
Global xh_haltCmdB.i
Global xh_haltSts1.i
Global xh_haltMs.i
Global xh_haltForced.i
Global cmdreg.i
Global hce.i
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
  If mode=4 : ProcedureReturn $FFFFFFFF : EndIf
  If b=xh_op And off=#XHCI_USBSTS
    If hce<>0 : ProcedureReturn #XHCI_STS_HCE : EndIf
    If Cold()<>0 : ProcedureReturn #XHCI_STS_HALT | #XHCI_STS_CNR : EndIf
    ProcedureReturn #XHCI_STS_HALT
  EndIf
  If b=xh_op And off=#XHCI_USBCMD : ProcedureReturn cmdreg : EndIf
  ProcedureReturn 0
EndProcedure
Procedure xh_Wr(b.i,off.i,value.i)
  writes=writes+1
  If b=xh_op And off=#XHCI_USBCMD
    cmdreg=value & ~#XHCI_CMD_RESET
    If (value & #XHCI_CMD_RESET)<>0 : hce=0 : EndIf
  EndIf
  If off=0 And (value & 2)<>0 And trace<>6 : tracefault=tracefault+1 : EndIf
  If (b<>xh_op Or off<>#XHCI_USBSTS) And Cold()<>0 : premature=premature+1 : EndIf
EndProcedure
Procedure.i xh_Fail(reason.i)
  failure=reason
  xh_err=reason
  ProcedureReturn 0
EndProcedure
Procedure.i xh_Ticks()
  ticks=ticks+1000
  ProcedureReturn ticks
EndProcedure
'''
main='''
Procedure.i Main()
 If mode=3
  cmdreg=#XHCI_CMD_RUN | #XHCI_CMD_EIE
  hce=1
 EndIf
 PokeI($06000000,xh_Reset())
 PokeI($06000038,xh_haltForced)
 PokeI($06000040,xh_err)
 PokeI($06000048,xh_haltSts0)
 PokeI($06000050,xh_haltCmd0)
 PokeI($06000058,xh_haltCmdW)
 PokeI($06000060,xh_haltCmdB)
 PokeI($06000068,xh_haltSts1)
 PokeI($06000070,xh_haltMs)
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
 out=[base.u64(cpu,base.OUT+8*i) for i in range(15)]
 assert out[5]==0,('reset write before marker',out)
 trace=[base.u64(cpu,base.OUT+0x100+i*8) for i in range(base.u64(cpu,base.OUT+0x30))]
 normal=[1,3,4,5,6,7,8,9,11,12,14]
 expected={0:[1,2]*2,1:normal*2,2:normal*2,3:[1,2,4,5,6,7,8,9,11,12,14]+normal,4:[1,2]*2}[mode]
 assert trace==expected,('trace sequence',mode,trace)
 assert out[1]==0,('premature operational/runtime write',mode,out)
 assert out[3]==0,('ready retained on stop',out)
 if mode==0:assert out[0]==0 and out[2]==0 and out[4]==14 and out[7]==0 and out[8]==14,out
 elif mode==3:
  # HCE: refused as HCE, HCRST forced and recorded, error cleared once the
  # reset completed; the witness holds the running controller as found,
  # the quiesce word (RUN and EIE both off), its read-back, the deciding
  # USBSTS and a wait that really ran the 16 ms bound.
  assert out[0]==1 and out[4]==47 and out[7]==1 and out[8]==0,('HCE reset',out)
  assert out[9:14]==[0x1000,5,0,0,0x1000] and out[14]>=16,('HCE witness',out)
 elif mode==4:
  # All-ones: GONE on the first read, no write, no forced reset.
  assert out[0]==0 and out[2]==0 and out[4]==46 and out[7]==0 and out[8]==46,('all-ones',out)
  assert out[9]==0xFFFFFFFF and out[13]==0xFFFFFFFF,('all-ones witness',out)
 else:assert out[0]==1 and out[2]>=3 and out[4]==0 and out[7]==0 and out[8]==0,out
 return n
with tempfile.TemporaryDirectory(prefix='xhci-initial-cnr-') as temp:
 work=pathlib.Path(temp);steps=sum(run(work,m) for m in range(5))
 mutants=[('original missing incoming readiness',bodies.replace('  If xh_WaitReady() = 0\n    ProcedureReturn 0\n  EndIf','',1)),('cleanup ignores failed reset',bodies.replace('  If xh_Reset() = 0\n    ProcedureReturn\n  EndIf','  xh_Reset()',1))]
 for label,body in mutants:
  assert body!=bodies,label
  try:run(work,0,body)
  except AssertionError:pass
  else:raise AssertionError('mutant survived: '+label)
 try:run(work,2,bodies.replace('  xh_Trace(6)','  xh_Trace(5)',1))
 except AssertionError:pass
 else:raise AssertionError('missing pre-write marker mutant survived')
 halt_mutants=[
  (3,'HCE refusal stops the reset','    If xh_err <> #XHCI_ERR_HCE\n      ProcedureReturn 0\n    EndIf\n','    ProcedureReturn 0\n'),
  (4,'all-ones read waited out as CNR','    If sts = $FFFFFFFF\n      xh_haltSts0 = sts\n      xh_haltSts1 = sts\n      XhciAccountWait(#XHCI_W_CNR, t0)\n      ProcedureReturn xh_Fail(#XHCI_ERR_GONE)\n    EndIf\n',''),
 ]
 for mode,label,old,new in halt_mutants:
  assert bodies.count(old)==1,('mutant anchor',label,bodies.count(old))
  try:run(work,mode,bodies.replace(old,new,1))
  except AssertionError:pass
  else:raise AssertionError('mutant survived: '+label)
 print('PASS: 5 initial-CNR/ready/HCE/all-ones cases with exact trace order;',steps,'instructions; 5 readiness/cleanup/marker/HCE/all-ones mutants rejected')
 print('Compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
