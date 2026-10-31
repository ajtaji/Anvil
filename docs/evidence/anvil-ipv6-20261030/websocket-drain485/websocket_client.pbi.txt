; Cooperative WebSocket client over WebClient/WebTransport, RFC6455.
; Compose websocket_frame, websocket_handshake and the shared HTTP owners.
; Network pumping remains external. No private sockets, waits or RNG fallback.
; Caller owns every context/buffer for the complete lifetime of the connection.
#WS_RANDOM=-607
Structure WebSocketClient
  http.i
  frame.i
  accept.i
  protocol.i
  protocolBytes.i
  rng.i
  scratch.i
  state.i
  error.i
  txLength.i
  txOffset.i
  txOpcode.i
  closeSent.i
  closeReceived.i
  closeStarted.i
  written.i
  opcode.i
  messageKind.i
  fin.i
EndStructure

Procedure.i wscFail(*s.WebSocketClient,code.i)
  Define *h.WebClient
  *h=*s\http
  If *h<>0 : WebClientClose(*h) : EndIf
  *s\state=-1 : *s\error=code : ProcedureReturn code
EndProcedure

Procedure.i wscClosed(*s.WebSocketClient)
  Define *h.WebClient,rc.i
  *h=*s\http
  ; Send acceptance can leave plaintext or protected records queued in TLS.
  rc=WebTransportDrain(@*h\connection)
  If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
  If rc=0 : ProcedureReturn 0 : EndIf
  WebClientClose(*h) : *s\state=3 : ProcedureReturn 2
EndProcedure

; Bind AFTER WebClientStart with a finalized WebSocket request and a response
; explicitly enabled for upgrade. rng(buffer,bytes) must return bytes after
; filling with cryptographically unpredictable data, or fail. scratch>=128bytes.
; frame is initialized, expectedAccept is29bytes and protocol is one offeredtoken.
Procedure.i WebSocketClientBind(*s.WebSocketClient,*http.WebClient,*frame.WebSocketFrame,expectedAccept.i,protocol.i,protocolBytes.i,rng.i,scratch.i)
  Define i.i,*response.WebResponse
  If *s=0 : ProcedureReturn #WS_ARGUMENT : EndIf
  For i=0 To SizeOf(WebSocketClient)-SizeOf(.i) Step SizeOf(.i) : PokeI(*s+i,0) : Next
  If *http=0 Or *frame=0 Or expectedAccept=0 Or scratch=0 Or rng=0 Or protocolBytes<0 Or protocolBytes>127 Or (protocolBytes>0 And protocol=0)
    *s\state=-1 : *s\error=#WS_ARGUMENT : ProcedureReturn #WS_ARGUMENT
  EndIf
  If *http\state<>1 Or *http\txCapacity<131 Or *frame\state<>0 Or *frame\error<>0 Or *frame\control=0
    *s\state=-1 : *s\error=#WS_ARGUMENT : ProcedureReturn #WS_ARGUMENT
  EndIf
  *response=*http\response
  If *response=0 : *s\state=-1 : *s\error=#WS_ARGUMENT : ProcedureReturn #WS_ARGUMENT : EndIf
  If *response\allowUpgrade=0 : *s\state=-1 : *s\error=#WS_ARGUMENT : ProcedureReturn #WS_ARGUMENT : EndIf
  *s\http=*http : *s\frame=*frame : *s\accept=expectedAccept
  *s\protocol=protocol : *s\protocolBytes=protocolBytes : *s\rng=rng : *s\scratch=scratch
  ProcedureReturn 0
EndProcedure

