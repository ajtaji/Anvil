; ======================================================================
;  i2c_cmd.pi4 - the `i2c` command. Core, chip-free: it names no chip and
;  touches no register. It asks the board whether it has an I2C bus at all
;  (RequireCap over #CAP_I2C), and if so it drives the bus ENTIRELY through
;  the HwI2c* seam the board supplies (RaspberryPi4/Board/hw_i2c.pi4 on the
;  Pi 4, over Lib/i2c.pi4). On a board that declares #CAP_I2C = 0 the same
;  command, compiled from the same bytes, refuses cleanly with the honest
;  sentence RequireCap prints. One command, many boards, no fork - the same
;  model gpio_cmd.pi4 demonstrates.
;
;  SUBCOMMANDS (numbers are HEX except speed, which is decimal - the same
;  split clock and baud use, because an address is read in hex everywhere
;  and a clock rate is read in decimal everywhere):
;
;    i2c probe                    scan the header bus and list every 7-bit
;                                 address that answers (0x08..0x77, the
;                                 range i2cdetect scans - the reserved ends
;                                 are skipped).
;    i2c read  <addr> <reg> [count]
;                                 point the device at <reg>, then read
;                                 [count] bytes (default 1). Both addr and
;                                 reg are hex; count is hex.
;    i2c write <addr> <reg> <byte...>
;                                 write <reg> then one or more data bytes.
;                                 All hex.
;    i2c speed [hz]               show the SCL clock, or set it. hz is
;                                 DECIMAL. The rate comes from the clock
;                                 the board says feeds its divider, asked
;                                 for at the time of the call - see below.
;
;  THE REGISTER READ USES A STOP, NOT A REPEATED START. `i2c read` is two
;  transactions: a one-byte write of the register pointer, then a read.
;  There is a STOP between them (write, STOP, START, read). Most
;  register-style devices accept that; a device that REQUIRES a repeated
;  start will not read correctly, and this command does not offer one - the
;  reason is in Lib/i2c.pi4's REPEATED START note (it is the exact bug shape
;  paid for twice on the RP2040 and RP2350, and there is no Pi 4 silicon
;  here to prove a repeated-start path against).
;
;  ---- THE SPEED USED TO BE NOMINAL, AND THAT WAS FORUM 622 ------------
;
;  This command reported a rate computed from a DATASHEET CONSTANT for the
;  clock feeding the bus divider - a nominal 150 MHz. It said so, in as
;  many words, which is why it took a while for anyone to add up what it
;  meant: two commands away, `info` on the same board in the same session
;  was printing a MEASURED figure for that same clock more than three
;  times higher. So a request for standard-mode 100 kHz was putting the
;  line at roughly 333 kHz - inside fast mode - and a request for 400000
;  would have gone past 1.3 MHz, outside what most devices accept. Nothing
;  looked broken, because a bus scan resolves perfectly well at that rate.
;  The number printed simply was not the number on the wire.
;
;  An honest caveat was standing in for work the board could already do.
;  So now the board is asked: HwI2cSourceHz(bus) is the clock feeding the
;  divider RIGHT NOW, HwI2cSourceWhere(bus) says where that figure came
;  from, and HwI2cRateMin/Max say what the divider can actually reach. All
;  three are printed, so the rate can be checked rather than believed, and
;  a rate outside the reachable range is REFUSED with the nearest one
;  named instead of being silently clamped to it.
;
;  WHICH CLOCK IT IS was measured on a wire before any of this was written
;  - the SCL pad sampled at six known dividers on a Pi 4 - and not
;  inferred from two printed numbers. The instrument is
;  RaspberryPi4/Examples/Diagnostics/pi4I2cScl.pi4.
;
;  A BOARD WITH NOTHING TO SAY SAYS NOTHING. The Arduino UNO Q returns 0
;  from all four, because its rate is a vendor-characterised table lookup
;  and not a division, and the core then prints no source and no range
;  rather than inventing either. Same discipline as the pin seam.
;
;  ---- THE BUS IS BROUGHT UP IN ONE PLACE. READ THIS BEFORE ADDING A
;  ---- SUBCOMMAND.
;
;  CmdI2c calls HwI2cUp(bus) ONCE, after it recognises the subcommand and
;  before it dispatches. Every path below therefore runs on a bus whose
;  pins are muxed to the controller, whose clock is programmed and whose
;  controller is enabled, and no path has to remember to do it.
;
;  IT WAS NOT ALWAYS LIKE THAT, AND THAT WAS FORUM 584. `read` and `write`
;  each called HwI2cUp themselves; `probe` and `speed` did not. On a Pi 4
;  the two pads stay plain inputs until the bus is brought up, so the
;  controller was driving a bus it was not connected to: `i2c probe` spun
;  out at the very first address and announced that SDA or SCL was stuck
;  low and the wiring and pull-ups were suspect, while `gpio status` on
;  those same two pins - before and after - showed them idle high with
;  pull-ups on, perfectly healthy. Worse, `i2c read` on that identical bus
;  answered "no acknowledge", because it HAD brought the bus up. Two
;  commands, one bus, two verdicts, and the confident one was the wrong
;  one.
;
;  Four subcommands and two of them remembering is not a thing to fix
;  twice; it is a thing to make impossible. Hence one call, at the top.
;
;  ---- AND A STALLED TRANSFER NO LONGER DIAGNOSES ITSELF ---------------
;
;  #HW_I2C_TIMEOUT means the controller did not finish. It does NOT mean
;  the bus is wedged - that was the second half of 584, a stock sentence
;  blaming wiring and pull-ups that were measurably fine. So the cause is
;  now MEASURED, by asking the board for the level at each pad, and
;  I2cTimeoutVerdict() turns those two readings into one verdict. Both the
;  scan and the read/write paths render that same verdict for the same
;  condition, which is the property that was missing.
;
;  PROVEN ON A Pi 4, 2026-09-03: the pins read alt0 after `i2c speed`, and
;  `i2c probe` with nothing on the header scans 0x08 to 0x77 and reports an
;  empty bus in one sentence. Before that date this header said COMPILE
;  VERIFIED ONLY and no part of this file had ever driven a bus.
; ======================================================================

