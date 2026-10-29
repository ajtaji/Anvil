; SPDX-License-Identifier: MIT
; Optional graphics protocol1.8. New reference, same face bytes/generation.
; No added face allocation or ownership. Policies copy, then vary independently.
Procedure.i NeonServiceFontDerive(font.i,role.i,pixels.i)
  Protected request.NeonServiceFontDeriveRequest,derived.i
  If font<=3 Or role<0 Or role>3 Or pixels<1 Or pixels>512
    NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : ProcedureReturn 0
  EndIf
  request\font=font : request\role=role : request\pixels=pixels
  derived=NeonServiceRequestExtension(#NEON_SERVICE_FONT_DERIVE_CREATE,@request,SizeOf(NeonServiceFontDeriveRequest),0,#NEON_SERVICE_FONT_DERIVE,#NEON_SERVICE_FONT_DERIVE_MINOR,0)
  If derived<=3
    If derived>=0 : NeonServiceExtensionStatus(#NEON_SERVICE_ERR_PROVIDER) : EndIf
    ProcedureReturn 0
  EndIf
  NeonServiceExtensionStatus(0) : ProcedureReturn derived
EndProcedure
