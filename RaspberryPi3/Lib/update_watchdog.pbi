; Original BCM2835 PM watchdog boot-trial adapter. Register behavior checked
; against Linux v6.12 drivers/watchdog/bcm2835_wdt.c; no code copied.
; Flat dependency: sdhost.pbi context guard and update_ab.pbi state owner.
; Does not change RSTS (firmware partition/halt selection).
Procedure.i p3uwRead(address.i)
  Protected value.i
  ASM
    dsb sy
    isb
  EndASM
  value = PeekL(address) & $FFFFFFFF
  ASM
    dsb sy
    isb
  EndASM
  ProcedureReturn value
EndProcedure

; Explicit user reset, not automatic after commit. Transport must acknowledge
; and drain UART first. Refuse receive/uncertain transaction state twice.
Procedure.i Pi3UpdateResetNow()
  Protected control.i
  If p3sdContext() = 0 Or Pi3UpdateResetReady() = 0 : ProcedureReturn 0 : EndIf
  p3uwWrite($3F100024, $5A00000A)
  control = p3uwRead($3F10001C)
  p3uwWrite($3F10001C, $5A000000 | (control & $00FFFFCF) | $20)
  Pi3DelayUs(500000)
  ; Reaching here means the requested reset did not occur.
  ProcedureReturn 0
EndProcedure
Global pi3_update_watchdog_early_owned.i
Global pi3_update_watchdog_window_owned.i
Global pi3_update_watchdog_trial_owned.i
Global pi3_update_watchdog_completed.i

; Immutable loader only: cover the firmware max-core-clock request, native
; SDHOST bring-up and cold A/B mount. The deployed build-7 loader could hang
; in that interval before its trial watchdog existed (forum topic 788). This
; timer is renewed only after a completed bounded work unit. It is stopped
; after successful or explicitly refused storage work. The later loader work
; window has the same progress contract; the candidate trial does not.
Procedure.i Pi3UpdateWatchdogArmEarly()
  Protected control.i
  If p3sdContext()=0 Or pi3_up_mounted<>0 Or pi3_up_receiving<>0 Or pi3_up_loaded<>0 : ProcedureReturn 0 : EndIf
  If pi3_update_watchdog_early_owned<>0 Or pi3_update_watchdog_window_owned<>0 Or pi3_update_watchdog_trial_owned<>0 : ProcedureReturn 0 : EndIf
  control=p3uwRead($3F10001C)
  p3uwWrite($3F100024,$5A0F0000)
  p3uwWrite($3F10001C,$5A000000 | (control & $00FFFFCF) | $20)
  If (p3uwRead($3F10001C) & $30)<>$20 : ProcedureReturn 0 : EndIf
  pi3_update_watchdog_completed=0
  pi3_update_watchdog_early_owned=1
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateWatchdogStopEarly()
  If p3sdContext()=0 Or pi3_update_watchdog_early_owned=0 Or pi3_update_watchdog_window_owned<>0 : ProcedureReturn 0 : EndIf
  p3uwWrite($3F10001C,$5A000102)
  If (p3uwRead($3F10001C) & $30)<>0 : ProcedureReturn 0 : EndIf
  pi3_update_watchdog_early_owned=0
  ProcedureReturn 1
EndProcedure

; Service only the cold immutable-storage watchdog after bounded work has
; completed. Once the loader owns the trial window this is deliberately a
; no-op, preserving the failure deadline through candidate load and branch.
Procedure.i Pi3UpdateWatchdogEarlyProgress()
  Protected control.i
  If p3sdContext()=0 Or pi3_update_watchdog_early_owned=0 Or pi3_update_watchdog_window_owned<>0
    ProcedureReturn 0
  EndIf
  control=p3uwRead($3F10001C)
  If (control & $30)<>$20 : ProcedureReturn 0 : EndIf
  p3uwWrite($3F100024,$5A0F0000)
  p3uwWrite($3F10001C,$5A000000 | (control & $00FFFFCF) | $20)
  ProcedureReturn (p3uwRead($3F10001C) & $30)=$20
EndProcedure

; Immutable loader only: acquire the deadman before the post-recovery selected
; slot load. Only completed bounded loader work can renew it. Immediately
; before branch it becomes a fresh, separately owned, unserviced trial timer.
Procedure.i Pi3UpdateWatchdogArmWindow()
  Protected control.i
  If p3sdContext()=0 Or pi3_up_mounted=0 Or pi3_up_receiving<>0 Or pi3_up_loaded<>0 : ProcedureReturn 0 : EndIf
  If pi3_update_watchdog_early_owned<>0 Or pi3_update_watchdog_window_owned<>0 Or pi3_update_watchdog_trial_owned<>0 : ProcedureReturn 0 : EndIf
  control=p3uwRead($3F10001C)
  p3uwWrite($3F100024,$5A0F0000)
  p3uwWrite($3F10001C,$5A000000 | (control & $00FFFFCF) | $20)
  If (p3uwRead($3F10001C) & $30)<>$20 : ProcedureReturn 0 : EndIf
  pi3_update_watchdog_completed=0
  pi3_update_watchdog_window_owned=1
  ProcedureReturn 1
