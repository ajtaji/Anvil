; ======================================================================
;  fan.pi4 - the fan policy. A temperature goes in and a duty comes out.
;
;  THIS FILE TOUCHES NO HARDWARE AND PRINTS NOTHING. It holds no register
;  address, no pin number and no sentence. It is the arithmetic and the
;  state machine between a thermometer and a pulse width, and it is
;  written that way on purpose: the decisions in it - when to start, when
;  to stop, how fast at a given temperature - are the ones worth checking
;  exhaustively, and a pure function of (temperature, time) can be driven
;  over its whole domain by a gate in milliseconds.
;
;  IT IS CORE, AND IT WAS DRAFTED AS A PI 4 LIBRARY BEFORE IT WAS MOVED.
;  Worth recording, because the reasoning is the capability model's whole
;  argument. Anvil/Core/fan_cmd.pbi is compiled for EVERY board and calls
;  these names, so on a board with no fan they would have to exist as
;  stubs to link - and a stub of a hysteresis engine is not an honest
;  "this board has no driver" the way a stub of HwUsbPortSpeed is. It is
;  a second implementation of arithmetic, in a file whose whole purpose
;  is to say a board has none of something. There is nothing about a
;  ramp between two temperatures that is a fact about a BCM2711, so it
;  belongs where every board gets the same copy. The chip-specific
;  halves stayed behind: RaspberryPi4/Lib/pwm.pi4 and Lib/thermal.pi4.
;
;  REQUIRES: nothing. No library, no seam, no constant from either. The
;  caller passes the temperature in MILLI-FAHRENHEIT, a flag saying
;  whether that temperature is a measurement at all, and a millisecond
;  clock.
;
;  THE WHOLE FILE IS FAHRENHEIT - project ruling, 2026-09-07. Not "it is
;  Celsius and the printer converts": the thresholds are stored in
;  milli-Fahrenheit, the comparisons are made in milli-Fahrenheit, and
;  the accessors give back whole Fahrenheit. That is what makes the
;  ruling's "one conversion" true rather than aspirational - there is
;  exactly one, at the READ, in Anvil/Hal/hal.pbi's HwTempMilliF(), and
;  by the time a number reaches this file it has already been through
;  it. A policy that kept Celsius internally and converted at each print
;  site would have four conversions and four chances to disagree, and
;  the operator's typed 113 would round-trip through 45 and back.
;
;  THE CALLER IS Anvil/Core/fan_cmd.pbi, which owns the pin, the PWM
;  channel, the settings and the words.
;
; ======================================================================
;  THE CURVE
; ======================================================================
;  Three numbers describe it and the shape is deliberately the dullest
;  one that works:
;
;    duty
;    1000 |                          ,-------------
;         |                     ,---'
;         |                ,---'
;     min |          ,----'
;         |          |
;       0 |----------'
;         +----------+----------+-------------------- temperature
;             low-hyst  low            high
;
;    * below LOW the fan is off;
;    * at LOW it starts, and it starts at MIN rather than at nothing,
;      because a duty of two percent is a fan that hums and does not
;      turn;
;    * between LOW and HIGH the duty is a straight line from MIN to
;      full;
;    * at and above HIGH it is full.
;
;  HYSTERESIS IS ON THE STOP EDGE ONLY. A running fan keeps running
;  until the part is HYST degrees BELOW low. Putting it on the start
;  edge too would mean a board that has just booted warm does nothing
;  until it is hotter than the number the operator typed, which is the
;  opposite of what they asked for.
;
;  THE DEFAULTS. Off below 113 F, full at 158 F, 5 degrees of
;  hysteresis. The first two are the old 45 C and 70 C exactly - 113 F
;  and 158 F are those numbers converted, not new choices - and they are
;  still chosen to sit inside this part's own thresholds rather than to
;  be round: the firmware begins throttling at 185 F (85 C) and reports
;  that number over the mailbox, so full speed at 158 F leaves nearly
;  thirty degrees of headroom for the fan to actually remove some heat
;  before the clock starts coming down. 113 F is above where a Pi 4
;  idles in still air with a heatsink, so a quiet board stays quiet.
;
;  THE HYSTERESIS IS 5 AND NOT 5.4, AND THAT IS A DECISION. The old
;  default was 3 C, which is 5.4 F; this file holds whole degrees and
;  the choice was between 5 and 6. 5 F (2.78 C) is the tighter of the
;  two - a fan that stops slightly sooner rather than slightly later -
;  and a whole number is what an operator reads off a curve and types
;  back. The band it guards is a fan hunting on and off around one
;  threshold, and half a degree Fahrenheit either way does not decide
;  that; the difference between "5" and "5.4" in a report does.
; ======================================================================

