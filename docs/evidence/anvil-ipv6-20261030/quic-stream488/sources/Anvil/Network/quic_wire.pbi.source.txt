; SPDX-License-Identifier: MIT
; QUIC v1 wire primitives, independently implemented from protocol definitions:
; https://www.rfc-editor.org/rfc/rfc9000.html sections 16 and 17
; https://www.rfc-editor.org/rfc/rfc9001.html section 5.4.2
; No sockets, allocation, authentication or connection state. A parsed header
; is UNTRUSTED. Authenticate before acting on packet numbers or reserved bits.
XIncludeFile "Anvil/Network/byte_order.pbi"
#QUIC_WIRE_ARGUMENT=-3301
#QUIC_WIRE_TRUNCATED=-3302
#QUIC_WIRE_VERSION=-3303
#QUIC_WIRE_RANGE=-3304
#QUIC_WIRE_FORMAT=-3305
#QUIC_INTEGER_MAX=$3FFFFFFFFFFFFFFF
#QUIC_PACKET_INITIAL=0
#QUIC_PACKET_EARLY=1
#QUIC_PACKET_HANDSHAKE=2
#QUIC_PACKET_RETRY=3
#QUIC_PACKET_SHORT=4
#QUIC_PACKET_NEGOTIATION=5

; Decode one complete integer, accepting nonminimal widths. On failure the
; destination is unchanged; returns width or negative. No implicit stream state.
Procedure.i QuicIntegerRead(source.i,bytes.i,result.i)
 Define n.i,v.i,i.i
 If bytes<0 Or result=0 Or (bytes>0 And source=0) : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If bytes=0 : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 n=1 << (PeekA(source)>>6)
 If bytes<n : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 v=PeekA(source) & 63
 For i=1 To n-1 : v=(v<<8)|PeekA(source+i) : Next
 PokeI(result,v) : ProcedureReturn n
EndProcedure

Procedure.i QuicIntegerSize(value.i)
 If value<0 Or value>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_WIRE_RANGE : EndIf
 If value<64 : ProcedureReturn 1 : EndIf
 If value<16384 : ProcedureReturn 2 : EndIf
 If value<$40000000 : ProcedureReturn 4 : EndIf
 ProcedureReturn 8
EndProcedure

; width=0 chooses shortest encoding; explicit 1/2/4/8 may be nonminimal.
; Validation precedes all writes, including a too-small output refusal.
Procedure.i QuicIntegerWrite(value.i,width.i,destination.i,capacity.i)
 Define n.i,i.i,prefix.i
 n=QuicIntegerSize(value) : If n<0 : ProcedureReturn n : EndIf
 If width=0 : width=n : EndIf
 If width<>1 And width<>2 And width<>4 And width<>8 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If width<n : ProcedureReturn #QUIC_WIRE_RANGE : EndIf
 If destination=0 Or capacity<0 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If capacity<width : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 prefix=0
 If width=2 : prefix=64 : EndIf
 If width=4 : prefix=128 : EndIf
 If width=8 : prefix=192 : EndIf
 For i=width-1 To 0 Step -1
  PokeA(destination+i,value & 255) : value=value>>8
 Next
 PokeA(destination,PeekA(destination)|prefix)
 ProcedureReturn width
EndProcedure

Structure QuicPacketHeader
 first.i
 version.i
 kind.i
 destinationOffset.i
 destinationBytes.i
 sourceOffset.i
 sourceBytes.i
 tokenOffset.i
 tokenBytes.i
 numberOffset.i
 protectedBytes.i
 packetBytes.i
 versionsOffset.i
 versionsCount.i
EndStructure

