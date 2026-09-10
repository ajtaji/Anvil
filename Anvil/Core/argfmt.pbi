
; ======================================================================
;  SETTINGS AND WI-FI - the commands over Lib/settings.pi4
; ======================================================================
;  settings.pi4 is a thirty-two key KEY=VALUE store held in DRAM and
;  persisted as plain KEY=VALUE text in SETTINGS.TXT in the root of
;  partition 1 of the boot medium. It was written, committed and
;  gate-proven (177 assertions on the A64 oracle, twelve deliberate
;  defects each watched turning it red) and NO COMMAND REACHED IT. This
;  section is that wiring. Read settings.pi4's header before changing
;  anything here; every rule below is its rule and not one invented at
;  this end.
;
;  THREE TRAPS, ALL OF WHICH THIS FILE HAS FALLEN INTO BEFORE
;  ---------------------------------------------------------
;  1. EVERY STRING settings.pi4 RETURNS IS AN .i POINTER. SettingsGet,
;     SettingsKeyAt, SettingsValueAt, SettingsErrorText,
;     SettingsMaskText, SettingsFileName and the two Wi-Fi key names are
;     all addresses. Print() picks its formatter from the argument's
;     TYPE and an untyped pointer is not a .s, so Print() of any of them
;     prints the ADDRESS IN DECIMAL and says nothing about it. That is
;     the exact bug PutClockRow carries a warning about, and the one
;     that printed "!! no card: 25246364" at UsbDiskUp. UartWriteStr,
;     every single time.
;  2. THE BLOCK WRITER IS ARMED FOR ONE CALL AND DISARMED ON EVERY PATH
;     OUT, including the failures. settings.pi4 never calls
;     FatSetBlockWriter itself (deliberately - settings.pi4:305-314), so
;     with none installed SettingsSave is inert. CmdSettingsSave below
;     follows CmdSave exactly. A writer left armed is how a later bug in
;     an unrelated command reaches the boot medium.
;  3. SECRETS ARE MASKED BY DEFAULT AND THE REASON IS THIS BOARD.
;     Anvil's output does not only go to a serial terminal in front of
;     the person typing: it goes to an HDMI console on a screen in a
;     room, and `screenshot` ships that framebuffer over the wire. A
;     default that puts a passphrase on glass, and into the next
;     screenshot somebody takes for an unrelated bug, is wrong.
;     SettingsIsSecret() decides - any key whose name contains
;     "password", "passphrase" or "secret" (settings.pi4:1146-1169) -
;     and `settings reveal <name>` is the deliberate keystroke that
;     prints one anyway.
;
;  WHY NOTHING LOADS THE SETTINGS BY ITSELF
;  ----------------------------------------
;  Neither Banner() nor `settings show` touches the medium. Two reasons,
;  and the first is the one that decided it:
;
;    * BRINGING THE MEDIUM UP IS NOT FREE OR QUIET. StorageUp() walks
;      PCIe, xHCI, the USB descriptors and SCSI, prints eight lines
;      doing it, and takes real time. Putting that in the startup path
;      would delay the prompt - and the prompt is the thing you need
;      most when something is wrong - for a file that on most boots has
;      nothing in it anybody is waiting for.
;    * settings.pi4's own rule is that a load happens when the caller
;      asks and never otherwise (its header, DELIBERATELY LEFT OUT).
;
;  So `settings` shows what is in memory and SAYS whether anything has
;  ever been read off the medium in this session. An empty table that
;  does not explain itself would be indistinguishable from a lost file,
;  which is the report settings.pi4 spends a page refusing to give.
; ======================================================================

; The length of a NUL-terminated string at an address. There is one in
; settings.pi4 - set_Len - and it is private, correctly: a library's
; internals are not the monitor's to reach into. Six lines is cheaper
; than a seam.
Procedure.i StrLenZ(a.i)
  Define n.i
  If a = 0
    ProcedureReturn 0
  EndIf
  n = 0
  While PeekA(a + n) <> 0
    n = n + 1
  Wend
  ProcedureReturn n
EndProcedure

