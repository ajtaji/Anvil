; SPDX-License-Identifier: MIT
; Optional graphics protocol1.6. Basic clients retain their minor0 contract.
; Geometry policy only; source widths, cached layout and glyph rasters stay valid.
Procedure.i NeonServiceFontSetSnapToPixel(font.i,enabled.i)
  Protected request.NeonServiceFontSnapRequest
  If font<=3 Or enabled<0 Or enabled>1
    ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS)
  EndIf
  request\font=font : request\enabled=enabled
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_FONT_SNAP_SET,@request,SizeOf(NeonServiceFontSnapRequest),0,#NEON_SERVICE_FONT_SNAP,#NEON_SERVICE_FONT_SNAP_MINOR,0))
EndProcedure
