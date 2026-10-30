; Cooperative HTTP exchange engine. No waits, sockets or board dependencies.
; Select the kernel or payload binding before including this file.
; Transport state: 0 pending, 1 open, 2 peer closed, negative failure.
; Pump the underlying network outside Step. Each Step does at most one send,
; one receive and bounded parsing; output backpressure preserves unread bytes.
XIncludeFile "Anvil/Network/web_request.pbi"
XIncludeFile "Anvil/Network/web_response.pbi"
XIncludeFile "Anvil/Network/web_transport.pbi"
XIncludeFile "Anvil/Network/h2_client.pbi"
#WEB_CLIENT_ARGUMENT=-550
#WEB_CLIENT_STATE=-551
#WEB_CLIENT_TIMEOUT=-552
#WEB_CLIENT_CANCELLED=-553
#WEB_CLIENT_TRANSPORT=-554
#WEB_CLIENT_STREAM_RESET=-555
Structure WebClient
  protocol.i
  h2.i
  h2Stream.i
  h2Offset.i
  h2Headers.i
  h2Trailers.i
  h2Ending.i
  h2ResetCode.i
  h2SentStart.i
  h2ReceivedStart.i
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
  If *s\state=1 Or *s\state=2 Or *s\state=3
    If *s\h2<>0 : H2ClientClose(*s\h2) : Else : WebTransportClose(@*s\connection) : EndIf
  EndIf
  *s\state=-1 : *s\error=error
  ProcedureReturn error
EndProcedure

; request is finalized; response was initialized with HEAD semantics as needed.
; All contexts/buffers and the URL host remain owned by the caller until Close.
Procedure.i wcInit(*s.WebClient,*url.WebUrl,*request.WebRequest,*response.WebResponse,tx.i,txCapacity.i,rx.i,rxCapacity.i,now.i,timeout.i)
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
  *s\started=now : *s\timeout=timeout : *s\state=1 : *s\protocol=1
  ProcedureReturn 0
EndProcedure

Procedure.i WebClientStart(*s.WebClient,*url.WebUrl,*request.WebRequest,*response.WebResponse,tx.i,txCapacity.i,rx.i,rxCapacity.i,now.i,timeout.i)
  Define rc.i
  rc=wcInit(*s,*url,*request,*response,tx,txCapacity,rx,rxCapacity,now,timeout)
  If rc<>0 : ProcedureReturn rc : EndIf
  rc=WebTransportOpen(@*s\connection)
  If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
  ProcedureReturn 0
EndProcedure

; Adopt an already-open HTTP/1 transport without opening it again. The caller
; must have selected HTTP/1 (or no ALPN), never h2. Destination must be fresh or
; closed. On success ownership moves; failure leaves the source connection intact.
Procedure.i WebClientAdopt(*s.WebClient,*connection.WebConnection,*request.WebRequest,*response.WebResponse,tx.i,txCapacity.i,rx.i,rxCapacity.i,now.i,timeout.i)
  Define url.WebUrl,rc.i,i.i
  If *s=0 Or *connection=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  If *connection=@*s\connection Or *connection\handle<=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  rc=WebTransportState(*connection)
  If rc<>1 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  url\secure=*connection\secure : url\host=*connection\host : url\port=*connection\port
  rc=wcInit(*s,@url,*request,*response,tx,txCapacity,rx,rxCapacity,now,timeout)
  If rc<>0 : ProcedureReturn rc : EndIf
  For i=0 To SizeOf(WebConnection)-1
    PokeA(@*s\connection+i,PeekA(*connection+i)) : PokeA(*connection+i,0)
  Next
  ProcedureReturn 0
EndProcedure

