
; ======================================================================
;  addrsafe.pi4 - the core side of the address-safety seam.
;
;  THE PROBLEM THIS EXISTS FOR, stated as it was found and not as it was
;  theorised. On one of Anvil's targets an MMIO access to a block whose
;  clock is gated does not fault, does not time out, and does not return
;  a bus-error pattern: it STALLS THE INTERCONNECT. The processor never
;  retires the instruction, the console stops mid-line, the network stops
;  answering, and the only way out is somebody physically removing power.
;  It happened three times in two days. The first one was a single
;  command - a plain read of one 32-bit register, typed at this prompt -
;  and the board's own transcript names it exactly, because the log is
;  flushed after every command and the command after that one has no echo
;  in it at all.
;
;  WHY NO DRIVER GUARD COULD HAVE HELPED. The driver for that block had a
;  presence check and it was correct. It never ran. `memory <address>`
;  goes straight to the address; that is what it is FOR. A guard that
;  lives inside a driver protects nothing from a command that does not
;  call the driver, and every raw memory command in this monitor is
;  exactly such a command.
;
;  WHY THE ANSWER IS NOT "THE CORE KNOWS THE BAD ADDRESSES". Anvil is one
;  core across many boards and the core names no chip - that rule is the
;  reason the Pi 4 and this second target share every file in this
;  directory. Which apertures are gated is chip knowledge AND firmware
;  knowledge: the same silicon under a different boot chain gates a
;  different set. So the core asks and the BOARD answers, through
;  HwAddrCheck() in Anvil/Hal/hal.pbi. This file is the asking side, and
;  it contains no address of any kind.
;
;  IT IS THE HwMonLo()/HwMonHi() SHAPE, ONE STEP FURTHER ON. That pair
;  already exists for exactly this reason: the core used to assume where
;  the monitor lived, the assumption was a fiction on the second board,
;  and the fix was to ask. The monitor-overlap refusal that came out of
;  it is the model for the refusal below - it names the region, says what
;  would have happened, and says plainly that nothing was done.
;
; ----------------------------------------------------------------------
;  WHAT THE CORE DOES WITH EACH OF THE FOUR ANSWERS
; ----------------------------------------------------------------------
;    SAFE       proceed. Nothing is printed - a guard that announces
;               itself on every ordinary command trains people to stop
;               reading it.
;
;    UNCLOCKED  refuse, naming the block and its extent, and say what
;               would have happened. This is a MEASURED fact about the
;               machine, not a policy, and the message says which.
;
;    ABSENT     refuse, saying there is nothing at that address at all
;               and where the space it is in runs. Added 2026-09-17,
;               when a board first learned how much memory is fitted to
;               it. It is the OPPOSITE of UNKNOWN and shares none of its
;               prose: this refusal is knowledge, and the reason it
;               matters is that the access COMPLETES - it comes back
;               with whatever the bus left on the wire, which prints as
;               data and reads as truth. The board's fragment names the
;               size, so the operator is told which board he is on in
;               the same breath.
;
;    UNKNOWN    refuse, and say that the refusal is ignorance rather than
;               knowledge - because those are very different things to an
;               operator and a monitor that blurs them is lying by tone.
;               Then say exactly how to go ahead anyway.
;
;  BOTH REFUSALS CAN BE OVERRIDDEN, and that is deliberate. Anvil is a
;  debugger. memcmd.pi4 has said since it was written that "being able to
;  point it at anything is most of its value" and that reading an address
;  with no device behind it is "a real risk and it is accepted, because
;  the alternative is a debugger that refuses to look at the thing you
;  are debugging". That is still true. What was wrong before was not that
;  the risk was accepted - it is that it was accepted SILENTLY, by an
;  operator who had no way to know which addresses carried it. A monitor
;  that cannot be told to go ahead is also a monitor that can never bring
;  a gated block UP, which is a thing this project's own workers need to
;  do on purpose.
;
; ----------------------------------------------------------------------
;  THE OVERRIDE, AND WHY IT IS TWO LINES AND NOT A FLAG
; ----------------------------------------------------------------------
;  The requirement was that a one-shot script must not be able to pass
;  the confirmation BY ACCIDENT. That rules out a suffix or a flag word:
;  a script assembled by pasting lines together, or written against the
;  old behaviour by somebody who added `force` everywhere once to make a
;  batch run, passes a flag without anybody deciding anything. It also
;  rules out prompting for a typed answer, because on one of these boards
;  the whole session can be a staged script with no reader at the other
;  end, and a confirmation nothing can answer is not a confirmation - it
;  is a hang.
;
;  So the override is a separate command that names the address AGAIN:
;
;      force <address>          arms exactly that one address
;      <the command>            ... for exactly the next command line
;
;  It cannot be reached by accident because the address has to be written
;  twice, under two different command words, on two consecutive lines. It
;  CAN be reached on purpose from a script, which is right - the person
;  writing those two lines has decided.
;
;  IT EXPIRES AFTER ONE COMMAND LINE. gForceAge is bumped by the
;  dispatcher on every line, beside the gMemWidth reset and for the same
;  reason written there: state that leaks from one command into the next
;  is a trap. An arm left standing from ten commands ago that quietly
;  authorises the eleventh is precisely the accident this is supposed to
;  prevent.
;
;  IT IS AN EXACT MATCH ON THE START ADDRESS. Arming $04AC0004 does not
;  arm $04AC0000, and does not arm a range that merely contains it. An
;  override that widened itself would be back to being a flag.
; ======================================================================

