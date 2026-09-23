; T2 Unicode character mapping. Supports cmap format 4 (BMP) and format 12.
; Caller owns UTF-8 input and glyph-ID output storage.

#ANVIL_TTC_E_NONE = 0
#ANVIL_TTC_E_NOT_OPEN = 1
#ANVIL_TTC_E_TABLE = 2
#ANVIL_TTC_E_FORMAT = 3
#ANVIL_TTC_E_CODEPOINT = 4
#ANVIL_TTC_E_CAPACITY = 5
#ANVIL_TTC_TAG_CMAP = $636D6170

Global anvil_ttc_open.i
Global anvil_ttc_error.i
Global anvil_ttc_revision.i
Global anvil_ttc_errorOffset.i
Global *anvil_ttc_fmt4
Global anvil_ttc_fmt4Length.i
Global *anvil_ttc_fmt12
Global anvil_ttc_fmt12Length.i

Procedure.i anvil_ttc_U8(at.i)
  ProcedureReturn PeekA(at) & $FF
EndProcedure
Procedure.i anvil_ttc_U16(at.i)
  ProcedureReturn (anvil_ttc_U8(at)<<8) | anvil_ttc_U8(at+1)
EndProcedure
Procedure.q anvil_ttc_U32(at.i)
  ProcedureReturn (anvil_ttc_U8(at)<<24) | (anvil_ttc_U8(at+1)<<16) | (anvil_ttc_U8(at+2)<<8) | anvil_ttc_U8(at+3)
EndProcedure
Procedure.i anvil_ttc_S16(at.i)
  Protected v.i=anvil_ttc_U16(at)
  If v & $8000 : v-65536 : EndIf
  ProcedureReturn v
EndProcedure
Procedure.i anvil_ttc_Fail(code.i,offset.i)
  anvil_ttc_open=0 : anvil_ttc_error=code : anvil_ttc_errorOffset=offset
  ProcedureReturn 0
EndProcedure
Procedure.i anvil_ttc_InputFail(code.i,offset.i)
  anvil_ttc_error=code : anvil_ttc_errorOffset=offset
  ProcedureReturn 0
EndProcedure
Procedure.i anvil_ttc_Ready()
  If anvil_ttc_open=0 Or anvil_ttc_revision=0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeRevision()<>anvil_ttc_revision Or AnvilTrueTypeTableCount()<1
    ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_NOT_OPEN,0)
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeCmapClose()
  anvil_ttc_open=0 : anvil_ttc_error=#ANVIL_TTC_E_NONE : anvil_ttc_errorOffset=0
  anvil_ttc_revision=0 : *anvil_ttc_fmt4=0 : *anvil_ttc_fmt12=0
  anvil_ttc_fmt4Length=0 : anvil_ttc_fmt12Length=0
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeCmapOpenState()
  ProcedureReturn anvil_ttc_Ready()
EndProcedure

