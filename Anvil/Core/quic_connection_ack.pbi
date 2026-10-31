; Shared bounded application of an authenticated handshake ACK event.
; Include quic_connection first. The packet, ledger and stream remain borrowed
; and immutable to other dispatch work until done. No I/O, crypto or waits.
; Applies sent history/CRYPTO ACKs and rearms PTO; RTT/loss/ECN remain external.
; Initial packet protection is not certificate identity; TLS validates the peer.
#QUIC_CONNECTION_ACK_STATE=-3531
#QUIC_CONNECTION_ACK_ARGUMENT=-3532
#QUIC_CONNECTION_ACK_METADATA=-3533
Procedure.i quicca_Valid(*c.QuicConnection)
 ProcedureReturn Bool(*c>0 And *c<=$7FFFFFFFFFFFFFFF-SizeOf(QuicConnection))
EndProcedure
Procedure.i quicca_Space(*c.QuicConnection)
 If *c\acknowledge\level=0 : ProcedureReturn @*c\initial : EndIf
 ProcedureReturn @*c\handshake
EndProcedure
Procedure.i quicca_Fail(*c.QuicConnection,reason.i)
 Define rc.i
 *c\acknowledge\phase=-1 : *c\acknowledge\result=reason
 rc=QuicConnectionClose(*c,reason)
 ProcedureReturn reason
EndProcedure
; Admission alone does not apply an ACK or advance the receive packet. A
; pending outgoing packet must finish first, to preserve its ledger ordering.
Procedure.i QuicConnectionAckBegin(*c.QuicConnection)
 Define rc.i,i.i,level.i,*s.QuicConnectionSpace
 If quicca_Valid(*c)=0 : ProcedureReturn #QUIC_CONNECTION_ACK_ARGUMENT : EndIf
 If *c\phase<>1 Or (*c\acknowledge\phase<>0 And *c\acknowledge\phase<>5) : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 If *c\application\phase=1 : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 If *c\startup\phase>=1 And *c\startup\phase<=8 : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 If *c\receive\phase<>2 Or *c\receive\authenticated<>1 Or *c\receive\process\phase<>2 : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 If *c\outgoing\phase<>0 And *c\outgoing\phase<>6 : ProcedureReturn #QUIC_SENT_BUSY : EndIf
 level=*c\receive\level
 If level=0 : *s=@*c\initial
 ElseIf level=2 : *s=@*c\handshake
 Else : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 If *c\receive\process\level<>level Or *c\receive\rx<>@*s\rx Or *c\receive\ack<>@*s\ack : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 rc=QuicHandshakeSentAckBegin(@*c\ackJob,@*s\history,level,@*c\receive\process\frame)
 If rc<>0 : ProcedureReturn rc : EndIf
 For i=0 To SizeOf(QuicConnectionAck)-1 : PokeA(@*c\acknowledge+i,0) : Next
 *c\acknowledge\phase=1 : *c\acknowledge\level=level
 ProcedureReturn 0
EndProcedure
; 0 pending,1 done,negative fatal/refused. One ledger step, at most256 marked
; bytes, or at most256 reclaimed bytes per call. The entire wire ACK is
; validated by the ledger before events mutate history. No rollback on failure.
; Accept the receive event only after all history/stream work has completed.
Procedure.i QuicConnectionAckStep(*c.QuicConnection)
 Define rc.i,n.i,p.i,offset.i,bytes.i,*s.QuicConnectionSpace
 If quicca_Valid(*c)=0 : ProcedureReturn #QUIC_CONNECTION_ACK_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 If *c\acknowledge\phase=5 : ProcedureReturn 1 : EndIf
 If *c\acknowledge\phase<1 Or *c\acknowledge\phase>4 : ProcedureReturn #QUIC_CONNECTION_ACK_STATE : EndIf
 If *c\receive\phase<>2 Or *c\receive\authenticated<>1 Or *c\receive\process\phase<>2 : ProcedureReturn quicca_Fail(*c,#QUIC_CONNECTION_ACK_STATE) : EndIf
 *s=quicca_Space(*c)
 If *c\acknowledge\phase=1
  rc=QuicHandshakeSentAckStep(@*c\ackJob)
  If rc<0 : ProcedureReturn quicca_Fail(*c,rc) : EndIf
  If rc=0 : ProcedureReturn 0 : EndIf
  If rc=2
   rc=QuicConnectionRecoveryRearm(*c,Bool(*c\acknowledge\events>0 And (*c\acknowledge\level=2 Or *c\handshakeConfirmed=1)))
   If rc<0 : ProcedureReturn quicca_Fail(*c,rc) : EndIf
   *c\acknowledge\phase=4 : ProcedureReturn 0
  EndIf
  If rc<>1 : ProcedureReturn quicca_Fail(*c,#QUIC_CONNECTION_ACK_STATE) : EndIf
  If *c\ackJob\number<*s\history\first Or *c\ackJob\number>=*s\history\issued : ProcedureReturn quicca_Fail(*c,#QUIC_CONNECTION_ACK_METADATA) : EndIf
  p=*s\metadata+(*c\ackJob\number % *s\history\capacity)*16
  If *c\ackJob\cookie<>p : ProcedureReturn quicca_Fail(*c,#QUIC_CONNECTION_ACK_METADATA) : EndIf
  offset=PeekI(p) : bytes=PeekI(p+8)
  If offset<0 Or bytes<0 Or bytes>16384 Or offset>#QUIC_INTEGER_MAX-bytes : ProcedureReturn quicca_Fail(*c,#QUIC_CONNECTION_ACK_METADATA) : EndIf
  *c\acknowledge\events=*c\acknowledge\events+1
  If bytes>0
   *c\acknowledge\offset=offset : *c\acknowledge\remaining=bytes : *c\acknowledge\phase=2
  EndIf
  ProcedureReturn 0
 EndIf
 If *c\acknowledge\phase=2
  n=*c\acknowledge\remaining : If n>256 : n=256 : EndIf
  rc=QuicCryptoTxAck(@*s\tx,*c\acknowledge\offset,n)
  If rc<>0 : ProcedureReturn quicca_Fail(*c,rc) : EndIf
  *c\acknowledge\offset=*c\acknowledge\offset+n : *c\acknowledge\remaining=*c\acknowledge\remaining-n
  If *c\acknowledge\remaining=0 : *c\acknowledge\phase=3 : EndIf
  ProcedureReturn 0
 EndIf
 If *c\acknowledge\phase=3
  rc=QuicCryptoTxReclaim(@*s\tx,256)
  If rc<0 : ProcedureReturn quicca_Fail(*c,rc) : EndIf
  If rc<256 : *c\acknowledge\phase=1 : EndIf
  ProcedureReturn 0
 EndIf
 rc=QuicHandshakeReceiveAccept(@*c\receive)
 If rc<>0 : ProcedureReturn quicca_Fail(*c,rc) : EndIf
 *c\acknowledge\phase=5 : ProcedureReturn 1
EndProcedure
