; Bounded native HTTP/1.1 connection service. Dependencies supplied BEFORE:
; http_head.pbi; nonblocking HtAccept(), HtRead(h,p,n), HtWrite(h,p,n),
; HtClose(h). Accept: positive unique owned handle,0 idle,negative error.
; Read/write: 0 would-block, positive bytes<=n, negative EOF/error. Close
; transfers ownership back to transport, which must drain queued writes or
; abort by its own bounded deadline. One serialized owner, never IRQ context.
#HS_CONNECTIONS = 4
#HS_HEAD = 4096
#HS_BODY = 1024
#HS_INPUT = 5120
#HS_OUTPUT = 4096
#HS_SLICE = 512
#HS_TIMEOUT = 10000
#HS_REQUESTS = 16
Global Dim hs_input.a[20480]
Global Dim hs_output.a[16384]
Global Dim hs_meta.i[20]
Global Dim hs_handle.i[4]
Global Dim hs_state.i[4]
Global Dim hs_used.i[4]
Global Dim hs_sent.i[4]
Global Dim hs_size.i[4]
Global Dim hs_due.i[4]
Global Dim hs_requests.i[4]
Global Dim hs_consumed.i[4]
Global Dim hs_close.i[4]
Global hs_clock.i
Global hs_errors.i

Procedure.i HsIn(slot.i)
  ProcedureReturn @hs_input[0] + slot * #HS_INPUT
EndProcedure
Procedure.i HsOut(slot.i)
  ProcedureReturn @hs_output[0] + slot * #HS_OUTPUT
EndProcedure
Procedure.i HsMeta(slot.i)
  ProcedureReturn @hs_meta[0] + slot * 5 * SizeOf(.i)
EndProcedure
Procedure HsDrop(slot.i)
  If hs_handle[slot] <> 0
    HtClose(hs_handle[slot])
  EndIf
  hs_handle[slot] = 0
  hs_state[slot] = 0
  hs_used[slot] = 0
  hs_sent[slot] = 0
  hs_size[slot] = 0
  hs_requests[slot] = 0
  hs_consumed[slot] = 0
  hs_close[slot] = 0
EndProcedure
Procedure.i HsByte(slot.i, value.i)
  If hs_size[slot] >= #HS_OUTPUT
    ProcedureReturn 0
  EndIf
  PokeA(HsOut(slot) + hs_size[slot], value)
  hs_size[slot] = hs_size[slot] + 1
  ProcedureReturn 1
EndProcedure
Procedure HsText(slot.i, text.i)
  Protected n.i
  For n = 0 To #HS_OUTPUT - 1
    If PeekA(text + n) = 0
      ProcedureReturn
    EndIf
    If HsByte(slot, PeekA(text + n)) = 0
      ProcedureReturn
    EndIf
  Next
EndProcedure
Procedure HsLine(slot.i)
  HsByte(slot, 13)
  HsByte(slot, 10)
EndProcedure
Procedure HsNumber(slot.i, number.i)
  Protected divisor.i
  divisor = 1000000000
  While divisor > 1 And number / divisor = 0
    divisor = divisor / 10
  Wend
  While divisor > 0
    HsByte(slot, 48 + (number / divisor) % 10)
    divisor = divisor / 10
  Wend
