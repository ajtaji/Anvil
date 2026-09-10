
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

Procedure ReadLine()
  Define c.i
  Define n.i
  n = 0
  gLineTrunc = 0
  gLineCtrlC = 0
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
    ; UartRead() BLOCKED HERE, and that is why the first build showed
    ; nothing: RxByte() is used by the payload paths, but the prompt
    ; reads through this loop, and a blocked read gives the cursor no
    ; time at all. Spin instead, and hand each turn to the keyboard and
    ; then the mouse.
    Repeat
      If UartReadReady() <> 0
        c = UartRead()
        NetConsoleClaimLocal()
        Break
      EndIf
      If gKbdH <> 0
        c = KeyboardChar()
        If c > 0
          NetConsoleClaimLocal()
          Break
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
        Break
      EndIf
      MouseTick()
      TouchTick()
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
    ; Swallow the LF of a CRLF pair. Terminals disagree about line
    ; endings and without this a CRLF terminal draws two prompts for
    ; every Enter, which looks like a fault and is not one.
    If c = 10 And gLastCR <> 0
      gLastCR = 0
      Continue
    EndIf
    gLastCR = 0
    If c = 13 Or c = 10
      If c = 13
        gLastCR = 1
      EndIf
      Break
    ElseIf c = 8 Or c = 127
      If n > 0
        n = n - 1
        UartWrite(8) : UartWrite(32) : UartWrite(8)
      EndIf
    ElseIf c = 3
      ; Ctrl-C discards the line. An EMPTY line does nothing at all -
      ; it does NOT repeat the last command. U-Boot does repeat, and
      ; holding Enter to catch its boot countdown once queued hundreds
      ; of repeats of a "help" and produced 4.6 MB of text.
      ;
      ; The truncation flag is cleared with the line. Complaining that a
      ; line was too long, about a line that has just been thrown away,
      ; would be a warning about nothing.
      ;
      ; gLineCtrlC IS SET so a caller that reads one line at a time - the
      ; mm/nm sub-prompt in memcmd.pi4 - can tell this deliberate abort
      ; apart from a blank Enter. The main loop never reads it: an empty
      ; line does nothing there either way. See gLineCtrlC in state.pi4.
      n = 0
      gLineTrunc = 0
      gLineCtrlC = 1
      Break
    ElseIf c >= 32 And c < 127
      If n < #LINE_MAX
        gLine[n] = c
        n = n + 1
        UartWrite(c)
      Else
        ; DROPPED, AND REMEMBERED. This used to be an empty Else: the
        ; character was silently thrown away and not echoed, so the only
        ; sign of it was a key that produced nothing. That is survivable
        ; for a mistyped address and it is NOT survivable for
        ; "wifi password <63 characters>", where the visible result is a
        ; passphrase that is quietly the wrong length and a radio that
        ; will not join for no stated reason. #LINE_MAX grew to 96 on
        ; 2026-08-26 so the longest legal passphrase fits, and to 144
        ; when the numbered Wi-Fi slots made `settings set
        ; wifi.4.password.plaintext <63 characters>` a 102-character
        ; line - see the arithmetic above #LINE_MAX. This flag is
        ; the belt to that pair of braces, and it covers every command
        ; rather than only the two that made it matter.
        gLineTrunc = 1
      EndIf
    EndIf
  ForEver
  gLine[n] = 0
  gLineLen = n
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
