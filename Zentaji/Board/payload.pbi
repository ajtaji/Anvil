; Board ownership around the CPU call. Trusted supervisor payloads must leave
; devices they touch quiesced; this is not a sandbox or arbitrary DMA recovery.
; Ordinary payloads release devices. Service-backed payloads retain the resident
; owners and call them through the actual shared ABI. Both paths verify return
; ownership before a prompt; failed recovery halts, never a false prompt.
XIncludeFile "Anvil/Kernel/Zentaji/payload_call.pbi"
; Optional graphics-owner handoff installed by the board composition.
; The shared payload path keeps its serial/text behavior without a renderer.
Procedure.i ZentajiPayloadGraphicsAbsent() : ProcedureReturn 1 : EndProcedure
Global *zenPayloadGraphicsDown=@ZentajiPayloadGraphicsAbsent
Global *zenPayloadGraphicsUp=@ZentajiPayloadGraphicsAbsent
Procedure.i ZentajiPayloadGraphicsBind(down.i,up.i)
 If (down=0 And up<>0) Or (down<>0 And up=0) : ProcedureReturn 0 : EndIf
 *zenPayloadGraphicsDown=@ZentajiPayloadGraphicsAbsent
 *zenPayloadGraphicsUp=@ZentajiPayloadGraphicsAbsent
 If down<>0 : *zenPayloadGraphicsDown=down : *zenPayloadGraphicsUp=up : EndIf
 ProcedureReturn 1
