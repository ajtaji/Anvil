; Shared bounded space/tab token parsing for command front ends.
; Explicit line lengths and caller-owned buffers; no storage or console I/O.

Procedure.i TokenNextBounded(*line, lineLength.i, *position, *dst, capacity.i)
  Protected pos.i = PeekI(*position)
  Protected count.i
  While pos < lineLength And (PeekA(*line + pos) = 32 Or PeekA(*line + pos) = 9)
    pos = pos + 1
  Wend
  count = 0
  While pos < lineLength
    If PeekA(*line + pos) = 32 Or PeekA(*line + pos) = 9 : Break : EndIf
    If count >= capacity - 1 : ProcedureReturn -1 : EndIf
    PokeA(*dst + count, PeekA(*line + pos))
    count = count + 1
    pos = pos + 1
  Wend
  PokeA(*dst + count, 0)
  PokeI(*position, pos)
  ProcedureReturn count
EndProcedure

Procedure.i TokenHex32Bounded(*line, lineLength.i, *position, *outValue)
  Protected count.i
  Protected digit.i
  Protected accum.i
  Protected c.i
  Protected pos.i = PeekI(*position)
  While pos < lineLength And (PeekA(*line + pos) = 32 Or PeekA(*line + pos) = 9)
    pos = pos + 1
  Wend
  count = 0 : accum = 0
  While pos < lineLength
    c = PeekA(*line + pos) & 255
    If c = 32 Or c = 9 : Break : EndIf
    If c >= 48 And c <= 57
      digit = c - 48
    ElseIf c >= 65 And c <= 70
      digit = c - 55
    ElseIf c >= 97 And c <= 102
      digit = c - 87
    Else
      ProcedureReturn 0
    EndIf
    If count >= 8 : ProcedureReturn 0 : EndIf
    accum = ((accum << 4) | digit) & $FFFFFFFF
    count = count + 1
    pos = pos + 1
  Wend
  If count = 0 : ProcedureReturn 0 : EndIf
  PokeI(*outValue, accum)
  PokeI(*position, pos)
  ProcedureReturn 1
EndProcedure

Procedure.i TokenEquals(*token, text.i, length.i)
  Protected index.i
  For index = 0 To length - 1
    If PeekA(*token + index) <> PeekA(text + index) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn Bool(PeekA(*token + length) = 0)
EndProcedure

Procedure.i TokenOnlySpace(*line, lineLength.i, pos.i)
  While pos < lineLength
    If PeekA(*line + pos) <> 32 And PeekA(*line + pos) <> 9 : ProcedureReturn 0 : EndIf
    pos = pos + 1
  Wend
  ProcedureReturn 1
EndProcedure