#FAN_LOW_F_DEFAULT  = 113
#FAN_HIGH_F_DEFAULT = 158
#FAN_HYST_F_DEFAULT = 5

; The lowest duty the curve will ask for while the fan is meant to be
; turning. Below roughly a quarter, a 12 V fan on a transistor and a
; 4-pin fan on its control input both do the same thing - sit still and
; buzz - and a policy that asks for 40 permille has asked for a noise.
#FAN_MIN_DUTY = 250

; THE SPIN-UP KICK. A stationary fan needs more torque to start than to
; keep going, so the first moments of a start are at full duty whatever
; the curve says. 400 ms is long enough for a 92 mm fan to be turning
; and short enough that it reads as a chirp rather than a burst.
#FAN_KICK_DUTY = 1000
#FAN_KICK_MS   = 400

; WHAT TO DO WITH NO THERMOMETER. Full. A policy whose input has gone
; away has no basis for running the fan slowly, and the two failure
; directions are not the same size: an unnecessary full-speed fan is
; noisy, and a stopped fan on a part whose temperature is unknown is how
; a board throttles to a crawl or worse. Every path out of this file
; that has no temperature returns this.
#FAN_FAILSAFE_DUTY = 1000

; The bounds a curve must satisfy. Below -40 F and above 248 F are
; outside anything this part reports and outside anything an operator
; means; refusing them by name is more useful than accepting a typo.
; They are the old -40 C and 120 C converted - and -40 is the one
; temperature that is the same number in both scales, which is a
; coincidence worth knowing about here because it means the low bound
; did not move at all.
#FAN_F_MIN = -40
#FAN_F_MAX = 248

; The smallest gap between low and high. A curve with high <= low has no
; ramp at all and is a step function written in three numbers; refuse it
; rather than divide by zero or silently become a thermostat. A single
; Fahrenheit degree is a narrower ramp than the single Celsius degree
; this used to be, which only means the refusal catches less - the ramp
; arithmetic below is exact at a span of one either way.
#FAN_SPAN_MIN_F = 1

; The largest hysteresis. More than this and a fan that started at 113 F
; would not stop until 77 F, which is room temperature - it would barely
; ever stop, and it would look like a stuck policy rather than a
; setting. 36 F is the old 20 C limit, rounded to the whole degree.
#FAN_HYST_MAX_F = 36

#FAN_DUTY_MAX = 1000

; ----------------------------------------------------------------------
;  MODES. What the operator asked for, above the curve.
; ----------------------------------------------------------------------
#FAN_MODE_AUTO  = 0   ; the curve decides
#FAN_MODE_OFF   = 1   ; nothing, whatever the temperature
#FAN_MODE_ON    = 2   ; full, whatever the temperature
#FAN_MODE_FIXED = 3   ; a duty the operator named, held

; ----------------------------------------------------------------------
;  REFUSAL CODES from the setters. Zero is success; each negative one
;  names which bound was crossed, so the command above can say which
;  number was wrong instead of "bad arguments".
; ----------------------------------------------------------------------
#FAN_OK           = 0
#FAN_ERR_RANGE    = -1   ; a temperature outside #FAN_F_MIN..#FAN_F_MAX
#FAN_ERR_SPAN     = -2   ; high is not above low by enough
#FAN_ERR_HYST     = -3   ; hysteresis negative or past #FAN_HYST_MAX_F
#FAN_ERR_DUTY     = -4   ; a duty outside 0..1000
#FAN_ERR_MODE     = -5   ; not one of the four modes

