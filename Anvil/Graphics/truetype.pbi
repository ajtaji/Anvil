; T0 TrueType/OpenType sfnt container reader.
; Memory only: file loading, metrics, cmap, outlines and rasterisation belong
; to later milestones. No renderer or atlas dependency is allowed here.

#ANVIL_TT_MAX_TABLES = 256

#ANVIL_TT_E_NONE       = 0
#ANVIL_TT_E_ARGUMENT   = 1
#ANVIL_TT_E_HEADER     = 2
#ANVIL_TT_E_TTC        = 3
#ANVIL_TT_E_DIRECTORY  = 4
#ANVIL_TT_E_TABLE      = 5
#ANVIL_TT_E_CHECKSUM   = 6
#ANVIL_TT_E_DUPLICATE  = 7
#ANVIL_TT_E_OVERLAP    = 8
#ANVIL_TT_E_UNSUPPORTED = 9

Global *anvil_tt_data.i
Global anvil_tt_bytes.i
Global anvil_tt_face.i
Global anvil_tt_revision.i
Global anvil_tt_tables.i
Global anvil_tt_error.i
Global anvil_tt_errorTag.i
Global anvil_tt_errorOffset.i
Global Dim anvil_tt_errorBuffer.a[96]
Global Dim anvil_tt_tag.i[#ANVIL_TT_MAX_TABLES]
Global Dim anvil_tt_offset.i[#ANVIL_TT_MAX_TABLES]
Global Dim anvil_tt_length.i[#ANVIL_TT_MAX_TABLES]
Global Dim anvil_tt_checksum.i[#ANVIL_TT_MAX_TABLES]

Procedure.i anvil_tt_U8(at.i)
  ProcedureReturn PeekA(*anvil_tt_data + at) & $FF
EndProcedure

Procedure.i anvil_tt_U16(at.i)
  ProcedureReturn (anvil_tt_U8(at) << 8) | anvil_tt_U8(at + 1)
EndProcedure

Procedure.i anvil_tt_U32(at.i)
  ProcedureReturn (anvil_tt_U8(at) << 24) | (anvil_tt_U8(at + 1) << 16) | (anvil_tt_U8(at + 2) << 8) | anvil_tt_U8(at + 3)
EndProcedure

Procedure.i anvil_tt_HexDigit(value.i)
  value = value & $F
  If value < 10 : ProcedureReturn 48 + value : EndIf
  ProcedureReturn 55 + value
EndProcedure

Procedure.i anvil_tt_FormatError()
  Protected n.i
  Protected pos.i = 0
  ; Fixed ASCII sentence prefix; the numeric fields are always bounded.
  PokeA(@anvil_tt_errorBuffer[pos], 84) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 114) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 117) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 101) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 84) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 121) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 112) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 101) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 32) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 114) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 101) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 102) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 117) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 115) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 97) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 108) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 32) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 99) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 111) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 100) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 101) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 61) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 48) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 120) : pos + 1
  For n = 7 To 0 Step -1 : PokeA(@anvil_tt_errorBuffer[pos], anvil_tt_HexDigit(anvil_tt_error >> (n * 4))) : pos + 1 : Next
  PokeA(@anvil_tt_errorBuffer[pos], 32) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 116) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 97) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 103) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 61) : pos + 1
  For n = 7 To 0 Step -1 : PokeA(@anvil_tt_errorBuffer[pos], anvil_tt_HexDigit(anvil_tt_errorTag >> (n * 4))) : pos + 1 : Next
  PokeA(@anvil_tt_errorBuffer[pos], 32) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 111) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 102) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 102) : pos + 1
  PokeA(@anvil_tt_errorBuffer[pos], 61) : pos + 1
  For n = 7 To 0 Step -1 : PokeA(@anvil_tt_errorBuffer[pos], anvil_tt_HexDigit(anvil_tt_errorOffset >> (n * 4))) : pos + 1 : Next
  PokeA(@anvil_tt_errorBuffer[pos], 0)
  ProcedureReturn pos
EndProcedure

