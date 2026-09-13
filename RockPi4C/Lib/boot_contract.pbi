; U-Boot booti entry contract for the original ROCK Pi 4C v1.2.
; x0 is the FDT, x1..x3 are zero and execution is Non-secure EL2. U-Boot/ATF
; keep PSCI ownership. The monitor never probes or rewrites firmware memory.
#ROCK_FDT_MAGIC = $D00DFEED
Global rock_dtb.i
Global rock_dtb_end.i
Global rock_current_el.i
Global rock_mpidr.i
Global rock_boot_error.i

Procedure.i RockBe32(address.i)
  ProcedureReturn (PeekA(address) << 24) | (PeekA(address + 1) << 16) | (PeekA(address + 2) << 8) | PeekA(address + 3)
EndProcedure

ProcedureNaked RockCaptureEnvironment()
  ASM
    msr daifset, #15
    adrp x9, global_rock_current_el
    add x9, x9, #:lo12:global_rock_current_el
    mrs x10, CurrentEL
    str x10, [x9]
    adrp x9, global_rock_mpidr
    add x9, x9, #:lo12:global_rock_mpidr
    mrs x10, mpidr_el1
    str x10, [x9]
    ret
  ENDASM
EndProcedure

Procedure.i RockRangesOverlap(a.i, aBytes.i, b.i, bBytes.i)
  If aBytes <= 0 Or bBytes <= 0 : ProcedureReturn 0 : EndIf
  If a > $7FFFFFFFFFFFFFFF - aBytes Or b > $7FFFFFFFFFFFFFFF - bBytes
    ProcedureReturn 1
  EndIf
  ProcedureReturn Bool(a < b + bBytes And b < a + aBytes)
EndProcedure

