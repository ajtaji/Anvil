; ======================================================================
;  fan_cmd.pi4 - the `fan` command, and the tick that acts on it.
;
;  THIS FILE IS CORE: it names no chip, no register and no pin. It asks
;  the board whether it can modulate an output and read its own
;  temperature at all (RequireCap over #CAP_PWM), and if so it drives
;  the fan through the HwPwm* seam and reads the part through HwTemp*.
;  On a board that declares #CAP_PWM = 0 the same command, compiled from
;  the same bytes, refuses with the honest sentence RequireCap prints.
;
;  WHAT LIVES WHERE, because three files is two more than the obvious
;  one and the split is the point:
;
;    RaspberryPi4/Lib/pwm.pi4      the modulator and the clock manager
;    RaspberryPi4/Lib/thermal.pi4  the sensor and the firmware tags
;    Anvil/Core/fan.pbi            the CURVE - a pure function of
;                                  temperature and time, with no
;                                  hardware and no words in it, and Core
;                                  because a ramp between two
;                                  temperatures is not a chip fact
;    RaspberryPi4/Board/hw_pwm.pi4 the seam between those and this
;    this file                     the words, the arguments, the
;                                  settings, and the tick
;
;  ARGUMENTS
;    fan                    what the fan is doing, and why
;    fan pin <gpio>         drive the fan from that pin, and remember it
;    fan pin none           stop driving, release the pin
;    fan auto               the curve decides - the default
;    fan off                stopped, whatever the temperature
;    fan on                 full, whatever the temperature
;    fan <percent>          held at a percentage, 0 to 100
;    fan curve <low> <high> off below low, full at high, both in whole
;                           degrees FAHRENHEIT
;    fan hyst <degrees>     how far below low it has to fall before a
;                           running fan stops, in whole degrees
;                           FAHRENHEIT
;    fan hz <n>             the modulation frequency
;
;  EVERY TEMPERATURE THIS COMMAND PRINTS OR TAKES IS FAHRENHEIT -
;  project ruling, 2026-09-07. The sensor and the firmware answer in
;  millidegrees Celsius, the seam passes that through unchanged, and the
;  one conversion is Anvil/Hal/hal.pbi's HwTempMilliF(), applied at the
;  read. The Celsius still appears in exactly one place - the bracket on
;  the temperature READ line, next to the raw millidegrees - because
;  that line is the one where somebody may want to check the monitor
;  against a datasheet or against another tool. The curve, the
;  hysteresis and the throttle point print Fahrenheit alone.
;
;  EVERY NUMBER IS DECIMAL, like gpio and clock and unlike the memory
;  family; a leading 0x or $ still forces hex through ParseDec, which is
;  the same rule everywhere in this monitor.
;
;  NOTHING HERE SAVES THE SETTINGS FILE. A setter writes the table and
;  the status report says out loud that there are unsaved changes, which
;  is exactly what `net` and `wifi` do. One command writes the medium -
;  `settings save` - so that is the one place a bad write can happen and
;  the one place to look when it does.
;
;  REQUIRES, in the main file, before this: Anvil/Hal/hal.pbi (the
;  #CAP_PWM gate and the #HW_PWM_*/#HW_TEMP_* vocabulary), the board's
;  HwPwm*/HwTemp* backend, Anvil/Core/fan.pbi (the curve),
;  Anvil/Core/state.pbi, Anvil/Core/parse.pbi, Anvil/Core/settings.pbi
;  and Anvil/Core/bootfile_cmd.pbi - the last one for PmfDecOf and
;  PmfPutDec, the two string-to-number helpers that already exist for
;  reading numeric settings. Two copies of "a decimal string, or the
;  default if it is not one" is two chances to disagree about "30x".
; ======================================================================

; ----------------------------------------------------------------------
;  HOW OFTEN THE POLICY IS RE-EVALUATED.
;
;  The SERVICE call - the software modulator's whole mechanism - runs on
;  EVERY spin of the prompt and is not rate limited; that is what makes
;  a software waveform possible at all.
;
;  The POLICY is different. Re-reading the temperature and recomputing a
;  duty twice a second is plenty for a lump of aluminium with a fan on
;  it, and on a board whose temperature comes from a firmware round trip
;  rather than a register it is the difference between a tick that costs
;  nothing and one that costs a mailbox transaction on every keystroke.
;
;  WHILE THE SPIN-UP KICK IS RUNNING IT GOES TO 50 ms, because the kick
;  is 400 ms long and a 500 ms policy period would make it anywhere
;  between 400 and 900 - which is a fan that chirps for twice as long as
;  the policy says it should, and an audible symptom with no cause
;  anybody would find.
; ----------------------------------------------------------------------
#FAN_TICK_MS = 500
#FAN_KICK_TICK_MS = 50

; The percentage the operator types, and the permille everything below
; uses. Named so the multiplication reads as a unit conversion rather
; than as a magic ten.
#FAN_PCT_TO_PERMILLE = 10
#FAN_PCT_MAX = 100

; ----------------------------------------------------------------------
;  STATE.
;
;  gFanArmed is the whole gate on the tick. It is 0 until a pin has been
;  chosen and the seam has accepted it, so a board with no fan wired -
;  which is every board until somebody types `fan pin` - does nothing at
;  all in the tick beyond one compare against zero.
; ----------------------------------------------------------------------
Global gFanArmed.i    = 0
Global gFanPin.i      = -1
Global gFanHz.i       = 0
Global gFanLastMs.i   = 0
Global gFanAppliedDuty.i = -1     ; -1 so the first decision always writes
; THE LAST READING, IN MILLIDEGREES CELSIUS - the seam's unit, un-
; converted, because this is the raw thing the board said and not
; something a person reads. The name says the unit for exactly the
; reason the ruling exists. Anything printed from it goes through
; HwTempMilliF() first.
Global gFanTempMilliC.i = #HW_TEMP_NONE
Global gFanTicks.i    = 0
Global gFanWrites.i   = 0

; ----------------------------------------------------------------------
;  THE SETTINGS KEYS. Each a whole word after `fan.`, each returned from
;  a procedure rather than typed at its use sites - the same shape
;  EthKeyAddress() uses, and for the same reason: a key spelled two ways
;  is a setting that saves under one name and loads under the other.
;
; ======================================================================
;  THE UNIT MARKER IS THE KEY NAME, AND THAT IS THE WHOLE MIGRATION
; ======================================================================
;  A card written before 2026-09-07 holds `fan.low = 45`, and 45 meant
;  Celsius. Read as Fahrenheit it is a fan running flat out in a cool
;  room, and NOTHING ON THE CARD SAYS WHICH IT WAS. That is the failure
;  to design out: not a wrong number, a number that cannot be told apart
;  from the right one.
;
;  SO THE THREE TEMPERATURE KEYS ARE RENAMED: `fan.lowF`, `fan.highF`,
;  `fan.hystF`. The unit is IN the key. A card either has the new names
;  or it does not, and both answers are true statements about that card:
;
;    * the new names present  -> Fahrenheit, written by this build
;    * only the old names     -> Celsius, written by an older build,
;                                converted once on the way in and
;                                rewritten under the new names
;    * neither                -> a fresh card; the defaults apply, and
;                                the defaults ARE the old ones converted
;                                (113 F is 45 C, 158 F is 70 C), so a
;                                card that was at the defaults keeps
;                                meaning exactly what it meant
;
;  WHY NOT A VERSION FIELD, WHICH IS THE OBVIOUS ANSWER. Because a
;  version field has to have been WRITTEN to be trusted, and the one
;  card that matters is the one already in a Pi with an older image on
;  it - it has no version field at all. "Absent" would then have to mean
;  Celsius, and a brand-new empty card is also absent, so a fresh
;  install would read its own Fahrenheit defaults as Celsius on the
;  first save-and-reload. A renamed key inverts that: the presence of
;  the OLD name is positive evidence of Celsius rather than an inference
;  from an absence, and there is no card in either state that can be
;  misread.
;
;  THE OLD KEYS ARE REMOVED ONCE THE NEW ONES ARE WRITTEN, so the
;  migration happens once and cannot happen twice with different
;  answers. Until `settings save` runs it repeats identically at every
;  boot, which is the safe direction to fail in.
;
;  `fan.pin`, `fan.mode` and `fan.hz` are UNCHANGED. A pin number, a
;  mode word and a frequency in hertz have no unit that this ruling
;  touches; renaming them would be churn that costs an operator their
;  saved pin for nothing.
; ----------------------------------------------------------------------
Procedure.i FanKeyPin()
  ProcedureReturn "fan.pin"
EndProcedure

Procedure.i FanKeyMode()
  ProcedureReturn "fan.mode"
EndProcedure

Procedure.i FanKeyLowF()
  ProcedureReturn "fan.lowF"
EndProcedure

Procedure.i FanKeyHighF()
  ProcedureReturn "fan.highF"
EndProcedure

Procedure.i FanKeyHystF()
  ProcedureReturn "fan.hystF"
EndProcedure

; The three superseded Celsius keys. They are never written any more;
; they exist so FanBoot can recognise an older card and convert it.
Procedure.i FanKeyLowCelsiusOld()
  ProcedureReturn "fan.low"
EndProcedure

Procedure.i FanKeyHighCelsiusOld()
  ProcedureReturn "fan.high"
EndProcedure

Procedure.i FanKeyHystCelsiusOld()
  ProcedureReturn "fan.hyst"
EndProcedure

Procedure.i FanKeyHz()
  ProcedureReturn "fan.hz"
EndProcedure

; "This key is not on this card." No stored curve value can be this: the
; argument readers are ParseDec, which will not read a minus sign, so
; nothing negative has ever been written to any of them.
#FAN_SETTING_ABSENT = -1000000

; ----------------------------------------------------------------------
;  FanSameZ(a, b) - two NUL-terminated strings, equal or not.
;
;  The settings store holds strings and the mode is a word, so reading
;  it back needs a compare. This is four lines rather than a call into
;  settings.pi4's own private one, because that one is private on
;  purpose and a core command reaching into another file's internals is
;  how a rename becomes a bug in an unrelated command.
; ----------------------------------------------------------------------
Procedure.i FanSameZ(a.i, b.i)
  Define i.i
  Define ca.i
  Define cb.i
  If a = 0 Or b = 0
    ProcedureReturn 0
  EndIf
  i = 0
  Repeat
    ca = PeekA(a + i)
    cb = PeekA(b + i)
    If ca <> cb
      ProcedureReturn 0
    EndIf
    If ca = 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  ForEver
EndProcedure

; ======================================================================
;  PRINTING
; ======================================================================

; PutFanRead(milliC) - THE READ LINE. Fahrenheit first, then the sensor
; truth in brackets:
;
;     113 F (45 C, 45764 millidegrees from the sensor)
;
; FAHRENHEIT LEADS BECAUSE IT IS THE ANSWER. The bracket is evidence,
; and it carries two different kinds: the Celsius is what a datasheet or
; another tool would say, so this line can be checked against one, and
; the raw millidegrees are what the board actually handed over before
; anything rounded it. A report that printed only the rounded whole
; number would make a fan that starts at 113 while the display says 112
; look like a fault; that was true when this line was Celsius and it is
; true now.
;
; THIS IS THE ONLY LINE IN THE MONITOR THAT PRINTS A CELSIUS NUMBER.
; Everything else - the curve, the hysteresis, the throttle point, the
; boot line - is Fahrenheit alone.
Procedure PutFanRead(milliC.i)
  If milliC = #HW_TEMP_NONE
    Print("not known")
    ProcedureReturn
  EndIf
  PrintDec(HwTempWholeF(milliC))
  Print(" F (")
  PrintDec(HwTempWhole(milliC))
  Print(" C, ")
  PrintDec(milliC)
  Print(" millidegrees from the sensor)")
EndProcedure

; PutFanTempF(milliC) - a temperature as Fahrenheit ALONE, for the lines
; that are a threshold rather than a reading: the throttle point and
; anything else quoted at a person who is deciding a curve. No bracket,
; because there is no sensor behind it to check against.
Procedure PutFanTempF(milliC.i)
  If milliC = #HW_TEMP_NONE
    Print("not known")
    ProcedureReturn
  EndIf
  PrintDec(HwTempWholeF(milliC))
  Print(" F")
EndProcedure

; PutFanDuty(permille) - a duty as a percentage with one decimal, from
; the permille, with no floating point anywhere near it.
Procedure PutFanDuty(permille.i)
  PrintDec(permille / 10)
  Print(".")
  PrintDec(permille - (permille / 10) * 10)
  Print(" percent")
EndProcedure

Procedure PutFanMode()
  Select FanMode()
    Case #FAN_MODE_AUTO
      Print("auto")
    Case #FAN_MODE_OFF
      Print("off")
    Case #FAN_MODE_ON
      Print("on")
    Case #FAN_MODE_FIXED
      Print("held")
  EndSelect
EndProcedure

Procedure PutFanKind()
  Select HwPwmKind()
    Case #HW_PWM_KIND_HARD
      Print("a hardware modulator")
    Case #HW_PWM_KIND_SOFT
      Print("a software toggle from the prompt's tick, which is coarse")
    Default
      Print("nothing - no pin is being driven")
  EndSelect
EndProcedure

Procedure PutFanTempSource()
  Select HwTempSource()
    Case #HW_TEMP_SRC_REGISTER
      Print("a sensor register the board reads directly")
    Case #HW_TEMP_SRC_FIRMWARE
      Print("the platform firmware, one request per reading")
    Default
      Print("nothing answered")
  EndSelect
EndProcedure

; FanWhyPwm(code) - the refusal, as a sentence, from a #HW_PWM_* code.
; One place, so the same failure reads the same however it was reached.
Procedure FanWhyPwm(code.i)
  Select code
    Case #HW_PWM_PIN
      PrintN("   The board will not modulate that pin. Type fan on its own for the")
      PrintN("   list of pins it will.")
    Case #HW_PWM_HZ
      PrintN("   That frequency is outside what this board's clocking can produce")
      PrintN("   on that pin. Type fan on its own; the status shows the range.")
    Case #HW_PWM_DUTY
      PrintN("   A duty is 0 to 100 percent and that was not one of those.")
    Case #HW_PWM_BUSY
      PrintN("   The board's clocking would not settle, so nothing was programmed.")
      PrintN("   That is a hardware-level failure and not an argument this command")
      PrintN("   can fix; the pin has been left alone.")
    Case #HW_PWM_STATE
      PrintN("   Nothing is being driven yet, so there is nothing to change. Type")
      PrintN("   fan pin <gpio> first.")
    Case #HW_PWM_INUSE
      PrintN("   This board has one modulator of that kind and it is already on")
      PrintN("   another pin. Type fan pin none to release it first.")
    Default
      PrintN("   The board refused, and did not say why - which is a defect in its")
      PrintN("   backend rather than in what was typed.")
  EndSelect
EndProcedure

; ======================================================================
;  APPLYING A DUTY
; ======================================================================
;  FanApply(permille) - write a duty to the hardware, but only when it
;  has CHANGED.
;
;  The comparison is not an optimisation. On a hardware channel a write
;  costs nothing, but on a software one every write is a chance for the
;  level shadow and the pad to disagree, and on a board whose modulator
;  ever gains a busy-wait it would be a busy-wait twice a second for
;  ever. More usefully: gFanWrites counts real changes, so a fan that is
;  hunting shows up as a number climbing rather than as a noise somebody
;  has to be in the room to hear.
; ----------------------------------------------------------------------
Procedure FanApply(permille.i)
  If permille = gFanAppliedDuty
    ProcedureReturn
  EndIf
  If HwPwmDuty(permille) = #HW_PWM_OK
    gFanAppliedDuty = permille
    gFanWrites = gFanWrites + 1
  EndIf
EndProcedure

; ======================================================================
;  TAKING THE SAMPLE
; ======================================================================
;  ONE PLACE IN THE MONITOR READS THE TEMPERATURE SEAM PERIODICALLY, and
;  this is it. Everything that only wants to SHOW a temperature reads
;  HwTempSampled() instead - see the sample's declaration in
;  Anvil/Hal/hal.pbi for why a reader on a repaint path cannot ask the
;  seam at all.
;
;  THE SAMPLER LIVES HERE BECAUSE THE FAN ALREADY OWNED THE CADENCE. The
;  policy has been reading the part's temperature twice a second since it
;  existed; a second periodic reader beside it would be two round trips
;  on a board whose temperature comes from a firmware transaction, and
;  two answers a second apart that a person could see disagree. So the
;  policy's read IS the sample - it goes through the same call, which
;  publishes - and the independent tick below only fires on a board where
;  the policy is not running at all.
;
;  HOW OFTEN, WHEN NOTHING IS ARMED: once a second, because a second is
;  the cadence of the thing that shows it and there is no sense reading
;  faster than anybody looks. A board with no thermometer pays one
;  seam call a second that answers with the sentinel, which is a load and
;  a compare, and the alternative - remembering that a board answered the
;  sentinel once and never asking again - would never notice a thermal
;  implementation arriving later.
; ----------------------------------------------------------------------
#HW_TEMP_SAMPLE_MS = 1000

; WHEN the last sample was taken. The sampler's own cadence, so it lives
; with the sampler; the VALUE is the hardware layer's vocabulary and
; lives there. Starting a whole period in the past makes the first call
; due, so a board comes up with a real reading rather than with a second
; of sentinel.
Global gHwTempSampleMs.i = -#HW_TEMP_SAMPLE_MS

; Read the seam and publish what it said. Returns the reading, in the
; seam's own unit, so a caller that needs it does not read twice.
Procedure.i HwTempSampleNow()
  gHwTempSampledMilliC = HwTempMilliC()
  gHwTempSampleMs = millis()
  ProcedureReturn gHwTempSampledMilliC
EndProcedure

; HwTempSampleTick() - called from the prompt's idle spin beside
; FanTick(), and from nowhere else. It runs whether or not a fan is
; armed; on an armed board the policy has already refreshed the sample
; well inside the period and this is a millis() read and a compare.
;
; THE ELAPSED TEST IS A SUBTRACTION, right across a wrap of millis(),
; the same shape as every other tick in the spin.
Procedure HwTempSampleTick()
  If millis() - gHwTempSampleMs < #HW_TEMP_SAMPLE_MS
    ProcedureReturn
  EndIf
  HwTempSampleNow()
EndProcedure

; ======================================================================
;  THE TICK
; ======================================================================
;  FanTick() - called from the prompt's idle spin, next to the Wi-Fi
;  keepalive and the TCP timer, and from nowhere else.
;
;  IT PRINTS NOTHING, EVER. It runs while the operator is typing; a line
;  of output from here would arrive in the middle of a half-typed
;  command. Everything it learns is in the counters the status report
;  prints.
;
;  IT IS TWO RATE CLASSES AND THAT IS THE WHOLE DESIGN:
;
;    HwPwmService() runs every single call, because a software waveform
;    IS that call happening often. It is one compare on a board driving
;    a hardware channel and one compare on a board driving nothing.
;
;    The policy runs at most every #FAN_TICK_MS, because it reads a
;    temperature and a temperature can cost a firmware round trip.
;
;  THE ELAPSED TEST IS A SUBTRACTION, not a comparison against a
;  precomputed deadline, so it is right across a wrap of millis() and
;  costs the same. Same shape as the keepalive next to it.
; ----------------------------------------------------------------------
Procedure FanTick()
  Define now.i
  Define due.i
  Define t.i
  Define have.i

  If gFanArmed = 0
    ProcedureReturn
  EndIf

  HwPwmService()

  now = millis()
  due = #FAN_TICK_MS
  If FanIsKicking() <> 0
    due = #FAN_KICK_TICK_MS
  EndIf
  If now - gFanLastMs < due
    ProcedureReturn
  EndIf
  gFanLastMs = now
  gFanTicks = gFanTicks + 1

  ; THE ONE CONVERSION, AT THE READ. The seam answers in millidegrees
  ; Celsius; everything from here on - the policy, the thresholds, the
  ; report - is Fahrenheit, and this is the line that makes it so. The
  ; raw Celsius is kept as well, because the read line prints it as the
  ; evidence behind the Fahrenheit.
  ;
  ; THE READ GOES THROUGH THE SAMPLER, so the policy's reading is also
  ; the one the banner shows and an armed board reads the seam once.
  t = HwTempSampleNow()
  have = 1
  If t = #HW_TEMP_NONE
    have = 0
  EndIf
  gFanTempMilliC = t

  FanApply(FanDutyFor(HwTempMilliF(t), have, now))
EndProcedure

; ======================================================================
;  CLAIMING AND RELEASING THE PIN
; ======================================================================

; FanStartOn(pin, hz) - claim the pin at a frequency and arm the tick.
; Prints the refusal itself and returns 0, or returns 1 having printed
; nothing - the caller says what it wants to say about a success.
Procedure.i FanStartOn(pin.i, hz.i)
  Define rc.i
  Define why.i
  Define lo.i
  Define hi.i

  why = HwPwmReservedReason(pin)
  If why <> 0
    Print("!! GPIO ")
    PrintDec(pin)
    Print(" is ")
    UartWriteStr(why)
    PrintN(".")
    PrintN("   Anvil will not drive a pin the board itself is using, because doing")
    PrintN("   so can take the machine down between one command and the next.")
    PrintN("   Nothing was done.")
    ProcedureReturn 0
  EndIf

  ; Release whatever was being driven first. Claiming a second pin
  ; without letting go of the first would leave the old one modulating
  ; with nothing watching it, which on a transistor is a fan running for
  ; ever at whatever duty it had.
  If gFanArmed <> 0
    HwPwmEnd()
    gFanArmed = 0
  EndIf

  ; THE REMEMBERED FREQUENCY IS ADAPTED TO THE PIN, WITH A SENTENCE.
  ;
  ; This is the one place in this command that does not refuse an
  ; out-of-range frequency, and the difference is who chose it. `fan hz`
  ; refuses, because the operator typed that number just now and wants to
  ; know it was wrong. Here the number is one that was stored - very
  ; likely 25000, the four-wire fan default - and the pin being chosen may
  ; be a software-toggled one whose ceiling is a thousandth of that.
  ; Refusing would make `fan pin 5` a dead end whose cure is a `fan hz`
  ; the operator has no reason to guess at. So the nearest reachable
  ; frequency is used and SAID OUT LOUD, which is a working fan and an
  ; honest transcript rather than one or the other.
  lo = HwPwmHzMin(pin)
  hi = HwPwmHzMax(pin)
  If hi > 0 And hz > hi
    Print("Note: ")
    PrintDec(hz)
    Print(" Hz is above what this board can modulate GPIO ")
    PrintDec(pin)
    PrintN(" at,")
    Print("so ")
    PrintDec(hi)
    PrintN(" Hz is being used instead. That pin has no hardware modulator")
    PrintN("behind it - type fan on its own to see the ones that do.")
    hz = hi
  ElseIf lo > 0 And hz < lo
    Print("Note: ")
    PrintDec(hz)
    Print(" Hz is below what this board can modulate GPIO ")
    PrintDec(pin)
    Print(" at, so ")
    PrintDec(lo)
    PrintN(" Hz is being used instead.")
    hz = lo
  EndIf

  rc = HwPwmBegin(pin, hz)
  If rc <> #HW_PWM_OK
    PrintN("!! that pin could not be set up as a fan output, so nothing was done.")
    FanWhyPwm(rc)
    ProcedureReturn 0
  EndIf

  gFanPin = pin
  gFanHz = HwPwmHz()
  gFanArmed = 1
  gFanAppliedDuty = -1
  ; Anchor the tick a full period in the past so the first decision
  ; happens on the very next spin rather than half a second later - the
  ; fan should react to the temperature it is at NOW, not to the one it
  ; reaches while a fresh timer runs down.
  gFanLastMs = millis() - #FAN_TICK_MS
  ProcedureReturn 1
EndProcedure

; FanRelease() - stop driving and disarm. The seam leaves the pad in
; whatever state the BOARD considers safe for a fan; this file does not
; know which that is and must not guess.
Procedure FanRelease()
  If gFanArmed = 0
    ProcedureReturn
  EndIf
  HwPwmEnd()
  gFanArmed = 0
  gFanPin = -1
  gFanAppliedDuty = -1
  ; THE FREQUENCY IS NOT CLEARED, and that is a correction made on the
  ; bench on 2026-09-06. It used to be set to 0 here, so `fan pin none`
  ; followed by `fan pin 18` came up at "0 Hz is below what this board
  ; can modulate GPIO 18 at, so 1 Hz is being used instead" - a fan
  ; control signal at ONE HERTZ, after the operator had asked for none
  ; of that. The frequency is a property of the fan the operator
  ; described, not of whether a pin is being driven this second, so it
  ; survives a release exactly as the curve and the mode do.
EndProcedure

; ======================================================================
;  THE STATUS REPORT
; ======================================================================
Procedure FanStatus()
  Define t.i
  Define tmax.i
  Define n.i
  Define i.i
  Define p.i
  Define d.i

  t = HwTempSampleNow()
  tmax = HwTempMaxMilliC()

  Print("temperature   ")
  PutFanRead(t)
  PrintNl()
  Print("  read from   ")
  PutFanTempSource()
  PrintNl()
  If tmax <> #HW_TEMP_NONE
    Print("  throttles at ")
    PutFanTempF(tmax)
    PrintNl()
  EndIf

  Print("mode          ")
  PutFanMode()
  If FanMode() = #FAN_MODE_FIXED
    Print(", at ")
    PutFanDuty(FanFixedDuty())
  EndIf
  PrintNl()

  Print("curve         off below ")
  PrintDec(FanLowF())
  Print(" F, full at ")
  PrintDec(FanHighF())
  Print(" F, ")
  PrintDec(FanHysteresisF())
  PrintN(" F of hysteresis")

  If gFanArmed = 0
    PrintN("pin           none. This command is not driving anything.")
    PrintN("  Type fan pin <gpio> to choose one. The board offers these:")
  Else
    Print("pin           GPIO ")
    PrintDec(gFanPin)
    Print(", driven by ")
    PutFanKind()
    PrintN(".")

    Print("frequency     ")
    PrintDec(HwPwmHz())
    Print(" Hz")
    If HwPwmHz() <> gFanHz
      ; Cannot normally differ - both come from the seam - and if it
      ; ever does, the number the hardware reports is the true one and
      ; the disagreement is worth seeing rather than hiding.
      Print(" (this command remembered ")
      PrintDec(gFanHz)
      Print(")")
    EndIf
    PrintNl()

    Print("duty          ")
    PutFanDuty(HwPwmDutyNow())
    If FanIsKicking() <> 0
      Print(" - the spin-up kick is still running")
    EndIf
    PrintNl()

    d = HwPwmDetail(#HW_PWM_DETAIL_SRCHZ)
    If d >= 0
      Print("  clocked at  ")
      PrintDec(d)
      Print(" Hz, divided by ")
      PrintDec(HwPwmDetail(#HW_PWM_DETAIL_DIVISOR))
      Print(" into a period of ")
      PrintDec(HwPwmDetail(#HW_PWM_DETAIL_RANGE))
      PrintN(" counts")
    EndIf
    d = HwPwmDetail(#HW_PWM_DETAIL_STALLS)
    If d >= 0
      Print("  the tick was too late ")
      PrintDec(d)
      PrintN(" times, and the pin was parked each time.")
      If d > 0
        PrintN("  A software toggle stops modulating while a command runs, so this")
        PrintN("  number climbs during long jobs. A pin with a hardware modulator")
        PrintN("  behind it does not have this problem - fan on its own lists them.")
      EndIf
      Print("  edges driven ")
      PrintDec(HwPwmDetail(#HW_PWM_DETAIL_EDGES))
      PrintNl()
    EndIf

    Print("history       ")
    PrintDec(FanStarts())
    Print(" starts, ")
    PrintDec(FanStops())
    Print(" stops, ")
    PrintDec(gFanWrites)
    Print(" duty changes over ")
    PrintDec(gFanTicks)
    PrintN(" decisions")
    If FanBlindTicks() > 0
      Print("  ")
      PrintDec(FanBlindTicks())
      PrintN(" of those decisions had no temperature and ran the fan at full,")
      PrintN("  which is what this policy does when it cannot see.")
    EndIf
    PrintN("Type fan pin none to stop driving it. The pins the board offers:")
  EndIf

  ; The pin list, either way - it is what `fan pin` takes and it is the
  ; only place the hardware/software distinction is visible before
  ; somebody commits to a pin.
  n = HwPwmPinCount()
  If n <= 0
    PrintN("  none at all. This board declares a fan capability and then offers no")
    PrintN("  pins, which is a defect in its backend.")
  Else
    i = 0
    Print("  ")
    While i < n
      p = HwPwmPinAt(i)
      If p >= 0
        PrintDec(p)
        If HwPwmPinIsHard(p) = 1
          Print("*")
        EndIf
        Print(" ")
      EndIf
      i = i + 1
    Wend
    PrintNl()
    PrintN("  A star marks a pin with a real modulator behind it - steady at any")
    PrintN("  frequency, and the right choice for a four-wire fan. The rest are")
    PrintN("  driven by a software toggle, which is fine for a two-wire fan on a")
    PrintN("  transistor and is coarse.")
  EndIf

  If SettingsDirty() <> 0
    PrintN("There are changes here that are not in the file. Type settings save.")
  EndIf
EndProcedure

; ======================================================================
;  THE SUBCOMMANDS
; ======================================================================

; ---- fan pin <gpio> | fan pin none -----------------------------------
Procedure FanCmdPin()
  Define pin.i
  Define buf.i

  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("none") <> 0 Or WordIs("off") <> 0
    If gFanArmed = 0
      PrintN("No pin was being driven, so nothing was done.")
    Else
      Print("GPIO ")
      PrintDec(gFanPin)
      PrintN(" released. The board has left the pad in the state it")
      PrintN("considers safe for a fan; on most wiring that means the fan runs.")
      FanRelease()
    EndIf
    SettingsRemove(FanKeyPin())
    ProcedureReturn
  EndIf
  ; Not a word - rewind and read it as a number.
  gPos = gWordAt

  pin = ParseDec()
  If gParseOk = 0
    PrintN("!! this needs a pin number in decimal, or the word none, and there was")
    PrintN("   neither - so nothing was done. Type fan for the pins this board")
    PrintN("   offers.")
    ProcedureReturn
  EndIf

  If FanStartOn(pin, gFanHz) = 0
    ProcedureReturn
  EndIf

  buf = @gNumBuf[0]
  PmfPutDec(pin, buf)
  If SettingsSet(FanKeyPin(), buf) = 0
    PrintN("!! the pin is being driven, but it could not be remembered - the")
    PrintN("   settings table would not take it. It will be forgotten at the next")
    PrintN("   reset. Type settings to see what is in the way.")
  EndIf

  Print("The fan is now on GPIO ")
  PrintDec(pin)
  Print(", driven by ")
  PutFanKind()
  PrintN(".")
  Print("Frequency ")
  PrintDec(HwPwmHz())
  PrintN(" Hz. Type fan to see the temperature and the duty.")
  PrintN("This is not saved to the file yet - type settings save.")
EndProcedure

; ---- fan curve <low> <high> ------------------------------------------
;
; BOTH NUMBERS ARE DEGREES FAHRENHEIT - project ruling, 2026-09-07 - and
; they are stored in Fahrenheit under `fan.lowF`/`fan.highF`. There is
; no conversion on this path at all: what the operator typed is what is
; compared against the reading and what is printed back, so 113 cannot
; come back as 112 through a round trip via Celsius.
;
; NEGATIVE DEGREES ARE NOT ACCEPTED HERE and that is a limit of the
; argument reader, not of the policy: ParseDec reads digits and a
; leading minus is not one, and the policy will take anything from -40 F
; upwards. A fan curve that starts below freezing is not a setting
; anybody wants on this hardware, so the reader is left alone rather
; than grown a sign for one unreachable case. Say so rather than let a
; typed "-5" silently become 5.
Procedure FanCmdCurve()
  Define lo.i
  Define hi.i
  Define rc.i
  Define buf.i

  lo = ParseDec()
  If gParseOk = 0
    PrintN("!! fan curve takes two whole numbers of degrees FAHRENHEIT - the")
    PrintN("   temperature below which the fan is off, and the temperature at")
    PrintN("   which it is at full. Nothing was done.")
    PrintN("   For example: fan curve 113 158")
    ProcedureReturn
  EndIf
  hi = ParseDec()
  If gParseOk = 0
    PrintN("!! fan curve takes TWO numbers and only one was given, so nothing was")
    PrintN("   done. Both are degrees Fahrenheit.")
    PrintN("   For example: fan curve 113 158")
    ProcedureReturn
  EndIf

  rc = FanSetCurve(lo, hi)
  If rc = #FAN_ERR_RANGE
    Print("!! a fan curve is set between ")
    PrintDec(#FAN_F_MIN)
    Print(" and ")
    PrintDec(#FAN_F_MAX)
    PrintN(" degrees FAHRENHEIT, and one")
    PrintN("   of those two numbers is outside that. Nothing was done. If those")
    PrintN("   numbers look low, they may be degrees celsius: this command took")
    PrintN("   celsius before 2026-09-07 and takes Fahrenheit now. 45 and 70")
    PrintN("   celsius are 113 and 158 Fahrenheit.")
    ProcedureReturn
  EndIf
  If rc = #FAN_ERR_SPAN
    PrintN("!! the second number has to be above the first by at least a degree -")
    PrintN("   the curve ramps between them, and a ramp needs somewhere to ramp.")
    PrintN("   Nothing was done. For a fan that is simply on above a temperature,")
    PrintN("   set the two a degree apart.")
    ProcedureReturn
  EndIf

  buf = @gNumBuf[0]
  PmfPutDec(lo, buf)
  SettingsSet(FanKeyLowF(), buf)
  PmfPutDec(hi, buf)
  SettingsSet(FanKeyHighF(), buf)
  ; An older card's celsius keys are now superseded by what was just
  ; typed. Leaving them would mean the next boot found both and had to
  ; guess; removing them means the card says one thing.
  SettingsRemove(FanKeyLowCelsiusOld())
  SettingsRemove(FanKeyHighCelsiusOld())

  Print("The fan is now off below ")
  PrintDec(FanLowF())
  Print(" F and at full from ")
  PrintDec(FanHighF())
  PrintN(" F,")
  Print("with ")
  PrintDec(FanHysteresisF())
  PrintN(" F of hysteresis on the way back down.")
  PrintN("This is not saved to the file yet - type settings save.")
EndProcedure

; ---- fan hyst <degrees> ----------------------------------------------
;
; DEGREES FAHRENHEIT, like the curve it belongs to. The default is 5,
; which is the old 3 celsius rounded to a whole Fahrenheit degree.
Procedure FanCmdHyst()
  Define h.i
  Define buf.i

  h = ParseDec()
  If gParseOk = 0
    PrintN("!! fan hyst takes one whole number of degrees FAHRENHEIT: how far")
    PrintN("   below the curve's low point the part has to fall before a running")
    PrintN("   fan stops. Nothing was done. For example: fan hyst 5")
    ProcedureReturn
  EndIf
  If FanSetHysteresis(h) <> #FAN_OK
    Print("!! hysteresis is 0 to ")
    PrintDec(#FAN_HYST_MAX_F)
    PrintN(" degrees Fahrenheit. More than that and a")
    PrintN("   fan that started would never stop, which reads as a stuck policy")
    PrintN("   rather than as a setting. Nothing was done.")
    ProcedureReturn
  EndIf
  buf = @gNumBuf[0]
  PmfPutDec(h, buf)
  SettingsSet(FanKeyHystF(), buf)
  SettingsRemove(FanKeyHystCelsiusOld())
  Print("A running fan will now stop below ")
  PrintDec(FanLowF() - FanHysteresisF())
  PrintN(" F.")
  PrintN("This is not saved to the file yet - type settings save.")
EndProcedure

; ---- fan hz <n> ------------------------------------------------------
Procedure FanCmdHz()
  Define hz.i
  Define buf.i

  hz = ParseDec()
  If gParseOk = 0
    PrintN("!! fan hz takes one number, the modulation frequency in hertz.")
    PrintN("   Nothing was done. A four-wire fan's control input wants 25000.")
    ProcedureReturn
  EndIf

  If gFanArmed = 0
    ; Nothing to reprogram - remember it for the pin that is chosen next.
    gFanHz = hz
    buf = @gNumBuf[0]
    PmfPutDec(hz, buf)
    SettingsSet(FanKeyHz(), buf)
    Print("Noted: ")
    PrintDec(hz)
    PrintN(" Hz. No pin is being driven yet, so nothing changed on the")
    PrintN("hardware - this is the frequency the next fan pin <gpio> will use, and")
    PrintN("that is when it will be checked against what the board can make.")
    PrintN("This is not saved to the file yet - type settings save.")
    ProcedureReturn
  EndIf

  If hz < HwPwmHzMin(gFanPin) Or hz > HwPwmHzMax(gFanPin)
    Print("!! on GPIO ")
    PrintDec(gFanPin)
    Print(" this board can make ")
    PrintDec(HwPwmHzMin(gFanPin))
    Print(" Hz to ")
    PrintDec(HwPwmHzMax(gFanPin))
    PrintN(" Hz,")
    Print("   and ")
    PrintDec(hz)
    PrintN(" is outside that. Nothing was done.")
    ProcedureReturn
  EndIf

  ; Re-begin the same pin at the new frequency. That is a stop and a
  ; start, so the duty is reapplied by the next tick rather than carried
  ; across - gFanAppliedDuty is reset by FanStartOn for exactly that.
  If FanStartOn(gFanPin, hz) = 0
    ProcedureReturn
  EndIf
  buf = @gNumBuf[0]
  PmfPutDec(hz, buf)
  SettingsSet(FanKeyHz(), buf)

  Print("Modulating GPIO ")
  PrintDec(gFanPin)
  Print(" at ")
  PrintDec(HwPwmHz())
  PrintN(" Hz.")
  If HwPwmHz() <> hz
    Print("That is not the ")
    PrintDec(hz)
    PrintN(" that was asked for - it is the nearest this board's")
    PrintN("clocking can actually produce, and it is the one the fan will see.")
  EndIf
  PrintN("This is not saved to the file yet - type settings save.")
EndProcedure

; ---- fan auto | off | on | <percent> ---------------------------------
Procedure FanCmdMode(mode.i, permille.i)
  Define buf.i

  FanSetMode(mode)
  If mode = #FAN_MODE_FIXED
    FanSetFixed(permille)
  EndIf

  buf = @gNumBuf[0]
  Select mode
    Case #FAN_MODE_AUTO
      SettingsSet(FanKeyMode(), "auto")
    Case #FAN_MODE_OFF
      SettingsSet(FanKeyMode(), "off")
    Case #FAN_MODE_ON
      SettingsSet(FanKeyMode(), "on")
    Case #FAN_MODE_FIXED
      ; Stored as the PERCENTAGE the operator typed, not as permille.
      ; The file is something a person edits on another machine; a
      ; number in it should be the number they would type here.
      PmfPutDec(permille / #FAN_PCT_TO_PERMILLE, buf)
      SettingsSet(FanKeyMode(), buf)
  EndSelect

  ; ACT AT ONCE rather than waiting for the next tick. `fan off` that
  ; leaves the fan running for half a second reads as a command that did
  ; not work, and half a second is long enough to type the next one.
  ;
  ; THE have FLAG IS COMPUTED, NOT ASSUMED. Passing 1 unconditionally
  ; would hand the curve #HW_TEMP_NONE as though it were a measurement -
  ; minus 273 degrees, which is below every threshold, so `fan auto` on a
  ; board whose thermometer had stopped answering would turn the fan OFF
  ; and report that it had done the right thing. That is precisely the
  ; case the failsafe exists for and it must reach it.
  If gFanArmed <> 0
    Define t.i
    Define have.i
    t = HwTempSampleNow()
    have = 1
    If t = #HW_TEMP_NONE
      have = 0
    EndIf
    gFanTempMilliC = t
    gFanLastMs = millis() - #FAN_TICK_MS
    ; Fahrenheit into the policy, through the one conversion, exactly as
    ; the tick does it.
    FanApply(FanDutyFor(HwTempMilliF(t), have, millis()))
  EndIf

  Print("Fan mode is now ")
  PutFanMode()
  If mode = #FAN_MODE_FIXED
    Print(", at ")
    PutFanDuty(FanFixedDuty())
  EndIf
  PrintN(".")
  If gFanArmed = 0
    PrintN("No pin is being driven, so nothing turned. Type fan pin <gpio>.")
  Else
    Print("The duty is now ")
    PutFanDuty(HwPwmDutyNow())
    PrintN(".")
  EndIf
  PrintN("This is not saved to the file yet - type settings save.")
EndProcedure

; ======================================================================
;  BOOT
; ======================================================================
;  FanBoot() - reset the policy to its defaults, then let the settings
;  file override what it names, then start driving if a pin was stored.
;
;  THE RESET IS FIRST AND IS UNCONDITIONAL. A settings file with three
;  of the six keys must leave the other three at the documented default
;  and not at whatever a previous image left in the same .bss word - and
;  a board with no settings medium at all must still come up with a
;  working curve.
;
;  IT PRINTS ONE LINE, and only when there is something to say. A board
;  with no fan configured says nothing, because a boot log line reading
;  "fan: not configured" on every one of a thousand boots is noise that
;  trains people to skip the boot log.
;
;  IT IS CALLED FROM Main(), AFTER the settings have been loaded and
;  before the prompt. On the Pi 4 that is board.pi4's Main; on any other
;  board it is that board's Main, in the same place.
; ----------------------------------------------------------------------
Procedure FanBoot()
  Define pin.i
  Define v.i

  FanPolicyReset()
  gFanArmed = 0
  gFanPin = -1
  gFanAppliedDuty = -1
  gFanWrites = 0
  gFanTicks = 0
  gFanHz = HwPwmHzDefault()

  CompilerIf #CAP_PWM = 0
    ; Nothing else to do. The command still exists and still refuses
    ; through RequireCap; the tick still exists and returns on its first
    ; compare. This branch is the only CompilerIf in the file and it
    ; guards a BOOT-TIME side effect rather than a command, which is the
    ; one thing RequireCap cannot gate because nobody typed anything.
    ProcedureReturn
  CompilerEndIf

  ; ------------------------------------------------------------------
  ;  THE CURVE, AND AN OLDER CARD'S CELSIUS.
  ;
  ;  Read the Fahrenheit keys. Where one is absent, look for the celsius
  ;  key it replaced: present means this card was written by a build
  ;  from before 2026-09-07 and its number is celsius, so convert it
  ;  once, here, through the same HwTempMilliF() every reading goes
  ;  through. Absent from both means a card that has never had a curve
  ;  on it, and the default applies - and the defaults are the old ones
  ;  converted, so a card that was at the defaults keeps meaning what it
  ;  meant.
  ;
  ;  EACH OF THE THREE IS DECIDED SEPARATELY, because a card can have
  ;  been half written: an operator who typed `fan hyst` and then
  ;  `settings save` on an older build has `fan.hyst` and no `fan.low`.
  ;  Treating the three as one record would take the whole curve from
  ;  the wrong unit on the strength of one key.
  ; ------------------------------------------------------------------
  Define lo.i
  Define hi.i
  Define hy.i
  Define old.i
  Define migrated.i
  Define buf.i

  migrated = 0

  lo = PmfDecOf(SettingsGet(FanKeyLowF()), #FAN_SETTING_ABSENT)
  If lo = #FAN_SETTING_ABSENT
    old = PmfDecOf(SettingsGet(FanKeyLowCelsiusOld()), #FAN_SETTING_ABSENT)
    If old = #FAN_SETTING_ABSENT
      lo = #FAN_LOW_F_DEFAULT
    Else
      lo = HwTempWholeF(old * 1000)
      migrated = 1
    EndIf
  EndIf

  hi = PmfDecOf(SettingsGet(FanKeyHighF()), #FAN_SETTING_ABSENT)
  If hi = #FAN_SETTING_ABSENT
    old = PmfDecOf(SettingsGet(FanKeyHighCelsiusOld()), #FAN_SETTING_ABSENT)
    If old = #FAN_SETTING_ABSENT
      hi = #FAN_HIGH_F_DEFAULT
    Else
      hi = HwTempWholeF(old * 1000)
      migrated = 1
    EndIf
  EndIf

  hy = PmfDecOf(SettingsGet(FanKeyHystF()), #FAN_SETTING_ABSENT)
  If hy = #FAN_SETTING_ABSENT
    old = PmfDecOf(SettingsGet(FanKeyHystCelsiusOld()), #FAN_SETTING_ABSENT)
    If old = #FAN_SETTING_ABSENT
      hy = #FAN_HYST_F_DEFAULT
    Else
      ; A HYSTERESIS IS A DIFFERENCE, NOT A TEMPERATURE, so it scales by
      ; nine fifths and the 32 does NOT apply. Running it through the
      ; absolute conversion would turn 3 degrees of hysteresis into 37,
      ; which is past the limit and reads as a stuck fan. This is the
      ; one place in the tree where the offset is deliberately left out
      ; and it is worth the four lines to say so.
      hy = HwTempWholeF(old * 1000) - HwTempWholeF(0)
      migrated = 1
    EndIf
  EndIf

  FanSetCurve(lo, hi)
  FanSetHysteresis(hy)

  If migrated <> 0
    ; WRITE THE NEW KEYS AND DROP THE OLD ONES, so the card says one
    ; thing after the next `settings save`. Until then this repeats
    ; identically at every boot, which is the safe direction to fail in.
    buf = @gNumBuf[0]
    PmfPutDec(FanLowF(), buf)
    SettingsSet(FanKeyLowF(), buf)
    PmfPutDec(FanHighF(), buf)
    SettingsSet(FanKeyHighF(), buf)
    PmfPutDec(FanHysteresisF(), buf)
    SettingsSet(FanKeyHystF(), buf)
    SettingsRemove(FanKeyLowCelsiusOld())
    SettingsRemove(FanKeyHighCelsiusOld())
    SettingsRemove(FanKeyHystCelsiusOld())

    PrintN("fan: the saved fan curve on this card was in degrees celsius, which is")
    PrintN("     what this monitor stored before 2026-09-07. It has been converted")
    Print("     to Fahrenheit and now reads off below ")
    PrintDec(FanLowF())
    Print(" F, full at ")
    PrintDec(FanHighF())
    PrintN(" F,")
    Print("     with ")
    PrintDec(FanHysteresisF())
    PrintN(" F of hysteresis - the same curve, said in the other unit.")
    PrintN("     The fan is running to it already. Type settings save to write the")
    PrintN("     converted numbers to the card; until then this conversion happens")
    PrintN("     again, identically, at every boot.")
  EndIf

  gFanHz = PmfDecOf(SettingsGet(FanKeyHz()), HwPwmHzDefault())

  v = SettingsGet(FanKeyMode())
  If v <> 0
    If FanSameZ(v, "auto") <> 0
      FanSetMode(#FAN_MODE_AUTO)
    ElseIf FanSameZ(v, "off") <> 0
      FanSetMode(#FAN_MODE_OFF)
    ElseIf FanSameZ(v, "on") <> 0
      FanSetMode(#FAN_MODE_ON)
    Else
      ; A number, stored as a percentage. PmfDecOf refuses a partial
      ; parse, so anything that is not digits falls back to the default
      ; - and the default here is AUTO rather than a duty, because a
      ; corrupted mode should hand the decision back to the curve and
      ; not hold the fan at a number nobody chose.
      Define pct.i
      pct = PmfDecOf(v, -1)
      If pct >= 0 And pct <= #FAN_PCT_MAX
        FanSetMode(#FAN_MODE_FIXED)
        FanSetFixed(pct * #FAN_PCT_TO_PERMILLE)
      Else
        FanSetMode(#FAN_MODE_AUTO)
      EndIf
    EndIf
  EndIf

  pin = PmfDecOf(SettingsGet(FanKeyPin()), -1)
  If pin < 0
    ProcedureReturn
  EndIf

  If FanStartOn(pin, gFanHz) = 0
    ; FanStartOn has printed the reason. Say what it means for the boot,
    ; because a refusal in the boot log with no consequence attached is
    ; a line people learn to ignore.
    PrintN("   The stored fan pin could not be brought up, so this board is")
    PrintN("   booting with no fan control at all. Type fan to see the pins.")
    ProcedureReturn
  EndIf

  Print("fan: GPIO ")
  PrintDec(pin)
  Print(" at ")
  PrintDec(HwPwmHz())
  Print(" Hz, ")
  PutFanMode()
  Print(", off below ")
  PrintDec(FanLowF())
  Print(" F and full at ")
  PrintDec(FanHighF())
  PrintN(" F.")
EndProcedure

; ======================================================================
;  THE DISPATCHER
; ======================================================================
;  The gate runs FIRST, once, for every subcommand: on a board without
;  #CAP_PWM this prints the honest sentence and returns, and no HwPwm*
;  or HwTemp* call below is reached.
; ----------------------------------------------------------------------
Procedure CmdFan()
  Define pct.i

  If RequireCap(#CAP_PWM, "fan", "this board has no way to modulate an output, or no way to read its own temperature, so a fan policy would be running blind") = 0
    ProcedureReturn
  EndIf

  SkipSpace()
  If gLine[gPos] = 0
    FanStatus()
    ProcedureReturn
  EndIf

  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  If WordIs("status") <> 0
    FanStatus()
  ElseIf WordIs("pin") <> 0
    FanCmdPin()
  ElseIf WordIs("curve") <> 0
    FanCmdCurve()
  ElseIf WordIs("hyst") <> 0 Or WordIs("hysteresis") <> 0
    FanCmdHyst()
  ElseIf WordIs("hz") <> 0 Or WordIs("frequency") <> 0
    FanCmdHz()
  ElseIf WordIs("auto") <> 0
    FanCmdMode(#FAN_MODE_AUTO, 0)
  ElseIf WordIs("off") <> 0
    FanCmdMode(#FAN_MODE_OFF, 0)
  ElseIf WordIs("on") <> 0 Or WordIs("full") <> 0
    FanCmdMode(#FAN_MODE_ON, 0)
  Else
    ; The last form is a bare percentage: `fan 50`. Rewind over the word
    ; and read it as a number; anything that is not one is the unknown
    ; subcommand, named rather than ignored.
    gPos = gWordAt
    pct = ParseDec()
    If gParseOk = 0
      PrintN("!! that is not one of this command's words, so nothing was done.")
      PrintN("   fan                     the temperature, the duty and the pins")
      PrintN("   fan pin <gpio>|none     which pin drives the fan")
      PrintN("   fan auto|off|on         let the curve decide, or override it")
      PrintN("   fan <percent>           hold it at a percentage, 0 to 100")
      PrintN("   fan curve <low> <high>  off below low, full at high, degrees F")
      PrintN("   fan hyst <degrees>      how far it must cool before stopping, F")
      PrintN("   fan hz <n>              the modulation frequency")
      ProcedureReturn
    EndIf
    If pct < 0 Or pct > #FAN_PCT_MAX
      Print("!! a fan duty is 0 to 100 percent and ")
      PrintDec(pct)
      PrintN(" is not, so nothing was")
      PrintN("   done. fan on is the same as fan 100 and says so more clearly.")
      ProcedureReturn
    EndIf
    FanCmdMode(#FAN_MODE_FIXED, pct * #FAN_PCT_TO_PERMILLE)
  EndIf
EndProcedure
