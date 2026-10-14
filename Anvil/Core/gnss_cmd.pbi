; ======================================================================
;  gnss_cmd.pbi - the `gnss` command: a satellite receiver from the console.
;
;    gnss                      open the receiver (USB) if it is not, and say what it has
;    gnss watch [seconds]      read it for that long (10 by default), a line a second
;    gnss raw [seconds]        print what it sends, as text (5 by default)
;    gnss source usb | bluetooth | ble | network
;                              open that source instead (the last three are placeholders)
;
;  Nothing here waits on the receiver: every loop pumps it and looks at the
;  clock, and any key ends it.
; ======================================================================

Procedure GnssCmdDeg(v.i)
  Define a.i
  a = v : If a < 0 : Print("-") : a = 0 - a : EndIf
  PrintDec(a / 10000000) : Print(".")
  PutDecPad(a % 10000000, 7)
EndProcedure

Procedure GnssCmdLine()
  Define q.i, v.i
  Define Dim fix.a[64]
  q = GnssFix(@fix[0])
  Select q
    Case #HW_GNSS_NOFIX : Print("no fix")
    Case #HW_GNSS_2D    : Print("2D fix")
    Case #HW_GNSS_3D    : Print("3D fix")
    Case #HW_GNSS_DGPS  : Print("differential fix")
  EndSelect
  If q <> #HW_GNSS_NOFIX
    Print("  ") : GnssCmdDeg(PeekL(@fix[4])) : Print(", ") : GnssCmdDeg(PeekL(@fix[8]))
    v = PeekL(@fix[12]) : Print("  alt ") : PrintDec(v / 1000) : Print(" m")
    v = PeekL(@fix[16]) : If v >= 0 : Print("  +-") : PrintDec(v / 1000) : Print(".") : PrintDec((v % 1000) / 100) : Print(" m") : EndIf
  EndIf
  v = PeekL(@fix[20]) : If v >= 0 : Print("  ") : PrintDec((v * 3600) / 1609344) : Print(" mph") : EndIf
  v = PeekL(@fix[24]) : If v >= 0 : Print("  course ") : PrintDec(v / 100000) : EndIf
  v = PeekL(@fix[28]) : If v >= 0 : Print("  sats ") : PrintDec(v) : EndIf
  v = PeekL(@fix[56]) : If v >= 0 : Print("/") : PrintDec(v) : EndIf
  v = PeekL(@fix[36])
  If v >= 0
    Print("  ") : PutDecPad(v / 3600000, 2) : Print(":") : PutDecPad((v / 60000) % 60, 2) : Print(":") : PutDecPad((v / 1000) % 60, 2) : Print(" UTC")
  EndIf
  Select PeekL(@fix[60])
    Case 1 : Print("  (UBX NAV-PVT)")
    Case 3 : Print("  (NMEA GGA)")
    Case 4 : Print("  (NMEA GNS)")
  EndSelect
  PrintN("")
EndProcedure

Procedure GnssCmdCounts()
  Define p.i, any.i
  Print("  ") : PrintDec(GnssBytes()) : Print(" bytes, ") : PrintDec(GnssGood()) : Print(" good frames, ") : PrintDec(GnssBad()) : Print(" bad;")
  any = 0
  For p = 0 To 8
    If GnssProtoOk(p) > 0 : Print(" ") : UartWriteStr(GnssProtoName(p)) : Print(" ") : PrintDec(GnssProtoOk(p)) : any = 1 : EndIf
  Next
  If any = 0 : Print(" no protocol recognised yet") : EndIf
  PrintN("")
EndProcedure

