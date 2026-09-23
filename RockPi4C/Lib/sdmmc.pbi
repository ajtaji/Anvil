; RK3399 removable SD socket, Synopsys DesignWare MSHC PIO path.
; Source contract: RK3399 DW-MSHC at FE320000, 4-bit socket in the board DT,
; HCLK_SDMMC/SCLK_SDMMC and SRST_SDMMC in the RK3399 CRU bindings. This first
; implementation deliberately negotiates and transfers in one-bit mode; it
; does not use DMA or touch card contents during initialization.
;
; Public filesystem ABI (512-byte sectors):
;   RockSdInit()                         1 ready, 0 refused
;   RockSdBlockCount()                   number of addressable sectors
;   RockSdReadBlocks(lba,count,*buffer)  1/0 ranged callback
;   RockSdWriteBlocks(lba,count,*buffer) 1/0 ranged callback, explicit caller
;   RockSdFlush()                        wait for card TRAN/ready (bounded)
;   RockSdErrorText()                    pointer to last error sentence
;
; Filesystem ranges stay ranges down to the card. Contiguous requests use
; bounded 128 KiB CMD18/CMD25 PIO windows, followed by explicit CMD12, instead
; of turning every sector into its own command and card-ready wait. Byte access
; keeps caller buffers alignment-independent. Writes remain armed only by the
; explicit filesystem mutation path above this driver.

#ROCK_SDMMC = $FE320000
#ROCK_SD_GRF = $FF770000
#ROCK_SD_CRU = $FF760000
#ROCK_SD_PMU = $FF310000
#ROCK_SDMMC_BLOCK = 512
#ROCK_SDMMC_MAX_BLOCKS = 256
#ROCK_SDMMC_FIFO_DEPTH = 256
#ROCK_SDMMC_DATA = $200
#ROCK_SDMMC_CMD = $02C
#ROCK_SDMMC_ARG = $028
#ROCK_SDMMC_RESP0 = $030
#ROCK_SDMMC_RESP1 = $034
#ROCK_SDMMC_RESP2 = $038
#ROCK_SDMMC_RESP3 = $03C
#ROCK_SDMMC_INTSTS = $044
#ROCK_SDMMC_STATUS = $048
#ROCK_SDMMC_FIFOTH = $04C
#ROCK_SDMMC_CTRL = $000
#ROCK_SD_CTRL_FIFO_RESET = $00000002
#ROCK_SDMMC_PWREN = $004
#ROCK_SDMMC_CLKDIV = $008
#ROCK_SDMMC_CLKSRC = $00C
#ROCK_SDMMC_CLKENA = $010
#ROCK_SDMMC_TMOUT = $014
#ROCK_SDMMC_CTYPE = $018
#ROCK_SDMMC_BLKSIZ = $01C
#ROCK_SDMMC_BYTCNT = $020
#ROCK_SDMMC_RINTSTS = $044

#ROCK_SD_ERR_OK = 0
#ROCK_SD_ERR_TIMER = 1
#ROCK_SD_ERR_POWER = 2
#ROCK_SD_ERR_CLOCK = 3
#ROCK_SD_ERR_RESET = 4
#ROCK_SD_ERR_CONTROLLER = 5
#ROCK_SD_ERR_COMMAND = 6
#ROCK_SD_ERR_TIMEOUT = 7
#ROCK_SD_ERR_CARD = 8
#ROCK_SD_ERR_CAPACITY = 9
#ROCK_SD_ERR_BOUNDS = 10
#ROCK_SD_ERR_BUFFER = 11
#ROCK_SD_ERR_DATA = 12
#ROCK_SD_ERR_BUSY = 13
#ROCK_SD_ERR_UNSUPPORTED = 14

#ROCK_SD_CMD_START = $80000000
#ROCK_SD_CMD_UPDATE_CLOCK = $00200000
#ROCK_SD_CMD_USE_HOLD = $20000000
#ROCK_SD_CMD_INIT = $00008000
#ROCK_SD_CMD_STOP = $00004000
#ROCK_SD_CMD_WAIT_PREV = $00002000
#ROCK_SD_CMD_DATA = $00000200
#ROCK_SD_CMD_WRITE = $00000400
#ROCK_SD_CMD_RESP = $00000040
#ROCK_SD_CMD_LONG = $00000080
#ROCK_SD_CMD_CRC = $00000100
#ROCK_SD_INT_CMD_DONE = $00000004
#ROCK_SD_INT_DATA_OVER = $00000008
#ROCK_SD_INT_CMD_ERRORS = $00001142 ; RCRC | RTO | RESP_ERR | HLE
#ROCK_SD_INT_DATA_ERRORS = $0000AF80 ; DCRC | DRTO | HTO | FRUN | HLE | SBE | EBE
#ROCK_SD_R1_ERRORS = $FFFFE008 ; R1 error bits, excluding current-state/ready/app-command
#ROCK_SD_OCR_READY = $80000000
#ROCK_SD_OCR_HC = $40000000
#ROCK_SD_OCR_VOLTAGE = $00FF8000
#ROCK_SD_R1_READY_FOR_DATA = $00000100
#ROCK_SD_R1_STATE_MASK = $00001E00
#ROCK_SD_R1_STATE_TRAN = $00000800

