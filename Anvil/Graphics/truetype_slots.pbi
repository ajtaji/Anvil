; Bounded resident TrueType slots. Core owns the memory backing each slot;
; this layer only borrows those byte ranges and controls parser binding.
; Rendering caches use slot generation as identity, while T0 revision guards
; every live parser pointer after a select or validation attempt.

#ANVIL_TTS_MAX_SLOTS = 4
#ANVIL_TTS_MAX_BYTES = 1048576

#ANVIL_TTS_E_NONE = 0
#ANVIL_TTS_E_ARGUMENT = 1
#ANVIL_TTS_E_ACTIVE = 2
#ANVIL_TTS_E_FORMAT = 3
#ANVIL_TTS_E_GENERATION = 4

Global Dim anvil_tts_data.i[#ANVIL_TTS_MAX_SLOTS]
Global Dim anvil_tts_bytes.i[#ANVIL_TTS_MAX_SLOTS]
Global Dim anvil_tts_generation.i[#ANVIL_TTS_MAX_SLOTS]
Global anvil_tts_selected.i = -1
Global anvil_tts_parserRevision.i
Global anvil_tts_error.i
Global anvil_tts_ready.i
; Renderer-neutral text settings. The persisted path itself belongs to the
; core Settings store; these values are the current in-memory selections.
Global anvil_tts_pixelHeight.i = 16
Global anvil_tts_defaultSlot.i = -1

Procedure.i AnvilTrueTypePixelHeight()
  AnvilTrueTypeSlotsInit()
  ProcedureReturn anvil_tts_pixelHeight
EndProcedure

Procedure.i AnvilTrueTypeSetPixelHeight(pixelHeight.i)
  AnvilTrueTypeSlotsInit()
  If pixelHeight < 1 Or pixelHeight > 512 : ProcedureReturn 0 : EndIf
  anvil_tts_pixelHeight = pixelHeight
  ProcedureReturn 1
EndProcedure

; -1 means bitmap fallback; 0..3 names the configured resident font slot.
Procedure.i AnvilTrueTypeDefaultSlot()
  AnvilTrueTypeSlotsInit()
  ProcedureReturn anvil_tts_defaultSlot
EndProcedure

Procedure.i AnvilTrueTypeSetDefaultSlot(slot.i)
  AnvilTrueTypeSlotsInit()
  If slot < -1 Or slot >= #ANVIL_TTS_MAX_SLOTS : ProcedureReturn 0 : EndIf
  anvil_tts_defaultSlot = slot
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeSlotsInit()
  Protected slot.i
  If anvil_tts_ready <> 0 : ProcedureReturn 1 : EndIf
  For slot = 0 To #ANVIL_TTS_MAX_SLOTS - 1
    anvil_tts_data[slot] = 0
    anvil_tts_bytes[slot] = 0
    anvil_tts_generation[slot] = 0
  Next
  anvil_tts_selected = -1
  anvil_tts_parserRevision = 0
  anvil_tts_error = #ANVIL_TTS_E_NONE
  anvil_tts_pixelHeight = 16
  anvil_tts_defaultSlot = -1
  anvil_tts_ready = 1
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_tts_CloseParser()
  AnvilTrueTypeGposClose()
  AnvilTrueTypeKernClose()
  AnvilTrueTypeOutlinesClose()
  AnvilTrueTypeCmapClose()
  AnvilTrueTypeMetricsClose()
  AnvilTrueTypeClose()
  anvil_tts_parserRevision = 0
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_tts_OpenParser(data.i, bytes.i)
  anvil_tts_parserRevision = 0
  If data = 0 Or bytes < 1 Or bytes > #ANVIL_TTS_MAX_BYTES
    ProcedureReturn 0
  EndIf
  If AnvilTrueTypeOpen(data, bytes) = 0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeMetricsOpen() = 0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeCmapOpen() = 0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeOutlinesOpen() = 0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeKernOpen() = 0 : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeGposOpen() = 0 : ProcedureReturn 0 : EndIf
  anvil_tts_parserRevision = AnvilTrueTypeRevision()
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_tts_Restore(slot.i)
  If slot < 0
    anvil_tts_CloseParser()
    anvil_tts_selected = -1
    ProcedureReturn 1
  EndIf
  If slot >= #ANVIL_TTS_MAX_SLOTS
    anvil_tts_CloseParser()
    anvil_tts_selected = -1
    ProcedureReturn 0
  EndIf
  If anvil_tts_data[slot] = 0 Or anvil_tts_bytes[slot] < 1
    anvil_tts_CloseParser()
    anvil_tts_selected = -1
    ProcedureReturn 0
  EndIf
  If anvil_tts_OpenParser(anvil_tts_data[slot], anvil_tts_bytes[slot]) = 0
    anvil_tts_CloseParser()
    anvil_tts_selected = -1
    ProcedureReturn 0
  EndIf
  anvil_tts_selected = slot
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeSlotParserBound()
  AnvilTrueTypeSlotsInit()
  If anvil_tts_selected < 0 Or anvil_tts_selected >= #ANVIL_TTS_MAX_SLOTS
    ProcedureReturn 0
  EndIf
  If anvil_tts_data[anvil_tts_selected] = 0 Or anvil_tts_generation[anvil_tts_selected] < 1
    ProcedureReturn 0
  EndIf
  If anvil_tts_parserRevision = 0 Or AnvilTrueTypeRevision() <> anvil_tts_parserRevision
    ProcedureReturn 0
  EndIf
  If AnvilTrueTypeMetricsOpenState() = 0 Or AnvilTrueTypeCmapOpenState() = 0 Or AnvilTrueTypeOutlinesOpenState() = 0 Or AnvilTrueTypeKernOpenState() = 0 Or AnvilTrueTypeGposOpenState() = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; Test a candidate buffer without publishing it as a slot. The current parser
; binding is restored even when any parser stage rejects the candidate.
Procedure.i AnvilTrueTypeSlotValidate(data.i, bytes.i)
  Protected previous.i
  Protected valid.i
  AnvilTrueTypeSlotsInit()
  anvil_tts_error = #ANVIL_TTS_E_NONE
  If data = 0 Or bytes < 1
    anvil_tts_error = #ANVIL_TTS_E_ARGUMENT
    ProcedureReturn 0
  EndIf
  previous = anvil_tts_selected
  valid = anvil_tts_OpenParser(data, bytes)
  If anvil_tts_Restore(previous) = 0
    anvil_tts_error = #ANVIL_TTS_E_FORMAT
    ProcedureReturn 0
  EndIf
  If valid = 0
    anvil_tts_error = #ANVIL_TTS_E_FORMAT
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; Validate a new borrowed buffer before publishing it. The selected face is
; always restored after candidate parsing, on both success and failure.
; Callers must keep the candidate buffer alive after success.
Procedure.i AnvilTrueTypeSlotLoad(slot.i, data.i, bytes.i)
  Protected previous.i
  Protected nextGeneration.i
  Protected valid.i
  AnvilTrueTypeSlotsInit()
  anvil_tts_error = #ANVIL_TTS_E_NONE
  If slot < 0 Or slot >= #ANVIL_TTS_MAX_SLOTS Or data = 0 Or bytes < 1 Or bytes > #ANVIL_TTS_MAX_BYTES
    anvil_tts_error = #ANVIL_TTS_E_ARGUMENT
    ProcedureReturn 0
  EndIf
  If slot = anvil_tts_selected
    anvil_tts_error = #ANVIL_TTS_E_ACTIVE
    ProcedureReturn 0
  EndIf
  If anvil_tts_generation[slot] = $7FFFFFFF
    anvil_tts_error = #ANVIL_TTS_E_GENERATION
    ProcedureReturn 0
  EndIf
  previous = anvil_tts_selected
  valid = anvil_tts_OpenParser(data, bytes)
  If valid <> 0
    ; Candidate parse state must never escape this call. Restore the old face
    ; before publishing new bytes/generation to the renderer.
    If anvil_tts_Restore(previous) = 0
      anvil_tts_error = #ANVIL_TTS_E_FORMAT
      ProcedureReturn 0
    EndIf
    nextGeneration = anvil_tts_generation[slot] + 1
    If nextGeneration < 1 : anvil_tts_error = #ANVIL_TTS_E_GENERATION : ProcedureReturn 0 : EndIf
    anvil_tts_data[slot] = data
    anvil_tts_bytes[slot] = bytes
    anvil_tts_generation[slot] = nextGeneration
    ProcedureReturn 1
  EndIf
  anvil_tts_CloseParser()
  If anvil_tts_Restore(previous) = 0
    anvil_tts_error = #ANVIL_TTS_E_FORMAT
  Else
    anvil_tts_error = #ANVIL_TTS_E_FORMAT
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i AnvilTrueTypeSlotSelect(slot.i)
  Protected previous.i
  AnvilTrueTypeSlotsInit()
  anvil_tts_error = #ANVIL_TTS_E_NONE
  If slot < 0 Or slot >= #ANVIL_TTS_MAX_SLOTS
    anvil_tts_error = #ANVIL_TTS_E_ARGUMENT
    ProcedureReturn 0
  EndIf
  If anvil_tts_data[slot] = 0 Or anvil_tts_bytes[slot] < 1
    anvil_tts_error = #ANVIL_TTS_E_ARGUMENT
    ProcedureReturn 0
  EndIf
  If slot = anvil_tts_selected And AnvilTrueTypeSlotParserBound() <> 0
    ProcedureReturn 1
  EndIf
  previous = anvil_tts_selected
  If anvil_tts_OpenParser(anvil_tts_data[slot], anvil_tts_bytes[slot]) <> 0
    anvil_tts_selected = slot
    ProcedureReturn 1
  EndIf
  anvil_tts_CloseParser()
  If anvil_tts_Restore(previous) = 0
    anvil_tts_error = #ANVIL_TTS_E_FORMAT
  Else
    anvil_tts_error = #ANVIL_TTS_E_FORMAT
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i AnvilTrueTypeSlotUnload(slot.i)
  AnvilTrueTypeSlotsInit()
  anvil_tts_error = #ANVIL_TTS_E_NONE
  If slot < 0 Or slot >= #ANVIL_TTS_MAX_SLOTS
    anvil_tts_error = #ANVIL_TTS_E_ARGUMENT
    ProcedureReturn 0
  EndIf
  If slot = anvil_tts_selected
    anvil_tts_error = #ANVIL_TTS_E_ACTIVE
    ProcedureReturn 0
  EndIf
  If anvil_tts_generation[slot] = $7FFFFFFF
    anvil_tts_error = #ANVIL_TTS_E_GENERATION
    ProcedureReturn 0
  EndIf
  anvil_tts_data[slot] = 0
  anvil_tts_bytes[slot] = 0
  anvil_tts_generation[slot] = anvil_tts_generation[slot] + 1
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeSlotSelected()
  AnvilTrueTypeSlotsInit()
  ProcedureReturn anvil_tts_selected
EndProcedure

; Renderer teardown and an explicit bitmap-font switch close the current
; parser binding without discarding resident slot bytes or generations.
Procedure.i AnvilTrueTypeSlotDeselect()
  AnvilTrueTypeSlotsInit()
  anvil_tts_CloseParser()
  anvil_tts_selected = -1
  anvil_tts_error = #ANVIL_TTS_E_NONE
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeSlotGeneration(slot.i)
  AnvilTrueTypeSlotsInit()
  If slot < 0 Or slot >= #ANVIL_TTS_MAX_SLOTS : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_tts_generation[slot]
EndProcedure

Procedure.i AnvilTrueTypeSlotBytes(slot.i)
  AnvilTrueTypeSlotsInit()
  If slot < 0 Or slot >= #ANVIL_TTS_MAX_SLOTS : ProcedureReturn 0 : EndIf
  ProcedureReturn anvil_tts_bytes[slot]
EndProcedure

Procedure.i AnvilTrueTypeSlotError()
  AnvilTrueTypeSlotsInit()
  ProcedureReturn anvil_tts_error
EndProcedure