EndProcedure
Global zenPayTimer.q,zenPayConfig.q,zenPayRoute.q,zenPayRouteMask.q,zenPayEnable.q,zenPayThreshold.q
Procedure.i HwPmfTargetId() : ProcedureReturn 1 : EndProcedure
Procedure.i HwPmfStackAllowed(lo.i,hi.i) : ProcedureReturn InPayload(lo,hi) : EndProcedure
Procedure ScreenServiceTick()
 AnvilPromptService(#APS_SCREEN)
EndProcedure
ProcedureNaked ZentajiPayloadRecoveryFailed(code.i,*reason)
 ; Bounded raw serial reporting also works after logical console detach.
 ; Never touch an active TX block. No monitor stack/callback/timer is used.
 ASM
  LIQ r16,$FFFF000000100000
  LI r19,16
  LI r6,0
pay_failure_next:
  LD8U r3,[r2]
  ADDI r2,r2,1
  BNEI r3,0,pay_failure_begin
  LI r6,1
  LI r3,13
pay_failure_begin:
  LI r17,4096
pay_failure_probe:
  LD64 r18,[r16+8]
  AND r18,r18,r19
  BNEI r18,0,pay_failure_halt
  LD64 r18,[r16+$58]
  BNEI r18,0,pay_failure_write
  ADDI r17,r17,-1
  BNEI r17,0,pay_failure_probe
  JMP pay_failure_halt
pay_failure_write:
  ST64 r3,[r16+$40]
  BEQI r6,0,pay_failure_next
  BEQI r6,2,pay_failure_halt
  LI r6,2
  LI r3,10
  JMP pay_failure_begin
pay_failure_halt:
  HALT r1
 EndASM
EndProcedure
Procedure.i HwPayloadRun(entry.i,argument.i,stack.i,stackBytes.i)
 Protected hadStorage.i,entered.i,code.i,services.i
 gGoRc=0
 services=Bool(argument<>0)
 If services<>0
  If svcPayloadScope<>1 Or argument<>SvcTableAddr()
   PrintN("!! the Zentaji payload service scope is not owned; nothing was entered.")
   ProcedureReturn 0
  EndIf
 EndIf
 If ZenCpuStatus()<>0 Or ZenCpuCoreId()<>0 Or HwPromptIdleReady()=0 Or UartRunning()=0
  PrintN("!! Zentaji payload ownership is not ready; nothing was entered.")
  ProcedureReturn 0
 EndIf
 If ZentajiTextOwned()=0
  PrintN("!! native text ownership is not ready; nothing was entered.")
  ProcedureReturn 0
 EndIf
 If ZentajiInputHardwareOwned()=0
  PrintN("!! native input ownership is not ready; nothing was entered.")
  ProcedureReturn 0
 EndIf
 If ShotArmed()<>0
  ShotTakeArm()
  PrintN("!! this Zentaji monitor has no frame-capture provider; nothing was entered.")
  ProcedureReturn 0
 EndIf
 hadStorage=zenStorageAcquired
 If services=0
 If ZentajiStorageDown()=0
  PrintN("!! storage could not be quiesced; nothing was entered.")
  UartWriteStr(ZentajiStorageErrorText()) : PrintNl()
  ProcedureReturn 0
 EndIf
 EndIf
 If ZentajiConsoleDrain()=0
  PrintN("!! serial output did not drain; nothing was entered.")
  If hadStorage<>0 And HwStorageUp()=0 : ZentajiPayloadRecoveryFailed($5B01,"Payload admission failed (0x5B01): monitor ownership could not be restored. Check storage, serial and timer state.") : EndIf
  ProcedureReturn 0
 EndIf
 zenPayTimer=PeekQ(#ZEN_IDLE_TIMER)
 zenPayConfig=PeekQ(#ZEN_IDLE_INTC+$120) : zenPayRoute=PeekQ(#ZEN_IDLE_INTC+$220)
 zenPayRouteMask=PeekQ(#ZEN_IDLE_INTC+$228) : zenPayEnable=PeekQ(#ZEN_IDLE_INTC+$F008)
 zenPayThreshold=PeekQ(#ZEN_IDLE_INTC+$F010)
 If zenPayloadGraphicsDown()<>1 : ZentajiPayloadRecoveryFailed($5B07,"Payload admission failed (0x5B07): graphics ownership could not retire.") : EndIf
 If ZentajiInputPayload(1,services)=0 : ZentajiPayloadRecoveryFailed($5B06,"Payload admission failed (0x5B06): native input ownership changed.") : EndIf
 If services=0
 If ZentajiTextRelease()=0 : ZentajiPayloadRecoveryFailed($5B05,"Payload admission failed (0x5B05): native text or display ownership changed.") : EndIf
 If ZentajiPromptIdleRelease()=0 : ZentajiPayloadRecoveryFailed($5B01,"Payload admission failed (0x5B01): monitor ownership could not be restored. Check storage, serial and timer state.") : EndIf
 UartOff()
 EndIf
 gGoAddr=entry
 entered=ZentajiPayloadEnter(zenMemoryContext,entry,argument,stack,stackBytes)
 code=ZentajiPayloadLastError() : gGoRc=ZentajiPayloadReturnValue()
 ; The CPU boundary has restored owned SP/vectors/FP state with IE masked.
 ; Do not overwrite foreign live hardware to make recovery appear successful.
 If ZentajiInputPayload(0,services)=0 : ZentajiPayloadRecoveryFailed($5B06,"Payload return failed (0x5B06): native input ownership changed. Release mouse capture and device interrupts before returning.") : EndIf
 If services<>0 And TextServiceLeave()<>0 : ZentajiPayloadRecoveryFailed($5B05,"Payload return failed (0x5B05): resident text session could not release its owner.") : EndIf
 If services=0
  If ZentajiTextResume()=0 : ZentajiPayloadRecoveryFailed($5B05,"Payload return failed (0x5B05): native text or display is still owned. Quiesce both devices before returning.") : EndIf
 Else
  If ZentajiTextOwned()=0 : ZentajiPayloadRecoveryFailed($5B05,"Payload return failed (0x5B05): resident native text or display ownership changed.") : EndIf
 EndIf
 If ZentajiPromptIdleContext()=0 Or ZentajiPromptIdleTimerFree()=0 Or PeekQ(#ZEN_IDLE_TIMER)<>zenPayTimer
  ZentajiPayloadRecoveryFailed($5B02,"Payload return failed (0x5B02): timer, interrupt or serial ownership changed. Restore device state before returning.")
 EndIf
 If PeekQ(#ZEN_IDLE_INTC+$120)<>zenPayConfig Or PeekQ(#ZEN_IDLE_INTC+$220)<>zenPayRoute Or PeekQ(#ZEN_IDLE_INTC+$228)<>zenPayRouteMask
  ZentajiPayloadRecoveryFailed($5B02,"Payload return failed (0x5B02): timer, interrupt or serial ownership changed. Restore device state before returning.")
 EndIf
 If PeekQ(#ZEN_IDLE_INTC+$F008)<>zenPayEnable Or PeekQ(#ZEN_IDLE_INTC+$F010)<>zenPayThreshold
  ZentajiPayloadRecoveryFailed($5B02,"Payload return failed (0x5B02): timer, interrupt or serial ownership changed. Restore device state before returning.")
 EndIf
 If services=0
 If UartAttach()=0 Or ZentajiPromptIdlePrepare(2000)=0 : ZentajiPayloadRecoveryFailed($5B02,"Payload return failed (0x5B02): timer, interrupt or serial ownership changed. Restore device state before returning.") : EndIf
 If hadStorage<>0
  If HwStorageUp()=0
   PrintN("!! payload return could not reacquire storage. The monitor is stopping.")
   UartWriteStr(ZentajiStorageErrorText()) : PrintNl() : UartDrain()
   ZentajiPayloadRecoveryFailed($5B03,"Payload return failed (0x5B03): storage ownership could not be reacquired. Check disk queues and configuration.")
  EndIf
 EndIf
 Else
  If UartAttach()=0 Or HwPromptIdleReady()=0 : ZentajiPayloadRecoveryFailed($5B02,"Payload return failed (0x5B02): timer, interrupt or serial ownership changed. Restore device state before returning.") : EndIf
  If hadStorage<>0 And ZentajiDiskOwned()=0 : ZentajiPayloadRecoveryFailed($5B03,"Payload return failed (0x5B03): storage ownership could not be reacquired. Check disk queues and configuration.") : EndIf
 EndIf
 If zenPayloadGraphicsUp()<>1 : ZentajiPayloadRecoveryFailed($5B07,"Payload return failed (0x5B07): graphics ownership could not be restored.") : EndIf
 If entered=0
  Print("!! the Zentaji CPU entry refused the payload, code ") : PrintDec(code) : PrintN(".")
 Else
  Print("The payload returned, r1 = $") : PutHex16(gGoRc) : PrintNl()
 EndIf
 ProcedureReturn entered
EndProcedure
