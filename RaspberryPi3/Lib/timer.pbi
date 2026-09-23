; BCM2837 ARM physical system timer, NOT the BCM2711 peripheral window.
; Broadcom BCM2835 peripherals ch12, translated through BCM2837 ranges.
; Primary serialized boot owner. Negative result is an explicit failure.
#PI3_ST = $3F003000
Procedure.i Pi3Micros()
  Protected first.i
  Protected second.i
  Protected low.i
  Protected attempt.i
  For attempt = 0 To 7
    first = PeekL(#PI3_ST + 8) & $FFFFFFFF
    low = PeekL(#PI3_ST + 4) & $FFFFFFFF
    second = PeekL(#PI3_ST + 8) & $FFFFFFFF
    If first = second
      ProcedureReturn (first << 32) | low
    EndIf
  Next
  ProcedureReturn -1
EndProcedure
Procedure.i Pi3DelayUs(duration.i)
  Protected start.i
  Protected now.i
  Protected attempt.i
  If duration < 0 Or duration > 1000000
    ProcedureReturn 0
  EndIf
  start = Pi3Micros()
  If start < 0
    ProcedureReturn 0
  EndIf
  For attempt = 0 To 9999999
    now = Pi3Micros()
    If now < start
      ProcedureReturn 0
    EndIf
    If now - start >= duration
      ProcedureReturn 1
    EndIf
  Next
  ; A frozen or inaccessible timer must not wedge early boot forever.
  ProcedureReturn 0
EndProcedure
