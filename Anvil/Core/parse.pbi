
; ======================================================================
;  Line editing and parsing
; ======================================================================

; The command prompt is the cooperative scheduler. Input is still checked
; first; one background lane runs per turn, with one forced lane after each
; eight admitted prompt events so typing cannot starve the screen/services.
; WFE is opt-in only after a board's deadman-protected EL3 wake probe.
Global anvil_promptServiceSlot.i = 0
Global anvil_promptWfeReady.i = 0
Global anvil_promptWfeEnabled.i = 0
Global anvil_promptProbePassed.i = 0
Global anvil_promptWfePeriod.i = 0
Global anvil_promptOldControl.i = 0
Global anvil_promptProbeSamples.i = 0
Global anvil_promptProbeMinTicks.i = 0
Global anvil_promptProbeMaxTicks.i = 0
Global anvil_promptProbeTotalTicks.i = 0
Global anvil_promptWindowStart.i = 0
Global anvil_promptIdleTicks.i = 0
Global anvil_promptCpuPercent.i = -1
Global anvil_promptCpuHundredths.i = -1
Global anvil_promptWindowReady.i = 0

; System-register helpers keep the values in the ABI return/argument register.
; Inline assembly does not bind an arbitrary local variable to x0.
Procedure.i AnvilSchedulerCounterHz()
  Asm
    mrs x0, cntfrq_el0
  EndAsm
EndProcedure

Procedure.i AnvilSchedulerCounterValue()
  Asm
    mrs x0, cntpct_el0
  EndAsm
EndProcedure

Procedure.i AnvilSchedulerReadControl()
  Asm
    mrs x0, cntkctl_el1
  EndAsm
EndProcedure

Procedure AnvilSchedulerWriteControl(value.i)
  Asm
    msr cntkctl_el1, x0
    isb
  EndAsm
EndProcedure

; Establish CNTKCTL_EL1's virtual-counter event stream. This does not
; claim the stream wakes WFE on this particular board; the board must run
; its bounded EL3 wake probe and call AnvilSchedulerWfeVerified(1).
Procedure.i AnvilSchedulerPrepareWfe()
  Define x0.i
  Define hz.i
  Define control.i
  Define oldControl.i
  Define evnti.i
  Define period.i
  Define target.i
  Define firstCount.i
  Define secondCount.i
  Define readback.i

  If MmuEl() <> 3
    ProcedureReturn 0
  EndIf
  hz = AnvilSchedulerCounterHz()
  If hz < 1000000 Or hz > 1000000000
    ProcedureReturn 0
  EndIf
  firstCount = AnvilSchedulerCounterValue()

  ; EVNTI selects a counter bit; rising transitions occur every
  ; 2^(EVNTI+1) ticks. Cap each sleep interval at 500 microseconds.
  target = hz / 2000
  evnti = 0
  period = 2
  While evnti < 15 And period <= target / 2
    evnti = evnti + 1
    period = period * 2
  Wend
  oldControl = AnvilSchedulerReadControl()
  anvil_promptOldControl = oldControl
  control = (oldControl & $FFFFFFFFFFFFFF03) | ((evnti & 15) << 4) | 4
  AnvilSchedulerWriteControl(control)
  readback = AnvilSchedulerReadControl()
  If (readback & $FC) <> (control & $FC)
    AnvilSchedulerWriteControl(oldControl)
    ProcedureReturn 0
  EndIf
  secondCount = AnvilSchedulerCounterValue()
  If secondCount <= firstCount
    AnvilSchedulerWriteControl(oldControl)
    ProcedureReturn 0
  EndIf
  anvil_promptWfePeriod = period
  anvil_promptWfeReady = 1
  ProcedureReturn period
EndProcedure

