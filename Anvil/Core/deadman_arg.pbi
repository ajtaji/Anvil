; Parse the optional watchdog timeout for all monitor targets. Leave the
; original token boundaries available for board-specific diagnostics.
#DEADMAN_REPORT=-2
#DEADMAN_BAD_WORD=-3
#DEADMAN_OFF=-4
Procedure.i DeadmanArgument()
 SkipSpace() : gWordAt=gPos : SkipWord() : gWordLen=gPos-gWordAt
 If gWordLen=0 : ProcedureReturn #DEADMAN_REPORT : EndIf
 If WordIs("off")<>0 : ProcedureReturn #DEADMAN_OFF : EndIf
 gPos=gWordAt
 Protected n.i=ParseDec()
 If gParseOk=0 : ProcedureReturn #DEADMAN_BAD_WORD : EndIf
 If n<0 : ProcedureReturn -1 : EndIf
 ProcedureReturn n
EndProcedure
