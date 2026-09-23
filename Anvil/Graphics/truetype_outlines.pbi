; T3 bounded TrueType `loca`/`glyf` decoder.
; Output point records are 12 bytes: signed int32 x,y,flags; bit0 is on-curve.
; Contours are packed int32 inclusive zero-based point endpoint indices.

#ANVIL_TTO_E_NONE = 0
#ANVIL_TTO_E_NOT_OPEN = 1
#ANVIL_TTO_E_TABLE = 2
#ANVIL_TTO_E_GLYPH = 3
#ANVIL_TTO_E_FORMAT = 4
#ANVIL_TTO_E_CAPACITY = 5
#ANVIL_TTO_E_DEPTH = 6
#ANVIL_TTO_E_COMPLEX = 7
#ANVIL_TTO_TAG_LOCA = $6C6F6361
#ANVIL_TTO_TAG_GLYF = $676C7966
#ANVIL_TTO_MAX_DEPTH = 16
#ANVIL_TTO_MAX_POINTS = 65535
#ANVIL_TTO_MAX_WORK = 65536

Global anvil_tto_open.i
Global anvil_tto_revision.i
Global anvil_tto_error.i
Global anvil_tto_errorOffset.i
Global anvil_tto_glyphCount.i
Global anvil_tto_indexFormat.i
Global anvil_tto_locaOffset.i
Global anvil_tto_locaLength.i
Global anvil_tto_glyfOffset.i
Global anvil_tto_glyfLength.i
Global *anvil_tto_locaData
Global *anvil_tto_glyf
Global Dim anvil_tto_active.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_flags.a[#ANVIL_TTO_MAX_POINTS]
Global Dim anvil_tto_frameData.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameLength.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_framePos.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameGlyph.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameBase.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameChildBase.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameFlags.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameArg1.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameArg2.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameM1.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameM2.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameM3.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameM4.i[#ANVIL_TTO_MAX_DEPTH+1]
Global Dim anvil_tto_frameXY.i[#ANVIL_TTO_MAX_DEPTH+1]

Procedure.i anvil_tto_U8(at.i)
  ProcedureReturn PeekA(at)&$FF
EndProcedure
Procedure.i anvil_tto_U16(at.i)
  ProcedureReturn (anvil_tto_U8(at)<<8)|anvil_tto_U8(at+1)
EndProcedure
Procedure.i anvil_tto_S16(at.i)
  Protected v.i=anvil_tto_U16(at)
  If v&$8000 : v-65536 : EndIf
  ProcedureReturn v
EndProcedure
Procedure.i anvil_tto_Round14(value.q)
  If value<0 : ProcedureReturn -((-value+8192)/16384) : EndIf
  ProcedureReturn (value+8192)/16384
EndProcedure
Procedure.q anvil_tto_U32(at.i)
  ProcedureReturn (anvil_tto_U8(at)<<24)|(anvil_tto_U8(at+1)<<16)|(anvil_tto_U8(at+2)<<8)|anvil_tto_U8(at+3)
EndProcedure
Procedure.i anvil_tto_Ready()
  If anvil_tto_open=0 Or anvil_tto_revision=0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeRevision()<>anvil_tto_revision Or AnvilTrueTypeMetricsOpenState()=0
    anvil_tto_open=0 : anvil_tto_error=#ANVIL_TTO_E_NOT_OPEN : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i anvil_tto_Fail(code.i,offset.i)
  anvil_tto_error=code : anvil_tto_errorOffset=offset : ProcedureReturn 0
EndProcedure
Procedure.i AnvilTrueTypeOutlinesClose()
  anvil_tto_open=0 : anvil_tto_revision=0 : anvil_tto_error=#ANVIL_TTO_E_NONE : anvil_tto_errorOffset=0
  *anvil_tto_locaData=0 : *anvil_tto_glyf=0 : anvil_tto_glyphCount=0
  anvil_tto_indexFormat=0 : anvil_tto_locaOffset=0 : anvil_tto_locaLength=0
  anvil_tto_glyfOffset=0 : anvil_tto_glyfLength=0
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeOutlinesOpen()
  Protected locaIndex.i, glyfIndex.i, required.q, n.i, current.q, prior.q
  AnvilTrueTypeOutlinesClose()
  anvil_tto_revision=AnvilTrueTypeRevision()
  If AnvilTrueTypeMetricsOpenState()=0 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_NOT_OPEN,0) : EndIf
  locaIndex=AnvilTrueTypeFind(#ANVIL_TTO_TAG_LOCA) : glyfIndex=AnvilTrueTypeFind(#ANVIL_TTO_TAG_GLYF)
  If locaIndex<0 Or glyfIndex<0 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_TABLE,0) : EndIf
  anvil_tto_glyphCount=AnvilTrueTypeGlyphCount() : anvil_tto_indexFormat=AnvilTrueTypeIndexToLocFormat()
  anvil_tto_locaOffset=AnvilTrueTypeTableOffset(locaIndex) : anvil_tto_locaLength=AnvilTrueTypeTableLength(locaIndex)
  anvil_tto_glyfOffset=AnvilTrueTypeTableOffset(glyfIndex) : anvil_tto_glyfLength=AnvilTrueTypeTableLength(glyfIndex)
  *anvil_tto_locaData=AnvilTrueTypeTableData(locaIndex) : *anvil_tto_glyf=AnvilTrueTypeTableData(glyfIndex)
  If anvil_tto_indexFormat=0 : required=(anvil_tto_glyphCount+1)*2 : Else : required=(anvil_tto_glyphCount+1)*4 : EndIf
  If required>anvil_tto_locaLength : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_TABLE,anvil_tto_locaOffset) : EndIf
  prior=0
  For n=0 To anvil_tto_glyphCount
    If anvil_tto_indexFormat=0 : current=anvil_tto_U16(*anvil_tto_locaData+n*2)*2
    Else : current=anvil_tto_U32(*anvil_tto_locaData+n*4) : EndIf
    If current<prior Or current>anvil_tto_glyfLength
      ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_locaOffset+n*(2+2*anvil_tto_indexFormat))
    EndIf
    prior=current
  Next
  anvil_tto_error=#ANVIL_TTO_E_NONE : anvil_tto_errorOffset=0 : anvil_tto_open=1
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeOutlinesOpenState()
  ProcedureReturn anvil_tto_Ready()
