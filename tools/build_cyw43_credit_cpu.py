"""Compile the shared credit-poll body with controlled RX events for Pi execution.

This proves poll policy, not radio or SDIO hardware behavior. No emulator runs.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Net/cyw43.pbi','RaspberryPi4/Lib/mmu.pi4']
 driver=(root/names[0]).read_text(encoding='utf8')
 def proc(name):
  m=re.search(r'^Procedure\.i '+name+r'\([^\n]*\n.*?^EndProcedure',driver,re.M|re.S)
  assert m,name
  return m.group()
 constants=['CYW43_CHAN_EVENT','CYW43_IO_OK','CYW43_IO_TIMEOUT','CYW43_IO_BADFRAME','CYW43_TR_POLL_ENTER','CYW43_TR_POLL_TIMEOUT','CYW43_POLL_CREDIT','CYW43_POLL_EVENT']
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'
 for name in constants:
  m=re.search(r'^#'+name+r'\s*=\s*(-?\d+)',driver,re.M);assert m,name
  s+='#'+name+'='+m.group(1)+'\n'
 # context,event request,RX verdict,TX sequence,new credit,queue success,
 # expected return,read count,retained frames,credit counter,event counter,control counter
 vectors=[
 ('fresh credit',[2,0,0,0,1,1,0,1,0,0,0,0]),
 ('wrapped credit',[2,0,0,255,0,1,0,1,0,0,0,0]),
 ('closed window',[2,0,0,7,7,1,-1,4,0,0,0,0]),
 ('stale window',[2,0,0,8,7,1,-1,4,0,0,0,0]),
 ('half window',[2,0,0,0,128,1,-1,4,0,0,0,0]),
 ('data retained',[2,0,5,9,10,1,0,1,1,1,0,0]),
 ('queue failure wins',[2,0,5,9,10,0,-4,1,1,0,0,0]),
 ('malformed wins',[2,0,-1,9,10,1,-4,1,0,0,0,0]),
 ('aggregate credit',[2,0,6,255,0,1,0,1,0,0,0,0]),
 ('event request wins',[2,1,2,0,1,1,2,1,0,0,0,0]),
 ('ioctl reply wins',[0,0,1,0,0,1,0,1,0,0,0,0]),
 ('control ignores credit',[0,0,0,0,1,1,-1,4,0,0,0,0]),
 ('control retains data',[0,0,5,0,1,1,-1,4,4,0,0,4]),
 ('event retains data',[3,0,5,0,1,1,-1,4,4,0,4,0])]
 s+=r'''
Global cyw43_hz.i=1000,cyw43_rxqCount.i,cyw43_rxFrameLen.i=4
Global cyw43_rxDataPollCredit.i,cyw43_rxDataPollEvent.i,cyw43_rxDataPollControl.i
Global cyw43_credit.i,cyw43_seq.i
Global Dim cyw43_rx.a[4]
Global fakeClock.i,fakeRx.i,fakeCredit.i,fakePushOk.i,reads.i,pushes.i
Global wtable.i
Global *pet
Procedure.i cyw43_Ticks()
 fakeClock=fakeClock+1 : ProcedureReturn fakeClock
EndProcedure
Procedure cyw43_TraceIo(code.i)
EndProcedure
Procedure.i cyw43_RxqHeadChannel()
 ProcedureReturn 2
EndProcedure
Procedure.i cyw43_RxqCanPoll()
 ProcedureReturn 1
EndProcedure
Procedure.i cyw43_RxFrame(want.i,queued.i)
 reads=reads+1 : cyw43_credit=fakeCredit : ProcedureReturn fakeRx
EndProcedure
Procedure.i cyw43_RxqPush(data.i,n.i,a.i,b.i)
 pushes=pushes+1
 If fakePushOk<>0 : cyw43_rxqCount=cyw43_rxqCount+1 : EndIf
 ProcedureReturn fakePushOk
EndProcedure
'''
 s+=proc('cyw43_DataCreditReady')+'\n'+proc('cyw43_Poll')+'\n'+r'''
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure CreditFixture(index.i,row.i)
 Define rc.i,p.i
 fakeClock=0 : reads=0 : pushes=0 : cyw43_rxqCount=0
 cyw43_rxDataPollCredit=0 : cyw43_rxDataPollEvent=0 : cyw43_rxDataPollControl=0
 fakeRx=PeekI(row+16) : cyw43_seq=PeekI(row+24) : fakeCredit=PeekI(row+32) : fakePushOk=PeekI(row+40)
 cyw43_credit=cyw43_seq
 rc=cyw43_Poll(-1,PeekI(row+8),3,PeekI(row))
 p=$E1C00100+index*64
 PokeI(p,rc) : PokeI(p+8,reads) : PokeI(p+16,pushes)
 PokeI(p+24,cyw43_rxDataPollCredit) : PokeI(p+32,cyw43_rxDataPollEvent) : PokeI(p+40,cyw43_rxDataPollControl)
 pet()
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$43524431)
 pet=PeekI(wtable+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 s+=f' For i=0 To {len(vectors)-1}\n CreditFixture(i,?CreditVectors+i*48)\n Next\n PokeI($E1C00008,{len(vectors)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\nCreditVectors:\n'
 for _,row in vectors:s+=' Data.q '+','.join(str(x) for x in row[:6])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=[dict(name=n,expected=row[6:]) for n,row in vectors]),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
