; Shared ownership for a QUIC handshake connection and its mutable storage.
; Compose TLS, quic_tls_operation, packet/key/ACK jobs and parameter parsing.
; Owns resources/deadline/close and normal PTO rearming, not a full recovery
; dispatcher or HTTP/3 implementation.
; Caller transfers one open UDP handle on successful Begin. The 20 input spans
; are exclusive, disjoint and alive until CloseStep returns1. Extra capacity
; beyond BufferBytes is not owned or wiped. Immutable host/trust inputs remain
; borrowed. Serialized dispatcher only; no I/O or wait loops are hidden here.
; Child jobs use only this owner's storage. Start no work once closing begins,
; and honor the shared worker's crypto exclusion across suspended execution.
XIncludeFile "Anvil/Core/quic_application_packet.pbi"
XIncludeFile "Anvil/Network/quic_application_state.pbi"
XIncludeFile "Anvil/Network/quic_peer_ids.pbi"
#QUIC_CONNECTION_ARGUMENT=-3511
#QUIC_CONNECTION_TIMEOUT=-3512
#QUIC_CONNECTION_STATE=-3513
#QUIC_CONNECTION_IO=-3514
#QUIC_CONNECTION_BUFFERS=20
#QUIC_RECOVERY_PROBE=1
#QUIC_RECOVERY_LOSS=2
Structure QuicConnectionSpace
 level.i
 largest.i
 readKeys.QuicKeys
 writeKeys.QuicKeys
 rx.QuicCryptoRx
 tx.QuicCryptoTx
 ack.QuicHandshakeAck
 history.QuicHandshakeSent
 metadata.i
EndStructure
Structure QuicConnectionSend
 phase.i ; 0 fresh,1 scan,2 frame,3 encrypt,4 submit,5 transport,6 done,-1 failed
 result.i
 level.i
 peerBytes.i
 cursor.i
 found.i
 view.QuicCryptoSlice
 number.i
 token.i
 copied.i
 bytes.i
 encryptStarted.i
 cryptoResult.i
 worker.TlsWorkerJob
EndStructure
Structure QuicConnectionAck
 phase.i ; 0 fresh,1 ledger,2 mark bytes,3 reclaim,4 accept,5 done,-1 failed
 result.i
 level.i
 offset.i
 remaining.i
 events.i
 rttSample.i
EndStructure
Structure QuicConnectionReceive
 phase.i ; 0 fresh,1 admission,2 crypto,3 frames,4 done,6 drop,-1 failed
 result.i
 level.i
 packet.i
 bytes.i
 sourceOffset.i
 sourceBytes.i
 receivedAt.i ; -1 means no timestamp supplied
 worker.TlsWorkerJob
EndStructure
Structure QuicConnectionTls
 phase.i ; 0 fresh,1..11 dispatch,12 complete,-1 failed
 result.i
 level.i
 peerBytes.i
 timeout.i
 keyTarget.i
 parametersReady.i
EndStructure
Structure QuicConnectionStart
 phase.i ; 0 fresh,1..8 dispatch,9 complete,-1 failed
 result.i
 timeout.i
 keyTarget.i
EndStructure
Structure QuicConnection
 phase.i ; 0 fresh,1 active,2 closing,3 closed
 result.i
 socket.i
 started.i
 timeout.i
 closeStage.i
 wipeIndex.i
 wipeOffset.i
 buffers.i[20]
 initial.QuicConnectionSpace
 handshake.QuicConnectionSpace
 keyjob.QuicKeyJob
 receive.QuicHandshakeReceive
 sendJob.QuicPacketJob
 ackJob.QuicHandshakeSentAck
 tlsOutput.QuicTlsOutput
 appRead.QuicKeys
 appWrite.QuicKeys
 params.QuicParameters
 spec.QuicLongPacketSpec
 header.QuicPacketHeader
 tlsOp.QuicTlsOperation
 outgoing.QuicConnectionSend
 initialRetired.i
 handshakeConfirmed.i
 acknowledge.QuicConnectionAck
 incoming.QuicConnectionReceive
 feed.QuicConnectionTls
 peerIdKnown.i
 peerIdBytes.i
 startup.QuicConnectionStart
 application.QuicApplicationPacket
 applicationState.QuicApplicationState
 peerIds.QuicPeerIds
 peerIdRecords.i[72]
 controlPhase.i ; 0 fresh,1 encrypt,2 submit,3 transport,4 complete,-1 failed
 controlBytes.i
 controlNumber.i
 controlToken.i
 controlHasAck.i
 controlEliciting.i
 applicationHistory.QuicHandshakeSent
 applicationAck.QuicHandshakeSentAck
 applicationSent.i[512]
 recoveryRtt.QuicRtt
 recoveryTimer.QuicProbeTimer
 recoveryLoss.QuicHandshakeSentLoss
 recoveryLevel.i
 recoveryRetryOffset.i
 recoveryRetryRemaining.i
 recoveryRetryLevel.i
