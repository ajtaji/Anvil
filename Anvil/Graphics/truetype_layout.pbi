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

; Caret snapshots are opt-in and invalidated by every layout attempt. They
; retain pen positions, not glyph placement offsets or raster bearings.
Global anvil_ttl_wantCarets.i,anvil_ttl_caretCount.i=-1
Global Dim anvil_ttl_penX.q[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_penY.q[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_penEnd.q[#ANVIL_TTL_MAX_GLYPHS]
Global Dim anvil_ttl_caretX.q[#ANVIL_TTL_MAX_GLYPHS+1]
Global Dim anvil_ttl_caretY.q[#ANVIL_TTL_MAX_GLYPHS+1]
Global Dim anvil_ttl_caretByte.i[#ANVIL_TTL_MAX_GLYPHS+1]
Global anvil_ttl_caretLineHeight.i


Procedure.q anvil_ttl_Scale(value.i,pixels.i,unitsPerEm.i)
  Protected scaled.q=value
  scaled=scaled*pixels*65536
  ProcedureReturn scaled/unitsPerEm
EndProcedure

; Convert signed font units to signed 16.16 pixels, truncating toward zero.
; This pure public operation does not select a face or alter layout state.
; Accept signed 32-bit metric values, 1..512 pixels and 1..65535 units/em;
; these bounds keep the intermediate product inside signed 64-bit arithmetic.
; resultOut must name eight writable, aligned bytes owned by the caller.
; Return 1 on success. Refuse invalid arguments with 0 and no output write.
Procedure.i AnvilTrueTypeScaleMetric(value.i,pixels.i,unitsPerEm.i,resultOut.i)
  If resultOut<=0 Or (resultOut&7)<>0 : ProcedureReturn 0 : EndIf
  If value<(-2147483647-1) Or value>2147483647 : ProcedureReturn 0 : EndIf
  If pixels<1 Or pixels>512 Or unitsPerEm<1 Or unitsPerEm>65535 : ProcedureReturn 0 : EndIf
  PokeI(resultOut,anvil_ttl_Scale(value,pixels,unitsPerEm))
  ProcedureReturn 1
EndProcedure

; Convert a previously validated UTF-8 stream to glyphs and forced-break
; markers. CRLF is one break; CR and LF are omitted from the drawable run.
Procedure.i anvil_ttl_Decode(text.i,byteCount.i,capacity.i,controlMode.i)
  Protected decoded.i,sourceIndex.i,sourcePos.i,b0.i,need.i,pendingBreak.i
  decoded=AnvilTrueTypeDecodeUtf8Controls(text,byteCount,@anvil_ttl_glyph[0],capacity,controlMode)
  If decoded<0 : ProcedureReturn -1 : EndIf
  If controlMode<>#ANVIL_TTC_CONTROLS_LEGACY
    anvil_ttl_count=decoded : anvil_ttl_trailingBreak=0
    For sourceIndex=0 To decoded-1 : anvil_ttl_forceBreak[sourceIndex]=0 : Next
    ProcedureReturn decoded
  EndIf
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
Procedure.i anvil_ttl_Layout(text.i,byteCount.i,pixelHeight.i,maxWidth.i,lineHeight.i,glyphOut.i,xOut.i,yOut.i,advanceOut.i,alignment.i,capacity.i,glyphCountOut.i,lineCountOut.i,measuredWidthOut.i,fixedAdvanceQ16.i,controlMode.i)
  Protected count.i,unitsPerEm.i,index.i,lineStart.i,lineEnd.i
  Protected metric.i,lsb.i,pen.q,maxWidthFixed.q,lineHeightFixed.q,lineBaseline.q,lineOffset.q
  Protected lines.i,maxMeasured.q,advance.q,position.i,pairResult.i,pendingLines.i
  Protected pairAdvance1.q,pairAdvance2.q,pairStep.q,pairIndex.i
  anvil_ttl_caretCount=-1
  If glyphCountOut=0 Or lineCountOut=0 Or measuredWidthOut=0 Or capacity<0 Or pixelHeight<=0 Or lineHeight<=0 Or maxWidth<0 Or alignment<0 Or alignment>2
    anvil_ttl_error=#ANVIL_TTL_E_ARGUMENT : ProcedureReturn 0
  EndIf
  If (capacity>0 And (glyphOut=0 Or xOut=0 Or yOut=0 Or advanceOut=0))
    anvil_ttl_error=#ANVIL_TTL_E_ARGUMENT : ProcedureReturn 0
  EndIf
  If pixelHeight>512 Or lineHeight>4096 Or maxWidth>32767 Or fixedAdvanceQ16<0 Or fixedAdvanceQ16>536870912 Or controlMode<0 Or controlMode>2
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
  count=anvil_ttl_Decode(text,byteCount,capacity,controlMode)
  If count<0 : anvil_ttl_error=#ANVIL_TTL_E_CAPACITY : ProcedureReturn 0 : EndIf
  unitsPerEm=AnvilTrueTypeUnitsPerEm()
  If unitsPerEm<=0 : anvil_ttl_error=#ANVIL_TTL_E_FONT : ProcedureReturn 0 : EndIf
  maxWidthFixed=maxWidth*65536 : lineHeightFixed=lineHeight*65536
  For index=0 To count-1
    If fixedAdvanceQ16>0
      anvil_ttl_advance[index]=fixedAdvanceQ16
    ElseIf anvil_ttl_glyph[index]=#ANVIL_TTC_CONTROL_GLYPH
      anvil_ttl_advance[index]=AnvilTrueTypeControlAdvance(pixelHeight)
    Else
      If AnvilTrueTypeHorizontalMetric(anvil_ttl_glyph[index],@metric,@lsb)=0
        anvil_ttl_error=#ANVIL_TTL_E_FONT : ProcedureReturn 0
      EndIf
      anvil_ttl_advance[index]=anvil_ttl_Scale(metric,pixelHeight,unitsPerEm)
    EndIf
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
      ElseIf fixedAdvanceQ16>0
        ; Fixed cells deliberately have no pair positioning. Keep wrapping,
        ; forced breaks and alignment in this same layout owner.
        If maxWidthFixed>0 And pen+advance>maxWidthFixed : Break : EndIf
        pen=pen+advance : lineEnd+1
      Else
        ; The pair API may report a valid no-match without writing all
        ; eight fields. Clear the last pair's offsets before every query.
        For pairIndex=0 To 7 : anvil_ttl_pairValues[pairIndex]=0 : Next
        pairResult=1
        If anvil_ttl_glyph[lineEnd-1]<>#ANVIL_TTC_CONTROL_GLYPH And anvil_ttl_glyph[lineEnd]<>#ANVIL_TTC_CONTROL_GLYPH
          pairResult=AnvilTrueTypePairPosition(anvil_ttl_glyph[lineEnd-1],anvil_ttl_glyph[lineEnd],@anvil_ttl_pairValues[0])
        EndIf
        If pairResult=0 : anvil_ttl_error=#ANVIL_TTL_E_PAIR : ProcedureReturn 0 : EndIf
        pairAdvance1=anvil_ttl_Scale(anvil_ttl_pairValues[2],pixelHeight,unitsPerEm)
        pairAdvance2=anvil_ttl_Scale(anvil_ttl_pairValues[6],pixelHeight,unitsPerEm)
        pairStep=pairAdvance1+advance+pairAdvance2
        ; A combining mark can legitimately have zero hmtx advance and
        ; leave the pen in place. A negative or screen-wide pair step is
        ; invalid here and must still be reported.
        If pairStep<0 Or pairStep>pixelHeight*4*65536
          anvil_ttl_error=#ANVIL_TTL_E_PAIR : ProcedureReturn 0
        EndIf
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
      If anvil_ttl_wantCarets<>0
        anvil_ttl_penX[position]=lineOffset+pen
        anvil_ttl_penY[position]=lineBaseline
        anvil_ttl_penEnd[position]=lineOffset+pen+advance
      EndIf
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

; Original proportional entry point retains pair positioning and metrics.
Procedure.i AnvilTrueTypeLayoutUtf8(text.i,byteCount.i,pixelHeight.i,maxWidth.i,lineHeight.i,glyphOut.i,xOut.i,yOut.i,advanceOut.i,alignment.i,capacity.i,glyphCountOut.i,lineCountOut.i,measuredWidthOut.i)
  ProcedureReturn anvil_ttl_Layout(text,byteCount,pixelHeight,maxWidth,lineHeight,glyphOut,xOut,yOut,advanceOut,alignment,capacity,glyphCountOut,lineCountOut,measuredWidthOut,0,0)
EndProcedure

; Explicit cell advance in Q16 pixels, 0 for the original proportional path,
; positive through8192pixels for fixed cells. CR/LF/wrapping/alignment and UTF8
; decoding retain the original owner. Raster bearings remain caller-owned;
; fixed spacing never scales glyph ink. Serialized with the existing parser.
Procedure.i AnvilTrueTypeLayoutUtf8Fixed(text.i,byteCount.i,pixelHeight.i,maxWidth.i,lineHeight.i,glyphOut.i,xOut.i,yOut.i,advanceOut.i,alignment.i,capacity.i,glyphCountOut.i,lineCountOut.i,measuredWidthOut.i,fixedAdvanceQ16.i)
  ProcedureReturn anvil_ttl_Layout(text,byteCount,pixelHeight,maxWidth,lineHeight,glyphOut,xOut,yOut,advanceOut,alignment,capacity,glyphCountOut,lineCountOut,measuredWidthOut,fixedAdvanceQ16,0)
EndProcedure

; Explicit legacy/hide/show controls, sharing UTF8/layout/kerning/wrapping.
Procedure.i AnvilTrueTypeLayoutUtf8Controls(text.i,byteCount.i,pixelHeight.i,maxWidth.i,lineHeight.i,glyphOut.i,xOut.i,yOut.i,advanceOut.i,alignment.i,capacity.i,glyphCountOut.i,lineCountOut.i,measuredWidthOut.i,fixedAdvanceQ16.i,controlMode.i)
  ProcedureReturn anvil_ttl_Layout(text,byteCount,pixelHeight,maxWidth,lineHeight,glyphOut,xOut,yOut,advanceOut,alignment,capacity,glyphCountOut,lineCountOut,measuredWidthOut,fixedAdvanceQ16,controlMode)
EndProcedure

Procedure.i AnvilTrueTypeLayoutError()
  ProcedureReturn anvil_ttl_error
EndProcedure

; Same layout and glyph outputs, with a source-scalar caret snapshot. Callers
; serialize this with the parser and consume/copy the snapshot before another
; layout. At most2048 source scalars, including hidden controls. CRLF keeps two
; source columns but one line break. A wrap boundary belongs to the next line.
Procedure.i AnvilTrueTypeLayoutCaretUtf8(text.i,byteCount.i,pixelHeight.i,maxWidth.i,lineHeight.i,glyphOut.i,xOut.i,yOut.i,advanceOut.i,alignment.i,capacity.i,glyphCountOut.i,lineCountOut.i,measuredWidthOut.i,fixedAdvanceQ16.i,controlMode.i)
  Protected rc.i,pos.i,column.i,glyph.i,b0.i,need.i,previous.i=-1,pending.i,j.i
  Protected x.q,y.q
  anvil_ttl_caretCount=-1
  ; A byte bound also bounds validation time, without changing normal layout.
  If byteCount<0 Or byteCount>#ANVIL_TTL_MAX_GLYPHS*4
    anvil_ttl_error=#ANVIL_TTL_E_CAPACITY : ProcedureReturn 0
  EndIf
  ; Validate and count scalars before layout writes any caller output. Use the
  ; existing decoder in legacy mode so hidden controls still count here.
  rc=AnvilTrueTypeDecodeUtf8Controls(text,byteCount,@anvil_ttl_glyph[0],#ANVIL_TTL_MAX_GLYPHS,#ANVIL_TTC_CONTROLS_LEGACY)
  If rc<0 : anvil_ttl_error=#ANVIL_TTL_E_CAPACITY : ProcedureReturn 0 : EndIf
  anvil_ttl_wantCarets=1
  rc=anvil_ttl_Layout(text,byteCount,pixelHeight,maxWidth,lineHeight,glyphOut,xOut,yOut,advanceOut,alignment,capacity,glyphCountOut,lineCountOut,measuredWidthOut,fixedAdvanceQ16,controlMode)
  anvil_ttl_wantCarets=0
  If rc=0 : ProcedureReturn 0 : EndIf
  anvil_ttl_caretLineHeight=lineHeight*65536
  anvil_ttl_caretX[0]=0 : anvil_ttl_caretY[0]=0 : anvil_ttl_caretByte[0]=0
  ; Input is already strictly validated. Only byte width and ASCII controls
  ; are needed to associate original scalar columns with drawable glyphs.
  While pos<byteCount
    b0=PeekA(text+pos)&$FF
    If b0<128 : need=1
    ElseIf b0<$E0 : need=2
    ElseIf b0<$F0 : need=3
    Else : need=4
    EndIf
    If controlMode=#ANVIL_TTC_CONTROLS_LEGACY And (b0=13 Or b0=10)
      If b0<>10 Or previous<>13 : y-anvil_ttl_caretLineHeight : EndIf
      x=0 : pending=column+1
    ElseIf controlMode=#ANVIL_TTC_CONTROLS_HIDE And (b0<32 Or b0=127)
      ; Hidden scalars keep distinct source columns at the same pen position.
    Else
      x=anvil_ttl_penX[glyph] : y=anvil_ttl_penY[glyph]
      ; Leading hidden columns follow alignment/wrapping of the next glyph.
      For j=pending To column
        anvil_ttl_caretX[j]=x : anvil_ttl_caretY[j]=y
      Next
      x=anvil_ttl_penEnd[glyph] : glyph+1 : pending=column+1
    EndIf
    column+1 : pos+need : previous=b0
    anvil_ttl_caretX[column]=x : anvil_ttl_caretY[column]=y : anvil_ttl_caretByte[column]=pos
  Wend
  anvil_ttl_caretCount=column+1
  ProcedureReturn 1
EndProcedure

; Number of boundaries (scalar count+1), or-1 if no valid snapshot remains.
Procedure.i AnvilTrueTypeCaretCount()
  ProcedureReturn anvil_ttl_caretCount
EndProcedure

; Q16 source-space pen X and baseline Y, plus original UTF8 byte offset.
; Three distinct aligned caller-owned words; refused calls write nothing.
Procedure.i AnvilTrueTypeCaretPoint(column.i,xOut.i,yOut.i,byteOut.i)
  If column<0 Or column>=anvil_ttl_caretCount : ProcedureReturn 0 : EndIf
  If xOut<=0 Or yOut<=0 Or byteOut<=0 Or ((xOut|yOut|byteOut)&7)<>0 : ProcedureReturn 0 : EndIf
  If xOut=yOut Or xOut=byteOut Or yOut=byteOut : ProcedureReturn 0 : EndIf
  PokeI(xOut,anvil_ttl_caretX[column]) : PokeI(yOut,anvil_ttl_caretY[column])
  PokeI(byteOut,anvil_ttl_caretByte[column])
  ProcedureReturn 1
EndProcedure

; Explicit zero-based line. Nearest source boundary; ties choose the later
; column, including zero-advance controls. No available boundary returns-1.
Procedure.i AnvilTrueTypeCaretColumnForX(line.i,xQ16.q)
  Protected i.i,best.i=-1,y.q,distance.q,bestDistance.q=$7FFFFFFFFFFFFFFF
  If line<0 Or line>#ANVIL_TTL_MAX_GLYPHS Or anvil_ttl_caretCount<1 : ProcedureReturn -1 : EndIf
  If xQ16<-$10000000000 Or xQ16>$10000000000 : ProcedureReturn -1 : EndIf
  y=-line*anvil_ttl_caretLineHeight
  For i=0 To anvil_ttl_caretCount-1
    If anvil_ttl_caretY[i]=y
      distance=xQ16-anvil_ttl_caretX[i]
      If distance<0 : distance=-distance : EndIf
      If distance<=bestDistance : bestDistance=distance : best=i : EndIf
    EndIf
  Next
  ProcedureReturn best
EndProcedure
