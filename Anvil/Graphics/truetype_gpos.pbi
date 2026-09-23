; Bounded OpenType GPOS `kern` feature reader for PairPos formats 1 and 2.
; Pair output is eight signed design-unit values in ValueRecord order:
; xPlacement1,yPlacement1,xAdvance1,yAdvance1,xPlacement2,yPlacement2,
; xAdvance2,yAdvance2. Device/variation deltas are range-checked but not
; evaluated; this API returns the default design-unit values. Pair lookups
; with nonzero LookupFlags are skipped because mark-filtering needs GDEF.

#ANVIL_TG_E_NONE = 0
#ANVIL_TG_E_NOT_OPEN = 1
#ANVIL_TG_E_TABLE = 2
#ANVIL_TG_E_FORMAT = 3
#ANVIL_TG_E_GLYPH = 4
#ANVIL_TG_E_CAPACITY = 5
#ANVIL_TG_E_UNSUPPORTED = 6
#ANVIL_TG_MAX_LOOKUPS = 64
#ANVIL_TG_MAX_PAIRPOS = 128
#ANVIL_TG_MAX_PAIR_WORK = 65536
#ANVIL_TG_MAX_MATRIX_CELLS = 65536
#ANVIL_TG_TAG_GPOS = $47504F53
#ANVIL_TG_TAG_KERN = $6B65726E
#ANVIL_TG_TAG_LATN = $6C61746E
#ANVIL_TG_TAG_DFLT = $44464C54