Procedure.i AnvilTrueTypeCmapOpen()
  Protected index.i, length.i, base.i, version.i, count.i, n.i, rec.i
  Protected platform.i, encoding.i, off.i, fmt.i, sub.i, subLen.i
  Protected best4.i, best12.i, best4Len.i, best12Len.i, rank.i, best4Rank.i, best12Rank.i
  Protected segCount.i, endBase.i, startBase.i, deltaBase.i, rangeBase.i
  Protected prior.i, first.i, last.i, groups.i, groupBase.i, ro.i
  Protected glyphCount.i, glyphStart.q, groupEnd.q
  AnvilTrueTypeCmapClose()
  anvil_ttc_revision=AnvilTrueTypeRevision()
  If AnvilTrueTypeMetricsOpenState()=0 : ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_NOT_OPEN,0) : EndIf
  index=AnvilTrueTypeFind(#ANVIL_TTC_TAG_CMAP)
  If index<0 : ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_TABLE,0) : EndIf
  length=AnvilTrueTypeTableLength(index) : base=AnvilTrueTypeTableData(index)
  If length<4 : ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_TABLE,AnvilTrueTypeTableOffset(index)) : EndIf
  version=anvil_ttc_U16(base) : count=anvil_ttc_U16(base+2)
  If version<>0 Or count<1 Or count>(length-4)/8
    ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index))
  EndIf
  best4=0 : best12=0 : best4Len=0 : best12Len=0 : best4Rank=99 : best12Rank=99
  For n=0 To count-1
    rec=base+4+n*8 : platform=anvil_ttc_U16(rec) : encoding=anvil_ttc_U16(rec+2)
    off=anvil_ttc_U32(rec+4)
    If off<=length-2 And (platform=0 Or (platform=3 And (encoding=1 Or encoding=10)))
      sub=base+off : fmt=anvil_ttc_U16(sub) : subLen=0
      If fmt=4 And off<=length-4 : subLen=anvil_ttc_U16(sub+2) : EndIf
      If fmt=12 And off<=length-8 : subLen=anvil_ttc_U32(sub+4) : EndIf
      If fmt=4 And subLen>=16 And subLen<=length-off
        segCount=anvil_ttc_U16(sub+6)/2
          If segCount>0 And (anvil_ttc_U16(sub+6)&1)=0 And 16+segCount*8<=subLen
          endBase=sub+14 : startBase=endBase+segCount*2+2
          deltaBase=startBase+segCount*2 : rangeBase=deltaBase+segCount*2
          prior=-1
          For groups=0 To segCount-1
            last=anvil_ttc_U16(endBase+groups*2)
            first=anvil_ttc_U16(startBase+groups*2)
            If first>last Or first<=prior
              ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index)+off)
            EndIf
            prior=last
          Next
          If anvil_ttc_U16(endBase+(segCount-1)*2)<>$FFFF Or anvil_ttc_U16(sub+14+segCount*2)<>0
            ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index)+off)
          EndIf
          For groups=0 To segCount-1
            ro=anvil_ttc_U16(rangeBase+groups*2)
            If (ro&1)<>0 : ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index)+off) : EndIf
            If ro<>0 And (rangeBase+groups*2+ro<rangeBase+segCount*2 Or rangeBase+groups*2+ro+2+(anvil_ttc_U16(endBase+groups*2)-anvil_ttc_U16(startBase+groups*2))*2>sub+subLen)
              ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index)+off)
            EndIf
          Next
          rank=2 : If platform=3 And encoding=1 : rank=0 : ElseIf platform=0 : rank=1 : EndIf
          If rank<best4Rank : best4=sub : best4Len=subLen : best4Rank=rank : EndIf
        EndIf
      ElseIf fmt=12 And subLen>=16 And subLen<=length-off
        groups=anvil_ttc_U32(sub+12)
        If groups<=(subLen-16)/12
          prior=-1 : groupBase=sub+16 : glyphCount=AnvilTrueTypeGlyphCount()
          For first=0 To groups-1
            last=anvil_ttc_U32(groupBase+first*12)
            groupEnd=anvil_ttc_U32(groupBase+first*12+4)
            glyphStart=anvil_ttc_U32(groupBase+first*12+8)
            If last>=$110000 Or last<=prior Or groupEnd>=$110000 Or groupEnd<last Or glyphStart+groupEnd-last>=glyphCount
              ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index)+off)
            EndIf
            prior=groupEnd
          Next
          If anvil_ttc_U16(sub+2)<>0 : ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index)+off) : EndIf
          rank=2 : If platform=3 And encoding=10 : rank=0 : ElseIf platform=0 : rank=1 : EndIf
          If rank<best12Rank : best12=sub : best12Len=subLen : best12Rank=rank : EndIf
        EndIf
      EndIf
    EndIf
  Next
  If best4=0 And best12=0 : ProcedureReturn anvil_ttc_Fail(#ANVIL_TTC_E_FORMAT,AnvilTrueTypeTableOffset(index)) : EndIf
  *anvil_ttc_fmt4=best4 : anvil_ttc_fmt4Length=best4Len
  *anvil_ttc_fmt12=best12 : anvil_ttc_fmt12Length=best12Len
  anvil_ttc_error=#ANVIL_TTC_E_NONE : anvil_ttc_errorOffset=0 : anvil_ttc_open=1
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_ttc_Map4(codepoint.i)
  Protected segCount.i, endBase.i, startBase.i, deltaBase.i, rangeBase.i
  Protected n.i, start.i, finish.i, delta.i, range.i, addr.i, glyph.i
  If codepoint<0 Or codepoint>65535 : ProcedureReturn 0 : EndIf
  segCount=anvil_ttc_U16(*anvil_ttc_fmt4+6)/2
  endBase=*anvil_ttc_fmt4+14 : startBase=endBase+segCount*2+2
  deltaBase=startBase+segCount*2 : rangeBase=deltaBase+segCount*2
  For n=0 To segCount-1
    finish=anvil_ttc_U16(endBase+n*2)
    If codepoint<=finish
      start=anvil_ttc_U16(startBase+n*2)
      If codepoint<start : ProcedureReturn 0 : EndIf
      delta=anvil_ttc_S16(deltaBase+n*2) : range=anvil_ttc_U16(rangeBase+n*2)
      If range=0 : ProcedureReturn (codepoint+delta)&$FFFF : EndIf
      addr=rangeBase+n*2+range+(codepoint-start)*2
      If addr<*anvil_ttc_fmt4 Or addr+2>*anvil_ttc_fmt4+anvil_ttc_fmt4Length : ProcedureReturn 0 : EndIf
      glyph=anvil_ttc_U16(addr)
      If glyph<>0 : glyph=(glyph+delta)&$FFFF : EndIf
      ProcedureReturn glyph
    EndIf
  Next
  ProcedureReturn 0
EndProcedure
Procedure.q anvil_ttc_Map12(codepoint.i)
  Protected groups.i, lo.i, hi.i, mid.i, rec.i, first.q, last.q, glyph.q
  groups=anvil_ttc_U32(*anvil_ttc_fmt12+12) : lo=0 : hi=groups-1
  While lo<=hi
    mid=(lo+hi)/2 : rec=*anvil_ttc_fmt12+16+mid*12
    first=anvil_ttc_U32(rec) : last=anvil_ttc_U32(rec+4)
    If codepoint<first : hi=mid-1
    ElseIf codepoint>last : lo=mid+1
    Else
      glyph=anvil_ttc_U32(rec+8)+(codepoint-first)
      If glyph>65535 : ProcedureReturn 0 : EndIf
      ProcedureReturn glyph
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure
Procedure.q AnvilTrueTypeGlyphForCodepoint(codepoint.i)
  Protected glyph.i
  If anvil_ttc_Ready()=0 : ProcedureReturn 0 : EndIf
  anvil_ttc_error=#ANVIL_TTC_E_NONE : anvil_ttc_errorOffset=0
  If codepoint<0 Or codepoint>=$110000 Or (codepoint>=$D800 And codepoint<=$DFFF)
    anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,0) : ProcedureReturn 0
  EndIf
  If *anvil_ttc_fmt12<>0 : glyph=anvil_ttc_Map12(codepoint)
  Else : glyph=anvil_ttc_Map4(codepoint) : EndIf
  If glyph>=AnvilTrueTypeGlyphCount() : ProcedureReturn 0 : EndIf
  ProcedureReturn glyph
