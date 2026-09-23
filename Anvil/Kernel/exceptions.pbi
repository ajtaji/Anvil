; Primary-core exception capture and current-EL SPx IRQ return, EL2/EL3.
; Post-implementation architectural verification (not imported handler code):
; Arm 102412_0103_02 pp31-35: vector slots and ERET SPSR/ELR restoration.
; Arm Cortex-A72 TRM 100095_0003_06 4.3.35/4.3.40: CPTR TFP bit10.
; Arm DDI0595 ID092421 pp310-317,1973-1976,2019-2022: TFP coverage,
; TPIDR register access and VBAR alignment. Exact official document URLs and
; scope are recorded in docs/EL3_STARTUP_REVIEW.md. No silicon proof claimed.
; TPIDR_EL2/EL3 is reserved as vector-entry scratch while installed.
; No interrupt is enabled/unmasked here. No SMC or lower-EL payload ABI.
; Only slot 5 (current EL SPx IRQ) may return, and only when callback returns 1.
; All other exceptions and unhandled IRQs report once and park.
; Nested exceptions park before overwriting the first saved frame.
; Callbacks have no arguments. IRQ callback must acknowledge the controller.
; Reporter runs after complete capture on an 16 KiB emergency stack.
; Single primary-core storage: install refuses secondary cores.
; The guard is raised immediately after saving bootstrap x10, before slot/GPR
; capture. The mapped writable frame and guard themselves are prerequisites:
; a fault accessing that bootstrap memory cannot promise a complete record.
; IRQ callbacks must not change EL, translation, stack ownership or DAIF masks.
; Return restoration assumes the saved frame remains mapped and unmodified.
; ExceptionSp is the handler-entry SP; only slot 5 supports resumable context.
Global Dim exception_frame.i[114]
Global Dim exception_stack.i[2050]
Global exception_active.i
Global exception_error.i
Global exception_vbar.i
Global exception_level.i
Global exception_reporter.i
Global exception_irq_handler.i

Procedure ExceptionSetReporter(callback.i)
  exception_reporter = callback
EndProcedure
Procedure ExceptionSetIrqHandler(callback.i)
  exception_irq_handler = callback
EndProcedure
Procedure.i ExceptionEl()
  ProcedureReturn exception_level
EndProcedure
Procedure.i ExceptionVbar()
  ProcedureReturn exception_vbar
EndProcedure
Procedure.i ExceptionError()
  ProcedureReturn exception_error
EndProcedure
Procedure.i ExceptionPc()
  ProcedureReturn ExceptionElr()
EndProcedure
Procedure.i ExceptionFrame()
  ProcedureReturn ((@exception_frame[0] + 15) >> 4) << 4
EndProcedure
Procedure.i ExceptionSlot()
  ProcedureReturn PeekI(ExceptionFrame() + 256)
EndProcedure
Procedure.i ExceptionEsr()
  ProcedureReturn PeekI(ExceptionFrame() + 264)
EndProcedure
Procedure.i ExceptionFar()
  ProcedureReturn PeekI(ExceptionFrame() + 272)
EndProcedure
Procedure.i ExceptionElr()
  ProcedureReturn PeekI(ExceptionFrame() + 280)
EndProcedure
Procedure.i ExceptionSpsr()
  ProcedureReturn PeekI(ExceptionFrame() + 288)
EndProcedure
Procedure.i ExceptionSp()
  ProcedureReturn PeekI(ExceptionFrame() + 248)
EndProcedure

ProcedureNaked ExceptionVectors2()
  ASM
    .align 2048
