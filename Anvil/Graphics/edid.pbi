; Platform-neutral EDID reader. The caller supplies a packed sequence of
; complete 128-byte blocks returned by its platform transport. This file
; has no mailbox, MMIO, or board-specific dependencies.

#ANVIL_EDID_BLOCK_BYTES = 128
#ANVIL_EDID_MAX_BLOCKS = 8
#ANVIL_EDID_MAX_MODES = 64

#ANVIL_EDID_E_NONE = 0
#ANVIL_EDID_E_ARGUMENT = 1
#ANVIL_EDID_E_HEADER = 2
#ANVIL_EDID_E_BASE_CHECKSUM = 3
#ANVIL_EDID_E_BLOCK_BOUNDS = 4
#ANVIL_EDID_E_EXTENSION_CHECKSUM = 5
#ANVIL_EDID_E_CTA_BOUNDS = 6

Global *anvil_edid_data.i
Global anvil_edid_bytes.i
Global anvil_edid_blocks.i
Global anvil_edid_extension_count.i
Global anvil_edid_truncated.i
Global anvil_edid_valid.i
Global anvil_edid_preferred.i
Global anvil_edid_preferred_timing_valid.i
Global anvil_edid_preferred_timing_clock.i
Global anvil_edid_preferred_hsync_start.i
Global anvil_edid_preferred_hsync_end.i
Global anvil_edid_preferred_htotal.i
Global anvil_edid_preferred_vsync_start.i
Global anvil_edid_preferred_vsync_end.i
Global anvil_edid_preferred_vtotal.i
Global anvil_edid_preferred_flags.i
Global anvil_edid_error.i
Global anvil_edid_error_offset.i
Global anvil_edid_modes.i
Global Dim anvil_edid_mode_w.i[#ANVIL_EDID_MAX_MODES]
Global Dim anvil_edid_mode_h.i[#ANVIL_EDID_MAX_MODES]
Global Dim anvil_edid_mode_clock.i[#ANVIL_EDID_MAX_MODES]
Global Dim anvil_edid_mode_refresh.i[#ANVIL_EDID_MAX_MODES]

Procedure.i anvil_edid_U8(offset.i)
  ProcedureReturn PeekA(*anvil_edid_data + offset) & $FF
EndProcedure

Procedure.i anvil_edid_U16Le(offset.i)
  ProcedureReturn anvil_edid_U8(offset) | (anvil_edid_U8(offset + 1) << 8)
EndProcedure

Procedure anvil_edid_Fail(code.i, offset.i)
  If anvil_edid_error = #ANVIL_EDID_E_NONE
    anvil_edid_error = code
    anvil_edid_error_offset = offset
  EndIf
EndProcedure

Procedure.i AnvilEdidReset()
  Protected n.i
  *anvil_edid_data = 0
  anvil_edid_bytes = 0
  anvil_edid_blocks = 0
  anvil_edid_extension_count = 0
  anvil_edid_truncated = 0
  anvil_edid_valid = 0
  anvil_edid_preferred = -1
  anvil_edid_preferred_timing_valid = 0
  anvil_edid_preferred_timing_clock = 0
  anvil_edid_preferred_hsync_start = 0
  anvil_edid_preferred_hsync_end = 0
  anvil_edid_preferred_htotal = 0
  anvil_edid_preferred_vsync_start = 0
  anvil_edid_preferred_vsync_end = 0
  anvil_edid_preferred_vtotal = 0
  anvil_edid_preferred_flags = 0
  anvil_edid_error = #ANVIL_EDID_E_NONE
  anvil_edid_error_offset = 0
  anvil_edid_modes = 0
  For n = 0 To #ANVIL_EDID_MAX_MODES - 1
    anvil_edid_mode_w[n] = 0
    anvil_edid_mode_h[n] = 0
    anvil_edid_mode_clock[n] = 0
    anvil_edid_mode_refresh[n] = 0
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_edid_AddMode(width.i, height.i, clock.i, refresh.i)
  Protected n.i
  If width < 1 Or width > 8192 Or height < 1 Or height > 8192
    ProcedureReturn -1
  EndIf
  For n = 0 To anvil_edid_modes - 1
    If anvil_edid_mode_w[n] = width And anvil_edid_mode_h[n] = height And anvil_edid_mode_refresh[n] = refresh
      If clock > anvil_edid_mode_clock[n] : anvil_edid_mode_clock[n] = clock : EndIf
      ProcedureReturn n
    EndIf
  Next
  If anvil_edid_modes >= #ANVIL_EDID_MAX_MODES
    anvil_edid_truncated = 1
    ProcedureReturn -1
  EndIf
  n = anvil_edid_modes
  anvil_edid_mode_w[n] = width
  anvil_edid_mode_h[n] = height
  anvil_edid_mode_clock[n] = clock
  anvil_edid_mode_refresh[n] = refresh
  anvil_edid_modes = anvil_edid_modes + 1
  ProcedureReturn n
EndProcedure

Procedure.i anvil_edid_Checksum(blockOffset.i)
  Protected n.i
  Protected sum.i = 0
  For n = 0 To #ANVIL_EDID_BLOCK_BYTES - 1
    sum = (sum + anvil_edid_U8(blockOffset + n)) & 255
  Next
  ProcedureReturn Bool(sum = 0)
EndProcedure

Procedure.i anvil_edid_ParseDtd(offset.i, preferred.i)
  Protected clock10k.i
  Protected width.i
  Protected hblank.i
  Protected height.i
  Protected vblank.i
  Protected totalH.i
  Protected totalV.i
  Protected pixelClock.i
  Protected refresh.i
  Protected mode.i
  Protected hsyncOffset.i
  Protected hsyncWidth.i
  Protected vsyncOffset.i
  Protected vsyncWidth.i
  clock10k = anvil_edid_U16Le(offset)
  If clock10k = 0 : ProcedureReturn -1 : EndIf
  width = anvil_edid_U8(offset + 2) | ((anvil_edid_U8(offset + 4) & $F0) << 4)
  hblank = anvil_edid_U8(offset + 3) | ((anvil_edid_U8(offset + 4) & $0F) << 8)
  height = anvil_edid_U8(offset + 5) | ((anvil_edid_U8(offset + 7) & $F0) << 4)
  vblank = anvil_edid_U8(offset + 6) | ((anvil_edid_U8(offset + 7) & $0F) << 8)
  If width < 1 Or height < 1 Or hblank < 1 Or vblank < 1 : ProcedureReturn -1 : EndIf
  totalH = width + hblank
  totalV = height + vblank
  If totalH < width Or totalV < height : ProcedureReturn -1 : EndIf
  pixelClock = clock10k * 10
  If pixelClock < 1000 Or pixelClock > 1000000 : ProcedureReturn -1 : EndIf
  ; pixelClock is kHz. Convert to milli-Hz to match CTA/standard modes and
  ; the public RefreshMilliHz API: kHz * 1,000,000 / pixels-per-frame.
  refresh = (pixelClock * 1000000) / (totalH * totalV)
  If (anvil_edid_U8(offset + 17) & $80) <> 0
    ; Interlaced timings are represented with an approximate frame rate and
    ; the interlace flag is not discarded into an apparently progressive
    ; exact timing: leave their refresh unknown (zero) for mode selection.
    refresh = 0
  EndIf
  mode = anvil_edid_AddMode(width, height, pixelClock, refresh)
  If preferred <> 0 And mode >= 0 And anvil_edid_preferred < 0
    anvil_edid_preferred = mode
    ; EDID detailed timing descriptor bytes 8..11 pack the sync offsets and
    ; widths; byte 17 carries interlace and sync/polarity flags. Preserve the
    ; complete programmable timing separately from summary/SVD modes.
    hsyncOffset=anvil_edid_U8(offset+8) | (((anvil_edid_U8(offset+11)>>6)&3)<<8)
    hsyncWidth=anvil_edid_U8(offset+9) | (((anvil_edid_U8(offset+11)>>4)&3)<<8)
    vsyncOffset=((anvil_edid_U8(offset+10)>>4)&15) | (((anvil_edid_U8(offset+11)>>2)&3)<<4)
    vsyncWidth=(anvil_edid_U8(offset+10)&15) | ((anvil_edid_U8(offset+11)&3)<<4)
    If hsyncOffset>0 And hsyncWidth>0 And vsyncOffset>0 And vsyncWidth>0 And hsyncOffset+hsyncWidth<=hblank And vsyncOffset+vsyncWidth<=vblank
      anvil_edid_preferred_hsync_start=width+hsyncOffset
      anvil_edid_preferred_hsync_end=width+hsyncOffset+hsyncWidth
      anvil_edid_preferred_htotal=totalH
      anvil_edid_preferred_vsync_start=height+vsyncOffset
      anvil_edid_preferred_vsync_end=height+vsyncOffset+vsyncWidth
      anvil_edid_preferred_vtotal=totalV
      anvil_edid_preferred_flags=anvil_edid_U8(offset+17)
      anvil_edid_preferred_timing_clock=pixelClock
      anvil_edid_preferred_timing_valid=1
    EndIf
  EndIf
  ProcedureReturn mode
EndProcedure

Procedure.i anvil_edid_CtaVic(vic.i, *w, *h, *refresh)
  Protected width.i = 0
  Protected height.i = 0
  Protected refreshValue.i = 0
  Select vic
    Case 1 : width=640 : height=480 : refreshValue=60000
    Case 2 : width=720 : height=480 : refreshValue=60000
    Case 3 : width=720 : height=480 : refreshValue=60000
    Case 4 : width=1280 : height=720 : refreshValue=60000
    Case 16 : width=1920 : height=1080 : refreshValue=60000
    Case 17 : width=720 : height=576 : refreshValue=50000
    Case 18 : width=720 : height=576 : refreshValue=50000
    Case 19 : width=1280 : height=720 : refreshValue=50000
    Case 31 : width=1920 : height=1080 : refreshValue=50000
    Case 32 : width=1920 : height=1080 : refreshValue=24000
    Case 33 : width=1920 : height=1080 : refreshValue=25000
    Case 34 : width=1920 : height=1080 : refreshValue=30000
    Case 93 : width=3840 : height=2160 : refreshValue=24000
    Case 94 : width=3840 : height=2160 : refreshValue=25000
    Case 95 : width=3840 : height=2160 : refreshValue=30000
    Case 96 : width=3840 : height=2160 : refreshValue=50000
    Case 97 : width=3840 : height=2160 : refreshValue=60000
    Case 98 : width=4096 : height=2160 : refreshValue=24000
    Case 99 : width=4096 : height=2160 : refreshValue=25000
    Case 100 : width=4096 : height=2160 : refreshValue=30000
    Case 101 : width=4096 : height=2160 : refreshValue=50000
    Case 102 : width=4096 : height=2160 : refreshValue=60000
    Default : ProcedureReturn 0
  EndSelect
  PokeI(*w,width) : PokeI(*h,height) : PokeI(*refresh,refreshValue)
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_edid_ParseCta(block.i)
  Protected base.i
  Protected rev.i
  Protected dtdStart.i
  Protected pos.i
  Protected endPos.i
  Protected header.i
  Protected tag.i
  Protected length.i
  Protected j.i
  Protected vic.i
  Protected width.i
  Protected height.i
  Protected refresh.i
  Protected clock.i
  base = block * #ANVIL_EDID_BLOCK_BYTES
  rev = anvil_edid_U8(base + 1)
  If rev < 1 Or rev > 4
    anvil_edid_Fail(#ANVIL_EDID_E_CTA_BOUNDS, base + 1)
    ProcedureReturn 0
  EndIf
  dtdStart = anvil_edid_U8(base + 2)
  If dtdStart = 0
    ProcedureReturn 1
  EndIf
  If dtdStart < 4 Or dtdStart > 127
    anvil_edid_Fail(#ANVIL_EDID_E_CTA_BOUNDS, base + 2)
    ProcedureReturn 0
  EndIf
  pos = base + 4
  endPos = base + dtdStart
  While pos < endPos
    header = anvil_edid_U8(pos)
    If header = 0
      pos = pos + 1
    Else
      tag = (header >> 5) & 7
      length = header & 31
      If length > endPos - pos - 1
        anvil_edid_Fail(#ANVIL_EDID_E_CTA_BOUNDS, pos)
        ProcedureReturn 0
      EndIf
      If tag = 2
        For j = 1 To length
          vic = anvil_edid_U8(pos + j) & $7F
          If anvil_edid_CtaVic(vic,@width,@height,@refresh) <> 0
            anvil_edid_AddMode(width,height,0,refresh)
          EndIf
        Next
      EndIf
      pos = pos + 1 + length
    EndIf
  Wend
  If pos <> endPos
    anvil_edid_Fail(#ANVIL_EDID_E_CTA_BOUNDS, pos)
    ProcedureReturn 0
  EndIf
  pos = base + dtdStart
  While pos + 18 <= base + 127
    If anvil_edid_ParseDtd(pos,0) = -2
      anvil_edid_Fail(#ANVIL_EDID_E_CTA_BOUNDS, pos)
      ProcedureReturn 0
    EndIf
    pos = pos + 18
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_edid_ParseEstablished()
  Protected b.i
  Protected mask.i
  ; EDID 1.3 established timings. Interlaced 1024x768 is represented with
  ; refresh zero so the caller can report it without choosing it by accident.
  b = anvil_edid_U8(35)
  If b & $80 : anvil_edid_AddMode(720,400,0,70000) : EndIf
  If b & $40 : anvil_edid_AddMode(720,400,0,88000) : EndIf
  If b & $20 : anvil_edid_AddMode(640,480,0,60000) : EndIf
  If b & $10 : anvil_edid_AddMode(640,480,0,67000) : EndIf
  If b & $08 : anvil_edid_AddMode(640,480,0,72000) : EndIf
  If b & $04 : anvil_edid_AddMode(640,480,0,75000) : EndIf
  If b & $02 : anvil_edid_AddMode(800,600,0,56000) : EndIf
  If b & $01 : anvil_edid_AddMode(800,600,0,60000) : EndIf
  b = anvil_edid_U8(36)
  If b & $80 : anvil_edid_AddMode(800,600,0,72000) : EndIf
  If b & $40 : anvil_edid_AddMode(800,600,0,75000) : EndIf
  If b & $20 : anvil_edid_AddMode(832,624,0,75000) : EndIf
  If b & $10 : anvil_edid_AddMode(1024,768,0,0) : EndIf
  If b & $08 : anvil_edid_AddMode(1024,768,0,60000) : EndIf
  If b & $04 : anvil_edid_AddMode(1024,768,0,70000) : EndIf
  If b & $02 : anvil_edid_AddMode(1024,768,0,75000) : EndIf
  If b & $01 : anvil_edid_AddMode(1280,1024,0,75000) : EndIf
  b = anvil_edid_U8(37)
  If b & $80 : anvil_edid_AddMode(1152,870,0,75000) : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_edid_ParseStandard()
  Protected n.i
  Protected h.i
  Protected aspect.i
  Protected w.i
  Protected height.i
  Protected refresh.i
  For n = 0 To 7
    h = anvil_edid_U8(38 + n * 2)
    aspect = anvil_edid_U8(39 + n * 2) >> 6
    If h = 1 And anvil_edid_U8(39 + n * 2) = 1 : Continue : EndIf
    w = (h + 31) * 8
    Select aspect
      Case 0
        If anvil_edid_U8(19) > 3 : height = (w * 10) / 16 : Else : height = w : EndIf
      Case 1 : height = (w * 3) / 4
      Case 2 : height = (w * 4) / 5
      Case 3 : height = (w * 9) / 16
    EndSelect
    refresh = (anvil_edid_U8(39 + n * 2) & 63) + 60
    anvil_edid_AddMode(w,height,0,refresh * 1000)
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilEdidParse(blocksPtr.i, byteCount.i, receivedBlocks.i, truncated.i)
  Protected n.i
  Protected sum.i
  Protected offset.i
  Protected extExpected.i
  Protected extRead.i
  Protected mode.i
  Protected w.i
  Protected h.i
  Protected r.i
  AnvilEdidReset()
  If blocksPtr < 1 Or receivedBlocks < 1 Or receivedBlocks > #ANVIL_EDID_MAX_BLOCKS Or byteCount <> receivedBlocks * #ANVIL_EDID_BLOCK_BYTES
    anvil_edid_Fail(#ANVIL_EDID_E_ARGUMENT,0)
    ProcedureReturn 0
  EndIf
  *anvil_edid_data = blocksPtr
  anvil_edid_bytes = byteCount
  anvil_edid_blocks = receivedBlocks
  If truncated <> 0 : anvil_edid_truncated = 1 : EndIf
  If anvil_edid_U8(0)<>0 Or anvil_edid_U8(1)<>255 Or anvil_edid_U8(2)<>255 Or anvil_edid_U8(3)<>255 Or anvil_edid_U8(4)<>255 Or anvil_edid_U8(5)<>255 Or anvil_edid_U8(6)<>255 Or anvil_edid_U8(7)<>0
    anvil_edid_Fail(#ANVIL_EDID_E_HEADER,0)
    ProcedureReturn 0
  EndIf
  If anvil_edid_U8(18)<>1 Or anvil_edid_U8(19)>4
    anvil_edid_Fail(#ANVIL_EDID_E_HEADER,18)
    ProcedureReturn 0
  EndIf
  If anvil_edid_Checksum(0)=0
    anvil_edid_Fail(#ANVIL_EDID_E_BASE_CHECKSUM,127)
    ProcedureReturn 0
  EndIf
  anvil_edid_valid = 1
  anvil_edid_extension_count = anvil_edid_U8(126)
  extExpected = anvil_edid_extension_count + 1
  If receivedBlocks < extExpected : anvil_edid_truncated = 1 : EndIf
  anvil_edid_ParseEstablished()
  anvil_edid_ParseStandard()
  ; The first base-block detailed timing is the EDID preferred timing. Other
  ; descriptors remain supported-mode entries, but do not replace it.
  For n = 0 To 3
    offset = 54 + n * 18
    mode = anvil_edid_ParseDtd(offset,Bool(n=0))
  Next
  extRead = receivedBlocks - 1
  If extRead > anvil_edid_extension_count : extRead = anvil_edid_extension_count : EndIf
  For n = 1 To extRead
    offset = n * #ANVIL_EDID_BLOCK_BYTES
    If anvil_edid_Checksum(offset)=0
      anvil_edid_Fail(#ANVIL_EDID_E_EXTENSION_CHECKSUM,offset+127)
      anvil_edid_truncated=1
      Continue
    EndIf
    If anvil_edid_U8(offset)=2
      If anvil_edid_ParseCta(n)=0 : anvil_edid_truncated=1 : EndIf
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilEdidValid() : ProcedureReturn anvil_edid_valid : EndProcedure
Procedure.i AnvilEdidBlockCount() : ProcedureReturn anvil_edid_blocks : EndProcedure
Procedure.i AnvilEdidExtensionCount() : ProcedureReturn anvil_edid_extension_count : EndProcedure
Procedure.i AnvilEdidTruncated() : ProcedureReturn anvil_edid_truncated : EndProcedure
Procedure.i AnvilEdidModeCount() : ProcedureReturn anvil_edid_modes : EndProcedure
Procedure.i AnvilEdidPreferredWidth() : If anvil_edid_preferred<0 : ProcedureReturn 0 : EndIf : ProcedureReturn anvil_edid_mode_w[anvil_edid_preferred] : EndProcedure
Procedure.i AnvilEdidPreferredHeight() : If anvil_edid_preferred<0 : ProcedureReturn 0 : EndIf : ProcedureReturn anvil_edid_mode_h[anvil_edid_preferred] : EndProcedure
Procedure.i AnvilEdidPreferredPixelClockKHz() : If anvil_edid_preferred<0 : ProcedureReturn 0 : EndIf : ProcedureReturn anvil_edid_mode_clock[anvil_edid_preferred] : EndProcedure
Procedure.i AnvilEdidPreferredRefreshMilliHz() : If anvil_edid_preferred<0 : ProcedureReturn 0 : EndIf : ProcedureReturn anvil_edid_mode_refresh[anvil_edid_preferred] : EndProcedure
Procedure.i AnvilEdidPreferredTimingValid() : ProcedureReturn anvil_edid_preferred_timing_valid : EndProcedure
Procedure.i AnvilEdidPreferredTimingPixelClockKHz() : ProcedureReturn anvil_edid_preferred_timing_clock : EndProcedure
Procedure.i AnvilEdidPreferredHSyncStart() : ProcedureReturn anvil_edid_preferred_hsync_start : EndProcedure
Procedure.i AnvilEdidPreferredHSyncEnd() : ProcedureReturn anvil_edid_preferred_hsync_end : EndProcedure
Procedure.i AnvilEdidPreferredHTotal() : ProcedureReturn anvil_edid_preferred_htotal : EndProcedure
Procedure.i AnvilEdidPreferredVSyncStart() : ProcedureReturn anvil_edid_preferred_vsync_start : EndProcedure
Procedure.i AnvilEdidPreferredVSyncEnd() : ProcedureReturn anvil_edid_preferred_vsync_end : EndProcedure
Procedure.i AnvilEdidPreferredVTotal() : ProcedureReturn anvil_edid_preferred_vtotal : EndProcedure
Procedure.i AnvilEdidPreferredInterlaced() : ProcedureReturn Bool(anvil_edid_preferred_flags&$80) : EndProcedure
Procedure.i AnvilEdidPreferredSeparateSync() : ProcedureReturn Bool((anvil_edid_preferred_flags&$18)=$18) : EndProcedure
Procedure.i AnvilEdidPreferredVSyncPositive() : If (anvil_edid_preferred_flags&$18)<>$18 : ProcedureReturn 0 : EndIf : ProcedureReturn Bool(anvil_edid_preferred_flags&$04) : EndProcedure
Procedure.i AnvilEdidPreferredHSyncPositive() : If (anvil_edid_preferred_flags&$18)<>$18 : ProcedureReturn 0 : EndIf : ProcedureReturn Bool(anvil_edid_preferred_flags&$02) : EndProcedure
Procedure.i AnvilEdidError() : ProcedureReturn anvil_edid_error : EndProcedure
Procedure.i AnvilEdidErrorOffset() : ProcedureReturn anvil_edid_error_offset : EndProcedure
Procedure.i AnvilEdidModeAt(index.i,*width,*height,*refreshMilliHz,*clockKHz)
  If index<0 Or index>=anvil_edid_modes : ProcedureReturn 0 : EndIf
  PokeI(*width,anvil_edid_mode_w[index])
  PokeI(*height,anvil_edid_mode_h[index])
  PokeI(*refreshMilliHz,anvil_edid_mode_refresh[index])
  PokeI(*clockKHz,anvil_edid_mode_clock[index])
  ProcedureReturn 1
EndProcedure
