; Incremental client-side WebSocket framing, independent of TCP/TLS/board code.
; RFC 6455 sections 5-8, https://www.rfc-editor.org/rfc/rfc6455.txt.
; Protocol facts only; no implementation copied. No extensions negotiated.
; The caller supplies disjoint context, 125-byte control and output buffers.
; Data can precede a later validation failure: commit messages only at FIN.
#WS_ARGUMENT=-600
#WS_PROTOCOL=-601
#WS_LIMIT=-602
#WS_UTF8=-603
#WS_CLOSED=-604
#WS_INCOMPLETE=-605
Structure WebSocketFrame
  state.i
  error.i
  headerBytes.i
  lengthBytes.i
  lengthMarker.i
  length.i
  remaining.i
  opcode.i
  fin.i
  active.i
  messageKind.i
  messageBytes.i
  messageLimit.i
  control.i
  controlLength.i
  utfNeed.i
  utfValue.i
  utfMinimum.i
  consumed.i
  written.i
EndStructure

Procedure.i wsFrameFail(*s.WebSocketFrame,code.i)
  *s\error=code : *s\state=-1 : ProcedureReturn code
EndProcedure

Procedure.i wsUtfByte(*s.WebSocketFrame,c.i)
  If *s\utfNeed=0
    If c<128 : ProcedureReturn 0 : EndIf
    If c>=194 And c<=223
      *s\utfNeed=1 : *s\utfValue=c & 31 : *s\utfMinimum=128
    ElseIf c>=224 And c<=239
      *s\utfNeed=2 : *s\utfValue=c & 15 : *s\utfMinimum=2048
    ElseIf c>=240 And c<=244
      *s\utfNeed=3 : *s\utfValue=c & 7 : *s\utfMinimum=65536
    Else
      ProcedureReturn #WS_UTF8
    EndIf
  Else
    If c<128 Or c>191 : ProcedureReturn #WS_UTF8 : EndIf
    *s\utfValue=(*s\utfValue<<6)|(c & 63) : *s\utfNeed=*s\utfNeed-1
    If *s\utfNeed=0
      If *s\utfValue<*s\utfMinimum Or *s\utfValue>$10FFFF Or (*s\utfValue>=$D800 And *s\utfValue<=$DFFF)
        ProcedureReturn #WS_UTF8
      EndIf
    EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i wsUtfSpan(p.i,n.i)
  Define s.WebSocketFrame,i.i,rc.i
  s\utfNeed=0 : s\utfValue=0 : s\utfMinimum=0
  For i=0 To n-1
    rc=wsUtfByte(@s,PeekA(p+i) & 255) : If rc<0 : ProcedureReturn rc : EndIf
  Next
  If s\utfNeed<>0 : ProcedureReturn #WS_UTF8 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i wsClosePayload(p.i,n.i)
  Define code.i
  If n=0 : ProcedureReturn 0 : EndIf
  If n=1 : ProcedureReturn #WS_PROTOCOL : EndIf
  code=((PeekA(p) & 255)<<8)|(PeekA(p+1) & 255)
  If code<1000 Or code>=5000 Or (code>=1015 And code<3000) Or code=1004 Or code=1005 Or code=1006
    ProcedureReturn #WS_PROTOCOL
  EndIf
  ProcedureReturn wsUtfSpan(p+2,n-2)
EndProcedure

