; SPDX-License-Identifier: MIT
; Independent RFC 9000 sections12.4/12.5 and19.1/19.2/19.3/19.6/19.19.
; Initial/Handshake plaintext frames only. Packet authentication and connection
; effects belong to the caller. Never acknowledge before ALL frames are applied.
XIncludeFile "Anvil/Network/quic_crypto_stream.pbi"
Structure QuicHandshakeFrame
 kind.i
 eliciting.i
 data.i
 bytes.i
 offset.i
 largest.i
 delay.i
 count.i
 ranges.i
 rangeBytes.i
 ect0.i
 ect1.i
 ce.i
 error.i
 trigger.i
EndStructure
Procedure.i quichf_Read(source.i,bytes.i,cursor.i,value.i)
 Define p.i,n.i
 p=PeekI(cursor) : n=QuicIntegerRead(source+p,bytes-p,value)
 If n<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 PokeI(cursor,p+n) : ProcedureReturn 0
EndProcedure
; Returns ONE complete frame's byte count, or negative with view unchanged.
; Views borrow immutable packet storage. ACK ranges contain First ACK Range,
; then count-1 gap/range pairs, all already checked against underflow. Count
; includes the first range. At most64 ranges: LIMIT is a local resource refusal,
; not proof the peer sent an invalid frame. Delay remains raw/unscaled.
; data/bytes describe CRYPTO data or close reason; unused fields are zero.
; Known application-only frames return LEVEL; unknown types return FORMAT.
; This dispatcher elects to refuse nonminimal frame TYPE encodings (LEVEL),
; while other variable integers retain their permitted nonminimal encodings.
Procedure.i QuicHandshakeFrameRead(source.i,bytes.i,level.i,*view.QuicHandshakeFrame)
 Define f.QuicHandshakeFrame,crypto.QuicCryptoSlice,p.i,n.i,i.i,k.i,low.i,gap.i,length.i
 If level<>0 And level<>2 : ProcedureReturn #QUIC_RX_LEVEL : EndIf
 If source<=0 Or bytes<0 Or source>$7FFFFFFFFFFFFFFF-bytes : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If *view<=0 Or *view>$7FFFFFFFFFFFFFFF-SizeOf(QuicHandshakeFrame) : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If bytes>0 And source<*view+SizeOf(QuicHandshakeFrame) And *view<source+bytes : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 n=QuicIntegerRead(source,bytes,@k) : If n<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 If n<>QuicIntegerSize(k) : ProcedureReturn #QUIC_RX_LEVEL : EndIf
 For i=0 To SizeOf(QuicHandshakeFrame)-1 : PokeA(@f+i,0) : Next
 f\kind=k : p=n
 If k=0
  ; One padding byte; the packet owner bounds its own dispatch work.
 ElseIf k=1
  f\eliciting=1
 ElseIf k=6
  n=QuicCryptoFrameRead(source,bytes,@crypto) : If n<0 : ProcedureReturn n : EndIf
  p=n : f\eliciting=1 : f\offset=crypto\offset : f\data=crypto\data : f\bytes=crypto\bytes
 ElseIf k=2 Or k=3
  If quichf_Read(source,bytes,@p,@f\largest)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  If quichf_Read(source,bytes,@p,@f\delay)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  If quichf_Read(source,bytes,@p,@f\count)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  If f\count>63 : ProcedureReturn #QUIC_RX_LIMIT : EndIf
  f\ranges=source+p
  If quichf_Read(source,bytes,@p,@length)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  If length>f\largest : ProcedureReturn #QUIC_RX_FORMAT : EndIf
  low=f\largest-length
  For i=1 To f\count
   If quichf_Read(source,bytes,@p,@gap)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If quichf_Read(source,bytes,@p,@length)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If low<2 Or gap>low-2 : ProcedureReturn #QUIC_RX_FORMAT : EndIf
   low=low-gap-2
   If length>low : ProcedureReturn #QUIC_RX_FORMAT : EndIf
   low=low-length
  Next
  f\count=f\count+1 : f\rangeBytes=source+p-f\ranges
  If k=3
   If quichf_Read(source,bytes,@p,@f\ect0)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If quichf_Read(source,bytes,@p,@f\ect1)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
   If quichf_Read(source,bytes,@p,@f\ce)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  EndIf
 ElseIf k=28
  If quichf_Read(source,bytes,@p,@f\error)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  If quichf_Read(source,bytes,@p,@f\trigger)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  If quichf_Read(source,bytes,@p,@length)<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  If length>bytes-p : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
  f\data=source+p : f\bytes=length : p=p+length
 ElseIf k<=30
  ProcedureReturn #QUIC_RX_LEVEL
 Else
  ProcedureReturn #QUIC_RX_FORMAT
 EndIf
 For i=0 To SizeOf(QuicHandshakeFrame)-1 : PokeA(*view+i,PeekA(@f+i)) : Next
 ProcedureReturn p
EndProcedure