Procedure.i anvil_tt_Fail(code.i, ignored.i)
  anvil_tt_error = code
  *anvil_tt_data = 0
  anvil_tt_bytes = 0
  anvil_tt_face = 0
  anvil_tt_tables = 0
  anvil_tt_FormatError()
  ProcedureReturn 0
EndProcedure


Procedure.i anvil_tt_FailAt(code.i, tag.i, offset.i, ignored.i)
  anvil_tt_errorTag = tag
  anvil_tt_errorOffset = offset
  ProcedureReturn anvil_tt_Fail(code, 0)
EndProcedure

Procedure.i anvil_tt_TableChecksum(offset.i, length.i, head.i)
  Protected words.i
  Protected n.i
  Protected j.i
  Protected pos.i
  Protected word.i
  Protected sum.q
  words = (length + 3) / 4
  sum = 0
  For n = 0 To words - 1
    word = 0
    For j = 0 To 3
      pos = n * 4 + j
      word = word << 8
      If pos < length
        If head = 0 Or pos < 8 Or pos >= 12
          ; head.checkSumAdjustment is zero while the head table checksum is
          ; calculated, as required by the sfnt table checksum rule.
          word = word | anvil_tt_U8(offset + pos)
        EndIf
      EndIf
    Next
    sum = (sum + word) & $FFFFFFFF
  Next
  ProcedureReturn sum
EndProcedure

