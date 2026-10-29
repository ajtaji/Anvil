; Bounded HTTP/1.1 request serialization, shared by TCP and TLS callers.
; RFC 9110 sections 7-9; RFC 9112 sections 3, 6 and 7. No transport calls.
; The caller retains input until consumed; short output capacity never loses it.
XIncludeFile "Anvil/Network/web_url.pbi"
#WEB_REQUEST_ARGUMENT=-540
#WEB_REQUEST_SYNTAX=-541
#WEB_REQUEST_LIMIT=-542
#WEB_REQUEST_STATE=-543
#WEB_REQUEST_LENGTH=-544
Structure WebRequest
  headers.i
  capacity.i
  length.i
  offset.i
  remaining.i
  chunked.i
  state.i
  error.i
  consumed.i
  written.i
  frameValue.i
  frameDivisor.i
  frameRemaining.i
  framePhase.i
  ending.i
EndStructure

Procedure.i wqFail(*s.WebRequest,error.i)
  *s\error=error : *s\state=-1 : ProcedureReturn error
EndProcedure

Procedure.i wqToken(c.i)
  If (c>=48 And c<=57) Or (c>=65 And c<=90) Or (c>=97 And c<=122) : ProcedureReturn 1 : EndIf
  If c=33 Or c=35 Or c=36 Or c=37 Or c=38 Or c=39 Or c=42 Or c=43 Or c=45 Or c=46 Or c=94 Or c=95 Or c=96 Or c=124 Or c=126 : ProcedureReturn 1 : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i wqEqual(p.i,n.i,text.i)
  Define i.i
  For i=0 To n-1
    If PeekA(text+i)=0 Or webUrlLower(PeekA(p+i) & 255)<>PeekA(text+i) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn Bool(PeekA(text+n)=0)
EndProcedure

Procedure wqByte(*s.WebRequest,c.i)
  If *s\error<0 : ProcedureReturn : EndIf
  If *s\length>=*s\capacity : wqFail(*s,#WEB_REQUEST_LIMIT) : ProcedureReturn : EndIf
  PokeA(*s\headers+*s\length,c) : *s\length=*s\length+1
EndProcedure

Procedure wqText(*s.WebRequest,text.i)
  Define i.i
  While PeekA(text+i)<>0 And *s\error=0
    wqByte(*s,PeekA(text+i)) : i=i+1
  Wend
EndProcedure

Procedure wqDecimal(*s.WebRequest,value.i)
  Define divisor.i,digit.i
  divisor=1
  While value/divisor>=10 : divisor=divisor*10 : Wend
  While divisor>0
    digit=(value/divisor) % 10 : wqByte(*s,48+digit) : divisor=divisor/10
  Wend
EndProcedure

; A bodyLength of -1 selects chunked upload; otherwise exactly that many bytes
; must be consumed. URL storage must remain valid through this call only.
; States: 0 adding fields, 1 streaming, 2 finished, -1 refused.
Procedure.i WebRequestInit(*s.WebRequest,*url.WebUrl,method.i,methodLength.i,bodyLength.i,keepAlive.i,headers.i,capacity.i)
  Define i.i,c.i
  If *s=0 : ProcedureReturn #WEB_REQUEST_ARGUMENT : EndIf
  For i=0 To SizeOf(WebRequest)-1 : PokeA(*s+i,0) : Next
  If *url=0 Or method=0 Or methodLength<1 Or methodLength>32 Or bodyLength< -1 Or headers=0 Or capacity<128 Or capacity>32768
    ProcedureReturn wqFail(*s,#WEB_REQUEST_ARGUMENT)
  EndIf
  If *url\host=0 Or *url\target=0 Or *url\hostLength<1 Or *url\hostLength>=#WEB_URL_HOST Or *url\targetLength<1 Or *url\targetLength>=#WEB_URL_TARGET Or *url\port<1 Or *url\port>65535
    ProcedureReturn wqFail(*s,#WEB_REQUEST_ARGUMENT)
  EndIf
  For i=0 To methodLength-1
    If wqToken(PeekA(method+i) & 255)=0 : ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX) : EndIf
  Next
  ; CONNECT needs authority-form and tunnel ownership, not origin-form.
  If wqEqual(method,methodLength,"connect") : ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX) : EndIf
  For i=0 To *url\hostLength-1
    c=PeekA(*url\host+i) & 255
    If c<=32 Or c>=127 Or c=58 Or c=47 : ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX) : EndIf
  Next
  If PeekA(*url\target)<>47 : ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX) : EndIf
  For i=0 To *url\targetLength-1
    c=PeekA(*url\target+i) & 255
    If c<=32 Or c>=127 Or c=35 : ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX) : EndIf
  Next
  *s\headers=headers : *s\capacity=capacity : *s\remaining=bodyLength : *s\chunked=Bool(bodyLength= -1)
  For i=0 To methodLength-1 : wqByte(*s,PeekA(method+i)) : Next
  wqByte(*s,32)
  For i=0 To *url\targetLength-1 : wqByte(*s,PeekA(*url\target+i)) : Next
  wqText(*s," HTTP/1.1") : wqByte(*s,13) : wqByte(*s,10)
  wqText(*s,"Host: ")
  For i=0 To *url\hostLength-1 : wqByte(*s,PeekA(*url\host+i)) : Next
  If *url\explicitPort : wqByte(*s,58) : wqDecimal(*s,*url\port) : EndIf
  wqByte(*s,13) : wqByte(*s,10)
  If *s\chunked
    wqText(*s,"Transfer-Encoding: chunked")
    wqByte(*s,13) : wqByte(*s,10)
  ElseIf bodyLength<>0 Or (wqEqual(method,methodLength,"get")=0 And wqEqual(method,methodLength,"head")=0)
    wqText(*s,"Content-Length: ") : wqDecimal(*s,bodyLength)
    wqByte(*s,13) : wqByte(*s,10)
  EndIf
  If keepAlive=0
    wqText(*s,"Connection: close") : wqByte(*s,13) : wqByte(*s,10)
  EndIf
  ProcedureReturn *s\error
