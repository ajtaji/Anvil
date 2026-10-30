"""Build physical bounded GCM decryption tests against independent AES-GCM."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pmf_compiler import resolve_compiler
from gen_gcm_vectors import build_vectors

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Crypto/aes.pbi','Anvil/Crypto/gcm.pbi','Anvil/Crypto/gcm_job.pbi','RaspberryPi4/Lib/mmu.pi4']
 vectors=[v for v in build_vectors() if len(v[1])==12]
 for keylen in (16,24,32):
  for n in (255,256,257,4096,16640):
   key=bytes(range(keylen));iv=bytes(range(12));aad=bytes((i*13)&255 for i in range(257));plain=bytes((i*37+11)&255 for i in range(n))
   ct=AESGCM(key).encrypt(iv,plain,aad);vectors.append((key,iv,aad,plain,ct[:-16],ct[-16:]))
 cases=[];s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r"""
Global wtable.i
Global *pet,*timer
Global Dim output.a[16642]
Global Dim baseline.a[16642]
Global Dim tag.a[16]
Global Dim junk.a[32]
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure GcmJobFixture(index.i,v.i,keylen.i,aadlen.i,n.i,mode.i)
 Define i.i,key.i,nonce.i,aad.i,plain.i,cipher.i,ct.i,rc.i,busy.i,t.i,cost.i,maximum.i,steps.i,bad.i,wipe.i,guard.i,expected.i,baseus.i,verdict.i,cancelled.i
 key=v : nonce=key+keylen : aad=nonce+12 : plain=aad+aadlen : cipher=plain+n
 For i=0 To 16642 : output[i]=$A5 : baseline[i]=$A5 : Next
 For i=0 To 15 : tag[i]=PeekA(cipher+n+i) : Next
 If mode=2 : tag[7]=tag[7] ! 1 : EndIf
 ct=cipher
 If mode=1
  For i=0 To n-1 : output[1+i]=PeekA(cipher+i) : Next
  ct=@output[1]
 EndIf
 t=timer() : rc=GcmInit(key,keylen)
 rc=GcmDecrypt(nonce,12,aad,aadlen,cipher,n,@baseline[1],@tag[0])
 baseus=timer()-t
 t=timer() : rc=GcmJobBeginDecrypt(key,keylen,nonce,aad,aadlen,ct,n,@output[1],@tag[0])
 maximum=timer()-t
 cancelled=1
 If mode=3
  rc=GcmJobStep() : GcmJobCancel()
  If GcmJobStep()<>-1 Or GcmJobResult<>-1 : cancelled=0 : EndIf
  For i=0 To 31 : If gcmj_key[i]<>0 : cancelled=0 : EndIf : Next
  For i=0 To 15 : If gcmj_h[i]<>0 Or gcmj_y[i]<>0 Or gcmj_tag[i]<>0 : cancelled=0 : EndIf : Next
  rc=GcmJobBeginDecrypt(key,keylen,nonce,aad,aadlen,ct,n,@output[1],@tag[0])
 EndIf
 busy=GcmJobBeginDecrypt(0,0,0,0,0,0,0,0,0)
 steps=0
 While rc=0 And steps<1000
  t=timer() : rc=GcmJobStep() : cost=timer()-t
  If cost>maximum : maximum=cost : EndIf
  steps=steps+1
  ; A different synchronous user overwrites all shared AES/GHASH scratch.
  i=GcmInit(@junk[0],32)
  GhashRun(@baseline[1],@secGcmH[0],@junk[0],32)
  pet()
 Wend
 verdict=GcmJobResult : bad=0 : guard=cancelled
 For i=0 To n-1
  expected=PeekA(plain+i)
  If mode=2 : expected=$A5 : EndIf
  If output[1+i]<>expected : bad=bad+1 : EndIf
 Next
 If output[0]<>$A5 Or output[n+1]<>$A5 : guard=0 : EndIf
 wipe=0
 For i=0 To 31 : wipe=wipe | gcmj_key[i] : Next
 For i=0 To 15 : wipe=wipe | gcmj_h[i] | gcmj_y[i] | gcmj_tag[i] : Next
 PokeI($E1C00100+index*64,rc)
 PokeI($E1C00108+index*64,verdict)
 PokeI($E1C00110+index*64,bad)
 PokeI($E1C00118+index*64,guard)
 PokeI($E1C00120+index*64,maximum)
 PokeI($E1C00128+index*64,baseus)
 PokeI($E1C00130+index*64,busy)
 PokeI($E1C00138+index*64,wipe)
 GcmJobCancel()
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 pet=PeekI(wtable+16+6*8) : timer=PeekI(wtable+16+11*8)
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 For i=0 To 31 : junk[i]=90+i : Next
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 PokeI($E1C00000,$47434D31)
"""
 for i,(k,iv,a,p,c,t) in enumerate(vectors):
  for mode in (0,1,2,3):
   j=len(cases);cases.append(dict(keybytes=len(k),aadbytes=len(a),bytes=len(p),mode=mode))
   s+=f' GcmJobFixture({j},?GcmJobVector{i},{len(k)},{len(a)},{len(p)},{mode})\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,v in enumerate(vectors):
  b=b''.join(v);s+=f'GcmJobVector{i}:\n'
  for j in range(0,len(b),24):s+=' Data.a '+','.join(str(x) for x in b[j:j+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