; Opt-in negotiation with caller-owned H2 context/buffers. This WebClient owns
; the H2 context exclusively until Close; do not pump or submit it separately.
; Plain HTTP, opted-in upgrades and older services without ALPN use HTTP/1.
Procedure.i WebClientStartAuto(*s.WebClient,*url.WebUrl,*request.WebRequest,*response.WebResponse,tx.i,txCapacity.i,rx.i,rxCapacity.i,*h.H2Client,*buffers.H2Buffers,now.i,timeout.i)
  Define rc.i,legacy.i
  If *url=0 Or *response=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  legacy=Bool(*url\secure=0 Or *response\allowUpgrade<>0)
  CompilerIf #WEB_KERNEL_BINDING=0
    If webpTlsOpenAlpn=0 Or webpTlsAlpn=0 : legacy=1 : EndIf
  CompilerEndIf
  If legacy<>0 : ProcedureReturn WebClientStart(*s,*url,*request,*response,tx,txCapacity,rx,rxCapacity,now,timeout) : EndIf
  If *h=0 Or *buffers=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  rc=wcInit(*s,*url,*request,*response,tx,txCapacity,rx,rxCapacity,now,timeout)
  If rc<>0 : ProcedureReturn rc : EndIf
  *s\protocol=0 : *s\h2=*h
  rc=H2ClientStartNegotiated(*h,*url,*buffers,now,timeout)
  If rc<>0 : ProcedureReturn wcFail(*s,rc) : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WebClientCancel(*s.WebClient)
  If *s=0 : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
  ProcedureReturn wcFail(*s,#WEB_CLIENT_CANCELLED)
EndProcedure

Procedure WebClientClose(*s.WebClient)
  If *s=0 : ProcedureReturn : EndIf
  If *s\state<>0 And *s\state<>-1
    If *s\h2<>0 : H2ClientClose(*s\h2) : Else : WebTransportClose(@*s\connection) : EndIf
  EndIf
  *s\state=0
EndProcedure

; Format response metadata for the existing header lookup API. This is stored
; metadata, not an HTTP/1 parser fed with fabricated framing. Informational
; fields count against limits but are not retained as final response headers.
Procedure.i wcH2Line(*s.WebClient,name.i,nameBytes.i,value.i,valueBytes.i,kind.i,keep.i)
 Define *r.WebResponse,n.i,i.i,at.i,rc.i
 *r=*s\response
 n=nameBytes+valueBytes
 If kind=0 : n=n+2 : EndIf
 If n>*r\lineCapacity Or *r\metadataBytes+n+2>#WEB_RESPONSE_MAX_METADATA : ProcedureReturn wcFail(*s,#WEB_RESPONSE_LIMIT) : EndIf
 *r\metadataBytes=*r\metadataBytes+n+2
 If keep=0 : ProcedureReturn 0 : EndIf
 If *r\headerLength+n+2>*r\headerCapacity : ProcedureReturn wcFail(*s,#WEB_RESPONSE_LIMIT) : EndIf
 at=0
 For i=0 To nameBytes-1 : PokeA(*r\line+at,PeekA(name+i)) : at=at+1 : Next
 If kind=0 : PokeA(*r\line+at,58) : PokeA(*r\line+at+1,32) : at=at+2 : EndIf
 For i=0 To valueBytes-1 : PokeA(*r\line+at,PeekA(value+i)) : at=at+1 : Next
 *r\lineLength=n : rc=wrStoreLine(*r) : *r\lineLength=0
 If rc<>0 : ProcedureReturn wcFail(*s,rc) : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i wcH2HeadersEnd(*s.WebClient)
 Define rc.i,*r.WebResponse
 If *s\h2Headers<>1 : ProcedureReturn 0 : EndIf
 rc=wcH2Line(*s,0,0,0,0,1,1)
 If rc<>0 : ProcedureReturn rc : EndIf
 *s\h2Headers=2 : *r=*s\response : *r\state=#WEB_RESPONSE_STREAM
 ProcedureReturn 0
EndProcedure
Procedure.i wcH2Field(*s.WebClient,*h.H2Client)
 Define *r.WebResponse,*stream.H2Stream,rc.i,status.i,keep.i
 *r=*s\response : *stream=h2cStream(*h,*s\h2Stream)
 If *stream=0 : ProcedureReturn wcFail(*s,#WEB_CLIENT_STATE) : EndIf
 If h2cEqual(*h\name,*h\nameLength,":status")
  status=*h\blockStatus : *r\status=status : *r\state=#WEB_RESPONSE_HEADERS
  *r\versionMajor=2 : *r\versionMinor=0 : *r\headerLength=0
  If status<200
   *r\interimCount=*r\interimCount+1
   If *r\interimCount>8 : ProcedureReturn wcFail(*s,#WEB_RESPONSE_LIMIT) : EndIf
  Else
   *s\h2Headers=1
  EndIf
  ProcedureReturn wcH2Line(*s,"HTTP/2 ",7,*h\value,*h\valueLength,1,Bool(status>=200))
 EndIf
 If *h\blockTrailers<>0
  rc=wcH2HeadersEnd(*s) : If rc<>0 : ProcedureReturn rc : EndIf
  *s\h2Trailers=1
 EndIf
 keep=Bool(*h\blockTrailers<>0 Or *h\blockStatus>=200)
 rc=wcH2Line(*s,*h\name,*h\nameLength,*h\value,*h\valueLength,0,keep)
 If rc<>0 : ProcedureReturn rc : EndIf
 If *stream\contentLength>=0
  *r\haveLength=1 : *r\contentLength=*stream\contentLength
  If *r\headOnly=0 And *r\status<>204 And *r\status<>304 : *r\remaining=*r\contentLength-*r\bodyBytes : EndIf
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i wcH2Complete(*s.WebClient,*h.H2Client)
 Define *r.WebResponse
 If *s\h2Ending=0 Or *h\txLength<>0 Or *h\requestHeaderBytes<>0 : ProcedureReturn 0 : EndIf
 *r=*s\response : *r\state=#WEB_RESPONSE_DONE : *r\remaining=0
 *r\reusable=Bool(*h\goaway=0 And *h\state=3)
 *s\state=2
 ProcedureReturn 1
EndProcedure
Procedure.i wcH2Step(*s.WebClient,body.i,bytes.i,endBody.i,output.i,capacity.i,now.i)
 Define *h.H2Client,*r.WebResponse,*request.WebRequest,*stream.H2Stream,rc.i,event.i,n.i,i.i
 *h=*s\h2 : *r=*s\response : *request=*s\request
 *r\written=0 : *r\consumed=0
 rc=wcH2Complete(*s,*h) : If rc<>0 : ProcedureReturn rc : EndIf
 event=H2ClientStep(*h,now)
 *s\sent=*h\sent-*s\h2SentStart : *s\received=*h\received-*s\h2ReceivedStart
 If event<0 : ProcedureReturn wcFail(*s,event) : EndIf
 If *h\state=4
  rc=H2ClientTakeHttp1(*h,@*s\connection)
  If rc<>0 : ProcedureReturn wcFail(*s,rc) : EndIf
  *s\h2=0 : *s\protocol=1 : ProcedureReturn 0
 EndIf
 If *h\state=2 Or *h\state=3 : *s\protocol=2 : *r\versionMajor=2 : *r\versionMinor=0 : EndIf
 If event=#H2_GOAWAY
  rc=H2ClientConsume(*h) : If rc<>0 : ProcedureReturn wcFail(*s,rc) : EndIf
  *r\reusable=0
  If *s\h2Stream=0 : ProcedureReturn wcFail(*s,#H2_CLOSED) : EndIf
  ProcedureReturn wcH2Complete(*s,*h)
 EndIf
 If event<>0
  If *s\h2Stream=0 Or *h\eventStream<>*s\h2Stream : ProcedureReturn wcFail(*s,#WEB_CLIENT_STATE) : EndIf
  If event=#H2_RESET
   *stream=h2cStream(*h,*s\h2Stream)
   If *stream<>0 : *s\h2ResetCode=*stream\resetCode : EndIf
   ProcedureReturn wcFail(*s,#WEB_CLIENT_STREAM_RESET)
  EndIf
  If event=#H2_FIELD
   rc=wcH2Field(*s,*h) : If rc<>0 : ProcedureReturn rc : EndIf
  ElseIf event=#H2_DATA
   rc=wcH2HeadersEnd(*s) : If rc<>0 : ProcedureReturn rc : EndIf
   n=*h\dataBytes-*s\h2Offset : If n>capacity : n=capacity : EndIf
   For i=0 To n-1 : PokeA(output+i,PeekA(*h\data+*s\h2Offset+i)) : Next
   *s\h2Offset=*s\h2Offset+n : *s\written=n : *r\written=n : *r\bodyBytes=*r\bodyBytes+n
   If *r\haveLength<>0 And *r\headOnly=0 And *r\status<>204 And *r\status<>304 : *r\remaining=*r\contentLength-*r\bodyBytes : EndIf
   If *s\h2Offset<*h\dataBytes : ProcedureReturn 0 : EndIf
   *s\h2Offset=0
  ElseIf event=#H2_END
   rc=wcH2HeadersEnd(*s) : If rc<>0 : ProcedureReturn rc : EndIf
   If *s\h2Trailers<>0
    rc=wcH2Line(*s,0,0,0,0,1,1) : If rc<>0 : ProcedureReturn rc : EndIf
   EndIf
   *s\h2Ending=1
  Else
   ProcedureReturn wcFail(*s,#WEB_CLIENT_STATE)
  EndIf
  rc=H2ClientConsume(*h) : If rc<>0 : ProcedureReturn wcFail(*s,rc) : EndIf
  If event=#H2_END
   rc=H2ClientRelease(*h,*s\h2Stream) : If rc<>0 : ProcedureReturn wcFail(*s,rc) : EndIf
   ProcedureReturn wcH2Complete(*s,*h)
  EndIf
  ProcedureReturn 0
 EndIf
 If *s\h2Ending<>0 : ProcedureReturn wcH2Complete(*s,*h) : EndIf
 If *s\h2Stream=0 And *h\state=3
  rc=H2ClientRequest(*h,*request)
  If rc=#H2_BUSY : ProcedureReturn 0 : EndIf
  If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
  *s\h2Stream=rc : ProcedureReturn 0
 EndIf
 If *s\h2Stream<>0
  *stream=h2cStream(*h,*s\h2Stream)
  If *stream=0 : ProcedureReturn wcFail(*s,#WEB_CLIENT_STATE) : EndIf
  If *h\decoding=0
   If *stream\status>=200
    rc=wcH2HeadersEnd(*s) : If rc<>0 : ProcedureReturn rc : EndIf
   ElseIf *r\status<200
    *r\status=0 : *r\state=#WEB_RESPONSE_STATUS
   EndIf
  EndIf
  If *request\state<>2 And *r\status<200
   rc=H2ClientData(*h,*s\h2Stream,body,bytes,endBody)
   If rc=#H2_BUSY : ProcedureReturn 0 : EndIf
   If rc<0 : ProcedureReturn wcFail(*s,rc) : EndIf
   *s\consumed=rc
  EndIf
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i wcH2Next(*s.WebClient,*request.WebRequest,*response.WebResponse,now.i,timeout.i)
 Define *previous.WebResponse,*h.H2Client,st.i
 *h=*s\h2 : *previous=*s\response
 If *s\state<>2 Or *previous\reusable=0 Or *h\goaway<>0 Or *h\state<>3 Or *h\event<>0 Or *h\activeStreams<>0 Or *h\txLength<>0 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
 If *request\state<>1 Or *response\state<>#WEB_RESPONSE_STATUS Or *response\error<>0 Or *response\allowUpgrade<>0 Or timeout<1 Or timeout>$7FFFFFFF : ProcedureReturn #WEB_CLIENT_ARGUMENT : EndIf
 st=WebTransportState(@*h\connection) : If st<>1 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
 *s\request=*request : *s\response=*response : *s\started=now : *s\timeout=timeout : *s\state=1
 *s\h2Stream=0 : *s\h2Offset=0 : *s\h2Headers=0 : *s\h2Trailers=0 : *s\h2Ending=0 : *s\h2ResetCode=0
 *s\sent=0 : *s\received=0 : *s\written=0 : *s\consumed=0 : *s\error=0
 *s\h2SentStart=*h\sent : *s\h2ReceivedStart=*h\received
 *h\started=now : *h\timeout=timeout
 ProcedureReturn 0
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
  If *s\h2<>0 : ProcedureReturn wcH2Step(*s,body,bytes,endBody,output,capacity,now) : EndIf
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
  If *s\h2<>0 : ProcedureReturn wcH2Next(*s,*request,*response,now,timeout) : EndIf
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
