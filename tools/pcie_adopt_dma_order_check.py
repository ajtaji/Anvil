"""Execute real adopted PcieInit with a modeled live former DMA owner.

No hardware access; failure demonstrates missing quiescence precondition,
not that this board's firmware actually left an active xHC.
"""
import argparse,pathlib,re,tempfile,subprocess,os,sys,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as base
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args()
text=subprocess.check_output(['git','show','f3d6ebb:RaspberryPi4/Lib/pcie.pi4'],cwd=base.ROOT,text=True)
bodies='\n'.join(re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\(\).*?^EndProcedure',text).group() for n in ('PcieProgramWindow','PcieInit'))
definitions={m.group(1):m.group(0) for m in re.finditer(r'(?m)^#(\w+)\s*=.*$',text)}
needed=set(re.findall(r'#(\w+)',bodies));pending=list(needed)
while pending:
 name=pending.pop()
 if name not in definitions:raise AssertionError('missingconstant '+name)
 for dep in re.findall(r'#(\w+)',definitions[name].split(';')[0])[1:]:
  if dep not in needed:needed.add(dep);pending.append(dep)
constants='\n'.join(v for k,v in definitions.items() if k in needed)
model='''
Global pcie_err.i
Global pcie_up.i
Global pcie_adopted.i
Global old_live.i=LIVE_VALUE
Global inbound_low.i=15
Global inbound_high.i=4
Global hazardous.i
Global regwrites.i
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
Procedure.i PcieRcPeek(off.i)
 If off=#PCIE_MISC_RC_BAR2_CONFIG_LO : ProcedureReturn inbound_low : EndIf
 If off=#PCIE_MISC_RC_BAR2_CONFIG_HI : ProcedureReturn inbound_high : EndIf
 ProcedureReturn 0
EndProcedure
Procedure pcie_Poke(off.i,value.i)
 regwrites=regwrites+1
 If off=#PCIE_MISC_RC_BAR2_CONFIG_LO
  If inbound_low<>value And old_live<>0 : hazardous=hazardous+1 : EndIf
  inbound_low=value
 EndIf
 If off=#PCIE_MISC_RC_BAR2_CONFIG_HI
  If inbound_high<>value And old_live<>0 : hazardous=hazardous+1 : EndIf
  inbound_high=value
 EndIf
EndProcedure
Procedure pcie_Modify(off.i,clear.i,set.i)
 pcie_Poke(off,set)
EndProcedure
'''
main='''
Procedure.i Main()
 PokeI($06000000,PcieInit())
 PokeI($06000008,hazardous)
 PokeI($06000010,old_live)
 PokeI($06000018,inbound_high)
 PokeI($06000020,regwrites)
 ProcedureReturn 0
EndProcedure
'''
a64=base.load_interpreter(base.INTERP)
with tempfile.TemporaryDirectory(prefix='pcie-adopt-order-') as tmp:
 work=pathlib.Path(tmp);results=[]
 for live in (0,1):
  src=work/'probe.pi4';out=work/'probe.img';src.write_text(constants+model.replace('LIVE_VALUE',str(live))+bodies+main)
  env=os.environ.copy();env['PMF_ROOT']=str(base.ROOT)
  r=subprocess.run([args.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-o',str(out)],cwd=base.ROOT,env=env,capture_output=True,text=True)
  if r.returncode or not out.exists():raise SystemExit(r.stdout+r.stderr)
  cpu=a64.A64()
  for n,b in enumerate(out.read_bytes()):cpu.memory[base.LOAD+n]=b
  cpu.pc=base.LOAD;cpu.sp=base.STACK;cpu.x[30]=base.RETURN_PC
  for n in range(100000):
   if cpu.pc==base.RETURN_PC:break
   cpu.step()
  else:raise AssertionError('didnotreturn')
  values=[base.u64(cpu,base.OUT+8*i) for i in range(5)]
  results.append(values)
  print('former DMA owner live=',live,'result/hazard/live/high/writecount=',values,'instructions=',n)
 assert results[0][1]==0,'inactive control unexpectedlyhazardous'
 print('Compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
 if results[1][1]:
  print('REPRODUCED: accepted adoption changes DMA mapping with no prior-owner quiescence proof')
  raise SystemExit(1)
 print('PASS: no mapping change while modeled former owner active')
