"""Execute actual reset/retrain and enumeration admission; fake RC only.

The PHY side is faked the same way the root complex is. pcie_SetSsc,
pcie_ReadLinkStatus and the pcie_Mdio* pair they ride on are not under test
here - what is under test is WHEN the production PcieResetAndTrain calls
them. Spread-spectrum clocking is programmed through the PHY's own MDIO bus,
which only answers once the link is trained (U-Boot brcm_pcie_probe does it
after the link report, pcie_brcmstb.c:476-489), so the fakes count a call
made before PcieLinkUp has ever answered yes as a hazard, and the ssc-early
mutant below moves the call up to prove that catch is live.
"""
import pathlib,re,sys,tempfile,subprocess,os,argparse
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import el3_runtime_emitted_check as b
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
s=(b.ROOT/'RaspberryPi4/Lib/pcie.pi4').read_text()
def proc(n):return re.search(r'(?ms)^Procedure(?:\.i)? '+n+r'\([^\n]*\).*?^EndProcedure',s).group()
reset=proc('PcieResetAndTrain')
admission=proc('PcieEnumerate').split('  pcie_Phase(#PCIE_PH_BUSNUM)')[0]+'\n ProcedureReturn 1\nEndProcedure\n'
body=reset+'\n'+admission+'\n'+proc('PcieNeedsTakeover')+chr(10)+proc('PcieInboundSizeCode')
defs={m[1]:m[0] for m in re.finditer(r'(?m)^#(\w+)\s*=.*$',s)}
needed=set(re.findall(r'#(\w+)',body));pending=list(needed)
while pending:
 for dep in re.findall(r'#(\w+)',defs[pending.pop()].split(';')[0])[1:]:
  if dep not in needed:needed.add(dep);pending.append(dep)
