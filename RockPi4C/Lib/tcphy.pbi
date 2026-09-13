; RK3399 TCPHY0 DisplayPort/USB3 split-mode initialization for the original
; ROCK Pi 4C v1.2 MiniDP connector. The exact board virtual-PD contract is
; init-mode=DP plus init-ss=1: two DP lanes on physical lanes 2/3 and USB3 on
; 0/1, normal orientation. Values and ordering are from the pinned Radxa
; release-4.4-rockpi4 TCPHY driver; no eDP or HDMI register is substituted.

#ROCK_TCPHY0 = $FF7C0000
#TCPHY_CMN_PLL0_VCOCAL_INIT = $210
#TCPHY_CMN_PLL0_VCOCAL_ITER = $214
#TCPHY_CMN_PLL0_INTDIV = $250
#TCPHY_CMN_PLL0_FRACDIV = $254
#TCPHY_CMN_PLL0_HIGH_THR = $258
#TCPHY_CMN_PLL0_DSM_DIAG = $25C
#TCPHY_CMN_PLL0_SS_CTRL1 = $260
#TCPHY_CMN_PLL0_SS_CTRL2 = $264
#TCPHY_CMN_PLL1_VCOCAL_START = $284
#TCPHY_CMN_PLL1_VCOCAL_INIT = $290
#TCPHY_CMN_PLL1_VCOCAL_ITER = $294
#TCPHY_CMN_PLL1_INTDIV = $2D0
#TCPHY_CMN_PLL1_FRACDIV = $2D4
#TCPHY_CMN_PLL1_HIGH_THR = $2D8
#TCPHY_CMN_PLL1_DSM_DIAG = $2DC
#TCPHY_CMN_PLL1_SS_CTRL1 = $2E0
#TCPHY_CMN_PLL1_SS_CTRL2 = $2E4
#TCPHY_CMN_PLLSM1_USER = $DC
#TCPHY_CMN_TXPUCAL = $380
#TCPHY_CMN_TXPDCAL = $3C0
#TCPHY_CMN_TXPU_ADJ = $420
#TCPHY_CMN_TXPD_ADJ = $430
#TCPHY_PLL0_FBH = $700
#TCPHY_PLL0_FBL = $704
#TCPHY_PLL0_OVRD = $708
#TCPHY_PLL0_V2I = $714
#TCPHY_PLL0_CP = $718
#TCPHY_PLL0_LF = $71C
#TCPHY_PLL1_FBH = $740
#TCPHY_PLL1_FBL = $744
#TCPHY_PLL1_OVRD = $748
#TCPHY_PLL1_V2I = $754
#TCPHY_PLL1_CP = $758
#TCPHY_PLL1_LF = $75C
#TCPHY_PLL1_PTAT1 = $760
#TCPHY_PLL1_PTAT2 = $764
#TCPHY_PLL1_INCLK = $768
#TCPHY_HSCLK_SEL = $780
#TCPHY_PMA_LANE_CFG = $30000
#TCPHY_DP_MODE_CTL = $30020
#TCPHY_DP_CLK_CTL = $30024
#TCPHY_DP_TX_CTL = $31020
#TCPHY_PMA_CMN_CTRL1 = $32000
#TCPHY_TX_ANA1 = $14080
#TCPHY_TX_ANA2 = $14084
#TCPHY_TX_COEFF = $14088
#TCPHY_TX_DIG2 = $14090
#TCPHY_TX_CYA = $14094
#TCPHY_TX_ANA3 = $14098
#TCPHY_TX_ANA4 = $1409C
#TCPHY_TX_ANA5 = $140A4

Global rock_tcphy_error.i

