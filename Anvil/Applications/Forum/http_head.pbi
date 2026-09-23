; Bounded HTTP request-head admission, not a socket server or body decoder.
; RFC 9112 sections 2, 3, 5, 6: https://www.rfc-editor.org/rfc/rfc9112.html
; Original implementation. No globals; caller owns input/output memory.
; Returns 0 incomplete, 1 admitted, or an HTTP rejection status. Caller closes
; on rejection and enforces a receive deadline. Never dispatch an incomplete head.
; Origin-form HTTP/1.1 only. Transfer coding is explicitly not implemented yet.
; Output: five native integers: head bytes, body bytes, target offset/length,
; method length (method starts at zero). Receive the body before dispatch.

Procedure.i FhEqual(data.i, count.i, text.i, folded.i)
  Protected n.i
  Protected a.i
  Protected b.i
  For n = 0 To count - 1
    a = PeekA(data + n)
    b = PeekA(text + n)
    If b = 0 : ProcedureReturn 0 : EndIf
    If folded <> 0 And a >= 65 And a <= 90 : a = a + 32 : EndIf
    If a <> b : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn Bool(PeekA(text + count) = 0)
EndProcedure

Procedure.i FhToken(c.i)
  If c >= 48 And c <= 57 : ProcedureReturn 1 : EndIf
  If c >= 65 And c <= 90 : ProcedureReturn 1 : EndIf
  If c >= 97 And c <= 122 : ProcedureReturn 1 : EndIf
  If c = 33 Or c = 35 Or c = 36 Or c = 37 Or c = 38 Or c = 39 Or c = 42 Or c = 43 Or c = 45 Or c = 46 Or c = 94 Or c = 95 Or c = 96 Or c = 124 Or c = 126
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i ForumHttpHead(data.i, available.i, maxHead.i, maxBody.i, output.i)
  Protected pos.i
  Protected begin.i
  Protected finish.i
  Protected c.i
  Protected n.i
  Protected colon.i
  Protected value.i
  Protected last.i
  Protected firstSpace.i
  Protected secondSpace.i
  Protected hosts.i
  Protected lengths.i
  Protected transfer.i
  Protected body.i
  Protected digit.i
  Protected target.i
  Protected targetSize.i
  If output = 0 : ProcedureReturn 500 : EndIf
  For n = 0 To 4 : PokeI(output + n * SizeOf(.i), 0) : Next
  If data = 0 Or available < 0 Or maxHead < 16 Or maxBody < 0
    ProcedureReturn 500
  EndIf
  If available > $7FFFFFFF Or maxHead > $7FFFFFFF Or maxBody > $7FFFFFFF
    ProcedureReturn 500
  EndIf
  While pos < available
    If pos >= maxHead : ProcedureReturn 431 : EndIf
    c = PeekA(data + pos)
    If c = 10 : ProcedureReturn 400 : EndIf
    If c = 13
      If pos + 1 >= maxHead : ProcedureReturn 431 : EndIf
      If pos + 1 >= available : ProcedureReturn 0 : EndIf
      If PeekA(data + pos + 1) <> 10 : ProcedureReturn 400 : EndIf
      finish = pos
      pos = pos + 2
      If begin = 0
        firstSpace = -1 : secondSpace = -1
        For n = begin To finish - 1
          c = PeekA(data + n)
          If c = 32
            If firstSpace = -1
              firstSpace = n
            ElseIf secondSpace = -1
              secondSpace = n
            Else
              ProcedureReturn 400
            EndIf
          ElseIf c < 33 Or c > 126
            ProcedureReturn 400
          EndIf
        Next
        If firstSpace <= 0 Or secondSpace <= firstSpace + 1 : ProcedureReturn 400 : EndIf
        For n = 0 To firstSpace - 1
          If FhToken(PeekA(data + n)) = 0 : ProcedureReturn 400 : EndIf
        Next
        If FhEqual(data + secondSpace + 1, finish - secondSpace - 1, "HTTP/1.1", 0) = 0
          ProcedureReturn 505
        EndIf
        target = firstSpace + 1 : targetSize = secondSpace - target
        If PeekA(data + target) <> 47 : ProcedureReturn 400 : EndIf
        For n = target To secondSpace - 1
          If PeekA(data + n) = 35 : ProcedureReturn 400 : EndIf
        Next
      ElseIf finish = begin
        If hosts <> 1 : ProcedureReturn 400 : EndIf
        If transfer <> 0 And lengths <> 0 : ProcedureReturn 400 : EndIf
        If transfer : ProcedureReturn 501 : EndIf
        PokeI(output, pos)
        PokeI(output + SizeOf(.i), body)
        PokeI(output + 2 * SizeOf(.i), target)
        PokeI(output + 3 * SizeOf(.i), targetSize)
        PokeI(output + 4 * SizeOf(.i), firstSpace)
        ProcedureReturn 1
      Else
        colon = -1
        For n = begin To finish - 1
          c = PeekA(data + n)
          If c = 58 : colon = n : Break : EndIf
          If FhToken(c) = 0 : ProcedureReturn 400 : EndIf
        Next
        If colon <= begin : ProcedureReturn 400 : EndIf
        value = colon + 1 : last = finish
        While value < last
          c = PeekA(data + value)
          If c <> 32 And c <> 9 : Break : EndIf
          value = value + 1
        Wend
        While last > value
          c = PeekA(data + last - 1)
          If c <> 32 And c <> 9 : Break : EndIf
          last = last - 1
        Wend
        For n = value To last - 1
          c = PeekA(data + n)
          If (c < 32 And c <> 9) Or c = 127 : ProcedureReturn 400 : EndIf
        Next
        If FhEqual(data + begin, colon - begin, "host", 1)
          hosts = hosts + 1
          If hosts <> 1 Or value = last : ProcedureReturn 400 : EndIf
          ; Exact configured-host validation is a mandatory later routing step.
          For n = value To last - 1
            c = PeekA(data + n)
            If c <= 32 Or c >= 127 Or c = 44 Or c = 47 Or c = 64 Or c = 92 Or c = 35
              ProcedureReturn 400
            EndIf
          Next
        ElseIf FhEqual(data + begin, colon - begin, "content-length", 1)
          lengths = lengths + 1
          If lengths <> 1 Or value = last : ProcedureReturn 400 : EndIf
          For n = value To last - 1
            digit = PeekA(data + n) - 48
            If digit < 0 Or digit > 9 : ProcedureReturn 400 : EndIf
            If body > maxBody / 10 : ProcedureReturn 413 : EndIf
            body = body * 10 + digit
            If body > maxBody : ProcedureReturn 413 : EndIf
          Next
        ElseIf FhEqual(data + begin, colon - begin, "transfer-encoding", 1)
          transfer = 1
        EndIf
      EndIf
      begin = pos
    Else
      If c = 0 : ProcedureReturn 400 : EndIf
      pos = pos + 1
    EndIf
  Wend
  If pos >= maxHead : ProcedureReturn 431 : EndIf
  ProcedureReturn 0
EndProcedure
