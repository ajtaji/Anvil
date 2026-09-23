; RK3399 CA53 DesignWare watchdog deadman for the resident EL3 recovery path.
; The mainline RK3399 DT binds ff848000 to snps,dw-wdt and gives it PCLK_WDT.
; Linux defines PCLK_WDT as pclk_alive, but cannot control its secure gate.
; ARM Trusted Firmware owns that gate through SGRF_SOC_CON3[8] and also
; ungates the companion CM0 watchdog clock at bit 10. Both bits are active
; high disables and use Rockchip's upper-halfword write mask.
;
; The RK3399 watchdog DT node has no reset property. Match the DesignWare
; Rockchip driver: read and preserve CR, clear interrupt mode, set enable,
; program identical TOP/TOP_INIT selectors, write CR, then restart. Do not
; add an unreferenced CRU reset pulse or disable an already-live deadman.

#ROCK_WATCHDOG_BASE = $FF848000
#ROCK_WATCHDOG_CR = $00
#ROCK_WATCHDOG_TORR = $04
#ROCK_WATCHDOG_CRR = $0C
#ROCK_WATCHDOG_RESTART = $76
#ROCK_WATCHDOG_SGRF = $FF330000
#ROCK_WATCHDOG_SGRF_SOC_CON3 = $E00C
#ROCK_WATCHDOG_SGRF_GATE_MASK = $00000500
#ROCK_WATCHDOG_TIMEOUT_MS = 8000
#ROCK_WATCHDOG_ERROR_EL = 1
#ROCK_WATCHDOG_ERROR_GATE = 2
#ROCK_WATCHDOG_ERROR_GPLL = 3
#ROCK_WATCHDOG_ERROR_RATE = 4
#ROCK_WATCHDOG_ERROR_CR = 5
#ROCK_WATCHDOG_ERROR_TORR = 6

Global rock_watchdog_armed.i
Global rock_watchdog_active.i
Global rock_watchdog_error.i
Global rock_watchdog_clock_hz.i
Global rock_watchdog_torr.i
Global rock_watchdog_sgrf.i
Global rock_watchdog_clksel57.i
Global rock_watchdog_gpll_hz.i
Global rock_watchdog_cr_before.i
Global rock_watchdog_cr.i
Global rock_watchdog_torr_read.i

