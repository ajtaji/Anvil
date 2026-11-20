; THE TRAIL, AS SENTENCES AND AS MACHINE LINES. `last` limits it to the
; newest entries; 0 prints every one held.
Procedure MonTrailSay(which.i, last.i)
  Define n.i
  Define held.i
  Define k.i
  Define code.i
  n = MonTrailCount(which)
  held = n
  If held > #MON_TRAIL_N : held = #MON_TRAIL_N : EndIf
  k = 0
  If last > 0 And held > last
    k = held - last
  EndIf
  While k < held
    code = MonTrailAt(which, k, 0)
    Print("TRAIL ")
    PrintDec(which)
    Print(" ")
    PutHexN(code, 4)
    Print(" ")
    PrintDec(MonTrailAt(which, k, 1))
    Print(" ms  ")
    MonPhaseSay(code)
    PrintNl()
    k = k + 1
  Wend
EndProcedure

; trail - both boots' records, for a host after a boot that stopped.
Procedure CmdTrail()
  PrintN("The boot trail: every step of the configuration half, with its millisecond.")
  If MonTrailValid(#MON_TRAIL_OFF_PREV) = 0
    PrintN("There is no record of a previous boot (a power cut clears it).")
  Else
    Print("The previous boot (boot ")
    PrintDec(MonTrailPrevBoot())
    If MonTrailPrevFinished() <> 0
      PrintN(") FINISHED its configuration half. Its steps (TRAIL 1):")
    Else
      PrintN(") DID NOT FINISH its configuration half. Its steps (TRAIL 1), the last")
      PrintN("one being where it stopped:")
    EndIf
    MonTrailSay(1, 0)
  EndIf
  Print("This boot (boot ")
  PrintDec(MonPhaseBoots())
  PrintN("), TRAIL 0:")
  MonTrailSay(0, 0)
EndProcedure
