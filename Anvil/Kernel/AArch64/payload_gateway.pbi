; AArch64 adapter for the shared entry/argument contract. The board's RunAt
; retains its own range, device quiesce, watchdog and return-recovery policy.
; gGoX0 is private ABI staging for the existing ARM trampolines, not a name
; a portable container engine needs to know.
XIncludeFile "Anvil/Kernel/AArch64/payload_state.pbi"

Procedure.i HwPayloadRun(entry.i, argument.i, stack.i, stackBytes.i)
  gPayloadDidEnter=0
  gGoRc=0
  gGoX0 = argument
  RunAt(entry)
  ; RunAt can refuse before reaching its ordinary cleanup. Never let a table
  ; pointer survive that refusal and become the next plain run's argument.
  gGoX0 = 0
  ProcedureReturn gPayloadDidEnter
EndProcedure
