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

Global rock_cru_error.i

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

Procedure.i RockCruRequirePll(offset.i, expected.i, errorCode.i)
  Protected con0.i = RockCruRead(offset)
  Protected con1.i = RockCruRead(offset+4)
  Protected con2.i = RockCruRead(offset+8)
  Protected con3.i = RockCruRead(offset+12)
  Protected fb.i = con0 & $FFF
  Protected ref.i = con1 & $3F
  Protected post1.i = (con1 >> 8) & 7
  Protected post2.i = (con1 >> 12) & 7
  Protected rate.i
  ; U-Boot's integer-mode rate formula is valid only for a locked PLL in
  ; normal mode with DSM disabled.
  If (con2 & $80000000)=0 Or ((con3 >> 8) & 3)<>1 Or (con3 & 8)=0
    rock_cru_error=errorCode : ProcedureReturn 0
  EndIf
  If ref = 0 Or post1 = 0 Or post2 = 0 : rock_cru_error=errorCode+1 : ProcedureReturn 0 : EndIf
  rate = (24000000/ref)*fb/post1/post2
  If rate <> expected : rock_cru_error=errorCode+2 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruRequireDisplayPlls()
  ; CPLL is 384 MHz and GPLL is 594 MHz in the exact mainline U-Boot handoff.
  ; Read the live dividers rather than silently relying on that loader policy:
  ; every display divider below is derived from one of these two rates.
  If RockCruRequirePll($60,384000000,47)=0 : ProcedureReturn 0 : EndIf
  If RockCruRequirePll($80,594000000,50)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruDisplayClocks()
  If RockCruRequireDisplayPlls() = 0 : ProcedureReturn 0 : EndIf
  ; TCPHY0 reference: xin24m / 1; TCPHY0 core: GPLL / 12 = 49.5 MHz.
  RockCruField(#ROCK_CRU_CLKSEL+$100,$9FDF,$00CB)
  RockCruGate(13,4,1)
  RockCruGate(13,5,1)
  ; Cadence core: GPLL / 6 = 99 MHz.
  RockCruField(#ROCK_CRU_CLKSEL+$B8,$00DF,$0085)
  RockCruGate(11,8,1)
  ; SPDIF_REC_DPTX: GPLL / 3 = 198 MHz. Required by the DT clock contract.
  RockCruField(#ROCK_CRU_CLKSEL+$80,$9F00,$8200)
  RockCruGate(10,6,1)
  ; VOPL assigned clocks request 400/100 MHz. The exact live 384 MHz CPLL
  ; supplies the closest integer rates: ACLK /1 = 384, HCLK /4 = 96 MHz.
  RockCruField(#ROCK_CRU_CLKSEL+$C0,$1FDF,$0340)
  RockCruGate(10,10,1)
  RockCruGate(10,11,1)
  ; VOPL pixel clock: GPLL DIV output /1, then exact 65/594 fractional
  ; division. CLKSEL_CON107 carries numerator:denominator in 16-bit halves.
  RockCruField(#ROCK_CRU_CLKSEL+$C8,$0BFF,$0200)
  RockCruWrite(#ROCK_CRU_CLKSEL+$1AC,($41 << 16) | $252)
  RockCruField(#ROCK_CRU_CLKSEL+$C8,$0800,$0800)
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
  If RockPmuPowerOn(14,53)=0 Or RockPmuIdleRelease(17,54)=0 : ProcedureReturn 0 : EndIf
  If RockPmuPowerOn(24,56)=0 Or RockPmuIdleRelease(11,57)=0 : ProcedureReturn 0 : EndIf
  If RockPmuPowerOn(20,59)=0 : ProcedureReturn 0 : EndIf
  If RockPmuIdleRelease(8,60)=0 : ProcedureReturn 0 : EndIf
  If RockPmuPowerOn(8,62)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockCruDisplayPrepare()
  rock_cru_error = 0
  RockDpPowerPinctrl()
  If RockCruDisplayClocks() = 0 : ProcedureReturn 0 : EndIf
  If RockCruDisplayPower() = 0 : ProcedureReturn 0 : EndIf
  ; Hold each display block while its driver establishes a known state.
  RockCruReset(148,1)
  RockCruReset(149,1)
  RockCruReset(332,1)
  RockCruReset(253,1)
  RockCruReset(259,1)
  RockCruReset(328,1)
  RockCruReset(330,1)
  RockCruReset(275,1)
  RockCruReset(279,1)
  RockCruReset(281,1)
  RockTimerWaitUs(1)
  If RockCruReset(332,0)=0 : rock_cru_error=64 : ProcedureReturn 0 : EndIf
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
