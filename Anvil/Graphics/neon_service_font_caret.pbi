; SPDX-License-Identifier: MIT
; Optional protocol 1.13. Exact record outputs remain unchanged on refusal.
; Text is borrowed for the serialized call; no resident layout pointer escapes.
Procedure.i NeonServiceFontCaretQuery(op.i,*request.NeonServiceFontCaretRequest)
  Protected copy.NeonServiceFontCaretRequest,rc.i,i.i,flags.i,minor.i
  If *request=0 Or (*request & 7)<>0 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  If op<#NEON_SERVICE_FONT_CARET_POINT Or op>#NEON_SERVICE_FONT_TEXT_COLUMN
    ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS)
  EndIf
  If *request\font<0 Or *request\text<1 Or *request\textBytes<1 Or *request\textBytes>4096
    ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS)
  EndIf
  For i=0 To SizeOf(NeonServiceFontCaretRequest)-8 Step 8 : PokeI(@copy+i,PeekI(*request+i)) : Next
  flags=#NEON_SERVICE_FONT_CARETS|#NEON_SERVICE_FONT_REFS : minor=#NEON_SERVICE_FONT_CARETS_MINOR
  If copy\font<=3 : flags=flags|#NEON_SERVICE_ROLE_CARETS : minor=#NEON_SERVICE_ROLE_CARETS_MINOR : EndIf
  rc=NeonServiceRequestExtension(op,@copy,SizeOf(NeonServiceFontCaretRequest),-1,flags,minor,0)
  If rc>0 : rc=#NEON_SERVICE_ERR_PROVIDER : EndIf
  If rc=0
    *request\resultX=copy\resultX : *request\resultY=copy\resultY
    *request\resultByte=copy\resultByte : *request\resultColumn=copy\resultColumn
  EndIf
  ProcedureReturn NeonServiceExtensionStatus(rc)
EndProcedure