Procedure.i RockDtbContains(text.i)
  Protected needle.i
  Protected at.i
  Protected scan.i
  Protected match.i
  For needle = 0 To 127
    If PeekA(text + needle) = 0 : Break : EndIf
  Next
  If needle = 0 Or needle > 127 : ProcedureReturn 0 : EndIf
  For at = rock_dtb To rock_dtb_end - needle
    match = 1
    For scan = 0 To needle - 1
      If PeekA(at + scan) <> PeekA(text + scan) : match = 0 : Break : EndIf
    Next
    If match <> 0 : ProcedureReturn 1 : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockValidateStructure(offStruct.i, sizeStruct.i, offStrings.i, sizeStrings.i)
  Protected cursor.i
  Protected finish.i
  Protected strings.i
  Protected token.i
  Protected bytes.i
  Protected nameOff.i
  Protected depth.i
  Protected scan.i
  cursor = rock_dtb + offStruct
  finish = cursor + sizeStruct
  strings = rock_dtb + offStrings
  While cursor <= finish - 4
    token = RockBe32(cursor) : cursor = cursor + 4
    Select token
      Case 1
        depth = depth + 1
        If depth > 64 : ProcedureReturn 0 : EndIf
        scan = cursor
        While scan < finish And PeekA(scan) <> 0 : scan = scan + 1 : Wend
        If scan >= finish : ProcedureReturn 0 : EndIf
        cursor = ((scan + 4) >> 2) << 2
      Case 2
        depth = depth - 1
        If depth < 0 : ProcedureReturn 0 : EndIf
      Case 3
        If cursor > finish - 8 : ProcedureReturn 0 : EndIf
        bytes = RockBe32(cursor) : nameOff = RockBe32(cursor + 4)
        cursor = cursor + 8
        If bytes < 0 Or bytes > finish-cursor Or nameOff < 0 Or nameOff >= sizeStrings
          ProcedureReturn 0
        EndIf
        scan = strings + nameOff
        While scan < strings + sizeStrings And PeekA(scan) <> 0 : scan = scan + 1 : Wend
        If scan >= strings + sizeStrings : ProcedureReturn 0 : EndIf
        cursor = ((cursor + bytes + 3) >> 2) << 2
      Case 4
        ; FDT_NOP
      Case 9
        ProcedureReturn Bool(depth = 0)
      Default
        ProcedureReturn 0
    EndSelect
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i RockValidateDtb()
  Protected total.i
  Protected offStruct.i
  Protected offStrings.i
  Protected offReserve.i
  Protected sizeStruct.i
  Protected sizeStrings.i
  Protected cursor.i
  Protected base.i
  Protected bytes.i
  If rock_dtb <> #ROCK_DTB_EXPECTED Or (rock_dtb & 7) <> 0
    rock_boot_error = 10 : ProcedureReturn 0
  EndIf
  If RockBe32(rock_dtb) <> #ROCK_FDT_MAGIC
    rock_boot_error = 11 : ProcedureReturn 0
  EndIf
  total = RockBe32(rock_dtb + 4)
  If total < 72 Or total > #ROCK_DTB_MAX_BYTES Or rock_dtb > $7FFFFFFFFFFFFFFF - total
    rock_boot_error = 12 : ProcedureReturn 0
  EndIf
  rock_dtb_end = rock_dtb + total
  If RockRangesOverlap(rock_dtb,total,#ROCK_IMAGE_BASE,#ROCK_RESERVE_END-#ROCK_IMAGE_BASE) <> 0
    rock_boot_error = 13 : ProcedureReturn 0
  EndIf
  offStruct = RockBe32(rock_dtb + 8)
  offStrings = RockBe32(rock_dtb + 12)
  offReserve = RockBe32(rock_dtb + 16)
  sizeStrings = RockBe32(rock_dtb + 32)
  sizeStruct = RockBe32(rock_dtb + 36)
  If RockBe32(rock_dtb + 20) <> 17 Or RockBe32(rock_dtb + 24) > 17
    rock_boot_error = 14 : ProcedureReturn 0
  EndIf
  If offReserve < 40 Or (offReserve & 7) <> 0 Or offStruct < 40 Or (offStruct & 3) <> 0 Or offStrings < 40
    rock_boot_error = 15 : ProcedureReturn 0
  EndIf
  If sizeStruct > total Or offStruct > total-sizeStruct Or sizeStrings > total Or offStrings > total-sizeStrings
    rock_boot_error = 16 : ProcedureReturn 0
  EndIf
  If RockValidateStructure(offStruct,sizeStruct,offStrings,sizeStrings) = 0
    rock_boot_error = 19 : ProcedureReturn 0
  EndIf
  ; These strings are required from the exact upstream board DT. Their
  ; presence is checked only after the token/name bounds above prove that the
  ; flattened tree can be traversed safely. A future general DT resolver may
  ; replace this conservative first-port identity gate; it must not weaken it.
  If RockDtbContains("radxa,rockpi4c") = 0 Or RockDtbContains("rockchip,rk3399") = 0 Or RockDtbContains("serial2:1500000n8") = 0 Or RockDtbContains("arm,gic-v3") = 0
    rock_boot_error = 20 : ProcedureReturn 0
  EndIf
  ; Validate every 64-bit big-endian reserve-map pair and reject a firmware
  ; reservation that intersects Anvil's exact early ownership window.
  cursor = rock_dtb + offReserve
  While cursor <= rock_dtb_end - 16
    base = (RockBe32(cursor) << 32) | (RockBe32(cursor + 4) & $FFFFFFFF)
    bytes = (RockBe32(cursor + 8) << 32) | (RockBe32(cursor + 12) & $FFFFFFFF)
    If base = 0 And bytes = 0 : rock_boot_error = 0 : ProcedureReturn 1 : EndIf
    If bytes <= 0 Or RockRangesOverlap(base,bytes,#ROCK_IMAGE_BASE,#ROCK_RESERVE_END-#ROCK_IMAGE_BASE) <> 0
      rock_boot_error = 17 : ProcedureReturn 0
    EndIf
    cursor = cursor + 16
  Wend
  rock_boot_error = 18
  ProcedureReturn 0
EndProcedure

Procedure.i RockValidateEntry()
  RockCaptureEnvironment()
  If rock_current_el <> 8
    rock_boot_error = 1 : ProcedureReturn 0
  EndIf
  ; U-Boot starts only the boot CPU. Refuse a surprise secondary rather than
  ; sharing the compiler's primary stack or global early state.
  If (rock_mpidr & $FF00FFFFFF) <> 0
    rock_boot_error = 2 : ProcedureReturn 0
  EndIf
  ProcedureReturn RockValidateDtb()
EndProcedure