EndProcedure
; Decode strict UTF-8 bytes to native-width glyph IDs. Returns the number of
; emitted glyph IDs (0 is a valid empty string); returns -1 on invalid input
; or insufficient capacity. Output is untouched when capacity is inadequate.
Procedure.i AnvilTrueTypeDecodeUtf8(text.i, byteCount.i, glyphOut.i, capacity.i)
  Protected pos.i=0, count.i=0, b0.i, b1.i, b2.i, b3.i, cp.i, need.i
  Protected glyph.i, metricsCount.i
  If anvil_ttc_Ready()=0 : ProcedureReturn -1 : EndIf
  If (byteCount>0 And text=0) Or byteCount<0 Or capacity<0 Or (byteCount>0 And glyphOut=0)
    anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,0) : ProcedureReturn -1
  EndIf
  anvil_ttc_error=#ANVIL_TTC_E_NONE : anvil_ttc_errorOffset=0
  ; First pass validates all bytes and counts codepoints so a short output
  ; buffer cannot leave a partially written glyph sequence.
  While pos<byteCount
    b0=anvil_ttc_U8(text+pos)
    If b0<128 : need=1 : cp=b0
    ElseIf b0>=$C2 And b0<=$DF : need=2 : cp=b0&$1F
    ElseIf b0>=$E0 And b0<=$EF : need=3 : cp=b0&$0F
    ElseIf b0>=$F0 And b0<=$F4 : need=4 : cp=b0&$07
    Else : anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,pos) : ProcedureReturn -1
    EndIf
    If pos+need>byteCount : anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,pos) : ProcedureReturn -1 : EndIf
    If need>=2
      b1=anvil_ttc_U8(text+pos+1)
      If (b1&$C0)<>$80 : anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,pos+1) : ProcedureReturn -1 : EndIf
      If (b0=$E0 And b1<$A0) Or (b0=$ED And b1>=$A0) Or (b0=$F0 And b1<$90) Or (b0=$F4 And b1>=$90)
        anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,pos) : ProcedureReturn -1
      EndIf
      cp=(cp<<6)|(b1&$3F)
    EndIf
    If need>=3
      b2=anvil_ttc_U8(text+pos+2)
      If (b2&$C0)<>$80 : anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,pos+2) : ProcedureReturn -1 : EndIf
      cp=(cp<<6)|(b2&$3F)
    EndIf
    If need=4
      b3=anvil_ttc_U8(text+pos+3)
      If (b3&$C0)<>$80 : anvil_ttc_InputFail(#ANVIL_TTC_E_CODEPOINT,pos+3) : ProcedureReturn -1 : EndIf
      cp=(cp<<6)|(b3&$3F)
    EndIf
    count+1 : pos+need
  Wend
  If count>capacity : anvil_ttc_InputFail(#ANVIL_TTC_E_CAPACITY,byteCount) : ProcedureReturn -1 : EndIf
  metricsCount=AnvilTrueTypeGlyphCount()
  pos=0 : count=0
  While pos<byteCount
    b0=anvil_ttc_U8(text+pos)
    If b0<128 : need=1 : cp=b0
    ElseIf b0<=$DF : need=2 : cp=b0&$1F
    ElseIf b0<=$EF : need=3 : cp=b0&$0F
    Else : need=4 : cp=b0&$07
    EndIf
    If need>=2 : cp=(cp<<6)|(anvil_ttc_U8(text+pos+1)&$3F) : EndIf
    If need>=3 : cp=(cp<<6)|(anvil_ttc_U8(text+pos+2)&$3F) : EndIf
    If need=4 : cp=(cp<<6)|(anvil_ttc_U8(text+pos+3)&$3F) : EndIf
    glyph=AnvilTrueTypeGlyphForCodepoint(cp)
    If AnvilTrueTypeCmapError()<>#ANVIL_TTC_E_NONE : ProcedureReturn -1 : EndIf
    If glyph>=metricsCount : anvil_ttc_InputFail(#ANVIL_TTC_E_FORMAT,pos) : ProcedureReturn -1 : EndIf
    PokeI(glyphOut+count*SizeOf(.i),glyph)
    count+1 : pos+need
  Wend
  ProcedureReturn count
EndProcedure
Procedure.i AnvilTrueTypeCmapError()
  anvil_ttc_Ready() : ProcedureReturn anvil_ttc_error
EndProcedure
Procedure.i AnvilTrueTypeCmapErrorOffset()
  anvil_ttc_Ready() : ProcedureReturn anvil_ttc_errorOffset
EndProcedure
