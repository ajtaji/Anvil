; Cooperative Initial/Handshake receive for the shared connection owner.
; The owned input datagram remains retained through completion. Handshake CID
; policy currently uses an eight-byte local ID and a nonempty peer source ID.
; No I/O or TLS feed here. ACK events stay borrowed until AckStep accepts them.
#QUIC_RECEIVE_STATE=-3541
#QUIC_RECEIVE_ARGUMENT=-3542
Procedure.i quiccr_Valid(*c.QuicConnection)
 ProcedureReturn Bool(*c>0 And *c<=$7FFFFFFFFFFFFFFF-SizeOf(QuicConnection))
EndProcedure
Procedure.i quiccr_Space(*c.QuicConnection)
 If *c\incoming\level=0 : ProcedureReturn @*c\initial : EndIf
 ProcedureReturn @*c\handshake
EndProcedure
Procedure.i quiccr_Fail(*c.QuicConnection,rc.i)
 Define n.i
 *c\incoming\phase=-1 : *c\incoming\result=rc
 n=QuicConnectionClose(*c,rc)
 ProcedureReturn rc
EndProcedure
Procedure.i quiccr_Decrypt()
 Define *c.QuicConnection,*s.QuicConnectionSpace,rc.i
 *c=ScArgument() : *s=quiccr_Space(*c)
 rc=QuicHandshakeReceiveBegin(@*c\receive,@*s\readKeys,*c\incoming\packet,*c\incoming\bytes,*s\level,*s\largest,@*s\rx,@*s\ack)
 If rc=0
  Repeat
   rc=QuicHandshakeReceiveStep(@*c\receive)
   If rc<>1 Or *c\receive\phase<>1 : Break : EndIf
   TlsWorkerCheckpoint()
  ForEver
 EndIf
 *c\incoming\result=rc : ProcedureReturn 1
EndProcedure
; 0 admitted,6 dropped without mutation,negative refused. Header/CID checks
; precede admission. Learning the peer ID waits for authenticated completion.
Procedure.i QuicConnectionReceiveBegin(*c.QuicConnection,level.i,packet.i,bytes.i)
 Define i.i,p.i,rc.i,h.QuicPacketHeader,*s.QuicConnectionSpace
 If quiccr_Valid(*c)=0 : ProcedureReturn #QUIC_RECEIVE_ARGUMENT : EndIf
 If *c\phase<>1 Or (*c\incoming\phase<>0 And *c\incoming\phase<>4 And *c\incoming\phase<>6) : ProcedureReturn #QUIC_RECEIVE_STATE : EndIf
 If *c\feed\phase>=1 And *c\feed\phase<=11 : ProcedureReturn #QUIC_RECEIVE_STATE : EndIf
 If *c\outgoing\phase<>0 And *c\outgoing\phase<>6 : ProcedureReturn #QUIC_SENT_BUSY : EndIf
 If *c\acknowledge\phase>=1 And *c\acknowledge\phase<=4 : ProcedureReturn #QUIC_SENT_BUSY : EndIf
 If TlsWorkerBusy()<>0 : ProcedureReturn #TLSWORK_BUSY : EndIf
 p=QuicConnectionBuffer(*c,15)
 If bytes<1 Or bytes>1472 Or packet<p Or packet>p+1472-bytes : ProcedureReturn #QUIC_RECEIVE_ARGUMENT : EndIf
 If level=0 : *s=@*c\initial
 ElseIf level=2 : *s=@*c\handshake
 Else : ProcedureReturn #QUIC_RECEIVE_ARGUMENT : EndIf
 If level=0 And *c\initialRetired<>0 : ProcedureReturn 6 : EndIf
 If *s\readKeys\ready<>1 : ProcedureReturn #QUIC_RECEIVE_STATE : EndIf
 rc=QuicPacketRead(@h,packet,bytes,8)
 If rc<>1 : ProcedureReturn 6 : EndIf
 If h\version<>1 Or h\kind<>level Or h\destinationBytes<>8 Or h\sourceBytes<1 Or h\sourceBytes>20 : ProcedureReturn 6 : EndIf
 p=QuicConnectionBuffer(*c,18)
 For i=0 To 7 : If PeekA(packet+h\destinationOffset+i)<>PeekA(p+i) : ProcedureReturn 6 : EndIf : Next
 If *c\peerIdKnown<>0
  If h\sourceBytes<>*c\peerIdBytes : ProcedureReturn 6 : EndIf
  p=QuicConnectionBuffer(*c,19)
  For i=0 To h\sourceBytes-1 : If PeekA(packet+h\sourceOffset+i)<>PeekA(p+i) : ProcedureReturn 6 : EndIf : Next
 EndIf
 For i=0 To SizeOf(QuicConnectionReceive)-1 : PokeA(@*c\incoming+i,0) : Next
 *c\incoming\phase=1 : *c\incoming\level=level : *c\incoming\packet=packet : *c\incoming\bytes=h\packetBytes
 *c\incoming\sourceOffset=h\sourceOffset : *c\incoming\sourceBytes=h\sourceBytes
 ProcedureReturn 0