Global rock_sd_error.i
Global rock_sd_ready.i
Global rock_sd_highCapacity.i
Global rock_sd_rca.i
Global rock_sd_blocks.i
Global rock_sd_ciuHz.i
Global rock_sd_clockDiv.i
Global rock_sd_cardHz.i
Global rock_sd_response0.i
Global rock_sd_response1.i
Global rock_sd_response2.i
Global rock_sd_response3.i
Global rock_sd_lastIntStatus.i
Global rock_sd_lastControllerStatus.i
Global rock_sd_lastCommand.i
Global rock_sd_lastArgument.i
Global rock_sd_lastResponse0.i
Global rock_sd_lastResponse1.i
Global rock_sd_lastResponse2.i
Global rock_sd_lastResponse3.i
Global Dim rock_sd_sector.a[#ROCK_SDMMC_BLOCK]

Procedure.i rock_sd_readReg(offset.i)
  ProcedureReturn PeekL(#ROCK_SDMMC + offset) & $FFFFFFFF
EndProcedure

Procedure rock_sd_writeReg(offset.i, value.i)
  PokeL(#ROCK_SDMMC + offset, value & $FFFFFFFF)
EndProcedure

Procedure.i rock_sd_waitReg(offset.i, mask.i, wanted.i, timeoutUs.i)
  Protected start.i
  Protected now.i
  Protected attempt.i
  If rock_timer_frequency = 0 : ProcedureReturn 0 : EndIf
  start = RockTimerTicks()
  For attempt = 0 To 4000000
    If (rock_sd_readReg(offset) & mask) = wanted : ProcedureReturn 1 : EndIf
    now = RockTimerTicks()
    If now < start Or (now-start) >= (rock_timer_frequency/1000000)*timeoutUs : Break : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure rock_sd_setError(code.i)
  rock_sd_error = code
  rock_sd_ready = 0
EndProcedure

Procedure.i rock_sd_clockUpdate()
  Protected attempt.i
  Protected start.i
  Protected now.i
  ; Both the Linux and U-Boot DW-MSHC drivers set PRV_DAT_WAIT on every
  ; clock-update command.  RK3399's wrapper must see that exact handshake.
  rock_sd_writeReg(#ROCK_SDMMC_CMD, #ROCK_SD_CMD_START | #ROCK_SD_CMD_UPDATE_CLOCK | #ROCK_SD_CMD_WAIT_PREV)
  start = RockTimerTicks()
  For attempt = 0 To 200000
    If (rock_sd_readReg(#ROCK_SDMMC_CMD) & #ROCK_SD_CMD_START) = 0 : ProcedureReturn 1 : EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= rock_timer_frequency/1000 : Break : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i rock_sd_setClock(divisor.i)
  Protected attempt.i
  Protected value.i
  If divisor < 0 Or divisor > 255 : ProcedureReturn 0 : EndIf
  rock_sd_writeReg(#ROCK_SDMMC_CLKENA, 0)
  If rock_sd_clockUpdate() = 0 : ProcedureReturn 0 : EndIf
  rock_sd_writeReg(#ROCK_SDMMC_CLKDIV, divisor)
  If rock_sd_clockUpdate() = 0 : ProcedureReturn 0 : EndIf
  rock_sd_writeReg(#ROCK_SDMMC_CLKENA, 1)
  If rock_sd_clockUpdate() = 0 : ProcedureReturn 0 : EndIf
  value = rock_sd_readReg(#ROCK_SDMMC_CLKENA)
  ProcedureReturn Bool((value & 1) <> 0)
EndProcedure

; Update-clock commands use CMD.START and wait for it to self-clear. Regular
; commands additionally check the controller's raw interrupt/error status.
Procedure.i rock_sd_command(opcode.i, argument.i, flags.i)
  Protected attempt.i
  Protected status.i
  Protected start.i
  Protected now.i
  ; Match the reference DW-MSHC command construction. RK3399 uses the clock
  ; hold register on normal commands. CMD0 is an initialization/abort command;
  ; every command other than CMD0/CMD12 waits for the preceding data path.
  flags = flags | #ROCK_SD_CMD_USE_HOLD
  If opcode = 0
    flags = flags | #ROCK_SD_CMD_INIT | #ROCK_SD_CMD_STOP
  ElseIf opcode <> 12
    flags = flags | #ROCK_SD_CMD_WAIT_PREV
  EndIf
  rock_sd_lastCommand = #ROCK_SD_CMD_START | flags | opcode
  rock_sd_lastArgument = argument
  rock_sd_writeReg(#ROCK_SDMMC_RINTSTS, $FFFFFFFF)
  rock_sd_writeReg(#ROCK_SDMMC_ARG, argument)
  rock_sd_writeReg(#ROCK_SDMMC_CMD, rock_sd_lastCommand)
  start = RockTimerTicks()
  For attempt = 0 To 4000000
    status = rock_sd_readReg(#ROCK_SDMMC_RINTSTS)
    rock_sd_lastIntStatus = status
    rock_sd_lastControllerStatus = rock_sd_readReg(#ROCK_SDMMC_STATUS)
    If (status & #ROCK_SD_INT_CMD_ERRORS) <> 0
      rock_sd_lastCommand = rock_sd_readReg(#ROCK_SDMMC_CMD)
      rock_sd_lastResponse0 = rock_sd_readReg(#ROCK_SDMMC_RESP0)
      rock_sd_lastResponse1 = rock_sd_readReg(#ROCK_SDMMC_RESP1)
      rock_sd_lastResponse2 = rock_sd_readReg(#ROCK_SDMMC_RESP2)
      rock_sd_lastResponse3 = rock_sd_readReg(#ROCK_SDMMC_RESP3)
      rock_sd_writeReg(#ROCK_SDMMC_RINTSTS, status)
      ProcedureReturn 0
    EndIf
    If (status & #ROCK_SD_INT_CMD_DONE) <> 0
      rock_sd_writeReg(#ROCK_SDMMC_RINTSTS, #ROCK_SD_INT_CMD_DONE)
      rock_sd_response0 = rock_sd_readReg(#ROCK_SDMMC_RESP0)
      rock_sd_response1 = rock_sd_readReg(#ROCK_SDMMC_RESP1)
      rock_sd_response2 = rock_sd_readReg(#ROCK_SDMMC_RESP2)
      rock_sd_response3 = rock_sd_readReg(#ROCK_SDMMC_RESP3)
      rock_sd_lastResponse0 = rock_sd_response0
      rock_sd_lastResponse1 = rock_sd_response1
      rock_sd_lastResponse2 = rock_sd_response2
      rock_sd_lastResponse3 = rock_sd_response3
      ProcedureReturn 1
    EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= rock_timer_frequency/10 : Break : EndIf
  Next
  rock_sd_lastIntStatus = rock_sd_readReg(#ROCK_SDMMC_RINTSTS)
  rock_sd_lastControllerStatus = rock_sd_readReg(#ROCK_SDMMC_STATUS)
  rock_sd_lastCommand = rock_sd_readReg(#ROCK_SDMMC_CMD)
  rock_sd_lastResponse0 = rock_sd_readReg(#ROCK_SDMMC_RESP0)
  rock_sd_lastResponse1 = rock_sd_readReg(#ROCK_SDMMC_RESP1)
  rock_sd_lastResponse2 = rock_sd_readReg(#ROCK_SDMMC_RESP2)
  rock_sd_lastResponse3 = rock_sd_readReg(#ROCK_SDMMC_RESP3)
  ProcedureReturn 0
EndProcedure

Procedure.i rock_sd_r1ok()
  ProcedureReturn Bool((rock_sd_response0 & #ROCK_SD_R1_ERRORS) = 0)
EndProcedure

Procedure.i rock_sd_waitBusy(timeoutUs.i)
  ProcedureReturn rock_sd_waitReg(#ROCK_SDMMC_STATUS, $00000200, 0, timeoutUs)
EndProcedure

; Linux's DesignWare driver resets the FIFO after a failed data path before
; another request can be issued. Without this, unread words from a short PIO
; drain become the front of the next sector and every request is one command
; behind thereafter.
Procedure.i rock_sd_resetFifo()
  Protected control.i
  control = rock_sd_readReg(#ROCK_SDMMC_CTRL)
  rock_sd_writeReg(#ROCK_SDMMC_CTRL, control | #ROCK_SD_CTRL_FIFO_RESET)
  ProcedureReturn rock_sd_waitReg(#ROCK_SDMMC_CTRL, #ROCK_SD_CTRL_FIFO_RESET, 0, 10000)
EndProcedure

Procedure.i rock_sd_dataFail(code.i)
  rock_sd_writeReg(#ROCK_SDMMC_RINTSTS, $FFFFFFFF)
  If rock_sd_resetFifo() = 0
    rock_sd_error = #ROCK_SD_ERR_CONTROLLER
  Else
    rock_sd_error = code
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i rock_sd_appCommand(argument.i, opcode.i, flags.i)
  If rock_sd_command(55, rock_sd_rca << 16, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC) = 0
    ProcedureReturn 0
  EndIf
  If (rock_sd_response0 & #ROCK_SD_R1_ERRORS) <> 0 Or (rock_sd_response0 & $20) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn rock_sd_command(opcode, argument, flags)
EndProcedure

; U-Boot's MMC layer uses CMD18/CMD25 for a multi-block request and then sends
; an explicit CMD12 with the DesignWare ABORT_STOP bit. Keep that exact command
; lifecycle here. CMD13 readiness remains the public flush contract after a
; write.
Procedure.i rock_sd_stopTransfer()
  If rock_sd_command(12, 0, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC | #ROCK_SD_CMD_STOP) = 0
    ProcedureReturn 0
  EndIf
  If rock_sd_r1ok() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn rock_sd_waitBusy(500000)
EndProcedure

Procedure.i rock_sd_cardData(command.i, lba.i, count.i, *buffer)
  Protected timeoutUs.i = 1000000
  Protected start.i
  Protected now.i
  Protected attempt.i
  Protected status.i
  Protected words.i
  Protected word.i
  Protected byteIndex.i
  Protected offset.i
  Protected argument.i
  Protected flags.i
  Protected totalBytes.i
  Protected writing.i
  If count <= 0 Or count > #ROCK_SDMMC_MAX_BLOCKS Or lba < 0 Or lba > rock_sd_blocks-count Or *buffer = 0
    rock_sd_error = #ROCK_SD_ERR_BOUNDS : ProcedureReturn 0
  EndIf
  totalBytes = count * #ROCK_SDMMC_BLOCK
  writing = 0
  If command = 24 : writing = 1 : EndIf
  If command = 25 : writing = 1 : EndIf
  If rock_sd_highCapacity <> 0
    argument = lba
  Else
    If lba > $007FFFFF : rock_sd_error = #ROCK_SD_ERR_BOUNDS : ProcedureReturn 0 : EndIf
    argument = lba * #ROCK_SDMMC_BLOCK
  EndIf

  rock_sd_writeReg(#ROCK_SDMMC_BLKSIZ, #ROCK_SDMMC_BLOCK)
  rock_sd_writeReg(#ROCK_SDMMC_BYTCNT, totalBytes)
  ; The reference FIFO-mode path resets the FIFO once for the whole request,
  ; before issuing its data command. It does not reset between its blocks.
  If rock_sd_resetFifo() = 0
    rock_sd_error = #ROCK_SD_ERR_CONTROLLER : ProcedureReturn 0
  EndIf
  flags = #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC | #ROCK_SD_CMD_DATA | #ROCK_SD_CMD_WAIT_PREV
  If writing <> 0 : flags = flags | #ROCK_SD_CMD_WRITE : EndIf
  If rock_sd_command(command, argument, flags) = 0
    rock_sd_error = #ROCK_SD_ERR_COMMAND : ProcedureReturn 0
  EndIf
  If rock_sd_r1ok() = 0 : rock_sd_error = #ROCK_SD_ERR_CARD : ProcedureReturn 0 : EndIf

  start = RockTimerTicks()
  byteIndex = 0
  For attempt = 0 To 8000000
    status = rock_sd_readReg(#ROCK_SDMMC_RINTSTS)
    rock_sd_lastIntStatus = status
    rock_sd_lastControllerStatus = rock_sd_readReg(#ROCK_SDMMC_STATUS)
    If (status & (#ROCK_SD_INT_DATA_ERRORS | #ROCK_SD_INT_CMD_ERRORS)) <> 0
      If count > 1 : rock_sd_stopTransfer() : EndIf
      ProcedureReturn rock_sd_dataFail(#ROCK_SD_ERR_DATA)
    EndIf
    status = rock_sd_readReg(#ROCK_SDMMC_STATUS)
    words = (status >> 17) & $1FFF
    If writing = 0
      While words > 0 And byteIndex < totalBytes
        word = rock_sd_readReg(#ROCK_SDMMC_DATA)
        For offset = 0 To 3
          If byteIndex < totalBytes
            PokeA(*buffer + byteIndex, (word >> (offset*8)) & $FF)
            byteIndex = byteIndex + 1
          EndIf
        Next
        words = words - 1
      Wend
    Else
      While words < #ROCK_SDMMC_FIFO_DEPTH And byteIndex < totalBytes
        word = 0
        For offset = 0 To 3
          If byteIndex < totalBytes
            word = word | ((PeekA(*buffer + byteIndex) & $FF) << (offset*8))
            byteIndex = byteIndex + 1
          EndIf
        Next
        rock_sd_writeReg(#ROCK_SDMMC_DATA, word)
        words = words + 1
      Wend
    EndIf
    status = rock_sd_readReg(#ROCK_SDMMC_RINTSTS)
    rock_sd_lastIntStatus = status
    If (status & #ROCK_SD_INT_DATA_OVER) <> 0
      ; DATA_OVER says the card-side transfer completed. It does not say the
      ; receive FIFO is empty. Linux dw_mci_read_data_pio(dto=true) continues
      ; while STATUS reports FIFO words; do the same until all 512 bytes have
      ; actually been pulled. Build 93 proved the old early return left sector
      ; N in the FIFO and made request N+1 receive it.
      If writing = 0 And byteIndex < totalBytes
        Continue
      EndIf
      rock_sd_writeReg(#ROCK_SDMMC_RINTSTS, #ROCK_SD_INT_DATA_OVER)
      If byteIndex <> totalBytes
        If count > 1 : rock_sd_stopTransfer() : EndIf
        ProcedureReturn rock_sd_dataFail(#ROCK_SD_ERR_DATA)
      EndIf
      If count > 1
        If rock_sd_stopTransfer() = 0
          ProcedureReturn rock_sd_dataFail(#ROCK_SD_ERR_COMMAND)
        EndIf
      EndIf
      ProcedureReturn 1
    EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= (rock_timer_frequency/1000000)*timeoutUs : Break : EndIf
  Next
  If count > 1 : rock_sd_stopTransfer() : EndIf
  ProcedureReturn rock_sd_dataFail(#ROCK_SD_ERR_TIMEOUT)
EndProcedure

Procedure.i rock_sd_status()
  If rock_sd_command(13, rock_sd_rca << 16, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn rock_sd_response0
EndProcedure

Procedure.i RockSdInit()
  Protected attempt.i
  Protected ocr.i
  Protected csize.i
  Protected mult.i
  Protected readLen.i
  Protected bytes.i
  Protected gpll.i
  Protected divider.i
  Protected parentRate.i
  Protected value.i

  If rock_sd_ready <> 0 : ProcedureReturn 1 : EndIf
  rock_sd_error = #ROCK_SD_ERR_OK
  rock_sd_blocks = 0
  rock_sd_rca = 0
  rock_sd_highCapacity = 0
  If rock_timer_frequency <> #ROCK_TIMER_FREQUENCY_EXPECTED
    rock_sd_setError(#ROCK_SD_ERR_TIMER) : ProcedureReturn 0
  EndIf

  ; The Rock Pi DTS selects GPIO4B0..5 function 1 for SDMMC data0..3, clock,
  ; command. Set fields with GRF hiword-mask semantics; set DAT/CMD pull-ups
  ; and leave clock unpulled, matching the shipped board pinctrl groups.
  PokeL(#ROCK_SD_GRF+$E024, $0FFF0555)
  PokeL(#ROCK_SD_GRF+$E064, $0FFF0455)
  ; The same DTS asks GPIO4B pins 8-11 and 13 for 8mA and pin12 (CLK) for
  ; 12mA. Linux RK3399 pinctrl maps these auto-range strengths to 3-bit codes
  ; 2 and 4, at GRF_DRV offsets E130/E134; pin13's 3-bit field straddles them.
  ; Spell $FFFF4492 as its signed 32-bit equivalent so PokeL receives the
  ; exact hiword-mask bit pattern without an out-of-range .l literal.
  PokeL(#ROCK_SD_GRF+$E130, $4492 - $10000)
  PokeL(#ROCK_SD_GRF+$E134, $00030001)
  ; Follow the RK3399 clock driver for identification: select the 24 MHz
  ; parent (selector 5), divide by 30, then account for the wrapper's fixed
  ; divide-by-two. This presents exactly 400 kHz to the DW-MSHC and permits
  ; CLKDIV=0 instead of synthesizing a second, guessed divider in the host.
  divider = 30
  PokeL(#ROCK_SD_CRU+$140, ($0700 | $007F) << 16 | ($0500 | (divider-1)))
  rock_sd_ciuHz = 24000000 / divider / 2
  rock_sd_clockDiv = 0
  If rock_sd_ciuHz <= 0 : rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0 : EndIf

  ; Program the parent HCLK before opening its gates. DTS assigns 200MHz;
  ; choose the nearest non-overspeed GPLL-derived rate on this silicon.
  parentRate = RockCruPllRate($80, 1, #ROCK_SD_ERR_CLOCK)
  If parentRate <= 0 : rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0 : EndIf
  value = (parentRate + 199999999) / 200000000
  If value < 1 Or value > 32 : rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0 : EndIf
  PokeL(#ROCK_SD_CRU+$134, $9F000000 | $00008000 | ((value-1) << 8))
  ; Open HCLK_SD parent, SDMMC bus/NOC and CIU only after their parents and
  ; dividers are programmed. The PMU idle-release handshake observes these
  ; bus clocks, so all gates precede it; controller MMIO still waits for power.
  PokeL(#ROCK_SD_CRU+$330, $20000000) ; enable HCLK_SD bank12 bit13
  PokeL(#ROCK_SD_CRU+$384, $03000000) ; enable HCLK_SDMMC and NOC bits8-9
  PokeL(#ROCK_SD_CRU+$318, $00020000) ; enable SCLK_SDMMC bank6 bit1
  ; RK3399_PD_SD is domain index 27; pm_domains maps it to PWRDN bit30 and
  ; BUS_IDLE_REQ/ACK bit28. Open clocks before releasing the idle request.
  If RockPmuPowerOn(30, #ROCK_SD_ERR_POWER) = 0 Or RockPmuIdleRelease(28, #ROCK_SD_ERR_POWER+1) = 0
    rock_sd_setError(#ROCK_SD_ERR_POWER) : ProcedureReturn 0
  EndIf
  ; Controller registers become accessible only after HCLK and CIU are enabled.
  rock_sd_writeReg(#ROCK_SDMMC_CLKSRC, 0)
  PokeL(#ROCK_SD_CRU+$41C, $04000400)
  If RockTimerWaitUs(10) = 0 : rock_sd_setError(#ROCK_SD_ERR_RESET) : ProcedureReturn 0 : EndIf
  PokeL(#ROCK_SD_CRU+$41C, $04000000)
  rock_sd_writeReg(#ROCK_SDMMC_PWREN, 1)
  rock_sd_writeReg(#ROCK_SDMMC_CTRL, 7)
  If rock_sd_waitReg(#ROCK_SDMMC_CTRL, 7, 0, 10000) = 0
    rock_sd_setError(#ROCK_SD_ERR_RESET) : ProcedureReturn 0
  EndIf
  rock_sd_writeReg(#ROCK_SDMMC_TMOUT, $FFFFFFFF)
  rock_sd_writeReg(#ROCK_SDMMC_INTSTS, $FFFFFFFF)
  rock_sd_writeReg(#ROCK_SDMMC_FIFOTH, ($0F << 16) | $0E)
  rock_sd_writeReg(#ROCK_SDMMC_CTYPE, 0) ; SD one-bit mode, never claim 4-bit
  If rock_sd_setClock(0) = 0 : rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0 : EndIf
  ; Match the RK3399 DW-MSHC phase contract: drive defaults to 90 degrees
  ; (phase value 1 in the two-bit field); sample defaults to 0. Linux binds
  ; these to CRU SDMMC_CON0/1 at +0x580/+0x584, with phase shift 1 and an
  ; 11-bit write mask, so the hiword-update words are 0x0FFE0002/0x0FFE0000.
  PokeL(#ROCK_SD_CRU+$580, $0FFE0002)
  PokeL(#ROCK_SD_CRU+$584, $0FFE0000)
  If (PeekL(#ROCK_SD_CRU+$580) & $FFE) <> 2 Or (PeekL(#ROCK_SD_CRU+$584) & $FFE) <> 0
    rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0
  EndIf
  If RockTimerWaitUs(1000) = 0 : rock_sd_setError(#ROCK_SD_ERR_TIMER) : ProcedureReturn 0 : EndIf

  If rock_sd_command(0, 0, 0) = 0
    rock_sd_setError(#ROCK_SD_ERR_COMMAND) : ProcedureReturn 0
  EndIf
  ; CMD8 identifies SD 2.x while allowing legacy cards to time out. This
  ; implementation supports SDHC/SDXC (CCS); SDSC remains byte-addressed.
  If rock_sd_command(8, $000001AA, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC) <> 0
    If (rock_sd_response0 & $FFF) <> $1AA : rock_sd_setError(#ROCK_SD_ERR_CARD) : ProcedureReturn 0 : EndIf
  EndIf
  ocr = 0
  For attempt = 0 To 100
    If rock_sd_appCommand(#ROCK_SD_OCR_VOLTAGE | #ROCK_SD_OCR_HC, 41, #ROCK_SD_CMD_RESP) = 0
      rock_sd_setError(#ROCK_SD_ERR_COMMAND) : ProcedureReturn 0
    EndIf
    ocr = rock_sd_response0
    If (ocr & #ROCK_SD_OCR_READY) <> 0 : Break : EndIf
    If RockTimerWaitUs(10000) = 0 : rock_sd_setError(#ROCK_SD_ERR_TIMER) : ProcedureReturn 0 : EndIf
  Next
  If (ocr & #ROCK_SD_OCR_READY) = 0 : rock_sd_setError(#ROCK_SD_ERR_TIMEOUT) : ProcedureReturn 0 : EndIf
  If (ocr & #ROCK_SD_OCR_HC) <> 0 : rock_sd_highCapacity = 1 : EndIf

  ; CMD2 all-CID, CMD3 assign RCA, CMD9 read CSD, CMD7 select card.
  If rock_sd_command(2, 0, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_LONG | #ROCK_SD_CMD_CRC) = 0
    rock_sd_setError(#ROCK_SD_ERR_COMMAND) : ProcedureReturn 0
  EndIf
  If rock_sd_command(3, 0, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC) = 0
    rock_sd_setError(#ROCK_SD_ERR_COMMAND) : ProcedureReturn 0
  EndIf
  If (rock_sd_response0 & $E000) <> 0 : rock_sd_setError(#ROCK_SD_ERR_CARD) : ProcedureReturn 0 : EndIf
  rock_sd_rca = (rock_sd_response0 >> 16) & $FFFF
  If rock_sd_rca = 0 : rock_sd_setError(#ROCK_SD_ERR_CARD) : ProcedureReturn 0 : EndIf
  If rock_sd_command(9, rock_sd_rca << 16, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_LONG | #ROCK_SD_CMD_CRC) = 0
    rock_sd_setError(#ROCK_SD_ERR_COMMAND) : ProcedureReturn 0
  EndIf
  If rock_sd_highCapacity <> 0
    csize = ((rock_sd_response2 & $3F) << 16) | ((rock_sd_response1 >> 16) & $FFFF)
    rock_sd_blocks = (csize + 1) * 1024
  Else
    csize = ((rock_sd_response2 & $3FF) << 2) | ((rock_sd_response1 >> 30) & 3)
    mult = (rock_sd_response1 >> 15) & 7
    readLen = (rock_sd_response2 >> 16) & 15
    bytes = (csize + 1) << (mult + 2 + readLen)
    rock_sd_blocks = bytes / #ROCK_SDMMC_BLOCK
  EndIf
  If rock_sd_blocks <= 0 : rock_sd_setError(#ROCK_SD_ERR_CAPACITY) : ProcedureReturn 0 : EndIf
  If rock_sd_command(7, rock_sd_rca << 16, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC | #ROCK_SD_CMD_WAIT_PREV) = 0
    rock_sd_setError(#ROCK_SD_ERR_COMMAND) : ProcedureReturn 0
  EndIf
  If rock_sd_r1ok() = 0 Or rock_sd_waitBusy(500000) = 0
    rock_sd_setError(#ROCK_SD_ERR_BUSY) : ProcedureReturn 0
  EndIf
  If rock_sd_highCapacity = 0
    If rock_sd_command(16, #ROCK_SDMMC_BLOCK, #ROCK_SD_CMD_RESP | #ROCK_SD_CMD_CRC) = 0
      rock_sd_setError(#ROCK_SD_ERR_COMMAND) : ProcedureReturn 0
    EndIf
    If rock_sd_r1ok() = 0 : rock_sd_setError(#ROCK_SD_ERR_CARD) : ProcedureReturn 0 : EndIf
  EndIf

  ; Move to 25 MHz through the same RK3399 clock path: GPLL divided to a
  ; 50 MHz wrapper input, then the wrapper's fixed divide-by-two. Disable the
  ; card clock while changing its parent/divider and keep DW CLKDIV bypassed.
  gpll = RockCruPllRate($80, 1, #ROCK_SD_ERR_CLOCK)
  If gpll <= 0 : rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0 : EndIf
  divider = (gpll + 49999999) / 50000000
  If divider < 1 Or divider > 128 : rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0 : EndIf
  rock_sd_writeReg(#ROCK_SDMMC_CLKENA, 0)
  If rock_sd_clockUpdate() = 0 : rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0 : EndIf
  PokeL(#ROCK_SD_CRU+$140, ($0700 | $007F) << 16 | ($0100 | (divider-1)))
  rock_sd_ciuHz = gpll / divider / 2
  rock_sd_clockDiv = 0
  If rock_sd_setClock(rock_sd_clockDiv) = 0
    rock_sd_setError(#ROCK_SD_ERR_CLOCK) : ProcedureReturn 0
  EndIf
  ; CLKDIV=0 is bypass; rock_sd_ciuHz already includes RK3399's fixed /2.
  If rock_sd_clockDiv > 0
    rock_sd_cardHz = rock_sd_ciuHz / (2 * rock_sd_clockDiv)
  Else
    rock_sd_cardHz = rock_sd_ciuHz
  EndIf
  rock_sd_error = #ROCK_SD_ERR_OK
  rock_sd_ready = 1
  ProcedureReturn 1
EndProcedure

Procedure.i RockSdBlockCount()
  If rock_sd_ready = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn rock_sd_blocks
EndProcedure

Procedure.i RockSdReadBlocks(lba.i, count.i, *buffer)
  Protected block.i
  Protected run.i
  Protected command.i
  If RockSdInit() = 0 : ProcedureReturn 0 : EndIf
  If count <= 0 Or *buffer = 0 Or lba < 0 Or lba > rock_sd_blocks-count
    rock_sd_error = #ROCK_SD_ERR_BOUNDS : ProcedureReturn 0
  EndIf
  block = 0
  While block < count
    run = count - block
    If run > #ROCK_SDMMC_MAX_BLOCKS : run = #ROCK_SDMMC_MAX_BLOCKS : EndIf
    command = 17
    If run > 1 : command = 18 : EndIf
    If rock_sd_cardData(command, lba+block, run, *buffer+block*#ROCK_SDMMC_BLOCK) = 0 : ProcedureReturn 0 : EndIf
    block = block + run
  Wend
  rock_sd_error = #ROCK_SD_ERR_OK
  ProcedureReturn 1
EndProcedure

Procedure.i RockSdWriteBlocks(lba.i, count.i, *buffer)
  Protected block.i
  Protected run.i
  Protected command.i
  If RockSdInit() = 0 : ProcedureReturn 0 : EndIf
  If count <= 0 Or *buffer = 0 Or lba < 0 Or lba > rock_sd_blocks-count
    rock_sd_error = #ROCK_SD_ERR_BOUNDS : ProcedureReturn 0
  EndIf
  block = 0
  While block < count
    run = count - block
    If run > #ROCK_SDMMC_MAX_BLOCKS : run = #ROCK_SDMMC_MAX_BLOCKS : EndIf
    command = 24
    If run > 1 : command = 25 : EndIf
    If rock_sd_cardData(command, lba+block, run, *buffer+block*#ROCK_SDMMC_BLOCK) = 0 : ProcedureReturn 0 : EndIf
    If RockSdFlush() = 0 : ProcedureReturn 0 : EndIf
    block = block + run
  Wend
  rock_sd_error = #ROCK_SD_ERR_OK
  ProcedureReturn 1
EndProcedure

Procedure.i RockSdFlush()
  Protected start.i
  Protected now.i
  Protected attempt.i
  Protected status.i
  If rock_sd_ready = 0 : ProcedureReturn 0 : EndIf
  start = RockTimerTicks()
  For attempt = 0 To 4000000
    status = rock_sd_status()
    If status = 0 : rock_sd_error = #ROCK_SD_ERR_BUSY : ProcedureReturn 0 : EndIf
    If (status & #ROCK_SD_R1_ERRORS) <> 0 : rock_sd_error = #ROCK_SD_ERR_CARD : ProcedureReturn 0 : EndIf
    If (status & #ROCK_SD_R1_READY_FOR_DATA) <> 0 And (status & #ROCK_SD_R1_STATE_MASK) = #ROCK_SD_R1_STATE_TRAN
      rock_sd_error = #ROCK_SD_ERR_OK : ProcedureReturn 1
    EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= (rock_timer_frequency/1000000)*500000 : Break : EndIf
  Next
  rock_sd_error = #ROCK_SD_ERR_BUSY
  ProcedureReturn 0
EndProcedure

Procedure.i RockSdErrorText()
  Select rock_sd_error
    Case #ROCK_SD_ERR_TIMER : ProcedureReturn ?rock_sd_err_timer
    Case #ROCK_SD_ERR_POWER : ProcedureReturn ?rock_sd_err_power
    Case #ROCK_SD_ERR_CLOCK : ProcedureReturn ?rock_sd_err_clock
    Case #ROCK_SD_ERR_RESET : ProcedureReturn ?rock_sd_err_reset
    Case #ROCK_SD_ERR_CONTROLLER : ProcedureReturn ?rock_sd_err_controller
    Case #ROCK_SD_ERR_COMMAND : ProcedureReturn ?rock_sd_err_command
    Case #ROCK_SD_ERR_TIMEOUT : ProcedureReturn ?rock_sd_err_timeout
    Case #ROCK_SD_ERR_CARD : ProcedureReturn ?rock_sd_err_card
    Case #ROCK_SD_ERR_CAPACITY : ProcedureReturn ?rock_sd_err_capacity
    Case #ROCK_SD_ERR_BOUNDS : ProcedureReturn ?rock_sd_err_bounds
    Case #ROCK_SD_ERR_BUFFER : ProcedureReturn ?rock_sd_err_buffer
    Case #ROCK_SD_ERR_DATA : ProcedureReturn ?rock_sd_err_data
    Case #ROCK_SD_ERR_BUSY : ProcedureReturn ?rock_sd_err_busy
    Case #ROCK_SD_ERR_UNSUPPORTED : ProcedureReturn ?rock_sd_err_unsupported
  EndSelect
  ProcedureReturn ?rock_sd_err_ok
EndProcedure

DataSection
rock_sd_err_ok:          Data.s "SD card ready"
rock_sd_err_timer:       Data.s "architectural timer unavailable"
rock_sd_err_power:       Data.s "SD domain power-on timeout"
rock_sd_err_clock:       Data.s "SD clock setup failed"
rock_sd_err_reset:       Data.s "SD controller reset timed out"
rock_sd_err_controller:  Data.s "SD controller unavailable"
rock_sd_err_command:     Data.s "SD command was not acknowledged"
rock_sd_err_timeout:     Data.s "SD operation timed out"
rock_sd_err_card:        Data.s "SD card protocol status error"
rock_sd_err_capacity:    Data.s "SD card capacity is invalid"
rock_sd_err_bounds:      Data.s "SD block range is out of bounds"
rock_sd_err_buffer:      Data.s "SD transfer buffer is invalid"
rock_sd_err_data:        Data.s "SD PIO data phase failed"
rock_sd_err_busy:        Data.s "SD card remained busy"
rock_sd_err_unsupported: Data.s "SD card operation unsupported"
EndDataSection
