; SPDX-License-Identifier: MIT
; Pure resident adapter. Configure/Seal before Begin; Draw inside the frame.
Procedure.i NeonServiceChromeMenuInstall()
  If NeonServiceReady()=0 : ProcedureReturn #NCM_ERR_RENDERER : EndIf
  ProcedureReturn NeonChromeMenuRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePrepare,@NeonServiceScissorSet,@NeonServiceScissorClear)
EndProcedure
