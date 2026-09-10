
; ======================================================================
;  FLOW AND CONSOLE COMMANDS  -  echo, sleep, version
; ======================================================================
;  The hardware-agnostic corner of U-Boot's command set: the ones that
;  touch no register, no bus and no medium, only the console and the
;  clock. They live in the Anvil core because every board that builds
;  the core gets them for free - there is nothing here for a board to
;  implement.
;
;  Implemented FROM THE REAL U-BOOT SOURCE in RaspberryPi4/Reference,
;  the same rule the memory family was held to:
;
;    echo     v2025.01_cmd_echo.c    do_echo, the whole file.
;    version  v2025.01_cmd_version.c do_version - trimmed to what this
;                                    monitor can HONESTLY say (see below).
;    sleep    U-Boot's do_sleep (cmd/sleep.c, not in this reference set,
;                                    so implemented to its documented
;                                    contract: a delay in seconds).
; ======================================================================

; ----------------------------------------------------------------------
;  echo - args to the console.  cmd_echo.c:do_echo.
;
;  U-BOOT'S EXACT SHAPE. A leading -n suppresses the trailing newline
;  (cmd_echo.c:16-20), and it is honoured ONLY as the first argument,
;  exactly as the C does (it tests argv[1] and nothing else). The words
;  are printed separated by ONE space (cmd_echo.c:23-29, the `space`
;  flag), so runs of spaces between words on the line collapse to one -
;  which is what U-Boot does too, because it rejoins an already-split
;  argv. A bare `echo` prints an empty line; `echo -n` prints nothing.
;
;  NO VARIABLE EXPANSION, and that is a ruling, not a gap. U-Boot's shell
;  expands $name and ${name} before echo ever runs - that is the hush
;  parser's job, not echo's - and this monitor has no shell. `echo $x`
;  prints the three characters, which is the honest thing for a monitor
;  that will not pretend to a variable substitution it does not have.
; ----------------------------------------------------------------------
Procedure CmdEcho()
  Define w.i
  Define newline.i
  Define first.i
  newline = 1
  first = 1
  w = ArgWord()
  ; -n, and only as the very first argument. 45 = '-', 110 = 'n', then
  ; the NUL that ArgWord wrote, so this matches "-n" and not "-newline".
  If w <> 0 And PeekA(w) = 45 And PeekA(w + 1) = 110 And PeekA(w + 2) = 0
    newline = 0
    w = ArgWord()
  EndIf
  While w <> 0
    If first = 0
      UartWrite(32)              ; the single separating space
    EndIf
    UartWriteStr(w)
    first = 0
    w = ArgWord()
  Wend
  If newline <> 0
    PrintNl()
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  sleep - wait a while, and BE INTERRUPTIBLE while doing it.
;
;  U-Boot's do_sleep waits get_timer() ticks and polls ctrlc() so a key
;  can end it (cmd/sleep.c). This board's whole recovery story is that
;  the prompt is still there, so a sleep that could not be broken would
;  be a hang you asked for politely - the same objection that keeps
;  `loop` out. So ANY key ends it, not only Ctrl-C, matching every other
;  long-running thing at this prompt except the screenshot.
;
;  SECONDS, DECIMAL. That is do_sleep's unit. A leading 0x or $ still
;  means hex, the same rule ParseDec follows for `clock`, so the two
;  spellings cannot be confused. Fractions are NOT accepted - U-Boot's
;  fractional sleep needs its string parser and this monitor has one
;  integer argument type - and an unrecognised tail is refused rather
;  than silently truncated.
;
;  A CEILING, SAID OUT LOUD. A day is longer than any bench wait and a
;  number with sixteen digits in it is a typo, so anything over 86400
;  seconds is refused rather than started - a monitor that vanishes for
;  a week on a fat-fingered argument, even a recoverable one, is not
;  helpful. The counter this rides is CNTPCT_EL0, so the wait is real
;  wall-clock time whatever the CPU clock is doing - see rxbreak.pi4.
; ----------------------------------------------------------------------
Procedure CmdSleep()
  Define secs.i
  Define hz.i
  Define start.i
  Define target.i

  secs = ParseDec()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that is more digits than a count of seconds can have. Nothing")
      PrintN("   was waited for.")
      ProcedureReturn
    EndIf
    PrintN("sleep <seconds>")
    PrintN("  wait that many seconds, then return to the prompt. The seconds are")
    PrintN("  decimal - a leading 0x or $ means hex, like clock. Any key ends the")
    PrintN("  wait early. There are no fractional seconds here.")
    ProcedureReturn
  EndIf

  ; A trailing something is a fractional sleep or a typo; either way it
  ; is not what this command does, so it is refused rather than ignored.
  SkipSpace()
  If gLine[gPos] <> 0
    PrintN("!! sleep takes one argument, a whole number of seconds. A fraction")
    PrintN("   or a second word is not accepted - nothing was waited for.")
    ProcedureReturn
  EndIf

  If secs < 0
    PrintN("!! a sleep cannot be for a negative number of seconds, so nothing")
    PrintN("   was waited for.")
    ProcedureReturn
  EndIf
  If secs > 86400
    PrintN("!! that is more than a day. A wait that long at this prompt is almost")
    PrintN("   certainly a typo, so it is refused rather than started. Nothing was")
    PrintN("   waited for. The ceiling is 86400 seconds.")
    ProcedureReturn
  EndIf

  hz = TickHz()
  If hz <= 0
    PrintN("!! this board reports no tick rate, so a timed wait cannot be trusted")
    PrintN("   to be any particular length. Nothing was waited for.")
    ProcedureReturn
  EndIf

  If secs = 0
    ; U-Boot's sleep 0 returns at once. Say so rather than printing
    ; nothing, which the whole output style refuses.
    PrintN("Slept for zero seconds, which is no wait at all.")
    ProcedureReturn
  EndIf

  start = Ticks()
  target = secs * hz
  Print("Sleeping ")
  PrintDec(secs)
  PrintN(" seconds. Press any key to end the wait early.")
  UartDrain()

  While (Ticks() - start) < target
    ; A direct read rather than OutBreak(): OutBreak's message is about a
    ; print that was cut short, and this is not printing anything. The
    ; byte is still EATEN, the same reason OutBreak eats it - otherwise
    ; the next ReadLine picks it up as a command nobody typed.
    If UartReadReady() <> 0
      UartRead()
      Print("Woke after about ")
      PrintDec((Ticks() - start) / hz)
      PrintN(" seconds, because a key was pressed.")
      ProcedureReturn
    EndIf
  Wend

  Print("Done - waited ")
  PrintDec(secs)
  PrintN(" seconds.")
