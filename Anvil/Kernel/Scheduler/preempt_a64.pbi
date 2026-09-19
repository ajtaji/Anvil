; Asynchronous A64 scheduler backend: privileged EL3h, one core.
; No boot wiring. Timer callbacks and vector lease are explicit composition.
; Full interrupt frame: x0-x30, SP, ELR/SPSR, FPCR/FPSR, q0-q31.
; Architectural facts: Arm102412_0103_02 sections5/6.
; https://documentation-service.arm.com/static/67ac57fb091bfc3e0a9479cc
#AP_BYTES = 800
#AP_STACK = 16384
Global Dim ap_frames.a[32 * 800 + 15]
Global Dim ap_stacks.a[32 * (16384 + 32) + 15]
Global Dim ap_kernel.a[800 + 15]
Global Dim ap_irqstack.a[16384 + 32 + 15]
Global Dim ap_entry.i[32]
Global Dim ap_argument.i[32]
Global Dim ap_result.i[32]
Global Dim ap_owner.i[32]
Global ap_frame.i
Global ap_kernelptr.i
Global ap_irqtop.i
Global ap_irqbase.i
Global ap_active.i
Global ap_executing.i
Global ap_inirq.i
Global ap_ticks.i
Global ap_installed.i
Global ap_boundcore.i
Global ap_oldvbar.i
Global ap_oldthread.i
Global ap_ack.i
Global ap_arm.i
Global ap_stop.i
Global ap_code.i
Global ap_codesize.i
Global ap_el.i
Global ap_core.i
Global ap_daif.i
Global ap_cptr.i
Global ap_vbar.i
Global ap_thread.i
Global ap_spsel.i
Global ap_vector.i
Global ap_fatal_busy.i
Global ap_restore_pending.i
Global ap_recovery_vbar.i
Global ap_fatal_reporter.i
Global Dim ap_fatal_record.i[8]
Global Dim ap_fatal_stack.a[16384 + 15]
Procedure.i ApFrame(slot.i)
  ProcedureReturn ((@ap_frames[0] + 15) & -16) + slot * #AP_BYTES
