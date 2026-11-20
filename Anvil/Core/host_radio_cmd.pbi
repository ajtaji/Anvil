; Monitor commands for a board whose physical radios belong to a host.
; The board owns transport, asynchronous completion and device discovery.
Procedure AnvilCmdHostRadio(bluetooth.i)
 Protected op.i,arg.i
 SkipSpace()
 If gLine[gPos]=0
  op=1
 Else
  gWordAt=gPos : SkipWord() : gWordLen=gPos-gWordAt
  If WordIs("status") : op=1
  ElseIf WordIs("scan") : op=2
  ElseIf WordIs("result") : op=5
  ElseIf bluetooth=0 And WordIs("profiles") : op=3
  ElseIf bluetooth<>0 And WordIs("devices") : op=3
  ElseIf bluetooth=0 And WordIs("join") : op=4
  ElseIf bluetooth<>0 And WordIs("pair") : op=4
  EndIf
  arg=ArgRest()
  If op=4 And arg=0 : op=0 : EndIf
  If op<>4 And arg<>0 : op=0 : EndIf
 EndIf
 If op=0
  If bluetooth
   PrintN("Use bt status, scan, devices, pair AA:BB:CC:DD:EE:FF, or result.")
  Else
   PrintN("Use wifi status, scan, profiles, join <Windows profile>, or result.")
  EndIf
  ProcedureReturn
 EndIf
 HwHostRadioCommand(bluetooth,op,arg)
EndProcedure