EndProcedure

Procedure.q anvil_tto_Loca(glyph.i)
  If anvil_tto_indexFormat=0 : ProcedureReturn anvil_tto_U16(*anvil_tto_locaData+glyph*2)*2 : EndIf
  ProcedureReturn anvil_tto_U32(*anvil_tto_locaData+glyph*4)
EndProcedure

; Recursively appends component points directly into caller buffers. Point and
; contour counts are in/out pointers so each component remains bounded by the
; original caller capacities. Transform is F2Dot14 and uses 64-bit products.
Procedure.i anvil_tto_DecodeSimple(glyph.i,data.i,length.i,points.i,pointCapacity.i,contours.i,contourCapacity.i,pointCount.i,contourCount.i)
  Protected pos.i=10, c.i, base.i, contourBase.i, contourTotal.i, endPoint.i
  Protected pointTotal.i, instructionLength.i, flag.i, repeatCount.i, n.i
  Protected x.i=0, y.i=0, delta.i
  contourTotal=anvil_tto_S16(data)
  If contourTotal<0 : ProcedureReturn -1 : EndIf
  If contourTotal=0 : ProcedureReturn 1 : EndIf
  If pos+contourTotal*2+2>length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
  contourBase=PeekI(contourCount) : base=PeekI(pointCount)
  If contourBase+contourTotal>contourCapacity Or contourBase+contourTotal>65535
    ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_CAPACITY,anvil_tto_glyfOffset+anvil_tto_Loca(glyph))
  EndIf
  For c=0 To contourTotal-1
    endPoint=anvil_tto_U16(data+pos+c*2)
    If c>0 And endPoint<=anvil_tto_U16(data+pos+(c-1)*2)
      ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos+c*2)
    EndIf
  Next
  pointTotal=anvil_tto_U16(data+pos+(contourTotal-1)*2)+1
  If pointTotal>#ANVIL_TTO_MAX_POINTS Or base+pointTotal>pointCapacity
    ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_CAPACITY,anvil_tto_glyfOffset+anvil_tto_Loca(glyph))
  EndIf
  pos+contourTotal*2 : instructionLength=anvil_tto_U16(data+pos) : pos+2
  If pos+instructionLength>length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
  pos+instructionLength : n=0
  While n<pointTotal
    If pos>=length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
    flag=anvil_tto_U8(data+pos) : pos+1 : repeatCount=0
    If flag&$80 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos-1) : EndIf
    If flag&8
      If pos>=length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
      repeatCount=anvil_tto_U8(data+pos) : pos+1
    EndIf
    If n+repeatCount>=pointTotal : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
    For c=0 To repeatCount : anvil_tto_flags[n]=flag : n+1 : Next
  Wend
  For n=0 To pointTotal-1
    flag=anvil_tto_flags[n]
    If flag&2
      If pos>=length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
      delta=anvil_tto_U8(data+pos) : pos+1 : If (flag&16)=0 : delta=-delta : EndIf
    ElseIf flag&16
      delta=0
    Else
      If pos+2>length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
      delta=anvil_tto_S16(data+pos) : pos+2
    EndIf
    x+delta
    If x<-2147483648 Or x>2147483647 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
    PokeL(points+(base+n)*12,x) : PokeL(points+(base+n)*12+8,flag&1)
  Next
  For n=0 To pointTotal-1
    flag=anvil_tto_flags[n]
    If flag&4
      If pos>=length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
      delta=anvil_tto_U8(data+pos) : pos+1 : If (flag&32)=0 : delta=-delta : EndIf
    ElseIf flag&32
      delta=0
    Else
      If pos+2>length : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
      delta=anvil_tto_S16(data+pos) : pos+2
    EndIf
    y+delta
    If y<-2147483648 Or y>2147483647 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)+pos) : EndIf
    PokeL(points+(base+n)*12+4,y)
  Next
  For c=0 To contourTotal-1
    PokeL(contours+(contourBase+c)*4,base+anvil_tto_U16(data+10+c*2))
  Next
  PokeI(pointCount,base+pointTotal) : PokeI(contourCount,contourBase+contourTotal)
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_tto_ReadComponent(depth.i,pointCount.i)
  Protected pos.i, length.i, data.i, flags.i, words.i, xy.i, argBytes.i
  Protected child.i, m1.i,m2.i,m3.i,m4.i, transformCount.i, arg1.i,arg2.i
  data=anvil_tto_frameData[depth] : length=anvil_tto_frameLength[depth] : pos=anvil_tto_framePos[depth]
  If pos+4>length : ProcedureReturn -2 : EndIf
  flags=anvil_tto_U16(data+pos) : child=anvil_tto_U16(data+pos+2) : pos+4
  transformCount=0
  If flags&8 : transformCount+1 : EndIf
  If flags&64 : transformCount+1 : EndIf
  If flags&128 : transformCount+1 : EndIf
  If transformCount>1 Or (flags&$1800)=$1800 : ProcedureReturn -2 : EndIf
  words=Bool(flags&1) : xy=Bool(flags&2) : argBytes=2 : If words : argBytes=4 : EndIf
  If pos+argBytes>length : ProcedureReturn -2 : EndIf
  If words
    If xy : arg1=anvil_tto_S16(data+pos) : arg2=anvil_tto_S16(data+pos+2)
    Else : arg1=anvil_tto_U16(data+pos) : arg2=anvil_tto_U16(data+pos+2) : EndIf
  Else
    If xy
      arg1=anvil_tto_U8(data+pos) : arg2=anvil_tto_U8(data+pos+1)
      If arg1&$80 : arg1-256 : EndIf
      If arg2&$80 : arg2-256 : EndIf
    Else : arg1=anvil_tto_U8(data+pos) : arg2=anvil_tto_U8(data+pos+1) : EndIf
  EndIf
  pos+argBytes : m1=16384 : m2=0 : m3=0 : m4=16384
  If flags&8
    If pos+2>length : ProcedureReturn -2 : EndIf
    m1=anvil_tto_S16(data+pos) : m4=m1 : pos+2
  ElseIf flags&64
    If pos+4>length : ProcedureReturn -2 : EndIf
    m1=anvil_tto_S16(data+pos) : m4=anvil_tto_S16(data+pos+2) : pos+4
  ElseIf flags&128
    If pos+8>length : ProcedureReturn -2 : EndIf
    m1=anvil_tto_S16(data+pos) : m2=anvil_tto_S16(data+pos+2)
    m3=anvil_tto_S16(data+pos+4) : m4=anvil_tto_S16(data+pos+6) : pos+8
  EndIf
  anvil_tto_frameFlags[depth]=flags : anvil_tto_frameArg1[depth]=arg1 : anvil_tto_frameArg2[depth]=arg2
  anvil_tto_frameM1[depth]=m1 : anvil_tto_frameM2[depth]=m2
  anvil_tto_frameM3[depth]=m3 : anvil_tto_frameM4[depth]=m4
  anvil_tto_frameXY[depth]=xy : anvil_tto_framePos[depth]=pos
  anvil_tto_frameChildBase[depth]=PeekI(pointCount)
  ProcedureReturn child