; ======================================================================
;  STATE
; ======================================================================
; The curve is held in MILLI-FAHRENHEIT, scaled once at the setter, so
; that the comparison against a milli-Fahrenheit reading is exact and
; there is no rounding inside the loop. The operator's whole degrees are
; what the setter takes and what the accessors give back.
;
; MILLI-FAHRENHEIT, NOT MILLIDEGREES CELSIUS - the unit changed on
; 2026-09-07 and the variable names say so. A file that had kept the
; name `fan_lowMilli` meaning Celsius while the setter fed it Fahrenheit
; would be the exact bug this whole change exists to make impossible.
Global fan_lowMilliF.i  = #FAN_LOW_F_DEFAULT * 1000
Global fan_highMilliF.i = #FAN_HIGH_F_DEFAULT * 1000
Global fan_hystMilliF.i = #FAN_HYST_F_DEFAULT * 1000
Global fan_mode.i      = #FAN_MODE_AUTO
Global fan_fixedDuty.i = 0

; Whether the curve currently considers the fan to be RUNNING. This is
; the hysteresis - the one bit of memory that makes the stop threshold
; different from the start threshold - and it is also what a spin-up
; kick is triggered by.
Global fan_running.i   = 0
Global fan_kickStart.i = 0
Global fan_kicking.i   = 0

; Counters, for the report and for the bench. A fan that has started
; forty times in five minutes is hunting, and the only way anybody finds
; that out is if somebody counted.
Global fan_starts.i    = 0
Global fan_stops.i     = 0
Global fan_blindTicks.i = 0    ; decisions taken with no temperature

; ======================================================================
;  SETTERS - each validates, and none half-applies
; ======================================================================

; FanSetCurve(lowF, highF) - both ends at once, because they are only
; meaningful together: setting low above the current high and then
; fixing high would leave an inverted curve alive in between, and a
; policy evaluated in that window would divide by a negative span.
;
; BOTH ARGUMENTS ARE WHOLE DEGREES FAHRENHEIT. There is no Celsius form
; of this procedure and there must not be one: a second entry point in
; the other unit is a coin flip at every call site.
Procedure.i FanSetCurve(lowF.i, highF.i)
  If lowF < #FAN_F_MIN Or lowF > #FAN_F_MAX
    ProcedureReturn #FAN_ERR_RANGE
  EndIf
  If highF < #FAN_F_MIN Or highF > #FAN_F_MAX
    ProcedureReturn #FAN_ERR_RANGE
  EndIf
  If highF - lowF < #FAN_SPAN_MIN_F
    ProcedureReturn #FAN_ERR_SPAN
  EndIf
  fan_lowMilliF  = lowF * 1000
  fan_highMilliF = highF * 1000
  ProcedureReturn #FAN_OK
EndProcedure

; FanSetHysteresis(hystF) - whole degrees FAHRENHEIT, like everything
; else here.
Procedure.i FanSetHysteresis(hystF.i)
  If hystF < 0 Or hystF > #FAN_HYST_MAX_F
    ProcedureReturn #FAN_ERR_HYST
  EndIf
  fan_hystMilliF = hystF * 1000
  ProcedureReturn #FAN_OK
EndProcedure

; FanSetMode(mode) - and a mode change RESETS THE RUNNING BIT rather
; than carrying it across. `fan off` then `fan auto` on a warm board
; should start the fan, with its kick, and not resume mid-ramp as
; though the intervening off had not happened.
Procedure.i FanSetMode(mode.i)
  If mode < #FAN_MODE_AUTO Or mode > #FAN_MODE_FIXED
    ProcedureReturn #FAN_ERR_MODE
  EndIf
  fan_mode = mode
  fan_running = 0
  fan_kicking = 0
  ProcedureReturn #FAN_OK
EndProcedure

