; Monitor-owned service control. Include after HTTP parser, transport and engine.
; Disabled until `http serve [port]`. Plain public static resources only.
; One cooperative network owner; no socket manipulation from interrupts.
Procedure HttpServerPoll()
  Protected now.i
  now = millis()
  If HtService(now) <> 0
    HsPoll(now)
  EndIf
EndProcedure

Procedure HttpServerStop()
  HsStop()
  HtStop()
EndProcedure

Procedure HttpServerStatus()
  If ht_owned = 0
    PrintN("HTTP server is stopped. Use http serve [port] to start it.")
    ProcedureReturn
  EndIf
  Print("HTTP server listens on port ")
  PrintDec(ht_port)
  PrintN(". Public resources: / and /health.")
  PrintN("Plain HTTP only; no accounts, private data or HTTPS endpoints.")
  PrintN("Bounded concurrent clients and keep-alive; service runs while the prompt polls.")
EndProcedure

Procedure HttpServerStartCommand()
  Protected token.i
  Protected port.i
  Protected count.i
  Protected value.i
  token = ArgWord()
  port = 8080
  If token <> 0
    port = 0
    count = 0
    While PeekA(token + count) <> 0
      value = PeekA(token + count)
      If value < 48 Or value > 57 Or count >= 5
        PrintN("HTTP error 1: Invalid port. Use http serve with a decimal port from 1 to 65535.")
        ProcedureReturn
      EndIf
      port = port * 10 + value - 48
      count = count + 1
    Wend
    If port < 1 Or port > 65535
      PrintN("HTTP error 1: Invalid port. Use a decimal port from 1 to 65535.")
      ProcedureReturn
    EndIf
  EndIf
  If ArgWord() <> 0
    PrintN("HTTP error 1: Extra arguments. Use http serve [port].")
    ProcedureReturn
  EndIf
  If ht_owned <> 0
    PrintN("HTTP error 2: The server is already running. Use http status or http stop first.")
    ProcedureReturn
  EndIf
  If HwLinkOpen(1) = 0
    ProcedureReturn
  EndIf
  If HtStart(port) = 0
    PrintN("HTTP error 3: No listener could be opened. Check tcp status for socket or port conflicts.")
    ProcedureReturn
  EndIf
  HttpServerPoll()
  HttpServerStatus()
EndProcedure