Procedure.i WebSocketFrameInit(*s.WebSocketFrame,control.i,limit.i)
  Define i.i
  If *s=0 : ProcedureReturn #WS_ARGUMENT : EndIf
  For i=0 To SizeOf(WebSocketFrame)-SizeOf(.i) Step SizeOf(.i) : PokeI(*s+i,0) : Next
  If control=0 Or limit<1 : ProcedureReturn wsFrameFail(*s,#WS_ARGUMENT) : EndIf
  *s\control=control : *s\messageLimit=limit
  ProcedureReturn 0
EndProcedure

Procedure.i wsFrameReady(*s.WebSocketFrame)
  If (*s\lengthMarker=126 And *s\length<126) Or (*s\lengthMarker=127 And *s\length<65536)
    ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL)
  EndIf
  If *s\opcode>=8
    If *s\length>125 Or *s\fin=0 : ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL) : EndIf
  Else
    If *s\length>*s\messageLimit-*s\messageBytes : ProcedureReturn wsFrameFail(*s,#WS_LIMIT) : EndIf
    *s\messageBytes=*s\messageBytes+*s\length
  EndIf
  *s\remaining=*s\length : *s\state=2
  ProcedureReturn 0
EndProcedure

Procedure.i wsFrameEnd(*s.WebSocketFrame)
  Define rc.i
  If *s\opcode=8
    rc=wsClosePayload(*s\control,*s\controlLength)
    If rc<0 : ProcedureReturn wsFrameFail(*s,rc) : EndIf
    *s\state=4 : ProcedureReturn 1
  EndIf
  If *s\opcode<8 And *s\fin
    If *s\messageKind=1 And *s\utfNeed<>0 : ProcedureReturn wsFrameFail(*s,#WS_UTF8) : EndIf
    *s\active=0
  EndIf
  *s\state=3 : ProcedureReturn 1
EndProcedure

; Returns 1 at exactly one frame boundary, zero for more input/output space,
; negative on error. Control frames go to control/controlLength, data to output.
; Call Next only after consuming the event, including any required Pong response.
Procedure.i WebSocketFrameFeed(*s.WebSocketFrame,source.i,bytes.i,output.i,capacity.i)
  Define c.i,rc.i,i.i
  If *s=0 : ProcedureReturn #WS_ARGUMENT : EndIf
  *s\consumed=0 : *s\written=0
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state=3 Or *s\state=4 : ProcedureReturn 1 : EndIf
  If bytes<0 Or capacity<0 Or (bytes>0 And source=0) Or (capacity>0 And output=0)
    ProcedureReturn wsFrameFail(*s,#WS_ARGUMENT)
  EndIf
  Repeat
    If *s\state=2 And *s\remaining=0 : ProcedureReturn wsFrameEnd(*s) : EndIf
    If i=bytes : ProcedureReturn 0 : EndIf
    If *s\state=2 And *s\opcode<8 And *s\written=capacity : ProcedureReturn 0 : EndIf
    c=PeekA(source+i) & 255 : i=i+1 : *s\consumed=i
    If *s\state=0
      If *s\headerBytes=0
        If (c & 112)<>0 : ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL) : EndIf
        *s\opcode=c & 15 : *s\fin=(c>>7) & 1
        If *s\opcode<>0 And *s\opcode<>1 And *s\opcode<>2 And *s\opcode<>8 And *s\opcode<>9 And *s\opcode<>10
          ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL)
        EndIf
        If *s\opcode=0
          If *s\active=0 : ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL) : EndIf
          *s\messageKind=*s\active
        ElseIf *s\opcode<8
          If *s\active<>0 : ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL) : EndIf
          *s\active=*s\opcode : *s\messageKind=*s\opcode : *s\messageBytes=0
          *s\utfNeed=0 : *s\utfValue=0 : *s\utfMinimum=0
        EndIf
        *s\headerBytes=1
      Else
        ; Servers must not mask. No mask bytes are consumed as payload.
        If (c & 128)<>0 : ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL) : EndIf
        *s\lengthMarker=c : *s\length=c : *s\headerBytes=2
        If c<126
          rc=wsFrameReady(*s) : If rc<0 : ProcedureReturn rc : EndIf
        Else
          If *s\opcode>=8 : ProcedureReturn wsFrameFail(*s,#WS_PROTOCOL) : EndIf
          *s\length=0 : *s\state=1 : *s\lengthBytes=2
          If c=127 : *s\lengthBytes=8 : EndIf
        EndIf
      EndIf
    ElseIf *s\state=1
      If *s\length>($7FFFFFFFFFFFFFFF-c)/256 : ProcedureReturn wsFrameFail(*s,#WS_LIMIT) : EndIf
      *s\length=*s\length*256+c : *s\lengthBytes=*s\lengthBytes-1
      If *s\lengthBytes=0
        rc=wsFrameReady(*s) : If rc<0 : ProcedureReturn rc : EndIf
      EndIf
    Else
      If *s\opcode>=8
        PokeA(*s\control+*s\controlLength,c) : *s\controlLength=*s\controlLength+1
      Else
        If *s\messageKind=1
          rc=wsUtfByte(*s,c) : If rc<0 : ProcedureReturn wsFrameFail(*s,rc) : EndIf
        EndIf
        PokeA(output+*s\written,c) : *s\written=*s\written+1
      EndIf
      *s\remaining=*s\remaining-1
    EndIf
  ForEver
EndProcedure

Procedure.i WebSocketFrameNext(*s.WebSocketFrame)
  If *s=0 : ProcedureReturn #WS_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state=4 : ProcedureReturn #WS_CLOSED : EndIf
  If *s\state<>3 : ProcedureReturn #WS_ARGUMENT : EndIf
  *s\state=0 : *s\headerBytes=0 : *s\lengthBytes=0 : *s\lengthMarker=0
  *s\length=0 : *s\remaining=0 : *s\controlLength=0
  ProcedureReturn 0
EndProcedure

Procedure.i WebSocketFrameEof(*s.WebSocketFrame)
  If *s=0 : ProcedureReturn #WS_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state=4 : ProcedureReturn 0 : EndIf
  ProcedureReturn wsFrameFail(*s,#WS_INCOMPLETE)
EndProcedure

; Encode one complete client frame. mask points to FOUR FRESH UNPREDICTABLE
; bytes supplied by the caller's cryptographic RNG, never a counter/fixed key.
; The source/mask/output buffers must not overlap. No extension or fragmentation.
Procedure.i WebSocketFrameEncode(opcode.i,source.i,bytes.i,mask.i,output.i,capacity.i)
  Define h.i,i.i,rc.i
  If bytes<0 Or mask=0 Or output=0 Or capacity<6 Or (bytes>0 And source=0) : ProcedureReturn #WS_ARGUMENT : EndIf
  If opcode<>1 And opcode<>2 And opcode<>8 And opcode<>9 And opcode<>10 : ProcedureReturn #WS_PROTOCOL : EndIf
  If opcode>=8 And bytes>125 : ProcedureReturn #WS_PROTOCOL : EndIf
  h=6 : If bytes>=126 : h=8 : EndIf : If bytes>=65536 : h=14 : EndIf
  If bytes>capacity-h : ProcedureReturn #WS_LIMIT : EndIf
  If opcode=1 : rc=wsUtfSpan(source,bytes) : If rc<0 : ProcedureReturn rc : EndIf : EndIf
  If opcode=8 : rc=wsClosePayload(source,bytes) : If rc<0 : ProcedureReturn rc : EndIf : EndIf
  PokeA(output,128|opcode)
  If h=6
    PokeA(output+1,128|bytes)
  ElseIf h=8
    PokeA(output+1,254) : PokeA(output+2,(bytes>>8) & 255) : PokeA(output+3,bytes & 255)
  Else
    PokeA(output+1,255)
    For i=0 To 7 : PokeA(output+2+i,(bytes>>(56-i*8)) & 255) : Next
  EndIf
  For i=0 To 3 : PokeA(output+h-4+i,PeekA(mask+i)) : Next
  For i=0 To bytes-1 : PokeA(output+h+i,(PeekA(source+i) ! PeekA(mask+(i & 3))) & 255) : Next
  ProcedureReturn h+bytes
EndProcedure
