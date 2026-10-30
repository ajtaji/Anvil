"""Compile real key-share setup control flow with deterministic RNG/key seams.
This tests scheduling/refusal, not randomness or elliptic-curve arithmetic.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Crypto/tls13_hs.pbi','RaspberryPi4/Lib/mmu.pi4'];hs=(root/names[0]).read_text()
 def procedure(name):
  m=re.search(r'^Procedure(?:\.i)? '+name+r'\([^\n]*\n.*?^EndProcedure',hs,re.M|re.S);assert m,name
  return m[0]+'\n'
 cases=[dict(stop=0,fail=0,retry=0,hook=1,rc=1,err=0,draws=3,derives=1,checks=4)]
 for stop in range(1,19):
  cases.append(dict(stop=stop,fail=0,retry=1,hook=1,rc=0,err=26,draws=0 if stop==1 else 1 if stop==2 else 2+(stop-2)//2,derives=max(0,(stop-3)//2),checks=stop))
 for fail in [1,2,3]:cases.append(dict(stop=0,fail=fail,retry=0,hook=1,rc=0,err=7,draws=fail,derives=0,checks=fail))
 cases += [dict(stop=0,fail=0,retry=1,hook=1,rc=0,err=7,draws=10,derives=8,checks=18),dict(stop=0,fail=0,retry=0,hook=0,rc=1,err=0,draws=3,derives=1,checks=0),dict(stop=0,fail=0,retry=2,hook=1,rc=0,err=99,draws=0,derives=0,checks=0)]
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'
 for name in ['TLS13_OK','TLS13_ST_FAILED','TLS13_REFUSE_COOPERATIVE_STOP','TLS13_REFUSE_KEYGEN_FAILED']:
  s+=re.search(r'^#'+name+r'\s*=.*$',hs,re.M)[0]+'\n'
 s+=r"""
#TLS_ALERT_INTERNAL_ERROR=80
Global Tls13State.i,Tls13Err.i,Tls13Alert.i,TlsKeyShareLen.i,TlsSessionIdLen.i
Global Dim TlsClientRandom.a[32]
Global Dim TlsSessionId.a[32]
Global Dim secTlsPriv.a[32]
Global *Tls13SetupPauseHook
Global table.i
Global *pet
Global stopAt.i,failAt.i,retryMode.i,draws.i,derives.i,checks.i
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i DrbgGenerate(dst.i,n.i)
 Define i.i
 draws=draws+1
 If draws=failAt : ProcedureReturn 0 : EndIf
 For i=0 To n-1 : PokeA(dst+i,draws) : Next
 ProcedureReturn n
EndProcedure
Procedure.i Tls13DeriveKeySharePublic()
 derives=derives+1
 If retryMode=1 : ProcedureReturn 0 : EndIf
 TlsKeyShareLen=32 : ProcedureReturn 1
EndProcedure
Procedure.i PauseSetup()
 checks=checks+1 : pet()
 If checks=stopAt : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
"""
 for name in ['TlsFail','Tls13SetupCheckpoint','Tls13NewKeyShare']:s+=procedure(name)
 s+=r"""
Procedure Run(index.i,stop.i,fail.i,retry.i,hook.i)
 Define p.i,rc.i
 stopAt=stop : failAt=fail : retryMode=retry : checks=0 : draws=0 : derives=0
 Tls13Err=0 : Tls13Alert=0 : Tls13State=0 : TlsKeyShareLen=0 : TlsSessionIdLen=0
 If retry=2 : Tls13State=#TLS13_ST_FAILED : Tls13Err=99 : EndIf
 Tls13SetupPauseHook=0 : If hook<>0 : Tls13SetupPauseHook=@PauseSetup : EndIf
 rc=Tls13NewKeyShare() : p=$E1C00100+index*128
 PokeI(p,rc) : PokeI(p+8,Tls13Err) : PokeI(p+16,Tls13State)
 PokeI(p+24,draws) : PokeI(p+32,derives) : PokeI(p+40,checks)
 PokeI(p+48,TlsKeyShareLen) : PokeI(p+56,TlsSessionIdLen)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable() : pet=PeekI(table+16+6*8)
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$54534B31)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
"""
 for i,c in enumerate(cases):s+=f' Run({i},{c["stop"]},{c["fail"]},{c["retry"]},{c["hook"]})\n'
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
