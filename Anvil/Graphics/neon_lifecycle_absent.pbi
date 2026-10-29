; SPDX-License-Identifier: MIT
; Explicit native-lifecycle provider for a composition with no native renderer.
; An external renderer may still install its complete callback family through
; the shared policy. This provider never acquires a native device or frame.
XIncludeFile "Anvil/Graphics/neon_lifecycle.pbi"
Procedure.i NeonHardwareLifecycleFlags()
  ProcedureReturn 0
EndProcedure
Procedure NeonHardwareCoordinateReset()
  ; There are no native tables to invalidate.
EndProcedure
Procedure.i NeonHardwareInit()
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure
Procedure.i NeonHardwareShutdown()
  ProcedureReturn #NEON_OK
EndProcedure
Procedure.i NeonHardwareFrameBegin(colour.i)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure
Procedure.i NeonHardwareFrameEnd()
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure
