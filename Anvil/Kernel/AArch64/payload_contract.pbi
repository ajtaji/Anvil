; AArch64 PMFBOOT contract. ID 1 is the compiler's existing append-only
; architecture identity; HwPmfTargetId independently identifies the board.
Procedure.i HwPmfArchitectureId()
  ProcedureReturn 1
EndProcedure
Procedure.i HwPmfStackAlignment()
  ProcedureReturn 16
EndProcedure
Procedure.i HwPmfInitialStackBytes()
  ProcedureReturn 16
EndProcedure
; v1 has no ISA metadata and is the historic AArch64 executable format.
; Another architecture must refuse v1 unless it implements that exact ABI.
Procedure.i HwPmfLegacyV1Allowed()
  ProcedureReturn 1
EndProcedure

Procedure.i HwPmfInstructionAlignment() : ProcedureReturn 4 : EndProcedure
