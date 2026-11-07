; AArch64 counter-event idle mechanism selected by the board composition.
; Existing clock, EL3, readback and watchdog qualification requirements remain.

Global anvil_promptWfeReady.i = 0
Global anvil_promptWfeEnabled.i = 0
Global anvil_promptProbePassed.i = 0
Global anvil_promptWfePeriod.i = 0
Global anvil_promptOldControl.i = 0
Global anvil_promptProbeSamples.i = 0
Global anvil_promptProbeMinTicks.i = 0
Global anvil_promptProbeMaxTicks.i = 0
Global anvil_promptProbeTotalTicks.i = 0

XIncludeFile "Anvil/Kernel/Scheduler/prompt_clock.pbi"

; The event-stream control helpers retain their ABI return/argument register.


Procedure.i AnvilSchedulerReadControl()
  Asm
    mrs x0, cntkctl_el1
  EndAsm
EndProcedure

Procedure AnvilSchedulerWriteControl(value.i)
  Asm
    msr cntkctl_el1, x0
    isb
  EndAsm
EndProcedure

; Establish CNTKCTL_EL1's virtual-counter event stream. This does not
; claim the stream wakes WFE on this particular board; the board must run
; its bounded EL3 wake probe and call AnvilSchedulerWfeVerified(1).
Procedure.i AnvilSchedulerPrepareWfe()
  Define x0.i
  Define hz.i
  Define control.i
  Define oldControl.i
  Define evnti.i
  Define period.i
  Define target.i
  Define firstCount.i
  Define secondCount.i
  Define readback.i

  If HwIdEl() <> 3
    ProcedureReturn 0
  EndIf
  hz = AnvilSchedulerCounterHz()
  If hz < 1000000 Or hz > 1000000000
    ProcedureReturn 0
  EndIf
  firstCount = AnvilSchedulerCounterValue()

  ; EVNTI selects a counter bit; rising transitions occur every
  ; 2^(EVNTI+1) ticks. The Pi 4's measured bit-15 event sleeps about
  ; 1.21 ms, reducing prompt polling while retaining input service on
  ; every wake. Other targets keep their existing 500 us bound.
  target = hz / 2000
  CompilerIf #PMF_CHIP = 2711
  target = hz / 500
  CompilerEndIf
  evnti = 0
  period = 2
  While evnti < 15 And period <= target / 2
    evnti = evnti + 1
    period = period * 2
  Wend
  oldControl = AnvilSchedulerReadControl()
  anvil_promptOldControl = oldControl
  control = (oldControl & $FFFFFFFFFFFFFF03) | ((evnti & 15) << 4) | 4
  AnvilSchedulerWriteControl(control)
  readback = AnvilSchedulerReadControl()
  If (readback & $FC) <> (control & $FC)
    AnvilSchedulerWriteControl(oldControl)
    ProcedureReturn 0
  EndIf
  secondCount = AnvilSchedulerCounterValue()
  If secondCount <= firstCount
    AnvilSchedulerWriteControl(oldControl)
    ProcedureReturn 0
  EndIf
  anvil_promptWfePeriod = period
  anvil_promptWfeReady = 1
  ProcedureReturn period
EndProcedure

; Only call with the board deadman armed. If the configured EL3 event
; stream does not wake WFE, the hardware watchdog is the external bound.
; One unmeasured WFE drains a possibly pending event before the measured wait.
Procedure.i AnvilSchedulerWakeProbe(samples.i)
  Define x0.i
  Define n.i
  Define t0.i
  Define elapsed.i
  Define maxTicks.i
  Define total.i
  Define minSeen.i
  Define maxSeen.i
  If samples < 1 Or samples > 64
    ProcedureReturn 0
  EndIf
  If AnvilSchedulerPrepareWfe() <= 0
    ProcedureReturn 0
  EndIf
  maxTicks = (TickHz() / 500) + 1
  minSeen = $7FFFFFFFFFFFFFFF
  maxSeen = 0
  total = 0
  For n = 1 To samples
    Asm
      wfe
    EndAsm
    t0 = Ticks()
    Asm
      wfe
    EndAsm
    elapsed = Ticks() - t0
    If elapsed <= 0 Or elapsed > maxTicks
      AnvilSchedulerWriteControl(anvil_promptOldControl)
      anvil_promptWfeReady = 0
      anvil_promptWfeEnabled = 0
      anvil_promptProbePassed = 0
      anvil_promptProbeSamples = n - 1
      anvil_promptProbeMinTicks = minSeen
      anvil_promptProbeMaxTicks = maxSeen
      anvil_promptProbeTotalTicks = total
      ProcedureReturn 0
    EndIf
    If elapsed < minSeen : minSeen = elapsed : EndIf
    If elapsed > maxSeen : maxSeen = elapsed : EndIf
    total = total + elapsed
  Next
  anvil_promptProbeSamples = samples
  anvil_promptProbeMinTicks = minSeen
  anvil_promptProbeMaxTicks = maxSeen
  anvil_promptProbeTotalTicks = total
  anvil_promptProbePassed = 1
  anvil_promptWfeEnabled = 1
  ProcedureReturn samples
