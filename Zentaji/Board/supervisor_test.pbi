; Board policy for the bounded supervisor timer and breakpoint diagnostic.
Global Dim zenDiagReport.q[7]
Procedure.i ZentajiDiagAbsent(period.i,result.i) : ProcedureReturn -1 : EndProcedure
Global *zenDiagRun=@ZentajiDiagAbsent
Procedure ZentajiCmdSupervisorTest()
 Protected previous.i,entry.i,slot.i,count.i
 SkipSpace()
 If gLine[gPos]<>0 : PrintN("? supertest takes no arguments.") : ProcedureReturn : EndIf
 If ZenCpuCoreId()<>0 Or ZenCpuStatus()<>0 Or HwPromptIdleReady()=0 Or TickHz()<1000
  PrintN("!! supertest needs the primary supervisor and its idle timer.") : ProcedureReturn
 EndIf
 ; Delivery of other sources is held during the diagnostic. The assembly
 ; restores the original enable mask without claiming any of their events.
 If PeekQ(#ZEN_IDLE_INTC+$F018)<>255
  PrintN("!! supertest needs exclusive timer IRQ admission.") : ProcedureReturn
 EndIf
 previous=ZentajiPayloadVectors()
 If previous<>PeekQ(zenMemoryContext+#ZEN_BOOT_VECTORS)
  PrintN("!! supertest found a different vector owner.") : ProcedureReturn
 EndIf
 If zenMemoryContext<HwMonLo()+16 Or PeekQ(zenMemoryContext-16)<>$31474149444E455A
  PrintN("!! this supervisor startup has no diagnostic entry.") : ProcedureReturn
 EndIf
 entry=PeekQ(zenMemoryContext-8)
 If entry<previous+4096 Or entry>=zenMemoryContext-16 Or (entry&7)<>0
  PrintN("!! the supervisor diagnostic entry is outside its startup image.") : ProcedureReturn
 EndIf
 For slot=0 To 6 : zenDiagReport[slot]=0 : Next
 *zenDiagRun=entry
 count=CallFunctionFast(zenDiagRun,TickHz()/1000,@zenDiagReport[0])
 *zenDiagRun=@ZentajiDiagAbsent
 If ZentajiPayloadVectors()<>previous Or HwPromptIdleReady()=0 Or ZenCpuStatus()<>0
  ZentajiPayloadRecoveryFailed($5B0A,"supertest could not restore the supervisor timer or vectors.")
 EndIf
 Print("supertest IRQ cause=") : PrintDec(zenDiagReport[0]) : Print(" line=") : PrintDec(zenDiagReport[1])
 Print(" claim=") : PrintDec(zenDiagReport[2]) : Print(" fired=") : PrintDec(zenDiagReport[3])
 Print(" count=") : PrintDec(count) : PrintNl()
 Print("supertest BRK cause=") : PrintDec(zenDiagReport[4]) : Print(" tag=") : PutHex8(zenDiagReport[5]) : PrintNl()
 If count=1 And zenDiagReport[0]=33 And zenDiagReport[1]=1 And zenDiagReport[2]=1 And zenDiagReport[3]=1 And zenDiagReport[4]=11 And zenDiagReport[5]=$5A454E And zenDiagReport[6]<>0
  PrintN("supertest PASS. Timer and breakpoint returned to the original supervisor context.")
 Else
  PrintN("!! supertest FAILED. The supervisor timer and vectors were restored.")
 EndIf
EndProcedure