; Parses one packet inside a complete UDP datagram. packetBytes advances past
; length-delimited long packets; short/Retry/VN consume the rest. Offsets refer
; to source, whose lifetime remains the caller's. Outputs valid ONLY on return1.
; Unknown versions expose only the invariant IDs/version and return VERSION.
; shortIdBytes is supplied by the connection, never guessed from the packet.
Procedure.i QuicPacketRead(*h.QuicPacketHeader,source.i,bytes.i,shortIdBytes.i)
 Define i.i,at.i,n.i,rc.i,v.i
 If *h=0 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 For i=0 To SizeOf(QuicPacketHeader)-1 : PokeA(*h+i,0) : Next
 If bytes<0 Or (bytes>0 And source=0) Or shortIdBytes<0 Or shortIdBytes>20 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If bytes<1 : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 *h\first=PeekA(source)
 If (*h\first & 128)=0
  If (*h\first & 64)=0 : ProcedureReturn #QUIC_WIRE_FORMAT : EndIf
  at=1+shortIdBytes
  If bytes<at Or bytes-at<20 : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
  *h\version=1 : *h\kind=#QUIC_PACKET_SHORT
  *h\destinationOffset=1 : *h\destinationBytes=shortIdBytes
  *h\numberOffset=at : *h\protectedBytes=bytes-at : *h\packetBytes=bytes
  ProcedureReturn 1
 EndIf
 If bytes<7 : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 *h\version=NetReadBE32(source+1)
 n=PeekA(source+5) : at=6
 If *h\version=1 And n>20 : ProcedureReturn #QUIC_WIRE_FORMAT : EndIf
 If n>=bytes-at : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 *h\destinationOffset=at : *h\destinationBytes=n : at=at+n
 n=PeekA(source+at) : at=at+1
 If *h\version=1 And n>20 : ProcedureReturn #QUIC_WIRE_FORMAT : EndIf
 If n>bytes-at : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 *h\sourceOffset=at : *h\sourceBytes=n : at=at+n
 If *h\version=0
  n=bytes-at
  If n=0 Or (n % 4)<>0 : ProcedureReturn #QUIC_WIRE_FORMAT : EndIf
  *h\kind=#QUIC_PACKET_NEGOTIATION : *h\versionsOffset=at : *h\versionsCount=n/4 : *h\packetBytes=bytes
  ProcedureReturn 1
 EndIf
 If *h\version<>1 : ProcedureReturn #QUIC_WIRE_VERSION : EndIf
 If (*h\first & 64)=0 : ProcedureReturn #QUIC_WIRE_FORMAT : EndIf
 *h\kind=(*h\first>>4) & 3
 If *h\kind=#QUIC_PACKET_RETRY
  If bytes-at<=16 : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
  *h\tokenOffset=at : *h\tokenBytes=bytes-at-16 : *h\packetBytes=bytes
  ProcedureReturn 1
 EndIf
 If *h\kind=#QUIC_PACKET_INITIAL
  rc=QuicIntegerRead(source+at,bytes-at,@v) : If rc<0 : ProcedureReturn rc : EndIf
  at=at+rc
  If v>bytes-at : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
  *h\tokenOffset=at : *h\tokenBytes=v : at=at+v
 EndIf
 rc=QuicIntegerRead(source+at,bytes-at,@v) : If rc<0 : ProcedureReturn rc : EndIf
 at=at+rc
 If v>bytes-at : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 ; Header protection samples 16 bytes starting four bytes after numberOffset.
 If v<20 : ProcedureReturn #QUIC_WIRE_FORMAT : EndIf
 *h\numberOffset=at : *h\protectedBytes=v : *h\packetBytes=at+v
 ProcedureReturn 1
EndProcedure

; Reconstruct after header unmasking, using only an authenticated largest number
; (-1 before the first). The caller still must authenticate the reconstructed PN.
Procedure.i QuicPacketNumberRead(truncated.i,width.i,largest.i,result.i)
 Define span.i,half.i,expected.i,candidate.i
 If result=0 Or width<1 Or width>4 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If largest< -1 Or largest>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_WIRE_RANGE : EndIf
 span=1 << (width*8) : half=span/2
 If truncated<0 Or truncated>=span : ProcedureReturn #QUIC_WIRE_RANGE : EndIf
 expected=largest+1 : candidate=(expected & (~(span-1))) | truncated
 If expected-candidate>=half And candidate<=#QUIC_INTEGER_MAX-span
  candidate=candidate+span
 ElseIf candidate-expected>half And candidate>=span
  candidate=candidate-span
 EndIf
 If candidate>#QUIC_INTEGER_MAX : ProcedureReturn #QUIC_WIRE_RANGE : EndIf
 PokeI(result,candidate) : ProcedureReturn 1
