; SPDX-License-Identifier: MIT
; Scalar caret columns and measured UTF8 prefixes. Prepare glyphs before calling;
; use outside Draw. Explicit fixed advance must match the selected renderer.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Graphics/neon_utf8.pbi"
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
#NEON_COLUMN_ERR_ARGS=-23400
#NEON_COLUMN_ERR_TEXT=-23401
#NEON_COLUMN_ERR_CAPACITY=-23402
#NEON_COLUMN_ERR_METRICS=-23403
#NEON_COLUMN_ERR_BUSY=-23404
#NEON_COLUMN_ERR_UNBOUND=-23405
Structure NeonTextColumnResult
 column.i
 x.f
 reserved.l
EndStructure
Procedure.f ntcUnbound(font.i,text.i)
 ProcedureReturn -1.0
EndProcedure
Global ntcMeasure.i=@ntcUnbound,ntcBound.i,ntcBusy.i
Procedure.i NeonTextColumnBind(measure.i)
 If ntcBusy<>0 : ProcedureReturn #NEON_COLUMN_ERR_BUSY : EndIf
 If measure=0 : ProcedureReturn #NEON_COLUMN_ERR_ARGS : EndIf
 ntcMeasure=measure : ntcBound=1 : ProcedureReturn 0
EndProcedure
Procedure.i NeonTextColumnUnbind()
 If ntcBusy<>0 : ProcedureReturn #NEON_COLUMN_ERR_BUSY : EndIf
 ntcMeasure=@ntcUnbound : ntcBound=0 : ProcedureReturn 0
EndProcedure
Procedure.i ntcMap(*result.NeonTextColumnResult,scratch.i,capacity.i,source.i,budget.i,font.i,column.i,x.f,fixedAdvance.f,mode.i)
 Protected bytes.i,offset.i,count.i,i.i,target.i,rc.i,nextOffset.i
 Protected previous.f,width.f,edge.f
 If ntcBusy<>0 : ProcedureReturn #NEON_COLUMN_ERR_BUSY : EndIf
 If budget<1 Or budget>4096 Or font<0 Or column<0 Or column>65535 Or fixedAdvance<0.0 Or (MathBitsOf(fixedAdvance) & $7FFFFFFF)>$46000000 Or (MathBitsOf(x) & $7FFFFFFF)>$4B800000
  ProcedureReturn #NEON_COLUMN_ERR_ARGS
 EndIf
 If (*result & 7)<>0 Or NeonByteSpan(*result,SizeOf(NeonTextColumnResult))=0 Or NeonByteSpan(scratch,capacity)=0 Or NeonByteSpan(source,budget)=0
  ProcedureReturn #NEON_COLUMN_ERR_ARGS
 EndIf
 If NeonByteOverlap(*result,SizeOf(NeonTextColumnResult),scratch,capacity)<>0 Or NeonByteOverlap(*result,SizeOf(NeonTextColumnResult),source,budget)<>0 Or NeonByteOverlap(scratch,capacity,source,budget)<>0
  ProcedureReturn #NEON_COLUMN_ERR_ARGS
 EndIf
 bytes=NeonUtf8Length(source,budget)
 If bytes<0 : ProcedureReturn #NEON_COLUMN_ERR_TEXT : EndIf
 If capacity<bytes+1 : ProcedureReturn #NEON_COLUMN_ERR_CAPACITY : EndIf
 If fixedAdvance>0.0
  While offset<bytes : offset=NeonUtf8Next(source,bytes,offset) : count=count+1 : Wend
  target=column
  If mode=1
   target=0
   If x>0.0
    edge=MathFFromInt(count)*fixedAdvance
    If (MathBitsOf(edge) & $7FFFFFFF)>$4B800000 : ProcedureReturn #NEON_COLUMN_ERR_METRICS : EndIf
    If x>=edge : target=count
    Else : target=MathFToInt(x/fixedAdvance+0.5) : If target>count : target=count : EndIf
    EndIf
   EndIf
  EndIf
  previous=MathFFromInt(target)*fixedAdvance
  If (MathBitsOf(previous) & $7FFFFFFF)>$4B800000 : ProcedureReturn #NEON_COLUMN_ERR_METRICS : EndIf
 Else
  If ntcBound=0 : ProcedureReturn #NEON_COLUMN_ERR_UNBOUND : EndIf
  ntcBusy=1
  PokeA(scratch,0)
  While offset<bytes
   If mode=0 And count=column : Break : EndIf
   If mode=1 And x<=0.0 : Break : EndIf
   nextOffset=NeonUtf8Next(source,bytes,offset)
   For i=offset To nextOffset-1 : PokeA(scratch+i,PeekA(source+i)) : Next
   PokeA(scratch+nextOffset,0)
   width=ntcMeasure(font,scratch)
   If width<previous Or (MathBitsOf(width) & $7FFFFFFF)>$4B800000
    rc=#NEON_COLUMN_ERR_METRICS : Break
   EndIf
   If mode=1 And x<previous+(width-previous)*0.5 : Break : EndIf
   previous=width : offset=nextOffset : count=count+1
  Wend
  ntcBusy=0
  If rc<>0 : ProcedureReturn rc : EndIf
  target=count
 EndIf
 *result\column=target : *result\x=previous : *result\reserved=0
 ProcedureReturn 0
EndProcedure
; Both calls publish {scalar column, pixel x, reserved=0}, or preserve result on
; refusal. Scratch is disposable/disjoint from source and result. Source budget
; includes NUL. Prefix metrics must be finite, nonnegative and nondecreasing.
; Fixed XForColumn extrapolates beyond text; proportional clamps at text end.
Procedure.i NeonTextXForColumn(*result.NeonTextColumnResult,scratch.i,capacity.i,source.i,budget.i,font.i,column.i,fixedAdvance.f)
 ProcedureReturn ntcMap(*result,scratch,capacity,source,budget,font,column,0.0,fixedAdvance,0)
EndProcedure
; Midpoint ties choose the later scalar; x<=0 chooses column0. Fixed input clamps
; to the Unicode scalar count, including supplementary characters as one column.
Procedure.i NeonTextColumnForX(*result.NeonTextColumnResult,scratch.i,capacity.i,source.i,budget.i,font.i,x.f,fixedAdvance.f)
 ProcedureReturn ntcMap(*result,scratch,capacity,source,budget,font,0,x,fixedAdvance,1)
EndProcedure
