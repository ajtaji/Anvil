; RFC6455 opening handshake over the existing HTTP serializer/parser.
; https://www.rfc-editor.org/rfc/rfc6455.txt sections4.1 and4.2.
; Protocol facts only; independently implemented. SHA1 is the existing owner.
; No extensions are requested or accepted. Optional subprotocol is one token.
; Caller supplies a fresh unpredictable16-byte nonce and disjoint buffers.
#WS_HANDSHAKE=-606
Procedure wsBase64(source.i,n.i,output.i)
  Define alphabet.i,i.i,j.i,a.i,b.i,c.i
  alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
  While i<n
    a=PeekA(source+i) & 255 : b=0 : c=0
    If i+1<n : b=PeekA(source+i+1) & 255 : EndIf
    If i+2<n : c=PeekA(source+i+2) & 255 : EndIf
    PokeA(output+j,PeekA(alphabet+(a>>2)))
    PokeA(output+j+1,PeekA(alphabet+(((a & 3)<<4)|(b>>4))))
    If i+1<n : PokeA(output+j+2,PeekA(alphabet+(((b & 15)<<2)|(c>>6)))) : Else : PokeA(output+j+2,61) : EndIf
    If i+2<n : PokeA(output+j+3,PeekA(alphabet+(c & 63))) : Else : PokeA(output+j+3,61) : EndIf
    i=i+3 : j=j+4
  Wend
  PokeA(output+j,0)
EndProcedure

; key25bytes, expectedAccept29bytes, scratch192bytes alignedto4.
; Finalize with WebRequestFinishHeaders after optional authentication/protocol.
; SHA1 streaming state is preserved; calls must remain serialized with SHA1.
Procedure.i WebSocketRequestInit(*q.WebRequest,*url.WebUrl,headers.i,capacity.i,nonce.i,key.i,expectedAccept.i,scratch.i)
  Define rc.i,i.i,guid.i
  If nonce=0 Or key=0 Or expectedAccept=0 Or scratch=0 Or (scratch & 3)<>0 : ProcedureReturn #WS_ARGUMENT : EndIf
  rc=WebRequestInit(*q,*url,"GET",3,0,1,headers,capacity)
  If rc<0 : ProcedureReturn rc : EndIf
  wsBase64(nonce,16,key)
  guid="258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
  For i=0 To 23 : PokeA(scratch+116+i,PeekA(key+i)) : Next
  For i=0 To 35 : PokeA(scratch+140+i,PeekA(guid+i)) : Next
  Sha1Snapshot(scratch) : Sha1Of(scratch+116,60,scratch+96) : Sha1Restore(scratch)
  wsBase64(scratch+96,20,expectedAccept)
  wqText(*q,"Connection: Upgrade") : wqByte(*q,13) : wqByte(*q,10)
  wqText(*q,"Upgrade: websocket") : wqByte(*q,13) : wqByte(*q,10)
  If *q\error<0 : ProcedureReturn *q\error : EndIf
  rc=WebRequestHeader(*q,"Sec-WebSocket-Version",21,"13",2)
  If rc<0 : ProcedureReturn rc : EndIf
  ProcedureReturn WebRequestHeader(*q,"Sec-WebSocket-Key",17,key,24)
EndProcedure

Procedure.i wsExact(p.i,n.i,want.i,wantN.i)
  Define i.i
  If n<>wantN : ProcedureReturn 0 : EndIf
  For i=0 To n-1 : If PeekA(p+i)<>PeekA(want+i) : ProcedureReturn 0 : EndIf : Next
  ProcedureReturn 1
EndProcedure

