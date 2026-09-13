; FTDI recovery console for the original Rock Pi 4C handoff.
; Include after arch_timer.pbi and uart2.pbi. The board may enter this poll
; loop only after its DTB, timer and UART contracts validate. Once EL2 vectors
; are installed, a fatal exception uses its emergency stack to enter the same
; exact command parser. An untrusted handoff still parks without commands.
;
; Exact grammar is lowercase `help` or `reboot`, terminated by CR, LF or
; CRLF. There is no prefix execution, abbreviation or network transport.

#ROCK_RECOVERY_LINE_BYTES = 16
#ROCK_RECOVERY_POLL_BYTES = 64

Global Dim rock_recovery_line.a[#ROCK_RECOVERY_LINE_BYTES]
Global rock_recovery_length.i
Global rock_recovery_discard.i
Global rock_recovery_ready.i
Global rock_recovery_error.i

ProcedureNaked.i RockRecoveryPsciReset()
  ASM
    ; The pinned RK3399 DTB declares PSCI 1.0 method "smc". U-Boot retains
    ; the EL3 service while Anvil runs at NS EL2. SYSTEM_RESET is 0x84000009.
    movz x0, #0x0009
    movk x0, #0x8400, lsl #16
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    dsb sy
    smc #0
    ret
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
  RockUartLine("RESET: PSCI SYSTEM_RESET")
  ; A missing final stop bit is less harmful than stranding recovery. Drain
  ; failure is recorded by uart2.pbi but never prevents the reset request.
  RockUartDrain()
  status=RockRecoveryPsciReset()
  ; Returning means EL3 rejected or failed SYSTEM_RESET. Machine state after
  ; that call is not an interactive contract: report x0, drain, then fail-stop.
  rock_recovery_error=3
  If rock_uart_ready<>0
    RockUartText("RESET FAILED PSCI X0=")
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

Procedure RockRecoveryFinishLine()
  If rock_recovery_discard<>0
    RockUartLine("ERR LINE DISCARDED")
  ElseIf rock_recovery_length=0
    ; Ignore the LF half of CRLF and empty lines.
  ElseIf RockRecoveryLineIsReboot()<>0
    rock_recovery_length=0
    RockRecoveryReset()
  ElseIf RockRecoveryLineIsHelp()<>0
    RockUartLine("COMMANDS: help reboot")
  Else
    RockUartLine("ERR COMMAND")
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
  If rock_recovery_ready=0 : ProcedureReturn 0 : EndIf
  ; Consume only bytes already waiting in the UART and cap work per call. No
  ; partial line blocks the monitor's late recovery loop.
  For attempt=0 To #ROCK_RECOVERY_POLL_BYTES-1
    value=RockUartReceive()
    If value=-1 : Break : EndIf
    consumed=1
    If value=-2
      ; OE/PE/FE/BI means the line is no longer trustworthy. Discard through
      ; the next clean terminator so a damaged prefix can never execute.
      rock_recovery_error=2
      rock_recovery_discard=1
    ElseIf value=13 Or value=10
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
  ; emergency stack. If UART or timer state is not trustworthy, return to the
  ; vector's masked WFE park. A second exception also parks in the vector.
  If RockRecoveryInit()=0 : ProcedureReturn 0 : EndIf
  RockUartLine("FATAL RECOVERY ACTIVE; TYPE reboot")
  Repeat
    RockRecoveryPoll()
    RockTimerWaitUs(1000)
  ForEver
EndProcedure
