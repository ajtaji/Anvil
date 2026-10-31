; SPDX-License-Identifier: MIT
; Independent QUIC CRYPTO framing/reassembly from RFC9000 sections7.5/19.6
; and RFC9001 section4.1.3. No TLS, sockets, allocation or packet authentication.
; Feed only packet-authenticated plaintext; Initial protection is not identity.
; One caller-owned context per encryption level, with separate data/bitmap.
; Context/storage remain exclusively owned and unmodified between calls.
XIncludeFile "Anvil/Network/quic_wire.pbi"
#QUIC_RX_ARGUMENT=-3421
#QUIC_RX_TRUNCATED=-3422
#QUIC_RX_RANGE=-3423
#QUIC_RX_FORMAT=-3424
#QUIC_RX_LIMIT=-3425
#QUIC_RX_CONFLICT=-3426
#QUIC_RX_LEVEL=-3427
#QUIC_RX_STATE=-3428
Structure QuicCryptoSlice
 offset.i
 data.i
 bytes.i
EndStructure
Structure QuicCryptoRx
 phase.i
 level.i
 data.i
 bits.i
 capacity.i
 base.i
 head.i
 buffered.i
 highest.i
 offered.i
EndStructure
Procedure.i quicrx_Span(p.i,n.i)
 If p<=0 Or n<0 Or p>$7FFFFFFFFFFFFFFF-n : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i quicrx_Overlap(a.i,n.i,b.i,m.i)
 If n>0 And m>0 And a<b+m And b<a+n : ProcedureReturn 1 : EndIf
 ProcedureReturn 0
EndProcedure
; Returns complete frame bytes, or negative without changing the borrowed view.
Procedure.i QuicCryptoFrameRead(source.i,bytes.i,*view.QuicCryptoSlice)
 Define cursor.i,n.i,value.i,offset.i,length.i
 If quicrx_Span(source,bytes)=0 Or quicrx_Span(*view,SizeOf(QuicCryptoSlice))=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If quicrx_Overlap(source,bytes,*view,SizeOf(QuicCryptoSlice))<>0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 n=QuicIntegerRead(source,bytes,@value) : If n<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 If value<>6 : ProcedureReturn #QUIC_RX_FORMAT : EndIf
 cursor=n
 n=QuicIntegerRead(source+cursor,bytes-cursor,@offset) : If n<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 cursor=cursor+n
 n=QuicIntegerRead(source+cursor,bytes-cursor,@length) : If n<0 : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 cursor=cursor+n
 If length>#QUIC_INTEGER_MAX-offset : ProcedureReturn #QUIC_RX_RANGE : EndIf
 If length>bytes-cursor : ProcedureReturn #QUIC_RX_TRUNCATED : EndIf
 *view\offset=offset : *view\data=source+cursor : *view\bytes=length
 ProcedureReturn cursor+length
EndProcedure
; capacity4096..262144, multiple8; bitmap needs capacity/8 bytes.
; Init clears the bitmap, not payload data. Invalid init changes nothing.
Procedure.i QuicCryptoRxInit(*s.QuicCryptoRx,level.i,data.i,capacity.i,bits.i,bitBytes.i)
 Define i.i,n.i
 If level<>0 And level<>2 And level<>3 : ProcedureReturn #QUIC_RX_LEVEL : EndIf
 If capacity<4096 Or capacity>262144 Or (capacity&7)<>0 Or bitBytes<capacity/8 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 n=capacity/8
 If quicrx_Span(*s,SizeOf(QuicCryptoRx))=0 Or quicrx_Span(data,capacity)=0 Or quicrx_Span(bits,n)=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If quicrx_Overlap(*s,SizeOf(QuicCryptoRx),data,capacity) Or quicrx_Overlap(*s,SizeOf(QuicCryptoRx),bits,n) Or quicrx_Overlap(data,capacity,bits,n) : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 For i=0 To n-1 : PokeA(bits+i,0) : Next
 *s\phase=1 : *s\level=level : *s\data=data : *s\bits=bits : *s\capacity=capacity
 *s\base=0 : *s\head=0 : *s\buffered=0 : *s\highest=0 : *s\offered=0
 ProcedureReturn 0
EndProcedure
Procedure.i quicrx_External(*s.QuicCryptoRx,p.i,n.i)
 If quicrx_Span(p,n)=0 : ProcedureReturn 0 : EndIf
 If quicrx_Overlap(p,n,*s,SizeOf(QuicCryptoRx)) Or quicrx_Overlap(p,n,*s\data,*s\capacity) Or quicrx_Overlap(p,n,*s\bits,*s\capacity/8) : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
