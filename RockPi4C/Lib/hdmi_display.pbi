; One-shot HDMI RGB888 scanout path for the Rock Pi 4C board route.
; The shipped board DTS connects VOPB to RK3399 DW HDMI; MiniDP continues to
; use VOPL. This facade owns DDC/EDID, VOPB and HDMI activation ordering.

#ROCK_HDMI_EDID_BYTES = 128
#ROCK_HDMI_GRF_SOC_CON20 = $FF776250
#ROCK_HDMI_GRF_VOP_SEL_MASK = $00000040
#ROCK_HDMI_GRF_GPIO4C_IOMUX = $FF77E028
#ROCK_HDMI_GRF_HDMI_DDC_MASK = $0000000F
#ROCK_HDMI_GRF_HDMI_DDC_FUNC3 = $0000000F
#ROCK_HDMI_DESIGN_ID = $0000
#ROCK_HDMI_REVISION_ID = $0001
#ROCK_HDMI_PRODUCT_ID0 = $0002
#ROCK_HDMI_PRODUCT_ID1 = $0003

Global Dim rock_hdmi_edid.a[#ROCK_HDMI_EDID_BYTES]
Global rock_hdmi_attempted.i
Global rock_display_stage.i
Global rock_hdmi_controller_ready.i
Global rock_hdmi_route_before.i
Global rock_hdmi_route_after.i

Procedure RockHdmiVopTelemetry()
  RockVopCaptureTelemetry()
  If rock_uart_ready=0
    ProcedureReturn
  EndIf
  RockUartText("HDMI VOP RAW VER=") : RockDisplayHexLong(rock_vop_raw_version)
  RockUartText(" SYS=") : RockDisplayHexLong(rock_vop_raw_sys_ctrl)
  RockUartText(" SYS1=") : RockDisplayHexLong(rock_vop_raw_sys_ctrl1)
  RockUartText(" DSP0=") : RockDisplayHexLong(rock_vop_raw_dsp_ctrl0)
  RockUartText(" DSP1=") : RockDisplayHexLong(rock_vop_raw_dsp_ctrl1)
  RockUartText(" ROUTE=") : RockDisplayHexLong(rock_hdmi_route_before)
  RockUartByte(58) : RockDisplayHexLong(rock_hdmi_route_after)
  RockUartByte(13) : RockUartByte(10)
  RockUartText("HDMI VOP WIN0=") : RockDisplayHexLong(rock_vop_raw_win0_ctrl0)
  RockUartText(" VIR=") : RockDisplayHexLong(rock_vop_raw_win0_vir)
  RockUartText(" MST=") : RockDisplayHexLong(rock_vop_raw_win0_mst)
  RockUartText(" STATUS=") : RockDisplayHexLong(rock_vop_raw_status)
  RockUartText(" INTR=") : RockDisplayHexLong(rock_vop_raw_intr)
  RockUartByte(13) : RockUartByte(10)
  RockUartText("HDMI VOP TIMING H=") : RockDisplayHexLong(rock_vop_raw_htotal)
  RockUartByte(58) : RockDisplayHexLong(rock_vop_raw_hact)
  RockUartText(" V=") : RockDisplayHexLong(rock_vop_raw_vtotal)
  RockUartByte(58) : RockDisplayHexLong(rock_vop_raw_vact)
  RockUartByte(13) : RockUartByte(10)
  RockUartText("HDMI VOP MMU DTE=") : RockDisplayHexLong(rock_vop_mmu_dte)
  RockUartText(" STATUS=") : RockDisplayHexLong(rock_vop_mmu_status)
  RockUartText(" FAULT=") : RockDisplayHexLong(rock_vop_mmu_fault)
  RockUartText(" RAW=") : RockDisplayHexLong(rock_vop_mmu_raw)
  RockUartText(" MASK=") : RockDisplayHexLong(rock_vop_mmu_mask)
  RockUartText(" IRQ=") : RockDisplayHexLong(rock_vop_mmu_irq)
  RockUartText(" GATE=") : RockDisplayHexLong(rock_vop_mmu_gating)
  RockUartByte(13) : RockUartByte(10)
EndProcedure

Procedure.i RockHdmiDisplayFail(code.i,text.i)
  ; A failed publication cannot leave later UART bytes targeting a surface
  ; whose scanout/health contract was refused.
  RockUartSetMirrorHook(0)
  rock_display_ready=0
  If rock_uart_ready<>0
    If rock_hdmi_controller_ready<>0 : RockHdmiStateTelemetry() : EndIf
    RockUartText("HDMI DETAIL CRU_ERR=") : RockDisplayHexLong(rock_cru_error)
    RockUartText(" PMIC_ERR=") : RockDisplayHexByte(rock_pmic_error)
    RockUartText(" DMA_ERR=") : RockDisplayHexByte(rock_dma_pl330_error)
    RockUartText(" SCREEN_ERR=") : RockDisplayHexByte(rock_screen_fault)
    RockUartText(" GPLL_HZ=") : RockDisplayDecimal(rock_cru_gpll_rate)
    RockUartText(" TX_ERR=") : RockDisplayHexLong(rock_hdmi_error)
    If rock_hdmi_controller_ready<>0
      ; DW identification and PHY status separate an inaccessible/unclocked
      ; core from a live transmitter reporting HPD low. Registers are byte
      ; reads through RockHdmiRead8's RK3399 offset*4 access.
      RockUartText(" DW_ID=")
      RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_DESIGN_ID)) : RockUartByte(58)
      RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_REVISION_ID)) : RockUartByte(58)
      RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_PRODUCT_ID0)) : RockUartByte(58)
      RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_PRODUCT_ID1))
      RockUartText(" PHY=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_PHY_STAT0))
    EndIf
    RockUartByte(13) : RockUartByte(10)
    If rock_mode_valid<>0 : RockDisplayModeTelemetry("HDMI MODE ") : EndIf
    If rock_vop_prepared<>0 : RockHdmiVopTelemetry() : EndIf
  EndIf
  ProcedureReturn RockDisplayFail(code,text)
EndProcedure

Procedure.i RockHdmiDisplayUp()
  Protected route.i
  Protected dmaReady.i
  Protected hpd.i
  Protected hpdStart.i
  Protected hpdNow.i
  Protected hpdAttempt.i
  rock_display_ready=0
  rock_display_buffer=0
  RockUartSetMirrorHook(0)
  rock_display_error=0
  rock_display_stage=$D000
  rock_hdmi_route_before=0
  rock_hdmi_route_after=0
  If rock_hdmi_attempted<>0
    ProcedureReturn RockDisplayFail(20,"HDMI is one-shot after hardware setup; reboot before retry.")
  EndIf
  rock_hdmi_attempted=1
  RockVopSelectHdmiVopB()
  RockDisplayStage("HD00 HDMI VOPB ROUTE BEGIN")
  rock_display_stage=$D001
  If RockCruHdmiPrepare()=0
    ProcedureReturn RockHdmiDisplayFail(20,"HDE0 HDMI/VOPB clocks, power domain, or reset setup failed.")
  EndIf
  RockWatchdogPet()
  rock_display_stage=$D001
  If RockPmicHdmiRailsEnsure()=0
    ProcedureReturn RockHdmiDisplayFail(32,"HDE0B RK808 HDMI rail preflight or enable failed.")
  EndIf
  RockWatchdogPet()
  rock_hdmi_controller_ready=1
  ; DTS hdmi_i2c_xfer muxes GPIO4_C0/C1 to the internal HDMI DDC engine.
  PokeL(#ROCK_HDMI_GRF_GPIO4C_IOMUX,(#ROCK_HDMI_GRF_HDMI_DDC_MASK << 16) | #ROCK_HDMI_GRF_HDMI_DDC_FUNC3)
  ASM
    dsb sy
  ENDASM
  If (PeekL(#ROCK_HDMI_GRF_GPIO4C_IOMUX) & #ROCK_HDMI_GRF_HDMI_DDC_MASK) <> #ROCK_HDMI_GRF_HDMI_DDC_FUNC3
    ProcedureReturn RockHdmiDisplayFail(31,"HDE0A HDMI DDC PINMUX READBACK FAILED.")
  EndIf
  RockWatchdogPet()
  RockDisplayStage("HD01 HDMI AND VOPB POWER CLOCK RESET READY")
  rock_display_stage=$D002
  hpd=0
  hpdStart=RockTimerTicks()
  For hpdAttempt=0 To 2999
    If RockHdmiHotplugPresent()<>0 : hpd=1 : Break : EndIf
    hpdNow=RockTimerTicks()
    If hpdNow<hpdStart Or hpdNow-hpdStart>=rock_timer_frequency*3/10 : Break : EndIf
    RockTimerWaitUs(100)
  Next
  If hpd=0
    ProcedureReturn RockHdmiDisplayFail(21,"HDE1 HDMI HOT-PLUG ABSENT.")
  EndIf
  ; Feed only after HPD is observed. The bounded HPD poll itself must never
  ; keep a dead transmitter alive indefinitely.
  RockWatchdogPet()
  rock_display_stage=$D003
  If RockHdmiReadEdid(@rock_hdmi_edid[0])=0
    ProcedureReturn RockHdmiDisplayFail(22,"HDE2 HDMI DDC EDID BASE BLOCK READ FAILED.")
  EndIf
  RockHdmiDetectSink(@rock_hdmi_edid[0])
  RockUartText("HDMI EDID SINK=")
  If rock_hdmi_sink_hdmi<>0 : RockUartLine("HDMI CTA VSDB") : Else : RockUartLine("DVI/UNKNOWN") : EndIf
  RockWatchdogPet()
  rock_display_stage=$D004
  If RockModeSelect(@rock_hdmi_edid[0])=0
    ProcedureReturn RockHdmiDisplayFail(23,"HDE3 HDMI EDID HAS NO SUPPORTED MODE.")
  EndIf
  RockWatchdogPet()
  rock_display_stage=$D005
  If RockVopModeValid()=0
    ProcedureReturn RockHdmiDisplayFail(24,"HDE4 HDMI MODE EXCEEDS VOPB OR FRAMEBUFFER BOUNDS.")
  EndIf
  RockWatchdogPet()
  RockDisplayStage("HD02 HDMI EDID MODE SELECTED")
  RockDisplayModeTelemetry("HDMI SELECTED ")
  rock_display_stage=$D006
  RockDisplayStage("HD02A HDMI VPLL BEGIN")
  If RockCruVpllModeForVop(0)=0
    ProcedureReturn RockHdmiDisplayFail(25,"HDE5 HDMI VOPB PIXEL CLOCK SETUP FAILED.")
  EndIf
  RockWatchdogPet()
  RockDisplayStage("HD02B HDMI VPLL READY")
  rock_display_stage=$D007
  RockDisplayStage("HD02C HDMI VOPB BACKGROUND BEGIN")
  If RockVopPrepareMode()=0
    ProcedureReturn RockHdmiDisplayFail(26,"HDE6 HDMI VOPB TIMING OR BACKGROUND FRAME FAILED.")
  EndIf
  RockWatchdogPet()
  RockDisplayStage("HD02D HDMI VOPB BACKGROUND READY")
  rock_display_stage=$D008
  ; GRF_SOC_CON20[6]: 0 selects VOPB, 1 selects VOPL. GRF writes use
  ; Rockchip's upper-halfword write mask.
  rock_hdmi_route_before=PeekL(#ROCK_HDMI_GRF_SOC_CON20) & #ROCK_HDMI_GRF_VOP_SEL_MASK
  PokeL(#ROCK_HDMI_GRF_SOC_CON20,(#ROCK_HDMI_GRF_VOP_SEL_MASK << 16))
  ASM
    dsb sy
  ENDASM
  rock_hdmi_route_after=PeekL(#ROCK_HDMI_GRF_SOC_CON20) & #ROCK_HDMI_GRF_VOP_SEL_MASK
  route=rock_hdmi_route_after
  If route<>0
    ProcedureReturn RockHdmiDisplayFail(27,"HDE7 HDMI GRF VOPB ROUTE READBACK FAILED.")
  EndIf
  RockWatchdogPet()
  rock_display_stage=$D009
  If RockHdmiEnableSelected()=0
    ProcedureReturn RockHdmiDisplayFail(28,"HDE8 HDMI TRANSMITTER OR PHY INITIALIZATION FAILED.")
  EndIf
  RockWatchdogPet()
  rock_display_stage=$D00A
  If RockVopConfigurePrimary()=0
    ProcedureReturn RockHdmiDisplayFail(29,"HDE9 HDMI VOPB PRIMARY PLANE CONFIGURATION FAILED.")
  EndIf
  RockWatchdogPet()
  ; ConfigurePrimary has now established the exact linear ARGB8888 surface,
  ; but WIN0 is still disabled. Publish it to the standard screen adapter,
  ; attempt the source-backed PL330 owner, and finish the complete banner
  ; before the first frame can become visible. A failed DMA admission remains
  ; explicit telemetry while the screen adapter uses its bounded CPU path.
  rock_display_width=rock_mode_width
  rock_display_height=rock_mode_height
  rock_display_pitch=rock_mode_pitch
  rock_display_buffer=RockVopFramebuffer()
  rock_display_ready=1
  dmaReady=RockDmaPl330Init()
  If dmaReady=0
    RockUartText("HDMI DMA UNAVAILABLE DMA_ERR=")
    RockDisplayHexByte(rock_dma_pl330_error)
    RockUartLine("; CPU FRAME FALLBACK")
  EndIf
  RockWatchdogPet()
  If RockScreenComposeStandardFrame()=0
    ProcedureReturn RockHdmiDisplayFail(35,"HDE9B STANDARD ANVIL FRAME COMPOSITION FAILED.")
  EndIf
  ; From this point each successfully transmitted UART byte is only queued;
  ; RockRecoveryLoop remains the sole consumer and renderer.
  RockUartSetMirrorHook(@RockScreenMirrorByte)
  rock_display_stage=$D00B
  If RockVopStartPrimary()=0
    ProcedureReturn RockHdmiDisplayFail(30,"HDEA HDMI VOPB FIRST FRAME TIMEOUT.")
  EndIf
  RockWatchdogPet()
  ; A single frame-start proves timing only. Reuse the pinned VOP health
  ; witness to clear sticky startup history and require nine fresh frame edges
  ; with no recurring AXI, WIN0, or post-buffer fault before publishing HDMI.
  If RockDisplayFrameTelemetry()=0
    ProcedureReturn RockHdmiDisplayFail(33,"HDEB HDMI VOPB FRAMEBUFFER SCANOUT FAULT.")
  EndIf
  RockWatchdogPet()
  rock_display_stage=$D00C
  RockHdmiVopTelemetry()
  RockHdmiStateTelemetry()
  RockWatchdogPet()
  RockDisplayStage("HD03 HDMI VOPB RGB888 FRAME ACTIVE")
  ProcedureReturn 1
EndProcedure
