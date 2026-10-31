"""Physical integration: frames, CRYPTO storage and final packet ACK eligibility."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from build_quic_handshake_frames_cpu import vi

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/quic_handshake_packet.pbi','Anvil/Network/quic_handshake_ack.pbi','Anvil/Network/quic_handshake_frames.pbi','Anvil/Network/quic_crypto_stream.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];vectors=[]
 def code(s):steps.append(s)
 def check(name,expr,want):code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def vec(b):vectors.append(b or b'\0');return f'?V{len(vectors)-1}'
 def reset(level=0,cap=64):code(f'Prepare({level},{cap})')
 def begin(b,pn=1,level=0,want=0):
  code(f'rc=QuicHandshakePacketBegin(@job,{vec(b)},{len(b)},{pn},{level},@rx,@ack)');check('begin','rc',want)
 def step(want,name='step'):check(name,'QuicHandshakePacketStep(@job)',want)
 def unseen(pn=1):check('not acknowledged yet',f'QuicHandshakeAckSeen(@ack,{pn})',0)
 def crypto(off,b):return b'\6'+vi(off)+vi(len(b))+b
 def fnv(b):
  h=2166136261
  for c in b:h=((h^c)*16777619)&0xffffffff
  return h
 ack=b'\2\0\0\0\0'
 reset();begin(b'\1\0'+crypto(0,b'abc')+ack)
 unseen();step(1);unseen();step(1);step(1);unseen();step(1);check('queued','rx\\buffered',3);unseen()
 step(2);unseen();check('ACK event kind','job\\frame\\kind',2)
 step(2,'unaccepted event stays');unseen();check('accept ACK','QuicHandshakePacketAccept(@job)',0)
 unseen();step(4);check('recorded after all frames','QuicHandshakeAckSeen(@ack,1)',1);check('ACK demand','ack\\pending',1)
 step(4,'complete idempotent');check('no duplicate completion demand','ack\\demand',1)
 check('stored bytes','Hash(@data[0],3)',fnv(b'abc'))
 # Same packet number cannot replay CRYPTO or ACK effects.
 begin(crypto(0,b'XYZ')+ack);check('duplicate lookup','job\\duplicate',1)
 step(6);check('duplicate crypto not applied','Hash(@data[0],3)',fnv(b'abc'));check('duplicate demand unchanged','ack\\demand',1)
 begin(b'\x1f');step(6,'malformed duplicate discarded')
 begin(b'');step(6,'empty duplicate discarded')
 check('clear demand','QuicHandshakeAckSent(@ack,1)',1)
 begin(ack,pn=2);step(2);check('accept ACK only','QuicHandshakePacketAccept(@job)',0);step(4);check('ACK only not eliciting','ack\\pending',0)
 begin(ack,pn=2);step(6,'duplicate ACK has no event');check('duplicate ACK no response','ack\\pending',0)
 # Bad tail cannot commit packet even when an earlier frame queued bytes.
 reset();begin(crypto(0,b'abc')+b'\x1f');step(1);step(1);step(-3424);unseen();check('partial effects retained','rx\\buffered',3)
 step(-3424,'fatal remains latched');begin(b'\1',want=-3452)
 reset();begin(crypto(32768,b'x'));step(1);step(-3425);unseen();check('capacity refusal queued none','rx\\buffered',0)
 reset();begin(ack+b'\1');step(2);check('reject ACK','QuicHandshakePacketReject(@job)',-3454);step(-3454);unseen()
 # Close is a terminal event, never processing a following CRYPTO frame.
 reset();begin(b'\x1c\x01\x06\x03bye'+crypto(0,b'abc'));step(5);check('close code','job\\frame\\error',1);check('close reason','Hash(job\\frame\\data,job\\frame\\bytes)',fnv(b'bye'));unseen();step(5);check('tail ignored after close','rx\\buffered',0)
 # Slice a large CRYPTO frame; it is not ACK-eligible after only the first slice.
 body=bytes((i*19+3)&255 for i in range(20000))
 reset(level=2);begin(crypto(0,body),level=2);step(1);step(1);check('bounded first copy','rx\\buffered',16384);unseen();step(1);check('second copy','rx\\buffered',20000);unseen();step(4);check('large contents','Hash(@data[0],20000)',fnv(body))
 # ACK tracker exhaustion occurs after parsing but still cannot ACK the packet.
 reset(cap=1);check('prior packet','QuicHandshakeAckRecord(@ack,0,0)',1);begin(b'\1',pn=2);step(1);step(-3443);unseen(2);check('prior history retained','QuicHandshakeAckSeen(@ack,0)',1)
 reset();begin(b'',want=-3453);begin(b'\1',level=2,want=-3452)
 check('source alias','QuicHandshakePacketBegin(@job,@data[0],1,1,0,@rx,@ack)',-3451)
 begin(b'\1');begin(b'\1',want=-3452);check('accept without event','QuicHandshakePacketAccept(@job)',-3452);step(1);step(4)
 # Sequential out-of-order fragments produce the same stream and ACK range.
 reset()
 for pn,off,b in [(3,6,b'ghi'),(1,0,b'abc'),(2,3,b'def')]:
  begin(crypto(off,b),pn);step(1);step(1);unseen(pn);step(4)
 check('one merged ACK range','ack\\count',1);check('all queued','rx\\buffered',9);check('joined bytes','Hash(@data[0],9)',fnv(b'abcdefghi'))
 for invalid in [b'\6\0\5abc',b'\x40\1',b'\x1d',b'\2\0\0\0\1']:
  reset();begin(invalid);step(-3422 if invalid==b'\6\0\5abc' else -3427 if invalid in (b'\x40\1',b'\x1d') else -3424);unseen()
 s=r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_handshake_packet.pbi"
Global job.QuicHandshakePacket,rx.QuicCryptoRx,ack.QuicHandshakeAck
Global Dim data.a[32768]
Global Dim bits.a[4096]
Global Dim ranges.a[1024]
Procedure Prepare(level.i,capacity.i)
 Define i.i,rc.i
 For i=0 To SizeOf(QuicHandshakePacket)-1 : PokeA(@job+i,0) : Next
 rc=QuicCryptoRxInit(@rx,level,@data[0],32768,@bits[0],4096)
 rc=QuicHandshakeAckInit(@ack,level,@ranges[0],capacity)
EndProcedure
Procedure.i Hash(p.i,n.i)
 Define i.i,h.i
 h=2166136261
 For i=0 To n-1 : h=((h ! PeekA(p+i))*16777619)&$FFFFFFFF : Next
 ProcedureReturn h
EndProcedure
Procedure.i Main()
 Define rc.i,j.i
 For j=0 To 65535 : PokeA($E1C00000+j,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for k,b in enumerate(vectors):
  s+=f'V{k}:\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(map(str,b[i:i+24]))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
