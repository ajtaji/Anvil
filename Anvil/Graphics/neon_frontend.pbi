; Shared Neon frontend: typed callback families and logical state queries.
; Native hardware lifecycle guards, GPU ownership, timings, resource addresses
; and packet emission stay in the selected native renderer. Fallback fields
; retain their established names; the native producer updates them, while an
; external owner's read-only queries leave those values untouched.

#NEON_OK            = 0
#NEON_ERR_ARENA     = 1    ; the arena is missing, misaligned or too small
#NEON_ERR_SURFACE   = 2    ; no surface bound, or not 32 bits per pixel
#NEON_ERR_V3D       = 3    ; V3dInit() or the MMU refused - V3dError() says
#NEON_ERR_GEOMETRY  = 4    ; V3dRenderBegin() refused the surface size
#NEON_ERR_ONETILE   = 5    ; the surface is a single tile - see NeonInit()
#NEON_ERR_SHADER    = 6    ; a QPU program would not encode
#NEON_ERR_VERTS     = 7    ; the vertex arena is full
#NEON_ERR_RECORDS   = 8    ; the shader-record arena is full
#NEON_ERR_LIST      = 9    ; the bin list is full
#NEON_ERR_NOFRAME   = 10   ; a primitive outside NeonFrameBegin/End
#NEON_ERR_INFRAME   = 11   ; NeonFrameBegin() inside a frame
#NEON_ERR_BIN       = 12   ; the binner did not finish
#NEON_ERR_RENDER    = 13   ; the renderer did not finish
#NEON_ERR_FONT      = 14   ; no font bound
#NEON_ERR_ARGS      = 15   ; a parameter out of range
#NEON_ERR_BACKEND   = 16   ; selected renderer lifecycle refused

#NEON_BACKEND_NATIVE   = 0
#NEON_BACKEND_EXTERNAL = 1

#NEON_MAX_DRAWS   = 4096
#NEON_MAX_VERTS   = 262144
#NEON_MAX_TDRAWS    = 2048  ; textured DRAW CALLS - one per Neon_TextTex
#NEON_MAX_TVERTS    = 98304 ; 6 verts a glyph -> ~16k glyphs, a full screen

Structure NeonAtlasGlyphUV
  left.i
  right.i
  top.i
  bottom.i
EndStructure

Global neon_err.i      = #NEON_OK
Global gNeonReady.i    = 0        ; NeonInit() completed
Global neon_nDraws.i   = 0
Global neon_nVerts.i   = 0
Global neon_nBoxes.i   = 0        ; counted separately, for the report
Global neon_nGlyphs.i  = 0
Global neon_nRuns.i    = 0
Global neon_nClipped.i = 0        ; primitives the clip rejected outright
Global neon_clipOn.i   = 0
Global neon_nTDraws.i   = 0
Global neon_nTVerts.i   = 0
Global neon_nTGlyphs.i  = 0

; ---- optional primitive backend -------------------------------------
; The widget layer below is intentionally renderer-neutral.  Normally its
; boxes, text, scissors, fans and lines fall through to Neon's native V3D
; frame owner.
; A resident renderer such as the Vulkan chrome adapter can install these
; entry points and reuse every existing primitive unchanged without
; entering NeonFrameBegin/NeonFrameEnd recursively.  The hook signatures
; exactly match the public Neon primitive procedures.
; Ownership stays with the installer; Neon only borrows the addresses.
Global gNeonBackendBox.i          = 0
Global gNeonBackendText.i         = 0
Global gNeonBackendTextTex.i      = 0
Global gNeonBackendScissorSet.i   = 0
Global gNeonBackendScissorClear.i = 0
Global gNeonBackendFanBegin.i     = 0
Global gNeonBackendFanPoint.i     = 0
Global gNeonBackendFanEnd.i       = 0
Global gNeonBackendFanOutline.i   = 0
Global gNeonBackendLinesBegin.i   = 0
Global gNeonBackendLine.i         = 0
Global gNeonBackendLinesEnd.i     = 0
Global gNeonBackendActive.i       = 0
; Optional renderer measurements pair with the draw backend. A negative
; callback result selects the native bitmap measurement path.
Global gNeonMeasureWidth.i        = 0
Global gNeonMeasureLineHeight.i   = 0
Global gNeonMeasureActive.i       = 0
; Optional owner queries are scalar and side-effect free. Frontend error
; validation uses a separate typed writer; native hardware work stays local.
Global gNeonStateQuery.i = 0
Global gNeonStateError.i = 0
Global gNeonStateActive.i = 0
#NEON_STATE_DRAWS = 1
#NEON_STATE_BOXES = 2
#NEON_STATE_GLYPHS = 3
#NEON_STATE_RUNS = 4
#NEON_STATE_VERTS = 5
#NEON_STATE_TEX_DRAWS = 6
#NEON_STATE_TEX_GLYPHS = 7
#NEON_STATE_TEX_VERTS = 8
#NEON_STATE_CLIPPED = 9
#NEON_STATE_SCISSOR_ON = 10
#NEON_STATE_ERROR = 11
#NEON_STATE_READY = 12


