; ======================================================================
;  bt_cmd.pbi - the `bt` command. Core, chip-free: it drives Bluetooth
;  entirely through Anvil/Net/hci.pbi, which runs over the board's BtTr*
;  byte pipe. Included only by a board that includes that pipe (there is
;  no #CAP for Bluetooth, so the include IS the capability, as touch_cmd
;  is for the touch panel).
;
;    bt                          state, then this usage
;    bt up                       power the controller and reset it; it
;                                runs its ROM firmware at 115200 baud
;    bt up <addr> <len> [baud]   the same, then load the firmware patch
;                                already in memory at <addr>, <len> bytes
;                                (hex; first: load BRCMBT.HCD <addr>),
;                                then raise the rate (decimal, default
;                                3000000 - the board's max-speed)
;    bt scan [units]             inquiry for units x 1.28 s (default 4)
;                                and list every device heard, once each
;    bt tone <addr> [s] [mono]   stream a 1 kHz tone to the speaker or
;                                headset at <addr> (AA:BB:CC:DD:EE:FF) for
;                                s seconds (default 10, 1 to 120): the
;                                link, pairing, L2CAP, AVDTP and SBC of
;                                Anvil/Net/a2dp.pbi end to end. Stereo
;                                (the mono signal twice) unless `mono`.
;    bt down                     stop the UART
;
;  ON THE PI 4 `bt up` LENDS THE SERIAL CONSOLE TO BLUETOOTH (hw_bt.pi4):
;  the serial wire is silent until `bt down`; use the network console or
;  the screen meanwhile.
;
;  The address printed after `bt up` without a patch is the CYW43455's
;  factory placeholder (43:45:C0:00:1F:AC); it is labelled as such.
; ======================================================================

EnableExplicit

Procedure BtCmdSayWhy()
  Print("!! ")
  UartWriteStr(HciWhy())
  PrintN(".")
EndProcedure

Procedure BtCmdAddr()
  Define i.i
  For i = 0 To 5
    If i > 0 : UartWrite(58) : EndIf         ; ':'
    PutHex2(HciBdAddrByte(i))
  Next
EndProcedure

Procedure BtCmdUsage()
  PrintN("bt drives the Bluetooth controller over its HCI UART. The subcommands are:")
  PrintN("  bt up                      power and reset it (ROM firmware, 115200)")
  PrintN("  bt up <addr> <len> [baud]  also load the patch at <addr> (hex), then")
  PrintN("                             raise the rate (decimal, default 3000000)")
  PrintN("  bt scan [units]            inquiry for units x 1.28 s, list devices")
  PrintN("  bt tone <addr> [s] [mono]  play a 1 kHz tone on a speaker for s seconds")
  PrintN("  bt down                    stop the UART")
  PrintN("The patch is BCM4345C0.hcd; put it on the boot medium and load it first,")
  PrintN("for example: load BRCMBT.HCD 2000000")
EndProcedure

Procedure BtCmdUp()
  Define addr.i, n.i, baud.i
  addr = 0 : n = 0 : baud = 3000000
  SkipSpace()
  If gLine[gPos] <> 0
    addr = ParseHex()
    If gParseOk = 0
      PrintN("!! bt up takes a patch address and length in hex. Nothing was done.")
      ProcedureReturn
    EndIf
    n = ParseHex()
    If gParseOk = 0 Or n < 3
      PrintN("!! bt up needs the patch's length in hex after its address. Nothing was done.")
      ProcedureReturn
    EndIf
    SkipSpace()
    If gLine[gPos] <> 0
      baud = ParseDec()
      If gParseOk = 0
        PrintN("!! the baud rate must be decimal. Nothing was done.")
        ProcedureReturn
      EndIf
    EndIf
  EndIf
  If HciBringUp(addr, n, baud) = 0
    BtCmdSayWhy()
    PrintN("The UART is left open for bt diag; bt down closes it and gives the console back.")
    ProcedureReturn
  EndIf
  Print("Bluetooth up at ")
  PrintDec(HciBaud())
  Print(" baud, HCI version ")
  PrintDec(HciHciVer())
  Print(", manufacturer ")
  PrintDec(HciManufacturer())
  Print(", subversion 0x")
  PutHex2((HciLmpSubver() >> 8) & $FF)
  PutHex2(HciLmpSubver() & $FF)
  PrintN(".")
  Print("Address ")
  BtCmdAddr()
  If HciBdAddrIsPlaceholder() <> 0
    PrintN(" - the unpatched factory placeholder, not this board's address.")
  Else
    PrintNl()
  EndIf
  Print("ACL: ")
  PrintDec(HciAclTotal())
  Print(" buffers of ")
  PrintDec(HciAclMax())
  PrintN(" bytes.")
  If HwBtConsoleLent() <> 0
    PrintN("The serial console is lent to Bluetooth until bt down (this console and the screen keep working).")
  EndIf
EndProcedure

Procedure BtCmdScan()
  Define units.i = 4
  Define n.i, i.i, r.i, k.i
  SkipSpace()
  If gLine[gPos] <> 0
    units = ParseDec()
    If gParseOk = 0 Or units < 1 Or units > 48
      PrintN("!! the scan length is 1 to 48 units of 1.28 seconds. Nothing was done.")
      ProcedureReturn
    EndIf
  EndIf
  n = HciInquiry(units)
  If n < 0
    BtCmdSayWhy()
    ProcedureReturn
  EndIf
  PrintDec(n)
  PrintN(" device(s) heard:")
  For i = 0 To n - 1
    Print("  ")
    For k = 0 To 5
      If k > 0 : UartWrite(58) : EndIf
      PutHex2(HciDeviceAddrByte(i, k))
    Next
    Print("  class 0x")
    PutHex2((HciDeviceClass(i) >> 16) & $FF)
    PutHex2((HciDeviceClass(i) >> 8) & $FF)
    PutHex2(HciDeviceClass(i) & $FF)
    r = HciDeviceRssi(i)
    If r <> 127
      Print("  ")
      PrintDec(r)
      Print(" dBm")
    EndIf
    PrintNl()
  Next
EndProcedure

Global Dim btc_addr.a[6]
Global Dim btc_frames.a[256]

; AA:BB:CC:DD:EE:FF into btc_addr (most significant first). 1 or 0.
Procedure.i BtCmdParseAddr()
  Define k.i, hi.i, lo.i
  SkipSpace()
  For k = 0 To 5
    hi = HexVal(gLine[gPos] & $FF)
    lo = HexVal(gLine[gPos + 1] & $FF)
    If hi < 0 Or lo < 0 : ProcedureReturn 0 : EndIf
    btc_addr[k] = (hi << 4) | lo
    gPos = gPos + 2
    If k < 5
      If gLine[gPos] <> 58 : ProcedureReturn 0 : EndIf
      gPos = gPos + 1
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure BtCmdTone()
  Define secs.i, stereo.i, hz.i, t0.i, due.i, sent.i, have.i, i.i, k.i, phase.i
  Define fb.i, misses.i, state.i, setupMs.i
  If BtCmdParseAddr() = 0
    PrintN("!! bt tone needs the device's address as AA:BB:CC:DD:EE:FF. Nothing was done.")
    ProcedureReturn
  EndIf
  secs = 10 : stereo = 1
  SkipSpace()
  If gLine[gPos] >= 48 And gLine[gPos] <= 57
    secs = ParseDec()
    If gParseOk = 0 Or secs < 1 Or secs > 120
      PrintN("!! the length is 1 to 120 seconds. Nothing was done.")
      ProcedureReturn
    EndIf
  EndIf
  SkipSpace()
  If gLine[gPos] <> 0
    gWordAt = gPos
    SkipWord()
    gWordLen = gPos - gWordAt
    If WordIs("mono") <> 0
      stereo = 0
    Else
      PrintN("!! the only word bt tone takes after the length is mono. Nothing was done.")
      ProcedureReturn
    EndIf
  EndIf
  If HciIsOpen() = 0 Or HciAclTotal() < 1
    PrintN("!! Bluetooth is not up: bt up (with the firmware patch) first.")
    ProcedureReturn
  EndIf
  hz = TickHz()
  If hz <= 0
    PrintN("!! this board has no tick counter to pace the audio with.")
    ProcedureReturn
  EndIf
  SbcStereo = stereo
  fb = 64 + stereo * 4
  t0 = Ticks()
  If A2dpBegin(@btc_addr[0], stereo) = 0
    Print("!! ")
    UartWriteStr(A2dpWhy())
    PrintN(".")
    ProcedureReturn
  EndIf
  Repeat
    state = A2dpPoll()
  Until state = #A2DP_STREAMING Or state = #A2DP_FAILED
  setupMs = (Ticks() - t0) / (hz / 1000)
  If state = #A2DP_FAILED
    Print("!! ")
    UartWriteStr(A2dpWhy())
    Print(" (step ")
    PrintDec(A2dpFailStep())
    Print(", code ")
    PrintDec(A2dpFailCode())
    PrintN(").")
    A2dpEnd()
    ProcedureReturn
  EndIf
  ; 375 frames a second (48000 / 128); three frames a packet, as the NES;
  ; at most two packets ahead of the clock.
  t0 = Ticks()
  sent = 0 : have = 0 : phase = 0 : misses = 0
  Repeat
    A2dpPoll()
    If A2dpStreaming() = 0 : Break : EndIf
    due = ((Ticks() - t0) * 375) / hz
    If have < 3 And sent + have < due + 6
      For i = 0 To 127
        SbcPcm(i) = PeekW(?btc_sine + phase * 2)
        phase = phase + 1
        If phase >= 48 : phase = 0 : EndIf
      Next
      SbcEncode()
      For k = 0 To fb - 1 : btc_frames[have * fb + k] = SbcEncoded(k) : Next
      have = have + 1
    EndIf
    If have = 3
      If A2dpSend(@btc_frames[0], 3) <> 0
        sent = sent + 3 : have = 0
      Else
        misses = misses + 1
      EndIf
    EndIf
  Until sent >= secs * 375
  state = A2dpState()
  A2dpEnd()
  If state <> #A2DP_STREAMING
    Print("!! the stream stopped: ")
    UartWriteStr(A2dpWhy())
    PrintN(".")
  EndIf
  Print("Tone: link and stream set up in ")
  PrintDec(setupMs)
  Print(" ms, ")
  PrintDec(A2dpPackets())
  Print(" packets (")
  PrintDec(sent)
  Print(" frames, ")
  If stereo <> 0 : Print("stereo") : Else : Print("mono") : EndIf
  Print("), ")
  PrintDec(misses)
  Print(" waits for a controller buffer, ")
  PrintDec(HciPairings())
  Print(" pairing answers, ")
  PrintDec(HciRxErrors())
  Print(" receive errors, ")
  PrintDec(A2dpPeerCommands())
  PrintN(" commands from the speaker.")
EndProcedure

DataSection
btc_sine:
  Data.w 0,783,1553,2296,3000,3653,4243,4760,5196,5543,5796,5949,6000,5949,5796,5543,5196,4760,4243,3653,3000,2296,1553,783
  Data.w 0,-783,-1553,-2296,-3000,-3653,-4243,-4760,-5196,-5543,-5796,-5949,-6000,-5949,-5796,-5543,-5196,-4760,-4243,-3653,-3000,-2296,-1553,-783
EndDataSection

Procedure CmdBt()
  SkipSpace()
  If gLine[gPos] = 0
    If HciBaud() > 0 And HciError() = 0
      Print("Bluetooth: ")
      PrintDec(HciBaud())
      Print(" baud, ")
      If HciPatched() <> 0
        PrintN("firmware patched.")
      Else
        PrintN("ROM firmware.")
      EndIf
    Else
      PrintN("Bluetooth is not up.")
    EndIf
    BtCmdUsage()
    ProcedureReturn
  EndIf
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("up") <> 0
    BtCmdUp()
  ElseIf WordIs("scan") <> 0
    BtCmdScan()
  ElseIf WordIs("diag") <> 0
    HwBtDiag()
    Print("HCI: ")
    PrintDec(HciRxBytes())
    Print(" bytes received, ")
    PrintDec(HciRxErrors())
    Print(" not a packet, last error: ")
    UartWriteStr(HciWhy())
    PrintN(".")
  ElseIf WordIs("tone") <> 0
    BtCmdTone()
  ElseIf WordIs("down") <> 0
    HciClose()
    PrintN("Bluetooth UART stopped and the serial console given back.")
  Else
    PrintN("!! bt does not know that subcommand.")
    BtCmdUsage()
  EndIf
EndProcedure
