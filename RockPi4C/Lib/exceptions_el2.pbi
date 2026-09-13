; EL2 vector foundation. Every slot captures the architectural fault record
; and parks. IRQ return is deliberately absent until GIC dispatch ownership is
; proven on silicon; an unexpected interrupt cannot return into corrupt state.
Global rock_exception_active.i
Global rock_exception_slot.i
Global rock_exception_esr.i
Global rock_exception_far.i
Global rock_exception_elr.i
Global rock_exception_spsr.i
Global rock_exception_vbar.i

ProcedureNaked RockExceptionFatal()
  ASM
    msr daifset, #15
    adrp x9, global_rock_exception_active
    add x9, x9, #:lo12:global_rock_exception_active
    ldr x10, [x9]
    cbnz x10, rock_exception_park
    movz x10, #1
    str x10, [x9]
    adrp x9, global_rock_exception_esr
    add x9, x9, #:lo12:global_rock_exception_esr
    mrs x10, esr_el2
    str x10, [x9]
    adrp x9, global_rock_exception_far
    add x9, x9, #:lo12:global_rock_exception_far
    mrs x10, far_el2
    str x10, [x9]
    adrp x9, global_rock_exception_elr
    add x9, x9, #:lo12:global_rock_exception_elr
    mrs x10, elr_el2
    str x10, [x9]
    adrp x9, global_rock_exception_spsr
    add x9, x9, #:lo12:global_rock_exception_spsr
    mrs x10, spsr_el2
    str x10, [x9]
rock_exception_park:
    wfe
    b rock_exception_park
  ENDASM
EndProcedure

ProcedureNaked RockExceptionVectors()
  ASM
    .align 2048
rock_exception_vectors:
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
    .align 128
    b rockexceptionfatal
  ENDASM
EndProcedure

ProcedureNaked RockExceptionInstallRaw()
  ASM
    adrp x9, rock_exception_vectors
    add x9, x9, #:lo12:rock_exception_vectors
    msr vbar_el2, x9
    isb
    adrp x10, global_rock_exception_vbar
    add x10, x10, #:lo12:global_rock_exception_vbar
    str x9, [x10]
    ret
  ENDASM
EndProcedure

Procedure.i RockExceptionInstall()
  If rock_current_el <> 8 Or rock_exception_active <> 0
    ProcedureReturn 0
  EndIf
  RockExceptionInstallRaw()
  If rock_exception_vbar = 0 Or (rock_exception_vbar & 2047) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
