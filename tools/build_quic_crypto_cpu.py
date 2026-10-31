"""Compile physical QUIC AES-128-GCM fixtures; real shared crypto, no emulator."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from quic_crypto_cases import cases

def build(compiler,out,vectors):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=cases(json.loads(vectors.read_text()));assert len(rows)<127
 names=['Anvil/Core/sha256.pbi','Anvil/Crypto/hmac.pbi','Anvil/Crypto/hkdf.pbi','Anvil/Crypto/aes.pbi','Anvil/Crypto/gcm.pbi','Anvil/Crypto/gcm_job.pbi','Anvil/Crypto/tls13_record.pbi','Anvil/Network/quic_crypto.pbi','RaspberryPi4/Lib/mmu.pi4']
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global keys.QuicKeys,kjob.QuicKeyJob,job.QuicPacketJob,other.QuicPacketJob
Global Dim seed.a[32]
Global Dim packet.a[2048]
Global Dim original.a[2048]
Global Dim dummy.a[32]
Global Dim record.a[128]
Global interleaveFailure.i
Global *pet,*clock
Global table.i,invalidations.i
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure Invalidate()
 invalidations=invalidations+1
 Tls13RecInvalidateCipher()
EndProcedure
Procedure Interleave()
 Define n.i,i.i
 n=Tls13RecProtect(23,@dummy[0],16,0,@record[0],128)
 If n=0
  interleaveFailure=1
 Else
  n=Tls13RecUnprotect(@record[0],n)
  If n<>16 : interleaveFailure=1 : EndIf
  For i=0 To 15 : If record[5+i]<>0 : interleaveFailure=1 : EndIf : Next
 EndIf
EndProcedure
Procedure Run(index.i,bytes.i,seedBytes.i,side.i,traffic.i,encrypt.i,shortId.i,number.i,mode.i,cancelStep.i,wrongKey.i,retry.i)
 Define i.i,rc.i,p.i,steps.i,t.i,cost.i,keyMax.i,stepMax.i,beginCost.i,early.i,verified.i,k.i,busy.i,foreign.i,again.i,guard.i
 p=$E1C00100+index*2048
 For i=0 To 2047 : packet[i]=$A5 : original[i]=$A5 : Next
 For i=0 To seedBytes-1 : Read.a seed[i] : Next
 For i=0 To bytes-1 : Read.a packet[8+i] : original[8+i]=packet[8+i] : Next
 For i=0 To SizeOf(QuicKeys)-1 : PokeA(@keys+i,0) : Next
 For i=0 To SizeOf(QuicKeyJob)-1 : PokeA(@kjob+i,0) : Next
 For i=0 To SizeOf(QuicPacketJob)-1 : PokeA(@job+i,0) : PokeA(@other+i,0) : Next
 invalidations=0
 interleaveFailure=0
 For i=0 To 31 : dummy[i]=0 : Next
 Tls13RecReset()
 Tls13RecSetWriteKey(@dummy[0],@dummy[0]) : Tls13RecSetReadKey(@dummy[0],@dummy[0])
 If traffic : rc=QuicTrafficKeysBegin(@kjob,@keys,@seed[0],seedBytes)
 Else : rc=QuicInitialKeysBegin(@kjob,@keys,@seed[0],seedBytes,side) : EndIf
 If mode=3
  For i=1 To cancelStep : rc=QuicKeyJobStep(@kjob) : Next
  QuicKeyJobCancel(@kjob) : rc=#QUIC_CRYPTO_CANCELLED
 Else
  While rc=0
   pet() : t=clock() : rc=QuicKeyJobStep(@kjob) : cost=clock()-t
   If cost>keyMax : keyMax=cost : EndIf
  Wend
 EndIf
 If wrongKey : PokeA(@keys\key0,PeekA(@keys\key0) ! 1) : EndIf
 If mode<>3 And rc=1
  If mode=2 : foreign=GcmJobBeginEncrypt(@keys\key0,16,@keys\iv0,0,0,0,0,0,@dummy[0]) : EndIf
  If encrypt=0 : number=number-1 : EndIf
  t=clock()
  If retry : rc=QuicRetryJobBegin(@job,@packet[8],bytes,encrypt)
  Else : rc=QuicPacketJobBegin(@job,@keys,@packet[8],bytes,shortId,number,encrypt) : EndIf
  beginCost=clock()-t
  If mode=2
   foreign=GcmJobBusy() : GcmJobCancel()
  Else
   If mode=1
    busy=QuicPacketJobBegin(@other,@keys,@packet[8],bytes,shortId,number,encrypt)
    foreign=QuicPacketJobCancel(@other)
   EndIf
   While rc=0 And steps<1024
    If mode=4 : Interleave() : EndIf
    pet() : t=clock() : rc=QuicPacketJobStep(@job) : cost=clock()-t
    If cost>stepMax : stepMax=cost : EndIf
    steps=steps+1
    If GcmJobAuthenticated() : verified=1 : EndIf
    If encrypt=0 And verified=0 And rc<>1
     For k=job\plainOffset To bytes-17
      If packet[8+k]<>original[8+k] : early=early+1 : EndIf
     Next
    EndIf
    If cancelStep>0 And steps=cancelStep And rc=0 : rc=QuicPacketJobCancel(@job) : EndIf
   Wend
   If mode=4 : Interleave() : EndIf
   again=QuicPacketJobStep(@job)
  EndIf
 EndIf
 For i=0 To 7 : If packet[i]<>$A5 Or packet[8+bytes+i]<>$A5 : guard=guard+1 : EndIf : Next
 PokeI(p,rc) : PokeI(p+8,job\number) : PokeI(p+16,job\plainOffset) : PokeI(p+24,job\plainBytes)
 PokeI(p+32,keyMax) : PokeI(p+40,beginCost) : PokeI(p+48,stepMax) : PokeI(p+56,steps)
 PokeI(p+64,early) : PokeI(p+72,guard) : PokeI(p+80,busy) : PokeI(p+88,foreign)
 PokeI(p+96,GcmJobBusy()) : PokeI(p+104,quicCryptoOwner) : PokeI(p+112,invalidations) : PokeI(p+120,again)
 For i=0 To SizeOf(QuicKeys)-1 : PokeA(p+128+i,PeekA(@keys+i)) : Next
 For i=0 To bytes-1 : PokeA(p+256+i,packet[8+i]) : Next
 For i=0 To 47 : If PeekA(@job\hp0+i)<>0 : PokeI(p+224,1) : EndIf : Next
 If mode=3
  For i=0 To SizeOf(QuicKeyJob)-1 : If PeekA(@kjob+i)<>0 : PokeI(p+232,1) : EndIf : Next
 EndIf
 PokeI(p+240,interleaveFailure)
 QuicKeysWipe(@keys)
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 *pet=PeekI(table+16+6*8) : *clock=PeekI(table+16+11*8)
 For i=0 To 262143 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$51434331)
 PokeI($E1C00010,2048)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 QuicCipherInvalidateHook=@Invalidate
'''
 s+=f' PokeI($E1C00008,{len(rows)})\n'
 for i,c in enumerate(rows):
  params=[i,len(bytes.fromhex(c['input'])),len(bytes.fromhex(c['seed'])),c['side'],int(c['traffic']),c['encrypt'],c['shortid'],c['number'],c['mode'],c['cancel'],int(c['wrong_key']),c.get('retry',0)]
  s+=f' Restore Case{i}\n Run('+','.join(map(str,params))+')\n'
 s+=' MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(rows):s+=f'Case{i}:\n Data.a '+','.join(map(str,bytes.fromhex(c['seed']+c['input'])))+'\n'
 s+='EndDataSection\n';src=out/'proof.pi4';src.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(src),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1600:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 todo=list(names)
 while todo:
  name=todo.pop()
  for dep in re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/name).read_text(),re.M):
   if dep not in names:names.append(dep);todo.append(dep)
 payload=(out/'proof.img.pmf').read_bytes()
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c3ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},checked_ranges=ranges,cases=rows),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);p.add_argument('--out',required=True,type=Path);p.add_argument('--vectors',required=True,type=Path)
 a=p.parse_args();build(a.compiler,a.out.resolve(),a.vectors)
