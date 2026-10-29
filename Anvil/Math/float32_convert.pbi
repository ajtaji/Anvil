; SPDX-License-Identifier: MIT
; Portable binary32 -> signed32 truncation, matching Int()'s symmetric
; +/-2147483647 saturation and
; NaN-zero policy. The full-width software conversion remains the oracle.
; No instruction template or board dependency is used.
Procedure.l MathFToI32(value.f)
  Protected bits.i,exponent.i,mantissa.i,result.i
  bits=PeekN(@value)
  exponent=(bits>>23) & 255 : mantissa=bits & $7FFFFF
  If exponent=255 And mantissa<>0 : ProcedureReturn 0 : EndIf
  If exponent<127 : ProcedureReturn 0 : EndIf
  If exponent>=158
    If (bits & $80000000)<>0 : ProcedureReturn -2147483647 : EndIf
    ProcedureReturn 2147483647
  EndIf
  mantissa=mantissa | $800000 : exponent=exponent-127
  If exponent>=23 : result=mantissa<<(exponent-23) : Else : result=mantissa>>(23-exponent) : EndIf
  If (bits & $80000000)<>0 : result=-result : EndIf
  ProcedureReturn result
EndProcedure
