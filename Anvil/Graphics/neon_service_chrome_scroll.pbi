; SPDX-License-Identifier: MIT
; Pure resident-service adapter. Include the scroll module and service client.
Procedure.i NeonServiceChromeScrollInstall(*state.NeonChromeScrollState,scale.f)
  If NeonServiceReady()=0 : ProcedureReturn #NCS_ERR_RENDERER : EndIf
  Protected rc.i=NeonChromeScrollConfigure(*state,scale)
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn NeonChromeScrollRendererInstall(@NeonServiceBox)
EndProcedure