EndProcedure

; ----------------------------------------------------------------------
;  version - what this monitor is.  cmd_version.c:do_version.
;
;  THE BOARD SAYS WHICH BOARD IT IS (forum 575). Every fact below that
;  names a computer - the product name, the processor, the exception
;  level, the pmfc target word, the kind of image - comes from the HwId*
;  seam the board supplies (Anvil/Hal/hal.pbi). Not one of them is a
;  literal in this file any more. It used to say "the Raspberry Pi 4
;  serial monitor" and "for target pi4" as prose, so the second board
;  described a different computer in the first lines an operator read,
;  and worked around it by carrying a whole second copy of this command;
;  a third board would have inherited the same wrong identity again.
;
;  U-Boot's do_version prints its banner and then, if the build recorded
;  them, the compiler and linker version strings (cmd_version.c:22-27).
;  This monitor records NEITHER, and inventing them would be exactly the
;  confident-wrong-answer this project refuses - so version prints what
;  Anvil actually knows about itself and stops. The build line in the
;  header is the reproducible fact; the toolchain that ran it is not
;  stamped into the image, so it is not claimed here.
;
;  THE BUILD NUMBER (forum 586). The version string alone could not tell
;  one build from another: it said "Version 2.0" for every image ever
;  produced, so a board that had just been flashed and a board that had
;  not looked identical from the prompt, and the only way to be sure was
;  to hash the image against the host file. #ANVIL_BUILD is raised by one
;  by every successful build in the IDE (and by `pmfc --bump-build`), so
;  two images are now different at a glance and the difference is a
;  number a person can read out over a phone.
;
;  IT DOES NOT REPLACE THE CONTENT STAMP AND MUST NOT BE READ AS ONE. The
;  number says WHICH build; only a digest says WHAT was built. A number
;  can be reset, frozen with `; pmf:build off`, or carried by a source
;  somebody edited without rebuilding.
;
;  SO THE DIGEST IS PRINTED TOO, AND version COMPUTES IT ITSELF. Until
;  now this command pointed at `info` and `crc32` and left the operator to
;  run two more commands and supply a length nothing on the board would
;  tell them. PutContentStamp() below asks the board for its own image
;  extent and runs the same CRC32 the host runs, so one command answers
;  both halves of "which image am I talking to". Saying both, and saying
;  which is which, is the whole point: a build number offered as an
;  identity would be a confident wrong answer of exactly the kind this
;  monitor refuses elsewhere.
;
;  #ANVIL_BUILD, #ANVIL_BUILD_DATE and #ANVIL_BUILD_TIME are declared in
;  each BOARD file, never here. This is the shared core, and a build
;  number in a library is bumped by every project that includes it - the
;  refusal is PMF-BLD-003. A board file that omits them breaks the build
;  here, loudly, which is the right failure.
; ----------------------------------------------------------------------

