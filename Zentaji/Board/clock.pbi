; Zentaji machine clock. Hardware TIME advances during CPU WFI as well as work.
; The frequency comes from the machine, not a compiler or host clock estimate.
XIncludeFile "Anvil/Kernel/Zentaji/zen_cpu.pbi"
#ZEN_IDLE_TIMERS = $FFFF000000050000
#ZEN_IDLE_INTC = $FFFF000000040000
#ZEN_IDLE_TIMER = $FFFF00000005F000 ; calling core's timer, line 1

Procedure.q Ticks()
  ProcedureReturn ZenCpuTime()
EndProcedure

Procedure.q TickHz()
  ProcedureReturn PeekQ(#ZEN_IDLE_TIMERS+$48)
EndProcedure

; Shared services use microseconds for bounded work, derived from hardware TIME.
; Split seconds/remainder before scaling so normal long uptimes do not overflow.
; A clock outside the signed service domain refuses with -1.
Procedure.q HwMicros()
 Protected ticks.q,hz.q,seconds.q,fraction.q,whole.q
 hz=TickHz() : ticks=Ticks()
 If hz<=0 Or hz>$7FFFFFFFFFFFFFFF/1000000 Or ticks<0 : ProcedureReturn -1 : EndIf
 seconds=ticks/hz
 If seconds>$7FFFFFFFFFFFFFFF/1000000 : ProcedureReturn -1 : EndIf
 whole=seconds*1000000 : fraction=((ticks%hz)*1000000)/hz
 If fraction>$7FFFFFFFFFFFFFFF-whole : ProcedureReturn -1 : EndIf
 ProcedureReturn whole+fraction
EndProcedure
