; Arm architectural timer access shared by every RK3399 core.
; No board MMIO clock is guessed. Every wait has both a timer deadline and an
; instruction ceiling so a trapped or frozen counter cannot wedge cold boot.
Global rock_timer_frequency.i
Global rock_timer_error.i

ProcedureNaked.i RockTimerFrequencyRaw()
  ASM
    mrs x0, cntfrq_el0
    ret
  ENDASM
EndProcedure

ProcedureNaked.i RockTimerTicks()
  ASM
    isb
    mrs x0, cntpct_el0
    ret
  ENDASM
EndProcedure

Procedure.i RockTimerInit()
  Protected first.i
  Protected second.i
  rock_timer_frequency = RockTimerFrequencyRaw()
  If rock_timer_frequency < 1000000 Or rock_timer_frequency > 100000000
    rock_timer_error = 1
    ProcedureReturn 0
  EndIf
  first = RockTimerTicks()
  second = RockTimerTicks()
  If second < first
    rock_timer_error = 2
    ProcedureReturn 0
  EndIf
  rock_timer_error = 0
  ProcedureReturn 1
EndProcedure

Procedure.i RockTimerWaitUs(usec.i)
  Protected start.i
  Protected now.i
  Protected ticks.i
  Protected attempt.i
  If rock_timer_frequency = 0 Or usec < 0 Or usec > 1000000
    ProcedureReturn 0
  EndIf
  ticks = (rock_timer_frequency / 1000000) * usec
  If ticks < 0 : ProcedureReturn 0 : EndIf
  start = RockTimerTicks()
  For attempt = 0 To 9999999
    now = RockTimerTicks()
    If now < start : ProcedureReturn 0 : EndIf
    If now - start >= ticks : ProcedureReturn 1 : EndIf
  Next
  ProcedureReturn 0
EndProcedure
