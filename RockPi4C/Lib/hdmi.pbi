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
#ROCK_HDMI_FC_DATAUTO3 = $10B7
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
#ROCK_HDMI_A_VIDPOLCFG = $5009
#ROCK_HDMI_CSC_CFG = $4100
#ROCK_HDMI_CSC_SCALE = $4101
#ROCK_HDMI_FC_AVICONF3 = $1017
#ROCK_HDMI_FC_AVICONF0 = $1019
#ROCK_HDMI_FC_AVICONF1 = $101A
#ROCK_HDMI_FC_AVICONF2 = $101B
#ROCK_HDMI_FC_AVIVID = $101C
#ROCK_HDMI_FC_AVIETB0 = $101D
#ROCK_HDMI_FC_AVISRB1 = $1024
#ROCK_HDMI_FC_PRCONF = $10E0

Global rock_hdmi_error.i
Global rock_hdmi_phy_lock_status.i
Global rock_hdmi_phy_powerdown_status.i
Global rock_hdmi_last_phy_i2c_status.i
Global Dim rock_hdmi_edid_staging.a[127]
Global Dim rock_hdmi_cta.a[127]
Global rock_hdmi_sink_hdmi.i

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

Procedure.i RockHdmiReadEdidBlock(pointer.i,block.i)
  Protected index.i
  Protected retry.i
  Protected result.i
  If pointer=0 Or block<0 Or block>4 Or rock_timer_frequency<>#ROCK_TIMER_FREQUENCY_EXPECTED
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
    RockHdmiWrite8(#ROCK_HDMI_I2CM_SEGPTR,block >> 1)
    RockHdmiWrite8(#ROCK_HDMI_IH_I2CM_STAT0,$03)
    For index=0 To 127
      RockHdmiWrite8(#ROCK_HDMI_I2CM_ADDRESS,((block & 1) << 7) | index)
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

Procedure.i RockHdmiReadEdid(pointer.i)
  ProcedureReturn RockHdmiReadEdidBlock(pointer,0)
EndProcedure

; Linux's drm_detect_hdmi_monitor() checks the CTA vendor-specific data
; block for HDMI OUI 00-0C-03 before choosing HDMI mode and an AVI packet.
Procedure.i RockHdmiDetectSink(pointer.i)
  Protected block.i
  Protected index.i
  Protected limit.i
  Protected header.i
  Protected size.i
  Protected checksum.i
  Protected extensionCount.i
  rock_hdmi_sink_hdmi=0
  extensionCount=PeekA(pointer+126) & 255
  If extensionCount>4 : extensionCount=4 : EndIf
  For block=1 To extensionCount
    If RockHdmiReadEdidBlock(@rock_hdmi_cta[0],block)=0 : Continue : EndIf
    checksum=0
    For index=0 To 127 : checksum=checksum+(rock_hdmi_cta[index] & 255) : Next
    If (checksum & 255)<>0 Or (rock_hdmi_cta[0] & 255)<>2 : Continue : EndIf
    limit=rock_hdmi_cta[2] & 255
    If limit<4 Or limit>127 : Continue : EndIf
    index=4
    While index<limit
      header=rock_hdmi_cta[index] & 255
      size=header & 31
      If index+size>=limit : Break : EndIf
      If (header >> 5)=3 And size>=3
        If (rock_hdmi_cta[index+1] & 255)=3 And (rock_hdmi_cta[index+2] & 255)=$0C And (rock_hdmi_cta[index+3] & 255)=0
          rock_hdmi_sink_hdmi=1
          ProcedureReturn 1
        EndIf
      EndIf
      index=index+size+1
    Wend
    RockWatchdogPet()
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
  ; The 147.2/184 MHz RGB8 rows match the MPLL table extracted from the
  ; released ROCK Pi 4C Debian 5.10.110-6-rockchip kernel binary.
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
  ElseIf pixelHz<=147200000
    If RockHdmiPhyI2cWrite($0051,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0002,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0038,$10)
  ElseIf pixelHz<=184000000
    If RockHdmiPhyI2cWrite($0051,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0002,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0000,$10)
  ElseIf pixelHz<=272000000 Or pixelHz<=340000000
    If RockHdmiPhyI2cWrite($0040,$06)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($0003,$15)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0000,$10)
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i RockHdmiSelectPhy(pixelHz.i)
  ; The 74.25/165/297 MHz rows match the PHY table extracted from the
  ; released ROCK Pi 4C Debian 5.10.110-6-rockchip kernel binary.
  If pixelHz<=74250000
    If RockHdmiPhyI2cWrite($0004,$19)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($8009,$09)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0272,$0E)
  ElseIf pixelHz<=165000000
    If RockHdmiPhyI2cWrite($0004,$19)=0 : ProcedureReturn 0 : EndIf
    If RockHdmiPhyI2cWrite($802B,$09)=0 : ProcedureReturn 0 : EndIf
    ProcedureReturn RockHdmiPhyI2cWrite($0209,$0E)
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
    ; The shipped Gen2 PHY path clears TXPWRON, waits for lock to drop, then
    ; asserts PDDQ. PDZ/ENTMDS are Gen1 controls and are never touched here.
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$08,$00)
    ; The newer Rockchip/Linux sequence waits for TX_PHY_LOCK low between
    ; TXPWRON=0 and PDDQ=1. Preserve its non-fatal behavior: the raw result is
    ; retained for telemetry, then the bounded reset/configure pass proceeds.
    RockHdmiPhyWaitPowerDown()
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$10,$10)
    ; The live CONFIG2_ID is F3 (Gen2 HDMI 2.0 PHY). Its entry in the
    ; installed Debian kernel's dw_hdmi_phys[] has has_svsret=1; assert this
    ; before the reset, as dw_hdmi_phy_init() does. A deadman payload proved
    ; this makes PHY_STAT0.TX_PHY_LOCK assert with PDZ/ENTMDS left off.
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$20,$20)
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
    ; The released ROCK Pi 4C Debian 5.10 HDMI binary ends its PHY table
    ; programming at VLEVCTRL (0x0E). Do not force CKCALCTRL.OVERRIDE here:
    ; that extra write belongs to a different DesignWare driver revision.
    ; Gen2 power-on in the released kernel writes TXPWRON=1, then PDDQ=0.
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$08,$08)
    RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$10,$00)
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
  ; The shipped DesignWare setup asserts HDCP_KEEPOUT even for unencrypted
  ; video. It preserves the control/data-island spacing some sinks require.
  Protected invid.i = $90 ; HDCP keepout plus active-high data enable.
  If rock_mode_vsync_positive<>0 : invid=invid | $40 : EndIf
  If rock_mode_hsync_positive<>0 : invid=invid | $20 : EndIf
  ; The released driver selects HDMI only after EDID advertises HDMI VSDB.
  If rock_hdmi_sink_hdmi<>0 : invid=invid | $08 : EndIf
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
  ; RGB888 takes the packetizer bypass path in the shipped ROCK Pi 4C
  ; Debian 5.10.110 driver: depth code zero, output selector BYPASS (3).
  ; Deeper color formats alone use the nonzero depth codes.
  RockHdmiWrite8(#ROCK_HDMI_VP_PR_CD,0)
  RockHdmiUpdate8(#ROCK_HDMI_FC_DATAUTO3,$04,0)
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

Procedure RockHdmiConfigureAvi()
  Protected aspect.i
  Protected vic.i
  Protected address.i
  ; The released dw-hdmi setup writes the AVI packet before packetizer,
  ; CSC, sampler, and HDCP polarity setup. The framebuffer is full-range RGB.
  aspect=0
  If rock_mode_width*9=rock_mode_height*16 : aspect=$20 : EndIf
  If rock_mode_width*3=rock_mode_height*4 : aspect=$10 : EndIf
  vic=0
  If rock_mode_width=1920 And rock_mode_height=1080 And rock_mode_pixel_hz=148500000 And rock_mode_htotal=2200 And rock_mode_vtotal=1125
    vic=16
  EndIf
  RockHdmiWrite8(#ROCK_HDMI_FC_AVICONF0,$40)
  RockHdmiWrite8(#ROCK_HDMI_FC_AVICONF1,aspect | $08)
  RockHdmiWrite8(#ROCK_HDMI_FC_AVICONF2,$08)
  RockHdmiWrite8(#ROCK_HDMI_FC_AVIVID,vic)
  RockHdmiWrite8(#ROCK_HDMI_FC_PRCONF,$10)
  RockHdmiWrite8(#ROCK_HDMI_FC_AVICONF3,0)
  For address=#ROCK_HDMI_FC_AVIETB0 To #ROCK_HDMI_FC_AVISRB1
    RockHdmiWrite8(address,0)
  Next
EndProcedure

Procedure RockHdmiVideoCsc()
  Protected index.i
  Protected a.i
  Protected b.i
  Protected c.i
  ; RGB8 input and RGB8 output: no interpolation or conversion. The Linux
  ; driver still writes identity coefficients and scale 1 before sampling.
  RockHdmiWrite8(#ROCK_HDMI_CSC_CFG,0)
  RockHdmiUpdate8(#ROCK_HDMI_CSC_SCALE,$F0,0)
  For index=0 To 3
    a=0 : b=0 : c=0
    If index=0 : a=$2000 : EndIf
    If index=1 : b=$2000 : EndIf
    If index=2 : c=$2000 : EndIf
    RockHdmiWrite8($4103+index*2,a & 255)
    RockHdmiWrite8($4102+index*2,a >> 8)
    RockHdmiWrite8($410B+index*2,b & 255)
    RockHdmiWrite8($410A+index*2,b >> 8)
    RockHdmiWrite8($4113+index*2,c & 255)
    RockHdmiWrite8($4112+index*2,c >> 8)
  Next
  RockHdmiUpdate8(#ROCK_HDMI_CSC_SCALE,$03,1)
EndProcedure

Procedure RockHdmiVideoSample()
  RockHdmiWrite8(#ROCK_HDMI_TX_INVID0,1)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING,7)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+1,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+2,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+3,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+4,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+5,0)
  RockHdmiWrite8(#ROCK_HDMI_TX_INSTUFFING+6,0)
EndProcedure

Procedure RockHdmiVideoHdcp()
  Protected mode.i=0
  Protected polarity.i=$10
  If rock_hdmi_sink_hdmi<>0 : mode=1 : EndIf
  If rock_mode_vsync_positive<>0 : polarity=polarity | $08 : EndIf
  If rock_mode_hsync_positive<>0 : polarity=polarity | $02 : EndIf
  ; The installed 5.10 binary writes all three VIDPOLCFG polarity bits in
  ; one masked update, after TX_INVID0. For 1080p positive sync this is 0x1A.
  RockHdmiUpdate8(#ROCK_HDMI_A_VIDPOLCFG,$1A,polarity)
  RockHdmiUpdate8(#ROCK_HDMI_A_HDCPCFG0,$01,mode)
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
  ; Match the released driver's dw_hdmi_setup() order. Controller/DDC setup
  ; already ran before EDID; this mode pass starts with overflow masked.
  RockHdmiWrite8(#ROCK_HDMI_IH_MUTE_FC_STAT2,$03)
  RockHdmiWrite8(#ROCK_HDMI_MC_CLKDIS,$7F)
  RockHdmiComposeTiming()
  If RockHdmiPhyConfigure(rock_mode_pixel_hz)=0 : ProcedureReturn 0 : EndIf
  ; dw_hdmi_enable_video_path(): control intervals, then pixel and TMDS
  ; clocks, then the explicit RGB CSC bypass.
  RockHdmiWrite8(#ROCK_HDMI_FC_CTRLDUR,12)
  RockHdmiWrite8(#ROCK_HDMI_FC_EXCTRLDUR,32)
  RockHdmiWrite8(#ROCK_HDMI_FC_EXCTRLSPAC,1)
  RockHdmiWrite8(#ROCK_HDMI_FC_CH0PREAM,$0B)
  RockHdmiWrite8(#ROCK_HDMI_FC_CH1PREAM,$16)
  RockHdmiWrite8(#ROCK_HDMI_FC_CH2PREAM,$21)
  clkdis=$7F & (~$01)
  RockHdmiWrite8(#ROCK_HDMI_MC_CLKDIS,clkdis)
  clkdis=clkdis & (~$02)
  RockHdmiWrite8(#ROCK_HDMI_MC_CLKDIS,clkdis)
  RockHdmiWrite8(#ROCK_HDMI_MC_CLKDIS,clkdis)
  RockHdmiWrite8(#ROCK_HDMI_MC_FLOWCTRL,0)
  If rock_hdmi_sink_hdmi<>0 : RockHdmiConfigureAvi() : EndIf
  RockHdmiVideoPacketize()
  If rock_hdmi_error<>0 : ProcedureReturn 0 : EndIf
  RockHdmiVideoCsc()
  RockHdmiVideoSample()
  RockHdmiVideoHdcp()
  ; The released setup clears a frame-composer overflow only after every
  ; video block is configured, with a TMDS reset and repeated FC write.
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
  If (value & $3B)<>$2A
    rock_hdmi_error=33 : ProcedureReturn 0
  EndIf
  If (RockHdmiRead8(#ROCK_HDMI_A_HDCPCFG0) & 1)<>Bool(rock_hdmi_sink_hdmi<>0)
    rock_hdmi_error=34 : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure
