"""Execute the real adopted PcieInit with a modelled live former DMA owner.

No hardware access. The defect this gate exists for (the adoption path
of an early pcie.pi4, once read from commit f3d6ebb): when the firmware
left the link trained, PcieInit adopted it AND rewrote the root complex's
inbound DMA window (RC_BAR2) before anything had proved the firmware's
xHCI stopped - so a controller still doing DMA had its addresses moved
underneath it. f3d6ebb was lost in the Anvil public-history reset of
2026-09-19/22 (single "source baseline" commit a2935e2); this gate used
to `git show` it and so could not run at all.

It now reads nothing from git. Two builds, both from the CURRENT file:

  * the tree as it is: with the former owner modelled LIVE, adoption must
    succeed and must not change RC_BAR2 (the outbound WIN0 remap that
    locates the live BAR is allowed; the inbound offset is not);
  * the same PcieInit with exactly that defect put back - an inbound
    offset write on the adoption path - which must be caught (hazard > 0).

A live=0 control proves the model does not call every write a hazard.
"""
import argparse,pathlib,re,tempfile,subprocess,os,sys,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as base
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
current=(base.ROOT/'RaspberryPi4/Lib/pcie.pi4').read_text(encoding='utf-8').replace('\r\n','\n')

# The defect, reintroduced: the adoption path rewrites the inbound offset
# (the firmware's $4_0000_0000) while the former owner may still be live.
DEFECT_ANCHOR='    ; existing register BAR for takeover, but keep the inbound offset.\n'
DEFECT_LINE='    pcie_Poke(#PCIE_MISC_RC_BAR2_CONFIG_HI, 0)\n'

def extract(text):
 def proc(n):
  m=re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\([^\n]*\).*?^EndProcedure',text)
  if not m:raise SystemExit('pcie adopt gate: production procedure '+n+' not found')
  return m.group()
 bodies='\n'.join(proc(n) for n in ('PciePrepareAdoption','PcieInit'))
 definitions={m.group(1):m.group(0) for m in re.finditer(r'(?m)^#(\w+)\s*=.*$',text)}
 needed=set(re.findall(r'#(\w+)',bodies))|{'PCIE_MISC_RC_BAR2_CONFIG_LO','PCIE_MISC_RC_BAR2_CONFIG_HI'};pending=list(needed)
 while pending:
  name=pending.pop()
  if name not in definitions:raise AssertionError('missingconstant '+name)
  for dep in re.findall(r'#(\w+)',definitions[name].split(';')[0])[1:]:
   if dep not in needed:needed.add(dep);pending.append(dep)
 return '\n'.join(v for k,v in definitions.items() if k in needed),bodies

