; Rock Pi 4C's font texture source. The shared Anvil TrueType parser/rasterizer
; owns font interpretation; this adapter only packs its coverage into a bounded
; ARGB8888 atlas for a future Mali textured blit. It never writes the screen.
; Include after truetype_renderer.pbi, storage.pbi, and watchdog.pbi.

#ROCK_FONT_MAX_BYTES = 1048576
#ROCK_FONT_READ_CHUNK = 4096
#ROCK_FONT_FIRST = 32
#ROCK_FONT_COUNT = 95
#ROCK_FONT_CELL = 16
#ROCK_FONT_COLUMNS = 16
#ROCK_FONT_ROWS = 6
#ROCK_FONT_ATLAS_W = #ROCK_FONT_CELL * #ROCK_FONT_COLUMNS
#ROCK_FONT_ATLAS_H = #ROCK_FONT_CELL * #ROCK_FONT_ROWS
#ROCK_FONT_COVERAGE_BYTES = 1024
#ROCK_FONT_PIXEL_HEIGHT = 13

Global Dim rock_font_file.a[#ROCK_FONT_MAX_BYTES]
Global Dim rock_font_coverage.a[#ROCK_FONT_COVERAGE_BYTES]
Global Dim rock_font_atlas.l[#ROCK_FONT_ATLAS_W * #ROCK_FONT_ATLAS_H]
Global rock_font_ready.i
Global rock_font_error.i
Global rock_font_bytes.i
Global rock_font_crc.i
Global rock_font_glyphs.i

Procedure.i RockFontAtlasBase()
  If rock_font_ready = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn @rock_font_atlas[0]
EndProcedure

Procedure.i RockFontPrepareAtlas()
  Protected path.i
  Protected size.i
  Protected offset.i
  Protected take.i
  Protected got.i
  Protected code.i
  Protected glyph.i
  Protected width.i
  Protected height.i
  Protected stride.i
  Protected bearingX.i
  Protected bearingY.i
  Protected advance.i
  Protected units.i
  Protected ascent.i
  Protected descent.i
  Protected lineGap.i
  Protected lineBox.i
  Protected baseline.i
  Protected drawX.i
  Protected drawY.i
  Protected cellX.i
  Protected cellY.i
  Protected x.i
  Protected y.i
  Protected alpha.i

  If rock_font_ready <> 0 : ProcedureReturn 1 : EndIf
  rock_font_error = 0
  rock_font_glyphs = 0
  If HwStorageUp() = 0 : rock_font_error = 1 : ProcedureReturn 0 : EndIf
  path = "1:/CourierPrime-Regular.ttf"
  If HwFileOpen(path) = 0 : rock_font_error = 2 : ProcedureReturn 0 : EndIf
  size = HwFileSize()
  If size < 1 Or size > #ROCK_FONT_MAX_BYTES
    HwFileClose()
    rock_font_error = 3
    ProcedureReturn 0
  EndIf
  offset = 0
  While offset < size
    take = size - offset
    If take > #ROCK_FONT_READ_CHUNK : take = #ROCK_FONT_READ_CHUNK : EndIf
    got = HwFileReadAt(offset, @rock_font_file[0] + offset, take)
    If got <> take
      HwFileClose()
      rock_font_error = 4
      ProcedureReturn 0
    EndIf
    offset = offset + got
    RockWatchdogPet()
  Wend
  HwFileClose()
  rock_font_bytes = size
  If AnvilTrueTypeSlotLoad(0, @rock_font_file[0], size) = 0
    rock_font_error = 5
    ProcedureReturn 0
  EndIf
  If AnvilTrueTypeSlotSelect(0) = 0
    rock_font_error = 6
    ProcedureReturn 0
  EndIf
  units = AnvilTrueTypeUnitsPerEm()
  If units < 1 : rock_font_error = 7 : ProcedureReturn 0 : EndIf
  ascent = (AnvilTrueTypeAscender() * #ROCK_FONT_PIXEL_HEIGHT) / units
  descent = (AnvilTrueTypeDescender() * #ROCK_FONT_PIXEL_HEIGHT) / units
  lineGap = (AnvilTrueTypeLineGap() * #ROCK_FONT_PIXEL_HEIGHT) / units
  lineBox = ascent - descent + lineGap
  If lineBox < 1 Or lineBox > #ROCK_FONT_CELL
    rock_font_error = 8
    ProcedureReturn 0
  EndIf
  baseline = (#ROCK_FONT_CELL - lineBox) / 2 + ascent

  For code = #ROCK_FONT_FIRST To #ROCK_FONT_FIRST + #ROCK_FONT_COUNT - 1
    RockWatchdogPet()
    glyph = AnvilTrueTypeGlyphForCodepoint(code)
    If glyph < 0 Or glyph >= AnvilTrueTypeGlyphCount()
      rock_font_error = 9
      ProcedureReturn 0
    EndIf
    If AnvilTrueTypeRasterizeGlyph(glyph, #ROCK_FONT_PIXEL_HEIGHT, @rock_font_coverage[0], #ROCK_FONT_COVERAGE_BYTES, @width, @height, @stride, @bearingX, @bearingY, @advance) = 0
      rock_font_error = 10
      ProcedureReturn 0
    EndIf
    If width > 0 And height > 0
      drawX = (#ROCK_FONT_CELL - advance) / 2 + bearingX
      drawY = baseline - bearingY
      If drawX < 0 Or drawY < 0 Or drawX + width > #ROCK_FONT_CELL Or drawY + height > #ROCK_FONT_CELL
        rock_font_error = 11
        ProcedureReturn 0
      EndIf
      cellX = ((code - #ROCK_FONT_FIRST) % #ROCK_FONT_COLUMNS) * #ROCK_FONT_CELL
      cellY = ((code - #ROCK_FONT_FIRST) / #ROCK_FONT_COLUMNS) * #ROCK_FONT_CELL
      For y = 0 To height - 1
        For x = 0 To width - 1
          alpha = PeekA(@rock_font_coverage[0] + y * stride + x) & 255
          rock_font_atlas[(cellY + drawY + y) * #ROCK_FONT_ATLAS_W + cellX + drawX + x] = (alpha << 24) | $00FFFFFF
        Next
      Next
    EndIf
    rock_font_glyphs = rock_font_glyphs + 1
  Next
  rock_font_crc = Crc32(@rock_font_atlas[0], #ROCK_FONT_ATLAS_W * #ROCK_FONT_ATLAS_H * 4)
  rock_font_ready = 1
  ProcedureReturn 1
EndProcedure
