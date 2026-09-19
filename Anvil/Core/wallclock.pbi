; ======================================================================
; wallclock.pbi - portable, provenance-carrying wall clock.
;
; Dependencies supplied before this file: Ticks() and TickHz(). The
; clock is an anchor over that monotonic counter. It never invents an
; epoch: WallClockNow() returns -1 until manual, restored-floor, or SNTP
; input sets it. A restored value is explicitly untrusted. SNTP here
; means a validated but unauthenticated network reply; it is not proof
; of cryptographic server identity.
; ======================================================================

EnableExplicit

; ----------------------------------------------------------------------
;  Constants. Bare literals - a constant initialiser on this compiler
;  cannot contain arithmetic (fat.pi4:359-363) - with the arithmetic
;  spelled out beside each one.
; ----------------------------------------------------------------------

; What WallClockNow() returns when nothing has ever set the clock. NOT zero:
; zero is 1970-01-01, a perfectly valid-looking date that a caller
; would happily format and print. -1 cannot be mistaken for a time on
; this scale, because the accepted range starts in 1980.
#WALLCLOCK_UNKNOWN = -1

; Where the time came from. The order matters in one place only:
; WallClockSet() accepts MANUAL..NETWORK and refuses NONE, so that "unset" is
; a state the caller cannot ask for by accident.
#WALLCLOCK_SRC_NONE     = 0
#WALLCLOCK_SRC_MANUAL   = 1
#WALLCLOCK_SRC_RESTORED = 2
#WALLCLOCK_SRC_SNTP  = 3

#WALLCLOCK_ZONE_UTC     = 0
#WALLCLOCK_ZONE_FIXED   = 1
#WALLCLOCK_ZONE_CHICAGO = 2

; The accepted range, derived in THE CALENDAR above.
#WALLCLOCK_EPOCH_MIN = 315532800      ; 1980-01-01 00:00:00 UTC, the FAT epoch
#WALLCLOCK_EPOCH_MAX = 4102444800     ; 2100-01-01 00:00:00 UTC, exclusive

; Seconds from the NTP prime epoch (1900-01-01 00:00:00 UTC) to the
; Unix epoch (1970-01-01). RFC 5905 section 6, RaspberryPi4/Reference/
; rfc5905.txt:721-722: "the prime epoch, or base date of era 0, is 0 h
; 1 January 1900 UTC, when all bits are zero."
;
; Derived: 1900 to 1970 is 70 years containing 17 leap days (1904
; through 1968 inclusive, step 4, is 17 values - 1900 itself is NOT a
; leap year, which is the trap in this number and the reason it is
; 2208988800 rather than 2209075200). 70 * 365 + 17 = 25,567 days,
; times 86400 = 2,208,988,800.
#WALLCLOCK_NTP_EPOCH = 2208988800

#WALLCLOCK_SECS_PER_DAY  = 86400
#WALLCLOCK_SECS_PER_HOUR = 3600

; The FAT epoch year, for the packed date word. [FATGEN] via
; fat.pi4:4112 - date = ((year - 1980) << 9) | (month << 5) | day.
#WALLCLOCK_FAT_YEAR0 = 1980

; How long WallClockInit() waits for the counter to show movement. Same
; constant and same reasoning as timer.pi4:169 - at 54 MHz a tick is
; 18.5 ns, so a counter that has not moved in 200000 passes of a
; handful of instructions is stopped, not slow.
#WALLCLOCK_MOVE_LIMIT = 200000

; Errors. English for each is in WallClockErrorText().
#WALLCLOCK_ERR_NONE     = 0
#WALLCLOCK_ERR_NO_CLOCK = 1           ; CNTFRQ_EL0 reads zero, or no movement
#WALLCLOCK_ERR_RANGE    = 2           ; an epoch outside 1980..2099
#WALLCLOCK_ERR_SOURCE   = 3           ; a source tag that is not one of the three
#WALLCLOCK_ERR_CIVIL    = 4           ; a year/month/day/hour/minute/second that is not a date
#WALLCLOCK_ERR_NOT_SET  = 5           ; asked for the time before anything set it
#WALLCLOCK_ERR_TEXT     = 6           ; WallClockDecode() was handed something that is not a decimal number
#WALLCLOCK_ERR_ZONE     = 7           ; unknown/malformed clock.zone setting

; ----------------------------------------------------------------------
;  State.
;
;  All of it is BSS and therefore zero on a cold start - the image
;  prologue zeroes .bss before Main() runs (the __a64_bss_zero loop;
;  see safety.pi4's note on why that makes a Global useless for
;  anything that must survive a reset). Zero means "no clock, no
;  frequency, no time", which is the state this file must start in.
; ----------------------------------------------------------------------

Global wallclock_hz.i         = 0     ; CNTFRQ_EL0 as read at init, in Hz
Global wallclock_baseEpoch.i  = 0     ; wall-clock seconds at the anchor
Global wallclock_baseTick.i   = 0     ; CNTPCT_EL0 at that same instant
Global wallclock_src.i        = 0     ; #WALLCLOCK_SRC_*
Global wallclock_setCount.i   = 0     ; how many times the clock has been set
Global wallclock_lastStep.i   = 0     ; seconds the last set moved the clock by
Global wallclock_zone.i       = 0     ; local offset from UTC, in seconds
Global wallclock_zoneSet.i    = 0     ; distinguishes default UTC from configured UTC
Global wallclock_zoneMode.i   = #WALLCLOCK_ZONE_UTC
Global wallclock_err.i        = 0     ; #WALLCLOCK_ERR_*

; The broken-down date, filled by WallClockToCivil() and read through the six
; accessors. Globals rather than six return values because this
; language returns one value, and an out parameter per field would make
; every call site six lines long.
Global wallclock_y.i  = 0
Global wallclock_mo.i = 0
Global wallclock_d.i  = 0
Global wallclock_h.i  = 0
Global wallclock_mi.i = 0
Global wallclock_s.i  = 0

; THREE SEPARATE TEXT BUFFERS, ON PURPOSE. A single shared one turns
;
;     UartWriteStr(WallClockStampUtc())
;     UartWriteStr(WallClockStampLocal())
;
; into two copies of whichever ran last, or worse, into one line that
; is half of each - the classic shared-static-buffer trap. Ninety-six
; bytes is not worth being clever about.
Global Dim wallclock_utcBuf.a[32]
Global Dim wallclock_locBuf.a[32]
Global Dim wallclock_lineBuf.a[128]
Global Dim wallclock_numBuf.a[24]     ; WallClockEncode(), decimal seconds
Global Dim wallclock_zoneBuf.a[24]

; ======================================================================
;  PORTABLE MONOTONIC SEAM
; ======================================================================
; The board supplies Ticks() and TickHz(). Keeping those two calls here
; makes the civil clock common code: it does not duplicate a target's
; counter register or assume a CPU frequency.
Procedure.i wallclock_Ticks()
  ProcedureReturn Ticks()
EndProcedure

Procedure.i wallclock_TickHz()
  ProcedureReturn TickHz()
EndProcedure

; ----------------------------------------------------------------------
;  wallclock_Scale() - cache the counter frequency. Private.
;
;  Called by WallClockInit(), and also by anything that finds wallclock_hz still
;  zero, so that a program which forgot to call WallClockInit() gets the
;  right answer rather than a divide by zero. What it does not get is
;  WallClockInit()'s proof that the counter is actually moving.
;
;  Returns the frequency, or 0.
; ----------------------------------------------------------------------
Procedure.i wallclock_Scale()
  Define hz.i
  hz = wallclock_TickHz()
  If hz <= 0
    wallclock_hz = 0
    ProcedureReturn 0
  EndIf
  wallclock_hz = hz
  ProcedureReturn hz
EndProcedure