EndStructure
; Span table order: RX data/bits,TX data/bits,ACK ranges,sent slots/metadata,
; TLS snapshot,handshake/receive/output/config,local/peer parameters/entries,
; input/output datagrams,original/client/peer connection IDs.
Procedure.i QuicConnectionBufferBytes(index.i)
 Select index
  Case 0 : ProcedureReturn 65536
  Case 1 : ProcedureReturn 8192
  Case 2 : ProcedureReturn 8192
  Case 5 : ProcedureReturn 8192
  Case 3 : ProcedureReturn 2048
  Case 4 : ProcedureReturn 2048
  Case 10 : ProcedureReturn 2048
  Case 14 : ProcedureReturn 2048
  Case 6 : ProcedureReturn 4096
  Case 13 : ProcedureReturn 4096
  Case 7 : ProcedureReturn #TLS13_CONTEXT_SIZE
  Case 8 : ProcedureReturn 32768
  Case 9 : ProcedureReturn 16645
  Case 11 : ProcedureReturn 48
  Case 12 : ProcedureReturn 128
  Case 15 : ProcedureReturn 1472
  Case 16 : ProcedureReturn 1472
  Case 17 : ProcedureReturn 8
  Case 18 : ProcedureReturn 8
  Case 19 : ProcedureReturn 20
 EndSelect
 ProcedureReturn 0
EndProcedure
Procedure.i qconn_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i qconn_Overlap(a.i,n.i,b.i,m.i)
 ProcedureReturn Bool(a<b+m And b<a+n)
EndProcedure
Procedure.i QuicConnectionBuffer(*c.QuicConnection,index.i)
 If qconn_Span(*c,SizeOf(QuicConnection))=0 Or index<0 Or index>=#QUIC_CONNECTION_BUFFERS : ProcedureReturn 0 : EndIf
 ProcedureReturn PeekI(@*c\buffers+index*8)
EndProcedure
Procedure.i qconn_Space(*c.QuicConnection,*s.QuicConnectionSpace,level.i,slot.i)
 Define rc.i
 *s\level=level : *s\largest=-1 : *s\metadata=QuicConnectionBuffer(*c,6)+slot*2048
 rc=QuicCryptoRxInit(@*s\rx,level,QuicConnectionBuffer(*c,0)+slot*32768,32768,QuicConnectionBuffer(*c,1)+slot*4096,4096) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicCryptoTxInit(@*s\tx,level,QuicConnectionBuffer(*c,2)+slot*4096,4096,QuicConnectionBuffer(*c,3)+slot*1024,1024) : If rc<>0 : ProcedureReturn rc : EndIf
 rc=QuicHandshakeAckInit(@*s\ack,level,QuicConnectionBuffer(*c,4)+slot*1024,64) : If rc<>0 : ProcedureReturn rc : EndIf
 ProcedureReturn QuicHandshakeSentInit(@*s\history,level,QuicConnectionBuffer(*c,5)+slot*4096,128)
