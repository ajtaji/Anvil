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
  rate = vco/post1/post2
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

Procedure.i RockCruVpll65()
  Protected con2.i
  Protected rate.i
  ; VPLL is the display-owned pixel parent. Radxa's VPLL-specific 65 MHz
  ; table entry is refdiv=1, fbdiv=113, postdiv1=7, postdiv2=6 and
  ; frac=0xC00000. Follow its slow/powerdown/dividers/fraction/powerup/
  ; lock/normal sequence. CON2's 24-bit fraction is an ordinary RMW field.
  RockCruField($CC,$0300,$0000)
  RockCruField($CC,$0001,$0001)
  RockCruField($C0,$0FFF,$0071)
  RockCruField($C4,$773F,$6701)
  con2 = RockCruRead($C8)
  RockCruWrite($C8,(con2 & $FF000000) | $00C00000)
  RockCruField($CC,$0008,$0000)
  RockCruField($CC,$0001,$0000)
  If RockCruWait($C8,$80000000,$80000000)=0
    rock_cru_error=63 : ProcedureReturn 0
  EndIf
  RockCruField($CC,$0300,$0100)
  rate = RockCruPllRate($C0,0,63)
  If rate <> 65000000 : rock_cru_error=65 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruDisplayClocks()
  Protected tcpDivider.i
  Protected dpDivider.i
  Protected spdifDivider.i
  Protected aclkDivider.i
  Protected hclkDivider.i
  Protected tcpRate.i
  Protected spdifRate.i
  Protected aclkRate.i
  Protected hclkRate.i
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
  aclkDivider = RockCruCeilingDivider(rock_cru_gpll_rate,400000000)
  If tcpDivider=0 Or dpDivider=0 Or spdifDivider=0 Or aclkDivider=0
    rock_cru_error=51 : ProcedureReturn 0
  EndIf
  tcpRate = rock_cru_gpll_rate/tcpDivider
  rock_cru_dp_core_rate = rock_cru_gpll_rate/dpDivider
  spdifRate = rock_cru_gpll_rate/spdifDivider
  aclkRate = rock_cru_gpll_rate/aclkDivider
  hclkDivider = RockCruCeilingDivider(aclkRate,100000000)
  If hclkDivider=0 : rock_cru_error=51 : ProcedureReturn 0 : EndIf
  hclkRate = aclkRate/hclkDivider
  If (rock_cru_dp_core_rate % 1000000) <> 0
    rock_cru_error=52 : ProcedureReturn 0
  EndIf
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
  RockCruField(#ROCK_CRU_CLKSEL+$C0,$1FDF,$0080 | (aclkDivider-1) | ((hclkDivider-1) << 8))
  RockCruGate(10,10,1)
  RockCruGate(10,11,1)
  ; A Rockchip fractional divider requires denominator >= 20*numerator;
  ; neither 65/594 nor 13/160 meets that precision contract. Own the
  ; dedicated VPLL at the pinned exact 65 MHz rate and select its DIV /1.
  RockCruGate(10,13,0)
  If RockCruVpll65()=0 : ProcedureReturn 0 : EndIf
  RockCruField(#ROCK_CRU_CLKSEL+$C8,$0BFF,$0000)
  RockCruGate(10,13,1)
  ; Leaf and NoC clocks for the little VOP.
  RockCruGate(28,7,1)
  RockCruGate(28,6,1)
  RockCruGate(28,5,1)
  RockCruGate(28,4,1)
  ; APB access to VIO GRF and Cadence DP control.
  RockCruGate(29,12,1)
  RockCruGate(29,7,1)
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruDisplayPower()
  ; Parent-to-child order: VIO -> HDCP and VIO -> VO -> VOPL; TCPD0 is
  ; independent. Direct power bits exist for VIO/HDCP/VO/TCPD0. VOPL is an
  ; idle-only child.
  If RockPmuPowerOn(14,53)=0 : ProcedureReturn 0 : EndIf
  If RockPmuIdleRelease(17,54)=0 : ProcedureReturn 0 : EndIf
  ; The pinned DTS supplies HCLK_HDCP and PCLK_HDCP, and the live-proven
  ; loader owner also ungates its ACLK_HDCP leaf. All three transition clocks
  ; must run before requesting HDCP power or releasing its bus idle.
  RockCruGate(11,3,1)
  RockCruGate(11,10,1)
  RockCruGate(11,12,1)
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
  ; Hold the VOP before its display-owned VPLL and DCLK are changed.
  RockCruReset(275,1)
  RockCruReset(279,1)
  RockCruReset(281,1)
  If RockCruDisplayClocks() = 0 : ProcedureReturn 0 : EndIf
  If RockCruDisplayPower() = 0 : ProcedureReturn 0 : EndIf
  ; Hold each display block while its driver establishes a known state.
  RockCruReset(#ROCK_RESET_UPHY0_PIPE_L00,1)
  RockCruReset(#ROCK_RESET_UPHY0,1)
  RockCruReset(#ROCK_RESET_P_UPHY0_TCPHY,1)
  RockCruReset(253,1)
  RockCruReset(259,1)
  RockCruReset(328,1)
  RockCruReset(330,1)
  RockTimerWaitUs(1)
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruCadenceRelease()
  If RockCruReset(328,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(253,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(330,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(259,0)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruVopRelease()
  If RockCruReset(275,0)=0 : ProcedureReturn 0 : EndIf
  If RockCruReset(279,0)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure
