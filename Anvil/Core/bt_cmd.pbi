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
;    bt down                     stop the UART
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
  ElseIf WordIs("down") <> 0
    HciClose()
    PrintN("Bluetooth UART stopped; the controller is still powered.")
  Else
    PrintN("!! bt does not know that subcommand.")
    BtCmdUsage()
  EndIf
EndProcedure