EndProcedure

; Header name/value are explicit byte spans. Framing and connection control
; belong to the serializer and cannot be injected or duplicated by the caller.
Procedure.i WebRequestHeader(*s.WebRequest,name.i,nameLength.i,value.i,valueLength.i)
  Define i.i,c.i
  If *s=0 : ProcedureReturn #WEB_REQUEST_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state<>0 : ProcedureReturn wqFail(*s,#WEB_REQUEST_STATE) : EndIf
  If name=0 Or nameLength<1 Or nameLength>256 Or valueLength<0 Or valueLength>8192 Or (valueLength>0 And value=0)
    ProcedureReturn wqFail(*s,#WEB_REQUEST_ARGUMENT)
  EndIf
  For i=0 To nameLength-1
    If wqToken(PeekA(name+i) & 255)=0 : ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX) : EndIf
  Next
  If wqEqual(name,nameLength,"host") Or wqEqual(name,nameLength,"content-length") Or wqEqual(name,nameLength,"transfer-encoding") Or wqEqual(name,nameLength,"connection") Or wqEqual(name,nameLength,"expect") Or wqEqual(name,nameLength,"upgrade")
    ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX)
  EndIf
  For i=0 To valueLength-1
    c=PeekA(value+i) & 255
    If (c<32 And c<>9) Or c=127 : ProcedureReturn wqFail(*s,#WEB_REQUEST_SYNTAX) : EndIf
  Next
  If nameLength+valueLength+4>*s\capacity-*s\length : ProcedureReturn wqFail(*s,#WEB_REQUEST_LIMIT) : EndIf
  For i=0 To nameLength-1 : wqByte(*s,PeekA(name+i)) : Next
  wqText(*s,": ")
  For i=0 To valueLength-1 : wqByte(*s,PeekA(value+i)) : Next
  wqByte(*s,13) : wqByte(*s,10)
  ProcedureReturn *s\error
EndProcedure

Procedure.i WebRequestFinishHeaders(*s.WebRequest)
  If *s=0 : ProcedureReturn #WEB_REQUEST_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state<>0 : ProcedureReturn wqFail(*s,#WEB_REQUEST_STATE) : EndIf
  wqByte(*s,13) : wqByte(*s,10)
  If *s\error=0 : *s\state=1 : EndIf
  ProcedureReturn *s\error
EndProcedure

; Returns output byte count. Advance body by consumed, send written bytes,
; then call again. endBody asserts that the supplied span is the final span;
; repeat that assertion while draining output. capacity zero is backpressure.
Procedure.i WebRequestOutput(*s.WebRequest,body.i,bytes.i,endBody.i,destination.i,capacity.i)
  Define c.i,n.i,digit.i
  If *s=0 : ProcedureReturn #WEB_REQUEST_ARGUMENT : EndIf
  *s\consumed=0 : *s\written=0
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If bytes<0 Or capacity<0 Or (bytes>0 And body=0) Or (capacity>0 And destination=0) : ProcedureReturn wqFail(*s,#WEB_REQUEST_ARGUMENT) : EndIf
  If *s\state=2
    If bytes>0 : ProcedureReturn wqFail(*s,#WEB_REQUEST_LENGTH) : EndIf
    ProcedureReturn 0
  EndIf
  If *s\state<>1 : ProcedureReturn wqFail(*s,#WEB_REQUEST_STATE) : EndIf
  If *s\chunked=0 And bytes>*s\remaining : ProcedureReturn wqFail(*s,#WEB_REQUEST_LENGTH) : EndIf
  While *s\written<capacity And *s\state=1
    c=-1
    If *s\offset<*s\length
      c=PeekA(*s\headers+*s\offset) : *s\offset=*s\offset+1
    ElseIf *s\chunked=0
      If *s\remaining=0 : *s\state=2 : Break : EndIf
      If *s\consumed=bytes
        If endBody : ProcedureReturn wqFail(*s,#WEB_REQUEST_LENGTH) : EndIf
        Break
      EndIf
      c=PeekA(body+*s\consumed) : *s\consumed=*s\consumed+1 : *s\remaining=*s\remaining-1
    Else
      Select *s\framePhase
        Case 0
          n=bytes-*s\consumed
          If n=0 And endBody=0 : Break : EndIf
          If n>16384 : n=16384 : EndIf
          *s\ending=Bool(n=0) : *s\frameValue=n : *s\frameRemaining=n : *s\frameDivisor=1
          While n / *s\frameDivisor>=16 : *s\frameDivisor=*s\frameDivisor*16 : Wend
          *s\framePhase=1
        Case 1
          digit=(*s\frameValue / *s\frameDivisor) % 16
          c=48+digit : If digit>9 : c=87+digit : EndIf
          *s\frameDivisor=*s\frameDivisor/16
          If *s\frameDivisor=0 : *s\framePhase=2 : EndIf
        Case 2
          c=13 : *s\framePhase=3
        Case 3
          c=10 : *s\framePhase=4
        Case 4
          If *s\frameRemaining=0
            *s\framePhase=5
          Else
            If *s\consumed=bytes
              If endBody : ProcedureReturn wqFail(*s,#WEB_REQUEST_LENGTH) : EndIf
              Break
            EndIf
            c=PeekA(body+*s\consumed) : *s\consumed=*s\consumed+1 : *s\frameRemaining=*s\frameRemaining-1
          EndIf
        Case 5
          c=13 : *s\framePhase=6
        Case 6
          c=10 : *s\framePhase=0
          If *s\ending : *s\state=2 : EndIf
      EndSelect
    EndIf
    If c>=0
      PokeA(destination+*s\written,c) : *s\written=*s\written+1
    EndIf
  Wend
  ; A full output buffer can end exactly at the known-length boundary.
  If *s\chunked=0 And *s\offset=*s\length And *s\remaining=0 : *s\state=2 : EndIf
  ProcedureReturn *s\written
EndProcedure
