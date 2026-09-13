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

Procedure RockDisplayCruTelemetry()
  If rock_uart_ready <> 0
    RockUartText("DPE1 DETAIL ERR ")
    RockDisplayHexByte(rock_cru_error)
    RockUartText(" SOURCE ")
    If rock_cru_error >= 47 And rock_cru_error <= 49
      RockUartText("CPLL")
    ElseIf rock_cru_error >= 50 And rock_cru_error <= 52
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
    ElseIf rock_cru_error = 64
      RockUartText("RESET")
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
    RockUartText("----")
  Else
    RockDisplayHexWord(rock_cdn_mailbox_actual_size)
  EndIf
  RockUartText(" EXPECT ")
  RockDisplayHexByte(rock_cdn_mailbox_expected_opcode)
  RockUartByte(47)
  RockDisplayHexByte(rock_cdn_mailbox_expected_module)
  RockUartByte(47)
  RockDisplayHexWord(rock_cdn_mailbox_expected_size)
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
    If rock_cdn_error = 24 : RockDisplayMailboxTelemetry() : EndIf
    RockUartByte(13)
    RockUartByte(10)
  EndIf
EndProcedure

Procedure.i RockDisplayUp()
  rock_display_ready=0
  rock_display_error=0
  RockDisplayStage("DP00 BEGIN COLD MINIDP")
  If RockCruDisplayPrepare()=0
    RockDisplayCruTelemetry()
    ProcedureReturn RockDisplayFail(1,"DPE1 CRU OR POWER DOMAIN")
  EndIf
  If RockCruCadenceRelease()=0 : ProcedureReturn RockDisplayFail(3,"DPE3 CADENCE RESET RELEASE") : EndIf
  RockCdnWrite(#CDN_SW_CLK_H,99)
  RockCdnInternalClocks()
  RockDisplayStage("DP01 CADENCE CLOCKS POWER RESETS READY")
  If RockCdnFirmwareLoad()=0 : ProcedureReturn RockDisplayFail(4,"DPE4 CADENCE FIRMWARE") : EndIf
  If RockCdnFirmwareActive(1)=0 : ProcedureReturn RockDisplayFail(5,"DPE5 CADENCE FIRMWARE ACTIVE") : EndIf
  If RockCdnEnableEvents()=0 : ProcedureReturn RockDisplayFail(6,"DPE6 CADENCE EVENT CONFIG") : EndIf
  RockDisplayStage("DP02 CADENCE FIRMWARE EVENTS READY")
  If RockTcPhyUp()=0 : ProcedureReturn RockDisplayFail(2,"DPE2 TCPHY0 DP USB SPLIT") : EndIf
  RockDisplayStage("DP03 TCPHY0 AUX AND TWO LANES READY")
  ; Select the Cadence HPD path only after PHY AUX and firmware are alive.
  PokeL(#ROCK_GRF+$6268,$30003000)
  If RockCdnHotPlug()=0 : ProcedureReturn RockDisplayFail(7,"DPE7 MINIDP HPD ABSENT") : EndIf
  RockDisplayStage("DP04 HPD PRESENT")
  If RockCdnHostCapabilities()=0 : ProcedureReturn RockDisplayFail(15,"DPEF CADENCE HOST CAPABILITIES") : EndIf
  If RockCdnDpcd()=0
    RockDisplayDpcdTelemetry()
    ProcedureReturn RockDisplayFail(8,"DPE8 DPCD AUX READ")
  EndIf
  If RockCdnReadEdid()=0 : ProcedureReturn RockDisplayFail(9,"DPE9 EDID OR 1024X768 MODE") : EndIf
  RockDisplayStage("DP05 DPCD EDID 1024X768 READY")
  If RockVopUp1024x768()=0 : ProcedureReturn RockDisplayFail(10,"DPEA VOPL FRAMEBUFFER") : EndIf
  RockDisplayStage("DP06 COLOR BARS AND TEXT ARMED")
  If RockCdnTrain()=0 : ProcedureReturn RockDisplayFail(11,"DPEB DISPLAYPORT LINK TRAIN") : EndIf
  RockDisplayStage("DP07 LINK TRAINED")
  If RockCdnVideoStatus(0)=0 : ProcedureReturn RockDisplayFail(12,"DPEC VIDEO IDLE") : EndIf
  If RockCdnVideo1024x768()=0 : ProcedureReturn RockDisplayFail(13,"DPED VIDEO TIMING") : EndIf
  If RockCdnVideoStatus(1)=0 : ProcedureReturn RockDisplayFail(14,"DPEE VIDEO VALID") : EndIf
  rock_display_width=#ROCK_FB_WIDTH
  rock_display_height=#ROCK_FB_HEIGHT
  rock_display_pitch=#ROCK_FB_WIDTH*4
  rock_display_buffer=RockVopFramebuffer()
  rock_display_ready=1
  RockDisplayStage("DP08 VISIBLE 1024X768 COLOR BARS ANVIL ROCK PI 4C")
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
