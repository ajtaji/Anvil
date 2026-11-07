; ISA-neutral PMFBOOT identity/stack admission. No image bytes are read or
; written here. Expected identities come from the selected hardware contract.
#PMF_ID_OK = 0
#PMF_ID_CONTRACT = 1
#PMF_ID_ARCH = 2
#PMF_ID_TARGET = 3
#PMF_ID_STACK = 4

Procedure.i PmfStackContractValid(alignment.i, initialBytes.i)
  If alignment <= 0 Or initialBytes <= 0
    ProcedureReturn 0
  EndIf
  If (alignment & (alignment - 1)) <> 0
    ProcedureReturn 0
  EndIf
  If initialBytes < alignment Or (initialBytes & (alignment - 1)) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i PmfIdentityCheck(architecture.i, target.i, stack.i, expectedArch.i, expectedTarget.i, alignment.i)
  If expectedArch <= 0 Or expectedTarget <= 0 Or alignment <= 0
    ProcedureReturn #PMF_ID_CONTRACT
  EndIf
  If (alignment & (alignment - 1)) <> 0
    ProcedureReturn #PMF_ID_CONTRACT
  EndIf
  If architecture <> expectedArch
    ProcedureReturn #PMF_ID_ARCH
  EndIf
  If target <> expectedTarget
    ProcedureReturn #PMF_ID_TARGET
  EndIf
  If stack <= 0 Or (stack & (alignment - 1)) <> 0
    ProcedureReturn #PMF_ID_STACK
  EndIf
  ProcedureReturn #PMF_ID_OK
EndProcedure
