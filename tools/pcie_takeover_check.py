"""Desk gate of actual PCIe adoption preparation and xHCI quiescence."""
import argparse,pathlib,re,tempfile,subprocess,os,sys,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as b
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args()
pc=(b.ROOT/'RaspberryPi4/Lib/pcie.pi4').read_text()
xh=(b.ROOT/'RaspberryPi4/Lib/xhci.pi4').read_text()
def proc(s,n):return re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\([^\n]*\).*?^EndProcedure',s).group()
body='\n'.join(proc(pc,n) for n in ('PcieAdoptCpu','PcieNeedsTakeover','PcieAdoptHalted','PciePrepareAdoption','PcieProgramWindow','PcieEnumerate','PcieEnableDma'))+'\n'+proc(xh,'XhciQuiesceAdopted')+'\n'+proc(xh,'xh_EnableDma')
defs={m[1]:m[0] for m in re.finditer(r'(?m)^#(\w+)\s*=.*$',pc+'\n'+xh)}
prefix=proc(xh,'XhciInitAt').split('  xh_err   = #XHCI_ERR_NONE')[0]
body+='\n'+prefix.replace('XhciInitAt(','ProbeBdf(')+'\n ProcedureReturn 1\nEndProcedure\n'
needed=set(re.findall(r'#(\w+)',body));pending=list(needed)
while pending:
 for dep in re.findall(r'#(\w+)',defs[pending.pop()].split(';')[0])[1:]:
  if dep not in needed:needed.add(dep);pending.append(dep)
