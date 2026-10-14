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

#HTTPSC_REQ_MAX  = 1024
#HTTPSC_WAIT_MS  = 30000
#HTTPSC_SHOW     = 600

Global Dim httpsc_req.a[#HTTPSC_REQ_MAX]
Global Dim httpsc_host.a[256]
Global Dim httpsc_buf.a[2048]
Global httpsc_reqLen.i

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

  u = ArgWord()
  If u = 0
    PrintN("https get <url>   for example: https get https://example.com/")
    ProcedureReturn
  EndIf
  ; skip "https://"
  If PeekA(u) = 104 And PeekA(u + 4) = 115 And PeekA(u + 5) = 58 And PeekA(u + 6) = 47 And PeekA(u + 7) = 47
    u = u + 8
  EndIf
  n = 0
  port = 443
  While PeekA(u + n) <> 0 And PeekA(u + n) <> 47 And PeekA(u + n) <> 58 And n < 253
    httpsc_host[n] = PeekA(u + n)
    n = n + 1
  Wend
  httpsc_host[n] = 0
  If n = 0
    PrintN("https get: no host name in that URL.")
    ProcedureReturn
  EndIf
  i = n
  If PeekA(u + i) = 58
    i = i + 1
    port = 0
    While PeekA(u + i) >= 48 And PeekA(u + i) <= 57
      port = port * 10 + PeekA(u + i) - 48
      i = i + 1
    Wend
  EndIf
  pathAt = u + i

  httpsc_reqLen = 0
  httpsc_Put("GET ")
  If PeekA(pathAt) = 47
    httpsc_Put(pathAt)
  Else
    httpsc_Put("/")
  EndIf
  httpsc_Put(" HTTP/1.1") : httpsc_Crlf()
  httpsc_Put("Host: ") : httpsc_Put(@httpsc_host[0]) : httpsc_Crlf()
  httpsc_Put("User-Agent: Anvil") : httpsc_Crlf()
  httpsc_Put("Accept: */*") : httpsc_Crlf()
  httpsc_Put("Connection: close") : httpsc_Crlf()
  httpsc_Crlf()

  h = TlsClientOpen(@httpsc_host[0], port)
  If h < 0
    Print("https: the connection was not opened: ")
    tlsc_Say(gSvcDetail) : PrintNl()
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
      tlsc_Say(gSvcDetail) : PrintNl()
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
      For i = 0 To k - 1
        c = httpsc_buf[i]
        If inHead <> 0
          If c = 10
            PrintNl()
            If lastNl <> 0
              inHead = 0
            EndIf
            lastNl = 1
          ElseIf c <> 13
            UartWrite(c)
            lastNl = 0
          EndIf
        Else
          total = total + 1
          If shown < #HTTPSC_SHOW
            If c = 10 Or (c >= 32 And c < 127)
              UartWrite(c)
            Else
              UartWrite(46)
            EndIf
            shown = shown + 1
          EndIf
        EndIf
      Next
    EndIf
    If st = #SVC_TLS_PEER_CLOSED And k <= 0
      Break
    EndIf
    If ((millis() - t0) & $FFFFFFFF) > #HTTPSC_WAIT_MS
      PrintNl()
      PrintN("https: stopped waiting after 30 seconds.")
      Break
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
