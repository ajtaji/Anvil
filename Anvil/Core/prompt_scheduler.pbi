; Cooperative prompt policy. No ISA instructions, privilege-level numbers or
; board identification. The selected hardware backend implements the contract
; in Anvil/Hal/prompt_idle.pbi.
XIncludeFile "Anvil/Hal/prompt_idle.pbi"

Global anvil_promptServiceSlot.i = 0
Global anvil_promptWindowStart.q = 0
Global anvil_promptIdleTicks.q = 0
Global anvil_promptCpuPercent.i = -1
Global anvil_promptCpuHundredths.i = -1
Global anvil_promptWindowReady.i = 0

; Main-core utilization only. -1 means no complete one-second window yet.
; Idle is measured only around the backend wait, not service time.
Procedure.i AnvilCpuUsagePercent()
  If anvil_promptWindowReady = 0
    ProcedureReturn -1
  EndIf
  If anvil_promptCpuHundredths < 0 : ProcedureReturn -1 : EndIf
  ProcedureReturn anvil_promptCpuPercent
EndProcedure

; Core 0's busy utilization in hundredths of a percent, sampled over the
; same completed one-second wall-clock window as AnvilCpuUsagePercent().
Procedure.i AnvilCpuUsageHundredths()
  If anvil_promptWindowReady = 0 Or anvil_promptCpuHundredths < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn anvil_promptCpuHundredths
EndProcedure

Procedure AnvilSchedulerAccount()
  Define now.q
  Define elapsed.q
  Define hz.q
  now = Ticks()
  If anvil_promptWindowReady = 0
    anvil_promptWindowStart = now
    anvil_promptIdleTicks = 0
    anvil_promptWindowReady = 1
    ProcedureReturn
  EndIf
  elapsed = now - anvil_promptWindowStart
  hz = TickHz()
  If hz > 0 And elapsed >= hz
    If anvil_promptIdleTicks > elapsed
      anvil_promptIdleTicks = elapsed
    EndIf
    anvil_promptCpuHundredths = 10000 - ((anvil_promptIdleTicks * 10000) / elapsed)
    If anvil_promptCpuHundredths < 0 : anvil_promptCpuHundredths = 0 : EndIf
    If anvil_promptCpuHundredths > 10000 : anvil_promptCpuHundredths = 10000 : EndIf
    ; Keep the original whole-percent getter semantics for existing callers.
    anvil_promptCpuPercent = 100 - ((anvil_promptIdleTicks * 100) / elapsed)
    If anvil_promptCpuPercent < 0 : anvil_promptCpuPercent = 0 : EndIf
    If anvil_promptCpuPercent > 100 : anvil_promptCpuPercent = 100 : EndIf
    anvil_promptWindowStart = now
    anvil_promptIdleTicks = 0
  EndIf
EndProcedure


Procedure AnvilPromptServiceOne()
  UartMessageBegin()
  Select anvil_promptServiceSlot
    Case 0
      MouseTick()
      TouchTick()
      CompilerIf #CAP_TOUCH = 1
        TouchKeyboardServiceTick()
      CompilerEndIf
    Case 1
      ScreenServiceTick()
    Case 2
      WifiMaintenanceTick()
      NetDhcpTick()
      CompilerIf #CAP_NET = 1
        NtpServiceTick()
      CompilerEndIf
    Case 3
      CompilerIf #CAP_PWM = 1
        If HwPwmKind() <> #HW_PWM_KIND_SOFT
          FanTick()
        EndIf
      CompilerElse
        FanTick()
      CompilerEndIf
      HwTempSampleTick()
      HwPromptBoardService()
    Case 4
      NetConsoleRearm()
      NetConsolePump()
      NetConsoleLlTick()
      CompilerIf #CAP_NET = 1
        HttpServerPoll()
      CompilerElse
        TcpTick()
      CompilerEndIf
  EndSelect
  UartMessageEnd()
  anvil_promptServiceSlot = anvil_promptServiceSlot + 1
  If anvil_promptServiceSlot > 4
    anvil_promptServiceSlot = 0
  EndIf
  AnvilSchedulerAccount()
EndProcedure

Procedure AnvilSchedulerIdleIfSafe()
  Define t0.q
  Define dt.q
  AnvilSchedulerAccount()
  If HwPromptIdleReady() = 0
    ProcedureReturn
  EndIf
  If UartReadReady() <> 0 Or InputEventsQueued() <> 0
    ProcedureReturn
  EndIf
  CompilerIf #CAP_PWM = 1
    If HwPwmKind() = #HW_PWM_KIND_SOFT
      ProcedureReturn
    EndIf
  CompilerEndIf
  t0 = Ticks()
  HwPromptIdleWait()
  dt = Ticks() - t0
  If dt > 0
    anvil_promptIdleTicks = anvil_promptIdleTicks + dt
  EndIf
  AnvilSchedulerAccount()
EndProcedure
