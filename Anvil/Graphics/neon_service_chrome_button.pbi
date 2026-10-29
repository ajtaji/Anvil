; SPDX-License-Identifier: MIT
; Prepared button metrics/geometry use the existing resident graphics service.
Procedure.i NeonServiceChromeButtonInstall()
  If NeonServiceReady()=0 : ProcedureReturn #NCB_ERR_RENDERER : EndIf
  ProcedureReturn NeonChromeButtonRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePrepare)
EndProcedure
