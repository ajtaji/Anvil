; SPDX-License-Identifier: MIT
; Resident service binding; prepare titles before the caller opens its frame.
Procedure.i NeonServiceChromePanelInstall()
  If NeonServiceReady()=0 : ProcedureReturn #NCP_ERR_RENDERER : EndIf
  ProcedureReturn NeonChromePanelRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServicePrepare)
EndProcedure