const='\n'.join(v for k,v in defs.items() if k in needed)
model="""
Global pcie_err.i,pcie_adoptCpu.i,pcie_adoptHalted.i,xh_err.i
Global pcie_adopted.i=1,cmd.i=6,live.i=1,ticks.i,reads.i,hazard.i
Global mode.i=MODE
Global pcie_up.i=1,pcie_enumerated.i,pcie_barBus.i,pcie_barCpu.i,pcie_barSize.i
Global epbar.i=$C0000004,bridgewin.i=$C000C000
Global inboundlow.i=15,inboundhigh.i=4
Dim rc.i(10000)
Procedure xh_Phase(p.i) : EndProcedure
Procedure.i xh_Fail(reason.i) : xh_err=reason : ProcedureReturn 0 : EndProcedure
Procedure pcie_Phase(p.i) : EndProcedure
Procedure.i PcieCpuFromBus(v.i) : ProcedureReturn #PCIE_OUT_CPU+v-#PCIE_OUT_BUS : EndProcedure
Procedure.i PcieBarSize(b.i,d.i,f.i,o.i)
 If live<>0 Or (cmd & 6)<>0 : hazard=hazard+1 : EndIf
 ProcedureReturn 65536
EndProcedure
Procedure.i PcieCfgRead32(b.i,d.i,f.i,o.i)
 If b=0
  If o=$18 : ProcedureReturn $10100 : EndIf
  If o=4 : ProcedureReturn 6 : EndIf
  If o=$20
   If mode=5 : ProcedureReturn 0 : EndIf
   ProcedureReturn bridgewin
  EndIf
 Else
  If o=0 : ProcedureReturn $34831106 : EndIf
  If o=8 : ProcedureReturn $0C033000 : EndIf
  If o=4 : ProcedureReturn cmd | $A0000000 : EndIf
  If o=$10 : ProcedureReturn epbar : EndIf
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure PcieCfgWrite32(b.i,d.i,f.i,o.i,v.i)
 If o=4 And (v & $FFFF0000)<>0 : hazard=hazard+1 : EndIf
 If b=1 And o=4
  If live<>0 : hazard=hazard+1 : EndIf
  If mode<>3 And (mode<>8 Or (v & 4)=0) : cmd=v : EndIf
 EndIf
 If b=0 And o=$20 : bridgewin=v : EndIf
 If b=1 And o=$10
  If live<>0 Or (cmd & 6)<>0 : hazard=hazard+1 : EndIf
  epbar=v
 EndIf
EndProcedure
Procedure pcie_Poke(o.i,v.i)
 If mode>=9 And o=#PCIE_MISC_WIN0_LO And v=#PCIE_OUT_BUS
  ProcedureReturn
 EndIf
 If o=$4034 Or o=$4038
  If live<>0 Or (cmd & 4)<>0 : hazard=hazard+1 : EndIf
  If o=$4034 : inboundlow=v : EndIf
  If o=$4038 : inboundhigh=v : EndIf
 EndIf
 rc[o/4]=v
EndProcedure
Procedure.i PcieRcPeek(o.i)
 If o=$4034 : ProcedureReturn inboundlow : EndIf
 If o=$4038 : ProcedureReturn inboundhigh : EndIf
 ProcedureReturn rc[o/4]
EndProcedure
Procedure.i xh_TickHz() : ProcedureReturn 1000000 : EndProcedure
Procedure.i xh_Ticks() : ticks=ticks+1000 : ProcedureReturn ticks : EndProcedure
Procedure.i xh_Rd(base.i,o.i)
 reads=reads+1
 If base=#PCIE_OUT_CPU And o=0 : ProcedureReturn $01000040 : EndIf
 If o=#XHCI_USBSTS
  If mode=1 Or (mode=4 And ticks<4000) : ProcedureReturn #XHCI_STS_CNR : EndIf
  If live=0 : ProcedureReturn #XHCI_STS_HALT : EndIf
 EndIf
 If o=#XHCI_USBCMD : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure xh_Wr(base.i,o.i,v.i)
 If mode=1 Or (mode=4 And ticks<4000) : hazard=hazard+1 : EndIf
 If mode<>2 : live=0 : EndIf
EndProcedure
"""
main="""
Procedure.i Main()
 Define x.i,y.i
 Define z.i
 If mode=7
  pcie_adopted=0
  live=0
  inboundhigh=0
  PcieProgramWindow()
  x=1
 Else
  x=PciePrepareAdoption()
 EndIf
 If mode=6
  z=PcieEnumerate()
 Else
  If x<>0 : y=XhciQuiesceAdopted() : EndIf
  If y<>0 : z=PcieEnumerate() : EndIf
 EndIf
 PokeI($6000000,x)
 PokeI($6000008,y)
 PokeI($6000010,hazard)
 PokeI($6000018,pcie_adoptHalted)
 PokeI($6000020,cmd)
 PokeI($6000028,reads)
 PokeI($6000030,z)
 PokeI($6000038,inboundhigh)
 If mode=8 : PokeI($6000040,xh_EnableDma()) : EndIf
 PokeI($6000048,xh_err)
 ProcedureReturn 0
EndProcedure
"""
interp=b.load_interpreter(b.INTERP)
model=re.sub(r'(?m)^Global (.*)$',lambda m:'\n'.join('Global '+v for v in m[1].split(',')),model)
main=main.replace('Define x.i,y.i','Define x.i\n Define y.i')
with tempfile.TemporaryDirectory(prefix='pcie-takeover-') as tmp:
 w=pathlib.Path(tmp)
 for mode in range(15):
  entry=main
  if mode==10:entry='Procedure.i Main()\n PokeI($6000000,PcieProgramWindow())\n PokeI($6000008,reads)\n PokeI($6000010,inboundhigh)\n ProcedureReturn 0\nEndProcedure'
  if mode>=11:
   args_bdf={11:'2,0,0',12:'1,1,0',13:'1,0,1',14:'1,0,0'}[mode]
   entry='Procedure.i Main()\n PokeI($6000000,ProbeBdf('+args_bdf+'))\n PokeI($6000008,xh_err)\n PokeI($6000010,cmd)\n PokeI($6000018,reads)\n ProcedureReturn 0\nEndProcedure'
  src=w/'test.pi4';out=w/'test.img';src.write_text(const+model.replace('MODE',str(mode))+body+'\n'+entry)
  env=os.environ.copy();env['PMF_ROOT']=str(b.ROOT)
  r=subprocess.run([a.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(b.LOAD),'--stack-addr',hex(b.STACK),'-o',str(out)],env=env,cwd=b.ROOT,capture_output=True,text=True)
  if r.returncode or not out.exists():raise SystemExit(r.stdout+r.stderr)
  cpu=interp.A64()
  for i,v in enumerate(out.read_bytes()):cpu.memory[b.LOAD+i]=v
  cpu.pc=b.LOAD;cpu.sp=b.STACK;cpu.x[30]=b.RETURN_PC
  for n in range(1000000):
   if cpu.pc==b.RETURN_PC:break
   cpu.step()
  else:raise AssertionError('deadline failed')
  v=[b.u64(cpu,b.OUT+8*i) for i in range(10)]
  print(mode,v,n)
  if mode>=11:
   assert v[:4]==([1,0,6,0] if mode==14 else [0,45,6,0]),v
   continue
  if mode==10:
   assert v[:3]==[0,0,4],v
   continue
  assert v[2]==0,v
  if mode in (0,4,8):assert v[:2]==[1,1] and v[3:5]==[1,2],v
  elif mode==9:assert v[:2]==[1,1] and v[3:5]==[1,0],v
  elif mode==7:assert v[:2]==[1,1] and v[3:6]==[0,2,0],v
  else:assert v[1]==0 and v[3]==0,v
  if mode==5:assert v[0]==0 and v[5]==0,v
  if mode in (0,4,7,8):assert v[6:8]==[1,0],v
  elif mode==9:assert v[6:8]==[0,0],v
  else:assert v[6:8]==[0,4],v
  if mode==8:assert v[8:10]==[0,44],v
  if mode==3:assert v[9]==45,v
 assert 'If PcieProgramWindow() = 0' in proc(pc,'PcieInit')
 assert 'If PcieProgramWindow() = 0' in proc(pc,'PcieEnumerate')
 print('PASS fifteen cases; compiler SHA256',hashlib.sha256(pathlib.Path(a.compiler).read_bytes()).hexdigest())
