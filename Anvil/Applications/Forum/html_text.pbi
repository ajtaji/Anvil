; Plain UTF-8 text to HTML text/double-quoted attribute content. Not Markdown,
; URL validation, JavaScript/CSS encoding, or an authorization boundary.
; Caller owns valid RAM spans and serializes writes to them. No global scratch.
; Returns byte count (not NUL terminated), or -1 with destination unchanged.
; Input and output may not overlap. Maximum input 65536 bytes per call.
Procedure.i ForumHtmlText(source.i, length.i, destination.i, capacity.i)
  Protected offset.i
  Protected value.i
  Protected following.i
  Protected remaining.i
  Protected low.i
  Protected high.i
  Protected needed.i
  Protected pass.i
  Protected written.i
  Protected entity.i
  Protected count.i
  Protected index.i
  If source <= 0 Or destination <= 0 Or length < 0 Or length > 65536 Or capacity < 0
    ProcedureReturn -1
  EndIf
  If source > $7FFFFFFFFFFFFFFF - length Or destination > $7FFFFFFFFFFFFFFF - capacity
    ProcedureReturn -1
  EndIf
  If source < destination + capacity And destination < source + length
    ProcedureReturn -1
  EndIf
  ; Validate complete UTF-8 first: no overlong forms, surrogates, out-of-range
  ; scalars, NUL or non-whitespace ASCII controls. Never inspect past length.
  offset = 0
  While offset < length
    value = PeekA(source + offset)
    remaining = 0 : low = 128 : high = 191
    If value < 32
      If value <> 9 And value <> 10 And value <> 13 : ProcedureReturn -1 : EndIf
    ElseIf value = 127
      ProcedureReturn -1
    ElseIf value >= 128
      If value >= 194 And value <= 223
        remaining = 1
      ElseIf value >= 224 And value <= 239
        remaining = 2
        If value = 224 : low = 160 : EndIf
        If value = 237 : high = 159 : EndIf
      ElseIf value >= 240 And value <= 244
        remaining = 3
        If value = 240 : low = 144 : EndIf
        If value = 244 : high = 143 : EndIf
      Else
        ProcedureReturn -1
      EndIf
      If remaining >= length - offset : ProcedureReturn -1 : EndIf
      following = PeekA(source + offset + 1)
      If following < low Or following > high : ProcedureReturn -1 : EndIf
      For index = 2 To remaining
        following = PeekA(source + offset + index)
        If following < 128 Or following > 191 : ProcedureReturn -1 : EndIf
      Next
    EndIf
    offset = offset + remaining + 1
  Wend
  ; Preflight exact size, then emit. Capacity errors never publish partial HTML.
  needed = 0 : written = 0
  For pass = 0 To 1
    For offset = 0 To length - 1
      value = PeekA(source + offset)
      entity = 0 : count = 1
      Select value
        Case 38 : entity = "&amp;" : count = 5
        Case 60 : entity = "&lt;" : count = 4
        Case 62 : entity = "&gt;" : count = 4
        Case 34 : entity = "&quot;" : count = 6
        Case 39 : entity = "&#39;" : count = 5
      EndSelect
      If pass = 0
        If count > capacity - needed : ProcedureReturn -1 : EndIf
        needed = needed + count
      Else
        If entity = 0
          PokeA(destination + written, value)
        Else
          For index = 0 To count - 1
            PokeA(destination + written + index, PeekA(entity + index))
          Next
        EndIf
        written = written + count
      EndIf
    Next
  Next
  ProcedureReturn written
EndProcedure
