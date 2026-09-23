; Shared CYW43 association retry controller.
;
; The board/security adapter owns credentials, PMK derivation, key handshake,
; output and progress. This procedure owns only the bounded join/retry flow,
; so Pi 3 and Pi 4 use the same association mechanics without importing each
; other's board code.

#ANVIL_WIFI_ASSOC_EVENT_REFUSED = 1
#ANVIL_WIFI_ASSOC_EVENT_RETRY = 2
#ANVIL_WIFI_ASSOC_EVENT_FAILED = 3
#ANVIL_WIFI_ASSOC_EVENT_KEYING = 4
#ANVIL_WIFI_ASSOC_EVENT_KEY_FAILED = 5

; Returns 1 only when association and the caller's key handshake both succeed.
; The handshake callback writes 1/0 to its aligned output slot. This avoids
; treating an untyped indirect-call return as a pointer in compiler frontends.
; Event callback receives (event, attemptIndex); progress callback is optional.
Procedure.i AnvilWifiAssociateCandidate(*ssid, ssidLen.i, timeoutMs.i, sliceMs.i, maxSlices.i, *handshakeFn, *progressFn, *eventFn)
  Define attempt.i
  Define result.i
  Define verdict.i
  Define slices.i
  Define handshakeResult.i
  If *ssid = 0 Or ssidLen < 1 Or ssidLen > 32 Or timeoutMs < 1 Or sliceMs < 1 Or maxSlices < 1 Or *handshakeFn = 0 Or *eventFn = 0
    ProcedureReturn 0
  EndIf

  Cyw43Disassoc(2000)
  Cyw43DrainEvents(120)
  For attempt = 0 To 1
    result = Cyw43JoinStart(*ssid, ssidLen, timeoutMs)
    If result <> 0
      eventFn(#ANVIL_WIFI_ASSOC_EVENT_REFUSED, attempt)
      Cyw43Disassoc(2000)
      Cyw43DrainEvents(150)
      Continue
    EndIf

    slices = 0
    verdict = #CYW43_JOIN_RUNNING
    While verdict = #CYW43_JOIN_RUNNING And slices < maxSlices
      verdict = Cyw43JoinPoll(sliceMs)
      slices = slices + 1
      If progressFn <> 0 : progressFn() : EndIf
    Wend
    If verdict = #CYW43_JOIN_JOINED
      eventFn(#ANVIL_WIFI_ASSOC_EVENT_KEYING, attempt)
      If progressFn <> 0 : progressFn() : EndIf
      handshakeResult = 0
      handshakeFn(@handshakeResult)
      If handshakeResult <> 0
        ProcedureReturn 1
      EndIf
      eventFn(#ANVIL_WIFI_ASSOC_EVENT_KEY_FAILED, attempt)
    ElseIf attempt = 0
      eventFn(#ANVIL_WIFI_ASSOC_EVENT_RETRY, attempt)
      If progressFn <> 0 : progressFn() : EndIf
    Else
      eventFn(#ANVIL_WIFI_ASSOC_EVENT_FAILED, attempt)
      If progressFn <> 0 : progressFn() : EndIf
    EndIf
    Cyw43Disassoc(2000)
    Cyw43DrainEvents(150)
  Next
  ProcedureReturn 0
EndProcedure
