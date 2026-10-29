; SPDX-License-Identifier: MIT
; Pure resident adapter; no renderer, input or frame ownership.
XIncludeFile "Anvil/Graphics/neon_service_font_caret.pbi"
; Full-text caret layout for both registered references and default roles.
Procedure.f nsceCaret(font.i,text.i,bytes.i,offset.i)
  Protected request.NeonServiceFontCaretRequest,i.i,column.i,rc.i
  If bytes<0 Or bytes>=4096 Or offset<0 Or offset>bytes : ProcedureReturn -1.0 : EndIf
  While i<offset
    i=NeonUtf8Next(text,bytes,i)
    If i<0 Or i>offset : ProcedureReturn -1.0 : EndIf
    column=column+1
  Wend
  request\font=font : request\text=text : request\textBytes=bytes+1 : request\column=column
  rc=NeonServiceFontCaretQuery(#NEON_SERVICE_FONT_CARET_POINT,@request)
  If rc<>0 Or request\resultByte<>offset Or request\resultY<>0 : ProcedureReturn -1.0 : EndIf
  ProcedureReturn MathFFromInt(request\resultX)/65536.0
EndProcedure
Procedure.i NeonServiceChromeEditInstall()
  Protected rc.i
  If NeonServiceReady()=0 : ProcedureReturn #NCE_ERR_RENDERER : EndIf
  rc=NeonChromeEditRendererInstall(@NeonServiceBox,@NeonServiceText,@NeonServiceTextWidth,@NeonServiceLineHeight,@NeonServicePrepare,@NeonServiceScissorSet,@NeonServiceScissorClear)
  If rc<>0 : ProcedureReturn rc : EndIf
  ProcedureReturn NeonChromeEditCaretRendererInstall(@nsceCaret)
EndProcedure