EndProcedure
; Select the supported long-header packet space. Application/Retry/version
; negotiation remain outside this handshake receiver and are dropped here.
Procedure.i QuicConnectionReceivePacketBegin(*c.QuicConnection,packet.i,bytes.i)
 Define p.i,h.QuicPacketHeader,rc.i
 If quiccr_Valid(*c)=0 : ProcedureReturn #QUIC_RECEIVE_ARGUMENT : EndIf
 If *c\phase<>1 Or (*c\incoming\phase<>0 And *c\incoming\phase<>4 And *c\incoming\phase<>6) : ProcedureReturn #QUIC_RECEIVE_STATE : EndIf
 p=QuicConnectionBuffer(*c,15)
 If bytes<1 Or bytes>1472 Or packet<p Or packet>p+1472-bytes : ProcedureReturn #QUIC_RECEIVE_ARGUMENT : EndIf
 rc=QuicPacketRead(@h,packet,bytes,8)
 If rc<>1 : ProcedureReturn 6 : EndIf
 If h\kind<>0 And h\kind<>2 : ProcedureReturn 6 : EndIf
 ProcedureReturn QuicConnectionReceiveBegin(*c,h\kind,packet,bytes)
EndProcedure
; 1 pending,2 borrowed ACK,4 complete,5 peer close,6 discard,negative failure.
; One worker slice or frame-parser step per call. No parser/TLS work runs on
; the suspended crypto stack. Packet-number state updates only on completion.
Procedure.i QuicConnectionReceiveStep(*c.QuicConnection)
 Define rc.i,i.i,p.i,*s.QuicConnectionSpace
 If quiccr_Valid(*c)=0 : ProcedureReturn #QUIC_RECEIVE_ARGUMENT : EndIf
 If *c\phase<>1 : ProcedureReturn #QUIC_RECEIVE_STATE : EndIf
 If *c\incoming\phase=4 Or *c\incoming\phase=6 : ProcedureReturn *c\incoming\phase : EndIf
 If *c\incoming\phase=1
  rc=TlsWorkerBegin(@*c\incoming\worker,@quiccr_Decrypt,*c)
  If rc=#TLSWORK_BUSY : ProcedureReturn 1 : EndIf
  If rc<>1 : ProcedureReturn quiccr_Fail(*c,rc) : EndIf
  *c\incoming\phase=2 : ProcedureReturn 1
 EndIf
 If *c\incoming\phase=2
  rc=TlsWorkerStep(@*c\incoming\worker)
  If rc=0 : ProcedureReturn 1 : EndIf
  If rc<>1 : ProcedureReturn quiccr_Fail(*c,rc) : EndIf
  rc=*c\incoming\result
  If rc=#QUIC_CRYPTO_BUSY : *c\incoming\phase=1 : ProcedureReturn 1 : EndIf
  If rc=1 : *c\incoming\phase=3 : ProcedureReturn 1 : EndIf
 ElseIf *c\incoming\phase=3
  rc=QuicHandshakeReceiveStep(@*c\receive)
 Else
  ProcedureReturn #QUIC_RECEIVE_STATE
 EndIf
 If rc=1 Or rc=2 : ProcedureReturn rc : EndIf
 If rc=4
  *s=quiccr_Space(*c)
  If *c\receive\crypto\number>*s\largest : *s\largest=*c\receive\crypto\number : EndIf
  If *c\peerIdKnown=0
   p=QuicConnectionBuffer(*c,19)
   For i=0 To *c\incoming\sourceBytes-1 : PokeA(p+i,PeekA(*c\incoming\packet+*c\incoming\sourceOffset+i)) : Next
   *c\peerIdBytes=*c\incoming\sourceBytes : *c\peerIdKnown=1
  EndIf
  *c\incoming\phase=4 : ProcedureReturn 4
 EndIf
 If rc=6 : *c\incoming\phase=6 : ProcedureReturn 6 : EndIf
 ProcedureReturn quiccr_Fail(*c,rc)
EndProcedure
