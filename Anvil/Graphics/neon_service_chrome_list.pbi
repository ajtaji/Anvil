; SPDX-License-Identifier: MIT
; Pure resident renderer adapter. Caller configures shared scroll/input state.
Procedure.i NeonServiceChromeListInstall()
  If NeonServiceReady()=0 : ProcedureReturn #NCL_ERR_RENDERER : EndIf
  ProcedureReturn NeonChromeListRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePrepare,@NeonServiceScissorSet,@NeonServiceScissorClear)
EndProcedure