model='''
Global pcie_err.i
Global pcie_up.i
Global pcie_adopted.i
Global pcie_adoptCpu.i
Global pcie_resetStarted.i
Global old_live.i=LIVE_VALUE
Global Dim rc.i[9500]
Global hazardous.i
Global regwrites.i
Global resets.i
Procedure.i PcieAddrIsWide()
 ProcedureReturn 1
EndProcedure
Procedure.i PcieLinkUp()
 ProcedureReturn 1
EndProcedure
Procedure pcie_Phase(p.i)
EndProcedure
Procedure delay(ms.i)
EndProcedure
Procedure.i PcieResetAndTrain()
 resets=resets+1
 ProcedureReturn 0
EndProcedure
; The firmware's state: the inbound offset it left ($4_0000_0000, the value
; read on silicon), a trained bridge with bus 1 behind it, and the VL805 -
; an xHCI (class $0C0330) with memory space on and BAR0 inside the bridge
; window at bus $F8000000.
Procedure.i PcieCfgRead32(bus.i,dev.i,fn.i,off.i)
 If bus=0
  If off=$18 : ProcedureReturn $00010100 : EndIf
  If off=$04 : ProcedureReturn $00100006 : EndIf
  If off=$20 : ProcedureReturn $FBF0F800 : EndIf
  ProcedureReturn 0
 EndIf
 If off=$08 : ProcedureReturn $0C033001 : EndIf
 If off=$04 : ProcedureReturn $00100006 : EndIf
 If off=$10 : ProcedureReturn $F8000004 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i PcieRcPeek(off.i)
 ProcedureReturn rc[off/4]
EndProcedure
Procedure pcie_Poke(off.i,value.i)
 regwrites=regwrites+1
 If off=#PCIE_MISC_RC_BAR2_CONFIG_LO Or off=#PCIE_MISC_RC_BAR2_CONFIG_HI
  If rc[off/4]<>(value & $FFFFFFFF) And old_live<>0 : hazardous=hazardous+1 : EndIf
 EndIf
 rc[off/4]=value & $FFFFFFFF
EndProcedure
Procedure pcie_Modify(off.i,clear.i,set.i)
 pcie_Poke(off,(rc[off/4] & ~clear) | set)
EndProcedure
Procedure GateFirmwareState()
 rc[#PCIE_MISC_RC_BAR2_CONFIG_LO/4]=15
 rc[#PCIE_MISC_RC_BAR2_CONFIG_HI/4]=4
EndProcedure
'''
main='''
Procedure.i Main()
 GateFirmwareState()
 PokeI($06000000,PcieInit())
 PokeI($06000008,hazardous)
 PokeI($06000010,old_live)
 PokeI($06000018,rc[#PCIE_MISC_RC_BAR2_CONFIG_HI/4])
 PokeI($06000020,regwrites)
 PokeI($06000028,resets)
 ProcedureReturn 0
EndProcedure
'''

def run(text,live,work):
 constants,bodies=extract(text)
 src=work/'probe.pi4';out=work/'probe.img';src.write_text(constants+model.replace('LIVE_VALUE',str(live))+bodies+main)
 env=os.environ.copy();env['PMF_ROOT']=str(base.ROOT)
 r=subprocess.run([args.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-o',str(out)],cwd=base.ROOT,env=env,capture_output=True,text=True)
 if r.returncode or not out.exists():raise SystemExit(r.stdout+r.stderr)
 cpu=a64.A64()
 for n,b in enumerate(out.read_bytes()):cpu.memory[base.LOAD+n]=b
 cpu.pc=base.LOAD;cpu.sp=base.STACK;cpu.x[30]=base.RETURN_PC
 for n in range(400000):
  if cpu.pc==base.RETURN_PC:break
  cpu.step()
 else:raise AssertionError('didnotreturn')
 return [base.u64(cpu,base.OUT+8*i) for i in range(6)]

a64=base.load_interpreter(base.INTERP)
if current.count(DEFECT_ANCHOR)!=1:raise SystemExit('pcie adopt gate: defect anchor must match once in PcieInit - re-aim it')
defect=current.replace(DEFECT_ANCHOR,DEFECT_ANCHOR+DEFECT_LINE)
fails=[]
with tempfile.TemporaryDirectory(prefix='pcie-adopt-order-') as tmp:
 work=pathlib.Path(tmp)
 for label,text in (('tree',current),('defect reintroduced',defect)):
  for live in (0,1):
   v=run(text,live,work)
   print(label,'live=',live,'result/hazard/live/inbound_hi/writes/resets=',v)
   if live==0 and v[1]!=0:fails.append(label+': the inactive control was called hazardous - the model is wrong')
   if label=='tree' and live==1:
    if v[0]!=1:fails.append('tree: adoption did not succeed against the modelled firmware state')
    if v[1]!=0:fails.append('tree: adoption changed the inbound DMA window while the former owner was live')
    if v[3]!=4:fails.append('tree: the firmware inbound offset was not preserved through adoption')
    if v[5]!=0:fails.append('tree: a trained link was reset instead of adopted')
   if label!='tree' and live==1 and v[1]==0:
    fails.append('defect reintroduced: NOT caught - this gate could not have caught f3d6ebb')
print('Compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
for f in fails:print('FAIL',f)
if fails:raise SystemExit(1)
print('PASS: adoption leaves the inbound window alone while the modelled former owner is live; the reintroduced f3d6ebb defect is caught')
