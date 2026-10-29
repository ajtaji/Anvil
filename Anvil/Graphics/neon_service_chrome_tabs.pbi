; SPDX-License-Identifier: MIT
; Pure resident adapter; no renderer or frame ownership.
Procedure.i NeonServiceChromeTabsInstall()
  If NeonServiceReady()=0 : ProcedureReturn #NCT_ERR_RENDERER : EndIf
  ProcedureReturn NeonChromeTabsRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePrepare,@NeonServiceScissorSet,@NeonServiceScissorClear)
EndProcedure
