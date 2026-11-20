; Both pointer providers carry fractions in hundredths of a pixel.
; The caller owns one signed remainder per axis and focus owner.
Procedure.i AnvilMouseStep(raw.i,carry.i)
 Protected total.i,stepPixels.i
 total=PeekI(carry)+raw*gMousePct
 stepPixels=total/100
 PokeI(carry,total-stepPixels*100)
 ProcedureReturn stepPixels
EndProcedure

Procedure AnvilCmdMouse(attached.i)
  Define v.i
  SkipSpace()
  If gLine[gPos] = 0
    Print("mouse sensitivity is ")
    PrintDec(gMousePct)
    PrintN("% of 1:1 (100 = raw counts, 200 = twice as fast).")
    If attached = 0
      PrintN("No mouse is attached yet; the setting still takes effect when one is.")
    EndIf
    PrintN("Type mouse <percent> to change it, e.g. mouse 200.")
    ProcedureReturn
  EndIf
  v = ParseDec()
  If gParseOk = 0
    PrintN("!! mouse wants a whole number of percent, e.g. mouse 150. Nothing")
    PrintN("   was changed.")
    ProcedureReturn
  EndIf
  If v < 10
    v = 10
  EndIf
  If v > 1000
    v = 1000
  EndIf
  gMousePct = v
  Print("mouse sensitivity is now ")
  PrintDec(gMousePct)
  PrintN("% of 1:1.")
EndProcedure