; Only call with the board deadman armed. If the configured EL3 event
; stream does not wake WFE, the hardware watchdog is the external bound.
; One unmeasured WFE drains a possibly pending event before the measured wait.
Procedure.i AnvilSchedulerWakeProbe(samples.i)
  Define x0.i
  Define n.i
  Define t0.i
  Define elapsed.i
  Define maxTicks.i
  Define total.i
  Define minSeen.i
  Define maxSeen.i
  If samples < 1 Or samples > 64
    ProcedureReturn 0
  EndIf
  If AnvilSchedulerPrepareWfe() <= 0
    ProcedureReturn 0
  EndIf
  maxTicks = (TickHz() / 500) + 1
  minSeen = $7FFFFFFFFFFFFFFF
  maxSeen = 0
  total = 0
  For n = 1 To samples
    Asm
      wfe
    EndAsm
    t0 = Ticks()
    Asm
      wfe
    EndAsm
    elapsed = Ticks() - t0
    If elapsed <= 0 Or elapsed > maxTicks
      AnvilSchedulerWriteControl(anvil_promptOldControl)
      anvil_promptWfeReady = 0
      anvil_promptWfeEnabled = 0
      anvil_promptProbePassed = 0
      anvil_promptProbeSamples = n - 1
      anvil_promptProbeMinTicks = minSeen
      anvil_promptProbeMaxTicks = maxSeen
      anvil_promptProbeTotalTicks = total
      ProcedureReturn 0
    EndIf
    If elapsed < minSeen : minSeen = elapsed : EndIf
    If elapsed > maxSeen : maxSeen = elapsed : EndIf
    total = total + elapsed
  Next
  anvil_promptProbeSamples = samples
  anvil_promptProbeMinTicks = minSeen
  anvil_promptProbeMaxTicks = maxSeen
  anvil_promptProbeTotalTicks = total
  anvil_promptProbePassed = 1
  anvil_promptWfeEnabled = 1
  ProcedureReturn samples
EndProcedure

; Standard hardware qualification is 32 samples, with the external
; watchdog armed by the board diagnostic caller.
Procedure.i AnvilSchedulerProbeWfe()
  ProcedureReturn AnvilSchedulerWakeProbe(32)
EndProcedure

Procedure.i AnvilSchedulerWakeProbeMinTicks()
  ProcedureReturn anvil_promptProbeMinTicks
EndProcedure

Procedure.i AnvilSchedulerWakeProbeMaxTicks()
  ProcedureReturn anvil_promptProbeMaxTicks
EndProcedure

Procedure.i AnvilSchedulerWakeProbeTotalTicks()
  ProcedureReturn anvil_promptProbeTotalTicks
EndProcedure

Procedure AnvilSchedulerWfeVerified(enabled.i)
  If enabled <> 0 And anvil_promptWfeReady <> 0 And anvil_promptProbePassed <> 0 And MmuEl() = 3
    anvil_promptWfeEnabled = 1
  Else
    anvil_promptWfeEnabled = 0
  EndIf
EndProcedure

; The Pi 3 Model B (BCM2837) EL3 path has a separately hardware-qualified
; event stream. Enable it only when the live counter/exception level match
; that tested configuration and CNTKCTL accepts the bounded period. This is
; a register setup/readback, not a boot-time WFE probe; other boards remain
; on the cooperative polling path until they are independently qualified.
Procedure.i AnvilSchedulerQualifyPi3Wfe()
  anvil_promptWfeReady = 0
  anvil_promptProbePassed = 0
  anvil_promptWfeEnabled = 0
  If MmuEl() <> 3 Or AnvilSchedulerCounterHz() <> 19200000
    ProcedureReturn 0
  EndIf
  If AnvilSchedulerPrepareWfe() <= 0
    anvil_promptWfeEnabled = 0
    ProcedureReturn 0
  EndIf
  ; The 32-sample deadman-protected hardware qualification is documented
  ; for this exact BCM2837/EL3/counter path. Do not repeat it on every boot.
  anvil_promptProbePassed = 1
  AnvilSchedulerWfeVerified(1)
  ProcedureReturn anvil_promptWfeEnabled
EndProcedure

; Main-core utilization only. -1 means no complete one-second window yet.
; Idle is measured only around the actual WFE instruction, not service time.
Procedure.i AnvilCpuUsagePercent()
  If anvil_promptWindowReady = 0
    ProcedureReturn -1
  EndIf
  If anvil_promptCpuHundredths < 0 : ProcedureReturn -1 : EndIf
  ProcedureReturn anvil_promptCpuPercent
EndProcedure

; Core 0's busy utilization in hundredths of a percent, sampled over the
; same completed one-second wall-clock window as AnvilCpuUsagePercent().
Procedure.i AnvilCpuUsageHundredths()
  If anvil_promptWindowReady = 0 Or anvil_promptCpuHundredths < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn anvil_promptCpuHundredths
EndProcedure

