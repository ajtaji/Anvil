; Minimal Rock Pi 4C PMU-I2C0/RK808 rail preflight for direct EL3 boot.
; Register layout, clocks and pinmux follow the shipped RK3399 DTS, RK3399
; clock binding/driver and U-Boot rk_i2c.c + rk8xx regulators. The routine
; validates rail voltage selectors before any enable write, and RMWs only
; RK808 LDO2/LDO7 enable bits. LDO4 (SDIO) is read-only telemetry.

#ROCK_PMUCRU = $FF750000
#ROCK_PMUCRU_CLKSEL2 = $FF750088
#ROCK_PMUCRU_CLKGATE0 = $FF750100
#ROCK_PMUCRU_CLKGATE1 = $FF750104
#ROCK_PMUGRF_GPIO1B_IOMUX = $FF320014
#ROCK_PMUGRF_GPIO1C_IOMUX = $FF320018
#ROCK_PMU_I2C0 = $FF3C0000
#ROCK_RK808_ADDR = $1B
#ROCK_RK808_ID_MSB = $17
#ROCK_RK808_ID_LSB = $18
#ROCK_RK808_LDO_EN = $24
#ROCK_RK808_LDO2_VSEL = $3D
#ROCK_RK808_LDO4_VSEL = $41
#ROCK_RK808_LDO7_VSEL = $47

Global rock_pmic_error.i
Global rock_pmic_ppll_rate.i
Global rock_pmic_i2c_rate.i
Global rock_pmic_ppll_con0.i
Global rock_pmic_ppll_con1.i
Global rock_pmic_ppll_con2.i
Global rock_pmic_ppll_con3.i
Global rock_pmic_ppll_mode.i
Global rock_pmic_id_msb.i
Global rock_pmic_id_lsb.i
Global rock_pmic_ldo_en_before.i
Global rock_pmic_ldo_en_after.i
Global rock_pmic_ldo2_vsel.i
Global rock_pmic_ldo4_vsel.i
Global rock_pmic_ldo7_vsel.i