EndProcedure
; spans points to 20 (address,capacity) pairs. All validation precedes mutation.
; The table is copied, not retained; it must not alias the descriptor or spans.
; Child initialization failure leaves closing resources, but does not adopt UDP.
Procedure.i QuicConnectionBegin(*c.QuicConnection,spans.i,socket.i,now.i,timeoutUs.i)
 Define i.i,j.i,p.i,n.i,other.i,m.i,rc.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 Or qconn_Span(spans,320)=0 Or socket<=0 Or now<0 Or timeoutUs<=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>0 And *c\phase<>3 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If qconn_Overlap(*c,SizeOf(QuicConnection),spans,320) : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 For i=0 To 19
  p=PeekI(spans+i*16) : n=QuicConnectionBufferBytes(i)
  If PeekI(spans+i*16+8)<n Or qconn_Span(p,n)=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
  If qconn_Overlap(p,n,*c,SizeOf(QuicConnection)) Or qconn_Overlap(p,n,spans,320) : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
  For j=0 To i-1
   other=PeekI(spans+j*16) : m=QuicConnectionBufferBytes(j)
   If qconn_Overlap(p,n,other,m) : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
  Next
 Next
 For i=0 To SizeOf(QuicConnection)-1 : PokeA(*c+i,0) : Next
 For i=0 To 19 : PokeI(@*c\buffers+i*8,PeekI(spans+i*16)) : Next
 *c\phase=1 : *c\started=now : *c\timeout=timeoutUs
 rc=qconn_Space(*c,@*c\initial,0,0)
 If rc=0 : rc=qconn_Space(*c,@*c\handshake,2,1) : EndIf
 If rc=0 : rc=QuicApplicationStateInit(@*c\applicationState) : EndIf
 If rc=0 : rc=QuicHandshakeSentInit(@*c\applicationHistory,4,@*c\applicationSent,128) : EndIf
 If rc=0 : rc=QuicRttInit(@*c\recoveryRtt,333000,1000) : EndIf
 If rc=0 : rc=QuicProbeTimerInit(@*c\recoveryTimer) : EndIf
 If rc<>0 : *c\phase=2 : *c\result=rc : ProcedureReturn rc : EndIf
 *c\socket=socket
 ProcedureReturn 0
EndProcedure
; Connection-owned recovery operations. Caller still supplies scheduling policy
; and consumes each loss event before Step. Recovery cannot run during close.
; Rearm normal PTO from owned, usable spaces. resetBackoff is supplied only
; after fresh validated ACKs or packet-space retirement. No-flight client
; anti-deadlock policy and time-threshold loss priority remain dispatch duties.
; Refusals preserve the old timer, including its backoff. All clocks are us.
Procedure.i QuicConnectionRecoveryRearm(*c.QuicConnection,resetBackoff.i)
 Define initial.i,handshake.i,application.i,delay.i,rc.i,i.i,*parameter.QuicParameter
 Define candidate.QuicProbeTimer
 If qconn_Span(*c,SizeOf(QuicConnection))=0 Or resetBackoff<0 Or resetBackoff>1 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 initial=-1 : handshake=-1 : application=-1 : delay=25000
 If *c\initial\history\phase=1 And *c\initial\writeKeys\ready=1
  initial=QuicHandshakeSentProbeTime(@*c\initial\history) : If initial< -1 : ProcedureReturn initial : EndIf
 EndIf
 If *c\handshake\history\phase=1 And *c\handshake\writeKeys\ready=1
  handshake=QuicHandshakeSentProbeTime(@*c\handshake\history) : If handshake< -1 : ProcedureReturn handshake : EndIf
 EndIf
 If *c\handshakeConfirmed=1 And *c\appWrite\ready=1
  application=QuicHandshakeSentProbeTime(@*c\applicationHistory) : If application< -1 : ProcedureReturn application : EndIf
  If *c\feed\parametersReady<>1 Or *c\params\phase<>0 Or *c\params\result<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
  *parameter=QuicParametersFind(@*c\params,11)
  If *parameter
   If *parameter\value<0 Or *parameter\value>=16384 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
   delay=*parameter\value*1000
  EndIf
 EndIf
 For i=0 To SizeOf(QuicProbeTimer)-1 : PokeA(@candidate+i,PeekA(@*c\recoveryTimer+i)) : Next
 If resetBackoff : candidate\backoff=0 : EndIf
 rc=QuicProbeTimerArm(@candidate,@*c\recoveryRtt,*c\handshakeConfirmed,delay,initial,handshake,application)
 If rc<0 : ProcedureReturn rc : EndIf
 For i=0 To SizeOf(QuicProbeTimer)-1 : PokeA(@*c\recoveryTimer+i,PeekA(@candidate+i)) : Next
 ProcedureReturn rc