; WHAT IS ARMED. gForceOn is 0 or 1; gForceAt is meaningless when it is 0
; and is deliberately not initialised to an address that would look
; plausible if it were read out of turn - the same discipline as
; memrange.pi4's gMonHitLo/gMonHitHi.
Global gForceOn.i
Global gForceAt.i
Global gForceAge.i

; ----------------------------------------------------------------------
;  ForceAge() - called once per command line by the dispatcher, in the
;  same block as the gMemWidth reset.
;
;  The line that RUNS `force` sets gForceAge to 0, so this bumps it to 1
;  at the end of that line and the arm survives. The next line bumps it
;  to 2 and the arm is gone, whether it was used or not. One line, no
;  more, and no dependence on the command having called the guard at all
;  - a mistyped command in between does not silently extend the window.
; ----------------------------------------------------------------------
Procedure ForceAge()
  If gForceOn = 0
    ProcedureReturn
  EndIf
  gForceAge = gForceAge + 1
  If gForceAge >= 2
    gForceOn = 0
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  AddrForceArmedFor(lo) - 1 if the override is armed for exactly this
;  start address, else 0. It changes nothing.
;
;  IT IS A PROCEDURE OF ITS OWN, and not two conditions inline in
;  AddrAllowed, for one reason: it is the only part of this mechanism
;  that can be EXECUTED BY A GATE. Everything around it prints, and
;  printing means a console, which means a device model. This is pure -
;  two comparisons on two globals - so tools/a64/a64_anvil_check.py runs
;  it on the real built image and proves the arm matches the address it
;  was given, does not match its neighbours, and is gone after two
;  ForceAge() calls. A confirmation step nothing can test is a
;  confirmation step nobody should trust.
;
;  EXACT MATCH ON THE START ADDRESS. Not "contains", not "overlaps".
; ----------------------------------------------------------------------
Procedure.i AddrForceArmedFor(lo.i)
  If gForceOn = 0
    ProcedureReturn 0
  EndIf
  If gForceAt <> lo
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  PutForceHow(lo) - the two lines that tell the operator how to go
;  ahead anyway. Printed by both refusals, with the address they would
;  have to arm, so the answer to "then how do I look at it" is on the
;  screen at the moment the question occurs rather than in the help text.
; ----------------------------------------------------------------------
Procedure PutForceHow(lo.i)
  PrintN("   If you have a reason to touch it anyway, type")
  Print("       force ")
  PutAddr(lo)
  PrintNl()
  PrintN("   and then repeat the command on the very next line. That arms this")
  PrintN("   one address for one command and nothing else. Typing the address")
  PrintN("   twice is the confirmation - there is no flag, because a flag is")
  PrintN("   something a script can carry without anybody having decided.")
EndProcedure

