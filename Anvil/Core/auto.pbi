
; ======================================================================
;  a - autoboot, and the boot delay it exists for.
;      See AUTOBOOT in the header for the record's layout and for why
;      it cannot be a Global.
; ======================================================================

Procedure CmdAuto()
  Define a.i
  Define e.i
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Autoboot is unchanged.")
      ProcedureReturn
    EndIf
    ; Bare autoboot - report.
    e = AutoEntry()
    If e = 0
      PrintN("Autoboot is not armed, so this monitor goes straight to its prompt")
      PrintN("when it starts and runs nothing by itself.")
      PrintN("  Type autoboot <address> to arm it.")
    Else
      Print("Autoboot is armed at ")
      PutAddr(e)
      PrintN(". About two seconds after the banner")
      PrintN("the monitor will jump there unless a key is pressed first.")
      PrintN("  Type autoboot 0 to clear it.")
    EndIf
    ProcedureReturn
  EndIf
  If a = 0
    AutoSet(0)
    PrintN("Autoboot is cleared. This monitor will now go straight to its prompt")
    PrintN("when it starts and run nothing by itself.")
    ProcedureReturn
  EndIf
  If HitsMonitor(a, a) <> 0
    Print("!! ")
    PutAddr(a)
    PrintN(" is inside the monitor itself, so autoboot was not")
    Print("   armed and is unchanged. The monitor lives at ")
    PutAddr(gMonHitLo)
    Print(" to ")
    PutAddr(gMonHitHi)
    PrintN(";")
    PrintN("   jumping in there on every start would wedge the board on every")
    PrintN("   start, with no prompt to type the fix at. Point it at a payload.")
    ProcedureReturn
  EndIf
  AutoSet(a)
  Print("Autoboot is armed at ")
  PutAddr(a)
  PrintN(". About two seconds after the next")
  PrintN("banner the monitor will jump there unless a key is pressed first.")
  PrintN("  Type autoboot 0 to clear it. The setting lives in DRAM and survives")
  PrintN("  a reset, but not a power cycle.")
EndProcedure

Procedure BootWait()
  ; NOTHING ARMED MEANS NO DELAY AT ALL. A countdown whose only possible
  ; outcome is "carry on to the prompt" costs two seconds on every start
  ; and teaches people to ignore it, which is exactly how a real
  ; countdown gets missed later. U-Boot with an empty bootcmd does the
  ; same thing. This is also the SAFE default: on a cold board the
  ; record is whatever DRAM happened to hold, it fails the magic and the
  ; guard, and the monitor drops to a prompt.
  Define e.i
  Define t0.i
  Define hz.i
  Define quarter.i
  Define dots.i
  Define c.i

  e = AutoEntry()
  If e = 0
    ProcedureReturn
  EndIf

  ; CHECKED AGAIN HERE, not only when it was armed. The record lives in
  ; DRAM across a reset, so "it was refused at the prompt" is not a
  ; promise about what is in those bytes now.
  If HitsMonitor(e, e) <> 0
    Print("!! the autoboot setting points at ")
    PutAddr(e)
    PrintN(", which is inside the monitor")
    PrintN("   itself. Jumping there would wedge the board, so it is being ignored")
    PrintN("   and cleared, and the prompt follows as usual. The setting lives in")
    PrintN("   DRAM across a reset, so it can be corrupted by something else; that")
    PrintN("   is why it is checked again here and not only when it was armed.")
    AutoSet(0)
    ProcedureReturn
  EndIf

  Print("Autoboot will jump to ")
  PutAddr(e)
  PrintN(" in about two seconds.")
  Print("Press any key now to stop it and get a prompt instead ")

  hz = TickHz()
  If hz <= 0
    hz = 54000000
  EndIf
  ; Ticks, not millis(): a divide per pass is pointless here and the
  ; whole point of counting CNTPCT_EL0 is that the answer does not move
  ; when c changes the ARM clock.
  t0 = Ticks()
  quarter = (hz * #BOOT_DOT) / 1000
  dots = 0
  c = 0
  While (Ticks() - t0) < ((hz * #BOOT_MS) / 1000)
    If UartReadReady() <> 0
      ; CONSUMED, deliberately. Left in the FIFO it would become the
      ; first character of the first command.
      c = UartRead()
      PrintNl()
      PrintN("Stopped by a keypress. Autoboot is still armed - type autoboot to see")
      PrintN("where it points, or autoboot 0 to clear it.")
      ProcedureReturn
    EndIf
    If (Ticks() - t0) > (quarter * (dots + 1))
      UartWrite(46)
      dots = dots + 1
    EndIf
  Wend

  PrintNl()
  RunAt(e)
EndProcedure
