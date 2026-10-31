; SPDX-License-Identifier: MIT
; Independent RFC 9000 sections12.3/13.1 packet-processing ordering.
; The caller MUST authenticate/decrypt first and bind the correct connection,
; packet number and encryption level. This module does not establish identity.
XIncludeFile "Anvil/Network/quic_handshake_frames.pbi"
XIncludeFile "Anvil/Network/quic_handshake_ack.pbi"
#QUIC_PROCESS_ARGUMENT=-3451
#QUIC_PROCESS_STATE=-3452
#QUIC_PROCESS_EMPTY=-3453
#QUIC_PROCESS_REJECTED=-3454
Structure QuicHandshakePacket
 phase.i
 error.i
 source.i
 bytes.i
 cursor.i
 pn.i
 level.i
 rx.i
 ack.i
 duplicate.i
 eliciting.i
 ending.i
 copied.i
 frame.QuicHandshakeFrame
EndStructure
Procedure.i quicpkt_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicpkt_Separate(a.i,n.i,b.i,m.i)
 If n>0 And m>0 And a<b+m And b<a+n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicpkt_OutsideRx(*r.QuicCryptoRx,p.i,n.i)
 If quicpkt_Separate(p,n,*r,SizeOf(QuicCryptoRx))=0 Or quicpkt_Separate(p,n,*r\data,*r\capacity)=0 Or quicpkt_Separate(p,n,*r\bits,*r\capacity/8)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicpkt_OutsideAck(*a.QuicHandshakeAck,p.i,n.i)
 If quicpkt_Separate(p,n,*a,SizeOf(QuicHandshakeAck))=0 Or quicpkt_Separate(p,n,*a\entries,*a\capacity*16)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicpkt_Fail(*s.QuicHandshakePacket,rc.i)
 *s\phase=-1 : *s\error=rc : ProcedureReturn rc
EndProcedure
; Public admission check for a containing crypto/packet owner. No receipt lookup
; or state mutation, so it can run before packet authentication.
Procedure.i QuicHandshakeStorageCheck(owner.i,ownerBytes.i,source.i,bytes.i,level.i,*r.QuicCryptoRx,*a.QuicHandshakeAck)
 If ownerBytes<1 Or quicpkt_Span(owner,ownerBytes)=0 Or quicpkt_Span(source,bytes)=0 Or quicpkt_Span(*r,SizeOf(QuicCryptoRx))=0 Or quicpkt_Span(*a,SizeOf(QuicHandshakeAck))=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If bytes>65535 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If level<>0 And level<>2 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If (*r\phase<>1 And *r\phase<>2) Or *a\phase<>1 Or level<>*r\level Or level<>*a\level : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 If quicpkt_Separate(owner,ownerBytes,source,bytes)=0 Or quicpkt_OutsideRx(*r,owner,ownerBytes)=0 Or quicpkt_OutsideAck(*a,owner,ownerBytes)=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If quicpkt_OutsideRx(*r,source,bytes)=0 Or quicpkt_OutsideAck(*a,source,bytes)=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If quicpkt_OutsideAck(*a,*r,SizeOf(QuicCryptoRx))=0 Or quicpkt_OutsideAck(*a,*r\data,*r\capacity)=0 Or quicpkt_OutsideAck(*a,*r\bits,*r\capacity/8)=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 ProcedureReturn 0
EndProcedure
; Zero-initialize job before first Begin. Unused/completed/discarded jobs may begin.
; Packet bytes and all initialized contexts/storage must be distinct and remain
; alive/exclusive until completion. TLS pumping follows packet completion.
Procedure.i QuicHandshakePacketBegin(*s.QuicHandshakePacket,source.i,bytes.i,pn.i,level.i,*r.QuicCryptoRx,*a.QuicHandshakeAck)
 Define rc.i,i.i
 rc=QuicHandshakeStorageCheck(*s,SizeOf(QuicHandshakePacket),source,bytes,level,*r,*a)
 If rc<0 : ProcedureReturn rc : EndIf
 If *s\phase<>0 And *s\phase<>4 And *s\phase<>6 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 If pn<0 Or pn>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 rc=QuicHandshakeAckSeen(*a,pn) : If rc<0 : ProcedureReturn rc : EndIf
 If bytes=0 And rc=0 : ProcedureReturn #QUIC_PROCESS_EMPTY : EndIf
 For i=0 To SizeOf(QuicHandshakePacket)-1 : PokeA(*s+i,0) : Next
 *s\phase=1 : *s\source=source : *s\bytes=bytes : *s\pn=pn : *s\level=level : *s\rx=*r : *s\ack=*a : *s\duplicate=rc
 If rc<>0 : *s\phase=6 : EndIf
 ProcedureReturn 0
