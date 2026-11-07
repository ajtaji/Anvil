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