; ----------------------------------------------------------------------
;  PutDecPad(v, width) - a non-negative number, zero-padded.
;
;  PrintDec ALONE WOULD LOSE THE LEADING ZERO, and that is not cosmetic.
;  A build at 09:30:45 is written into the source as 093045 and read back
;  as the number 93045, which PrintDec renders as "93045" - five digits
;  where the format says six, so "at 93045 (HHMMSS)" invites the reader to
;  parse it as 9:30:4 and get the wrong minute. A field with a declared
;  width has to be printed at that width.
;
;  Digits above `width` are still printed rather than truncated: a value
;  too wide for its field is visibly wrong, and silently cutting it would
;  be the same lie in the other direction.
; ----------------------------------------------------------------------
Procedure PutDecPad(v.i, width.i)
  Define d.i
  Define k.i
  If v < 0
    UartWrite(45)                    ; '-', so a wrong value is visible
    v = -v
  EndIf
  ; the largest power of ten this field needs
  d = 1
  k = 1
  While k < width
    d = d * 10
    k = k + 1
  Wend
  ; then anything wider than the field
  While v / (d * 10) > 0
    d = d * 10
  Wend
  While d > 0
    UartWrite(48 + ((v / d) % 10))
    d = d / 10
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  The build stamp, printed in ONE place for every board.
;
;  Two renderings of three numbers, and both boards use both, so a change
;  to either lands on every target at once.
;
;  There is now exactly ONE `version` and ONE banner as well (forum 575),
;  so this file is no longer the only shared part of the identity - but
;  the note is kept because it is the reason the shape held while the
;  other half was still forked, and because it is still true: two copies
;  of a stamp drift the first time one of them is edited.
;
;  The board passes its OWN #ANVIL_BUILD / _DATE / _TIME, so nothing here
;  names a board constant and each board still counts its own builds.
; ----------------------------------------------------------------------
Procedure PutBuildIdLine(b.i, d.i, t.i)
  ; Machine-readable, first and alone, like uptime's - so a script
  ; driving the monitor over serial reads the build without parsing
  ; English, and the fields are fixed width so it can slice them.
  Print("build ")
  PrintDec(b)
  Print(" date ")
  PutDecPad(d, 8)
  Print(" time ")
  PutDecPad(t, 6)
  PrintNl()
EndProcedure