EndProcedure
; Returns1 more work,2 ACK event,4 complete,5 peer close,6 discarded,negative fatal.
; ACK event is borrowed in frame and MUST be applied to sent-packet history
; before Accept. Step repeats an outstanding event without advancing it.
; Each Step decodes one frame or copies <=16384 CRYPTO bytes. Duplicate packets
; are discarded without interpreting frames, changing history or ACK demand.
; Failure can leave earlier CRYPTO bytes queued: close, never retry/roll back.
Procedure.i QuicHandshakePacketStep(*s.QuicHandshakePacket)
 Define n.i,rc.i,*r.QuicCryptoRx
 If quicpkt_Span(*s,SizeOf(QuicHandshakePacket))=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase=-1 : ProcedureReturn *s\error : EndIf
 If *s\phase=2 Or *s\phase=4 Or *s\phase=5 Or *s\phase=6 : ProcedureReturn *s\phase : EndIf
 If *s\phase<>1 And *s\phase<>3 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 If *s\phase=3
  n=*s\frame\bytes-*s\copied : If n>16384 : n=16384 : EndIf
  rc=QuicCryptoRxPut(*s\rx,*s\level,*s\frame\offset+*s\copied,*s\frame\data+*s\copied,n)
  If rc<0 : ProcedureReturn quicpkt_Fail(*s,rc) : EndIf
  *s\copied=*s\copied+n
  If *s\copied=*s\frame\bytes : *s\cursor=*s\ending : *s\phase=1 : EndIf
  ProcedureReturn 1
 EndIf
 If *s\cursor=*s\bytes
  rc=QuicHandshakeAckRecord(*s\ack,*s\pn,*s\eliciting)
  If rc<0 : ProcedureReturn quicpkt_Fail(*s,rc) : EndIf
  *s\phase=4 : ProcedureReturn 4
 EndIf
 n=QuicHandshakeFrameRead(*s\source+*s\cursor,*s\bytes-*s\cursor,*s\level,@*s\frame)
 If n<0 : ProcedureReturn quicpkt_Fail(*s,n) : EndIf
 *s\ending=*s\cursor+n
 If *s\frame\eliciting<>0 : *s\eliciting=1 : EndIf
 If *s\frame\kind=2 Or *s\frame\kind=3 : *s\phase=2 : ProcedureReturn 2 : EndIf
 If *s\frame\kind=28 : *s\phase=5 : ProcedureReturn 5 : EndIf
 If *s\frame\kind=6 : *s\copied=0 : *s\phase=3 : ProcedureReturn 1 : EndIf
 *s\cursor=*s\ending : ProcedureReturn 1
EndProcedure
Procedure.i QuicHandshakePacketAccept(*s.QuicHandshakePacket)
 If quicpkt_Span(*s,SizeOf(QuicHandshakePacket))=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase<>2 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 *s\cursor=*s\ending : *s\phase=1 : ProcedureReturn 0
EndProcedure
Procedure.i QuicHandshakePacketReject(*s.QuicHandshakePacket)
 If quicpkt_Span(*s,SizeOf(QuicHandshakePacket))=0 : ProcedureReturn #QUIC_PROCESS_ARGUMENT : EndIf
 If *s\phase<>2 : ProcedureReturn #QUIC_PROCESS_STATE : EndIf
 ProcedureReturn quicpkt_Fail(*s,#QUIC_PROCESS_REJECTED)
EndProcedure
