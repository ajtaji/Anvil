; RK3399 GICv3 foundation. This code owns only the current redistributor and
; EL2 hypervisor physical timer PPI (INTID 26). IRQ stays masked here.
#ROCK_GICD_CTLR = $0000
#ROCK_GICD_TYPER = $0004
#ROCK_GICD_RWP = $80000000
#ROCK_GICD_ENABLE_G1NS = $00000001
#ROCK_GICD_ARE_NS = $00000010
#ROCK_GICR_TYPER = $0008
#ROCK_GICR_WAKER = $0014
#ROCK_GICR_PROCESSOR_SLEEP = $0002
#ROCK_GICR_CHILDREN_ASLEEP = $0004
#ROCK_GICR_IGROUPR0 = $0080
#ROCK_GICR_ISENABLER0 = $0100
#ROCK_GICR_ICENABLER0 = $0180
#ROCK_GICR_ICPENDR0 = $0280
#ROCK_GICR_ICACTIVER0 = $0380
#ROCK_GICR_IPRIORITYR0 = $0400
Global rock_gicr_this.i
Global rock_gic_error.i
Global rock_gic_scratch.i
Global rock_gic_ready.i

ProcedureNaked.i RockGicAffinity()
  ASM
    mrs x0, mpidr_el1
    movz x9, #255
    lsr x1, x0, #32
    and x1, x1, x9
    lsr x2, x0, #16
    and x2, x2, x9
    lsl x1, x1, #24
    lsl x2, x2, #16
    orr x1, x1, x2
    lsr x2, x0, #8
    and x2, x2, x9
    lsl x2, x2, #8
    orr x1, x1, x2
    and x0, x0, x9
    orr x0, x1, x0
    ret
  ENDASM
EndProcedure

Procedure.i RockGicWait(address.i, mask.i, wanted.i)
  Protected start.i
  Protected now.i
  Protected attempt.i
  start = RockTimerTicks()
  For attempt = 0 To 999999
    If (PeekN(address) & mask) = wanted : ProcedureReturn 1 : EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= rock_timer_frequency/10 : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockGicFindRedistributor()
  Protected affinity.i
  Protected frame.i
  Protected typer.i
  affinity = RockGicAffinity()
  For frame = 0 To #ROCK_GICR_FRAMES-1
    typer = PeekI(#ROCK_GICR + frame * #ROCK_GICR_STRIDE + #ROCK_GICR_TYPER)
    If ((typer >> 32) & $FFFFFFFF) = affinity
      rock_gicr_this = #ROCK_GICR + frame * #ROCK_GICR_STRIDE
      ProcedureReturn 1
    EndIf
  Next
  rock_gic_error = 2
  ProcedureReturn 0
EndProcedure

ProcedureNaked RockGicSystemRegisters()
  ASM
    mrs x9, icc_sre_el2
    movz x10, #9
    orr x9, x9, x10
    msr icc_sre_el2, x9
    isb
    mrs x9, icc_sre_el1
    movz x10, #1
    orr x9, x9, x10
    msr icc_sre_el1, x9
    movz x9, #255
    msr icc_pmr_el1, x9
    msr icc_bpr1_el1, xzr
    movz x9, #1
    msr icc_igrpen1_el1, x9
    isb
    ret
  ENDASM
EndProcedure

Procedure.i RockGicInitTimerFoundation()
  Protected value.i
  Protected sgi.i
  Protected mask.i
  Protected priority.i
  If rock_current_el <> 8 Or rock_timer_frequency = 0 Or rock_exception_vbar = 0 Or rock_gic_ready <> 0
    rock_gic_error = 1 : ProcedureReturn 0
  EndIf
  If (PeekN(#ROCK_GICD + #ROCK_GICD_TYPER) & $1F) < 4
    rock_gic_error = 3 : ProcedureReturn 0
  EndIf
  If RockGicFindRedistributor() = 0 : ProcedureReturn 0 : EndIf
  value = PeekN(rock_gicr_this + #ROCK_GICR_WAKER) & $FFFFFFFF
  PokeL(rock_gicr_this + #ROCK_GICR_WAKER,value & $FFFFFFFD)
  If RockGicWait(rock_gicr_this + #ROCK_GICR_WAKER,#ROCK_GICR_CHILDREN_ASLEEP,0) = 0
    rock_gic_error = 4 : ProcedureReturn 0
  EndIf
  sgi = rock_gicr_this + #ROCK_GICR_SGI
  mask = 1 << #ROCK_GIC_TIMER_INTID
  PokeL(sgi + #ROCK_GICR_ICENABLER0,mask)
  PokeL(sgi + #ROCK_GICR_ICPENDR0,mask)
  PokeL(sgi + #ROCK_GICR_ICACTIVER0,mask)
  value = PeekN(sgi + #ROCK_GICR_IGROUPR0) & $FFFFFFFF
  PokeL(sgi + #ROCK_GICR_IGROUPR0,value | mask)
  priority = sgi + #ROCK_GICR_IPRIORITYR0 + (#ROCK_GIC_TIMER_INTID & $FFFFFFFC)
  value = PeekN(priority) & $FFFFFFFF
  value = (value & $FF00FFFF) | $00A00000
  PokeL(priority,value)
  value = PeekN(#ROCK_GICD + #ROCK_GICD_CTLR) & $FFFFFFFF
  PokeL(#ROCK_GICD + #ROCK_GICD_CTLR,value | #ROCK_GICD_ENABLE_G1NS | #ROCK_GICD_ARE_NS)
  If RockGicWait(#ROCK_GICD + #ROCK_GICD_CTLR,#ROCK_GICD_RWP,0) = 0
    rock_gic_error = 5 : ProcedureReturn 0
  EndIf
  RockGicSystemRegisters()
  PokeL(sgi + #ROCK_GICR_ISENABLER0,mask)
  ASM
    dsb sy
    isb
  ENDASM
  rock_gic_ready = 1
  rock_gic_error = 0
  ProcedureReturn 1
EndProcedure
