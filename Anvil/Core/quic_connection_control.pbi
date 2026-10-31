; Shared cooperative application ACK output, optionally with PING.
; Include quic_connection first. Caller drives transport and serializes all
; application crypto against this operation, including raw application APIs.
; Uses owned output buffer16; bytes are immutable from Step=2 through Completed.
; No I/O, ACK scheduling, recovery timer or congestion policy is hidden here.
#QUIC_CONTROL_ARGUMENT=-3611
#QUIC_CONTROL_STATE=-3612
Procedure.i quicco_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicco_Fail(*c.QuicConnection,reason.i)
 Define rc.i
 *c\controlPhase=-1 : rc=QuicConnectionClose(*c,reason)
 ProcedureReturn reason
EndProcedure
; 0 admitted,negative refusal/failure. PN reservation is irreversible, including
; failures after reservation. Exponent is OUR advertised ACK-delay exponent.
Procedure.i QuicConnectionControlBegin(*c.QuicConnection,now.i,exponent.i,ping.i)
 Define p.i,header.i,n.i,number.i,token.i,rc.i,i.i
 If quicco_Span(*c,SizeOf(QuicConnection))=0 Or ping<0 Or ping>1 : ProcedureReturn #QUIC_CONTROL_ARGUMENT : EndIf
 If *c\phase<>1 Or (*c\controlPhase<>0 And *c\controlPhase<>4) : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\application\phase=1 Or *c\appWrite\ready<>1 Or *c\peerIdKnown<>1 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\outgoing\phase<>0 And *c\outgoing\phase<>6 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\incoming\phase>=1 And *c\incoming\phase<=3 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\feed\phase>=1 And *c\feed\phase<=11 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\acknowledge\phase>=1 And *c\acknowledge\phase<=4 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\peerIdBytes<0 Or *c\peerIdBytes>20 Or *c\applicationState\ack\pending<>1 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If TlsWorkerBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 rc=QuicApplicationAckDelay(@*c\applicationState,now,exponent) : If rc<0 : ProcedureReturn rc : EndIf
 If *c\applicationHistory\busy<>0 Or *c\applicationHistory\issued<>*c\applicationState\nextNumber : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\applicationHistory\issued-*c\applicationHistory\first>=*c\applicationHistory\capacity : ProcedureReturn #QUIC_SENT_LIMIT : EndIf
 number=QuicApplicationNumberReserve(@*c\applicationState) : If number<0 : ProcedureReturn number : EndIf
 rc=QuicHandshakeSentReserve(@*c\applicationHistory)
 If rc<>number : ProcedureReturn quicco_Fail(*c,#QUIC_CONTROL_STATE) : EndIf
 p=QuicConnectionBuffer(*c,16) : header=1+*c\peerIdBytes+4
 n=QuicApplicationAckWrite(@*c\applicationState,p+header,1472-header-16-ping,@token,now,exponent)
 If n<0 : ProcedureReturn quicco_Fail(*c,n) : EndIf
 PokeA(p,$43)
 For i=0 To *c\peerIdBytes-1 : PokeA(p+1+i,PeekA(QuicConnectionBuffer(*c,19)+i)) : Next
 NetWriteBE32(p+1+*c\peerIdBytes,number & $FFFFFFFF)
 If ping : PokeA(p+header+n,1) : EndIf
 *c\controlBytes=header+n+ping+16 : *c\controlNumber=number : *c\controlToken=token
 rc=QuicApplicationPacketBegin(@*c\application,@*c\appWrite,p,*c\controlBytes,*c\peerIdBytes,number,1)
 If rc<>0 : ProcedureReturn quicco_Fail(*c,rc) : EndIf
 *c\controlEliciting=ping : *c\controlPhase=1 : ProcedureReturn 0
EndProcedure
; 0 computing,2 immutable ciphertext ready,3 awaiting actual transport result,
; 1 complete,negative failure. Dispatcher can service other work between steps.
Procedure.i QuicConnectionControlStep(*c.QuicConnection)
 Define rc.i
 If quicco_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONTROL_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If *c\controlPhase=4 : ProcedureReturn 1 : EndIf
 If *c\controlPhase=2 Or *c\controlPhase=3 : ProcedureReturn *c\controlPhase : EndIf
 If *c\controlPhase<>1 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 rc=QuicApplicationPacketStep(@*c\application)
 If rc=0 : ProcedureReturn 0 : EndIf
 If rc<>1 : ProcedureReturn quicco_Fail(*c,rc) : EndIf
 *c\controlPhase=2 : ProcedureReturn 2
EndProcedure
; Call only when transport ACCEPTED these exact bytes, never on EAGAIN.
Procedure.i QuicConnectionControlAccepted(*c.QuicConnection,now.i)
 Define rc.i
 If quicco_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONTROL_ARGUMENT : EndIf
 If *c\phase<>1 Or *c\controlPhase<>2 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 rc=QuicHandshakeSentCommit(@*c\applicationHistory,*c\controlNumber,*c\controlBytes,now,*c\controlEliciting,0,0)
 If rc<>0 : ProcedureReturn quicco_Fail(*c,rc) : EndIf
 *c\controlPhase=3 : ProcedureReturn 0
EndProcedure
; result=0 means actual successful transmission, not mere queue acceptance.
; A stale ACK token leaves newer ACK demand pending. Failure closes ownership;
; CloseStep handles cancellation/socket closure before releasing buffers.
Procedure.i QuicConnectionControlCompleted(*c.QuicConnection,result.i)
 Define rc.i
 If quicco_Span(*c,SizeOf(QuicConnection))=0 : ProcedureReturn #QUIC_CONTROL_ARGUMENT : EndIf
 If *c\phase<>1 Or *c\controlPhase<>3 : ProcedureReturn #QUIC_CONTROL_STATE : EndIf
 If result>0 : ProcedureReturn #QUIC_CONTROL_ARGUMENT : EndIf
 If result<0 : ProcedureReturn quicco_Fail(*c,result) : EndIf
 rc=QuicPacketAckSent(@*c\applicationState\ack,*c\controlToken)
 If rc<0 : ProcedureReturn quicco_Fail(*c,rc) : EndIf
 *c\controlPhase=4 : ProcedureReturn 1
EndProcedure