Procedure.i RockWatchdogArm()
  Protected savedCruError.i=rock_cru_error
  Protected gpll.i
  Protected divider.i
  Protected cycles.i
  Protected top.i
  Protected scan.i
  Protected value.i

  rock_watchdog_armed=0
  rock_watchdog_error=0
  rock_watchdog_clock_hz=0
  rock_watchdog_torr=0
  rock_watchdog_sgrf=0
  rock_watchdog_clksel57=0
  rock_watchdog_gpll_hz=0
  rock_watchdog_cr_before=0
  rock_watchdog_cr=0
  rock_watchdog_torr_read=0
  If rock_current_el<>12
    rock_watchdog_error=#ROCK_WATCHDOG_ERROR_EL
    ProcedureReturn 0
  EndIf

  ; TF-A secure_watchdog_ungate(): clear active-high CA53 and CM0 gate bits.
  PokeL(#ROCK_WATCHDOG_SGRF+#ROCK_WATCHDOG_SGRF_SOC_CON3,$05000000)
  ASM
    dsb sy
  ENDASM
  rock_watchdog_sgrf=PeekL(#ROCK_WATCHDOG_SGRF+#ROCK_WATCHDOG_SGRF_SOC_CON3) & $FFFFFFFF
  If (rock_watchdog_sgrf & #ROCK_WATCHDOG_SGRF_GATE_MASK)<>0
    rock_watchdog_error=#ROCK_WATCHDOG_ERROR_GATE
    ProcedureReturn 0
  EndIf

  ; U-Boot derives PCLK_WDT from GPLL / (CLKSEL_CON57[4:0] + 1).
  rock_watchdog_clksel57=RockCruRead(#ROCK_CRU_CLKSEL+57*4)
  gpll=RockCruPllRate($80,1,102)
  rock_watchdog_gpll_hz=gpll
  If gpll<=0
    rock_cru_error=savedCruError
    rock_watchdog_error=#ROCK_WATCHDOG_ERROR_GPLL
    ProcedureReturn 0
  EndIf
  divider=(rock_watchdog_clksel57 & $1F)+1
  rock_watchdog_clock_hz=gpll/divider
  rock_cru_error=savedCruError
  If rock_watchdog_clock_hz<1000000 Or rock_watchdog_clock_hz>200000000
    rock_watchdog_error=#ROCK_WATCHDOG_ERROR_RATE
    ProcedureReturn 0
  EndIf

  ; designware_wdt_settimeout(): fls(timeout_ms * clk_khz - 1) - 16,
  ; clamped to the hardware TOP selector range 0..15.
  cycles=(#ROCK_WATCHDOG_TIMEOUT_MS*(rock_watchdog_clock_hz/1000))-1
  top=-16
  scan=cycles
  While scan<>0
    top=top+1
    scan=scan >> 1
  Wend
  If top<0 : top=0 : EndIf
  If top>15 : top=15 : EndIf
  rock_watchdog_torr=top | (top << 4)

  ; Match the local Rockchip rockchip_wdt.c enable path exactly: preserve CR,
  ; feed an already-enabled counter, clear interrupt mode, and set enable.
  ; Do not stop a live watchdog first.
  rock_watchdog_cr_before=PeekL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CR) & $FFFFFFFF
  If (rock_watchdog_cr_before & 1)<>0
    PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CRR,#ROCK_WATCHDOG_RESTART)
    ASM
      dsb sy
    ENDASM
  EndIf
  value=(rock_watchdog_cr_before & $FFFFFFFD) | 1
  PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_TORR,rock_watchdog_torr)
  PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CR,value)
  PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CRR,#ROCK_WATCHDOG_RESTART)
  ASM
    dsb sy
  ENDASM
  ; From this point the physical watchdog can expire even if a readback check
  ; below rejects the setup. Keep feeding it from healthy recovery while the
  ; raw telemetry identifies the mismatched register.
  rock_watchdog_active=1
  rock_watchdog_cr=PeekL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CR) & $FFFFFFFF
  rock_watchdog_torr_read=PeekL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_TORR) & $FFFFFFFF
  If (rock_watchdog_cr & 3)<>1
    rock_watchdog_error=#ROCK_WATCHDOG_ERROR_CR
    ProcedureReturn 0
  EndIf
  ; RK3399 implements/readbacks TOP in TORR[3:0]. Rockchip still writes the
  ; same selector into TOP_INIT[7:4], but physical build 104 proved those
  ; bits read as zero on this instance. Require the implemented selector and
  ; require every read-as-zero/reserved bit to remain zero.
  If (rock_watchdog_torr_read & $0F)<>(rock_watchdog_torr & $0F) Or (rock_watchdog_torr_read & $FFFFFFF0)<>0
    rock_watchdog_error=#ROCK_WATCHDOG_ERROR_TORR
    ProcedureReturn 0
  EndIf
  rock_watchdog_armed=1
  ProcedureReturn 1
EndProcedure

Procedure RockWatchdogPet()
  ; Shared display helpers may call this before recovery arms the deadman.
  ; An inactive pet must not start or otherwise modify the watchdog. Active
  ; is distinct from validated: failed post-enable readback still needs feeds.
  If rock_watchdog_active<>0
    PokeL(#ROCK_WATCHDOG_BASE+#ROCK_WATCHDOG_CRR,#ROCK_WATCHDOG_RESTART)
    ASM
      dsb sy
    ENDASM
  EndIf
EndProcedure

Procedure RockWatchdogTelemetry()
  RockUartText("WDT ERR=") : RockDisplayHexLong(rock_watchdog_error)
  RockUartText(" ACTIVE=") : RockDisplayHexLong(rock_watchdog_active)
  RockUartText(" SGRF=") : RockDisplayHexLong(rock_watchdog_sgrf)
  RockUartText(" CLK57=") : RockDisplayHexLong(rock_watchdog_clksel57)
  RockUartText(" GPLL=") : RockDisplayHexLong(rock_watchdog_gpll_hz)
  RockUartText(" PCLK=") : RockDisplayHexLong(rock_watchdog_clock_hz)
  RockUartText(" CR0=") : RockDisplayHexLong(rock_watchdog_cr_before)
  RockUartText(" CR=") : RockDisplayHexLong(rock_watchdog_cr)
  RockUartText(" TORR=") : RockDisplayHexLong(rock_watchdog_torr_read)
  RockUartText(" WANT=") : RockDisplayHexLong(rock_watchdog_torr)
  RockUartByte(13) : RockUartByte(10)
EndProcedure
