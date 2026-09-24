; RK3399 Rock Pi 4C on-board eMMC, Arasan SDHCI 5.1 at FE330000.
; Bounded 512-byte sector backend for the shared filesystem. Writes remain
; disarmed until an explicit file operation arms and then disarms them.
; The eMMC controller is separate from the FE320000 removable SD controller.

#ROCK_EMMC_HOST = $FE330000
#ROCK_EMMC_ERROR_MASK = $FFFF8000
#ROCK_EMMC_ERR_OK = 0
#ROCK_EMMC_ERR_TIMER = 1
#ROCK_EMMC_ERR_POWER = 2
#ROCK_EMMC_ERR_HOST = 3
#ROCK_EMMC_ERR_CLOCK = 4
#ROCK_EMMC_ERR_RESET = 5
#ROCK_EMMC_ERR_COMMAND = 6
#ROCK_EMMC_ERR_TIMEOUT = 7
#ROCK_EMMC_ERR_CAPACITY = 8
#ROCK_EMMC_ERR_BOUNDS = 9
#ROCK_EMMC_ERR_BUFFER = 10
#ROCK_EMMC_ERR_DATA = 11
#ROCK_EMMC_ERR_WRITE_DISARMED = 12
#ROCK_EMMC_ERR_WRITE = 13
#ROCK_EMMC_ERR_PARTITION = 14

Global rock_emmc_ready.i
Global rock_emmc_blocks.i
Global rock_emmc_error.i
Global rock_emmc_lastCommand.i
Global rock_emmc_lastArgument.i
Global rock_emmc_lastInterrupt.i
Global rock_emmc_lastResponse.i
Global rock_emmc_ocr.i
Global rock_emmc_revision.i
Global rock_emmc_accessPartition.i
Global rock_emmc_writeEnabled.i
Global rock_emmc_clockHz.i
Global rock_emmc_fastFallback.i
Global Dim rock_emmc_ext_csd.a[511]
Global Dim rock_emmc_clock_probe_slow.a[511]
Global Dim rock_emmc_clock_probe_fast.a[511]

