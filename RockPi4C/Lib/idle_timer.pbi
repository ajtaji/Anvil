; EL3 timer event-stream idle for the polled recovery loop. The timer event
; wakes WFE without unmasking interrupts or installing an IRQ/FIQ handler.
; A return-only silicon proof established this CNTKCTL_EL1 path on RK3399.
#ROCK_IDLE_KCTL_EVENT_MASK = $FC
#ROCK_IDLE_KCTL_EVENT_VALUE = $C4

Global rock_idle_timer_ready.i
Global rock_idle_timer_error.i
Global rock_idle_skip_after_watchdog.i
Global rock_idle_kctl_original.i
Global rock_idle_kctl_write.i

ProcedureNaked.i RockIdleTimerDaif()
  ASM
    mrs x0, daif
    ret
  ENDASM
EndProcedure

ProcedureNaked.i RockIdleTimerKctl()
  ASM
    mrs x0, cntkctl_el1
    ret
  ENDASM
EndProcedure

ProcedureNaked RockIdleTimerWriteKctl()
  ASM
    adrp x9, global_rock_idle_kctl_write
    add x9, x9, #:lo12:global_rock_idle_kctl_write
    ldr x0, [x9]
    msr cntkctl_el1, x0
    isb
    ret
  ENDASM
EndProcedure

ProcedureNaked.i RockIdleTimerWait()
  ASM
    ; Clear any latched local event first, then wait for the next timer event.
    ; A verified SEVL encoding is used because PMF does not parse its mnemonic.
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

Procedure.i RockIdleTimerInit()
  rock_idle_timer_ready = 0
  rock_idle_timer_error = 0
  If rock_current_el <> 12 Or rock_timer_frequency <> 24000000
    rock_idle_timer_error = 1
    ProcedureReturn 0
  EndIf
  ; A failed WFE wake must be recoverable by the physical deadman.
  If rock_watchdog_armed = 0
    rock_idle_timer_error = 2
    ProcedureReturn 0
  EndIf
  If rock_idle_skip_after_watchdog <> 0
    rock_idle_timer_error = 5
    ProcedureReturn 0
  EndIf
  If (RockIdleTimerDaif() & $C0) <> $C0
    rock_idle_timer_error = 3
    ProcedureReturn 0
  EndIf
  rock_idle_kctl_original = RockIdleTimerKctl()
  rock_idle_kctl_write = (rock_idle_kctl_original & $FFFFFFFFFFFFFF03) | #ROCK_IDLE_KCTL_EVENT_VALUE
  RockIdleTimerWriteKctl()
  If (RockIdleTimerKctl() & #ROCK_IDLE_KCTL_EVENT_MASK) <> #ROCK_IDLE_KCTL_EVENT_VALUE
    rock_idle_kctl_write = rock_idle_kctl_original
    RockIdleTimerWriteKctl()
    rock_idle_timer_error = 4
    ProcedureReturn 0
  EndIf
  rock_idle_timer_ready = 1
  ProcedureReturn 1
EndProcedure
