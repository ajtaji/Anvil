; T1 TrueType font metrics. Include after truetype.pbi.
; Original bounded reader for head/maxp/hhea/hmtx and optional OS/2 metrics.
; It consumes the current T0-open memory font and never changes T0 state.

#ANVIL_TTM_E_NONE = 0
#ANVIL_TTM_E_NOT_OPEN = 1
#ANVIL_TTM_E_TABLE = 2
#ANVIL_TTM_E_FORMAT = 3
#ANVIL_TTM_E_RANGE = 4
#ANVIL_TTM_E_GLYPH = 5

#ANVIL_TT_TAG_HEAD = $68656164
#ANVIL_TT_TAG_MAXP = $6D617870
#ANVIL_TT_TAG_HHEA = $68686561
#ANVIL_TT_TAG_HMTX = $686D7478
#ANVIL_TT_TAG_OS2 = $4F532F32

Global anvil_ttm_open.i
Global anvil_ttm_error.i
Global anvil_ttm_errorTag.i
Global anvil_ttm_errorOffset.i
Global Dim anvil_ttm_errorBuffer.a[96]
Global anvil_ttm_unitsPerEm.i
Global anvil_ttm_indexToLocFormat.i
Global anvil_ttm_glyphCount.i
Global anvil_ttm_ascender.i
Global anvil_ttm_descender.i
Global anvil_ttm_lineGap.i
Global anvil_ttm_numberOfHMetrics.i
Global anvil_ttm_headOffset.i
Global anvil_ttm_maxpOffset.i
Global anvil_ttm_hheaOffset.i
Global anvil_ttm_hmtxOffset.i
Global anvil_ttm_hmtxLength.i
Global anvil_ttm_revision.i
Global *anvil_ttm_head
Global *anvil_ttm_maxp
Global *anvil_ttm_hhea
Global *anvil_ttm_hmtx
Global anvil_ttm_os2Present.i
Global anvil_ttm_os2Version.i
Global anvil_ttm_os2TypoAscender.i
Global anvil_ttm_os2TypoDescender.i
Global anvil_ttm_os2TypoLineGap.i
Global anvil_ttm_os2WinAscent.i
Global anvil_ttm_os2WinDescent.i
Global anvil_ttm_os2WeightClass.i
Global anvil_ttm_os2WidthClass.i

Procedure.i anvil_ttm_U8(at.i)
  ProcedureReturn PeekA(at) & $FF
EndProcedure
Procedure.i anvil_ttm_U16(at.i)
  ProcedureReturn (anvil_ttm_U8(at) << 8) | anvil_ttm_U8(at+1)
EndProcedure
Procedure.i anvil_ttm_U32(at.i)
  ProcedureReturn (anvil_ttm_U8(at)<<24) | (anvil_ttm_U8(at+1)<<16) | (anvil_ttm_U8(at+2)<<8) | anvil_ttm_U8(at+3)
EndProcedure
Procedure.i anvil_ttm_Ready()
  If anvil_ttm_open=0 Or anvil_ttm_revision=0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeRevision()<>anvil_ttm_revision Or AnvilTrueTypeTableCount()<1
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_NOT_OPEN,0,0)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_ttm_S16(at.i)
  Protected value.i
  value = anvil_ttm_U16(at)
  If (value & $8000) <> 0 : value = value - $10000 : EndIf
  ProcedureReturn value
EndProcedure

Procedure.i anvil_ttm_HexDigit(value.i)
  value = value & $F
  If value < 10 : ProcedureReturn 48 + value : EndIf
  ProcedureReturn 55 + value
EndProcedure

Procedure.i anvil_ttm_FormatError()
  Protected pos.i
  Protected n.i
  Dim prefix.a[25]
  ; "TrueType metrics error=0x" (24 bytes), followed by fixed-width fields.
  prefix[0]=84 : prefix[1]=114 : prefix[2]=117 : prefix[3]=101
  prefix[4]=84 : prefix[5]=121 : prefix[6]=112 : prefix[7]=101
  prefix[8]=32 : prefix[9]=109 : prefix[10]=101 : prefix[11]=116
  prefix[12]=114 : prefix[13]=105 : prefix[14]=99 : prefix[15]=115
  prefix[16]=32 : prefix[17]=101 : prefix[18]=114 : prefix[19]=114
  prefix[20]=111 : prefix[21]=114 : prefix[22]=61 : prefix[23]=48
  prefix[24]=120
  pos=0
  For n=0 To 24 : PokeA(@anvil_ttm_errorBuffer[pos],prefix[n]) : pos+1 : Next
  For n=7 To 0 Step -1 : PokeA(@anvil_ttm_errorBuffer[pos],anvil_ttm_HexDigit(anvil_ttm_error>>(n*4))) : pos+1 : Next
  PokeA(@anvil_ttm_errorBuffer[pos],32) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],116) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],97) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],103) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],61) : pos+1
  For n=7 To 0 Step -1 : PokeA(@anvil_ttm_errorBuffer[pos],anvil_ttm_HexDigit(anvil_ttm_errorTag>>(n*4))) : pos+1 : Next
  PokeA(@anvil_ttm_errorBuffer[pos],32) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],111) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],102) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],102) : pos+1
  PokeA(@anvil_ttm_errorBuffer[pos],61) : pos+1
  For n=7 To 0 Step -1 : PokeA(@anvil_ttm_errorBuffer[pos],anvil_ttm_HexDigit(anvil_ttm_errorOffset>>(n*4))) : pos+1 : Next
  PokeA(@anvil_ttm_errorBuffer[pos],0)
  ProcedureReturn pos
