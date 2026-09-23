; RK3399 DesignWare HDMI transmitter path from the pinned Rockchip U-Boot
; driver (drivers/video/dw_hdmi.c + rockchip/rk_hdmi.c). This module owns
; only DW frame-composer/packetizer/TX PHY registers. HDMI registers are
; byte-wide over a 32-bit bus: every DW byte offset is multiplied by 4, as
; required by rk3399.dtsi reg-io-width = <4>.
;
; Preconditions: EL3, MMU/data and instruction caches off, architectural
; timer initialized, HDMI clocks and HDCP power domain enabled, HDMI block
; deasserted from reset, VOP HDMI route and background timing configured,
; connected sink detected and rock_mode_* selected. VOP primary plane is
; deliberately outside this layer. No interrupt/GIC state is needed.
;
; The RK3399 U-Boot table supports standard TMDS modes through 340 MHz. The
; board's first-frame fallback is the exact 1024x768@65 MHz VPLL profile; it
; maps to the Rockchip MPLL 65 MHz row and PHY <=74.25 MHz row. Other modes
; use the same source table ceiling-selection rules, capped at 340 MHz.

#ROCK_HDMI_BASE = $FF940000
#ROCK_HDMI_IH_I2CMPHY_STAT0 = $0108
#ROCK_HDMI_IH_I2CM_STAT0 = $0105
#ROCK_HDMI_IH_FC_STAT2 = $0102
#ROCK_HDMI_IH_PHY_STAT0 = $0104
#ROCK_HDMI_IH_MUTE_FC_STAT2 = $0182
#ROCK_HDMI_IH_MUTE_I2CM_STAT0 = $0185
#ROCK_HDMI_IH_MUTE = $01FF
#ROCK_HDMI_TX_INVID0 = $0200
#ROCK_HDMI_TX_INSTUFFING = $0201
#ROCK_HDMI_FC_INVIDCONF = $1000
#ROCK_HDMI_FC_INHACTV0 = $1001
#ROCK_HDMI_FC_INHACTV1 = $1002
#ROCK_HDMI_FC_INHBLANK0 = $1003
#ROCK_HDMI_FC_INHBLANK1 = $1004
#ROCK_HDMI_FC_INVACTV0 = $1005
#ROCK_HDMI_FC_INVACTV1 = $1006
#ROCK_HDMI_FC_INVBLANK = $1007
#ROCK_HDMI_FC_HSYNCINDELAY0 = $1008
#ROCK_HDMI_FC_HSYNCINDELAY1 = $1009
#ROCK_HDMI_FC_HSYNCINWIDTH0 = $100A
#ROCK_HDMI_FC_HSYNCINWIDTH1 = $100B
#ROCK_HDMI_FC_VSYNCINDELAY = $100C
#ROCK_HDMI_FC_VSYNCINWIDTH = $100D
#ROCK_HDMI_FC_CTRLDUR = $1011
#ROCK_HDMI_FC_EXCTRLDUR = $1012
#ROCK_HDMI_FC_EXCTRLSPAC = $1013
#ROCK_HDMI_FC_CH0PREAM = $1014
#ROCK_HDMI_FC_CH1PREAM = $1015
#ROCK_HDMI_FC_CH2PREAM = $1016
#ROCK_HDMI_FC_STAT2 = $10D8
#ROCK_HDMI_VP_PR_CD = $0801
#ROCK_HDMI_VP_STUFF = $0802
#ROCK_HDMI_VP_REMAP = $0803
#ROCK_HDMI_VP_CONF = $0804
#ROCK_HDMI_MC_CLKDIS = $4001
#ROCK_HDMI_MC_SWRSTZ = $4002
#ROCK_HDMI_MC_FLOWCTRL = $4004
#ROCK_HDMI_MC_PHYRSTZ = $4005
#ROCK_HDMI_MC_HEACPHY_RST = $4007
#ROCK_HDMI_PHY_CONF0 = $3000
#ROCK_HDMI_PHY_TST0 = $3001
#ROCK_HDMI_PHY_STAT0 = $3004
#ROCK_HDMI_PHY_MASK0 = $3006
#ROCK_HDMI_PHY_I2CM_SLAVE_ADDR = $3020
#ROCK_HDMI_PHY_I2CM_ADDRESS = $3021
#ROCK_HDMI_PHY_I2CM_DATAO1 = $3022
#ROCK_HDMI_PHY_I2CM_DATAO0 = $3023
#ROCK_HDMI_PHY_I2CM_OPERATION = $3026
#ROCK_HDMI_PHY_I2CM_INT = $3027
#ROCK_HDMI_PHY_I2CM_CTLINT = $3028
#ROCK_HDMI_I2CM_SLAVE = $7E00
#ROCK_HDMI_I2CM_ADDRESS = $7E01
#ROCK_HDMI_I2CM_DATAI = $7E03
#ROCK_HDMI_I2CM_OPERATION = $7E04
#ROCK_HDMI_I2CM_INT = $7E05
#ROCK_HDMI_I2CM_CTLINT = $7E06
#ROCK_HDMI_I2CM_DIV = $7E07
#ROCK_HDMI_I2CM_SEGADDR = $7E08
#ROCK_HDMI_I2CM_SOFTRSTZ = $7E09
#ROCK_HDMI_I2CM_SEGPTR = $7E0A
#ROCK_HDMI_I2CM_SS_SCL_HCNT_0 = $7E0C
#ROCK_HDMI_I2CM_SS_SCL_HCNT_1 = $7E0B
#ROCK_HDMI_I2CM_SS_SCL_LCNT_0 = $7E0E
#ROCK_HDMI_I2CM_SS_SCL_LCNT_1 = $7E0D
#ROCK_HDMI_A_HDCPCFG0 = $5000

