; ======================================================================
;  payload_call.pbi - THE PAYLOAD ENTRY. One procedure, every board.
;
;  Anvil/Hal/abi.pbi states what a payload may assume at its first
;  instruction: x0 holds the service table (or 0 when the payload did not
;  ask for one), x1..x7 are ZERO, and the payload is entered at the
;  monitor's own level. Anvil/Core/pmfboot.pbi fills the table and puts
;  its address in gGoX0; the board's RunAt() decides WHETHER to enter
;  (its own safety checks, its own devices to quiesce) and then calls
;  PayloadCall(), which is the only code that keeps the contract.
;
;  WHY THIS FILE EXISTS (2026-09-27). The contract was kept in exactly one
;  place, the Pi 4's CallAddr() in RaspberryPi4/Board/cache.pi4. The other
;  boards entered a payload their own way and broke it silently:
;    Pi 3   RunAt -> Pi3EnterPayload(a): `blr x0` with x0 = the ENTRY
;           ADDRESS, so a payload read its own first instructions as the
;           service table;
;    UNO Q  RunAt -> QCall(a, 0, 0, 0, 0, 0): x0 = 0, x5..x7 whatever
;           they held;
;  and neither kept the payload's return value. Every payload built
;  --wants-services was refused at bind on both boards, and nothing on the
;  desk noticed, because every gate modelled the table instead of entering
;  through the board. One procedure is the fix: a board cannot get the
;  handover wrong if it does not write one.
;
;  IN   gGoAddr   where to branch (the board has already judged it)
;       gGoX0     what x0 holds at entry: the table, or 0
;  OUT  gGoRc     x0 at return, all 64 bits
;  Everything crosses in BSS globals (Anvil/Core/state.pbi), because the
;  stack is the one thing a payload is guaranteed to disturb.
;
;  WHAT IS RESTORED ON THE WAY BACK, AND WHAT IS NOT
;    SP     the monitor's own, saved in gSp before the branch. A payload's
;           prologue switches to its own --stack-addr; one built
;           --entry-returns switches back, one that is not may not.
;    VBAR   the board's business: HwPayloadReturned() (Anvil/Hal/hal.pbi,
;           HwPayload*) reinstalls this level's vectors where the board
;           owns them. A payload is same-level code and may have replaced
;           them.
;    DAIF   MASKED the moment the payload is back, and put back to the
;           value it had before the branch only AFTER HwPayloadReturned -
;           in that order, because until the vectors are this monitor's
;           again an interrupt would be taken by whatever the payload left
;           in VBAR. The Pi 3 and the Rock run masked and stay masked; the
;           UNO Q runs under the firmware's boot services, whose interrupt
;           state is the firmware's, so forcing a mask for good would be a
;           new policy on that board, not a restoration.
;  x19..x29 are callee-saved in this backend's convention and a compiled
;  payload keeps them; nothing here depends on x8..x18.
;
;  THE PI 4 STILL HAS ITS OWN CallAddr() in cache.pi4, which keeps the
;  same contract. Moving the Pi 4 onto this procedure is a board.pi4 change
;  (one include, and CallAddr() replaced by PayloadCall() plus a
;  HwPayloadReturned() that parks on a vector failure as CallAddr did) and
;  is owed to the port lane; until it lands, two procedures keep one
;  contract, and only this one is gated by tools/a64/payload_entry_check.py.
; ======================================================================

Global gPayloadDaif.i          ; DAIF across the branch, restored after

Declare.i HwPayloadReturned()  ; the board's half - Anvil/Hal/hal.pbi, HwPayload*

Procedure PayloadCall()
  ASM
    ; The monitor's sp, where the payload cannot reach it.
    mov  x11, sp
    adrp x10, global_gsp
    add  x10, x10, #:lo12:global_gsp
    str  x11, [x10]
    ; DAIF as it is now, to be put back rather than guessed.
    mrs  x11, daif
    adrp x10, global_gpayloaddaif
    add  x10, x10, #:lo12:global_gpayloaddaif
    str  x11, [x10]

    ; The payload was written as data. Make it visible to fetch.
    dsb  sy
    ic   ialluis
    dsb  sy
    isb

    ; The entry, all 64 bits (an `ldr w9` would branch to the low half).
    adrp x9, global_ggoaddr
    add  x9, x9, #:lo12:global_ggoaddr
    ldr  x9, [x9]

    ; THE ENTRY CONTRACT. x1..x7 zero, then x0 LAST, because x0 is the
    ; one with a value in it and a later clear would undo the handover.
    movz x1, #0
    movz x2, #0
    movz x3, #0
    movz x4, #0
    movz x5, #0
    movz x6, #0
    movz x7, #0
    adrp x0, global_ggox0
    add  x0, x0, #:lo12:global_ggox0
    ldr  x0, [x0]

    ; BLR: x30 is the instruction after this one, so a payload built
    ; --entry-returns comes back here.
    blr  x9

    ; --- it came back ------------------------------------------------
    ; x0 first, before anything can touch it.
    adrp x10, global_ggorc
    add  x10, x10, #:lo12:global_ggorc
    str  x0, [x10]
    msr  daifset, #15
    adrp x10, global_gsp
    add  x10, x10, #:lo12:global_gsp
    ldr  x11, [x10]
    mov  sp, x11
  EndASM
  ; sp is ours again, so this call and the epilogue below use OUR frame.
  HwPayloadReturned()
  ; The vectors are ours: the interrupt state can be what it was.
  ASM
    adrp x10, global_gpayloaddaif
    add  x10, x10, #:lo12:global_gpayloaddaif
    ldr  x11, [x10]
    msr  daif, x11
    isb
  EndASM
EndProcedure

; ----------------------------------------------------------------------
;  PayloadEnter(a) - what a board's RunAt calls once it has decided to
;  enter: the address in, the payload's x0 cleared out of gGoRc until it
;  returns, and gGoX0 CLEARED ON THE WAY BACK OUT, so a plain `run` after
;  a `boot` is not handed a stale table (Anvil/Core/pmfboot.pbi fills it
;  immediately before each entry). The answer is gGoRc.
; ----------------------------------------------------------------------
Procedure.i PayloadEnter(a.i)
  gGoAddr = a
  gGoRc = 0
  PayloadCall()
  gGoX0 = 0
  ProcedureReturn gGoRc
EndProcedure
