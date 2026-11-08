; Shared interactive command lifecycle. Include after parse, rxbreak and
; addrsafe. A board supplies HwCommandDispatch and HwCommandLoopHook; the core
; owns prompt bytes, line preparation, timing and the unknown-word reply.
#ACMD_BEFORE_PROMPT=1
#ACMD_AFTER_PROMPT=2
#ACMD_BEFORE_INPUT=3
#ACMD_AFTER_INPUT=4
#ACMD_AFTER_COMMAND=5

Procedure.i AnvilCommandPrepare()
 Protected c.i,measured.i,suffix.i
 OutBreakArm()
 gPos=0 : SkipSpace() : gWordAt=gPos
 c=gLine[gPos]&255
 SkipWord() : gWordLen=gPos-gWordAt
 measured=TimeArm()
 If measured=1
  c=gLine[gWordAt]&255
 ElseIf measured=2
  c=0
 EndIf
 ; Both are per-line state, including empty/refused/unknown commands.
 gMemWidth=0 : ForceAge()
 If gWordLen>=3 And gLine[gWordAt+gWordLen-2]=46
  suffix=gLine[gWordAt+gWordLen-1]&255
  If suffix=98 Or suffix=66
   gMemWidth=1
  ElseIf suffix=119 Or suffix=87
   gMemWidth=2
  ElseIf suffix=108 Or suffix=76
   gMemWidth=4
  EndIf
  If gMemWidth<>0 : gWordLen=gWordLen-2 : EndIf
 EndIf
 ProcedureReturn c
EndProcedure

Procedure AnvilCommandUnknown()
 Protected k.i
 Print("? this monitor does not know the command ")
 While k<gWordLen And k<24
  UartWrite(gLine[gWordAt+k]&255) : k=k+1
 Wend
 PrintN(", so nothing was done.")
 PrintN("  Type help, or just a question mark, for the list of commands.")
 PrintN("  Every command is a whole word; the old single letters still work.")
EndProcedure

; 1 completes one command line; 0 is an explicit board/session stop.
Procedure.i AnvilCommandStep()
 Protected c.i
 If HwCommandLoopHook(#ACMD_BEFORE_PROMPT)=0 : ProcedureReturn 0 : EndIf
 ; Protocol bytes: exact lower-case spelling, trailing space, no newline.
 Print("pmf> ")
 If HwCommandLoopHook(#ACMD_AFTER_PROMPT)=0 : ProcedureReturn 0 : EndIf
 If HwCommandLoopHook(#ACMD_BEFORE_INPUT)=0 : ProcedureReturn 0 : EndIf
 ReadLine()
 If HwCommandLoopHook(#ACMD_AFTER_INPUT)=0 : ProcedureReturn 0 : EndIf
 c=AnvilCommandPrepare()
 If c<>0
  If HwCommandDispatch(c)=0 : AnvilCommandUnknown() : EndIf
 EndIf
 TimeReport()
 If HwCommandLoopHook(#ACMD_AFTER_COMMAND)=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure AnvilCommandLoop()
 While AnvilCommandStep()<>0
 Wend
EndProcedure
