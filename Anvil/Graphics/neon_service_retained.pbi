; SPDX-License-Identifier: MIT
; Pure adapter. Include retained UI and the service client before this file.
Procedure.i NeonServiceRetainedInstall()
  If NeonServiceReady()=0 : ProcedureReturn #NRU_ERR_RENDERER : EndIf
  ProcedureReturn NeonRetainedRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePolygon,@NeonServicePrepare)
EndProcedure