Global rock_hdmi_error.i
Global rock_hdmi_phy_lock_status.i
Global rock_hdmi_phy_powerdown_status.i
Global rock_hdmi_last_phy_i2c_status.i
Global Dim rock_hdmi_edid_staging.a[127]

Procedure.i RockHdmiRead8(offset.i)
  ProcedureReturn PeekL(#ROCK_HDMI_BASE + (offset << 2)) & $FF
EndProcedure

Procedure RockHdmiWrite8(offset.i,value.i)
  PokeL(#ROCK_HDMI_BASE + (offset << 2),value & $FF)
EndProcedure

Procedure RockHdmiUpdate8(offset.i,mask.i,value.i)
  Protected oldValue.i = RockHdmiRead8(offset)
  RockHdmiWrite8(offset,(oldValue & (~mask)) | (value & mask))
EndProcedure

Procedure.i RockHdmiHotplugPresent()
  ; RK3399 DesignWare PHY_STAT0.HPD is active high, bit 1 (DW offset 0x3004).
  ProcedureReturn Bool((RockHdmiRead8(#ROCK_HDMI_PHY_STAT0) & $02)<>0)
EndProcedure

Procedure RockHdmiInitController()
  ; Match U-Boot dw_hdmi_phy_init() and Linux v6.1 dw_hdmi_i2c_init().
  ; GIC/CPU interrupts remain masked: these are local polarity/mask registers.
  RockHdmiWrite8(#ROCK_HDMI_PHY_I2CM_INT,$08)
  RockHdmiWrite8(#ROCK_HDMI_PHY_I2CM_CTLINT,$88)
  RockHdmiWrite8(#ROCK_HDMI_PHY_MASK0,$FD) ; unmask HPD(bit=$02), mask other PHY IRQs
  RockHdmiWrite8(#ROCK_HDMI_IH_PHY_STAT0,$01) ; W1C HPD cause (IH bit 0)
  ; initialize_hdmi_mutes() and dw_hdmi_i2c_init(): CPU IRQ delivery remains
  ; disabled, while raw status remains available to the polling path.
  RockHdmiWrite8(#ROCK_HDMI_IH_MUTE,$03)
  RockHdmiWrite8(#ROCK_HDMI_IH_MUTE_FC_STAT2,$03)
  RockHdmiWrite8(#ROCK_HDMI_I2CM_DIV,$00) ; Standard-speed DDC, 100 kHz mode
  RockHdmiWrite8(#ROCK_HDMI_I2CM_SOFTRSTZ,$00) ; E-DDC I2C software reset
  RockHdmiWrite8(#ROCK_HDMI_I2CM_INT,$08)
  RockHdmiWrite8(#ROCK_HDMI_I2CM_CTLINT,$88)
  RockHdmiWrite8(#ROCK_HDMI_IH_I2CM_STAT0,$03) ; clear DONE and ERROR
  RockHdmiWrite8(#ROCK_HDMI_IH_MUTE_I2CM_STAT0,$03)
EndProcedure

Procedure.i RockHdmiPhyWaitPowerDown()
  Protected start.i=RockTimerTicks()
  Protected now.i
  Protected status.i
  Protected attempt.i
  ; Linux dw_hdmi_phy_power_off() gives Gen2 PHY lock five 2 ms intervals
  ; to deassert after TXPWRON clears, before PDDQ is asserted. This poll is
  ; deliberately feed-free so the external deadman still covers a bad bus.
  For attempt=0 To 4
    status=RockHdmiRead8(#ROCK_HDMI_PHY_STAT0)
    If (status & 1)=0
      rock_hdmi_phy_powerdown_status=status
      ProcedureReturn 1
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=(rock_timer_frequency/1000000)*10000 : Break : EndIf
    RockTimerWaitUs(2000)
  Next
  rock_hdmi_phy_powerdown_status=RockHdmiRead8(#ROCK_HDMI_PHY_STAT0)
  ProcedureReturn Bool((rock_hdmi_phy_powerdown_status & 1)=0)
EndProcedure

Procedure.i RockHdmiWaitDdcDone(timeoutMs.i)
  Protected start.i = RockTimerTicks()
  Protected now.i
  Protected attempt.i
  Protected status.i
  For attempt=0 To 9999999
    status=RockHdmiRead8(#ROCK_HDMI_IH_I2CM_STAT0) & 3
    If status<>0
      ; DONE and ERROR are write-one-to-clear. Never treat NACK/arbitration
      ; error as a completed read; the upstream Linux transfer path checks it.
      RockHdmiWrite8(#ROCK_HDMI_IH_I2CM_STAT0,status)
      If (status & 1)<>0 : ProcedureReturn -1 : EndIf
      If (status & 2)<>0 : ProcedureReturn 1 : EndIf
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=(rock_timer_frequency/1000)*timeoutMs : Break : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockHdmiReadEdid(pointer.i)
  Protected index.i
  Protected retry.i
  Protected result.i
  If pointer=0 Or rock_timer_frequency<>#ROCK_TIMER_FREQUENCY_EXPECTED
    rock_hdmi_error=50 : ProcedureReturn 0
  EndIf
  RockHdmiInitController()
  If RockHdmiHotplugPresent()=0 : rock_hdmi_error=51 : ProcedureReturn 0 : EndIf
  ; RK3399 U-Boot sets DDC high/low counts 0x7A/0x8D and standard mode.
  ; The node's reg-io-width=4 means each byte-register address uses offset<<2.
  ; Retry the complete base block at most twice after the initial pass. Each
  ; byte has the same 10 ms timeout used by the RK3399 U-Boot reader. Total
  ; worst-case wait is bounded; no partially received block is published.
  For retry=0 To 2
    ; Re-apply every field after a reset/retry; do not inherit a partial or
    ; loader-established DDC setup.
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SS_SCL_HCNT_1,$00)
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SS_SCL_HCNT_0,$7A)
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SS_SCL_LCNT_1,$00)
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SS_SCL_LCNT_0,$8D)
    RockHdmiWrite8(#ROCK_HDMI_I2CM_DIV,$00)
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SLAVE,$50)
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SEGADDR,$30)
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SEGPTR,$00)
    RockHdmiWrite8(#ROCK_HDMI_IH_I2CM_STAT0,$03)
    For index=0 To 127
      RockHdmiWrite8(#ROCK_HDMI_I2CM_ADDRESS,index)
      RockHdmiWrite8(#ROCK_HDMI_I2CM_OPERATION,1)
      result=RockHdmiWaitDdcDone(10)
      If result<>1
        rock_hdmi_error=52
        RockHdmiWrite8(#ROCK_HDMI_I2CM_SOFTRSTZ,$00)
        Break
      EndIf
      rock_hdmi_edid_staging[index]=RockHdmiRead8(#ROCK_HDMI_I2CM_DATAI)
      ; A DONE result plus a captured byte is verified DDC progress. Feed in
      ; batches, outside RockHdmiWaitDdcDone's status-poll loop.
      If (index & 15)=15 : RockWatchdogPet() : EndIf
    Next
    If index=128
      For index=0 To 127
        PokeA(pointer+index,rock_hdmi_edid_staging[index])
      Next
      rock_hdmi_error=0
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockHdmiWaitPhyI2c()
  Protected start.i = RockTimerTicks()
  Protected now.i
  Protected status.i
  Protected attempt.i
  ; Keep the reference's 1000 ms register-operation deadline, plus an
  ; instruction ceiling in case the architectural counter stops advancing.
  For attempt=0 To 9999999
    status=RockHdmiRead8(#ROCK_HDMI_IH_I2CMPHY_STAT0) & 3
    If status<>0
      RockHdmiWrite8(#ROCK_HDMI_IH_I2CMPHY_STAT0,status)
      rock_hdmi_last_phy_i2c_status=status
      ProcedureReturn Bool((status & 2)<>0 And (status & 1)=0)
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=rock_timer_frequency : Break : EndIf
  Next
  rock_hdmi_last_phy_i2c_status=0
  ProcedureReturn 0
EndProcedure

Procedure.i RockHdmiPhyI2cWrite(data.i,address.i)
  Protected completed.i
  RockHdmiWrite8(#ROCK_HDMI_IH_I2CMPHY_STAT0,$FF)
  RockHdmiWrite8(#ROCK_HDMI_PHY_I2CM_ADDRESS,address)
  RockHdmiWrite8(#ROCK_HDMI_PHY_I2CM_DATAO1,(data >> 8) & $FF)
  RockHdmiWrite8(#ROCK_HDMI_PHY_I2CM_DATAO0,data & $FF)
  RockHdmiWrite8(#ROCK_HDMI_PHY_I2CM_OPERATION,$10)
  completed=RockHdmiWaitPhyI2c()
  ; A successful DesignWare PHY-I2C completion is genuine forward progress.
  ; The wait loop itself remains feed-free so a stuck transaction resets.
  If completed<>0 : RockWatchdogPet() : EndIf
  ProcedureReturn completed
EndProcedure

Procedure.i RockHdmiSelectMpll(pixelHz.i)
  ; Values and ceiling thresholds are rockchip-u-boot-next-dev:
  ; drivers/video/rockchip/rk_hdmi.c rockchip_mpll_cfg[].
  If pixelHz<=40000000
    If RockHdmiPhyI2cWrite($00B3,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0000,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0018,$10)
  ElseIf pixelHz<=65000000
    If RockHdmiPhyI2cWrite($0072,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0001,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0028,$10)
  ElseIf pixelHz<=66000000
    If RockHdmiPhyI2cWrite($013E,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0003,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0038,$10)
  ElseIf pixelHz<=83500000
    If RockHdmiPhyI2cWrite($0072,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0001,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0028,$10)
  ElseIf pixelHz<=146250000
    If RockHdmiPhyI2cWrite($0051,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0002,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0038,$10)
  ElseIf pixelHz<=148500000
    If RockHdmiPhyI2cWrite($0051,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0003,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0000,$10)
  ElseIf pixelHz<=272000000 Or pixelHz<=340000000
    If RockHdmiPhyI2cWrite($0040,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0003,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0000,$10)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i RockHdmiSelectPhy(pixelHz.i)
  ; Values and ceiling thresholds are rockchip-u-boot-next-dev:
  ; drivers/video/rockchip/rk_hdmi.c rockchip_phy_config[].
  If pixelHz<=74250000
    If RockHdmiPhyI2cWrite($0004,$19)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($8009,$09)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0272,$0E)
  ElseIf pixelHz<=148500000
    If RockHdmiPhyI2cWrite($0004,$19)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($802B,$09)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($028D,$0E)
  ElseIf pixelHz<=297000000
    If RockHdmiPhyI2cWrite($0005,$19)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($8039,$09)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($028D,$0E)
  ElseIf pixelHz<=340000000
    If RockHdmiPhyI2cWrite($0000,$19)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($8039,$09)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($019D,$0E)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i RockHdmiPhyConfigure(pixelHz.i)
  Protected attempt.i
  Protected status.i
  Protected start.i
  Protected now.i
  Protected value.i
  For attempt=0 To 1
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$02,$02)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$01,$00)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$40,$00)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$80,$00)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$08,$00)
    ; The newer Rockchip/Linux sequence waits for TX_PHY_LOCK low between
    ; TXPWRON=0 and PDDQ=1. Preserve its non-fatal behavior: the raw result is
    ; retained for telemetry, then the bounded reset/configure pass proceeds.
    RockHdmiPhyWaitPowerDown()
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$10,$10)
    RockHdmiWrite8(#ROCK_HDMI_MC_PHYRSTZ,1)
    RockHdmiWrite8(#ROCK_HDMI_MC_PHYRSTZ,0)
    RockHdmiWrite8(#ROCK_HDMI_MC_HEACPHY_RST,1) ; HEACPHY_RST_ASSERT
    RockHdmiUpdate8(#ROCK_HDMI_PHY_TST0,$20,$20)
    RockHdmiWrite8(#ROCK_HDMI_PHY_I2CM_SLAVE_ADDR,$69)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_TST0,$20,$00)
    If RockHdmiSelectMpll(pixelHz)=0 : rock_hdmi_error=20 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0000,$13)=0 : rock_hdmi_error=21 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0006,$17)=0 : rock_hdmi_error=22 : ProcedureReturn 0 : EndIf
    If RockHdmiSelectPhy(pixelHz)=0 : rock_hdmi_error=23 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($8000,$05)=0 : rock_hdmi_error=24 : ProcedureReturn 0 : EndIf
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$80,$80)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$40,$00)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$40,$40)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$08,$08)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$10,$00)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$20,$20)
    start=RockTimerTicks()
    For value=0 To 999999
      status=RockHdmiRead8(#ROCK_HDMI_PHY_STAT0) & 1
      ; Linux v6.1 DesignWare Gen2 power-on waits for PHY_STAT0.TX_PHY_LOCK
      ; bit 0 asserted. The legacy U-Boot helper disagrees on the polarity.
      If status<>0
        rock_hdmi_phy_lock_status=RockHdmiRead8(#ROCK_HDMI_PHY_STAT0)
        Break
      EndIf
      now=RockTimerTicks()
      If now<start Or now-start>=(rock_timer_frequency/1000000)*2000*5 : Break : EndIf
      RockTimerWaitUs(2000)
    Next
    If status=0 : rock_hdmi_error=25 : ProcedureReturn 0 : EndIf
  Next
  rock_hdmi_phy_lock_status=RockHdmiRead8(#ROCK_HDMI_PHY_STAT0)
  ProcedureReturn 1
EndProcedure

Procedure RockHdmiComposeTiming()
  Protected hFront.i = rock_mode_hsync_start-rock_mode_width
  Protected hSync.i = rock_mode_hsync_end-rock_mode_hsync_start
  Protected hBack.i = rock_mode_htotal-rock_mode_hsync_end
  Protected vFront.i = rock_mode_vsync_start-rock_mode_height
  Protected vSync.i = rock_mode_vsync_end-rock_mode_vsync_start
  Protected vBack.i = rock_mode_vtotal-rock_mode_vsync_end
  Protected hBlank.i = hFront+hSync+hBack
  Protected vBlank.i = vFront+vSync+vBack
  Protected invid.i = $10 ; Data-enable polarity is active high.
  If rock_mode_vsync_positive<>0 : invid=invid | $40 : EndIf
  If rock_mode_hsync_positive<>0 : invid=invid | $20 : EndIf
  ; Base-block EDID alone does not prove an HDMI VSDB sink. Emit DVI-compatible
  ; RGB timing (no AVI/audio packets) until the caller supplies CTA parsing.
  invid=invid | $00 ; DVI mode, progressive, low-active blank (header value 0).
  RockHdmiWrite8(#ROCK_HDMI_FC_INVIDCONF,invid)
  RockHdmiWrite8(#ROCK_HDMI_FC_INHACTV1,rock_mode_width >> 8)
  RockHdmiWrite8(#ROCK_HDMI_FC_INHACTV0,rock_mode_width)
  RockHdmiWrite8(#ROCK_HDMI_FC_INVACTV1,rock_mode_height >> 8)
  RockHdmiWrite8(#ROCK_HDMI_FC_INVACTV0,rock_mode_height)
  RockHdmiWrite8(#ROCK_HDMI_FC_INHBLANK1,hBlank >> 8)
  RockHdmiWrite8(#ROCK_HDMI_FC_INHBLANK0,hBlank)
  RockHdmiWrite8(#ROCK_HDMI_FC_INVBLANK,vBlank)
  RockHdmiWrite8(#ROCK_HDMI_FC_HSYNCINDELAY1,hFront >> 8)
  RockHdmiWrite8(#ROCK_HDMI_FC_HSYNCINDELAY0,hFront)
  RockHdmiWrite8(#ROCK_HDMI_FC_VSYNCINDELAY,vFront)
  RockHdmiWrite8(#ROCK_HDMI_FC_HSYNCINWIDTH1,hSync >> 8)
  RockHdmiWrite8(#ROCK_HDMI_FC_HSYNCINWIDTH0,hSync)
  RockHdmiWrite8(#ROCK_HDMI_FC_VSYNCINWIDTH,vSync)
EndProcedure

Procedure RockHdmiVideoPacketize()
  Protected value.i
  RockHdmiWrite8(#ROCK_HDMI_VP_PR_CD,0)
  RockHdmiUpdate8(#ROCK_HDMI_VP_STUFF,$01,$01)
  RockHdmiUpdate8(#ROCK_HDMI_VP_CONF,$14,$04)
  RockHdmiUpdate8(#ROCK_HDMI_VP_STUFF,$20,$20)
  RockHdmiWrite8(#ROCK_HDMI_VP_REMAP,0)
  RockHdmiUpdate8(#ROCK_HDMI_VP_CONF,$68,$40)
  RockHdmiUpdate8(#ROCK_HDMI_VP_STUFF,$06,$06)
  RockHdmiUpdate8(#ROCK_HDMI_VP_CONF,$03,$03)
  value=RockHdmiRead8(#ROCK_HDMI_VP_CONF)
  If (value & $43)<>$43 : rock_hdmi_error=30 : EndIf
EndProcedure

Procedure RockHdmiStateTelemetry()
  If rock_uart_ready=0
    ProcedureReturn
  EndIf
  RockUartText("HDMI RAW PHY_STAT=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_PHY_STAT0))
  RockUartText(" PHY_CONF=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_PHY_CONF0))
  RockUartText(" PWRDN=") : RockDisplayHexByte(rock_hdmi_phy_powerdown_status)
  RockUartText(" CLKDIS=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_MC_CLKDIS))
  RockUartText(" SWRSTZ=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_MC_SWRSTZ))
  RockUartText(" FC_INVID=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_FC_INVIDCONF))
  RockUartText(" TX_INVID=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_TX_INVID0))
  RockUartText(" VP_CONF=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_VP_CONF))
  RockUartText(" HDCP0=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_A_HDCPCFG0))
  RockUartText(" IH_PHY=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_IH_PHY_STAT0))
  RockUartText(" IH_FC2=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_IH_FC_STAT2))
  RockUartText(" IH_PHYI2C=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_IH_I2CMPHY_STAT0))
  RockUartText(" FC_STAT2=") : RockDisplayHexByte(RockHdmiRead8(#ROCK_HDMI_FC_STAT2))
  RockUartByte(13) : RockUartByte(10)
EndProcedure

Procedure.i RockHdmiEnableSelected()
  Protected hFront.i
  Protected hSync.i
  Protected hBack.i
  Protected vFront.i
  Protected vSync.i
  Protected vBack.i
  Protected hBlank.i
  Protected vBlank.i
  Protected clkdis.i
  Protected value.i
  rock_hdmi_error=0
  If rock_mode_valid=0 Or rock_mode_width<=0 Or rock_mode_height<=0 Or rock_mode_pixel_hz<=0
    rock_hdmi_error=1 : ProcedureReturn 0
  EndIf
  If rock_mode_pixel_hz>340000000
    rock_hdmi_error=2 : ProcedureReturn 0
  EndIf
  hFront=rock_mode_hsync_start-rock_mode_width
  hSync=rock_mode_hsync_end-rock_mode_hsync_start
  hBack=rock_mode_htotal-rock_mode_hsync_end
  vFront=rock_mode_vsync_start-rock_mode_height
  vSync=rock_mode_vsync_end-rock_mode_vsync_start
  vBack=rock_mode_vtotal-rock_mode_vsync_end
  hBlank=hFront+hSync+hBack
  vBlank=vFront+vSync+vBack
  If hFront<=0 Or hSync<=0 Or hBack<0 Or vFront<=0 Or vSync<=0 Or vBack<0 Or hBlank>65535 Or vBlank>255
    rock_hdmi_error=3 : ProcedureReturn 0
  EndIf
  If (RockHdmiRead8(#ROCK_HDMI_PHY_STAT0) & 2)=0
    rock_hdmi_error=4 : ProcedureReturn 0
  EndIf
  RockHdmiInitController()
  ; Disable every DW subclock while establishing deterministic controller state.
  RockHdmiWrite8(#ROCK_HDMI_MC_CLKDIS,$7F)
  RockHdmiWrite8(#ROCK_HDMI_MC_FLOWCTRL,0)
  RockHdmiComposeTiming()
  If RockHdmiPhyConfigure(rock_mode_pixel_hz)=0 : ProcedureReturn 0 : EndIf
  RockHdmiWrite8(#ROCK_HDMI_FC_CTRLDUR,12)
  RockHdmiWrite8(#ROCK_HDMI_FC_EXCTRLDUR,32)
  RockHdmiWrite8(#ROCK_HDMI_FC_EXCTRLSPAC,1)
  RockHdmiWrite8(#ROCK_HDMI_FC_CH0PREAM,$0B)
  RockHdmiWrite8(#ROCK_HDMI_FC_CH1PREAM,$16)
  RockHdmiWrite8(#ROCK_HDMI_FC_CH2PREAM,$21)
  RockHdmiWrite8(#ROCK_HDMI_MC_FLOWCTRL,0)
  ; The base-block-only path deliberately emits DVI-compatible RGB. Match
  ; dw_hdmi_setup() by selecting DVI in both the frame composer and HDCP
  ; mode latch instead of depending on the controller reset value.
  RockHdmiUpdate8(#ROCK_HDMI_A_HDCPCFG0,$01,$00)
  RockHdmiVideoPacketize()
  If rock_hdmi_error<>0 : ProcedureReturn 0 : EndIf
  clkdis=$7F & (~$01)
  RockHdmiWrite8(#ROCK_HDMI_MC_CLKDIS,clkdis)
  clkdis=clkdis & (~$02)
  RockHdmiWrite8(#ROCK_HDMI_MC_CLKDIS,clkdis)
  RockHdmiWrite8(#ROCK_HDMI_TX_INVID0,1)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING,7)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+1,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+2,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+3,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+4,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+5,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+6,0)
  RockHdmiWrite8(#ROCK_HDMI_MC_SWRSTZ,$FD)
  value=RockHdmiRead8(#ROCK_HDMI_FC_INVIDCONF)
  RockHdmiWrite8(#ROCK_HDMI_FC_INVIDCONF,value)
  RockHdmiWrite8(#ROCK_HDMI_FC_INVIDCONF,value)
  RockHdmiWrite8(#ROCK_HDMI_FC_INVIDCONF,value)
  RockHdmiWrite8(#ROCK_HDMI_FC_INVIDCONF,value)
  If (RockHdmiRead8(#ROCK_HDMI_MC_CLKDIS) & 3)<>0
    rock_hdmi_error=31 : ProcedureReturn 0
  EndIf
  value=RockHdmiRead8(#ROCK_HDMI_PHY_STAT0)
  If (value & 3)<>3
    rock_hdmi_error=32 : ProcedureReturn 0
  EndIf
  value=RockHdmiRead8(#ROCK_HDMI_PHY_CONF0)
  If (value & $FB)<>$EA
    rock_hdmi_error=33 : ProcedureReturn 0
  EndIf
  If (RockHdmiRead8(#ROCK_HDMI_A_HDCPCFG0) & 1)<>0
    rock_hdmi_error=34 : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