; At most16384 input bytes/call. Larger parsed frames must be fed in pieces.
; Validate all overlap bytes before committing any. Already-consumed prefixes
; are ignored; retained overlaps must match. Returns number of new bytes.
Procedure.i QuicCryptoRxPut(*s.QuicCryptoRx,level.i,offset.i,source.i,bytes.i)
 Define skip.i,i.i,index.i,mask.i,bit.i,added.i,ending.i
 If quicrx_Span(*s,SizeOf(QuicCryptoRx))=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If *s\phase<>1 And *s\phase<>2 : ProcedureReturn #QUIC_RX_STATE : EndIf
 If level<>*s\level : ProcedureReturn #QUIC_RX_LEVEL : EndIf
 If bytes<0 Or bytes>16384 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If offset<0 Or offset>#QUIC_INTEGER_MAX Or bytes>#QUIC_INTEGER_MAX-offset : ProcedureReturn #QUIC_RX_RANGE : EndIf
 If bytes=0 : ProcedureReturn 0 : EndIf
 If quicrx_External(*s,source,bytes)=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 ending=offset+bytes
 If *s\phase=2 And ending>*s\base : ProcedureReturn #QUIC_RX_LEVEL : EndIf
 If ending<=*s\base : ProcedureReturn 0 : EndIf
 If ending-*s\base>*s\capacity : ProcedureReturn #QUIC_RX_LIMIT : EndIf
 skip=0 : If offset<*s\base : skip=*s\base-offset : EndIf
 For i=skip To bytes-1
  index=(*s\head+offset+i-*s\base) % *s\capacity
  mask=1 << (index&7) : bit=PeekA(*s\bits+(index>>3))
  If (bit&mask)<>0 And PeekA(*s\data+index)<>PeekA(source+i) : ProcedureReturn #QUIC_RX_CONFLICT : EndIf
 Next
 For i=skip To bytes-1
  index=(*s\head+offset+i-*s\base) % *s\capacity
  mask=1 << (index&7) : bit=PeekA(*s\bits+(index>>3))
  If (bit&mask)=0
   PokeA(*s\data+index,PeekA(source+i)) : PokeA(*s\bits+(index>>3),bit|mask) : added=added+1
  EndIf
 Next
 *s\buffered=*s\buffered+added
 If ending>*s\highest : *s\highest=ending : EndIf
 ProcedureReturn added
EndProcedure
; Offers at most4096 contiguous bytes, never across ring wrap. The view stays
; valid through Put; Consume or Init ends the borrow. Zero means a gap/empty.
Procedure.i QuicCryptoRxPeek(*s.QuicCryptoRx,limit.i,*view.QuicCryptoSlice)
 Define n.i,index.i
 If quicrx_Span(*s,SizeOf(QuicCryptoRx))=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If *s\phase<>1 And *s\phase<>2 : ProcedureReturn #QUIC_RX_STATE : EndIf
 If limit<1 Or limit>4096 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If quicrx_External(*s,*view,SizeOf(QuicCryptoSlice))=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 n=0
 While n<limit And *s\head+n<*s\capacity
  index=*s\head+n
  If (PeekA(*s\bits+(index>>3)) & (1<<(index&7)))=0 : Break : EndIf
  n=n+1
 Wend
 *s\offered=n : *view\offset=*s\base : *view\data=*s\data+*s\head : *view\bytes=n
 ProcedureReturn n
EndProcedure
; Consumes only the most recent offer, including partial acceptance by TLS.
Procedure.i QuicCryptoRxConsume(*s.QuicCryptoRx,bytes.i)
 Define i.i,index.i,p.i
 If quicrx_Span(*s,SizeOf(QuicCryptoRx))=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If *s\phase<>1 And *s\phase<>2 : ProcedureReturn #QUIC_RX_STATE : EndIf
 If bytes<0 Or bytes>*s\offered : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 For i=0 To bytes-1
  index=*s\head+i : p=*s\bits+(index>>3)
  PokeA(p,PeekA(p) & (255 ! (1<<(index&7))))
 Next
 *s\head=(*s\head+bytes) % *s\capacity : *s\base=*s\base+bytes
 *s\buffered=*s\buffered-bytes : *s\offered=0
 ProcedureReturn 0
EndProcedure
; Call on a TLS receive-level transition. Outstanding older data is a protocol
; error. Sealed levels accept only old retransmissions, never new bytes.
Procedure.i QuicCryptoRxSeal(*s.QuicCryptoRx)
 If quicrx_Span(*s,SizeOf(QuicCryptoRx))=0 : ProcedureReturn #QUIC_RX_ARGUMENT : EndIf
 If *s\phase<>1 And *s\phase<>2 : ProcedureReturn #QUIC_RX_STATE : EndIf
 If *s\buffered<>0 Or *s\base<>*s\highest : ProcedureReturn #QUIC_RX_LEVEL : EndIf
 *s\phase=2 : *s\offered=0 : ProcedureReturn 0
EndProcedure