; These private, never-selected targets give the compiler an exact
; signature for each indirect-call slot even in programs which use only the
; native renderer.  The active flag, not a magic null target, selects a
; backend.  Real targets arrive through NeonDrawBackendInstall below.

Procedure.i nfc_StateQueryUnbound(selector.i)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure nfc_StateErrorUnbound(code.i)
EndProcedure

Procedure.i nfc_BackendBoxUnbound(x.i, y.i, w.i, h.i, colour.i)
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure.i nfc_BackendTextUnbound(font.i, x.i, y.i, *s, colour.i)
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure.i nfc_BackendTextTexUnbound(font.i, x.i, y.i, *s, colour.i)
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure.i nfc_MeasureWidthUnbound(font.i, *s)
  ProcedureReturn -1
EndProcedure

Procedure.i nfc_MeasureLineHeightUnbound(font.i)
  ProcedureReturn -1
EndProcedure

Procedure nfc_BackendScissorSetUnbound(x.i, y.i, w.i, h.i)
EndProcedure

Procedure nfc_BackendScissorClearUnbound()
EndProcedure

Procedure.i nfc_BackendFanBeginUnbound()
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure nfc_BackendFanPointUnbound(x.i, y.i)
EndProcedure

Procedure.i nfc_BackendFanEndUnbound(colour.i)
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure.i nfc_BackendFanOutlineUnbound(colour.i)
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure.i nfc_BackendLinesBeginUnbound()
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure nfc_BackendLineUnbound(x0.i, y0.i, x1.i, y1.i)
EndProcedure

Procedure.i nfc_BackendLinesEndUnbound(colour.i)
  ProcedureReturn #NEON_ERR_NOFRAME
EndProcedure

Procedure NeonFrontendError(code.i)
  neon_err = code
  If gNeonStateActive <> 0 : gNeonStateError(code) : EndIf
EndProcedure

Procedure NeonStateBackendClear()
  gNeonStateActive = 0
  gNeonStateQuery = @nfc_StateQueryUnbound
  gNeonStateError = @nfc_StateErrorUnbound
EndProcedure

Procedure.i NeonStateBackendInstall(queryProc.i, errorProc.i)
  If queryProc = 0 And errorProc = 0
    NeonStateBackendClear() : ProcedureReturn #NEON_OK
  EndIf
  If gNeonBackendActive = 0 Or queryProc = 0 Or errorProc = 0
    NeonFrontendError(#NEON_ERR_ARGS) : ProcedureReturn #NEON_ERR_ARGS
  EndIf
  gNeonStateQuery = queryProc : gNeonStateError = errorProc
  gNeonStateActive = 1
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i NeonStateBackendActive()
  ProcedureReturn gNeonStateActive
EndProcedure

Procedure.i Neon_Error()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_ERROR) : EndIf
  ProcedureReturn neon_err
EndProcedure

Procedure.i Neon_Ready()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_READY) : EndIf
  ProcedureReturn gNeonReady
EndProcedure

; Renderer-neutral optional text measurements. The callbacks only answer
; questions; they must not render, rasterize, or mutate renderer state.

Procedure.i NeonMeasureBackendInstall(widthProc.i, lineHeightProc.i)
  If widthProc = 0 And lineHeightProc = 0
    NeonMeasureBackendClear()
    ProcedureReturn #NEON_OK
  EndIf
  If gNeonBackendActive = 0 Or widthProc = 0 Or lineHeightProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  gNeonMeasureWidth = widthProc
  gNeonMeasureLineHeight = lineHeightProc
  gNeonMeasureActive = 1
  ProcedureReturn #NEON_OK
EndProcedure

Procedure NeonMeasureBackendClear()
  gNeonMeasureWidth = @nfc_MeasureWidthUnbound
  gNeonMeasureLineHeight = @nfc_MeasureLineHeightUnbound
  gNeonMeasureActive = 0
