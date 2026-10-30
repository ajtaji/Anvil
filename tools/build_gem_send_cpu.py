"""Compile GEM transmit ownership with controlled register outcomes on the Pi CPU."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['RaspberryPi4/Lib/gem.pi4','RaspberryPi4/Lib/mmu.pi4'];driver=(root/names[0]).read_text()
 def proc(n):return re.search(r'^Procedure(?:\.i)? '+n+r'\([^\n]*\n.*?^EndProcedure',driver,re.M|re.S).group()
 wanted='ERR_\\w+|NCR(?:_\\w+)?|TSR(?:_\\w+)?|DESC_\\w+|TX_\\w+|OFF_TX\\w+|BUF_BYTES|FRAME_\\w+|LINE|REGION_MIN'
 constants=re.findall(r'^#GEM_(?:'+wanted+r')\s*=.*$',driver,re.M)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+'\n'.join(constants)+'\n'+r'''
Global gem_err.i,gem_started.i,gem_txPending.i,gem_txCount.i,gem_txHead.i,gem_lastTsr.i,gem_region.i,gem_regionBytes.i
Global Dim region.a[#GEM_REGION_MIN+64]
Global Dim sourceFrame.a[1536]
Global ncr.i,tsr.i,failRead.i=-1,failWrite.i,stopFail.i,linkUp.i=1,fakeTicks.i,writes.i,view.i
Procedure.i gem_Rd(off.i)
 If off=failRead : gem_err=-2 : ProcedureReturn -2 : EndIf
 If off=#GEM_NCR : ProcedureReturn ncr : EndIf
 ProcedureReturn tsr
EndProcedure
Procedure.i gem_Wr(off.i,value.i)
 writes=writes+1
 If failWrite<>0 : gem_err=-2 : ProcedureReturn 0 : EndIf
 If off=#GEM_NCR
  If stopFail=0 : ncr=value : EndIf
 Else
  tsr=0
 EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i PcieLinkUp()
 ProcedureReturn linkUp
EndProcedure
Procedure.i PcieDmaOk(base.i,bytes.i)
 ProcedureReturn 1
EndProcedure
Procedure.i PcieDmaBus(addr.i)
 ProcedureReturn addr+$1000000000
EndProcedure
Procedure gem_Barrier()
EndProcedure
Procedure gem_CacheRange(addr.i,n.i)
EndProcedure
Procedure.i Ticks()
 fakeTicks=fakeTicks+1 : ProcedureReturn fakeTicks
EndProcedure
Procedure.i GemTimeoutTicks(ms.i)
 ProcedureReturn ms
EndProcedure
'''
 s+='\n'.join(proc(n) for n in ['gem_WrSync','gem_DescAddr','GemSetRegion','GemStopChecked','GemPollSend','GemTrySend','GemSend'])+r'''
Procedure Save(index.i,rc.i)
 Define p.i,addr.i,i.i,d.i
 p=$E1C00100+index*2048 : addr=gem_region+#GEM_OFF_TXBUF+view*#GEM_BUF_BYTES
 d=gem_region+#GEM_OFF_TXRING+view*#GEM_DESC_SIZE
 PokeI(p,rc) : PokeI(p+8,gem_txPending) : PokeI(p+16,gem_txHead)
 PokeI(p+24,gem_txCount) : PokeI(p+32,gem_started) : PokeI(p+40,gem_err)
 PokeI(p+48,writes) : PokeI(p+56,PeekN(d+#GEM_DESC_CTRL))
 PokeI(p+64,Bool(PeekN(d)=((addr+$1000000000)&$FFFFFFFF)))
 PokeI(p+72,PeekN(d+#GEM_DESC_ADDRH))
 For i=0 To 1535 : PokeA(p+80+i,PeekA(addr+i)) : Next
EndProcedure
Procedure Complete()
 Define d.i
 d=gem_region+#GEM_OFF_TXRING+gem_txHead*#GEM_DESC_SIZE
 PokeL(d+#GEM_DESC_CTRL,PeekN(d+#GEM_DESC_CTRL)|#GEM_TX_USED)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$474D5431)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 gem_region=(@region[0]+63) & -64
 For i=0 To 1535 : sourceFrame[i]=(i*7+3)&255 : Next
'''
 steps=[
 ('not started', 'rc=GemTrySend(@sourceFrame[0],60)', [0, 0, 0, 0, 0, -14, 0, 0, 0, 0], 0),
 ('short', 'gem_started=1 : ncr=#GEM_NCR_RE|#GEM_NCR_TE : rc=GemTrySend(@sourceFrame[0],13)', [0, 0, 0, 0, 1, -1, 0, 0, 0, 0], 0),
 ('padded submit', 'rc=GemTrySend(@sourceFrame[0],14)', [1, 1, 0, 0, 1, 0, 1, 32828, 1, 16], 14),
 ('pending', 'For i=0 To 1535 : sourceFrame[i]=$EE : Next\n rc=GemPollSend()', [0, 1, 0, 0, 1, 0, 1, 32828, 1, 16], 14),
 ('busy preserves caller copy', 'rc=GemTrySend(@sourceFrame[0],64)', [-1, 1, 0, 0, 1, -21, 1, 32828, 1, 16], 14),
 ('region pinned', 'rc=GemSetRegion(gem_region+64,#GEM_REGION_MIN)', [0, 1, 0, 0, 1, -21, 1, 32828, 1, 16], 14),
 ('completion', 'Complete() : rc=GemPollSend()', [1, 0, 1, 1, 1, 0, 2, 2147516476, 1, 16], 14),
 ('no double count', 'rc=GemPollSend()', [1, 0, 1, 1, 1, 0, 2, 2147516476, 1, 16], 14),
 ('maximum submit', 'For i=0 To 1535 : sourceFrame[i]=(i*7+3)&255 : Next\n view=1 : rc=GemTrySend(@sourceFrame[0],1514)', [1, 1, 1, 1, 1, 0, 3, 34282, 1, 16], 1514),
 ('status read failure retains', 'Complete() : failRead=#GEM_TSR : rc=GemPollSend()', [-1, 1, 1, 1, 1, -2, 3, 2147517930, 1, 16], 1514),
 ('status clear failure retains', 'failRead=-1 : failWrite=1 : rc=GemPollSend()', [-1, 1, 1, 1, 1, -2, 4, 2147517930, 1, 16], 1514),
 ('complete once after recovery', 'failWrite=0 : rc=GemPollSend()', [1, 0, 2, 2, 1, 0, 5, 2147517930, 1, 16], 1514),
 ('ambiguous start retains', 'view=2 : failWrite=1 : rc=GemTrySend(@sourceFrame[0],64)', [0, 1, 2, 2, 1, -2, 6, 32832, 1, 16], 64),
 ('ambiguous start cannot replay', 'failWrite=0 : rc=GemTrySend(@sourceFrame[0],64)', [-1, 1, 2, 2, 1, -21, 6, 32832, 1, 16], 64),
 ('ambiguous send completes', 'Complete() : rc=GemPollSend()', [1, 0, 3, 3, 1, 0, 7, 2147516480, 1, 16], 64),
 ('descriptor fault retires', 'view=3 : rc=GemTrySend(@sourceFrame[0],60) : Complete()\n PokeL(gem_region+#GEM_OFF_TXRING+3*16+4,#GEM_TX_USED|#GEM_TX_LAST|60|$10000000) : rc=GemPollSend()', [-1, 0, 4, 3, 1, -17, 9, 2415951932, 1, 16], 60),
 ('TSR fault retires', 'view=4 : rc=GemTrySend(@sourceFrame[0],60) : Complete() : tsr=#GEM_TSR_UND : rc=GemPollSend()', [-1, 0, 5, 3, 1, -17, 11, 2147516476, 1, 16], 60),
 ('timeout failed stop pins', 'view=5 : stopFail=1 : rc=GemSend(@sourceFrame[0],60,1)', [0, 1, 5, 3, 0, -16, 13, 32828, 1, 16], 60),
 ('failed stop refuses region', 'rc=GemSetRegion(gem_region+64,#GEM_REGION_MIN)', [0, 1, 5, 3, 0, -21, 13, 32828, 1, 16], 60),
 ('stopped poll retains', 'rc=GemPollSend()', [-1, 1, 5, 3, 0, -14, 13, 32828, 1, 16], 60),
 ('checked stop releases', 'stopFail=0 : rc=GemStopChecked()', [1, 0, 5, 3, 0, -14, 14, 32828, 1, 16], 60),
 ('idle region allowed', 'rc=GemSetRegion(gem_region,#GEM_REGION_MIN)', [1, 0, 5, 3, 0, -14, 14, 32828, 1, 16], 60),
 ('wrap descriptor', 'gem_started=1 : ncr=#GEM_NCR_RE|#GEM_NCR_TE : gem_txHead=7 : view=7 : rc=GemTrySend(@sourceFrame[0],60)', [1, 1, 7, 3, 1, 0, 15, 1073774652, 1, 16], 60),
 ('wrap completes', 'Complete() : rc=GemPollSend()', [1, 0, 0, 4, 1, 0, 16, 3221258300, 1, 16], 60),
 ('oversize refused', 'rc=GemTrySend(@sourceFrame[0],1515)', [0, 0, 0, 4, 1, -1, 16, 3221258300, 1, 16], 60),
 ('null refused', 'rc=GemTrySend(0,60)', [0, 0, 0, 4, 1, -1, 16, 3221258300, 1, 16], 60),
 ('PCIe down stop releases', 'view=0 : rc=GemTrySend(@sourceFrame[0],60) : linkUp=0 : rc=GemStopChecked()', [1, 0, 0, 4, 0, 0, 17, 32828, 1, 16], 60),]
 for k,(_,code,_,_) in enumerate(steps):s+=code+f"\n Save({k},rc)\n"
 s+=f" PokeI($E1C00008,{len(steps)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\n"
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=[dict(name=n,expected=e,copied=b) for n,_,e,b in steps]),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.compiler,a.out.resolve())
