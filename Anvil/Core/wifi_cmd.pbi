
; ======================================================================
;  wifi - FOUR NUMBERED NETWORKS AND THE OLD SINGLE PAIR BEHIND THEM
; ======================================================================
;  These commands store credentials and NOTHING READS THEM YET. There is
;  no radio driver in this monitor. That is said in the output rather
;  than left to be discovered, because "wifi network Workshop" followed
;  by silence and no network is exactly the shape of the defect that
;  cost a day here on 2026-08-26.
;
;  THE SLOT NUMBER IS THE PREFERENCE ORDER. Slot 1 is tried first. That
;  is settings.pi4's rule (see WI-FI, MORE THAN ONE NETWORK in its
;  header) and this end must keep saying it, because an ordering that
;  only exists in a library comment is not one the operator can act on.
;  Every place a slot number is printed here, it is printed as a
;  position in a list and not as a label.
;
;  THE OLD SPELLINGS STILL WORK. `wifi network <name>` and
;  `wifi password <phrase>` write the flat keys "wifi.network" and
;  "wifi.password.plaintext" exactly as they always did, and those are
;  read LAST - after slot four - so a stick written by an older build
;  keeps working and nobody's saved passphrase disappears on upgrade.
;  They are shown at the bottom of `wifi`, labelled "old", where their
;  place in the order can be read off the screen.
;
;  WHY THE SLOTTED PASSPHRASE IS A DIFFERENT WORD, `wifi phrase`
;  -------------------------------------------------------------
;  The obvious spelling was `wifi password <slot> <phrase>`, matching
;  `wifi ssid <slot> <name>`. IT WAS REJECTED, and this is the one
;  decision in this section worth reading twice.
;
;  `wifi password` takes THE WHOLE REST OF THE LINE as the passphrase,
;  because a passphrase may contain spaces. If that same word also took
;  an optional leading slot number, then `wifi password 3 hunter2` is
;  two different commands and nothing on the line says which:
;
;      set slot 3's passphrase to "hunter2"          or
;      set the old flat passphrase to "3 hunter2"
;
;  Whichever way the monitor guesses, the other one is stored silently
;  and wrongly - a passphrase two characters shorter than the operator
;  typed, a radio that will not join, and no diagnostic. That is the
;  precise failure this file raised #LINE_MAX for (see the note above
;  #LINE_MAX). A monitor that guesses which credential was meant is not
;  one anybody should trust, which is the same sentence the command-word
;  table gives for refusing to abbreviate `screenshot` to `s`.
;
;  So the slotted passphrase is its own word. `wifi phrase <slot>
;  <phrase>` cannot be confused with anything, `wifi password <phrase>`
;  keeps its exact old meaning, and neither has an ambiguous case.
;
;  AND THE BELT TO THAT PAIR OF BRACES: if the argument to the OLD
;  `wifi password` or `wifi network` begins with a bare number followed
;  by a blank, it is REFUSED rather than stored - see WifiLooksSlotted.
;  That is somebody reaching for the slotted form under the old word,
;  and storing what they typed would put a mangled credential in the
;  table without a word said. The refusal names both ways out. The cost
;  is that a passphrase that genuinely begins "3 " cannot be set by that
;  command; the refusal says so and names `settings set` as the way in.
; ======================================================================

; ----------------------------------------------------------------------
;  WifiSlotWord - a slot number typed as an argument, or -1 when the
;  word is not a plain decimal number at all.
;
;  IT IS DELIBERATELY NOT ParseDec. ParseDec reads a leading $ or 0x as
;  hex (anvil.pi4:1402-1416), which is exactly right for an address and
;  exactly wrong here - `wifi ssid 0x2 Whatever` would quietly mean slot
;  two. A slot number is a small decimal or it is a mistake. ParseDec
;  also works off gLine and gPos, and by the time a slot number is being
;  looked at ArgWord has already taken the word off the line.
;
;  THE RANGE IS THE CALLER'S BUSINESS. This hands back the number it
;  read, out of range included, so the caller can print it and say what
;  the range is. "There is no slot 7" is a better sentence than "that is
;  not a slot", and it can only be written if the 7 survives to here.
;
;  Two digits at most. Nothing in this store is a three-digit slot and
;  refusing the third digit means a mistyped line cannot arrive as a
;  plausible-looking number.
; ----------------------------------------------------------------------
Procedure.i WifiSlotWord(a.i)
  Define i.i
  Define c.i
  Define v.i
  Define n.i
  If a = 0
    ProcedureReturn -1
  EndIf
  v = 0
  n = 0
  i = 0
  Repeat
    c = PeekA(a + i)
    If c = 0
      Break
    EndIf
    If c < 48 Or c > 57            ; 48 = '0' and 57 = '9'
      ProcedureReturn -1
    EndIf
    If n >= 2
      ProcedureReturn -1
    EndIf
    v = (v * 10) + (c - 48)
    n = n + 1
    i = i + 1
  ForEver
  If n = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn v
EndProcedure

; ----------------------------------------------------------------------
;  WifiLooksSlotted - 1 if this value begins with a bare number, then a
;  blank, then something else.
;
;  It exists for ONE purpose: to catch somebody typing the slotted form
;  under the old unslotted word, where the value is the whole rest of
;  the line and the number would be stored as part of the credential.
;  See the essay above. It is a HEURISTIC and it is allowed to be,
;  because everything it does is REFUSE - it never chooses a meaning,
;  it only declines to guess between two, and the sentence it triggers
;  names both ways forward.
; ----------------------------------------------------------------------
Procedure.i WifiLooksSlotted(a.i)
  Define i.i
  Define c.i
  Define d.i
  If a = 0
    ProcedureReturn 0
  EndIf
  i = 0
  d = 0
  While d < 2
    c = PeekA(a + i)
    If c < 48 Or c > 57            ; 48 = '0' and 57 = '9'
      Break
    EndIf
    d = d + 1
    i = i + 1
  Wend
  If d = 0
    ProcedureReturn 0
  EndIf
  c = PeekA(a + i)
  If c <> 32 And c <> 9            ; 32 = a space and 9 = a tab
    ProcedureReturn 0
  EndIf
  ; There has to be something AFTER the blank. ArgRest has already
  ; trimmed the trailing ones, so this only fires on a real second word.
  While c = 32 Or c = 9
    i = i + 1
    c = PeekA(a + i)
  Wend
  If c = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  The sentence for a slot number that is not one. Written once, because