Procedure.i wscQueue(*s.WebSocketClient,opcode.i,data.i,bytes.i)
  Define *h.WebClient,*wsRandom,rc.i
  *h=*s\http
  If *s\txOffset<>*s\txLength : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  *wsRandom=*s\rng
  rc=wsRandom(*s\scratch,4)
  If rc<>4 : ProcedureReturn wscFail(*s,#WS_RANDOM) : EndIf
  rc=WebSocketFrameEncode(opcode,data,bytes,*s\scratch,*h\tx,*h\txCapacity)
  If rc<0 : ProcedureReturn rc : EndIf
  *s\txLength=rc : *s\txOffset=0 : *s\txOpcode=opcode
  ProcedureReturn 0
EndProcedure

; One complete bounded outgoing message/control frame. Source may be reused on
; success: it has been copied and masked into the HTTP context's TX buffer.
; A state error while TX is busy is backpressure, not connection failure.
Procedure.i WebSocketClientSend(*s.WebSocketClient,opcode.i,data.i,bytes.i,now.i)
  Define rc.i
  If *s=0 : ProcedureReturn #WS_ARGUMENT : EndIf
  If *s\state=-1 : ProcedureReturn *s\error : EndIf
  If *s\state<>1 : ProcedureReturn #WEB_CLIENT_STATE : EndIf
  rc=wscQueue(*s,opcode,data,bytes)
  If rc=0 And opcode=8 : *s\state=2 : *s\closeStarted=now : EndIf
  ProcedureReturn rc
EndProcedure

Procedure.i wscFrameEvent(*s.WebSocketClient,now.i)
  Define *f.WebSocketFrame,rc.i
  *f=*s\frame
  If *f\state=4
    *s\closeReceived=1
    If *s\closeSent : ProcedureReturn wscClosed(*s) : EndIf
    rc=wscQueue(*s,8,*f\control,*f\controlLength)
    If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
    If *s\state<>2 : *s\closeStarted=now : EndIf
    *s\state=2 : ProcedureReturn 0
  EndIf
  If *f\opcode=9
    rc=wscQueue(*s,10,*f\control,*f\controlLength)
    If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
  EndIf
  ProcedureReturn WebSocketFrameNext(*f)
EndProcedure

; Return0=progress,1=data-frame boundary,2=clean close,negative=failure.
; written may be nonzero before a boundary or a later error; retain fragmented
; text until FIN if the consumer requires whole-message validation.
Procedure.i WebSocketClientStep(*s.WebSocketClient,output.i,capacity.i,now.i)
  Define *h.WebClient,*f.WebSocketFrame,*response.WebResponse,rc.i,st.i
  If *s=0 : ProcedureReturn #WS_ARGUMENT : EndIf
  *s\written=0
  If *s\state=-1 : ProcedureReturn *s\error : EndIf
  If *s\state=3 : ProcedureReturn 2 : EndIf
  If capacity<0 Or (capacity>0 And output=0) : ProcedureReturn wscFail(*s,#WS_ARGUMENT) : EndIf
  *h=*s\http : *f=*s\frame
  If *h=0 Or *f=0 : ProcedureReturn wscFail(*s,#WS_ARGUMENT) : EndIf
  If *s\state=0
    rc=WebClientStep(*h,0,0,1,0,0,now)
    If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
    *response=*h\response
    If *response\status>=200 : ProcedureReturn wscFail(*s,#WS_HANDSHAKE) : EndIf
    If rc=0 : ProcedureReturn 0 : EndIf
    If rc<>2 : ProcedureReturn wscFail(*s,#WS_HANDSHAKE) : EndIf
    rc=WebSocketHandshakeCheck(*h\response,*s\accept,*s\protocol,*s\protocolBytes,*s\scratch,128)
    If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
    *s\state=1 : ProcedureReturn 0
  EndIf
  If *s\state=2 And ((now-*s\closeStarted) & $FFFFFFFF)>=2000 : ProcedureReturn wscFail(*s,#WEB_CLIENT_TIMEOUT) : EndIf
  ; Once both Close frames are accepted, only drain: no more reads or echoes.
  If *s\closeSent And *s\closeReceived And *s\txOffset=*s\txLength : ProcedureReturn wscClosed(*s) : EndIf
  st=WebTransportState(@*h\connection)
  If st<0 : ProcedureReturn wscFail(*s,st) : EndIf
  If st=0 : ProcedureReturn 0 : EndIf
  If st<>1 And st<>2 : ProcedureReturn wscFail(*s,#WEB_CLIENT_TRANSPORT) : EndIf
  ; Peer EOF does not prove our reply was sent. TCP half-close permits sending;
  ; a closed TLS transport must fail or reach the existing close deadline.
  If *s\txOffset<*s\txLength
    rc=WebTransportSend(@*h\connection,*h\tx+*s\txOffset,*s\txLength-*s\txOffset)
    If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
    If rc>*s\txLength-*s\txOffset : ProcedureReturn wscFail(*s,#WEB_CLIENT_TRANSPORT) : EndIf
    *s\txOffset=*s\txOffset+rc
    If *s\txOffset<*s\txLength : ProcedureReturn 0 : EndIf
    If *s\txOpcode=8 : *s\closeSent=1 : EndIf
    If *s\closeSent And *s\closeReceived : ProcedureReturn wscClosed(*s) : EndIf
  EndIf
  If *f\state=3 Or *f\state=4
    rc=wscFrameEvent(*s,now)
    If rc<>0 Or *s\txOffset<*s\txLength : ProcedureReturn rc : EndIf
    If *s\closeSent And *s\closeReceived : ProcedureReturn rc : EndIf
  EndIf
  If *h\rxOffset=*h\rxLength
    *h\rxOffset=0 : *h\rxLength=0
    rc=WebTransportRecv(@*h\connection,*h\rx,*h\rxCapacity)
    If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
    If rc>*h\rxCapacity : ProcedureReturn wscFail(*s,#WEB_CLIENT_TRANSPORT) : EndIf
    *h\rxLength=rc
    If rc=0 And st=2 : ProcedureReturn wscFail(*s,WebSocketFrameEof(*f)) : EndIf
  EndIf
  If *h\rxOffset=*h\rxLength : ProcedureReturn 0 : EndIf
  rc=WebSocketFrameFeed(*f,*h\rx+*h\rxOffset,*h\rxLength-*h\rxOffset,output,capacity)
  *h\rxOffset=*h\rxOffset+*f\consumed : *s\written=*f\written
  *s\opcode=*f\opcode : *s\messageKind=*f\messageKind : *s\fin=*f\fin
  If rc<0 : ProcedureReturn wscFail(*s,rc) : EndIf
  If rc=1
    If *f\opcode<8 : ProcedureReturn 1 : EndIf
    ProcedureReturn wscFrameEvent(*s,now)
  EndIf
  ProcedureReturn 0
EndProcedure

; Abort is explicit and immediate; graceful shutdown queues opcode8 with Send.
Procedure WebSocketClientAbort(*s.WebSocketClient)
  If *s=0 : ProcedureReturn : EndIf
  wscFail(*s,#WEB_CLIENT_CANCELLED)
EndProcedure
