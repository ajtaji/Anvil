; SPDX-License-Identifier: MIT
; Prompt accounting uses the same published counter vocabulary as other core
; services. The board owns the counter implementation and frequency.
Procedure.i AnvilSchedulerCounterHz()
  ProcedureReturn TickHz()
EndProcedure
Procedure.i AnvilSchedulerCounterValue()
  ProcedureReturn Ticks()
EndProcedure
