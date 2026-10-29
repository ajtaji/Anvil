; ======================================================================
;  tls_cmd.pbi - the monitor's own HTTPS: `https get <url>` and `tls`.
;
;  `https get` runs the SAME connection engine a payload's TLS slots run
;  (Anvil/Core/tls_client.pbi): name, TCP, TLS 1.3, the chain verified
;  against the root store, the host name and dates checked. So a working
;  `https get` at the prompt is the proof a payload can reach that server.
;
;    https get <url>      GET over TLS 1.3; prints the status line, the
;                         headers, the body's size and its first bytes
;    tls                  the connection and the root store
;    tls roots            the root store by kind
;    tls reload           read the root bundle again (after copying a newer
;                         one to the stick)
; ======================================================================

EnableExplicit
XIncludeFile "Anvil/Network/web_url.pbi"
XIncludeFile "Anvil/Network/web_response.pbi"
XIncludeFile "Anvil/Network/web_request.pbi"
XIncludeFile "Anvil/Core/web_transport.pbi"

#HTTPSC_REQ_MAX  = 1024
#HTTPSC_WAIT_MS  = 30000
#HTTPSC_SHOW     = 600

Global Dim httpsc_req.a[#HTTPSC_REQ_MAX]
Global Dim httpsc_host.a[256]
Global Dim httpsc_buf.a[2048]
Global httpsc_reqLen.i
Global httpsc_url.WebUrl
Global Dim httpsc_target.a[#WEB_URL_TARGET]
Global httpsc_request.WebRequest
Global httpsc_response.WebResponse
Global Dim httpsc_line.a[4096]
Global Dim httpsc_headers.a[#WEB_RESPONSE_MAX_METADATA]
Global Dim httpsc_decoded.a[2048]

Procedure httpsc_PutPort(port.i)
  Define divisor.i
  divisor=10000
  While divisor>1 And port<divisor : divisor=divisor/10 : Wend
  While divisor>0
    httpsc_req[httpsc_reqLen]=48+port/divisor
    httpsc_reqLen=httpsc_reqLen+1
    port=port%divisor : divisor=divisor/10
  Wend
EndProcedure

Procedure httpsc_Put(*s)
  Define i.i
  i = 0
  While PeekA(*s + i) <> 0 And httpsc_reqLen < #HTTPSC_REQ_MAX - 1
    httpsc_req[httpsc_reqLen] = PeekA(*s + i)
    httpsc_reqLen = httpsc_reqLen + 1
    i = i + 1
  Wend
EndProcedure

Procedure httpsc_Crlf()
  httpsc_req[httpsc_reqLen] = 13
  httpsc_req[httpsc_reqLen + 1] = 10
  httpsc_reqLen = httpsc_reqLen + 2
EndProcedure

; https get <url> - [https://]host[:port][/path]
Procedure CmdHttpsGet()
  Define u.i
  Define i.i
  Define n.i
  Define port.i
  Define pathAt.i
  Define h.i
  Define st.i
  Define t0.i
  Define sent.i
  Define k.i
  Define total.i
  Define shown.i
  Define c.i
  Define inHead.i
  Define lastNl.i
  Define urlResult.i
  Define offset.i
  Define consumed.i
  Define responseError.i

  u = ArgWord()
  If u = 0
    PrintN("https get <url>   for example: https get https://example.com/")
    ProcedureReturn
  EndIf
  n=0
  While n<=#WEB_URL_LIMIT
    If PeekA(u+n)=0 : Break : EndIf
    n=n+1
  Wend
  httpsc_url\host=@httpsc_host[0] : httpsc_url\hostCapacity=256
  httpsc_url\target=@httpsc_target[0] : httpsc_url\targetCapacity=#WEB_URL_TARGET
  urlResult=WebUrlParse(u,n,1,@httpsc_url)
  If urlResult=#WEB_URL_OK And httpsc_url\secure=0 : urlResult=#WEB_URL_SCHEME : EndIf
  If urlResult<>#WEB_URL_OK
    Print("https get: invalid or unsupported HTTPS URL (code ")
    PrintDec(urlResult) : PrintN(").")
    ProcedureReturn
  EndIf
  ; Reserve space for all fixed headers and the longest decimal port. Refuse
  ; before opening a connection; never send a silently shortened request.
  If httpsc_url\targetLength+httpsc_url\hostLength+200>=#HTTPSC_REQ_MAX
    PrintN("https get: request exceeds the command buffer.")
    ProcedureReturn
  EndIf
  port=httpsc_url\port
  pathAt=httpsc_url\target

  responseError=WebRequestInit(@httpsc_request,@httpsc_url,"GET",3,0,0,@httpsc_req[0],#HTTPSC_REQ_MAX)
  If responseError=0 : responseError=WebRequestHeader(@httpsc_request,"Accept-Encoding",15,"identity",8) : EndIf
  If responseError=0 : responseError=WebRequestHeader(@httpsc_request,"User-Agent",10,"Anvil",5) : EndIf
  If responseError=0 : responseError=WebRequestHeader(@httpsc_request,"Accept",6,"*/*",3) : EndIf
  If responseError=0 : responseError=WebRequestFinishHeaders(@httpsc_request) : EndIf
  If responseError<0 : PrintN("https: request headers could not be serialized.") : ProcedureReturn : EndIf
  httpsc_reqLen=httpsc_request\length

  responseError=WebResponseInit(@httpsc_response,@httpsc_line[0],4096,@httpsc_headers[0],#WEB_RESPONSE_MAX_METADATA,0)
  If responseError<0 : PrintN("https: response storage could not be initialized.") : ProcedureReturn : EndIf
  h = TlsClientOpen(@httpsc_host[0], port)
  If h < 0
    Print("https: the connection was not opened: ")
    If gSvcDetail <> 0 : str_print_at(gSvcDetail) : EndIf
    PrintNl()
    ProcedureReturn
  EndIf
  Print("https: ")
  str_print_at(@httpsc_host[0])
  Print(":")
  PrintDec(port)
  PrintN(" - resolving, connecting, TLS 1.3 handshake...")

  t0 = millis()
  sent = 0
  total = 0
  shown = 0
  inHead = 1
  lastNl = 0
  Repeat
    PayNetCommandPump(20)
    st = TlsClientState(h)
    If st < 0
      Print("https: FAILED - ")
      If gSvcDetail <> 0 : str_print_at(gSvcDetail) : EndIf
      PrintNl()
      TlsClientShow()
      TlsClientClose(h)
      ProcedureReturn
    EndIf
    If st = #SVC_TLS_OPEN And sent < httpsc_reqLen
      If sent = 0
        PrintN("https: TLS 1.3 established; the certificate chain verified to a root in the store.")
      EndIf
      k = TlsClientSend(h, @httpsc_req[sent], httpsc_reqLen - sent)
      If k > 0
        sent = sent + k
      EndIf
    EndIf
    k = TlsClientRecv(h, @httpsc_buf[0], 2048)
    If k > 0
      offset=0
      While offset<k And httpsc_response\state<>#WEB_RESPONSE_DONE
        consumed=WebResponseFeed(@httpsc_response,@httpsc_buf[offset],k-offset,@httpsc_decoded[0],2048)
        If consumed<0
          Print("https: HTTP response refused (code ") : PrintDec(consumed) : PrintN(").")
          TlsClientClose(h) : ProcedureReturn
        EndIf
        offset=offset+consumed
        If inHead<>0 And httpsc_response\status>=200 And httpsc_response\state<>#WEB_RESPONSE_HEADERS
          For i=0 To httpsc_response\headerLength-1
            c=httpsc_headers[i]
            If c=10 : PrintNl() : ElseIf c<>13 : UartWrite(c) : EndIf
          Next
          inHead=0
        EndIf
        total=total+httpsc_response\written
        For i=0 To httpsc_response\written-1
          If shown<#HTTPSC_SHOW
            c=httpsc_decoded[i]
            If c=10 Or (c>=32 And c<127) : UartWrite(c) : Else : UartWrite(46) : EndIf
            shown=shown+1
          EndIf
        Next
        If consumed=0 And httpsc_response\written=0
          PrintN("https: response processing made no progress.")
          TlsClientClose(h) : ProcedureReturn
        EndIf
      Wend
    EndIf
    If httpsc_response\state=#WEB_RESPONSE_DONE : Break : EndIf
    If st = #SVC_TLS_PEER_CLOSED And k <= 0
      responseError=WebResponseEof(@httpsc_response)
      If responseError<0
        Print("https: server closed an incomplete response (code ") : PrintDec(responseError) : PrintN(").")
        TlsClientClose(h) : ProcedureReturn
      EndIf
      Break
    EndIf
    If ((millis() - t0) & $FFFFFFFF) > #HTTPSC_WAIT_MS
      PrintNl()
      PrintN("https: stopped waiting after 30 seconds; response incomplete.")
      TlsClientClose(h) : ProcedureReturn
    EndIf
  ForEver
  PrintNl()
  Print("https: body ")
  PrintDec(total)
  Print(" bytes")
  If total > shown
    Print(" (the first ")
    PrintDec(shown)
    Print(" shown)")
  EndIf
  PrintNl()
  TlsClientClose(h)
EndProcedure

Procedure CmdHttps()
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("get") <> 0
    CmdHttpsGet()
    ProcedureReturn
  EndIf
  PrintN("https get <url>   fetch a page over TLS 1.3, verified against the root store")
EndProcedure

Procedure CmdTls()
  Define r.i
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("roots") <> 0
    TlsRootsEnsure()
    TlsRootsShow()
    ProcedureReturn
  EndIf
  If WordIs("reload") <> 0
    r = TlsRootsLoad(0)
    If r > 0
      Print("tls: ")
      PrintDec(r)
      PrintN(" roots registered.")
    Else
      Print("tls: the root store was not loaded - ")
      str_print_at(TlsRootsErrorText(r)) : PrintNl()
    EndIf
    TlsRootsShow()
    ProcedureReturn
  EndIf
  TlsClientShow()
  TlsRootsShow()
  PrintN("tls roots   tls reload   https get <url>")
EndProcedure