EndProcedure

Procedure.i NeonMeasureBackendActive()
  ProcedureReturn gNeonMeasureActive
EndProcedure

; Install one complete primitive family or none.  A partial family would
; split one widget frame between two frame owners, so it is refused rather
; than guessed at.  Passing twelve zeroes restores the native Neon path.
;
; THE ADDRESSES ARE PARAMETERS, NOT FIELDS OF A STRUCTURE (forum 915). For a
; while this took a NeonDrawBackend pointer and loaded each address out of
; it. The compiler cannot follow a procedure address loaded from memory, so
; it counts it as EVERY procedure whose address the program stores into
; memory - the service table's slots among them - and the Pi 4 monitor
; stopped building: the text hook closed a loop through the USB service
; slots, whose enumeration prints boot steps, back into the console mirror
; that paints text through the hook. On this backend parameters live in
; globals, so the compiler is right to refuse a loop it cannot rule out.
; An address passed as a parameter is followed exactly, to the procedure
; the caller named.

Procedure.i NeonDrawBackendInstall(boxProc.i, textProc.i, textTexProc.i, scissorSetProc.i, scissorClearProc.i, fanBeginProc.i, fanPointProc.i, fanEndProc.i, fanOutlineProc.i, linesBeginProc.i, lineProc.i, linesEndProc.i)
  If boxProc = 0 And textProc = 0 And textTexProc = 0 And scissorSetProc = 0 And scissorClearProc = 0 And fanBeginProc = 0 And fanPointProc = 0 And fanEndProc = 0 And fanOutlineProc = 0 And linesBeginProc = 0 And lineProc = 0 And linesEndProc = 0
    NeonDrawBackendClear()
    ProcedureReturn #NEON_OK
  EndIf
  If boxProc = 0 Or textProc = 0 Or textTexProc = 0 Or scissorSetProc = 0 Or scissorClearProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  If fanBeginProc = 0 Or fanPointProc = 0 Or fanEndProc = 0 Or fanOutlineProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  If linesBeginProc = 0 Or lineProc = 0 Or linesEndProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  NeonMeasureBackendClear()
  NeonStateBackendClear()
  gNeonBackendBox          = boxProc
  gNeonBackendText         = textProc
  gNeonBackendTextTex      = textTexProc
  gNeonBackendScissorSet   = scissorSetProc
  gNeonBackendScissorClear = scissorClearProc
  gNeonBackendFanBegin     = fanBeginProc
  gNeonBackendFanPoint     = fanPointProc
  gNeonBackendFanEnd       = fanEndProc
  gNeonBackendFanOutline   = fanOutlineProc
  gNeonBackendLinesBegin   = linesBeginProc
  gNeonBackendLine         = lineProc
  gNeonBackendLinesEnd     = linesEndProc
  gNeonBackendActive       = 1
  ProcedureReturn #NEON_OK
EndProcedure

Procedure NeonDrawBackendClear()
  NeonMeasureBackendClear()
  NeonStateBackendClear()
  gNeonBackendBox          = @nfc_BackendBoxUnbound
  gNeonBackendText         = @nfc_BackendTextUnbound
  gNeonBackendTextTex      = @nfc_BackendTextTexUnbound
  gNeonBackendScissorSet   = @nfc_BackendScissorSetUnbound
  gNeonBackendScissorClear = @nfc_BackendScissorClearUnbound
  gNeonBackendFanBegin     = @nfc_BackendFanBeginUnbound
  gNeonBackendFanPoint     = @nfc_BackendFanPointUnbound
  gNeonBackendFanEnd       = @nfc_BackendFanEndUnbound
  gNeonBackendFanOutline   = @nfc_BackendFanOutlineUnbound
  gNeonBackendLinesBegin   = @nfc_BackendLinesBeginUnbound
  gNeonBackendLine         = @nfc_BackendLineUnbound
  gNeonBackendLinesEnd     = @nfc_BackendLinesEndUnbound
  gNeonBackendActive       = 0
EndProcedure

Procedure.i NeonDrawBackendActive()
  If gNeonBackendActive <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i Neon_Draws()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_DRAWS) : EndIf
  ProcedureReturn neon_nDraws
EndProcedure

Procedure.i Neon_Boxes()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_BOXES) : EndIf
  ProcedureReturn neon_nBoxes
EndProcedure

