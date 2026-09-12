; BCM2837 SDHOST (SD0), not Arasan SDHCI/EMMC2. Native polled 1-bit SDHC.
; Include timer.pbi and mailbox.pbi first. Caller supplies firmware maximum
; core-clock rate, and firmware-validated ARM RAM extent. SDHOST uses CORE,
; not the Pi4 EMMC clock. SLOW_CARD keeps the full divider in data mode.
; Original implementation from register/protocol facts; no Linux code copied.
; Specification/reference scope and silicon limits: docs/PI3_SELF_UPDATE.md.
#P3SD_BASE = $3F202000
#P3SD_GPIO = $3F200000
#P3SD_ERR_MASK = $F8
Global p3sd_ready.i
Global p3sd_attempted.i
Global p3sd_error.i
Global p3sd_command.i
Global p3sd_status.i
Global p3sd_rca.i
Global p3sd_blocks.i
Global p3sd_ram_base.i
Global p3sd_ram_bytes.i
Global p3sd_clock_ceiling.i
Global p3sd_write_first.i
Global p3sd_write_count.i
Global Dim p3sd_response.i[4]

Procedure Pi3SdBarrier()
  ASM
    dsb sy
    isb
  EndASM
EndProcedure
Procedure.i p3sdRead(reg.i)
  Protected value.i
  Pi3SdBarrier()
  value = PeekL(#P3SD_BASE + reg) & $FFFFFFFF
  Pi3SdBarrier()
  ProcedureReturn value
EndProcedure
Procedure p3sdWrite(reg.i, value.i)
  Pi3SdBarrier()
  PokeL(#P3SD_BASE + reg, value)
  Pi3SdBarrier()
EndProcedure
Procedure.i p3sdFail(error.i)
  p3sd_error = error
  p3sd_ready = 0
  ProcedureReturn 0
EndProcedure
Procedure.i Pi3SdError()
  ProcedureReturn p3sd_error
EndProcedure
Procedure.i Pi3SdBlockCount()
  ProcedureReturn p3sd_blocks
EndProcedure
Procedure.i p3sdContext()
  ASM
    mrs x0, mpidr_el1
    movz x9, #$FFFF
    movk x9, #$FF, lsl #16
    and x10, x0, x9
    lsr x0, x0, #32
    movz x9, #255
    and x0, x0, x9
    orr x0, x0, x10
    cbnz x0, p3sdBadContext
    mrs x0, currentel
    cmp x0, #8
    b.eq p3sdContext2
    cmp x0, #12
    b.ne p3sdBadContext
    mrs x0, sctlr_el3
    b p3sdCheckContext
p3sdContext2:
    mrs x0, sctlr_el2
p3sdCheckContext:
    movz x9, #5
    and x0, x0, x9
    cbnz x0, p3sdBadContext
    mrs x0, daif
    movz x9, #$3C0
    and x0, x0, x9
    cmp x0, x9
    b.ne p3sdBadContext
    movz x0, #1
    b p3sdEndContext
p3sdBadContext:
    movz x0, #0
p3sdEndContext:
  EndASM
EndProcedure
Procedure.i p3sdWaitClear(reg.i, mask.i, timeout.i)
  Protected start.i
  Protected now.i
  Protected spin.i
  start = Pi3Micros()
  If start < 0 : ProcedureReturn p3sdFail(-2) : EndIf
  For spin = 0 To 999999
    If (p3sdRead(reg) & mask) = 0 : ProcedureReturn 1 : EndIf
    now = Pi3Micros()
    If now < start Or now - start >= timeout : ProcedureReturn p3sdFail(-3) : EndIf
  Next
  ProcedureReturn p3sdFail(-2)
EndProcedure
Procedure.i p3sdCommand(index.i, argument.i, flags.i)
  Protected value.i
  Protected n.i
  Protected start.i
  Protected now.i
  If p3sdWaitClear(0, $8000, 100000) = 0 : ProcedureReturn 0 : EndIf
  p3sd_command = index
  p3sdWrite($20, $7F8)
  p3sdWrite(4, argument)
  p3sdWrite(0, $8000 | flags | index)
  If p3sdWaitClear(0, $8000, 100000) = 0 : ProcedureReturn 0 : EndIf
  value = p3sdRead(0)
  p3sd_status = p3sdRead($20)
  If (value & $4000) <> 0 Or (p3sd_status & #P3SD_ERR_MASK) <> 0 : ProcedureReturn p3sdFail(-4) : EndIf
  If (flags & $800) <> 0
    start = Pi3Micros()
    If start < 0 : ProcedureReturn p3sdFail(-2) : EndIf
    For n = 0 To 999999
      p3sd_status = p3sdRead($20)
      If (p3sd_status & #P3SD_ERR_MASK) <> 0 : ProcedureReturn p3sdFail(-4) : EndIf
      If (p3sd_status & $400) <> 0 : Break : EndIf
      now = Pi3Micros()
      If now < start Or now - start >= 1000000 : ProcedureReturn p3sdFail(-3) : EndIf
    Next
    If n > 999999 : ProcedureReturn p3sdFail(-3) : EndIf
    p3sdWrite($20, $400)
  EndIf
  For n = 0 To 3 : p3sd_response[n] = p3sdRead($10 + n * 4) : Next
  ProcedureReturn 1
EndProcedure
Procedure.i p3sdR1()
  If (p3sd_response[0] & $FDFFE008) <> 0 : ProcedureReturn p3sdFail(-5) : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i p3sdClock(hz.i)
  Protected div.i
  div = (p3sd_clock_ceiling + hz - 1) / hz
  If div < 2 : div = 2 : EndIf
  If div > 2049 : ProcedureReturn p3sdFail(-6) : EndIf
  p3sdWrite($0C, div - 2)
  ; Hardware timeout conservatively scaled for slowest permitted card clock;
  ; software real-time bounds remain authoritative.
  p3sdWrite(8, hz / 2)
  If p3sdRead($0C) <> div - 2 : ProcedureReturn p3sdFail(-6) : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i p3sdCardReady()
  Protected start.i
  Protected now.i
  Protected spin.i
  start = Pi3Micros()
  If start < 0 : ProcedureReturn p3sdFail(-2) : EndIf
  For spin = 0 To 9999
    If p3sdCommand(13, p3sd_rca << 16, 0) = 0 Or p3sdR1() = 0 : ProcedureReturn 0 : EndIf
    If (p3sd_response[0] & $1F00) = $900 : ProcedureReturn 1 : EndIf
    now = Pi3Micros()
    If now < start Or now - start >= 1000000 : ProcedureReturn p3sdFail(-7) : EndIf
  Next
  ProcedureReturn p3sdFail(-7)
EndProcedure

Procedure.i Pi3SdInit(clockCeilingHz.i, ramBase.i, ramBytes.i)
  Protected pins.i
  Protected value.i
  Protected actual.i
  Protected start.i
  Protected now.i
  Protected n.i
  Protected size.i
  If p3sd_attempted <> 0 Or p3sdContext() = 0 : ProcedureReturn p3sdFail(-1) : EndIf
  If ramBase <> 0 Or ramBytes < $2000000 Or ramBytes > $3F000000 Or clockCeilingHz < 1000000 Or clockCeilingHz > 800000000 : ProcedureReturn p3sdFail(-1) : EndIf
  actual = Pi3ClockRate(4)
  If actual < 1 Or actual > clockCeilingHz Or actual / ((clockCeilingHz + 399999) / 400000) < 100000 : ProcedureReturn p3sdFail(-6) : EndIf
  p3sd_ram_base = ramBase
  p3sd_ram_bytes = ramBytes
  p3sd_clock_ceiling = clockCeilingHz
  p3sd_attempted = 1
  ; GPIO48..53 ALT0 SD0. Preserve unrelated pin fields. Pi3's WLAN uses
  ; GPIO34..39/Arasan and is not reconfigured by this controller.
  pins = PeekL(#P3SD_GPIO + 16) & $FFFFFFFF
  pins = (pins & $C0FFFFFF) | $24000000
  PokeL(#P3SD_GPIO + 16, pins)
  pins = PeekL(#P3SD_GPIO + 20) & $FFFFFFFF
  pins = (pins & $FFFFF000) | $924
  PokeL(#P3SD_GPIO + 20, pins)
  Pi3SdBarrier()
  ; SDHOST controller reset/power sequencing. Never changes OTP/card fuses.
  p3sdWrite($30, 0)
  p3sdWrite(0, 0)
  p3sdWrite(4, 0)
  p3sdWrite($20, $7F8)
  p3sdWrite($38, 0)
  p3sdWrite($3C, 0)
  p3sdWrite($50, 0)
  value = p3sdRead($34)
  value = (value & $FFF801FF) | $10800
  p3sdWrite($34, value)
  If Pi3DelayUs(20000) = 0 : ProcedureReturn p3sdFail(-2) : EndIf
  p3sdWrite($30, 1)
  If Pi3DelayUs(20000) = 0 : ProcedureReturn p3sdFail(-2) : EndIf
  ; BUSY status generation is enabled and polled; primary DAIF stays masked.
  p3sdWrite($38, $40A)
  If p3sdClock(400000) = 0 : ProcedureReturn 0 : EndIf
  If p3sdCommand(0, 0, $400) = 0 : ProcedureReturn 0 : EndIf
  If p3sdCommand(8, $1AA, 0) = 0 : ProcedureReturn 0 : EndIf
  If p3sd_response[0] <> $1AA : ProcedureReturn p3sdFail(-8) : EndIf
  start = Pi3Micros()
  If start < 0 : ProcedureReturn p3sdFail(-2) : EndIf
  For n = 0 To 9999
    If p3sdCommand(55, 0, 0) = 0 Or p3sdR1() = 0 : ProcedureReturn 0 : EndIf
    If (p3sd_response[0] & $20) = 0 : ProcedureReturn p3sdFail(-8) : EndIf
    If p3sdCommand(41, $40FF8000, 0) = 0 : ProcedureReturn 0 : EndIf
    If (p3sd_response[0] & $80000000) <> 0 : Break : EndIf
    now = Pi3Micros()
    If now < start Or now - start >= 2000000 : ProcedureReturn p3sdFail(-8) : EndIf
  Next
  If n > 9999 Or (p3sd_response[0] & $40000000) = 0 : ProcedureReturn p3sdFail(-8) : EndIf
  If p3sdCommand(2, 0, $200) = 0 : ProcedureReturn 0 : EndIf
  If p3sdCommand(3, 0, 0) = 0 : ProcedureReturn 0 : EndIf
  If (p3sd_response[0] & $E000) <> 0 : ProcedureReturn p3sdFail(-8) : EndIf
  p3sd_rca = p3sd_response[0] >> 16
  If p3sd_rca = 0 : ProcedureReturn p3sdFail(-8) : EndIf
  If p3sdCommand(9, p3sd_rca << 16, $200) = 0 : ProcedureReturn 0 : EndIf
  ; SDHOST returns unshifted 128-bit R2; unlike the Arasan SDHCI driver.
  If (p3sd_response[3] >> 30) <> 1 : ProcedureReturn p3sdFail(-8) : EndIf
  size = ((p3sd_response[2] & $3F) << 16) | (p3sd_response[1] >> 16)
  p3sd_blocks = (size + 1) * 1024
  If p3sdCommand(7, p3sd_rca << 16, $800) = 0 Or p3sdR1() = 0 : ProcedureReturn 0 : EndIf
  If p3sdCardReady() = 0 : ProcedureReturn 0 : EndIf
  If p3sdClock(25000000) = 0 : ProcedureReturn 0 : EndIf
  p3sd_error = 0
  p3sd_ready = 1
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3SdSetWriteWindow(first.i, count.i)
  If p3sd_ready = 0 Or p3sdContext() = 0 : ProcedureReturn 0 : EndIf
  If first < 1 Or count < 1 Or count > p3sd_blocks Or first > p3sd_blocks - count : ProcedureReturn 0 : EndIf
  p3sd_write_first = first
  p3sd_write_count = count
  ProcedureReturn 1
EndProcedure

Procedure.i p3sdTransfer(lba.i, buffer.i, writing.i)
  Protected start.i
  Protected now.i
  Protected spin.i
  Protected count.i
  Protected edm.i
  Protected words.i
  Protected state.i
  If p3sd_ready = 0 Or p3sdContext() = 0 : ProcedureReturn p3sdFail(-1) : EndIf
  If lba < 0 Or lba >= p3sd_blocks Or (buffer & 3) <> 0 Or buffer < $1000 Or buffer > p3sd_ram_bytes - 512 : ProcedureReturn p3sdFail(-9) : EndIf
  If writing <> 0
    If p3sd_write_count < 1 Or lba < p3sd_write_first Or lba - p3sd_write_first >= p3sd_write_count
      ProcedureReturn p3sdFail(-13)
    EndIf
  EndIf
  state = p3sdRead($34) & 15
  If state <> 0 And state <> 1 : ProcedureReturn p3sdFail(-10) : EndIf
  p3sdWrite($3C, 512)
  p3sdWrite($50, 1)
  If writing <> 0
    If p3sdCommand(24, lba, $80) = 0 : ProcedureReturn 0 : EndIf
  Else
    If p3sdCommand(17, lba, $40) = 0 : ProcedureReturn 0 : EndIf
  EndIf
  If p3sdR1() = 0 : ProcedureReturn 0 : EndIf
  start = Pi3Micros()
  If start < 0 : ProcedureReturn p3sdFail(-2) : EndIf
  count = 0
  For spin = 0 To 999999
    p3sd_status = p3sdRead($20)
    If (p3sd_status & #P3SD_ERR_MASK) <> 0 : ProcedureReturn p3sdFail(-11) : EndIf
    edm = p3sdRead($34)
    words = (edm >> 4) & 31
    If words > 16 : ProcedureReturn p3sdFail(-11) : EndIf
    If writing <> 0 : words = 16 - words : EndIf
    If words > 8 : words = 8 : EndIf
    While words > 0 And count < 128
      If writing <> 0
        p3sdWrite($40, PeekL(buffer + count * 4))
      Else
        PokeL(buffer + count * 4, p3sdRead($40))
      EndIf
      count = count + 1
      words = words - 1
    Wend
    If count = 128 : Break : EndIf
    now = Pi3Micros()
    If now < start Or now - start >= 500000 : ProcedureReturn p3sdFail(-12) : EndIf
  Next
  If count <> 128 : ProcedureReturn p3sdFail(-12) : EndIf
  For spin = 0 To 999999
    p3sd_status = p3sdRead($20)
    If (p3sd_status & #P3SD_ERR_MASK) <> 0 : ProcedureReturn p3sdFail(-11) : EndIf
    edm = p3sdRead($34)
    state = edm & 15
    If state = 0 Or state = 1 : Break : EndIf
    ; SDHOST single-block completion can stop in its inter-block wait state.
    ; FORCE_DATA_MODE ends only that known state, never a transfer in progress.
    If (writing = 0 And state = 4) Or (writing <> 0 And state = 10)
      p3sdWrite($34, edm | $80000)
    EndIf
    now = Pi3Micros()
    If now < start Or now - start >= 1000000 : ProcedureReturn p3sdFail(-12) : EndIf
  Next
  If spin > 999999 : ProcedureReturn p3sdFail(-12) : EndIf
  If p3sdCardReady() = 0 : ProcedureReturn 0 : EndIf
  p3sd_error = 0
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3SdReadBlock(lba.i, buffer.i)
  ProcedureReturn p3sdTransfer(lba, buffer, 0)
EndProcedure
Procedure.i Pi3SdWriteBlock(lba.i, buffer.i)
  ProcedureReturn p3sdTransfer(lba, buffer, 1)
EndProcedure
