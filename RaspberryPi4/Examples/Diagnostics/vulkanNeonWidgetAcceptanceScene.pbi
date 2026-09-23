; vulkanNeonWidgetAcceptanceScene.pbi - real Neon widgets for the Vulkan
; chrome adapter acceptance run.
;
; This is an include-only scene, not a second renderer. Every visible object
; below is emitted by the existing Neon menu, panel, text and list procedures.
; The scene never calls NeonVkChromeBox/Text/Scissor directly and never calls
; NeonFrameBegin/NeonFrameEnd. NeonVkChromeCreate installs the resident
; Neon primitive callbacks only after all resources and the atlas upload are
; ready. NeonVkChromeBegin/End own each Vulkan frame; Destroy removes the
; callbacks.
;
; Required caller order (the caller owns the Vulkan attachment and supplies
; its mapped source address/pitch for the display-owner present):
;
;   NvwaPrime()                 ; settle the immediate-mode menu, no rendering
;   NeonVkChromeCreate(physicalDevice, device, queue, commandPool, renderPass,
;                      framebuffer, #NVWA_WIDTH, #NVWA_HEIGHT,
;                      #NVWA_EXPECT_QUADS)
;   NvwaRenderFrame(@clearValue, attachmentBase, attachmentPitch)
;   NeonVkChromeDestroy()
;
; NvwaPrime installs a complete no-op primitive backend only long enough for
; the real immediate-mode widgets to measure themselves. The one Vulkan frame
; therefore has the exact settled geometry below and publishes only one
; presentation intent. RenderFrame consumes that intent once and calls the
; display owner's DisplayBlit once. It refuses a CPU fallback.
;
; The adapter's contract appends one ordered six-vertex draw for every box and
; one ordered draw containing all supported glyph quads for every nonempty
; text call. All text is ASCII and all faces are scale 1. This makes the
; geometry, draw and vertex ledgers exact rather than photograph-only.

#NVWA_OK                 = 0
#NVWA_ERR_NO_BACKEND     = -1
#NVWA_ERR_GEOMETRY       = -2
#NVWA_ERR_COUNTS         = -3
#NVWA_ERR_PRESENT        = -4
#NVWA_ERR_DMA            = -5

#NVWA_WIDTH              = 800
#NVWA_HEIGHT             = 1280
#NVWA_SETTLE_PASSES      = 1
#NVWA_GRADED_FRAME       = 1

#NVWA_BAR_X              = 0
#NVWA_BAR_Y              = 0
#NVWA_BAR_W              = 800
#NVWA_BAR_H              = 28

#NVWA_PANEL_X            = 24
#NVWA_PANEL_Y            = 120
#NVWA_PANEL_W            = 752
#NVWA_PANEL_H            = 300
#NVWA_PANEL_HEADER_H     = 26

#NVWA_TEXT_X             = 48
#NVWA_TEXT_Y             = 160

#NVWA_LIST_X             = 48
#NVWA_LIST_Y             = 200
#NVWA_LIST_W             = 704
#NVWA_LIST_H             = 64
#NVWA_LIST_ROW_H         = 20
#NVWA_LIST_VISIBLE_ROWS  = 3
#NVWA_LIST_TOTAL_ROWS    = 5

; Settled open-menu geometry at UI scale 1000. FILE is four 8-pixel glyphs
; plus 24 pixels of tab padding. The widest row is "New" plus "Ctrl+N":
; 28 + 18 + 24 + 46 + 48 = 164 pixels. Its two 24-pixel rows and one
; 9-pixel separator make a 57-pixel view and a 65-pixel panel.
#NVWA_FILE_TAB_X         = 8
#NVWA_FILE_TAB_W         = 56
#NVWA_DROP_X             = 8
#NVWA_DROP_Y             = 28
#NVWA_DROP_W             = 164
#NVWA_DROP_VIEW_Y        = 32
#NVWA_DROP_VIEW_H        = 57
#NVWA_DROP_PANEL_H       = 65

; Callback and Vulkan ledger for the settled frame.
#NVWA_EXPECT_BOX_CALLS       = 35
#NVWA_EXPECT_TEXT_CALLS      = 12
#NVWA_EXPECT_GLYPH_QUADS     = 74
#NVWA_EXPECT_QUADS           = 109
#NVWA_EXPECT_DRAWS           = 47
#NVWA_EXPECT_VERTICES        = 654
#NVWA_EXPECT_SCISSOR_SETS    = 2
#NVWA_EXPECT_SCISSOR_CLEARS  = 2
#NVWA_EXPECT_SCISSOR_CALLS   = 4
#NVWA_EXPECT_SCISSOR_STATES  = 5

; Draw records are zero based and immutable. Begin owns state 1, the full
; surface. The clipped list, the restored full surface, the open drop-down and
; its final clear own states 2 through 5.
#NVWA_FULL0_FIRST        = 0
#NVWA_FULL0_DRAWS        = 12
#NVWA_LIST_FIRST         = 12
#NVWA_LIST_DRAWS         = 7
#NVWA_FULL1_FIRST        = 19
#NVWA_FULL1_DRAWS        = 16
#NVWA_MENU_FIRST         = 35
#NVWA_MENU_DRAWS         = 11
#NVWA_FULL2_FIRST        = 46
#NVWA_FULL2_DRAWS        = 1

; Exact list clip. Row 3 begins at y=260 and extends to y=280, so only its
; first four rows of pixels survive this rectangle. Row 4 begins below it and
; the real Neon_ListItem rejects that row before it emits a primitive.
#NVWA_LIST_CLIP_X        = 48
#NVWA_LIST_CLIP_Y        = 200
#NVWA_LIST_CLIP_W        = 694
#NVWA_LIST_CLIP_H        = 64
#NVWA_PARTIAL_ROW_Y      = 260
#NVWA_PARTIAL_ROW_VISIBLE = 4
#NVWA_HIDDEN_ROW_Y       = 280

Procedure.i NvwaExpectedBoxCalls()
  ProcedureReturn #NVWA_EXPECT_BOX_CALLS
EndProcedure

Procedure.i NvwaExpectedTextCalls()
  ProcedureReturn #NVWA_EXPECT_TEXT_CALLS
EndProcedure

Procedure.i NvwaExpectedGlyphQuads()
  ProcedureReturn #NVWA_EXPECT_GLYPH_QUADS
EndProcedure

Procedure.i NvwaExpectedQuads()
  ProcedureReturn #NVWA_EXPECT_QUADS
EndProcedure

Procedure.i NvwaExpectedDraws()
  ProcedureReturn #NVWA_EXPECT_DRAWS
EndProcedure

Procedure.i NvwaExpectedVertices()
  ProcedureReturn #NVWA_EXPECT_VERTICES
EndProcedure

Procedure.i NvwaExpectedScissorCalls()
  ProcedureReturn #NVWA_EXPECT_SCISSOR_CALLS
EndProcedure

; No-op primitive family used only to run the widgets' first measurement pass.
; It deliberately has the same signatures as Neon_Box/Text/Scissor. Nothing
; here records pixels, vertices or Vulkan commands.
Procedure.i nvwaPrimeBox(x.i, y.i, w.i, h.i, colour.i)
  ProcedureReturn #NEON_OK
EndProcedure

Procedure.i nvwaPrimeText(font.i, x.i, y.i, *s, colour.i)
  ProcedureReturn #NEON_OK
EndProcedure

Procedure nvwaPrimeScissorSet(x.i, y.i, w.i, h.i)
EndProcedure

Procedure nvwaPrimeScissorClear()
EndProcedure

Procedure.i NvwaCompose()
  ; A missing adapter must fail visibly. Falling through to native Neon would
  ; enter a second V3D frame owner and invalidate this acceptance run.
  If NeonDrawBackendActive() = 0
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf

  NeonSetUIScale(1000)
  Neon_ChromeBeginFrame(-4096, -4096, 0, 0, 0, 0, 16)

  ; Ground and a real titled panel.
  Neon_Box(0, 0, #NVWA_WIDTH, #NVWA_HEIGHT, Neon_C_Bg)
  Neon_Panel(#NVWA_PANEL_X, #NVWA_PANEL_Y, #NVWA_PANEL_W, #NVWA_PANEL_H, "PROJECT", Neon_C_Acc, #NVWA_PANEL_HEADER_H)
  Neon_Text(#NEON_FONT_UI, #NVWA_TEXT_X, #NVWA_TEXT_Y, "VULKAN PATH", Neon_C_Text)

  ; The list owns a real widget clip and scrollbar. The fourth visible call is
  ; partially clipped; the fifth is wholly outside and emits no primitive.
  Neon_ListBegin(7001, #NVWA_LIST_X, #NVWA_LIST_Y, #NVWA_LIST_W, #NVWA_LIST_H, #NVWA_LIST_ROW_H)
  Neon_ListItem("Core",        0, 0, 1, "")
  Neon_ListItem("Renderer",    1, 1, 0, "42")
  Neon_ListItem("Atlas",       2, 0, 0, "")
  Neon_ListItem("Clipped row", 2, 0, 0, "")
  Neon_ListItem("HIDDEN",      2, 0, 0, "")
  Neon_ListEnd()

  ; Menus are last, as in the IDE, so the open FILE drop-down overlays other
  ; widgets. Neon_MenuSelectRoot is the menu's own deterministic open action;
  ; no private box or text substitutes the widget.
  Neon_MenuSelectRoot(0)
  Neon_MenuBarBegin(#NVWA_BAR_X, #NVWA_BAR_Y, #NVWA_BAR_W, #NVWA_BAR_H)
  If Neon_MenuBegin("FILE") <> 0
    Neon_MenuItem("New", "Ctrl+N", 1, 0)
    Neon_MenuItem("Word Wrap", "", 1, 1)
    Neon_MenuSeparator()
  EndIf
  Neon_MenuEnd()

  If Neon_MenuBegin("HELP") <> 0
    Neon_MenuItem("About", "", 1, 0)
  EndIf
  Neon_MenuEnd()
  Neon_MenuBarEnd()

  Neon_ChromeEndFrame()
  If Neon_ScissorOn() <> 0
    ProcedureReturn #NVWA_ERR_GEOMETRY
  EndIf
  ProcedureReturn #NVWA_OK
EndProcedure

; Settle the real menu's next-frame dimensions without opening a native Neon
; V3D frame and without allocating any Vulkan object. It must run before
; NeonVkChromeCreate so Create can replace the no-op family with the resident
; adapter only after every Vulkan resource and the atlas upload succeed.
Procedure.i NvwaPrime()
  Define rc.i
  If NeonDrawBackendActive() <> 0
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf
  If Neon_SurfaceW() <> #NVWA_WIDTH Or Neon_SurfaceH() <> #NVWA_HEIGHT
    ProcedureReturn #NVWA_ERR_GEOMETRY
  EndIf
  rc = NeonDrawBackendInstall(@nvwaPrimeBox, @nvwaPrimeText, @nvwaPrimeScissorSet, @nvwaPrimeScissorClear, @neon_BackendFanBeginUnbound, @neon_BackendFanPointUnbound, @neon_BackendFanEndUnbound, @neon_BackendFanOutlineUnbound, @neon_BackendLinesBeginUnbound, @neon_BackendLineUnbound, @neon_BackendLinesEndUnbound)
  If rc <> #NEON_OK
    ProcedureReturn rc
  EndIf
  rc = NvwaCompose()
  NeonDrawBackendClear()
  ProcedureReturn rc
EndProcedure

; Render exactly one settled frame, consume exactly one adapter presentation
; intent, then present through the display owner's DMA path exactly once.
; Display DMA must already be initialized, bounded, bound and enabled.
Procedure.i NvwaRenderFrame(*clearValue, sourceBase.i, sourcePitch.i)
  Define rc.i
  Define endRc.i
  Define dmaOps.i
  Define dmaFallbacks.i
  Define dmaRefusals.i

  If NeonVkChromeReady() = 0 Or NeonDrawBackendActive() = 0
    ProcedureReturn #NVWA_ERR_NO_BACKEND
  EndIf
  If Neon_SurfaceW() <> #NVWA_WIDTH Or Neon_SurfaceH() <> #NVWA_HEIGHT
    ProcedureReturn #NVWA_ERR_GEOMETRY
  EndIf
  If sourceBase <= 0 Or sourcePitch < (#NVWA_WIDTH * 4)
    ProcedureReturn #NVWA_ERR_GEOMETRY
  EndIf

  rc = NeonVkChromeBegin(*clearValue)
  If rc <> #VK_SUCCESS
    ProcedureReturn rc
  EndIf
  rc = NvwaCompose()
  endRc = NeonVkChromeEnd()
  If rc <> #NVWA_OK
    ; End closes the mapped command frame even when widget composition fails.
    If NeonVkChromePresentPending() <> 0
      NeonVkChromePresentConsume()
    EndIf
    ProcedureReturn rc
  EndIf
  If endRc <> #VK_SUCCESS
    ProcedureReturn endRc
  EndIf
  If NeonVkChromeDrawCount() <> #NVWA_EXPECT_DRAWS Or NeonVkChromeVertexCount() <> #NVWA_EXPECT_VERTICES
    If NeonVkChromePresentPending() <> 0
      NeonVkChromePresentConsume()
    EndIf
    ProcedureReturn #NVWA_ERR_COUNTS
  EndIf
  If NeonVkChromePresentPending() <> 1
    ProcedureReturn #NVWA_ERR_PRESENT
  EndIf
  If NeonVkChromePresentConsume() <> 1
    ProcedureReturn #NVWA_ERR_PRESENT
  EndIf
  If NeonVkChromePresentPending() <> 0
    ProcedureReturn #NVWA_ERR_PRESENT
  EndIf

  dmaOps = DisplayDmaOps()
  dmaFallbacks = DisplayDmaFallbacks()
  dmaRefusals = DisplayDmaRefusals()
  DisplayBlit(sourceBase, sourcePitch, 0, 0, #NVWA_WIDTH, #NVWA_HEIGHT)
  If DisplayDmaOps() <> dmaOps + 1 Or DisplayDmaFallbacks() <> dmaFallbacks Or DisplayDmaRefusals() <> dmaRefusals
    ProcedureReturn #NVWA_ERR_DMA
  EndIf
  ProcedureReturn #NVWA_OK
EndProcedure
