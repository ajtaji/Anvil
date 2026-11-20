; Native core-control acceptance. A stackless secondary receives its challenge
; in r1. HALT publishes the response in its own EXIT register and stops that core.
#ZEN_CORE_CONTROL=$FFFF000000030000
Global zenCoreLease.i,zenCoreRound.i,zenCoreFault.i,zenCoreFailedId.i
Global Dim zenCoreChallenge.q[64]

ProcedureNaked ZentajiCoreWorker()
 ASM
  MFCR r2,COREID
  ADD r3,r1,r1
  ADD r3,r3,r1
  ADD r3,r3,r2
  HALT r3
 EndASM
EndProcedure
Procedure.i ZentajiCoreCount()
 Protected count.i=PeekQ(#ZEN_CORE_CONTROL+$40)
 If (PeekQ(#ZEN_CORE_CONTROL)&$FFFF)<>4 Or count<1 Or count>64 : ProcedureReturn 0 : EndIf
 ProcedureReturn count
EndProcedure
Procedure.i ZentajiCoreWindow(id.i)
 ProcedureReturn #ZEN_CORE_CONTROL+$100+id*$40
EndProcedure
Procedure.i ZentajiCoreMatches(id.i)
 Protected base.i=ZentajiCoreWindow(id)
 ProcedureReturn Bool(PeekQ(base+8)=@ZentajiCoreWorker And PeekQ(base+$10)=zenCoreChallenge[id] And PeekQ(base+$18)=0 And PeekQ(base+$20)=0)
EndProcedure
Procedure.i ZentajiCoreRelease()
 Protected id.i,base.i
 If zenCoreLease=0 : ProcedureReturn 1 : EndIf
 ; Validate every lease before modifying any of them. A completed HALT,
 ; including a wrong answer, is safe to reset when its launch words match.
 For id=1 To zenCoreLease
  base=ZentajiCoreWindow(id)
  If ZentajiCoreMatches(id)=0 Or PeekQ(base)<>3
   zenCoreFailedId=id : zenCoreFault=1 : ProcedureReturn 0
  EndIf
 Next
 For id=1 To zenCoreLease
  base=ZentajiCoreWindow(id) : PokeQ(base+$28,3)
  PokeQ(base+8,0) : PokeQ(base+$10,0)
 Next
 zenCoreLease=0 : zenCoreFault=0 : zenCoreFailedId=0
 ProcedureReturn 1
EndProcedure
Procedure CmdCoreAcceptStatus()
 Protected id.i,base.i,count.i=ZentajiCoreCount()
 Print("coretest fitted=") : PrintDec(count) : Print(" owned=") : PrintDec(zenCoreLease)
 Print(" round=") : PrintDec(zenCoreRound) : Print(" fault=") : PrintDec(zenCoreFault)
 Print(" fault_core=") : PrintDec(zenCoreFailedId) : PrintNl()
 For id=1 To count-1
  base=ZentajiCoreWindow(id)
  Print("  core=") : PrintDec(id) : Print(" state=") : PrintDec(PeekQ(base))
  Print(" argument=") : PutHex16(PeekQ(base+$10))
  Print(" exit=") : PutHex16(PeekQ(base+$30)) : PrintNl()
 Next
EndProcedure
Procedure CmdCoreAcceptStop()
 If ZentajiCoreRelease()=0
  PrintN("!! coretest stop refused: a secondary's state or launch words changed.")
 Else
  PrintN("coretest stopped. All owned secondaries are parked.")
 EndIf
 CmdCoreAcceptStatus()
EndProcedure
Procedure CmdCoreAcceptRun()
 Protected count.i=ZentajiCoreCount(),id.i,base.i,round.i,start.q
 If count<2 : PrintN("!! coretest needs a fitted secondary core.") : ProcedureReturn : EndIf
 If ZenCpuCoreId()<>0 Or ZenCpuStatus()<>0 Or HwPromptIdleReady()=0
  PrintN("!! coretest needs the monitor on supervisor core 0 with its timer.") : ProcedureReturn
 EndIf
 If ZentajiCoreRelease()=0 : PrintN("!! coretest cannot replace a changed secondary lease.") : ProcedureReturn : EndIf
 For id=1 To count-1
  base=ZentajiCoreWindow(id)
  If PeekQ(base)<>0 Or PeekQ(base+8)<>0 Or PeekQ(base+$10)<>0 Or PeekQ(base+$18)<>0 Or PeekQ(base+$20)<>0
   Print("!! coretest found an occupied or staged secondary: ") : PrintDec(id) : PrintNl() : ProcedureReturn
  EndIf
 Next
 zenCoreLease=count-1
 For round=1 To 16
  zenCoreRound=(zenCoreRound & $FFFFFF)+1
  For id=1 To zenCoreLease
   base=ZentajiCoreWindow(id)
   zenCoreChallenge[id]=zenCoreRound*257+id*17
   PokeQ(base+8,@ZentajiCoreWorker) : PokeQ(base+$10,zenCoreChallenge[id])
   PokeQ(base+$28,1)
  Next
  start=Ticks()
  For id=1 To zenCoreLease
   base=ZentajiCoreWindow(id)
   While PeekQ(base)<>3
    If Ticks()-start>=TickHz() : Break : EndIf
    HwPromptIdleWait()
   Wend
   If PeekQ(base)<>3 Or ZentajiCoreMatches(id)=0 Or PeekQ(base+$30)<>zenCoreChallenge[id]*3+id
    zenCoreFault=1 : zenCoreFailedId=id
    PrintN("!! coretest failed waiting for a matching secondary result.") : CmdCoreAcceptStatus() : ProcedureReturn
   EndIf
  Next
 Next
 Print("coretest PASS: 16 challenge rounds on ") : PrintDec(zenCoreLease) : PrintN(" secondary cores.")
 CmdCoreAcceptStatus()
EndProcedure
