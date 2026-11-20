Procedure ShotPutHeader()
  Print("SHOT ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_SEQ), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_W), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_H), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_PITCH), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_ROT), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_TIER), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_X0), 16)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_PANELW), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_PANELH), 8)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_BPP), 2)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_SRC), 2)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_WHO), 2)
  Print(" ")
  PutHexN(ScrShotField(#MON_SHOT_OFF_BYTES), 8)
  PrintNl()
EndProcedure

Procedure ShotSayNothing()
  PrintN("!! there is no kept picture to send: the capture area holds no complete")
  PrintN("   capture, so nothing was streamed. Either no run has been captured")
  PrintN("   since this board started, or the last attempt was refused because")
  PrintN("   there was no screen behind the console at the time.")
  PrintN("   shot arm, then boot the payload, gets one. shot now takes one of the")
  PrintN("   screen as it is at this instant, which is what p sends live.")
EndProcedure

Procedure CmdShot()
  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  If gWordLen = 0
    ShotDump()
    ProcedureReturn
  EndIf
  If WordIs("arm") <> 0
    ShotArm(1)
    PrintN("The next payload this board enters will have its last presented frame")
    PrintN("copied into the capture area before anything repaints over it, whether")
    PrintN("or not the payload asks. Read it back afterwards with shot.")
    PrintN("  It is armed for ONE run. Arm it again for the next one - an arm that")
    PrintN("  stayed set would overwrite a picture somebody was still reading.")
    ProcedureReturn
  EndIf
  If WordIs("disarm") <> 0 Or WordIs("off") <> 0
    ShotArm(0)
    PrintN("The capture on return is disarmed. A payload that asks for a capture")
    PrintN("itself still gets one; nothing is taken on its way back.")
    ProcedureReturn
  EndIf
  If WordIs("now") <> 0
    If ScrShotNow(#MON_SHOT_WHO_PAYLOAD, 0) = 0
      PrintN("!! nothing was captured: there is no screen behind the console, or its")
      PrintN("   presented surface does not fit the capture area. Check screen status")
      PrintN("   before trying shot now again.")
      ProcedureReturn
    EndIf
    Print("Kept the screen as it is now; it is picture number ")
    PrintDec(ScrShotField(#MON_SHOT_OFF_SEQ))
    PrintN(".")
    ProcedureReturn
  EndIf
  If WordIs("status") <> 0 Or WordIs("header") <> 0
    ShotStatus()
    ProcedureReturn
  EndIf

  PrintN("? shot takes arm, disarm, now, status, or nothing at all to stream the")
  PrintN("  kept picture, so nothing was done.")
EndProcedure
