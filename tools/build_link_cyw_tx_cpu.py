"""Compile the shared live CYW43 queue adapter with controlled driver outcomes."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/link_tx_queue.pbi','Anvil/Network/link_cyw_tx.pbi','Anvil/Network/link.pbi','RaspberryPi4/Lib/mmu.pi4','Anvil/Net/cyw43.pbi']
 link=(root/names[2]).read_text()
 def proc(n):return re.search(r'^Procedure(?:\.i)? '+n+r'\([^\n]*\n.*?^EndProcedure',link,re.M|re.S).group()
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/link_tx_queue.pbi"\n'+r'''
#HW_LINK_WIFI=2
#CYW43_IO_TIMEOUT=-1
#CYW43_IO_AGAIN=-8
#CYW43_IO_BADFRAME=-4
#CYW43_IO_OK=0
Global *gLinkTxSubmitHook=0,*gLinkTxProgressHook=0
Global gLinkTxPending.i,gLinkTxCompleted.i,gLinkTxDropped.i,gLinkTxBusy.i,gLinkTxFail.i
Global fakeReady.i=1,fakeRadio.i=1,fakeAddress.i=1,fakeTime.i,fakeCredit.i,fakeResult.i
Global tries.i,fallbacks.i,wireBytes.i
Global Dim stageFrame.a[1514]
Global Dim wireFrame.a[1514]
Global Dim inputFrame.a[1514]
Procedure.i HwLinkReady(kind.i)
 ProcedureReturn fakeReady
EndProcedure
Procedure.i Cyw43TxGeneration()
 ProcedureReturn fakeRadio
EndProcedure
Procedure.i NetIfGeneration(kind.i)
 ProcedureReturn fakeAddress
EndProcedure
Procedure.i millis()
 ProcedureReturn fakeTime
EndProcedure
Procedure.i cyw43_DataCreditReady()
 ProcedureReturn fakeCredit
EndProcedure
Procedure.i Cyw43DataPtr()
 ProcedureReturn @stageFrame[0]
EndProcedure
Procedure.i Cyw43TrySend(bytes.i)
 Define i.i
 tries=tries+1 : wireBytes=bytes
 For i=0 To 1513 : wireFrame[i]=0 : Next
 For i=0 To bytes-1 : wireFrame[i]=stageFrame[i] : Next
 ProcedureReturn fakeResult
EndProcedure
Procedure.i LinkTxMaxOn(kind.i)
 ProcedureReturn 1514
EndProcedure
Procedure.i HwLinkSend(kind.i,p.i,n.i,ms.i)
 fallbacks=fallbacks+1 : ProcedureReturn 1
EndProcedure
'''
 driver=(root/'Anvil/Net/cyw43.pbi').read_text()
 s+=re.search(r'^Procedure\.i Cyw43CanSend\([^\n]*\n.*?^EndProcedure',driver,re.M|re.S).group()+'\n'
 s+='\n'.join(proc(n) for n in ['LinkTxSetHooks','LinkTxProgress','LinkSendFrame'])+'\nXIncludeFile "Anvil/Network/link_cyw_tx.pbi"\n'+r'''
Procedure Fill(seed.i)
 Define i.i
 For i=0 To 1513 : inputFrame[i]=(i*7+seed)&255 : Next
EndProcedure
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,gLinkTxPending) : PokeI(p+16,gLinkTxCompleted)
 PokeI(p+24,gLinkTxDropped) : PokeI(p+32,gLinkTxBusy) : PokeI(p+40,gLinkTxFail)
 PokeI(p+48,tries) : PokeI(p+56,fallbacks) : PokeI(p+64,wireBytes)
 For i=0 To 1513 : PokeA(p+80+i,wireFrame[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$43595131)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached() : LinkCywTxInstall()
'''
 # Explicit state expectations: rc,pending,completed,dropped,busy,fail,tries,fallbacks,wire bytes.
 steps=[
 ('queue without credit','Fill(3) : rc=LinkSendFrame(2,@inputFrame[0],1514)',[1,1,0,0,1,0,0,0,0],0),
 ('caller reused input','Fill(9) : LinkTxProgress(2) : rc=0',[0,1,0,0,2,0,0,0,0],0),
 ('credit arrives','fakeCredit=1 : LinkTxProgress(2) : rc=0',[0,0,1,0,2,0,1,0,1514],3),
 ('fast direct retirement','rc=LinkSendFrame(2,@inputFrame[0],64)',[1,0,2,0,2,0,2,0,64],9),
 ('fill first','fakeCredit=0 : Fill(11) : rc=LinkSendFrame(2,@inputFrame[0],60)',[1,1,2,0,3,0,2,0,64],9),
 ('fill second','Fill(12) : rc=LinkSendFrame(2,@inputFrame[0],60)',[1,2,2,0,3,0,2,0,64],9),
 ('fill third','Fill(13) : rc=LinkSendFrame(2,@inputFrame[0],60)',[1,3,2,0,3,0,2,0,64],9),
 ('fill fourth','Fill(14) : rc=LinkSendFrame(2,@inputFrame[0],60)',[1,4,2,0,3,0,2,0,64],9),
 ('full is refused','Fill(99) : rc=LinkSendFrame(2,@inputFrame[0],60)',[0,4,2,0,4,0,2,0,64],9),
 ('fifo one','fakeCredit=1 : LinkTxProgress(2) : rc=0',[0,3,3,0,4,0,3,0,60],11),
 ('fifo two','LinkTxProgress(2) : rc=0',[0,2,4,0,4,0,4,0,60],12),
 ('fifo three','LinkTxProgress(2) : rc=0',[0,1,5,0,4,0,5,0,60],13),
 ('fifo four','LinkTxProgress(2) : rc=0',[0,0,6,0,4,0,6,0,60],14),
 ('old address pending','fakeCredit=0 : Fill(20) : rc=LinkSendFrame(2,@inputFrame[0],60)',[1,1,6,0,5,0,6,0,60],14),
 ('address invalidates','fakeAddress=2 : LinkTxProgress(2) : rc=0',[0,0,6,1,5,1,6,0,60],14),
 ('old radio pending','rc=LinkSendFrame(2,@inputFrame[0],60)',[1,1,6,1,6,1,6,0,60],14),
 ('radio invalidates','fakeRadio=2 : LinkTxProgress(2) : rc=0',[0,0,6,2,6,2,6,0,60],14),
 ('down pending','rc=LinkSendFrame(2,@inputFrame[0],60)',[1,1,6,2,7,2,6,0,60],14),
 ('down invalidates','fakeReady=0 : LinkTxProgress(2) : rc=0',[0,0,6,3,7,3,6,0,60],14),
 ('down refuses','rc=LinkSendFrame(2,@inputFrame[0],60)',[0,0,6,3,7,3,6,0,60],14),
 ('wrapping clock enqueue','fakeReady=1 : fakeTime=$FFFFFFF0 : rc=LinkSendFrame(2,@inputFrame[0],60)',[1,1,6,3,8,3,6,0,60],14),
 ('still within deadline','fakeTime=40 : LinkTxProgress(2) : rc=0',[0,1,6,3,9,3,6,0,60],14),
 ('expired without send','fakeTime=90 : LinkTxProgress(2) : rc=0',[0,0,6,4,9,4,6,0,60],14),
 ('other backend fallback','rc=LinkSendFrame(1,@inputFrame[0],60)',[1,0,6,4,9,4,6,1,60],14),
 ('terminal bus error','fakeCredit=1 : fakeResult=-4 : Fill(33) : rc=LinkSendFrame(2,@inputFrame[0],60)',[1,0,6,5,9,5,7,1,60],33),
 ('no replay','LinkTxProgress(2) : rc=0',[0,0,6,5,9,5,7,1,60],33)]
 for k,(_,code,_,_) in enumerate(steps):s+=code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(steps)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=[dict(name=n,expected=e,seed=seed) for n,_,e,seed in steps]),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.compiler,a.out.resolve())
