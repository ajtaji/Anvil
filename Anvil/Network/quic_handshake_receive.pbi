; SPDX-License-Identifier: MIT
; Independent RFC 9001 section5.5 and RFC 9000 sections12.3/13.1 integration.
; Compose shared SHA/HMAC/HKDF/AES/GCM jobs before this module. Connection/CID
; selection, peer identity, address validation and key lifetime remain external.
XIncludeFile "Anvil/Network/quic_crypto.pbi"
XIncludeFile "Anvil/Network/quic_handshake_packet.pbi"
Structure QuicHandshakeReceive
 phase.i
 result.i
 level.i
 rx.i
 ack.i
 consumed.i
 authenticated.i
 crypto.QuicPacketJob
 process.QuicHandshakePacket
EndStructure
Procedure.i quicrecv_Valid(*s.QuicHandshakeReceive)
 If *s<=0 Or *s>$7FFFFFFFFFFFFFFF-SizeOf(QuicHandshakeReceive) : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicrecv_Finish(*s.QuicHandshakeReceive,rc.i)
 *s\result=rc : *s\phase=rc
 If rc<0 : *s\phase=-1 : EndIf
 ProcedureReturn rc
EndProcedure
; Begin one in-place Initial/Handshake packet from a datagram. consumed reports
; its header-declared wire length; remaining coalesced bytes are not processed.
; Return0 pending,6 discard,negative refusal. BUSY leaves job retryable and never
; cancels another crypto owner. largest is last authenticated PN (-1 initially).
; All storage, key and packet lifetimes remain exclusive until terminal result.
Procedure.i QuicHandshakeReceiveBegin(*s.QuicHandshakeReceive,*keys.QuicKeys,packet.i,bytes.i,level.i,largest.i,*r.QuicCryptoRx,*a.QuicHandshakeAck)
 Define rc.i,i.i,h.QuicPacketHeader
 rc=QuicHandshakeStorageCheck(*s,SizeOf(QuicHandshakeReceive),packet,bytes,level,*r,*a)
 If rc<0 : ProcedureReturn rc : EndIf
 rc=QuicHandshakeStorageCheck(*keys,SizeOf(QuicKeys),packet,bytes,level,*r,*a)
 If rc<0 : ProcedureReturn rc : EndIf
 If *s<*keys+SizeOf(QuicKeys) And *keys<*s+SizeOf(QuicHandshakeReceive) : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase<>0 And *s\phase<>4 And *s\phase<>6 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 If bytes<1 Or bytes>#QUIC_CRYPTO_MAX_PACKET Or largest< -1 Or largest>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *keys\ready<>1 : ProcedureReturn #QUIC_CRYPTO_STATE : EndIf
 If quicCryptoOwner<>0 Or GcmJobBusy()<>0 : ProcedureReturn #QUIC_CRYPTO_BUSY : EndIf
 For i=0 To SizeOf(QuicHandshakeReceive)-1 : PokeA(*s+i,0) : Next
 *s\level=level : *s\rx=*r : *s\ack=*a
 rc=QuicPacketRead(@h,packet,bytes,0)
 If rc<>1 : ProcedureReturn quicrecv_Finish(*s,6) : EndIf
 *s\consumed=h\packetBytes
 If (level=0 And h\kind<>#QUIC_PACKET_INITIAL) Or (level=2 And h\kind<>#QUIC_PACKET_HANDSHAKE) : ProcedureReturn quicrecv_Finish(*s,6) : EndIf
 rc=QuicPacketJobBegin(@*s\crypto,*keys,packet,bytes,0,largest,0)
 If rc=#QUIC_CRYPTO_BUSY : ProcedureReturn rc : EndIf
 If rc=#QUIC_CRYPTO_STATE : ProcedureReturn quicrecv_Finish(*s,rc) : EndIf
 If rc<>0 : ProcedureReturn quicrecv_Finish(*s,6) : EndIf
 *s\phase=1 : ProcedureReturn 0
EndProcedure
; Same processing results as PacketStep (1 more,2 ACK,4 complete,5 close,6 drop).
; Header/authentication failures discard without receive/history effects.
; Authenticated reserved bits and frame failures remain fatal, not silent drops.
Procedure.i QuicHandshakeReceiveStep(*s.QuicHandshakeReceive)
 Define rc.i
 If quicrecv_Valid(*s)=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase=-1 Or *s\phase>=4 : ProcedureReturn *s\result : EndIf
 If *s\phase=1
  rc=QuicPacketJobStep(@*s\crypto)
  If rc=0 : ProcedureReturn 1 : EndIf
  If rc=#QUIC_CRYPTO_AUTH : ProcedureReturn quicrecv_Finish(*s,6) : EndIf
  If rc<>1 : ProcedureReturn quicrecv_Finish(*s,rc) : EndIf
  *s\authenticated=1
  rc=QuicHandshakePacketBegin(@*s\process,*s\crypto\packet+*s\crypto\plainOffset,*s\crypto\plainBytes,*s\crypto\number,*s\level,*s\rx,*s\ack)
  If rc<0 : ProcedureReturn quicrecv_Finish(*s,rc) : EndIf
  *s\phase=2 : ProcedureReturn 1
 EndIf
 If *s\phase<>2 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 rc=QuicHandshakePacketStep(@*s\process)
 If rc<0 Or rc>=4 : ProcedureReturn quicrecv_Finish(*s,rc) : EndIf
 ProcedureReturn rc
EndProcedure
Procedure.i QuicHandshakeReceiveAccept(*s.QuicHandshakeReceive)
 If quicrecv_Valid(*s)=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase<>2 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 ProcedureReturn QuicHandshakePacketAccept(@*s\process)
EndProcedure
Procedure.i QuicHandshakeReceiveReject(*s.QuicHandshakeReceive)
 Define rc.i
 If quicrecv_Valid(*s)=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase<>2 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 rc=QuicHandshakePacketReject(@*s\process)
 If rc=#QUIC_PROCESS_STATE : ProcedureReturn rc : EndIf
 ProcedureReturn quicrecv_Finish(*s,rc)
EndProcedure
; Cancel requires discarding the packet and closing this receive connection.
; It never cancels another owner's crypto or rolls back queued plaintext.
Procedure.i QuicHandshakeReceiveCancel(*s.QuicHandshakeReceive)
 Define rc.i
 If quicrecv_Valid(*s)=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase=1
  rc=QuicPacketJobCancel(@*s\crypto)
  If rc<>#QUIC_CRYPTO_CANCELLED : ProcedureReturn rc : EndIf
 ElseIf *s\phase<>2
  ProcedureReturn #QUIC_PROCESS_STATE
 EndIf
 ProcedureReturn quicrecv_Finish(*s,#QUIC_CRYPTO_CANCELLED)
EndProcedure