; ----------------------------------------------------------------------
;  WHAT A STALLED TRANSFER ACTUALLY MEANS - the three answers, and no
;  fourth one. I2cTimeoutVerdict() below is the ONLY place that decides.
; ----------------------------------------------------------------------
#I2C_VERDICT_UNKNOWN = 0   ; the board cannot read the pads, so nobody knows
#I2C_VERDICT_WEDGED  = 1   ; at least one line is being held low - MEASURED
#I2C_VERDICT_IDLE    = 2   ; both lines are high: the bus is at rest and well

; ----------------------------------------------------------------------
;  I2cTimeoutVerdict(sda, scl) - one condition, one verdict.
;
;  sda and scl are HwI2cPadLevel() answers: 1 high, 0 low, -1 unreadable.
;
;  An I2C bus at rest is HIGH on both lines, held there by pull-up
;  resistors; that is the entire electrical convention. So:
;
;    * either line reading LOW while a transfer failed to complete is a
;      bus being held down - the real stuck-line, missing-pull-up,
;      shorted-wiring case, and the only case that may be called wedged;
;    * both lines HIGH means the wiring and the pull-ups are doing exactly
;      what they should. Whatever went wrong, it was not those, and saying
;      it was sends the operator to re-solder a bus that is fine;
;    * a board that cannot read its pads gets neither answer. UNKNOWN is
;      not a failure of this procedure, it is this procedure refusing to
;      guess - the same third answer HwAddrCheck() has and for the same
;      reason.
;
;  PURE, DELIBERATELY. It reads no register, calls nothing and touches
;  only its two arguments, so the project's own A64 interpreter can
;  execute it directly with a flat memory and no device model at all.
;  That is what tools/a64/a64_anvil_check.py does with it. The one
;  decision in this fix that could quietly regress is therefore the one
;  decision a gate can run on every build.
; ----------------------------------------------------------------------
Procedure.i I2cTimeoutVerdict(sda.i, scl.i)
  If sda < 0 Or scl < 0
    ProcedureReturn #I2C_VERDICT_UNKNOWN
  EndIf
  If sda = 0 Or scl = 0
    ProcedureReturn #I2C_VERDICT_WEDGED
  EndIf
  ProcedureReturn #I2C_VERDICT_IDLE
EndProcedure