Procedure PutBuildStamp(b.i, d.i, t.i)
  Print("  This is build ")
  PrintDec(b)
  Print(" of this board's monitor, made ")
  PutDecPad(d / 10000, 4)
  UartWrite(45)                      ; '-'
  PutDecPad((d / 100) % 100, 2)
  UartWrite(45)
  PutDecPad(d % 100, 2)
  Print(" at ")
  PutDecPad(t / 10000, 2)
  UartWrite(58)                      ; ':'
  PutDecPad((t / 100) % 100, 2)
  UartWrite(58)
  PutDecPad(t % 100, 2)
  PrintN(".")
  PrintN("  The number is raised by one by every successful build, so two images")
  PrintN("  can be told apart from the prompt. It says WHICH build this is, not")
  PrintN("  WHAT is in it - a number can be reset, frozen, or carried by a source")
  PrintN("  somebody edited without rebuilding. The digest below is what is in it.")
EndProcedure

; ----------------------------------------------------------------------
;  PutIdLine() - THE ONE PLACE THIS MONITOR NAMES ITSELF AND ITS BOARD.
;
;  The banner and `version` both print it, so the two cannot describe two
;  different computers - which they did, on the second board, for as long
;  as each carried its own copy of the sentence.
;
;  The board name comes from HwIdBoard() and nothing here knows what it
;  will say. "monitor" rather than "serial monitor": one of the boards
;  this builds for has no serial port at all, and the console paragraph
;  immediately below says what the console actually is on each.
; ----------------------------------------------------------------------
Procedure PutIdLine()
  Print("PureMetal Forge - Anvil, the ")
  UartWriteStr(HwIdBoard())
  PrintN(" monitor. Version 2.0,")
  PrintN("64-bit AArch64, running with no operating system underneath it.")
EndProcedure

; ----------------------------------------------------------------------
;  PutProcessorLine() - the core and the exception level, READ rather
;  than asserted.
;
;  This line used to end "at exception level 2" as prose. It was right on
;  one board by luck and wrong on the other in fact, and a number that is
;  right by luck is exactly the confident wrong answer this monitor
;  refuses everywhere else. HwIdEl() decodes the running processor's own
;  CurrentEL on both boards, so a boot path that one day handed the
;  monitor a different level would move this digit instead of quietly
;  contradicting it.
; ----------------------------------------------------------------------
Procedure PutProcessorLine()
  Print("The processor is a ")
  UartWriteStr(HwIdCpu())
  Print(" in AArch64 at exception level ")
  PrintDec(HwIdEl())
  PrintN(".")
EndProcedure