; FanSetFixed(permille) - the duty for #FAN_MODE_FIXED. It does not
; select the mode; the caller does that, because `fan 50` is two
; decisions and both should be visible at the call site.
Procedure.i FanSetFixed(permille.i)
  If permille < 0 Or permille > #FAN_DUTY_MAX
    ProcedureReturn #FAN_ERR_DUTY
  EndIf
  fan_fixedDuty = permille
  ProcedureReturn #FAN_OK
EndProcedure

; FanPolicyReset() - back to the defaults, running bit clear. Called at
; startup before any setting is loaded, so that a settings store with
; only some of the keys leaves the rest at a known value rather than at
; whatever a previous image left in .bss.
Procedure FanPolicyReset()
  fan_lowMilliF  = #FAN_LOW_F_DEFAULT * 1000
  fan_highMilliF = #FAN_HIGH_F_DEFAULT * 1000
  fan_hystMilliF = #FAN_HYST_F_DEFAULT * 1000
  fan_mode      = #FAN_MODE_AUTO
  fan_fixedDuty = 0
  fan_running   = 0
  fan_kicking   = 0
  fan_kickStart = 0
  fan_starts    = 0
  fan_stops     = 0
  fan_blindTicks = 0
EndProcedure

; ======================================================================
;  THE CURVE ITSELF
; ======================================================================
;  FanRampDuty(milliF) - where on the ramp a temperature sits, with no
;  hysteresis, no mode and no kick. Pure: same input, same answer,
;  always. This is the function a gate can walk end to end.
;
;  THE INTERPOLATION IS DONE IN MILLI-FAHRENHEIT AND MULTIPLIED BEFORE
;  IT IS DIVIDED. span is at most 288000 and the numerator's other
;  factor is at most 750, so the product is under 2.2e8 - nowhere near
;  the 64-bit width this target has, and the division happens once at
;  the end where it costs one rounding instead of one per step.
; ----------------------------------------------------------------------
Procedure.i FanRampDuty(milliF.i)
  Define span.i
  Define above.i
  If milliF <= fan_lowMilliF
    ProcedureReturn #FAN_MIN_DUTY
  EndIf
  If milliF >= fan_highMilliF
    ProcedureReturn #FAN_DUTY_MAX
  EndIf
  span = fan_highMilliF - fan_lowMilliF
  ; span cannot be zero: FanSetCurve refuses a span below
  ; #FAN_SPAN_MIN_F and the defaults are 45 degrees apart.
  above = milliF - fan_lowMilliF
  ProcedureReturn #FAN_MIN_DUTY + ((#FAN_DUTY_MAX - #FAN_MIN_DUTY) * above) / span
EndProcedure

