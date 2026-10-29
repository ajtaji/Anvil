; Incremental HTTP/1 response framing, independent of TCP/TLS and board code.
; RFC 9112 sections 4-8; RFC 9110 sections 5, 6 and 8. No copied implementation.
; Caller owns context and disjoint line/header/output buffers. Feed consumes
; only reported bytes and stops exactly at message end or output backpressure.
; Strict CRLF, bounded metadata, no ignored/truncated framing fields. Decoded
; transfer bytes are returned; Content-Encoding remains an application concern.
#WEB_RESPONSE_STATUS=0
#WEB_RESPONSE_HEADERS=1
#WEB_RESPONSE_LENGTH=2
#WEB_RESPONSE_CLOSE=3
#WEB_RESPONSE_CHUNK_SIZE=4
#WEB_RESPONSE_CHUNK_DATA=5
#WEB_RESPONSE_CHUNK_CR=6
#WEB_RESPONSE_CHUNK_LF=7
#WEB_RESPONSE_TRAILERS=8
#WEB_RESPONSE_DONE=9
#WEB_RESPONSE_ARGUMENT=-520
#WEB_RESPONSE_SYNTAX=-521
#WEB_RESPONSE_FRAMING=-522
#WEB_RESPONSE_LIMIT=-523
#WEB_RESPONSE_INCOMPLETE=-524
#WEB_RESPONSE_CODING=-525
#WEB_RESPONSE_UPGRADE=-526
#WEB_RESPONSE_NOTFOUND=-527
#WEB_RESPONSE_MAX_METADATA=32768
Structure WebResponse
  state.i
  error.i
  status.i
  versionMinor.i
  headOnly.i
  allowUpgrade.i
  line.i
  lineCapacity.i
  lineLength.i
  sawCR.i
  headers.i
  headerCapacity.i
  headerLength.i
  metadataBytes.i
  interimCount.i
  haveLength.i
  contentLength.i
  chunked.i
  connectionClose.i
  connectionKeepAlive.i
  remaining.i
  bodyBytes.i
  written.i
  consumed.i
  reusable.i
EndStructure

Procedure.i wrLower(c.i)
  If c>=65 And c<=90 : ProcedureReturn c+32 : EndIf
  ProcedureReturn c
EndProcedure

Procedure.i wrToken(c.i)
  If (c>=48 And c<=57) Or (c>=65 And c<=90) Or (c>=97 And c<=122) : ProcedureReturn 1 : EndIf
  If c=33 Or c=35 Or c=36 Or c=37 Or c=38 Or c=39 Or c=42 Or c=43 Or c=45 Or c=46 Or c=94 Or c=95 Or c=96 Or c=124 Or c=126
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i wrEqual(p.i,n.i,text.i)
  Define i.i
  For i=0 To n-1
    If PeekA(text+i)=0 : ProcedureReturn 0 : EndIf
    If wrLower(PeekA(p+i) & 255)<>PeekA(text+i) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn Bool(PeekA(text+n)=0)
EndProcedure

; Read one final-response field (zero-based occurrence); duplicate fields stay
; distinct. A null destination with capacity zero queries its byte length.
; Trailers are retained after the header terminator but never override headers.
Procedure.i WebResponseHeader(*s.WebResponse,name.i,occurrence.i,destination.i,capacity.i)
  Define at.i,finish.i,colon.i,start.i,last.i,i.i,count.i,first.i,c.i
  If *s=0 Or name=0 Or occurrence<0 Or capacity<0 Or (capacity>0 And destination=0)
    ProcedureReturn #WEB_RESPONSE_ARGUMENT
  EndIf
  If capacity>0 : PokeA(destination,0) : EndIf
  first=1
  While at+1<*s\headerLength
    finish=at
    While finish+1<*s\headerLength
      If PeekA(*s\headers+finish)=13 And PeekA(*s\headers+finish+1)=10 : Break : EndIf
      finish=finish+1
    Wend
    If finish=at : Break : EndIf
    If first=0
      colon=at
      While colon<finish
        If PeekA(*s\headers+colon)=58 : Break : EndIf
        colon=colon+1
      Wend
      If colon<finish
        If wrEqual(*s\headers+at,colon-at,name)
          If count=occurrence
            start=colon+1 : last=finish
            While start<last
              c=PeekA(*s\headers+start) : If c<>32 And c<>9 : Break : EndIf
              start=start+1
            Wend
            While last>start
              c=PeekA(*s\headers+last-1) : If c<>32 And c<>9 : Break : EndIf
              last=last-1
            Wend
            If destination=0 And capacity=0 : ProcedureReturn last-start : EndIf
            If last-start>=capacity : ProcedureReturn #WEB_RESPONSE_LIMIT : EndIf
            For i=start To last-1 : PokeA(destination+i-start,PeekA(*s\headers+i)) : Next
            PokeA(destination+last-start,0) : ProcedureReturn last-start
          EndIf
          count=count+1
        EndIf
      EndIf
    EndIf
    first=0 : at=finish+2
  Wend
  ProcedureReturn #WEB_RESPONSE_NOTFOUND