Procedure AnvilSchedulerAccount()
  Define now.i
  Define elapsed.i
  Define hz.i
  now = Ticks()
  If anvil_promptWindowReady = 0
    anvil_promptWindowStart = now
    anvil_promptIdleTicks = 0
    anvil_promptWindowReady = 1
    ProcedureReturn
  EndIf
  elapsed = now - anvil_promptWindowStart
  hz = TickHz()
  If hz > 0 And elapsed >= hz
    If anvil_promptIdleTicks > elapsed
      anvil_promptIdleTicks = elapsed
    EndIf
    anvil_promptCpuHundredths = 10000 - ((anvil_promptIdleTicks * 10000) / elapsed)
    If anvil_promptCpuHundredths < 0 : anvil_promptCpuHundredths = 0 : EndIf
    If anvil_promptCpuHundredths > 10000 : anvil_promptCpuHundredths = 10000 : EndIf
    ; Keep the original whole-percent getter semantics for existing callers.
    anvil_promptCpuPercent = 100 - ((anvil_promptIdleTicks * 100) / elapsed)
    If anvil_promptCpuPercent < 0 : anvil_promptCpuPercent = 0 : EndIf
    If anvil_promptCpuPercent > 100 : anvil_promptCpuPercent = 100 : EndIf
    anvil_promptWindowStart = now
    anvil_promptIdleTicks = 0
  EndIf
EndProcedure

Procedure AnvilPromptServiceOne()
  UartMessageBegin()
  Select anvil_promptServiceSlot
    Case 0
      MouseTick()
      TouchTick()
      CompilerIf #CAP_TOUCH = 1
        TouchKeyboardServiceTick()
      CompilerEndIf
    Case 1
      ScreenServiceTick()
    Case 2
      WifiLinkTick()
      NetDhcpTick()
      CompilerIf #CAP_NET = 1
        NtpServiceTick()
      CompilerEndIf
    Case 3
      CompilerIf #CAP_PWM = 1
        If HwPwmKind() <> #HW_PWM_KIND_SOFT
          FanTick()
        EndIf
      CompilerElse
        FanTick()
      CompilerEndIf
      HwTempSampleTick()
    Case 4
      NetConsoleRearm()
      NetConsolePump()
      NetConsoleLlTick()
      CompilerIf #CAP_NET = 1
        HttpServerPoll()
      CompilerElse
        TcpTick()
      CompilerEndIf
  EndSelect
  UartMessageEnd()
  anvil_promptServiceSlot = anvil_promptServiceSlot + 1
  If anvil_promptServiceSlot > 4
    anvil_promptServiceSlot = 0
  EndIf
  AnvilSchedulerAccount()
EndProcedure

Procedure AnvilSchedulerIdleIfSafe()
  Define t0.i
  Define dt.i
  AnvilSchedulerAccount()
  If anvil_promptWfeEnabled = 0 Or anvil_promptWfeReady = 0
    ProcedureReturn
  EndIf
  If MmuEl() <> 3 Or UartReadReady() <> 0 Or InputEventsQueued() <> 0
    ProcedureReturn
  EndIf
  CompilerIf #CAP_PWM = 1
    If HwPwmKind() = #HW_PWM_KIND_SOFT
      ProcedureReturn
    EndIf
  CompilerEndIf
  t0 = Ticks()
  Asm
    wfe
  EndAsm
  dt = Ticks() - t0
  If dt > 0
    anvil_promptIdleTicks = anvil_promptIdleTicks + dt
  EndIf
  AnvilSchedulerAccount()
EndProcedure