Procedure.i AnvilTrueTypeClose()
  anvil_tt_revision = anvil_tt_revision + 1
  PokeA(@anvil_tt_errorBuffer[0], 0)
  *anvil_tt_data = 0
  anvil_tt_bytes = 0
  anvil_tt_face = 0
  anvil_tt_tables = 0
  anvil_tt_error = #ANVIL_TT_E_NONE
  anvil_tt_errorTag = 0
  anvil_tt_errorOffset = 0
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeOpen(data.i, bytes.i)
  Protected signature.i
  Protected version.i
  Protected fontCount.i
  Protected firstOffset.i
  Protected faceOffset.i
  Protected directoryEnd.i
  Protected tableEnd.i
  Protected record.i
  Protected n.i
  Protected other.i
  Protected tag.i
  Protected checksum.i
  Protected offset.i
  Protected length.i

  AnvilTrueTypeClose()
  If data = 0 Or bytes < 12
    ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_ARGUMENT, 0)
  EndIf
  *anvil_tt_data = data
  anvil_tt_bytes = bytes
  signature = anvil_tt_U32(0)
  firstOffset = 0
  If signature = $74746366 ; ttcf
    If bytes < 16 : ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_TTC, 0) : EndIf
    version = anvil_tt_U32(4)
    If version <> $00010000 And version <> $00020000
      ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_TTC, 0)
    EndIf
    fontCount = anvil_tt_U32(8)
    If fontCount < 1 Or fontCount > 64 Or fontCount > (bytes - 12) / 4
      ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_TTC, 0)
    EndIf
    For n = 0 To fontCount - 1
      faceOffset = anvil_tt_U32(12 + n * 4)
      If faceOffset < 12 + fontCount * 4 Or faceOffset > bytes - 12
        ProcedureReturn anvil_tt_FailAt(#ANVIL_TT_E_TTC, 0, 12 + n * 4, 0)
      EndIf
      If n = 0 : firstOffset = faceOffset : EndIf
    Next
  Else
    If signature <> $00010000 And signature <> $74727565
      If signature = $4F54544F
        ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_UNSUPPORTED, 0)
      EndIf
      ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_HEADER, 0)
    EndIf
  EndIf
  anvil_tt_face = firstOffset
  If anvil_tt_face > bytes - 12
    ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_HEADER, 0)
  EndIf
  signature = anvil_tt_U32(anvil_tt_face)
  If signature <> $00010000 And signature <> $74727565
    If firstOffset <> 0
      ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_HEADER, 0)
    EndIf
    ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_HEADER, 0)
  EndIf
  anvil_tt_tables = anvil_tt_U16(anvil_tt_face + 4)
  If anvil_tt_tables < 1 Or anvil_tt_tables > #ANVIL_TT_MAX_TABLES
    ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_HEADER, 0)
  EndIf
  directoryEnd = anvil_tt_face + 12 + anvil_tt_tables * 16
  If directoryEnd < anvil_tt_face Or directoryEnd > bytes
    ProcedureReturn anvil_tt_Fail(#ANVIL_TT_E_HEADER, 0)
  EndIf
  For n = 0 To anvil_tt_tables - 1
    record = anvil_tt_face + 12 + n * 16
    tag = anvil_tt_U32(record)
    checksum = anvil_tt_U32(record + 4)
    offset = anvil_tt_U32(record + 8)
    length = anvil_tt_U32(record + 12)
    If length < 1 Or offset > bytes Or length > bytes - offset
      ProcedureReturn anvil_tt_FailAt(#ANVIL_TT_E_TABLE, tag, offset, 0)
    EndIf
    tableEnd = offset + length
    If tableEnd < offset
      ProcedureReturn anvil_tt_FailAt(#ANVIL_TT_E_TABLE, tag, offset, 0)
    EndIf
    For other = 0 To n - 1
      If anvil_tt_tag[other] = tag
        ProcedureReturn anvil_tt_FailAt(#ANVIL_TT_E_DUPLICATE, tag, offset, 0)
      EndIf
      If offset < anvil_tt_offset[other] + anvil_tt_length[other] And anvil_tt_offset[other] < tableEnd
        ProcedureReturn anvil_tt_FailAt(#ANVIL_TT_E_OVERLAP, tag, offset, 0)
      EndIf
    Next
    anvil_tt_tag[n] = tag
    anvil_tt_checksum[n] = checksum
    anvil_tt_offset[n] = offset
    anvil_tt_length[n] = length
  Next
  For n = 0 To anvil_tt_tables - 1
    If anvil_tt_TableChecksum(anvil_tt_offset[n], anvil_tt_length[n], Bool(anvil_tt_tag[n] = $68656164)) <> anvil_tt_checksum[n]
      ProcedureReturn anvil_tt_FailAt(#ANVIL_TT_E_CHECKSUM, anvil_tt_tag[n], anvil_tt_offset[n], 0)
    EndIf
  Next
  anvil_tt_error = #ANVIL_TT_E_NONE
  anvil_tt_errorTag = 0
  anvil_tt_errorOffset = 0
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeTableCount()
  ProcedureReturn anvil_tt_tables
EndProcedure

Procedure.i AnvilTrueTypeTableTag(index.i)
  If index < 0 Or index >= anvil_tt_tables : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_tt_tag[index]
EndProcedure

Procedure.i AnvilTrueTypeTableOffset(index.i)
  If index < 0 Or index >= anvil_tt_tables : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_tt_offset[index]
EndProcedure

Procedure.i AnvilTrueTypeTableLength(index.i)
  If index < 0 Or index >= anvil_tt_tables : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_tt_length[index]
EndProcedure

Procedure.i AnvilTrueTypeFind(tag.i)
  Protected n.i
  If anvil_tt_tables < 1 : ProcedureReturn -1 : EndIf
  For n = 0 To anvil_tt_tables - 1
    If anvil_tt_tag[n] = tag : ProcedureReturn n : EndIf
  Next
  ProcedureReturn -1
EndProcedure

Procedure.i AnvilTrueTypeError()
  ProcedureReturn anvil_tt_error
EndProcedure

Procedure.i AnvilTrueTypeErrorTag()
  ProcedureReturn anvil_tt_errorTag
EndProcedure

Procedure.i AnvilTrueTypeErrorOffset()
  ProcedureReturn anvil_tt_errorOffset
EndProcedure

Procedure.i AnvilTrueTypeErrorText()
  ProcedureReturn @anvil_tt_errorBuffer[0]
EndProcedure




; Consumers keep this token with decoded state and invalidate it after every
; close/open attempt, including a reopen at the same memory address.
Procedure.i AnvilTrueTypeRevision()
  ProcedureReturn anvil_tt_revision
EndProcedure

Procedure.i AnvilTrueTypeTableData(index.i)
  If *anvil_tt_data = 0 Or index < 0 Or index >= anvil_tt_tables : ProcedureReturn 0 : EndIf
  ProcedureReturn *anvil_tt_data + anvil_tt_offset[index]
EndProcedure
