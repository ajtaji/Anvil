"""Physical protected-packet to receipt pipeline; independent Python AEAD inputs."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from quic_crypto_cases import protect,keys,CID
from quic_wire_cases import long

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=[]
 def add(name,plain=b'\6\0\3abc\1\0',level=0,mode=0,rc=4,auth=1,queued=3,count=1,pending=1,alter=None,reserved=False,tail=b''):
  seed=CID if level==0 else bytes(range(32));header=long(kind=level,pn=1,pnbytes=4,cipher=len(plain)+16)
  if reserved:header=bytes([header[0]|4])+header[1:]
  wire=protect(header,plain,1,keys(seed,1,level==2));consumed=0 if mode==1 else len(wire)
  if alter is not None:
   altered=bytearray(wire);altered[alter]^=1;wire=bytes(altered)
  rows.append(dict(name=name,wire=(wire+tail).hex(),seed=seed.hex(),level=level,mode=mode,rc=rc,auth=auth,queued=queued,count=count,pending=pending,consumed=consumed))
 add('Initial protected CRYPTO')
 add('Handshake protected CRYPTO',level=2)
 for i in range(1,17):add('bad tag '+str(i),alter=-i,rc=6,auth=0,queued=0,count=0,pending=0)
 add('authenticated malformed frame',plain=b'\x1f\0\0\0',rc=-3424,queued=0,count=0,pending=0)
 add('authenticated reserved bits',reserved=True,rc=-3344,auth=0,queued=0,count=0,pending=0)
 add('wrong payload key',mode=5,rc=6,auth=0,queued=0,count=0,pending=0)
 add('cancel before authentication',mode=2,rc=-3345,auth=0,queued=0,count=0,pending=0)
 add('foreign crypto owner',mode=1,rc=-3342,auth=0,queued=0,count=0,pending=0)
 add('authenticated duplicate',mode=4,rc=6,queued=0,count=1,pending=0)
 add('ACK event accepted',plain=b'\6\0\3abc\2\0\0\0\0')
 add('ACK event rejected',plain=b'\6\0\3abc\2\0\0\0\0',mode=3,rc=-3454,count=0,pending=0)
 add('coalesced tail untouched',tail=bytes.fromhex(rows[0]['wire']))
 # Unauthenticated malformed header drops without entering GCM.
 rows.append(dict(rows[0],name='truncated header',wire='c30000',rc=6,auth=0,queued=0,count=0,pending=0,consumed=0))
 rows.append(dict(rows[0],name='wrong encryption level',level=2,seed=bytes(range(32)).hex(),rc=6,auth=0,queued=0,count=0,pending=0))
 names=['Anvil/Core/sha256.pbi','Anvil/Crypto/hmac.pbi','Anvil/Crypto/hkdf.pbi','Anvil/Crypto/aes.pbi','Anvil/Crypto/gcm.pbi','Anvil/Crypto/gcm_job.pbi','Anvil/Crypto/tls13_record.pbi','Anvil/Network/quic_handshake_receive.pbi','RaspberryPi4/Lib/mmu.pi4']
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global receive.QuicHandshakeReceive,rx.QuicCryptoRx,ack.QuicHandshakeAck
Global keys.QuicKeys,keyjob.QuicKeyJob
Global Dim seed.a[32]
Global Dim packet.a[4096]
Global Dim original.a[4096]
Global Dim data.a[4096]
Global Dim bits.a[512]
Global Dim ranges.a[1024]
Global Dim dummy.a[32]
Procedure.i Hash(p.i,n.i)
 Define i.i,h.i
 h=2166136261
 For i=0 To n-1 : h=((h ! PeekA(p+i))*16777619)&$FFFFFFFF : Next
 ProcedureReturn h
EndProcedure
Procedure Run(index.i,bytes.i,seedBytes.i,level.i,mode.i)
 Define i.i,p.i,rc.i,n.i,early.i,baseline.i,events.i,eventGate.i,foreign.i,again.i
 p=$E1C00100+index*128
 For i=0 To SizeOf(QuicHandshakeReceive)-1 : PokeA(@receive+i,0) : Next
 For i=0 To SizeOf(QuicKeys)-1 : PokeA(@keys+i,0) : Next
 For i=0 To SizeOf(QuicKeyJob)-1 : PokeA(@keyjob+i,0) : Next
 For i=0 To 4095 : packet[i]=$A5 : original[i]=$A5 : Next
 For i=0 To seedBytes-1 : Read.a seed[i] : Next
 For i=0 To bytes-1 : Read.a packet[i] : original[i]=packet[i] : Next
 rc=QuicCryptoRxInit(@rx,level,@data[0],4096,@bits[0],512)
 rc=QuicHandshakeAckInit(@ack,level,@ranges[0],64)
 If level=0 : rc=QuicInitialKeysBegin(@keyjob,@keys,@seed[0],seedBytes,1)
 Else : rc=QuicTrafficKeysBegin(@keyjob,@keys,@seed[0],seedBytes) : EndIf
 While rc=0 : rc=QuicKeyJobStep(@keyjob) : Wend
 If mode=5 : PokeA(@keys\key0,PeekA(@keys\key0) ! 1) : EndIf
 If mode=4 : rc=QuicHandshakeAckRecord(@ack,1,0) : baseline=1 : EndIf
 If mode=1 : rc=GcmJobBeginEncrypt(@keys\key0,16,@keys\iv0,0,0,0,0,0,@dummy[0]) : EndIf
 rc=QuicHandshakeReceiveBegin(@receive,@keys,@packet[0],bytes,level,-1,@rx,@ack)
 If mode=1 : foreign=GcmJobBusy() : GcmJobCancel() : EndIf
 If mode=2 And rc=0 : rc=QuicHandshakeReceiveCancel(@receive) : EndIf
 If rc=0
  For n=0 To 4095
   rc=QuicHandshakeReceiveStep(@receive)
   If receive\authenticated=0
    If rx\buffered<>0 Or ack\count<>baseline : early=early+1 : EndIf
   EndIf
   If rc=2
    events=events+1
    If ack\count<>baseline : eventGate=eventGate+1 : EndIf
    If mode=3 : rc=QuicHandshakeReceiveReject(@receive)
    Else : rc=QuicHandshakeReceiveAccept(@receive) : If rc=0 : rc=1 : EndIf : EndIf
   EndIf
   If rc<>1 : Break : EndIf
  Next
 EndIf
 again=QuicHandshakeReceiveStep(@receive)
 PokeI(p,rc) : PokeI(p+8,receive\authenticated) : PokeI(p+16,rx\buffered) : PokeI(p+24,ack\count)
 PokeI(p+32,ack\pending) : PokeI(p+40,early) : PokeI(p+48,eventGate) : PokeI(p+56,GcmJobBusy())
 PokeI(p+64,quicCryptoOwner) : PokeI(p+72,receive\consumed) : PokeI(p+80,again) : PokeI(p+88,events)
 PokeI(p+96,foreign) : PokeI(p+104,Hash(@packet[0],bytes)) : PokeI(p+112,Hash(@data[0],rx\buffered))
 If mode=2 : PokeI(p+104,QuicHandshakeReceiveStep(@receive)) : EndIf
 PokeI(p+120,Hash(@packet[0]+bytes,4096-bytes))
 QuicKeysWipe(@keys)
EndProcedure
Procedure.i Main()
 Define rc.i,j.i
 For j=0 To 65535 : PokeA($E1C00000+j,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached() : QuicCipherInvalidateHook=@Tls13RecInvalidateCipher
'''
 cases=[]
 def fnv(b):
  h=2166136261
  for c in b:h=((h^c)*16777619)&0xffffffff
  return h
 # Each row has16 fixed observations. For mutable successful wire bytes,
 # independently decrypt/header-unmask expected output rather than ignore it.
 for i,c in enumerate(rows):
  wire=bytes.fromhex(c['wire']);seed=bytes.fromhex(c['seed']);s+=f'Restore V{i}\nRun({i},{len(wire)},{len(seed)},{c["level"]},{c["mode"]})\n'
  unchanged=c['auth']==0 and c['mode']!=2
  expected_wire=None
  if unchanged:expected_wire=wire
  elif c['auth']:
   from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
   from cryptography.hazmat.primitives.ciphers.aead import AESGCM
   k=keys(seed,1,c['level']==2);plainwire=bytearray(wire)
   # Header helper above uses8-byte DCID,4-byte SCID and1-byte length here.
   offset=len(long(kind=c['level'],cipher=16))-4
   mask=Cipher(algorithms.AES(k[3]),modes.ECB()).encryptor().update(wire[offset+4:offset+20])
   plainwire[0]^=mask[0]&15
   for t in range(4):plainwire[offset+t]^=mask[t+1]
   header=bytes(plainwire[:offset+4]);end=c['consumed'];nonce=(int.from_bytes(k[2],'big')^1).to_bytes(12,'big')
   plain=AESGCM(k[1]).decrypt(nonce,wire[offset+4:end],header)
   expected_wire=header+plain+wire[end-16:]
  vals=[c['rc'],c['auth'],c['queued'],c['count'],c['pending'],0,0,0,0,c['consumed'],-3452 if c['mode']==1 else c['rc'],int('ACK event' in c['name']),int(c['mode']==1),fnv(expected_wire) if expected_wire is not None else None,fnv(b'abc' if c['queued']==3 else b''),fnv(b'\xa5'*(4096-len(wire)))]
  for j,v in enumerate(vals):
   if v is None:
    # Cancellation permits packet mutation; this slot instead observes a real
    # repeat Step call to check that cancellation remains terminal.
    v=-3345
   cases.append(dict(name=c['name']+' field '+str(j),expected=v))
 s+=f'PokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(rows):
  b=bytes.fromhex(c['seed']+c['wire']);s+=f'V{i}:\n'
  for k in range(0,len(b),24):s+=' Data.a '+','.join(map(str,b[k:k+24]))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 todo=list(names)
 while todo:
  name=todo.pop()
  for dep in re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/name).read_text(encoding='utf8'),re.M):
   if dep not in names:names.append(dep);todo.append(dep)
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases,scenarios=rows),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
