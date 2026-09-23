; ======================================================================
;  Rock Pi 4C standard Anvil screen adapter.
;
;  INCLUDE ORDER: after the architectural timer, UART2, watchdog, RK DMA,
;  display_common/HDMI display publication, Anvil/Hal/hal.pbi,
;  Anvil/Core/build_identity.pbi, Anvil/Graphics/text_glyph.pbi and
;  Anvil/Graphics/anvil_logo.pbi. This file includes nothing itself.
;
;  UART OUTPUT NEVER DRAWS. RockScreenMirrorByte[Style] only appends to a
;  bounded ring. RockScreenService owns every pixel write and consumes at
;  most 32 bytes and 1500 microseconds per call after the banner is complete.
;  A busy serial producer therefore cannot wait for scanout.
;
;  The layout is Anvil's existing Pi 3 / Pi 4 layout: a fixed 120-pixel top
;  band, the shared 76 x 74 anvil picture, the established steel/orange/faint
;  palette, immutable build label and the console below it. There is no
;  Rock-specific visual design in this adapter.
; ======================================================================

#ROCK_SCREEN_RING_BYTES = 8192
#ROCK_SCREEN_RING_MASK = 8191
#ROCK_SCREEN_SERVICE_BYTES = 32
#ROCK_SCREEN_SERVICE_US = 1500
#ROCK_SCREEN_ROW_IDLE_US = 10000
#ROCK_SCREEN_DMA_MIN_BYTES = 256
#ROCK_SCREEN_SCROLL_CHUNK_BYTES = 65536
#ROCK_SCREEN_CPU_WATCHDOG_BYTES = 262144
#ROCK_SCREEN_BANNER_H = 120
#ROCK_SCREEN_CELL_W = 10
#ROCK_SCREEN_CELL_H = 16
; Match the maximum scanout width admitted by the display contract.
#ROCK_SCREEN_MAX_WIDTH = 2560
#ROCK_SCREEN_ROW_BUFFER_BYTES = #ROCK_SCREEN_MAX_WIDTH * #ROCK_SCREEN_CELL_H * 4
#ROCK_SCREEN_STYLE_NORMAL = 0
#ROCK_SCREEN_STYLE_PROMPT = 1

#ROCK_SCREEN_BG = $FF000028
#ROCK_SCREEN_STEEL = $FFE2E8F0
#ROCK_SCREEN_ORANGE = $FFFF9430
#ROCK_SCREEN_FAINT = $FF788496
#ROCK_SCREEN_LOGO_NAME = $FFFFB040
#ROCK_SCREEN_PROMPT = $FF50FF78

