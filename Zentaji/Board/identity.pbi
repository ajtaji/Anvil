; Owned startup/memory layout must be bound before these identity calls.
Procedure.i HwIdBoard() : ProcedureReturn "Zentaji" : EndProcedure
Procedure.i HwIdCpu() : ProcedureReturn "Zentaji64 CPU" : EndProcedure
Procedure.i HwIdTarget() : ProcedureReturn "zentaji" : EndProcedure
Procedure.i HwIdExecutionModel() : ProcedureReturn "64-bit Zentaji" : EndProcedure
Procedure HwIdSayProcessorMode()
 If ZenCpuStatus()=0
  Print(" in Zentaji supervisor mode")
 Else
  Print(" outside the qualified monitor context, STATUS $") : PutHex16(ZenCpuStatus())
 EndIf
EndProcedure
Procedure HwIdSayConsole()
 PrintN("The console uses Zentaji serial port 0; idle waits use its hardware timer and WFI.")
EndProcedure
Procedure.i HwIdImageBase() : ProcedureReturn HwMonLo() : EndProcedure
Procedure.i HwIdImageLen() : ProcedureReturn HwMonBytes() : EndProcedure
Procedure.i HwIdImageHashable() : ProcedureReturn 0 : EndProcedure
Procedure HwIdSayImageWhere()
 PrintN("  The extent comes from the validated owned-startup context, including mutable data.")
EndProcedure
Procedure HwIdSayImage()
 PrintN("  The ROM loads a supervisor ZEX; Anvil owns its stack, vectors and file services.")
EndProcedure