Procedure.i RockPmicRead(offset.i)
  ProcedureReturn PeekL(#ROCK_PMUCRU+offset) & $FFFFFFFF
EndProcedure

Procedure RockPmicField(offset.i,mask.i,value.i)
  PokeL(offset,(mask << 16) | (value & mask))
  ASM
    dsb sy
  ENDASM
EndProcedure

Procedure.i RockPmicWaitIpd(mask.i)
  Protected start.i=RockTimerTicks()
  Protected now.i
  Protected n.i
  Protected status.i
  For n=0 To 1000000
    status=PeekL(#ROCK_PMU_I2C0+$1C) & mask
    If status<>0
      PokeL(#ROCK_PMU_I2C0+$1C,status) ; IPD is write-one-to-clear.
      ProcedureReturn status
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=rock_timer_frequency/10 : Break : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockPmicI2cStart()
  PokeL(#ROCK_PMU_I2C0+$1C,$7F)
  PokeL(#ROCK_PMU_I2C0+$00,$09) ; EN | START.
  PokeL(#ROCK_PMU_I2C0+$18,$10) ; START interrupt enable.
  ProcedureReturn RockPmicWaitIpd($10)
EndProcedure

Procedure.i RockPmicI2cStop()
  Protected stopped.i
  PokeL(#ROCK_PMU_I2C0+$1C,$7F)
  PokeL(#ROCK_PMU_I2C0+$00,$11) ; EN | STOP.
  PokeL(#ROCK_PMU_I2C0+$18,$20)
  stopped=RockPmicWaitIpd($20)
  PokeL(#ROCK_PMU_I2C0+$18,0)
  PokeL(#ROCK_PMU_I2C0+$1C,$7F)
  PokeL(#ROCK_PMU_I2C0+$00,0)
  ProcedureReturn Bool(stopped<>0)
EndProcedure

Procedure.i RockPmicI2cReadReg(reg.i,*result)
  Protected status.i
  If RockPmicI2cStart()=0 : PokeL(#ROCK_PMU_I2C0+$00,0) : ProcedureReturn 0 : EndIf
  PokeL(#ROCK_PMU_I2C0+$08,$01000000 | ((#ROCK_RK808_ADDR << 1) | 1))
  PokeL(#ROCK_PMU_I2C0+$0C,$01000000 | (reg & $FF))
  PokeL(#ROCK_PMU_I2C0+$00,$23) ; EN | TRX | LASTACK.
  PokeL(#ROCK_PMU_I2C0+$14,1)
  PokeL(#ROCK_PMU_I2C0+$18,$48) ; MBRF + NAK.
  status=RockPmicWaitIpd($48)
  If status=0
    RockPmicI2cStop() : ProcedureReturn 0
  EndIf
  If (status & $40)<>0
    RockPmicI2cStop() : ProcedureReturn 0
  EndIf
  PokeI(*result,PeekL(#ROCK_PMU_I2C0+$200) & $FF)
  If RockPmicI2cStop()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockPmicI2cWriteReg(reg.i,value.i)
  Protected status.i
  If RockPmicI2cStart()=0 : PokeL(#ROCK_PMU_I2C0+$00,0) : ProcedureReturn 0 : EndIf
  ; TX FIFO bytes are little-endian packed by byte lane: SLA+W, register, data.
  PokeL(#ROCK_PMU_I2C0+$100,(#ROCK_RK808_ADDR << 1) | ((reg & $FF) << 8) | ((value & $FF) << 16))
  PokeL(#ROCK_PMU_I2C0+$00,$01) ; EN | TX.
  PokeL(#ROCK_PMU_I2C0+$10,3)
  PokeL(#ROCK_PMU_I2C0+$18,$44) ; MBTF + NAK.
  status=RockPmicWaitIpd($44)
  If status=0
    RockPmicI2cStop() : ProcedureReturn 0
  EndIf
  If (status & $40)<>0
    RockPmicI2cStop() : ProcedureReturn 0
  EndIf
  If RockPmicI2cStop()=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockPmicPllRate()
  Protected fb.i
  Protected ref.i
  Protected post1.i
  Protected post2.i
  Protected fraction.i
  Protected scaled.i

  rock_pmic_ppll_con0=RockPmicRead(0)
  rock_pmic_ppll_con1=RockPmicRead(4)
  rock_pmic_ppll_con2=RockPmicRead(8)
  rock_pmic_ppll_con3=RockPmicRead(12)
  rock_pmic_ppll_mode=(rock_pmic_ppll_con3 >> 8) & 3

  ; RK3399's PLL mux has three real parents: slow mode is xin24m, normal
  ; mode is the PLL output, and deep-slow mode is xin32k. The Rockchip clock
  ; driver models those exact parents. The direct-SD miniloader is allowed to
  ; leave PPLL in slow mode, so derive I2C0 from its live 24 MHz parent instead
  ; of falsely requiring a programmed/locked PLL before PMIC access.
  If rock_pmic_ppll_mode=0 : ProcedureReturn 24000000 : EndIf
  If rock_pmic_ppll_mode<>1 : ProcedureReturn 0 : EndIf
  If (rock_pmic_ppll_con2 & $80000000)=0 Or (rock_pmic_ppll_con3 & 1)<>0
    ProcedureReturn 0
  EndIf
  fb=rock_pmic_ppll_con0 & $FFF
  ref=rock_pmic_ppll_con1 & $3F
  post1=(rock_pmic_ppll_con1 >> 8) & 7
  post2=(rock_pmic_ppll_con1 >> 12) & 7
  If (rock_pmic_ppll_con3 & 8)=0 : fraction=rock_pmic_ppll_con2 & $FFFFFF : EndIf
  If fb<16 Or ref=0 Or post1=0 Or post2=0 : ProcedureReturn 0 : EndIf
  scaled=fb*16777216+fraction
  ProcedureReturn (24000000*scaled/ref)/(16777216*post1*post2)
EndProcedure

Procedure.i RockPmicI2cSetup()
  Protected pll.i
  Protected divider.i
  Protected actual.i
  Protected i2cDiv.i
  Protected divl.i
  Protected divh.i
  Protected packed.i
  ; PPLL feeds SCLK_I2C0_PMU. Read its live normal-mode configuration and
  ; derive a legal rate, including the hardware-defined 24 MHz slow parent,
  ; rather than inheriting a firmware assumption.
  pll=RockPmicPllRate()
  If pll<16000000 Or pll>3200000000
    rock_pmic_error=1
    If rock_uart_ready<>0
      RockUartText("RK3399 PPLL REFUSED CON=")
      RockDisplayHexLong(rock_pmic_ppll_con0) : RockUartByte(58)
      RockDisplayHexLong(rock_pmic_ppll_con1) : RockUartByte(58)
      RockDisplayHexLong(rock_pmic_ppll_con2) : RockUartByte(58)
      RockDisplayHexLong(rock_pmic_ppll_con3)
      RockUartText(" MODE=") : RockDisplayHexByte(rock_pmic_ppll_mode)
      RockUartByte(13) : RockUartByte(10)
    EndIf
    ProcedureReturn 0
  EndIf
  divider=(pll+199999999)/200000000
  If divider<1 Or divider>128 : rock_pmic_error=2 : ProcedureReturn 0 : EndIf
  actual=pll/divider
  If actual<=0 Or actual>200000000 : rock_pmic_error=3 : ProcedureReturn 0 : EndIf
  ; PMU CLKSEL_CON2[6:0] is SCLK_I2C0_PMU divisor minus one.
  RockPmicField(#ROCK_PMUCRU_CLKSEL2,$007F,divider-1)
  ; PMU gate 0 bit 9 is SCLK_I2C0; gate 1 bit 7 is PCLK_I2C0.
  RockPmicField(#ROCK_PMUCRU_CLKGATE0,$0200,0)
  RockPmicField(#ROCK_PMUCRU_CLKGATE1,$0080,0)
  ; PMUGRF GPIO1B7=I2C0 SDA func2; GPIO1C0=I2C0 SCL func2.
  RockPmicField(#ROCK_PMUGRF_GPIO1B_IOMUX,$C000,$8000)
  RockPmicField(#ROCK_PMUGRF_GPIO1C_IOMUX,$0003,$0002)
  i2cDiv=(actual+799999)/800000-2
  If i2cDiv<0 Or i2cDiv>65534 : rock_pmic_error=4 : ProcedureReturn 0 : EndIf
  divl=i2cDiv/2
  divh=(i2cDiv+1)/2
  packed=(divl & $FFFF) | ((divh & $FFFF) << 16)
  PokeL(#ROCK_PMU_I2C0+$04,packed)
  ASM
    dsb sy
  ENDASM
  If ((PeekL(#ROCK_PMUCRU_CLKSEL2) & $7F)<>(divider-1)) Or ((PeekL(#ROCK_PMUCRU_CLKGATE0) & $0200)<>0) Or ((PeekL(#ROCK_PMUCRU_CLKGATE1) & $0080)<>0) Or ((PeekL(#ROCK_PMU_I2C0+$04) & $FFFFFFFF)<>packed) Or ((PeekL(#ROCK_PMUGRF_GPIO1B_IOMUX) >> 14) & 3)<>2 Or (PeekL(#ROCK_PMUGRF_GPIO1C_IOMUX) & 3)<>2
    rock_pmic_error=5 : ProcedureReturn 0
  EndIf
  rock_pmic_ppll_rate=pll
  rock_pmic_i2c_rate=actual
  ProcedureReturn 1
EndProcedure

Procedure.i RockPmicHdmiRailsEnsure()
  Protected value.i
  Protected newEnable.i
  rock_pmic_error=0
  If RockPmicI2cSetup()=0 : ProcedureReturn 0 : EndIf
  If RockPmicI2cReadReg(#ROCK_RK808_ID_MSB,@rock_pmic_id_msb)=0 Or RockPmicI2cReadReg(#ROCK_RK808_ID_LSB,@rock_pmic_id_lsb)=0
    rock_pmic_error=10 : ProcedureReturn 0
  EndIf
  ; RK808 hardware variant ID is 0 (low version nibble is ignored).
  If (((rock_pmic_id_msb << 8) | rock_pmic_id_lsb) & $FFF0)<>0
    rock_pmic_error=11 : ProcedureReturn 0
  EndIf
  If RockPmicI2cReadReg(#ROCK_RK808_LDO_EN,@rock_pmic_ldo_en_before)=0 Or RockPmicI2cReadReg(#ROCK_RK808_LDO2_VSEL,@rock_pmic_ldo2_vsel)=0 Or RockPmicI2cReadReg(#ROCK_RK808_LDO4_VSEL,@rock_pmic_ldo4_vsel)=0 Or RockPmicI2cReadReg(#ROCK_RK808_LDO7_VSEL,@rock_pmic_ldo7_vsel)=0
    rock_pmic_error=12 : ProcedureReturn 0
  EndIf
  ; Shipped DTS fixes LDO2=1.8V, LDO7=0.9V, LDO4(SDIO)=3.0V.
  ; RK808 selectors are LDO2 0x00 (1.8V), LDO7 0x01 (0.9V), and
  ; LDO4 0x0C (3.0V). The direct-SD loader leaves LDO7 at selector 0x00
  ; (0.8V) while it is disabled. Program the DTS voltage before enabling it.
  ; LDO4 is read-only telemetry and is never changed by HDMI setup.
  If rock_uart_ready<>0
    RockUartText("RK808 PRE ID=") : RockDisplayHexByte(rock_pmic_id_msb) : RockDisplayHexByte(rock_pmic_id_lsb)
    RockUartText(" EN=") : RockDisplayHexByte(rock_pmic_ldo_en_before)
    RockUartText(" L2=") : RockDisplayHexByte(rock_pmic_ldo2_vsel)
    RockUartText(" L4=") : RockDisplayHexByte(rock_pmic_ldo4_vsel)
    RockUartText(" L7=") : RockDisplayHexByte(rock_pmic_ldo7_vsel)
    RockUartText(" PPLL=") : RockDisplayDecimal(rock_pmic_ppll_rate)
    RockUartText(" I2C=") : RockDisplayDecimal(rock_pmic_i2c_rate) : RockUartByte(13) : RockUartByte(10)
  EndIf
  ; LDO4 is reported for SD diagnostics but must not gate HDMI activation.
  ; LDO2 is already at its only accepted value. Bring disabled LDO7 from the
  ; measured miniloader default to the board DTS value, then read it back.
  If (rock_pmic_ldo2_vsel & $1F)<>0
    rock_pmic_error=13 : ProcedureReturn 0
  EndIf
  If (rock_pmic_ldo7_vsel & $1F)<>1
    If RockPmicI2cWriteReg(#ROCK_RK808_LDO7_VSEL,(rock_pmic_ldo7_vsel & $E0) | 1)=0
      rock_pmic_error=17 : ProcedureReturn 0
    EndIf
    If RockPmicI2cReadReg(#ROCK_RK808_LDO7_VSEL,@rock_pmic_ldo7_vsel)=0 Or (rock_pmic_ldo7_vsel & $1F)<>1
      rock_pmic_error=18 : ProcedureReturn 0
    EndIf
  EndIf
  newEnable=rock_pmic_ldo_en_before | $42 ; LDO2 bit 1, LDO7 bit 6.
  If newEnable<>rock_pmic_ldo_en_before
    If RockPmicI2cWriteReg(#ROCK_RK808_LDO_EN,newEnable)=0
      rock_pmic_error=14 : ProcedureReturn 0
    EndIf
  EndIf
  If RockPmicI2cReadReg(#ROCK_RK808_LDO_EN,@rock_pmic_ldo_en_after)=0
    rock_pmic_error=15 : ProcedureReturn 0
  EndIf
  If (rock_pmic_ldo_en_after & $42)<>$42
    rock_pmic_error=16 : ProcedureReturn 0
  EndIf
  If rock_uart_ready<>0
    RockUartText("RK808 POST EN=") : RockDisplayHexByte(rock_pmic_ldo_en_after)
    RockUartText(" ERR=") : RockDisplayHexByte(rock_pmic_error) : RockUartByte(13) : RockUartByte(10)
  EndIf
  ProcedureReturn 1
EndProcedure