; ----------------------------------------------------------------------
;  WallClockInit() - read the counter frequency and PROVE the counter moves.
;
;  Returns 1 on success. Returns 0 for either of two failures, which are
;  worth telling apart and WallClockErrorText() does not, because both mean
;  the same thing to a caller: there is no time on this board.
;
;    CNTFRQ_EL0 reads zero - no loader ever programmed it.
;    CNTPCT_EL0 never moves - the counter is stopped.
;
;  A STOPPED COUNTER IS WORSE HERE THAN IN timer.pi4. There, it turns
;  every bounded wait into an infinite loop, which is at least visible.
;  Here it produces a clock that is set correctly, reports correctly for
;  one instant, and then reports that same instant forever - a wall
;  clock that has stopped, which is the one failure a wall clock must
;  not have quietly. So the check is not optional decoration; it is the
;  difference between "no clock" and "a clock that lies".
;
;  Calling WallClockInit() does NOT set the time and does not clear it.
; ----------------------------------------------------------------------
Procedure.i WallClockInit()
  Define t0.i
  Define n.i
  Define ok.i

  wallclock_err = #WALLCLOCK_ERR_NONE
  If wallclock_Scale() = 0
    wallclock_err = #WALLCLOCK_ERR_NO_CLOCK
    ProcedureReturn 0
  EndIf

  t0 = wallclock_Ticks()
  ok = 0
  n = 0
  While n < #WALLCLOCK_MOVE_LIMIT
    If wallclock_Ticks() <> t0
      ok = 1
      n = #WALLCLOCK_MOVE_LIMIT
    Else
      n = n + 1
    EndIf
  Wend

  If ok = 0
    wallclock_err = #WALLCLOCK_ERR_NO_CLOCK
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  WallClockHz() - the cached counter frequency, or 0 before WallClockInit().
; ----------------------------------------------------------------------
Procedure.i WallClockHz()
  ProcedureReturn wallclock_hz
EndProcedure

; ----------------------------------------------------------------------
;  WallClockUptime() - seconds since the counter started.
;
;  ALWAYS AVAILABLE, even with no wall clock at all, because it is the
;  one time-like quantity this board can answer honestly on its own.
;  It counts from when the counter started, which is board reset and
;  not WallClockInit(), and it is exactly the number that must NEVER be
;  dressed up as a date. Returns 0 if there is no counter.
; ----------------------------------------------------------------------
Procedure.i WallClockUptime()
  If wallclock_hz = 0
    wallclock_Scale()
  EndIf
  If wallclock_hz <= 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn wallclock_Ticks() / wallclock_hz
EndProcedure

; ======================================================================
;  SETTING IT
; ======================================================================

; ----------------------------------------------------------------------
;  WallClockSet(epoch, source) - anchor the wall clock.
;
;  epoch  - seconds since 1970-01-01 00:00:00 UTC, inside
;           #WALLCLOCK_EPOCH_MIN .. #WALLCLOCK_EPOCH_MAX.
;  source - #WALLCLOCK_SRC_MANUAL, #WALLCLOCK_SRC_RESTORED or #WALLCLOCK_SRC_SNTP.
;           #WALLCLOCK_SRC_NONE is REFUSED: use WallClockClear() to say "I no
;           longer know", so that forgetting and asserting cannot be
;           spelled the same way.
;
;  Returns 1, or 0 with WallClockLastError() set.
;
;  THE ANCHOR IS TWO NUMBERS READ AS CLOSE TOGETHER AS THIS LANGUAGE
;  ALLOWS: the epoch handed in, and the counter value at that moment.
;  Everything afterwards is base plus elapsed, so the clock cannot
;  drift away from the counter, only with it.
;
;  A RE-SET RECORDS ITS STEP. WallClockLastStep() is the signed number of
;  seconds this call moved the clock by, which is the single most
;  useful line in a log when SNTP finally corrects a hand-typed time:
;  it says how wrong the old answer was, and therefore how wrong every
;  timestamp already written is.
; ----------------------------------------------------------------------
Procedure.i WallClockSet(epoch.i, source.i)
  Define before.i

  wallclock_err = #WALLCLOCK_ERR_NONE

  If source < #WALLCLOCK_SRC_MANUAL Or source > #WALLCLOCK_SRC_SNTP
    wallclock_err = #WALLCLOCK_ERR_SOURCE
    ProcedureReturn 0
  EndIf
  If epoch < #WALLCLOCK_EPOCH_MIN Or epoch >= #WALLCLOCK_EPOCH_MAX
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn 0
  EndIf
  If wallclock_hz = 0
    wallclock_Scale()
  EndIf
  If wallclock_hz <= 0
    wallclock_err = #WALLCLOCK_ERR_NO_CLOCK
    ProcedureReturn 0
  EndIf

  ; The step, computed BEFORE the anchor moves. Reversing these two
  ; assignments would make every step read zero, which is a plausible
  ; number and therefore the wrong kind of bug.
  before = 0
  If wallclock_src <> #WALLCLOCK_SRC_NONE
    before = wallclock_baseEpoch + (wallclock_Ticks() - wallclock_baseTick) / wallclock_hz
    wallclock_lastStep = epoch - before
  Else
    wallclock_lastStep = 0
  EndIf

  wallclock_baseTick  = wallclock_Ticks()
  wallclock_baseEpoch = epoch
  wallclock_src       = source
  wallclock_setCount  = wallclock_setCount + 1
  ProcedureReturn 1
EndProcedure