Global rock_screen_attached.i
Global rock_screen_ready.i
Global rock_screen_fault.i
Global rock_screen_frame.i
Global rock_screen_cols.i
Global rock_screen_rows.i
Global rock_screen_col.i
Global rock_screen_row.i
Global rock_screen_banner_phase.i
Global rock_screen_banner_row.i
Global rock_screen_banner_pos.i
Global rock_screen_style.i
Global rock_screen_head.i
Global rock_screen_tail.i
Global rock_screen_dropped.i
Global rock_screen_scroll_active.i
Global rock_screen_scroll_offset.i
Global rock_screen_scroll_bytes.i
Global rock_screen_scroll_gap.i
Global rock_screen_scroll_dst.i
Global rock_screen_dma_scroll_bytes.i
Global rock_screen_cpu_scroll_bytes.i
Global rock_screen_row_buffer_active.i
Global rock_screen_row_buffer_dirty.i
Global rock_screen_text_render.i
Global rock_screen_row_last_ticks.i
Global rock_screen_dma_text_bytes.i
Global rock_screen_cpu_text_bytes.i
Global Dim rock_screen_ring.a[#ROCK_SCREEN_RING_BYTES]
Global Dim rock_screen_ring_style.a[#ROCK_SCREEN_RING_BYTES]
Global Dim rock_screen_row_buffer.l[#ROCK_SCREEN_MAX_WIDTH * #ROCK_SCREEN_CELL_H]

; Return nonzero once the service call has consumed its time slice. A timer
; that has not been initialised cannot enforce a deadline, so the independent
; byte/row limits remain the bound in that early state.
Procedure.i RockScreenTimeExpired(start.i)
  Protected now.i
  Protected budget.i
  If rock_timer_frequency <= 0
    ProcedureReturn 0
  EndIf
  budget = (rock_timer_frequency / 1000000) * #ROCK_SCREEN_SERVICE_US
  now = RockTimerTicks()
  If now < start
    ProcedureReturn 1
  EndIf
  ProcedureReturn Bool(now - start >= budget)
EndProcedure

Procedure RockScreenCpuFill32(dst.i, value.i, bytes.i)
  Protected offset.i
  offset = 0
  While offset + 4 <= bytes
    If (offset & (#ROCK_SCREEN_CPU_WATCHDOG_BYTES - 1)) = 0
      RockWatchdogPet()
    EndIf
    PokeL(dst + offset, value)
    offset = offset + 4
  Wend
EndProcedure

; Copy toward the lower address. That is the only direction the terminal
; scroll uses, so the CPU fallback remains overlap-safe without a second path.
Procedure RockScreenCpuCopyUp(dst.i, src.i, bytes.i)
  Protected offset.i
  offset = 0
  While offset + 4 <= bytes
    If (offset & (#ROCK_SCREEN_CPU_WATCHDOG_BYTES - 1)) = 0
      RockWatchdogPet()
    EndIf
    PokeL(dst + offset, PeekL(src + offset))
    offset = offset + 4
  Wend
EndProcedure

; One rectangle over the already-published linear ARGB8888 surface. Opaque
; runs use the RK DMA engine at 256 bytes and above. A declined transfer is a
; request for the CPU fallback, not a partially rendered frame.
Procedure.i RockScreenFillRect(x.i, y.i, w.i, h.i, colour.i)
  Protected sw.i
  Protected sh.i
  Protected row.i
  Protected dst.i
  Protected bytes.i
  Protected total.i
  If rock_display_ready = 0 Or rock_display_buffer = 0
    ProcedureReturn 0
  EndIf
  If w <= 0 Or h <= 0
    ProcedureReturn 1
  EndIf
  sw = rock_display_width
  sh = rock_display_height
  If x < 0 : w = w + x : x = 0 : EndIf
  If y < 0 : h = h + y : y = 0 : EndIf
  If x + w > sw : w = sw - x : EndIf
  If y + h > sh : h = sh - y : EndIf
  If w <= 0 Or h <= 0
    ProcedureReturn 1
  EndIf
  bytes = w * 4
  ; A full tightly packed rectangle is one DMA fill. Otherwise each row is a
  ; separate contiguous transfer; framebuffer pitch is never guessed.
  If x = 0 And w = sw And rock_display_pitch = bytes
    total = bytes * h
    dst = rock_display_buffer + y * rock_display_pitch
    If rock_dma_pl330_ready <> 0 And total >= #ROCK_SCREEN_DMA_MIN_BYTES
      If RockDmaFill32(dst, colour, total) <> 0
        ProcedureReturn 1
      EndIf
    EndIf
    RockScreenCpuFill32(dst, colour, total)
    ProcedureReturn 1
  EndIf
  row = 0
  While row < h
    dst = rock_display_buffer + (y + row) * rock_display_pitch + x * 4
    If rock_dma_pl330_ready <> 0 And bytes >= #ROCK_SCREEN_DMA_MIN_BYTES
      If RockDmaFill32(dst, colour, bytes) = 0
        RockScreenCpuFill32(dst, colour, bytes)
      EndIf
    Else
      RockScreenCpuFill32(dst, colour, bytes)
    EndIf
    row = row + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure RockScreenPixel(x.i, y.i, colour.i)
  If rock_display_ready = 0 Or rock_display_buffer = 0
    ProcedureReturn
  EndIf
  If x < 0 Or y < 0 Or x >= rock_display_width Or y >= rock_display_height
    ProcedureReturn
  EndIf
  If rock_screen_text_render <> 0
    PokeL(@rock_screen_row_buffer[0] + (y - #ROCK_SCREEN_BANNER_H - rock_screen_row * #ROCK_SCREEN_CELL_H) * rock_display_pitch + x * 4, colour)
    rock_screen_row_buffer_dirty = 1
  Else
    PokeL(rock_display_buffer + y * rock_display_pitch + x * 4, colour)
  EndIf
EndProcedure

; The shared 4 x 7 fallback face. The fixed 10 x 16 terminal cell is the Pi 3
; convention; the two unused columns and rows make adjacent glyphs readable.
Procedure RockScreenGlyph(code.i, x.i, y.i, scale.i, colour.i)
  Protected bits.i
  Protected row.i
  Protected col.i
  Protected sx.i
  Protected sy.i
  If code < 32 Or code > 126 : code = 63 : EndIf
  If scale < 1
    ProcedureReturn
  EndIf
  bits = AnvilTextGlyph(code)
  For row = 0 To 6
    For col = 0 To 3
      If (bits & (1 << ((6 - row) * 4 + 3 - col))) <> 0
        For sy = 0 To scale - 1
          For sx = 0 To scale - 1
            RockScreenPixel(x + col * scale + sx, y + row * scale + sy, colour)
          Next
        Next
      EndIf
    Next
  Next
EndProcedure

Procedure.i RockScreenTextRange(text.i, x.i, y.i, scale.i, colour.i, first.i, count.i)
  Protected index.i
  Protected code.i
  Protected drawn.i
  If text = 0 Or count <= 0 : ProcedureReturn first : EndIf
  index = first
  While drawn < count
    code = PeekA(text + index) & 255
    If code = 0 : Break : EndIf
    RockScreenGlyph(code, x + index * (5 * scale), y, scale, colour)
    index = index + 1
    drawn = drawn + 1
  Wend
  ProcedureReturn index
EndProcedure

Procedure.i RockScreenText(text.i, x.i, y.i, scale.i, colour.i)
  ProcedureReturn RockScreenTextRange(text, x, y, scale, colour, 0, 4096)
EndProcedure

; VOP WIN0 scans one linear, pitched surface. PL330 copies a contiguous span,
; so a complete terminal row is rasterized offscreen and published as one DMA
; transfer. The row buffer is owned by this adapter and never scanned directly.
Procedure RockScreenBufferEnsure()
  If rock_screen_row_buffer_active = 0
    If rock_dma_pl330_ready <> 0
      If RockDmaFill32(@rock_screen_row_buffer[0], #ROCK_SCREEN_BG, rock_display_pitch * #ROCK_SCREEN_CELL_H) = 0
        RockScreenCpuFill32(@rock_screen_row_buffer[0], #ROCK_SCREEN_BG, rock_display_pitch * #ROCK_SCREEN_CELL_H)
      EndIf
    Else
      RockScreenCpuFill32(@rock_screen_row_buffer[0], #ROCK_SCREEN_BG, rock_display_pitch * #ROCK_SCREEN_CELL_H)
    EndIf
    rock_screen_row_buffer_active = 1
    rock_screen_row_buffer_dirty = 0
  EndIf
EndProcedure

Procedure RockScreenBufferPublish()
  Protected dst.i
  Protected bytes.i
  If rock_screen_row_buffer_active = 0 Or rock_screen_row_buffer_dirty = 0
    ProcedureReturn
  EndIf
  bytes = rock_display_pitch * #ROCK_SCREEN_CELL_H
  dst = rock_display_buffer + (#ROCK_SCREEN_BANNER_H + rock_screen_row * #ROCK_SCREEN_CELL_H) * rock_display_pitch
  If rock_dma_pl330_ready <> 0
    If RockDmaCopy(dst, @rock_screen_row_buffer[0], bytes) <> 0
      rock_screen_dma_text_bytes = rock_screen_dma_text_bytes + bytes
    Else
      RockScreenCpuCopyUp(dst, @rock_screen_row_buffer[0], bytes)
      rock_screen_cpu_text_bytes = rock_screen_cpu_text_bytes + bytes
    EndIf
  Else
    RockScreenCpuCopyUp(dst, @rock_screen_row_buffer[0], bytes)
    rock_screen_cpu_text_bytes = rock_screen_cpu_text_bytes + bytes
  EndIf
  rock_screen_row_buffer_dirty = 0
  RockWatchdogPet()
EndProcedure

Procedure RockScreenClearCell(col.i, row.i)
  Protected line.i
  RockScreenBufferEnsure()
  For line = 0 To #ROCK_SCREEN_CELL_H - 1
    RockScreenCpuFill32(@rock_screen_row_buffer[0] + line * rock_display_pitch + col * #ROCK_SCREEN_CELL_W * 4, #ROCK_SCREEN_BG, #ROCK_SCREEN_CELL_W * 4)
  Next
  rock_screen_row_buffer_dirty = 1
EndProcedure

Procedure RockScreenScroll()
  If rock_screen_rows < 1
    ProcedureReturn
  EndIf
  rock_screen_scroll_dst = rock_display_buffer + #ROCK_SCREEN_BANNER_H * rock_display_pitch
  rock_screen_scroll_gap = #ROCK_SCREEN_CELL_H * rock_display_pitch
  rock_screen_scroll_bytes = (rock_screen_rows - 1) * rock_screen_scroll_gap
  rock_screen_scroll_offset = 0
  rock_screen_scroll_active = 1
  rock_screen_row = rock_screen_rows - 1
EndProcedure

; PL330 refuses overlapping source/destination ranges. Each forward chunk is
; no larger than the one-line gap, so its own ranges do not overlap and later
; source bytes remain intact. One bounded chunk per service call keeps UART
; polling independent of a full-frame scroll.
Procedure RockScreenScrollService()
  Protected chunk.i
  Protected dst.i
  Protected src.i
  If rock_screen_scroll_active = 0
    ProcedureReturn
  EndIf
  If rock_screen_scroll_offset < rock_screen_scroll_bytes
    chunk = rock_screen_scroll_bytes - rock_screen_scroll_offset
    If chunk > #ROCK_SCREEN_SCROLL_CHUNK_BYTES : chunk = #ROCK_SCREEN_SCROLL_CHUNK_BYTES : EndIf
    If chunk > rock_screen_scroll_gap : chunk = rock_screen_scroll_gap : EndIf
    dst = rock_screen_scroll_dst + rock_screen_scroll_offset
    src = dst + rock_screen_scroll_gap
    If rock_dma_pl330_ready <> 0 And chunk >= #ROCK_SCREEN_DMA_MIN_BYTES
      If RockDmaCopy(dst, src, chunk) <> 0
        rock_screen_dma_scroll_bytes = rock_screen_dma_scroll_bytes + chunk
      Else
        RockScreenCpuCopyUp(dst, src, chunk)
        rock_screen_cpu_scroll_bytes = rock_screen_cpu_scroll_bytes + chunk
      EndIf
    Else
      RockScreenCpuCopyUp(dst, src, chunk)
      rock_screen_cpu_scroll_bytes = rock_screen_cpu_scroll_bytes + chunk
    EndIf
    rock_screen_scroll_offset = rock_screen_scroll_offset + chunk
    RockWatchdogPet()
    ProcedureReturn
  EndIf
  RockScreenFillRect(0, #ROCK_SCREEN_BANNER_H + (rock_screen_rows - 1) * #ROCK_SCREEN_CELL_H, rock_display_width, #ROCK_SCREEN_CELL_H, #ROCK_SCREEN_BG)
  rock_screen_scroll_active = 0
  RockWatchdogPet()
EndProcedure

Procedure RockScreenNewline()
  RockScreenBufferPublish()
  rock_screen_row_buffer_active = 0
  rock_screen_col = 0
  rock_screen_row = rock_screen_row + 1
  If rock_screen_row >= rock_screen_rows
    RockScreenScroll()
  EndIf
EndProcedure

Procedure RockScreenPaintByte(code.i, style.i)
  Protected spaces.i
  Protected fg.i
  If rock_screen_ready = 0 Or rock_screen_fault <> 0
    ProcedureReturn
  EndIf
  Select code
    Case 13
      rock_screen_col = 0
    Case 10
      RockScreenNewline()
    Case 8
      If rock_screen_col > 0
        rock_screen_col = rock_screen_col - 1
        RockScreenClearCell(rock_screen_col, rock_screen_row)
      EndIf
    Case 127
      If rock_screen_col > 0
        rock_screen_col = rock_screen_col - 1
        RockScreenClearCell(rock_screen_col, rock_screen_row)
      EndIf
    Case 9
      spaces = 4 - (rock_screen_col & 3)
      While spaces > 0
        If rock_screen_col >= rock_screen_cols : RockScreenNewline() : EndIf
        RockScreenClearCell(rock_screen_col, rock_screen_row)
        rock_screen_col = rock_screen_col + 1
        spaces = spaces - 1
      Wend
    Default
      If code < 32
        ProcedureReturn
      EndIf
      If rock_screen_col >= rock_screen_cols : RockScreenNewline() : EndIf
      RockScreenClearCell(rock_screen_col, rock_screen_row)
      fg = #ROCK_SCREEN_STEEL
      If style = #ROCK_SCREEN_STYLE_PROMPT : fg = #ROCK_SCREEN_PROMPT : EndIf
      rock_screen_text_render = 1
      RockScreenGlyph(code, rock_screen_col * #ROCK_SCREEN_CELL_W, #ROCK_SCREEN_BANNER_H + rock_screen_row * #ROCK_SCREEN_CELL_H, 2, fg)
      rock_screen_text_render = 0
      rock_screen_col = rock_screen_col + 1
  EndSelect
EndProcedure

; Producer-side style selection. It changes metadata only and cannot enter the
; renderer. Existing serial output can leave this at NORMAL forever.
Procedure RockScreenMirrorStyle(style.i)
  If style = #ROCK_SCREEN_STYLE_PROMPT
    rock_screen_style = #ROCK_SCREEN_STYLE_PROMPT
  Else
    rock_screen_style = #ROCK_SCREEN_STYLE_NORMAL
  EndIf
EndProcedure

Procedure RockScreenMirrorByteStyle(code.i, style.i)
  Protected nextHead.i
  If code < 0 Or code > 255
    ProcedureReturn
  EndIf
  nextHead = (rock_screen_head + 1) & #ROCK_SCREEN_RING_MASK
  If nextHead = rock_screen_tail
    rock_screen_tail = (rock_screen_tail + 1) & #ROCK_SCREEN_RING_MASK
    rock_screen_dropped = rock_screen_dropped + 1
  EndIf
  rock_screen_ring[rock_screen_head] = code
  rock_screen_ring_style[rock_screen_head] = style
  rock_screen_head = nextHead
EndProcedure

Procedure RockScreenMirrorByte(code.i)
  RockScreenMirrorByteStyle(code, rock_screen_style)
EndProcedure

Procedure.i RockScreenDroppedBytes()
  ProcedureReturn rock_screen_dropped
EndProcedure

; Validate only the surface contract HDMI/VOP already published. This adapter
; never touches a display register and never reruns mode setup.
Procedure.i RockScreenAttach()
  If rock_screen_attached <> 0 : ProcedureReturn 1 : EndIf
  If rock_display_ready = 0 Or rock_display_buffer = 0
    ProcedureReturn 0
  EndIf
  If rock_display_width < 320 Or rock_display_height <= #ROCK_SCREEN_BANNER_H + #ROCK_SCREEN_CELL_H
    rock_screen_fault = 1
    ProcedureReturn 0
  EndIf
  If rock_display_pitch < rock_display_width * 4
    rock_screen_fault = 2
    ProcedureReturn 0
  EndIf
  If rock_display_pitch * #ROCK_SCREEN_CELL_H > #ROCK_SCREEN_ROW_BUFFER_BYTES
    rock_screen_fault = 7
    ProcedureReturn 0
  EndIf
  rock_screen_cols = rock_display_width / #ROCK_SCREEN_CELL_W
  rock_screen_rows = (rock_display_height - #ROCK_SCREEN_BANNER_H) / #ROCK_SCREEN_CELL_H
  If rock_screen_cols < 1 Or rock_screen_rows < 1
    rock_screen_fault = 3
    ProcedureReturn 0
  EndIf
  rock_screen_col = 0
  rock_screen_row = 0
  rock_screen_banner_phase = 0
  rock_screen_banner_row = 0
  rock_screen_banner_pos = 0
  rock_screen_scroll_active = 0
  rock_screen_scroll_offset = 0
  rock_screen_scroll_bytes = 0
  rock_screen_row_buffer_active = 0
  rock_screen_row_buffer_dirty = 0
  rock_screen_text_render = 0
  rock_screen_attached = 1
  rock_screen_ready = 0
  ProcedureReturn 1
EndProcedure

; Standard banner composition. The initial clear prefers one DMA request over
; the whole tightly packed framebuffer. If controller admission or that
; transfer fails, the bounded CPU fill feeds the watchdog every 256 KiB. HDMI
; calls RockScreenComposeStandardFrame before primary-plane enable, so neither
; path exposes a partially cleared framebuffer. The remaining bounded phases
; also complete before primary-plane enable during bring-up.
Procedure RockScreenBannerService(start.i)
  Protected count.i
  Protected total.i
  Protected x.i
  Protected y.i
  Protected xx.i
  Protected yy.i
  Protected px.i
  Protected rr.i
  Protected gg.i
  Protected bb.i
  Protected text.i
  If rock_screen_ready <> 0 Or rock_screen_fault <> 0
    ProcedureReturn
  EndIf
  Select rock_screen_banner_phase
    Case 0
      If rock_display_pitch <> rock_display_width * 4
        rock_screen_fault = 4
        ProcedureReturn
      EndIf
      total = rock_display_pitch * rock_display_height
      If total <= 0
        rock_screen_fault = 5
        ProcedureReturn
      EndIf
      If rock_dma_pl330_ready <> 0 And total >= #ROCK_SCREEN_DMA_MIN_BYTES
        If RockDmaFill32(rock_display_buffer, #ROCK_SCREEN_BG, total) = 0
          RockScreenCpuFill32(rock_display_buffer, #ROCK_SCREEN_BG, total)
        EndIf
      Else
        RockScreenCpuFill32(rock_display_buffer, #ROCK_SCREEN_BG, total)
      EndIf
      RockWatchdogPet()
      rock_screen_banner_phase = 1
      rock_screen_banner_pos = 0
    Case 1
      text = "PureMetal Forge"
      If rock_screen_banner_pos < 10
        RockScreenGlyph(PeekA(text + rock_screen_banner_pos) & 255, 24 + rock_screen_banner_pos * 15, 18, 3, #ROCK_SCREEN_STEEL)
      ElseIf rock_screen_banner_pos < 15
        RockScreenGlyph(PeekA(text + rock_screen_banner_pos) & 255, 24 + rock_screen_banner_pos * 15, 18, 3, #ROCK_SCREEN_ORANGE)
      EndIf
      rock_screen_banner_pos = rock_screen_banner_pos + 1
      If rock_screen_banner_pos >= 15
        rock_screen_banner_phase = 2
        rock_screen_banner_pos = 0
      EndIf
    Case 2
      text = "Anvil Monitor  |  Rock Pi 4C  |  RK3399  |  AArch64 at EL3"
      rock_screen_banner_pos = RockScreenTextRange(text, 24, 56, 2, #ROCK_SCREEN_FAINT, rock_screen_banner_pos, 8)
      If PeekA(text + rock_screen_banner_pos) = 0
        rock_screen_banner_phase = 3
        rock_screen_banner_pos = 0
      EndIf
    Case 3
      text = AnvilBuildLabel(#ANVIL_BUILD, #ANVIL_BUILD_DATE, #ANVIL_BUILD_TIME)
      rock_screen_banner_pos = RockScreenTextRange(text, 24, 78, 2, #ROCK_SCREEN_STEEL, rock_screen_banner_pos, 8)
      If PeekA(text + rock_screen_banner_pos) = 0
        rock_screen_banner_phase = 4
        rock_screen_banner_pos = 0
      EndIf
    Case 4
      RockScreenText("CPU0 --.--%", 24, 96, 2, #ROCK_SCREEN_FAINT)
      rock_screen_banner_phase = 5
      rock_screen_banner_row = 0
    Case 5
      If rock_display_width < 500
        rock_screen_banner_phase = 6
      Else
        x = rock_display_width - 96
        y = 12
        count = 6
        If rock_screen_banner_row + count > #ANVIL_PIC_H
          count = #ANVIL_PIC_H - rock_screen_banner_row
        EndIf
        For yy = 0 To count - 1
          For xx = 0 To #ANVIL_PIC_W - 1
            px = ?anvilPix + ((rock_screen_banner_row + yy) * #ANVIL_PIC_W + xx) * 3
            rr = PeekA(px) & 255
            gg = PeekA(px + 1) & 255
            bb = PeekA(px + 2) & 255
            RockScreenPixel(x + xx, y + rock_screen_banner_row + yy, $FF000000 | (rr << 16) | (gg << 8) | bb)
          Next
        Next
        rock_screen_banner_row = rock_screen_banner_row + count
        If count > 0 : RockWatchdogPet() : EndIf
        If rock_screen_banner_row >= #ANVIL_PIC_H
          rock_screen_banner_phase = 6
        EndIf
      EndIf
    Case 6
      If rock_display_width >= 500
        x = rock_display_width - 96 + ((#ANVIL_PIC_W - 45) / 2)
        RockScreenText("A N V I L", x, 92, 1, #ROCK_SCREEN_LOGO_NAME)
      EndIf
      rock_screen_banner_phase = 7
    Case 7
      ; Pi 4's standard bright/dim two-line separator.
      RockScreenFillRect(24, #ROCK_SCREEN_BANNER_H - 6, rock_display_width - 48, 1, #ROCK_SCREEN_ORANGE)
      RockScreenFillRect(24, #ROCK_SCREEN_BANNER_H - 5, rock_display_width - 48, 1, $FF3C2814)
      rock_screen_banner_phase = 8
    Case 8
      ASM
        dsb sy
      ENDASM
      rock_screen_ready = 1
  EndSelect
EndProcedure

; Bring-up entry for a surface published before the VOP primary plane is
; enabled. Every pass advances a finite banner phase; 256 is far above the
; current 45-pass composition and is an instruction ceiling, not a poll.
; Calling this before RockVopStartPrimary prevents title/logo construction
; from ever appearing piecewise on the monitor.
Procedure.i RockScreenComposeStandardFrame()
  Protected pass.i
  If RockScreenAttach() = 0
    ProcedureReturn 0
  EndIf
  For pass = 0 To 255
    If rock_screen_ready <> 0
      ProcedureReturn 1
    EndIf
    If rock_screen_fault <> 0
      ProcedureReturn 0
    EndIf
    RockScreenBannerService(RockTimerTicks())
  Next
  rock_screen_fault = 6
  ProcedureReturn 0
EndProcedure

; The only consumer of the UART mirror. Banner work and terminal work share
; the same 1500 us deadline, and terminal work has the independent 32-byte
; ceiling even on a stopped or unavailable architectural counter.
Procedure RockScreenService()
  Protected start.i
  Protected count.i
  Protected code.i
  Protected style.i
  If rock_screen_fault <> 0
    ProcedureReturn
  EndIf
  If RockScreenAttach() = 0
    ProcedureReturn
  EndIf
  start = RockTimerTicks()
  If rock_screen_ready = 0
    RockScreenBannerService(start)
    ProcedureReturn
  EndIf
  If rock_screen_scroll_active <> 0
    RockScreenScrollService()
    ProcedureReturn
  EndIf
  count = 0
  While rock_screen_tail <> rock_screen_head And count < #ROCK_SCREEN_SERVICE_BYTES
    code = rock_screen_ring[rock_screen_tail] & 255
    style = rock_screen_ring_style[rock_screen_tail] & 255
    rock_screen_tail = (rock_screen_tail + 1) & #ROCK_SCREEN_RING_MASK
    RockScreenPaintByte(code, style)
    count = count + 1
    If rock_screen_scroll_active <> 0 : Break : EndIf
    If RockScreenTimeExpired(start) <> 0 : Break : EndIf
  Wend
  If count > 0
    rock_screen_row_last_ticks = RockTimerTicks()
    ASM
      dsb sy
    ENDASM
    RockWatchdogPet()
  ElseIf rock_screen_row_buffer_dirty <> 0 And rock_screen_tail = rock_screen_head
    If RockTimerTicks() - rock_screen_row_last_ticks >= (rock_timer_frequency / 1000000) * #ROCK_SCREEN_ROW_IDLE_US
      RockScreenBufferPublish()
    EndIf
  EndIf
EndProcedure

Procedure.i RockScreenReady()
  ProcedureReturn rock_screen_ready
EndProcedure

; ======================================================================
;  Portable payload pixel surface. The monitor and payload use the same
;  published scanout, but the monitor's 120-pixel reservation is not imposed
;  on a payload: the HwCon contract hands the whole surface to the payload.
; ======================================================================
Procedure.i HwConWidth()
  ProcedureReturn rock_display_width
EndProcedure

Procedure.i HwConHeight()
  ProcedureReturn rock_display_height
EndProcedure

Procedure.i HwConTier()
  If rock_dma_pl330_ready <> 0
    ProcedureReturn #HW_TIER_DMA
  EndIf
  ProcedureReturn #HW_TIER_CPU
EndProcedure

Procedure.i HwConTextHeight()
  ProcedureReturn #ROCK_SCREEN_CELL_H
EndProcedure

Procedure.i HwConFrameBegin()
  If rock_display_ready = 0 Or rock_display_buffer = 0 Or rock_screen_frame <> 0
    ProcedureReturn 0
  EndIf
  rock_screen_frame = 1
  ProcedureReturn 1
EndProcedure

Procedure.i HwConFrameEnd()
  If rock_screen_frame = 0 Or rock_display_ready = 0
    ProcedureReturn 0
  EndIf
  rock_screen_frame = 0
  ; EL3 currently runs with the data cache off. This barrier publishes every
  ; completed CPU/DMA write before returning ownership to the direct scanner.
  ; A future cache-enable change must add a clean here, at this one seam.
  ASM
    dsb sy
  ENDASM
  ProcedureReturn 1
EndProcedure

Procedure HwConRect(x.i, y.i, w.i, h.i, argb.i)
  Protected a.i
  Protected sr.i
  Protected sg.i
  Protected sb.i
  Protected row.i
  Protected col.i
  Protected p.i
  Protected d.i
  Protected dr.i
  Protected dg.i
  Protected db.i
  If rock_display_ready = 0 Or w <= 0 Or h <= 0
    ProcedureReturn
  EndIf
  If x < 0 : w = w + x : x = 0 : EndIf
  If y < 0 : h = h + y : y = 0 : EndIf
  If x + w > rock_display_width : w = rock_display_width - x : EndIf
  If y + h > rock_display_height : h = rock_display_height - y : EndIf
  If w <= 0 Or h <= 0
    ProcedureReturn
  EndIf
  a = (argb >> 24) & 255
  If a = 0
    ProcedureReturn
  EndIf
  If a = 255
    RockScreenFillRect(x, y, w, h, argb)
    ProcedureReturn
  EndIf
  sr = (argb >> 16) & 255
  sg = (argb >> 8) & 255
  sb = argb & 255
  For row = 0 To h - 1
    p = rock_display_buffer + (y + row) * rock_display_pitch + x * 4
    For col = 0 To w - 1
      d = PeekL(p)
      dr = (d >> 16) & 255
      dg = (d >> 8) & 255
      db = d & 255
      dr = (a * sr + (255 - a) * dr + 127) / 255
      dg = (a * sg + (255 - a) * dg + 127) / 255
      db = (a * sb + (255 - a) * db + 127) / 255
      PokeL(p, $FF000000 | (dr << 16) | (dg << 8) | db)
      p = p + 4
    Next
  Next
EndProcedure

Procedure.i HwConText(x.i, y.i, *utf8, argb.i, bg.i)
  Protected n.i
  Protected code.i
  Protected tx.i
  Protected ty.i
  Protected maxWidth.i
  Protected step.i
  Protected seen.i
  If *utf8 = 0 Or rock_display_ready = 0 : ProcedureReturn 0 : EndIf
  tx = x
  ty = y - #ROCK_SCREEN_CELL_H
  While n < 4096
    code = PeekA(*utf8 + n) & 255
    If code = 0 : Break : EndIf
    step = 1
    If code >= 128
      code = 63
      If (PeekA(*utf8 + n) & 255) >= $C2 And (PeekA(*utf8 + n) & 255) <= $DF
        step = 2
      ElseIf (PeekA(*utf8 + n) & 255) >= $E0 And (PeekA(*utf8 + n) & 255) <= $EF
        step = 3
      ElseIf (PeekA(*utf8 + n) & 255) >= $F0 And (PeekA(*utf8 + n) & 255) <= $F4
        step = 4
      EndIf
      seen = 1
      While seen < step And ((PeekA(*utf8 + n + seen) & $C0) = $80)
        seen = seen + 1
      Wend
      If seen < step : step = 1 : EndIf
    EndIf
    Select code
      Case 13
        tx = x
      Case 10
        If tx - x > maxWidth : maxWidth = tx - x : EndIf
        tx = x
        ty = ty + #ROCK_SCREEN_CELL_H
      Case 9
        Repeat
          HwConRect(tx, ty, #ROCK_SCREEN_CELL_W, #ROCK_SCREEN_CELL_H, $FF000000 | (bg & $00FFFFFF))
          tx = tx + #ROCK_SCREEN_CELL_W
        Until (((tx - x) / #ROCK_SCREEN_CELL_W) & 3) = 0
      Default
        If code < 32 : code = 63 : EndIf
        HwConRect(tx, ty, #ROCK_SCREEN_CELL_W, #ROCK_SCREEN_CELL_H, $FF000000 | (bg & $00FFFFFF))
        RockScreenGlyph(code, tx, ty, 2, $FF000000 | (argb & $00FFFFFF))
        tx = tx + #ROCK_SCREEN_CELL_W
    EndSelect
    n = n + step
  Wend
  If tx - x > maxWidth : maxWidth = tx - x : EndIf
  ProcedureReturn maxWidth
EndProcedure

Procedure.i HwConTextWidth(*utf8)
  Protected n.i
  Protected code.i
  Protected count.i
  Protected longest.i
  Protected step.i
  Protected seen.i
  If *utf8 = 0 : ProcedureReturn 0 : EndIf
  While n < 4096
    code = PeekA(*utf8 + n) & 255
    If code = 0 : Break : EndIf
    If code = 10
      If count > longest : longest = count : EndIf
      count = 0
      n = n + 1
    ElseIf code = 13
      n = n + 1
    Else
      step = 1
      If code >= $C2 And code <= $DF
        step = 2
      ElseIf code >= $E0 And code <= $EF
        step = 3
      ElseIf code >= $F0 And code <= $F4
        step = 4
      EndIf
      seen = 1
      While seen < step And ((PeekA(*utf8 + n + seen) & $C0) = $80)
        seen = seen + 1
      Wend
      If seen < step : step = 1 : EndIf
      count = count + 1
      n = n + step
    EndIf
  Wend
  If count > longest : longest = count : EndIf
  ProcedureReturn longest * #ROCK_SCREEN_CELL_W
EndProcedure

Procedure.i HwConCapture()
  ; No RK capture area exists yet. Refuse rather than claiming a copy that
  ; aliases the live scan buffer and is overwritten by the next prompt.
  ProcedureReturn 0
EndProcedure

Procedure.i HwConBacklight(pct.i)
  ; HDMI monitor brightness belongs to the monitor (DDC/CI), not this VOP.
  ProcedureReturn -1
EndProcedure