EndProcedure
; 0 idle,1 probe,2 run a bounded loss scan; recoveryLevel is valid on1/2.
; A stale scan requests work immediately. Any pending loss deadline suppresses
; PTO even when the stored PTO candidate is earlier. Poll never declares loss.
; After2, use current RTT loss delay/threshold3, consume each scan event, then
; poll again. Requests repeat until serviced; only a PTO advances backoff.
Procedure.i QuicConnectionRecoveryPoll(*c.QuicConnection,now.i)
 Define delay.i,level.i,history.i,stamp.i,unknown.i,selected.i,best.i,rc.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 Or now<0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\recoveryRetryRemaining<>0 Or *c\initial\history\busy<>0 Or *c\handshake\history\busy<>0 Or *c\applicationHistory\busy<>0 : ProcedureReturn #QUIC_SENT_BUSY : EndIf
 delay=QuicRttLossDelay(@*c\recoveryRtt) : If delay<0 : ProcedureReturn delay : EndIf
 unknown=-1 : selected=-1 : best=$7FFFFFFFFFFFFFFF
 For level=0 To 4 Step 2
  history=0
  Select level
   Case 0
    If *c\initial\history\phase=1 And *c\initial\writeKeys\ready=1 : history=@*c\initial\history : EndIf
   Case 2
    If *c\handshake\history\phase=1 And *c\handshake\writeKeys\ready=1 : history=@*c\handshake\history : EndIf
   Case 4
    If *c\applicationHistory\phase=1 And *c\appWrite\ready=1 : history=@*c\applicationHistory : EndIf
  EndSelect
  If history<>0
   stamp=QuicHandshakeSentLossTime(history,delay,3)
   If stamp< -1 : ProcedureReturn stamp : EndIf
   If stamp=-1
    If unknown=-1 : unknown=level : EndIf
   ElseIf stamp>0
    If selected=-1 Or stamp<best : selected=level : best=stamp : EndIf
   EndIf
  EndIf
 Next
 If unknown>=0 : *c\recoveryLevel=unknown : ProcedureReturn #QUIC_RECOVERY_LOSS : EndIf
 If selected>=0
  If now>=best : *c\recoveryLevel=selected : ProcedureReturn #QUIC_RECOVERY_LOSS : EndIf
  ProcedureReturn 0
 EndIf
 rc=QuicProbeTimerPoll(@*c\recoveryTimer,now)
 If rc=1 : *c\recoveryLevel=*c\recoveryTimer\level : EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i qconn_LossOwned(*c.QuicConnection)
 ProcedureReturn Bool(*c\recoveryLoss\owner=@*c\initial\history Or *c\recoveryLoss\owner=@*c\handshake\history Or *c\recoveryLoss\owner=@*c\applicationHistory)
EndProcedure
Procedure.i QuicConnectionLossBegin(*c.QuicConnection,level.i,now.i,delay.i,threshold.i)
 Define history.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 Or *c\recoveryRetryRemaining<>0 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\controlPhase>=1 And *c\controlPhase<=3 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\outgoing\phase<>0 And *c\outgoing\phase<>6 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 Select level
  Case 0 : history=@*c\initial\history
  Case 2 : history=@*c\handshake\history
  Case 4 : history=@*c\applicationHistory
  Default : ProcedureReturn #QUIC_CONNECTION_ARGUMENT
 EndSelect
 ProcedureReturn QuicHandshakeSentLossBegin(@*c\recoveryLoss,history,now,delay,threshold)
