; RK3399 display clock, reset and power-domain ownership.
; Exact fields are from the RK3399 clock/reset bindings and Radxa's pinned
; release-4.4-rockpi4 clock/power drivers. CRU writes use Rockchip's upper
; halfword mask; PMU power and bus-idle registers are ordinary read/modify/
; write registers. Domains are only powered on and are never powered off.

#ROCK_CRU = $FF760000
#ROCK_PMU = $FF310000
#ROCK_GRF = $FF770000
#ROCK_PMUGRF = $FF320000
#ROCK_GPIO1 = $FF730000
#ROCK_CRU_CLKSEL = $100
#ROCK_CRU_CLKGATE = $300
#ROCK_CRU_SOFTRST = $400
#ROCK_PMU_PWRDN_CON = $14
#ROCK_PMU_PWRDN_ST = $18
#ROCK_PMU_BUS_IDLE_REQ = $60
#ROCK_PMU_BUS_IDLE_ST = $64
#ROCK_PMU_BUS_IDLE_ACK = $68
#ROCK_RESET_UPHY0_PIPE_L00 = 148
#ROCK_RESET_UPHY0 = 149
#ROCK_RESET_P_UPHY0_TCPHY = 332

Global rock_cru_error.i
Global rock_cru_gpll_rate.i
Global rock_cru_dp_core_rate.i
Global rock_cru_vio_aclk_rate.i
Global rock_cru_vio_pclk_rate.i
Global rock_cru_hdcp_aclk_rate.i
Global rock_cru_hdcp_hclk_rate.i
Global rock_cru_hdcp_pclk_rate.i
Global rock_cru_vop_aclk_rate.i
Global rock_cru_vop_hclk_rate.i