EndProcedure

Procedure.i anvil_tto_ApplyComponent(depth.i,points.i,pointCount.i)
  Protected flags.i, base.i, childBase.i, n.i, childCount.i, arg1.i,arg2.i
  Protected dx.i,dy.i,px.i,py.i,q.i,m1.i,m2.i,m3.i,m4.i,xy.i
  Protected tx.q,ty.q,sumX.q,sumY.q
  flags=anvil_tto_frameFlags[depth] : base=anvil_tto_frameBase[depth]
  childBase=anvil_tto_frameChildBase[depth] : childCount=PeekI(pointCount)-childBase
  arg1=anvil_tto_frameArg1[depth] : arg2=anvil_tto_frameArg2[depth]
  m1=anvil_tto_frameM1[depth] : m2=anvil_tto_frameM2[depth]
  m3=anvil_tto_frameM3[depth] : m4=anvil_tto_frameM4[depth] : xy=anvil_tto_frameXY[depth]
  If xy
    dx=arg1 : dy=arg2
    If flags&$0800
      sumX=m1*dx+m3*dy : sumY=m2*dx+m4*dy
      dx=anvil_tto_Round14(sumX) : dy=anvil_tto_Round14(sumY)
    EndIf
  Else
    If arg1<0 Or arg1>=childBase-base Or arg2<0 Or arg2>=childCount Or childCount=0 : ProcedureReturn 0 : EndIf
    dx=PeekL(points+(base+arg1)*12) : dy=PeekL(points+(base+arg1)*12+4)
    px=PeekL(points+(childBase+arg2)*12) : py=PeekL(points+(childBase+arg2)*12+4)
    sumX=m1*px+m3*py : sumY=m2*px+m4*py
    tx=anvil_tto_Round14(sumX) : ty=anvil_tto_Round14(sumY)
    dx=dx-tx : dy=dy-ty
  EndIf
  For n=childBase To PeekI(pointCount)-1
    px=PeekL(points+n*12) : py=PeekL(points+n*12+4) : q=px
    sumX=m1*q+m3*py : sumY=m2*q+m4*py
    tx=anvil_tto_Round14(sumX)+dx : ty=anvil_tto_Round14(sumY)+dy
    If tx<-2147483648 Or tx>2147483647 Or ty<-2147483648 Or ty>2147483647 : ProcedureReturn 0 : EndIf
    PokeL(points+n*12,tx) : PokeL(points+n*12+4,ty)
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_tto_FinishComposite(depth.i)
  Protected data.i, pos.i, length.i, flags.i, instructionLength.i
  data=anvil_tto_frameData[depth] : pos=anvil_tto_framePos[depth] : length=anvil_tto_frameLength[depth]
  flags=anvil_tto_frameFlags[depth]
  If flags&256
    If pos+2>length : ProcedureReturn 0 : EndIf
    instructionLength=anvil_tto_U16(data+pos) : pos+2
    If pos+instructionLength>length : ProcedureReturn 0 : EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

