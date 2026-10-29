"""Build physical-board cooperative exponentiation and interleaving proof."""
from pathlib import Path
import argparse, hashlib, json, os, random, re, subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Crypto/bignum_job.pbi','Anvil/Crypto/bignum.pbi','RaspberryPi4/Lib/mmu.pi4']
 rng=random.Random(17423);cases=[];data=[]
 for bits,expbits in [(15,0),(31,1),(255,256),(256,256),(384,384),(521,521),(1024,17),(2048,17)]:
  modulus=(1<<(bits-1))|rng.getrandbits(bits-1)|1
  exponent=rng.getrandbits(expbits) if expbits else 0
  for base in [0,modulus-1,rng.randrange(modulus)]:
   n=(bits+7)//8;en=(expbits+7)//8
   cases.append(dict(bits=bits,bytes=n,exponent_bytes=en,expected=pow(base,exponent,modulus).to_bytes(n,'big').hex(),calls=(en*8+2)//3))
   data.append(modulus.to_bytes(n,'big')+base.to_bytes(n,'big')+exponent.to_bytes(en,'big'))
 s='\n'.join('XIncludeFile "'+names[i]+'"' for i in [1,0,2])+'\n'+r'''
Global wtable.i
Global *pet,*timer
Global ja.BnPowJob
Global jb.BnPowJob
Global Dim xa.u[160]
Global Dim xb.u[160]
Global Dim modulus.u[160]
Global Dim pa.u[160]
Global Dim pb.u[160]
Global Dim ta.u[160]
Global Dim tb.u[160]
Global Dim output.a[512]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure BnJobFixture(index.i,v.i,n.i,en.i)
 Define i.i,rc.i,other.i,calls.i,t.i,elapsed.i,maximum.i,p.i,inverse.i,start.i,beginTime.i,invalid.i,active.i,wiped.i
 BnDecode(@modulus[0],v,n)
 BnDecodeReduce(@xa[0],v+n,n,@modulus[0])
 BnDecodeReduce(@xb[0],v+n,n,@modulus[0])
 inverse=BnNinv15(BnGw(@modulus[0],1))
 pet() : start=timer()
 rc=BnPowBegin(@ja,@xa[0],v+2*n,en,@modulus[0],inverse,@pa[0],@ta[0])
 beginTime=timer()-start
 other=BnPowBegin(@jb,@xb[0],v+2*n,en,@modulus[0],inverse,@pb[0],@tb[0])
 active=0
 If en>0 : active=BnPowBegin(@ja,@xa[0],v+2*n,en,@modulus[0],inverse,@pa[0],@ta[0]) : EndIf
 invalid=BnPowStep(@ja,0)
 calls=0 : maximum=0
 While rc=0
  t=timer() : rc=BnPowStep(@ja,3) : elapsed=timer()-t
  If elapsed>maximum : maximum=elapsed : EndIf
  If other=0 : other=BnPowStep(@jb,7) : EndIf
  calls=calls+1 : pet()
 Wend
 While other=0 : other=BnPowStep(@jb,7) : pet() : Wend
 p=$E1C00100+index*1024
 PokeI(p,rc) : PokeI(p+8,other) : PokeI(p+16,calls)
 PokeI(p+24,maximum) : PokeI(p+32,beginTime) : PokeI(p+40,timer()-start)
 PokeI(p+48,invalid) : PokeI(p+56,active)
 BnEncode(@output[0],n,@xa[0])
 For i=0 To n-1 : PokeA(p+128+i,output[i]) : Next
 BnEncode(@output[0],n,@xb[0])
 For i=0 To n-1 : PokeA(p+384+i,output[i]) : Next
 BnPowClear(@ja) : BnPowClear(@jb) : wiped=1
 For i=0 To SizeOf(BnPowJob)-1
  If PeekA(@ja+i)<>0 Or PeekA(@jb+i)<>0 : wiped=0 : EndIf
 Next
 For i=0 To 159
  If pa[i]<>0 Or pb[i]<>0 Or ta[i]<>0 Or tb[i]<>0 : wiped=0 : EndIf
 Next
 PokeI(p+64,wiped)
 ; Cancellation must wipe partial intermediates and refuse further stepping.
 rc=BnPowBegin(@ja,@xa[0],v+2*n,en,@modulus[0],inverse,@pa[0],@ta[0])
 rc=BnPowStep(@ja,1) : BnPowClear(@ja)
 PokeI(p+72,BnPowStep(@ja,1))
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 32767 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$42504A31)
 pet=PeekI(wtable+16+6*8) : timer=PeekI(wtable+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for i,c in enumerate(cases):s+=f' BnJobFixture({i},?V{i},{c["bytes"]},{c["exponent_bytes"]})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed() : ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,b in enumerate(data):
  s+=f'V{i}:\n'
  for j in range(0,len(b),24):s+=' Data.a '+','.join(map(str,b[j:j+24]))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c07fff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
