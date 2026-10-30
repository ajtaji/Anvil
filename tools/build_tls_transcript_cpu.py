"""Compile real transcript chunking, SHA interference and cancellation on Pi."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Core/sha256.pbi','Anvil/Crypto/tls13_hs.pbi','RaspberryPi4/Lib/mmu.pi4']
 hs=(root/names[1]).read_text()
 def procedure(name):
  m=re.search(r'^Procedure(?:\.i)? '+name+r'\([^\n]*\n.*?^EndProcedure',hs,re.M|re.S);assert m,name
  return m[0]+'\n'
 data=bytes((i*29+7)&255 for i in range(16384));cases=[]
 for n in [0,1,63,64,65,511,512,513,1023,1024,1025,4096,16384]:
  cases.append(dict(bytes=n,cancel=0,mode=1,expected=hashlib.sha256(data[:37]+data[:n]).hexdigest(),rc=1,err=0))
 for stop in range(1,6):
  n=1537;used=min(n,(stop-1)*512)
  cases.append(dict(bytes=n,cancel=stop,mode=1,expected=hashlib.sha256(data[:37]+data[:used]).hexdigest(),rc=0,err=26))
 for n,mode in [(1025,0),(-1,1),(1,2),(0,2)]:
  bad=n<0 or (mode==2 and n>0)
  cases.append(dict(bytes=n,cancel=0,mode=mode,expected=hashlib.sha256(data[:37]+(b'' if bad else data[:n])).hexdigest(),rc=0 if bad else 1,err=27 if bad else 0))
 s='XIncludeFile "'+names[0]+'"\nXIncludeFile "'+names[2]+'"\n'
 for name in ['TLS13_OK','TLS13_ST_FAILED','TLS13_REFUSE_COOPERATIVE_STOP','TLS13_REFUSE_TRANSCRIPT_INPUT']:
  s+=re.search(r'^#'+name+r'\s*=.*$',hs,re.M)[0]+'\n'
 s+='#TLS_ALERT_INTERNAL_ERROR=80\nGlobal Tls13State.i,Tls13Err.i,Tls13Alert.i\nGlobal Dim TlsTrSnap.a[104]\nGlobal *Tls13PauseHook\n'
 for name in ['TlsFail','Tls13TranscriptReset','Tls13TranscriptAbsorb','Tls13TranscriptAppend','Tls13TranscriptHash']:s+=procedure(name)
 s+=r"""
Global table.i
Global *pet,*timer
Global Dim input.a[16384]
Global Dim digest.a[32]
Global Dim foreign.a[32]
Global calls.i,stopAt.i,lastTick.i,maxGap.i
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Interfere()
 Define gap.i
 gap=timer()-lastTick : If gap>maxGap : maxGap=gap : EndIf
 calls=calls+1 : pet()
 ; A different service may use the single SHA context while this one yields.
 Sha256Of(@input[8000],31,@foreign[0])
 lastTick=timer()
 If stopAt>0 And calls=stopAt : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure Run(index.i,n.i,stop.i,mode.i)
 Define p.i,rc.i,retry.i,i.i,addr.i,begin.i,elapsed.i,syncCost.i
 p=$E1C00100+index*128
 Tls13State=0 : Tls13Err=0 : Tls13Alert=0 : Tls13PauseHook=0
 Tls13TranscriptReset() : Tls13TranscriptAbsorb(@input[0],37)
 begin=timer()
 If n>=0 And mode<>2 : Tls13TranscriptAbsorb(@input[0],n) : EndIf
 syncCost=timer()-begin
 Tls13TranscriptReset() : Tls13TranscriptAbsorb(@input[0],37)
 calls=0 : stopAt=stop : maxGap=0 : addr=@input[0]
 If mode<>0 : Tls13PauseHook=@Interfere : EndIf
 If mode=2 : addr=0 : EndIf
 begin=timer() : lastTick=begin
 rc=Tls13TranscriptAppend(addr,n) : elapsed=timer()-begin
 retry=-1
 If rc=0 : retry=Tls13TranscriptAppend(@input[0],1) : EndIf
 Tls13TranscriptHash(@digest[0])
 PokeI(p,rc) : PokeI(p+8,Tls13Err) : PokeI(p+16,Tls13State) : PokeI(p+24,calls)
 PokeI(p+32,maxGap) : PokeI(p+40,syncCost) : PokeI(p+48,elapsed) : PokeI(p+56,retry)
 For i=0 To 31 : PokeA(p+64+i,digest[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 pet=PeekI(table+16+6*8) : timer=PeekI(table+16+11*8)
 For i=0 To 16383 : PokeA($E1C00000+i,0) : input[i]=(i*29+7) & 255 : Next
 PokeI($E1C00000,$54524131)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
"""
 for i,c in enumerate(cases):s+=f' Run({i},{c["bytes"]},{c["cancel"]},{c["mode"]})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed() : ProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1800:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
