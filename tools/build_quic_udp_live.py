"""Build the physical UDP/protected-receive/protected-ACK integration fixture."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['RaspberryPi4/Lib/mmu.pi4','Anvil/Network/udp_payload.pbi','Anvil/Core/sha256.pbi','Anvil/Crypto/hmac.pbi','Anvil/Crypto/hkdf.pbi','Anvil/Crypto/aes.pbi','Anvil/Crypto/gcm.pbi','Anvil/Crypto/gcm_job.pbi','Anvil/Network/quic_handshake_receive.pbi','Anvil/Network/quic_handshake_sent.pbi','Anvil/Network/quic_crypto_send.pbi']
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+r'''
Global services.i,*pet,*clock
Global ep.UdpEndpoint,info.UdpDatagramInfo,status.UdpSocketStatus
Global readKeys.QuicKeys,writeKeys.QuicKeys,keyjob.QuicKeyJob
Global receive.QuicHandshakeReceive,sendJob.QuicPacketJob,spec.QuicLongPacketSpec
Global rx.QuicCryptoRx,ack.QuicHandshakeAck
Global history.QuicHandshakeSent,ackJob.QuicHandshakeSentAck,ackEvents.i
Global Dim historySlots.a[4096]
Global tx.QuicCryptoTx,lastSend.i,reclaimed.i
Global Dim txData.a[4096]
Global Dim txStates.a[1024]
Global Dim packet.a[1472]
Global Dim output.a[1472]
Global Dim data.a[4096]
Global Dim bits.a[512]
Global Dim ranges.a[1024]
Global received.i,badTags.i,duplicates.i,completed.i,sent.i,largest.i,maxService.i
Procedure CaptureTable()
 ASM
 adrp x1, global_services
 add x1, x1, #:lo12:global_services
 str x0, [x1]
 EndASM
EndProcedure
Procedure.i Pump()
 Define t.i,rc.i,cost.i
 pet() : t=clock() : rc=UdpPayloadService() : cost=clock()-t
 If cost>maxService : maxService=cost : EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i WaitTx(h.i)
 Define started.i,rc.i
 started=clock()
 While clock()-started<3000000
  rc=Pump() : If rc<0 : ProcedureReturn rc : EndIf
  rc=UdpPayloadStatus(h,@status) : If rc<>0 : ProcedureReturn rc : EndIf
  If status\txState=#UDP_TX_SENT : ProcedureReturn 0 : EndIf
  If status\txState=#UDP_TX_FAILED : ProcedureReturn status\txError : EndIf
 Wend
 ProcedureReturn -9201
EndProcedure
Procedure.i SendAck(h.i)
 Define i.i,n.i,rc.i,token.i,started.i,pn.i
 ; This fixture sends at most two copies, each under its own fresh PN.
 If sent>=2 : ProcedureReturn -9213 : EndIf
 pn=QuicHandshakeSentReserve(@history) : If pn<0 : ProcedureReturn pn : EndIf
 spec\kind=0 : spec\destination=?ServerId : spec\destinationBytes=4
 spec\source=?ClientId : spec\sourceBytes=8 : spec\number=pn : spec\numberBytes=4
 spec\cipherBytes=1174
 n=QuicLongPacketWrite(@spec,@output[0],1472) : If n<>26 : ProcedureReturn -9202 : EndIf
 For i=n To 1199 : output[i]=0 : Next
 rc=QuicHandshakeAckWrite(@ack,@output[n],1158,@token) : If rc<>5 : ProcedureReturn -9203 : EndIf
 rc=QuicCryptoTxFrame(@tx,0,3,@output[n+5],1153) : If rc<>6 : ProcedureReturn -9215 : EndIf
 rc=QuicPacketJobBegin(@sendJob,@writeKeys,@output[0],1200,0,pn,1)
 If rc<>0 : ProcedureReturn rc : EndIf
 started=clock()
 Repeat
  rc=Pump() : If rc<0 : ProcedureReturn rc : EndIf
  rc=QuicPacketJobStep(@sendJob)
  If clock()-started>3000000 : QuicPacketJobCancel(@sendJob) : ProcedureReturn -9204 : EndIf
 Until rc<>0
 If rc<>1 : ProcedureReturn rc : EndIf
 rc=UdpPayloadSendTo(h,@ep,@output[0],1200) : If rc<1 : ProcedureReturn rc : EndIf
 rc=QuicHandshakeSentCommit(@history,pn,1200,clock(),1,1,0) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicCryptoTxSent(@tx,0,3) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=WaitTx(h) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicHandshakeAckSent(@ack,token) : If rc<>1 : ProcedureReturn -9205 : EndIf
 sent=sent+1 : lastSend=clock() : ProcedureReturn 0
EndProcedure
Procedure.i Run(h.i)
 Define i.i,n.i,rc.i,started.i,part.i,header.QuicPacketHeader
 largest=-1
 rc=QuicCryptoRxInit(@rx,0,@data[0],4096,@bits[0],512) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicHandshakeAckInit(@ack,0,@ranges[0],64) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicHandshakeSentInit(@history,0,@historySlots[0],128) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicCryptoTxInit(@tx,0,@txData[0],4096,@txStates[0],1024) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicCryptoTxAppend(@tx,?Outgoing,3) : If rc<>3 : ProcedureReturn -9216 : EndIf
 rc=QuicInitialKeysBegin(@keyjob,@readKeys,?OriginalId,8,1)
 While rc=0 : pet() : rc=QuicKeyJobStep(@keyjob) : Wend
 If rc<>1 : ProcedureReturn rc : EndIf
 rc=QuicInitialKeysBegin(@keyjob,@writeKeys,?OriginalId,8,0)
 While rc=0 : pet() : rc=QuicKeyJobStep(@keyjob) : Wend
 If rc<>1 : ProcedureReturn rc : EndIf
 rc=UdpPayloadSendTo(h,@ep,?Hello,4) : If rc<1 : ProcedureReturn rc : EndIf
 rc=WaitTx(h) : If rc<>0 : ProcedureReturn rc : EndIf
 started=clock()
 While received<4 And clock()-started<8000000
  rc=Pump() : If rc<0 : ProcedureReturn rc : EndIf
  n=UdpPayloadReceive(h,@info,@packet[0],1472)
  If n<>#SVC_EAGAIN
   If n<>1200 Or info\family<>4 Or info\peerPort<>55442 : ProcedureReturn -9206 : EndIf
   For i=0 To 15 : If PeekA(@info\peerAddress+i)<>PeekA(@ep\address+i) : ProcedureReturn -9207 : EndIf : Next
   received=received+1
   rc=QuicPacketRead(@header,@packet[0],n,0)
   If rc<>1 Or header\kind<>0 Or header\destinationBytes<>8 Or header\sourceBytes<>4 Or header\tokenBytes<>0 : ProcedureReturn -9208 : EndIf
   For i=0 To 7 : If PeekA(@packet[0]+header\destinationOffset+i)<>PeekA(?ClientId+i) : ProcedureReturn -9209 : EndIf : Next
   For i=0 To 3 : If PeekA(@packet[0]+header\sourceOffset+i)<>PeekA(?ServerId+i) : ProcedureReturn -9210 : EndIf : Next
   rc=QuicHandshakeReceiveBegin(@receive,@readKeys,@packet[0],n,0,largest,@rx,@ack)
   If rc=0
    Repeat
     rc=Pump() : If rc<0 : ProcedureReturn rc : EndIf
     rc=QuicHandshakeReceiveStep(@receive)
     If rc=2
      rc=QuicHandshakeSentAckBegin(@ackJob,@history,receive\level,@receive\process\frame)
      If rc<>0 : ProcedureReturn rc : EndIf
      Repeat
       rc=Pump() : If rc<0 : ProcedureReturn rc : EndIf
       rc=QuicHandshakeSentAckStep(@ackJob)
       If rc=1
        ackEvents=ackEvents+1
        part=QuicCryptoTxAck(@tx,ackJob\cookie,3) : If part<>0 : ProcedureReturn part : EndIf
        part=QuicCryptoTxReclaim(@tx,4096) : If part<0 : ProcedureReturn part : EndIf
        reclaimed=reclaimed+part
       EndIf
       If clock()-started>=8000000 : QuicHandshakeSentAckCancel(@ackJob) : ProcedureReturn -9214 : EndIf
      Until rc<>0 And rc<>1
      If rc<>2 : QuicHandshakeReceiveReject(@receive) : ProcedureReturn rc : EndIf
      rc=QuicHandshakeReceiveAccept(@receive)
      If rc=0 : rc=1 : EndIf
     EndIf
     If clock()-started>=8000000 : QuicHandshakeReceiveCancel(@receive) : ProcedureReturn -9211 : EndIf
    Until rc<>1
   EndIf
   If receive\authenticated<>0 And receive\crypto\number>largest : largest=receive\crypto\number : EndIf
   If rc=6
    If receive\authenticated<>0 : duplicates=duplicates+1 : Else : badTags=badTags+1 : EndIf
   ElseIf rc=4
    completed=completed+1
    If ack\pending<>0 : rc=SendAck(h) : If rc<>0 : ProcedureReturn rc : EndIf : EndIf
   Else
    ProcedureReturn rc
   EndIf
  EndIf
  ; A fixed test timer deliberately exercises retry; not a recovery policy.
  If sent=1 And clock()-lastSend>300000 And history\acked=0
   rc=QuicHandshakeSentLost(@history,0) : If rc<>1 : ProcedureReturn -9217 : EndIf
   rc=QuicCryptoTxRetry(@tx,0,3) : If rc<>0 : ProcedureReturn rc : EndIf
   rc=SendAck(h) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
 Wend
 If received<>4 : ProcedureReturn -9212 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i Main()
 CaptureTable()
 Define i.i,rc.i,h.i,closed.i,cleanup.i
 rc=UdpPayloadBind(services) : If rc<>0 : ProcedureReturn 71 : EndIf
 pet=PeekI(services+16+6*8) : clock=PeekI(services+16+11*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 72 : EndIf
 MmuEnableCached()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$55445331) : PokeI($E1C00008,23)
 ep\family=4 : ep\kind=0 : ep\port=55442
 For i=0 To 15 : PokeA(@ep\address+i,PeekA(?Peer+i)) : Next
 h=UdpPayloadOpen(4,0,55013)
 If h>0 : rc=Run(h) : closed=UdpPayloadClose(h) : Else : rc=h : closed=-1 : EndIf
 If receive\phase=1 Or receive\phase=2 : cleanup=QuicHandshakeReceiveCancel(@receive) : EndIf
 If ackJob\phase=1 Or ackJob\phase=2 : cleanup=QuicHandshakeSentAckCancel(@ackJob) : EndIf
 If sendJob\phase<>0 : cleanup=QuicPacketJobCancel(@sendJob) : EndIf
 PokeI($E1C00100,rc) : PokeI($E1C00108,received) : PokeI($E1C00110,badTags)
 PokeI($E1C00118,duplicates) : PokeI($E1C00120,completed) : PokeI($E1C00128,sent)
 PokeI($E1C00130,rx\buffered) : PokeI($E1C00138,ack\count) : PokeI($E1C00140,ack\pending)
 PokeI($E1C00148,largest) : PokeI($E1C00150,data[0]) : PokeI($E1C00158,data[1]) : PokeI($E1C00160,data[2])
 PokeI($E1C00168,closed) : PokeI($E1C00170,GcmJobBusy())
 PokeI($E1C00178,history\issued) : PokeI($E1C00180,history\acked) : PokeI($E1C00188,history\inFlight)
 PokeI($E1C00190,history\largestAcked) : PokeI($E1C00198,ackEvents)
 PokeI($E1C001A0,tx\base) : PokeI($E1C001A8,tx\tail) : PokeI($E1C001B0,reclaimed)
 PokeI($E1C00040,maxService)
 QuicKeysWipe(@readKeys) : QuicKeysWipe(@writeKeys)
 MmuDisableCachedFlushed() : ProcedureReturn 0
EndProcedure
DataSection
OriginalId:
 Data.a $83,$94,$C8,$F0,$3E,$51,$57,$08
ClientId:
 Data.a 97,98,99,100,101,102,103,104
ServerId:
 Data.a 87,88,89,90
Hello:
 Data.a 81,72,48,49
Outgoing:
 Data.a 120,121,122
Peer:
 Data.a 192,168,1,104,0,0,0,0,0,0,0,0,0,0,0,0
EndDataSection
'''
 source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 todo=list(names)
 while todo:
  name=todo.pop()
  for dep in re.findall(r'^\s*XIncludeFile\s+"([^"]+)"',(root/name).read_text(encoding='utf8'),re.M):
   if dep not in names:names.append(dep);todo.append(dep)
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 labels=['result','received','bad tags','duplicates','completed','ACKs sent','queued bytes','ACK ranges','pending ACK','largest PN','byte a','byte b','byte c','socket close','crypto busy','issued','acknowledged','in flight','largest acknowledged','ACK events','TX base','TX tail','reclaimed']
 cases=[dict(name=n,expected=v) for n,v in zip(labels,[0,4,1,1,2,2,3,1,0,2,97,98,99,0,0,2,2,0,1,2,3,3,3])]
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