; ----------------------------------------------------------------------
;  AddrAllowed(lo, hi, forWrite, *cmd, *nothing) - THE GUARD.
;
;  lo..hi     the inclusive byte range the command is about to touch,
;             AFTER base has been added, so what is checked is what will
;             actually be accessed.
;  forWrite   1 if the command will write into that range, 0 if it will
;             only read it.
;  *cmd       the command word for the message - "memory", "fill".
;  *nothing   a past-participle fragment that reads after "Nothing was ",
;             so each command's refusal ends in its own verb: "dumped",
;             "written", "copied", "compared", "computed", "tested".
;
;  RETURNS 1 to proceed and 0 to stop, exactly like GpioWriteAllowed()
;  and RequireCap(), so a call site is one If and an early return.
;
;  BOTH STRING ARGUMENTS ARE POINTERS and are printed with UartWriteStr,
;  never Print - Print picks its formatter from the argument TYPE and an
;  untyped pointer is not a .s, so Print(*cmd) would print the address in
;  decimal. The trap is documented at RequireCap and at PutClockRow; this
;  is it avoided once more.
; ----------------------------------------------------------------------
Procedure.i AddrAllowed(lo.i, hi.i, forWrite.i, *cmd, *nothing)
  Define code.i
  Define blo.i
  Define bhi.i
  Define *why

  code = HwAddrCheck(lo, hi, forWrite)
  If code = #HW_ADDR_SAFE
    ProcedureReturn 1
  EndIf

  ; The board's account of what it matched, read BEFORE anything else can
  ; call the seam again - hal.pi4 says these are valid only immediately
  ; after the check that was not SAFE.
  *why = HwAddrReason()
  blo = HwAddrBlockLo()
  bhi = HwAddrBlockHi()

  ; ---- the override, if it is armed for exactly this start address ----
  If AddrForceArmedFor(lo) <> 0
    gForceOn = 0                  ; consumed, whatever happens next
    Print("   forced: ")
    PutAddr(lo)
    Print(" was armed by force, so ")
    UartWriteStr(*cmd)
    PrintN(" is going ahead.")
    If code = #HW_ADDR_UNCLOCKED
      PrintN("   This block is KNOWN not to answer. If the board stops here, that")
      PrintN("   is what happened, and it needs the power removing - no reset")
      PrintN("   command can reach a processor that is stalled on a bus access.")
    ElseIf code = #HW_ADDR_ABSENT
      PrintN("   There is KNOWN to be nothing there. Whatever comes back is not")
      PrintN("   the contents of anything, and it will look exactly like data.")
    Else
      PrintN("   Nothing is known about this address either way. If the board stops")
      PrintN("   here, that is what happened.")
    EndIf
    UartDrain()
    ProcedureReturn 1
  EndIf

  ; ---- the refusal ----------------------------------------------------
  Print("!! ")
  UartWriteStr(*cmd)
  Print(" was refused: ")
  PutAddr(lo)
  If hi <> lo
    Print(" .. ")
    PutAddr(hi)
  EndIf
  PrintNl()
  If code = #HW_ADDR_UNCLOCKED
    Print("   is inside ")
    UartWriteStr(*why)
    PrintN(".")
    If blo <> 0 Or bhi <> 0
      Print("   That block runs ")
      PutAddr(blo)
      Print(" to ")
      PutAddr(bhi)
      PrintN(".")
    EndIf
    Print("   Nothing was ")
    UartWriteStr(*nothing)
    PrintN(". This is not caution and it is not a policy:")
    PrintN("   this board has measured that block and reports it cannot answer a")
    PrintN("   bus access right now. On this machine that is not an error - the")
    PrintN("   access never completes, the processor stops on it, and the board")
    PrintN("   has to have its power removed by hand.")
  ElseIf code = #HW_ADDR_ABSENT
    ; THE SENTENCE READS AFTER "is ", not after "is inside ". Nothing
    ; contains this address - that is the whole finding - so the board's
    ; fragment is a position ("above the 4 GB of RAM this board has")
    ; rather than the name of a block.
    Print("   is ")
    UartWriteStr(*why)
    PrintN(".")
    If blo <> 0 Or bhi <> 0
      Print("   That space runs ")
      PutAddr(blo)
      Print(" to ")
      PutAddr(bhi)
      PrintN(".")
    EndIf
    Print("   Nothing was ")
    UartWriteStr(*nothing)
    PrintN(". THIS REFUSAL IS KNOWLEDGE, NOT IGNORANCE:")
    PrintN("   the board asked how much memory is fitted and this address is")
    PrintN("   past it. Reading it would not stop the board - it would answer")
    PrintN("   with whatever the bus left on the wire, which is the worse")
    PrintN("   outcome: a plausible value under a heading that says memory is")
    PrintN("   indistinguishable from the truth, and a stop at least announces")
    PrintN("   itself. info says what the size is and where it came from.")
  Else
    Print("   is not in anything this board can vouch for")
    If *why <> 0
      PrintNl()
      Print("   - ")
      UartWriteStr(*why)
      PrintN(".")
    Else
      PrintN(".")
    EndIf
    Print("   Nothing was ")
    UartWriteStr(*nothing)
    PrintN(". THIS REFUSAL IS IGNORANCE, NOT KNOWLEDGE: the")
    PrintN("   board has no entry for this address, so it will not claim the")
    PrintN("   access is safe and it will not claim it is dangerous. It says so")
    PrintN("   rather than guessing, because a guess in either direction reads")
    PrintN("   exactly like a fact.")
  EndIf
  PutForceHow(lo)
  PrintN("   info lists what this board does know, and where each answer came")
  PrintN("   from.")
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  CmdForce - the override command.
;
;    force <address>     arm that one address for the next command line
;    force               say what is armed
;    force off           disarm
;
;  IT ARMS AND IT DOES NOTHING ELSE. It reads no memory, so typing it at
;  an address that would stall the bus is itself completely safe - which
;  matters, because the operator is by definition about to do something
;  they have been warned about and the arming step must not be the thing
;  that bites.
; ----------------------------------------------------------------------
Procedure CmdForce()
  Define a.i
  Define at.i

  ; THE ARGUMENT IS TAKEN AS A WHOLE WORD FIRST, and only then read as
  ; hex, because the two disarm spellings are not all non-hex: `clear`
  ; begins with a c, and a bare ParseHex() would happily read that as the
  ; address $C and arm it. Arming the wrong address because the operator
  ; asked to disarm is the exact opposite of what this command is for.
  SkipSpace()
  gWordAt = gPos
  at = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  If gWordLen <> 0 And (WordIs("off") <> 0 Or WordIs("clear") <> 0 Or WordIs("none") <> 0)
    If gForceOn = 0
      PrintN("Nothing was armed, so nothing was disarmed.")
    Else
      Print("Disarmed ")
      PutAddr(gForceAt)
      PrintN(". It will not be waved through now.")
      gForceOn = 0
    EndIf
    ProcedureReturn
  EndIf

  If gWordLen <> 0
    gPos = at                     ; rewind and read that same word as hex
    a = ParseHex()
    ; THE WHOLE WORD MUST BE THE ADDRESS. ParseHex stops at the first
    ; character that is not a hex digit and reports success on what it
    ; got, so "4AC0004x" would arm $4AC0004 and say nothing about the x.
    ; Every other command in this monitor tolerates that; this one must
    ; not, because it is the confirmation step and a confirmation that
    ; quietly reinterprets what was typed is not one.
    If gParseOk <> 0 And gPos = at + gWordLen
      gForceOn = 1
      gForceAt = a
      gForceAge = 0
      Print("Armed ")
      PutAddr(a)
      PrintN(" for the NEXT command line only.")
      PrintN("  Repeat the refused command now. If you type anything else first,")
      PrintN("  this expires and the refusal comes back - which is the point.")
      PrintN("  Nothing has been read or written; force only arms.")
      ProcedureReturn
    EndIf
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was armed.")
    Else
      PrintN("!! force takes one whole hexadecimal address and nothing else, and")
      PrintN("   that is not one, so nothing was armed. It has to be exactly the")
      PrintN("   address the refused command starts at.")
    EndIf
    ProcedureReturn
  EndIf

  ; A bare `force` - report and explain.
  If gForceOn <> 0
    Print("Armed: ")
    PutAddr(gForceAt)
    PrintN(", for the next command line only.")
  Else
    PrintN("Nothing is armed.")
  EndIf
  PrintN("force <address>")
    PrintN("  arm ONE address so that the next command line may touch it even")
    PrintN("  though this board refused it. The address is hex and must be the")
    PrintN("  same one the refused command starts at, exactly - arming 4AC0004")
    PrintN("  does not arm 4AC0000 and does not arm a range that contains it.")
    PrintN("  It lasts for one command line and then expires, used or not.")
    PrintN("  Why two lines and not a flag on the command: a flag is something a")
    PrintN("  script can carry without anybody having decided, and the whole")
    PrintN("  point of this is that somebody decided. force off disarms early.")
EndProcedure
