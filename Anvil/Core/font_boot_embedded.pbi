; Optional composition: include the embedded font asset and common font owner first.
; File-only targets do not include this module.

Global anvil_font_embeddedReady.i

; The image carries one parser-ready face for the first screen frame. Its
; private slot borrows immutable image bytes; the four command slots remain
; available for files loaded after the storage medium mounts.
Procedure.i AnvilFontBootEmbeddedInit()
  If anvil_font_embeddedReady <> 0 : ProcedureReturn 1 : EndIf
  AnvilTrueTypeSlotsInit()
  If #ANVIL_BOOT_TTF_BYTES < 1 Or #ANVIL_BOOT_TTF_BYTES > #ANVIL_TTS_MAX_BYTES
    PrintN("!! embedded TrueType font is outside the slot size limit")
    ProcedureReturn 0
  EndIf
  If AnvilTrueTypeSlotLoad(#ANVIL_TTS_BOOT_SLOT, ?anvilBootTtf, #ANVIL_BOOT_TTF_BYTES) = 0
    PrintN("!! embedded TrueType font failed validation")
    ProcedureReturn 0
  EndIf
  If AnvilTrueTypeSlotSelect(#ANVIL_TTS_BOOT_SLOT) = 0
    PrintN("!! embedded TrueType font could not be selected")
    ProcedureReturn 0
  EndIf
  AnvilTrueTypeSetDefaultSlot(#ANVIL_TTS_BOOT_SLOT)
  anvil_font_embeddedReady = 1
  ProcedureReturn 1
EndProcedure
