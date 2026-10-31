; SPDX-License-Identifier: MIT
; Independent RFC9000 sections12.4 and19 decoding of QUIC v1 1-RTT frames.
; Authenticate and bind the packet before use. Views borrow packet storage.
; This parses syntax only: role, stream/CID state, flow control, ACK effects,
; handshake confirmation and key retirement belong to the connection owner.
XIncludeFile "Anvil/Network/quic_handshake_frames.pbi"
Structure QuicApplicationFrame
 base.QuicHandshakeFrame
 stream.i
 finalSize.i
 value.i
 sequence.i
 retire.i
 idBytes.i
 resetToken.i
 fin.i
EndStructure
Procedure.i quicaf_Read(source.i,bytes.i,cursor.i,value.i)
 Define p.i,n.i
 p=PeekI(cursor) : n=QuicIntegerRead(source+p,bytes-p,value)
 If n<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 PokeI(cursor,p+n) : ProcedureReturn 0
EndProcedure
; Positive consumed bytes or negative refusal with the entire view unchanged.
; One frame per call; ACK parsing retains the shared 64-range local bound.
; Nonminimal type encodings are refused; nonminimal field integers are legal.
; No-LEN STREAM consumes the rest of the packet, even bytes resembling frames.
Procedure.i QuicApplicationFrameRead(source.i,bytes.i,*view.QuicApplicationFrame)
 Define f.QuicApplicationFrame,p.i,n.i,k.i,i.i,length.i
 If source<=0 Or bytes<0 Or source>$7FFFFFFFFFFFFFFF-bytes : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If *view<=0 Or *view>$7FFFFFFFFFFFFFFF-SizeOf(QuicApplicationFrame) : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If bytes>0 And source<*view+SizeOf(QuicApplicationFrame) And *view<source+bytes : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 n=QuicIntegerRead(source,bytes,@k) : If n<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 If n<>QuicIntegerSize(k) : ProcedureReturn #QUIC_RX_FORMAT : EndIf
 For i=0 To SizeOf(QuicApplicationFrame)-1 : PokeA(@f+i,0) : Next
 f\base\kind=k : p=n
 If k<=3 Or k=6 Or k=28
  ; These wire layouts are identical in Handshake and 1-RTT packets.
  p=QuicHandshakeFrameRead(source,bytes,2,@f\base)
  If p<0 : ProcedureReturn p : EndIf
 Else
  f\base\eliciting=1
  If k=4 Or k=5
   If quicaf_Read(source,bytes,@p,@f\stream)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If quicaf_Read(source,bytes,@p,@f\base\error)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If k=4
    If quicaf_Read(source,bytes,@p,@f\finalSize)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   EndIf
  ElseIf k=7
   If quicaf_Read(source,bytes,@p,@length)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If length=0 : ProcedureReturn #QUIC_RX_FORMAT : EndIf
   If length>bytes-p : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   f\base\data=source+p : f\base\bytes=length : p=p+length
  ElseIf k>=8 And k<=15
   If quicaf_Read(source,bytes,@p,@f\stream)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If k&4
    If quicaf_Read(source,bytes,@p,@f\base\offset)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   EndIf
   length=bytes-p
   If k&2
    If quicaf_Read(source,bytes,@p,@length)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   EndIf
   If length>bytes-p : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If length>$3FFFFFFFFFFFFFFF-f\base\offset : ProcedureReturn #QUIC_RX_RANGE : EndIf
   f\base\data=source+p : f\base\bytes=length : p=p+length : f\fin=k&1
   If f\fin : f\finalSize=f\base\offset+length : EndIf
  ElseIf k>=16 And k<=23
   If k=17 Or k=21
    If quicaf_Read(source,bytes,@p,@f\stream)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   EndIf
   If quicaf_Read(source,bytes,@p,@f\value)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If k=18 Or k=19 Or k=22 Or k=23
    If f\value>$1000000000000000 : ProcedureReturn #QUIC_RX_RANGE : EndIf
   EndIf
  ElseIf k=24
   If quicaf_Read(source,bytes,@p,@f\sequence)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If quicaf_Read(source,bytes,@p,@f\retire)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If f\retire>f\sequence : ProcedureReturn #QUIC_RX_FORMAT : EndIf
   If p>=bytes : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   f\idBytes=PeekA(source+p)&255 : p=p+1
   If f\idBytes<1 Or f\idBytes>20 : ProcedureReturn #QUIC_RX_FORMAT : EndIf
   If f\idBytes+16>bytes-p : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   f\base\data=source+p : f\base\bytes=f\idBytes
   f\resetToken=source+p+f\idBytes : p=p+f\idBytes+16
  ElseIf k=25
   If quicaf_Read(source,bytes,@p,@f\sequence)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  ElseIf k=26 Or k=27
   If bytes-p<8 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   f\base\data=source+p : f\base\bytes=8 : p=p+8
  ElseIf k=29
   f\base\eliciting=0
   If quicaf_Read(source,bytes,@p,@f\base\error)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If quicaf_Read(source,bytes,@p,@length)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If length>bytes-p : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   f\base\data=source+p : f\base\bytes=length : p=p+length
  ElseIf k<>30
   ProcedureReturn #QUIC_RX_FORMAT
  EndIf
 EndIf
 For i=0 To SizeOf(QuicApplicationFrame)-1 : PokeA(*view+i,PeekA(@f+i)) : Next
 ProcedureReturn p
EndProcedure