Procedure.i RockCruRead(offset.i)
  ProcedureReturn PeekL(#ROCK_CRU+offset) & $FFFFFFFF
EndProcedure

Procedure RockCruWrite(offset.i, value.i)
  PokeL(#ROCK_CRU+offset,value & $FFFFFFFF)
EndProcedure

Procedure RockCruField(offset.i, mask.i, value.i)
  RockCruWrite(offset,(mask << 16) | (value & mask))
EndProcedure

Procedure RockCruGate(bank.i, bit.i, enable.i)
  Protected value.i = 1 << (bit+16)
  If enable = 0 : value = value | (1 << bit) : EndIf
  RockCruWrite(#ROCK_CRU_CLKGATE+bank*4,value)
EndProcedure

Procedure.i RockCruReset(id.i, asserted.i)
  Protected bank.i
  Protected bit.i
  Protected value.i
  If id < 0 Or id >= 336 : ProcedureReturn 0 : EndIf
  bank = id >> 4
  bit = id & 15
  value = 1 << (bit+16)
  If asserted <> 0 : value = value | (1 << bit) : EndIf
  RockCruWrite(#ROCK_CRU_SOFTRST+bank*4,value)
  ASM
    dsb sy
  ENDASM
  ProcedureReturn 1
EndProcedure

Procedure.i RockPmuWait(offset.i, mask.i, wanted.i)
  Protected start.i = RockTimerTicks()
  Protected now.i
  Protected attempt.i
  For attempt = 0 To 1000000
    If ((PeekL(#ROCK_PMU+offset) & $FFFFFFFF) & mask) = wanted : ProcedureReturn 1 : EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= rock_timer_frequency/100 : Break : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockPmuPowerOn(bit.i, errorCode.i)
  Protected mask.i = 1 << bit
  Protected value.i
  If ((PeekL(#ROCK_PMU+#ROCK_PMU_PWRDN_ST) & $FFFFFFFF) & mask) = 0 : ProcedureReturn 1 : EndIf
  value = PeekL(#ROCK_PMU+#ROCK_PMU_PWRDN_CON) & $FFFFFFFF
  PokeL(#ROCK_PMU+#ROCK_PMU_PWRDN_CON,value & ~mask)
  ASM
    dsb sy
  ENDASM
  If RockPmuWait(#ROCK_PMU_PWRDN_ST,mask,0) = 0
    rock_cru_error=errorCode : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockPmuIdleRelease(bit.i, errorCode.i)
  Protected mask.i = 1 << bit
  Protected value.i = PeekL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_REQ) & $FFFFFFFF
  PokeL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_REQ,value & ~mask)
  ASM
    dsb sy
  ENDASM
  If RockPmuWait(#ROCK_PMU_BUS_IDLE_ACK,mask,0) = 0
    rock_cru_error=errorCode : ProcedureReturn 0
  EndIf
  If RockPmuWait(#ROCK_PMU_BUS_IDLE_ST,mask,0) = 0
    rock_cru_error=errorCode+1 : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure RockDpPowerPinctrl()
  Protected direction.i
  ; Exact Radxa dp_pwr pin: GPIO1_D0, not GPIO1_C0. The board DTS asks for
  ; GPIO function plus pull-up and does not drive the line. Preserve that
  ; electrical contract: force input, then apply the PMUGRF mux/pull fields.
  direction=PeekL(#ROCK_GPIO1+$04) & $FFFFFFFF
  PokeL(#ROCK_GPIO1+$04,direction & $FEFFFFFF)
  PokeL(#ROCK_PMUGRF+$1C,$00030000)
  PokeL(#ROCK_PMUGRF+$5C,$00030001)
  ASM
    dsb sy
  ENDASM
EndProcedure

Procedure.i RockCruPllRate(offset.i, integerOnly.i, errorCode.i)
  Protected con0.i = RockCruRead(offset)
  Protected con1.i = RockCruRead(offset+4)
  Protected con2.i = RockCruRead(offset+8)
  Protected con3.i = RockCruRead(offset+12)
  Protected fb.i = con0 & $FFF
  Protected ref.i = con1 & $3F
  Protected post1.i = (con1 >> 8) & 7
  Protected post2.i = (con1 >> 12) & 7
  Protected fraction.i
  Protected scaled.i
  Protected vco.i
  Protected rate.i
  ; The RK3399 PLL formula used by the pinned Rockchip clock drivers is valid
  ; only for a powered, locked PLL in normal mode. GPLL must additionally be
  ; integer-only; the pinned VPLL table deliberately uses its 24-bit fraction.
  If (con2 & $80000000)=0 Or ((con3 >> 8) & 3)<>1 Or (con3 & 1)<>0
    rock_cru_error=errorCode : ProcedureReturn 0
  EndIf
  If integerOnly<>0 And (con3 & 8)=0 : rock_cru_error=errorCode : ProcedureReturn 0 : EndIf
  If fb < 16 Or fb > 3200 Or ref = 0 Or post1 = 0 Or post2 = 0
    rock_cru_error=errorCode+1 : ProcedureReturn 0
  EndIf
  If (con3 & 8)=0 : fraction=con2 & $FFFFFF : EndIf
  scaled = fb*16777216+fraction
  vco = (24000000*scaled/ref)/16777216
  rate = (24000000*scaled/ref)/(16777216*post1*post2)
  ; These are the RK3399 PLL limits enforced by the pinned U-Boot driver.
  If vco < 800000000 Or vco > 3200000000 Or rate < 16000000 Or rate > 3200000000
    rock_cru_error=errorCode+2 : ProcedureReturn 0
  EndIf
  ProcedureReturn rate
EndProcedure

Procedure.i RockCruCeilingDivider(parent.i, target.i)
  Protected divider.i
  If parent <= 0 Or target <= 0 : ProcedureReturn 0 : EndIf
  divider = (parent+target-1)/target
  If divider < 1 Or divider > 32 : ProcedureReturn 0 : EndIf
  ProcedureReturn divider
EndProcedure

Procedure.i RockCruWait(offset.i, mask.i, wanted.i)
  Protected start.i = RockTimerTicks()
  Protected now.i
  Protected attempt.i
  For attempt = 0 To 1000000
    If (RockCruRead(offset) & mask) = wanted : ProcedureReturn 1 : EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= rock_timer_frequency/100 : Break : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockCruExpect(offset.i, mask.i, wanted.i, errorCode.i)
  ; CRU clock selections and gates are ordinary readable state even though
  ; their writes use Rockchip's upper-halfword mask.  Do not carry on into a
  ; power-domain transition when a parent, divider, or leaf gate did not take.
  ASM
    dsb sy
  ENDASM
  If (RockCruRead(offset) & mask) <> (wanted & mask)
    rock_cru_error=errorCode
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruVpllSet(pixelHz.i)
  Protected con2.i
  Protected rate.i
  If RockModeVpllPlan(pixelHz)=0 : rock_cru_error=66 : ProcedureReturn 0 : EndIf
  ; Follow the pinned driver's slow/powerdown/dividers/fraction/powerup/
  ; lock/normal sequence. CON2's 24-bit fraction is an ordinary RMW field.
  RockCruField($CC,$0300,$0000)
  RockCruField($CC,$0001,$0001)
  RockCruField($C0,$0FFF,rock_mode_vpll_fb)
  RockCruField($C4,$773F,rock_mode_vpll_ref | (rock_mode_vpll_post1 << 8) | (rock_mode_vpll_post2 << 12))
  con2 = RockCruRead($C8)
  RockCruWrite($C8,(con2 & $FF000000) | rock_mode_vpll_frac)
  RockCruField($CC,$0008,rock_mode_vpll_dsmpd << 3)
  RockCruField($CC,$0001,$0000)
  If RockCruWait($C8,$80000000,$80000000)=0
    rock_cru_error=63 : ProcedureReturn 0
  EndIf
  RockCruField($CC,$0300,$0100)
  rate = RockCruPllRate($C0,0,63)
  If rate <> rock_mode_vpll_actual_hz Or rate>pixelHz Or pixelHz-rate>1
    rock_cru_error=65 : ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruVpll65()
  ; The established 1024x768 bootstrap remains fixed until EDID selection.
  ProcedureReturn RockCruVpllSet(65000000)
EndProcedure

Procedure.i RockCruVpllMode()
  ; RockModeSelect publishes validity last. Refuse an unselected mode and
  ; leave DCLK gated if reprogramming or exact readback fails.
  If rock_mode_valid=0 : rock_cru_error=66 : ProcedureReturn 0 : EndIf
  RockCruGate(10,13,0)
  If RockCruVpllSet(rock_mode_pixel_hz)=0 : ProcedureReturn 0 : EndIf
  RockCruField(#ROCK_CRU_CLKSEL+$C8,$0BFF,$0000)
  RockCruGate(10,13,1)
  If RockCruExpect(#ROCK_CRU_CLKSEL+$C8,$0BFF,$0000,73)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKGATE+10*4,$2000,0,74)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruDisplayClocks()
  Protected tcpDivider.i
  Protected dpDivider.i
  Protected spdifDivider.i
  Protected vioAclkDivider.i
  Protected vioPclkDivider.i
  Protected hdcpAclkDivider.i
  Protected hdcpHclkDivider.i
  Protected hdcpPclkDivider.i
  Protected vopAclkDivider.i
  Protected vopHclkDivider.i
  Protected clock42.i
  Protected clock43.i
  Protected clock48.i
  rock_cru_gpll_rate = RockCruPllRate($80,1,47)
  If rock_cru_gpll_rate = 0 : ProcedureReturn 0 : EndIf
  ; Accept the 800 MHz silicon-observed stock handoff and the 594 MHz pinned
  ; reference configuration. Derive their leaves below, but refuse any other
  ; parent rather than inventing an unverified tolerance.
  If rock_cru_gpll_rate <> 594000000 And rock_cru_gpll_rate <> 800000000
    rock_cru_error=50 : ProcedureReturn 0
  EndIf
  ; Derive display-owned leaves from the live GPLL. Ceiling division keeps
  ; every clock at or below its DT target and supports both proven handoffs:
  ; private U-Boot's 594 MHz GPLL and stock Android U-Boot's 800 MHz GPLL.
  tcpDivider = RockCruCeilingDivider(rock_cru_gpll_rate,50000000)
  dpDivider = RockCruCeilingDivider(rock_cru_gpll_rate,100000000)
  spdifDivider = RockCruCeilingDivider(rock_cru_gpll_rate,200000000)
  vioAclkDivider = RockCruCeilingDivider(rock_cru_gpll_rate,400000000)
  hdcpAclkDivider = RockCruCeilingDivider(rock_cru_gpll_rate,400000000)
  vopAclkDivider = RockCruCeilingDivider(rock_cru_gpll_rate,400000000)
  If tcpDivider=0 Or dpDivider=0 Or spdifDivider=0 Or vioAclkDivider=0 Or hdcpAclkDivider=0 Or vopAclkDivider=0
    rock_cru_error=51 : ProcedureReturn 0
  EndIf
  rock_cru_dp_core_rate = rock_cru_gpll_rate/dpDivider
  rock_cru_vio_aclk_rate = rock_cru_gpll_rate/vioAclkDivider
  rock_cru_hdcp_aclk_rate = rock_cru_gpll_rate/hdcpAclkDivider
  rock_cru_vop_aclk_rate = rock_cru_gpll_rate/vopAclkDivider
  ; The pinned RK3399 DT assigns 400 MHz to ACLK_VIO/ACLK_HDCP/ACLK_VOP1
  ; and 200 MHz to HCLK_VOP1.  HCLK_HDCP and both APB children are derived
  ; locally and bounded to 200/100 MHz.  Explicitly owning these dividers is
  ; essential: leaving them at an arbitrary bootloader value made the
  ; supposedly identical display path depend on which image ran first.
  vioPclkDivider = RockCruCeilingDivider(rock_cru_vio_aclk_rate,100000000)
  hdcpHclkDivider = RockCruCeilingDivider(rock_cru_hdcp_aclk_rate,200000000)
  hdcpPclkDivider = RockCruCeilingDivider(rock_cru_hdcp_aclk_rate,100000000)
  vopHclkDivider = RockCruCeilingDivider(rock_cru_vop_aclk_rate,200000000)
  If vioPclkDivider=0 Or hdcpHclkDivider=0 Or hdcpPclkDivider=0 Or vopHclkDivider=0
    rock_cru_error=51 : ProcedureReturn 0
  EndIf
  rock_cru_vio_pclk_rate = rock_cru_vio_aclk_rate/vioPclkDivider
  rock_cru_hdcp_hclk_rate = rock_cru_hdcp_aclk_rate/hdcpHclkDivider
  rock_cru_hdcp_pclk_rate = rock_cru_hdcp_aclk_rate/hdcpPclkDivider
  rock_cru_vop_hclk_rate = rock_cru_vop_aclk_rate/vopHclkDivider
  If (rock_cru_dp_core_rate % 1000000) <> 0
    rock_cru_error=52 : ProcedureReturn 0
  EndIf
  ; VIO and HDCP are separate roots in CLKSEL42.  Both select GPLL (mux 1)
  ; at no more than the DT's 400 MHz assignment.  CLKSEL43 owns every child
  ; divider used during the VIO/HDCP power transitions and by the DP block.
  clock42 = $0040 | (vioAclkDivider-1) | $4000 | ((hdcpAclkDivider-1) << 8)
  clock43 = (vioPclkDivider-1) | ((hdcpHclkDivider-1) << 5) | ((hdcpPclkDivider-1) << 10)
  RockCruField(#ROCK_CRU_CLKSEL+$A8,$DFDF,clock42)
  RockCruField(#ROCK_CRU_CLKSEL+$AC,$7FFF,clock43)
  ; TCPHY0 reference: xin24m / 1; core: live GPLL at no more than 50 MHz.
  RockCruField(#ROCK_CRU_CLKSEL+$100,$9FDF,$00C0 | (tcpDivider-1))
  RockCruGate(13,4,1)
  RockCruGate(13,5,1)
  ; Linux keeps both UPHY0 APB leaves alive implicitly. Bare Anvil owns them:
  ; PCLK_UPHY0_TCPHY_G is the direct register interface and TCPD_G its peer.
  RockCruGate(21,5,1)
  RockCruGate(21,6,1)
  ; Cadence core: live GPLL at no more than 100 MHz.
  RockCruField(#ROCK_CRU_CLKSEL+$B8,$00DF,$0080 | (dpDivider-1))
  RockCruGate(11,8,1)
  ; SPDIF_REC_DPTX: live GPLL at no more than its 200 MHz DT target.
  RockCruField(#ROCK_CRU_CLKSEL+$80,$9F00,$8000 | ((spdifDivider-1) << 8))
  RockCruGate(10,6,1)
  ; Use GPLL for VOPL too: stock U-Boot leaves CPLL in slow/bypass mode.
  clock48 = $0080 | (vopAclkDivider-1) | ((vopHclkDivider-1) << 8)
  RockCruField(#ROCK_CRU_CLKSEL+$C0,$1FDF,clock48)
  RockCruGate(10,10,1)
  RockCruGate(10,11,1)
  ; A Rockchip fractional divider requires denominator >= 20*numerator;
  ; neither 65/594 nor 13/160 meets that precision contract. Own the
  ; dedicated VPLL at the pinned exact 65 MHz rate and select its DIV /1.
  RockCruGate(10,13,0)
  If RockCruVpll65()=0 : ProcedureReturn 0 : EndIf
  RockCruField(#ROCK_CRU_CLKSEL+$C8,$0BFF,$0000)
  RockCruGate(10,13,1)
  ; Parent and transition clocks needed by Linux's VIO and HDCP genpd
  ; callbacks.  ACLK_HDCP itself has no gate on RK3399; gate 11 bit12 is
  ; reserved and must never be used as a substitute.
  RockCruGate(11,0,1)
  RockCruGate(11,1,1)
  RockCruGate(11,3,1)
  RockCruGate(11,10,1)
  RockCruGate(29,0,1)
  RockCruGate(29,4,1)
  RockCruGate(29,5,1)
  RockCruGate(29,3,1)
  ; Leaf and NoC clocks for the little VOP.
  RockCruGate(28,7,1)
  RockCruGate(28,6,1)
  RockCruGate(28,5,1)
  RockCruGate(28,4,1)
  ; APB access to VIO GRF and Cadence DP control.
  RockCruGate(29,12,1)
  RockCruGate(29,7,1)
  ; Refuse the transition before power is touched if any complete clock
  ; contract field failed to latch.  A gate bit is zero when enabled.
  If RockCruExpect(#ROCK_CRU_CLKSEL+$A8,$DFDF,clock42,67)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKSEL+$AC,$7FFF,clock43,68)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKSEL+$100,$9FDF,$00C0 | (tcpDivider-1),69)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKSEL+$B8,$00DF,$0080 | (dpDivider-1),70)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKSEL+$80,$9F00,$8000 | ((spdifDivider-1) << 8),71)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKSEL+$C0,$1FDF,clock48,72)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKSEL+$C8,$0BFF,$0000,73)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKGATE+10*4,$2C40,0,74)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKGATE+11*4,$050B,0,75)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKGATE+13*4,$0030,0,76)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKGATE+21*4,$0060,0,77)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKGATE+28*4,$00F0,0,78)=0 : ProcedureReturn 0 : EndIf
  If RockCruExpect(#ROCK_CRU_CLKGATE+29*4,$10B9,0,79)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruDisplayPower()
  ; Parent-to-child order: VIO -> HDCP and VIO -> VO -> VOPL; TCPD0 is
  ; independent. Direct power bits exist for VIO/HDCP/VO/TCPD0. VOPL is an
  ; idle-only child.
  If RockPmuPowerOn(14,53)=0 : ProcedureReturn 0 : EndIf
  If RockPmuIdleRelease(17,54)=0 : ProcedureReturn 0 : EndIf
  ; RockCruDisplayClocks has already enabled the real ACLK/HCLK/PCLK HDCP
  ; roots and their NoC paths.  Linux enables those same three genpd clocks
  ; before changing PWRDN_CON; there is no ACLK_HDCP gate at bank11 bit12.
  If RockPmuPowerOn(24,56)=0 : ProcedureReturn 0 : EndIf
  If RockPmuIdleRelease(11,57)=0 : ProcedureReturn 0 : EndIf
  If RockPmuPowerOn(20,59)=0 : ProcedureReturn 0 : EndIf
  If RockPmuIdleRelease(8,60)=0 : ProcedureReturn 0 : EndIf
  If RockPmuPowerOn(8,62)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruDisplayPrepare()
  rock_cru_error = 0
  RockDpPowerPinctrl()
  ; First establish a quiescent boundary for every block this display owner
  ; will configure.  Resets are CRU signals and do not depend on the target
  ; power domains being awake.  Parent clocks and transition clocks are
  ; configured next; only then are the domains brought up parent-to-child.
  RockCruReset(275,1)
  RockCruReset(279,1)
  RockCruReset(281,1)
  RockCruReset(#ROCK_RESET_UPHY0_PIPE_L00,1)
  RockCruReset(#ROCK_RESET_UPHY0,1)
  RockCruReset(#ROCK_RESET_P_UPHY0_TCPHY,1)
  RockCruReset(253,1)
  RockCruReset(259,1)
  RockCruReset(328,1)
  RockCruReset(330,1)
  If RockCruDisplayClocks() = 0 : ProcedureReturn 0 : EndIf
  If RockCruDisplayPower() = 0 : ProcedureReturn 0 : EndIf
  RockTimerWaitUs(1)
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruCadenceRelease()
  ; Exact shipped cdn_dp_clk_enable order for the transmitter is core, DPTX,
  ; APB.  SOURCE_AIF_CAR's internal AIF/SPDIF_CDR resets are Cadence-local
  ; and do not replace SRST_DPTX_SPDIF_REC. Preserve Anvil's established
  ; external SPDIF reset state after the video-owned trio is released.
  If RockCruReset(253,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(328,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(330,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(259,0)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruVopRelease()
  If RockCruReset(275,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(279,0)=0 : ProcedureReturn 0 : EndIf
  ; Linux enables the VOP clocks and powers the domain before programming the
  ; CRTC.  Release AXI, AHB, then DCLK here so the later Linux-ordered facade
  ; can write the timing/window shadow registers and issue its first CFG_DONE.
  If RockCruReset(281,0)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