; Explicit depth-bounded DFS: PureMetal does not support recursive procedures.
Procedure.i anvil_tto_Expand(rootGlyph.i,points.i,pointCapacity.i,contours.i,contourCapacity.i,pointCount.i,contourCount.i)
  Protected depth.i=0, glyph.i=rootGlyph, entering.i=1, n.i, result.i, work.i=0
  Protected start.q, finish.q, data.i, length.i, contoursInGlyph.i, child.i
  While 1
    If entering
      If glyph<0 Or glyph>=anvil_tto_glyphCount : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_GLYPH,anvil_tto_locaOffset) : EndIf
      work+1
      If work>#ANVIL_TTO_MAX_WORK : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_COMPLEX,anvil_tto_glyfOffset+anvil_tto_Loca(glyph)) : EndIf
      For n=0 To depth-1
        If anvil_tto_active[n]=glyph : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset) : EndIf
      Next
      anvil_tto_active[depth]=glyph
      start=anvil_tto_Loca(glyph) : finish=anvil_tto_Loca(glyph+1)
      If finish=start
        entering=0
      Else
        If finish-start<10 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+start) : EndIf
        data=*anvil_tto_glyf+start : length=finish-start : contoursInGlyph=anvil_tto_S16(data)
        If contoursInGlyph>=0
          result=anvil_tto_DecodeSimple(glyph,data,length,points,pointCapacity,contours,contourCapacity,pointCount,contourCount)
          If result=0 : ProcedureReturn 0 : EndIf
          entering=0
        Else
          If contoursInGlyph<>-1 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+start) : EndIf
          anvil_tto_frameData[depth]=data : anvil_tto_frameLength[depth]=length
          anvil_tto_framePos[depth]=10 : anvil_tto_frameGlyph[depth]=glyph
          anvil_tto_frameBase[depth]=PeekI(pointCount)
          If depth>=#ANVIL_TTO_MAX_DEPTH : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_DEPTH,anvil_tto_glyfOffset+start) : EndIf
          child=anvil_tto_ReadComponent(depth,pointCount)
          If child<0 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+start+anvil_tto_framePos[depth]) : EndIf
          glyph=child : depth+1 : entering=1 : Continue
        EndIf
      EndIf
    EndIf
    If depth=0 : ProcedureReturn 1 : EndIf
    depth-1
    If anvil_tto_ApplyComponent(depth,points,pointCount)=0
      ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(anvil_tto_frameGlyph[depth]))
    EndIf
    If anvil_tto_frameFlags[depth]&32
      child=anvil_tto_ReadComponent(depth,pointCount)
      If child<0 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(anvil_tto_frameGlyph[depth])+anvil_tto_framePos[depth]) : EndIf
      glyph=child : depth+1 : entering=1
    Else
      If anvil_tto_FinishComposite(depth)=0
        ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_FORMAT,anvil_tto_glyfOffset+anvil_tto_Loca(anvil_tto_frameGlyph[depth])+anvil_tto_framePos[depth])
      EndIf
      glyph=anvil_tto_frameGlyph[depth] : entering=0
    EndIf
  Wend