; Admit one PL011 byte before the editor drains its shared software queue.
; The byte is appended at the tail, so events already accepted keep their
; order. A full queue is left untouched: InputEventsPush() deliberately
; cancels the whole queue on overflow, so never consume a UART byte unless
; there is room for the event it may produce.
Procedure.i AnvilPromptAdmitUart()
  Define c.i
  If UartReadReady() = 0
    ProcedureReturn 0
  EndIf
  If InputEventsQueued() >= #AIE_QMAX
    ProcedureReturn 0
  EndIf
  c = UartRead()
  NetConsoleClaimLocal()
  InputFeedByte(#AIS_PHYSICAL, c)
  ProcedureReturn 1
EndProcedure

Procedure.i HexVal(c.i)
  If c >= 48 And c <= 57
    ProcedureReturn c - 48
  EndIf
  If c >= 65 And c <= 70
    ProcedureReturn c - 55
  EndIf
  If c >= 97 And c <= 102
    ProcedureReturn c - 87
  EndIf
  ProcedureReturn -1
EndProcedure

; ----------------------------------------------------------------------
;  ReadLine - one command line, from whichever source produced it.
;
;  ====================================================================
;   IT NO LONGER EDITS, AND IT NO LONGER DECIDES WHAT A BYTE MEANS
;  ====================================================================
;  This procedure used to be three things at once: a service loop, a
;  byte-to-meaning table, and an append-only line editor. The soft
;  keyboard needs the second and third of those to be reachable from
;  something that is not a byte source at all, so they moved to the
;  layers that own them:
;
;    Anvil/Core/input_events.pbi   what a byte means, and the one queue
;                                  every producer pushes into
;    Anvil/Core/text_edit.pbi      the buffer, the caret and the echo
;
;  What is left here is the part that was always ReadLine's: spinning
;  the monitor's services while nobody is typing, and turning a finished
;  line over to the parser.
;
;  UART RX ADMISSION RUNS BEFORE QUEUE DELIVERY on every prompt turn, but
;  the byte is appended at the tail so already-accepted events keep their
;  order. After that the editor delivers queued events, USB keyboard, then
;  an already-buffered network byte. Background work uses the cooperative
;  five-slot scheduler above; one slot runs on an idle turn and after
;  eight accepted input events, so sustained typing cannot starve screen
;  or maintenance service. Touch read and keyboard dispatch stay paired.
;
;  THE QUEUE IS DRAINED BEFORE A NEW BYTE IS READ. A soft keypress and a
;  serial byte arriving in the same spin must be applied in the order
;  they were produced, and the queue is what remembers that order.
;
;  LOCAL OWNERSHIP OF THE NETWORK CONSOLE IS CLAIMED WHERE IT ALWAYS
;  WAS - at the UART read and at the USB keyboard read - plus one new
;  place: an accepted soft keystroke. The design is explicit that
;  "Accepted soft keystrokes are local input, like physical keys", and
;  equally explicit that merely opening or drawing the keyboard "must
;  not steal the remote console's endpoint", so the claim is made when
;  an event is APPLIED and never when one is produced or drawn.
; ----------------------------------------------------------------------
Procedure ReadLine()
  Define c.i
  Define rc.i
  Define kind.i
  Define src.i
  Define inputBurst.i
  Dim ev.a[#AIE_EVSZ]

  TextEditBegin()
  AnvilSchedulerAccount()
  ; Point typed input at the command line. This is idempotent: on every
  ; line after the first it is a compare and a return, so pressing Enter
  ; cannot cancel a held modifier or an in-flight contact.
  InputFocusSet(#AIF_COMMAND_LINE)
  ; Everything the last command printed, plus the prompt, goes to the
  ; screen here, outside the producer callback. The nonblocking prompt
  ; spin below continues servicing display updates while input is idle.
  ; The prompt is already written, so the one thing the screen service can
  ; say - that screen memory is quarantined - is a message here.
  UartMessageBegin()
  ScreenServiceTick()
  UartMessageEnd()
  ; ATTACH HERE, NOT DEEPER IN. The first version did it inside
  ; MouseTick(), which meant the "looking for a mouse" lines landed
  ; after the prompt had already been drawn and cut it in half. This is
  ; before the wait, runs once, and MouseTryAttach() guards itself.
  ;
  ; AND WHAT IT PRINTS IS A MESSAGE. The prompt is already out, so anything
  ; the search says would land after it; see THE MESSAGE CONTEXT below.
  If gMouseTried = 0 And gScreen <> 0
    UartMessageBegin()
    MouseTryAttach()
    UartMessageEnd()
  EndIf
  Repeat
    CompilerIf #CAP_PWM = 1
      If HwPwmKind() = #HW_PWM_KIND_SOFT
        UartMessageBegin()
        FanTick()
        UartMessageEnd()
      EndIf
    CompilerEndIf
    AnvilPromptAdmitUart()
    ; THE QUEUE FIRST. Anything a previous spin produced - a soft
    ; keypress routed through the dispatcher, or the byte this spin's
    ; predecessor read - is applied before another byte is taken in, so
    ; two producers in one spin keep the order they arrived in.
    If InputEventsPop(@ev[0]) = 1
      kind = PeekL(@ev[0] + #AIE_EV_KIND)
      src = PeekL(@ev[0] + #AIE_EV_SRC)
      ; AN ACCEPTED SOFT KEYSTROKE IS LOCAL INPUT. Here and not at the
      ; producer: drawing or opening a keyboard claims nothing, and a
      ; remote session is only displaced when somebody actually types.
      If src = #AIS_TOUCH_KEYBOARD
        If kind = #AIE_TEXT Or kind = #AIE_KEY_DOWN
          NetConsoleClaimLocal()
        EndIf
      EndIf
      Select kind
        Case #AIE_TEXT
          TextEditInsert(PeekL(@ev[0] + #AIE_EV_CODE))
        Case #AIE_KEY_DOWN
          rc = TextEditKey(PeekL(@ev[0] + #AIE_EV_CODE))
          If rc <> #AIE_OK
            ; A KEY THE EDITOR CANNOT HONOUR SAYS SO, IN A SENTENCE,
            ; WITH ITS CODE. Today that is Tab and nothing else: this
            ; monitor has no completion and will not invent one. It is a
            ; MESSAGE, not command output: no command has run, and the
            ; half-typed line must stay exactly as it is on every console.
            UartMessageBegin()
            UartWriteStr(InputErrText(rc))
            PrintNl()
            UartMessageEnd()
          EndIf
        Case #AIE_KEY_UP
          ; The editor has no held state, but the release is DELIVERED
          ; and counted rather than dropped on the floor - see
          ; TextEditKeyRelease.
          TextEditKeyRelease(PeekL(@ev[0] + #AIE_EV_CODE))
        Case #AIE_CANCEL
          ; Contacts and modifiers were released underneath us. The
          ; half-typed line is KEPT.
          TextEditCancelNotice(PeekL(@ev[0] + #AIE_EV_CODE))
        Default
          ; InputEventsPush range-checks every kind, so arriving here
          ; means the queue produced something Push cannot have
          ; accepted. Say so rather than editing on a guess - as a
          ; message, for the same reason as the refused key above.
          UartMessageBegin()
          UartWriteStr(InputErrText(#AIE_ERR_KIND))
          PrintNl()
          UartMessageEnd()
      EndSelect
      If TextEditDone() <> 0
        Break
      EndIf
      inputBurst = inputBurst + 1
      If inputBurst >= 8
        inputBurst = 0
        AnvilPromptServiceOne()
      EndIf
      Continue
    EndIf

    ; UartRead() is admitted nonblocking at the top of this turn, before
    ; queue delivery or any screen/network service. No renderer waits in
    ; this path; the board screen hook only enqueues producer bytes.
    If gKbdH <> 0
      c = KeyboardChar()
      If c > 0
        NetConsoleClaimLocal()
        InputFeedByte(#AIS_PHYSICAL, c)
        inputBurst = inputBurst + 1
        If inputBurst >= 8
          inputBurst = 0
          AnvilPromptServiceOne()
        EndIf
        Continue
      EndIf
    EndIf
    ; THE NETWORK CONSOLE IS A THIRD SOURCE OF CHARACTERS. Pump sends
    ; whatever was printed to the peer and takes in datagrams; a byte
    ; the peer sent reads exactly like a keystroke.
    ; KEEP THE CONSOLE'S ENDPOINT MATCHING THE BOARD'S ADDRESS. This
    ; one call does two things, and the prompt is the right place for
    ; both because it is where the monitor spends nearly all its time.
    ;
    ; ALREADY LISTENING: put the bound port back. ping, dns and dhcp
    ; each call NetUdpBind with a port of their own so that only their
    ; reply is delivered, and none of them puts it back - so without
    ; this the network console went permanently deaf after the first
    ; `ping`. One place instead of a dozen command exits.
    ;
    ; NOT LISTENING YET: arm it, if the board has an address at all,
    ; ON WHICHEVER INTERFACE HOLDS IT. Arming used to be latched by whichever
    ; path completed DHCP, which covers only the paths somebody
    ; thought of - and a board that got its address by one of the
    ; others (the portable dhcp command, net ip, the settings-driven
    ; configuration) sat there answering ping with nothing listening
    ; until a human typed a join at the serial console. Measured on
    ; the bench 2026-09-06 with no serial cable attached, which is an
    ; unreachable board on a network it has joined. It is re-derived
    ; here instead, every spin, so no path can be forgotten.
    ;
    ; ==================================================================
    ;  THE MESSAGE CONTEXT. EVERY SERVICE BELOW RUNS INSIDE IT.  2026-09-16
    ; ==================================================================
    ;  Nobody at the keyboard asked for anything these services say. A
    ;  console arming on a new address, a lease, the radio rekeying or
    ;  coming back, a mouse being found: each used to print through the
    ;  ordinary console path, which put the sentence straight after
    ;  "pmf> " and into the middle of the line being typed - on the serial
    ;  line, the network console and the screen at once (forum 791).
    ;
    ;  A message for the user never reaches the command line. Inside the
    ;  bracket every byte goes to the message log instead of to any
    ;  console (RaspberryPi4/Lib/uart.pi4, Anvil/Core/messages.pbi); the
    ;  banner shows the newest and `messages` prints them. The bracket is
    ;  around the SERVICES, not around sentences, so a service added to
    ;  this loop later is covered without anyone remembering to.
    ;
    ;  The editor's echo is outside it by construction: the typed byte is
    ;  applied at the top of the loop, never in here.
    c = NetConsoleGetc()
    If c >= 0
      ; A BYTE FROM THE PEER DOES NOT CLAIM LOCAL OWNERSHIP, and that
      ; asymmetry with the two reads above is the whole point of
      ; tagging the source: it is the remote session's own byte.
      InputFeedByte(#AIS_NETWORK, c)
      inputBurst = inputBurst + 1
      If inputBurst >= 8
        inputBurst = 0
        AnvilPromptServiceOne()
      EndIf
      Continue
    EndIf
    AnvilPromptServiceOne()
    AnvilSchedulerIdleIfSafe()
  ForEver
  ; The three things the old inline editor did at the end of the line -
  ; terminate the buffer, publish its length, and end the echoed line -
  ; are now two: text_edit.pbi keeps gLine NUL terminated and gLineLen
  ; current on every edit, because a buffer whose length is only correct
  ; after the editor has finished is a buffer nothing may look at while
  ; somebody is typing. The newline is still ReadLine's.
  PrintNl()
  If gLineTrunc <> 0
    Print("!! that line was longer than ")
    PrintDec(#LINE_MAX)
    PrintN(" characters. The extra characters were")
    PrintN("   DROPPED as you typed rather than stored, so what runs is only the")
    PrintN("   line echoed above. Nothing has been done with it yet.")
  EndIf
EndProcedure

; ======================================================================
;  COMMAND WORDS
; ======================================================================
;  Anvil started with one-letter commands because it started as a thing
;  to type at a wedged board at two in the morning. That is a fine
;  reason for `g` and a poor reason for a monitor other people read the
;  transcripts of: `d 3` and `deadman 3` cost the same to type once you
;  know, and only one of them tells you what it did when you find it in
;  a log a week later.
;
;  So every command now has a WORD, and every old letter still works.
;  Nothing that ever worked stops working - the host tools speak `b`,
;  `g` and `p`, U-Boot's own `loads` and `go` land on the right
;  handlers, and a decade of muscle memory is not a bug to fix.
;
;  MATCHING IS ON THE WHOLE WORD, case-insensitively. Prefix matching
;  was considered and rejected: `s` would be ambiguous between screen
;  and srecord, and a monitor that guesses which destructive command was
;  meant is not a monitor anyone should trust.
; ----------------------------------------------------------------------
Global gWordAt.i               ; where the command word starts in gLine
Global gWordLen.i              ; and how long it is

; 1 if the command word is exactly *name, ignoring case.
Procedure.i WordIs(*name)
  Define i.i
  Define a.i
  Define b.i
  i = 0
  Repeat
    b = PeekA(*name + i) & $FF
    If b = 0
      Break
    EndIf
    If i >= gWordLen
      ProcedureReturn 0
    EndIf
    a = gLine[gWordAt + i] & $FF
    ; Fold both sides rather than the input only, so a mixed-case name
    ; in the table below cannot quietly never match.
    If a >= 65 And a <= 90
      a = a + 32
    EndIf
    If b >= 65 And b <= 90
      b = b + 32
    EndIf
    If a <> b
      ProcedureReturn 0
    EndIf
    i = i + 1
  ForEver
  ; The name ran out; the word must have run out at the same point, or
  ; "screen" would match "screenshot".
  If i <> gWordLen
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; 1 if the word is the single letter c, upper or lower case. Callers
; pass the ASCII code - this language has no character literals - and
; the letter itself is in the comment beside each call.
Procedure.i LetterIs(c.i)
  Define a.i
  If gWordLen <> 1
    ProcedureReturn 0
  EndIf
  a = gLine[gWordAt] & $FF
  If a >= 65 And a <= 90
    a = a + 32
  EndIf
  ProcedureReturn Bool(a = c)
EndProcedure

Procedure SkipSpace()
  ; gLine is NUL terminated and NUL is not a space, so this cannot run
  ; off the end.
  While gLine[gPos] = 32 Or gLine[gPos] = 9
    gPos = gPos + 1
  Wend
EndProcedure

Procedure SkipWord()
  ; Step over the command word itself. This is what lets "loads" and
  ; "go 0x200000" - what ubsend.py types at U-Boot - land on l and g
  ; here without the host needing to know the difference.
  While gLine[gPos] <> 0 And gLine[gPos] <> 32
    gPos = gPos + 1
  Wend
EndProcedure

; ======================================================================
;  MEASURE A COMMAND - `measure <command line>`
; ======================================================================
;  THE WORD IS `measure` AND NOT `time`, AND THAT IS NOT A PREFERENCE.
;  `time` is already a shipped command - it is the wall clock, it sets
;  and shows the date, and it is in every board's chain. Taking that word
;  for a stopwatch would break the clock on every board at once, quietly,
;  for the sake of a nicer name. The word was asked for; the collision is
;  the reason it is not used, and this paragraph is here so the question
;  is not asked twice.
;
;  WHY IT EXISTS, and it is not convenience. Every speed this monitor has
;  ever been credited with was measured by a HOST waiting on the network
;  console, and that wait includes the console's own round trip - which
;  is not small and is not even constant between client programs. One
;  client on this bench measures a floor of about four hundred
;  milliseconds per command; another measures about one. The same
;  three-hundred-megabyte load therefore reads as 0.078 s or as 0.502 s
;  depending on which program held the stopwatch, and the second one
;  looks exactly like a six-fold regression that is not there.
;
;  So the board times itself. `measure` takes the rest of the line, runs it
;  exactly as if the word were not there, and prints what it cost from
;  the monitor's own tick source. The host clock becomes a sanity check
;  instead of the measurement.
;
;  IT IS A PREFIX, NOT A WRAPPER, AND THAT IS DELIBERATE. The command
;  chain is a chain of word comparisons inside each board's main loop;
;  a wrapper would have to re-enter that chain, which means either a
;  pointer back into it - a cycle the frame-safety check refuses, and
;  rightly - or restructuring every board's loop. A prefix costs two
;  calls at the top and bottom of the loop, and both of them are here in
;  the core rather than in any board.
;
;  THE TIMED COMMAND'S OUTPUT IS UNTOUCHED. The elapsed line is printed
;  after it, on its own line, so a transcript can be read and a script
;  that parses the command's own answer still finds it.
;
;  NESTING IS REFUSED rather than quietly flattened. `measure measure
;  version` is somebody expecting something, and what they would get is
;  one measurement of `version` - so it says so and runs nothing.
; ----------------------------------------------------------------------
Global gTimeArmed.i = 0
Global gTimeAt.i = 0

; Called with the command word already read into gWordAt/gWordLen.
;   0  the word was not `time` - nothing happened
;   1  the clock is running and the NEXT word is now the command word, so
;      the caller refreshes anything it derived from the old one
;   2  REFUSED, and the caller must run nothing at all. It is a separate
;      answer from 1 because "say why and then run the command anyway"
;      is the shape that makes a refusal decorative.
Procedure.i TimeArm()
  gTimeArmed = 0
  If WordIs("measure") = 0
    ProcedureReturn 0
  EndIf
  SkipSpace()
  If gLine[gPos] = 0
    PrintN("!! measure needs a command after it - measure <command line> - and")
    PrintN("   there was none, so nothing was run and nothing was timed.")
    ; The caller is told to run nothing. A bare `time` must not fall
    ; through to an unknown-command complaint as well, and it must
    ; certainly not run anything.
    ProcedureReturn 2
  EndIf
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("measure") <> 0
    PrintN("!! measure cannot measure itself - one measure to a line. Nothing")
    PrintN("   was run and nothing was timed.")
    ProcedureReturn 2
  EndIf
  ; THE STAMP IS TAKEN LAST, after the parsing this procedure does, so
  ; that what is measured is the command and not the reading of its name.
  gTimeAt = Ticks()
  gTimeArmed = 1
  ProcedureReturn 1
EndProcedure

; Called at the bottom of the command loop. Prints nothing unless a
; command was actually armed and run.
Procedure TimeReport()
  Define d.i
  Define hz.i
  Define us.i

  If gTimeArmed = 0
    ProcedureReturn
  EndIf
  gTimeArmed = 0
  d = Ticks() - gTimeAt
  hz = TickHz()
  If hz < 1000000 Or d < 0
    ; A tick source this cannot divide by is reported as such. A zero
    ; would read as an instant command, which is the one wrong answer
    ; that looks like a good result.
    PrintN("measure: the board's tick source did not answer, so this command")
    PrintN("         was not timed. Nothing about the command itself went wrong.")
    ProcedureReturn
  EndIf
  us = d / (hz / 1000000)
  Print("measure: ")
  PrintDec(us / 1000)
  Print(".")
  ; Three decimals, zeros kept - 1.007 ms must not print as 1.7.
  If (us % 1000) < 100
    Print("0")
  EndIf
  If (us % 1000) < 10
    Print("0")
  EndIf
  PrintDec(us % 1000)
  Print(" ms (")
  PrintDec(us)
  PrintN(" us on this board's own counter)")
EndProcedure

Procedure.i ParseHex()
  ; UP TO SIXTEEN DIGITS - a whole 64-bit address. Seventeen is refused
  ; (gParseOver), not truncated and not wrapped.
  Define v.i
  Define d.i
  Define n.i
  v = 0
  n = 0
  gParseOver = 0
  SkipSpace()
  If gLine[gPos] = 36                              ; a leading $
    gPos = gPos + 1
  ElseIf gLine[gPos] = 48 And (gLine[gPos + 1] = 120 Or gLine[gPos + 1] = 88)
    gPos = gPos + 2                                ; a leading 0x / 0X
  EndIf
  Repeat
    d = HexVal(gLine[gPos] & $FF)
    If d < 0
      Break
    EndIf
    ; (v << 4) - the parentheses are load bearing. & | ! bind TIGHTER
    ; than << here, so "v << 4 | d" would mean "v << (4 | d)".
    If n < #HEX_MAX
      v = (v << 4) | d
    Else
      gParseOver = 1
    EndIf
    n = n + 1
    gPos = gPos + 1
  ForEver
  gParseOk = 0
  If n > 0 And gParseOver = 0
    gParseOk = 1
  EndIf
  ProcedureReturn v
EndProcedure

Procedure.i ParseDec()
  ; THE ONLY DECIMAL ARGUMENT IN THIS MONITOR, and it exists for exactly
  ; one caller: `c 1500000000`. A clock rate is a decimal quantity
  ; everywhere it is ever written down and $59682F00 is not something
  ; anyone types on purpose. A leading $ or 0x still means hex, so the
  ; two spellings cannot be ambiguous and nobody has to remember which
  ; command is which if they always write the prefix.
  Define v.i
  Define d.i
  Define n.i
  gParseOver = 0
  SkipSpace()
  If gLine[gPos] = 36
    ProcedureReturn ParseHex()
  EndIf
  If gLine[gPos] = 48 And (gLine[gPos + 1] = 120 Or gLine[gPos + 1] = 88)
    ProcedureReturn ParseHex()
  EndIf
  v = 0
  n = 0
  Repeat
    d = gLine[gPos] & $FF
    If d < 48 Or d > 57
      Break
    EndIf
    If n < #DEC_MAX
      v = v * 10 + (d - 48)
    Else
      gParseOver = 1
    EndIf
    n = n + 1
    gPos = gPos + 1
  ForEver
  gParseOk = 0
  If n > 0 And gParseOver = 0
    gParseOk = 1
  EndIf
  ProcedureReturn v
EndProcedure
