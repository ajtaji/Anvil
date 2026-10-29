; Shared fixed-bitmap font state and metrics for Neon renderers.
; No device, timer, error sink or renderer dependency. Legacy neon_* fields
; retain their names for native atlas code but have this single shared owner.
; Glyph rows are MSB-left and byte-padded. The legacy row reader consumes
; the first byte of each row; callers supply an in-range glyph and row.
; A selected face is an integer scale and optional one-pixel emboldening,
; independently of a desktop TrueType font's point-size or DPI semantics.

Global neon_fbits.i    = 0        ; address of the 1bpp glyph blob
Global neon_fw.i       = 0        ; cell width, pixels
Global neon_fh.i       = 0        ; cell height
Global neon_frb.i      = 0        ; bytes per glyph row
Global neon_ffirst.i   = 0
Global neon_flast.i    = 0

; Four font slots, matching the engine's four faces (GlUIChrome.pbi:73-76).
; The engine's are separate rasterised atlases at different point sizes;
; here they are the same 1bpp cell at integer scales, which is what a
; 1-bit font can honestly do. Index 0 UI, 1 small, 2 mono, 3 bold.
Global Dim neon_fontScale.i[4]
Global Dim neon_fontEmbolden.i[4]

Global neon_fontRevision.i = 0

#NEON_FONT_UI    = 0
#NEON_FONT_SMALL = 1
#NEON_FONT_MONO  = 2
#NEON_FONT_BOLD  = 3

Procedure.i NeonBitmapFontScale(font.i)
  If font < 0 Or font > 3
    ProcedureReturn 1
  EndIf
  If neon_fontScale[font] < 1
    ProcedureReturn 1
  EndIf
  ProcedureReturn neon_fontScale[font]
EndProcedure

Procedure NeonFontSetup(idx.i, scale.i, bold.i)
  If idx < 0 Or idx > 3
    ProcedureReturn
  EndIf
  If scale < 1
    scale = 1
  EndIf
  neon_fontScale[idx] = scale
  If bold <> 0
    neon_fontEmbolden[idx] = 1
  Else
    neon_fontEmbolden[idx] = 0
  EndIf
EndProcedure

Procedure.i Neon_FontUI()
  ProcedureReturn #NEON_FONT_UI
EndProcedure

Procedure.i Neon_FontSmall()
  ProcedureReturn #NEON_FONT_SMALL
EndProcedure

Procedure.i Neon_FontMono()
  ProcedureReturn #NEON_FONT_MONO
EndProcedure

Procedure.i Neon_FontBold()
  ProcedureReturn #NEON_FONT_BOLD
EndProcedure

Procedure.i Neon_PointsForPixelHeight(pixels.i)
  Protected pt.i
  pt = ((pixels * 75) + 50) / 100
  If pt < 5
    pt = 5
  EndIf
  ProcedureReturn pt
EndProcedure

Procedure NeonFontDefaults()
  NeonFontSetup(#NEON_FONT_UI,    1, 0)
  NeonFontSetup(#NEON_FONT_SMALL, 1, 0)
  NeonFontSetup(#NEON_FONT_MONO,  1, 0)
  NeonFontSetup(#NEON_FONT_BOLD,  1, 1)
EndProcedure

Procedure.i Neon_CharWidth(font.i)
  ProcedureReturn neon_fw * NeonBitmapFontScale(font)
EndProcedure

Procedure.i NeonBitmapLineHeight(font.i)
  ProcedureReturn neon_fh * NeonBitmapFontScale(font)
EndProcedure

Procedure.i NeonBitmapFontBold(font.i)
  If font < 0 Or font > 3
    ProcedureReturn 0
  EndIf
  If neon_fontEmbolden[font] <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i NeonBitmapGlyphRow(ch.i, row.i, bold.i)
  Protected b.i
  b = PeekA(neon_fbits + (((ch - neon_ffirst) * neon_fh) + row) * neon_frb)
  If bold <> 0
    b = (b | (b >> 1)) & $FF
  EndIf
  ProcedureReturn b
EndProcedure

; Return 1 on publication, 0 on invalid arguments with all state preserved.
; The native wrapper retains its own frontend-error reporting contract.
Procedure.i NeonBitmapFontBind(bitsAddr.i, cellW.i, cellH.i, first.i, last.i)
  If bitsAddr <= 0 Or cellW < 1 Or cellH < 1 Or last < first
    ProcedureReturn 0
  EndIf
  neon_fbits  = bitsAddr
  neon_fw     = cellW
  neon_fh     = cellH
  neon_frb    = (cellW + 7) / 8
  neon_ffirst = first
  neon_flast  = last
  ; An explicit font selection invalidates both atlas forms even if the caller
  ; reused the same bitmap address with changed glyphs or cell metadata.
  neon_fontRevision = neon_fontRevision + 1
  ProcedureReturn 1
EndProcedure
