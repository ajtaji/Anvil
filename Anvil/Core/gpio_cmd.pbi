; ======================================================================
;  gpio_cmd.pi4 - the `gpio` command. THE DEMONSTRATOR of the capability
;  model, and the first family to ride the HwGpio* seam.
;
;  This file is CORE: it names no chip and touches no register. It asks the
;  board whether it has GPIO at all (RequireCap over #CAP_GPIO), and if so
;  it reports the pins through the HwGpio* seam the board supplies
;  (RaspberryPi4/Board/hw_gpio.pi4 on the Pi 4, over Lib/gpio.pi4). On a
;  board that declares #CAP_GPIO = 0 the same command, compiled from the
;  same bytes, refuses cleanly with the honest sentence RequireCap prints.
;  That degrade - one command, two boards, no fork and no #ifdef - is the
;  whole point of the foundation this file sits on.
;
;  IT READS AND IT WRITES. The read half is a STATUS report: the pin's
;  function, its level, and its pull. The write half drives and reconfigures
;  a pin over the write seam the backend supplies (HwGpioMode / HwGpioWrite /
;  HwGpioToggle). Everything stays chip-free: the core names no register and
;  does not even own the list of pins the board reserves - it asks the seam
;  (HwGpioReservedReason) and prints the sentence the board hands back.
;
;  ARGUMENTS - reads:
;    gpio               the user-header pins - 0..HwGpioUserMax()
;    gpio status        the same, spelled out (status is the default)
;    gpio all           every GPIO line the board has - 0..HwGpioCount()-1
;    gpio status all    the same
;    gpio <n>           just pin n
;    gpio status <n>    the same
;
;  ARGUMENTS - writes (each names one pin, and reports the pad read back):
;    gpio set <n>       drive pin n high  (makes it an output, and says so)
;    gpio clear <n>     drive pin n low   (makes it an output, and says so)
;    gpio toggle <n>    invert an output pin
;    gpio output <n>    set the pin's direction to output
;    gpio input <n>     set the pin's direction to input
;
;  PINS ARE DECIMAL, like clock and unlike the memory commands: a GPIO
;  number is a small decimal quantity written in decimal everywhere it
;  appears - on the header, in the datasheet - and 0x-prefixing one would be
;  a surprise. A leading 0x or $ still forces hex, exactly as ParseDec does
;  for clock.
;
;  SAFETY. A write to a pin the board itself is using is REFUSED, with a
;  whole sentence naming the function (the console, the radio), not a silent
;  no-op - reconfiguring the console pin would take this prompt down. The
;  reserved set is the board's to know (HwGpioReservedReason in the backend);
;  reading any pin stays allowed, because diagnostics must be able to look at
;  a reserved pin even though they may not touch it.
;
;  HONEST HARDWARE. After a write the pad is READ BACK and the actual level
;  is reported - what the pin says, not what was asked for - the same
;  convention the status report already follows (an output being fought by an
;  external driver shows its real state, not the intent).
; ======================================================================

; ----------------------------------------------------------------------
;  PutGpioMode - the pin's function as words, from the #HW_GPIO_* code and
;  (for an alternate function) the alt number the board decoded. Padded to
;  a fixed width so the columns line up down a 28-line report.
; ----------------------------------------------------------------------
Procedure PutGpioMode(pin.i)
  Define m.i
  Define alt.i
  m = HwGpioModeGet(pin)
  If m = #HW_GPIO_IN
    Print("input ")
  ElseIf m = #HW_GPIO_OUT
    Print("output")
  ElseIf m = #HW_GPIO_ALT
    alt = HwGpioAltGet(pin)
    ; "ALT" then the number, no space, so it reads ALT0..ALT5 and still
    ; fits the six-column field the input/output words use.
    Print("ALT")
    If alt < 0
      ; The board said ALT but could not name which - report it rather
      ; than printing a plausible wrong number. This should not happen on
      ; a backend whose HwGpioModeGet and HwGpioAltGet agree, and if it
      ; does it is the backend's bug, said out loud.
      Print("?  ")
    Else
      PrintDec(alt)
      Print("  ")
    EndIf
  Else
    ; -1, a bad pin - but the caller has already range-checked, so this is
    ; the "the read itself failed" case, not a typo. Named, not blank.
    Print("  ??  ")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  PutGpioPull - the pull direction as a word, from the #HW_PULL_* code.
; ----------------------------------------------------------------------
Procedure PutGpioPull(pin.i)
  Define p.i
  p = HwGpioPullGet(pin)
  If p = #HW_PULL_NONE
    Print("none")
  ElseIf p = #HW_PULL_UP
    Print("up")
  ElseIf p = #HW_PULL_DOWN
    Print("down")
  Else
    Print("??")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  GpioReportPin - one line: number, function, level, pull.
;
;  The level is READ FROM THE PAD (HwGpioLevelGet -> Lib/gpio.pi4's GPLEV),
;  which is the actual electrical level and not a shadow of what was last
;  written - so an output being fought by an external driver shows its
;  real state. -1 there means the read failed and is named, not shown as 0.
; ----------------------------------------------------------------------
Procedure GpioReportPin(pin.i)
  Define lvl.i
  Print("GPIO ")
  If pin < 10
    UartWrite(32)                     ; 32 = a space, so 0..9 align under 10..
  EndIf
  PrintDec(pin)
  Print("  ")
  PutGpioMode(pin)
  Print("  level ")
  lvl = HwGpioLevelGet(pin)
  If lvl < 0
    Print("?")
  Else
    PrintDec(lvl)
  EndIf
  Print("  pull ")
  PutGpioPull(pin)
  PrintNl()
EndProcedure

; ----------------------------------------------------------------------
;  GpioStatus - the read report. This is the ORIGINAL `gpio` command, now
;  reachable as the default (bare `gpio`), as `gpio status [pin|all]`, and
;  as the old positional `gpio all` / `gpio <n>`. The gate has moved up to
;  CmdGpio so it runs once for every subcommand; this is the report only.
;
;  The parse cursor is positioned by the caller: at end of line for the
;  user-header default, or at the [pin|all] argument for the rest.
; ----------------------------------------------------------------------
Procedure GpioStatus()
  Define lo.i
  Define hi.i
  Define pin.i
  Define count.i

  count = HwGpioCount()

  SkipSpace()
  If gLine[gPos] = 0
    ; No argument: the user-header pins, which is the safe default -
    ; reporting a pin wired to the SD card or the PHY invites poking it.
    lo = 0
    hi = HwGpioUserMax()
    If hi < 0
      ; A board with GPIO but no user header (HwGpioUserMax returned -1).
      ; Do not silently report nothing; say what to type instead.
      PrintN("This board has general-purpose I/O but no user header this command")
      PrintN("knows about, so it will not guess a default range. Type gpio all to")
      PrintN("see every line, or gpio <n> for one, with n in decimal.")
      ProcedureReturn
    EndIf
    Print("The user-header GPIO pins (0 to ")
    PrintDec(hi)
    PrintN("). Type gpio all for every line,")
    PrintN("or gpio <n> for one. The level is the actual pad, read back.")
  Else
    ; An argument. Either the word "all" or a decimal pin number.
    gWordAt = gPos
    SkipWord()
    gWordLen = gPos - gWordAt
    If WordIs("all") <> 0
      lo = 0
      hi = count - 1
      Print("Every GPIO line on this board (0 to ")
      PrintDec(hi)
      PrintN("). The pins above the user")
      PrintN("header drive on-board functions - know what a pin does before you")
      PrintN("touch it. The level is the actual pad, read back.")
    Else
      ; A pin number, in decimal. Reparse from the start of the word.
      gPos = gWordAt
      pin = ParseDec()
      If gParseOk = 0
        If gParseOver <> 0
          PrintN("!! that pin number has too many digits to be a GPIO line, so")
          PrintN("   nothing was reported.")
        Else
          PrintN("!! gpio takes no argument for the user-header pins, the word all")
          PrintN("   for every line, or a single pin number in decimal. That was")
          PrintN("   none of those, so nothing was reported.")
        EndIf
        ProcedureReturn
      EndIf
      If pin < 0 Or pin >= count
        Print("!! this board has GPIO lines 0 to ")
        PrintDec(count - 1)
        Print(", and ")
        PrintDec(pin)
        PrintN(" is not one of")
        PrintN("   them, so nothing was reported.")
        ProcedureReturn
      EndIf
      lo = pin
      hi = pin
    EndIf
  EndIf

  pin = lo
  While pin <= hi
    ; ONE BREAK CHECK PER LINE, at the top, so a stopped report never
    ; leaves half a row on the wire - the same discipline DumpMem uses.
    ; The full report is only 58 lines, but the cost is a UART status read
    ; and the habit is worth keeping for the family that grows this.
    If OutBreak() <> 0
      PrintN("   stopped.")
      ProcedureReturn
    EndIf
    GpioReportPin(pin)
    pin = pin + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  GpioArgPin - parse the ONE decimal pin a write subcommand takes, range
;  check it against the board's line count, and return it - or -1 having
;  printed the honest reason. Shared by set / clear / toggle / input /
;  output so the "no number", "too many digits" and "not a line" messages
;  are written once. Decimal, like the status report and like clock; a
;  leading 0x or $ still forces hex through ParseDec.
; ----------------------------------------------------------------------
Procedure.i GpioArgPin()
  Define pin.i
  Define count.i
  count = HwGpioCount()
  pin = ParseDec()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that pin number has too many digits to be a GPIO line, so")
      PrintN("   nothing was done.")
    Else
      PrintN("!! this needs a pin number, in decimal, and there was not one - so")
      PrintN("   nothing was done. Type gpio for the pins, or help for the syntax.")
    EndIf
    ProcedureReturn -1
  EndIf
  If pin < 0 Or pin >= count
    Print("!! this board has GPIO lines 0 to ")
    PrintDec(count - 1)
    Print(", and ")
    PrintDec(pin)
    PrintN(" is not one of")
    PrintN("   them, so nothing was done.")
    ProcedureReturn -1
  EndIf
  ProcedureReturn pin
EndProcedure

; ----------------------------------------------------------------------
;  GpioWriteAllowed - 1 if the pin may be reconfigured, 0 if the board
;  reserves it. In the reserved case the whole-sentence refusal is printed
;  HERE, naming the function through the string the seam hands back. The
;  core prints the board's reason and knows nothing about which pins those
;  are or why - that is the whole point of the seam. Reading is never gated;
;  this is only ever asked before a write.
; ----------------------------------------------------------------------
Procedure.i GpioWriteAllowed(pin.i)
  Define *why
  *why = HwGpioReservedReason(pin)
  If *why = 0
    ProcedureReturn 1
  EndIf
  Print("!! GPIO ")
  PrintDec(pin)
  Print(" is ")
  UartWriteStr(*why)
  PrintN(".")
  PrintN("   Anvil will not reconfigure a pin the board itself is using, because")
  PrintN("   doing so can take the machine down between one command and the next.")
  PrintN("   Nothing was done. Reading the pin is always allowed - gpio with the")
  PrintN("   pin number shows its function, level and pull.")
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  GpioDrive - gpio set / gpio clear. Driving a pin means it must be an
;  output, so this switches it to output and SAYS SO. The level is STAGED
;  first and the mode set second: on the BCM2711 the GPSET/GPCLR write is
;  remembered while the pin is still an input and takes effect the instant
;  it becomes an output (Lib/gpio.pi4's PinHigh/PinLow note), so this order
;  drives the requested level without the pad glitching through the old one.
;  Then the pad is read back and the ACTUAL level reported.
; ----------------------------------------------------------------------
Procedure GpioDrive(high.i)
  Define pin.i
  pin = GpioArgPin()
  If pin < 0
    ProcedureReturn
  EndIf
  If GpioWriteAllowed(pin) = 0
    ProcedureReturn
  EndIf
  If high <> 0
    HwGpioWrite(pin, 1)                ; stage high
  Else
    HwGpioWrite(pin, 0)               ; stage low
  EndIf
  HwGpioMode(pin, #HW_GPIO_OUT)       ; and drive it - now an output
  Print("GPIO ")
  PrintDec(pin)
  If high <> 0
    Print(" driven high")
  Else
    Print(" driven low")
  EndIf
  PrintN(", and set to output. The pad now reads:")
  GpioReportPin(pin)
EndProcedure

; ----------------------------------------------------------------------
;  GpioToggleCmd - gpio toggle. Invert an OUTPUT. On an input the pad
;  follows the outside world and "invert" has nothing to invert, so a pin
;  that is not already an output is refused rather than silently switched -
;  the direction change is gpio output's job, said out loud. Then the pad
;  is read back.
; ----------------------------------------------------------------------
Procedure GpioToggleCmd()
  Define pin.i
  Define m.i
  pin = GpioArgPin()
  If pin < 0
    ProcedureReturn
  EndIf
  If GpioWriteAllowed(pin) = 0
    ProcedureReturn
  EndIf
  m = HwGpioModeGet(pin)
  If m <> #HW_GPIO_OUT
    Print("!! GPIO ")
    PrintDec(pin)
    PrintN(" is not an output, so there is nothing to invert. toggle")
    PrintN("   flips a pin this monitor is already driving; to start driving one")
    PrintN("   use gpio set or gpio clear, which make it an output. Nothing was done.")
    ProcedureReturn
  EndIf
  HwGpioToggle(pin)
  Print("GPIO ")
  PrintDec(pin)
  PrintN(" toggled. The pad now reads:")
  GpioReportPin(pin)
EndProcedure

; ----------------------------------------------------------------------
;  GpioDir - gpio input / gpio output. The plain direction change; it
;  drives nothing on its own (an output takes whatever level was last
;  staged into GPSET/GPCLR, which the read-back shows). An ALT pin becomes
;  a plain input or output, taking it off its alternate function - which
;  the read-back also shows.
; ----------------------------------------------------------------------
Procedure GpioDir(out.i)
  Define pin.i
  pin = GpioArgPin()
  If pin < 0
    ProcedureReturn
  EndIf
  If GpioWriteAllowed(pin) = 0
    ProcedureReturn
  EndIf
  If out <> 0
    HwGpioMode(pin, #HW_GPIO_OUT)
    Print("GPIO ")
    PrintDec(pin)
    PrintN(" set to output. The pad now reads:")
  Else
    HwGpioMode(pin, #HW_GPIO_IN)
    Print("GPIO ")
    PrintDec(pin)
    PrintN(" set to input. The pad now reads:")
  EndIf
  GpioReportPin(pin)
EndProcedure

; ----------------------------------------------------------------------
;  CmdGpio - the dispatcher. The gate runs FIRST, once, for every
;  subcommand: on a board without #CAP_GPIO this prints the honest "not
;  available" sentence and returns, and nothing below runs - no HwGpio*
;  seam call is reached. Then the first word chooses a subcommand; if it is
;  none of them it is the old positional status form (`gpio all`, `gpio 5`)
;  and nothing that ever worked stops working.
; ----------------------------------------------------------------------
Procedure CmdGpio()
  ; THE GATE, FIRST. The reason is generic to the hardware class, not to
  ; any chip, so this line is the same in the core for every board.
  If RequireCap(#CAP_GPIO, "gpio", "this board exposes no general-purpose I/O pins to Anvil") = 0
    ProcedureReturn
  EndIf

  SkipSpace()
  If gLine[gPos] = 0
    ; No argument at all - the read report over the user header, as it has
    ; always been. status is the default.
    GpioStatus()
    ProcedureReturn
  EndIf

  ; Peek the first word to see whether it is a write subcommand.
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  If WordIs("status") <> 0
    ; gpio status [pin|all] - the read report, the cursor now past the word
    ; so GpioStatus parses any [pin|all] that follows.
    GpioStatus()
  ElseIf WordIs("set") <> 0
    GpioDrive(1)
  ElseIf WordIs("clear") <> 0
    GpioDrive(0)
  ElseIf WordIs("toggle") <> 0
    GpioToggleCmd()
  ElseIf WordIs("output") <> 0
    GpioDir(1)
  ElseIf WordIs("input") <> 0
    GpioDir(0)
  Else
    ; Not a subcommand word, so it is the old positional form: "all" or a
    ; pin number for the status report. Rewind to the start of the word so
    ; GpioStatus re-reads it.
    gPos = gWordAt
    GpioStatus()
  EndIf
EndProcedure
