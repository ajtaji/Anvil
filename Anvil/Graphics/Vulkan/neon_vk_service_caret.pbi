; SPDX-License-Identifier: MIT
; Shared renderer adapter. Provider resolves the opaque handle and validates
; caller memory ownership before entering. No renderer-specific pointer escapes.
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
Procedure.i NeonVkServiceCaret(op.i,*font.NeonVkPortFontRef,*request.NeonServiceFontCaretRequest,bytes.i)
  Protected i.i,rc.i,x.i,y.i,offset.i,column.i,value.f,lines.i,advance.i
  If op<#NEON_SERVICE_FONT_CARET_POINT Or op>#NEON_SERVICE_FONT_TEXT_COLUMN
    ProcedureReturn #NEON_SERVICE_ERR_ARGS
  EndIf
  If bytes<>SizeOf(NeonServiceFontCaretRequest) Or (*request & 7)<>0 Or NeonByteSpan(*request,bytes)=0
    ProcedureReturn #NEON_SERVICE_ERR_ARGS
  EndIf
  If *request\textBytes<1 Or *request\textBytes>4096 Or NeonByteSpan(*request\text,*request\textBytes)=0
    ProcedureReturn #NEON_SERVICE_ERR_ARGS
  EndIf
  If NeonByteOverlap(*request,bytes,*request\text,*request\textBytes)<>0 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  For i=0 To *request\textBytes-1
    If PeekA(*request\text+i)=0 : Break : EndIf
  Next
  If i<>*request\textBytes-1 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
  If *font<>0
    lines=NeonVkPortFontPrepareCarets(*font,*request\text)
    If lines<0 : ProcedureReturn lines : EndIf
    advance=*font\fixedAdvanceQ16
  Else
    If *request\font<0 Or *request\font>3 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
    lines=NeonVkChromePrepareCarets(*request\font,*request\text,0,0)
    If lines<1 : ProcedureReturn #NEON_VK_FONT_ERR_METRICS : EndIf
  EndIf
  Select op
    Case #NEON_SERVICE_FONT_CARET_POINT
      If AnvilTrueTypeCaretPoint(*request\column,@x,@y,@offset)=0 : rc=#NEON_VK_FONT_ERR_METRICS : EndIf
    Case #NEON_SERVICE_FONT_CARET_HIT
      column=AnvilTrueTypeCaretColumnForX(*request\line,*request\xQ16)
      If column<0 : rc=#NEON_VK_FONT_ERR_METRICS : EndIf
    Case #NEON_SERVICE_FONT_TEXT_X
      value=NeonVkPortCaretXPrepared(lines,advance,*request\column)
      If value<0.0 : rc=#NEON_VK_FONT_ERR_METRICS : Else : x=MathFToInt(value*65536.0) : EndIf
    Case #NEON_SERVICE_FONT_TEXT_COLUMN
      If *request\xQ16 < -65536000000 Or *request\xQ16>65536000000 : ProcedureReturn #NEON_SERVICE_ERR_ARGS : EndIf
      column=NeonVkPortCaretColumnPrepared(lines,MathFFromInt(*request\xQ16)/65536.0)
      If column<0 : rc=#NEON_VK_FONT_ERR_METRICS : EndIf
  EndSelect
  If rc<>0 : ProcedureReturn rc : EndIf
  *request\resultX=x : *request\resultY=y : *request\resultByte=offset : *request\resultColumn=column
  ProcedureReturn 0
EndProcedure
