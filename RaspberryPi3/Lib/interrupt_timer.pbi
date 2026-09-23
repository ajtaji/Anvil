; BCM2837 core-0 non-secure physical timer. No GIC and no global IRQ enable.
; Original implementation from BCM2836 QA7 rev3.4 sections4.6/4.10 (applies
; to BCM2837) and Arm DDI0595 CNTP_CTL_EL0/CNTP_TVAL_EL0 descriptions.
; https://datasheets.raspberrypi.com/bcm2836/bcm2836-peripherals.pdf
; https://documentation-service.arm.com/static/6166bf63e4f35d248467c9c0
; Sole primary-core EL2 owner, DAIF.I masked for every mutating operation.
; Period is positive signed32 counter ticks, not guessed microseconds.
#PI3_IT_ROUTE = $40000040
#PI3_IT_SOURCE = $40000060
Global pi3_it_ready.i
Global pi3_it_armed.i
Global pi3_it_period.i
Global pi3_it_frequency.i
Global pi3_it_error.i

ProcedureNaked.i Pi3ItContext()
  ASM
  mrs x0, CurrentEL
  cmp x0, #8
  b.ne _pi3_it_bad_context
  mrs x0, mpidr_el1
  lsr x1, x0, #32
  movz x9, #255
  and x1, x1, x9
  movz x9, #65535
  movk x9, #255, lsl #16
  and x0, x0, x9
  orr x0, x0, x1
  cbnz x0, _pi3_it_bad_context
  mrs x0, daif
  movz x9, #128
  and x0, x0, x9
  cmp x0, #128
  b.ne _pi3_it_bad_context
  movz x0, #1
  ret
_pi3_it_bad_context:
  movz x0, #0
  ret
  ENDASM
EndProcedure
ProcedureNaked.i Pi3ItReadFrequency()
  ASM
  mrs x0, cntfrq_el0
  ret
  ENDASM
EndProcedure
ProcedureNaked.i Pi3ItReadControl()
  ASM
  mrs x0, cntp_ctl_el0
  ret
  ENDASM
EndProcedure
ProcedureNaked Pi3ItDisable()
  ASM
  msr cntp_ctl_el0, xzr
  isb
  ret
  ENDASM
EndProcedure
ProcedureNaked Pi3ItProgram()
  ASM
  adrp x9, global_pi3_it_period
  add x9, x9, #:lo12:global_pi3_it_period
  ldr x9, [x9]
  msr cntp_tval_el0, x9
  isb
  ret
  ENDASM
EndProcedure
ProcedureNaked Pi3ItEnable()
  ASM
  dsb sy
  movz x9, #1
  msr cntp_ctl_el0, x9
  isb
  ret
  ENDASM
EndProcedure
Procedure.i Pi3IrqTimerInit(periodTicks.i)
  If Pi3ItContext() = 0 : pi3_it_error = 1 : ProcedureReturn 0 : EndIf
  If periodTicks < 1 Or periodTicks > $7FFFFFFF : pi3_it_error = 2 : ProcedureReturn 0 : EndIf
  If pi3_it_ready <> 0 : pi3_it_error = 3 : ProcedureReturn 0 : EndIf
  If (PeekL(#PI3_IT_ROUTE) & $22) <> 0 Or (Pi3ItReadControl() & 1) <> 0
    pi3_it_error = 3 : ProcedureReturn 0
  EndIf
  pi3_it_frequency = Pi3ItReadFrequency()
  If pi3_it_frequency <= 0 : pi3_it_error = 4 : ProcedureReturn 0 : EndIf
  pi3_it_period = periodTicks
  pi3_it_ready = 1
  pi3_it_armed = 0
  pi3_it_error = 0
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3IrqTimerArm()
  Protected route.i
  If Pi3ItContext() = 0 : pi3_it_error = 1 : ProcedureReturn 0 : EndIf
  If pi3_it_ready = 0 : pi3_it_error = 5 : ProcedureReturn 0 : EndIf
  route = PeekL(#PI3_IT_ROUTE) & $FFFFFFFF
  If (route & $22) <> pi3_it_armed * 2 : pi3_it_error = 6 : ProcedureReturn 0 : EndIf
  Pi3ItDisable()
  Pi3ItProgram()
  PokeL(#PI3_IT_ROUTE, route | 2)
  pi3_it_armed = 1
  Pi3ItEnable()
  pi3_it_error = 0
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3IrqTimerPending()
  If Pi3ItContext() = 0 Or pi3_it_armed = 0 : ProcedureReturn 0 : EndIf
  ; A mixed/unknown IRQ remains for the exception owner to diagnose. Never
  ; acknowledge an unrelated interrupt as though it were this timer.
  If (PeekL(#PI3_IT_SOURCE) & $FFFFFFFF) <> 2 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool((Pi3ItReadControl() & 7) = 5)
EndProcedure
Procedure.i Pi3IrqTimerHandle()
  If Pi3IrqTimerPending() = 0 : ProcedureReturn 0 : EndIf
  ; Writing a future TVAL clears the timer condition. There is no local
  ; controller EOI register to write. Missed ticks coalesce; no catch-up loop.
  Pi3ItProgram()
  Pi3ItEnable()
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3IrqTimerStop()
  Protected route.i
  If Pi3ItContext() = 0 : pi3_it_error = 1 : ProcedureReturn 0 : EndIf
  If pi3_it_ready = 0 : pi3_it_error = 5 : ProcedureReturn 0 : EndIf
  route = PeekL(#PI3_IT_ROUTE) & $FFFFFFFF
  If (route & $22) <> pi3_it_armed * 2 : pi3_it_error = 6 : ProcedureReturn 0 : EndIf
  Pi3ItDisable()
  PokeL(#PI3_IT_ROUTE, route & $FFFFFFFD)
  ASM
  dsb sy
  ENDASM
  pi3_it_ready = 0
  pi3_it_armed = 0
  pi3_it_frequency = 0
  pi3_it_error = 0
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3IrqTimerFrequency() : ProcedureReturn pi3_it_frequency : EndProcedure
Procedure.i Pi3IrqTimerError() : ProcedureReturn pi3_it_error : EndProcedure
