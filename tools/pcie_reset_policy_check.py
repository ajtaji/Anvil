"""Execute actual reset/retrain and enumeration admission; fake RC only."""
import pathlib,re,sys,tempfile,subprocess,os,argparse
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as b
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args()
s=(b.ROOT/'RaspberryPi4/Lib/pcie.pi4').read_text()
def proc(n):return re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\([^\n]*\).*?^EndProcedure',s).group()
reset=proc('PcieResetAndTrain')
admission=proc('PcieEnumerate').split('  pcie_Phase(#PCIE_PH_BUSNUM)')[0]+'\n ProcedureReturn 1\nEndProcedure\n'
body=reset+'\n'+admission+'\n'+proc('PcieNeedsTakeover')
defs={m[1]:m[0] for m in re.finditer(r'(?m)^#(\w+)\s*=.*$',s)}
needed=set(re.findall(r'#(\w+)',body));pending=list(needed)
while pending:
 for dep in re.findall(r'#(\w+)',defs[pending.pop()].split(';')[0])[1:]:
  if dep not in needed:needed.add(dep);pending.append(dep)
const='\n'.join(v for k,v in defs.items() if k in needed)
globals='pcie_resetStarted pcie_up pcie_enumerated pcie_adopted pcie_adoptCpu pcie_adoptHalted pcie_barBus pcie_barCpu pcie_barSize pcie_dmaOff pcie_dmaOffRead pcie_vl805Ready pcie_err'.split()
model='\n'.join('Global '+n+'.i' for n in globals)+'''
Global elapsed.i
Global released.i=-1
Global asserted.i
Global hazard.i
Global mode.i=MODE
Dim regs.i[10000]
Procedure pcie_Phase(p.i) : EndProcedure
Procedure delay(ms.i) : elapsed=elapsed+ms : EndProcedure
Procedure.i PcieCfgRead32(b.i,d.i,f.i,o.i) : ProcedureReturn 2 : EndProcedure
Procedure.i PcieRcPeek(o.i)
 If o=#PCIE_MISC_PCIE_STATUS : ProcedureReturn 128 : EndIf
 ProcedureReturn regs[o/4]
EndProcedure
Procedure pcie_Poke(o.i,v.i)
 regs[o/4]=v
EndProcedure
Procedure pcie_Modify(o.i,clear.i,set.i)
 regs[o/4]=(regs[o/4] & (~clear)) | set
 If o=#PCIE_RGR1_SW_INIT_1
  If (set & 1)<>0
   asserted=asserted+1
  EndIf
  If (clear & 1)<>0
   If asserted=0 Or elapsed<2 : hazard=hazard+1 : EndIf
   released=elapsed
  EndIf
 EndIf
EndProcedure
Procedure.i PcieLinkUp()
 If released<0 Or elapsed-released<100 : hazard=hazard+1 : EndIf
 ProcedureReturn mode<>1
EndProcedure
Procedure.i PcieProgramWindow()
 If released<0 Or elapsed-released<100 : hazard=hazard+1 : EndIf
 ProcedureReturn 1
EndProcedure
'''
main='''
Procedure.i Main()
 pcie_up=1
 pcie_adopted=1
 pcie_adoptHalted=1
 If mode=2 : pcie_adoptHalted=0 : EndIf
 regs[#PCIE_MISC_HARD_PCIE_HARD_DEBUG/4]=$FFFFFFFF
 regs[#PCIE_RC_CFG_PRIV1_LINK_CAPABILITY/4]=$FFFFFFFF
 PokeI($06000000,PcieEnumerate())
 PokeI($06000008,hazard)
 PokeI($06000010,asserted)
 PokeI($06000018,regs[#PCIE_MISC_MISC_CTRL/4])
 PokeI($06000020,regs[#PCIE_MISC_HARD_PCIE_HARD_DEBUG/4])
 PokeI($06000028,regs[#PCIE_RC_CFG_PRIV1_LINK_CAPABILITY/4])
 PokeI($06000030,pcie_up)
 ProcedureReturn 0
EndProcedure
'''
interp=b.load_interpreter(b.INTERP)
def run(w,text,mode):
 src=w/'reset.pi4';img=w/'reset.img';src.write_text(const+model.replace('MODE',str(mode))+text+main)
 env=os.environ.copy();env['PMF_ROOT']=str(b.ROOT)
 r=subprocess.run([a.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(b.LOAD),'--stack-addr',hex(b.STACK),'-o',str(img)],cwd=b.ROOT,env=env,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 c=interp.A64();c.memory.update({b.LOAD+i:v for i,v in enumerate(img.read_bytes())});c.pc=b.LOAD;c.sp=b.STACK;c.x[30]=b.RETURN_PC
 for i in range(300000):
  if c.pc==b.RETURN_PC:break
  c.step()
 else:raise RuntimeError('instruction limit')
 v=[b.u64(c,b.OUT+8*i) for i in range(7)]
 assert v[1]==0,v
 if mode==2:assert v[0]==0 and v[2]==0,v
 elif mode==1:assert v[0]==0 and v[2]==1 and v[6]==0,v
 else:
  assert v[0]==1 and v[2]==1 and v[6]==1,v
  assert v[3]&0x480==0x480,v
  assert v[4]&0x310002==0x110000,v
  assert v[5]&0xc00==0,v
 return v
with tempfile.TemporaryDirectory(prefix='pcie-reset-policy-') as tmp:
 w=pathlib.Path(tmp)
 for mode in range(3):print(mode,run(w,body,mode))
 mutants=[body.replace(' | #PCIE_MISC_CTRL_RCB_64B_MODE | #PCIE_MISC_CTRL_RCB_MPS_MODE)',' | #PCIE_MISC_CTRL_RCB_MPS_MODE)',1),body.replace(' | #PCIE_MISC_CTRL_RCB_MPS_MODE)',' )',1),body.replace('delay(100)','delay(1)',1),body.replace('#PCIE_HARD_DEBUG_CLKREQ_SAFE)','#PCIE_HARD_DEBUG_CLKREQ_MASK)',1),body.replace('  pcie_Modify(#PCIE_RC_CFG_PRIV1_LINK_CAPABILITY, #PCIE_LINK_CAPABILITY_ASPM_SUPPORT_MASK, 0)','',1)]
 mutants.append(body.replace('    If PcieResetAndTrain() = 0','    If 1 = 0',1))
 for mutant in mutants:
  assert mutant!=body
  try:run(w,mutant,0)
  except AssertionError:pass
  else:raise AssertionError('policy mutant survived')
print('PASS reset admission, failed link, unsafe ownership refusal; six policy/order mutants rejected')
