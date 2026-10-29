; Incremental text/event-stream decoder over decoded HTTP body bytes.
; WHATWG HTML 9.2: CR/LF/CRLF, one leading BOM, UTF-8 replacement,
; multiline data, persistent IDs, event names and retry hints.
; Caller-owned bounded buffers; no transport calls or automatic retries.
#WEB_EVENT_ARGUMENT=-630
#WEB_EVENT_LIMIT=-631
#WEB_EVENT_STATE=-632
Structure WebEventStream
  line.i
  lineCapacity.i
  lineLength.i
  data.i
  dataCapacity.i
  dataLength.i
  event.i
  eventCapacity.i
  eventLength.i
  id.i
  lastId.i
  idCapacity.i
  idLength.i
  lastIdLength.i
  retry.i
  retryChanged.i
  consumed.i
  ready.i
  error.i
  closed.i
  skipLf.i
  started.i
  utfNeed.i
  utfCode.i
  utfLow.i
  utfHigh.i
EndStructure

Procedure.i weFail(*s.WebEventStream,error.i)
  *s\error=error : ProcedureReturn error
EndProcedure

; id and lastId are separate buffers of idCapacity bytes. lastId changes
; only at a blank line, including an ID-only block without an event.
Procedure.i WebEventStreamInit(*s.WebEventStream,line.i,lineCapacity.i,data.i,dataCapacity.i,event.i,eventCapacity.i,id.i,lastId.i,idCapacity.i)
  Define i.i
  If *s=0 : ProcedureReturn #WEB_EVENT_ARGUMENT : EndIf
  For i=0 To SizeOf(WebEventStream)-1 : PokeA(*s+i,0) : Next
  If line=0 Or data=0 Or event=0 Or id=0 Or lastId=0 Or id=lastId Or lineCapacity<4 Or dataCapacity<1 Or eventCapacity<7 Or idCapacity<1 Or lineCapacity>65536 Or dataCapacity>1048576 Or eventCapacity>65536 Or idCapacity>65536
    ProcedureReturn weFail(*s,#WEB_EVENT_ARGUMENT)
  EndIf
  *s\line=line : *s\lineCapacity=lineCapacity
  *s\data=data : *s\dataCapacity=dataCapacity
  *s\event=event : *s\eventCapacity=eventCapacity
  *s\id=id : *s\lastId=lastId : *s\idCapacity=idCapacity
  *s\retry=3000
  ProcedureReturn 0
EndProcedure

Procedure.i weName(p.i,n.i,text.i)
  Define i.i
  For i=0 To n-1
    If PeekA(text+i)=0 Or PeekA(p+i)<>PeekA(text+i) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn Bool(PeekA(text+n)=0)
EndProcedure

Procedure.i weLine(*s.WebEventStream)
  Define n.i,field.i,value.i,count.i,i.i,c.i,v.i,bad.i
  n=*s\lineLength : *s\lineLength=0
  If n=0
    For i=0 To *s\idLength-1 : PokeA(*s\lastId+i,PeekA(*s\id+i)) : Next
    *s\lastIdLength=*s\idLength
    If *s\dataLength=0 : *s\eventLength=0 : ProcedureReturn 0 : EndIf
    *s\dataLength=*s\dataLength-1
    If *s\eventLength=0
      v="message"
      For i=0 To 6 : PokeA(*s\event+i,PeekA(v+i)) : Next
      *s\eventLength=7
    EndIf
    *s\ready=1 : ProcedureReturn 1
  EndIf
  If PeekA(*s\line)=58 : ProcedureReturn 0 : EndIf
  field=n : value=n
  For i=0 To n-1
    If PeekA(*s\line+i)=58 : field=i : value=i+1 : Break : EndIf
  Next
  If value<n And PeekA(*s\line+value)=32 : value=value+1 : EndIf
  count=n-value
  If weName(*s\line,field,"data")
    If count+1>*s\dataCapacity-*s\dataLength : ProcedureReturn weFail(*s,#WEB_EVENT_LIMIT) : EndIf
    For i=0 To count-1 : PokeA(*s\data+*s\dataLength+i,PeekA(*s\line+value+i)) : Next
    *s\dataLength=*s\dataLength+count
    PokeA(*s\data+*s\dataLength,10) : *s\dataLength=*s\dataLength+1
  ElseIf weName(*s\line,field,"event")
    If count>*s\eventCapacity : ProcedureReturn weFail(*s,#WEB_EVENT_LIMIT) : EndIf
    For i=0 To count-1 : PokeA(*s\event+i,PeekA(*s\line+value+i)) : Next
    *s\eventLength=count
  ElseIf weName(*s\line,field,"id")
    For i=0 To count-1 : If PeekA(*s\line+value+i)=0 : ProcedureReturn 0 : EndIf : Next
    If count>*s\idCapacity : ProcedureReturn weFail(*s,#WEB_EVENT_LIMIT) : EndIf
    For i=0 To count-1 : PokeA(*s\id+i,PeekA(*s\line+value+i)) : Next
    *s\idLength=count
  ElseIf weName(*s\line,field,"retry")
    If count=0 : ProcedureReturn 0 : EndIf
    For i=0 To count-1
      c=PeekA(*s\line+value+i) & 255
      If c<48 Or c>57 : bad=1 : Break : EndIf
      ; Saturate only valid decimal hints to the supported timer range.
      If v<2147483647 : v=v*10+c-48 : If v>2147483647 : v=2147483647 : EndIf : EndIf
    Next
    If bad=0 : *s\retry=v : *s\retryChanged=1 : EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i weCodepoint(*s.WebEventStream,c.i)
  Define n.i,p.i
  If *s\started=0
    *s\started=1
    If c=$FEFF : ProcedureReturn 0 : EndIf
  EndIf
  If *s\skipLf
    *s\skipLf=0
    If c=10 : ProcedureReturn 0 : EndIf
  EndIf
  If c=13 Or c=10
    *s\skipLf=Bool(c=13) : ProcedureReturn weLine(*s)
  EndIf
  n=1
  If c>$7F : n=2 : EndIf
  If c>$7FF : n=3 : EndIf
  If c>$FFFF : n=4 : EndIf
  If n>*s\lineCapacity-*s\lineLength : ProcedureReturn weFail(*s,#WEB_EVENT_LIMIT) : EndIf
  p=*s\line+*s\lineLength : *s\lineLength=*s\lineLength+n
  If n=1
    PokeA(p,c)
  ElseIf n=2
    PokeA(p,$C0 | (c>>6)) : PokeA(p+1,$80 | (c & 63))
  ElseIf n=3
    PokeA(p,$E0 | (c>>12)) : PokeA(p+1,$80 | ((c>>6) & 63)) : PokeA(p+2,$80 | (c & 63))
  Else
    PokeA(p,$F0 | (c>>18)) : PokeA(p+1,$80 | ((c>>12) & 63)) : PokeA(p+2,$80 | ((c>>6) & 63)) : PokeA(p+3,$80 | (c & 63))
  EndIf
  ProcedureReturn 0
EndProcedure

; 1 exposes one complete event; consume length-delimited buffers and call
; Next before feeding again. Unconsumed bytes remain owned by the caller.
Procedure.i WebEventStreamFeed(*s.WebEventStream,input.i,bytes.i)
  Define c.i,rc.i
  If *s=0 : ProcedureReturn #WEB_EVENT_ARGUMENT : EndIf
  *s\consumed=0
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\ready : ProcedureReturn 1 : EndIf
  If *s\closed : ProcedureReturn #WEB_EVENT_STATE : EndIf
  If bytes<0 Or (bytes>0 And input=0) : ProcedureReturn weFail(*s,#WEB_EVENT_ARGUMENT) : EndIf
  While *s\consumed<bytes
    c=PeekA(input+*s\consumed) & 255
    If *s\utfNeed>0
      If c<*s\utfLow Or c>*s\utfHigh
        *s\utfNeed=0 : rc=weCodepoint(*s,$FFFD)
        If rc<>0 : ProcedureReturn rc : EndIf
        Continue
      EndIf
      *s\consumed=*s\consumed+1
      *s\utfCode=(*s\utfCode<<6) | (c & 63) : *s\utfNeed=*s\utfNeed-1
      *s\utfLow=$80 : *s\utfHigh=$BF
      If *s\utfNeed=0 : rc=weCodepoint(*s,*s\utfCode) : If rc<>0 : ProcedureReturn rc : EndIf : EndIf
    Else
      *s\consumed=*s\consumed+1
      *s\utfLow=$80 : *s\utfHigh=$BF
      If c<$80
        rc=weCodepoint(*s,c) : If rc<>0 : ProcedureReturn rc : EndIf
      ElseIf c>=$C2 And c<=$DF
        *s\utfNeed=1 : *s\utfCode=c & 31
      ElseIf c>=$E0 And c<=$EF
        *s\utfNeed=2 : *s\utfCode=c & 15
        If c=$E0 : *s\utfLow=$A0 : EndIf
        If c=$ED : *s\utfHigh=$9F : EndIf
      ElseIf c>=$F0 And c<=$F4
        *s\utfNeed=3 : *s\utfCode=c & 7
        If c=$F0 : *s\utfLow=$90 : EndIf
        If c=$F4 : *s\utfHigh=$8F : EndIf
      Else
        rc=weCodepoint(*s,$FFFD) : If rc<>0 : ProcedureReturn rc : EndIf
      EndIf
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i WebEventStreamNext(*s.WebEventStream)
  If *s=0 : ProcedureReturn #WEB_EVENT_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\ready=0 : ProcedureReturn #WEB_EVENT_STATE : EndIf
  *s\ready=0 : *s\dataLength=0 : *s\eventLength=0
  ProcedureReturn 0
EndProcedure

; EOF never dispatches an unfinished event. A ready event must be consumed.
Procedure.i WebEventStreamEof(*s.WebEventStream)
  If *s=0 : ProcedureReturn #WEB_EVENT_ARGUMENT : EndIf
  If *s\error<0 : ProcedureReturn *s\error : EndIf
  If *s\ready : ProcedureReturn #WEB_EVENT_STATE : EndIf
  *s\closed=1 : *s\dataLength=0 : *s\eventLength=0 : *s\lineLength=0 : *s\utfNeed=0
  ProcedureReturn 0
EndProcedure