Procedure.i rock_emmc_wait8(offset.i, mask.i, wanted.i, timeoutUs.i)
  Protected start.i
  Protected now.i
  Protected attempt.i
  start=RockTimerTicks()
  For attempt=0 To 4000000
    If (PeekA(#ROCK_EMMC_HOST+offset) & mask)=wanted
      ProcedureReturn 1
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start >= 24*timeoutUs
      Break
    EndIf
  Next
  rock_emmc_error=#ROCK_EMMC_ERR_TIMEOUT
  ProcedureReturn 0
EndProcedure

Procedure.i rock_emmc_waitPresent(mask.i, wanted.i, timeoutUs.i)
  Protected start.i
  Protected now.i
  Protected attempt.i
  start=RockTimerTicks()
  For attempt=0 To 4000000
    If (PeekL(#ROCK_EMMC_HOST+$24) & mask)=wanted
      ProcedureReturn 1
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start >= 24*timeoutUs
      Break
    EndIf
  Next
  rock_emmc_error=#ROCK_EMMC_ERR_TIMEOUT
  ProcedureReturn 0
EndProcedure

Procedure.i rock_emmc_command(index.i, argument.i, flags.i)
  Protected start.i
  Protected now.i
  Protected attempt.i
  Protected status.i
  rock_emmc_lastCommand=index
  rock_emmc_lastArgument=argument
  If rock_emmc_waitPresent(3,0,100000)=0
    ProcedureReturn 0
  EndIf
  PokeL(#ROCK_EMMC_HOST+$30,$FFFFFFFF)
  PokeL(#ROCK_EMMC_HOST+$08,argument)
  PokeL(#ROCK_EMMC_HOST+$0C,((index << 8) | flags) << 16)
  start=RockTimerTicks()
  For attempt=0 To 4000000
    status=PeekL(#ROCK_EMMC_HOST+$30) & $FFFFFFFF
    If (status & (1 | #ROCK_EMMC_ERROR_MASK))<>0
      Break
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start >= 2400000
      Break
    EndIf
  Next
  rock_emmc_lastInterrupt=status
  rock_emmc_lastResponse=PeekL(#ROCK_EMMC_HOST+$10) & $FFFFFFFF
  PokeL(#ROCK_EMMC_HOST+$30,status)
  If (status & 1)=0
    rock_emmc_error=#ROCK_EMMC_ERR_TIMEOUT
    ProcedureReturn 0
  EndIf
  If (status & #ROCK_EMMC_ERROR_MASK)<>0
    rock_emmc_error=#ROCK_EMMC_ERR_COMMAND
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i rock_emmc_readData(index.i, argument.i, *buffer)
  Protected start.i
  Protected now.i
  Protected attempt.i
  Protected status.i
  Protected word.i
  Protected value.i
  If *buffer=0
    rock_emmc_error=#ROCK_EMMC_ERR_BUFFER
    ProcedureReturn 0
  EndIf
  rock_emmc_lastCommand=index
  rock_emmc_lastArgument=argument
  If rock_emmc_waitPresent(3,0,100000)=0
    ProcedureReturn 0
  EndIf
  PokeL(#ROCK_EMMC_HOST+$30,$FFFFFFFF)
  PokeW(#ROCK_EMMC_HOST+$04,512)
  PokeW(#ROCK_EMMC_HOST+$06,1)
  PokeL(#ROCK_EMMC_HOST+$08,argument)
  ; R1 response with CRC/index checks, read data, one block, PIO.
  PokeL(#ROCK_EMMC_HOST+$0C,(((index << 8) | $3A) << 16) | $10)
  start=RockTimerTicks()
  For attempt=0 To 10000000
    status=PeekL(#ROCK_EMMC_HOST+$30) & $FFFFFFFF
    If (status & ($20 | #ROCK_EMMC_ERROR_MASK))<>0
      Break
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start >= 12000000
      Break
    EndIf
  Next
  rock_emmc_lastInterrupt=status
  rock_emmc_lastResponse=PeekL(#ROCK_EMMC_HOST+$10) & $FFFFFFFF
  If (status & $20)=0 Or (status & #ROCK_EMMC_ERROR_MASK)<>0
    rock_emmc_error=#ROCK_EMMC_ERR_DATA
    ProcedureReturn 0
  EndIf
  For word=0 To 127
    value=PeekL(#ROCK_EMMC_HOST+$20) & $FFFFFFFF
    PokeA(*buffer+word*4,value & 255)
    PokeA(*buffer+word*4+1,(value >> 8) & 255)
    PokeA(*buffer+word*4+2,(value >> 16) & 255)
    PokeA(*buffer+word*4+3,(value >> 24) & 255)
  Next
  start=RockTimerTicks()
  For attempt=0 To 10000000
    status=PeekL(#ROCK_EMMC_HOST+$30) & $FFFFFFFF
    If (status & (2 | #ROCK_EMMC_ERROR_MASK))<>0
      Break
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start >= 12000000
      Break
    EndIf
  Next
  rock_emmc_lastInterrupt=status
  PokeL(#ROCK_EMMC_HOST+$30,status)
  If (status & 2)=0 Or (status & #ROCK_EMMC_ERROR_MASK)<>0
    rock_emmc_error=#ROCK_EMMC_ERR_DATA
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i rock_emmc_waitReady()
  Protected attempt.i
  For attempt=0 To 2000
    PokeL($FF84800C,$76)
    If rock_emmc_command(13,$00010000,$1A)=0
      ProcedureReturn 0
    EndIf
    If (rock_emmc_lastResponse & $1F00)=$0900
      ProcedureReturn 1
    EndIf
    If RockTimerWaitUs(1000)=0
      rock_emmc_error=#ROCK_EMMC_ERR_TIMER
      ProcedureReturn 0
    EndIf
  Next
  rock_emmc_error=#ROCK_EMMC_ERR_TIMEOUT
  ProcedureReturn 0
EndProcedure

Procedure.i rock_emmc_writeData(lba.i,*buffer)
  Protected start.i
  Protected now.i
  Protected attempt.i
  Protected status.i
  Protected word.i
  Protected value.i
  If rock_emmc_waitPresent(3,0,100000)=0
    ProcedureReturn 0
  EndIf
  PokeL(#ROCK_EMMC_HOST+$30,$FFFFFFFF)
  PokeW(#ROCK_EMMC_HOST+$04,512)
  PokeW(#ROCK_EMMC_HOST+$06,1)
  PokeL(#ROCK_EMMC_HOST+$08,lba)
  PokeL(#ROCK_EMMC_HOST+$0C,(((24 << 8) | $3A) << 16))
  start=RockTimerTicks()
  For attempt=0 To 10000000
    status=PeekL(#ROCK_EMMC_HOST+$30) & $FFFFFFFF
    If (status & ($10 | #ROCK_EMMC_ERROR_MASK))<>0
      Break
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=12000000
      Break
    EndIf
  Next
  rock_emmc_lastInterrupt=status
  If (status & $10)=0 Or (status & #ROCK_EMMC_ERROR_MASK)<>0
    rock_emmc_error=#ROCK_EMMC_ERR_WRITE
    ProcedureReturn 0
  EndIf
  For word=0 To 127
    value=(PeekA(*buffer+word*4) & 255) | ((PeekA(*buffer+word*4+1) & 255) << 8) | ((PeekA(*buffer+word*4+2) & 255) << 16) | ((PeekA(*buffer+word*4+3) & 255) << 24)
    PokeL(#ROCK_EMMC_HOST+$20,value)
  Next
  start=RockTimerTicks()
  For attempt=0 To 40000000
    status=PeekL(#ROCK_EMMC_HOST+$30) & $FFFFFFFF
    If (status & (2 | #ROCK_EMMC_ERROR_MASK))<>0
      Break
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=48000000
      Break
    EndIf
  Next
  rock_emmc_lastInterrupt=status
  PokeL(#ROCK_EMMC_HOST+$30,status)
  If (status & 2)=0 Or (status & #ROCK_EMMC_ERROR_MASK)<>0
    rock_emmc_error=#ROCK_EMMC_ERR_WRITE
    ProcedureReturn 0
  EndIf
  ProcedureReturn rock_emmc_waitReady()
EndProcedure

; The board's 200 MHz SDHCI source uses the standard v3 divided clock:
; 250 -> 400 kHz for identification, 4 -> 25 MHz for normal transfers.
; Disable the card clock while changing the divider, wait for the internal
; clock to stabilize, then re-enable the card clock. The sequence was first
; checked by a returning read/write/readback payload on this board.
Procedure.i rock_emmc_setClockDivider(divider.i)
  Protected control.i
  If divider<>250 And divider<>4
    rock_emmc_error=#ROCK_EMMC_ERR_CLOCK
    ProcedureReturn 0
  EndIf
  If rock_emmc_waitPresent(3,0,100000)=0
    ProcedureReturn 0
  EndIf
  control=(divider << 8) | 1
  PokeW(#ROCK_EMMC_HOST+$2C,control)
  If rock_emmc_wait8($2C,2,2,10000)=0
    rock_emmc_error=#ROCK_EMMC_ERR_CLOCK
    ProcedureReturn 0
  EndIf
  PokeW(#ROCK_EMMC_HOST+$2C,control | 4)
  If ((PeekW(#ROCK_EMMC_HOST+$2C) & $FF05)<>((divider << 8) | 5))
    rock_emmc_error=#ROCK_EMMC_ERR_CLOCK
    ProcedureReturn 0
  EndIf
  rock_emmc_clockHz=100000000/divider
  ProcedureReturn 1
EndProcedure

Procedure.i rock_emmc_sameSector(*left,*right)
  Protected index.i
  For index=0 To 511
    If (PeekA(*left+index) & 255)<>(PeekA(*right+index) & 255)
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i rock_emmc_restoreSlowClock()
  ; A failed data transfer may leave CMD/DATA inhibit set. The reset clears
  ; only those lines and preserves the selected user partition and power.
  PokeA(#ROCK_EMMC_HOST+$2F,6)
  If rock_emmc_wait8($2F,6,0,10000)=0
    rock_emmc_error=#ROCK_EMMC_ERR_RESET
    ProcedureReturn 0
  EndIf
  ProcedureReturn rock_emmc_setClockDivider(250)
EndProcedure

Procedure.i RockEmmcInit()
  Protected attempt.i
  Protected ocr.i
  Protected fastOk.i
  If rock_emmc_ready<>0
    ProcedureReturn 1
  EndIf
  rock_emmc_error=#ROCK_EMMC_ERR_OK
  rock_emmc_blocks=0
  rock_emmc_writeEnabled=0
  rock_emmc_clockHz=0
  rock_emmc_fastFallback=0
  If RockTimerInit()=0
    rock_emmc_error=#ROCK_EMMC_ERR_TIMER
    ProcedureReturn 0
  EndIf
  If RockPmuPowerOn(26,0)=0 Or RockPmuIdleRelease(24,0)=0
    rock_emmc_error=#ROCK_EMMC_ERR_POWER
    ProcedureReturn 0
  EndIf
  RockCruGate(6,12,1)
  RockCruGate(6,14,1)
  RockCruGate(32,8,1)
  RockCruGate(32,9,1)
  RockCruGate(32,10,1)
  If (PeekW(#ROCK_EMMC_HOST+$FE) & $FFFF)<>$1002
    rock_emmc_error=#ROCK_EMMC_ERR_HOST
    ProcedureReturn 0
  EndIf
  PokeA(#ROCK_EMMC_HOST+$2F,6)
  If rock_emmc_wait8($2F,6,0,10000)=0
    rock_emmc_error=#ROCK_EMMC_ERR_RESET
    ProcedureReturn 0
  EndIf
  ; Keep the bootloader's PHY and parent-clock state. The observed SCLK_EMMC
  ; is 200 MHz; divide by 500 for eMMC identification at 400 kHz.
  PokeA(#ROCK_EMMC_HOST+$28,$C0)
  If (PeekA(#ROCK_EMMC_HOST+$29) & 1)=0
    PokeA(#ROCK_EMMC_HOST+$29,$0B)
  EndIf
  PokeW(#ROCK_EMMC_HOST+$2C,$FA01)
  If rock_emmc_wait8($2C,2,2,10000)=0
    rock_emmc_error=#ROCK_EMMC_ERR_CLOCK
    ProcedureReturn 0
  EndIf
  PokeW(#ROCK_EMMC_HOST+$2C,$FA05)
  rock_emmc_clockHz=400000
  PokeL(#ROCK_EMMC_HOST+$34,$08FF8033)
  PokeL(#ROCK_EMMC_HOST+$38,0)
  If rock_emmc_command(0,0,0)=0
    ProcedureReturn 0
  EndIf
  ocr=0
  For attempt=0 To 100
    PokeL($FF84800C,$76)
    If rock_emmc_command(1,$40FF8080,2)=0
      ProcedureReturn 0
    EndIf
    ocr=rock_emmc_lastResponse
    If (ocr & $80000000)<>0
      Break
    EndIf
    If RockTimerWaitUs(10000)=0
      rock_emmc_error=#ROCK_EMMC_ERR_TIMER
      ProcedureReturn 0
    EndIf
  Next
  rock_emmc_ocr=ocr
  If (ocr & $C0000000)<>$C0000000
    rock_emmc_error=#ROCK_EMMC_ERR_CAPACITY
    ProcedureReturn 0
  EndIf
  If rock_emmc_command(2,0,9)=0
    ProcedureReturn 0
  EndIf
  If rock_emmc_command(3,$00010000,$1A)=0
    ProcedureReturn 0
  EndIf
  If rock_emmc_command(9,$00010000,9)=0
    ProcedureReturn 0
  EndIf
  If rock_emmc_command(7,$00010000,$1B)=0
    ProcedureReturn 0
  EndIf
  If rock_emmc_readData(8,0,@rock_emmc_ext_csd[0])=0
    ProcedureReturn 0
  EndIf
  rock_emmc_revision=PeekA(@rock_emmc_ext_csd[192]) & 255
  rock_emmc_accessPartition=PeekA(@rock_emmc_ext_csd[179]) & 7
  If rock_emmc_accessPartition<>0
    rock_emmc_error=#ROCK_EMMC_ERR_PARTITION
    ProcedureReturn 0
  EndIf
  rock_emmc_blocks=(PeekA(@rock_emmc_ext_csd[212]) & 255) | ((PeekA(@rock_emmc_ext_csd[213]) & 255)<<8) | ((PeekA(@rock_emmc_ext_csd[214]) & 255)<<16) | ((PeekA(@rock_emmc_ext_csd[215]) & 255)<<24)
  If rock_emmc_blocks<=0
    rock_emmc_error=#ROCK_EMMC_ERR_CAPACITY
    ProcedureReturn 0
  EndIf
  ; Compare the same user-area sector on both sides of the clock change.
  ; No fixed filesystem content is assumed, so this works on unformatted
  ; cards and board revisions with a different partition layout.
  If rock_emmc_readData(17,0,@rock_emmc_clock_probe_slow[0])=0
    ProcedureReturn 0
  EndIf
  If rock_emmc_setClockDivider(4)<>0
    If rock_emmc_readData(17,0,@rock_emmc_clock_probe_fast[0])<>0
      If rock_emmc_sameSector(@rock_emmc_clock_probe_slow[0],@rock_emmc_clock_probe_fast[0])<>0
        fastOk=1
      EndIf
    EndIf
  EndIf
  If fastOk=0
    rock_emmc_fastFallback=1
    If rock_emmc_restoreSlowClock()=0
      ProcedureReturn 0
    EndIf
    If rock_emmc_readData(17,0,@rock_emmc_clock_probe_fast[0])=0
      ProcedureReturn 0
    EndIf
    If rock_emmc_sameSector(@rock_emmc_clock_probe_slow[0],@rock_emmc_clock_probe_fast[0])=0
      rock_emmc_error=#ROCK_EMMC_ERR_DATA
      ProcedureReturn 0
    EndIf
  EndIf
  rock_emmc_error=#ROCK_EMMC_ERR_OK
  rock_emmc_ready=1
  ProcedureReturn 1
EndProcedure

Procedure.i RockEmmcBlockCount()
  ProcedureReturn rock_emmc_blocks
EndProcedure

Procedure.i RockEmmcReadBlocks(lba.i, count.i, *buffer)
  Protected block.i
  If rock_emmc_ready=0 Or *buffer=0
    rock_emmc_error=#ROCK_EMMC_ERR_BUFFER
    ProcedureReturn 0
  EndIf
  If lba<0 Or count<=0 Or count>rock_emmc_blocks Or lba>rock_emmc_blocks-count
    rock_emmc_error=#ROCK_EMMC_ERR_BOUNDS
    ProcedureReturn 0
  EndIf
  For block=0 To count-1
    PokeL($FF84800C,$76)
    If rock_emmc_readData(17,lba+block,*buffer+block*512)=0
      ProcedureReturn 0
    EndIf
  Next
  rock_emmc_error=#ROCK_EMMC_ERR_OK
  ProcedureReturn 1
EndProcedure

Procedure RockEmmcDisarmWrites()
  rock_emmc_writeEnabled=0
EndProcedure

Procedure.i RockEmmcArmWrites()
  rock_emmc_writeEnabled=0
  If rock_emmc_ready=0 Or rock_emmc_accessPartition<>0
    rock_emmc_error=#ROCK_EMMC_ERR_PARTITION
    ProcedureReturn 0
  EndIf
  ; Confirm the current hardware partition again because a returning
  ; payload may have changed eMMC's volatile access selector.
  If rock_emmc_readData(8,0,@rock_emmc_ext_csd[0])=0
    ProcedureReturn 0
  EndIf
  rock_emmc_accessPartition=PeekA(@rock_emmc_ext_csd[179]) & 7
  If rock_emmc_accessPartition<>0
    rock_emmc_error=#ROCK_EMMC_ERR_PARTITION
    ProcedureReturn 0
  EndIf
  rock_emmc_writeEnabled=1
  rock_emmc_error=#ROCK_EMMC_ERR_OK
  ProcedureReturn 1
EndProcedure

Procedure.i RockEmmcWriteBlocks(lba.i, count.i, *buffer)
  Protected block.i
  If rock_emmc_writeEnabled=0
    rock_emmc_error=#ROCK_EMMC_ERR_WRITE_DISARMED
    ProcedureReturn 0
  EndIf
  If rock_emmc_ready=0 Or rock_emmc_accessPartition<>0
    rock_emmc_error=#ROCK_EMMC_ERR_PARTITION
    ProcedureReturn 0
  EndIf
  If *buffer=0
    rock_emmc_error=#ROCK_EMMC_ERR_BUFFER
    ProcedureReturn 0
  EndIf
  If lba<0 Or count<=0 Or count>rock_emmc_blocks Or lba>rock_emmc_blocks-count
    rock_emmc_error=#ROCK_EMMC_ERR_BOUNDS
    ProcedureReturn 0
  EndIf
  For block=0 To count-1
    PokeL($FF84800C,$76)
    If rock_emmc_writeData(lba+block,*buffer+block*512)=0
      rock_emmc_writeEnabled=0
      ProcedureReturn 0
    EndIf
  Next
  rock_emmc_error=#ROCK_EMMC_ERR_OK
  ProcedureReturn 1
EndProcedure

Procedure.i RockEmmcFlush()
  If rock_emmc_ready=0
    ProcedureReturn 0
  EndIf
  ProcedureReturn rock_emmc_waitReady()
EndProcedure

Procedure.i RockEmmcErrorText()
  Select rock_emmc_error
    Case #ROCK_EMMC_ERR_TIMER : ProcedureReturn ?rock_emmc_err_timer
    Case #ROCK_EMMC_ERR_POWER : ProcedureReturn ?rock_emmc_err_power
    Case #ROCK_EMMC_ERR_HOST : ProcedureReturn ?rock_emmc_err_host
    Case #ROCK_EMMC_ERR_CLOCK : ProcedureReturn ?rock_emmc_err_clock
    Case #ROCK_EMMC_ERR_RESET : ProcedureReturn ?rock_emmc_err_reset
    Case #ROCK_EMMC_ERR_COMMAND : ProcedureReturn ?rock_emmc_err_command
    Case #ROCK_EMMC_ERR_TIMEOUT : ProcedureReturn ?rock_emmc_err_timeout
    Case #ROCK_EMMC_ERR_CAPACITY : ProcedureReturn ?rock_emmc_err_capacity
    Case #ROCK_EMMC_ERR_BOUNDS : ProcedureReturn ?rock_emmc_err_bounds
    Case #ROCK_EMMC_ERR_BUFFER : ProcedureReturn ?rock_emmc_err_buffer
    Case #ROCK_EMMC_ERR_DATA : ProcedureReturn ?rock_emmc_err_data
    Case #ROCK_EMMC_ERR_WRITE_DISARMED : ProcedureReturn ?rock_emmc_err_disarmed
    Case #ROCK_EMMC_ERR_WRITE : ProcedureReturn ?rock_emmc_err_write
    Case #ROCK_EMMC_ERR_PARTITION : ProcedureReturn ?rock_emmc_err_partition
  EndSelect
  ProcedureReturn ?rock_emmc_ok
EndProcedure

DataSection
rock_emmc_ok: Data.s "eMMC ready"
rock_emmc_err_timer: Data.s "eMMC timer unavailable"
rock_emmc_err_power: Data.s "eMMC power domain unavailable"
rock_emmc_err_host: Data.s "eMMC SDHCI host unavailable"
rock_emmc_err_clock: Data.s "eMMC clock unstable"
rock_emmc_err_reset: Data.s "eMMC reset timed out"
rock_emmc_err_command: Data.s "eMMC command rejected"
rock_emmc_err_timeout: Data.s "eMMC command timed out"
rock_emmc_err_capacity: Data.s "eMMC capacity unavailable"
rock_emmc_err_bounds: Data.s "eMMC sector range invalid"
rock_emmc_err_buffer: Data.s "eMMC buffer unavailable"
rock_emmc_err_data: Data.s "eMMC sector read failed"
rock_emmc_err_disarmed: Data.s "eMMC writes are disarmed"
rock_emmc_err_write: Data.s "eMMC sector write failed"
rock_emmc_err_partition: Data.s "eMMC user area not selected"
EndDataSection
