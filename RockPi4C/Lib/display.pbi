; Original ROCK Pi 4C v1.2 MiniDP first-light facade.
; This owns the complete ordered dependency chain and publishes no display
; capability until a trained link is carrying the deterministic framebuffer.

Global rock_display_ready.i
Global rock_display_width.i
Global rock_display_height.i
Global rock_display_pitch.i
Global rock_display_buffer.i
Global rock_display_error.i

Procedure RockDisplayStage(text.i)
  If rock_uart_ready <> 0 : RockUartLine(text) : EndIf
EndProcedure

Procedure.i RockDisplayFail(code.i, text.i)
  rock_display_error=code
  RockDisplayStage(text)
  ProcedureReturn 0
EndProcedure

Procedure RockDisplayDecimal(value.i)
  Protected divisor.i = 1
  While value / divisor >= 10
    divisor = divisor * 10
  Wend
  Repeat
    RockUartByte(48 + value / divisor)
    value = value % divisor
    divisor = divisor / 10
  Until divisor = 0
EndProcedure

Procedure RockDisplayModeTelemetry(text.i)
  If rock_uart_ready = 0 : ProcedureReturn 0 : EndIf
  RockUartText(text)
  RockDisplayDecimal(rock_mode_width)
  RockUartByte(88)
  RockDisplayDecimal(rock_mode_height)
  RockUartText(" PIXEL HZ ")
  RockDisplayDecimal(rock_mode_pixel_hz)
  RockUartText(" SOURCE ")
  RockDisplayDecimal(rock_mode_source)
  RockUartText(" REASON ")
  RockDisplayDecimal(rock_mode_reason)
  If rock_mode_source = #ROCK_MODE_SOURCE_PREFERRED_DTD
    RockUartText(" EDID PREFERRED")
  Else
    RockUartText(" ADVERTISED FALLBACK; PREFERRED ")
    RockDisplayDecimal(rock_mode_preferred_width)
    RockUartByte(88)
    RockDisplayDecimal(rock_mode_preferred_height)
    RockUartText(" AT HZ ")
    RockDisplayDecimal(rock_mode_preferred_pixel_hz)
  EndIf
  RockUartByte(13)
  RockUartByte(10)
EndProcedure

Procedure RockDisplayHexByte(value.i)
  Protected digit.i = (value >> 4) & 15
  If digit < 10
    RockUartByte(48+digit)
  Else
    RockUartByte(55+digit)
  EndIf
  digit = value & 15
  If digit < 10
    RockUartByte(48+digit)
  Else
    RockUartByte(55+digit)
  EndIf
EndProcedure

Procedure RockDisplayHexWord(value.i)
  RockDisplayHexByte((value >> 8) & 255)
  RockDisplayHexByte(value & 255)
EndProcedure

Procedure RockDisplayHexLong(value.i)
  RockDisplayHexWord((value >> 16) & $FFFF)
  RockDisplayHexWord(value & $FFFF)
EndProcedure

Procedure RockDisplayEdidTelemetry()
  Protected block.i
  Protected offset.i
  If rock_uart_ready = 0 : ProcedureReturn 0 : EndIf
  For block=0 To rock_edid_block_count-1
    For offset=0 To 127
      If (offset & 15)=0
        RockUartText("EDID BLOCK ")
        RockDisplayDecimal(block)
        RockUartByte(32)
        RockDisplayHexByte(offset)
        RockUartText(": ")
      EndIf
      RockDisplayHexByte(PeekA(@rock_cdn_edid[0]+block*128+offset) & 255)
      If (offset & 15)=15
        RockUartByte(13) : RockUartByte(10)
      Else
        RockUartByte(32)
      EndIf
    Next
  Next
EndProcedure

