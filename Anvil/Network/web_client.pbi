; Cooperative HTTP/1 exchange engine. No waits, sockets or board dependencies.
; Select the kernel or payload binding before including this file.
; Transport state: 0 pending, 1 open, 2 peer closed, negative failure.
; Pump the underlying network outside Step. Each Step does at most one send,
; one receive and bounded parsing; output backpressure preserves unread bytes.
XIncludeFile "Anvil/Network/web_request.pbi"
XIncludeFile "Anvil/Network/web_response.pbi"
XIncludeFile "Anvil/Network/web_transport.pbi"
#WEB_CLIENT_ARGUMENT=-550
#WEB_CLIENT_STATE=-551
#WEB_CLIENT_TIMEOUT=-552
#WEB_CLIENT_CANCELLED=-553
#WEB_CLIENT_TRANSPORT=-554
Structure WebClient
  connection.WebConnection
  request.i
  response.i
  tx.i
  txCapacity.i
  txLength.i
  txOffset.i
  rx.i
  rxCapacity.i
  rxLength.i
  rxOffset.i
  started.i
  timeout.i
  state.i
  error.i
  consumed.i
  written.i
  sent.i
  received.i
EndStructure

Procedure.i wcFail(*s.WebClient,error.i)
  If *s\state=1 Or *s\state=2 Or *s\state=3 : WebTransportClose(@*s\connection) : EndIf
  *s\state=-1 : *s\error=error
  ProcedureReturn error
EndProcedure

