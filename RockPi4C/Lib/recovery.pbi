; FTDI recovery console for the original Rock Pi 4C direct SD handoff.
; Include after arch_timer.pbi and uart2.pbi. The board may enter this poll
; loop only after its DTB, timer and UART contracts validate. Once EL3 vectors
; are installed, a fatal exception uses its emergency stack to enter the same
; exact command parser. An untrusted handoff still parks without commands.
;
; Exact grammar includes the bounded storage/serial update commands in
; storage_proof.pbi, terminated by CR, LF or CRLF. There is no prefix execution,
; abbreviation or network transport.

#ROCK_RECOVERY_LINE_BYTES = 512
#ROCK_RECOVERY_POLL_BYTES = 8
#ROCK_RECOVERY_PUMP_BYTES = 64

Global Dim rock_recovery_line.a[#ROCK_RECOVERY_LINE_BYTES]
Global rock_recovery_length.i
Global rock_recovery_discard.i
Global rock_recovery_ready.i
Global rock_recovery_error.i
Global rock_recovery_hdmi_attempted.i
Global rock_recovery_fatal_mode.i
Global rock_recovery_payload_entry.i
Global rock_recovery_payload_sp.i
Global rock_recovery_payload_return.i
Global rock_recovery_payload_cache_address.i

ProcedureNaked.i RockRecoveryWarmReset()
  ASM
    ; Direct EL3 ownership has no PSCI monitor behind it. This RK3399 warm
    ; reset sequence has been used on the physical board: clear PMUGRF's
    ; reset request source, then issue the keyed CRU warm-reset request.
    movz x9, #0x0300
    movk x9, #0xFF32, lsl #16
    str wzr, [x9]
    movz x9, #0x0504
    movk x9, #0xFF76, lsl #16
    movz w10, #0xECA8
    dsb sy
    str w10, [x9]
    dsb sy
rock_reset_wait:
    wfe
    b rock_reset_wait
  ENDASM
EndProcedure

ProcedureNaked RockRecoveryFailStop()
  ASM
    msr daifset, #15
rock_recovery_fail_stop:
    wfe
    b rock_recovery_fail_stop
  ENDASM
EndProcedure

Procedure RockRecoveryHex64(value.i)
  Protected index.i
  Protected digit.i
  For index=0 To 15
    digit=(value >> (60-index*4)) & 15
    If digit<10
      RockUartByte(48+digit)
    Else
      RockUartByte(55+digit)
    EndIf
  Next
EndProcedure

Procedure RockRecoveryReset()
  Protected status.i
  ; Stop asynchronous entry before announcing reset. UART transmission and
  ; its timer-bounded TEMT drain do not depend on interrupts.
  ASM
    msr daifset, #15
  ENDASM
  RockUartLine("RESET: RK3399 CRU WARM RESET")
  ; A missing final stop bit is less harmful than stranding recovery. Drain
  ; failure is recorded by uart2.pbi but never prevents the reset request.
  RockUartDrain()
  status=RockRecoveryWarmReset()
  ; The reset routine normally does not return. If it does, fail-stop.
  rock_recovery_error=3
  If rock_uart_ready<>0
    RockUartText("RESET REQUEST RETURNED X0=")
    RockRecoveryHex64(status)
    RockUartByte(13)
    RockUartByte(10)
    RockUartDrain()
  EndIf
  RockRecoveryFailStop()
EndProcedure

Procedure.i RockRecoveryLineIsReboot()
  If rock_recovery_length<>6 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool((PeekA(@rock_recovery_line[0]) & 255)=114 And (PeekA(@rock_recovery_line[0]+1) & 255)=101 And (PeekA(@rock_recovery_line[0]+2) & 255)=98 And (PeekA(@rock_recovery_line[0]+3) & 255)=111 And (PeekA(@rock_recovery_line[0]+4) & 255)=111 And (PeekA(@rock_recovery_line[0]+5) & 255)=116)
EndProcedure

Procedure.i RockRecoveryLineIsHelp()
  If rock_recovery_length<>4 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool((PeekA(@rock_recovery_line[0]) & 255)=104 And (PeekA(@rock_recovery_line[0]+1) & 255)=101 And (PeekA(@rock_recovery_line[0]+2) & 255)=108 And (PeekA(@rock_recovery_line[0]+3) & 255)=112)
EndProcedure

Procedure.i RockRecoveryLineIsHdmi()
  If rock_recovery_length<>4 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool((PeekA(@rock_recovery_line[0]) & 255)=104 And (PeekA(@rock_recovery_line[0]+1) & 255)=100 And (PeekA(@rock_recovery_line[0]+2) & 255)=109 And (PeekA(@rock_recovery_line[0]+3) & 255)=105)
EndProcedure

Procedure.i RockRecoveryLineIsGpuInfo()
  If rock_recovery_length<>7 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool((PeekA(@rock_recovery_line[0]) & 255)=103 And (PeekA(@rock_recovery_line[0]+1) & 255)=112 And (PeekA(@rock_recovery_line[0]+2) & 255)=117 And (PeekA(@rock_recovery_line[0]+3) & 255)=105 And (PeekA(@rock_recovery_line[0]+4) & 255)=110 And (PeekA(@rock_recovery_line[0]+5) & 255)=102 And (PeekA(@rock_recovery_line[0]+6) & 255)=111)
EndProcedure

Procedure.i RockRecoveryLineIsFontAtlas()
  If rock_recovery_length<>9 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool((PeekA(@rock_recovery_line[0]) & 255)=102 And (PeekA(@rock_recovery_line[1]) & 255)=111 And (PeekA(@rock_recovery_line[2]) & 255)=110 And (PeekA(@rock_recovery_line[3]) & 255)=116 And (PeekA(@rock_recovery_line[4]) & 255)=97 And (PeekA(@rock_recovery_line[5]) & 255)=116 And (PeekA(@rock_recovery_line[6]) & 255)=108 And (PeekA(@rock_recovery_line[7]) & 255)=97 And (PeekA(@rock_recovery_line[8]) & 255)=115)
EndProcedure

Procedure.i RockRecoveryLineIsPayload()
  If rock_recovery_length<7 : ProcedureReturn 0 : EndIf
  If (PeekA(@rock_recovery_line[0]) & 255)<>112 Or (PeekA(@rock_recovery_line[0]+1) & 255)<>97 Or (PeekA(@rock_recovery_line[0]+2) & 255)<>121 Or (PeekA(@rock_recovery_line[0]+3) & 255)<>108 Or (PeekA(@rock_recovery_line[0]+4) & 255)<>111 Or (PeekA(@rock_recovery_line[0]+5) & 255)<>97 Or (PeekA(@rock_recovery_line[0]+6) & 255)<>100
    ProcedureReturn 0
  EndIf
  If rock_recovery_length=7 : ProcedureReturn 1 : EndIf
  ProcedureReturn Bool((PeekA(@rock_recovery_line[0]+7) & 255)=32 Or (PeekA(@rock_recovery_line[0]+7) & 255)=9)
EndProcedure

Procedure RockRecoveryPayloadDataLine()
  ASM
    adrp x9, global_rock_recovery_payload_cache_address
    add x9, x9, #:lo12:global_rock_recovery_payload_cache_address
    ldr x9, [x9]
    dc civac, x9
  ENDASM
EndProcedure

Procedure RockRecoveryPayloadInstructionLine()
  ASM
    adrp x9, global_rock_recovery_payload_cache_address
    add x9, x9, #:lo12:global_rock_recovery_payload_cache_address
    ldr x9, [x9]
    ic ivau, x9
  ENDASM
EndProcedure

; Make the received bytes visible as A64 instructions. Both RK3399 CPU
; clusters have 64-byte cache lines. Clean and invalidate the D-cache range
; first, order that completion, then invalidate the matching I-cache range.
Procedure.i RockRecoveryPayloadCache(length.i)
  Protected first.i
  Protected last.i
  Protected address.i
  If length<=0 Or length>#ROCK_STORAGE_STAGE_BYTES : ProcedureReturn 0 : EndIf
  first=(@rock_storage_stage[0] >> 6) << 6
  last=@rock_storage_stage[0]+length-1
  address=first
  While address<=last
    rock_recovery_payload_cache_address=address
    RockRecoveryPayloadDataLine()
    address=address+64
  Wend
  ASM
    dsb sy
  ENDASM
  address=first
  While address<=last
    rock_recovery_payload_cache_address=address
    RockRecoveryPayloadInstructionLine()
    address=address+64
  Wend
  ASM
    dsb sy
    isb
  ENDASM
  ProcedureReturn 1
EndProcedure

ProcedureNaked.i RockRecoveryPayloadVbar()
  ASM
    mrs x0, vbar_el3
    ret
  ENDASM
EndProcedure

; The payload may replace SP, every caller-saved register, and VBAR_EL3.
; Exchange only through monitor-owned globals until the monitor SP is back.
Procedure RockRecoveryPayloadCall()
  ASM
    mov x11, sp
    adrp x10, global_rock_recovery_payload_sp
    add x10, x10, #:lo12:global_rock_recovery_payload_sp
    str x11, [x10]
    adrp x9, global_rock_recovery_payload_entry
    add x9, x9, #:lo12:global_rock_recovery_payload_entry
    ldr x9, [x9]
    movz x0, #0
    movz x1, #0
    movz x2, #0
    movz x3, #0
    movz x4, #0
    movz x5, #0
    movz x6, #0
    movz x7, #0
    blr x9
    msr daifset, #15
    adrp x10, global_rock_recovery_payload_return
    add x10, x10, #:lo12:global_rock_recovery_payload_return
    str x0, [x10]
    adrp x10, global_rock_recovery_payload_sp
    add x10, x10, #:lo12:global_rock_recovery_payload_sp
    ldr x11, [x10]
    mov sp, x11
    bl rockexceptioninstallraw
  ENDASM
EndProcedure

Procedure RockRecoveryPayload()
  Protected position.i=7
  Protected length.i
  Protected checksum.i
  Protected armed.i
  If rock_storage_parseHexToken(@rock_recovery_line[0],rock_recovery_length,@position,@length)=0 Or rock_storage_parseHexToken(@rock_recovery_line[0],rock_recovery_length,@position,@checksum)=0 Or rock_storage_onlySpace(@rock_recovery_line[0],rock_recovery_length,position)=0
    RockUartLine("USAGE: payload <length-hex> <crc32-hex>")
    ProcedureReturn
  EndIf
  If length<4 Or length>#ROCK_STORAGE_STAGE_BYTES Or (length & 3)<>0 Or ((@rock_storage_stage[0]) & 3)<>0
    RockUartLine("PAYLOAD REFUSED: INVALID STAGE EXTENT")
    ProcedureReturn
  EndIf
  If RockStorageReceive(length,checksum)=0
    ProcedureReturn
  EndIf
  If RockRecoveryPayloadCache(length)=0
    RockUartLine("PAYLOAD REFUSED: CACHE RANGE")
    ProcedureReturn
  EndIf
  armed=RockWatchdogArm()
  If armed=0
    RockUartLine("PAYLOAD REFUSED: DEADMAN NOT ARMED")
    RockWatchdogTelemetry()
    ProcedureReturn
  EndIf
  If rock_watchdog_armed=0 Or rock_watchdog_active=0
    RockUartLine("PAYLOAD REFUSED: DEADMAN VERIFY FAILED")
    RockWatchdogTelemetry()
    ProcedureReturn
  EndIf
  RockWatchdogPet()
  rock_recovery_payload_entry=@rock_storage_stage[0]
  rock_recovery_payload_return=0
  RockUartText("PAYLOAD STAGE ") : RockRecoveryHex64(rock_recovery_payload_entry)
  RockUartText(" BYTES ") : RockStorageHex8(length)
  RockUartText(" CRC ") : RockStorageHex8(checksum) : RockUartLine("")
  RockUartLine("PAYLOAD ENTER; DEADMAN ARMED")
  If RockUartDrain()=0
    RockUartLine("PAYLOAD REFUSED: UART DRAIN FAILED")
    ProcedureReturn
  EndIf
  RockRecoveryPayloadCall()
  If rock_exception_vbar=0 Or (rock_exception_vbar & 2047)<>0 Or RockRecoveryPayloadVbar()<>rock_exception_vbar
    RockUartLine("PAYLOAD RETURN REFUSED: EL3 VECTORS NOT RESTORED")
    RockUartDrain()
    RockRecoveryFailStop()
  EndIf
  RockWatchdogPet()
  RockUartText("PAYLOAD RETURN X0=")
  RockRecoveryHex64(rock_recovery_payload_return)
  RockUartLine("")
EndProcedure

Procedure RockRecoveryHdmi()
  ; HDMI changes several shared clock, route and PHY states synchronously.
  ; Until the facade proves an idempotent rollback, permit one attempt only;
  ; after either success or failure, reboot is the recovery path. The
  ; DesignWare watchdog must be running before any display register is
  ; touched, so a stalled clock/PHY transaction resets back to recovery.
  Protected ready.i
  If rock_recovery_hdmi_attempted<>0
    RockUartLine("HDMI ALREADY ATTEMPTED; REBOOT TO RETRY")
    ProcedureReturn
  EndIf
  If RockWatchdogArm()=0
    RockUartLine("HDMI REFUSED: DEADMAN NOT ARMED")
    RockWatchdogTelemetry()
    ProcedureReturn
  EndIf
  RockWatchdogPet()
  rock_recovery_hdmi_attempted=1
  RockUartLine("HDMI INIT BEGIN; DEADMAN ARMED; UART OUTPUT SYNCHRONOUS")
  ready=RockHdmiDisplayUp()
  If ready<>0
    RockUartLine("HDMI INIT READY")
  Else
    RockUartText("HDMI INIT FAILED ERROR=")
    RockRecoveryHex64(rock_display_error)
    RockUartText(" STAGE=")
    RockRecoveryHex64(rock_display_stage)
    RockUartByte(13)
    RockUartByte(10)
    RockUartLine("REBOOT BEFORE RETRY")
  EndIf
EndProcedure

Procedure RockRecoveryGpuInfo()
  Protected ready.i
  ; A read from an inaccessible clock domain can stall the CPU rather than
  ; return an error. Keep the already-proven hardware deadman active across
  ; the exact observation-only sequence proved by the returning G1 payload.
  If rock_watchdog_armed=0 Or rock_watchdog_active=0
    If RockWatchdogArm()=0
      RockUartLine("GPUINFO REFUSED: DEADMAN NOT ARMED")
      RockWatchdogTelemetry()
      ProcedureReturn
    EndIf
  EndIf
  RockWatchdogPet()
  RockUartLine("GPUINFO BEGIN; DEADMAN ARMED; READ ONLY")
  ready=RockGpuProbeReachability()
  RockWatchdogPet()

  RockUartText("GPUINFO INFRA ERR=") : RockStorageHex8(rock_gpu_error)
  RockUartText(" PWR=") : RockStorageHex8(rock_gpu_pmu_pwrdn_con)
  RockUartByte(47) : RockStorageHex8(rock_gpu_pmu_pwrdn_st)
  RockUartText(" IDLE=") : RockStorageHex8(rock_gpu_pmu_idle_req)
  RockUartByte(47) : RockStorageHex8(rock_gpu_pmu_idle_st)
  RockUartByte(47) : RockStorageHex8(rock_gpu_pmu_idle_ack)
  RockUartText(" CLK=") : RockStorageHex8(rock_gpu_clksel13)
  RockUartByte(47) : RockStorageHex8(rock_gpu_clkgate13)
  RockUartByte(47) : RockStorageHex8(rock_gpu_clkgate30)
  RockUartText(" RST=") : RockStorageHex8(rock_gpu_softrst18)
  RockUartByte(13) : RockUartByte(10)

  RockUartText("GPUINFO GPU READY=") : RockStorageHex8(ready)
  RockUartText(" ID=") : RockStorageHex8(rock_gpu_id)
  RockUartText(" MMU=") : RockStorageHex8(rock_gpu_mmu_features)
  RockUartText(" AS=") : RockStorageHex8(rock_gpu_as_present)
  RockUartText(" JS=") : RockStorageHex8(rock_gpu_js_present)
  RockUartText(" STATUS=") : RockStorageHex8(rock_gpu_status)
  RockUartText(" JM=") : RockStorageHex8(rock_gpu_job_int_js_state)
  RockUartText(" MMUINT=") : RockStorageHex8(rock_gpu_mmu_int_stat)
  RockUartByte(13) : RockUartByte(10)
EndProcedure

Procedure RockRecoveryFinishLine()
  If rock_recovery_discard<>0
    RockUartLine("ERR LINE DISCARDED")
  ElseIf rock_recovery_length=0
    ; Ignore the LF half of CRLF and empty lines.
  ElseIf RockRecoveryLineIsReboot()<>0
    rock_recovery_length=0
    RockRecoveryReset()
  ElseIf RockRecoveryLineIsHelp()<>0
    RockUartLine("COMMANDS: help hdmi payload gpuinfo fontatlas reboot storage sdmeta map read get write put writeproof trustupdate")
    RockUartLine("FILES: sd emmc fs ls [path] stat <path> cat <path> load <path> receive <len> <crc> save <path>")
    RockUartLine("       mkdir <path> rm <path> rmdir <path> mv <old> <new>; quoted paths work")
  ElseIf RockRecoveryLineIsPayload()<>0
    If rock_recovery_fatal_mode<>0
      RockUartLine("ERR PAYLOAD DISABLED IN FATAL RECOVERY")
    Else
      RockRecoveryPayload()
    EndIf
  ElseIf RockRecoveryLineIsHdmi()<>0
    If rock_recovery_fatal_mode<>0
      RockUartLine("ERR HDMI DISABLED IN FATAL RECOVERY")
    Else
      RockRecoveryHdmi()
    EndIf
  ElseIf RockRecoveryLineIsGpuInfo()<>0
    If rock_recovery_fatal_mode<>0
      RockUartLine("ERR GPUINFO DISABLED IN FATAL RECOVERY")
    Else
      RockRecoveryGpuInfo()
    EndIf
  ElseIf RockRecoveryLineIsFontAtlas()<>0
    If rock_recovery_fatal_mode<>0
      RockUartLine("ERR FONT ATLAS DISABLED IN FATAL RECOVERY")
    Else
      If RockWatchdogArm()=0
        RockUartLine("FONT ATLAS REFUSED: DEADMAN NOT ARMED")
      Else
        RockUartLine("FONT ATLAS BEGIN; DEADMAN ARMED")
        If RockFontPrepareAtlas()<>0
          RockUartText("FONT ATLAS READY BYTES=") : RockStorageHex8(rock_font_bytes)
          RockUartText(" GLYPHS=") : RockStorageHex8(rock_font_glyphs)
          RockUartText(" CRC=") : RockStorageHex8(rock_font_crc)
          RockUartByte(13) : RockUartByte(10)
        Else
          RockUartText("FONT ATLAS ERR=") : RockStorageHex8(rock_font_error)
          RockUartByte(13) : RockUartByte(10)
        EndIf
      EndIf
    EndIf
  Else
    ; Do not depend on Boolean short-circuit evaluation for a safety gate:
    ; a fatal exception must never call storage code or touch SD MMIO.
    If rock_recovery_fatal_mode<>0
      RockUartLine("ERR STORAGE DISABLED IN FATAL RECOVERY")
    Else
      If RockFsCommand(@rock_recovery_line[0], rock_recovery_length)=0
        If RockStorageCommand(@rock_recovery_line[0], rock_recovery_length)=0
          RockUartLine("ERR COMMAND")
        EndIf
      EndIf
    EndIf
  EndIf
  rock_recovery_length=0
  rock_recovery_discard=0
EndProcedure

Procedure.i RockRecoveryInit()
  rock_recovery_length=0
  rock_recovery_discard=0
  rock_recovery_ready=0
  rock_recovery_error=0
  If rock_uart_ready=0 Or rock_timer_frequency<1000000
    rock_recovery_error=1
    ProcedureReturn 0
  EndIf
  rock_recovery_ready=1
  RockUartLine("RECOVERY READY; TYPE help")
  ProcedureReturn 1
EndProcedure

Procedure.i RockRecoveryPoll()
  Protected attempt.i
  Protected value.i
  Protected consumed.i
  Protected pumped.i
  If rock_recovery_ready=0 : ProcedureReturn 0 : EndIf
  ; Empty the hardware FIFO into a shared software ring before the slower
  ; parser. Limit parsing so the next refill occurs well inside the UART
  ; FIFO's 427 us fill interval at 1.5 Mbaud.
  pumped = RockUartPump(#ROCK_RECOVERY_PUMP_BYTES)
  If pumped <> 0 : consumed = 1 : EndIf
  For attempt=0 To #ROCK_RECOVERY_POLL_BYTES-1
    value=RockUartReceive()
    If value=-1 : Break : EndIf
    consumed=1
    If rock_recovery_skip_lf<>0
      If value=10
        rock_recovery_skip_lf=0
        Continue
      EndIf
      rock_recovery_skip_lf=0
    EndIf
    If value=-2
      ; OE/PE/FE/BI means the line is no longer trustworthy. Discard through
      ; the next clean terminator so a damaged prefix can never execute.
      rock_recovery_error=2
      rock_recovery_discard=1
    ElseIf value=13
      RockUartDropOptionalLf()
      rock_recovery_skip_lf=0
      RockRecoveryFinishLine()
    ElseIf value=10
      RockRecoveryFinishLine()
    ElseIf rock_recovery_discard<>0
      ; Keep draining this contaminated or overlong line.
    ElseIf value<32 Or value>126
      rock_recovery_discard=1
    ElseIf rock_recovery_length>=#ROCK_RECOVERY_LINE_BYTES
      rock_recovery_discard=1
    Else
      PokeA(@rock_recovery_line[0]+rock_recovery_length,value)
      rock_recovery_length=rock_recovery_length+1
    EndIf
  Next
  ProcedureReturn consumed
EndProcedure

Procedure RockRecoveryFatalLoop()
  ; RockExceptionFatal calls this only after switching to the dedicated
  ; emergency stack. Do not start display MMIO from exception recovery: the
  ; fault may have left clocks, stacks or device ownership in an unknown state.
  rock_recovery_hdmi_attempted=1
  rock_recovery_fatal_mode=1
  ; If UART or timer state is not trustworthy, return to the vector's masked
  ; WFE park. A second exception also parks in the vector.
  If RockRecoveryInit()=0 : ProcedureReturn 0 : EndIf
  RockUartLine("FATAL RECOVERY ACTIVE; TYPE reboot")
  Repeat
    RockRecoveryPoll()
    RockTimerWaitUs(1000)
  ForEver
EndProcedure
