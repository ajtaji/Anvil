; SPDX-License-Identifier: MIT
; Use outside a frame after preparing both source and the selected marker.
; Font glyph availability/fallback policy remains with the application.
XIncludeFile "Anvil/Graphics/neon_text_fit.pbi"
Procedure.i NeonServiceTextFitInstall()
  If NeonServiceReady()=0 : ProcedureReturn #NEON_TEXT_FIT_ERR_UNBOUND : EndIf
  ProcedureReturn NeonTextFitBind(@NeonServiceTextWidth)
EndProcedure