; ----------------------------------------------------------------------
;  FanShouldRun(milliF) - the hysteresis, as a predicate, WITHOUT
;  changing the state. The command's status report needs to be able to
;  ask "what would the policy do right now" without the asking being
;  what makes the fan start.
; ----------------------------------------------------------------------
Procedure.i FanShouldRun(milliF.i)
  If fan_running <> 0
    ; Running: keep going until it is hyst degrees below the start
    ; point. Strictly below, so a hysteresis of zero makes the two
    ; thresholds the same number and the fan stops the moment it is
    ; under it - which is what a hysteresis of zero should mean.
    If milliF < fan_lowMilliF - fan_hystMilliF
      ProcedureReturn 0
    EndIf
    ProcedureReturn 1
  EndIf
  ; Stopped: start at the low threshold itself, not above it.
  If milliF >= fan_lowMilliF
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  THE DECISION
; ======================================================================
;  FanDutyFor(milliF, haveTemp, nowMs) - the whole policy, and the only
;  procedure here that CHANGES anything.
;
;  milliF IS ALREADY FAHRENHEIT. The caller converted it once, at the
;  read, through Anvil/Hal/hal.pbi's HwTempMilliF(). Nothing in this
;  file converts anything, which is how "one conversion" stays true.
;
;  haveTemp is a flag rather than a sentinel value so that this file
;  needs no constant from the thermometer's library and can be driven
;  from a gate with nothing else present.
;
;  nowMs is passed in rather than read, for the same reason: a policy
;  that read the clock itself could not be tested at a chosen instant,
;  and the spin-up kick is entirely a question of instants.
;
;  ORDER OF PRECEDENCE, highest first:
;    1  OFF          - an operator who typed `fan off` means it
;    2  ON / FIXED   - likewise
;    3  no reading   - #FAN_FAILSAFE_DUTY
;    4  the curve, with hysteresis and the kick
;
;  OFF OUTRANKS THE FAILSAFE, and that is a real decision rather than an
;  accident of ordering. `fan off` with a broken thermometer keeps the
;  fan off; the operator has taken the machine's judgement away
;  deliberately and the machine should not take it back. `fan auto` is
;  where the failsafe lives, and auto is the default.
; ----------------------------------------------------------------------
Procedure.i FanDutyFor(milliF.i, haveTemp.i, nowMs.i)
  Define want.i
  Define duty.i

  If fan_mode = #FAN_MODE_OFF
    If fan_running <> 0
      fan_stops = fan_stops + 1
    EndIf
    fan_running = 0
    fan_kicking = 0
    ProcedureReturn 0
  EndIf

  If fan_mode = #FAN_MODE_ON
    fan_running = 1
    fan_kicking = 0
    ProcedureReturn #FAN_DUTY_MAX
  EndIf

  If fan_mode = #FAN_MODE_FIXED
    fan_running = 1
    fan_kicking = 0
    ProcedureReturn fan_fixedDuty
  EndIf

  ; ---- auto -----------------------------------------------------------
  If haveTemp = 0
    fan_blindTicks = fan_blindTicks + 1
    fan_running = 1
    fan_kicking = 0
    ProcedureReturn #FAN_FAILSAFE_DUTY
  EndIf

  want = FanShouldRun(milliF)

  If want = 0
    If fan_running <> 0
      fan_stops = fan_stops + 1
    EndIf
    fan_running = 0
    fan_kicking = 0
    ProcedureReturn 0
  EndIf

  If fan_running = 0
    ; A start. Arm the kick and count it.
    fan_running   = 1
    fan_starts    = fan_starts + 1
    fan_kicking   = 1
    fan_kickStart = nowMs
  EndIf

  duty = FanRampDuty(milliF)

  If fan_kicking <> 0
    ; SUBTRACT AND COMPARE, never compare against a precomputed end
    ; time. The elapsed form is right across any wrap of the clock the
    ; caller hands in, and costs the same.
    If nowMs - fan_kickStart < #FAN_KICK_MS
      If duty < #FAN_KICK_DUTY
        duty = #FAN_KICK_DUTY
      EndIf
    Else
      fan_kicking = 0
    EndIf
  EndIf

  ProcedureReturn duty
EndProcedure

; ======================================================================
;  ACCESSORS - whole degrees FAHRENHEIT out, because that is what went in
; ======================================================================
;  THE NAMES CARRY THE UNIT AND THAT IS THE POINT. These were FanLowC(),
;  FanHighC() and FanHysteresisC() until 2026-09-07. Renaming them
;  rather than quietly changing what they return is what turns every
;  caller that was not updated into a compile error instead of into a
;  number that is off by a factor of nine fifths.
; ----------------------------------------------------------------------
Procedure.i FanLowF()
  ProcedureReturn fan_lowMilliF / 1000
EndProcedure

Procedure.i FanHighF()
  ProcedureReturn fan_highMilliF / 1000
EndProcedure

Procedure.i FanHysteresisF()
  ProcedureReturn fan_hystMilliF / 1000
EndProcedure

Procedure.i FanMode()
  ProcedureReturn fan_mode
EndProcedure

Procedure.i FanFixedDuty()
  ProcedureReturn fan_fixedDuty
EndProcedure

Procedure.i FanIsRunning()
  ProcedureReturn fan_running
EndProcedure

Procedure.i FanIsKicking()
  ProcedureReturn fan_kicking
EndProcedure

Procedure.i FanStarts()
  ProcedureReturn fan_starts
EndProcedure

Procedure.i FanStops()
  ProcedureReturn fan_stops
EndProcedure

Procedure.i FanBlindTicks()
  ProcedureReturn fan_blindTicks
EndProcedure
