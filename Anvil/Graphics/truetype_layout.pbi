; Bounded UTF-8 glyph placement and line wrapping. All output storage is
; caller-owned. x/y/advance values are signed 16.16 pixels; y is baseline-
; relative and positive upward. Raster bearings are applied by the caller.

#ANVIL_TTL_MAX_GLYPHS = 2048
#ANVIL_TTL_E_NONE = 0
#ANVIL_TTL_E_ARGUMENT = 1
#ANVIL_TTL_E_CAPACITY = 2
#ANVIL_TTL_E_FONT = 3
#ANVIL_TTL_E_PAIR = 4
#ANVIL_TTL_ALIGN_LEFT = 0
#ANVIL_TTL_ALIGN_CENTER = 1
#ANVIL_TTL_ALIGN_RIGHT = 2

Global anvil_ttl_error.i
Global anvil_ttl_count.i
Global anvil_ttl_trailingBreak.i
Global Dim anvil_ttl_glyph.i[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_advance.q[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_adjustAdvance.q[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_placeX.q[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_placeY.q[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_forceBreak.i[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_pairValues.i[8]

Procedure.q anvil_ttl_Scale(value.i,pixels.i,unitsPerEm.i)
  Protected scaled.q=value
  scaled=scaled*pixels*65536
  ProcedureReturn scaled/unitsPerEm
EndProcedure

; Convert a previously validated UTF-8 stream to glyphs and forced-break
; markers. CRLF is one break; CR and LF are omitted from the drawable run.
Procedure.i anvil_ttl_Decode(text.i,byteCount.i,capacity.i)
  Protected decoded.i,sourceIndex.i,sourcePos.i,b0.i,need.i,pendingBreak.i
  decoded=AnvilTrueTypeDecodeUtf8(text,byteCount,@anvil_ttl_glyph[0],capacity)
  If decoded<0 : ProcedureReturn -1 : EndIf
  anvil_ttl_count=0 : anvil_ttl_trailingBreak=0 : sourceIndex=0 : sourcePos=0 : pendingBreak=0
  While sourcePos<byteCount
    b0=PeekA(text+sourcePos)&$FF
    If b0<128 : need=1
    ElseIf b0<$E0 : need=2
    ElseIf b0<$F0 : need=3
    Else : need=4
    EndIf
    If (b0=10 Or b0=13)
      pendingBreak+1
      If b0=13 And sourcePos+1<byteCount
        If (PeekA(text+sourcePos+1)&$FF)=10
          sourcePos+1 : sourceIndex+1
        EndIf
      EndIf
    Else
      If anvil_ttl_count>=capacity : ProcedureReturn -1 : EndIf
      anvil_ttl_glyph[anvil_ttl_count]=anvil_ttl_glyph[sourceIndex]
      anvil_ttl_forceBreak[anvil_ttl_count]=pendingBreak
      pendingBreak=0 : anvil_ttl_count+1
    EndIf
    sourceIndex+1 : sourcePos+need
  Wend
  anvil_ttl_trailingBreak=pendingBreak
  ProcedureReturn anvil_ttl_count
EndProcedure

; Wrap at glyph boundaries, honoring CR/LF breaks. Pair positioning is applied
; only to adjacent glyphs on the same line. Returns 1 on success.
Procedure.i AnvilTrueTypeLayoutUtf8(text.i,byteCount.i,pixelHeight.i,maxWidth.i,lineHeight.i,glyphOut.i,xOut.i,yOut.i,advanceOut.i,alignment.i,capacity.i,glyphCountOut.i,lineCountOut.i,measuredWidthOut.i)
  Protected count.i,unitsPerEm.i,index.i,lineStart.i,lineEnd.i
  Protected metric.i,lsb.i,pen.q,maxWidthFixed.q,lineHeightFixed.q,lineBaseline.q,lineOffset.q
  Protected lines.i,maxMeasured.q,advance.q,position.i,pairResult.i,pendingLines.i
  Protected pairAdvance1.q,pairAdvance2.q
  If glyphCountOut=0 Or lineCountOut=0 Or measuredWidthOut=0 Or capacity<0 Or pixelHeight<=0 Or lineHeight<=0 Or maxWidth<0 Or alignment<0 Or alignment>2
    anvil_ttl_error=#ANVIL_TTL_E_ARGUMENT : ProcedureReturn 0
  EndIf
  If (capacity>0 And (glyphOut=0 Or xOut=0 Or yOut=0 Or advanceOut=0))
    anvil_ttl_error=#ANVIL_TTL_E_ARGUMENT : ProcedureReturn 0
  EndIf
  If pixelHeight>512 Or lineHeight>4096 Or maxWidth>32767
    anvil_ttl_error=#ANVIL_TTL_E_ARGUMENT : ProcedureReturn 0
  EndIf
  If AnvilTrueTypeMetricsOpenState()=0 Or AnvilTrueTypeCmapOpenState()=0
    anvil_ttl_error=#ANVIL_TTL_E_FONT : ProcedureReturn 0
  EndIf
  If AnvilTrueTypeKernOpenState()=0 Or AnvilTrueTypeGposOpenState()=0
    ; Empty kern/GPOS tables are valid open states; malformed present tables
    ; must be reported instead of silently changing placement.
    anvil_ttl_error=#ANVIL_TTL_E_FONT : ProcedureReturn 0
  EndIf
  If capacity>#ANVIL_TTL_MAX_GLYPHS : capacity=#ANVIL_TTL_MAX_GLYPHS : EndIf
  count=anvil_ttl_Decode(text,byteCount,capacity)
  If count<0 : anvil_ttl_error=#ANVIL_TTL_E_CAPACITY : ProcedureReturn 0 : EndIf
  unitsPerEm=AnvilTrueTypeUnitsPerEm()
  If unitsPerEm<=0 : anvil_ttl_error=#ANVIL_TTL_E_FONT : ProcedureReturn 0 : EndIf
  maxWidthFixed=maxWidth*65536 : lineHeightFixed=lineHeight*65536
  For index=0 To count-1
    If AnvilTrueTypeHorizontalMetric(anvil_ttl_glyph[index],@metric,@lsb)=0
      anvil_ttl_error=#ANVIL_TTL_E_FONT : ProcedureReturn 0
    EndIf
    anvil_ttl_advance[index]=anvil_ttl_Scale(metric,pixelHeight,unitsPerEm)
    anvil_ttl_adjustAdvance[index]=0 : anvil_ttl_placeX[index]=0 : anvil_ttl_placeY[index]=0
  Next
  ; Grow each line with its actual pair adjustments. A pair is committed only
  ; when both glyphs stay on this line, so wrapping never leaves cross-line kerning.
  lineStart=0 : position=0 : lines=0 : maxMeasured=0
  While lineStart<count
    lineEnd=lineStart : pen=0 : pendingLines=anvil_ttl_forceBreak[lineStart]
    If pendingLines>0
      If lineStart=0 : lines=lines+pendingLines
      ElseIf pendingLines>1 : lines=lines+pendingLines-1
      EndIf
    EndIf
    While lineEnd<count
      If lineEnd>lineStart And anvil_ttl_forceBreak[lineEnd]>0 : Break : EndIf
      advance=anvil_ttl_advance[lineEnd]
      If lineEnd=lineStart
        pen=advance : lineEnd+1
      Else
        pairResult=AnvilTrueTypePairPosition(anvil_ttl_glyph[lineEnd-1],anvil_ttl_glyph[lineEnd],@anvil_ttl_pairValues[0])
        If pairResult=0 : anvil_ttl_error=#ANVIL_TTL_E_PAIR : ProcedureReturn 0 : EndIf
        pairAdvance1=anvil_ttl_Scale(anvil_ttl_pairValues[2],pixelHeight,unitsPerEm)
        pairAdvance2=anvil_ttl_Scale(anvil_ttl_pairValues[6],pixelHeight,unitsPerEm)
        ; Previous pen already included value1/value2 from earlier pairs.
        ; Add this pair's first advance to the previous glyph and second to this one.
        If maxWidthFixed>0 And pen+pairAdvance1+advance+pairAdvance2>maxWidthFixed
          Break
        EndIf
        anvil_ttl_adjustAdvance[lineEnd-1]=anvil_ttl_adjustAdvance[lineEnd-1]+pairAdvance1
        anvil_ttl_adjustAdvance[lineEnd]=anvil_ttl_adjustAdvance[lineEnd]+pairAdvance2
        anvil_ttl_placeX[lineEnd-1]=anvil_ttl_placeX[lineEnd-1]+anvil_ttl_Scale(anvil_ttl_pairValues[0],pixelHeight,unitsPerEm)
        anvil_ttl_placeY[lineEnd-1]=anvil_ttl_placeY[lineEnd-1]+anvil_ttl_Scale(anvil_ttl_pairValues[1],pixelHeight,unitsPerEm)
        anvil_ttl_placeX[lineEnd]=anvil_ttl_placeX[lineEnd]+anvil_ttl_Scale(anvil_ttl_pairValues[4],pixelHeight,unitsPerEm)
        anvil_ttl_placeY[lineEnd]=anvil_ttl_placeY[lineEnd]+anvil_ttl_Scale(anvil_ttl_pairValues[5],pixelHeight,unitsPerEm)
        pen=pen+pairAdvance1+advance+pairAdvance2
        lineEnd+1
      EndIf
    Wend
    If lineEnd=lineStart : lineEnd+1 : EndIf
    lineOffset=0
    If maxWidthFixed>0 And maxWidthFixed>pen
      If alignment=#ANVIL_TTL_ALIGN_CENTER : lineOffset=(maxWidthFixed-pen)/2
      ElseIf alignment=#ANVIL_TTL_ALIGN_RIGHT : lineOffset=maxWidthFixed-pen
      EndIf
    EndIf
    pen=0
    lineBaseline=-lines*lineHeightFixed
    For index=lineStart To lineEnd-1
      advance=anvil_ttl_advance[index]+anvil_ttl_adjustAdvance[index]
      PokeI(glyphOut+position*SizeOf(.i),anvil_ttl_glyph[index])
      PokeI(xOut+position*SizeOf(.i),lineOffset+pen+anvil_ttl_placeX[index])
      PokeI(yOut+position*SizeOf(.i),lineBaseline+anvil_ttl_placeY[index])
      PokeI(advanceOut+position*SizeOf(.i),advance)
      pen+advance : position+1
    Next
    If pen>maxMeasured : maxMeasured=pen : EndIf
    lines+1
    lineStart=lineEnd
  Wend
  If count=0
    lines=1
    lines=anvil_ttl_trailingBreak+1
  ElseIf anvil_ttl_trailingBreak>0
    lines=lines+anvil_ttl_trailingBreak
  EndIf
  PokeI(glyphCountOut,position) : PokeI(lineCountOut,lines) : PokeI(measuredWidthOut,maxMeasured)
  anvil_ttl_error=#ANVIL_TTL_E_NONE
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeLayoutError()
  ProcedureReturn anvil_ttl_error
EndProcedure