; ----------------------------------------------------------------------
;  I2cBusVerdict(bus) - the verdict for a stalled transfer on this bus,
;  taken from the pads NOW. The measurement half; the decision half is
;  I2cTimeoutVerdict, kept separate so it stays pure and gateable.
; ----------------------------------------------------------------------
Procedure.i I2cBusVerdict(bus.i)
  Define sda.i
  Define scl.i
  sda = HwI2cPadLevel(bus, #HW_I2C_SDA)
  scl = HwI2cPadLevel(bus, #HW_I2C_SCL)
  ProcedureReturn I2cTimeoutVerdict(sda, scl)
EndProcedure

; ----------------------------------------------------------------------
;  I2cPutLine(bus, which) - "SDA (GPIO 2)" or, on a board that will not
;  name its pins, just "SDA". Used by every sentence that has to point at
;  one of the two lines.
; ----------------------------------------------------------------------
Procedure I2cPutLine(bus.i, which.i)
  Define pin.i
  If which = #HW_I2C_SCL
    Print("SCL")
  Else
    Print("SDA")
  EndIf
  pin = HwI2cPin(bus, which)
  If pin >= 0
    Print(" (GPIO ")
    PrintDec(pin)
    Print(")")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  I2cSayPins(bus) - which pins the bus is on, what function they need,
;  and what they are doing right now. Printed by `i2c speed` and by the
;  board's `info`, because "the bus is set to 100000 Hz" was true all the
;  way through 584 and told nobody anything.
;
;  A board that will not name its pins gets one honest line saying so and
;  no invented detail.
; ----------------------------------------------------------------------
Procedure I2cSayPins(bus.i)
  Define sda.i
  Define scl.i
  Define fn.i
  Define rd.i
  Define lv.i

  sda = HwI2cPin(bus, #HW_I2C_SDA)
  scl = HwI2cPin(bus, #HW_I2C_SCL)
  fn  = HwI2cPinFunc(bus)

  If sda < 0 Or scl < 0
    PrintN("This board does not say which pins carry the bus, so nothing here can")
    PrintN("report their function or read their level.")
    ProcedureReturn
  EndIf

  Print("The bus runs on GPIO ")
  PrintDec(sda)
  Print(" as SDA and GPIO ")
  PrintDec(scl)
  Print(" as SCL")
  If fn <> 0
    Print(", which the controller can only")
    PrintNl()
    Print("reach while both are on ")
    UartWriteStr(fn)
    Print(".")
  Else
    Print(".")
  EndIf
  PrintNl()

  ; What they are ACTUALLY on, right now, read back off the chip - not
  ; what this command just asked for. The difference between those two is
  ; the whole of 584.
  Print("Right now GPIO ")
  PrintDec(sda)
  Print(" is ")
  rd = HwI2cPinReady(bus, #HW_I2C_SDA)
  If rd = 1
    If fn <> 0
      UartWriteStr(fn)
    Else
      Print("on the bus function")
    EndIf
  ElseIf rd = 0
    Print("NOT on that function")
  Else
    Print("of a function this board cannot read back")
  EndIf
  Print(" and GPIO ")
  PrintDec(scl)
  Print(" is ")
  rd = HwI2cPinReady(bus, #HW_I2C_SCL)
  If rd = 1
    If fn <> 0
      UartWriteStr(fn)
    Else
      Print("on the bus function")
    EndIf
  ElseIf rd = 0
    Print("NOT on that function")
  Else
    Print("of a function this board cannot read back")
  EndIf
  PrintN(".")

  lv = HwI2cPadLevel(bus, #HW_I2C_SDA)
  If lv < 0
    PrintN("This board cannot read the levels at those pads.")
    ProcedureReturn
  EndIf
  Print("At the pads SDA reads ")
  If lv = 0
    Print("low")
  Else
    Print("high")
  EndIf
  Print(" and SCL reads ")
  lv = HwI2cPadLevel(bus, #HW_I2C_SCL)
  If lv = 0
    Print("low")
  Else
    Print("high")
  EndIf
  PrintN(".")
  If I2cBusVerdict(bus) = #I2C_VERDICT_WEDGED
    PrintN("An idle I2C bus rests HIGH on both lines, so a line reading low with no")
    PrintN("transfer running means something is holding it down.")
  Else
    PrintN("An idle I2C bus rests high on both lines, which is what that is.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  I2cSayTimeout(bus, at) - the sentence for a transfer that did not
;  complete, chosen by MEASURING the two pads. Three conditions, three
;  answers, and the wiring is only blamed when a line is actually low.
;
;  The address is named in all three, because "nothing was done" is much
;  less useful than "nothing was done at 0x50".
; ----------------------------------------------------------------------
Procedure I2cSayTimeout(bus.i, at.i)
  Define v.i
  Define sda.i
  Define scl.i

  v = I2cBusVerdict(bus)

  If v = #I2C_VERDICT_WEDGED
    sda = HwI2cPadLevel(bus, #HW_I2C_SDA)
    scl = HwI2cPadLevel(bus, #HW_I2C_SCL)
    Print("!! the transfer")
    If at >= 0
      Print(" to 0x")
      PutHex2(at)
    EndIf
    PrintN(" never completed, and the bus really is wedged:")
    Print("   ")
    If sda = 0
      I2cPutLine(bus, #HW_I2C_SDA)
      If scl = 0
        Print(" and ")
        I2cPutLine(bus, #HW_I2C_SCL)
        Print(" are both being held low")
      Else
        Print(" is being held low")
      EndIf
    Else
      I2cPutLine(bus, #HW_I2C_SCL)
      Print(" is being held low")
    EndIf
    PrintN(", and an idle bus rests high.")
    PrintN("   Check the wiring, check that the bus has pull-up resistors to 3.3V,")
    PrintN("   and check for a device holding the line down. Nothing was done.")
    ProcedureReturn
  EndIf

  If v = #I2C_VERDICT_IDLE
    Print("!! nothing answered")
    If at >= 0
      Print(" at 0x")
      PutHex2(at)
    EndIf
    PrintN(" and the transfer never completed. This is NOT")
    PrintN("   a wiring fault: both lines were read at the pads afterwards and both")
    PrintN("   are high, which is exactly how a healthy idle bus sits. Either there")
    PrintN("   is no device at that address, or it is not powered. Nothing was done.")
    ProcedureReturn
  EndIf

  Print("!! the transfer")
  If at >= 0
    Print(" to 0x")
    PutHex2(at)
  EndIf
  PrintN(" never completed, and this board cannot read the")
  PrintN("   levels at its own bus pads, so whether the lines are stuck low or")
  PrintN("   simply idle cannot be told apart here - and this command will not")
  PrintN("   guess which. Check the wiring, the pull-ups and the device power,")
  PrintN("   in that order. Nothing was done.")
EndProcedure

; ----------------------------------------------------------------------
;  I2cSayError - one honest, whole-sentence line per #HW_I2C_* failure,
;  naming what the BUS actually did. `at` is the 7-bit address involved,
;  or -1 where none applies. Never called for #HW_I2C_OK.
;
;  `bus` is here so the timeout case can measure the pads before it says
;  anything. It used to say the same wiring sentence every time; see
;  I2cSayTimeout and the 584 note in the header.
; ----------------------------------------------------------------------
Procedure I2cSayError(bus.i, code.i, at.i)
  If code = #HW_I2C_NACK
    Print("!! no acknowledge")
    If at >= 0
      Print(" from the device at 0x")
      PutHex2(at)
    EndIf
    PrintN(". Either there is no device at that address, or it")
    PrintN("   is present but did not respond. Nothing was done.")
  ElseIf code = #HW_I2C_CLKT
    Print("!! the device")
    If at >= 0
      Print(" at 0x")
      PutHex2(at)
    EndIf
    PrintN(" held the clock line down past the stretch timeout,")
    PrintN("   so the transfer was abandoned. The device may be wedged - power")
    PrintN("   the device off and on (not the Pi) and try again. Nothing was done.")
  ElseIf code = #HW_I2C_TIMEOUT
    I2cSayTimeout(bus, at)
  ElseIf code = #HW_I2C_NOBUS
    PrintN("!! this board does not have that I2C bus, so nothing was done.")
  ElseIf code = #HW_I2C_RANGE
    ; Reachable only if something other than `i2c speed` starts asking for
    ; a rate; that path prints a far better sentence of its own, naming
    ; the range and the nearest rate. This is the fallback, and it still
    ; has to be a whole sentence rather than a shrug.
    PrintN("!! that rate is outside what this bus's divider can produce from the")
    PrintN("   clock feeding it, so nothing was changed. Type i2c speed with no")
    PrintN("   number to see the clock and the range it can reach.")
  ElseIf code = #HW_I2C_ARG
    PrintN("!! that argument was out of range, so nothing was done.")
  Else
    PrintN("!! the bus reported an error this command does not recognise, so")
    PrintN("   nothing was done. This is a backend bug, said out loud.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  I2cParseAddr - a 7-bit address from the line, in hex. Returns it, or
;  -1 (having printed why) for a missing or out-of-range address.
; ----------------------------------------------------------------------
Procedure.i I2cParseAddr()
  Define a.i
  a = ParseHex()
  If gParseOk = 0
    PrintN("!! expected a device address in hex (00 to 7f). Nothing was done.")
    ProcedureReturn -1
  EndIf
  If a < 0 Or a > $7F
    Print("!! 0x")
    PutHex2(a & $FF)
    PrintN(" is not a 7-bit I2C address - they run 0x00 to 0x7f. Nothing")
    PrintN("   was done.")
    ProcedureReturn -1
  EndIf
  ProcedureReturn a
EndProcedure

; ----------------------------------------------------------------------
;  PutI2cBytes - the bytes in gI2cBuf[0..n-1] as hex, sixteen per row,
;  each row led by its offset so a long read stays readable.
; ----------------------------------------------------------------------
Procedure PutI2cBytes(n.i)
  Define i.i
  i = 0
  While i < n
    If (i & 15) = 0
      If i > 0
        PrintNl()
      EndIf
      Print("  +")
      PutHex2(i)
      Print("  ")
    EndIf
    PutHex2(gI2cBuf[i] & $FF)
    UartWrite(32)                       ; 32 = a space between bytes
    i = i + 1
  Wend
  PrintNl()
EndProcedure

; ----------------------------------------------------------------------
;  I2cDoProbe - scan the bus and list the addresses that answer.
;
;  WHAT A TIMEOUT DOES TO THE SCAN, and this is the half of 584 that
;  turned a wrong sentence into a wrong RESULT. A stalled transfer used to
;  abort the whole scan at the first address, so the operator never saw
;  0x09 let alone 0x77. That is right for a bus that is genuinely wedged -
;  every address will stall, each stall is a long spin, and grinding
;  through 112 of them helps nobody - and it is wrong for every other
;  reason a transfer might not finish, because those do not repeat.
;
;  So the scan asks the same question the read path asks: what do the pads
;  say. A line held low stops the scan, because that condition is about the
;  BUS and will not change at the next address. Both lines idle high does
;  not stop it: nothing answered here, which is what a scan is for, and the
;  address is skipped exactly as a plain no-acknowledge is. UNKNOWN stops
;  it, because a board that cannot tell the two apart must not gamble the
;  operator's time on the cheerful reading.
; ----------------------------------------------------------------------
Procedure I2cDoProbe(bus.i)
  Define a.i
  Define r.i
  Define found.i
  Define quiet.i

  Print("Scanning I2C bus ")
  PrintDec(bus)
  PrintN(" from 0x08 to 0x77.")
  I2cSayPins(bus)
  PrintN("An address is listed only if a device drove its acknowledge - an idle")
  PrintN("bus is never mistaken for a device.")

  found = 0
  quiet = 0
  a = $08
  While a <= $77
    ; One break check per address, so a long scan can be stopped and never
    ; leaves a half-written line - the discipline the dump commands use.
    If OutBreak() <> 0
      PrintN("   stopped.")
      ProcedureReturn
    EndIf
    r = HwI2cProbe(bus, a)
    If r = #HW_I2C_OK
      Print("  device at 0x")
      PutHex2(a)
      PrintNl()
      found = found + 1
    ElseIf r = #HW_I2C_TIMEOUT
      If I2cBusVerdict(bus) = #I2C_VERDICT_IDLE
        ; Both lines high. Nothing here, the bus is fine, keep scanning -
        ; and remember that it happened, so the closing sentence can say
        ; so rather than implying every address answered cleanly.
        quiet = quiet + 1
      Else
        PrintNl()
        I2cSayError(bus, r, a)
        PrintN("   The scan was stopped there: that is a condition of the bus, not")
        PrintN("   of one address, so every remaining address would answer the same.")
        ProcedureReturn
      EndIf
    ElseIf r = #HW_I2C_NOBUS
      I2cSayError(bus, r, -1)
      ProcedureReturn
    EndIf
    ; #HW_I2C_NACK is the ordinary "nothing here" answer - skip in silence.
    a = a + 1
  Wend

  If found = 0
    PrintN("The scan finished: 112 addresses tried, nothing answered, the bus is")
    PrintN("empty. If you expected a device, check that it is powered and wired to")
    PrintN("these two pins.")
  ElseIf found = 1
    PrintN("1 device found.")
  Else
    PrintDec(found)
    PrintN(" devices found.")
  EndIf

  ; Said only when it happened, and never instead of the count above. A
  ; controller that will not finish a transfer on a bus reading idle-high
  ; is not a wiring fault and is not a missing device either - it is worth
  ; one line, because it is the shape of a real defect.
  If quiet > 0
    Print("Note: ")
    PrintDec(quiet)
    PrintN(" of those addresses did not finish their transfer, on a bus whose")
    PrintN("two lines both read high throughout. That is not a wiring fault, and it")
    PrintN("is worth reporting.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  I2cDoRead - i2c read <addr> <reg> [count]
; ----------------------------------------------------------------------
Procedure I2cDoRead(bus.i)
  Define addr.i
  Define reg.i
  Define count.i
  Define r.i

  addr = I2cParseAddr()
  If addr < 0
    ProcedureReturn
  EndIf

  reg = ParseHex()
  If gParseOk = 0
    PrintN("!! expected a register number in hex after the address. Nothing")
    PrintN("   was done.")
    ProcedureReturn
  EndIf
  If reg < 0 Or reg > $FF
    PrintN("!! the register must be a single byte, 00 to ff. Nothing was done.")
    ProcedureReturn
  EndIf

  count = ParseHex()
  If gParseOk = 0
    count = 1                           ; the documented default
  EndIf
  If count < 1 Or count > #I2C_CMD_MAX
    Print("!! the count must be from 1 to ")
    PrintDec(#I2C_CMD_MAX)
    PrintN(" bytes. Nothing was done.")
    ProcedureReturn
  EndIf

  ; The bus was brought up by CmdI2c before this was dispatched - one
  ; call, one place, for every subcommand. See the header's 584 note.

  ; 1. Point the device at the register (a one-byte write). A STOP follows.
  gI2cBuf[0] = reg
  r = HwI2cWrite(bus, addr, @gI2cBuf[0], 1)
  If r <> #HW_I2C_OK
    I2cSayError(bus, r, addr)
    ProcedureReturn
  EndIf

  ; 2. Read the data back (a fresh START).
  r = HwI2cRead(bus, addr, @gI2cBuf[0], count)
  If r <> #HW_I2C_OK
    I2cSayError(bus, r, addr)
    ProcedureReturn
  EndIf

  Print("Read ")
  PrintDec(count)
  Print(" byte")
  If count <> 1
    UartWrite(115)                      ; 115 = 's'
  EndIf
  Print(" from 0x")
  PutHex2(addr)
  Print(" starting at register 0x")
  PutHex2(reg)
  PrintN(":")
  PutI2cBytes(count)
EndProcedure

; ----------------------------------------------------------------------
;  I2cDoWrite - i2c write <addr> <reg> <byte...>
; ----------------------------------------------------------------------
Procedure I2cDoWrite(bus.i)
  Define addr.i
  Define reg.i
  Define b.i
  Define n.i
  Define r.i

  addr = I2cParseAddr()
  If addr < 0
    ProcedureReturn
  EndIf

  reg = ParseHex()
  If gParseOk = 0
    PrintN("!! expected a register number in hex after the address. Nothing")
    PrintN("   was done.")
    ProcedureReturn
  EndIf
  If reg < 0 Or reg > $FF
    PrintN("!! the register must be a single byte, 00 to ff. Nothing was done.")
    ProcedureReturn
  EndIf

  ; buf[0] is the register pointer; the data bytes follow it.
  gI2cBuf[0] = reg
  n = 1
  Repeat
    SkipSpace()
    If gLine[gPos] = 0
      Break
    EndIf
    b = ParseHex()
    If gParseOk = 0
      PrintN("!! one of the data bytes was not valid hex. Nothing was")
      PrintN("   written - a partial write is worse than none.")
      ProcedureReturn
    EndIf
    If b < 0 Or b > $FF
      PrintN("!! each data byte must be 00 to ff. Nothing was written.")
      ProcedureReturn
    EndIf
    If n > #I2C_CMD_MAX
      Print("!! that is more than ")
      PrintDec(#I2C_CMD_MAX)
      PrintN(" bytes in one write. Nothing was written.")
      ProcedureReturn
    EndIf
    gI2cBuf[n] = b
    n = n + 1
  ForEver

  If n < 2
    PrintN("!! i2c write needs at least one data byte after the register.")
    PrintN("   Nothing was written.")
    ProcedureReturn
  EndIf

  ; The bus was brought up by CmdI2c before this was dispatched.
  r = HwI2cWrite(bus, addr, @gI2cBuf[0], n)
  If r <> #HW_I2C_OK
    I2cSayError(bus, r, addr)
    ProcedureReturn
  EndIf

  ; n includes the register byte; report the data bytes plus the register.
  Print("Wrote register 0x")
  PutHex2(reg)
  Print(" and ")
  PrintDec(n - 1)
  Print(" data byte")
  If (n - 1) <> 1
    UartWrite(115)                      ; 's'
  EndIf
  Print(" to 0x")
  PutHex2(addr)
  PrintN(".")
EndProcedure

; ----------------------------------------------------------------------
;  I2cSaySource(bus) - WHERE THE RATE COMES FROM. Printed by `i2c speed`
;  and by the board's `info`, from this one procedure, so the two cannot
;  drift apart - which is the whole point, because 622 was two commands
;  on one board quoting two different figures for one clock.
;
;  A rate is a divider away from some other clock. Until this existed the
;  monitor printed the rate and never the clock, so nothing it said could
;  be checked, and what it was actually dividing was a number out of a
;  datasheet rather than anything on this board.
;
;  THE ORDER OF THE TWO CALLS MATTERS. HwI2cSourceHz is asked FIRST and
;  HwI2cSourceWhere second, because a board records which of its answers
;  it took as it takes it; asking where before asking what would report
;  the previous call's provenance beside this call's number.
;
;  A BOARD WITH NO DIVIDER TO NAME gets one honest line and no invented
;  detail, exactly as I2cSayPins does for a board that will not name its
;  pins.
; ----------------------------------------------------------------------
Procedure I2cSaySource(bus.i)
  Define src.i
  Define where.i
  Define lo.i
  Define hi.i

  src = HwI2cSourceHz(bus)
  If src <= 0
    PrintN("This board does not make that rate by dividing a clock it can name, so")
    PrintN("there is no source clock to show and no range to quote.")
    ProcedureReturn
  EndIf

  where = HwI2cSourceWhere(bus)
  Print("The divider is fed from ")
  PrintDec(src)
  PrintN(" Hz, which is")
  Print("  ")
  If where <> 0
    UartWriteStr(where)
  Else
    Print("a figure this board will not say the origin of")
  EndIf
  PrintN(".")

  lo = HwI2cRateMin(bus)
  hi = HwI2cRateMax(bus)
  If lo > 0 And hi > 0
    Print("From that clock this bus can be set anywhere from ")
    PrintDec(lo)
    PrintN(" Hz")
    Print("to ")
    PrintDec(hi)
    PrintN(" Hz, and nothing outside that will be accepted.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  I2cSayRate(bus) - the rate the bus is set to, and where that number
;  came from. THE ONE PROCEDURE `i2c speed` AND `info` BOTH CALL.
;
;  That sharing is the fix for 622 as much as the arithmetic is. The two
;  commands used to answer the same question from different sources - one
;  divided a datasheet constant, the other printed what the firmware
;  measured - and they disagreed by a factor of three on one board in one
;  session with nothing between them to notice. Rendered from one place,
;  they cannot.
; ----------------------------------------------------------------------
Procedure I2cSayRate(bus.i)
  Define r.i
  r = HwI2cGetSpeed(bus)
  If r < 0
    I2cSayError(bus, r, -1)
    ProcedureReturn
  EndIf
  Print("The I2C bus ")
  PrintDec(bus)
  Print(" clock is about ")
  PrintDec(r)
  PrintN(" Hz.")
  I2cSaySource(bus)
EndProcedure

; ----------------------------------------------------------------------
;  I2cSayNearest(bus, hz) - the reachable rate closest to the one asked
;  for. Called only after a refusal, so one of the two bounds is always
;  the answer; a bound the board declines to give is not guessed at.
; ----------------------------------------------------------------------
Procedure I2cSayNearest(bus.i, hz.i)
  Define lo.i
  Define hi.i
  lo = HwI2cRateMin(bus)
  hi = HwI2cRateMax(bus)
  If lo <= 0 Or hi <= 0
    ProcedureReturn
  EndIf
  Print("   The nearest it can actually do is ")
  If hz > hi
    PrintDec(hi)
  Else
    PrintDec(lo)
  EndIf
  PrintN(" Hz.")
EndProcedure

; ----------------------------------------------------------------------
;  I2cDoSpeed - i2c speed [hz]. hz is DECIMAL (like clock and baud).
;
;  IT ALSO REPORTS THE PINS, and that is not decoration. `i2c speed`
;  answered "about 100000 Hz" all the way through 584 - a perfectly true
;  statement about a divider register, on a bus whose pads were not
;  connected to the controller at all. A clock rate for a bus that reaches
;  no pins is the most reassuring number the monitor could have printed.
;  Now it says which pins, what function they must be on, what function
;  they are on, and what the pads read, so the answer can be checked
;  against `gpio status` on either pin without believing anything.
;
;  AND IT REPORTS THE SOURCE CLOCK, which is 622. The rate itself was the
;  next thing that could not be checked: a true statement about a divider
;  register, divided by a number nobody had measured. Every line here now
;  names what it divided and where that came from.
; ----------------------------------------------------------------------
Procedure I2cDoSpeed(bus.i)
  Define hz.i
  Define r.i

  SkipSpace()
  If gLine[gPos] = 0
    ; Report the current rate - the same rendering `info` prints.
    I2cSayRate(bus)
    I2cSayPins(bus)
    ProcedureReturn
  EndIf

  hz = ParseDec()
  If gParseOk = 0
    PrintN("!! expected a clock rate in Hz (decimal). Nothing was changed.")
    ProcedureReturn
  EndIf
  If hz <= 0
    PrintN("!! the clock rate must be a positive number of Hz. Nothing was")
    PrintN("   changed.")
    ProcedureReturn
  EndIf

  r = HwI2cSetSpeed(bus, hz)

  ; THE REFUSAL, AND IT NAMES THE WAY OUT. A rate the divider cannot reach
  ; used to be clamped in silence - ask this bus for 2000 Hz and it set
  ; its slowest and reported that as if it had been asked for.
  If r = #HW_I2C_RANGE
    Print("!! ")
    PrintDec(hz)
    PrintN(" Hz is not a rate this bus can produce, so the clock is unchanged.")
    I2cSaySource(bus)
    I2cSayNearest(bus, hz)
    ProcedureReturn
  EndIf
  If r < 0
    I2cSayError(bus, r, -1)
    ProcedureReturn
  EndIf

  Print("Asked for ")
  PrintDec(hz)
  Print(" Hz; the divider gives ")
  PrintDec(r)
  PrintN(" Hz.")
  ; The divider is a whole number, so the rate lands at or just below what
  ; was asked for - never above it, because a device rated for a rate is
  ; not harmed by a slower bus and may well be by a faster one.
  I2cSaySource(bus)
  PrintN("Standard-mode I2C is 100000 and fast-mode is 400000; most devices")
  PrintN("accept either.")
  I2cSayPins(bus)
EndProcedure

; ----------------------------------------------------------------------
;  I2cUsage - what to type, printed for a bare `i2c` or an unknown word.
; ----------------------------------------------------------------------
Procedure I2cUsage()
  PrintN("i2c talks to devices on this board's I2C bus. The subcommands are:")
  PrintN("  i2c probe                    list the addresses that answer")
  PrintN("  i2c read  <addr> <reg> [count]   read count bytes (default 1)")
  PrintN("  i2c write <addr> <reg> <byte...> write a register then bytes")
  PrintN("  i2c speed [hz]               show or set the clock (hz is decimal)")
  PrintN("Addresses, registers, bytes and count are HEX; the speed is decimal,")
  PrintN("the same as clock and baud. A register read puts a STOP between the")
  PrintN("pointer write and the read, not a repeated start.")
EndProcedure

; ----------------------------------------------------------------------
;  CmdI2c - the dispatcher for the family. gPos is already past "i2c".
; ----------------------------------------------------------------------
Procedure CmdI2c()
  Define bus.i
  Define which.i

  ; THE GATE, FIRST. On a board without #CAP_I2C this prints the honest
  ; "not available on this board" sentence and returns 0, and this command
  ; returns cleanly having touched no seam.
  If RequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn
  EndIf

  bus = HwI2cDefaultBus()

  SkipSpace()
  If gLine[gPos] = 0
    I2cUsage()
    ProcedureReturn
  EndIf

  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  ; WHICH SUBCOMMAND, DECIDED BEFORE ANY HARDWARE IS TOUCHED. The word is
  ; turned into a number here so that bringing the bus up can sit between
  ; recognising the command and running it - one call, covering all four,
  ; on a line no subcommand can be added without passing through.
  which = 0
  If WordIs("probe") <> 0
    which = 1
  ElseIf WordIs("read") <> 0
    which = 2
  ElseIf WordIs("write") <> 0
    which = 3
  ElseIf WordIs("speed") <> 0
    which = 4
  EndIf

  If which = 0
    PrintN("!! i2c does not know that subcommand.")
    I2cUsage()
    ProcedureReturn
  EndIf

  ; ***THE BUS COMES UP HERE, AND ONLY HERE.*** HwI2cUp muxes the pins to
  ; the controller's function, programs the clock and enables the
  ; controller, and it is idempotent, so calling it once per command line
  ; costs nothing and cannot be forgotten by a later subcommand. Two of
  ; the four used to call it for themselves and two did not, which is the
  ; whole of forum 584 - a scan on pins the controller was not connected
  ; to, reported as a wiring fault.
  If HwI2cUp(bus) = 0
    I2cSayError(bus, #HW_I2C_NOBUS, -1)
    ProcedureReturn
  EndIf

  If which = 1
    I2cDoProbe(bus)
  ElseIf which = 2
    I2cDoRead(bus)
  ElseIf which = 3
    I2cDoWrite(bus)
  Else
    I2cDoSpeed(bus)
  EndIf
EndProcedure
