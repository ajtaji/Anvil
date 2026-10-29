; SPDX-License-Identifier: MIT
; Shared CPU bitmap-atlas raster and borrowed read-only queries.
; The composition supplies #NEON_* error constants, NeonAtlasGlyphUV and the
; shared neon_err sink through neon_frontend.pbi. It assigns neon_texSrc to
; at least #NEON_ATLAS_MAXBYTES writable bytes and neon_glyphUV to 4096 bytes
; before Ensure. Their allocation/lifetime stay with the composition. No GPU,
; native renderer, timer or tiling operation is owned or invoked here.
XIncludeFile "Anvil/Graphics/neon_bitmap_font.pbi"
XIncludeFile "Anvil/Graphics/float_bits.pbi"

#NEON_ATLAS_W       = 16
#NEON_ATLAS_MAXH    = 4096
#NEON_ATLAS_MAXBYTES = 262144   ; 16 * 4096 * 4

Global neon_texSrc.i    = 0       ; raster RGBA8 atlas, the TFU reads it
Global neon_glyphUV.i   = 0       ; per-glyph cell-edge UVs, CPU-only (unmapped)
Global neon_rasterBuilt.i    = 0  ; CPU RGBA atlas and UV table are complete
Global neon_rasterFontBits.i = 0  ; font which owns that immutable snapshot
Global neon_rasterRevision.i = -1
Global neon_rasterW.i        = 0  ; dimensions of the borrowed linear view
Global neon_rasterH.i        = 0
Global neon_rasterBytes.i    = 0  ; exact populated CPU raster extent
Global neon_atlasCols.i   = 0     ; #NEON_ATLAS_W / cell width
Global neon_atlasGlyphs.i = 0     ; last - first + 1

; The smallest power of two that is >= v (>= 1). Used to pad the atlas
; height so V = vTexel / height is exactly representable.
Procedure.i neon_NextPow2(v.i)
  Protected p.i
  p = 1
  While p < v
    p = p << 1
  Wend
  ProcedureReturn p
EndProcedure