; ----------------------------------------------------------------------
;  SubstrFound - 1 if `needle` occurs anywhere in `hay`, both
;  NUL-terminated. Case-sensitive.
;
;  string.pi4 has FindString, but that library is NOT built into the
;  monitor (board.pi4 does not include it - a monitor is not a text
;  processor), so this is the ten lines that do the one thing `env grep`
;  needs rather than pulling a whole string library into the image. It
;  never reads past either NUL: the inner scan stops the moment hay's
;  terminator fails to match a needle character.
; ----------------------------------------------------------------------
Procedure.i SubstrFound(hay.i, needle.i)
  Define i.i
  Define j.i
  Define nc.i
  If needle = 0 Or hay = 0
    ProcedureReturn 0
  EndIf
  If PeekA(needle) = 0
    ProcedureReturn 1                ; an empty needle is in everything
  EndIf
  i = 0
  While PeekA(hay + i) <> 0
    j = 0
    Repeat
      nc = PeekA(needle + j)
      If nc = 0
        ProcedureReturn 1            ; needle ran out first - it matched
      EndIf
      If PeekA(hay + i + j) <> nc    ; hay's NUL (0) never equals nc here
        Break
      EndIf
      j = j + 1
    ForEver
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

; Print a NUL-terminated string and pad it out to w columns, so a table
; of settings lines up. A name longer than w simply runs past it and the
; row is ragged, which is better than truncating a key name - a name you
; cannot read is a name you cannot type back in.
Procedure PutPadded(a.i, w.i)
  Define n.i
  If a = 0
    ProcedureReturn
  EndIf
  UartWriteStr(a)
  n = StrLenZ(a)
  While n < w
    UartWrite(32)                ; 32 = a space
    n = n + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  ArgWord - the next word on the line, NUL-TERMINATED IN PLACE.
;
;  Returns its address, or 0 when there is no word left. gLine is the
;  line editor's own buffer and ReadLine will overwrite the whole of it
;  before the next command runs, so writing a terminator into it costs
;  nothing - CmdFat does the same thing for the same reason.
;
;  THE SEPARATOR IS STEPPED OVER BEFORE IT IS OVERWRITTEN. Get that
;  order the wrong way round and gPos lands on the NUL this just wrote,
;  every later argument on the line disappears, and the command reports
;  a missing argument that is plainly there.
; ----------------------------------------------------------------------
Procedure.i ArgWord()
  Define at.i
  Define endAt.i
  SkipSpace()
  at = gPos
  SkipWord()
  endAt = gPos
  If endAt = at
    ProcedureReturn 0
  EndIf
  If gLine[gPos] <> 0
    gPos = gPos + 1
  EndIf
  gLine[endAt] = 0
  ProcedureReturn @gLine[at]
EndProcedure

; ----------------------------------------------------------------------
;  ArgRest - EVERYTHING left on the line, as one value.
;
;  A network name may contain spaces and so may a passphrase, so the
;  value of `settings set`, `wifi network` and `wifi password` is the
;  whole rest of the line and not a word. That is a real requirement and
;  not a nicety: "The Smith Family" and "correct horse battery staple"
;  are both ordinary things to have to type.
;
;  TRAILING BLANKS ARE TRIMMED, and this is a kindness with a reason.
;  settings.pi4 refuses a value that begins or ends with a space
;  (#SET_ERR_VALUE_EDGE, settings.pi4:579-586) because such a space
;  would be lost when the file is read back. A trailing space is
;  invisible on a terminal, so without this trim the operator would get
;  a refusal about a character they cannot see. Leading blanks are gone
;  already - SkipSpace ate them - and a value that genuinely needs to
;  end in a space cannot be stored by this library at all, so nothing is
;  lost by trimming.
; ----------------------------------------------------------------------
Procedure.i ArgRest()
  Define at.i
  Define e.i
  Define ch.i
  SkipSpace()
  at = gPos
  If gLine[at] = 0
    ProcedureReturn 0
  EndIf
  e = at
  While gLine[e] <> 0
    e = e + 1
  Wend
  Repeat
    If e <= at
      Break
    EndIf
    ch = gLine[e - 1] & $FF
    If ch <> 32 And ch <> 9      ; 32 = a space, 9 = a tab
      Break
    EndIf
    e = e - 1
    gLine[e] = 0
  ForEver
  If e = at
    ProcedureReturn 0
  EndIf
  ProcedureReturn @gLine[at]
EndProcedure
