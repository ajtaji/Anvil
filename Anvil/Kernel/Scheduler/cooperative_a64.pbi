; Cooperative AArch64 contexts. Same core, EL and address space only.
; Include scheduler.pbi first. No IRQ calls, SMP or preemptive fairness.
; Public calls follow AAPCS64. ScSwap retains x18-x30, SP, all SIMD and
; FP environment; callers must still treat ABI caller-saved registers as dead.
; ABI reference: https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst
#SC_BYTES = 656
#SC_STACK = 16384
Global Dim sc_context.a[32 * 656 + 15]
Global Dim sc_stacks.a[32 * (16384 + 32) + 15]
Global Dim sc_kernel.a[656 + 15]
Global Dim sc_entry.i[32]
Global Dim sc_argument.i[32]
Global Dim sc_result.i[32]
Global Dim sc_owner.i[32]
Global sc_from.i
Global sc_to.i
Global sc_active.i
Global sc_level.i
Global sc_core.i
Global sc_observed_core.i
Global sc_environment.i
Global sc_fpready.i
Global sc_codebase.i
Global sc_codesize.i
Procedure.i ScContext(slot.i)
  ProcedureReturn ((@sc_context[0] + 15) & -16) + slot * #SC_BYTES
EndProcedure
Procedure.i ScStack(slot.i)
  ProcedureReturn ((@sc_stacks[0] + 15) & -16) + slot * (#SC_STACK + 32)
EndProcedure
Procedure.i ScKernel()
  ProcedureReturn (@sc_kernel[0] + 15) & -16
EndProcedure
ProcedureNaked ScReadEnvironment()
  ASM
    mrs x9, CurrentEL
    adrp x10, global_sc_environment
    add x10, x10, #:lo12:global_sc_environment
    str x9, [x10]
    movz x11, #0
    cmp x9, #12
    b.ne sc_fp_done
    mrs x10, cptr_el3
    movz x12, #1024
    and x10, x10, x12
    cbnz x10, sc_fp_done
    movz x11, #1
sc_fp_done:
    adrp x10, global_sc_fpready
    add x10, x10, #:lo12:global_sc_fpready
    str x11, [x10]
    mrs x9, mpidr_el1
    adrp x10, global_sc_observed_core
    add x10, x10, #:lo12:global_sc_observed_core
    str x9, [x10]
    ret
  ENDASM
EndProcedure
ProcedureNaked ScSeed()
  ASM
    adrp x9, global_sc_to
    add x9, x9, #:lo12:global_sc_to
    ldr x9, [x9]
    mrs x10, fpcr
    str x10, [x9, #112]
    mrs x10, fpsr
    str x10, [x9, #120]
    mrs x10, daif
    str x10, [x9, #640]
    ret
  ENDASM
EndProcedure
ProcedureNaked ScSwap()
  ASM
    adrp x9, global_sc_from
    add x9, x9, #:lo12:global_sc_from
    ldr x9, [x9]
    str x18, [x9, #0]
    str x19, [x9, #8]
    str x20, [x9, #16]
    str x21, [x9, #24]
    str x22, [x9, #32]
    str x23, [x9, #40]
    str x24, [x9, #48]
    str x25, [x9, #56]
    str x26, [x9, #64]
    str x27, [x9, #72]
    str x28, [x9, #80]
    str x29, [x9, #88]
    str x30, [x9, #96]
    mov x10, sp
    str x10, [x9, #104]
    mrs x10, fpcr
    str x10, [x9, #112]
    mrs x10, fpsr
    str x10, [x9, #120]
    mrs x10, daif
    str x10, [x9, #640]
    str q0, [x9, #128]
    str q1, [x9, #144]
    str q2, [x9, #160]
    str q3, [x9, #176]
    str q4, [x9, #192]
    str q5, [x9, #208]
    str q6, [x9, #224]
    str q7, [x9, #240]
    str q8, [x9, #256]
    str q9, [x9, #272]
    str q10, [x9, #288]
    str q11, [x9, #304]
    str q12, [x9, #320]
    str q13, [x9, #336]
    str q14, [x9, #352]
    str q15, [x9, #368]
    str q16, [x9, #384]
    str q17, [x9, #400]
    str q18, [x9, #416]
    str q19, [x9, #432]
    str q20, [x9, #448]
    str q21, [x9, #464]
    str q22, [x9, #480]
    str q23, [x9, #496]
    str q24, [x9, #512]
    str q25, [x9, #528]
    str q26, [x9, #544]
    str q27, [x9, #560]
    str q28, [x9, #576]
    str q29, [x9, #592]
    str q30, [x9, #608]
    str q31, [x9, #624]
    adrp x9, global_sc_to
    add x9, x9, #:lo12:global_sc_to
    ldr x9, [x9]
    ldr q0, [x9, #128]
    ldr q1, [x9, #144]
    ldr q2, [x9, #160]
    ldr q3, [x9, #176]
    ldr q4, [x9, #192]
    ldr q5, [x9, #208]
    ldr q6, [x9, #224]
    ldr q7, [x9, #240]
    ldr q8, [x9, #256]
    ldr q9, [x9, #272]
    ldr q10, [x9, #288]
    ldr q11, [x9, #304]
    ldr q12, [x9, #320]
    ldr q13, [x9, #336]
    ldr q14, [x9, #352]
    ldr q15, [x9, #368]
    ldr q16, [x9, #384]
    ldr q17, [x9, #400]
    ldr q18, [x9, #416]
    ldr q19, [x9, #432]
    ldr q20, [x9, #448]
    ldr q21, [x9, #464]
    ldr q22, [x9, #480]
    ldr q23, [x9, #496]
    ldr q24, [x9, #512]
    ldr q25, [x9, #528]
    ldr q26, [x9, #544]
    ldr q27, [x9, #560]
    ldr q28, [x9, #576]
    ldr q29, [x9, #592]
    ldr q30, [x9, #608]
    ldr q31, [x9, #624]
    ldr x10, [x9, #112]
    msr fpcr, x10
    ldr x10, [x9, #120]
    msr fpsr, x10
    ldr x10, [x9, #104]
    mov sp, x10
    ldr x18, [x9, #0]
    ldr x19, [x9, #8]
    ldr x20, [x9, #16]
    ldr x21, [x9, #24]
    ldr x22, [x9, #32]
    ldr x23, [x9, #40]
    ldr x24, [x9, #48]
    ldr x25, [x9, #56]
    ldr x26, [x9, #64]
    ldr x27, [x9, #72]
    ldr x28, [x9, #80]
    ldr x29, [x9, #88]
    ldr x30, [x9, #96]
    ldr x10, [x9, #640]
    msr daif, x10
    ret
  ENDASM
EndProcedure
ProcedureNaked ScBootstrap()
  ASM
    bl scenter
    brk #0
  ENDASM
EndProcedure
Procedure.i ScValidEnvironment()
  ScReadEnvironment()
  If sc_fpready = 0 : ProcedureReturn 0 : EndIf
  If sc_level = 0
    ; Initial backend requires EL3; lower-EL trap permissions need a trusted
    ; handoff contract. This is never callable from unprivileged EL0.
    If sc_environment <> 12 : ProcedureReturn 0 : EndIf
    sc_level = sc_environment
    sc_core = sc_observed_core
  ElseIf sc_environment <> sc_level Or sc_observed_core <> sc_core
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i ScGuard(slot.i)
  Protected p.i
  Protected savedsp.i
  p = ScStack(slot)
  savedsp = PeekI(ScContext(slot) + 104)
  If savedsp < p + 16 Or savedsp > p + #SC_STACK + 16 Or (savedsp & 15) <> 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(PeekI(p) = $5343484544475541 And PeekI(p + 8) = $52444C4F57455221 And PeekI(p + #SC_STACK + 16) = $5343484544475541 And PeekI(p + #SC_STACK + 24) = $5244555050455221)
EndProcedure
; Composition supplies its mapped executable interval. This checks arithmetic
; and membership, not page permissions or the semantic validity of an address.
Procedure.i ScConfigure(codebase.i, codesize.i)
  If sc_codebase <> 0 Or sc_active <> 0 : ProcedureReturn 0 : EndIf
  If codebase <= 0 Or codesize < 4 Or (codebase & 3) <> 0 Or (codesize & 3) <> 0 : ProcedureReturn 0 : EndIf
  If codebase > $7FFFFFFFFFFFFFFF - codesize : ProcedureReturn 0 : EndIf
  If ScValidEnvironment() = 0 : ProcedureReturn 0 : EndIf
  sc_codebase = codebase
  sc_codesize = codesize
  ProcedureReturn 1
EndProcedure
Procedure.i ScCreate(entry.i, argument.i)
  Protected handle.i
  Protected slot.i
  Protected p.i
  Protected n.i
  If sc_active <> 0 Or entry <= 0 Or (entry & 3) <> 0 : ProcedureReturn 0 : EndIf
  If sc_codebase = 0 Or entry < sc_codebase : ProcedureReturn 0 : EndIf
  If entry - sc_codebase > sc_codesize - 4 : ProcedureReturn 0 : EndIf
  If ScValidEnvironment() = 0 : ProcedureReturn 0 : EndIf
  handle = SchedCreate()
  If handle = 0 : ProcedureReturn 0 : EndIf
  slot = SchedSlot(handle)
  sc_owner[slot] = handle
  sc_entry[slot] = entry
  sc_argument[slot] = argument
  sc_result[slot] = 0
  p = ScContext(slot)
  For n = 0 To #SC_BYTES - 1 : PokeA(p + n, 0) : Next
  PokeI(p + 96, @ScBootstrap)
  PokeI(p + 104, ScStack(slot) + #SC_STACK + 16)
  p = ScStack(slot)
  PokeI(p, $5343484544475541)
  PokeI(p + 8, $52444C4F57455221)
  PokeI(p + #SC_STACK + 16, $5343484544475541)
  PokeI(p + #SC_STACK + 24, $5244555050455221)
  sc_to = ScContext(slot)
  ScSeed()
  ProcedureReturn handle
EndProcedure
Procedure.i ScArgument()
  Protected slot.i
  slot = SchedSlot(sc_active)
  If slot < 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn sc_argument[slot]
EndProcedure
Procedure ScBack()
  sc_from = ScContext(SchedSlot(sc_active))
  sc_to = ScKernel()
  ScSwap()
EndProcedure
Procedure ScEnter()
  Protected *entry
  Protected result.i
  Protected slot.i
  slot = SchedSlot(sc_active)
  entry = sc_entry[slot]
  result = entry()
  sc_result[slot] = result
  SchedFinish(sc_active)
  ScBack()
EndProcedure
Procedure.i ScYield()
  If sc_active = 0 Or ScValidEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If SchedYield(sc_active) = 0 : ProcedureReturn 0 : EndIf
  ScBack()
  ProcedureReturn 1
EndProcedure
Procedure.i ScWait(key.i, deadline.i)
  If sc_active = 0 Or ScValidEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If SchedWait(sc_active, key, deadline) = 0 : ProcedureReturn 0 : EndIf
  ScBack()
  ProcedureReturn 1
EndProcedure
Procedure.i ScRunOne()
  Protected handle.i
  Protected slot.i
  If sc_active <> 0 Or ScValidEnvironment() = 0 : ProcedureReturn 0 : EndIf
  handle = SchedNext()
  If handle = 0 : ProcedureReturn 0 : EndIf
  slot = SchedSlot(handle)
  If sc_owner[slot] <> handle Or ScGuard(slot) = 0
    sc_result[slot] = -1
    SchedFinish(handle)
    ProcedureReturn handle
  EndIf
  sc_active = handle
  sc_from = ScKernel()
  sc_to = ScContext(slot)
  ScSwap()
  sc_active = 0
  If ScGuard(slot) = 0
    sc_result[slot] = -1
    If SchedState(handle) = #SCHED_READY Or SchedState(handle) = #SCHED_WAITING : SchedCancel(handle) : EndIf
  EndIf
  ProcedureReturn handle
EndProcedure
Procedure.i ScResult(handle.i)
  Protected slot.i
  slot = SchedSlot(handle)
  If slot < 0 Or sc_owner[slot] <> handle : ProcedureReturn 0 : EndIf
  ProcedureReturn sc_result[slot]
EndProcedure
Procedure.i ScReap(handle.i)
  Protected slot.i
  Protected n.i
  Protected context.i
  Protected stack.i
  slot = SchedSlot(handle)
  If slot < 0 Or sc_active <> 0 Or sc_owner[slot] <> handle : ProcedureReturn 0 : EndIf
  If SchedReap(handle) = 0 : ProcedureReturn 0 : EndIf
  context = ScContext(slot)
  stack = ScStack(slot)
  For n = 0 To #SC_BYTES - 1 Step 8 : PokeI(context + n, 0) : Next
  For n = 0 To #SC_STACK + 31 Step 8 : PokeI(stack + n, 0) : Next
  sc_entry[slot] = 0
  sc_argument[slot] = 0
  sc_result[slot] = 0
  sc_owner[slot] = 0
  ProcedureReturn 1
EndProcedure