; ----------------------------------------------------------------------
;  neon_RasterEnsure - build only the CPU-readable RGBA atlas and its
;  copied-out glyph metadata.
;
;  This is the common owner for both texture paths. The direct V3D path
;  still tiles this raster below; another renderer may copy these bytes
;  into its own staging resource. Publication is last, so no query can
;  observe a partly-filled raster or UV table.
; ----------------------------------------------------------------------
Procedure.i neon_RasterEnsure()
  Protected cols.i
  Protected nGlyph.i
  Protected rows.i
  Protected paddedH.i
  Protected g.i
  Protected ch.i
  Protected cellX0.i
  Protected cellY0.i
  Protected tx.i
  Protected ty.i
  Protected bits.i
  Protected off.i
  Protected i.i
  Protected n.i
  Protected bytes.i

  If neon_fbits = 0
    neon_err = #NEON_ERR_FONT
    ProcedureReturn #NEON_ERR_FONT
  EndIf
  If neon_rasterBuilt <> 0 And neon_rasterFontBits = neon_fbits And neon_rasterRevision = neon_fontRevision
    ProcedureReturn #NEON_OK
  EndIf
  If neon_texSrc <= 0 Or neon_glyphUV <= 0
    neon_err = #NEON_ERR_ARENA
    ProcedureReturn #NEON_ERR_ARENA
  EndIf
  If neon_fw < 1 Or neon_fw > #NEON_ATLAS_W Or (#NEON_ATLAS_W % neon_fw) <> 0 Or neon_fh < 1
    neon_err = #NEON_ERR_ARGS
    ProcedureReturn #NEON_ERR_ARGS
  EndIf

  cols = #NEON_ATLAS_W / neon_fw
  nGlyph = neon_flast - neon_ffirst + 1
  If nGlyph < 1 Or nGlyph > 256
    neon_err = #NEON_ERR_ARGS
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  rows = (nGlyph + cols - 1) / cols
  ; Keep one row outside every glyph cell.  Its first texel is an opaque
  ; white sample used by renderers which put boxes and glyphs through one
  ; sampled+tinted pipeline.  Adding the row before power-of-two padding is
  ; important: a completely full atlas must not corrupt its final glyph.
  paddedH = neon_NextPow2((rows * neon_fh) + 1)
  If paddedH > #NEON_ATLAS_MAXH
    neon_err = #NEON_ERR_ARGS
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  bytes = #NEON_ATLAS_W * paddedH * 4
  If bytes < 1 Or bytes > #NEON_ATLAS_MAXBYTES
    neon_err = #NEON_ERR_ARGS
    ProcedureReturn #NEON_ERR_ARGS
  EndIf

  n = #NEON_ATLAS_W * paddedH
  i = 0
  While i < n
    PokeN(neon_texSrc + (i * 4), $00000000)
    i = i + 1
  Wend

  g = 0
  While g < nGlyph
    ch = neon_ffirst + g
    cellX0 = (g % cols) * neon_fw
    cellY0 = (g / cols) * neon_fh
    ty = 0
    While ty < neon_fh
      bits = NeonBitmapGlyphRow(ch, ty, 0)
      tx = 0
      While tx < neon_fw
        If (bits & (128 >> tx)) <> 0
          off = (((cellY0 + ty) * #NEON_ATLAS_W) + (cellX0 + tx)) * 4
          PokeN(neon_texSrc + off, $FFFFFFFF)
        EndIf
        tx = tx + 1
      Wend
      ty = ty + 1
    Wend
    g = g + 1
  Wend

  ; The final row is reserved, so this can never overlap a glyph cell.
  PokeN(neon_texSrc + (((paddedH - 1) * #NEON_ATLAS_W) * 4), $FFFFFFFF)

  g = 0
  While g < nGlyph
    cellX0 = (g % cols) * neon_fw
    cellY0 = (g / cols) * neon_fh
    PokeN(neon_glyphUV + (g * 16) +  0, GraphicsF32RatioBits(cellX0,            #NEON_ATLAS_W))
    PokeN(neon_glyphUV + (g * 16) +  4, GraphicsF32RatioBits(cellX0 + neon_fw,  #NEON_ATLAS_W))
    PokeN(neon_glyphUV + (g * 16) +  8, GraphicsF32RatioBits(cellY0,            paddedH))
    PokeN(neon_glyphUV + (g * 16) + 12, GraphicsF32RatioBits(cellY0 + neon_fh,  paddedH))
    g = g + 1
  Wend

  neon_rasterW = #NEON_ATLAS_W
  neon_rasterH = paddedH
  neon_atlasCols = cols
  neon_atlasGlyphs = nGlyph
  neon_rasterBytes = bytes
  neon_rasterFontBits = neon_fbits
  neon_rasterRevision = neon_fontRevision
  neon_rasterBuilt = 1
  ProcedureReturn #NEON_OK
EndProcedure

; ----------------------------------------------------------------------
;  READ-ONLY CPU ATLAS CONTRACT
;
;  Neon_AtlasRasterEnsure builds the linear RGBA8 source and UV metadata
;  without submitting a TFU job. The returned base is a BORROWED view:
;  Neon retains allocation and lifetime ownership, and the caller may only
;  read/copy `Neon_AtlasRasterBytes()` bytes from it. There is deliberately
;  no setter, detach or free operation. Glyph UVs are copied into caller-
;  owned storage instead of exposing the renderer's metadata table.
;
;  A font change makes every query unavailable until Ensure succeeds for
;  that font. This is independent from the private UBLINEAR image: the
;  existing V3D path still owns and builds that image in neon_TexEnsure.
; ----------------------------------------------------------------------
Procedure.i Neon_AtlasRasterEnsure()
  ProcedureReturn neon_RasterEnsure()
EndProcedure

Procedure.i Neon_AtlasRasterReady()
  If neon_rasterBuilt = 0 Or neon_rasterFontBits <> neon_fbits Or neon_rasterRevision <> neon_fontRevision
    ProcedureReturn 0
  EndIf
  If neon_texSrc <= 0 Or neon_rasterW < 1 Or neon_rasterH < 1 Or neon_rasterBytes < 1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Neon_AtlasRasterGeneration()
  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn neon_rasterRevision
EndProcedure

Procedure.i Neon_AtlasRasterBase()
  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn neon_texSrc
EndProcedure

Procedure.i Neon_AtlasRasterWidth()
  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn neon_rasterW
EndProcedure

Procedure.i Neon_AtlasRasterHeight()
  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn neon_rasterH
EndProcedure

Procedure.i Neon_AtlasRasterBytes()
  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn neon_rasterBytes
EndProcedure

Procedure.i Neon_AtlasRasterFirstGlyph()
  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn neon_ffirst
EndProcedure

Procedure.i Neon_AtlasRasterLastGlyph()
  If Neon_AtlasRasterReady() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn neon_flast
EndProcedure

Procedure.i Neon_AtlasRasterGlyphUV(ch.i, *uv.NeonAtlasGlyphUV)
  Protected g.i
  Protected src.i
  If Neon_AtlasRasterReady() = 0 Or *uv = 0
    ProcedureReturn 0
  EndIf
  If ch < neon_ffirst Or ch > neon_flast
    ProcedureReturn 0
  EndIf
  g = ch - neon_ffirst
  If g < 0 Or g >= neon_atlasGlyphs
    ProcedureReturn 0
  EndIf
  src = neon_glyphUV + (g * 16)
  *uv\left   = PeekN(src + 0)
  *uv\right  = PeekN(src + 4)
  *uv\top    = PeekN(src + 8)
  *uv\bottom = PeekN(src + 12)
  ProcedureReturn 1
EndProcedure

; Copy the exact one-texel rectangle reserved for solid-colour geometry.
; Keeping this beside the glyph query means another renderer never has to
; know where the atlas builder placed the texel or assume that (0,0) is free.
Procedure.i Neon_AtlasRasterWhiteUV(*uv.NeonAtlasGlyphUV)
  Protected y.i
  If Neon_AtlasRasterReady() = 0 Or *uv = 0
    ProcedureReturn 0
  EndIf
  y = neon_rasterH - 1
  *uv\left   = $00000000
  *uv\right  = GraphicsF32RatioBits(1, neon_rasterW)
  *uv\top    = GraphicsF32RatioBits(y, neon_rasterH)
  *uv\bottom = $3F800000
  ProcedureReturn 1
EndProcedure