Procedure.i RockTcRead(offset.i)
  ProcedureReturn PeekL(#ROCK_TCPHY0+offset) & $FFFFFFFF
EndProcedure

Procedure RockTcWrite(offset.i, value.i)
  PokeL(#ROCK_TCPHY0+offset,value & $FFFFFFFF)
EndProcedure

Procedure.i RockTcLaneOffset(base.i, lane.i)
  ProcedureReturn (base | (lane << 9)) << 2
EndProcedure

Procedure RockTcUsbPll()
  RockTcWrite(#TCPHY_CMN_PLL0_VCOCAL_INIT,$F0)
  RockTcWrite(#TCPHY_CMN_PLL0_VCOCAL_ITER,$18)
  RockTcWrite(#TCPHY_CMN_PLL0_INTDIV,$D0)
  RockTcWrite(#TCPHY_CMN_PLL0_FRACDIV,$4A4A)
  RockTcWrite(#TCPHY_CMN_PLL0_HIGH_THR,$34)
  RockTcWrite(#TCPHY_CMN_PLL0_SS_CTRL1,$1EE)
  RockTcWrite(#TCPHY_CMN_PLL0_SS_CTRL2,$7F03)
  RockTcWrite(#TCPHY_CMN_PLL0_DSM_DIAG,$20)
  RockTcWrite(#TCPHY_PLL0_OVRD,0)
  RockTcWrite(#TCPHY_PLL0_FBH,0)
  RockTcWrite(#TCPHY_PLL0_FBL,0)
  RockTcWrite(#TCPHY_PLL0_V2I,7)
  RockTcWrite(#TCPHY_PLL0_CP,$45)
  RockTcWrite(#TCPHY_PLL0_LF,8)
EndProcedure

Procedure RockTcDpRbrPll()
  Protected value.i = RockTcRead(#TCPHY_HSCLK_SEL)
  RockTcWrite(#TCPHY_DP_CLK_CTL,$2405)
  RockTcWrite(#TCPHY_HSCLK_SEL,(value & $FFFFFFCC) | $30)
  RockTcWrite(#TCPHY_CMN_PLL1_VCOCAL_INIT,$F0)
  RockTcWrite(#TCPHY_CMN_PLL1_VCOCAL_ITER,$18)
  RockTcWrite(#TCPHY_CMN_PLL1_VCOCAL_START,$30B9)
  RockTcWrite(#TCPHY_CMN_PLL1_INTDIV,$86)
  RockTcWrite(#TCPHY_CMN_PLL1_FRACDIV,$F915)
  RockTcWrite(#TCPHY_CMN_PLL1_HIGH_THR,$22)
  RockTcWrite(#TCPHY_CMN_PLL1_SS_CTRL1,$140)
  RockTcWrite(#TCPHY_CMN_PLL1_SS_CTRL2,$7F03)
  RockTcWrite(#TCPHY_CMN_PLL1_DSM_DIAG,$20)
  RockTcWrite(#TCPHY_CMN_PLLSM1_USER,0)
  RockTcWrite(#TCPHY_PLL1_OVRD,0)
  RockTcWrite(#TCPHY_PLL1_FBH,0)
  RockTcWrite(#TCPHY_PLL1_FBL,0)
  RockTcWrite(#TCPHY_PLL1_V2I,6)
  RockTcWrite(#TCPHY_PLL1_CP,$45)
  RockTcWrite(#TCPHY_PLL1_LF,8)
  RockTcWrite(#TCPHY_PLL1_PTAT1,$100)
  RockTcWrite(#TCPHY_PLL1_PTAT2,7)
  RockTcWrite(#TCPHY_PLL1_INCLK,1)
EndProcedure

Procedure RockTcCommon24M()
  Protected lane.i
  Protected value.i
  RockTcWrite(#TCPHY_PMA_CMN_CTRL1,$830)
  For lane = 0 To 3
    RockTcWrite(RockTcLaneOffset($40F2,lane),$90)
    RockTcWrite(RockTcLaneOffset($4122,lane),$960)
    RockTcWrite(RockTcLaneOffset($4123,lane),$30)
  Next
  value = RockTcRead(#TCPHY_HSCLK_SEL)
  RockTcWrite(#TCPHY_HSCLK_SEL,(value & $FFFFFFCC) | $30)
EndProcedure

Procedure RockTcUsbTxLane(lane.i)
  RockTcWrite(RockTcLaneOffset($4100,lane),$7799)
  RockTcWrite(RockTcLaneOffset($4101,lane),$7798)
  RockTcWrite(RockTcLaneOffset($4102,lane),$5098)
  RockTcWrite(RockTcLaneOffset($4103,lane),$5098)
  RockTcWrite(RockTcLaneOffset($4050,lane),0)
  RockTcWrite(RockTcLaneOffset($40E8,lane),$BF)
EndProcedure

Procedure RockTcUsbRxLane(lane.i)
  RockTcWrite(RockTcLaneOffset($8000,lane),$A6FD)
  RockTcWrite(RockTcLaneOffset($8001,lane),$A6FD)
  RockTcWrite(RockTcLaneOffset($8002,lane),$A410)
  RockTcWrite(RockTcLaneOffset($8003,lane),$2410)
  RockTcWrite(RockTcLaneOffset($8006,lane),$23FF)
  RockTcWrite(RockTcLaneOffset($8090,lane),$13)
  RockTcWrite(RockTcLaneOffset($81BB,lane),$3E7)
  RockTcWrite(RockTcLaneOffset($81DC,lane),$1004)
  RockTcWrite(RockTcLaneOffset($8007,lane),$2010)
  RockTcWrite(RockTcLaneOffset($40E8,lane),$FB)
EndProcedure

Procedure RockTcDpLane(lane.i, swing.i, emphasis.i)
  Protected value.i
  Protected magnitude.i
  Protected post.i
  If swing = 0
    If emphasis = 0 : magnitude=$2A : post=0 : EndIf
    If emphasis = 1 : magnitude=$1F : post=$15 : EndIf
    If emphasis = 2 : magnitude=$14 : post=$22 : EndIf
    If emphasis = 3 : magnitude=2 : post=$2B : EndIf
  ElseIf swing = 1
    If emphasis = 0 : magnitude=$21 : post=0 : EndIf
    If emphasis = 1 : magnitude=$12 : post=$15 : EndIf
    If emphasis = 2 : magnitude=2 : post=$22 : EndIf
  ElseIf swing = 2
    If emphasis = 0 : magnitude=$15 : post=0 : EndIf
    If emphasis = 1 : magnitude=0 : post=$15 : EndIf
  EndIf
  RockTcWrite(RockTcLaneOffset($4001,lane),$BEFC)
  RockTcWrite(RockTcLaneOffset($4100,lane),$6799)
  RockTcWrite(RockTcLaneOffset($4101,lane),$6798)
  RockTcWrite(RockTcLaneOffset($4102,lane),$98)
  RockTcWrite(RockTcLaneOffset($4103,lane),$98)
  RockTcWrite(RockTcLaneOffset($4050,lane),magnitude)
  RockTcWrite(RockTcLaneOffset($404C,lane),post)
  If swing = 2 And emphasis = 0
    RockTcWrite(RockTcLaneOffset($41E1,lane),$700)
    RockTcWrite(RockTcLaneOffset($4047,lane),$13C)
  Else
    RockTcWrite(RockTcLaneOffset($4047,lane),$128)
    RockTcWrite(RockTcLaneOffset($41E1,lane),$400)
  EndIf
  value = RockTcRead(RockTcLaneOffset($40E0,lane))
  RockTcWrite(RockTcLaneOffset($40E0,lane),(value & $8FFF) | $6000)
EndProcedure

Procedure.i RockTcSigned8(value.i)
  value = value & 255
  If value >= 128 : ProcedureReturn value-256 : EndIf
  ProcedureReturn value
EndProcedure

Procedure RockTcAuxCalibrate()
  Protected pu.i = RockTcRead(#TCPHY_CMN_TXPUCAL) & $7F
  Protected pd.i = RockTcRead(#TCPHY_CMN_TXPDCAL) & $7F
  Protected puAdj.i = RockTcSigned8(RockTcRead(#TCPHY_CMN_TXPU_ADJ) & $FF)
  Protected pdAdj.i = RockTcSigned8(RockTcRead(#TCPHY_CMN_TXPD_ADJ) & $FF)
  Protected calibration.i = (pu+pd)/2 + puAdj + pdAdj
  Protected ana1.i = RockTcRead(#TCPHY_TX_ANA1)
  Protected ana2.i
  Protected value.i
  ana1 = ana1 & $FFFFDFFF
  RockTcWrite(#TCPHY_TX_ANA1,ana1)
  value = RockTcRead(#TCPHY_TX_DIG2)
  RockTcWrite(#TCPHY_TX_DIG2,(value & $FFFFFFC0) | (calibration & $3F))
  RockTimerWaitUs(10000)
  ana1 = ana1 | $2000 : RockTcWrite(#TCPHY_TX_ANA1,ana1)
  RockTimerWaitUs(200)
  RockTcWrite(#TCPHY_DP_TX_CTL,0)
  ana2 = $100 : RockTcWrite(#TCPHY_TX_ANA2,ana2)
  RockTimerWaitUs(1)
  ana2 = ana2 | $200 : RockTcWrite(#TCPHY_TX_ANA2,ana2)
  RockTcWrite(#TCPHY_TX_ANA3,0)
  ana1 = ana1 | 8 : RockTcWrite(#TCPHY_TX_ANA1,ana1)
  RockTimerWaitUs(1)
  ana1 = ana1 | $10 : RockTcWrite(#TCPHY_TX_ANA1,ana1)
  RockTcWrite(#TCPHY_TX_ANA5,0)
  RockTcWrite(#TCPHY_TX_ANA4,$1001)
  ana1 = ana1 | $80 : RockTcWrite(#TCPHY_TX_ANA1,ana1)
  RockTimerWaitUs(5)
  ana1 = ana1 | $100 : RockTcWrite(#TCPHY_TX_ANA1,ana1)
  ana2 = ana2 | 1 : RockTcWrite(#TCPHY_TX_ANA2,ana2)
  RockTimerWaitUs(1)
  ana2 = ana2 | 2 : RockTcWrite(#TCPHY_TX_ANA2,ana2)
  ana1 = (ana1 | $8020) & $FFFFFE7F : RockTcWrite(#TCPHY_TX_ANA1,ana1)
  RockTimerWaitUs(1)
  ana1 = ana1 | $40 : RockTcWrite(#TCPHY_TX_ANA1,ana1)
  RockTcWrite(#TCPHY_TX_ANA4,0)
  RockTcWrite(#TCPHY_TX_COEFF,0)
  RockTcWrite(#TCPHY_TX_CYA,0)
  value = RockTcRead(#TCPHY_TX_DIG2)
  RockTcWrite(#TCPHY_TX_DIG2,value | $8000)
EndProcedure

Procedure.i RockTcPowerState(state.i)
  Protected request.i = 1 << state
  Protected value.i
  Protected start.i
  Protected now.i
  Protected attempt.i
  If (RockTcRead(#TCPHY_PMA_CMN_CTRL1) & 1) = 0 : rock_tcphy_error=41 : ProcedureReturn 0 : EndIf
  value = RockTcRead(#TCPHY_DP_MODE_CTL)
  RockTcWrite(#TCPHY_DP_MODE_CTL,(value & $FFFFFFF0) | request)
  start = RockTimerTicks()
  For attempt = 0 To 100000
    value = (RockTcRead(#TCPHY_DP_MODE_CTL) >> 4) & $F
    If value = request : ProcedureReturn 1 : EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= rock_timer_frequency/10 : Break : EndIf
  Next
  rock_tcphy_error=42
  ProcedureReturn 0
EndProcedure

Procedure.i RockTcWaitMask(offset.i, mask.i, wanted.i, timeoutUs.i)
  Protected start.i = RockTimerTicks()
  Protected now.i
  Protected attempt.i
  For attempt = 0 To 1000000
    If (RockTcRead(offset) & mask) = wanted : ProcedureReturn 1 : EndIf
    now = RockTimerTicks()
    If now < start Or now-start >= (rock_timer_frequency/1000000)*timeoutUs : Break : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i RockTcPhyUp()
  Protected value.i
  rock_tcphy_error = 0
  ; Pinned pre-init fields are owned while TCPHY, UPHY and PIPE remain reset.
  PokeL(#ROCK_GRF+$E588,$40004000)
  PokeL(#ROCK_GRF+$E580,$00080000)
  If RockCruReset(149,0) = 0 : rock_tcphy_error=43 : ProcedureReturn 0 : EndIf
  ; Configure only after the TCPHY register state machine is out of reset.
  PokeL(#ROCK_GRF+$E580,$00010000)
  value = RockTcRead(#TCPHY_TX_ANA1)
  RockTcWrite(#TCPHY_TX_ANA1,value | $1000)
  RockTcCommon24M()
  RockTcWrite(#TCPHY_PMA_LANE_CFG,$5100)
  RockTcUsbPll()
  RockTcDpRbrPll()
  RockTcUsbTxLane(0)
  RockTcUsbRxLane(1)
  RockTcDpLane(2,0,0)
  RockTcDpLane(3,0,0)
  value = RockTcRead(#TCPHY_DP_MODE_CTL)
  RockTcWrite(#TCPHY_DP_MODE_CTL,(value & $FFFFFFF0) | $104)
  If RockCruReset(148,0) = 0 : rock_tcphy_error=45 : ProcedureReturn 0 : EndIf
  If RockTcWaitMask(#TCPHY_PMA_CMN_CTRL1,1,1,100000) = 0 : rock_tcphy_error=44 : ProcedureReturn 0 : EndIf
  If RockCruReset(332,0) = 0 : rock_tcphy_error=47 : ProcedureReturn 0 : EndIf
  PokeL(#ROCK_GRF+$6268,$00080000)
  If RockTcWaitMask(#TCPHY_DP_MODE_CTL,$40,$40,100000) = 0 : rock_tcphy_error=46 : ProcedureReturn 0 : EndIf
  RockTcAuxCalibrate()
  If RockTcPowerState(0) = 0 : ProcedureReturn 0 : EndIf
  value = RockTcRead(#TCPHY_DP_MODE_CTL) | $F000
  value = value & $FFFFCFFF
  RockTcWrite(#TCPHY_DP_MODE_CTL,value)
  ProcedureReturn 1
EndProcedure
