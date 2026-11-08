; Zentaji hardware behind the shared payload ABI. Core0 supervisor owns it.
XIncludeFile "Anvil/Hal/service_errors.pbi"
Procedure.i HwBoardName() : ProcedureReturn "Zentaji" : EndProcedure
; No address translation or instruction/data cache is implemented by this CPU.
Procedure.i HwMmuState() : ProcedureReturn 0 : EndProcedure
; No dynamic module arena/provider is admitted by this composition.
Procedure.i HwSeamCore(id.i) : ProcedureReturn 0 : EndProcedure
Procedure HwPet()
 ; Only feed an actually enabled watchdog; never enable it as a side effect.
 If (PeekQ(#ZEN_IDLE_TIMERS+$800)&1)<>0 : PokeQ(#ZEN_IDLE_TIMERS+$810,$FEEDD06E) : EndIf
EndProcedure
ProcedureNaked HwReboot()
 ASM
  LIQ r16,$FFFF000000020050
  LI r17,$5E7
  ST64 r17,[r16]
  HALT 0
 EndASM
EndProcedure

; No module loader/registry is installed here. A fill is unavailable and a
; lookup/availability question returns no function/provider, never a fake one.
Procedure.i HwPayloadModuleHas(seam.i) : ProcedureReturn 0 : EndProcedure
Procedure.i HwPayloadModuleFill(seam.i,index.i,fn.i) : ProcedureReturn #SVC_ENOSYS : EndProcedure
Procedure.i HwPayloadModuleFn(seam.i,index.i) : ProcedureReturn 0 : EndProcedure
