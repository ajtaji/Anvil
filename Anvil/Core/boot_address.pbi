; ----------------------------------------------------------------------
;  BootDirty - the same guard `run` uses: never boot a half-arrived image.
;  Returns 1 (and prints) when the last load was dirty, 0 when it is clean.
; ----------------------------------------------------------------------
Procedure.i BootDirty()
  If gBad > 0 Or gFail <> 0
    PrintN("!! the last image did not arrive cleanly, so nothing was booted. What")
    PrintN("   is in memory is part of a program and part of whatever was there")
    PrintN("   before, and booting that is how a board wedges with no explanation.")
    PrintN("   Load the image again, all the way through, first.")
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; gBootAddrOk - set by BootDefaultAddr: 1 if the address is usable, 0 if the
; number was too long (in which case BootDefaultAddr has already printed and
; the caller must return). A global rather than a by-reference argument
; because this language has no .Integer structure pointer; gParseOver next to
; it is a global for the same reason.
Global gBootAddrOk.i

; ----------------------------------------------------------------------
;  BootDefaultAddr - the address argument, or its default: the entry point of
;  the last load if we have one, else the base of the low payload window -
;  exactly what `run` defaults to (Anvil/Core/memcmd.pbi CmdGo). Returns the
;  address; sets gBootAddrOk to 0 (and prints) only on a too-long number.
; ----------------------------------------------------------------------
Procedure.i BootDefaultAddr()
  Define a.i
  gBootAddrOk = 1
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was booted.")
      gBootAddrOk = 0
      ProcedureReturn 0
    EndIf
    If gHaveEntry <> 0
      a = gEntry
    Else
      ; THE BOARD'S STAGING ADDRESS, NOT #PAY0_LO - 2026-09-08. It is the
      ; same address on this board today; what changed is that it FOLLOWS
      ; THE MONITOR'S SIZE instead of being a constant, so a default that
      ; read the constant would one day name an address inside the
      ; monitor. HwStageAddr() is the one place that answer is worked out.
      a = HwStageAddr()
    EndIf
  EndIf
  ProcedureReturn a
EndProcedure