Procedure.i Neon_Glyphs()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_GLYPHS) : EndIf
  ProcedureReturn neon_nGlyphs
EndProcedure

Procedure.i Neon_Runs()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_RUNS) : EndIf
  ProcedureReturn neon_nRuns
EndProcedure

Procedure.i Neon_Verts()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_VERTS) : EndIf
  ProcedureReturn neon_nVerts
EndProcedure

Procedure.i Neon_TexDraws()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_TEX_DRAWS) : EndIf
  ProcedureReturn neon_nTDraws
EndProcedure

Procedure.i Neon_TexGlyphs()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_TEX_GLYPHS) : EndIf
  ProcedureReturn neon_nTGlyphs
EndProcedure

Procedure.i Neon_TexVerts()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_TEX_VERTS) : EndIf
  ProcedureReturn neon_nTVerts
EndProcedure

Procedure.i Neon_Clipped()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_CLIPPED) : EndIf
  ProcedureReturn neon_nClipped
EndProcedure

Procedure.i Neon_ScissorOn()
  If gNeonStateActive <> 0 : ProcedureReturn gNeonStateQuery(#NEON_STATE_SCISSOR_ON) : EndIf
  ProcedureReturn neon_clipOn
EndProcedure



; Public font binding belongs to the shared frontend. Bitmap validation/state
; retain their single owner; invalid binds preserve it and report through the
; same active frontend error owner as the other public Neon calls.
XIncludeFile "Anvil/Graphics/neon_bitmap_font.pbi"

Procedure.i NeonFontUse(bitsAddr.i, cellW.i, cellH.i, first.i, last.i)
  If NeonBitmapFontBind(bitsAddr, cellW, cellH, first, last) = 0
    NeonFrontendError(#NEON_ERR_FONT)
    ProcedureReturn #NEON_ERR_FONT
  EndIf
  ProcedureReturn #NEON_OK
EndProcedure


; Shared public text metrics: optional owner callbacks, otherwise the
; authoritative bitmap metrics. Preserve the established width scan bound.
Procedure.i Neon_LineHeight(font.i)
  Protected measured.i
  If gNeonMeasureActive <> 0
    measured = gNeonMeasureLineHeight(font)
    If measured > 0 : ProcedureReturn measured : EndIf
  EndIf
  ProcedureReturn NeonBitmapLineHeight(font)
EndProcedure

Procedure.i Neon_TextWidth(font.i, *s)
  Protected i.i
  Protected ch.i
  Protected n.i
  Protected measured.i
  If *s = 0
    ProcedureReturn 0
  EndIf
  If gNeonMeasureActive <> 0
    measured = gNeonMeasureWidth(font, *s)
    If measured >= 0 : ProcedureReturn measured : EndIf
  EndIf
  i = 0
  n = 0
  Repeat
    ch = PeekA(*s + i)
    If ch = 0
      Break
    EndIf
    ; Control codes are skipped, exactly as GlUtilities.pbi:1690-1692
    ; skips anything below 32 and DEL.
    If ch >= 32 And ch <> 127
      n = n + 1
    EndIf
    i = i + 1
    If i > 4096
      Break
    EndIf
  ForEver
  ProcedureReturn n * Neon_CharWidth(font)
EndProcedure


; Native primitive fallback is a separate complete family. Unselected typed
; targets give each slot a signature; the active flag guards all calls.
; Bind once before
; rendering starts; optional external-family clear must never erase it.
Global gNeonNativeBox.i = @nfc_BackendBoxUnbound
Global gNeonNativeText.i = @nfc_BackendTextUnbound
Global gNeonNativeTextTex.i = @nfc_BackendTextTexUnbound
Global gNeonNativeScissorSet.i = @nfc_BackendScissorSetUnbound
Global gNeonNativeScissorClear.i = @nfc_BackendScissorClearUnbound
Global gNeonNativeFanBegin.i = @nfc_BackendFanBeginUnbound
Global gNeonNativeFanPoint.i = @nfc_BackendFanPointUnbound
Global gNeonNativeFanEnd.i = @nfc_BackendFanEndUnbound
Global gNeonNativeFanOutline.i = @nfc_BackendFanOutlineUnbound
Global gNeonNativeLinesBegin.i = @nfc_BackendLinesBeginUnbound
Global gNeonNativeLine.i = @nfc_BackendLineUnbound
Global gNeonNativeLinesEnd.i = @nfc_BackendLinesEndUnbound
Global gNeonNativeDrawActive.i = 0

Procedure.i NeonNativeDrawBackendInstall(boxProc.i, textProc.i, textTexProc.i, scissorSetProc.i, scissorClearProc.i, fanBeginProc.i, fanPointProc.i, fanEndProc.i, fanOutlineProc.i, linesBeginProc.i, lineProc.i, linesEndProc.i)
  If gNeonNativeDrawActive <> 0 Or gNeonReady <> 0 Or gNeonBackendActive <> 0
    NeonFrontendError(#NEON_ERR_BACKEND)
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  If boxProc = 0 Or textProc = 0 Or textTexProc = 0 Or scissorSetProc = 0 Or scissorClearProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  If fanBeginProc = 0 Or fanPointProc = 0 Or fanEndProc = 0 Or fanOutlineProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  If linesBeginProc = 0 Or lineProc = 0 Or linesEndProc = 0
    NeonFrontendError(#NEON_ERR_ARGS)
    ProcedureReturn #NEON_ERR_ARGS
  EndIf
  gNeonNativeBox = boxProc
  gNeonNativeText = textProc
  gNeonNativeTextTex = textTexProc
  gNeonNativeScissorSet = scissorSetProc
  gNeonNativeScissorClear = scissorClearProc
  gNeonNativeFanBegin = fanBeginProc
  gNeonNativeFanPoint = fanPointProc
  gNeonNativeFanEnd = fanEndProc
  gNeonNativeFanOutline = fanOutlineProc
  gNeonNativeLinesBegin = linesBeginProc
  gNeonNativeLine = lineProc
  gNeonNativeLinesEnd = linesEndProc
  gNeonNativeDrawActive = 1
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i Neon_Box(x.i, y.i, w.i, h.i, colour.i)
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendBox(x, y, w, h, colour)
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeBox(x, y, w, h, colour)
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure.i Neon_Text(font.i, x.i, y.i, *s, colour.i)
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendText(font, x, y, *s, colour)
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeText(font, x, y, *s, colour)
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure.i Neon_TextTex(font.i, x.i, y.i, *s, colour.i)
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendTextTex(font, x, y, *s, colour)
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeTextTex(font, x, y, *s, colour)
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure Neon_ScissorSet(x.i, y.i, w.i, h.i)
  ; Preserve the native clip mirror before notifying the external owner.
  If gNeonNativeDrawActive <> 0
    gNeonNativeScissorSet(x, y, w, h)
  Else
    neon_clipOn = 1
  EndIf
  If gNeonBackendActive <> 0
    gNeonBackendScissorSet(x, y, w, h)
  EndIf
EndProcedure

Procedure Neon_ScissorClear()
  ; Preserve the native clip mirror before notifying the external owner.
  If gNeonNativeDrawActive <> 0
    gNeonNativeScissorClear()
  Else
    neon_clipOn = 0
  EndIf
  If gNeonBackendActive <> 0
    gNeonBackendScissorClear()
  EndIf
EndProcedure

Procedure.i NeonFanBegin()
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendFanBegin()
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeFanBegin()
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure NeonFanPoint(x.i, y.i)
  If gNeonBackendActive <> 0
    gNeonBackendFanPoint(x, y)
    ProcedureReturn
  EndIf
  If gNeonNativeDrawActive <> 0
    gNeonNativeFanPoint(x, y)
    ProcedureReturn
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
EndProcedure

Procedure.i NeonFanEnd(colour.i)
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendFanEnd(colour)
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeFanEnd(colour)
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure.i NeonFanOutline(colour.i)
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendFanOutline(colour)
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeFanOutline(colour)
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure.i NeonLinesBegin()
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendLinesBegin()
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeLinesBegin()
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure

Procedure NeonLine(x0.i, y0.i, x1.i, y1.i)
  If gNeonBackendActive <> 0
    gNeonBackendLine(x0, y0, x1, y1)
    ProcedureReturn
  EndIf
  If gNeonNativeDrawActive <> 0
    gNeonNativeLine(x0, y0, x1, y1)
    ProcedureReturn
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
EndProcedure

Procedure.i NeonLinesEnd(colour.i)
  If gNeonBackendActive <> 0
    ProcedureReturn gNeonBackendLinesEnd(colour)
  EndIf
  If gNeonNativeDrawActive <> 0
    ProcedureReturn gNeonNativeLinesEnd(colour)
  EndIf
  NeonFrontendError(#NEON_ERR_BACKEND)
  ProcedureReturn #NEON_ERR_BACKEND
EndProcedure