EndProcedure

Procedure.i anvil_ttm_Fail(code.i, tag.i, offset.i)
  anvil_ttm_open=0
  anvil_ttm_error=code
  anvil_ttm_errorTag=tag
  anvil_ttm_errorOffset=offset
  anvil_ttm_FormatError()
  ProcedureReturn 0
EndProcedure

Procedure.i AnvilTrueTypeMetricsClose()
  anvil_ttm_open=0
  PokeA(@anvil_ttm_errorBuffer[0],0)
  anvil_ttm_revision=0
  *anvil_ttm_head=0 : *anvil_ttm_maxp=0 : *anvil_ttm_hhea=0 : *anvil_ttm_hmtx=0
  anvil_ttm_error=#ANVIL_TTM_E_NONE
  anvil_ttm_errorTag=0
  anvil_ttm_errorOffset=0
  anvil_ttm_unitsPerEm=0
  anvil_ttm_indexToLocFormat=0
  anvil_ttm_glyphCount=0
  anvil_ttm_ascender=0
  anvil_ttm_descender=0
  anvil_ttm_lineGap=0
  anvil_ttm_numberOfHMetrics=0
  anvil_ttm_hmtxOffset=0
  anvil_ttm_hmtxLength=0
  anvil_ttm_os2Present=0
  anvil_ttm_os2Version=0
  anvil_ttm_os2TypoAscender=0
  anvil_ttm_os2TypoDescender=0
  anvil_ttm_os2TypoLineGap=0
  anvil_ttm_os2WinAscent=0
  anvil_ttm_os2WinDescent=0
  anvil_ttm_os2WeightClass=0
  anvil_ttm_os2WidthClass=0
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeMetricsOpen()
  Protected headIndex.i
  Protected maxpIndex.i
  Protected hheaIndex.i
  Protected hmtxIndex.i
  Protected os2Index.i
  Protected headLength.i
  Protected maxpLength.i
  Protected hheaLength.i
  Protected hmtxLength.i
  Protected os2Length.i
  Protected head.i
  Protected maxp.i
  Protected hhea.i
  Protected hmtx.i
  Protected os2.i
  Protected os2Offset.i
  Protected revision.i
  Protected need.i
  Protected version.i

  AnvilTrueTypeMetricsClose()
  revision=AnvilTrueTypeRevision()
  If AnvilTrueTypeTableCount()<1 Or AnvilTrueTypeError()<>0
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_NOT_OPEN,0,0)
  EndIf
  headIndex=AnvilTrueTypeFind(#ANVIL_TT_TAG_HEAD)
  maxpIndex=AnvilTrueTypeFind(#ANVIL_TT_TAG_MAXP)
  hheaIndex=AnvilTrueTypeFind(#ANVIL_TT_TAG_HHEA)
  hmtxIndex=AnvilTrueTypeFind(#ANVIL_TT_TAG_HMTX)
  If headIndex<0 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_HEAD,0) : EndIf
  If maxpIndex<0 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_MAXP,0) : EndIf
  If hheaIndex<0 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_HHEA,0) : EndIf
  If hmtxIndex<0 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_HMTX,0) : EndIf
  headLength=AnvilTrueTypeTableLength(headIndex)
  maxpLength=AnvilTrueTypeTableLength(maxpIndex)
  hheaLength=AnvilTrueTypeTableLength(hheaIndex)
  hmtxLength=AnvilTrueTypeTableLength(hmtxIndex)
  head=AnvilTrueTypeTableData(headIndex)
  maxp=AnvilTrueTypeTableData(maxpIndex)
  hhea=AnvilTrueTypeTableData(hheaIndex)
  hmtx=AnvilTrueTypeTableData(hmtxIndex)
  anvil_ttm_headOffset=AnvilTrueTypeTableOffset(headIndex)
  anvil_ttm_maxpOffset=AnvilTrueTypeTableOffset(maxpIndex)
  anvil_ttm_hheaOffset=AnvilTrueTypeTableOffset(hheaIndex)
  anvil_ttm_hmtxOffset=AnvilTrueTypeTableOffset(hmtxIndex)
  If headLength<54 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_HEAD,anvil_ttm_headOffset) : EndIf
  If maxpLength<6 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_MAXP,anvil_ttm_maxpOffset) : EndIf
  If hheaLength<36 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_HHEA,anvil_ttm_hheaOffset) : EndIf
  If anvil_ttm_U32(head)<>$00010000 Or anvil_ttm_U32(head+12)<>$5F0F3CF5 Or anvil_ttm_S16(head+52)<>0
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_FORMAT,#ANVIL_TT_TAG_HEAD,anvil_ttm_headOffset)
  EndIf
  version=anvil_ttm_U32(maxp)
  If version<>$00010000 Or maxpLength<32
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_FORMAT,#ANVIL_TT_TAG_MAXP,anvil_ttm_maxpOffset)
  EndIf
  If anvil_ttm_U32(hhea)<>$00010000 Or anvil_ttm_S16(hhea+32)<>0
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_FORMAT,#ANVIL_TT_TAG_HHEA,anvil_ttm_hheaOffset)
  EndIf
  anvil_ttm_unitsPerEm=anvil_ttm_U16(head+18)
  anvil_ttm_indexToLocFormat=anvil_ttm_S16(head+50)
  anvil_ttm_glyphCount=anvil_ttm_U16(maxp+4)
  anvil_ttm_numberOfHMetrics=anvil_ttm_U16(hhea+34)
  anvil_ttm_ascender=anvil_ttm_S16(hhea+4)
  anvil_ttm_descender=anvil_ttm_S16(hhea+6)
  anvil_ttm_lineGap=anvil_ttm_S16(hhea+8)
  If anvil_ttm_unitsPerEm<16 Or anvil_ttm_unitsPerEm>16384
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_RANGE,#ANVIL_TT_TAG_HEAD,anvil_ttm_headOffset+18)
  EndIf
  If anvil_ttm_indexToLocFormat<>0 And anvil_ttm_indexToLocFormat<>1
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_FORMAT,#ANVIL_TT_TAG_HEAD,anvil_ttm_headOffset+50)
  EndIf
  If anvil_ttm_glyphCount<1 Or anvil_ttm_numberOfHMetrics<1 Or anvil_ttm_numberOfHMetrics>anvil_ttm_glyphCount
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_RANGE,#ANVIL_TT_TAG_HHEA,anvil_ttm_hheaOffset+34)
  EndIf
  need=anvil_ttm_numberOfHMetrics*4+(anvil_ttm_glyphCount-anvil_ttm_numberOfHMetrics)*2
  If need>hmtxLength
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_HMTX,anvil_ttm_hmtxOffset)
  EndIf
  anvil_ttm_os2Present=0
  os2Index=AnvilTrueTypeFind(#ANVIL_TT_TAG_OS2)
  If os2Index>=0
    os2Length=AnvilTrueTypeTableLength(os2Index)
    os2=AnvilTrueTypeTableData(os2Index)
    os2Offset=AnvilTrueTypeTableOffset(os2Index)
    If os2Length<2 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_OS2,os2Offset) : EndIf
    anvil_ttm_os2Version=anvil_ttm_U16(os2)
    If anvil_ttm_os2Version>5 : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_FORMAT,#ANVIL_TT_TAG_OS2,os2Offset) : EndIf
    need=78
    If anvil_ttm_os2Version=1 : need=86 : EndIf
    If anvil_ttm_os2Version>=2 And anvil_ttm_os2Version<=4 : need=96 : EndIf
    If anvil_ttm_os2Version=5 : need=100 : EndIf
    If os2Length<need : ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_TABLE,#ANVIL_TT_TAG_OS2,os2Offset) : EndIf
    anvil_ttm_os2WeightClass=anvil_ttm_U16(os2+4)
    anvil_ttm_os2WidthClass=anvil_ttm_U16(os2+6)
    anvil_ttm_os2TypoAscender=anvil_ttm_S16(os2+68)
    anvil_ttm_os2TypoDescender=anvil_ttm_S16(os2+70)
    anvil_ttm_os2TypoLineGap=anvil_ttm_S16(os2+72)
    anvil_ttm_os2WinAscent=anvil_ttm_U16(os2+74)
    anvil_ttm_os2WinDescent=anvil_ttm_U16(os2+76)
    anvil_ttm_os2Present=1
  EndIf
  *anvil_ttm_head=head
  *anvil_ttm_maxp=maxp
  *anvil_ttm_hhea=hhea
  *anvil_ttm_hmtx=hmtx
  anvil_ttm_hmtxLength=hmtxLength
  anvil_ttm_error=#ANVIL_TTM_E_NONE
  anvil_ttm_errorTag=0
  anvil_ttm_errorOffset=0
  PokeA(@anvil_ttm_errorBuffer[0],0)
  anvil_ttm_revision=revision
  anvil_ttm_open=1
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeHorizontalMetric(glyph.i, advanceOut.i, lsbOut.i)
  Protected pos.i
  Protected advance.i
  Protected lsb.i
  If anvil_ttm_Ready()=0
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_NOT_OPEN,#ANVIL_TT_TAG_HMTX,anvil_ttm_hmtxOffset)
  EndIf
  If glyph<0 Or glyph>=anvil_ttm_glyphCount
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_GLYPH,#ANVIL_TT_TAG_HMTX,anvil_ttm_hmtxOffset)
  EndIf
  If advanceOut=0 Or lsbOut=0
    ProcedureReturn anvil_ttm_Fail(#ANVIL_TTM_E_RANGE,#ANVIL_TT_TAG_HMTX,anvil_ttm_hmtxOffset)
  EndIf
  If glyph<anvil_ttm_numberOfHMetrics
    pos=*anvil_ttm_hmtx+glyph*4
    advance=anvil_ttm_U16(pos)
    lsb=anvil_ttm_S16(pos+2)
  Else
    pos=*anvil_ttm_hmtx+(anvil_ttm_numberOfHMetrics-1)*4
    advance=anvil_ttm_U16(pos)
    pos=*anvil_ttm_hmtx+anvil_ttm_numberOfHMetrics*4+(glyph-anvil_ttm_numberOfHMetrics)*2
    lsb=anvil_ttm_S16(pos)
  EndIf
  PokeI(advanceOut,advance)
  PokeI(lsbOut,lsb)
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeMetricsOpenState()
  ProcedureReturn anvil_ttm_Ready()
EndProcedure
Procedure.i AnvilTrueTypeUnitsPerEm()
  If anvil_ttm_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_unitsPerEm
EndProcedure
Procedure.i AnvilTrueTypeIndexToLocFormat()
  If anvil_ttm_Ready()=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn anvil_ttm_indexToLocFormat
EndProcedure
Procedure.i AnvilTrueTypeGlyphCount()
  If anvil_ttm_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_glyphCount
EndProcedure
Procedure.i AnvilTrueTypeAscender()
  If anvil_ttm_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_ascender
EndProcedure
Procedure.i AnvilTrueTypeDescender()
  If anvil_ttm_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_descender
EndProcedure
Procedure.i AnvilTrueTypeLineGap()
  If anvil_ttm_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_lineGap
EndProcedure
Procedure.i AnvilTrueTypeNumberOfHMetrics()
  If anvil_ttm_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_numberOfHMetrics
EndProcedure
Procedure.i AnvilTrueTypeHasOS2()
  If anvil_ttm_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2Present
EndProcedure
Procedure.i AnvilTrueTypeOS2Version()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn -1 : EndIf
  ProcedureReturn anvil_ttm_os2Version
EndProcedure
Procedure.i AnvilTrueTypeOS2TypoAscender()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2TypoAscender
EndProcedure
Procedure.i AnvilTrueTypeOS2TypoDescender()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2TypoDescender
EndProcedure
Procedure.i AnvilTrueTypeOS2TypoLineGap()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2TypoLineGap
EndProcedure
Procedure.i AnvilTrueTypeOS2WinAscent()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2WinAscent
EndProcedure
Procedure.i AnvilTrueTypeOS2WinDescent()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2WinDescent
EndProcedure
Procedure.i AnvilTrueTypeOS2WeightClass()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2WeightClass
EndProcedure
Procedure.i AnvilTrueTypeOS2WidthClass()
  If anvil_ttm_Ready()=0 Or anvil_ttm_os2Present=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_ttm_os2WidthClass
EndProcedure
Procedure.i AnvilTrueTypeMetricsError()
  anvil_ttm_Ready()
  ProcedureReturn anvil_ttm_error
EndProcedure
Procedure.i AnvilTrueTypeMetricsErrorTag()
  anvil_ttm_Ready()
  ProcedureReturn anvil_ttm_errorTag
EndProcedure
Procedure.i AnvilTrueTypeMetricsErrorOffset()
  anvil_ttm_Ready()
  ProcedureReturn anvil_ttm_errorOffset
EndProcedure
Procedure.i AnvilTrueTypeMetricsErrorText()
  anvil_ttm_Ready()
  ProcedureReturn @anvil_ttm_errorBuffer[0]
EndProcedure