; ----------------------------------------------------------------------
;  PutContentStamp() - WHAT is in this image, as opposed to which build
;  it is.  Forum 586.
;
;  586 was "version cannot tell one build from another": the command
;  printed the same six fixed lines whatever was flashed, so an old image
;  and a new one were indistinguishable at the prompt and every re-flash
;  had to be verified by some other means. The build number closed half of
;  that - it moves by one on every successful build - and it is a LABEL,
;  not a fingerprint. This is the fingerprint.
;
;  It is the monitor hashing ITSELF: the board says where its image is and
;  how long it is (HwIdImageBase / HwIdImageLen), and the same Crc32Part
;  the `crc32` command and tools/anvil.py use runs over exactly those
;  bytes. Two builds that differ by one instruction differ here; two
;  images that are the same bytes agree here and agree with the host.
;
;  A BOARD THAT CANNOT SAY IS TOLD APART FROM A BOARD THAT SAYS ZERO.
;  HwIdImageLen() answers 0 when the extent is not knowable - the boot
;  medium is not mounted on one board, the firmware would not give up its
;  loaded-image record on the other - and HwIdSayImageWhere() then says
;  the reason in whole sentences. Printing a digest over a guessed extent
;  would be worse than printing none, because it would look like an
;  answer.
;
;  IT IS INTERRUPTIBLE AND A STOPPED ONE PRINTS NOTHING. Same rule as
;  `crc32`: a CRC of part of a range looks exactly like a CRC of all of
;  it. The useful lines are printed BEFORE the digest is computed, so a
;  person who does not want to wait already has everything else.
; ----------------------------------------------------------------------
Procedure PutContentStamp(full.i)
  Define base.i
  Define len.i
  Define crc.i
  Define done.i
  Define chunk.i

  ; The length first and the provenance second. HwIdSayImageWhere() is
  ; allowed to describe the answer the length call just worked out, which
  ; is the ordering rule the I2C clock seam already carries.
  base = HwIdImageBase()
  len = HwIdImageLen()

  If len <= 0 Or base = 0
    PrintN("  This board cannot say how long its own image is, so version can print")
    PrintN("  no digest of it and will not invent one:")
    HwIdSayImageWhere()
    PrintN("  Until that is answerable the build number above is the only thing")
    PrintN("  here that tells two images apart, and a digest has to come from the")
    PrintN("  host that produced the file.")
    ProcedureReturn
  EndIf

  Print("  This monitor's own image is ")
  PrintDec(len)
  Print(" bytes, ")
  PutAddr(base)
  Print(" .. ")
  PutAddr(base + len - 1)
  PrintN(".")
  HwIdSayImageWhere()

  ; ------------------------------------------------------------------
  ;  THE DIGEST IS NOT COMPUTED UNLESS IT IS ASKED FOR, AND THAT WAS
  ;  DECIDED BY MEASURING IT RATHER THAN BY GUESSING.
  ;
  ;  It was unconditional first. On the bench board a crc32 over the
  ;  whole image takes BETWEEN TEN AND TWELVE SECONDS - measured, at the
  ;  prompt, with the caches off as they are at boot - because the loop
  ;  is bitwise and every byte of it is an uncached DRAM read. Adding
  ;  that to every `version` would be the wrong trade: `version` is a
  ;  question a person asks to find out where they are, and one that
  ;  locks the prompt for ten seconds stops being askable.
  ;
  ;  So the SIZE is printed always - and the size alone already tells two
  ;  builds apart, alongside the build number above - and the digest is
  ;  one word away. The exact command is printed with the numbers already
  ;  in it, so nothing has to be looked up or worked out.
  ;
  ;  NO DURATION IS QUOTED HERE. Ten seconds is THIS board's number, at
  ;  this board's boot clock, and a figure like that stated in the shared
  ;  core is the forum-575 defect wearing a different hat.
  ; ------------------------------------------------------------------
  If full = 0
    PrintN("  That size and the build number above are enough to tell two images")
    PrintN("  apart. For the digest that says WHAT is in it, type:")
    Print("    version full        - or crc32 ")
    PutHex8(base)
    UartWrite(32)
    PutHex8(len)
    PrintNl()
    PrintN("  It is not done here unasked because it reads every byte of the")
    PrintN("  image, which is not instant on a board with its caches off.")
    ProcedureReturn
  EndIf

  PrintN("  Working out its crc32 now; press any key to give up on it.")
  UartDrain()

  crc = $FFFFFFFF
  done = 0
  While done < len
    If OutBreak() <> 0
      PrintN("  No digest is printed, because a CRC of part of an image looks")
      PrintN("  exactly like a CRC of all of it and is not one. Type version full")
      PrintN("  again for the whole of it.")
      ProcedureReturn
    EndIf
    chunk = len - done
    If chunk > 65536
      chunk = 65536              ; 64 KiB between break checks, the same
    EndIf                        ; interval the crc32 command uses
    crc = Crc32Part(crc, base + done, chunk)
    done = done + chunk
  Wend
  crc = crc ! $FFFFFFFF

  Print("  Its crc32 is ")
  PutHex8(crc)
  PrintN(", worked out just now over the running code.")
  PrintN("  IEEE 802.3, reflected, polynomial EDB88320 - the same value")
  PrintN("  tools/anvil.py computes on the host, so the two agree independently")
  PrintN("  or they do not. THIS is what says which image you are talking to.")
EndProcedure