exception_vectors_2:
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #0
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #1
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #2
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #3
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #4
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #5
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #6
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #7
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #8
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #9
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #10
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #11
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #12
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #13
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #14
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
    msr tpidr_el2, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #15
    str x10, [x9, #256]
    b exception_capture_2
    .align 128
exception_capture_2:
    msr daifset, #15
    str x0, [x9, #0]
    str x1, [x9, #8]
    str x2, [x9, #16]
    str x3, [x9, #24]
    str x4, [x9, #32]
    str x5, [x9, #40]
    str x6, [x9, #48]
    str x7, [x9, #56]
    str x8, [x9, #64]
    str x11, [x9, #88]
    str x12, [x9, #96]
    str x13, [x9, #104]
    str x14, [x9, #112]
    str x15, [x9, #120]
    str x16, [x9, #128]
    str x17, [x9, #136]
    str x18, [x9, #144]
    str x19, [x9, #152]
    str x20, [x9, #160]
    str x21, [x9, #168]
    str x22, [x9, #176]
    str x23, [x9, #184]
    str x24, [x9, #192]
    str x25, [x9, #200]
    str x26, [x9, #208]
    str x27, [x9, #216]
    str x28, [x9, #224]
    str x29, [x9, #232]
    str x30, [x9, #240]
    mrs x10, tpidr_el2
    str x10, [x9, #72]
    mov x10, sp
    str x10, [x9, #248]
    mrs x10, esr_el2
    str x10, [x9, #264]
    mrs x10, far_el2
    str x10, [x9, #272]
    mrs x10, elr_el2
    str x10, [x9, #280]
    mrs x10, spsr_el2
    str x10, [x9, #288]
    mrs x10, fpcr
    str x10, [x9, #296]
    mrs x10, fpsr
    str x10, [x9, #304]
    str q0, [x9, #320]
    str q1, [x9, #336]
    str q2, [x9, #352]
    str q3, [x9, #368]
    str q4, [x9, #384]
    str q5, [x9, #400]
    str q6, [x9, #416]
    str q7, [x9, #432]
    str q8, [x9, #448]
    str q9, [x9, #464]
    str q10, [x9, #480]
    str q11, [x9, #496]
    str q12, [x9, #512]
    str q13, [x9, #528]
    str q14, [x9, #544]
    str q15, [x9, #560]
    str q16, [x9, #576]
    str q17, [x9, #592]
    str q18, [x9, #608]
    str q19, [x9, #624]
    str q20, [x9, #640]
    str q21, [x9, #656]
    str q22, [x9, #672]
    str q23, [x9, #688]
    str q24, [x9, #704]
    str q25, [x9, #720]
    str q26, [x9, #736]
    str q27, [x9, #752]
    str q28, [x9, #768]
    str q29, [x9, #784]
    str q30, [x9, #800]
    str q31, [x9, #816]
    adrp x10, global_exception_stack
    add x10, x10, #:lo12:global_exception_stack
    movz x11, #16384
    add x10, x10, x11
    lsr x10, x10, #4
    lsl x10, x10, #4
    mov sp, x10
    ldr x10, [x9, #256]
    cmp x10, #5
    b.ne exception_fatal_2
    adrp x10, global_exception_irq_handler
    add x10, x10, #:lo12:global_exception_irq_handler
    ldr x10, [x10]
    cbz x10, exception_fatal_2
    blr x10
    cmp x0, #1
    b.ne exception_fatal_2
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    ldr q0, [x9, #320]
    ldr q1, [x9, #336]
    ldr q2, [x9, #352]
    ldr q3, [x9, #368]
    ldr q4, [x9, #384]
    ldr q5, [x9, #400]
    ldr q6, [x9, #416]
    ldr q7, [x9, #432]
    ldr q8, [x9, #448]
    ldr q9, [x9, #464]
    ldr q10, [x9, #480]
    ldr q11, [x9, #496]
    ldr q12, [x9, #512]
    ldr q13, [x9, #528]
    ldr q14, [x9, #544]
    ldr q15, [x9, #560]
    ldr q16, [x9, #576]
    ldr q17, [x9, #592]
    ldr q18, [x9, #608]
    ldr q19, [x9, #624]
    ldr q20, [x9, #640]
    ldr q21, [x9, #656]
    ldr q22, [x9, #672]
    ldr q23, [x9, #688]
    ldr q24, [x9, #704]
    ldr q25, [x9, #720]
    ldr q26, [x9, #736]
    ldr q27, [x9, #752]
    ldr q28, [x9, #768]
    ldr q29, [x9, #784]
    ldr q30, [x9, #800]
    ldr q31, [x9, #816]
    ldr x10, [x9, #296]
    msr fpcr, x10
    ldr x10, [x9, #304]
    msr fpsr, x10
    ldr x10, [x9, #280]
    msr elr_el2, x10
    ldr x10, [x9, #288]
    msr spsr_el2, x10
    ldr x10, [x9, #248]
    mov sp, x10
    adrp x10, global_exception_active
    add x10, x10, #:lo12:global_exception_active
    movz x11, #0
    str x11, [x10]
    ldr x0, [x9, #0]
    ldr x1, [x9, #8]
    ldr x2, [x9, #16]
    ldr x3, [x9, #24]
    ldr x4, [x9, #32]
    ldr x5, [x9, #40]
    ldr x6, [x9, #48]
    ldr x7, [x9, #56]
    ldr x8, [x9, #64]
    ldr x10, [x9, #80]
    ldr x11, [x9, #88]
    ldr x12, [x9, #96]
    ldr x13, [x9, #104]
    ldr x14, [x9, #112]
    ldr x15, [x9, #120]
    ldr x16, [x9, #128]
    ldr x17, [x9, #136]
    ldr x18, [x9, #144]
    ldr x19, [x9, #152]
    ldr x20, [x9, #160]
    ldr x21, [x9, #168]
    ldr x22, [x9, #176]
    ldr x23, [x9, #184]
    ldr x24, [x9, #192]
    ldr x25, [x9, #200]
    ldr x26, [x9, #208]
    ldr x27, [x9, #216]
    ldr x28, [x9, #224]
    ldr x29, [x9, #232]
    ldr x30, [x9, #240]
    ldr x9, [x9, #72]
    eret
exception_fatal_2:
    adrp x10, global_exception_reporter
    add x10, x10, #:lo12:global_exception_reporter
    ldr x10, [x10]
    cbz x10, exception_park_2
    blr x10
exception_park_2:
    wfe
    b exception_park_2
  EndASM
EndProcedure

ProcedureNaked ExceptionVectors3()
  ASM
    .align 2048
exception_vectors_3:
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #0
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #1
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #2
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #3
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #4
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #5
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #6
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #7
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #8
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #9
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #10
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #11
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #12
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #13
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #14
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
    msr tpidr_el3, x9
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    ldr x9, [x9]
    cbnz x9, exception_park_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    str x10, [x9, #80]
    adrp x9, global_exception_active
    add x9, x9, #:lo12:global_exception_active
    movz x10, #1
    str x10, [x9]
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    movz x10, #15
    str x10, [x9, #256]
    b exception_capture_3
    .align 128
exception_capture_3:
    msr daifset, #15
    str x0, [x9, #0]
    str x1, [x9, #8]
    str x2, [x9, #16]
    str x3, [x9, #24]
    str x4, [x9, #32]
    str x5, [x9, #40]
    str x6, [x9, #48]
    str x7, [x9, #56]
    str x8, [x9, #64]
    str x11, [x9, #88]
    str x12, [x9, #96]
    str x13, [x9, #104]
    str x14, [x9, #112]
    str x15, [x9, #120]
    str x16, [x9, #128]
    str x17, [x9, #136]
    str x18, [x9, #144]
    str x19, [x9, #152]
    str x20, [x9, #160]
    str x21, [x9, #168]
    str x22, [x9, #176]
    str x23, [x9, #184]
    str x24, [x9, #192]
    str x25, [x9, #200]
    str x26, [x9, #208]
    str x27, [x9, #216]
    str x28, [x9, #224]
    str x29, [x9, #232]
    str x30, [x9, #240]
    mrs x10, tpidr_el3
    str x10, [x9, #72]
    mov x10, sp
    str x10, [x9, #248]
    mrs x10, esr_el3
    str x10, [x9, #264]
    mrs x10, far_el3
    str x10, [x9, #272]
    mrs x10, elr_el3
    str x10, [x9, #280]
    mrs x10, spsr_el3
    str x10, [x9, #288]
    mrs x10, fpcr
    str x10, [x9, #296]
    mrs x10, fpsr
    str x10, [x9, #304]
    str q0, [x9, #320]
    str q1, [x9, #336]
    str q2, [x9, #352]
    str q3, [x9, #368]
    str q4, [x9, #384]
    str q5, [x9, #400]
    str q6, [x9, #416]
    str q7, [x9, #432]
    str q8, [x9, #448]
    str q9, [x9, #464]
    str q10, [x9, #480]
    str q11, [x9, #496]
    str q12, [x9, #512]
    str q13, [x9, #528]
    str q14, [x9, #544]
    str q15, [x9, #560]
    str q16, [x9, #576]
    str q17, [x9, #592]
    str q18, [x9, #608]
    str q19, [x9, #624]
    str q20, [x9, #640]
    str q21, [x9, #656]
    str q22, [x9, #672]
    str q23, [x9, #688]
    str q24, [x9, #704]
    str q25, [x9, #720]
    str q26, [x9, #736]
    str q27, [x9, #752]
    str q28, [x9, #768]
    str q29, [x9, #784]
    str q30, [x9, #800]
    str q31, [x9, #816]
    adrp x10, global_exception_stack
    add x10, x10, #:lo12:global_exception_stack
    movz x11, #16384
    add x10, x10, x11
    lsr x10, x10, #4
    lsl x10, x10, #4
    mov sp, x10
    ldr x10, [x9, #256]
    cmp x10, #5
    b.ne exception_fatal_3
    adrp x10, global_exception_irq_handler
    add x10, x10, #:lo12:global_exception_irq_handler
    ldr x10, [x10]
    cbz x10, exception_fatal_3
    blr x10
    cmp x0, #1
    b.ne exception_fatal_3
    adrp x9, global_exception_frame
    add x9, x9, #:lo12:global_exception_frame
    add x9, x9, #15
    lsr x9, x9, #4
    lsl x9, x9, #4
    ldr q0, [x9, #320]
    ldr q1, [x9, #336]
    ldr q2, [x9, #352]
    ldr q3, [x9, #368]
    ldr q4, [x9, #384]
    ldr q5, [x9, #400]
    ldr q6, [x9, #416]
    ldr q7, [x9, #432]
    ldr q8, [x9, #448]
    ldr q9, [x9, #464]
    ldr q10, [x9, #480]
    ldr q11, [x9, #496]
    ldr q12, [x9, #512]
    ldr q13, [x9, #528]
    ldr q14, [x9, #544]
    ldr q15, [x9, #560]
    ldr q16, [x9, #576]
    ldr q17, [x9, #592]
    ldr q18, [x9, #608]
    ldr q19, [x9, #624]
    ldr q20, [x9, #640]
    ldr q21, [x9, #656]
    ldr q22, [x9, #672]
    ldr q23, [x9, #688]
    ldr q24, [x9, #704]
    ldr q25, [x9, #720]
    ldr q26, [x9, #736]
    ldr q27, [x9, #752]
    ldr q28, [x9, #768]
    ldr q29, [x9, #784]
    ldr q30, [x9, #800]
    ldr q31, [x9, #816]
    ldr x10, [x9, #296]
    msr fpcr, x10
    ldr x10, [x9, #304]
    msr fpsr, x10
    ldr x10, [x9, #280]
    msr elr_el3, x10
    ldr x10, [x9, #288]
    msr spsr_el3, x10
    ldr x10, [x9, #248]
    mov sp, x10
    adrp x10, global_exception_active
    add x10, x10, #:lo12:global_exception_active
    movz x11, #0
    str x11, [x10]
    ldr x0, [x9, #0]
    ldr x1, [x9, #8]
    ldr x2, [x9, #16]
    ldr x3, [x9, #24]
    ldr x4, [x9, #32]
    ldr x5, [x9, #40]
    ldr x6, [x9, #48]
    ldr x7, [x9, #56]
    ldr x8, [x9, #64]
    ldr x10, [x9, #80]
    ldr x11, [x9, #88]
    ldr x12, [x9, #96]
    ldr x13, [x9, #104]
    ldr x14, [x9, #112]
    ldr x15, [x9, #120]
    ldr x16, [x9, #128]
    ldr x17, [x9, #136]
    ldr x18, [x9, #144]
    ldr x19, [x9, #152]
    ldr x20, [x9, #160]
    ldr x21, [x9, #168]
    ldr x22, [x9, #176]
    ldr x23, [x9, #184]
    ldr x24, [x9, #192]
    ldr x25, [x9, #200]
    ldr x26, [x9, #208]
    ldr x27, [x9, #216]
    ldr x28, [x9, #224]
    ldr x29, [x9, #232]
    ldr x30, [x9, #240]
    ldr x9, [x9, #72]
    eret
exception_fatal_3:
    adrp x10, global_exception_reporter
    add x10, x10, #:lo12:global_exception_reporter
    ldr x10, [x10]
    cbz x10, exception_park_3
    blr x10
exception_park_3:
    wfe
    b exception_park_3
  EndASM
EndProcedure

Procedure.i ExceptionInstall()
  ASM
    mrs x0, mpidr_el1
    movz x1, #255
    and x0, x0, x1
    cbnz x0, exception_install_refuse
    mrs x0, currentel
    cmp x0, #8
    b.eq exception_install_el2
    cmp x0, #12
    b.ne exception_install_refuse
    mrs x3, cptr_el3
    movz x2, #1024
    orr x3, x3, x2
    eor x3, x3, x2
    msr cptr_el3, x3
    isb
    adr x1, exception_vectors_3
    movz x0, #3
    b exception_install_done
exception_install_el2:
    mrs x3, cptr_el2
    movz x2, #1024
    orr x3, x3, x2
    eor x3, x3, x2
    msr cptr_el2, x3
    isb
    adr x1, exception_vectors_2
    movz x0, #2
exception_install_done:
    isb
    adrp x2, global_exception_error
    add x2, x2, #:lo12:global_exception_error
    movz x3, #0
    str x3, [x2]
    adrp x2, global_exception_vbar
    add x2, x2, #:lo12:global_exception_vbar
    str x1, [x2]
    adrp x1, global_exception_level
    add x1, x1, #:lo12:global_exception_level
    str x0, [x1]
    adrp x1, global_exception_vbar
    add x1, x1, #:lo12:global_exception_vbar
    ldr x1, [x1]
    dsb sy
    cmp x0, #3
    b.ne exception_install_publish2
    msr vbar_el3, x1
    b exception_install_published
exception_install_publish2:
    msr vbar_el2, x1
exception_install_published:
    isb
    b exception_install_return
exception_install_refuse:
    adrp x1, global_exception_error
    add x1, x1, #:lo12:global_exception_error
    movz x0, #1
    str x0, [x1]
    movz x0, #0
exception_install_return:
  EndASM
  ProcedureReturn
EndProcedure
