Procedure CmdCoreTest()
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If gWordLen = 0
    CmdCoreAcceptStatus()
  Else
    SkipSpace()
    If gLine[gPos] <> 0
      PrintN("? coretest takes exactly run, stop, status, or no argument.")
    ElseIf WordIs("run") <> 0
      CmdCoreAcceptRun()
    ElseIf WordIs("stop") <> 0
      CmdCoreAcceptStop()
    ElseIf WordIs("status") <> 0
      CmdCoreAcceptStatus()
    Else
      PrintN("? coretest takes run, stop, status, or no argument.")
    EndIf
  EndIf
EndProcedure