Procedure.i GnssCmdOpen(src.i)
  If GnssSource() = src
    ProcedureReturn 1
  EndIf
  If GnssOpen(src) = 0
    Print("!! the ") : UartWriteStr(GnssSourceName(src)) : Print(" source did not open: ") : UartWriteStr(GnssWhy()) : PrintN("")
    ProcedureReturn 0
  EndIf
  Print("GNSS source: ") : UartWriteStr(GnssSourceName(src))
  If src = #GNSS_SRC_USB
    Print(", ") : UartWriteStr(UsbSerKindText(UsbSerKind())) : Print(" ") : PutHexN(UsbSerVid(), 4) : Print(":") : PutHexN(UsbSerPid(), 4)
    Print(" on USB slot ") : PrintDec(UsbSerSlot())
    If UsbSerNeedsBaud() <> 0 : Print(", baud searched from 9600") : EndIf
  EndIf
  PrintN(".")
  ProcedureReturn 1
EndProcedure

Procedure GnssCmdWatch(seconds.i, raw.i)
  Define t0.i, tNext.i, now.i, n.i, i.i, c.i
  Define Dim b.a[256]
  t0 = HwMicros() : tNext = t0 + 1000000
  Repeat
    If raw <> 0
      ; the bytes themselves: the source's own read, shown as text
      n = gnss_SrcRead(@b[0], 256)
      For i = 0 To n - 1
        c = b[i]
        gnss_Byte(c)
        If c = 10 Or c = 13 Or (c >= 32 And c < 127)
          If c <> 13 : UartWrite(c) : EndIf
        Else
          Print("<") : PutHex2(c) : Print(">")
        EndIf
      Next
    Else
      GnssPump()
    EndIf
    now = HwMicros()
    If raw = 0 And now >= tNext
      GnssCmdLine() : NetConsoleFlush() : tNext = tNext + 1000000      ; a line a second reaches a network console too
    EndIf
    HwPet()
    If OutBreak() <> 0 : Break : EndIf
  Until now - t0 >= seconds * 1000000
  If raw <> 0 : PrintN("") : EndIf
  GnssCmdCounts()
  NetConsoleFlush()
EndProcedure

Procedure CmdGnss()
  Define s.i
  SkipSpace()
  If gLine[gPos] = 0
    If GnssCmdOpen(#GNSS_SRC_USB) <> 0
      GnssCmdWatch(2, 0)
    EndIf
    PrintN("Type gnss watch [seconds], gnss raw [seconds] or gnss source usb | bluetooth | ble | network.")
    ProcedureReturn
  EndIf
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("watch") <> 0 Or WordIs("raw") <> 0
    s = 10 : If WordIs("raw") <> 0 : s = 5 : EndIf
    SkipSpace()
    If gLine[gPos] <> 0
      s = ParseDec()
      If gParseOk = 0 Or s < 1 Or s > 3600
        PrintN("!! seconds must be 1 to 3600.")
        ProcedureReturn
      EndIf
    EndIf
    If GnssSource() = #GNSS_SRC_NONE
      If GnssCmdOpen(#GNSS_SRC_USB) = 0
        ProcedureReturn
      EndIf
    EndIf
    If WordIs("raw") <> 0 : GnssCmdWatch(s, 1) : Else : GnssCmdWatch(s, 0) : EndIf
  ElseIf WordIs("source") <> 0
    SkipSpace()
    gWordAt = gPos : SkipWord() : gWordLen = gPos - gWordAt
    If WordIs("usb") <> 0
      GnssCmdOpen(#GNSS_SRC_USB)
    ElseIf WordIs("bluetooth") <> 0
      GnssCmdOpen(#GNSS_SRC_BLUETOOTH)
    ElseIf WordIs("ble") <> 0
      GnssCmdOpen(#GNSS_SRC_BLE)
    ElseIf WordIs("network") <> 0
      GnssCmdOpen(#GNSS_SRC_NETWORK)
    Else
      PrintN("!! the sources are usb, bluetooth, ble and network.")
    EndIf
  Else
    PrintN("!! gnss does not know that word. Try gnss, gnss watch, gnss raw or gnss source.")
  EndIf
EndProcedure
