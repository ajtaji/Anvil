; In-house silicon discriminator, not included by the ordinary board build.
; RK3399 TRM1.1 Part3 sections3.3.7/3.7.8 and the pinned vendor driver's
; vop_disable_allwin() permit background-only scanout with timing/output on.
; Compare the same native mode with WIN0 on/off/restored, without touching
; clock, timing, framebuffer address, DP state or persistent storage.
; RK3399 TRM1.1 Part3 p240: VOP_VOP_STATUS +2A4 bits12:0 are
; the read-only display vertical counter. Sample without UART traffic.
; These are CPU-observed edge intervals, not a probe of the DP wire: polling
; latency bounds the precision, and a skipped counter is reported separately.
Procedure RockDisplayLineCadenceTest()
  Protected previous.i
  Protected line.i
  Protected tick.i
  Protected priorTick.i
  Protected deadline.i
  Protected delta.i
  Protected minimum.i = $7FFFFFFFFFFFFFFF
  Protected maximum.i
  Protected samples.i
  Protected skipped.i
  Protected firstWrap.i
  Protected lastWrap.i
  Protected wraps.i
  Protected frameMinimum.i = $7FFFFFFFFFFFFFFF
  Protected frameMaximum.i
  Protected expected.i
  previous=RockVopRead($2A4) & $1FFF
  tick=RockTimerTicks()
  deadline=tick+rock_timer_frequency/2
  Repeat
    line=RockVopRead($2A4) & $1FFF
    tick=RockTimerTicks()
    If line<>previous
      expected=previous+1
      If expected=rock_mode_vtotal : expected=0 : EndIf
      If line<>expected
        skipped=skipped+1
      ElseIf priorTick<>0
        delta=tick-priorTick
        If delta<minimum : minimum=delta : EndIf
        If delta>maximum : maximum=delta : EndIf
        samples=samples+1
      EndIf
      If line<previous
        If wraps=0
          firstWrap=tick
        Else
          delta=tick-lastWrap
          If delta<frameMinimum : frameMinimum=delta : EndIf
          If delta>frameMaximum : frameMaximum=delta : EndIf
        EndIf
        lastWrap=tick
        wraps=wraps+1
      EndIf
      previous=line
      priorTick=tick
    EndIf
  Until wraps>=10 Or tick>=deadline
  RockUartText("LINE CADENCE SAMPLES ") : RockDisplayDecimal(samples)
  RockUartText(" SKIPPED ") : RockDisplayDecimal(skipped)
  RockUartText(" TIMER HZ ") : RockDisplayDecimal(rock_timer_frequency)
  RockUartText(" EXPECTED NS ")
  RockDisplayDecimal((rock_mode_htotal*1000000000)/rock_mode_pixel_hz)
  If samples>0
    RockUartText(" OBSERVED MIN/MAX NS ")
    RockDisplayDecimal((minimum*1000000000)/rock_timer_frequency) : RockUartByte(47)
    RockDisplayDecimal((maximum*1000000000)/rock_timer_frequency)
  EndIf
  RockUartText(" WRAPS ") : RockDisplayDecimal(wraps)
  If wraps>1
    RockUartText(" FRAME MIN/MAX NS ")
    RockDisplayDecimal((frameMinimum*1000000000)/rock_timer_frequency) : RockUartByte(47)
    RockDisplayDecimal((frameMaximum*1000000000)/rock_timer_frequency)
  EndIf
  RockUartByte(13) : RockUartByte(10)
EndProcedure

Procedure RockDisplayIsolationTest()
  Protected savedControl.i
  If rock_display_ready=0 : ProcedureReturn 0 : EndIf
  savedControl=RockVopRead(#VOP_WIN0_CTRL0)
  If (savedControl & #VOP_WIN_ENABLE)=0
    RockUartLine("Isolation test refused: WIN0 is not enabled; check display initialization.")
    ProcedureReturn 0
  EndIf
  RockUartLine("ISOLATION BASELINE WIN0 ON")
  RockUartText("VOP EXTRA BG/CBR/OFFSET/ALPHA/DST/CSC ")
  RockDisplayHexLong(RockVopRead($018)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead($058)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead($05C)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead($060)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead($064)) : RockUartByte(32)
  RockDisplayHexLong(RockVopRead($2C0))
  RockUartByte(13) : RockUartByte(10)
  RockDisplayFrameTelemetry()
  RockDisplayLineCadenceTest()
  RockVopField(#VOP_WIN0_CTRL0,#VOP_WIN_ENABLE,0)
  RockVopWrite(#VOP_CFG_DONE,1)
  ASM
    dsb sy
  ENDASM
  RockUartLine("ISOLATION BACKGROUND ONLY")
  ; Each measurement waits200ms for the latched layer transition and FIFO
  ; settling, then clears old faults and observes nine fresh frame edges.
  RockDisplayFrameTelemetry()
  RockDisplayLineCadenceTest()
  RockVopWrite(#VOP_WIN0_CTRL0,savedControl)
  RockVopWrite(#VOP_CFG_DONE,1)
  ASM
    dsb sy
  ENDASM
  RockUartLine("ISOLATION RESTORED EXACT WIN0")
  RockDisplayFrameTelemetry()
  RockDisplayLineCadenceTest()
  If RockVopRead(#VOP_WIN0_CTRL0)<>savedControl
    RockUartLine("Isolation restoration failed: WIN0 differs; check the register readback.")
    ProcedureReturn 0
  EndIf
  RockUartLine("ISOLATION RESTORE READBACK PASS")
EndProcedure
