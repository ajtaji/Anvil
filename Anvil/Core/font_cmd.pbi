; Bounded TrueType slot commands. Storage owns these file bytes, the
; TrueType slot layer borrows immutable committed buffers, and renderers may
; consume only the currently selected parser face.

#ANVIL_FONT_SLOT_COUNT = #ANVIL_TTS_MAX_SLOTS
#ANVIL_FONT_MAX_BYTES = #ANVIL_TTS_MAX_BYTES
#ANVIL_FONT_READ_CHUNK = 4096
#ANVIL_FONT_PATH_BYTES = 1024

Global Dim anvil_font_slot_data.a[#ANVIL_FONT_SLOT_COUNT * #ANVIL_FONT_MAX_BYTES]
Global Dim anvil_font_slot_path.a[#ANVIL_FONT_SLOT_COUNT * #ANVIL_FONT_PATH_BYTES]
Global anvil_font_bootChecked.i

Procedure.i AnvilFontSettingsBootApply()
  Protected *value
  Protected pathBytes.i
  Protected pixelHeight.i
  If anvil_font_bootChecked <> 0 : ProcedureReturn 1 : EndIf
  anvil_font_bootChecked = 1
  If SettingsLoadState() = 0
    AnvilTrueTypeSetDefaultSlot(-1)
    AnvilTrueTypeSlotDeselect()
    ProcedureReturn 1
  EndIf
  *value = SettingsGet("font.size")
  If *value <> 0
    pixelHeight = PmfDecOf(*value, 16)
    If AnvilTrueTypeSetPixelHeight(pixelHeight) = 0
      AnvilTrueTypeSetPixelHeight(16)
      PrintN("!! saved font.size is outside 1..512; using 16 pixels")
    EndIf
  EndIf
  *value = SettingsGet("font.default")
  If *value = 0
    AnvilTrueTypeSetDefaultSlot(-1)
    AnvilTrueTypeSlotDeselect()
    ProcedureReturn 1
  EndIf
  pathBytes = SettingsLength("font.default")
  AnvilTrueTypeSetDefaultSlot(0)
  If pathBytes > 0 And pathBytes < #ANVIL_FONT_PATH_BYTES
    If anvil_font_LoadFile(0, *value, pathBytes) <> 0
      If AnvilTrueTypeSlotSelect(0) <> 0
        Print("default TrueType font loaded from ") : UartWriteStr(*value) : PrintNl()
        ProcedureReturn 1
      EndIf
    EndIf
  EndIf
  AnvilTrueTypeSlotDeselect()
  Print("!! configured default font is unavailable: ") : UartWriteStr(*value)
  PrintN("; built-in bitmap font remains active")
  ProcedureReturn 0
EndProcedure

Procedure.i anvil_font_SlotAddress(slot.i)
  If slot < 0 Or slot >= #ANVIL_FONT_SLOT_COUNT : ProcedureReturn 0 : EndIf
  ProcedureReturn @anvil_font_slot_data[slot * #ANVIL_FONT_MAX_BYTES]
EndProcedure

Procedure.i anvil_font_CopySlotPath(slot.i, *path, bytes.i)
  Protected i.i
  Protected base.i
  If slot < 0 Or slot >= #ANVIL_FONT_SLOT_COUNT Or *path = 0 Or bytes < 1 Or bytes >= #ANVIL_FONT_PATH_BYTES
    ProcedureReturn 0
  EndIf
  base = slot * #ANVIL_FONT_PATH_BYTES
  For i = 0 To bytes - 1
    anvil_font_slot_path[base + i] = PeekA(*path + i)
  Next
  anvil_font_slot_path[base + bytes] = 0
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_font_ClearSlotPath(slot.i)
  If slot < 0 Or slot >= #ANVIL_FONT_SLOT_COUNT : ProcedureReturn 0 : EndIf
  anvil_font_slot_path[slot * #ANVIL_FONT_PATH_BYTES] = 0
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_font_SlotPath(slot.i)
  If slot < 0 Or slot >= #ANVIL_FONT_SLOT_COUNT : ProcedureReturn 0 : EndIf
  ProcedureReturn @anvil_font_slot_path[slot * #ANVIL_FONT_PATH_BYTES]
EndProcedure

Procedure.i anvil_font_ParseSlot()
  Protected slot.i
  slot = ParseDec()
  If gParseOk = 0 Or slot < 0 Or slot >= #ANVIL_FONT_SLOT_COUNT
    ProcedureReturn -1
  EndIf
  ProcedureReturn slot
EndProcedure

Procedure anvil_font_Info()
  Protected slot.i
  Protected selected.i
  Protected defaultSlot.i
  Protected *defaultPath
  selected = AnvilTrueTypeSlotSelected()
  PrintN("TrueType fonts (four bounded slots; 1024 KiB per file)")
  For slot = 0 To #ANVIL_FONT_SLOT_COUNT - 1
    Print("  slot ") : PrintDec(slot) : Print(": ")
    If AnvilTrueTypeSlotBytes(slot) > 0
      If selected = slot : Print("selected, ") : EndIf
      PrintDec(AnvilTrueTypeSlotBytes(slot)) : Print(" bytes, generation ")
      PrintDec(AnvilTrueTypeSlotGeneration(slot))
      If anvil_font_SlotPath(slot) <> 0
        Print(" from ") : UartWriteStr(anvil_font_SlotPath(slot))
      EndIf
      PrintNl()
    Else
      PrintN("empty")
    EndIf
  Next
  If selected >= 0 And AnvilTrueTypeSlotParserBound() <> 0
    Print("  units/em ") : PrintDec(AnvilTrueTypeUnitsPerEm())
    Print(", glyphs ") : PrintDec(AnvilTrueTypeGlyphCount()) : PrintNl()
    Print("  ascender ") : PrintDec(AnvilTrueTypeAscender())
    Print(", descender ") : PrintDec(AnvilTrueTypeDescender())
    Print(", line gap ") : PrintDec(AnvilTrueTypeLineGap()) : PrintNl()
  ElseIf selected >= 0
    PrintN("  selected parser binding is stale; select this slot again before rendering")
  Else
    PrintN("  no font selected")
  EndIf
  Print("  text size ") : PrintDec(AnvilTrueTypePixelHeight()) : PrintN(" pixels")
  defaultSlot = AnvilTrueTypeDefaultSlot()
  *defaultPath = SettingsGet("font.default")
  If defaultSlot < 0
    PrintN("  default font: built-in bitmap")
  ElseIf AnvilTrueTypeSlotBytes(defaultSlot) > 0
    Print("  default font: slot ") : PrintDec(defaultSlot)
    If anvil_font_SlotPath(defaultSlot) <> 0
      Print(" from ") : UartWriteStr(anvil_font_SlotPath(defaultSlot))
    EndIf
    PrintNl()
  ElseIf *defaultPath <> 0
    Print("  default font unavailable: ") : UartWriteStr(*defaultPath)
    PrintN("; built-in bitmap fallback active")
  Else
    Print("  default slot ") : PrintDec(defaultSlot)
    PrintN(" is not loaded; built-in bitmap fallback active")
  EndIf
EndProcedure

; Read and validate one path into an empty resident slot. The caller owns
; user-facing diagnostics and persistence policy.
Procedure.i anvil_font_LoadFile(slot.i, *path, pathBytes.i)
  Protected bytes.i
  Protected offset.i
  Protected take.i
  Protected got.i
  Protected target.i
  If slot < 0 Or slot >= #ANVIL_FONT_SLOT_COUNT Or *path = 0 Or pathBytes < 1 Or pathBytes >= #ANVIL_FONT_PATH_BYTES
    ProcedureReturn 0
  EndIf
  If AnvilTrueTypeSlotBytes(slot) > 0 : ProcedureReturn 0 : EndIf
  If HwStorageUp() = 0 : ProcedureReturn 0 : EndIf
  If HwFileOpen(*path) = 0 : ProcedureReturn 0 : EndIf
  bytes = HwFileSize()
  If bytes < 1 Or bytes > #ANVIL_FONT_MAX_BYTES
    HwFileClose() : ProcedureReturn 0
  EndIf
  target = anvil_font_SlotAddress(slot)
  offset = 0
  While offset < bytes
    take = bytes - offset
    If take > #ANVIL_FONT_READ_CHUNK : take = #ANVIL_FONT_READ_CHUNK : EndIf
    got = HwFileReadAt(offset, target + offset, take)
    If got <> take
      HwFileClose() : ProcedureReturn 0
    EndIf
    offset = offset + got
  Wend
  HwFileClose()
  If AnvilTrueTypeSlotLoad(slot, target, bytes) = 0 : ProcedureReturn 0 : EndIf
  If anvil_font_CopySlotPath(slot, *path, pathBytes) = 0 : anvil_font_ClearSlotPath(slot) : EndIf
  ProcedureReturn 1
EndProcedure

Procedure anvil_font_Size()
  Protected pixelHeight.i
  SkipSpace() : pixelHeight = ParseDec()
  If gParseOk = 0
    PrintN("!! usage: font size <pixels 1..512>") : ProcedureReturn
  EndIf
  SkipSpace()
  If gLine[gPos] <> 0
    PrintN("!! font size must be one decimal value from 1 through 512") : ProcedureReturn
  EndIf
  If AnvilTrueTypeSetPixelHeight(pixelHeight) = 0
    PrintN("!! font size must be one decimal value from 1 through 512") : ProcedureReturn
  EndIf
  PmfPutDec(pixelHeight, @gNumBuf[0])
  If SettingsSet("font.size", @gNumBuf[0]) = 0
    PrintN("!! font size is active for this boot, but could not be recorded in settings")
  Else
    PrintN("font size changed in memory; type settings save to persist it")
  EndIf
EndProcedure

Procedure anvil_font_Default()
  Protected slot.i
  Protected start.i
  Protected pathBytes.i
  SkipSpace() : start = gPos : gWordAt = gPos : SkipWord() : gWordLen = gPos - gWordAt
  If WordIs("bitmap") <> 0
    SkipSpace()
    If gLine[gPos] <> 0
      PrintN("!! usage: font default bitmap takes no arguments")
      ProcedureReturn
    EndIf
    If SettingsHas("font.default") <> 0
      If SettingsRemove("font.default") = 0
        PrintN("!! bitmap is active, but the saved default could not be cleared") : ProcedureReturn
      EndIf
    EndIf
    AnvilTrueTypeSetDefaultSlot(-1) : AnvilTrueTypeSlotDeselect()
    PrintN("built-in bitmap font is the default; type settings save to persist it")
    ProcedureReturn
  EndIf
  gPos = start : slot = anvil_font_ParseSlot()
  SkipSpace()
  If slot < 0 Or gLine[gPos] <> 0
    PrintN("!! usage: font default <loaded slot 0..3|bitmap>") : ProcedureReturn
  EndIf
  If AnvilTrueTypeSlotBytes(slot) = 0 Or anvil_font_SlotPath(slot) = 0
    PrintN("!! that font slot has no loaded path to use as the default") : ProcedureReturn
  EndIf
  pathBytes = 0
  While pathBytes < #ANVIL_FONT_PATH_BYTES And PeekA(anvil_font_SlotPath(slot)+pathBytes) <> 0 : pathBytes + 1 : Wend
  If pathBytes < 1 Or pathBytes >= #ANVIL_FONT_PATH_BYTES
    PrintN("!! the selected slot path is invalid")
    ProcedureReturn
  EndIf
  If AnvilTrueTypeSlotSelect(slot) = 0
    PrintN("!! that font slot could not be selected; default unchanged")
    ProcedureReturn
  EndIf
  If SettingsSet("font.default", anvil_font_SlotPath(slot)) = 0
    PrintN("!! font selected, but the default path could not be recorded in settings") : ProcedureReturn
  EndIf
  AnvilTrueTypeSetDefaultSlot(slot)
  Print("default font set to slot ") : PrintDec(slot) : Print(" from ")
  UartWriteStr(anvil_font_SlotPath(slot)) : PrintN("; type settings save to persist it")
EndProcedure

Procedure anvil_font_Load()
  Protected slot.i
  Protected pathBytes.i
  Protected bytes.i

  slot = anvil_font_ParseSlot()
  If slot < 0
    PrintN("!! usage: font load <slot 0..3> <path>; no font changed")
    ProcedureReturn
  EndIf
  If AnvilTrueTypeSlotBytes(slot) > 0
    PrintN("!! that font slot is occupied; select another slot or unload it first")
    ProcedureReturn
  EndIf
  pathBytes = ParseStoragePath()
  If pathBytes < 1
    PrintN("!! font load needs a valid file path after the slot number")
    ProcedureReturn
  EndIf
  SkipSpace()
  If gLine[gPos] <> 0
    PrintN("!! font load takes one file path only; slot unchanged")
    ProcedureReturn
  EndIf
  If anvil_font_LoadFile(slot, @gName[0], pathBytes) = 0
    Print("!! could not read or validate TrueType font ") : UartWriteStr(@gName[0])
    PrintN("; slot unchanged")
    ProcedureReturn
  EndIf
  bytes = AnvilTrueTypeSlotBytes(slot)
  Print("font loaded into slot ") : PrintDec(slot) : Print(", ")
  PrintDec(bytes) : PrintN(" bytes; select it with font select <slot>")
EndProcedure

Procedure anvil_font_Select()
  Protected slot.i
  Protected wordPos.i
  SkipSpace()
  wordPos = gPos
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("bitmap") <> 0
    SkipSpace()
    If gLine[gPos] <> 0
      PrintN("!! usage: font select bitmap takes no arguments")
      ProcedureReturn
    EndIf
    AnvilTrueTypeSlotDeselect()
    PrintN("built-in bitmap font selected")
    ProcedureReturn
  EndIf
  ; ParseDec expects the cursor at the start of the numeric slot token.
  ; WordIs only examines the token fields, so restore the saved position.
  gPos = wordPos
  slot = anvil_font_ParseSlot()
  SkipSpace()
  If slot < 0 Or gLine[gPos] <> 0
    PrintN("!! usage: font select <loaded slot 0..3>")
    ProcedureReturn
  EndIf
  If AnvilTrueTypeSlotSelect(slot) = 0
    Print("!! font slot ") : PrintDec(slot) : PrintN(" could not be selected; prior font was restored")
    ProcedureReturn
  EndIf
  Print("font slot ") : PrintDec(slot) : Print(" selected: ")
  If anvil_font_SlotPath(slot) <> 0 : UartWriteStr(anvil_font_SlotPath(slot)) : EndIf
  PrintNl()
EndProcedure

Procedure anvil_font_Unload()
  Protected slot.i
  Protected selected.i
  slot = anvil_font_ParseSlot()
  SkipSpace()
  If slot < 0 Or gLine[gPos] <> 0
    PrintN("!! usage: font unload <slot 0..3>")
    ProcedureReturn
  EndIf
  selected = AnvilTrueTypeSlotSelected()
  If selected = slot And AnvilTrueTypeSlotGeneration(slot) = $7FFFFFFF
    PrintN("!! that slot generation cannot advance; font remains selected")
    ProcedureReturn
  EndIf
  If selected = slot
    AnvilTrueTypeSlotDeselect()
  EndIf
  If AnvilTrueTypeSlotUnload(slot) = 0
    PrintN("!! that slot could not be unloaded")
    ProcedureReturn
  EndIf
  anvil_font_ClearSlotPath(slot)
  Print("font slot ") : PrintDec(slot) : PrintN(" unloaded")
EndProcedure

Procedure CmdFont()
  AnvilTrueTypeSlotsInit()
  SkipSpace()
  If gLine[gPos] = 0
    PrintN("usage: font info | load <slot 0..3> <path> | default <slot|bitmap> | size <pixels 1..512> | select <slot|bitmap> | unload <slot>")
    ProcedureReturn
  EndIf
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("info") <> 0
    SkipSpace()
    If gLine[gPos] <> 0
      PrintN("!! usage: font info takes no arguments")
      ProcedureReturn
    EndIf
    anvil_font_Info()
  ElseIf WordIs("load") <> 0
    anvil_font_Load()
  ElseIf WordIs("select") <> 0
    anvil_font_Select()
  ElseIf WordIs("unload") <> 0
    anvil_font_Unload()
  ElseIf WordIs("size") <> 0
    anvil_font_Size()
  ElseIf WordIs("default") <> 0
    anvil_font_Default()
  Else
    PrintN("usage: font info | load <slot 0..3> <path> | default <slot|bitmap> | size <pixels 1..512> | select <slot|bitmap> | unload <slot>")
  EndIf
EndProcedure