; scratch capacity>=128; values larger than scratch are explicit failures.
; Headers are retained by the HTTP parser; duplicate security fields refused.
Procedure.i WebSocketHandshakeCheck(*r.WebResponse,expectedAccept.i,protocol.i,protocolBytes.i,scratch.i,capacity.i)
  Define n.i,i.i,start.i,seen.i,occurrence.i,c.i
  If *r=0 Or expectedAccept=0 Or scratch=0 Or capacity<128 Or protocolBytes<0 Or protocolBytes>127 Or (protocolBytes>0 And protocol=0) : ProcedureReturn #WS_ARGUMENT : EndIf
  If *r\state<>#WEB_RESPONSE_DONE Or *r\error<>0 Or *r\status<>101 Or *r\allowUpgrade=0 : ProcedureReturn #WS_HANDSHAKE : EndIf
  For i=0 To protocolBytes-1 : If wrToken(PeekA(protocol+i))=0 : ProcedureReturn #WS_ARGUMENT : EndIf : Next
  n=WebResponseHeader(*r,"upgrade",0,scratch,capacity)
  If n<>9 Or wrEqual(scratch,n,"websocket")=0 : ProcedureReturn #WS_HANDSHAKE : EndIf
  If WebResponseHeader(*r,"upgrade",1,0,0)<>#WEB_RESPONSE_NOTFOUND : ProcedureReturn #WS_HANDSHAKE : EndIf
  n=WebResponseHeader(*r,"sec-websocket-accept",0,scratch,capacity)
  If n<>28 : ProcedureReturn #WS_HANDSHAKE : EndIf
  If wsExact(scratch,n,expectedAccept,28)=0 : ProcedureReturn #WS_HANDSHAKE : EndIf
  If WebResponseHeader(*r,"sec-websocket-accept",1,0,0)<>#WEB_RESPONSE_NOTFOUND : ProcedureReturn #WS_HANDSHAKE : EndIf
  If WebResponseHeader(*r,"sec-websocket-extensions",0,0,0)<>#WEB_RESPONSE_NOTFOUND : ProcedureReturn #WS_HANDSHAKE : EndIf
  n=WebResponseHeader(*r,"sec-websocket-protocol",0,scratch,capacity)
  If n<>#WEB_RESPONSE_NOTFOUND
    If n<=0 Or protocolBytes=0 : ProcedureReturn #WS_HANDSHAKE : EndIf
    If wsExact(scratch,n,protocol,protocolBytes)=0 : ProcedureReturn #WS_HANDSHAKE : EndIf
    If WebResponseHeader(*r,"sec-websocket-protocol",1,0,0)<>#WEB_RESPONSE_NOTFOUND : ProcedureReturn #WS_HANDSHAKE : EndIf
  EndIf
  occurrence=0 : seen=0
  Repeat
    n=WebResponseHeader(*r,"connection",occurrence,scratch,capacity)
    If n=#WEB_RESPONSE_NOTFOUND : Break : EndIf
    If n<0 : ProcedureReturn #WS_HANDSHAKE : EndIf
    i=0
    While i<n
      c=PeekA(scratch+i)
      If c=32 Or c=9 Or c=44 : i=i+1 : Continue : EndIf
      start=i
      While i<n
        If wrToken(PeekA(scratch+i))=0 : Break : EndIf
        i=i+1
      Wend
      If i=start : ProcedureReturn #WS_HANDSHAKE : EndIf
      If wrEqual(scratch+start,i-start,"upgrade") : seen=1 : EndIf
      While i<n
        c=PeekA(scratch+i) : If c<>32 And c<>9 : Break : EndIf : i=i+1
      Wend
      If i<n : If PeekA(scratch+i)<>44 : ProcedureReturn #WS_HANDSHAKE : EndIf : i=i+1 : EndIf
    Wend
    occurrence=occurrence+1
  ForEver
  If seen=0 : ProcedureReturn #WS_HANDSHAKE : EndIf
  ProcedureReturn 0
EndProcedure

; Parse standard ws/wss URLs through the same HTTP authority/target owner.
; scratch is disjoint from source and URL output buffers, capacity>=bytes+3.
Procedure.i WebSocketUrlParse(source.i,bytes.i,allowPlain.i,*url.WebUrl,scratch.i,capacity.i)
  Define secure.i,prefix.i,i.i
  If source=0 Or bytes<5 Or bytes>#WEB_URL_LIMIT-2 Or scratch=0 Or capacity<bytes+3 : ProcedureReturn #WEB_URL_ARGUMENT : EndIf
  If webUrlLower(PeekA(source))<>119 Or webUrlLower(PeekA(source+1))<>115 : ProcedureReturn #WEB_URL_SCHEME : EndIf
  prefix=2
  If webUrlLower(PeekA(source+2))=115 : secure=1 : prefix=3 : EndIf
  If bytes<prefix+3 Or PeekA(source+prefix)<>58 Or PeekA(source+prefix+1)<>47 Or PeekA(source+prefix+2)<>47 : ProcedureReturn #WEB_URL_SCHEME : EndIf
  For i=0 To bytes-1 : If PeekA(source+i)=35 : ProcedureReturn #WEB_URL_SYNTAX : EndIf : Next
  PokeA(scratch,104) : PokeA(scratch+1,116) : PokeA(scratch+2,116) : PokeA(scratch+3,112)
  If secure : PokeA(scratch+4,115) : EndIf
  For i=prefix To bytes-1 : PokeA(scratch+i+2,PeekA(source+i)) : Next
  PokeA(scratch+bytes+2,0)
  ProcedureReturn WebUrlParse(scratch,bytes+2,allowPlain,*url)
EndProcedure