;  five commands can produce it and five slightly different spellings of
;  the same refusal is how a monitor stops sounding like one tool.
; ----------------------------------------------------------------------
Procedure WifiSayNoSuchSlot(n.i)
  Print("!! there is no Wi-Fi slot ")
  If n < 0
    Print("by that name")
  Else
    PrintDec(n)
  EndIf
  PrintN(", so nothing was changed.")
  Print("   The slots are numbered 1 to ")
  PrintDec(SettingsWifiSlots())
  PrintN(" and THE NUMBER IS THE ORDER THEY WOULD BE")
  PrintN("   TRIED IN - slot 1 first. Put the network you most want joined in")
  PrintN("   slot 1.")
  Print("   Slot ")
  PrintDec(SettingsWifiLegacySlot())
  PrintN(" is the older single-network pair. It is READ, after all the")
  PrintN("   others, so an existing stick keeps working - but it cannot be set")
  PrintN("   from here. Use wifi network and wifi password for that pair, or")
  PrintN("   better, copy it into a numbered slot and type wifi forget.")
EndProcedure

; ----------------------------------------------------------------------
;  One row of the list. The passphrase is MASKED and its true length is
;  printed beside it, which is the same bargain SettingsShowTable makes
;  and for the same reason: this output goes to the HDMI console and
;  into the next screenshot, but "did it take all sixty-three
;  characters" is a real question and it is the operator's own console.
; ----------------------------------------------------------------------
Procedure WifiShowSlot(s.i)
  Define ssid.i
  Define pw.i

  ssid = SettingsWifiSlotSsid(s)
  pw   = SettingsWifiSlotPassword(s)

  Print("  ")
  If s = SettingsWifiLegacySlot()
    ; The old pair is labelled with a word and not with its pseudo-slot
    ; number. Printing "5" here would invite somebody to type
    ; `wifi ssid 5 ...`, which is refused - and its position at the
    ; bottom of this list already says everything the number would.
    Print("old ")
  Else
    PrintDec(s)
    Print("   ")
  EndIf

  If ssid = 0
    PrintN("-")
    ProcedureReturn
  EndIf

  PutPadded(ssid, 34)              ; a POINTER, and PutPadded knows it
  If pw = 0
    PrintN("no passphrase - an open network, or half typed")
    ProcedureReturn
  EndIf
  UartWriteStr(SettingsMaskText()) ; a POINTER, so not Print
  Print("   (")
  PrintDec(StrLenZ(pw))
  PrintN(" characters, hidden)")
EndProcedure

; Print a duration counter without multiplying it (a long-running board can
; overflow ticks * 1000). Totals are milliseconds; maxima are microseconds.
Procedure wifi_BusTotal(label.i, ticks.i)
  Define perMs.i
  UartWriteStr(label)
  perMs = SdioTickHz() / 1000
  If perMs > 0
    PrintDec(ticks / perMs)
    PrintN(" ms")
  Else
    PrintDec(ticks)
    PrintN(" ticks (counter frequency unavailable)")
  EndIf
EndProcedure

Procedure wifi_BusMax(label.i, ticks.i)
  Define perUs.i
  UartWriteStr(label)
  perUs = SdioTickHz() / 1000000
  If perUs > 0
    PrintDec(ticks / perUs)
    PrintN(" us")
  Else
    PrintDec(ticks)
    PrintN(" ticks (counter frequency unavailable)")
  EndIf
EndProcedure

; Read-only radio transport evidence. Nothing here resets a counter or writes
; a register, so before/after readings can be compared around one transfer.
Procedure WifiBusStatus()
  PrintN("Wi-Fi SDIO transport counters since this radio was brought up:")
  Print("  bus ") : PrintDec(SdioClockKhz()) : Print(" kHz, ")
  PrintDec(SdioBusWidth()) : Print("-bit; F2 block ")
  PrintDec(Cyw43F2BlockSize()) : Print(" bytes, block mode ")
  If Cyw43BlockMode() <> 0 : PrintN("ON") : Else : PrintN("OFF") : EndIf

  Print("  CMD53 calls ") : PrintDec(SdioCmd53Calls())
  Print(" (read ") : PrintDec(SdioCmd53ReadCalls())
  Print(", write ") : PrintDec(SdioCmd53WriteCalls())
  Print("); bytes requested ") : PrintDec(SdioCmd53Bytes())
  Print("; failures ") : PrintDec(SdioCmd53Failures()) : PrintNl()
  Print("  CMD53 block mode ") : PrintDec(SdioCmd53BlockCalls())
  Print(", byte mode ") : PrintDec(SdioCmd53ByteCalls()) : PrintNl()
  wifi_BusTotal("  CMD53 total service ", SdioCmd53Ticks())
  wifi_BusMax("  slowest CMD53 ", SdioCmd53MaxTicks())
  wifi_BusTotal("  waiting for buffer ready ", SdioCmd53ReadyTicks())
  wifi_BusMax("  slowest buffer-ready wait ", SdioCmd53ReadyMaxTicks())
  wifi_BusTotal("  waiting for transfer complete ", SdioCmd53EndTicks())
  wifi_BusMax("  slowest transfer-complete wait ", SdioCmd53EndMaxTicks())

  Print("  F2 reads ") : PrintDec(Cyw43F2ReadCalls())
  Print(" / ") : PrintDec(Cyw43F2ReadBytes())
  Print(" bytes requested; writes ") : PrintDec(Cyw43F2WriteCalls())
  Print(" / ") : PrintDec(Cyw43F2WriteBytes())
  Print(" bytes requested; failures ") : PrintDec(Cyw43F2Failures()) : PrintNl()
  Print("  receive first reads ") : PrintDec(Cyw43RxFirstReads())
  Print(", rest reads ") : PrintDec(Cyw43RxRestReads())
  Print(", empty polls ") : PrintDec(Cyw43RxEmpty()) : PrintNl()
  Print("  SDPCM channels: data ") : PrintDec(Cyw43RxDataChannel())
  Print(", control ") : PrintDec(Cyw43RxControl())
  Print(", event ") : PrintDec(Cyw43RxEvent())
  Print(", glom ") : PrintDec(Cyw43RxGlom())
  Print(", unknown ") : PrintDec(Cyw43RxUnknownChannel()) : PrintNl()
  Print("  glom descriptors ") : PrintDec(Cyw43RxGlomDescriptors())
  Print(", superframes ") : PrintDec(Cyw43RxGlomSuperframes())
  Print(", packets ") : PrintDec(Cyw43RxGlomPackets())
  Print(", failures ") : PrintDec(Cyw43RxGlomFailures()) : PrintNl()
  Print("  data frames delivered ") : PrintDec(Cyw43RxDataFrames())
  Print(", retained in control waits ") : PrintDec(Cyw43RxDataQueuedInControlPoll())
  Print(", TX-credit waits ") : PrintDec(Cyw43RxDataQueuedInCreditPoll())
  Print(", event waits ") : PrintDec(Cyw43RxDataQueuedInEventPoll()) : PrintNl()
  Print("  retained queue now ") : PrintDec(Cyw43RxQueueDepth())
  Print(", high-water ") : PrintDec(Cyw43RxQueueHighWater())
  Print(", total entries ") : PrintDec(Cyw43RxQueueTotal())
  Print(", full/refused ") : PrintDec(Cyw43RxQueueFull()) : PrintNl()
  Print("  receive terminates started ") : PrintDec(Cyw43RxAbortStarted())
  Print(", completed ") : PrintDec(Cyw43RxAbortDone())
  Print(", failed ") : PrintDec(Cyw43RxAbortFailed())
  Print(", active ") : PrintDec(Cyw43RxAbortActive())
  Print(", unsafe latch ") : PrintDec(Cyw43RxAbortFault()) : PrintNl()
  Print("  TX-credit polls ") : PrintDec(Cyw43CreditPolls())
  Print(", still stalled after 5 ms ") : PrintDec(Cyw43Stalls()) : PrintNl()
  Print("  SDPCM sequence mismatches ") : PrintDec(Cyw43RxSeqMismatch())
  If Cyw43RxSeqMismatch() <> 0
    Print("; last expected ") : PrintDec(Cyw43RxSeqLastExpected())
    Print(", got ") : PrintDec(Cyw43RxSeqLastGot())
  EndIf
  PrintNl()
  Print("  NEXTLEN offered ") : PrintDec(Cyw43RxNextLenCount())
  Print(" times; largest ") : PrintDec(Cyw43RxNextLenMax() * 16) : PrintN(" bytes")
  Print("  malformed: bad header ") : PrintDec(Cyw43RxBadHdr())
  Print(", too large ") : PrintDec(Cyw43RxTooBig())
  Print(", short ") : PrintDec(Cyw43RxShort()) : PrintNl()
  If Cyw43RxBadHdr() <> 0
    Print("    last bad length $") : PutHexN(Cyw43RxBadLastSize(), 4)
    Print(", complement $") : PutHexN(Cyw43RxBadLastComplement(), 4) : PrintNl()
  EndIf
  If Cyw43RxTooBig() <> 0
    Print("    oversized glom ") : PrintDec(Cyw43RxTooBigGlom())
    Print("; last length ") : PrintDec(Cyw43RxTooBigLastSize())
    Print(", raw channel $") : PutHexN(Cyw43RxTooBigLastChannel(), 2) : PrintNl()
  EndIf
  Print("  last SDIO error ") : PrintDec(SdioLastError())
  Print(", interrupt $") : PutHexN(SdioLastIntr(), 8)
  Print(", status $") : PutHexN(SdioLastStatus(), 8) : PrintNl()
  PrintN("  These are observations, not a speed claim. After one transfer, compare")
  PrintN("  tcp status for each socket; net's preferred-route footer does not identify")
  PrintN("  this radio. Queue full, glom failure or terminate failure is a loss alarm.")
