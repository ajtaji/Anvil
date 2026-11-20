XIncludeFile "Anvil/Core/net_tcp_cmd.pbi"

; ======================================================================
;  CmdHttp - http get <url>
; ======================================================================
XIncludeFile "Anvil/Core/web_transport.pbi"
Global httpc_url.WebUrl,httpc_request.WebRequest,httpc_response.WebResponse,httpc_client.WebClient
Global Dim httpc_host.a[256]
Global Dim httpc_target.a[#WEB_URL_TARGET]
Global Dim httpc_headers.a[4096]
Global Dim httpc_line.a[4096]
Global Dim httpc_metadata.a[#WEB_RESPONSE_MAX_METADATA]
Global Dim httpc_tx.a[2048]
Global Dim httpc_rx.a[2048]
Global Dim httpc_output.a[2048]

Procedure http_Get()
 Define url.i,n.i,rc.i,start.i,total.i,shown.i,i.i,headerShown.i
 url=ArgRest()
 If url=0
  PrintN("!! http get needs a URL, so nothing was fetched.")
  PrintN("   http get http://example.com/") : ProcedureReturn
 EndIf
 n=0 : While n<=#WEB_URL_LIMIT And PeekA(url+n)<>0 : n=n+1 : Wend
 httpc_url\host=@httpc_host[0] : httpc_url\hostCapacity=256
 httpc_url\target=@httpc_target[0] : httpc_url\targetCapacity=#WEB_URL_TARGET
 rc=WebUrlParse(url,n,0,@httpc_url)
 If rc=0 And httpc_url\secure<>0 : rc=#WEB_URL_SCHEME : EndIf
 If rc<0
  Print("!! Invalid or unsupported plain HTTP URL (code ") : PrintDec(rc) : PrintN(").")
  ProcedureReturn
 EndIf
 rc=WebRequestInit(@httpc_request,@httpc_url,"GET",3,0,0,@httpc_headers[0],4096)
 If rc=0 : rc=WebRequestHeader(@httpc_request,"Accept-Encoding",15,"identity",8) : EndIf
 If rc=0 : rc=WebRequestHeader(@httpc_request,"User-Agent",10,"Anvil",5) : EndIf
 If rc=0 : rc=WebRequestFinishHeaders(@httpc_request) : EndIf
 If rc=0 : rc=WebResponseInit(@httpc_response,@httpc_line[0],4096,@httpc_metadata[0],#WEB_RESPONSE_MAX_METADATA,0) : EndIf
 If rc<0
  Print("!! HTTP request setup refused (code ") : PrintDec(rc) : PrintN(").") : ProcedureReturn
 EndIf
 If HwLinkOpen(1)=0 : ProcedureReturn : EndIf
 Print("GET ") : UartWriteStr(httpc_url\target) : Print(" from ") : UartWriteStr(httpc_url\host)
 PrintN(". Press a key to stop.") : UartDrain()
 start=millis()
 rc=WebClientStart(@httpc_client,@httpc_url,@httpc_request,@httpc_response,@httpc_tx[0],2048,@httpc_rx[0],2048,start,30000)
 While rc=0
  If NetBreakCheck()
   rc=WebClientCancel(@httpc_client) : Break
  EndIf
  PayNetCommandPump(1)
  rc=WebClientStep(@httpc_client,0,0,1,@httpc_output[0],2048,millis())
  total=total+httpc_client\written
  For i=0 To httpc_client\written-1
   If shown<#TCPCMD_BODY_SHOW
    gHttpBody[shown]=httpc_output[i] : shown=shown+1
   EndIf
  Next
 Wend
 WebClientClose(@httpc_client)
 If rc<0
  Print("!! HTTP exchange refused or incomplete (code ") : PrintDec(rc) : PrintN(").")
  ProcedureReturn
 EndIf
 Print("HTTP/1.1 ") : PrintDec(httpc_response\status)
 Print(" - ") : PrintDec(total) : Print(" body bytes in ") : PrintDec((millis()-start) & $FFFFFFFF)
 Print(" ms over ") : PrintDec(httpc_client\received) : PrintN(" bytes of response.")
 If httpc_response\status>=300 And httpc_response\status<400
  PrintN("This redirect was NOT followed. Response headers:")
  tcp_PutBytes(@httpc_metadata[0],httpc_response\headerLength)
 EndIf
 If shown>0
  Print("--- the first ") : PrintDec(shown) : PrintN(" body bytes ---")
  tcp_PutBytes(@gHttpBody[0],shown) : PrintN("--- end ---")
 Else
  PrintN("The response carried no body.")
 EndIf
EndProcedure

Procedure CmdHttp()
  If RequireCap(#CAP_NET, "http", "this board has no network interface Anvil can use") = 0
    ProcedureReturn
  EndIf
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("get") <> 0
    http_Get()
    ProcedureReturn
  EndIf
  If WordIs("serve") <> 0
    HttpServerStartCommand()
    ProcedureReturn
  EndIf
  If WordIs("stop") <> 0
    If ArgWord() <> 0
      PrintN("HTTP error 1: Extra arguments. Use http stop without a port or other arguments.")
      ProcedureReturn
    EndIf
    HttpServerStop()
    PrintN("HTTP server is stopped.")
    ProcedureReturn
  EndIf
  If WordIs("status") <> 0
    If ArgWord() <> 0
      PrintN("HTTP error 1: Extra arguments. Use http status without other arguments.")
      ProcedureReturn
    EndIf
    HttpServerStatus()
    ProcedureReturn
  EndIf
  PrintN("!! http expects get, serve, stop or status. No operation was performed.")
  PrintN("   http get http://example.com/")
  PrintN("   http serve [port]   default 8080; public static pages only")
  PrintN("   http status         http stop")
  PrintN("   These are PLAIN HTTP operations, without TLS. An https URL is")
  PrintN("   refused by name rather than fetched in clear.")
EndProcedure