EndProcedure
Procedure HsRespond(slot.i, status.i, headOnly.i)
  Protected body.i
  Protected length.i
  Protected html.i
  body = "Request refused."
  html = 0
  If status = 200
    body = "Anvil HTTP service is ready."
  ElseIf status = 201
    status = 200
    html = 1
    body = "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content=width=device-width><title>Anvil</title><style>body{font:18px system-ui;background:#111827;color:#e5e7eb;max-width:48rem;margin:10vh auto;padding:2rem}a{color:#7dd3fc}main{border:1px solid #374151;border-radius:1rem;padding:2rem}h1{color:white}</style><main><h1>Anvil web server</h1><p>The native HTTP service is running.</p><p>The forum is under construction. Registration and sign-in are not enabled.</p><p><a href=/health>Service health</a></p></main></html>"
  ElseIf status = 404
    body = "Not found."
  EndIf
  length = 0
  While PeekA(body + length) <> 0 And length < 2048
    length = length + 1
  Wend
  hs_size[slot] = 0
  hs_sent[slot] = 0
  HsText(slot, "HTTP/1.1 ")
  HsNumber(slot, status)
  HsText(slot, " Response")
  HsLine(slot)
  If hs_close[slot]
    HsText(slot, "Connection: close")
  Else
    HsText(slot, "Connection: keep-alive")
  EndIf
  HsLine(slot)
  HsText(slot, "Content-Length: ")
  HsNumber(slot, length)
  HsLine(slot)
  If html
    HsText(slot, "Content-Type: text/html; charset=utf-8")
  Else
    HsText(slot, "Content-Type: text/plain; charset=utf-8")
  EndIf
  HsLine(slot)
  HsText(slot, "X-Content-Type-Options: nosniff")
  HsLine(slot)
  If status = 405
    HsText(slot, "Allow: GET, HEAD")
    HsLine(slot)
  EndIf
  HsLine(slot)
  If headOnly = 0 : HsText(slot, body) : EndIf
  hs_state[slot] = 2
  hs_due[slot] = hs_clock
EndProcedure
Procedure HsRoute(slot.i)
  Protected meta.i
  Protected headOnly.i
  Protected target.i
  Protected size.i
  meta = HsMeta(slot)
  headOnly = FhEqual(HsIn(slot), PeekI(meta + 4 * SizeOf(.i)), "HEAD", 0)
  If headOnly = 0 And FhEqual(HsIn(slot), PeekI(meta + 4 * SizeOf(.i)), "GET", 0) = 0
    HsRespond(slot, 405, 0)
    ProcedureReturn
  EndIf
  target = HsIn(slot) + PeekI(meta + 2 * SizeOf(.i))
  size = PeekI(meta + 3 * SizeOf(.i))
  If FhEqual(target, size, "/", 0)
    HsRespond(slot, 201, headOnly)
  ElseIf FhEqual(target, size, "/health", 0)
    HsRespond(slot, 200, headOnly)
  Else
    HsRespond(slot, 404, headOnly)
  EndIf
EndProcedure

Procedure HsReject(slot.i, status.i)
  Protected headOnly.i
  hs_close[slot] = 1
  If hs_used[slot] >= 5
    headOnly = FhEqual(HsIn(slot), 5, "HEAD ", 0)
  EndIf
  HsRespond(slot, status, headOnly)
EndProcedure

Procedure.i HsHasExpectation(slot.i)
  Protected n.i
  Protected size.i
  Protected input.i
  input = HsIn(slot)
  size = PeekI(HsMeta(slot))
  For n = 2 To size - 7
    If PeekA(input + n - 2) = 13 And PeekA(input + n - 1) = 10
      If FhEqual(input + n, 7, "expect:", 1)
        ProcedureReturn 1
      EndIf
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

