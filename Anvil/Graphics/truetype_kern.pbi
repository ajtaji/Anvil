; T6 bounded OpenType version-0 `kern` format-0 horizontal pair lookup.
; GPOS positioning tables are outside this module; unsupported kern formats
; are safely skipped by their validated subtable lengths.

#ANVIL_TK_E_NONE = 0
#ANVIL_TK_E_NOT_OPEN = 1
#ANVIL_TK_E_TABLE = 2
#ANVIL_TK_E_FORMAT = 3
#ANVIL_TK_E_GLYPH = 4
#ANVIL_TK_MAX_SUBTABLES = 32
#ANVIL_TK_TAG_KERN = $6B65726E

Global anvil_tk_open.i
Global anvil_tk_revision.i
Global anvil_tk_error.i
Global anvil_tk_errorOffset.i
Global anvil_tk_base.i
Global anvil_tk_glyphCount.i
Global anvil_tk_subtables.i
Global Dim anvil_tk_pairOffset.i[#ANVIL_TK_MAX_SUBTABLES]
Global Dim anvil_tk_pairCount.i[#ANVIL_TK_MAX_SUBTABLES]
Global Dim anvil_tk_override.i[#ANVIL_TK_MAX_SUBTABLES]

Procedure.i anvil_tk_U8(at.i)
  ProcedureReturn PeekA(at)&$FF
EndProcedure
Procedure.i anvil_tk_U16(at.i)
  ProcedureReturn (anvil_tk_U8(at)<<8)|anvil_tk_U8(at+1)
EndProcedure
Procedure.i anvil_tk_S16(at.i)
  Protected value.i=anvil_tk_U16(at)
  If value&$8000 : value-65536 : EndIf
  ProcedureReturn value
EndProcedure
Procedure.i anvil_tk_Ready()
  If anvil_tk_open=0 Or anvil_tk_revision=0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeRevision()<>anvil_tk_revision Or AnvilTrueTypeMetricsOpenState()=0
    anvil_tk_open=0 : anvil_tk_error=#ANVIL_TK_E_NOT_OPEN : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeKernClose()
  anvil_tk_open=0 : anvil_tk_revision=0 : anvil_tk_error=#ANVIL_TK_E_NONE : anvil_tk_errorOffset=0
  anvil_tk_base=0 : anvil_tk_glyphCount=0 : anvil_tk_subtables=0
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeKernOpen()
  Protected index.i, length.i, nTables.i, pos.i, version.i, subLength.i
  Protected coverage.i, format.i, pairs.i, need.i, n.i, key.i, previous.i
  Protected power.i, selector.i, expectedRange.i, expectedShift.i
  Protected offset.i, left.i, right.i
  AnvilTrueTypeKernClose()
  anvil_tk_revision=AnvilTrueTypeRevision()
  If AnvilTrueTypeMetricsOpenState()=0 : anvil_tk_error=#ANVIL_TK_E_NOT_OPEN : ProcedureReturn 0 : EndIf
  anvil_tk_glyphCount=AnvilTrueTypeGlyphCount()
  index=AnvilTrueTypeFind(#ANVIL_TK_TAG_KERN)
  If index<0
    anvil_tk_open=1 : anvil_tk_error=#ANVIL_TK_E_NONE : ProcedureReturn 1
  EndIf
  length=AnvilTrueTypeTableLength(index) : anvil_tk_base=AnvilTrueTypeTableData(index)
  If length<4 : anvil_tk_error=#ANVIL_TK_E_TABLE : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index) : ProcedureReturn 0 : EndIf
  If anvil_tk_U16(anvil_tk_base)<>0
    anvil_tk_error=#ANVIL_TK_E_FORMAT : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index) : ProcedureReturn 0
  EndIf
  nTables=anvil_tk_U16(anvil_tk_base+2) : pos=4 : anvil_tk_subtables=0
  For n=0 To nTables-1
    If pos+6>length : anvil_tk_error=#ANVIL_TK_E_TABLE : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+pos : ProcedureReturn 0 : EndIf
    version=anvil_tk_U16(anvil_tk_base+pos) : subLength=anvil_tk_U16(anvil_tk_base+pos+2) : coverage=anvil_tk_U16(anvil_tk_base+pos+4)
    If version<>0 Or subLength<6 Or subLength>length-pos
      anvil_tk_error=#ANVIL_TK_E_FORMAT : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+pos : ProcedureReturn 0
    EndIf
    format=coverage>>8
    If format=0 And (coverage&$00F7)=1 ; horizontal; no minimum, cross-stream or reserved bits
      If subLength<14 : anvil_tk_error=#ANVIL_TK_E_TABLE : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+pos : ProcedureReturn 0 : EndIf
      pairs=anvil_tk_U16(anvil_tk_base+pos+6) : need=14+pairs*6
      If need>subLength : anvil_tk_error=#ANVIL_TK_E_TABLE : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+pos : ProcedureReturn 0 : EndIf
      power=0 : selector=0
      If pairs>0
        power=1
        While power*2<=pairs : power*2 : selector+1 : Wend
      EndIf
      expectedRange=power*6 : expectedShift=(pairs-power)*6
      If anvil_tk_U16(anvil_tk_base+pos+8)<>expectedRange Or anvil_tk_U16(anvil_tk_base+pos+10)<>selector Or anvil_tk_U16(anvil_tk_base+pos+12)<>expectedShift
        anvil_tk_error=#ANVIL_TK_E_FORMAT : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+pos+8 : ProcedureReturn 0
      EndIf
      If anvil_tk_subtables>=#ANVIL_TK_MAX_SUBTABLES
        anvil_tk_error=#ANVIL_TK_E_FORMAT : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+pos : ProcedureReturn 0
      EndIf
      offset=pos+14 : previous=-1
      For left=0 To pairs-1
        key=anvil_tk_U16(anvil_tk_base+offset+left*6)*65536+anvil_tk_U16(anvil_tk_base+offset+left*6+2)
        If key<=previous
          anvil_tk_error=#ANVIL_TK_E_FORMAT : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+offset+left*6 : ProcedureReturn 0
        EndIf
        If anvil_tk_U16(anvil_tk_base+offset+left*6)>=anvil_tk_glyphCount Or anvil_tk_U16(anvil_tk_base+offset+left*6+2)>=anvil_tk_glyphCount
          anvil_tk_error=#ANVIL_TK_E_GLYPH : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+offset+left*6 : ProcedureReturn 0
        EndIf
        previous=key
      Next
      anvil_tk_pairOffset[anvil_tk_subtables]=offset
      anvil_tk_pairCount[anvil_tk_subtables]=pairs
      anvil_tk_override[anvil_tk_subtables]=Bool(coverage&8)
      anvil_tk_subtables+1
    EndIf
    pos+subLength
  Next
  If pos>length : anvil_tk_error=#ANVIL_TK_E_TABLE : anvil_tk_errorOffset=AnvilTrueTypeTableOffset(index)+length : ProcedureReturn 0 : EndIf
  anvil_tk_error=#ANVIL_TK_E_NONE : anvil_tk_errorOffset=0 : anvil_tk_open=1
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeKernOpenState()
  ProcedureReturn anvil_tk_Ready()
EndProcedure
Procedure.i AnvilTrueTypeKerning(leftGlyph.i,rightGlyph.i)
  Protected n.i, lo.i, hi.i, mid.i, pair.i, key.i, found.i, value.i, total.i
  If anvil_tk_Ready()=0 : ProcedureReturn 0 : EndIf
  If leftGlyph<0 Or rightGlyph<0 Or leftGlyph>=anvil_tk_glyphCount Or rightGlyph>=anvil_tk_glyphCount
    anvil_tk_error=#ANVIL_TK_E_GLYPH : anvil_tk_errorOffset=0 : ProcedureReturn 0
  EndIf
  key=leftGlyph*65536+rightGlyph : total=0
  For n=0 To anvil_tk_subtables-1
    lo=0 : hi=anvil_tk_pairCount[n]-1 : found=0
    While lo<=hi
      mid=(lo+hi)/2 : pair=anvil_tk_base+anvil_tk_pairOffset[n]+mid*6
      value=anvil_tk_U16(pair)*65536+anvil_tk_U16(pair+2)
      If value<key : lo=mid+1
      ElseIf value>key : hi=mid-1
      Else : found=1 : value=anvil_tk_S16(pair+4) : Break
      EndIf
    Wend
    If found
      If anvil_tk_override[n] : total=value : Else : total+value : EndIf
    EndIf
  Next
  anvil_tk_error=#ANVIL_TK_E_NONE : anvil_tk_errorOffset=0
  ProcedureReturn total
EndProcedure
Procedure.i AnvilTrueTypeKernError()
  anvil_tk_Ready() : ProcedureReturn anvil_tk_error
EndProcedure
Procedure.i AnvilTrueTypeKernErrorOffset()
  anvil_tk_Ready() : ProcedureReturn anvil_tk_errorOffset
EndProcedure