Procedure RockDisplayEdidCapabilities()
  Protected block.i
  Protected range.i
  Protected slot.i
  Protected source.i
  If rock_uart_ready = 0 : ProcedureReturn 0 : EndIf
  RockUartText("EDID CAPS BLOCKS ")
  RockDisplayDecimal(rock_edid_block_count)
  RockUartText(" MODES ")
  RockDisplayDecimal(rock_edid_cap_count)
  RockUartByte(13) : RockUartByte(10)
  If rock_edid_block_count>1
    For block=1 To rock_edid_block_count-1
      RockUartText("EDID EXT ") : RockDisplayDecimal(block)
      RockUartText(" TAG ") : RockDisplayHexByte(rock_edid_extension_tag[block])
      RockUartText(" PARSED ") : RockDisplayDecimal(rock_edid_extension_parsed[block])
      RockUartByte(13) : RockUartByte(10)
    Next
  EndIf
  If rock_edid_range_count>0
    For range=0 To rock_edid_range_count-1
    RockUartText("EDID RANGE V ")
    RockDisplayDecimal(rock_edid_range_min_v[range])
    RockUartByte(45) : RockDisplayDecimal(rock_edid_range_max_v[range])
    RockUartText(" HZ H ")
    RockDisplayDecimal(rock_edid_range_min_h[range])
    RockUartByte(45) : RockDisplayDecimal(rock_edid_range_max_h[range])
    RockUartText(" KHZ PIXEL MAX ")
    RockDisplayDecimal(rock_edid_range_max_pixel[range])
    RockUartByte(13) : RockUartByte(10)
    Next
  EndIf
  For slot=0 To rock_edid_cap_count-1
    source=rock_edid_cap_source[slot]
    RockUartText("EDID CAP ") : RockDisplayDecimal(slot) : RockUartByte(32)
    If source=#ROCK_EDID_CAP_ESTABLISHED
      RockUartText("ESTABLISHED")
    ElseIf source=#ROCK_EDID_CAP_STANDARD
      RockUartText("STANDARD")
    ElseIf source=#ROCK_EDID_CAP_BASE_DTD
      RockUartText("BASE DTD")
    ElseIf source=#ROCK_EDID_CAP_CTA_SVD
      RockUartText("CTA SVD")
    ElseIf source=#ROCK_EDID_CAP_CTA_DTD
      RockUartText("CTA DTD")
    Else
      RockUartText("UNKNOWN")
    EndIf
    RockUartText(" CODE ") : RockDisplayDecimal(rock_edid_cap_code[slot])
    RockUartText(" NATIVE ") : RockDisplayDecimal(rock_edid_cap_native[slot])
    RockUartText(" PREFERRED ") : RockDisplayDecimal(rock_edid_cap_preferred[slot])
    RockUartText(" MAPPED ") : RockDisplayDecimal(rock_edid_cap_mapped[slot])
    If rock_edid_cap_mapped[slot]<>0
      RockUartByte(32) : RockDisplayDecimal(rock_edid_cap_width[slot])
      RockUartByte(88) : RockDisplayDecimal(rock_edid_cap_height[slot])
      RockUartText(" MHZ ") : RockDisplayDecimal(rock_edid_cap_refresh_millihz[slot])
      RockUartText(" PIXEL ") : RockDisplayDecimal(rock_edid_cap_pixel_hz[slot])
      RockUartText(" TOTAL ") : RockDisplayDecimal(rock_edid_cap_htotal[slot])
      RockUartByte(88) : RockDisplayDecimal(rock_edid_cap_vtotal[slot])
      RockUartText(" INTERLACE ") : RockDisplayDecimal(rock_edid_cap_interlaced[slot])
      If rock_edid_cap_hsync_positive[slot]>=0
        RockUartText(" HPOS ") : RockDisplayDecimal(rock_edid_cap_hsync_positive[slot])
        RockUartText(" VPOS ") : RockDisplayDecimal(rock_edid_cap_vsync_positive[slot])
      EndIf
    EndIf
    RockUartByte(13) : RockUartByte(10)
  Next
EndProcedure