EndProcedure
; Handshake loss retries retained CRYPTO in <=256-byte steps before exposing
; the loss event. ACKed/reclaimed bytes remain retired. Application events
; still require their own frame owner. Keep the scan active until DONE/close.
Procedure.i QuicConnectionLossStep(*c.QuicConnection)
 Define rc.i,n.i,p.i,offset.i,bytes.i,*s.QuicConnectionSpace
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 Or qconn_LossOwned(*c)=0 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\recoveryRetryRemaining>0
  If *c\recoveryLoss\phase<>1 : QuicConnectionClose(*c,#QUIC_CONNECTION_STATE) : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
  If *c\recoveryRetryLevel=0 : *s=@*c\initial : Else : *s=@*c\handshake : EndIf
  n=*c\recoveryRetryRemaining : If n>256 : n=256 : EndIf
  rc=QuicCryptoTxRetry(@*s\tx,*c\recoveryRetryOffset,n)
  If rc<0 : QuicConnectionClose(*c,rc) : ProcedureReturn rc : EndIf
  *c\recoveryRetryOffset=*c\recoveryRetryOffset+n : *c\recoveryRetryRemaining=*c\recoveryRetryRemaining-n
  If *c\recoveryRetryRemaining>0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
 EndIf
 rc=QuicHandshakeSentLossStep(@*c\recoveryLoss)
 If rc=1 And *c\recoveryLoss\owner<>@*c\applicationHistory
  If *c\recoveryLoss\owner=@*c\initial\history : *s=@*c\initial : Else : *s=@*c\handshake : EndIf
  p=*s\metadata+(*c\recoveryLoss\number % *s\history\capacity)*16
  If qconn_Span(p,16)=0 Or *c\recoveryLoss\cookie<>p
   QuicConnectionClose(*c,#QUIC_CONNECTION_STATE) : ProcedureReturn #QUIC_CONNECTION_STATE
  EndIf
  offset=PeekI(p) : bytes=PeekI(p+8)
  If offset<0 Or bytes<0 Or bytes>16384 Or offset>#QUIC_INTEGER_MAX-bytes
   QuicConnectionClose(*c,#QUIC_CONNECTION_STATE) : ProcedureReturn #QUIC_CONNECTION_STATE
  EndIf
  If bytes>0
   *c\recoveryRetryOffset=offset : *c\recoveryRetryRemaining=bytes : *c\recoveryRetryLevel=*s\level
   ProcedureReturn 0
  EndIf
 EndIf
 If rc=2
  n=QuicConnectionRecoveryRearm(*c,0) : If n<0 : ProcedureReturn n : EndIf
 EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i QuicConnectionClose(*c.QuicConnection,reason.i)
 Define rc.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase=3 : ProcedureReturn 1 : EndIf
 If *c\phase=2 : ProcedureReturn 0 : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\recoveryTimer\phase=1
  rc=QuicProbeTimerDiscard(@*c\recoveryTimer) : If rc<>0 : ProcedureReturn rc : EndIf
 EndIf
 *c\phase=2 : *c\result=reason : *c\closeStage=0
 ProcedureReturn 0
EndProcedure
; An overall deadline, independent of each TLS operation's budget. The caller
; checks this from its dispatcher even when waiting for packets or crypto.
Procedure.i QuicConnectionCheckDeadline(*c.QuicConnection,now.i)
 Define rc.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 Or now<0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\timeout>0 And now-*c\started>=*c\timeout
  rc=QuicConnectionClose(*c,#QUIC_CONNECTION_TIMEOUT)
  ProcedureReturn #QUIC_CONNECTION_TIMEOUT
 EndIf
 ProcedureReturn 0
EndProcedure
; Clear only after the protocol owner has verified handshake confirmation.
; TLS Finished alone is not QUIC HANDSHAKE_DONE. No such claim is made here.
Procedure.i QuicConnectionClearDeadline(*c.QuicConnection)
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 *c\timeout=0 : ProcedureReturn 0
EndProcedure
; Initialize after authenticated TLS parameters. limit MUST equal our advertised
; active_connection_id_limit (not the peer's). Eight storage slots include
; pending retirement obligations; exhausted storage is an explicit local error.
Procedure.i QuicConnectionPeerIdsInit(*c.QuicConnection,limit.i)
 Define token.i,*e.QuicParameter
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 Or *c\feed\parametersReady<>1 Or *c\peerIdKnown<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If TlsWorkerBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If Tls13ContextState(QuicConnectionBuffer(*c,7),#TLS13_CONTEXT_SIZE)<>#TLS13_ST_CONNECTED : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 *e=QuicParametersFind(@*c\params,2)
 If *e<>0 : token=*c\params\source+*e\offset : EndIf
 ProcedureReturn QuicPeerIdsInit(@*c\peerIds,@*c\peerIdRecords,8,limit,QuicConnectionBuffer(*c,19),*c\peerIdBytes,token)
EndProcedure
; Apply a decoded NEW_CONNECTION_ID from the current authenticated packet.
; Caller serializes transport output; no outstanding ciphertext may use a CID
; being retired. Does not send RETIRE_CONNECTION_ID or ACK the received packet.
Procedure.i QuicConnectionPeerIdAdd(*c.QuicConnection,sequence.i,retire.i,id.i,bytes.i,token.i)
 Define rc.i,p.i,dst.i,i.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\controlPhase>=1 And *c\controlPhase<=3 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\phase<>1 Or *c\application\phase<>2 Or *c\application\result<>1 Or *c\application\encrypt<>0 Or *c\application\keys<>@*c\appRead : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If TlsWorkerBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If *c\outgoing\phase<>0 And *c\outgoing\phase<>6 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 rc=QuicPeerIdsAdd(@*c\peerIds,sequence,retire,id,bytes,token)
 If rc<0 : ProcedureReturn rc : EndIf
 p=QuicPeerIdsFind(@*c\peerIds,*c\peerIds\selected)
 dst=QuicConnectionBuffer(*c,19) : *c\peerIdBytes=PeekI(p+8)
 For i=0 To 19 : PokeA(dst+i,0) : Next
 For i=0 To *c\peerIdBytes-1 : PokeA(dst+i,PeekA(p+32+i)) : Next
 ProcedureReturn rc
EndProcedure
; Client-side HANDSHAKE_DONE effect. Caller has decoded this frame from the
; current authenticated application packet; syntax alone never authenticates it.
; Does not accept/ACK other frames in that packet. Serialized dispatch only.
; 1 applied/already confirmed,negative unchanged refusal. Retires Handshake
; protection, retransmission state and persistent TLS handshake secrets together.
Procedure.i QuicConnectionHandshakeDone(*c.QuicConnection)
 Define snapshot.i,selected.i,rc.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\application\phase<>2 Or *c\application\result<>1 Or *c\application\encrypt<>0 Or *c\application\keys<>@*c\appRead : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\handshakeConfirmed=1 : ProcedureReturn 1 : EndIf
 If TlsWorkerBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If *c\startup\phase<>9 Or *c\feed\phase<>12 Or *c\tlsOp\phase<>2 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\incoming\phase<>0 And *c\incoming\phase<>4 And *c\incoming\phase<>6 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\outgoing\phase<>0 And *c\outgoing\phase<>6 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\acknowledge\phase<>0 And *c\acknowledge\phase<>5 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\initialRetired<>1 Or *c\appRead\ready<>1 Or *c\appWrite\ready<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\handshake\history\phase<>1 Or *c\handshake\history\busy<>0 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\handshake\rx\phase<>1 And *c\handshake\rx\phase<>2 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If *c\handshake\tx\phase<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 snapshot=QuicConnectionBuffer(*c,7)
 If Tls13ContextState(snapshot,#TLS13_CONTEXT_SIZE)<>#TLS13_ST_CONNECTED : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If Tls13ContextMatchesBuffers(snapshot,#TLS13_CONTEXT_SIZE,QuicConnectionBuffer(*c,8),QuicConnectionBuffer(*c,9),QuicConnectionBuffer(*c,11))<>1 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 selected=Bool(TlsHsAddr=QuicConnectionBuffer(*c,8) And TlsRecvAddr=QuicConnectionBuffer(*c,9) And TlsQuicConfig=QuicConnectionBuffer(*c,11))
 If selected And Tls13State<>#TLS13_ST_CONNECTED : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 ; All operations below have validated ownership/state and cannot refuse under
 ; the serialized-dispatch contract. No pending transport output is discarded.
 rc=Tls13ContextRetireHandshakeSecrets(snapshot,#TLS13_CONTEXT_SIZE)
 If selected : rc=Tls13ContextRestore(snapshot,#TLS13_CONTEXT_SIZE) : EndIf
 QuicKeysWipe(@*c\handshake\readKeys) : QuicKeysWipe(@*c\handshake\writeKeys)
 rc=QuicHandshakeSentDiscard(@*c\handshake\history)
 rc=QuicCryptoTlsAbandon(@*c\handshake\rx)
 rc=QuicCryptoTxAbandon(@*c\handshake\tx)
 *c\handshakeConfirmed=1 : *c\timeout=0
 rc=QuicConnectionRecoveryRearm(*c,1) : If rc<0 : ProcedureReturn rc : EndIf
 ProcedureReturn 1
EndProcedure
; CloseStep returns2 until the dispatcher closes exactly this UDP handle.
; Confirm only a successful real close. I/O failure retains socket ownership.
Procedure.i QuicConnectionSocketClosed(*c.QuicConnection,socket.i,result.i)
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase<>2 Or *c\closeStage<>2 Or socket<=0 Or socket<>*c\socket : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 If result<>0 : ProcedureReturn #QUIC_CONNECTION_IO : EndIf
 *c\socket=0 : ProcedureReturn 0
EndProcedure
; 0 pending,1 closed,2 needs UDP close,negative refusal/fault. Never release
; storage before1. Only owned jobs are cancelled; no global crypto wipe occurs.
; Buffer erasure is at most4096 bytes/call plus fixed-size descriptor cleanup.
Procedure.i QuicConnectionCloseStep(*c.QuicConnection)
 Define rc.i,i.i,n.i,p.i,budget.i,reason.i
 If qconn_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONNECTION_ARGUMENT : EndIf
 If *c\phase=3 : ProcedureReturn 1 : EndIf
 If *c\phase<>2 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
 ; Another suspended TLS operation retains shared arithmetic scratch. Defer
 ; cleanup instead of allowing a packet cancellation to reset its GCM job.
 If TlsWorkerBusy()<>0 And TlsWorkerOwns(@*c\tlsOp\context\worker)=0 And TlsWorkerOwns(@*c\outgoing\worker)=0 And TlsWorkerOwns(@*c\incoming\worker)=0 And TlsWorkerOwns(@*c\application\worker)=0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 If *c\closeStage=0
  If *c\recoveryLoss\phase=1
   If qconn_LossOwned(*c)=0 : ProcedureReturn #QUIC_CONNECTION_STATE : EndIf
   rc=QuicHandshakeSentLossCancel(@*c\recoveryLoss)
   If rc<>#QUIC_SENT_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\applicationAck\phase=1 Or *c\applicationAck\phase=2
   rc=QuicHandshakeSentAckCancel(@*c\applicationAck)
   If rc<>#QUIC_SENT_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\applicationHistory\phase=1
   rc=QuicHandshakeSentDiscard(@*c\applicationHistory) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If *c\application\phase=1
   rc=QuicApplicationPacketCancel(@*c\application)
   If rc<>#QUIC_APP_PACKET_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\tlsOp\phase=1
   rc=QuicTlsOperationCancel(@*c\tlsOp)
   If rc<>#QUIC_OP_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\outgoing\worker\phase=1
   rc=TlsWorkerCancel(@*c\outgoing\worker)
   If rc<>1 : ProcedureReturn rc : EndIf
  EndIf
  If *c\incoming\worker\phase=1
   rc=TlsWorkerCancel(@*c\incoming\worker)
   If rc<>1 : ProcedureReturn rc : EndIf
  EndIf
  If *c\ackJob\phase=1 Or *c\ackJob\phase=2
   rc=QuicHandshakeSentAckCancel(@*c\ackJob)
   If rc<>#QUIC_SENT_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\receive\phase=1 Or *c\receive\phase=2
   rc=QuicHandshakeReceiveCancel(@*c\receive)
   If rc<>#QUIC_CRYPTO_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\receive\crypto\phase<>0
   rc=QuicPacketJobCancel(@*c\receive\crypto)
   If rc<>#QUIC_CRYPTO_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\sendJob\phase<>0
   rc=QuicPacketJobCancel(@*c\sendJob)
   If rc<>#QUIC_CRYPTO_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  QuicKeyJobCancel(@*c\keyjob)
  If *c\tlsOutput\phase=1 Or *c\tlsOutput\phase=3
   rc=QuicTlsOutputAbandon(@*c\tlsOutput) : If rc<>#QUIC_OUTPUT_CANCELLED : ProcedureReturn rc : EndIf
  EndIf
  If *c\initial\rx\phase<>0
   rc=QuicCryptoTlsAbandon(@*c\initial\rx) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If *c\handshake\rx\phase<>0
   rc=QuicCryptoTlsAbandon(@*c\handshake\rx) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If *c\initial\tx\phase<>0
   rc=QuicCryptoTxAbandon(@*c\initial\tx) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If *c\handshake\tx\phase<>0
   rc=QuicCryptoTxAbandon(@*c\handshake\tx) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If *c\initial\history\phase=1
   rc=QuicHandshakeSentDiscard(@*c\initial\history) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  If *c\handshake\history\phase=1
   rc=QuicHandshakeSentDiscard(@*c\handshake\history) : If rc<>0 : ProcedureReturn rc : EndIf
  EndIf
  QuicKeysWipe(@*c\initial\readKeys) : QuicKeysWipe(@*c\initial\writeKeys)
  QuicKeysWipe(@*c\handshake\readKeys) : QuicKeysWipe(@*c\handshake\writeKeys)
  QuicKeysWipe(@*c\appRead) : QuicKeysWipe(@*c\appWrite)
  *c\closeStage=1 : ProcedureReturn 0
 EndIf
 If *c\closeStage=1
  rc=Tls13ContextWipe(QuicConnectionBuffer(*c,7),#TLS13_CONTEXT_SIZE)
  ; Clear working secrets only if this connection is currently selected.
  ; Another selected connection's metadata and crypto scratch stay untouched.
  If TlsHsAddr=QuicConnectionBuffer(*c,8) And TlsRecvAddr=QuicConnectionBuffer(*c,9)
   rc=Tls13ContextRestore(QuicConnectionBuffer(*c,7),#TLS13_CONTEXT_SIZE)
  EndIf
  *c\closeStage=2 : ProcedureReturn 0
 EndIf
 If *c\closeStage=2
  If *c\socket<>0 : ProcedureReturn 2 : EndIf
  *c\closeStage=3
 EndIf
 budget=4096
 While budget>0 And *c\wipeIndex<20
  n=QuicConnectionBufferBytes(*c\wipeIndex)-*c\wipeOffset
  If n>budget : n=budget : EndIf
  p=QuicConnectionBuffer(*c,*c\wipeIndex)+*c\wipeOffset
  For i=0 To n-1 : PokeA(p+i,0) : Next
  *c\wipeOffset=*c\wipeOffset+n : budget=budget-n
  If *c\wipeOffset=QuicConnectionBufferBytes(*c\wipeIndex) : *c\wipeIndex=*c\wipeIndex+1 : *c\wipeOffset=0 : EndIf
 Wend
 If *c\wipeIndex<20 : ProcedureReturn 0 : EndIf
 reason=*c\result
 For i=0 To SizeOf(QuicConnection)-1 : PokeA(*c+i,0) : Next
 *c\phase=3 : *c\result=reason
 ProcedureReturn 1
EndProcedure
