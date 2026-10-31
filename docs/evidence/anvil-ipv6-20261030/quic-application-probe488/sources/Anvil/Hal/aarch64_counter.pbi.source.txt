; AArch64 architectural physical counter access, independent of board clocks.
; The boot environment must permit CNTPCT_EL0/CNTFRQ_EL0 at the caller's EL.
; Frequency is the firmware-programmed counter rate, never the CPU rate.
; Raw reads preserve callers that need no instruction barrier. Ordered reads
; execute ISB before sampling; neither form implies a data-memory barrier.
; No globals, allocation, clock programming, interrupt or event configuration.
ProcedureNaked.i A64CounterRead()
  ASM
    mrs x0, cntpct_el0
    ret
  ENDASM
EndProcedure

ProcedureNaked.i A64CounterFrequency()
  ASM
    mrs x0, cntfrq_el0
    ret
  ENDASM
EndProcedure

ProcedureNaked.i A64CounterReadOrdered()
  ASM
    isb
    mrs x0, cntpct_el0
    ret
  ENDASM
EndProcedure

; Caller owns a proven event source and recovery watchdog. SEVL plus the first
; WFE drains the local event latch; the second WFE awaits the next event.
; These functions do not enable the event source or unmask interrupts.
ProcedureNaked.i A64CounterWaitEventSample()
  ASM
    .long $D50320BF ; SEVL
    wfe
    wfe
    isb
    mrs x0, cntpct_el0
    ret
  ENDASM
EndProcedure

ProcedureNaked.i A64CounterWaitEventTicks()
  ASM
    isb
    mrs x9, cntpct_el0
    .long $D50320BF ; SEVL
    wfe
    wfe
    isb
    mrs x0, cntpct_el0
    sub x0, x0, x9
    ret
  ENDASM
EndProcedure
