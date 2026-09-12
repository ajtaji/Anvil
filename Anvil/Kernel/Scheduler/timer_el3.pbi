; Pi 4 EL3 secure physical timer, exclusive primary-core ownership.
; Arm Generic Timer guide: EL3 timer is CNTPS_*_EL1, not CNTP_*_EL0.
; https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Generic%20Timer.pdf
; Pi bcm2711.dtsi + arm,arch_timer.yaml: secure timer PPI13 => INTID29.
; https://github.com/raspberrypi/linux/blob/rpi-6.6.y/arch/arm/boot/dts/broadcom/bcm2711.dtsi
; Supervisor independently cross-checked the same timer PPI in both:
; https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/boot/dts/broadcom/bcm2711.dtsi
; https://github.com/torvalds/linux/blob/v6.12/arch/arm/boot/dts/broadcom/bcm2711.dtsi
; Requires interrupts.pi4; no boot call, no vector writes, no DAIF unmask.
Global at_ready.i
Global at_period.i
Global at_control.i
Global at_compare.i
Global at_seen.i
Global at_write.i
ProcedureNaked.i AtEnvironment()
  ASM
    mrs x0, CurrentEL
    cmp x0, #12
    b.ne at_bad_env
    mrs x0, mpidr_el1
    movz x9, #65535
    movk x9, #255, lsl #16
    and x10, x0, x9
    lsr x0, x0, #32
    movz x9, #255
    and x0, x0, x9
    orr x0, x0, x10
    cbnz x0, at_bad_env
    mrs x0, daif
    cmp x0, #960
    b.ne at_bad_env
    mrs x0, scr_el3
    cmp x0, #1457
    b.ne at_bad_env
    movz x0, #1
    ret
at_bad_env:
    movz x0, #0
    ret
  ENDASM
EndProcedure
Procedure.i AtController()
  If InterruptContext() = 0 : ProcedureReturn 0 : EndIf
  If PeekL(#IG_D) <> 3 Or PeekL(#IG_C) <> $1E7 Or PeekL(#IG_C + 4) <> $F0
    ProcedureReturn 0
  EndIf
  If (PeekL(#IG_D + $80) & (1 << 29)) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
ProcedureNaked.i AtControl()
  ASM
    mrs x0, cntps_ctl_el1
    ret
  ENDASM
EndProcedure
ProcedureNaked.i AtCompare()
  ASM
    mrs x0, cntps_cval_el1
    ret
  ENDASM
EndProcedure
ProcedureNaked AtDisableTimer()
  ASM
    msr cntps_ctl_el1, xzr
    isb
    ret
  ENDASM
EndProcedure
ProcedureNaked AtSetCompare()
  ASM
    adrp x9, global_at_write
    add x9, x9, #:lo12:global_at_write
    ldr x9, [x9]
    msr cntps_cval_el1, x9
    isb
    ret
  ENDASM
EndProcedure
ProcedureNaked AtSetControl()
  ASM
    adrp x9, global_at_write
    add x9, x9, #:lo12:global_at_write
    ldr x9, [x9]
    msr cntps_ctl_el1, x9
    isb
    ret
  ENDASM
EndProcedure
ProcedureNaked AtProgram()
  ASM
    mrs x9, cntpct_el0
    adrp x10, global_at_period
    add x10, x10, #:lo12:global_at_period
    ldr x10, [x10]
    add x9, x9, x10
    msr cntps_cval_el1, x9
    movz x9, #1
    msr cntps_ctl_el1, x9
    isb
    ret
  ENDASM
EndProcedure
Procedure.i AtArm()
  If AtEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If at_ready = 0 Or AtController() = 0 : ProcedureReturn 0 : EndIf
  If InterruptEnable(29) = 0 : ProcedureReturn 0 : EndIf
  AtProgram()
  ProcedureReturn (AtControl() & 3) = 1
EndProcedure
Procedure.i AtTick()
  If AtEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If at_ready = 0 Or AtController() = 0 : ProcedureReturn 0 : EndIf
  If (AtControl() & 5) <> 5 : ProcedureReturn 0 : EndIf
  AtProgram()
  If (AtControl() & 3) <> 1 : ProcedureReturn 0 : EndIf
  at_seen = 1
  ProcedureReturn 1
EndProcedure
Procedure.i AtAcknowledge()
  If AtEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If at_ready = 0 Or AtController() = 0 : ProcedureReturn 0 : EndIf
  at_seen = 0
  If InterruptDispatch() <> 1 : ProcedureReturn 0 : EndIf
  If at_seen = 0 : ProcedureReturn 2 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i AtStop()
  If AtEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If at_ready = 0 Or AtController() = 0 : ProcedureReturn 0 : EndIf
  AtDisableTimer()
  If (AtControl() & 3) <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn InterruptDisable(29)
EndProcedure
Procedure.i AtPrepare(period.i)
  If AtEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If at_ready <> 0 Or period <= 0 Or period > $7FFFFFFF
    ProcedureReturn 0
  EndIf
  If AtController() = 0 : ProcedureReturn 0 : EndIf
  If (AtControl() & 1) <> 0 : ProcedureReturn 0 : EndIf
  at_control = AtControl() & 3
  at_compare = AtCompare()
  If InterruptClaim(29, @AtTick) = 0 : ProcedureReturn 0 : EndIf
  at_period = period
  at_ready = 1
  ProcedureReturn 1
EndProcedure
Procedure.i AtRelease()
  If AtStop() = 0 : ProcedureReturn 0 : EndIf
  at_write = at_compare : AtSetCompare()
  at_write = at_control : AtSetControl()
  If AtCompare() <> at_compare Or (AtControl() & 3) <> at_control
    ProcedureReturn 0
  EndIf
  If InterruptRelease(29, @AtTick) = 0 : ProcedureReturn 0 : EndIf
  at_ready = 0
  ProcedureReturn 1
EndProcedure