EndProcedure

Procedure.i WebResponseHeaderCount(*s.WebResponse)
  Define i.i,count.i,first.i,start.i
  If *s=0 : ProcedureReturn 0 : EndIf
  first=1
  For i=0 To *s\headerLength-2
    If PeekA(*s\headers+i)=13 And PeekA(*s\headers+i+1)=10
      If i=start : Break : EndIf
      If first=0 : count=count+1 : EndIf
      first=0 : start=i+2
    EndIf
  Next
  ProcedureReturn count
EndProcedure

Procedure.i wrFail(*s.WebResponse,error.i)
  *s\state=-1 : *s\error=error : *s\reusable=0
  ProcedureReturn error
EndProcedure

Procedure.i WebResponseInit(*s.WebResponse,line.i,lineCapacity.i,headers.i,headerCapacity.i,headOnly.i)
  Define i.i
  If *s=0 : ProcedureReturn #WEB_RESPONSE_ARGUMENT : EndIf
  For i=0 To SizeOf(WebResponse)-SizeOf(.i) Step SizeOf(.i) : PokeI(*s+i,0) : Next
  If line=0 Or lineCapacity<128 Or lineCapacity>8192 Or headers=0 Or headerCapacity<128 Or headerCapacity>#WEB_RESPONSE_MAX_METADATA Or (headOnly<>0 And headOnly<>1)
    ProcedureReturn wrFail(*s,#WEB_RESPONSE_ARGUMENT)
  EndIf
  *s\line=line : *s\lineCapacity=lineCapacity
  *s\headers=headers : *s\headerCapacity=headerCapacity : *s\headOnly=headOnly
  ProcedureReturn 0
EndProcedure

; Opt-in only. The protocol owner must validate all upgrade handshake fields.
Procedure.i WebResponseAllowUpgrade(*s.WebResponse)
  If *s=0 : ProcedureReturn #WEB_RESPONSE_ARGUMENT : EndIf
  If *s\state<>#WEB_RESPONSE_STATUS Or *s\error<>0 Or *s\metadataBytes<>0 Or *s\headOnly<>0
    ProcedureReturn #WEB_RESPONSE_ARGUMENT
  EndIf
  *s\allowUpgrade=1 : ProcedureReturn 0
EndProcedure

Procedure.i wrStoreLine(*s.WebResponse)
  Define i.i,p.i
  If *s\headerLength+*s\lineLength+2>*s\headerCapacity : ProcedureReturn #WEB_RESPONSE_LIMIT : EndIf
  p=*s\headers+*s\headerLength
  For i=0 To *s\lineLength-1 : PokeA(p+i,PeekA(*s\line+i)) : Next
  PokeA(p+*s\lineLength,13) : PokeA(p+*s\lineLength+1,10)
  *s\headerLength=*s\headerLength+*s\lineLength+2
  ProcedureReturn 0
EndProcedure

Procedure.i wrLength(*s.WebResponse,p.i,n.i)
  Define i.i,c.i,value.i,digits.i,items.i,first.i
  i=0 : items=0
  Repeat
    While i<n
      c=PeekA(p+i)
      If c<>32 And c<>9 : Break : EndIf
      i=i+1
    Wend
    value=0 : digits=0
    While i<n
      c=PeekA(p+i)
      If c<48 Or c>57 : Break : EndIf
      If value>($7FFFFFFFFFFFFFFF-(c-48))/10 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
      value=value*10+c-48 : digits=digits+1 : i=i+1
    Wend
    If digits=0 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
    If items=0 : first=value : ElseIf value<>first : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
    items=items+1
    While i<n
      c=PeekA(p+i)
      If c<>32 And c<>9 : Break : EndIf
      i=i+1
    Wend
    If i=n : Break : EndIf
    If PeekA(p+i)<>44 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
    i=i+1
    If i=n : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
  ForEver
  If *s\haveLength<>0 And *s\contentLength<>first : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
  *s\contentLength=first : *s\haveLength=1
  ProcedureReturn 0
EndProcedure

Procedure.i wrConnection(*s.WebResponse,p.i,n.i)
  Define i.i,start.i,c.i
  While i<n
    c=PeekA(p+i)
    If c=32 Or c=9 Or c=44
      i=i+1
    Else
      start=i
      While i<n
        If wrToken(PeekA(p+i) & 255)=0 : Break : EndIf
        i=i+1
      Wend
      If i=start : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
      If wrEqual(p+start,i-start,"close") : *s\connectionClose=1 : EndIf
      If wrEqual(p+start,i-start,"keep-alive") : *s\connectionKeepAlive=1 : EndIf
      While i<n
        c=PeekA(p+i)
        If c<>32 And c<>9 : Break : EndIf
        i=i+1
      Wend
      If i<n
        If PeekA(p+i)<>44 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
      EndIf
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i wrHeader(*s.WebResponse,trailer.i)
  Define p.i,n.i,i.i,colon.i,start.i,finish.i,c.i
  p=*s\line : n=*s\lineLength : colon=-1
  For i=0 To n-1
    c=PeekA(p+i) & 255
    If c=58 : colon=i : Break : EndIf
    If wrToken(c)=0 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
  Next
  If colon<1 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
  start=colon+1 : finish=n
  For i=start To n-1
    c=PeekA(p+i) & 255
    If (c<32 And c<>9) Or c=127 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
  Next
  While start<finish
    c=PeekA(p+start) : If c<>32 And c<>9 : Break : EndIf
    start=start+1
  Wend
  While finish>start
    c=PeekA(p+finish-1) : If c<>32 And c<>9 : Break : EndIf
    finish=finish-1
  Wend
  If trailer<>0
    If wrEqual(p,colon,"content-length") Or wrEqual(p,colon,"transfer-encoding") Or wrEqual(p,colon,"connection") Or wrEqual(p,colon,"host") Or wrEqual(p,colon,"content-encoding") Or wrEqual(p,colon,"trailer")
      ProcedureReturn #WEB_RESPONSE_FRAMING
    EndIf
    ProcedureReturn 0
  EndIf
  If wrEqual(p,colon,"content-length") : ProcedureReturn wrLength(*s,p+start,finish-start) : EndIf
  If wrEqual(p,colon,"transfer-encoding")
    If *s\chunked<>0 Or wrEqual(p+start,finish-start,"chunked")=0 : ProcedureReturn #WEB_RESPONSE_CODING : EndIf
    *s\chunked=1
  EndIf
  If wrEqual(p,colon,"connection") : ProcedureReturn wrConnection(*s,p+start,finish-start) : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i wrChunk(*s.WebResponse)
  Define p.i,n.i,i.i,c.i,d.i,value.i,digits.i,start.i,closed.i
  p=*s\line : n=*s\lineLength
  While i<n
    c=wrLower(PeekA(p+i) & 255) : d=-1
    If c>=48 And c<=57 : d=c-48 : ElseIf c>=97 And c<=102 : d=c-87 : EndIf
    If d<0 : Break : EndIf
    If value>($7FFFFFFFFFFFFFFF-d)/16 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
    value=value*16+d : digits=digits+1 : i=i+1
  Wend
  If digits=0 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
  While i<n
    c=PeekA(p+i)
    If c=32 Or c=9 : i=i+1 : Continue : EndIf
    If c<>59 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
    i=i+1
    While i<n
      c=PeekA(p+i) : If c<>32 And c<>9 : Break : EndIf
      i=i+1
    Wend
    start=i
    While i<n
      If wrToken(PeekA(p+i) & 255)=0 : Break : EndIf
      i=i+1
    Wend
    If i=start : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
    While i<n
      c=PeekA(p+i) : If c<>32 And c<>9 : Break : EndIf
      i=i+1
    Wend
    If i<n
      If PeekA(p+i)=61
        i=i+1
        While i<n
          c=PeekA(p+i) : If c<>32 And c<>9 : Break : EndIf
          i=i+1
        Wend
        If i=n : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
        If PeekA(p+i)=34
          i=i+1 : closed=0
          While i<n
            c=PeekA(p+i) & 255 : i=i+1
            If c=34 : closed=1 : Break : EndIf
            If c=92
              If i=n : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
              c=PeekA(p+i) & 255 : i=i+1
            EndIf
            If (c<32 And c<>9) Or c=127 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
          Wend
          If closed=0 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
        Else
          start=i
          While i<n
            If wrToken(PeekA(p+i) & 255)=0 : Break : EndIf
            i=i+1
          Wend
          If i=start : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
        EndIf
      EndIf
    EndIf
  Wend
  *s\remaining=value
  If value=0 : *s\state=#WEB_RESPONSE_TRAILERS : Else : *s\state=#WEB_RESPONSE_CHUNK_DATA : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i wrLine(*s.WebResponse)
  Define p.i,n.i,i.i,c.i,result.i
  p=*s\line : n=*s\lineLength
  If *s\state=#WEB_RESPONSE_CHUNK_SIZE : ProcedureReturn wrChunk(*s) : EndIf
  result=wrStoreLine(*s) : If result<0 : ProcedureReturn result : EndIf
  If *s\state=#WEB_RESPONSE_STATUS
    If n<12 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
    If PeekA(p)<>72 Or PeekA(p+1)<>84 Or PeekA(p+2)<>84 Or PeekA(p+3)<>80 Or PeekA(p+4)<>47 Or PeekA(p+5)<>49 Or PeekA(p+6)<>46 Or (PeekA(p+7)<>48 And PeekA(p+7)<>49) Or PeekA(p+8)<>32
      ProcedureReturn #WEB_RESPONSE_SYNTAX
    EndIf
    For i=9 To 11
      c=PeekA(p+i) : If c<48 Or c>57 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
      *s\status=*s\status*10+c-48
    Next
    If *s\status<100 Or *s\status>599 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
    If n>12
      If PeekA(p+12)<>32 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
    EndIf
    For i=13 To n-1
      c=PeekA(p+i) & 255 : If (c<32 And c<>9) Or c=127 : ProcedureReturn #WEB_RESPONSE_SYNTAX : EndIf
    Next
    *s\versionMinor=PeekA(p+7)-48 : *s\state=#WEB_RESPONSE_HEADERS
    ProcedureReturn 0
  EndIf
  If n>0 : ProcedureReturn wrHeader(*s,Bool(*s\state=#WEB_RESPONSE_TRAILERS)) : EndIf
  If *s\state=#WEB_RESPONSE_TRAILERS : *s\state=#WEB_RESPONSE_DONE : ProcedureReturn 0 : EndIf
  If *s\status=101
    If *s\allowUpgrade=0 : ProcedureReturn #WEB_RESPONSE_UPGRADE : EndIf
    If *s\versionMinor<>1 Or *s\chunked<>0 Or *s\haveLength<>0 Or *s\connectionClose<>0 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
    *s\state=#WEB_RESPONSE_DONE : *s\reusable=0 : ProcedureReturn 0
  EndIf
  If *s\chunked<>0 And *s\haveLength<>0 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
  If *s\status<200
    If *s\chunked<>0 Or *s\haveLength<>0 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
    *s\interimCount=*s\interimCount+1
    If *s\interimCount>8 : ProcedureReturn #WEB_RESPONSE_LIMIT : EndIf
    *s\state=#WEB_RESPONSE_STATUS : *s\status=0 : *s\headerLength=0
    *s\connectionClose=0 : *s\connectionKeepAlive=0
    ProcedureReturn 0
  EndIf
  *s\reusable=Bool(*s\connectionClose=0 And (*s\versionMinor=1 Or *s\connectionKeepAlive<>0))
  If *s\status=204
    If *s\chunked<>0 Or *s\haveLength<>0 : ProcedureReturn #WEB_RESPONSE_FRAMING : EndIf
    *s\state=#WEB_RESPONSE_DONE
  ElseIf *s\headOnly<>0 Or *s\status=304
    *s\state=#WEB_RESPONSE_DONE
  ElseIf *s\chunked<>0
    *s\state=#WEB_RESPONSE_CHUNK_SIZE
  ElseIf *s\haveLength<>0
    *s\remaining=*s\contentLength : *s\state=#WEB_RESPONSE_LENGTH
    If *s\remaining=0 : *s\state=#WEB_RESPONSE_DONE : EndIf
  Else
    *s\state=#WEB_RESPONSE_CLOSE : *s\reusable=0
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WebResponseFeed(*s.WebResponse,source.i,bytes.i,destination.i,capacity.i)
  Define i.i,c.i,result.i
  If *s=0 : ProcedureReturn #WEB_RESPONSE_ARGUMENT : EndIf
  *s\written=0 : *s\consumed=0
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If bytes<0 Or capacity<0 Or (bytes>0 And source=0) Or (capacity>0 And destination=0)
    ProcedureReturn wrFail(*s,#WEB_RESPONSE_ARGUMENT)
  EndIf
  While i<bytes And *s\state<>#WEB_RESPONSE_DONE
    If *s\state=#WEB_RESPONSE_LENGTH Or *s\state=#WEB_RESPONSE_CLOSE Or *s\state=#WEB_RESPONSE_CHUNK_DATA
      If *s\written=capacity : Break : EndIf
      If *s\bodyBytes=$7FFFFFFFFFFFFFFF : ProcedureReturn wrFail(*s,#WEB_RESPONSE_LIMIT) : EndIf
      PokeA(destination+*s\written,PeekA(source+i))
      *s\written=*s\written+1 : *s\bodyBytes=*s\bodyBytes+1 : i=i+1 : *s\consumed=i
      If *s\state<>#WEB_RESPONSE_CLOSE
        *s\remaining=*s\remaining-1
        If *s\remaining=0
          If *s\state=#WEB_RESPONSE_LENGTH : *s\state=#WEB_RESPONSE_DONE : Else : *s\state=#WEB_RESPONSE_CHUNK_CR : EndIf
        EndIf
      EndIf
    Else
      c=PeekA(source+i) & 255 : i=i+1 : *s\consumed=i
      If *s\state=#WEB_RESPONSE_CHUNK_CR
        If c<>13 : ProcedureReturn wrFail(*s,#WEB_RESPONSE_SYNTAX) : EndIf
        *s\state=#WEB_RESPONSE_CHUNK_LF
      ElseIf *s\state=#WEB_RESPONSE_CHUNK_LF
        If c<>10 : ProcedureReturn wrFail(*s,#WEB_RESPONSE_SYNTAX) : EndIf
        *s\state=#WEB_RESPONSE_CHUNK_SIZE
      Else
        If *s\state<>#WEB_RESPONSE_CHUNK_SIZE
          *s\metadataBytes=*s\metadataBytes+1
          If *s\metadataBytes>#WEB_RESPONSE_MAX_METADATA : ProcedureReturn wrFail(*s,#WEB_RESPONSE_LIMIT) : EndIf
        EndIf
        If *s\sawCR<>0
          If c<>10 : ProcedureReturn wrFail(*s,#WEB_RESPONSE_SYNTAX) : EndIf
          result=wrLine(*s) : *s\lineLength=0 : *s\sawCR=0
          If result<0 : ProcedureReturn wrFail(*s,result) : EndIf
        ElseIf c=13
          *s\sawCR=1
        Else
          If c=10 Or c=0 : ProcedureReturn wrFail(*s,#WEB_RESPONSE_SYNTAX) : EndIf
          If *s\lineLength=*s\lineCapacity : ProcedureReturn wrFail(*s,#WEB_RESPONSE_LIMIT) : EndIf
          PokeA(*s\line+*s\lineLength,c) : *s\lineLength=*s\lineLength+1
        EndIf
      EndIf
    EndIf
  Wend
  ProcedureReturn i
EndProcedure

Procedure.i WebResponseEof(*s.WebResponse)
  If *s=0 : ProcedureReturn #WEB_RESPONSE_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\state=#WEB_RESPONSE_CLOSE : *s\state=#WEB_RESPONSE_DONE : EndIf
  If *s\state<>#WEB_RESPONSE_DONE : ProcedureReturn wrFail(*s,#WEB_RESPONSE_INCOMPLETE) : EndIf
  ProcedureReturn 0
EndProcedure
