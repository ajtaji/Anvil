"""Compile shared DMA queue and actual board completion latch for a physical CPU test."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/link_tx_queue.pbi','Anvil/Network/link_dma_tx.pbi','RaspberryPi4/Board/hw_link.pi4','RaspberryPi4/Lib/mmu.pi4']
 board=(root/names[2]).read_text()
 def proc(n):return re.search(r'^Procedure(?:\.i)? '+n+r'\([^\n]*\n.*?^EndProcedure',board,re.M|re.S).group()
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/link_tx_queue.pbi"\n'+r'''
#HW_LINK_WIRED=1
#HW_LINK_WIFI=2
Global gLinkTxPending.i,gLinkTxCompleted.i,gLinkTxDropped.i,gLinkTxBusy.i,gLinkTxFail.i
Global fakeReady.i=1,fakeDevice.i=1,fakeAddress.i=1,fakeTime.i,fakeDone.i,fakePending.i,fakePollError.i,fakeTryError.i
Global tries.i,wireBytes.i
Global hwLinkDmaActive.i,hwLinkDmaResult.i,hwLinkDmaEpoch.i
Global Dim hwLinkDmaShort.a[60]
Global Dim wireFrame.a[1514]
Global Dim inputFrame.a[1514]
Procedure.i millis()
 fakeTime=fakeTime+1 : ProcedureReturn fakeTime
EndProcedure
Procedure.i NetIfGeneration(kind.i)
 ProcedureReturn fakeAddress
EndProcedure
Procedure.i GenetStarted()
 ProcedureReturn fakeReady
EndProcedure
Procedure.i GenetStartCount()
 ProcedureReturn fakeDevice
EndProcedure
Procedure.i GenetPollSend()
 If fakePollError<>0 : ProcedureReturn -1 : EndIf
 If fakePending=0 : ProcedureReturn 1 : EndIf
 If fakeDone=0 : ProcedureReturn 0 : EndIf
 fakePending=0 : ProcedureReturn 1
EndProcedure
Procedure.i GenetTrySend(p.i,n.i)
 Define i.i
 tries=tries+1
 If GenetPollSend()=0 : ProcedureReturn -1 : EndIf
 For i=0 To 1513 : wireFrame[i]=0 : Next
 For i=0 To n-1 : wireFrame[i]=PeekA(p+i) : Next
 wireBytes=n : fakePending=1 : fakeDone=0
 If fakeTryError<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i GenetSend(p.i,n.i,ms.i)
 If GenetTrySend(p,n)<>1 : ProcedureReturn 0 : EndIf
 fakeDone=1 : ProcedureReturn GenetPollSend()
EndProcedure
Procedure.i Cyw43DataMax()
 ProcedureReturn 0
EndProcedure
Procedure.i Cyw43DataPtr()
 ProcedureReturn 0
EndProcedure
Procedure.i Cyw43Send(n.i)
 ProcedureReturn -1
EndProcedure
'''
 s+='\n'.join(proc(n) for n in ['HwLinkDmaReady','HwLinkDmaGeneration','HwLinkDmaPoll','HwLinkDmaTry','HwLinkDmaDrain','HwLinkSend'])+'\nXIncludeFile "Anvil/Network/link_dma_tx.pbi"\n'+r'''
Procedure Fill(seed.i)
 Define i.i
 For i=0 To 1513 : inputFrame[i]=(i*7+seed)&255 : Next
EndProcedure
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,gLinkTxPending) : PokeI(p+16,gLinkTxCompleted)
 PokeI(p+24,gLinkTxDropped) : PokeI(p+32,gLinkTxFail) : PokeI(p+40,tries)
 PokeI(p+48,wireBytes) : PokeI(p+56,linkDmaTxActive)
 PokeI(p+64,hwLinkDmaActive) : PokeI(p+72,hwLinkDmaResult)
 For i=0 To 1513 : PokeA(p+80+i,wireFrame[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$444D5131)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 rc=LinkDmaTxConfigure(1,@HwLinkDmaTry,@HwLinkDmaPoll,@HwLinkDmaReady,@HwLinkDmaGeneration)
 If rc<>1 : ProcedureReturn 3 : EndIf
'''
 steps=[
 ('padded submit', 'Fill(3) : rc=LinkDmaTxSubmit(1,@inputFrame[0],14)', [1, 1, 0, 0, 0, 1, 60, 1, 1, 0], 3, 14),
 ('reuse caller', 'Fill(9) : LinkDmaTxProgress(1) : rc=0', [0, 1, 0, 0, 0, 1, 60, 1, 1, 0], 3, 14),
 ('second', 'rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 2, 0, 0, 0, 1, 60, 1, 1, 0], 3, 14),
 ('third', 'Fill(11) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 3, 0, 0, 0, 1, 60, 1, 1, 0], 3, 14),
 ('fourth', 'Fill(12) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 4, 0, 0, 0, 1, 60, 1, 1, 0], 3, 14),
 ('full', 'Fill(13) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [0, 4, 0, 0, 0, 1, 60, 1, 1, 0], 3, 14),
 ('complete first', 'fakeDone=1 : LinkDmaTxProgress(1) : rc=0', [0, 3, 1, 0, 0, 1, 60, 0, 1, 1], 3, 14),
 ('submit second', 'LinkDmaTxProgress(1) : rc=0', [0, 3, 1, 0, 0, 2, 60, 1, 1, 0], 9, 60),
 ('console interleaves after completion', 'fakeDone=1 : rc=HwLinkSend(1,@inputFrame[0],60,10)', [1, 3, 1, 0, 0, 3, 60, 1, 1, 1], 13, 60),
 ('queue consumes latched result', 'LinkDmaTxProgress(1) : rc=0', [0, 2, 2, 0, 0, 3, 60, 0, 1, 1], 13, 60),
 ('third submits in order', 'LinkDmaTxProgress(1) : rc=0', [0, 2, 2, 0, 0, 4, 60, 1, 1, 0], 11, 60),
 ('down invalidates all', 'fakeReady=0 : LinkDmaTxProgress(1) : rc=0', [0, 0, 2, 2, 2, 4, 60, 0, 1, 0], 11, 60),
 ('down refuses', 'rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [0, 0, 2, 2, 2, 4, 60, 0, 1, 0], 11, 60),
 ('restart new generation', 'fakeReady=1 : fakeDevice=2 : fakePending=0 : Fill(20) : fakeTime=0 : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 1, 2, 2, 2, 5, 60, 1, 1, 0], 20, 60),
 ('active timeout', 'fakeTime=102 : LinkDmaTxProgress(1) : rc=0', [0, 0, 2, 3, 3, 5, 60, 0, 1, 0], 20, 60),
 ('old DMA still owns buffer', 'Fill(21) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 1, 2, 3, 3, 5, 60, 0, 1, 0], 20, 60),
 ('old completes before new submit', 'fakeDone=1 : LinkDmaTxProgress(1) : rc=0', [0, 1, 2, 3, 3, 6, 60, 1, 1, 0], 21, 60),
 ('device generation invalidates', 'fakeDevice=3 : fakePending=0 : LinkDmaTxProgress(1) : rc=0', [0, 0, 2, 4, 4, 6, 60, 0, 1, 0], 21, 60),
 ('wrap submit', 'fakeTime=$FFFFFFF0 : Fill(22) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 1, 2, 4, 4, 7, 60, 1, 1, 0], 22, 60),
 ('wrap still pending', 'fakeTime=40 : LinkDmaTxProgress(1) : rc=0', [0, 1, 2, 4, 4, 7, 60, 1, 1, 0], 22, 60),
 ('wrap timeout', 'fakeTime=90 : LinkDmaTxProgress(1) : rc=0', [0, 0, 2, 5, 5, 7, 60, 0, 1, 0], 22, 60),
 ('maximum frame', 'fakeDone=1 : Fill(30) : rc=LinkDmaTxSubmit(1,@inputFrame[0],1514)', [1, 1, 2, 5, 5, 8, 1514, 1, 1, 0], 30, 1514),
 ('poll failure drops without replay', 'fakePollError=1 : LinkDmaTxProgress(1) : rc=0', [0, 0, 2, 6, 6, 8, 1514, 0, 1, -1], 30, 1514),
 ('driver still busy after poll failure', 'fakePollError=0 : Fill(31) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 1, 2, 6, 6, 9, 1514, 0, 0, 0], 30, 1514),
 ('retained DMA completes', 'fakeDone=1 : LinkDmaTxProgress(1) : rc=0', [0, 1, 2, 6, 6, 10, 60, 1, 1, 0], 31, 60),
 ('address generation invalidates', 'fakeAddress=2 : LinkDmaTxProgress(1) : rc=0', [0, 0, 2, 7, 7, 10, 60, 0, 1, 0], 31, 60),
 ('ambiguous submission', 'fakeDone=1 : fakeTryError=1 : Fill(32) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 0, 2, 8, 8, 11, 60, 0, 0, 0], 32, 60),
 ('ambiguous submission cannot replay', 'fakeTryError=0 : Fill(33) : rc=LinkDmaTxSubmit(1,@inputFrame[0],60)', [1, 1, 2, 8, 8, 12, 60, 0, 0, 0], 32, 60),
 ('down discards unsent', 'fakeReady=0 : LinkDmaTxProgress(1) : rc=0', [0, 0, 2, 9, 9, 12, 60, 0, 0, 0], 32, 60),
 ('unsupported delegates', 'rc=LinkDmaTxSubmit(2,@inputFrame[0],60)', [-2, 0, 2, 9, 9, 12, 60, 0, 0, 0], 32, 60),
 ('configure cannot replace owner', 'rc=LinkDmaTxConfigure(1,@HwLinkDmaTry,@HwLinkDmaPoll,@HwLinkDmaReady,@HwLinkDmaGeneration)', [0, 0, 2, 9, 9, 12, 60, 0, 0, 0], 32, 60),]
 for k,(_,code,_,_,_) in enumerate(steps):s+=code+f"\n Save({k},rc)\n"
 s+=f" PokeI($E1C00008,{len(steps)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\n"
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=[dict(name=n,expected=e,seed=seed,copied=copied) for n,_,e,seed,copied in steps]),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.compiler,a.out.resolve())
