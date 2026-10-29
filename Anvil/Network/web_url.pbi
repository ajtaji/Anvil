; Bounded HTTP(S) URL decomposition for the shared web client.
; RFC 3986 sections 3.1-3.5; RFC 9110 sections 4.2 and 7.1.
; Input is an explicit byte span, not an implicitly readable C string.
; Keeps escaped path/query bytes, excludes fragments, and emits origin-form.
; No DNS, allocation or transport calls. Caller owns output and serialization.
; IPv6 literals and international host conversion require transport/resolver
; support; currently refused explicitly, never mistaken for a host/port pair.
#WEB_URL_OK = 0
#WEB_URL_ARGUMENT = -500
#WEB_URL_SCHEME = -501
#WEB_URL_AUTHORITY = -502
#WEB_URL_PORT = -503
#WEB_URL_SYNTAX = -504
#WEB_URL_CAPACITY = -505
#WEB_URL_HOST_UNSUPPORTED = -506
#WEB_URL_LIMIT = 4096
#WEB_URL_HOST = 256
#WEB_URL_TARGET = 3072
Structure WebUrl
  secure.i
  port.i
  explicitPort.i
  hostLength.i
  targetLength.i
  host.i
  target.i
  hostCapacity.i
  targetCapacity.i
EndStructure

Procedure.i webUrlLower(c.i)
  If c>=65 And c<=90 : ProcedureReturn c+32 : EndIf
  ProcedureReturn c
EndProcedure

Procedure.i webUrlHex(c.i)
  c=webUrlLower(c)
  ProcedureReturn Bool((c>=48 And c<=57) Or (c>=97 And c<=102))
EndProcedure

; defaultSecure selects the scheme for a bare host, preserving monitor syntax.
; Explicit schemes are checked completely and case-insensitively.
; Caller supplies separate writable host/target buffers and capacities.
; Output is usable only after a zero return; lengths are cleared on entry.
Procedure.i WebUrlParse(*input,bytes.i,defaultSecure.i,*out.WebUrl)
  Define i.i,c.i,start.i,finish.i,colon.i,port.i,digits.i,target.i,label.i
  If *out=0 : ProcedureReturn #WEB_URL_ARGUMENT : EndIf
  *out\hostLength=0 : *out\targetLength=0 : *out\explicitPort=0
  If *out\host=0 Or *out\target=0 Or *out\hostCapacity<2 Or *out\targetCapacity<2
    ProcedureReturn #WEB_URL_ARGUMENT
  EndIf
  PokeA(*out\host,0) : PokeA(*out\target,0)
  If *input=0 Or bytes<1 Or bytes>#WEB_URL_LIMIT Or (defaultSecure<>0 And defaultSecure<>1)
    ProcedureReturn #WEB_URL_ARGUMENT
  EndIf
  ; No raw whitespace, controls, backslash or non-ASCII bytes in a URI.
  ; Percent escapes remain escaped; decoding them here changes URI structure.
  For i=0 To bytes-1
    c=PeekA(*input+i) & 255
    If c<=32 Or c>=127 Or c=92 Or c=34 Or c=60 Or c=62 Or c=96 Or c=123 Or c=125 Or c=124 Or c=94
      ProcedureReturn #WEB_URL_SYNTAX
    EndIf
    If c=37
      If i+2>=bytes : ProcedureReturn #WEB_URL_SYNTAX : EndIf
      If webUrlHex(PeekA(*input+i+1) & 255)=0 Or webUrlHex(PeekA(*input+i+2) & 255)=0
        ProcedureReturn #WEB_URL_SYNTAX
      EndIf
    EndIf
  Next
  *out\secure=defaultSecure : start=0
  For i=0 To bytes-3
    If PeekA(*input+i)=58 And PeekA(*input+i+1)=47 And PeekA(*input+i+2)=47
      If i<>4 And i<>5 : ProcedureReturn #WEB_URL_SCHEME : EndIf
      If webUrlLower(PeekA(*input))<>104 Or webUrlLower(PeekA(*input+1))<>116 Or webUrlLower(PeekA(*input+2))<>116 Or webUrlLower(PeekA(*input+3))<>112
        ProcedureReturn #WEB_URL_SCHEME
      EndIf
      If i=5
        If webUrlLower(PeekA(*input+4))<>115 : ProcedureReturn #WEB_URL_SCHEME : EndIf
        *out\secure=1
      Else
        *out\secure=0
      EndIf
      start=i+3 : Break
    EndIf
    If PeekA(*input+i)=47 Or PeekA(*input+i)=63 Or PeekA(*input+i)=35 : Break : EndIf
  Next
  *out\port=80 : If *out\secure<>0 : *out\port=443 : EndIf
  finish=start
  While finish<bytes
    c=PeekA(*input+finish)
    If c=47 Or c=63 Or c=35 : Break : EndIf
    finish=finish+1
  Wend
  If finish=start : ProcedureReturn #WEB_URL_AUTHORITY : EndIf
  If PeekA(*input+start)=91 : ProcedureReturn #WEB_URL_HOST_UNSUPPORTED : EndIf
  colon=finish : label=0
  For i=start To finish-1
    c=PeekA(*input+i)
    If c=58 : colon=i : Break : EndIf
    If c=46
      If label=0 Or PeekA(*input+i-1)=45 : ProcedureReturn #WEB_URL_AUTHORITY : EndIf
      label=0
    Else
      If (c<48 Or c>57) And (webUrlLower(c)<97 Or webUrlLower(c)>122) And c<>45
        ProcedureReturn #WEB_URL_AUTHORITY
      EndIf
      If c=45 And label=0 : ProcedureReturn #WEB_URL_AUTHORITY : EndIf
      label=label+1
      If label>63 : ProcedureReturn #WEB_URL_AUTHORITY : EndIf
    EndIf
  Next
  If colon=start Or colon-start>=#WEB_URL_HOST : ProcedureReturn #WEB_URL_AUTHORITY : EndIf
  If PeekA(*input+colon-1)=45 : ProcedureReturn #WEB_URL_AUTHORITY : EndIf
  If colon<finish
    port=0 : digits=0
    For i=colon+1 To finish-1
      c=PeekA(*input+i)
      If c<48 Or c>57 : ProcedureReturn #WEB_URL_PORT : EndIf
      port=port*10+c-48 : digits=digits+1
      If port>65535 Or digits>5 : ProcedureReturn #WEB_URL_PORT : EndIf
    Next
    If digits=0 Or port=0 : ProcedureReturn #WEB_URL_PORT : EndIf
    *out\port=port : *out\explicitPort=1
  EndIf
  If colon-start>=*out\hostCapacity : ProcedureReturn #WEB_URL_CAPACITY : EndIf
  For i=start To colon-1 : PokeA(*out\host+i-start,webUrlLower(PeekA(*input+i))) : Next
  *out\hostLength=colon-start : PokeA(*out\host+colon-start,0)
  target=0
  If finish=bytes
    PokeA(*out\target,47) : target=1
  ElseIf PeekA(*input+finish)<>47
    PokeA(*out\target,47) : target=1
  EndIf
  For i=finish To bytes-1
    c=PeekA(*input+i)
    If c=35 : Break : EndIf
    If target>=#WEB_URL_TARGET-1 Or target>=*out\targetCapacity-1 : ProcedureReturn #WEB_URL_CAPACITY : EndIf
    PokeA(*out\target+target,c) : target=target+1
  Next
  PokeA(*out\target+target,0) : *out\targetLength=target
  ProcedureReturn #WEB_URL_OK
EndProcedure
