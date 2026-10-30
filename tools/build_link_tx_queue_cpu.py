"""Build the shared owned transmit FIFO test for a returning physical Pi run."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
CASES=[
 ('init',0,1,0,0),('submit',0,1,1514,3),('submit',0,1,1,9),
 ('finish',0,1,1,0),('submit',0,1,63,17),('submit',0,1,64,33),
 ('submit',0,1,25,99),('finish',0,1,9,1),('finish',0,1,1,1),
 ('submit',0,1,27,44),('finish',0,1,1,1),('finish',0,1,2,-4),
 ('finish',0,1,3,1),('finish',0,1,4,1),('finish',0,1,5,1),
 ('finish',0,1,5,1),('submit',0,1,0,2),('submit',0,1,1515,2),
 ('alias',0,1,16,0),('submit',0,2,50,2),('submit',0,1,99,72),
 ('init',1,5,0,0),('submit',1,5,33,81),('finish',0,1,6,0),
 ('init',0,2,0,0),('finish',0,1,6,1),('submit',0,2,1,90),
 ('init',0,2,0,0),('init',0,1,0,0),('finish',0,2,1,2),
 ('finish',1,5,1,1),('finish',0,2,1,1),('init',0,0,0,0)]
def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/link_tx_queue.pbi','RaspberryPi4/Lib/mmu.pi4']
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/link_tx_queue.pbi"\n'+r'''
Global Dim queueA.a[#LINK_TXQ_BYTES]
Global Dim queueB.a[#LINK_TXQ_BYTES]
Global Dim inputFrame.a[1515]
Procedure SaveQueue(index.i,rc.i,q.i,generation.i)
 Define i.i,p.i
 p=$E1C00100+index*6272
 PokeI(p,rc)
 PokeI(p+8,LinkTxQueueCount(q,generation))
 PokeI(p+16,LinkTxQueueLength(q,generation))
 PokeI(p+24,LinkTxQueueTicket(q,generation))
 For i=0 To #LINK_TXQ_BYTES-1 : PokeA(p+32+i,PeekA(q+i)) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i,q.i
 For i=0 To 262143 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$51554531)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,(op,which,gen,a,b) in enumerate(CASES):
  s+=f' q=@queue{"A" if which==0 else "B"}[0]\n'
  if op=='init':s+=f' rc=LinkTxQueueInit(q,{gen})\n'
  elif op=='finish':s+=f' rc=LinkTxQueueFinish(q,{gen},{a},{b})\n'
  elif op=='alias':s+=f' rc=LinkTxQueueSubmit(q,{gen},q+80,{a})\n'
  else:
   s+=f' For i=0 To 1514 : inputFrame[i]=(i*7+{b}) & 255 : Next\n rc=LinkTxQueueSubmit(q,{gen},@inputFrame[0],{a})\n'
   s+=' For i=0 To 1514 : inputFrame[i]=$EE : Next\n'
  s+=f' SaveQueue({k},rc,q,{gen})\n'
 s+=f' PokeI($E1C00008,{len(CASES)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c3ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=CASES),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.compiler,a.out.resolve())