; ----------------------------------------------------------------------
;  version [full]
;
;  `full` is the only argument and it means "and work the digest out".
;  A WORD RATHER THAN A FLAG, matching `boot status` / `force off` and
;  everything else here: this monitor has no option parser and inventing
;  one for a single case would be a second way to spell things.
;
;  AN UNRECOGNISED ARGUMENT IS REFUSED, NOT IGNORED. `version -f` or
;  `version fll` silently printing the short form is the shape that got
;  `--fast` refused in the flashing tool: an invocation that looks like
;  the long one and quietly is not.
; ----------------------------------------------------------------------
Procedure CmdVersion()
  Define w.i
  Define full.i

  full = 0
  w = ArgWord()
  If w <> 0
    ; "full", case-insensitively, the | $20 idiom this monitor already
    ; uses for on/off elsewhere. 102 f, 117 u, 108 l, 108 l.
    If (PeekA(w) | $20) = 102 And (PeekA(w + 1) | $20) = 117 And (PeekA(w + 2) | $20) = 108 And (PeekA(w + 3) | $20) = 108 And PeekA(w + 4) = 0
      full = 1
    Else
      Print("!! version takes one optional word and ")
      UartWriteStr(w)
      PrintN(" is not it. Nothing")
      PrintN("   was printed. The word is full, which adds a crc32 over this")
      PrintN("   monitor's own image - bare version prints everything else,")
      PrintN("   including that image's size and the command to hash it.")
      ProcedureReturn
    EndIf
  EndIf

  PutBuildIdLine(#ANVIL_BUILD, #ANVIL_BUILD_DATE, #ANVIL_BUILD_TIME)
  PutIdLine()
  PutBuildStamp(#ANVIL_BUILD, #ANVIL_BUILD_DATE, #ANVIL_BUILD_TIME)
  PutContentStamp(full)
  ; The target word is a CHECKABLE CLAIM about how the image was produced
  ; and it is the worst line in this command to get wrong - somebody
  ; diagnosing a bad image reads it and goes looking where it points. It
  ; is the board's word, never a literal here.
  Print("  Built by pmfc for target ")
  UartWriteStr(HwIdTarget())
  PrintN(".")
  HwIdSayImage()
  PrintN("  The compiler and linker versions are not stamped into the image, so -")
  PrintN("  unlike U-Boot's version - they are not printed here rather than")
  PrintN("  guessed at.")
  PrintN("  Type info for the board, revision and clocks, or help for the commands.")
EndProcedure

; ----------------------------------------------------------------------
;  FmtHexZ - one unsigned value as lowercase hex, no leading zeros, into
;  a NUL-terminated buffer. Returns the length written (not the NUL).
;  *buf must hold at least 17 bytes.
;
;  Lowercase and no leading zeros to match how a person writes a number
;  they will type back in - "1a0", not "00000000000001A0" - and it is
;  what U-Boot's setexpr stores. The MSB-first nibble walk is PutHexN's
;  (format.pi4), with a leading-zero skip and a buffer instead of the
;  wire. The >> is arithmetic on a signed .i, but & 15 takes only the
;  nibble, so a negative result formats as its full 16-digit two's
;  complement - which is the unsigned value setexpr means by it.
; ----------------------------------------------------------------------
Procedure.i FmtHexZ(v.i, *buf)
  Define k.i
  Define nib.i
  Define started.i
  Define len.i
  Define c.i
  started = 0
  len = 0
  k = 60
  While k >= 0
    nib = (v >> k) & 15
    ; Emit once a non-zero nibble has been seen, and always emit the last
    ; nibble so a value of zero comes out as "0" and not as nothing.
    If nib <> 0 Or started <> 0 Or k = 0
      If nib < 10
        c = 48 + nib
      Else
        c = 87 + nib               ; 87 + 10 = 97 = 'a'
      EndIf
      PokeB(*buf + len, c)
      len = len + 1
      started = 1
    EndIf
    k = k - 4
  Wend
  PokeB(*buf + len, 0)
  ProcedureReturn len
EndProcedure

; ----------------------------------------------------------------------
;  setexpr - evaluate an expression into the settings store.
;
;  U-Boot's setexpr (cmd/setexpr.c) writes the result of an expression
;  into an environment variable. This monitor's settings store IS that
;  environment, so setexpr writes a value there that survives with
;  `settings save` and comes back with `settings load`.
;
;    setexpr name val1 op val2    name = val1 op val2
;    setexpr name val1            name = val1  (assignment / copy)
;
;  Operators, all on 64-bit values: + - * / % & | ^ << >>. Both operands
;  are hex (a leading 0x or $ is optional, like every other address
;  argument here). The result is stored as lowercase hex, which is how
;  U-Boot stores it and what memory / write / crc32 all take straight
;  back as an address.
;
;  WHAT IS DELIBERATELY NOT HERE THIS PASS, named so it is a ruling and
;  not a surprise: the `*addr` operand that reads memory, the `fmt`
;  format-string form, and the `gsub`/`sub` regex forms. Each is a
;  separate feature of do_setexpr and earns its own pass; the arithmetic
;  core is what a bench reaches for - work out a load address, an offset,
;  a size - and it is what this does, completely.
;
;  DIVISION OR MODULO BY ZERO IS REFUSED, not trapped: it would fault the
;  monitor with no message, so it is caught before the divide and the
;  store is left untouched.
; ----------------------------------------------------------------------
Procedure CmdSetexpr()
  Define name.i
  Define v1.i
  Define v2.i
  Define op.i
  Define opc.i
  Define opc2.i
  Define r.i

  name = ArgWord()
  If name = 0
    PrintN("!! setexpr needs the name of the setting to write, and none was given,")
    PrintN("   so nothing was changed.")
    PrintN("   setexpr <name> <val1> [<op> <val2>]   op: + - * / % & | ^ << >>")
    PrintN("   Both values are hex; the result is stored as hex in the settings store.")
    ProcedureReturn
  EndIf

  v1 = ParseHex()
  If gParseOk = 0
    PrintN("!! setexpr needs at least one value, in hex, after the name. Nothing")
    PrintN("   was changed.")
    PrintN("   setexpr <name> <val1> [<op> <val2>]")
    ProcedureReturn
  EndIf

  op = ArgWord()
  If op = 0
    ; No operator: assignment. setexpr name val1 sets name to val1.
    r = v1
  Else
    opc = PeekA(op)
    opc2 = PeekA(op + 1)
    v2 = ParseHex()
    If gParseOk = 0
      PrintN("!! an operator was given but the second value after it is missing or")
      PrintN("   is not a hex number, so nothing was changed.")
      PrintN("   setexpr <name> <val1> <op> <val2>")
      ProcedureReturn
    EndIf
    If opc = 43        ; +
      r = v1 + v2
    ElseIf opc = 45    ; -
      r = v1 - v2
    ElseIf opc = 42    ; *
      r = v1 * v2
    ElseIf opc = 47    ; /
      If v2 = 0
        PrintN("!! division by zero. Nothing was changed.")
        ProcedureReturn
      EndIf
      r = v1 / v2
    ElseIf opc = 37    ; %
      If v2 = 0
        PrintN("!! a remainder by zero has no answer. Nothing was changed.")
        ProcedureReturn
      EndIf
      r = v1 % v2
    ElseIf opc = 38    ; &
      r = v1 & v2
    ElseIf opc = 124   ; |
      r = v1 | v2
    ElseIf opc = 94    ; ^
      r = v1 ! v2      ; ! is xor in this language
    ElseIf opc = 60 And opc2 = 60   ; <<
      r = v1 << v2
    ElseIf opc = 62 And opc2 = 62   ; >>
      r = v1 >> v2
    Else
      Print("!! ")
      UartWriteStr(op)
      PrintN(" is not an operator setexpr knows. Nothing was changed.")
      PrintN("   The operators are + - * / % & | ^ << >>")
      ProcedureReturn
    EndIf
  EndIf

  FmtHexZ(r, @gNumBuf[0])

  If SettingsSet(name, @gNumBuf[0]) = 0
    SettingsSayWhyNot()
    PrintN("   Nothing was changed.")
    ProcedureReturn
  EndIf

  Print("Set ")
  UartWriteStr(name)
  Print(" to ")
  UartWriteStr(@gNumBuf[0])
  PrintN(" (hex).")
  PrintN("  This is in memory only. Type saveenv - or settings save - to keep it.")
EndProcedure