Global anvil_tg_open.i
Global anvil_tg_revision.i
Global anvil_tg_error.i
Global anvil_tg_errorOffset.i
Global *anvil_tg_font
Global anvil_tg_length.i
Global anvil_tg_fontOffset.i
Global anvil_tg_glyphCount.i
Global anvil_tg_lookups.i
Global Dim anvil_tg_lookupOrder.i[#ANVIL_TG_MAX_LOOKUPS]
Global anvil_tg_pairpos.i
Global anvil_tg_kernFeature.i
Global anvil_tg_unresolved.i
Global Dim anvil_tg_pairOffset.i[#ANVIL_TG_MAX_PAIRPOS]
Global Dim anvil_tg_pairLookup.i[#ANVIL_TG_MAX_PAIRPOS]
Global Dim anvil_tg_pairFormat.i[#ANVIL_TG_MAX_PAIRPOS]
Global Dim anvil_tg_pairValue1.i[#ANVIL_TG_MAX_PAIRPOS]
Global Dim anvil_tg_pairValue2.i[#ANVIL_TG_MAX_PAIRPOS]

Procedure.i anvil_tg_U8(at.i)
  ProcedureReturn PeekA(at)&$FF
EndProcedure
Procedure.i anvil_tg_U16(at.i)
  ProcedureReturn (anvil_tg_U8(at)<<8)|anvil_tg_U8(at+1)
EndProcedure
Procedure.i anvil_tg_S16(at.i)
  Protected value.i=anvil_tg_U16(at)
  If value&$8000 : value-65536 : EndIf
  ProcedureReturn value
EndProcedure
Procedure.q anvil_tg_U32(at.i)
  ProcedureReturn (anvil_tg_U8(at)<<24)|(anvil_tg_U8(at+1)<<16)|(anvil_tg_U8(at+2)<<8)|anvil_tg_U8(at+3)
EndProcedure
Procedure.i anvil_tg_Span(offset.i,size.i)
  If offset<0 Or size<0 Or offset>anvil_tg_length Or size>anvil_tg_length-offset : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i anvil_tg_PopCount(value.i)
  Protected count.i=0, bit.i
  For bit=0 To 7 : If value&(1<<bit) : count+1 : EndIf : Next
  ProcedureReturn count
EndProcedure
Procedure.i anvil_tg_Fail(code.i,offset.i)
  anvil_tg_open=0 : anvil_tg_error=code : anvil_tg_errorOffset=offset : ProcedureReturn 0
EndProcedure
Procedure.i anvil_tg_Ready()
  If anvil_tg_open=0 Or anvil_tg_revision=0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeRevision()<>anvil_tg_revision Or AnvilTrueTypeMetricsOpenState()=0
    ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_NOT_OPEN,0)
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeGposClose()
  anvil_tg_open=0 : anvil_tg_revision=0 : anvil_tg_error=#ANVIL_TG_E_NONE : anvil_tg_errorOffset=0
  *anvil_tg_font=0 : anvil_tg_length=0 : anvil_tg_fontOffset=0 : anvil_tg_glyphCount=0
  anvil_tg_lookups=0 : anvil_tg_pairpos=0 : anvil_tg_kernFeature=0 : anvil_tg_unresolved=0
  ProcedureReturn 1
EndProcedure

; Decode/validate one ValueRecord. Returns byte size; writes its four signed
; design-unit fields when `values` points to four native integers.
Procedure.i anvil_tg_ValueRecord(offset.i,format.i,relativeBase.i,values.i)
  Protected pos.i=offset, field.i, device.i, slot.i=0, startSize.i, endSize.i, deviceFormat.i, words.i
  If format&$FF00 : ProcedureReturn -1 : EndIf
  For field=0 To 7
    If format&(1<<field)
      If anvil_tg_Span(pos,2)=0 : ProcedureReturn -1 : EndIf
      If field<4
        If values<>0 : PokeI(values+field*SizeOf(.i),anvil_tg_S16(*anvil_tg_font+pos)) : EndIf
      Else
        device=anvil_tg_U16(*anvil_tg_font+pos)
        If device<>0
          device=device+relativeBase
          If anvil_tg_Span(device,6)=0 : ProcedureReturn -1 : EndIf
          startSize=anvil_tg_U16(*anvil_tg_font+device)
          endSize=anvil_tg_U16(*anvil_tg_font+device+2)
          deviceFormat=anvil_tg_U16(*anvil_tg_font+device+4)
          If (deviceFormat<>$8000 And endSize<startSize) Or (deviceFormat<>1 And deviceFormat<>2 And deviceFormat<>3 And deviceFormat<>$8000) : ProcedureReturn -1 : EndIf
          If deviceFormat=$8000
            If anvil_tg_Span(device+6,0)=0 : ProcedureReturn -1 : EndIf
          Else
            If deviceFormat=1 : words=(endSize-startSize+1+7)/8
            ElseIf deviceFormat=2 : words=(endSize-startSize+1+3)/4
            Else : words=(endSize-startSize+1+1)/2 : EndIf
            If anvil_tg_Span(device+6,words*2)=0 : ProcedureReturn -1 : EndIf
          EndIf
        EndIf
      EndIf
      pos+2 : slot+1
    EndIf
  Next
  ProcedureReturn slot*2
EndProcedure

; Return coverage glyph count or -1. Supports Coverage formats 1 and 2.
Procedure.i anvil_tg_CoverageCount(offset.i)
  Protected format.i, count.i, n.i, glyph.i, first.i, last.i, prior.i, expected.i
  If anvil_tg_Span(offset,4)=0 : ProcedureReturn -1 : EndIf
  format=anvil_tg_U16(*anvil_tg_font+offset) : count=anvil_tg_U16(*anvil_tg_font+offset+2)
  If format=1
    If anvil_tg_Span(offset,4+count*2)=0 : ProcedureReturn -1 : EndIf
    prior=-1
    For n=0 To count-1
      glyph=anvil_tg_U16(*anvil_tg_font+offset+4+n*2)
      If glyph<=prior Or glyph>=anvil_tg_glyphCount : ProcedureReturn -1 : EndIf
      prior=glyph
    Next
    ProcedureReturn count
ElseIf format=2
    If anvil_tg_Span(offset,4+count*6)=0 : ProcedureReturn -1 : EndIf
    prior=-1 : expected=0
    For n=0 To count-1
      first=anvil_tg_U16(*anvil_tg_font+offset+4+n*6)
      last=anvil_tg_U16(*anvil_tg_font+offset+6+n*6)
      If first>last Or first<=prior Or last>=anvil_tg_glyphCount Or anvil_tg_U16(*anvil_tg_font+offset+8+n*6)<>expected : ProcedureReturn -1 : EndIf
      expected=expected+last-first+1 : prior=last
    Next
    ProcedureReturn expected
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i anvil_tg_CoverageIndex(offset.i,glyph.i)
  Protected format.i,count.i,lo.i,hi.i,mid.i,at.i,first.i,last.i,baseIndex.i
  format=anvil_tg_U16(*anvil_tg_font+offset) : count=anvil_tg_U16(*anvil_tg_font+offset+2)
  If format=1
    lo=0 : hi=count-1
    While lo<=hi
      mid=(lo+hi)/2 : at=anvil_tg_U16(*anvil_tg_font+offset+4+mid*2)
      If at<glyph : lo=mid+1 : ElseIf at>glyph : hi=mid-1 : Else : ProcedureReturn mid : EndIf
    Wend
  ElseIf format=2
    lo=0 : hi=count-1
    While lo<=hi
      mid=(lo+hi)/2 : at=offset+4+mid*6
      first=anvil_tg_U16(*anvil_tg_font+at) : last=anvil_tg_U16(*anvil_tg_font+at+2)
      If glyph<first : hi=mid-1
      ElseIf glyph>last : lo=mid+1
      Else
        baseIndex=anvil_tg_U16(*anvil_tg_font+at+4)
        ProcedureReturn baseIndex+glyph-first
      EndIf
    Wend
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i anvil_tg_Class(offset.i,glyph.i,classCount.i)
  Protected format.i,count.i,start.i,n.i,first.i,last.i,value.i,lo.i,hi.i,mid.i,at.i
  format=anvil_tg_U16(*anvil_tg_font+offset)
  If format=1
    start=anvil_tg_U16(*anvil_tg_font+offset+2) : count=anvil_tg_U16(*anvil_tg_font+offset+4)
    If glyph<start Or glyph>=start+count : ProcedureReturn 0 : EndIf
    value=anvil_tg_U16(*anvil_tg_font+offset+6+(glyph-start)*2)
  Else
    count=anvil_tg_U16(*anvil_tg_font+offset+2) : lo=0 : hi=count-1
    While lo<=hi
      mid=(lo+hi)/2 : at=offset+4+mid*6
      first=anvil_tg_U16(*anvil_tg_font+at) : last=anvil_tg_U16(*anvil_tg_font+at+2)
      If glyph<first : hi=mid-1
      ElseIf glyph>last : lo=mid+1
    Else
      value=anvil_tg_U16(*anvil_tg_font+at+4)
      If value>=classCount : ProcedureReturn -1 : EndIf
      ProcedureReturn value
      EndIf
    Wend
    ProcedureReturn 0
  EndIf
  If value>=classCount : ProcedureReturn -1 : EndIf
  ProcedureReturn value
EndProcedure

Procedure.i anvil_tg_AddPairPos(subOffset.i,lookup.i)
  Protected format.i,coverageOffset.i,coverageCount.i,value1.i,value2.i
  Protected pairSetCount.i,pairSets.i,n.i,pairOffset.i,pairCount.i,pos.i,recordSize.i
  Protected second.i,prior.i,size1.i,size2.i,subEnd.i,class1Offset.i,class2Offset.i,first.i,last.i
  Protected class1Count.i,class2Count.i,matrixBytes.q,coverageAbs.i,cell.i,cellCount.i
  If anvil_tg_Span(subOffset,10)=0 : ProcedureReturn 0 : EndIf
  format=anvil_tg_U16(*anvil_tg_font+subOffset) : coverageOffset=anvil_tg_U16(*anvil_tg_font+subOffset+2)
  value1=anvil_tg_U16(*anvil_tg_font+subOffset+4) : value2=anvil_tg_U16(*anvil_tg_font+subOffset+6)
  If (value1&$FF00)<>0 Or (value2&$FF00)<>0 : ProcedureReturn 0 : EndIf
  coverageAbs=subOffset+coverageOffset : coverageCount=anvil_tg_CoverageCount(coverageAbs)
  If coverageCount<0 : ProcedureReturn 0 : EndIf
  size1=anvil_tg_PopCount(value1)*2 : size2=anvil_tg_PopCount(value2)*2
  If format=1
    pairSetCount=anvil_tg_U16(*anvil_tg_font+subOffset+8)
    If pairSetCount<>coverageCount Or anvil_tg_Span(subOffset,10+pairSetCount*2)=0 : ProcedureReturn 0 : EndIf
    pairSets=subOffset+10 : recordSize=2+size1+size2
    For n=0 To pairSetCount-1
      pairOffset=subOffset+anvil_tg_U16(*anvil_tg_font+pairSets+n*2)
      If anvil_tg_Span(pairOffset,2)=0 : ProcedureReturn 0 : EndIf
      pairCount=anvil_tg_U16(*anvil_tg_font+pairOffset)
      If anvil_tg_Span(pairOffset+2,pairCount*recordSize)=0 : ProcedureReturn 0 : EndIf
      If pairCount>#ANVIL_TG_MAX_PAIR_WORK : ProcedureReturn 0 : EndIf
      pos=pairOffset+2 : prior=-1
      For second=0 To pairCount-1
        If anvil_tg_U16(*anvil_tg_font+pos)>=anvil_tg_glyphCount Or anvil_tg_U16(*anvil_tg_font+pos)<=prior : ProcedureReturn 0 : EndIf
        prior=anvil_tg_U16(*anvil_tg_font+pos) : pos+2
        If anvil_tg_ValueRecord(pos,value1,subOffset,0)<0 : ProcedureReturn 0 : EndIf
        pos=pos+size1
        If anvil_tg_ValueRecord(pos,value2,subOffset,0)<0 : ProcedureReturn 0 : EndIf
        pos=pos+size2
      Next
    Next
  ElseIf format=2
    If anvil_tg_Span(subOffset,16)=0 : ProcedureReturn 0 : EndIf
    class1Offset=subOffset+anvil_tg_U16(*anvil_tg_font+subOffset+8)
    class2Offset=subOffset+anvil_tg_U16(*anvil_tg_font+subOffset+10)
    class1Count=anvil_tg_U16(*anvil_tg_font+subOffset+12) : class2Count=anvil_tg_U16(*anvil_tg_font+subOffset+14)
    If class1Count<1 Or class2Count<1 : ProcedureReturn 0 : EndIf
    If anvil_tg_CoverageCount(coverageAbs)<0 Or anvil_tg_Span(class1Offset,4)=0 Or anvil_tg_Span(class2Offset,4)=0 : ProcedureReturn 0 : EndIf
    If anvil_tg_U16(*anvil_tg_font+class1Offset)<>1 And anvil_tg_U16(*anvil_tg_font+class1Offset)<>2 : ProcedureReturn 0 : EndIf
    If anvil_tg_U16(*anvil_tg_font+class2Offset)<>1 And anvil_tg_U16(*anvil_tg_font+class2Offset)<>2 : ProcedureReturn 0 : EndIf
    If anvil_tg_U16(*anvil_tg_font+class1Offset)=1
      If anvil_tg_Span(class1Offset,6)=0 : ProcedureReturn 0 : EndIf
      If anvil_tg_Span(class1Offset,6+anvil_tg_U16(*anvil_tg_font+class1Offset+4)*2)=0 : ProcedureReturn 0 : EndIf
      For n=0 To anvil_tg_U16(*anvil_tg_font+class1Offset+4)-1
        If anvil_tg_U16(*anvil_tg_font+class1Offset+6+n*2)>=class1Count : ProcedureReturn 0 : EndIf
      Next
    Else
      If anvil_tg_Span(class1Offset,4)=0 : ProcedureReturn 0 : EndIf
      If anvil_tg_Span(class1Offset,4+anvil_tg_U16(*anvil_tg_font+class1Offset+2)*6)=0 : ProcedureReturn 0 : EndIf
      prior=-1
      For n=0 To anvil_tg_U16(*anvil_tg_font+class1Offset+2)-1
        first=anvil_tg_U16(*anvil_tg_font+class1Offset+4+n*6) : last=anvil_tg_U16(*anvil_tg_font+class1Offset+6+n*6)
        If first>last Or first<=prior Or last>=anvil_tg_glyphCount Or anvil_tg_U16(*anvil_tg_font+class1Offset+8+n*6)>=class1Count : ProcedureReturn 0 : EndIf
        prior=last
      Next
    EndIf
    If anvil_tg_U16(*anvil_tg_font+class2Offset)=1
      If anvil_tg_Span(class2Offset,6)=0 : ProcedureReturn 0 : EndIf
      If anvil_tg_Span(class2Offset,6+anvil_tg_U16(*anvil_tg_font+class2Offset+4)*2)=0 : ProcedureReturn 0 : EndIf
      For n=0 To anvil_tg_U16(*anvil_tg_font+class2Offset+4)-1
        If anvil_tg_U16(*anvil_tg_font+class2Offset+6+n*2)>=class2Count : ProcedureReturn 0 : EndIf
      Next
    Else
      If anvil_tg_Span(class2Offset,4)=0 : ProcedureReturn 0 : EndIf
      If anvil_tg_Span(class2Offset,4+anvil_tg_U16(*anvil_tg_font+class2Offset+2)*6)=0 : ProcedureReturn 0 : EndIf
      prior=-1
      For n=0 To anvil_tg_U16(*anvil_tg_font+class2Offset+2)-1
        first=anvil_tg_U16(*anvil_tg_font+class2Offset+4+n*6) : last=anvil_tg_U16(*anvil_tg_font+class2Offset+6+n*6)
        If first>last Or first<=prior Or last>=anvil_tg_glyphCount Or anvil_tg_U16(*anvil_tg_font+class2Offset+8+n*6)>=class2Count : ProcedureReturn 0 : EndIf
        prior=last
      Next
    EndIf
    matrixBytes=class1Count*class2Count*(size1+size2)
    cellCount=class1Count*class2Count
    If cellCount>#ANVIL_TG_MAX_MATRIX_CELLS : ProcedureReturn 0 : EndIf
    If anvil_tg_Span(subOffset+16,matrixBytes)=0 : ProcedureReturn 0 : EndIf
    recordSize=size1+size2 : pos=subOffset+16
    For cell=0 To cellCount-1
      If anvil_tg_ValueRecord(pos,value1,subOffset,0)<0 : ProcedureReturn 0 : EndIf
      pos=pos+size1
      If anvil_tg_ValueRecord(pos,value2,subOffset,0)<0 : ProcedureReturn 0 : EndIf
      pos=pos+size2
    Next
  Else
    anvil_tg_unresolved=1
    ProcedureReturn 1 ; Other pair positioning formats are not evaluated.
  EndIf
  If anvil_tg_pairpos>=#ANVIL_TG_MAX_PAIRPOS : ProcedureReturn 0 : EndIf
  anvil_tg_pairOffset[anvil_tg_pairpos]=subOffset
  anvil_tg_pairLookup[anvil_tg_pairpos]=lookup
  anvil_tg_pairFormat[anvil_tg_pairpos]=format
  anvil_tg_pairValue1[anvil_tg_pairpos]=value1 : anvil_tg_pairValue2[anvil_tg_pairpos]=value2
  anvil_tg_pairpos+1
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeGposOpen()
  Protected index.i,major.i,minor.i,scriptList.i,featureList.i,lookupList.i
  Protected scriptCount.i,scriptRec.i,scriptOffset.i,scriptTag.i,preferred.i
  Protected script.i,defaultOffset.i,langCount.i,langOffset.i,featureCount.i
  Protected required.i,n.i,featureIndex.i,featureRecords.i,featureOffset.i
  Protected lookupCount.i,lookupTable.i,lookupOffset.i,lookupType.i,lookupFlags.i
  Protected subCount.i,subOffset.i,subType.i,extensionOffset.q,seen.i,m.i
  Protected selected.i,tag.i,tableEnd.i,featureRec.i,lookupScan.i,sort.i,sortValue.i
  AnvilTrueTypeGposClose() : anvil_tg_revision=AnvilTrueTypeRevision()
  If AnvilTrueTypeMetricsOpenState()=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_NOT_OPEN,0) : EndIf
  anvil_tg_glyphCount=AnvilTrueTypeGlyphCount()
  index=AnvilTrueTypeFind(#ANVIL_TG_TAG_GPOS)
  If index<0 : anvil_tg_open=1 : ProcedureReturn 1 : EndIf
  anvil_tg_length=AnvilTrueTypeTableLength(index) : *anvil_tg_font=AnvilTrueTypeTableData(index)
  anvil_tg_fontOffset=AnvilTrueTypeTableOffset(index)
  If anvil_tg_length<10 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset) : EndIf
  major=anvil_tg_U16(*anvil_tg_font) : minor=anvil_tg_U16(*anvil_tg_font+2)
  If major<>1 Or minor>1 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_FORMAT,anvil_tg_fontOffset) : EndIf
  If minor=1 And anvil_tg_length<14 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset) : EndIf
  scriptList=anvil_tg_U16(*anvil_tg_font+4) : featureList=anvil_tg_U16(*anvil_tg_font+6) : lookupList=anvil_tg_U16(*anvil_tg_font+8)
  If anvil_tg_Span(scriptList,2)=0 Or anvil_tg_Span(featureList,2)=0 Or anvil_tg_Span(lookupList,2)=0
    ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset)
  EndIf
  scriptCount=anvil_tg_U16(*anvil_tg_font+scriptList) : If anvil_tg_Span(scriptList+2,scriptCount*6)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+scriptList) : EndIf
  scriptRec=0 : preferred=0
  For n=0 To scriptCount-1
    tag=anvil_tg_U32(*anvil_tg_font+scriptList+2+n*6)
    If tag=#ANVIL_TG_TAG_LATN : scriptRec=scriptList+2+n*6 : preferred=1 : Break : EndIf
    If tag=#ANVIL_TG_TAG_DFLT And preferred=0 : scriptRec=scriptList+2+n*6 : EndIf
  Next
  If scriptRec=0
    anvil_tg_open=1 : ProcedureReturn 1
  EndIf
  scriptOffset=scriptList+anvil_tg_U16(*anvil_tg_font+scriptRec+4)
  If anvil_tg_Span(scriptOffset,4)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+scriptOffset) : EndIf
  defaultOffset=anvil_tg_U16(*anvil_tg_font+scriptOffset)
  langCount=anvil_tg_U16(*anvil_tg_font+scriptOffset+2)
  If anvil_tg_Span(scriptOffset+4,langCount*6)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+scriptOffset) : EndIf
  If defaultOffset<>0 : langOffset=scriptOffset+defaultOffset
  ElseIf langCount>0 : langOffset=scriptOffset+anvil_tg_U16(*anvil_tg_font+scriptOffset+8)
  Else : anvil_tg_open=1 : ProcedureReturn 1
  EndIf
  If anvil_tg_Span(langOffset,6)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+langOffset) : EndIf
  If anvil_tg_U16(*anvil_tg_font+langOffset)<>0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_FORMAT,anvil_tg_fontOffset+langOffset) : EndIf
  required=anvil_tg_U16(*anvil_tg_font+langOffset+2) : featureCount=anvil_tg_U16(*anvil_tg_font+langOffset+4)
  If anvil_tg_Span(langOffset+6,featureCount*2)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+langOffset) : EndIf
  featureRecords=anvil_tg_U16(*anvil_tg_font+featureList)
  If anvil_tg_Span(featureList+2,featureRecords*6)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+featureList) : EndIf
  anvil_tg_lookups=0
  For n=0 To featureCount
    If n=featureCount : featureIndex=required : Else : featureIndex=anvil_tg_U16(*anvil_tg_font+langOffset+6+n*2) : EndIf
    If featureIndex=$FFFF : Continue : EndIf
    If featureIndex>=featureRecords : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_FORMAT,anvil_tg_fontOffset+langOffset+6+n*2) : EndIf
    featureRec=featureList+2+featureIndex*6
    If anvil_tg_U32(*anvil_tg_font+featureRec)<>#ANVIL_TG_TAG_KERN : Continue : EndIf
    anvil_tg_kernFeature=1
    featureOffset=featureList+anvil_tg_U16(*anvil_tg_font+featureRec+4)
    If anvil_tg_Span(featureOffset,4)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+featureOffset) : EndIf
    m=anvil_tg_U16(*anvil_tg_font+featureOffset+2)
    If anvil_tg_Span(featureOffset+4,m*2)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+featureOffset) : EndIf
    For selected=0 To m-1
      lookupOffset=anvil_tg_U16(*anvil_tg_font+featureOffset+4+selected*2) : seen=0
      For lookupScan=0 To anvil_tg_lookups-1 : If anvil_tg_lookupOrder[lookupScan]=lookupOffset : seen=1 : Break : EndIf : Next
      If seen=0
        If anvil_tg_lookups>=#ANVIL_TG_MAX_LOOKUPS : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_CAPACITY,anvil_tg_fontOffset+featureOffset) : EndIf
        anvil_tg_lookupOrder[anvil_tg_lookups]=lookupOffset : anvil_tg_lookups+1
      EndIf
    Next
  Next
  ; Apply selected feature lookups in LookupList order, independent of the
  ; order in which LangSys feature records happened to reference them.
  For n=1 To anvil_tg_lookups-1
    sort=n : sortValue=anvil_tg_lookupOrder[n]
    While sort>0
      If anvil_tg_lookupOrder[sort-1]<=sortValue : Break : EndIf
      anvil_tg_lookupOrder[sort]=anvil_tg_lookupOrder[sort-1]
      sort-1
    Wend
    anvil_tg_lookupOrder[sort]=sortValue
  Next
  lookupCount=anvil_tg_U16(*anvil_tg_font+lookupList)
  If anvil_tg_Span(lookupList+2,lookupCount*2)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+lookupList) : EndIf
  anvil_tg_pairpos=0
  For n=0 To anvil_tg_lookups-1
    lookupOffset=anvil_tg_lookupOrder[n]
    If lookupOffset>=lookupCount : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_FORMAT,anvil_tg_fontOffset+featureList) : EndIf
    lookupTable=lookupList+anvil_tg_U16(*anvil_tg_font+lookupList+2+lookupOffset*2)
    If anvil_tg_Span(lookupTable,6)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+lookupTable) : EndIf
    lookupType=anvil_tg_U16(*anvil_tg_font+lookupTable) : lookupFlags=anvil_tg_U16(*anvil_tg_font+lookupTable+2)
    subCount=anvil_tg_U16(*anvil_tg_font+lookupTable+4)
    If anvil_tg_Span(lookupTable+6,subCount*2+Bool(lookupFlags&$10)*2)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+lookupTable) : EndIf
    ; Mark filtering and attachment-class flags require GDEF; skip such lookup
    ; rather than apply it to marks that it intended to ignore.
    If lookupFlags<>0 : anvil_tg_unresolved=1 : Continue : EndIf
    For m=0 To subCount-1
      subOffset=lookupTable+anvil_tg_U16(*anvil_tg_font+lookupTable+6+m*2)
      If lookupType=2
        If anvil_tg_AddPairPos(subOffset,n)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_FORMAT,anvil_tg_fontOffset+subOffset) : EndIf
      ElseIf lookupType=9
        If anvil_tg_Span(subOffset,8)=0 : ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_TABLE,anvil_tg_fontOffset+subOffset) : EndIf
        If anvil_tg_U16(*anvil_tg_font+subOffset)=1 And anvil_tg_U16(*anvil_tg_font+subOffset+2)=2
          extensionOffset=anvil_tg_U32(*anvil_tg_font+subOffset+4)
          If extensionOffset>anvil_tg_length-subOffset Or anvil_tg_AddPairPos(subOffset+extensionOffset,n)=0
            ProcedureReturn anvil_tg_Fail(#ANVIL_TG_E_FORMAT,anvil_tg_fontOffset+subOffset)
          EndIf
        Else
          anvil_tg_unresolved=1
        EndIf
      Else
        anvil_tg_unresolved=1
      EndIf
    Next
  Next
  anvil_tg_error=#ANVIL_TG_E_NONE : anvil_tg_errorOffset=0 : anvil_tg_open=1
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeGposOpenState()
  ProcedureReturn anvil_tg_Ready()
EndProcedure
Procedure.i AnvilTrueTypeGposHasKernFeature()
  If anvil_tg_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_tg_kernFeature
EndProcedure
Procedure.i AnvilTrueTypeGposHasUnresolvedKern()
  If anvil_tg_Ready()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_tg_unresolved
EndProcedure

Procedure.i anvil_tg_ReadPair(slot.i,leftGlyph.i,rightGlyph.i,values.i)
  Protected sub.i,format.i,coverage.i,index.i,value1.i,value2.i
  Protected pairSetCount.i,pairSet.i,pairCount.i,lo.i,hi.i,mid.i,at.i,second.i
  Protected class1Offset.i,class2Offset.i,class1Count.i,class2Count.i,class1.i,class2.i
  Protected matrixOffset.i,recordSize.i,size1.i,size2.i,fieldOut.i
  Protected firstValues.i,secondValues.i
  sub=anvil_tg_pairOffset[slot] : format=anvil_tg_pairFormat[slot]
  coverage=sub+anvil_tg_U16(*anvil_tg_font+sub+2) : index=anvil_tg_CoverageIndex(coverage,leftGlyph)
  If index<0 : ProcedureReturn 0 : EndIf
  value1=anvil_tg_pairValue1[slot] : value2=anvil_tg_pairValue2[slot]
  size1=anvil_tg_PopCount(value1)*2 : size2=anvil_tg_PopCount(value2)*2
  If format=1
    pairSetCount=anvil_tg_U16(*anvil_tg_font+sub+8)
    If index>=pairSetCount : ProcedureReturn 0 : EndIf
    pairSet=sub+anvil_tg_U16(*anvil_tg_font+sub+10+index*2)
    pairCount=anvil_tg_U16(*anvil_tg_font+pairSet) : lo=0 : hi=pairCount-1
    recordSize=2+size1+size2
    While lo<=hi
      mid=(lo+hi)/2 : at=pairSet+2+mid*recordSize : second=anvil_tg_U16(*anvil_tg_font+at)
      If second<rightGlyph : lo=mid+1
      ElseIf second>rightGlyph : hi=mid-1
      Else
        firstValues=values : secondValues=values+4*SizeOf(.i)
        If anvil_tg_ValueRecord(at+2,value1,sub,firstValues)<0 : ProcedureReturn -1 : EndIf
        If anvil_tg_ValueRecord(at+2+size1,value2,sub,secondValues)<0 : ProcedureReturn -1 : EndIf
        ProcedureReturn 1
      EndIf
    Wend
  ElseIf format=2
    class1Offset=sub+anvil_tg_U16(*anvil_tg_font+sub+8)
    class2Offset=sub+anvil_tg_U16(*anvil_tg_font+sub+10)
    class1Count=anvil_tg_U16(*anvil_tg_font+sub+12) : class2Count=anvil_tg_U16(*anvil_tg_font+sub+14)
    class1=anvil_tg_Class(class1Offset,leftGlyph,class1Count)
    class2=anvil_tg_Class(class2Offset,rightGlyph,class2Count)
    If class1<0 Or class2<0 : ProcedureReturn -1 : EndIf
    matrixOffset=sub+16+(class1*class2Count+class2)*(size1+size2)
    If anvil_tg_ValueRecord(matrixOffset,value1,sub,values)<0 : ProcedureReturn -1 : EndIf
    If anvil_tg_ValueRecord(matrixOffset+size1,value2,sub,values+4*SizeOf(.i))<0 : ProcedureReturn -1 : EndIf
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i AnvilTrueTypeGposPair(leftGlyph.i,rightGlyph.i,valuesOut.i)
  Protected n.i,slot.i,lookup.i,matched.i,values.i,field.i,any.i
  Dim anvil_tg_lookupValues.i[8]
  If anvil_tg_Ready()=0 Or valuesOut=0 : ProcedureReturn 0 : EndIf
  If leftGlyph<0 Or rightGlyph<0 Or leftGlyph>=anvil_tg_glyphCount Or rightGlyph>=anvil_tg_glyphCount
    anvil_tg_error=#ANVIL_TG_E_GLYPH : anvil_tg_errorOffset=0 : ProcedureReturn 0
  EndIf
  For field=0 To 7 : PokeI(valuesOut+field*SizeOf(.i),0) : Next
  If anvil_tg_unresolved
    anvil_tg_error=#ANVIL_TG_E_UNSUPPORTED : anvil_tg_errorOffset=anvil_tg_fontOffset
    ProcedureReturn 0
  EndIf
  any=0
  For n=0 To anvil_tg_lookups-1
    lookup=n : matched=0
    For slot=0 To anvil_tg_pairpos-1
      If anvil_tg_pairLookup[slot]<>lookup : Continue : EndIf
      For field=0 To 7 : anvil_tg_lookupValues[field]=0 : Next
      values=@anvil_tg_lookupValues[0]
      matched=anvil_tg_ReadPair(slot,leftGlyph,rightGlyph,values)
      If matched<0 : anvil_tg_error=#ANVIL_TG_E_FORMAT : ProcedureReturn 0 : EndIf
      If matched>0 : Break : EndIf
    Next
    If matched>0
      any=1
      For field=0 To 7
        PokeI(valuesOut+field*SizeOf(.i),PeekI(valuesOut+field*SizeOf(.i))+anvil_tg_lookupValues[field])
      Next
    EndIf
  Next
  anvil_tg_error=#ANVIL_TG_E_NONE : anvil_tg_errorOffset=0
  ProcedureReturn any
EndProcedure

; Select kerning source at face/feature level. A selected GPOS kern feature
; suppresses legacy fallback even when this pair has no adjustment. Legacy
; `kern` is used only if no GPOS kern feature exists.
Procedure.i AnvilTrueTypePairPosition(leftGlyph.i,rightGlyph.i,valuesOut.i)
  Protected result.i, kern.i, n.i
  If valuesOut=0 : ProcedureReturn 0 : EndIf
  If leftGlyph<0 Or rightGlyph<0 Or leftGlyph>=AnvilTrueTypeGlyphCount() Or rightGlyph>=AnvilTrueTypeGlyphCount() : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeGposOpenState()
    result=AnvilTrueTypeGposPair(leftGlyph,rightGlyph,valuesOut)
    If result<>0 : ProcedureReturn 1 : EndIf
    If AnvilTrueTypeGposError()=#ANVIL_TG_E_UNSUPPORTED
      ; Unsupported selected GPOS kerning is reported through GposError and
      ; HasUnresolvedKern; preserve the glyph run with zero pair adjustments.
      For n=0 To 7 : PokeI(valuesOut+n*SizeOf(.i),0) : Next
      ProcedureReturn 1
    EndIf
    If AnvilTrueTypeGposError()<>#ANVIL_TG_E_NONE : ProcedureReturn 0 : EndIf
    If AnvilTrueTypeGposHasKernFeature()
      If AnvilTrueTypeGposHasUnresolvedKern() : ProcedureReturn 0 : EndIf
      ProcedureReturn 1
    EndIf
  EndIf
  For n=0 To 7 : PokeI(valuesOut+n*SizeOf(.i),0) : Next
  If AnvilTrueTypeKernOpenState()
    kern=AnvilTrueTypeKerning(leftGlyph,rightGlyph)
    If AnvilTrueTypeKernError()<>#ANVIL_TK_E_NONE : ProcedureReturn 0 : EndIf
    PokeI(valuesOut+2*SizeOf(.i),kern)
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeGposError()
  anvil_tg_Ready() : ProcedureReturn anvil_tg_error
EndProcedure
Procedure.i AnvilTrueTypeGposErrorOffset()
  anvil_tg_Ready() : ProcedureReturn anvil_tg_errorOffset
EndProcedure