; request is finalized; response was initialized with HEAD semantics as needed.
; All contexts/buffers and the URL host remain owned by the caller until Close.
Procedure.i WebClientStart(*s.WebClient,*url.WebUrl,*request.WebRequest,*response.WebResponse,tx.i,txCapacity.i,rx.i,rxCapacity.i,now.i,timeout.i)
  Define i.i,rc.i
  If *s=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  ; Start is for a fresh or explicitly closed context, not a live connection.
  For i=0 To SizeOf(WebClient)-1 : PokeA(*s+i,0) : Next
  If *url=0 Or *request=0 Or *response=0 Or tx=0 Or rx=0 Or txCapacity<128 Or txCapacity>16384 Or rxCapacity<128 Or rxCapacity>16384 Or timeout<1 Or timeout>$7FFFFFFF
    *s\state=-1 : *s\error=#WEB_CLIENT_ARGUMENT : ProcedureReturn *s\error
  EndIf
  If *request\state<>1 Or *response\state<>#WEB_RESPONSE_STATUS Or *response\error<>0
    *s\state=-1 : *s\error=#WEB_CLIENT_STATE : ProcedureReturn *s\error
  EndIf
  *s\connection\secure=*url\secure : *s\connection\host=*url\host : *s\connection\port=*url\port
  *s\request=*request : *s\response=*response
  *s\tx=tx : *s\txCapacity=txCapacity : *s\rx=rx : *s\rxCapacity=rxCapacity
  *s\started=now : *s\timeout=timeout : *s\state=1
  rc=WebTransportOpen(@*s\connection)
  If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WebClientCancel(*s.WebClient)
  If *s=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  ProcedureReturn wcFail(*s,#WEB_CLIENT_CANCELLED)
EndProcedure

Procedure WebClientClose(*s.WebClient)
  If *s=0 : ProcedureReturn : EndIf
  If *s\state<>0 And *s\state<>-1 : WebTransportClose(@*s\connection) : EndIf
  *s\state=0
EndProcedure

; A zero result means call again; 1 means a complete response; negative means
; failure and closed transport. Opted-in upgrade returns 2 and retains unread
; rx bytes/connection for protocol validation. Always consume output before reuse.
; Early final responses stop uploading and prohibit connection reuse.
Procedure.i WebClientStep(*s.WebClient,body.i,bytes.i,endBody.i,output.i,capacity.i,now.i)
  Define *request.WebRequest,*response.WebResponse,rc.i,st.i
  If *s=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  *s\consumed=0 : *s\written=0
  If *s\state=-1 : ProcedureReturn *s\error : EndIf
  If *s\state=2 : ProcedureReturn 1 : EndIf
  If *s\state=3 : ProcedureReturn 2 : EndIf
  If *s\state<>1 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  If bytes<0 Or capacity<0 Or (bytes>0 And body=0) Or (capacity>0 And output=0) : ProcedureReturn wcFail(*s,#WEB_CLIENT_ARGUMENT) : EndIf
  If ((now-*s\started) & $FFFFFFFF)>=*s\timeout : ProcedureReturn wcFail(*s,#WEB_CLIENT_TIMEOUT) : EndIf
  *request=*s\request : *response=*s\response
  st=WebTransportState(@*s\connection)
  If st<0 : ProcedureReturn wcFail(*s,st) : EndIf
  If st=0 : ProcedureReturn 0 : EndIf
  If st<>1 And st<>2 : ProcedureReturn wcFail(*s,#WEB_CLIENT_TRANSPORT) : EndIf
  ; Read first, so a server rejection can stop a large upload promptly.
  If *s\rxOffset=*s\rxLength
    *s\rxOffset=0 : *s\rxLength=0
    rc=WebTransportRecv(@*s\connection,*s\rx,*s\rxCapacity)
    If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
    If rc>*s\rxCapacity : ProcedureReturn wcFail(*s,#WEB_CLIENT_TRANSPORT) : EndIf
    *s\rxLength=rc : *s\received=*s\received+rc
    If rc=0 And st=2
      rc=WebResponseEof(*response)
      If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
    EndIf
  EndIf
  If *s\rxOffset<*s\rxLength
    rc=WebResponseFeed(*response,*s\rx+*s\rxOffset,*s\rxLength-*s\rxOffset,output,capacity)
    *s\rxOffset=*s\rxOffset+*response\consumed : *s\written=*response\written
    If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
  EndIf
  If *response\state=#WEB_RESPONSE_DONE
    If *response\status=101 And *response\allowUpgrade
      ; Upgraded bytes may follow headers in the same read. Keep them and
      ; the connection for the protocol owner; never reuse as ordinary HTTP.
      If *request\state<>2 Or *s\txOffset<>*s\txLength Or st<>1 : ProcedureReturn wcFail(*s,#WEB_CLIENT_STATE) : EndIf
      *s\state=3 : ProcedureReturn 2
    EndIf
    If *request\state<>2 Or *s\txOffset<>*s\txLength Or st=2 Or *s\rxOffset<>*s\rxLength : *response\reusable=0 : EndIf
    *s\state=2
    If *response\reusable=0 : WebTransportClose(@*s\connection) : EndIf
    ProcedureReturn 1
  EndIf
  If st=2 : ProcedureReturn 0 : EndIf
  If *response\status>=200 : ProcedureReturn 0 : EndIf
  If *s\txOffset=*s\txLength And *request\state<>2
    rc=WebRequestOutput(*request,body,bytes,endBody,*s\tx,*s\txCapacity)
    *s\consumed=*request\consumed
    If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
    *s\txOffset=0 : *s\txLength=rc
  EndIf
  If *s\txOffset<*s\txLength
    rc=WebTransportSend(@*s\connection,*s\tx+*s\txOffset,*s\txLength-*s\txOffset)
    If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
    If rc>*s\txLength-*s\txOffset : ProcedureReturn wcFail(*s,#WEB_CLIENT_TRANSPORT) : EndIf
    *s\txOffset=*s\txOffset+rc : *s\sent=*s\sent+rc
  EndIf
  ProcedureReturn 0
EndProcedure

; Sequential reuse on the SAME origin and connection. The new request must be
; built from the original URL authority; do not mutate its host while connected.
; Call before replacing the old response context, whose reuse decision is read.
Procedure.i WebClientNext(*s.WebClient,*request.WebRequest,*response.WebResponse,now.i,timeout.i)
  Define *previous.WebResponse,st.i
  If *s=0 Or *request=0 Or *response=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  If *s\state<>2 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  *previous=*s\response
  If *previous\reusable=0 Or *s\rxOffset<>*s\rxLength Or *s\txOffset<>*s\txLength : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  If *request\state<>1 Or *response\state<>#WEB_RESPONSE_STATUS Or timeout<1 Or timeout>$7FFFFFFF : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  st=WebTransportState(@*s\connection)
  If st<>1 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  *s\request=*request : *s\response=*response : *s\started=now : *s\timeout=timeout
  *s\txOffset=0 : *s\txLength=0 : *s\rxOffset=0 : *s\rxLength=0
  *s\consumed=0 : *s\written=0 : *s\sent=0 : *s\received=0 : *s\error=0 : *s\state=1
  ProcedureReturn 0
EndProcedure
