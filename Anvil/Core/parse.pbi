
; ======================================================================
;  Line editing and parsing
; ======================================================================

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
;  THE SERVICE ORDER AND THE SOURCE ORDER ARE UNCHANGED, deliberately
;  and to the call. UART first, then the USB keyboard, then the network
;  console after its rearm/pump/link-local/TCP block, then the pointer,
;  screen, radio, DHCP, NTP and fan work - and, exactly as before, a
;  spin that produced a character skips the service block entirely and
;  goes straight back round. Every one of those calls has a paragraph
;  below saying why it is where it is; none of that reasoning changed,
;  so none of those comments did either.
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
  Dim ev.a[#AIE_EVSZ]

  TextEditBegin()
  ; Point typed input at the command line. This is idempotent: on every
  ; line after the first it is a compare and a return, so pressing Enter
  ; cannot cancel a held modifier or an in-flight contact.
  InputFocusSet(#AIF_COMMAND_LINE)
  ; Everything the last command printed, plus the prompt, goes to the
  ; screen here, outside the producer callback. The nonblocking prompt
  ; spin below continues servicing display updates while input is idle.
  ScreenServiceTick()
  ; ATTACH HERE, NOT DEEPER IN. The first version did it inside
  ; MouseTick(), which meant the "looking for a mouse" lines landed
  ; after the prompt had already been drawn and cut it in half. This is
  ; before the wait, runs once, and MouseTryAttach() guards itself.
  If gMouseTried = 0 And gScreen <> 0
    MouseTryAttach()
  EndIf
  Repeat
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
            ; monitor has no completion and will not invent one. Printed
            ; on its own line so a half-typed command is not cut in two.
            PrintNl()
            UartWriteStr(InputErrText(rc))
            PrintNl()
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
          ; accepted. Say so rather than editing on a guess.
          PrintNl()
          UartWriteStr(InputErrText(#AIE_ERR_KIND))
          PrintNl()
      EndSelect
      If TextEditDone() <> 0
        Break
      EndIf
      Continue
    EndIf

    ; UartRead() BLOCKED HERE, and that is why the first build showed
    ; nothing: RxByte() is used by the payload paths, but the prompt
    ; reads through this loop, and a blocked read gives the cursor no
    ; time at all. Spin instead, and hand each turn to the keyboard and
    ; then the mouse.
    If UartReadReady() <> 0
      c = UartRead()
      NetConsoleClaimLocal()
      InputFeedByte(#AIS_PHYSICAL, c)
      Continue
    EndIf
    If gKbdH <> 0
      c = KeyboardChar()
      If c > 0
        NetConsoleClaimLocal()
        InputFeedByte(#AIS_PHYSICAL, c)
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
    NetConsoleRearm()
    NetConsolePump()
    ; AND IF THIS BOARD GAVE ITSELF ITS ADDRESS, KEEP IT. A link-local
    ; address is held only for as long as nobody else claims it, and
    ; RFC 3927 section 2.5 says a SECOND conflict inside ten seconds
    ; must end in the address being surrendered rather than defended a
    ; second time. The defence itself goes out from the pump above
    ; without anything here knowing it happened - it is a staged frame
    ; like an ARP reply. This is the other half: the moment the address
    ; has to be given up and another taken, which is a monitor act (the
    ; console, the board's record of the address, the sentence `net`
    ; prints) and not a library one. One load and a compare unless it
    ; has actually happened. See Anvil/Core/netll.pbi.
    NetConsoleLlTick()
    ; AND SO IS TCP. A connection opened by `tcp connect` finishes its
    ; handshake here, its retransmission timer runs here, and a
    ; keepalive goes out from here - because the prompt is where this
    ; monitor spends nearly all of its time and a protocol that only
    ; advances while a command is running is a protocol that stalls the
    ; moment somebody stops typing. TcpTick takes a zero slice, so with
    ; nothing waiting it is a table walk and a return.
    TcpTick()
    c = NetConsoleGetc()
    If c >= 0
      ; A BYTE FROM THE PEER DOES NOT CLAIM LOCAL OWNERSHIP, and that
      ; asymmetry with the two reads above is the whole point of
      ; tagging the source: it is the remote session's own byte.
      InputFeedByte(#AIS_NETWORK, c)
      Continue
    EndIf
    MouseTick()
    TouchTick()
    CompilerIf #CAP_TOUCH = 1
    ; THE SOFT KEYBOARD'S SERVICE, IMMEDIATELY AFTER THE ONE DRAIN AND
    ; NOWHERE ELSE.
    ;
    ; TouchTick above is the single drain of the hardware touch ring; it
    ; hands every record to the dispatcher, which decides - once, at the
    ; DOWN - whose contact it is. This is the keyboard emptying ITS OWN
    ; lane in the same pass, which is why there is no second poll of the
    ; controller anywhere in this monitor.
    ;
    ; IT IS IN THIS LOOP AND NOT IN ScreenServiceTick, although that is
    ; called from more places and would look tidier. This loop is the
    ; prompt: it is the only moment at which a keystroke has an editor to
    ; go to. Servicing the keyboard from the screen tick would queue
    ; keystrokes taken during a boot step, a long transfer or a payload
    ; and apply them to whatever line was typed next - which is the
    ; design's "queued touches cannot execute a command after upload",
    ; and the way to honour it is not to take them at all.
    ;
    ; ON A BOARD WITH NO TOUCH SURFACE THIS IS NOT COMPILED. #CAP_TOUCH
    ; is 0 there and the layer, the model's board adapter and the panel
    ; it draws on do not exist - the same shape as the NtpServiceTick
    ; call below, for the same reason.
    TouchKeyboardServiceTick()
    CompilerEndIf
    ; A restrained glint on the anvil is also a service-progress indicator:
    ; it advances only from this core spin, stops if the monitor stalls, and
    ; is internally rate-limited/damage-bounded. It is not driven by network
    ; traffic and it never delays this loop.
    ScreenServiceTick()
    ; KEEP THE RADIO ASSOCIATED. Self-rate-limited to a 20 s cadence, so
    ; this is a millis() read and two compares on all but one spin in
    ; millions - but when the access point idles the board out (~2 h with
    ; no traffic), or drops it for any other reason, this is what notices
    ; and re-associates + re-leases + brings the wireless console back,
    ; instead of the board sitting there believing it is still reachable.
    WifiLinkTick()
    ; DHCP leases are per-interface protocol state. Renew, rebind,
    ; expiry and INIT-REBOOT advance here even while no network command
    ; is active, without blocking the prompt or the other interface.
    NetDhcpTick()
    CompilerIf #CAP_NET = 1
    NtpServiceTick()
    CompilerEndIf
    ; AND KEEP THE FAN TURNING. Two rate classes in one call, and both
    ; of them have to be here rather than anywhere else.
    ;
    ; A SOFTWARE-MODULATED FAN IS THIS LOOP. Its waveform is the pin
    ; being toggled by FanTick, so the shortest period it can honour is
    ; a few times the interval between two spins of this Repeat - which
    ; is why FanTick's service half is NOT rate limited, and why a board
    ; driving a real modulator instead pays one compare here.
    ;
    ; The POLICY half self-limits to twice a second, so on all but one
    ; spin in thousands this whole call is a millis() read and a
    ; compare - the same shape as the keepalive above it.
    ;
    ; IT PRINTS NOTHING, EVER. It runs while a line is half typed.
    FanTick()
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
