"""Compile shared send policy with controlled credit and bus outcomes on the Pi.

This proves transmit policy, not radio or SDIO hardware behavior. No emulator runs.
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

 constants=re.findall(r'^#CYW43_(?:SDPCM_\w+|BDC_\w+|ETH_MAX|TXBUF|CHAN_DATA|IO_\w+|TR_IOCTL_STALL|POLL_CREDIT)\s*=.*$',driver,re.M)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+'\n'.join(constants)+'\n'
 # sync, length, seq, initial credit, credit after poll, bus success;
 # expected result, transfers, polls, final seq, successful frames, stalls.
 vectors=[
 ('try one byte',[0,1,0,1,1,1,0,1,0,1,1,0]),
 ('try padded',[0,63,7,8,8,1,0,1,0,8,1,0]),
 ('try max',[0,1514,254,255,255,1,0,1,0,255,1,0]),
 ('try wrap',[0,64,255,0,0,1,0,1,0,0,1,0]),
 ('try closed',[0,64,7,7,8,1,-8,0,0,7,0,0]),
 ('try stale',[0,64,8,7,9,1,-8,0,0,8,0,0]),
 ('try ambiguous half',[0,64,0,128,1,1,-8,0,0,0,0,0]),
 ('try bus failed',[0,64,9,10,10,0,-4,1,0,9,0,0]),
 ('try empty',[0,0,0,1,1,1,-2,0,0,0,0,0]),
 ('try too large',[0,1515,0,1,1,1,-2,0,0,0,0,0]),
 ('sync ready',[1,64,0,1,1,1,0,1,0,1,1,0]),
 ('sync earns credit',[1,64,0,0,1,1,0,1,1,1,1,0]),
 ('sync timeout',[1,64,0,0,0,1,-1,0,1,0,0,1]),
 ('sync bus no replay',[1,64,0,0,1,0,-4,1,1,0,0,0])]
 s+=r"""
Global cyw43_credit.i,cyw43_seq.i,cyw43_creditPolls.i,cyw43_stalls.i,cyw43_txFrames.i
Global Dim cyw43_tx.a[#CYW43_TXBUF]
Global fakeCredit.i,fakeBus.i,transfers.i,polls.i
Procedure cyw43_Trace(code.i)
EndProcedure
Procedure.i cyw43_Poll(id.i,event.i,ms.i,context.i)
 polls=polls+1 : cyw43_credit=fakeCredit : ProcedureReturn 0
EndProcedure
Procedure.i cyw43_F2Xfer(write.i,p.i,n.i)
 transfers=transfers+1 : ProcedureReturn fakeBus
EndProcedure
"""
 s+=proc('cyw43_DataCreditReady')+'\n'+proc('Cyw43TrySend')+'\n'+proc('Cyw43Send')+'\n'+r"""
Procedure SendFixture(index.i,row.i)
 Define rc.i,p.i,i.i
 cyw43_seq=PeekI(row+16) : cyw43_credit=PeekI(row+24)
 fakeCredit=PeekI(row+32) : fakeBus=PeekI(row+40)
 transfers=0 : polls=0 : cyw43_creditPolls=0 : cyw43_stalls=0 : cyw43_txFrames=0
 For i=0 To #CYW43_TXBUF-1 : cyw43_tx[i]=$A5 : Next
 For i=0 To 1513 : cyw43_tx[16+i]=(i*7+3) & 255 : Next
 If PeekI(row)=0 : rc=Cyw43TrySend(PeekI(row+8)) : Else : rc=Cyw43Send(PeekI(row+8)) : EndIf
 p=$E1C00100+index*2048
 PokeI(p,rc) : PokeI(p+8,transfers) : PokeI(p+16,polls)
 PokeI(p+24,cyw43_seq) : PokeI(p+32,cyw43_txFrames) : PokeI(p+40,cyw43_stalls)
 PokeI(p+48,cyw43_creditPolls)
 For i=0 To #CYW43_TXBUF-1 : PokeA(p+64+i,cyw43_tx[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$54525931)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
"""
 s+=f' For i=0 To {len(vectors)-1}\n SendFixture(i,?SendVectors+i*48)\n Next\n PokeI($E1C00008,{len(vectors)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\nSendVectors:\n'
 for _,row in vectors:s+=' Data.q '+','.join(str(x) for x in row[:6])+'\n'
 s+='EndDataSection\n';
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=[dict(name=n,input=row[:6],expected=row[6:]) for n,row in vectors]),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
