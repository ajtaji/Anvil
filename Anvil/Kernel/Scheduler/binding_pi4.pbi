; Explicit exclusive EL3 scheduler binding. No automatic boot or task start.
; Include scheduler, preempt_a64, interrupts, timer_el3 before this file.
; State: 0 detached,1 vectors installed,2 GIC transferred,3 prepared.
; Failed rollback retains its exact state for diagnosis/retry; never reports0.
Global ab_state.i
Global ab_original.i
Global ab_vector.i
Procedure.i AbRollback()
  If ab_state = 0 : ProcedureReturn 1 : EndIf
  If AtEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If ab_state = 3
    If ApCanUninstall() = 0 : ProcedureReturn 0 : EndIf
    If AtRelease() = 0 : ProcedureReturn 0 : EndIf
    ab_state = 2
  EndIf
  If ab_state = 2
    If ap_restore_pending = 0
      If InterruptCanTransfer(ab_vector) = 0 : ProcedureReturn 0 : EndIf
    EndIf
    If ApUninstall() = 0 : ProcedureReturn 0 : EndIf
    ; State4 means vectors restored but GIC lease still needs return.
    ab_state = 4
  EndIf
  If ab_state = 4
    If InterruptTransfer(ab_vector, ab_original) = 0 : ProcedureReturn 0 : EndIf
    ab_state = 0
  EndIf
  If ab_state = 1
    If ApUninstall() = 0 : ProcedureReturn 0 : EndIf
    ab_state = 0
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i AbPrepare(period.i, code.i, size.i, reporter.i)
  If ab_state <> 0 Or AtEnvironment() = 0 : ProcedureReturn 0 : EndIf
  If period <= 0 Or period > $7FFFFFFF Or (AtControl() & 1) <> 0
    ProcedureReturn 0
  EndIf
  ab_original = InterruptVbar()
  If InterruptCanTransfer(ab_original) = 0 : ProcedureReturn 0 : EndIf
  If ApInstall(ab_original, @AtAcknowledge, @AtArm, @AtStop, code, size) = 0
    If ap_restore_pending <> 0
      ab_state = 1
      ab_vector = ap_vector
    EndIf
    ProcedureReturn 0
  EndIf
  ab_state = 1
  ab_vector = ap_vector
  If ApSetFatalReporter(reporter) = 0
    AbRollback()
    ProcedureReturn 0
  EndIf
  If InterruptTransfer(ab_original, ab_vector) = 0
    AbRollback()
    ProcedureReturn 0
  EndIf
  ab_state = 2
  If AtPrepare(period) = 0
    AbRollback()
    ProcedureReturn 0
  EndIf
  ab_state = 3
  ProcedureReturn 1
EndProcedure
