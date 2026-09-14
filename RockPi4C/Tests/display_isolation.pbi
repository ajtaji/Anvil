; In-house silicon discriminator, not included by the ordinary board build.
; RK3399 TRM1.1 Part3 sections3.3.7/3.7.8 and the pinned vendor driver's
; vop_disable_allwin() permit background-only scanout with timing/output on.
; Compare the same native mode with WIN0 on/off/restored, without touching
; clock, timing, framebuffer address, DP state or persistent storage.
Procedure RockDisplayIsolationTest()
  Protected savedControl.i
  If rock_display_ready=0 : ProcedureReturn 0 : EndIf
  savedControl=RockVopRead(#VOP_WIN0_CTRL0)
  If (savedControl & #VOP_WIN_ENABLE)=0
    RockUartLine("Isolation test refused: WIN0 is not enabled; check display initialization.")
    ProcedureReturn 0
  EndIf
  RockUartLine("ISOLATION BASELINE WIN0 ON")
  RockDisplayFrameTelemetry()
  RockVopField(#VOP_WIN0_CTRL0,#VOP_WIN_ENABLE,0)
  RockVopWrite(#VOP_CFG_DONE,1)
  ASM
    dsb sy
  ENDASM
  RockUartLine("ISOLATION BACKGROUND ONLY")
  ; Each measurement waits200ms for the latched layer transition and FIFO
  ; settling, then clears old faults and observes nine fresh frame edges.
  RockDisplayFrameTelemetry()
  RockVopWrite(#VOP_WIN0_CTRL0,savedControl)
  RockVopWrite(#VOP_CFG_DONE,1)
  ASM
    dsb sy
  ENDASM
  RockUartLine("ISOLATION RESTORED EXACT WIN0")
  RockDisplayFrameTelemetry()
  If RockVopRead(#VOP_WIN0_CTRL0)<>savedControl
    RockUartLine("Isolation restoration failed: WIN0 differs; check the register readback.")
    ProcedureReturn 0
  EndIf
  RockUartLine("ISOLATION RESTORE READBACK PASS")
EndProcedure