Procedure RockDisplayScanoutTelemetry()
  If rock_uart_ready = 0 : ProcedureReturn 0 : EndIf
  RockUartText("SCAN VPLL ")
  RockDisplayHexLong(RockCruRead($C0)) : RockUartByte(32)
  RockDisplayHexLong(RockCruRead($C4)) : RockUartByte(32)
  RockDisplayHexLong(RockCruRead($C8)) : RockUartByte(32)
  RockDisplayHexLong(RockCruRead($CC))
  RockUartText(" DCLK ")
  RockDisplayHexLong(RockCruRead(#ROCK_CRU_CLKSEL+$C8))
  RockUartText(" ACLK/HCLK ")
  RockDisplayHexLong(RockCruRead(#ROCK_CRU_CLKSEL+$C0))
  RockUartText(" CDN TU/SP ")
  RockDisplayHexLong(rock_cdn_programmed_framer_tu) : RockUartByte(32)
  RockDisplayHexLong(rock_cdn_programmed_framer_sp)
  RockUartText(" WIN0 ")
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_CTRL0))
  RockUartText(" HTOTAL ")
  RockDisplayHexLong(RockVopRead(#VOP_HTOTAL))
  RockUartText(" VTOTAL ")
  RockDisplayHexLong(RockVopRead(#VOP_VTOTAL))
  RockUartByte(13) : RockUartByte(10)
  RockUartText("VOP CTRL ")
  RockDisplayHexLong(RockVopRead(#VOP_SYS_CTRL)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_SYS_CTRL1)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_DSP_CTRL0)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_DSP_CTRL1))
  RockUartText(" WIN ")
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_CTRL1)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_VIR)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_YRGB_MST)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_SCL_FACTOR))
  RockUartText(" POST ")
  RockDisplayHexLong(RockVopRead(#VOP_POST_SCL_FACTOR)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_POST_SCL_CTRL))
  RockUartText(" UNUSED/AFBC ")
  RockDisplayHexLong(RockVopRead(#VOP_WIN2_CTRL0)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_AFBCD0_CTRL))
  RockUartByte(13) : RockUartByte(10)
  RockUartText("VOP ACTIVE H/V POST H/V ")
  RockDisplayHexLong(RockVopRead(#VOP_HACT)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_VACT)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_POST_HACT)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_POST_VACT))
  RockUartText(" WIN ACT/DSP/START ")
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_ACT_INFO)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_DSP_INFO)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead(#VOP_WIN0_DSP_ST))
  RockUartByte(13) : RockUartByte(10)
EndProcedure

Procedure.i RockDisplayFrameTelemetry()
  Protected start.i
  Protected now.i
  Protected deadline.i
  Protected raw.i
  Protected faults.i
  Protected frames.i
  Protected hz.i
  Protected attempts.i
  Protected settleRaw.i
  Protected busFaultFrames.i
  Protected win0FaultFrames.i
  Protected postFaultFrames.i
  Protected firstFrameTick.i
  Protected lastFrameTick.i
  ; Pinned RK3399 VOPL RAW_STATUS0 latches frame-start and underrun causes.
  ; Clear uses the VOP write-mask convention: mask in the high half and the
  ; same asserted bits in the low half. CPU interrupts remain disabled.
  ; The VOP begins scanning before the Cadence stream is made active. Preserve
  ; that initial state separately, then let both FIFOs run for several frames
  ; before clearing and measuring the steady path. Otherwise a legitimate
  ; first-fill POST_BUF_EMPTY latch is indistinguishable from a continuing
  ; memory/scanout underrun.
  settleRaw=RockVopRead(#VOP_INTR_RAW_STATUS0)
  RockTimerWaitUs(200000)
  RockVopWrite(#VOP_INTR_CLEAR0,$08610861)
  start=RockTimerTicks()
  deadline=start+(rock_timer_frequency/2)
  For attempts=0 To 9999999
    raw=RockVopRead(#VOP_INTR_RAW_STATUS0)
    faults=faults | (raw & (#VOP_INTR_BUS_ERROR | #VOP_INTR_WIN0_EMPTY | #VOP_INTR_POST_EMPTY))
    If (raw & #VOP_INTR_FS) <> 0
      now=RockTimerTicks()
      If frames=0 : firstFrameTick=now : EndIf
      lastFrameTick=now
      frames=frames+1
      If (raw & #VOP_INTR_BUS_ERROR) <> 0 : busFaultFrames=busFaultFrames+1 : EndIf
      If (raw & #VOP_INTR_WIN0_EMPTY) <> 0 : win0FaultFrames=win0FaultFrames+1 : EndIf
      If (raw & #VOP_INTR_POST_EMPTY) <> 0 : postFaultFrames=postFaultFrames+1 : EndIf
      RockVopWrite(#VOP_INTR_CLEAR0,$08610861)
      If frames=9 : Break : EndIf
    EndIf
    now=RockTimerTicks()
    If now < start Or now >= deadline : Break : EndIf
  Next
  now=RockTimerTicks()
  ; Nine observed frame edges delimit eight complete periods. The time from
  ; the initial clear to the first edge is only a partial frame and must not
  ; enter the frequency calculation (that previously printed about 64 Hz for
  ; a nominal 60-Hz stream).
  If frames > 1 And lastFrameTick > firstFrameTick
    hz=((frames-1)*rock_timer_frequency)/(lastFrameTick-firstFrameTick)
  EndIf
  RockUartText("VOP SETTLE ") : RockDisplayHexLong(settleRaw)
  RockUartText(" STABLE FRAMES ") : RockDisplayDecimal(frames)
  RockUartText(" HZ ") : RockDisplayDecimal(hz)
  RockUartText(" RAW/FAULT ") : RockDisplayHexLong(raw) : RockUartByte(32)
  RockDisplayHexLong(faults)
  RockUartText(" COUNT B/W/P ") : RockDisplayDecimal(busFaultFrames) : RockUartByte(47)
  RockDisplayDecimal(win0FaultFrames) : RockUartByte(47) : RockDisplayDecimal(postFaultFrames)
  RockUartByte(13) : RockUartByte(10)
  ; Transport activation is not display readiness. A recurring underrun or
  ; missing frame boundary must not publish a usable scanout capability.
  ProcedureReturn Bool(frames=9 And faults=0)
EndProcedure

Procedure.i RockDisplayLinkLaneMask()
  ; DPCD 0202h packs lane 0 in the low nibble and lane 1 in the high nibble.
  ; Validate exactly the lane count returned by the completed training event;
  ; never accept an unknown count or require an untrained physical lane.
  Select rock_cdn_link_lanes
    Case 1 : ProcedureReturn $07
    Case 2 : ProcedureReturn $77
  EndSelect
  ProcedureReturn 0
EndProcedure

Procedure RockDisplayLiveLinkTelemetry()
  Protected index.i
  Protected lane01.i
  Protected aligned.i
  Protected required.i
  If rock_uart_ready=0 : ProcedureReturn 0 : EndIf
  RockUartText("DP LINK 0202-0207 ")
  If rock_cdn_live_link_valid=0
    RockUartText("UNAVAILABLE CDNERR ")
    RockDisplayHexByte(rock_cdn_error)
  Else
    For index=0 To 5
      RockDisplayHexByte(rock_cdn_live_link_status[index])
      If index<5 : RockUartByte(32) : EndIf
    Next
    lane01=rock_cdn_live_link_status[0]
    aligned=rock_cdn_live_link_status[2] & 1
    required=RockDisplayLinkLaneMask()
    If required<>0 And (lane01 & required)=required And aligned<>0
      RockUartText(" CHANNEL EQ OK")
    Else
      RockUartText(" CHANNEL EQ LOST")
    EndIf
  EndIf
  RockUartByte(13) : RockUartByte(10)
EndProcedure

Procedure.i RockDisplayCadenceRegister(address.i)
  Protected value.i
  If RockCdnRegRead(address,@value)=0
    ; A timed-out/partial mailbox response is not a fresh message boundary.
    ; Stop this diagnostic batch instead of submitting another command into
    ; the incomplete response. Retain the original mailbox witness/error.
    RockUartText("Read failed with code ")
    RockDisplayDecimal(rock_cdn_error)
    RockUartText("; check the Cadence mailbox witness before retrying.")
    RockUartByte(13) : RockUartByte(10)
    ProcedureReturn 0
  EndIf
  RockDisplayHexLong(value)
  ProcedureReturn 1
EndProcedure

Procedure RockDisplayCadenceTelemetry()
  If rock_uart_ready=0 : ProcedureReturn 0 : EndIf
  RockUartText("CDN VIF ")
  If RockDisplayCadenceRegister(#CDN_VIF_STATUS)=0 : ProcedureReturn 0 : EndIf
  RockUartText(" STUFF ")
  If RockDisplayCadenceRegister(#CDN_PCK_STUFF_STATUS_0)=0 : ProcedureReturn 0 : EndIf
  RockUartByte(32)
  If RockDisplayCadenceRegister(#CDN_PCK_STUFF_STATUS_1)=0 : ProcedureReturn 0 : EndIf
  RockUartText(" RATE ")
  If RockDisplayCadenceRegister(#CDN_RATE_GOVERNOR_STATUS)=0 : ProcedureReturn 0 : EndIf
  RockUartByte(13) : RockUartByte(10)
  RockUartText("CDN SYNC/MTPH/IRQ ")
  If RockDisplayCadenceRegister(#CDN_HSYNC2VSYNC_STATUS)=0 : ProcedureReturn 0 : EndIf
  RockUartByte(32)
  If RockDisplayCadenceRegister(#CDN_MTPH_STATUS)=0 : ProcedureReturn 0 : EndIf
  RockUartByte(32)
  If RockDisplayCadenceRegister(#CDN_INTERRUPT_SOURCE)=0 : ProcedureReturn 0 : EndIf
  ; SOURCE_PIF is one of the Cadence host-visible APB blocks, not a
  ; firmware-owned bank, and is therefore read directly like the mailbox.
  RockUartText(" PIF ") : RockDisplayHexLong(RockCdnRead(#CDN_SOURCE_PIF_STATUS))
  RockUartByte(13) : RockUartByte(10)
EndProcedure

Procedure RockDisplaySubsystemTelemetry(text.i, error.i)
  If rock_uart_ready <> 0
    RockUartText(text)
    RockDisplayHexByte(error)
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure RockDisplayDpPowerTelemetry()
  Protected value.i
  If rock_uart_ready <> 0
    value = PeekL(#ROCK_GPIO1+$50) & $FFFFFFFF
    RockUartText("DP_PWR LEVEL ")
    RockUartByte(48+((value >> 24) & 1))
    RockUartText(" EXT ")
    RockDisplayHexLong(value)
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure RockDisplayFirmwareTelemetry()
  If rock_uart_ready <> 0
    RockUartText("CADENCE FW ")
    RockDisplayHexLong(rock_cdn_firmware_version)
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure RockDisplayTcPhyTelemetry()
  If rock_uart_ready <> 0
    RockUartText("TCPHY CMN ")
    RockDisplayHexLong(RockTcRead(#TCPHY_PMA_CMN_CTRL1))
    RockUartText(" MODE ")
    RockDisplayHexLong(RockTcRead(#TCPHY_DP_MODE_CTL))
    RockUartText(" MAP ")
    RockDisplayHexLong(RockTcRead(#TCPHY_PMA_LANE_CFG))
    RockUartText(" AUX ")
    RockDisplayHexLong(RockTcRead(#TCPHY_TX_ANA1))
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure RockDisplayGrfTelemetry()
  If rock_uart_ready <> 0
    RockUartText("GRF_SOC_CON26 ")
    RockDisplayHexLong(PeekL(#ROCK_GRF+$6268) & $FFFFFFFF)
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure RockDisplayCruTelemetry()
  If rock_uart_ready <> 0
    RockUartText("DPE1 DETAIL ERR ")
    RockDisplayHexByte(rock_cru_error)
    RockUartText(" SOURCE ")
    If rock_cru_error >= 47 And rock_cru_error <= 52
      RockUartText("GPLL")
    ElseIf rock_cru_error >= 53 And rock_cru_error <= 55
      RockUartText("VIO")
    ElseIf rock_cru_error >= 56 And rock_cru_error <= 58
      RockUartText("HDCP")
    ElseIf rock_cru_error = 59
      RockUartText("VO")
    ElseIf rock_cru_error >= 60 And rock_cru_error <= 61
      RockUartText("VOPL")
    ElseIf rock_cru_error = 62
      RockUartText("TCPD0")
    ElseIf rock_cru_error >= 63 And rock_cru_error <= 65
      RockUartText("VPLL")
    ElseIf rock_cru_error = 66
      RockUartText("PIXEL CLOCK PLAN")
    ElseIf rock_cru_error = 67 Or rock_cru_error = 68
      RockUartText("VIO/HDCP CLOCK TREE")
    ElseIf rock_cru_error = 69
      RockUartText("TCPHY CLOCK TREE")
    ElseIf rock_cru_error = 70 Or rock_cru_error = 71
      RockUartText("CDN/SPDIF CLOCK TREE")
    ElseIf rock_cru_error = 72 Or rock_cru_error = 73
      RockUartText("VOP CLOCK TREE")
    ElseIf rock_cru_error >= 74 And rock_cru_error <= 79
      RockUartText("DISPLAY CLOCK GATES")
    Else
      RockUartText("UNKNOWN")
    EndIf
    RockUartText(" CPLL ")
    RockDisplayHexLong(RockCruRead($60))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($64))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($68))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($6C))
    RockUartText(" GPLL ")
    RockDisplayHexLong(RockCruRead($80))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($84))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($88))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($8C))
    RockUartText(" VPLL ")
    RockDisplayHexLong(RockCruRead($C0))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($C4))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($C8))
    RockUartByte(32)
    RockDisplayHexLong(RockCruRead($CC))
    RockUartText(" PMU ")
    RockDisplayHexLong(PeekL(#ROCK_PMU+#ROCK_PMU_PWRDN_ST) & $FFFFFFFF)
    RockUartByte(32)
    RockDisplayHexLong(PeekL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_REQ) & $FFFFFFFF)
    RockUartByte(32)
    RockDisplayHexLong(PeekL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_ST) & $FFFFFFFF)
    RockUartByte(32)
    RockDisplayHexLong(PeekL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_ACK) & $FFFFFFFF)
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure RockDisplayMailboxTelemetry()
  Protected index.i
  RockUartText(" MBOX GOT ")
  If rock_cdn_mailbox_actual_opcode < 0
    RockUartText("--")
  Else
    RockDisplayHexByte(rock_cdn_mailbox_actual_opcode)
  EndIf
  RockUartByte(47)
  If rock_cdn_mailbox_actual_module < 0
    RockUartText("--")
  Else
    RockDisplayHexByte(rock_cdn_mailbox_actual_module)
  EndIf
  RockUartByte(47)
  If rock_cdn_mailbox_actual_size < 0
    If rock_cdn_mailbox_actual_size_high < 0
      RockUartText("----")
    Else
      RockDisplayHexByte(rock_cdn_mailbox_actual_size_high)
      RockUartText("??")
    EndIf
  Else
    RockDisplayHexWord(rock_cdn_mailbox_actual_size)
  EndIf
  RockUartText(" EXPECT ")
  RockDisplayHexByte(rock_cdn_mailbox_expected_opcode)
  RockUartByte(47)
  RockDisplayHexByte(rock_cdn_mailbox_expected_module)
  RockUartByte(47)
  RockDisplayHexWord(rock_cdn_mailbox_expected_size)
  RockUartText(" HEADER ")
  RockDisplayHexByte(rock_cdn_mailbox_header_count)
  RockUartText("/04")
  RockUartText(" DRAIN ")
  RockDisplayHexWord(rock_cdn_mailbox_drain_count)
  RockUartByte(47)
  If rock_cdn_mailbox_actual_size < 0
    RockUartText("----")
  Else
    RockDisplayHexWord(rock_cdn_mailbox_actual_size)
  EndIf
  If rock_cdn_mailbox_drain_complete = 0 : RockUartText(" INCOMPLETE") : EndIf
  If rock_cdn_mailbox_payload5_valid <> 0
    RockUartText(" PAYLOAD")
    For index = 0 To 4
      RockUartByte(32)
      RockDisplayHexByte(PeekA(@rock_cdn_mailbox_payload5[0]+index) & 255)
    Next
  EndIf
EndProcedure

Procedure RockDisplayDpcdTelemetry()
  If rock_uart_ready <> 0
    RockUartText("DPE8 DPCD PHASE ")
    RockUartByte(48+rock_cdn_dpcd_phase)
    RockUartText(" AUX ")
    If rock_cdn_aux_status < 0
      RockUartText("--")
    Else
      RockDisplayHexByte(rock_cdn_aux_status)
    EndIf
    RockUartText(" CDNERR ")
    RockDisplayHexByte(rock_cdn_error)
    If rock_cdn_dpcd_phase = #CDN_DPCD_PHASE_RESPONSE Or rock_cdn_dpcd_phase = #CDN_DPCD_PHASE_AUX_MAILBOX
      RockDisplayMailboxTelemetry()
    EndIf
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure.i RockDisplayUp()
  Protected prepared.i
  Protected configured.i
  Protected modeFailure.i
  Protected linkLaneMask.i
  rock_display_ready=0
  rock_display_width=0
  rock_display_height=0
  rock_display_pitch=0
  rock_display_buffer=0
  rock_display_error=0
  RockDisplayStage("DP00 BEGIN COLD MINIDP")
  prepared = RockCruDisplayPrepare()
  RockDisplayDpPowerTelemetry()
  If prepared=0
    RockDisplayCruTelemetry()
    ProcedureReturn RockDisplayFail(1,"DPE1 CRU OR POWER DOMAIN")
  EndIf
  If RockCruCadenceRelease()=0
    RockDisplaySubsystemTelemetry("DPE3 CRU ERR ",rock_cru_error)
    ProcedureReturn RockDisplayFail(3,"DPE3 CADENCE RESET RELEASE")
  EndIf
  ; Cadence consumes the actual integer core clock in MHz, not MHz-1.
  RockCdnWrite(#CDN_SW_CLK_H,rock_cru_dp_core_rate/1000000)
  RockCdnInternalClocks()
  RockDisplayStage("DP01 CADENCE CLOCKS POWER RESETS READY")
  If RockCdnFirmwareLoad()=0
    RockDisplaySubsystemTelemetry("DPE4 CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(4,"DPE4 CADENCE FIRMWARE")
  EndIf
  RockDisplayFirmwareTelemetry()
  If RockCdnFirmwareActive(1)=0
    RockDisplaySubsystemTelemetry("DPE5 CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(5,"DPE5 CADENCE FIRMWARE ACTIVE")
  EndIf
  If RockCdnEnableEvents()=0
    RockDisplaySubsystemTelemetry("DPE6 CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(6,"DPE6 CADENCE EVENT CONFIG")
  EndIf
  RockDisplayStage("DP02 CADENCE FIRMWARE EVENTS READY")
  If RockTcPhyUp()=0
    RockDisplaySubsystemTelemetry("DPE2 TCPHY ERR ",rock_tcphy_error)
    ProcedureReturn RockDisplayFail(2,"DPE2 TCPHY0 DP USB SPLIT")
  EndIf
  RockDisplayTcPhyTelemetry()
  RockDisplayStage("DP03 TCPHY0 AUX AND TWO LANES READY")
  ; Select the Cadence HPD path only after PHY AUX and firmware are alive.
  PokeL(#ROCK_GRF+$6268,$30003000)
  RockDisplayGrfTelemetry()
  If RockCdnHotPlug()=0
    RockDisplaySubsystemTelemetry("DPE7 CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(7,"DPE7 MINIDP HPD ABSENT")
  EndIf
  RockDisplayStage("DP04 HPD PRESENT")
  If RockCdnHostCapabilities()=0
    RockDisplaySubsystemTelemetry("DPEF CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(15,"DPEF CADENCE HOST CAPABILITIES")
  EndIf
  If RockCdnDpcd()=0
    RockDisplayDpcdTelemetry()
    ProcedureReturn RockDisplayFail(8,"DPE8 DPCD AUX READ")
  EndIf
  If RockCdnReadEdid()=0
    RockDisplaySubsystemTelemetry("DPE9 CDN ERR ",rock_cdn_error)
    If rock_cdn_error = 30 Or rock_cdn_error = 43
      RockDisplayEdidTelemetry()
    EndIf
    If rock_cdn_error = 43
      RockDisplaySubsystemTelemetry("DPE9 EDID CAP REASON ",rock_edid_error)
    ElseIf rock_cdn_error = 30
      RockDisplaySubsystemTelemetry("DPE9 MODE REJECTION REASON ",rock_mode_reason)
    EndIf
    ProcedureReturn RockDisplayFail(9,"DPE9 INVALID EDID OR NO SUPPORTED MODE")
  EndIf
  RockDisplayEdidTelemetry()
  RockDisplayEdidCapabilities()
  RockDisplayModeTelemetry("DP05 EDID MODE ")
  If RockCdnTrain()=0
    RockDisplaySubsystemTelemetry("DPEB CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(11,"DPEB DISPLAYPORT LINK TRAIN")
  EndIf
  RockDisplayStage("DP07 LINK TRAINED")
  If RockCdnVideoStatus(0)=0
    RockDisplaySubsystemTelemetry("DPEC CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(12,"DPEC VIDEO IDLE")
  EndIf
  ; Admit the selected mode before any timing registers are programmed.
  ; The encoder's pure plan performs no mailbox writes on refusal.
  configured = RockCdnPlanVideo()
  If configured = 0 And (rock_cdn_error = 35 Or rock_cdn_error = 36)
    modeFailure = rock_cdn_error
    If RockModeFallback(@rock_cdn_edid[0],modeFailure) <> 0
      RockDisplayModeTelemetry("DP MODE FALLBACK ")
      configured = RockCdnPlanVideo()
    EndIf
  EndIf
  If configured=0
    RockDisplaySubsystemTelemetry("DPED CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(13,"DPED VIDEO TIMING")
  EndIf
  If RockVopModeValid()=0
    RockDisplaySubsystemTelemetry("DPEA VOP ERR ",rock_vop_error)
    ProcedureReturn RockDisplayFail(10,"Display admission failed with code 10; check the selected mode's timing and framebuffer bounds.")
  EndIf
  If RockCruVpllMode()=0
    RockDisplaySubsystemTelemetry("DPE1 CRU ERR ",rock_cru_error)
    ProcedureReturn RockDisplayFail(1,"DPE1 SELECTED PIXEL CLOCK")
  EndIf
  ; Mirror the full Rockchip DRM lifecycle, not isolated register snippets:
  ; rockchip_drm_fb.c rockchip_atomic_commit_complete enables the CRTC,
  ; then its encoder, then commits the primary plane. drm_atomic_helper.c
  ; commit_modeset_enables establishes that CRTC-before-encoder ordering.
  If RockVopPrepareMode()=0
    RockDisplaySubsystemTelemetry("DPEA VOP ERR ",rock_vop_error)
    ProcedureReturn RockDisplayFail(10,"Display setup failed with code 10; check the VOP timing-generator initialization.")
  EndIf
  ; cdn_dp_encoder_enable owns GRF_SOC_CON9 DP_SEL_VOP_LIT. The
  ; transmitter route belongs to this encoder commit, not plane setup.
  PokeL(#ROCK_GRF+$6224,$10001000)
  If RockCdnVideoMode()=0
    RockDisplaySubsystemTelemetry("DPED CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(13,"Display setup failed with code 13; check the DisplayPort timing programming.")
  EndIf
  If RockCdnVideoStatus(1)=0
    RockDisplaySubsystemTelemetry("DPEE CDN ERR ",rock_cdn_error)
    ProcedureReturn RockDisplayFail(14,"DPEE VIDEO VALID")
  EndIf
  If RockVopConfigurePrimary()=0
    RockDisplaySubsystemTelemetry("DPEA VOP ERR ",rock_vop_error)
    ProcedureReturn RockDisplayFail(10,"Display setup failed with code 10; check the primary-plane configuration.")
  EndIf
  If RockVopStartPrimary()=0
    RockDisplaySubsystemTelemetry("DPEA VOP ERR ",rock_vop_error)
    ProcedureReturn RockDisplayFail(10,"Display setup failed with code 10; check the primary-plane frame boundary.")
  EndIf
  RockDisplayStage("DP06 COLOR BARS AND TEXT ARMED")
  RockDisplayScanoutTelemetry()
  RockTimerWaitUs(50000)
  If RockCdnReadLiveLinkStatus()<>0
    RockDisplayLiveLinkTelemetry()
    RockDisplayCadenceTelemetry()
  Else
    RockDisplayLiveLinkTelemetry()
    ProcedureReturn RockDisplayFail(17,"Display validation failed with code 17; check the DisplayPort link-status response.")
  EndIf
  linkLaneMask=RockDisplayLinkLaneMask()
  If linkLaneMask=0 Or (rock_cdn_live_link_status[0] & linkLaneMask)<>linkLaneMask Or (rock_cdn_live_link_status[2] & 1)=0
    ProcedureReturn RockDisplayFail(17,"Display validation failed with code 17; check DisplayPort lane alignment and channel equalization.")
  EndIf
  If RockDisplayFrameTelemetry()=0
    ProcedureReturn RockDisplayFail(16,"Display validation failed with code 16; scanout underruns or frame boundaries are missing. Check the timing and pixel-supply pipeline.")
  EndIf
  rock_display_width=rock_mode_width
  rock_display_height=rock_mode_height
  rock_display_pitch=rock_mode_pitch
  rock_display_buffer=RockVopFramebuffer()
  rock_display_ready=1
  RockDisplayModeTelemetry("DP08 SCANOUT READY ")
  ProcedureReturn 1
EndProcedure

Procedure.i RockDisplayBuffer()
  If rock_display_ready=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn rock_display_buffer
EndProcedure

Procedure.i RockDisplayWidth()
  ProcedureReturn rock_display_width
EndProcedure

Procedure.i RockDisplayHeight()
  ProcedureReturn rock_display_height
EndProcedure

Procedure.i RockDisplayPitch()
  ProcedureReturn rock_display_pitch
EndProcedure
