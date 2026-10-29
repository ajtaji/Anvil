"""Compile resident randomness service and DRBG isolation proofs for physical Pi4."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Core/sha256.pbi', 'Anvil/Crypto/hmac.pbi', 'Anvil/Crypto/drbg.pbi', 'Anvil/Crypto/drbg_entropy.pbi', 'Anvil/Crypto/drbg_service.pbi', 'Anvil/Hal/random_service.pbi', 'Anvil/Network/web_random.pbi']
    s=r'''XIncludeFile "Anvil/Core/sha256.pbi"
XIncludeFile "Anvil/Crypto/hmac.pbi"
XIncludeFile "Anvil/Crypto/drbg.pbi"
Global entropyMode.i,entropyCalls.i
Procedure.i HwEntropyAvailable()
 ProcedureReturn 1
EndProcedure
Procedure.i HwEntropyRead(dst.i,n.i)
 Define i.i
 entropyCalls=entropyCalls+1
 For i=0 To n-1 : PokeA(dst+i,i+entropyCalls) : Next
 If entropyMode=1 : ProcedureReturn n-1 : EndIf
 ProcedureReturn n
EndProcedure
XIncludeFile "Anvil/Crypto/drbg_entropy.pbi"
XIncludeFile "Anvil/Crypto/drbg_service.pbi"
XIncludeFile "Anvil/Hal/random_service.pbi"
XIncludeFile "Anvil/Network/web_random.pbi"
Global mode.i,recursive.i
Global Dim output.a[4096]
Global Dim tab.i[202]
Procedure.i Ready()
 If mode=1 : ProcedureReturn 0 : EndIf
 If mode=2 : ProcedureReturn -6 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i Generate(dst.i,n.i)
 Define i.i
 For i=0 To n-1 : PokeA(dst+i,123) : Next
 If mode=3 : ProcedureReturn n-1 : EndIf
 If mode=4 : ProcedureReturn n+1 : EndIf
 If mode=5 : ProcedureReturn -6 : EndIf
 ProcedureReturn n
EndProcedure
Procedure Store(index.i,rc.i)
 PokeI($E1C00100+index*8,rc)
EndProcedure
Procedure.i Main(services.i)
 Define i.i,rc.i,zero.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$524E4731)
 Store(0,RandomServiceReady())
 Store(1,RandomServiceBytes(@output[0],16))
 Store(2,RandomServiceBind(0,@Generate))
 Store(3,RandomServiceBind(@Ready,@Generate))
 Store(4,RandomServiceBind(@Ready,@Generate))
 Store(5,RandomServiceBytes(0,16))
 Store(6,RandomServiceBytes(@output[0],0))
 Store(7,RandomServiceBytes(@output[0],4097))
 For mode=1 To 5
  For i=0 To 15 : output[i]=99 : Next
  rc=RandomServiceBytes(@output[0],16) : Store(7+mode,rc)
  zero=0 : For i=0 To 15 : zero=zero | output[i] : Next
  Store(20+mode,zero)
 Next
 mode=6 : Store(13,RandomServiceBytes(@output[0],16)) : randomServiceBusy=1 : Store(14,RandomServiceBytes(@output[0],16)) : randomServiceBusy=0
 Store(15,RandomServiceReady())
 Store(16,WebRandomBind(0))
 tab[0]=$53564E41 | (1<<32) : tab[1]=9 | (200<<32)
 Store(17,WebRandomBind(@tab[0]))
 tab[1]=10 | (200<<32) : Store(18,WebRandomBind(@tab[0]))
 tab[177]=@RandomServiceBytes : tab[178]=@RandomServiceReady
 Store(19,WebRandomBind(@tab[0]))
 Store(26,WebRandomBytes(@output[0],16))
 Store(27,WebRandomReady())
 randomSvcReadyFn=@RandomDrbgReady : randomSvcGenerateFn=@RandomDrbgGenerate
 entropyMode=1 : Store(28,RandomServiceReady()) : Store(29,DrbgSeeded())
 entropyMode=0
 Sha256Begin() : Sha256Update("prefix",6)
 Store(30,RandomServiceBytes(@output[0],16))
 Sha256Update("suffix",6) : Sha256End($E1C00400)
 HmacKey("key",3) : HmacBegin() : HmacUpdate("first",5)
 Store(31,RandomServiceBytes(@output[0],16))
 HmacUpdate("last",4) : HmacEnd($E1C00420,32)
 For i=0 To 15 : PokeA($E1C00440+i,output[i]) : Next
 randomDrbgBytes=1048576 : entropyMode=1
 Store(32,RandomServiceBytes(@output[0],16))
 zero=0 : For i=0 To 15 : zero=zero | output[i] : Next
 Store(33,zero)
 entropyMode=0 : Store(34,RandomServiceBytes(@output[0],16))
 Store(35,randomDrbgBytes) : Store(36,entropyCalls)
 zero=0 : For i=0 To 58 : zero=zero | secRandomSaved[i] : Next
 Store(37,zero)
 For i=0 To 15 : PokeA($E1C00450+i,output[i]) : Next
 ProcedureReturn 0
EndProcedure
'''
    source=out/"proof.pi4";source.write_text(s,encoding="utf8")
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=list(range(38))),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();build(args.compiler,args.out.resolve())