EndProcedure

Procedure CmdWifi()
  Define v.i
  Define net.i
  Define pw.i
  Define hadNet.i
  Define hadPw.i
  Define n.i
  Define s.i
  Define k.i

  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  If gWordLen = 0 Or WordIs("show") <> 0
    n = SettingsWifiSlotCount()
    Print("Wi-Fi networks stored: ")
    PrintDec(n)
    Print(" of ")
    PrintDec(SettingsWifiSlots())
    PrintN(" slots, plus the older single pair.")
    PrintN("THE NUMBER IS THE ORDER THEY WOULD BE TRIED IN - slot 1 first.")
    PrintN("  #   network name                      passphrase")

    ; EVERY SLOT IS PRINTED, INCLUDING THE EMPTY ONES. A list that
    ; showed only what is set would hide the shape of the thing: an
    ; operator cannot see that slot 1 is free, and so cannot see that
    ; the network they care about is being tried third. Four rows and a
    ; dash is cheap and the layout IS the explanation.
    s = 1
    While s <= SettingsWifiSlots()
      If OutBreak() <> 0
        ProcedureReturn
      EndIf
      WifiShowSlot(s)
      s = s + 1
    Wend

    ; And the old pair, LAST, which is where it sits in the order.
    net = SettingsWifiNetwork()
    pw = SettingsWifiPassword()
    If net <> 0 Or pw <> 0
      WifiShowSlot(SettingsWifiLegacySlot())
      PrintN("  The row marked old is the single network this monitor used to keep,")
      PrintN("  under wifi.network and wifi.password.plaintext. It is still read, and")
      PrintN("  it is read LAST - after every numbered slot - so a stick written by")
      PrintN("  an older build keeps working and no saved passphrase went missing.")
      PrintN("  To promote it, type it into a numbered slot and then wifi forget.")
    EndIf

    If n = 0
      PrintN("Nothing is stored. Type wifi ssid 1 <name> and wifi phrase 1 <phrase>.")
    EndIf
    If pw <> 0
      Print("  settings reveal ")
      UartWriteStr(SettingsWifiPasswordKey())   ; a POINTER, not Print
      PrintN("  prints the old one in full.")
    EndIf
    PrintN("Passphrases are hidden here because this output also goes to the HDMI")
    PrintN("console and into the next screenshot. settings reveal <name> prints")
    PrintN("one, and wifi keys lists the names to give it.")
    PrintN("Type wifi scan to bring the radio up and see which of these are on")
    PrintN("the air right now. Joining is the next piece; the scan is what proves")
    PrintN("the stored names against real access points.")
    If SettingsDirty() <> 0
      PrintN("There are changes here that are not in the file. Type settings save.")
    EndIf
    ProcedureReturn
  EndIf

  ; ------------------------------------------------------------------
  ;  wifi ssid <slot> <name> - the numbered network name.
  ;
  ;  The name is the WHOLE REST OF THE LINE after the slot number, so it
  ;  may contain spaces; plenty of them do. The slot is a separate word
  ;  before it and is therefore never ambiguous with the name, which is
  ;  the whole reason the passphrase needed a word of its own - see the
  ;  essay at the top of this section.
  ; ------------------------------------------------------------------
  ; scan - bring the radio up and report which stored networks are on
  ; the air. The bring-up reads 600 KB of firmware off the stick and
  ; runs once; a second scan reuses the radio already up.
  If WordIs("scan") <> 0
    ; A scan replaces the firmware's result table. It therefore owns the
    ; radio generation just as a manual join does; an automatic selector
    ; must not resume later against a different table.
    WifiRecoveryCancel()
    n = WifiScanMatch()
    ; Scan is a foreground owner and cancels any older automatic generation.
    ; Reconcile afterward: an already-keyed link is untouched, an unready
    ; radio gets radio initialization, and a ready/unkeyed radio resumes the
    ; association machine against the scan result it just produced.
    WifiRecoveryReconcile(1)
    ProcedureReturn
  EndIf

  ; join - associate and run the four-way handshake to a known network.
  ; Done at boot too; this is for re-trying it from the prompt.
  ;
  ; ALREADY JOINED IS SAID, NOT SWALLOWED. Every step below is a no-op
  ; when the state says up (WifiJoinKnown returns 1 keyed, WifiDhcp
  ; returns 1 leased, the console is already armed), so this used to
  ; print NOTHING - and on a board whose link had silently died with the
  ; state still claiming up (silicon, 2026-08-30), the one command a
  ; person reaches for first did nothing and said nothing. Say what the
  ; state is and name the command that forces a fresh association.
  If WordIs("join") <> 0 Or WordIs("connect") <> 0
    ; FIRST, ARM FROM WHATEVER STATE THE BOARD IS ALREADY IN. Typing
    ; `wifi join` on a board that is keyed and addressed used to be the
    ; only way an operator could get the network console listening, and
    ; it worked by accident - the join re-ran DHCP and the DHCP armed.
    ; Arming is now re-derived from the board's address (see
    ; NetConsoleRearm), so ask for it here, before the "nothing to do"
    ; answer below, and the command does what the person typing it meant
    ; even when the association itself really has nothing left to do.
    NetConsoleRearm()
    If gWifiKeyed <> 0 And gWifiHaveIp <> 0
      PrintN("Wi-Fi already believes it is joined and leased, so join has nothing")
      PrintN("to do. If the link is actually dead (the network console is deaf),")
      PrintN("type wifi rejoin - it forces a fresh association and a fresh lease.")
      PrintN("The health check also detects a silent link and reconnects on its")
      PrintN("own within about a minute.")
      ProcedureReturn
    EndIf
    ; A manual join owns the radio now. Cancel any automatic recovery
    ; generation before the synchronous compatibility path reads settings.
    WifiRecoveryCancel()
    If WifiJoinKnown() <> 0
      If WifiDhcp() <> 0
        NetConsoleRearm()
      EndIf
    Else
      WifiRecoveryInitialJoinFailed()
    EndIf
    ; AND AGAIN AFTER THE ATTEMPT, whatever it returned. DHCP may have
    ; bound the lease on a path of its own (the portable dhcp command
    ; runs over whichever link is up and does not know this file's
    ; flags), and a join that reports failure while the board is in fact
    ; addressed must still leave the console listening.
    NetConsoleRearm()
    ProcedureReturn
  EndIf

  ; ip / status - show this board's own MAC and address on the network.
  If WordIs("ip") <> 0 Or WordIs("status") <> 0 Or WordIs("addr") <> 0
    WifiPrintNet()
    ProcedureReturn
  EndIf

  If WordIs("bus") <> 0 Or WordIs("transport") <> 0
    WifiBusStatus()
    ProcedureReturn
  EndIf

  ; rejoin / reconnect - re-associate and re-lease now, without waiting for
  ; the health check to notice a drop. Useful after moving the board, or to
  ; prove the recovery path by hand.
  If WordIs("rejoin") <> 0 Or WordIs("reconnect") <> 0
    ; gWifiHealPend means a heal attempt already reset the keyed/leased
    ; gates and failed part-way - the board HAS connected this boot, so
    ; rejoin is exactly the right command and must not be refused.
    If gWifiKeyed = 0 And gWifiHaveIp = 0 And gWifiHealPend = 0
      PrintN("Wi-Fi has never connected this boot, so there is nothing to rejoin.")
      PrintN("Type wifi join to connect for the first time.")
      ProcedureReturn
    EndIf
    WifiRejoin(1)
    ProcedureReturn
  EndIf

  ; link - the state of the keepalive + auto-reconnect, and a switch for it.
  ; `wifi link off` stops the periodic keepalive/health check; `wifi link on`
  ; starts it again. `wifi drop` simulates an access-point deauth (a REAL
  ; disassociation) so the detector can be watched reconnecting on its own.
  If WordIs("link") <> 0 Or WordIs("health") <> 0
    ; The optional on/off word, matched case-insensitively (| $20 folds an
    ; ASCII letter to lower) and exactly (the trailing NUL, so "onward" is
    ; not "on"). ArgWord returns the raw typed word, NUL-terminated.
    k = ArgWord()
    If k <> 0
      If (PeekA(k) | $20) = 111 And (PeekA(k + 1) | $20) = 110 And PeekA(k + 2) = 0   ; "on"
        WifiLinkSet(1)
        PrintN("Wi-Fi keepalive and auto-reconnect are ON.")
        ProcedureReturn
      EndIf
      If (PeekA(k) | $20) = 111 And (PeekA(k + 1) | $20) = 102 And (PeekA(k + 2) | $20) = 102 And PeekA(k + 3) = 0   ; "off"
        WifiLinkSet(0)
        PrintN("Wi-Fi keepalive and auto-reconnect are OFF. The board will not")
        PrintN("re-associate by itself if the access point drops it.")
        ProcedureReturn
      EndIf
    EndIf
    Print("Wi-Fi keepalive and auto-reconnect: ")
    If WifiLinkActive() <> 0
      PrintN("ON.")
    Else
      PrintN("OFF.")
    EndIf
    Print("  A keepalive frame goes out every ")
    PrintDec(#WIFI_KA_MS / 1000)
    PrintN(" seconds so the access point does not")
    PrintN("  idle the board out, and on the same cadence the firmware is asked")
    PrintN("  whether it is still associated; two 'no' answers in a row trigger a")
    PrintN("  re-association and a fresh DHCP lease.")
    Print("  Re-associations since boot: ")
    PrintDec(WifiRejoinCount())
    PrintNl()
    PrintN("  wifi link off   stop it     wifi link on   start it")
    PrintN("  wifi drop       simulate an access-point drop and watch it recover")
    ProcedureReturn
  EndIf

  ; drop - the test hook. Really disassociate, then let the automatic
  ; health check detect it and reconnect. This proves the whole loop on
  ; silicon without waiting for a two-hour idle-out.
  If WordIs("drop") <> 0
    WifiLinkDrop()
    ProcedureReturn
  EndIf

  ; rekey [on|off] - service the access point's mid-session rekey (the
  ; TX-only-death CURE) or, off, log it without answering to reproduce the
  ; death. Bare word shows the state.
  If WordIs("rekey") <> 0
    k = ArgWord()
    If k <> 0
      If (PeekA(k) | $20) = 111 And (PeekA(k + 1) | $20) = 110 And PeekA(k + 2) = 0
        gWifiRekeyOn = 1
        PrintN("Wi-Fi: mid-session rekey servicing is ON (the cure). Group-key and")
        PrintN("PTK rekeys the access point starts are answered, so the link stays up.")
        ProcedureReturn
      EndIf
      If (PeekA(k) | $20) = 111 And (PeekA(k + 1) | $20) = 102 And (PeekA(k + 2) | $20) = 102 And PeekA(k + 3) = 0
        gWifiRekeyOn = 0
        PrintN("Wi-Fi: mid-session rekey servicing is OFF. A rekey will be logged")
        PrintN("but NOT answered - the link will go TX-only dead when one arrives.")
        ProcedureReturn
      EndIf
    EndIf
    Print("Wi-Fi: mid-session rekey servicing is ")
    If gWifiRekeyOn <> 0
      PrintN("ON (the cure).")
    Else
      PrintN("OFF (death will be reproduced).")
    EndIf
    ProcedureReturn
  EndIf

  ; heal [on|off] - the automatic re-association backstop. Off lets a
  ; death PERSIST for observation; manual wifi rejoin still works.
  If WordIs("heal") <> 0
    k = ArgWord()
    If k <> 0
      If (PeekA(k) | $20) = 111 And (PeekA(k + 1) | $20) = 110 And PeekA(k + 2) = 0
        WifiHealSet(1)
        PrintN("Wi-Fi: automatic re-association (the backstop) is ON.")
        ProcedureReturn
      EndIf
      If (PeekA(k) | $20) = 111 And (PeekA(k + 1) | $20) = 102 And (PeekA(k + 2) | $20) = 102 And PeekA(k + 3) = 0
        WifiHealSet(0)
        PrintN("Wi-Fi: automatic re-association is OFF. A dead link will be left")
        PrintN("dead so it can be observed; type wifi rejoin to recover by hand.")
        ProcedureReturn
      EndIf
    EndIf
    Print("Wi-Fi: automatic re-association (the backstop) is ")
    If gWifiHealOn <> 0
      PrintN("ON.")
    Else
      PrintN("OFF.")
    EndIf
    ProcedureReturn
  EndIf

  ; eapol - the mid-session rekey evidence. This is the panel that proves
  ; cure vs mitigation: a rekey arriving (frames seen), being answered
  ; (group/PTK serviced), and the re-association count STAYING 0.
  If WordIs("eapol") <> 0
    PrintN("Wi-Fi mid-session rekey (the TX-only-death root cause):")
    Print("  servicing (the cure)      ")
    If gWifiRekeyOn <> 0
      PrintN("ON")
    Else
      PrintN("OFF")
    EndIf
    Print("  auto-heal (the backstop)  ")
    If gWifiHealOn <> 0
      PrintN("ON")
    Else
      PrintN("OFF")
    EndIf
    Print("  EAPOL-Key frames seen     ")
    PrintDec(gWifiEapolSeen)
    PrintNl()
    Print("  group rekeys serviced     ")
    PrintDec(gWifiGrpKeyed)
    PrintNl()
    Print("  PTK rekeys serviced       ")
    PrintDec(gWifiPtkKeyed)
    PrintNl()
    Print("  rekeys not serviced       ")
    PrintDec(gWifiEapolErr)
    PrintNl()
    If gWifiEapolFailStage <> #WIFI_EAPOL_FAIL_NONE
      Print("  last failure              ")
      UartWriteStr(wifi_EapolFailureName(gWifiEapolFailStage))
      Print(" (stage ")
      PrintDec(gWifiEapolFailStage)
      Print(", rc ")
      PrintDec(gWifiEapolFailRc)
      PrintN(")")
    Else
      PrintN("  last failure              none")
    EndIf
    Print("  failure cleanup pending   ")
    If gWifiEapolRecover <> 0
      PrintN("YES")
    Else
      PrintN("no")
    EndIf
    Print("  re-associations (want 0)  ")
    PrintDec(WifiRejoinCount())
    PrintNl()
    If gWifiEapolLast <> 0
      Print("  last EAPOL key-info $")
      PutHexN(gWifiEapolInfo, 4)
      Print("  (")
      PrintDec((millis() - gWifiEapolLast) / 1000)
      PrintN(" s ago)")
    Else
      PrintN("  no EAPOL frame has arrived this session yet.")
    EndIf
    Print("  deauth/disassoc events    ")
    PrintDec(gWifiDeauths)
    PrintNl()
    If gWifiEvtType >= 0
      Print("  last radio event ")
      UartWriteStr(Cyw43EventName(gWifiEvtType))
      Print(" reason ")
      PrintDec(gWifiEvtReason)
      Print("  (")
      PrintDec((millis() - gWifiEvtLast) / 1000)
      PrintN(" s ago)")
    EndIf
    PrintN("  A rekey that arrives and is serviced with the count still 0 is the")
    PrintN("  cure; a death that only heals fast is the mitigation.")
    ProcedureReturn
  EndIf

  If WordIs("ssid") <> 0
    k = ArgWord()
    If k = 0
      PrintN("!! wifi ssid needs a slot number and a network name, and neither was")
      PrintN("   given, so nothing was changed.")
      Print("   wifi ssid <slot> <name>, where the slot is 1 to ")
      PrintDec(SettingsWifiSlots())
      PrintNl()
      PrintN("   THE SLOT NUMBER IS THE ORDER THEY WOULD BE TRIED IN - slot 1 first.")
      PrintN("   The name is the WHOLE REST OF THE LINE, so it may contain spaces.")
      ProcedureReturn
    EndIf
    s = WifiSlotWord(k)
    If s < 1 Or s > SettingsWifiSlots()
      WifiSayNoSuchSlot(s)
      ProcedureReturn
    EndIf
    v = ArgRest()
    If v = 0
      Print("!! wifi ssid ")
      PrintDec(s)
      PrintN(" needs the network name after the slot number, and none")
      PrintN("   was given, so nothing was changed and that slot is as it was.")
      Print("   wifi ssid ")
      PrintDec(s)
      PrintN(" <name>, where the name is the rest of the line.")
      PrintN("   One to thirty-two characters, and ordinary printable ones only: a")
      PrintN("   name with a byte above 126 in it cannot be stored by this monitor,")
      PrintN("   which is a real limitation and not a bug.")
      Print("   To empty the slot instead, type wifi forget ")
      PrintDec(s)
      PrintN(".")
      ProcedureReturn
    EndIf
    If SettingsSetWifiSlotSsid(s, v) = 0
      SettingsSayWhyNot()
      Print("   You typed ")
      PrintDec(StrLenZ(v))
      PrintN(" characters. Nothing was changed.")
      ProcedureReturn
    EndIf
    WifiConfigChanged()
    Print("Wi-Fi slot ")
    PrintDec(s)
    Print(" is now ")
    UartWriteStr(v)                ; a POINTER
    Print("   (")
    PrintDec(StrLenZ(v))
    PrintN(" characters)")
    Print("  stored under ")
    UartWriteStr(SettingsWifiSlotSsidKey(s))
    PrintNl()
    ; The order is restated at the moment it is being set, because this
    ; is when the operator is deciding it and it is the only thing about
    ; a slot number that is not obvious.
    If s > 1
      Print("  Slot ")
      PrintDec(s)
      Print(" is tried AFTER slot ")
      PrintDec(s - 1)
      PrintN(". Lower numbers are preferred.")
    Else
      PrintN("  Slot 1 is the first one that would be tried.")
    EndIf
    If SettingsWifiSlotPassword(s) = 0
      Print("  There is no passphrase in this slot yet. Type wifi phrase ")
      PrintDec(s)
      PrintN(" <phrase>,")
      PrintN("  unless it is an open network with no passphrase at all.")
    EndIf
    PrintN("  This is in memory only. Type settings save to write it to the medium.")
    ProcedureReturn
  EndIf

  ; ------------------------------------------------------------------
  ;  wifi phrase <slot> <passphrase> - the numbered passphrase.
  ;
  ;  A WORD OF ITS OWN AND NOT `wifi password <slot> <phrase>`. The full
  ;  argument is at the top of this section; the short version is that
  ;  `wifi password` already takes the whole rest of the line, so a
  ;  leading number there is ambiguous between a slot and the first two
  ;  characters of a credential, and a monitor that guesses which one
  ;  the operator meant will one day guess wrong and say nothing.
  ; ------------------------------------------------------------------
  If WordIs("phrase") <> 0
    k = ArgWord()
    If k = 0
      PrintN("!! wifi phrase needs a slot number and a passphrase, and neither was")
      PrintN("   given, so nothing was changed and nothing was stored.")
      Print("   wifi phrase <slot> <passphrase>, where the slot is 1 to ")
      PrintDec(SettingsWifiSlots())
      PrintNl()
      PrintN("   It is a separate word from wifi password on purpose: that command")
      PrintN("   takes the whole rest of the line, so a slot number in front of it")
      PrintN("   could not be told apart from the start of a passphrase.")
      ProcedureReturn
    EndIf
    s = WifiSlotWord(k)
    If s < 1 Or s > SettingsWifiSlots()
      WifiSayNoSuchSlot(s)
      ProcedureReturn
    EndIf
    v = ArgRest()
    If v = 0
      Print("!! wifi phrase ")
      PrintDec(s)
      PrintN(" needs the passphrase after the slot number, and none")
      PrintN("   was given, so nothing was changed and nothing was stored.")
      Print("   wifi phrase ")
      PrintDec(s)
      PrintN(" <passphrase>, the whole rest of the line, so it may")
      PrintN("   contain spaces. Eight to sixty-three characters - that is WPA2's")
      PrintN("   own range and the radio driver will refuse anything outside it.")
      PrintN("   It is stored in plain text.")
      ProcedureReturn
    EndIf
    n = StrLenZ(v)
    If SettingsSetWifiSlotPassword(s, v) = 0
      SettingsSayWhyNot()
      Print("   You typed ")
      PrintDec(n)
      PrintN(" characters. Nothing was changed and nothing was stored.")
      If n < 8
        PrintN("   Eight is WPA2's floor, not this monitor's - a shorter one could")
        PrintN("   not be used to join a network even if it were stored.")
      EndIf
      ProcedureReturn
    EndIf
    WifiConfigChanged()
    Print("The passphrase for Wi-Fi slot ")
    PrintDec(s)
    Print(" is set. It is ")
    PrintDec(n)
    PrintN(" characters long.")
    PrintN("  The length is printed so you can check the line editor took all of")
    PrintN("  what you typed. The passphrase itself is not echoed back here.")
    SettingsSayPlainText()
    Print("  It is stored under ")
    UartWriteStr(SettingsWifiSlotPasswordKey(s))
    PrintN(" - the warning is in")
    PrintN("  the key name on purpose, so it survives the file being copied or")
    PrintN("  pasted anywhere.")
    If SettingsWifiSlotSsid(s) = 0
      Print("  There is no network name in this slot yet, so nothing could use this")
      PrintNl()
      Print("  passphrase. Type wifi ssid ")
      PrintDec(s)
      PrintN(" <name>.")
    EndIf
    PrintN("  This is in memory only. Type settings save to write it to the medium.")
    ProcedureReturn
  EndIf

  ; ------------------------------------------------------------------
  ;  wifi find <name> - which slot holds this network name.
  ;
  ;  It exists because the comparison behind it is BYTE-EXACT and that
  ;  is a thing worth being able to check from a console. Two of the
  ;  networks this board sits among differ by one letter and one differs
  ;  from another only by a "2.4ghz" suffix; when a join fails, "does
  ;  this board have the profile I think it has, spelled exactly the way
  ;  I think it is" is the first question, and typing the name in is the
  ;  only way to answer it without reading the file on a PC.
  ;
  ;  IT DOES NOT CASE FOLD AND IT DOES NOT TRIM anything the line editor
  ;  did not already trim, because SettingsWifiFindSsid does neither.
  ;  A near miss reporting "not found" is the correct and useful answer.
  ; ------------------------------------------------------------------
  If WordIs("find") <> 0
    v = ArgRest()
    If v = 0
      PrintN("!! wifi find needs the network name to look for, and none was given.")
      PrintN("   wifi find <name>, where the name is the whole rest of the line.")
      PrintN("   It says which slot holds that name, if any. The comparison is")
      PrintN("   EXACT - upper and lower case are different, and a 2.4ghz suffix")
      PrintN("   makes a different network. Nothing was changed either way.")
      ProcedureReturn
    EndIf
    s = SettingsWifiFindSsid(v)
    If s = 0
      Print("No slot holds ")
      UartWriteStr(v)              ; a POINTER
      PrintN(".")
      PrintN("  The comparison is byte for byte: upper and lower case are different")
      PrintN("  networks, a trailing 2.4ghz is part of the name, and a name that is")
      PrintN("  one letter out does not match. Type wifi to see what is stored.")
      ProcedureReturn
    EndIf
    If s = SettingsWifiLegacySlot()
      Print("The older single pair holds ")
      UartWriteStr(v)
      PrintN(".")
      PrintN("  That is the LAST thing that would be tried, after every numbered")
      PrintN("  slot. To prefer it, type it into a numbered slot.")
    Else
      Print("Wi-Fi slot ")
      PrintDec(s)
      Print(" holds ")
      UartWriteStr(v)
      PrintN(".")
      Print("  That is position ")
      PrintDec(s)
      PrintN(" in the order they would be tried, counting from 1.")
    EndIf
    If SettingsWifiSlotPassword(s) = 0
      PrintN("  There is no passphrase against it.")
    EndIf
    ProcedureReturn
  EndIf

  ; ------------------------------------------------------------------
  ;  wifi keys - the exact key names, for `settings reveal` and for
  ;  anybody editing SETTINGS.TXT on a PC.
  ;
  ;  The names are BUILT AT RUN TIME by settings.pi4, so printing them
  ;  from the library rather than typing them here means the two can
  ;  never disagree - which is the same argument that keeps the length
  ;  limits in the library.
  ; ------------------------------------------------------------------
  If WordIs("keys") <> 0
    Print("The settings these commands write. ")
    PrintDec(SettingsWifiSlots())
    PrintN(" slots, in preference order:")
    s = 1
    While s <= SettingsWifiSlots()
      If OutBreak() <> 0
        ProcedureReturn
      EndIf
      Print("  ")
      UartWriteStr(SettingsWifiSlotSsidKey(s))
      Print("   and   ")
      UartWriteStr(SettingsWifiSlotPasswordKey(s))
      PrintNl()
      s = s + 1
    Wend
    Print("  ")
    UartWriteStr(SettingsWifiNetworkKey())
    Print("   and   ")
    UartWriteStr(SettingsWifiPasswordKey())
    PrintNl()
    PrintN("  The last pair is the older single network and is read LAST.")
    PrintN("Anything with password in its name is hidden by settings and by wifi.")
    PrintN("settings reveal <name> prints one in full - that is the deliberate")
    PrintN("keystroke that puts a passphrase on the screen.")
    ProcedureReturn
  EndIf

  If WordIs("network") <> 0
    v = ArgRest()
    If v = 0
      PrintN("!! wifi network needs the name of the network, and none was given, so")
      PrintN("   nothing was changed.")
      PrintN("   wifi network <name>")
      PrintN("  The name is the WHOLE REST OF THE LINE, so it may contain spaces -")
      PrintN("  plenty of them do. One to thirty-two characters, and ordinary")
      PrintN("  printable ones only: a name with a byte above 126 in it cannot be")
      PrintN("  stored by this monitor, which is a real limitation and not a bug.")
      PrintN("  Nothing was changed.")
      ProcedureReturn
    EndIf
    ; THE BELT. A leading bare number and a blank is somebody reaching
    ; for `wifi ssid <slot> <name>` under the old word. Storing what
    ; they typed would put "3 Workshop" in the old flat key, which would
    ; then be tried last, under a name no access point broadcasts, and
    ; nothing would have said a word. See the essay at the top of this
    ; section for why this is a refusal and not a guess.
    If WifiLooksSlotted(v) <> 0
      PrintN("!! that begins with a number and a space, and this command takes the")
      PrintN("   WHOLE rest of the line as the name - so it would store the number")
      PrintN("   as part of it. Refusing rather than guessing. Nothing was changed.")
      PrintN("   If you meant a numbered slot:   wifi ssid <slot> <name>")
      PrintN("   If the name really does start with that number, this command")
      PrintN("   cannot set it: use  settings set wifi.network <name>  instead.")
      ProcedureReturn
    EndIf
    If SettingsSetWifiNetwork(v) = 0
      SettingsSayWhyNot()
      Print("   You typed ")
      PrintDec(StrLenZ(v))
      PrintN(" characters. Nothing was changed.")
      ProcedureReturn
    EndIf
    WifiConfigChanged()
    Print("The Wi-Fi network name is now ")
    UartWriteStr(v)
    Print("   (")
    PrintDec(StrLenZ(v))
    PrintN(" characters)")
    Print("  stored under ")
    UartWriteStr(SettingsWifiNetworkKey())
    PrintNl()
    PrintN("  This is in memory only. Type settings save to write it to the medium.")
    ProcedureReturn
  EndIf

  ; "passphrase" as well as "password", because 802.11 calls it a
  ; passphrase and half the world calls it a password, and being told
  ; "unknown word" for the right idea spelled the other way is the sort
  ; of small refusal that makes a tool feel hostile.
  If WordIs("password") <> 0 Or WordIs("passphrase") <> 0
    v = ArgRest()
    If v = 0
      PrintN("!! wifi password needs the passphrase, and none was given, so nothing")
      PrintN("   was changed and nothing was stored.")
      PrintN("   wifi password <passphrase>")
      PrintN("  The passphrase is the WHOLE REST OF THE LINE, so it may contain")
      PrintN("  spaces. Eight to sixty-three characters - that is WPA2's own range")
      PrintN("  and the radio driver will refuse anything outside it.")
      PrintN("  It is stored in plain text. Type wifi password <something> and the")
      PrintN("  whole of that argument is printed before anything is stored.")
      PrintN("  Nothing was changed.")
      ProcedureReturn
    EndIf
    ; THE SAME BELT as on wifi network, and this is the one that matters
    ; more: a passphrase silently two characters longer than the
    ; operator typed is a radio that will not join and a console that
    ; said nothing. Refused, with both ways forward named.
    If WifiLooksSlotted(v) <> 0
      PrintN("!! that begins with a number and a space, and this command takes the")
      PrintN("   WHOLE rest of the line as the passphrase - so it would store the")
      PrintN("   number as the first two characters of it, and the radio would")
      PrintN("   fail to join for no reason you could see. Refusing rather than")
      PrintN("   guessing. Nothing was changed and nothing was stored.")
      PrintN("   If you meant a numbered slot:   wifi phrase <slot> <passphrase>")
      PrintN("   If the passphrase really does start with that number, this command")
      PrintN("   cannot set it: use  settings set wifi.password.plaintext <phrase>")
      PrintN("   instead. The input line is 144 characters, which is enough for the")
      PrintN("   longest one of those, so it will fit.")
      ProcedureReturn
    EndIf
    n = StrLenZ(v)
    If SettingsSetWifiPassword(v) = 0
      SettingsSayWhyNot()
      Print("   You typed ")
      PrintDec(n)
      PrintN(" characters. Nothing was changed and nothing was stored.")
      If n < 8
        PrintN("   Eight is WPA2's floor, not this monitor's - a shorter one could")
        PrintN("   not be used to join a network even if it were stored.")
      EndIf
      ProcedureReturn
    EndIf
    WifiConfigChanged()
    Print("The Wi-Fi passphrase is set. It is ")
    PrintDec(n)
    PrintN(" characters long.")
    PrintN("  The length is printed so you can check the line editor took all of")
    PrintN("  what you typed. The passphrase itself is not echoed back here.")
    SettingsSayPlainText()
    Print("  It is stored under ")
    UartWriteStr(SettingsWifiPasswordKey())
    PrintN(" - the warning is in the key name")
    PrintN("  on purpose, so it survives the file being copied or pasted anywhere.")
    PrintN("  This is in memory only. Type settings save to write it to the medium.")
    ProcedureReturn
  EndIf

  If WordIs("forget") <> 0
    ; ----------------------------------------------------------------
    ;  BARE `wifi forget` STILL MEANS THE OLD PAIR AND NOTHING ELSE.
    ;
    ;  It was tempting to make it mean "forget everything" now that
    ;  there are five things it could mean. Rejected, and firmly: this
    ;  command already exists, it already has a meaning, and somebody
    ;  who types it out of habit to clear the old pair would instead
    ;  destroy four sets of credentials they had just finished typing
    ;  in. A destructive command whose meaning quietly widened under an
    ;  upgrade is the worst kind. `wifi forget <slot>` is the new
    ;  spelling and it says which one out loud.
    ; ----------------------------------------------------------------
    k = ArgWord()
    If k <> 0
      s = WifiSlotWord(k)
      If s < 1 Or s > SettingsWifiLegacySlot()
        WifiSayNoSuchSlot(s)
        ProcedureReturn
      EndIf
      If SettingsRemoveWifiSlot(s) = 0
        If s = SettingsWifiLegacySlot()
          PrintN("The older single pair was already empty, so nothing was forgotten")
          PrintN("and nothing changed.")
        Else
          Print("Wi-Fi slot ")
          PrintDec(s)
          PrintN(" was already empty, so nothing was forgotten and")
          PrintN("nothing changed.")
        EndIf
        ProcedureReturn
      EndIf
      WifiConfigChanged()
      If s = SettingsWifiLegacySlot()
        PrintN("The older single pair has been forgotten - both the network name and")
        PrintN("the passphrase.")
      Else
        Print("Wi-Fi slot ")
        PrintDec(s)
        PrintN(" has been forgotten - both the network name and the")
        PrintN("passphrase, because half a slot is a credential kept for a network")
        PrintN("nobody can see is being kept.")
        PrintN("  The other slots have NOT moved up. Slot numbers are the order they")
        PrintN("  would be tried in, and renumbering them behind you would change a")
        PrintN("  preference you did not touch.")
      EndIf
      PrintN("  Their bytes are cleared out of the table in memory as well as the")
      PrintN("  names. A copy is still in SETTINGS.TXT on the medium until you type")
      PrintN("  settings save. Until then a reset and a settings load bring it back.")
      ProcedureReturn
    EndIf

    hadNet = SettingsHas(SettingsWifiNetworkKey())
    hadPw = SettingsHas(SettingsWifiPasswordKey())
    If hadNet = 0 And hadPw = 0
      PrintN("There was no Wi-Fi network name and no passphrase, so nothing was")
      PrintN("forgotten and nothing changed.")
      ProcedureReturn
    EndIf
    If hadNet <> 0
      SettingsRemove(SettingsWifiNetworkKey())
      PrintN("The Wi-Fi network name has been forgotten.")
    EndIf
    If hadPw <> 0
      SettingsRemove(SettingsWifiPasswordKey())
      PrintN("The Wi-Fi passphrase has been forgotten. Its bytes are cleared out of")
      PrintN("the table in memory as well as the name.")
    EndIf
    WifiConfigChanged()
    PrintN("  A copy is still in SETTINGS.TXT on the medium until you type")
    PrintN("  settings save. Until then a reset and a settings load bring it back.")
    Print("  This did NOT touch the numbered slots. Type wifi forget <1 to ")
    PrintDec(SettingsWifiLegacySlot())
    PrintN(">")
    PrintN("  to clear one of those.")
    ProcedureReturn
  EndIf

  Print("? wifi does not know the word ")
  n = 0
  While n < gWordLen And n < 24
    UartWrite(gLine[gWordAt + n] & $FF)
    n = n + 1
  Wend
  PrintN(", so nothing was done and nothing was changed.")
  Print("  Four networks can be stored, in slots 1 to ")
  PrintDec(SettingsWifiSlots())
  PrintN(". THE NUMBER IS THE ORDER")
  PrintN("  THEY WOULD BE TRIED IN - slot 1 first.")
  PrintN("  wifi                       list every slot, passphrases hidden")
  PrintN("  wifi show                  the same thing, spelled out")
  PrintN("  wifi ssid <slot> <name>    the name is the rest of the line")
  PrintN("  wifi phrase <slot> <phrase>")
  PrintN("                             the phrase is the rest of the line. It is a")
  PrintN("                             different word from wifi password on purpose")
  PrintN("  wifi find <name>           which slot holds that name. EXACT: case and")
  PrintN("                             a 2.4ghz suffix both count")
  PrintN("  wifi forget <slot>         clear one slot, name and passphrase")
  PrintN("  wifi keys                  the settings names, for settings reveal")
  PrintN("  The older single-network pair, still read and read LAST:")
  PrintN("  wifi network <name>        the name is the whole rest of the line")
  PrintN("  wifi password <phrase>     the phrase is the whole rest of the line")
  PrintN("  wifi passphrase <phrase>   the same command, spelled the other way")
  PrintN("  wifi forget                take both of them back out")
  PrintN("  Bringing the radio up and staying connected:")
  PrintN("  wifi scan                  which stored networks are on the air now")
  PrintN("  wifi join                  associate and key to a stored network")
  PrintN("  wifi ip                    this board's MAC and address")
  PrintN("  wifi bus                   read-only SDIO/frame-loss counters")
  PrintN("  wifi rejoin                re-associate and re-lease right now")
  PrintN("  wifi link [on|off]         the keepalive + auto-reconnect, and its count")
  PrintN("  wifi drop                  simulate an access-point drop and watch it recover")
  PrintN("  wifi eapol                 the mid-session rekey panel (root-cause evidence)")
  PrintN("  wifi rekey [on|off]        service the hourly rekey (the cure), or reproduce it")
  PrintN("  wifi heal [on|off]         the automatic re-association backstop")
EndProcedure
