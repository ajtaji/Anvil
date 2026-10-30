; SPDX-License-Identifier: MIT
; HTTP/2 frame headers and connection preface, independently implemented from
; RFC 9113 sections 3.4, 4 and 6 (protocol facts, no implementation copied).
; https://www.rfc-editor.org/rfc/rfc9113.html
; Only the header is consumed. Payload syntax, CONTINUATION ordering, stream
; state and flow control belong to the connection engine, not this decoder.
XIncludeFile "Anvil/Network/byte_order.pbi"
#H2_FRAME_ARGUMENT=-3201
#H2_FRAME_PROTOCOL=-3202
#H2_FRAME_SIZE=-3203
#H2_FRAME_DEFAULT_MAX=16384
#H2_FRAME_WIRE_MAX=16777215
Structure H2FrameHeader
 length.i
 kind.i
 flags.i
 stream.i
 used.i
 maximum.i
 error.i
 wire0.q
 wire1.q
EndStructure

Procedure.i H2FrameValidate(*h.H2FrameHeader,maximum.i)
 Define minimum.i
 If *h=0 Or maximum<16384 Or maximum>#H2_FRAME_WIRE_MAX : ProcedureReturn #H2_FRAME_ARGUMENT : EndIf
 If *h\length<0 Or *h\length>#H2_FRAME_WIRE_MAX Or *h\kind<0 Or *h\kind>255 Or *h\flags<0 Or *h\flags>255 Or *h\stream<0 Or *h\stream>$7FFFFFFF : ProcedureReturn #H2_FRAME_ARGUMENT : EndIf
 If *h\length>maximum : ProcedureReturn #H2_FRAME_SIZE : EndIf
 If *h\kind=0 Or *h\kind=1 Or *h\kind=2 Or *h\kind=3 Or *h\kind=5 Or *h\kind=9
  If *h\stream=0 : ProcedureReturn #H2_FRAME_PROTOCOL : EndIf
 EndIf
 If *h\kind=4 Or *h\kind=6 Or *h\kind=7
  If *h\stream<>0 : ProcedureReturn #H2_FRAME_PROTOCOL : EndIf
 EndIf
 minimum=0
 Select *h\kind
  Case 0
   If (*h\flags & 8)<>0 : minimum=1 : EndIf
  Case 1
   If (*h\flags & 8)<>0 : minimum=1 : EndIf
   If (*h\flags & 32)<>0 : minimum=minimum+5 : EndIf
  Case 2
   If *h\length<>5 : ProcedureReturn #H2_FRAME_SIZE : EndIf
  Case 3
   If *h\length<>4 : ProcedureReturn #H2_FRAME_SIZE : EndIf
  Case 8
   If *h\length<>4 : ProcedureReturn #H2_FRAME_SIZE : EndIf
  Case 4
   If (*h\length % 6)<>0 : ProcedureReturn #H2_FRAME_SIZE : EndIf
   If (*h\flags & 1)<>0 And *h\length<>0 : ProcedureReturn #H2_FRAME_SIZE : EndIf
  Case 5
   minimum=4
   If (*h\flags & 8)<>0 : minimum=5 : EndIf
  Case 6
   If *h\length<>8 : ProcedureReturn #H2_FRAME_SIZE : EndIf
  Case 7
   minimum=8
 EndSelect
 If *h\length<minimum : ProcedureReturn #H2_FRAME_SIZE : EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i H2FrameInit(*h.H2FrameHeader,maximum.i)
 Define i.i
 If *h=0 : ProcedureReturn #H2_FRAME_ARGUMENT : EndIf
 For i=0 To SizeOf(H2FrameHeader)-1 : PokeA(*h+i,0) : Next
 *h\maximum=maximum
 If maximum<16384 Or maximum>#H2_FRAME_WIRE_MAX : *h\error=#H2_FRAME_ARGUMENT : EndIf
 ProcedureReturn *h\error
EndProcedure

; Returns consumed header bytes, never consumes payload bytes. Inspect used=9
; for a complete header; call Init before the next one. Errors stay latched.
Procedure.i H2FrameFeed(*h.H2FrameHeader,source.i,bytes.i)
 Define take.i,i.i,wire.i
 If *h=0 : ProcedureReturn #H2_FRAME_ARGUMENT : EndIf
 If *h\error<>0 : ProcedureReturn *h\error : EndIf
 If bytes<0 Or (bytes>0 And source=0) Or *h\used<0 Or *h\used>9
  *h\error=#H2_FRAME_ARGUMENT : ProcedureReturn *h\error
 EndIf
 wire=@*h\wire0
 take=9-*h\used : If take>bytes : take=bytes : EndIf
 For i=0 To take-1 : PokeA(wire+*h\used+i,PeekA(source+i)) : Next
 *h\used=*h\used+take
 If *h\used=9
  *h\length=(PeekA(wire+0)<<16)|(PeekA(wire+1)<<8)|PeekA(wire+2)
  *h\kind=PeekA(wire+3) : *h\flags=PeekA(wire+4)
  *h\stream=((PeekA(wire+5) & 127)<<24)|(PeekA(wire+6)<<16)|(PeekA(wire+7)<<8)|PeekA(wire+8)
  *h\error=H2FrameValidate(*h,*h\maximum)
  If *h\error<>0 : ProcedureReturn *h\error : EndIf
 EndIf
 ProcedureReturn take
EndProcedure

; Argument, header semantics and capacity are checked before any output write.
Procedure.i H2FrameWrite(destination.i,capacity.i,bytes.i,kind.i,flags.i,stream.i)
 Define h.H2FrameHeader,rc.i,mask.i
 If destination=0 Or capacity<9 : ProcedureReturn #H2_FRAME_ARGUMENT : EndIf
 h\length=bytes : h\kind=kind : h\flags=flags : h\stream=stream
 rc=H2FrameValidate(@h,#H2_FRAME_WIRE_MAX) : If rc<>0 : ProcedureReturn rc : EndIf
 ; Clear undefined flags for base protocol types. Extension types retain the
 ; caller's flags because their semantics belong to the extension engine.
 mask=255
 Select kind
  Case 0 : mask=9
  Case 1 : mask=45
  Case 2 : mask=0
  Case 3 : mask=0
  Case 4 : mask=1
  Case 5 : mask=8
  Case 6 : mask=1
  Case 7 : mask=0
  Case 8 : mask=0
  Case 9 : mask=4
 EndSelect
 flags=flags & mask
 PokeA(destination,(bytes>>16)&255) : PokeA(destination+1,(bytes>>8)&255) : PokeA(destination+2,bytes&255)
 PokeA(destination+3,kind) : PokeA(destination+4,flags)
 NetWriteBE32(destination+5,stream)
 ProcedureReturn 9
EndProcedure

Procedure.i H2ClientPreface(destination.i,capacity.i)
 Define text.i,i.i
 If destination=0 Or capacity<24 : ProcedureReturn #H2_FRAME_ARGUMENT : EndIf
 text="PRI * HTTP/2.0"
 For i=0 To 13 : PokeA(destination+i,PeekA(text+i)) : Next
 PokeA(destination+14,13) : PokeA(destination+15,10) : PokeA(destination+16,13) : PokeA(destination+17,10)
 PokeA(destination+18,83) : PokeA(destination+19,77)
 PokeA(destination+20,13) : PokeA(destination+21,10) : PokeA(destination+22,13) : PokeA(destination+23,10)
 ProcedureReturn 24
EndProcedure