; Anchor an accepted SNTP timestamp including its 32-bit fractional field.
; anchorTick is the monotonic instant associated with that timestamp, normally
; the receive instant captured by the UDP dispatcher. Keeping it explicit means
; a later service tick cannot make the clock lag merely because APPLY was
; deferred while some other bounded prompt service ran.
Procedure.i WallClockSetNtpAt(epoch.i, fraction.i, anchorTick.i)
  Define fracTicks.i
  If fraction < 0 Or fraction > 4294967295
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn 0
  EndIf
  If WallClockSet(epoch, #WALLCLOCK_SRC_SNTP) = 0
    ProcedureReturn 0
  EndIf
  fracTicks = (fraction * wallclock_hz) / 4294967296
  wallclock_baseTick = anchorTick - fracTicks
  ProcedureReturn 1
EndProcedure

Procedure.i WallClockSetNtp(epoch.i, fraction.i)
  ProcedureReturn WallClockSetNtpAt(epoch, fraction, wallclock_Ticks())
EndProcedure

; ----------------------------------------------------------------------
;  WallClockSetCivil(y, mo, d, h, mi, s, source) - the same, from a date.
;
;  UTC. For a person typing local time, see WallClockSetCivilLocal().
;  Returns 1, or 0 with WallClockLastError() set to #WALLCLOCK_ERR_CIVIL for a date
;  that is not a date - 31 September and 29 February 2027 both fail
;  here rather than being folded into the next month.
; ----------------------------------------------------------------------
Procedure.i WallClockSetCivil(y.i, mo.i, d.i, h.i, mi.i, s.i, source.i)
  Define e.i
  e = WallClockToEpoch(y, mo, d, h, mi, s)
  If e < 0
    ProcedureReturn 0                 ; WallClockToEpoch set the error
  EndIf
  ProcedureReturn WallClockSet(e, source)
EndProcedure

; ----------------------------------------------------------------------
;  WallClockSetCivilLocal(y, mo, d, h, mi, s, source) - from LOCAL civil time.
;
;  What an operator types is what their watch says, which is local
;  time. This subtracts the zone offset and stores UTC, so the two
;  spellings of "set the clock" cannot silently disagree by five hours.
;  With the offset left at zero it is identical to WallClockSetCivil().
; ----------------------------------------------------------------------
Procedure.i WallClockSetCivilLocal(y.i, mo.i, d.i, h.i, mi.i, s.i, source.i)
  Define e.i
  Define standard.i
  Define daylight.i
  Define standardOk.i
  Define daylightOk.i
  e = WallClockToEpoch(y, mo, d, h, mi, s)
  If e < 0
    ProcedureReturn 0
  EndIf
  If wallclock_zoneMode = #WALLCLOCK_ZONE_CHICAGO
    ; Test both legal UTC interpretations. The spring gap has none and the
    ; fall overlap has two; both are refused because silently choosing one
    ; would move a hand-entered time by an hour.
    standard = e + 21600
    daylight = e + 18000
    standardOk = 0
    daylightOk = 0
    If WallClockOffsetAt(standard) = -21600 : standardOk = 1 : EndIf
    If WallClockOffsetAt(daylight) = -18000 : daylightOk = 1 : EndIf
    If standardOk + daylightOk <> 1
      wallclock_err = #WALLCLOCK_ERR_CIVIL
      ProcedureReturn 0
    EndIf
    If standardOk <> 0
      ProcedureReturn WallClockSet(standard, source)
    EndIf
    ProcedureReturn WallClockSet(daylight, source)
  EndIf
  ProcedureReturn WallClockSet(e - wallclock_zone, source)
EndProcedure

; ----------------------------------------------------------------------
;  WallClockClear() - forget the time. The clock reports unknown again.
;
;  Exists so that "I no longer trust this" is expressible. A program
;  that has just found its settings file corrupt should be able to say
;  so rather than carrying on with the value it read.
;
;  The frequency is NOT cleared - the counter is still there and
;  WallClockUptime() still works.
; ----------------------------------------------------------------------
Procedure WallClockClear()
  wallclock_baseEpoch = 0
  wallclock_baseTick  = 0
  wallclock_src       = #WALLCLOCK_SRC_NONE
  wallclock_lastStep  = 0
  wallclock_err       = #WALLCLOCK_ERR_NONE
EndProcedure

; ----------------------------------------------------------------------
;  WallClockSetZone(seconds) / WallClockZone() - the local offset from UTC.
;
;  Fixed offsets are deliberately separate from named rule zones. The one
;  currently supported named rule, America/Chicago, applies the documented US
;  historical DST transitions below; a fixed -06:00 never changes itself.
;
;  Refuses anything beyond a day either way, which is not a zone but a
;  typo. Returns 1 or 0.
; ----------------------------------------------------------------------
Procedure.i WallClockSetZone(seconds.i)
  If seconds <= 0 - #WALLCLOCK_SECS_PER_DAY Or seconds >= #WALLCLOCK_SECS_PER_DAY
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn 0
  EndIf
  wallclock_zone = seconds
  wallclock_zoneSet = 1
  If seconds = 0
    wallclock_zoneMode = #WALLCLOCK_ZONE_UTC
  Else
    wallclock_zoneMode = #WALLCLOCK_ZONE_FIXED
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i WallClockZone()
  Define t.i
  t = WallClockNow()
  If t = #WALLCLOCK_UNKNOWN
    ProcedureReturn wallclock_zone
  EndIf
  ProcedureReturn WallClockOffsetAt(t)
EndProcedure

Procedure.i WallClockZoneConfigured()
  ProcedureReturn wallclock_zoneSet
EndProcedure

; Public/default presentation before a saved setting is found. This differs
; from an explicit `time zone UTC`: both display UTC, but status can still say
; whether the operator configured it.
Procedure WallClockUseUtcDefault()
  wallclock_zone = 0
  wallclock_zoneMode = #WALLCLOCK_ZONE_UTC
  wallclock_zoneSet = 0
  wallclock_err = #WALLCLOCK_ERR_NONE
EndProcedure

Procedure.i wallclock_StrEq(*a, *b)
  Define i.i
  Define ca.i
  Define cb.i
  If *a = 0 Or *b = 0 : ProcedureReturn 0 : EndIf
  i = 0
  Repeat
    ca = PeekB(*a + i) & $FF
    cb = PeekB(*b + i) & $FF
    If ca <> cb : ProcedureReturn 0 : EndIf
    If ca = 0 : ProcedureReturn 1 : EndIf
    i = i + 1
  ForEver
EndProcedure

; clock.zone accepts a named rule or an explicit fixed offset. Unknown names
; are refused; an NTP server location is never used to infer a zone.
Procedure.i WallClockSetZoneName(*name)
  Define sign.i
  Define hh.i
  Define mm.i
  Define seconds.i
  wallclock_err = #WALLCLOCK_ERR_NONE
  If wallclock_StrEq(*name, "UTC") <> 0
    wallclock_zone = 0
    wallclock_zoneMode = #WALLCLOCK_ZONE_UTC
    wallclock_zoneSet = 1
    ProcedureReturn 1
  EndIf
  If wallclock_StrEq(*name, "America/Chicago") <> 0
    wallclock_zone = -21600
    wallclock_zoneMode = #WALLCLOCK_ZONE_CHICAGO
    wallclock_zoneSet = 1
    ProcedureReturn 1
  EndIf
  If *name <> 0
    If (PeekB(*name) & $FF) = 102 And (PeekB(*name + 1) & $FF) = 105 And (PeekB(*name + 2) & $FF) = 120 And (PeekB(*name + 3) & $FF) = 101 And (PeekB(*name + 4) & $FF) = 100 And (PeekB(*name + 5) & $FF) = 58
      sign = PeekB(*name + 6) & $FF
      If ((sign = 43) Or (sign = 45)) And (PeekB(*name + 9) & $FF) = 58 And (PeekB(*name + 12) & $FF) = 0
        If (PeekB(*name + 7) & $FF) >= 48 And (PeekB(*name + 7) & $FF) <= 57 And (PeekB(*name + 8) & $FF) >= 48 And (PeekB(*name + 8) & $FF) <= 57
          If (PeekB(*name + 10) & $FF) >= 48 And (PeekB(*name + 10) & $FF) <= 57 And (PeekB(*name + 11) & $FF) >= 48 And (PeekB(*name + 11) & $FF) <= 57
            hh = ((PeekB(*name + 7) & $FF) - 48) * 10 + ((PeekB(*name + 8) & $FF) - 48)
            mm = ((PeekB(*name + 10) & $FF) - 48) * 10 + ((PeekB(*name + 11) & $FF) - 48)
            If hh <= 23 And mm <= 59
              seconds = hh * 3600 + mm * 60
              If sign = 45 : seconds = 0 - seconds : EndIf
              ProcedureReturn WallClockSetZone(seconds)
            EndIf
          EndIf
        EndIf
      EndIf
    EndIf
  EndIf
  wallclock_err = #WALLCLOCK_ERR_ZONE
  ProcedureReturn 0
EndProcedure

Procedure.i WallClockZoneName()
  Define p.i
  Define z.i
  If wallclock_zoneMode = #WALLCLOCK_ZONE_CHICAGO
    ProcedureReturn "America/Chicago"
  EndIf
  If wallclock_zoneMode = #WALLCLOCK_ZONE_UTC
    ProcedureReturn "UTC"
  EndIf
  ; Fixed offsets are already validated to two-digit hours and minutes.
  z = wallclock_zone
  p = wallclock_PutStr(@wallclock_zoneBuf[0], 0, "fixed:", 23)
  If z < 0
    PokeB(@wallclock_zoneBuf[0] + p, 45)
    z = 0 - z
  Else
    PokeB(@wallclock_zoneBuf[0] + p, 43)
  EndIf
  p = wallclock_Put2(@wallclock_zoneBuf[0], p + 1, z / 3600)
  PokeB(@wallclock_zoneBuf[0] + p, 58)
  p = wallclock_Put2(@wallclock_zoneBuf[0], p + 1, (z % 3600) / 60)
  PokeB(@wallclock_zoneBuf[0] + p, 0)
  ProcedureReturn @wallclock_zoneBuf[0]
EndProcedure

; ======================================================================
;  READING IT
; ======================================================================

; ----------------------------------------------------------------------
;  WallClockNow() - UTC seconds since 1970, or #WALLCLOCK_UNKNOWN.
;
;  #WALLCLOCK_UNKNOWN (-1) whenever nothing has set the clock, and that is
;  the whole design: there is no fallback, no assumed epoch and no
;  "close enough". See THE LIE FIRST in the header.
;
;  Monotonic between sets, because it is an anchor plus a counter
;  delta and the counter cannot run backwards. If a delta ever DOES
;  come out negative - which would mean the counter went backwards,
;  something this file cannot cause and cannot fix - it is treated as
;  zero rather than allowed to produce a time earlier than the anchor.
;  A clock that goes backwards breaks every "is this newer" test in
;  the program above it.
; ----------------------------------------------------------------------
Procedure.i WallClockNow()
  Define d.i
  If wallclock_src = #WALLCLOCK_SRC_NONE
    wallclock_err = #WALLCLOCK_ERR_NOT_SET
    ProcedureReturn #WALLCLOCK_UNKNOWN
  EndIf
  If wallclock_hz <= 0
    wallclock_err = #WALLCLOCK_ERR_NO_CLOCK
    ProcedureReturn #WALLCLOCK_UNKNOWN
  EndIf
  d = wallclock_Ticks() - wallclock_baseTick
  If d < 0
    d = 0
  EndIf
  ProcedureReturn wallclock_baseEpoch + d / wallclock_hz
EndProcedure

; ----------------------------------------------------------------------
;  WallClockLocalNow() - the same, shifted by the zone offset.
;
;  FOR DISPLAY ONLY. Never store this, never put it in a file, never
;  hand it to SNTP arithmetic: it is UTC plus an offset a person typed
;  and it carries no record of that offset. Everything persistent in
;  this file is UTC.
; ----------------------------------------------------------------------
Procedure.i WallClockLocalNow()
  Define t.i
  t = WallClockNow()
  If t = #WALLCLOCK_UNKNOWN
    ProcedureReturn #WALLCLOCK_UNKNOWN
  EndIf
  ProcedureReturn t + WallClockOffsetAt(t)
EndProcedure

; ----------------------------------------------------------------------
;  WallClockMicros() - microseconds into the current second, 0..999999.
;
;  The counter runs at 54 MHz, so this is genuinely sub-second
;  information and not a rounded-off zero. It is the fractional part
;  ONLY; combining it with WallClockNow() is the caller's job, and it is
;  deliberately not returned as one number because epoch microseconds
;  invites a caller to subtract two of them across a re-set.
;
;  ((delta % hz) * 1000000) cannot overflow: the remainder is under
;  the frequency, so at 54 MHz the product is at most 5.4e13 against a
;  signed 64-bit ceiling of 9.2e18.
; ----------------------------------------------------------------------
Procedure.i WallClockMicros()
  Define d.i
  If wallclock_src = #WALLCLOCK_SRC_NONE Or wallclock_hz <= 0
    ProcedureReturn 0
  EndIf
  d = wallclock_Ticks() - wallclock_baseTick
  If d < 0
    d = 0
  EndIf
  ProcedureReturn ((d % wallclock_hz) * 1000000) / wallclock_hz
EndProcedure

; ----------------------------------------------------------------------
;  WallClockHasTime() - 1 if anything has set the clock.
;
;  "There is a value" - NOT "the value is trustworthy". See
;  WallClockTrusted().
; ----------------------------------------------------------------------
Procedure.i WallClockHasTime()
  If wallclock_src = #WALLCLOCK_SRC_NONE
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; Stable public spelling used by the banner and services. A restored floor
; is a valid value with untrusted provenance; callers needing evidence use
; WallClockTrusted() as the stronger question.
Procedure.i WallClockValid()
  ProcedureReturn WallClockHasTime()
EndProcedure

; ----------------------------------------------------------------------
;  WallClockTrusted() - 1 if the value may be presented as the time.
;
;  MANUAL and NETWORK are trusted; RESTORED is not, because a time read
;  back from the boot medium is a lower bound and not a time - see THE
;  FLOOR in the header. This is the test the FAT seam uses and the one
;  your own code should use before writing a timestamp anywhere it will
;  outlive the session.
; ----------------------------------------------------------------------
Procedure.i WallClockTrusted()
  If wallclock_src = #WALLCLOCK_SRC_MANUAL Or wallclock_src = #WALLCLOCK_SRC_SNTP
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WallClockSource()
  ProcedureReturn wallclock_src
EndProcedure

Procedure.i WallClockSetCount()
  ProcedureReturn wallclock_setCount
EndProcedure

Procedure.i WallClockLastStep()
  ProcedureReturn wallclock_lastStep
EndProcedure

; ----------------------------------------------------------------------
;  WallClockAge() - seconds since the clock was last set. 0 if never.
;
;  THE NUMBER A READER NEEDS NEXT TO A TIMESTAMP. Error accumulates
;  from the anchor and from nowhere else, so a stamp two minutes old is
;  as good as its source and one three weeks old is a guess with a
;  decimal point.
; ----------------------------------------------------------------------
Procedure.i WallClockAge()
  Define d.i
  If wallclock_src = #WALLCLOCK_SRC_NONE Or wallclock_hz <= 0
    ProcedureReturn 0
  EndIf
  d = wallclock_Ticks() - wallclock_baseTick
  If d < 0
    d = 0
  EndIf
  ProcedureReturn d / wallclock_hz
EndProcedure

; ----------------------------------------------------------------------
;  WallClockDriftSeconds(ppm) - how far this clock could have wandered.
;
;  THE CALLER SUPPLIES THE ASSUMPTION. Nothing on this disk states the
;  accuracy of the board's crystal and this bench cannot measure it, so
;  a drift figure baked into this file would be invented. Hand it the
;  parts-per-million you are willing to assume - 50 is an ordinary
;  board crystal - and it returns the bound that follows from the age
;  of the anchor:  seconds = age * ppm / 1000000.
;
;  Returns 0 for a clock that was never set, and for ppm <= 0.
;
;  IT IS A BOUND ON MAGNITUDE, NOT AN ERROR. The sign is unknown: the
;  clock may be that far ahead or that far behind.
; ----------------------------------------------------------------------
Procedure.i WallClockDriftSeconds(ppm.i)
  If ppm <= 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn (WallClockAge() * ppm) / 1000000
EndProcedure

; ======================================================================
;  THE CALENDAR
; ======================================================================

; ----------------------------------------------------------------------
;  WallClockLeapYear(y) - 1 if y is a leap year in the Gregorian calendar.
;
;  Divisible by 4, except not by 100, except yes by 400. Written as
;  three separate tests rather than one expression so that each rule is
;  visible on its own line; the house rule about `Or` needing a full
;  comparison on both sides is what the spelling below satisfies.
; ----------------------------------------------------------------------
Procedure.i WallClockLeapYear(y.i)
  If (y % 4) <> 0
    ProcedureReturn 0
  EndIf
  If (y % 100) <> 0
    ProcedureReturn 1
  EndIf
  If (y % 400) = 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  WallClockYearDays(y) - 365, or 366 in a leap year.
; ----------------------------------------------------------------------
Procedure.i WallClockYearDays(y.i)
  ProcedureReturn 365 + WallClockLeapYear(y)
EndProcedure

; ----------------------------------------------------------------------
;  WallClockMonthDays(y, m) - days in month m of year y. 0 if m is not 1..12.
;
;  A Select rather than a table, because a table needs initialising at
;  run time on this compiler (a Global Dim cannot carry initial values)
;  and an initialiser that has not run yet is a silent field of zeros.
;  Twelve cases cost nothing and cannot be uninitialised.
; ----------------------------------------------------------------------
Procedure.i WallClockMonthDays(y.i, m.i)
  Select m
    Case 1
      ProcedureReturn 31
    Case 2
      ProcedureReturn 28 + WallClockLeapYear(y)
    Case 3
      ProcedureReturn 31
    Case 4
      ProcedureReturn 30
    Case 5
      ProcedureReturn 31
    Case 6
      ProcedureReturn 30
    Case 7
      ProcedureReturn 31
    Case 8
      ProcedureReturn 31
    Case 9
      ProcedureReturn 30
    Case 10
      ProcedureReturn 31
    Case 11
      ProcedureReturn 30
    Case 12
      ProcedureReturn 31
  EndSelect
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  WallClockValidCivil(y, mo, d, h, mi, s) - 1 if that is a real instant.
;
;  Checks the day against the actual length of the actual month, so
;  2026-02-29 fails and 2028-02-29 passes. Seconds stop at 59: this
;  clock is on the POSIX scale and has no 61-second minute, which is
;  the leap-second bargain stated in the header.
; ----------------------------------------------------------------------
Procedure.i WallClockValidCivil(y.i, mo.i, d.i, h.i, mi.i, s.i)
  If y < #WALLCLOCK_FAT_YEAR0 Or y > 2099
    ProcedureReturn 0
  EndIf
  If mo < 1 Or mo > 12
    ProcedureReturn 0
  EndIf
  If d < 1 Or d > WallClockMonthDays(y, mo)
    ProcedureReturn 0
  EndIf
  If h < 0 Or h > 23
    ProcedureReturn 0
  EndIf
  If mi < 0 Or mi > 59
    ProcedureReturn 0
  EndIf
  If s < 0 Or s > 59
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  WallClockToEpoch(y, mo, d, h, mi, s) - a UTC date to seconds since 1970.
;
;  Returns -1 for anything that is not a valid instant in the accepted
;  range, with WallClockLastError() = #WALLCLOCK_ERR_CIVIL.
;
;  Two counting loops, bounded at 130 and 12 - see THE CALENDAR in the
;  header for why this is a loop and not the era algorithm. While
;  rather than For because both ranges can be EMPTY (January of 1980
;  runs neither loop), and an empty For is exactly the shape that turns
;  out to execute once on some compiler somewhere.
; ----------------------------------------------------------------------
Procedure.i WallClockToEpoch(y.i, mo.i, d.i, h.i, mi.i, s.i)
  Define days.i
  Define yy.i
  Define mm.i

  wallclock_err = #WALLCLOCK_ERR_NONE
  If WallClockValidCivil(y, mo, d, h, mi, s) = 0
    wallclock_err = #WALLCLOCK_ERR_CIVIL
    ProcedureReturn -1
  EndIf

  days = 0
  yy = 1970
  While yy < y
    days = days + WallClockYearDays(yy)
    yy = yy + 1
  Wend

  mm = 1
  While mm < mo
    days = days + WallClockMonthDays(y, mm)
    mm = mm + 1
  Wend

  days = days + d - 1
  ProcedureReturn days * #WALLCLOCK_SECS_PER_DAY + h * #WALLCLOCK_SECS_PER_HOUR + mi * 60 + s
EndProcedure

; ----------------------------------------------------------------------
;  WallClockToCivil(epoch) - break a UTC epoch into the six fields.
;
;  Returns 1 and fills WallClockYear() .. WallClockSecond(). Returns 0 and ZEROES
;  all six for anything outside the accepted range, so that a caller
;  who ignores the return value formats 0000-00-00 - obviously broken -
;  rather than a stale date left over from the previous call, which is
;  obviously fine and completely wrong.
; ----------------------------------------------------------------------
Procedure.i WallClockToCivil(epoch.i)
  Define days.i
  Define rem.i
  Define y.i
  Define mo.i
  Define n.i

  wallclock_err = #WALLCLOCK_ERR_NONE
  If epoch < #WALLCLOCK_EPOCH_MIN Or epoch >= #WALLCLOCK_EPOCH_MAX
    wallclock_y  = 0
    wallclock_mo = 0
    wallclock_d  = 0
    wallclock_h  = 0
    wallclock_mi = 0
    wallclock_s  = 0
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn 0
  EndIf

  ; Both quotient and remainder are non-negative here because the
  ; accepted range starts well above zero. That is worth stating: this
  ; compiler's divide truncates toward zero, so a negative epoch would
  ; give a remainder of the wrong sign and a date a day out - which is
  ; the second reason pre-1980 is refused rather than supported.
  days = epoch / #WALLCLOCK_SECS_PER_DAY
  rem  = epoch - days * #WALLCLOCK_SECS_PER_DAY

  y = 1970
  n = WallClockYearDays(y)
  While days >= n
    days = days - n
    y = y + 1
    n = WallClockYearDays(y)
  Wend

  mo = 1
  n = WallClockMonthDays(y, mo)
  While days >= n
    days = days - n
    mo = mo + 1
    n = WallClockMonthDays(y, mo)
  Wend

  wallclock_y  = y
  wallclock_mo = mo
  wallclock_d  = days + 1
  wallclock_h  = rem / #WALLCLOCK_SECS_PER_HOUR
  wallclock_mi = (rem - wallclock_h * #WALLCLOCK_SECS_PER_HOUR) / 60
  wallclock_s  = rem - wallclock_h * #WALLCLOCK_SECS_PER_HOUR - wallclock_mi * 60
  ProcedureReturn 1
EndProcedure

Procedure.i WallClockYear()
  ProcedureReturn wallclock_y
EndProcedure

Procedure.i WallClockMonth()
  ProcedureReturn wallclock_mo
EndProcedure

Procedure.i WallClockDay()
  ProcedureReturn wallclock_d
EndProcedure

Procedure.i WallClockHour()
  ProcedureReturn wallclock_h
EndProcedure

Procedure.i WallClockMinute()
  ProcedureReturn wallclock_mi
EndProcedure

Procedure.i WallClockSecond()
  ProcedureReturn wallclock_s
EndProcedure

; Sunday is zero. 1970-01-01 was Thursday (4), so an epoch-day count is
; enough and stays independent of any platform calendar service.
Procedure.i wallclock_Weekday(epoch.i)
  ProcedureReturn ((epoch / #WALLCLOCK_SECS_PER_DAY) + 4) % 7
EndProcedure

Procedure.i wallclock_NthSunday(y.i, mo.i, nth.i)
  Define first.i
  Define firstSunday.i
  first = WallClockToEpoch(y, mo, 1, 0, 0, 0)
  If first < 0 : ProcedureReturn 0 : EndIf
  firstSunday = 1 + ((7 - wallclock_Weekday(first)) % 7)
  ProcedureReturn firstSunday + (nth - 1) * 7
EndProcedure

Procedure.i wallclock_LastSunday(y.i, mo.i)
  Define days.i
  Define last.i
  days = WallClockMonthDays(y, mo)
  last = WallClockToEpoch(y, mo, days, 0, 0, 0)
  If last < 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn days - wallclock_Weekday(last)
EndProcedure

; America/Chicago rules across the supported 1980..2099 range. Congress
; changed the US dates in 1987 and 2007; encoding those transitions avoids
; applying today's rule to older restored timestamps. A future statutory
; change requires a source update rather than a location guess.
Procedure.i wallclock_ChicagoIsDst(epoch.i)
  Define y.i
  Define sd.i
  Define ed.i
  Define startUtc.i
  Define endUtc.i
  If WallClockToCivil(epoch) = 0 : ProcedureReturn 0 : EndIf
  y = wallclock_y
  If y < 1987
    sd = wallclock_LastSunday(y, 4)
    ed = wallclock_LastSunday(y, 10)
  ElseIf y < 2007
    sd = wallclock_NthSunday(y, 4, 1)
    ed = wallclock_LastSunday(y, 10)
  Else
    sd = wallclock_NthSunday(y, 3, 2)
    ed = wallclock_NthSunday(y, 11, 1)
  EndIf
  ; 02:00 CST is 08:00 UTC; 02:00 CDT is 07:00 UTC.
  If y < 1987
    startUtc = WallClockToEpoch(y, 4, sd, 8, 0, 0)
    endUtc = WallClockToEpoch(y, 10, ed, 7, 0, 0)
  ElseIf y < 2007
    startUtc = WallClockToEpoch(y, 4, sd, 8, 0, 0)
    endUtc = WallClockToEpoch(y, 10, ed, 7, 0, 0)
  Else
    startUtc = WallClockToEpoch(y, 3, sd, 8, 0, 0)
    endUtc = WallClockToEpoch(y, 11, ed, 7, 0, 0)
  EndIf
  If epoch >= startUtc And epoch < endUtc
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WallClockOffsetAt(epoch.i)
  If wallclock_zoneMode = #WALLCLOCK_ZONE_CHICAGO
    If wallclock_ChicagoIsDst(epoch) <> 0
      ProcedureReturn -18000
    EndIf
    ProcedureReturn -21600
  EndIf
  ProcedureReturn wallclock_zone
EndProcedure

; ======================================================================
;  NTP - the one piece of SNTP that is about time rather than networking
; ======================================================================

; ----------------------------------------------------------------------
;  WallClockNtpToEpoch(ntpSeconds) - NTP era-0 seconds to Unix seconds.
;
;  An SNTP reply carries a 64-bit timestamp whose top 32 bits are
;  seconds since 1900-01-01 (RFC 5905 section 6, rfc5905.txt:721-722).
;  Subtract #WALLCLOCK_NTP_EPOCH and it is a Unix epoch.
;
;  Returns -1, with #WALLCLOCK_ERR_RANGE, for anything that does not land in
;  the accepted range - which includes zero, the value an SNTP reply
;  carries when the server is saying it has no time itself. A server
;  that admits it does not know must not be turned into 1900-01-01 and
;  then into a file date.
;
;  ERA 0 RUNS OUT IN 2036, when the 32-bit second count wraps
;  (rfc5905.txt:741). This procedure takes a .i, which is 64 bits on
;  this target, so a CALLER that has already handled the era can pass
;  the extended value straight through and it will work. What it must
;  not do is pass a raw wrapped 32-bit field and expect this to guess
;  which era it belongs to: after 2036 that field alone is genuinely
;  ambiguous, and the range check here will refuse the result rather
;  than silently produce 1900.
; ----------------------------------------------------------------------
Procedure.i WallClockNtpToEpoch(ntpSeconds.i)
  Define e.i
  wallclock_err = #WALLCLOCK_ERR_NONE
  If ntpSeconds <= 0
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn -1
  EndIf
  e = ntpSeconds - #WALLCLOCK_NTP_EPOCH
  If e < #WALLCLOCK_EPOCH_MIN Or e >= #WALLCLOCK_EPOCH_MAX
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn -1
  EndIf
  ProcedureReturn e
EndProcedure

; Convert the unsigned 32-bit seconds field carried on the wire. The packet
; does not carry an era number. Within this clock's deliberately bounded
; 1980..2099 range exactly one of era 0 or era 1 can be valid, including the
; 2036 rollover described by RFC 5905 section 6.
Procedure.i WallClockNtp32ToEpoch(raw.i)
  Define e0.i
  Define e1.i
  wallclock_err = #WALLCLOCK_ERR_NONE
  If raw < 0 Or raw > 4294967295
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn -1
  EndIf
  e0 = raw - #WALLCLOCK_NTP_EPOCH
  If e0 >= #WALLCLOCK_EPOCH_MIN And e0 < #WALLCLOCK_EPOCH_MAX
    ProcedureReturn e0
  EndIf
  e1 = raw + 4294967296 - #WALLCLOCK_NTP_EPOCH
  If e1 >= #WALLCLOCK_EPOCH_MIN And e1 < #WALLCLOCK_EPOCH_MAX
    ProcedureReturn e1
  EndIf
  wallclock_err = #WALLCLOCK_ERR_RANGE
  ProcedureReturn -1
EndProcedure

; ----------------------------------------------------------------------
;  WallClockEpochToNtp(epoch) - the other direction, for a request packet.
;
;  Returns -1 for an epoch outside the accepted range.
; ----------------------------------------------------------------------
Procedure.i WallClockEpochToNtp(epoch.i)
  wallclock_err = #WALLCLOCK_ERR_NONE
  If epoch < #WALLCLOCK_EPOCH_MIN Or epoch >= #WALLCLOCK_EPOCH_MAX
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn -1
  EndIf
  ProcedureReturn epoch + #WALLCLOCK_NTP_EPOCH
EndProcedure

; ======================================================================
;  THE FAT SEAM
; ======================================================================

; ----------------------------------------------------------------------
;  WallClockFatDate() - the packed [FATGEN] date word, or 0.
;
;  date = ((year - 1980) << 9) | (month << 5) | day, transcribed from
;  fat.pi4:4112, which is where this tree documents the format.
;
;  RETURNS 0 - WHICH fat.pi4 REFUSES - unless WallClockTrusted() is 1. A
;  restored-from-disk time is a floor and must not become a file's
;  modification date; see THE FLOOR in the header. The caller's own
;  guard is the one that matters:
;
;      If WallClockTrusted() <> 0
;        FatSetTimestamp(WallClockFatDate(), WallClockFatTime())
;      EndIf
;
;  Uses WallClockToCivil(), so it CLOBBERS the six broken-down fields. Call
;  it before reading WallClockYear() and friends, not after.
; ----------------------------------------------------------------------
Procedure.i WallClockFatDate()
  If WallClockTrusted() = 0
    wallclock_err = #WALLCLOCK_ERR_NOT_SET
    ProcedureReturn 0
  EndIf
  If WallClockToCivil(WallClockLocalNow()) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn ((wallclock_y - #WALLCLOCK_FAT_YEAR0) << 9) | (wallclock_mo << 5) | wallclock_d
EndProcedure

; ----------------------------------------------------------------------
;  WallClockFatTime() - the packed [FATGEN] time word, or 0.
;
;  time = (hour << 11) | (minute << 5) | (second / 2), from the same
;  line of fat.pi4. THE SECONDS FIELD IS FIVE BITS AND COUNTS TWO-
;  SECOND UNITS - that is the format's limitation, not a rounding
;  choice made here, and it means an odd second is truncated down. It
;  truncates rather than rounding because rounding 59 upward produces
;  30 in a field whose legal maximum is 29, which fat.pi4:4155 refuses.
;
;  LOCAL TIME, NOT UTC, AND THAT IS THE FORMAT'S FAULT. [FATGEN] stores
;  a wall-clock date with no zone at all, so every operating system
;  writes local time there. Writing UTC would make our files look
;  hours off in a file manager next to files written by anything else.
;  With the zone offset left at zero this is UTC, which is the honest
;  default for a board that has not been told where it is.
;
;  Returns 0 unless WallClockTrusted() is 1. Zero is midnight, which IS a
;  legal time word, so unlike WallClockFatDate() this value would not be
;  refused by fat.pi4 on its own - which is exactly why the two must
;  be gated together by the caller's If, and why the header says so
;  twice.
; ----------------------------------------------------------------------
Procedure.i WallClockFatTime()
  If WallClockTrusted() = 0
    wallclock_err = #WALLCLOCK_ERR_NOT_SET
    ProcedureReturn 0
  EndIf
  If WallClockToCivil(WallClockLocalNow()) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn (wallclock_h << 11) | (wallclock_mi << 5) | (wallclock_s / 2)
EndProcedure

; ======================================================================
;  TEXT
; ======================================================================

; ----------------------------------------------------------------------
;  wallclock_Put2 / wallclock_Put4 / wallclock_PutStr - buffer writers. Private.
;
;  Each takes the buffer address and a position, writes, and returns
;  the new position, so a formatter reads as a straight line with no
;  index arithmetic between the pieces.
;
;  THIS LANGUAGE HAS NO CHARACTER LITERALS, so every byte here is a
;  number with the character named beside it. 48 is the digit zero.
; ----------------------------------------------------------------------
Procedure.i wallclock_Put2(*buf, pos.i, v.i)
  PokeB(*buf + pos, 48 + (v / 10) % 10)
  PokeB(*buf + pos + 1, 48 + v % 10)
  ProcedureReturn pos + 2
EndProcedure

Procedure.i wallclock_Put4(*buf, pos.i, v.i)
  PokeB(*buf + pos, 48 + (v / 1000) % 10)
  PokeB(*buf + pos + 1, 48 + (v / 100) % 10)
  PokeB(*buf + pos + 2, 48 + (v / 10) % 10)
  PokeB(*buf + pos + 3, 48 + v % 10)
  ProcedureReturn pos + 4
EndProcedure

Procedure.i wallclock_PutStr(*buf, pos.i, *s, lim.i)
  Define c.i
  Define i.i
  i = 0
  c = PeekB(*s) & $FF
  While c <> 0 And pos < lim
    PokeB(*buf + pos, c)
    pos = pos + 1
    i = i + 1
    c = PeekB(*s + i) & $FF
  Wend
  ProcedureReturn pos
EndProcedure

; A decimal integer into a buffer. Handles the sign and zero; the
; magnitude is emitted by walking a divisor down, the same shape
; PrintDec uses (uart.pi4:1119), because a digit-reversing buffer would
; need a second buffer.
Procedure.i wallclock_PutDec(*buf, pos.i, v.i, lim.i)
  Define scale.i
  Define d.i
  Define started.i
  If v < 0
    If pos < lim
      PokeB(*buf + pos, 45)               ; minus
      pos = pos + 1
    EndIf
    v = 0 - v
  EndIf
  If v = 0
    If pos < lim
      PokeB(*buf + pos, 48)               ; zero
      pos = pos + 1
    EndIf
    ProcedureReturn pos
  EndIf
  ; 10^18, built by multiplication so the constant folder cannot see it
  ; overflow a narrower model - the trap uart.pi4:1100-1117 documents.
  scale = 1000000000
  scale = scale * 1000000000
  If scale <= 0
    scale = 1000000000
  EndIf
  started = 0
  While scale > 0
    d = (v / scale) % 10
    If d <> 0 Or started <> 0
      If pos < lim
        PokeB(*buf + pos, 48 + d)
        pos = pos + 1
      EndIf
      started = 1
    EndIf
    scale = scale / 10
  Wend
  ProcedureReturn pos
EndProcedure

; ----------------------------------------------------------------------
;  WallClockStampUtc() - "2026-08-28 14:03:11 UTC", or "time unknown".
;
;  ISO-style and therefore SORTABLE AS TEXT, which is why this spelling
;  survives house rule 20 for logs and filenames while WallClockStampLocal()
;  serves the human display. The zone is written out because a stamp
;  without one is the thing that starts arguments.
;
;  Returns the address of a NUL-terminated string in this file's own
;  buffer, overwritten by the next call to THIS procedure only - see
;  the three-buffer note at the globals.
;
;  NEVER SET, NEVER GUESSED: with no clock this returns the words
;  "time unknown" rather than an epoch-zero date.
; ----------------------------------------------------------------------
Procedure.i WallClockStampUtc()
  Define p.i
  Define t.i

  t = WallClockNow()
  If t = #WALLCLOCK_UNKNOWN
    p = wallclock_PutStr(@wallclock_utcBuf[0], 0, "time unknown", 31)
    PokeB(@wallclock_utcBuf[0] + p, 0)
    ProcedureReturn @wallclock_utcBuf[0]
  EndIf
  If WallClockToCivil(t) = 0
    p = wallclock_PutStr(@wallclock_utcBuf[0], 0, "time out of range", 31)
    PokeB(@wallclock_utcBuf[0] + p, 0)
    ProcedureReturn @wallclock_utcBuf[0]
  EndIf

  p = wallclock_Put4(@wallclock_utcBuf[0], 0, wallclock_y)
  PokeB(@wallclock_utcBuf[0] + p, 45)           ; hyphen
  p = wallclock_Put2(@wallclock_utcBuf[0], p + 1, wallclock_mo)
  PokeB(@wallclock_utcBuf[0] + p, 45)           ; hyphen
  p = wallclock_Put2(@wallclock_utcBuf[0], p + 1, wallclock_d)
  PokeB(@wallclock_utcBuf[0] + p, 32)           ; space
  p = wallclock_Put2(@wallclock_utcBuf[0], p + 1, wallclock_h)
  PokeB(@wallclock_utcBuf[0] + p, 58)           ; colon
  p = wallclock_Put2(@wallclock_utcBuf[0], p + 1, wallclock_mi)
  PokeB(@wallclock_utcBuf[0] + p, 58)           ; colon
  p = wallclock_Put2(@wallclock_utcBuf[0], p + 1, wallclock_s)
  p = wallclock_PutStr(@wallclock_utcBuf[0], p, " UTC", 31)
  PokeB(@wallclock_utcBuf[0] + p, 0)
  ProcedureReturn @wallclock_utcBuf[0]
EndProcedure

; ----------------------------------------------------------------------
;  WallClockStampLocal() - "08/28/2026 02:03:11 PM", or "time unknown".
;
;  Month/day/year and a 12-hour clock, which is what an American
;  engineer reading a console actually wants - vault rule 20. With the
;  zone offset at its default of zero this is UTC wearing American
;  clothes, which is honest: the board has not been told where it is.
;
;  MIDNIGHT IS 12 AM AND NOON IS 12 PM, which is the one thing a
;  12-hour formatter always gets wrong. hour 0 prints as 12 AM, hour 12
;  prints as 12 PM, and hours 13..23 print as 1..11 PM.
; ----------------------------------------------------------------------
Procedure.i WallClockStampLocal()
  Define p.i
  Define t.i
  Define h12.i
  Define pm.i

  t = WallClockLocalNow()
  If t = #WALLCLOCK_UNKNOWN
    p = wallclock_PutStr(@wallclock_locBuf[0], 0, "time unknown", 31)
    PokeB(@wallclock_locBuf[0] + p, 0)
    ProcedureReturn @wallclock_locBuf[0]
  EndIf
  If WallClockToCivil(t) = 0
    p = wallclock_PutStr(@wallclock_locBuf[0], 0, "time out of range", 31)
    PokeB(@wallclock_locBuf[0] + p, 0)
    ProcedureReturn @wallclock_locBuf[0]
  EndIf

  pm = 0
  If wallclock_h >= 12
    pm = 1
  EndIf
  h12 = wallclock_h % 12
  If h12 = 0
    h12 = 12
  EndIf

  p = wallclock_Put2(@wallclock_locBuf[0], 0, wallclock_mo)
  PokeB(@wallclock_locBuf[0] + p, 47)           ; solidus
  p = wallclock_Put2(@wallclock_locBuf[0], p + 1, wallclock_d)
  PokeB(@wallclock_locBuf[0] + p, 47)           ; solidus
  p = wallclock_Put4(@wallclock_locBuf[0], p + 1, wallclock_y)
  PokeB(@wallclock_locBuf[0] + p, 32)           ; space
  p = wallclock_Put2(@wallclock_locBuf[0], p + 1, h12)
  PokeB(@wallclock_locBuf[0] + p, 58)           ; colon
  p = wallclock_Put2(@wallclock_locBuf[0], p + 1, wallclock_mi)
  PokeB(@wallclock_locBuf[0] + p, 58)           ; colon
  p = wallclock_Put2(@wallclock_locBuf[0], p + 1, wallclock_s)
  If pm = 0
    p = wallclock_PutStr(@wallclock_locBuf[0], p, " AM", 31)
  Else
    p = wallclock_PutStr(@wallclock_locBuf[0], p, " PM", 31)
  EndIf
  PokeB(@wallclock_locBuf[0] + p, 0)
  ProcedureReturn @wallclock_locBuf[0]
EndProcedure

; ----------------------------------------------------------------------
;  WallClockSourceText() - where this time came from, in English.
; ----------------------------------------------------------------------
Procedure.i WallClockSourceText()
  Select wallclock_src
    Case #WALLCLOCK_SRC_MANUAL
      ProcedureReturn "set by hand"
    Case #WALLCLOCK_SRC_RESTORED
      ProcedureReturn "restored from disk - a floor, not a time"
    Case #WALLCLOCK_SRC_SNTP
      ProcedureReturn "SNTP/network reply (not authenticated)"
  EndSelect
  ProcedureReturn "never set"
EndProcedure

; ----------------------------------------------------------------------
;  WallClockLine() - THE ONE TO PRINT. Stamp, provenance and age together.
;
;    "08/28/2026 02:03:11 PM  [set by hand, 47 s ago]"
;    "clock not set (board up 312 s)"
;
;  WHY THIS EXISTS AS ITS OWN PROCEDURE. WallClockStampLocal() on its own is
;  a timestamp with no provenance, and a timestamp with no provenance
;  gets believed. Every part of this file that could be used to state
;  a time confidently is therefore paired here with the two facts that
;  qualify it, in one call, so that the honest form is also the easy
;  one. A caller who wants the bare stamp can still have it; a caller
;  who is not thinking about the question gets the truth by default.
;
;  When the clock is unset it reports the UPTIME instead, because "up
;  312 seconds" is the one time-like statement this board can make on
;  its own and it is often the answer the reader actually needed.
; ----------------------------------------------------------------------
Procedure.i WallClockLine()
  Define p.i

  If wallclock_src = #WALLCLOCK_SRC_NONE
    p = wallclock_PutStr(@wallclock_lineBuf[0], 0, "clock not set (board up ", 127)
    p = wallclock_PutDec(@wallclock_lineBuf[0], p, WallClockUptime(), 127)
    p = wallclock_PutStr(@wallclock_lineBuf[0], p, " s)", 127)
    PokeB(@wallclock_lineBuf[0] + p, 0)
    ProcedureReturn @wallclock_lineBuf[0]
  EndIf

  p = wallclock_PutStr(@wallclock_lineBuf[0], 0, WallClockStampLocal(), 127)
  p = wallclock_PutStr(@wallclock_lineBuf[0], p, "  [", 127)
  p = wallclock_PutStr(@wallclock_lineBuf[0], p, WallClockSourceText(), 127)
  p = wallclock_PutStr(@wallclock_lineBuf[0], p, ", ", 127)
  p = wallclock_PutDec(@wallclock_lineBuf[0], p, WallClockAge(), 127)
  p = wallclock_PutStr(@wallclock_lineBuf[0], p, " s ago]", 127)
  PokeB(@wallclock_lineBuf[0] + p, 0)
  ProcedureReturn @wallclock_lineBuf[0]
EndProcedure

; Compact banner contract. Detailed provenance and age remain in
; WallClockLine() for the clock command. The returned pointer remains valid
; until the next call. No location is inferred from an NTP server.
Procedure.i WallClockCaption()
  Define p.i
  Define z.i
  Define zh.i
  Define zm.i

  If wallclock_src = #WALLCLOCK_SRC_NONE
    p = wallclock_PutStr(@wallclock_lineBuf[0], 0, "Time not synchronized", 127)
    PokeB(@wallclock_lineBuf[0] + p, 0)
    ProcedureReturn @wallclock_lineBuf[0]
  EndIf

  ; A restored disk value is only a lower bound. Do not place a plausible
  ; ticking date in the banner where narrow-screen tail clipping could hide
  ; its caveat. The full floor remains visible in `time` status.
  If wallclock_src = #WALLCLOCK_SRC_RESTORED
    p = wallclock_PutStr(@wallclock_lineBuf[0], 0, "Time not synchronized", 127)
    PokeB(@wallclock_lineBuf[0] + p, 0)
    ProcedureReturn @wallclock_lineBuf[0]
  EndIf

  p = 0
  If wallclock_src = #WALLCLOCK_SRC_MANUAL
    p = wallclock_PutStr(@wallclock_lineBuf[0], p, "Manual: ", 127)
  EndIf
  p = wallclock_PutStr(@wallclock_lineBuf[0], p, WallClockStampLocal(), 127)
  If wallclock_zoneMode = #WALLCLOCK_ZONE_CHICAGO
    If WallClockOffsetAt(WallClockNow()) = -18000
      p = wallclock_PutStr(@wallclock_lineBuf[0], p, " CDT", 127)
    Else
      p = wallclock_PutStr(@wallclock_lineBuf[0], p, " CST", 127)
    EndIf
  ElseIf wallclock_zoneSet = 0 Or wallclock_zone = 0
    p = wallclock_PutStr(@wallclock_lineBuf[0], p, " UTC", 127)
  Else
    z = wallclock_zone
    If z < 0
      p = wallclock_PutStr(@wallclock_lineBuf[0], p, " UTC-", 127)
      z = 0 - z
    Else
      p = wallclock_PutStr(@wallclock_lineBuf[0], p, " UTC+", 127)
    EndIf
    zh = z / 3600
    zm = (z % 3600) / 60
    p = wallclock_Put2(@wallclock_lineBuf[0], p, zh)
    PokeB(@wallclock_lineBuf[0] + p, 58)
    p = wallclock_Put2(@wallclock_lineBuf[0], p + 1, zm)
  EndIf
  PokeB(@wallclock_lineBuf[0] + p, 0)
  ProcedureReturn @wallclock_lineBuf[0]
EndProcedure

; ======================================================================
;  PERSISTENCE - the two halves that belong to time rather than storage
; ======================================================================

; ----------------------------------------------------------------------
;  WallClockSettingsKey() - the settings.pi4 key, spelled in ONE place.
;
;  Lowercase and dotted, matching settings.pi4's own keys
;  ("wifi.network", settings.pi4:1748). One procedure so that the
;  saver and the loader cannot drift apart by a character, which is
;  the failure mode that makes a persisted value silently never
;  reload.
; ----------------------------------------------------------------------
Procedure.i WallClockSettingsKey()
  ProcedureReturn "clock.utc"
EndProcedure

Procedure.i WallClockZoneSettingsKey()
  ProcedureReturn "clock.zone"
EndProcedure

; ----------------------------------------------------------------------
;  WallClockEncode(epoch) - the epoch as decimal text, for a settings value.
;
;  Returns the address of a NUL-terminated string in this file's own
;  number buffer. Decimal and not hex, because a person editing
;  SETTINGS.TXT on another machine can paste a Unix timestamp in from
;  anywhere; nothing else in that file is hex either.
; ----------------------------------------------------------------------
Procedure.i WallClockEncode(epoch.i)
  Define p.i
  p = wallclock_PutDec(@wallclock_numBuf[0], 0, epoch, 23)
  PokeB(@wallclock_numBuf[0] + p, 0)
  ProcedureReturn @wallclock_numBuf[0]
EndProcedure

; ----------------------------------------------------------------------
;  WallClockDecode(*s) - decimal text back to an epoch, or -1.
;
;  REFUSES rather than parsing as far as it can. "2026-08-28" and
;  "1756389791x" and an empty string all return -1 with
;  #WALLCLOCK_ERR_TEXT, because a settings file that has been hand-edited
;  into something else must not silently become a plausible time.
;  Leading and trailing spaces are accepted - settings.pi4 already
;  trims, but a value pasted by hand may not have been.
;
;  No sign is accepted: every epoch in the accepted range is positive,
;  and a negative one would be refused by WallClockSet() anyway. The range
;  is checked HERE too, so the caller gets one refusal instead of a
;  number that fails later somewhere else.
; ----------------------------------------------------------------------
Procedure.i WallClockDecode(*s)
  Define i.i
  Define c.i
  Define v.i
  Define digits.i

  wallclock_err = #WALLCLOCK_ERR_NONE
  If *s = 0
    wallclock_err = #WALLCLOCK_ERR_TEXT
    ProcedureReturn -1
  EndIf

  i = 0
  v = 0
  digits = 0

  c = PeekB(*s + i) & $FF
  While c = 32                            ; leading spaces
    i = i + 1
    c = PeekB(*s + i) & $FF
  Wend

  While c >= 48 And c <= 57               ; digits zero through nine
    v = v * 10 + (c - 48)
    digits = digits + 1
    If digits > 18                        ; more than a 64-bit epoch can be
      wallclock_err = #WALLCLOCK_ERR_TEXT
      ProcedureReturn -1
    EndIf
    i = i + 1
    c = PeekB(*s + i) & $FF
  Wend

  While c = 32                            ; trailing spaces
    i = i + 1
    c = PeekB(*s + i) & $FF
  Wend

  If digits = 0 Or c <> 0
    wallclock_err = #WALLCLOCK_ERR_TEXT
    ProcedureReturn -1
  EndIf
  If v < #WALLCLOCK_EPOCH_MIN Or v >= #WALLCLOCK_EPOCH_MAX
    wallclock_err = #WALLCLOCK_ERR_RANGE
    ProcedureReturn -1
  EndIf
  ProcedureReturn v
EndProcedure

; ======================================================================
;  ERRORS
; ======================================================================

Procedure.i WallClockLastError()
  ProcedureReturn wallclock_err
EndProcedure

; ----------------------------------------------------------------------
;  WallClockErrorText() - the address of a NUL-terminated English sentence.
;
;  Names WHAT WAS FOUND, not what to do about it, matching
;  fat.pi4:4331-4340's reasoning: a library that guessed at fixes in a
;  string would be wrong out loud.
; ----------------------------------------------------------------------
Procedure.i WallClockErrorText()
  Select wallclock_err
    Case #WALLCLOCK_ERR_NONE
      ProcedureReturn "Clock status 0: no wall-clock error is recorded."
    Case #WALLCLOCK_ERR_NO_CLOCK
      ProcedureReturn "Clock error 1: the monotonic tick source is stopped or unavailable; check the board timer."
    Case #WALLCLOCK_ERR_RANGE
      ProcedureReturn "Clock error 2: the time is outside 1980-01-01 through 2099-12-31; check the supplied date."
    Case #WALLCLOCK_ERR_SOURCE
      ProcedureReturn "Clock error 3: the source is not manual, restored, or SNTP; check the source tag."
    Case #WALLCLOCK_ERR_CIVIL
      ProcedureReturn "Clock error 4: the civil fields do not name one unambiguous date and time; check the requested local time."
    Case #WALLCLOCK_ERR_NOT_SET
      ProcedureReturn "Clock error 5: no wall time is available; wait for synchronization or set it explicitly."
    Case #WALLCLOCK_ERR_TEXT
      ProcedureReturn "Clock error 6: the saved value is not a valid decimal Unix time; check clock.utc."
    Case #WALLCLOCK_ERR_ZONE
      ProcedureReturn "Clock error 7: the zone name or fixed offset is unsupported; use UTC, America/Chicago, or fixed:+HH:MM."
  EndSelect
  ProcedureReturn "Clock error: an unknown wall-clock failure occurred; inspect the last error code."
EndProcedure