# THE TRAILING NEWLINE IS LOAD-BEARING. The constant block is concatenated
# straight onto the model below, and its last line ends in a COMMENT - so
# without this the first `Global` of the model was glued to the end of that
# comment and never declared at all. It swallowed pcie_resetStarted quietly
# for as long as this gate has existed, and it swallowed pcie_memBytes on
# the day the window started being sized from it, which is how it was found.
const='\n'.join(v for k,v in defs.items() if k in needed)+'\n'
globals='pcie_memBytes pcie_resetStarted pcie_up pcie_enumerated pcie_adopted pcie_adoptCpu pcie_adoptHalted pcie_barBus pcie_barCpu pcie_barSize pcie_dmaOff pcie_dmaOffRead pcie_vl805Ready pcie_err pcie_linkSpeed pcie_linkWidth pcie_sscOk pcie_sscCntlRaw pcie_sscStatusRaw'.split()
model='\n'.join('Global '+n+'.i' for n in globals)+'''
Global elapsed.i
Global released.i=-1
Global asserted.i
Global hazard.i
Global mode.i=MODE
Global linkUpSeen.i
Global sscCalls.i
Global lnkCalls.i
Global sscBeforeLink.i
Dim regs.i[10000]
Dim mdio.i[64]
Procedure pcie_Phase(p.i) : EndProcedure
Procedure delay(ms.i) : elapsed=elapsed+ms : EndProcedure
Procedure.i PcieCfgRead32(b.i,d.i,f.i,o.i) : ProcedureReturn 2 : EndProcedure
Procedure.i PcieRcPeek(o.i)
 If o=#PCIE_MISC_PCIE_STATUS : ProcedureReturn 128 : EndIf
 ProcedureReturn regs[o/4]
EndProcedure
; THE INBOUND WINDOW REGISTERS, modelled as silicon that may not take what
; it is given. Mode 3 is a RC_BAR2_CONFIG_LO that ignores the write, mode 4
; a MISC_CTRL whose SCB0 field will not move, mode 5 a CONFIG_HI that comes
; back holding an offset. All three are what forum 916 looked like from
; inside this file before anything read the pair back.
Procedure pcie_Poke(o.i,v.i)
 If mode=3 And o=#PCIE_MISC_RC_BAR2_CONFIG_LO
  ; the register ignores the write
 ElseIf mode=5 And o=#PCIE_MISC_RC_BAR2_CONFIG_HI
  regs[o/4]=$40
 Else
  regs[o/4]=v
 EndIf
EndProcedure
Procedure pcie_Modify(o.i,clear.i,set.i)
 If mode=4 And o=#PCIE_MISC_MISC_CTRL
  set=set & (~#PCIE_MISC_CTRL_SCB0_SIZE_MASK)
 EndIf
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
 If mode<>1 : linkUpSeen=1 : EndIf
 ProcedureReturn mode<>1
EndProcedure
Procedure.i PcieProgramWindow()
 If released<0 Or elapsed-released<100 : hazard=hazard+1 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i pcie_MdioRead(regad.i)
 ProcedureReturn mdio[regad & 63]
EndProcedure
Procedure.i pcie_MdioWrite(regad.i,v.i)
 mdio[regad & 63]=v
 ProcedureReturn 1
EndProcedure
Procedure.i pcie_SetSsc()
 If linkUpSeen=0 : sscBeforeLink=sscBeforeLink+1 : hazard=hazard+1 : EndIf
 sscCalls=sscCalls+1
 pcie_MdioWrite(31,$1100)
 pcie_sscCntlRaw=$C000
 pcie_sscStatusRaw=$0C00
 ProcedureReturn pcie_MdioRead(2)
EndProcedure
Procedure pcie_ReadLinkStatus()
 If linkUpSeen=0 : hazard=hazard+1 : EndIf
 lnkCalls=lnkCalls+1
 pcie_linkSpeed=2
 pcie_linkWidth=1
EndProcedure
'''
main='''
Procedure.i Main()
 pcie_memBytes=MEMBYTES
 ; A PREVIOUS, SUCCESSFUL TRAIN'S FACTS, PLANTED BEFORE THIS ONE STARTS.
 ; Every retrain begins with a link already described somewhere - that is
 ; what a RE-train is - so the interesting state is not a fresh boot but a
 ; second attempt, and these five are what a reader sees.
 pcie_linkSpeed=2
 pcie_linkWidth=1
 pcie_sscOk=1
 pcie_sscCntlRaw=$C000
 pcie_sscStatusRaw=$0C00
 pcie_up=1
 pcie_adopted=1
 pcie_adoptHalted=1
 If mode=2 : pcie_adoptHalted=0 : EndIf
 regs[#PCIE_MISC_HARD_PCIE_HARD_DEBUG/4]=$FFFFFFFF
 regs[#PCIE_RC_CFG_PRIV1_LINK_CAPABILITY/4]=$FFFFFFFF
 mdio[2]=1
 PokeI($06000000,PcieEnumerate())
 PokeI($06000008,hazard)
 PokeI($06000010,asserted)
 PokeI($06000018,regs[#PCIE_MISC_MISC_CTRL/4])
 PokeI($06000020,regs[#PCIE_MISC_HARD_PCIE_HARD_DEBUG/4])
 PokeI($06000028,regs[#PCIE_RC_CFG_PRIV1_LINK_CAPABILITY/4])
 PokeI($06000030,pcie_up)
 PokeI($06000038,sscCalls)
 PokeI($06000040,lnkCalls)
 PokeI($06000048,sscBeforeLink)
 PokeI($06000050,pcie_err)
 PokeI($06000058,regs[#PCIE_MISC_RC_BAR2_CONFIG_LO/4])
 PokeI($06000060,pcie_linkSpeed)
 PokeI($06000068,pcie_linkWidth)
 PokeI($06000070,pcie_sscOk)
 PokeI($06000078,pcie_sscCntlRaw)
 PokeI($06000080,pcie_sscStatusRaw)
 PokeI($06000088,regs[#PCIE_RC_CFG_PRIV1_ROOT_CAP/4])
 ProcedureReturn 0
EndProcedure
'''
interp=b.load_interpreter(b.INTERP)
# THE SIZES A Pi 4 IS SOLD WITH, and the inbound size code each one must
# produce: log2(size)-15, capped at 17 because the wrapper erratum stops
# inbound DMA at 3 GiB and every code above 17 describes address space no
# transfer can reach. 0 is a board that never said, which is every build
# that includes the library on its own, and it falls back to 17.
SIZES=((0,17),(0x40000000,15),(0x80000000,16),(0x100000000,17),(0x200000000,17))
def run(w,text,mode,mem=0,code=None):
 if code is None:code=dict(SIZES)[mem]
 src=w/'reset.pi4';img=w/'reset.img';src.write_text(const+model.replace('MODE',str(mode))+text+main.replace('MEMBYTES',str(mem)))
 env=os.environ.copy();env['PMF_ROOT']=str(b.ROOT)
 r=subprocess.run([a.compiler,'--compile',str(src),'-t','pi4','--entry-returns','--load-addr',hex(b.LOAD),'--stack-addr',hex(b.STACK),'-o',str(img)],cwd=b.ROOT,env=env,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 c=interp.A64();c.memory.update({b.LOAD+i:v for i,v in enumerate(img.read_bytes())});c.pc=b.LOAD;c.sp=b.STACK;c.x[30]=b.RETURN_PC
 for i in range(300000):
  if c.pc==b.RETURN_PC:break
  c.step()
 else:raise RuntimeError('instruction limit')
 v=[b.u64(c,b.OUT+8*i) for i in range(18)]
 for i in (10,12,13,14,15,16):
  v[i]=v[i]-(1<<64) if v[i]>=(1<<63) else v[i]
 assert v[1]==0,v
 # A RETRAIN THAT DID NOT FINISH MUST NOT LEAVE THE OLD LINK STANDING.
 # Modes 1 to 5 all return before pcie_ReadLinkStatus is ever reached, so
 # the speed, the width, the spread-spectrum verdict and the two PHY words
 # planted by the previous train have to read -1 - this file's own word for
 # "not asked". A number left over from a link that no longer exists is
 # worse than no number, because it is indistinguishable from a fresh one.
 # Mode 2 is refused BEFORE the retrain is entered - unsafe ownership - so
 # nothing has torn the link down and the previous facts are still true.
 # Modes 1, 3, 4 and 5 all enter PcieResetAndTrain and leave it early.
 if mode in (1,3,4,5):
  assert v[12]==-1 and v[13]==-1 and v[14]==-1 and v[15]==-1 and v[16]==-1,('stale link facts survived a failed retrain',mode,v)
 if mode==2:assert v[0]==0 and v[2]==0 and v[7]==0,v
 elif mode==1:assert v[0]==0 and v[2]==1 and v[6]==0 and v[7]==0 and v[8]==0,v
 elif mode in (3,4,5):
  # The window did not take the size it was given, or came back with an
  # offset. Enumeration must refuse, name the reason, and never publish the
  # link - and it happens before training, so SSC is never attempted.
  assert v[0]==0 and v[6]==0 and v[7]==0 and v[8]==0,v
  assert v[10]==(-10 if mode==5 else -16),v
 else:
  assert v[0]==1 and v[2]==1 and v[6]==1,v
  assert v[3]&0x480==0x480,v
  # SCB_MAX_BURST_SIZE. 0 is how 128 bytes is spelled on this part and 128
  # is what Linux picks for it; the field is asserted rather than left to
  # whatever clearing a mask happens to produce, so that the day somebody
  # writes a value here it has to be the right one.
  assert v[3]&0x300000==0,('burst is not 128 bytes',v)
  # L1SS UN-ADVERTISED. The clock policy drives refclk unconditionally, so
  # the capability that offers an endpoint an L1 substate behind it must be
  # withdrawn in the same breath. Field is bits 7:3, value 2.
  assert v[17]&0xF8==0x10,('L1SS still advertised while the reference clock is driven',v)
  # And a train that DID finish publishes the link it trained.
  assert v[12]==2 and v[13]==1 and v[14]==1,v
  assert v[15]==0xC000 and v[16]==0x0C00,('the PHY words were not kept',v)
  # THE WINDOW IS THE SIZE OF THE MEMORY. Both registers, because the
  # window is only as large as the smaller of them: RC_BAR2_CONFIG_LO's
  # low five bits are the BAR size the endpoint sees and MISC_CTRL bits
  # 31:27 are the SCB0 size the wrapper enforces.
  assert v[11]&0x1F==code,(code,v)
  assert (v[3]>>27)&0x1F==code,(code,v)
  assert v[4]&0x310002==0x110000,v
  assert v[5]&0xc00==0,v
  # SSC asked for once and the trained link read once, both after link-up.
  assert v[7]==1 and v[8]==1 and v[9]==0,v
 return v
with tempfile.TemporaryDirectory(prefix='pcie-reset-policy-') as tmp:
 w=pathlib.Path(tmp)
 for mode in range(6):print(mode,run(w,body,mode))
 # AND EACH SIZE A Pi 4 IS SOLD WITH. Mode 0 is the healthy root complex,
 # so what is under test here is only the arithmetic and the readback: the
 # window programmed, both registers agreeing, and the check passing
 # against the value that was chosen rather than against a constant.
 for mem,want in SIZES[1:]:print(hex(mem),want,run(w,body,0,mem))
 mutants=[body.replace(' | #PCIE_MISC_CTRL_RCB_64B_MODE | #PCIE_MISC_CTRL_RCB_MPS_MODE)',' | #PCIE_MISC_CTRL_RCB_MPS_MODE)',1),body.replace(' | #PCIE_MISC_CTRL_RCB_MPS_MODE)',' )',1),body.replace('delay(100)','delay(1)',1),body.replace('#PCIE_HARD_DEBUG_CLKREQ_SAFE)','#PCIE_HARD_DEBUG_CLKREQ_MASK)',1),body.replace('  pcie_Modify(#PCIE_RC_CFG_PRIV1_LINK_CAPABILITY, #PCIE_LINK_CAPABILITY_ASPM_SUPPORT_MASK, 0)','',1)]
 mutants.append(body.replace('    If PcieResetAndTrain() = 0','    If 1 = 0',1))
 # The PHY block, moved up to before PERST is released: SSC over MDIO on a
 # link that has not trained. Must go red, or the order is not being checked.
 ssc='  pcie_sscOk = pcie_SetSsc()\n  pcie_ReadLinkStatus()\n'
 assert body.count(ssc)==1 and body.count('  pcie_Phase(#PCIE_PH_TRAIN)\n')==1
 mutants.append(body.replace(ssc,'',1).replace('  pcie_Phase(#PCIE_PH_TRAIN)\n',ssc+'  pcie_Phase(#PCIE_PH_TRAIN)\n',1))
 # And dropped altogether, so that "asked for once" is a claim something can break.
 mutants.append(body.replace(ssc,'',1))
 # THE OLD LINK'S FACTS LEFT STANDING ACROSS THE RESET. This is the shape
 # the file's own header forbids - "publish none of it until retraining and
 # enumeration succeed" - and without the withdrawal a failed second
 # attempt reports the first attempt's link as though it were still there.
 stale='  pcie_linkSpeed = -1\n  pcie_linkWidth = -1\n  pcie_sscOk = -1\n  pcie_sscCntlRaw = -1\n  pcie_sscStatusRaw = -1\n'
 assert body.count(stale)==1,'the stale-link withdrawal is not where the gate expects it'
 staleMutants=[body.replace(stale,'',1)]
 # Only the verdict withdrawn and not the words behind it: a reader would
 # see "not asked" beside two PHY registers from a link that is gone.
 staleMutants.append(body.replace('  pcie_sscCntlRaw = -1\n  pcie_sscStatusRaw = -1\n','',1))
 # THE BURST SIZE. 256 bytes instead of the 128 Linux picks for this part -
 # a value that is legal, plausible and wrong, which is the only kind worth
 # mutating for.
 # The NAME also appears in the constant's own explanation, so target the
 # call site rather than the spelling.
 burst=' | #PCIE_MISC_CTRL_MAX_BURST_128 | '
 assert body.count(burst)==1
 mutants.append(body.replace(burst,' | $100000 | ',1))
 # NOT A MUTANT, AND THE REASON IS WORTH KEEPING. Putting the burst back to
 # a bare cleared mask - how this file stood before the audit - produces the
 # SAME register on this board, because 128 bytes is spelled 0 here. It was
 # written as a mutant, it survived, and it was removed rather than papered
 # over: no runtime assertion can tell a named decision from an unnamed one
 # that happens to agree. The naming is for the reader and for the part
 # where 0 means reserved, and this gate does not get to claim otherwise.
 #   mutants.append(body.replace(burst,' | ',1))
 # THE L1SS ADVERTISEMENT LEFT UP while the reference clock is held on.
 rootcap='  pcie_Modify(#PCIE_RC_CFG_PRIV1_ROOT_CAP, #PCIE_ROOT_CAP_L1SS_MODE_MASK, #PCIE_ROOT_CAP_L1SS_UNADVERTISED)\n'
 assert body.count(rootcap)==1
 mutants.append(body.replace(rootcap,'',1))
 # Each mutant is tried against the modes that should see it. The inbound
 # readback mutants below are invisible to mode 0 by construction - a window
 # that TAKES the write reads back correctly whether or not anybody looks -
 # so they are aimed at the modes where the register refuses the value.
 cases=[(m,(0,),0) for m in mutants]
 # The readback deleted: modes 3, 4 and 5 stop noticing that the window is
 # not the size this file believes. That is forum 916 on demand.
 at=body.index('  pcie_Phase(#PCIE_PH_INBOUND)')
 back=body[at:body.index('  pcie_dmaOffRead = 0',at)+len('  pcie_dmaOffRead = 0\n')]
 assert '#PCIE_ERR_INBOUND' in back and '#PCIE_ERR_DMA_OFFSET' in back
 cases.append((body.replace(back,'',1),(3,4,5),0))
 # Only one of the two size registers checked - the pair must agree, and a
 # driver that reads one of them is exactly as wrong as one that reads none.
 cases.append((body.replace('  If ((PcieRcPeek(#PCIE_MISC_MISC_CTRL) >> 27) & $1F) <> code\n    pcie_err = #PCIE_ERR_INBOUND\n    ProcedureReturn 0\n  EndIf\n','',1),(4,),0))
 # The offset half not checked: an inbound window that is not an identity map.
 cases.append((body.replace('  If (PcieRcPeek(#PCIE_MISC_RC_BAR2_CONFIG_LO) & $FFFFFFE0) <> 0 Or PcieRcPeek(#PCIE_MISC_RC_BAR2_CONFIG_HI) <> 0\n    pcie_err = #PCIE_ERR_DMA_OFFSET\n    ProcedureReturn 0\n  EndIf\n','',1),(5,),0))
 # THE SIZE CODE NOT FOLLOWING THE MEMORY. The window goes back to being
 # programmed from the constant, which is right on a 4 GB board and a
 # gigabyte too wide on a 1 GB one - and a window wider than the memory is
 # only harmless while the DMA check knows about it. Run at 1 GB, where
 # the difference exists.
 assert body.count('  code = PcieInboundSizeCode()')==1
 cases.append((body.replace('  code = PcieInboundSizeCode()','  code = #PCIE_INBOUND_SIZE_CODE',1),(0,),0x40000000))
 # THE READBACK COMPARED AGAINST THE CONSTANT INSTEAD OF THE VALUE CHOSEN.
 # On a 1 GB board the registers correctly hold 15 and the check demands
 # 17, so a healthy window is reported as a failure - and, worse, a write
 # that was ignored and left 17 standing would be reported as a success.
 # It is the wrong number in both directions at once.
 assert body.count(' <> code')==2
 cases.append((body.replace(' <> code',' <> #PCIE_INBOUND_SIZE_CODE'),(0,),0x40000000))
 for mutant,modes,mem in cases:
  assert mutant!=body
  caught=0
  for mode in modes:
   try:run(w,mutant,mode,mem)
   except AssertionError:caught=1
  if caught==0:raise AssertionError('policy mutant survived: '+repr([l for l in mutant.splitlines() if l not in body.splitlines()][:2] or 'a deletion'))
print('PASS reset admission, failed link, unsafe ownership refusal, inbound window sized to the memory fitted (1, 2, 4 and 8 GB and a board that did not say) and read back against the value chosen (size and offset, both registers), spread-spectrum and link read after training, the burst size named at 128 bytes, L1 substates un-advertised while the reference clock is driven, and the old link withdrawn by every retrain that does not finish; seventeen policy/order/readback/sizing/staleness mutants rejected')
