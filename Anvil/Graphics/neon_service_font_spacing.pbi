; SPDX-License-Identifier: MIT
; Optional graphics protocol1.5. Existing font/vector clients retain minor0.
; Register a font reference first; idle-only, no glyph rerasterization required.
Procedure.i NeonServiceFontSetFixedAdvance(font.i,advance.f)
  Protected request.NeonServiceFontAdvanceRequest
  If font<=3 Or advance<0.0 Or (MathBitsOf(advance) & $7FFFFFFF)>$46000000
    ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS)
  EndIf
  request\font=font : request\advanceQ16=MathFToInt(advance*65536.0+0.5)
  If advance>0.0 And request\advanceQ16=0 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_FONT_ADVANCE,@request,SizeOf(NeonServiceFontAdvanceRequest),0,#NEON_SERVICE_FONT_SPACING,#NEON_SERVICE_FONT_SPACING_MINOR,0))
EndProcedure
