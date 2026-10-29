; SPDX-License-Identifier: MIT
; Optional graphics protocol1.7. Control modes:0legacy,1hide,2show C0/DEL.
; Width/prewarm/draw share this policy; changing it is idle-only.
Procedure.i NeonServiceFontSetControlMode(font.i,mode.i)
  Protected request.NeonServiceFontControlsRequest
  If font<=3 Or mode<0 Or mode>2
    ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS)
  EndIf
  request\font=font : request\mode=mode
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_FONT_CONTROLS_SET,@request,SizeOf(NeonServiceFontControlsRequest),0,#NEON_SERVICE_FONT_CONTROLS,#NEON_SERVICE_FONT_CONTROLS_MINOR,0))
EndProcedure
Procedure.i NeonServiceFontSetShowControls(font.i,enabled.i)
  If enabled<0 Or enabled>1 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  ProcedureReturn NeonServiceFontSetControlMode(font,enabled+1)
EndProcedure