; Called only after the strict head parser admits a complete header block.
; Every Connection field contributes tokens; close wins regardless of order.
; Invalid list syntax conservatively disables reuse, never changes framing.
Procedure.i HsWantsClose(slot.i)
  Protected input.i
  Protected size.i
  Protected n.i
  Protected finish.i
  Protected first.i
  Protected last.i
  input = HsIn(slot)
  size = PeekI(HsMeta(slot))
  For n = 2 To size - 11
    If PeekA(input + n - 2) = 13 And PeekA(input + n - 1) = 10
      If FhEqual(input + n, 11, "connection:", 1)
        n = n + 11
        finish = n
        While finish < size And PeekA(input + finish) <> 13
          finish = finish + 1
        Wend
        While n < finish
          While n < finish And (PeekA(input + n) = 32 Or PeekA(input + n) = 9 Or PeekA(input + n) = 44)
            n = n + 1
          Wend
          first = n
          While n < finish And FhToken(PeekA(input + n)) <> 0
            n = n + 1
          Wend
          last = n
          If last > first
            If FhEqual(input + first, last - first, "close", 1) : ProcedureReturn 1 : EndIf
          EndIf
          While n < finish And (PeekA(input + n) = 32 Or PeekA(input + n) = 9)
            n = n + 1
          Wend
          If n < finish
            If PeekA(input + n) <> 44 : ProcedureReturn 1 : EndIf
            n = n + 1
          EndIf
        Wend
      EndIf
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i HsPoll(now.i)
  Protected slot.i
  Protected freeSlot.i
  Protected handle.i
  Protected n.i
  Protected want.i
  Protected parsed.i
  Protected total.i
  Protected left.i
  Protected pos.i
  If now < hs_clock
    ProcedureReturn 0
  EndIf
  hs_clock = now
  freeSlot = -1
  For slot = 0 To #HS_CONNECTIONS - 1
    If hs_state[slot] = 0 And freeSlot = -1 : freeSlot = slot : EndIf
  Next
  If freeSlot >= 0
    handle = HtAccept()
    If handle > 0
      hs_handle[freeSlot] = handle
      hs_state[freeSlot] = 1
      hs_due[freeSlot] = now
    ElseIf handle < 0
      hs_errors = hs_errors + 1
    EndIf
  EndIf
  For slot = 0 To #HS_CONNECTIONS - 1
    If hs_state[slot] <> 0
      If now - hs_due[slot] >= #HS_TIMEOUT
        HsDrop(slot)
      ElseIf hs_state[slot] = 1
        want = #HS_INPUT - hs_used[slot]
        If want > #HS_SLICE : want = #HS_SLICE : EndIf
        n = 0
        parsed = ForumHttpHead(HsIn(slot), hs_used[slot], #HS_HEAD, #HS_BODY, HsMeta(slot))
        total = PeekI(HsMeta(slot)) + PeekI(HsMeta(slot) + SizeOf(.i))
        ; Buffered complete requests precede a later transport EOF. Do not
        ; discard the next pipelined request when a peer half-closes its send.
        If parsed = 0 Or (parsed = 1 And hs_used[slot] < total)
          If want > 0 : n = HtRead(hs_handle[slot], HsIn(slot) + hs_used[slot], want) : EndIf
        EndIf
        If n < 0 Or n > want
          HsDrop(slot)
        Else
          hs_used[slot] = hs_used[slot] + n
          parsed = ForumHttpHead(HsIn(slot), hs_used[slot], #HS_HEAD, #HS_BODY, HsMeta(slot))
          If parsed > 1
            HsReject(slot, parsed)
          ElseIf parsed = 1
            If HsHasExpectation(slot)
              HsReject(slot, 417)
            Else
              total = PeekI(HsMeta(slot)) + PeekI(HsMeta(slot) + SizeOf(.i))
              If hs_used[slot] >= total
                hs_consumed[slot] = total
                hs_requests[slot] = hs_requests[slot] + 1
                hs_close[slot] = HsWantsClose(slot)
                If hs_requests[slot] >= #HS_REQUESTS : hs_close[slot] = 1 : EndIf
                HsRoute(slot)
              EndIf
            EndIf
          ElseIf hs_used[slot] = #HS_INPUT
            HsReject(slot, 431)
          EndIf
        EndIf
      ElseIf hs_state[slot] = 2
        want = hs_size[slot] - hs_sent[slot]
        If want > #HS_SLICE : want = #HS_SLICE : EndIf
        n = HtWrite(hs_handle[slot], HsOut(slot) + hs_sent[slot], want)
        If n < 0 Or n > want
          HsDrop(slot)
        Else
          hs_sent[slot] = hs_sent[slot] + n
          If hs_sent[slot] = hs_size[slot]
            If hs_close[slot]
              HsDrop(slot)
            Else
              ; Preserve all already-read pipelined bytes, including a partial
              ; next head. One response completes before the next is routed.
              left = hs_used[slot] - hs_consumed[slot]
              For pos = 0 To left - 1
                PokeA(HsIn(slot) + pos, PeekA(HsIn(slot) + hs_consumed[slot] + pos))
              Next
              hs_used[slot] = left
              hs_sent[slot] = 0
              hs_size[slot] = 0
              hs_consumed[slot] = 0
              hs_state[slot] = 1
              hs_due[slot] = now
            EndIf
          EndIf
        EndIf
      EndIf
    EndIf
  Next
  ProcedureReturn 1
EndProcedure
Procedure HsStop()
  Protected slot.i
  For slot = 0 To #HS_CONNECTIONS - 1 : HsDrop(slot) : Next
EndProcedure
