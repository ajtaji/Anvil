"""Compile GENET transmit ownership with controlled register outcomes for the Pi."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['RaspberryPi4/Lib/genet.pi4','RaspberryPi4/Lib/mmu.pi4'];driver=(root/names[0]).read_text()
 def proc(n):return re.search(r'^Procedure(?:\.i)? '+n+r'\([^\n]*\n.*?^EndProcedure',driver,re.M|re.S).group()
 wanted='ERR_\\w+|MIN_FRAME|MAX_FRAME|TX_OFF|TDMA_PROD_INDEX|TDMA_CONS_INDEX|TDMA_CTRL|RDMA_CTRL|DMA_EN|UMAC_TX_FLUSH|DESC_\\w+|TX_FLAGS|DMA_BUFLENGTH_\\w+|TX_DESCS'
 constants=re.findall(r'^#GENET_(?:'+wanted+r')\s*=.*$',driver,re.M)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+'\n'.join(constants)+'\n'+r'''
Global genet_err.i,genet_started.i,genet_txPending.i,genet_txGoal.i,genet_txCount.i,genet_txIndex.i
Global Dim genet_txOwned.a[#GENET_MAX_FRAME+64]
Global Dim sourceFrame.a[1536]
Global fakeProd.i,fakeCons.i,failOffset.i=-1,publishFail.i,modifyFail.i,ticks.i,writes.i,cacheBytes.i,descAddr.i
Procedure.i genet_Peek(off.i)
 If off=#GENET_TDMA_PROD_INDEX : ProcedureReturn fakeProd : EndIf
 ProcedureReturn fakeCons
EndProcedure
Procedure.i genet_Poke(off.i,value.i)
 writes=writes+1
 If off=#GENET_TDMA_PROD_INDEX
  If off<>failOffset Or publishFail<>0 : fakeProd=value : EndIf
 ElseIf off>=#GENET_TX_OFF And off<#GENET_TX_OFF+3072
  If (off-#GENET_TX_OFF) % 12 = 4 : descAddr=value : EndIf
 EndIf
 If off=failOffset : genet_err=-2 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i genet_Modify(off.i,clear.i,bits.i)
 If modifyFail<>0 : genet_err=-2 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure genet_DelayUs(n.i)
EndProcedure
Procedure genet_CacheRange(addr.i,n.i)
 cacheBytes=n
EndProcedure
Procedure.i GenetAddrIsWide()
 ProcedureReturn 1
EndProcedure
Procedure.i genet_Ticks()
 ticks=ticks+1 : ProcedureReturn ticks
EndProcedure
Procedure.i GenetTimeoutTicks(ms.i)
 ProcedureReturn ms
EndProcedure
'''
 s+='\n'.join(proc(n) for n in ['GenetDisableDma','GenetPollSend','GenetTrySend','GenetSend'])+r'''
Procedure Save(index.i,rc.i)
 Define p.i,addr.i,i.i
 p=$E1C00100+index*2048 : addr=(@genet_txOwned[0]+63) & -64
 PokeI(p,rc) : PokeI(p+8,genet_txPending) : PokeI(p+16,genet_txGoal)
 PokeI(p+24,genet_txCount) : PokeI(p+32,genet_txIndex) : PokeI(p+40,genet_err)
 PokeI(p+48,writes) : PokeI(p+56,cacheBytes)
 PokeI(p+64,Bool(descAddr=addr)) : PokeI(p+72,Bool(descAddr<>@sourceFrame[0]))
 For i=0 To 1535 : PokeA(p+80+i,PeekA(addr+i)) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$474E5431)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 For i=0 To 1535 : sourceFrame[i]=(i*7+3)&255 : Next
'''
 steps=[
 ('not started','rc=GenetTrySend(@sourceFrame[0],60)',[0,0,0,0,0,-14,0,0,0,1],0),
 ('short','genet_started=1 : rc=GenetTrySend(@sourceFrame[0],59)',[0,0,0,0,0,-1,0,0,0,1],0),
 ('wrap submit','fakeProd=65535 : fakeCons=65535 : genet_txIndex=255 : rc=GenetTrySend(@sourceFrame[0],60)',[1,1,0,0,0,0,4,60,1,1],60),
 ('old consumer is not complete','For i=0 To 1535 : sourceFrame[i]=$EE : Next\n rc=GenetPollSend()',[0,1,0,0,0,0,4,60,1,1],60),
 ('busy preserves bytes','rc=GenetTrySend(@sourceFrame[0],64)',[-1,1,0,0,0,-19,4,60,1,1],60),
 ('wrap completion','fakeCons=0 : rc=GenetPollSend()',[1,0,0,1,0,-19,4,60,1,1],60),
 ('no double count','rc=GenetPollSend()',[1,0,0,1,0,-19,4,60,1,1],60),
 ('ambiguous producer write','For i=0 To 1535 : sourceFrame[i]=(i*7+3)&255 : Next\n failOffset=#GENET_TDMA_PROD_INDEX : publishFail=1 : rc=GenetTrySend(@sourceFrame[0],64)',[0,1,1,1,1,-2,8,64,1,1],64),
 ('failed write retained','rc=GenetPollSend()',[0,1,1,1,1,-2,8,64,1,1],64),
 ('failed write completed','fakeCons=1 : rc=GenetPollSend()',[1,0,1,2,1,-2,8,64,1,1],64),
 ('descriptor failure','failOffset=#GENET_TX_OFF+12+4 : rc=GenetTrySend(@sourceFrame[0],64)',[0,0,1,2,1,-2,9,64,1,1],64),
 ('next submit','failOffset=-1 : rc=GenetTrySend(@sourceFrame[0],64)',[1,1,2,2,2,0,13,64,1,1],64),
 ('read failure retained','fakeCons=-2 : rc=GenetPollSend()',[-1,1,2,2,2,-2,13,64,1,1],64),
 ('completion','fakeCons=2 : rc=GenetPollSend()',[1,0,2,3,2,-2,13,64,1,1],64),
 ('timeout retains owner','rc=GenetSend(@sourceFrame[0],64,1)',[0,1,3,3,3,-15,17,64,1,1],64),
 ('failed disable retains owner','modifyFail=1 : rc=GenetDisableDma()',[0,1,3,3,3,-2,17,64,1,1],64),
 ('successful disable releases','modifyFail=0 : rc=GenetDisableDma()',[1,0,3,3,3,-2,19,64,1,1],64),
 ('maximum owned frame','fakeCons=3 : rc=GenetTrySend(@sourceFrame[0],1536)',[1,1,4,3,4,0,23,1536,1,1],1536),
 ('maximum completion','fakeCons=4 : rc=GenetPollSend()',[1,0,4,4,4,0,23,1536,1,1],1536),
 ('oversize refusal','rc=GenetTrySend(@sourceFrame[0],1537)',[0,0,4,4,4,-1,23,1536,1,1],1536),
 ('null refusal','rc=GenetTrySend(0,60)',[0,0,4,4,4,-1,23,1536,1,1],1536)]
 for k,(_,code,_,_) in enumerate(steps):s+=code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(steps)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=[dict(name=n,expected=e,copied=b) for n,_,e,b in steps]),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.compiler,a.out.resolve())