EndProcedure

Structure QuicLongPacketSpec
 kind.i
 destination.i
 destinationBytes.i
 source.i
 sourceBytes.i
 token.i
 tokenBytes.i
 number.i
 numberBytes.i
 cipherBytes.i
EndStructure

; Writes an unprotected v1 Initial/0-RTT/Handshake header INCLUDING PN.
; cipherBytes includes the 16-byte AEAD tag. Caller adds encrypted payload,
; authenticates this header as AAD, then applies header protection. Source IDs
; and token must not overlap destination. Errors leave destination untouched.
Procedure.i QuicLongPacketWrite(*s.QuicLongPacketSpec,destination.i,capacity.i)
 Define total.i,encoded.i,tokenWidth.i,at.i,i.i,limit.i
 If *s=0 Or destination=0 Or capacity<0 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If *s\kind<0 Or *s\kind>2 Or *s\destinationBytes<0 Or *s\destinationBytes>20 Or *s\sourceBytes<0 Or *s\sourceBytes>20 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If (*s\destinationBytes>0 And *s\destination=0) Or (*s\sourceBytes>0 And *s\source=0) Or (*s\tokenBytes>0 And *s\token=0) : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If *s\tokenBytes<0 Or *s\tokenBytes>#QUIC_INTEGER_MAX Or (*s\kind<>0 And *s\tokenBytes<>0) : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 If *s\numberBytes<1 Or *s\numberBytes>4 : ProcedureReturn #QUIC_WIRE_ARGUMENT : EndIf
 limit=1 << (*s\numberBytes*8)
 If *s\number<0 Or *s\number>=limit Or *s\cipherBytes<16 Or *s\cipherBytes>#QUIC_INTEGER_MAX-*s\numberBytes : ProcedureReturn #QUIC_WIRE_RANGE : EndIf
 If *s\cipherBytes+*s\numberBytes<20 : ProcedureReturn #QUIC_WIRE_RANGE : EndIf
 encoded=QuicIntegerSize(*s\cipherBytes+*s\numberBytes)
 total=7+*s\destinationBytes+*s\sourceBytes+encoded+*s\numberBytes
 If *s\kind=0
  tokenWidth=QuicIntegerSize(*s\tokenBytes)
  total=total+tokenWidth+*s\tokenBytes
 EndIf
 If total>capacity : ProcedureReturn #QUIC_WIRE_TRUNCATED : EndIf
 PokeA(destination,192|(*s\kind<<4)|(*s\numberBytes-1)) : NetWriteBE32(destination+1,1)
 PokeA(destination+5,*s\destinationBytes) : at=6
 For i=0 To *s\destinationBytes-1 : PokeA(destination+at+i,PeekA(*s\destination+i)) : Next
 at=at+*s\destinationBytes : PokeA(destination+at,*s\sourceBytes) : at=at+1
 For i=0 To *s\sourceBytes-1 : PokeA(destination+at+i,PeekA(*s\source+i)) : Next
 at=at+*s\sourceBytes
 If *s\kind=0
  QuicIntegerWrite(*s\tokenBytes,tokenWidth,destination+at,tokenWidth) : at=at+tokenWidth
  For i=0 To *s\tokenBytes-1 : PokeA(destination+at+i,PeekA(*s\token+i)) : Next
  at=at+*s\tokenBytes
 EndIf
 QuicIntegerWrite(*s\cipherBytes+*s\numberBytes,encoded,destination+at,encoded) : at=at+encoded
 For i=*s\numberBytes-1 To 0 Step -1
  PokeA(destination+at+i,(*s\number >> (8*(*s\numberBytes-1-i))) & 255)
 Next
 ProcedureReturn at+*s\numberBytes
EndProcedure