EndProcedure
Procedure.i AnvilTrueTypeGlyphOutline(glyph.i,points.i,pointCapacity.i,contours.i,contourCapacity.i,pointCountOut.i,contourCountOut.i)
  Protected pointCount.i=0, contourCount.i=0, result.i
  If pointCountOut=0 Or contourCountOut=0 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_CAPACITY,0) : EndIf
  PokeI(pointCountOut,0) : PokeI(contourCountOut,0)
  If anvil_tto_Ready()=0 : ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_NOT_OPEN,0) : EndIf
  If points=0 Or contours=0 Or pointCapacity<0 Or pointCapacity>#ANVIL_TTO_MAX_POINTS Or contourCapacity<0 Or contourCapacity>65535
    ProcedureReturn anvil_tto_Fail(#ANVIL_TTO_E_CAPACITY,0)
  EndIf
  result=anvil_tto_Expand(glyph,points,pointCapacity,contours,contourCapacity,@pointCount,@contourCount)
  If result=0 : ProcedureReturn 0 : EndIf
  PokeI(pointCountOut,pointCount) : PokeI(contourCountOut,contourCount)
  anvil_tto_error=#ANVIL_TTO_E_NONE : anvil_tto_errorOffset=0 : ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeOutlinesError()
  anvil_tto_Ready() : ProcedureReturn anvil_tto_error
EndProcedure
Procedure.i AnvilTrueTypeOutlinesErrorOffset()
  anvil_tto_Ready() : ProcedureReturn anvil_tto_errorOffset
EndProcedure
