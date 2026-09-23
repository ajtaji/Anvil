; One implementation of the Pi 3 boot primitives shared by the monitor,
; immutable loader and serial updater compositions.
;
; The caller must include this after timer/mailbox and after the shared board
; globals (pi3_dtb, pi3_ram_base and pi3_ram_end) have been declared.

Procedure Pi3Park()
  ASM
    msr daifset, #15
pi3_common_park:
    wfe
    b pi3_common_park
  EndASM
EndProcedure

Procedure.i Pi3ReadBe32(address.i)
  ProcedureReturn (PeekA(address) << 24) | (PeekA(address + 1) << 16) | (PeekA(address + 2) << 8) | PeekA(address + 3)
EndProcedure

Procedure.i Pi3BootMaxCoreClock()
  ProcedureReturn Pi3ClockMaxRate(4)
EndProcedure

Global pi3_boot_stock_arm_actual.i
Global pi3_boot_stock_core_actual.i
Global pi3_boot_stock_measured.i

; Ask firmware to apply the Pi 3 stock ARM/CORE rates before SDHOST starts.
; Maximum-rate queries are admission checks; the SET_CLOCK_RATE replies are
; the actual values, and a lower thermal/policy-clamped value remains valid.
Procedure.i Pi3BootSetStockClocks()
  Protected maxArm.i
  Protected maxCore.i
  maxArm = Pi3ClockMaxRate(3)
  maxCore = Pi3ClockMaxRate(4)
  If maxArm < 1200000000 Or maxCore < 400000000 : ProcedureReturn 0 : EndIf
  pi3_boot_stock_arm_actual = Pi3ClockSetRate(3, 1200000000, 0)
  If pi3_boot_stock_arm_actual < 1 : ProcedureReturn 0 : EndIf
  pi3_boot_stock_core_actual = Pi3ClockSetRate(4, 400000000, 0)
  If pi3_boot_stock_core_actual < 1 : ProcedureReturn 0 : EndIf
  ; Prefer the optional hardware-measured tag. The ordinary GET rate is the
  ; next enable/configured rate, not a physical measurement.
  pi3_boot_stock_arm_actual = Pi3ClockMeasuredRate(3)
  pi3_boot_stock_core_actual = Pi3ClockMeasuredRate(4)
  If pi3_boot_stock_arm_actual > 0 And pi3_boot_stock_core_actual > 0
    pi3_boot_stock_measured = 1
  Else
    pi3_boot_stock_measured = 0
    pi3_boot_stock_arm_actual = Pi3ClockRate(3)
    pi3_boot_stock_core_actual = Pi3ClockRate(4)
  EndIf
  If pi3_boot_stock_arm_actual < 1 Or pi3_boot_stock_core_actual < 1 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3BootStockArmActual()
  ProcedureReturn pi3_boot_stock_arm_actual
EndProcedure

Procedure.i Pi3BootStockCoreActual()
  ProcedureReturn pi3_boot_stock_core_actual
EndProcedure

Procedure.i Pi3BootStockClockIsMeasured()
  ProcedureReturn pi3_boot_stock_measured
EndProcedure