EndProcedure
 ; Service is permitted only to the immutable loader, after completed work.
; Never call this from a polling loop, timer tick, or candidate health loop.
Procedure.i Pi3UpdateWatchdogProgress(completed.i)
  If p3sdContext()=0 Or pi3_update_watchdog_trial_owned<>0 : ProcedureReturn 0 : EndIf
  If pi3_update_watchdog_early_owned + pi3_update_watchdog_window_owned <> 1 : ProcedureReturn 0 : EndIf
  If completed<=pi3_update_watchdog_completed : ProcedureReturn 0 : EndIf
  If (p3uwRead($3F10001C) & $30)<>$20 : ProcedureReturn 0 : EndIf
  p3uwWrite($3F100024,$5A0F0000)
  If (p3uwRead($3F10001C) & $30)<>$20 : ProcedureReturn 0 : EndIf
  pi3_update_watchdog_completed=completed
  ProcedureReturn 1
EndProcedure

; The trial starts here, after verification and placement, not before them.
; This transition revokes loader servicing before control reaches the image.
Procedure.i Pi3UpdateWatchdogBeginTrial()
  If p3sdContext()=0 Or pi3_update_watchdog_early_owned<>0 Or pi3_update_watchdog_window_owned<>1 Or pi3_update_watchdog_trial_owned<>0 : ProcedureReturn 0 : EndIf
  If pi3_up_loaded<4 Or pi3_up_mounted=0 Or pi3_up_receiving<>0 : ProcedureReturn 0 : EndIf
  If (p3uwRead($3F10001C) & $30)<>$20 : ProcedureReturn 0 : EndIf
  p3uwWrite($3F100024,$5A0F0000)
  If (p3uwRead($3F10001C) & $30)<>$20 : ProcedureReturn 0 : EndIf
  pi3_update_watchdog_window_owned=0
  pi3_update_watchdog_trial_owned=1
  ProcedureReturn 1
EndProcedure
Procedure p3uwWrite(address.i, value.i)
 ASM
    dsb sy
    isb
  EndASM
  PokeL(address, value)
  ASM
    dsb sy
    isb
  EndASM
EndProcedure
Procedure.i Pi3UpdateWatchdogArm()
  Protected control.i
  If p3sdContext() = 0 Or pi3_up_loaded < 4 Or pi3_up_active < 0 : ProcedureReturn 0 : EndIf
  If PeekL(@pi3_up_record[0] + pi3_up_active * 512 + 64) <> #PI3_UPDATE_TRIED : ProcedureReturn 0 : EndIf
  ; A loader that already owns the whole pre-branch window verifies rather
  ; than feeding/restarting it here.
  If pi3_update_watchdog_window_owned<>0
    ProcedureReturn (p3uwRead($3F10001C) & $30)=$20
  EndIf
  control = p3uwRead($3F10001C)
  ; 15 seconds at 65536 ticks/second. No unlimited progress feeding: failure
  ; to reach the confirmation health point causes a full watchdog reset.
  p3uwWrite($3F100024, $5A0F0000)
  p3uwWrite($3F10001C, $5A000000 | (control & $00FFFFCF) | $20)
  ProcedureReturn (p3uwRead($3F10001C) & $30) = $20
EndProcedure
; Immutable cold loader only, before SD mount and recovery wait. Reset-control
; configuration bits can survive a watchdog reset and do not prove an active
; foreign owner. The updater must NEVER call this before confirmation.
Procedure.i Pi3UpdateWatchdogColdStop()
  If p3sdContext() = 0 : ProcedureReturn 0 : EndIf
  p3uwWrite($3F10001C, $5A000102)
  If (p3uwRead($3F10001C) & $30) <> 0 : ProcedureReturn 0 : EndIf
  pi3_update_watchdog_early_owned=0
  pi3_update_watchdog_window_owned=0
  pi3_update_watchdog_trial_owned=0
  pi3_update_watchdog_completed=0
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3UpdateWatchdogStop()
  If p3sdContext() = 0 Or pi3_up_active < 0 : ProcedureReturn 0 : EndIf
  If PeekL(@pi3_up_record[0] + pi3_up_active * 512 + 64) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn 0 : EndIf
  p3uwWrite($3F10001C, $5A000102)
  If (p3uwRead($3F10001C) & $30) <> 0 : ProcedureReturn 0 : EndIf
  pi3_update_watchdog_early_owned=0
  pi3_update_watchdog_window_owned=0
  pi3_update_watchdog_trial_owned=0
  pi3_update_watchdog_completed=0
  ProcedureReturn 1
EndProcedure