EndProcedure

; Standard hardware qualification is 32 samples, with the external
; watchdog armed by the board diagnostic caller.
Procedure.i AnvilSchedulerProbeWfe()
  ProcedureReturn AnvilSchedulerWakeProbe(32)
EndProcedure

Procedure.i AnvilSchedulerWakeProbeMinTicks()
  ProcedureReturn anvil_promptProbeMinTicks
EndProcedure

Procedure.i AnvilSchedulerWakeProbeMaxTicks()
  ProcedureReturn anvil_promptProbeMaxTicks
EndProcedure

Procedure.i AnvilSchedulerWakeProbeTotalTicks()
  ProcedureReturn anvil_promptProbeTotalTicks
EndProcedure

Procedure AnvilSchedulerWfeVerified(enabled.i)
  If enabled <> 0 And anvil_promptWfeReady <> 0 And anvil_promptProbePassed <> 0 And HwIdEl() = 3
    anvil_promptWfeEnabled = 1
  Else
    anvil_promptWfeEnabled = 0
  EndIf
EndProcedure

; The Pi 3 Model B (BCM2837) EL3 path has a separately hardware-qualified
; event stream. Enable it only when the live counter/exception level match
; that tested configuration and CNTKCTL accepts the bounded period. This is
; a register setup/readback, not a boot-time WFE probe; other boards remain
; on the cooperative polling path until they are independently qualified.
Procedure.i AnvilSchedulerQualifyPi3Wfe()
  anvil_promptWfeReady = 0
  anvil_promptProbePassed = 0
  anvil_promptWfeEnabled = 0
  If HwIdEl() <> 3 Or AnvilSchedulerCounterHz() <> 19200000
    ProcedureReturn 0
  EndIf
  If AnvilSchedulerPrepareWfe() <= 0
    anvil_promptWfeEnabled = 0
    ProcedureReturn 0
  EndIf
  ; The 32-sample deadman-protected hardware qualification is documented
  ; for this exact BCM2837/EL3/counter path. Do not repeat it on every boot.
  anvil_promptProbePassed = 1
  AnvilSchedulerWfeVerified(1)
  ProcedureReturn anvil_promptWfeEnabled
EndProcedure

; The BCM2711 EL3/counter path passed deadman-guarded 32-wake silicon
; probes at both bit 13 and bit 15 with CNTFRQ_EL0 = 54 MHz. Keep the readback and frequency
; bounds at every boot; a different clock or exception level polls instead.
Procedure.i AnvilSchedulerQualifyPi4Wfe()
  anvil_promptWfeReady = 0
  anvil_promptProbePassed = 0
  anvil_promptWfeEnabled = 0
  If HwIdEl() <> 3 Or AnvilSchedulerCounterHz() <> 54000000
    ProcedureReturn 0
  EndIf
  If AnvilSchedulerPrepareWfe() <= 0
    ProcedureReturn 0
  EndIf
  anvil_promptProbePassed = 1
  AnvilSchedulerWfeVerified(1)
  ProcedureReturn anvil_promptWfeEnabled
EndProcedure

Procedure.i HwPromptIdleReady()
  If anvil_promptWfeEnabled = 0 Or anvil_promptWfeReady = 0
    ProcedureReturn 0
  EndIf
  If HwIdEl() <> 3
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure HwPromptIdleWait()
  Asm
    wfe
  EndAsm
EndProcedure

; Preserve the existing synchronous board idle hook behind its hardware seam.
Global *gAnvilIdleHook = 0
Procedure HwPromptBoardService()
  If *gAnvilIdleHook <> 0
    gAnvilIdleHook()
  EndIf
EndProcedure