EndProcedure
Procedure.i ApStack(slot.i)
  ProcedureReturn ((@ap_stacks[0] + 15) & -16) + slot * (#AP_STACK + 32)
EndProcedure
ProcedureNaked ApEnvironment()
  ASM
    mrs x9, CurrentEL
    adrp x10, global_ap_el
    add x10, x10, #:lo12:global_ap_el
    str x9, [x10]
    cmp x9, #12
    b.ne ap_env_wrong
    mrs x9, mpidr_el1
    adrp x10, global_ap_core
    add x10, x10, #:lo12:global_ap_core
    str x9, [x10]
    mrs x9, daif
    adrp x10, global_ap_daif
    add x10, x10, #:lo12:global_ap_daif
    str x9, [x10]
    mrs x9, cptr_el3
    adrp x10, global_ap_cptr
    add x10, x10, #:lo12:global_ap_cptr
    str x9, [x10]
    mrs x9, vbar_el3
    adrp x10, global_ap_vbar
    add x10, x10, #:lo12:global_ap_vbar
    str x9, [x10]
    mrs x9, tpidr_el3
    adrp x10, global_ap_thread
    add x10, x10, #:lo12:global_ap_thread
    str x9, [x10]
    mrs x9, spsel
    adrp x10, global_ap_spsel
    add x10, x10, #:lo12:global_ap_spsel
    str x9, [x10]
    adrp x9, ap_vectors
    add x9, x9, #:lo12:ap_vectors
    adrp x10, global_ap_vector
    add x10, x10, #:lo12:global_ap_vector
    str x9, [x10]
ap_env_wrong:
    ret
  ENDASM
EndProcedure
ProcedureNaked ApMask()
  ASM
    msr daifset, #15
    ret
  ENDASM
EndProcedure
ProcedureNaked ApInstallVector()
  ASM
    adrp x9, global_ap_vector
    add x9, x9, #:lo12:global_ap_vector
    ldr x9, [x9]
    msr vbar_el3, x9
    isb
    ret
  ENDASM
EndProcedure
ProcedureNaked ApRestoreVector()
  ASM
    adrp x9, global_ap_oldvbar
    add x9, x9, #:lo12:global_ap_oldvbar
    ldr x9, [x9]
    msr vbar_el3, x9
    adrp x9, global_ap_oldthread
    add x9, x9, #:lo12:global_ap_oldthread
    ldr x9, [x9]
    msr tpidr_el3, x9
    isb
    ret
  ENDASM
EndProcedure
ProcedureNaked ApFatal()
  ASM
    msr daifset, #15
    adrp x9, global_ap_fatal_busy
    add x9, x9, #:lo12:global_ap_fatal_busy
    ldr x10, [x9]
    cbnz x10, ap_fatal_park
    movz x10, #1
    str x10, [x9]
    adrp x9, global_ap_fatal_record
    add x9, x9, #:lo12:global_ap_fatal_record
    mrs x10, CurrentEL
    str x10, [x9]
    mrs x10, esr_el3
    str x10, [x9, #8]
    mrs x10, elr_el3
    str x10, [x9, #16]
    mrs x10, far_el3
    str x10, [x9, #24]
    mov x10, sp
    str x10, [x9, #32]
    adrp x10, global_ap_active
    add x10, x10, #:lo12:global_ap_active
    ldr x10, [x10]
    str x10, [x9, #40]
    adrp x10, global_ap_inirq
    add x10, x10, #:lo12:global_ap_inirq
    ldr x10, [x10]
    str x10, [x9, #48]
    ; Zero means raw register observation, not a validated fault/task frame.
    str xzr, [x9, #56]
    adrp x9, global_ap_fatal_stack
    add x9, x9, #:lo12:global_ap_fatal_stack
    movz x10, #16384
    add x9, x9, x10
    lsr x9, x9, #4
    lsl x9, x9, #4
    mov sp, x9
    adrp x9, global_ap_fatal_reporter
    add x9, x9, #:lo12:global_ap_fatal_reporter
    ldr x9, [x9]
    cbz x9, ap_fatal_park
    blr x9
ap_fatal_park:
    wfe
    b ap_fatal_park
  ENDASM
EndProcedure
Procedure.i ApSetFatalReporter(callback.i)
  If ap_installed = 0 Or ap_active <> 0 Or ap_fatal_busy <> 0
    ProcedureReturn 0
  EndIf
  ApEnvironment()
  If ap_el <> 12 Or ap_core <> ap_boundcore Or ap_daif <> 960 Or ap_vbar <> ap_vector
    ProcedureReturn 0
  EndIf
  If callback < ap_code Or callback >= ap_code + ap_codesize Or (callback & 3) <> 0
    ProcedureReturn 0
  EndIf
  ap_fatal_reporter = callback
  ProcedureReturn 1
EndProcedure
ProcedureNaked ApVectors()
  ASM
    .align 2048
ap_vectors:
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b ap_irq_entry
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
    b apfatal
    .align 128
ap_irq_entry:
    msr daifset, #15
    msr tpidr_el3, x9
    adrp x9, global_ap_frame
    add x9, x9, #:lo12:global_ap_frame
    ldr x9, [x9]
    str x10, [x9, #80]
    adrp x10, global_ap_executing
    add x10, x10, #:lo12:global_ap_executing
    ldr x10, [x10]
    cbz x10, apfatal
    adrp x10, global_ap_active
    add x10, x10, #:lo12:global_ap_active
    ldr x10, [x10]
    cbz x10, apfatal
    adrp x10, global_ap_inirq
    add x10, x10, #:lo12:global_ap_inirq
    ldr x10, [x10]
    cbnz x10, apfatal
    adrp x10, global_ap_inirq
    add x10, x10, #:lo12:global_ap_inirq
    movz x9, #1
    str x9, [x10]
    adrp x9, global_ap_frame
    add x9, x9, #:lo12:global_ap_frame
    ldr x9, [x9]
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
    mrs x10, elr_el3
    str x10, [x9, #256]
    mrs x10, spsr_el3
    str x10, [x9, #264]
    mrs x10, fpcr
    str x10, [x9, #272]
    mrs x10, fpsr
    str x10, [x9, #280]
    str q0, [x9, #288]
    str q1, [x9, #304]
    str q2, [x9, #320]
    str q3, [x9, #336]
    str q4, [x9, #352]
    str q5, [x9, #368]
    str q6, [x9, #384]
    str q7, [x9, #400]
    str q8, [x9, #416]
    str q9, [x9, #432]
    str q10, [x9, #448]
    str q11, [x9, #464]
    str q12, [x9, #480]
    str q13, [x9, #496]
    str q14, [x9, #512]
    str q15, [x9, #528]
    str q16, [x9, #544]
    str q17, [x9, #560]
    str q18, [x9, #576]
    str q19, [x9, #592]
    str q20, [x9, #608]
    str q21, [x9, #624]
    str q22, [x9, #640]
    str q23, [x9, #656]
    str q24, [x9, #672]
    str q25, [x9, #688]
    str q26, [x9, #704]
    str q27, [x9, #720]
    str q28, [x9, #736]
    str q29, [x9, #752]
    str q30, [x9, #768]
    str q31, [x9, #784]
    adrp x9, global_ap_irqtop
    add x9, x9, #:lo12:global_ap_irqtop
    ldr x9, [x9]
    mov sp, x9
    bl apontick
    b aprestore
  ENDASM
EndProcedure
ProcedureNaked ApLaunch()
  ASM
    msr tpidr_el3, x9
    adrp x9, global_ap_kernelptr
    add x9, x9, #:lo12:global_ap_kernelptr
    ldr x9, [x9]
    str x0, [x9, #0]
    str x1, [x9, #8]
    str x2, [x9, #16]
    str x3, [x9, #24]
    str x4, [x9, #32]
    str x5, [x9, #40]
    str x6, [x9, #48]
    str x7, [x9, #56]
    str x8, [x9, #64]
    str x10, [x9, #80]
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
    str x30, [x9, #256]
    mrs x10, nzcv
    mrs x11, daif
    orr x10, x10, x11
    movz x11, #13
    orr x10, x10, x11
    str x10, [x9, #264]
    mrs x10, fpcr
    str x10, [x9, #272]
    mrs x10, fpsr
    str x10, [x9, #280]
    str q0, [x9, #288]
    str q1, [x9, #304]
    str q2, [x9, #320]
    str q3, [x9, #336]
    str q4, [x9, #352]
    str q5, [x9, #368]
    str q6, [x9, #384]
    str q7, [x9, #400]
    str q8, [x9, #416]
    str q9, [x9, #432]
    str q10, [x9, #448]
    str q11, [x9, #464]
    str q12, [x9, #480]
    str q13, [x9, #496]
    str q14, [x9, #512]
    str q15, [x9, #528]
    str q16, [x9, #544]
    str q17, [x9, #560]
    str q18, [x9, #576]
    str q19, [x9, #592]
    str q20, [x9, #608]
    str q21, [x9, #624]
    str q22, [x9, #640]
    str q23, [x9, #656]
    str q24, [x9, #672]
    str q25, [x9, #688]
    str q26, [x9, #704]
    str q27, [x9, #720]
    str q28, [x9, #736]
    str q29, [x9, #752]
    str q30, [x9, #768]
    str q31, [x9, #784]
    adrp x9, global_ap_executing
    add x9, x9, #:lo12:global_ap_executing
    movz x10, #1
    str x10, [x9]
    b aprestore
  ENDASM
EndProcedure
ProcedureNaked ApRestore()
  ASM
    adrp x9, global_ap_frame
    add x9, x9, #:lo12:global_ap_frame
    ldr x9, [x9]
    ldr x10, [x9, #256]
    msr elr_el3, x10
    ldr x10, [x9, #264]
    msr spsr_el3, x10
    ldr x10, [x9, #272]
    msr fpcr, x10
    ldr x10, [x9, #280]
    msr fpsr, x10
    ldr q0, [x9, #288]
    ldr q1, [x9, #304]
    ldr q2, [x9, #320]
    ldr q3, [x9, #336]
    ldr q4, [x9, #352]
    ldr q5, [x9, #368]
    ldr q6, [x9, #384]
    ldr q7, [x9, #400]
    ldr q8, [x9, #416]
    ldr q9, [x9, #432]
    ldr q10, [x9, #448]
    ldr q11, [x9, #464]
    ldr q12, [x9, #480]
    ldr q13, [x9, #496]
    ldr q14, [x9, #512]
    ldr q15, [x9, #528]
    ldr q16, [x9, #544]
    ldr q17, [x9, #560]
    ldr q18, [x9, #576]
    ldr q19, [x9, #592]
    ldr q20, [x9, #608]
    ldr q21, [x9, #624]
    ldr q22, [x9, #640]
    ldr q23, [x9, #656]
    ldr q24, [x9, #672]
    ldr q25, [x9, #688]
    ldr q26, [x9, #704]
    ldr q27, [x9, #720]
    ldr q28, [x9, #736]
    ldr q29, [x9, #752]
    ldr q30, [x9, #768]
    ldr q31, [x9, #784]
    ldr x10, [x9, #248]
    mov sp, x10
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
  ENDASM
EndProcedure
ProcedureNaked ApBootstrap()
  ASM
    bl apenter
    b apfatal
  ENDASM
EndProcedure
Procedure.i ApAddress(address.i)
  If ap_code <= 0 Or address < ap_code Or (address & 3) <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(address - ap_code <= ap_codesize - 4)
EndProcedure
Procedure.i ApGuard(slot.i)
  Protected stack.i
  Protected savedsp.i
  stack = ApStack(slot)
  savedsp = PeekI(ApFrame(slot) + 248)
  If savedsp < stack + 16 Or savedsp > stack + #AP_STACK + 16 Or (savedsp & 15) <> 0 : ProcedureReturn 0 : EndIf
  If (PeekI(ApFrame(slot) + 264) & 31) <> 13 : ProcedureReturn 0 : EndIf
  If ApAddress(PeekI(ApFrame(slot) + 256)) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(PeekI(stack) = $4150475541524421 And PeekI(stack + #AP_STACK + 16) = $4150475541524421)
EndProcedure
Procedure.i ApInstall(expectedVbar.i, ack.i, arm.i, stop.i, code.i, codesize.i)
  If ap_installed <> 0 Or code <= 0 Or codesize < 4 Or (code & 3) <> 0 Or (codesize & 3) <> 0 : ProcedureReturn 0 : EndIf
  If code > $7FFFFFFFFFFFFFFF - codesize : ProcedureReturn 0 : EndIf
  ApEnvironment()
  If ap_el <> 12 Or ap_spsel <> 1 Or ap_daif <> 960 Or (ap_cptr & 1024) <> 0 : ProcedureReturn 0 : EndIf
  If ap_vbar <> expectedVbar Or ap_thread <> 0 : ProcedureReturn 0 : EndIf
  ap_code = code : ap_codesize = codesize
  If ApAddress(ack) = 0 Or ApAddress(arm) = 0 Or ApAddress(stop) = 0 : ap_code = 0 : ProcedureReturn 0 : EndIf
  ap_ack = ack : ap_arm = arm : ap_stop = stop
  ap_boundcore = ap_core
  ap_oldvbar = ap_vbar : ap_oldthread = ap_thread
  ap_kernelptr = (@ap_kernel[0] + 15) & -16
  ap_frame = ap_kernelptr
  ap_irqbase = (@ap_irqstack[0] + 15) & -16
  ap_irqtop = ap_irqbase + 16384 + 16
  PokeI(ap_irqbase, $4150475541524421)
  PokeI(ap_irqtop, $4150475541524421)
  ApInstallVector()
  ApEnvironment()
  If ap_vbar <> ap_vector
    ; Installation failed after a write: retain ownership until rollback is
    ; observed, even if the failure left neither the old nor requested VBAR.
    ap_installed = 1
    ap_restore_pending = 1
    ApRestoreVector()
    ApEnvironment()
    ap_recovery_vbar = ap_vbar
    If ap_vbar = ap_oldvbar And ap_thread = ap_oldthread
      ap_installed = 0
      ap_restore_pending = 0
    EndIf
    ProcedureReturn 0
  EndIf
  ap_installed = 1
  ProcedureReturn 1
EndProcedure
Procedure.i ApCreate(entry.i, argument.i)
  Protected handle.i
  Protected slot.i
  Protected p.i
  Protected n.i
  If ap_installed = 0 Or ap_active <> 0 Or ap_restore_pending <> 0 Or ApAddress(entry) = 0 : ProcedureReturn 0 : EndIf
  ApEnvironment()
  If ap_core <> ap_boundcore Or ap_el <> 12 Or ap_spsel <> 1 Or ap_daif <> 960 : ProcedureReturn 0 : EndIf
  handle = SchedCreate()
  If handle = 0 : ProcedureReturn 0 : EndIf
  slot = SchedSlot(handle)
  ap_owner[slot] = handle : ap_entry[slot] = entry : ap_argument[slot] = argument
  p = ApFrame(slot)
  For n = 0 To #AP_BYTES - 1 Step 8 : PokeI(p + n, 0) : Next
  PokeI(p + 248, ApStack(slot) + #AP_STACK + 16)
  PokeI(p + 256, @ApBootstrap)
  ; EL3h; D/A/F masked, I enabled only by the final ERET.
  PokeI(p + 264, 845)
  PokeI(ApStack(slot), $4150475541524421)
  PokeI(ApStack(slot) + #AP_STACK + 16, $4150475541524421)
  ap_result[slot] = 0
  ProcedureReturn handle
EndProcedure
Procedure ApOnTick()
  Protected *ack
  Protected acknowledged.i
  Protected handle.i
  Protected slot.i
  ack = ap_ack
  acknowledged = ack()
  If acknowledged <> 1 And acknowledged <> 2
    ApFatal()
    ProcedureReturn
  EndIf
  If PeekI(ap_irqbase) <> $4150475541524421 Or PeekI(ap_irqtop) <> $4150475541524421
    ApFatal()
    ProcedureReturn
  EndIf
  slot = SchedSlot(ap_active)
  If slot < 0 Or ApGuard(slot) = 0
    ApFatal()
    ProcedureReturn
  EndIf
  ; A controller spurious acknowledgment has no scheduling quantum.
  If acknowledged = 2
    ap_inirq = 0
    ProcedureReturn
  EndIf
  ap_ticks = ap_ticks + 1
  If SchedYield(ap_active) = 0
    ApFatal()
    ProcedureReturn
  EndIf
  handle = SchedNext()
  slot = SchedSlot(handle)
  If slot < 0 Or ap_owner[slot] <> handle Or ApGuard(slot) = 0
    ApFatal()
    ProcedureReturn
  EndIf
  ap_active = handle
  ap_frame = ApFrame(slot)
  ap_inirq = 0
EndProcedure
Procedure.i ApOwnedSlot(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0 : ProcedureReturn -1 : EndIf
  If ap_owner[slot] <> handle : ProcedureReturn -1 : EndIf
  ProcedureReturn slot
EndProcedure
Procedure ApFinish()
  Protected *timer
  Protected handle.i
  Protected slot.i
  ApMask()
  If SchedFinish(ap_active) = 0
    ApFatal()
    ProcedureReturn
  EndIf
  handle = SchedNext()
  If handle = 0
    timer = ap_stop
    If timer() <> 1
      ApFatal()
      ProcedureReturn
    EndIf
    ap_active = 0
    ap_executing = 0
    ap_frame = ap_kernelptr
  Else
    slot = ApOwnedSlot(handle)
    If slot < 0
      ApFatal()
      ProcedureReturn
    EndIf
    If ApGuard(slot) = 0
      ApFatal()
      ProcedureReturn
    EndIf
    ap_active = handle
    ap_frame = ApFrame(slot)
    timer = ap_arm
    If timer() <> 1
      ApFatal()
      ProcedureReturn
    EndIf
  EndIf
  ApRestore()
EndProcedure
Procedure ApEnter()
  Protected slot.i
  Protected *entry
  Protected result.i
  slot = ApOwnedSlot(ap_active)
  If slot < 0
    ApFatal()
    ProcedureReturn
  EndIf
  entry = ap_entry[slot]
  result = entry()
  ap_result[slot] = result
  ApFinish()
EndProcedure
Procedure.i ApArgument()
  Protected slot.i
  slot = SchedSlot(ap_active)
  If slot < 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn ap_argument[slot]
EndProcedure
Procedure.i ApResult(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0 Or ap_owner[slot] <> handle : ProcedureReturn 0 : EndIf
  ProcedureReturn ap_result[slot]
EndProcedure
Procedure.i ApRun()
  Protected *timer
  Protected handle.i
  Protected slot.i
  If ap_installed = 0 Or ap_active <> 0 Or ap_restore_pending <> 0 : ProcedureReturn 0 : EndIf
  ApEnvironment()
  If ap_el <> 12 Or ap_core <> ap_boundcore Or ap_spsel <> 1 Or ap_daif <> 960 Or ap_vbar <> ap_vector Or (ap_cptr & 1024) <> 0 : ProcedureReturn 0 : EndIf
  handle = SchedNext()
  If handle = 0 : ProcedureReturn 0 : EndIf
  slot = ApOwnedSlot(handle)
  If slot < 0 : ProcedureReturn 0 : EndIf
  If ApGuard(slot) = 0
    ap_result[slot] = -1
    SchedFinish(handle)
    ProcedureReturn 0
  EndIf
  ap_active = handle
  ap_frame = ApFrame(slot)
  timer = ap_arm
  If timer() <> 1
    timer = ap_stop
    If timer() <> 1
      ApFatal()
      ProcedureReturn 0
    EndIf
    SchedYield(handle)
    ap_active = 0
    ap_frame = ap_kernelptr
    ProcedureReturn 0
  EndIf
  ApLaunch()
  ProcedureReturn 1
EndProcedure
Procedure.i ApReap(handle.i)
  Protected slot.i
  Protected p.i
  Protected n.i
  If ap_active <> 0 : ProcedureReturn 0 : EndIf
  ApEnvironment()
  If ap_el <> 12 Or ap_core <> ap_boundcore Or ap_daif <> 960 : ProcedureReturn 0 : EndIf
  slot = SchedSlot(handle)
  If slot < 0 Or ap_owner[slot] <> handle : ProcedureReturn 0 : EndIf
  If SchedReap(handle) = 0 : ProcedureReturn 0 : EndIf
  p = ApFrame(slot)
  For n = 0 To #AP_BYTES - 1 Step 8 : PokeI(p + n, 0) : Next
  p = ApStack(slot)
  For n = 0 To #AP_STACK + 31 Step 8 : PokeI(p + n, 0) : Next
  ap_owner[slot] = 0 : ap_entry[slot] = 0 : ap_argument[slot] = 0 : ap_result[slot] = 0
  ProcedureReturn 1
EndProcedure
Procedure.i ApCanUninstall()
  Protected n.i
  If ap_installed = 0 Or ap_active <> 0 : ProcedureReturn 0 : EndIf
  ApEnvironment()
  If ap_el <> 12 Or ap_core <> ap_boundcore Or ap_daif <> 960 Or ap_vbar <> ap_vector : ProcedureReturn 0 : EndIf
  For n = 0 To 31
    If ap_owner[n] <> 0 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure
Procedure.i ApUninstall()
  If ap_restore_pending = 0
    If ApCanUninstall() = 0 : ProcedureReturn 0 : EndIf
    ap_restore_pending = 1
  Else
    ApEnvironment()
    If ap_el <> 12 Or ap_core <> ap_boundcore Or ap_daif <> 960
      ProcedureReturn 0
    EndIf
    If ap_vbar <> ap_vector And ap_vbar <> ap_oldvbar And ap_vbar <> ap_recovery_vbar
      ProcedureReturn 0
    EndIf
  EndIf
  ApRestoreVector()
  ApEnvironment()
  ap_recovery_vbar = ap_vbar
  If ap_vbar <> ap_oldvbar Or ap_thread <> ap_oldthread : ProcedureReturn 0 : EndIf
  ap_installed = 0
  ap_restore_pending = 0
  ap_fatal_reporter = 0
  ProcedureReturn 1
EndProcedure
