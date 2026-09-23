; ======================================================================
;  usb_cmd.pi4 - the `usb` DIAGNOSTICS command. Core, chip-free.
;
;  This file names no chip and touches no register, no controller and no
;  driver. It asks the board whether it has a USB host at all (RequireCap
;  over #CAP_USB) and, if so, reports what the board's existing host stack
;  already knows through the HwUsb* seam (RaspberryPi4/Board/hw_usb.pi4 on
;  the Pi 4, over Lib/pcie + Lib/xhci + Lib/usbmsc and the enumeration
;  walk). On a board that declares #CAP_USB = 0 the same command, compiled
;  from the same bytes, refuses cleanly with the honest sentence RequireCap
;  prints - one command, many boards, no fork and no #ifdef, exactly as
;  gpio_cmd.pi4 does for GPIO.
;
;  WHAT THIS IS: DIAGNOSTIC VISIBILITY for a bare-metal bench. The host
;  stack is already driven by mount/load/save and by the cursor; what was
;  missing was a way to SEE what is attached and to pull a raw block off a
;  stick without going through the filesystem. That is all this adds. It
;  drives nothing the monitor does not already drive.
;
;  THE SYNTAX:
;    usb                 same as usb info
;    usb info            the host controller, the ports, and a device list
;    usb tree            the topology: controller -> root ports -> internal
;                        hub -> hub ports, then the addressed devices
;    usb storage         the mass-storage device: vendor, product, block
;                        size, block count, capacity
;    usb read <blk> <addr> [count]
;                        read count 512-byte blocks (default 1) starting at
;                        block <blk> into memory at <addr>. ALL THREE
;                        ARGUMENTS ARE HEX, like the memory commands, and
;                        the destination is range-checked against the
;                        payload windows and the monitor's own region the
;                        same way load and get are.
; ======================================================================

; A count cap for usb read. Not a feature limit - it exists so a typo in a
; hex count cannot ask for millions of blocks (and so blk*count arithmetic
; cannot overflow). 65536 blocks is 32 MB, well inside the low window.
#USB_READ_MAX = 65536
; Blocks per call to the board's range read - a 1 MiB run, which is also
; the most one READ (10) carries on the Pi 4. A break is noticed between
; runs.
#USB_READ_RUN = 2048

; ----------------------------------------------------------------------
;  Small renderers for the portable #HW_USB_* codes. The board hands the
;  core a code; the core turns it into words. Kept in one place so a tree
;  line and an info line read identically.
; ----------------------------------------------------------------------
Procedure PutUsbSpeed(s.i)
  If s = #HW_USB_SPEED_LOW
    Print("low speed (1.5 Mb/s)")
  ElseIf s = #HW_USB_SPEED_FULL
    Print("full speed (12 Mb/s)")
  ElseIf s = #HW_USB_SPEED_HIGH
    Print("high speed (480 Mb/s)")
  ElseIf s = #HW_USB_SPEED_SUPER
    Print("super speed (5 Gb/s)")
  Else
    Print("speed unknown")
  EndIf
EndProcedure

; Padded to eight columns so slot/addr line up down a device list.
Procedure PutUsbKind(k.i)
  If k = #HW_USB_KIND_KEYBOARD
    Print("keyboard")
  ElseIf k = #HW_USB_KIND_MOUSE
    Print("mouse   ")
  ElseIf k = #HW_USB_KIND_STORAGE
    Print("storage ")
  ElseIf k = #HW_USB_KIND_HUB
    Print("hub     ")
  Else
    Print("other   ")
  EndIf
EndProcedure

; VID:PID as four-and-four hex, or an honest word when the device
; descriptor could not be re-read (a full-speed device that stalled the
; longer read, say). -1 from the seam is the "unavailable" answer.
Procedure PutUsbId(vid.i, pid.i)
  If vid < 0 Or pid < 0
    Print("id unknown")
    ProcedureReturn
  EndIf
  PutHexN(vid, 4)
  Print(":")
  PutHexN(pid, 4)
EndProcedure

; xHCI HCIVERSION is BCD: high byte major, low byte minor-in-BCD, so
; $0100 is 1.00 and $0110 is 1.10. Printing the low byte as two hex
; digits renders the BCD correctly without decoding it.
Procedure PutUsbVersion(v.i)
  PrintDec((v >> 8) & $FF)
  Print(".")
  PutHexN(v & $FF, 2)
EndProcedure

; Where a device sits. Route 0 is a root port; anything else is the
; downstream port of the internal hub (the seam's one-tier route).
Procedure PutUsbWhere(i.i)
  Define r.i
  r = HwUsbDevRoute(i)
  If r = 0
    Print("on a root port")
  Else
    Print("behind the internal hub, port ")
    PrintDec(r)
  EndIf
EndProcedure

; One device: kind, slot, address, speed, VID:PID, class, and where.
Procedure PutUsbDevLine(i.i)
  Define cls.i
  Print("  ")
  PutUsbKind(HwUsbDevKind(i))
  Print("  slot ")
  PrintDec(HwUsbDevSlot(i))
  Print("  addr ")
  PrintDec(HwUsbDevAddress(i))
  Print("  ")
  PutUsbSpeed(HwUsbDevSpeed(i))
  Print("  ")
  PutUsbId(HwUsbDevVid(i), HwUsbDevPid(i))
  Print("  class ")
  cls = HwUsbDevClass(i)
  If cls < 0
    Print("??")
  Else
    PutHexN(cls, 2)
  EndIf
  Print("  ")
  PutUsbWhere(i)
  PrintNl()
EndProcedure

; The refusal both info and tree print when the host will not come up. It
; points at mount, which brings the medium up with a full step-by-step
; report of exactly where the chain fails.
Procedure PutUsbNoHost()
  PrintN("!! the USB host controller on this board would not start, so nothing")
  PrintN("   on the USB bus can be seen. Type mount to bring the boot medium up")
  PrintN("   with a full step-by-step report of where the USB chain fails.")
EndProcedure

Procedure UsbInfo()
  Define k.i
  Define i.i
  k = HwUsbTree()
  If k < 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  Print("USB host: xHCI controller up, PCI id ")
  PutHexN(HwUsbHostVid(), 4)
  Print(":")
  PutHexN(HwUsbHostPid(), 4)
  Print(", version ")
  PutUsbVersion(HwUsbHostVersion())
  PrintNl()
  Print("Root ports: ")
  PrintDec(HwUsbPortCount())
  PrintNl()
  If HwUsbHubPresent() <> 0
    Print("Internal hub: on root port ")
    PrintDec(HwUsbHubRootPort())
    Print(", ")
    PrintDec(HwUsbHubPorts())
    PrintN(" downstream ports")
  Else
    PrintN("Internal hub: none")
  EndIf
  Print("Attached devices: ")
  PrintDec(k)
  PrintNl()
  i = 0
  While i < k
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    PutUsbDevLine(i)
    i = i + 1
  Wend
  PrintN("Type usb tree for the topology, usb storage for the disk, or")
  PrintN("usb read <block> <address> [count] to pull raw blocks into memory.")
EndProcedure

; ----------------------------------------------------------------------
;  UsbWalkReport - WHY the ports above did not become devices.
;
;  The enumeration walk is written so that no failure along it is fatal,
;  which is right - the device that fails is usually not the one being
;  looked for - and the price was that every refusal was thrown away.
;  Two root ports reporting a connection and zero devices addressed
;  printed the same lines as an empty bus.
;
;  So the walk keeps a row per port it stopped at, and this prints them.
;  It prints when NOTHING was addressed, and also whenever some port
;  stopped short even though others succeeded - a hub that enumerated
;  while the boot stick did not is exactly the case worth seeing.
;
;  A board whose walk keeps no rows answers a count of zero and this
;  prints nothing at all, which is why it is safe in the shared core.
; ----------------------------------------------------------------------
Procedure UsbWalkReport(addressed.i)
  Define n.i
  Define i.i
  Define sc.i
  Define shown.i

  n = HwUsbWalkCount()
  If n <= 0
    ProcedureReturn
  EndIf

  ; Is there anything to say? Only rows that stopped short are worth
  ; printing, unless nothing was addressed at all - in which case the
  ; successful-looking rows are themselves the surprise.
  shown = 0
  i = 0
  While i < n
    If HwUsbWalkReached(i) = 0
      shown = 1
    EndIf
    i = i + 1
  Wend
  If shown = 0 And addressed > 0
    ProcedureReturn
  EndIf

  PrintNl()
  PrintN("Why the ports above did not all become devices:")
  i = 0
  While i < n
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    If HwUsbWalkIsHub(i) <> 0
      Print("  hub port  ")
    Else
      Print("  root port ")
    EndIf
    PrintDec(HwUsbWalkPort(i))
    Print("  ")
    ; The step text is a string RETURNED by the board, so it is a pointer
    ; and goes out through UartWriteStr - Print() of a returned value
    ; prints the address as a number.
    UartWriteStr(HwUsbWalkStepText(HwUsbWalkStep(i)))
    PrintNl()

    ; PORTSC, raw, for a root port. It is the register the reset and the
    ; speed were both read out of, so a report that names a port problem
    ; without it is asking to be taken on trust.
    sc = HwUsbWalkPortsc(i)
    If sc >= 0
      Print("              PORTSC ")
      PutHexN(sc, 8)
      Print("   CCS ")
      PrintDec(sc & 1)
      Print("  PED ")
      PrintDec((sc >> 1) & 1)
      Print("  PR ")
      PrintDec((sc >> 4) & 1)
      Print("  PP ")
      PrintDec((sc >> 9) & 1)
      Print("  PLS ")
      PrintDec((sc >> 5) & 15)
      PrintNl()
    EndIf

    If HwUsbWalkSlot(i) <> 0
      Print("              slot ")
      PrintDec(HwUsbWalkSlot(i))
      PrintNl()
    EndIf

    ; The codes below are printed only for a port that STOPPED SHORT. The
    ; driver's error code is sticky - it still names whatever failed last
    ; anywhere on the bus - so beside a port that was addressed it would
    ; blame that port for somebody else's refusal.
    If HwUsbWalkReached(i) = 0
      ; The completion code is the CONTROLLER's own verdict on the last
      ; command this port ran, and 1 is Success - so anything else here
      ; is the controller naming the fault rather than an inference.
      If HwUsbWalkComp(i) <> 0 And HwUsbWalkComp(i) <> 1
        Print("              last completion code ")
        PrintDec(HwUsbWalkComp(i))
        PrintN("  (1 would be Success; see the xHCI completion code table)")
      EndIf

      If HwUsbWalkErr(i) <> 0
        Print("              ")
        UartWriteStr(HwUsbWalkErrText(HwUsbWalkErr(i)))
        PrintNl()
      EndIf
    EndIf
    i = i + 1
  Wend

  ; The controller's own state, once, at the end. If every row above
  ; says the same thing, this is the line that says whether the ports
  ; were the problem or the controller was.
  Print("  controller after the walk:  USBSTS ")
  PutHexN(HwUsbWalkUsbSts(), 8)
  Print("   USBCMD ")
  PutHexN(HwUsbWalkUsbCmd(), 8)
  PrintNl()
  PrintN("    USBSTS bit 0 is HCHalted, bit 2 Host System Error, bit 3 Event")
  PrintN("    Interrupt, bit 12 Host Controller Error. A halted or errored")
  PrintN("    controller explains every row at once and is read first.")
EndProcedure

Procedure UsbTree()
  Define k.i
  Define n.i
  Define p.i
  Define i.i
  k = HwUsbTree()
  If k < 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  PrintN("USB topology on this board:")
  Print("  host controller   xHCI ")
  PutHexN(HwUsbHostVid(), 4)
  Print(":")
  PutHexN(HwUsbHostPid(), 4)
  Print("  version ")
  PutUsbVersion(HwUsbHostVersion())
  Print("  (")
  PrintDec(HwUsbPortCount())
  PrintN(" root ports)")
  ; THE LINK UNDER THE CONTROLLER, AND ITS FIRMWARE - what a slow bus would
  ; show first. Printed only where the board has one.
  If HwUsbHostLinkSpeed() > 0
    Print("  controller link   PCI Express ")
    If HwUsbHostLinkSpeed() = 1
      Print("2.5 GT/s")
    ElseIf HwUsbHostLinkSpeed() = 2
      Print("5.0 GT/s")
    Else
      Print("speed code ")
      PrintDec(HwUsbHostLinkSpeed())
    EndIf
    Print(" x")
    PrintDec(HwUsbHostLinkWidth())
    If HwUsbHostLinkSsc() = 1
      Print(", spread-spectrum clocking on")
    ElseIf HwUsbHostLinkSsc() = 0
      Print(", spread-spectrum clocking NOT on")
    EndIf
    If HwUsbHostFirmware() >= 0
      Print(", controller firmware ")
      PutHexN(HwUsbHostFirmware(), 8)
    EndIf
    PrintNl()
  EndIf

  n = HwUsbPortCount()
  p = 1
  While p <= n
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    If HwUsbPortConnected(p) <> 0
      Print("  root port ")
      PrintDec(p)
      Print("  connected, ")
      PutUsbSpeed(HwUsbPortSpeed(p))
      If HwUsbPortLinkState(p) >= 0
        Print(", link state U")
        PrintDec(HwUsbPortLinkState(p))
      EndIf
      If HwUsbPortPowerTimeouts(p) >= 0
        Print(", U1/U2 timeouts ")
        PrintDec(HwUsbPortPowerTimeouts(p) & $FF)
        Print("/")
        PrintDec((HwUsbPortPowerTimeouts(p) >> 8) & $FF)
      EndIf
      PrintNl()
    EndIf
    p = p + 1
  Wend

  If HwUsbHubPresent() <> 0
    Print("  internal hub on root port ")
    PrintDec(HwUsbHubRootPort())
    Print("  (")
    PrintDec(HwUsbHubPorts())
    PrintN(" downstream ports)")
    n = HwUsbHubPorts()
    p = 1
    While p <= n
      If OutBreak() <> 0
        ProcedureReturn
      EndIf
      If HwUsbHubPortConnected(p) = 1
        Print("    hub port ")
        PrintDec(p)
        Print("  connected, ")
        PutUsbSpeed(HwUsbHubPortSpeed(p))
        PrintNl()
      EndIf
      p = p + 1
    Wend
  EndIf

  Print("Devices (")
  PrintDec(k)
  PrintN("):")
  If k = 0
    PrintN("  none addressed. A device on a port that did not answer enumeration")
    PrintN("  is not listed here; the ports above are shown either way.")
  EndIf
  i = 0
  While i < k
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    PutUsbDevLine(i)
    i = i + 1
  Wend
  UsbWalkReport(k)
EndProcedure

; ----------------------------------------------------------------------
;  usb link - THE SAME LINK AS `usb tree`'s ONE SENTENCE, IN RAW WORDS.
;
;  `usb tree` ends its controller line with words: "spread-spectrum
;  clocking on". Those words come from a single flag, and a flag cannot be
;  audited - it reads identically whether the driver turned the feature on,
;  found it already on, or simply believes it did. This command prints the
;  registers underneath instead: the name the board gives each one, the raw
;  word as read, every named field inside it, and the board's own sentence
;  saying what the drivers that run this part in service leave there.
;
;  THE CORE LEARNS NOTHING ABOUT ANY CHIP HERE. Every offset, bit position
;  and reference claim comes back through the seam as text and numbers the
;  board owns. This procedure knows only that a link has registers, that a
;  register has fields, and that -1 means nobody answered.
;
;  A board with no such link answers zero rows, which is a fact and not a
;  failure, and gets a sentence of its own.
; ----------------------------------------------------------------------
Procedure UsbLink()
  Define n.i
  Define r.i
  Define f.i
  Define nf.i
  Define v.i

  If HwUsbHostPresent() = 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  n = HwUsbLinkRegCount()
  If n <= 0
    PrintN("This board's USB host controller does not sit behind a link this")
    PrintN("monitor can read registers from, so there is nothing to show. That is")
    PrintN("a property of the board, not a failure - type usb tree for the")
    PrintN("controller and its ports.")
    ProcedureReturn
  EndIf
  PrintN("The link under the USB host controller, as the registers read now:")
  r = 0
  While r < n
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    Print("  ")
    UartWriteStr(HwUsbLinkRegName(r))
    v = HwUsbLinkRegValue(r)
    If v < 0
      ; NOT A ZERO. A register nothing answered and a register holding zero
      ; are different facts, and printing them alike is how a driver gets
      ; credited with a bit it never read.
      PrintN("")
      PrintN("      not read - nothing answered for this register on this board")
    Else
      Print("   ")
      PutHexN(v, 8)
      PrintNl()
      nf = HwUsbLinkFieldCount(r)
      f = 0
      While f < nf
        Print("      ")
        UartWriteStr(HwUsbLinkFieldName(r, f))
        Print("  = ")
        PrintDec(HwUsbLinkFieldValue(r, f))
        PrintNl()
        f = f + 1
      Wend
    EndIf
    Print("      ")
    UartWriteStr(HwUsbLinkRegNote(r))
    PrintNl()
    r = r + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  usb timing - WHERE THE USB STACK'S TIME GOES, ON THE BOARD'S OWN CLOCK.
;
;  WHY IT IS NOT A HOST STOPWATCH. Every storage figure this monitor has
;  ever quoted was timed by a PC waiting on the network console, and that
;  console has a floor of about four hundred milliseconds - so a one-block
;  read and a one-megabyte read measured the same, and the difference
;  between them was noise. These rows are counted on the board's own
;  architectural counter by the driver that does the waiting.
;
;  WHY ROWS AND NOT A TIMELINE. The boot trail is a timeline and it holds
;  64 entries; a boot writes 161 of them, so the 13 seconds worth reading
;  are overwritten by the 400 milliseconds that follow. A fixed row per
;  WAIT SITE cannot wrap, and count-with-total says more than a timeline
;  anyway: 800 ms of port reset is one slow port or four fast retries, and
;  those are different faults.
;
;  A board that keeps no such ledger answers zero rows, and that is a fact
;  about the board rather than a failure to read.
; ----------------------------------------------------------------------

; Microseconds as milliseconds with three decimals, so a 12 us wait and a
; 12 second one print in one column and can be compared by eye. Written
; out rather than reached for a formatter: the fraction must keep its
; leading zeros or 1.007 ms prints as 1.7.
Procedure PutUsbMs(us.i)
  Define whole.i
  Define frac.i
  whole = us / 1000
  frac = us % 1000
  PrintDec(whole)
  Print(".")
  If frac < 100
    Print("0")
  EndIf
  If frac < 10
    Print("0")
  EndIf
  PrintDec(frac)
EndProcedure

; Pad a decimal to a width so the columns line up. The monitor has no
; field-width printing and a ragged table is a table nobody reads.
Procedure PutUsbPad(v.i, w.i)
  Define n.i
  Define t.i
  n = 1
  t = v
  While t >= 10
    t = t / 10
    n = n + 1
  Wend
  While n < w
    Print(" ")
    n = n + 1
  Wend
  PrintDec(v)
EndProcedure

Procedure UsbTiming()
  Define n.i
  Define i.i
  Define visits.i
  Define total.i
  Define bytes.i
  Define grand.i

  If HwUsbHostPresent() = 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  n = HwUsbWaitCount()
  If n <= 0
    PrintN("This board's USB stack keeps no wait ledger, so there is nothing to")
    PrintN("show. That is a property of the board, not a failure.")
    ProcedureReturn
  EndIf

  PrintN("Where the USB stack waited, counted on this board's own 54 MHz timer.")
  PrintN("Times are milliseconds. FIRST and LAST are measured from the first")
  PrintN("wait of the boot, so a row's place in the boot is as readable as its")
  PrintN("cost. A site never reached prints no row at all.")
  PrintN("")
  PrintN("Each site takes two lines: its name, then visits / total / worst /")
  PrintN("first / last. The name is a string this board owns and its length is")
  PrintN("not known here, so the numbers get the column rather than sharing one")
  PrintN("with a name that would push them out of line.")
  PrintN("")
  grand = 0
  i = 0
  While i < n
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    visits = HwUsbWaitVisits(i)
    If visits > 0
      total = HwUsbWaitTotalUs(i)
      grand = grand + total
      Print("  ")
      UartWriteStr(HwUsbWaitName(i))
      PrintNl()
      Print("      ")
      PutUsbPad(visits, 8)
      Print("  ")
      PutUsbMs(total)
      Print("   ")
      PutUsbMs(HwUsbWaitWorstUs(i))
      Print("   ")
      PutUsbMs(HwUsbWaitFirstUs(i))
      Print("   ")
      PutUsbMs(HwUsbWaitLastUs(i))
      PrintNl()
    EndIf
    i = i + 1
  Wend
  PrintN("")
  Print("Every wait above adds up to ")
  PutUsbMs(grand)
  PrintN(" ms.")

  bytes = HwUsbWaitBytes()
  If bytes > 0
    Print("The bulk row moved ")
    PrintDec(bytes)
    PrintN(" bytes, which is the storage path's whole")
    PrintN("cost with nothing of this console in it.")
  EndIf
  If HwUsbBurstIn() >= 0
    Print("Bulk burst size as configured: IN ")
    PrintDec(HwUsbBurstIn())
    Print(", OUT ")
    PrintDec(HwUsbBurstOut())
    PrintN(".")
    PrintN("  That is bMaxBurst from the SuperSpeed endpoint companion")
    PrintN("  descriptor, plus one packet per burst. A bulk OUT to storage")
    PrintN("  behind a hub is forced to 0 by this controller's errata.")
  EndIf
  PrintN("Type usb timing reset to zero every row, then run one command and")
  PrintN("read this again - that measures that command and nothing else.")
EndProcedure

Procedure UsbTimingReset()
  If HwUsbHostPresent() = 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  If HwUsbWaitCount() <= 0
    PrintN("This board's USB stack keeps no wait ledger, so there was nothing to")
    PrintN("zero. That is a property of the board, not a failure.")
    ProcedureReturn
  EndIf
  HwUsbWaitLedgerReset()
  PrintN("The USB wait ledger is zero. Everything it counts from now on belongs")
  PrintN("to what happens next; the boot's own figures are gone and only a")
  PrintN("restart brings them back.")
EndProcedure

; ======================================================================
;  usb devices - THE FLAT LISTING, FOR SOMEBODY WRITING A DRIVER
; ======================================================================
;  `usb tree` answers "what is plugged in". This answers "what does it
;  actually say about itself", which is a different question and the one
;  a driver author has. Every device, in address order, with its
;  descriptors decoded: identity, strings, the active configuration, and
;  every interface, alternate setting and endpoint under it.
;
;  ALL OF THE DECODING IS HERE, IN THE CORE, AND NONE OF IT IS IN A BOARD
;  FILE. A configuration descriptor has the same shape on every bus on
;  every board; only the way the bytes are FETCHED differs, and that is
;  the seam. A second copy of this walk written for the next board's host
;  controller would be a defect (rule 30), so there is one copy and it
;  knows nothing about any controller.
;
;  THE WALK IS BOUNDED AND IT REFUSES. A configuration descriptor is a
;  chain of variable-length records, and a device that reports a length
;  of zero - or a record that runs past the end of what was read - sends
;  a naive walk round forever or off the end of the buffer. Every step
;  goes through UsbCfgNext, which answers -1 for both, and the listing
;  stops with a sentence saying where. A malformed descriptor is exactly
;  what a driver author is most likely to be holding.
; ----------------------------------------------------------------------

; Two bytes of the DEVICE descriptor, little-endian, -1 if either is past
; its end. bcdUSB and bcdDevice are the only two-byte fields printed from
; it and both must be whole or absent. The configuration descriptor's own
; word reader is in the USB core with the walk; this one is here because
; nothing but the listing reads the device descriptor as words.
Procedure.i UsbDevWord(off.i)
  Define lo.i
  Define hi.i
  lo = UsbDescDevByte(off)
  hi = UsbDescDevByte(off + 1)
  If lo < 0 Or hi < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn lo | (hi << 8)
EndProcedure






; The port path: the root port, then the hub port under it when there is
; one. "3" is a device on root port 3; "1.4" is the fourth downstream
; port of a hub on root port 1.
Procedure PutUsbPath(i.i)
  PrintDec(HwUsbDevRootPort(i))
  If HwUsbDevRoute(i) <> 0
    Print(".")
    PrintDec(HwUsbDevRoute(i))
  EndIf
EndProcedure

Procedure PutUsbString(i.i, w.i)
  Select UsbDescStrState(w)
    Case #USB_STR_NONE
      Print("none")
    Case #USB_STR_NOT_READ
      Print("not read")
    Default
      UartWriteStr(UsbDescStr(w))
  EndSelect
EndProcedure

; bcdUSB / bcdDevice, which are binary-coded decimal: $0210 is 2.10.
Procedure PutUsbBcd(v.i)
  PrintDec((v >> 8) & $FF)
  Print(".")
  PutHexN(v & $FF, 2)
EndProcedure

; Every endpoint of one interface, from `off` to the next interface or
; the end. Answers the offset it stopped at, or -1 if the chain broke.
Procedure.i UsbPutEndpoints(off.i)
  Define typ.i
  Define len.i
  Define addr.i
  Define attr.i
  Define mps.i
  Define ivl.i
  Define nxt.i

  While off > 0
    len = UsbCfgByte(off)
    typ = UsbCfgByte(off + 1)
    If len < 0 Or typ < 0
      ProcedureReturn -1
    EndIf
    ; An interface descriptor ends this interface's endpoint list.
    If typ = 4
      ProcedureReturn off
    EndIf
    If typ = 5
      addr = UsbCfgByte(off + 2)
      attr = UsbCfgByte(off + 3)
      mps  = UsbCfgWord(off + 4)
      ivl  = UsbCfgByte(off + 6)
      If addr < 0 Or attr < 0 Or mps < 0 Or ivl < 0
        ProcedureReturn -1
      EndIf
      Print("      endpoint ")
      PutHexN(addr, 2)
      If (addr & $80) <> 0
        Print(" IN   ")
      Else
        Print(" OUT  ")
      EndIf
      UartWriteStr(UsbEpTypeText(attr))
      Print("  wMaxPacketSize ")
      PrintDec(mps & $07FF)
      Print("  bInterval ")
      PrintDec(ivl)
      PrintNl()
    EndIf
    If typ = $30
      ; SUPERSPEED ENDPOINT COMPANION - USB 3.2 section 9.6.7. It follows
      ; the endpoint it describes, and bMaxBurst is packets-minus-one.
      addr = UsbCfgByte(off + 2)
      If addr < 0
        ProcedureReturn -1
      EndIf
      Print("        SuperSpeed companion: bMaxBurst ")
      PrintDec(addr & $1F)
      Print(" (")
      PrintDec((addr & $1F) + 1)
      PrintN(" packets per burst)")
    EndIf
    nxt = UsbCfgNext(off)
    If nxt < 0
      ProcedureReturn -1
    EndIf
    off = nxt
  Wend
  ProcedureReturn 0
EndProcedure

; One device, decoded. Returns 1, or 0 when the descriptors would not
; load - and the caller says so rather than printing a blank block.
Procedure.i UsbPutDevice(i.i)
  Define v.i
  Define cls.i
  Define sub.i
  Define proto.i
  Define off.i
  Define nxt.i
  Define ifn.i
  Define alt.i
  Define attr.i

  Print("device ")
  PrintDec(HwUsbDevAddress(i))
  Print("  slot ")
  PrintDec(HwUsbDevSlot(i))
  Print("  port ")
  PutUsbPath(i)
  Print("  ")
  PutUsbSpeed(HwUsbDevSpeed(i))
  If HwUsbDevParent(i) = 0
    PrintN("  on a root port")
  Else
    Print("  behind the hub in slot ")
    PrintDec(HwUsbDevParent(i))
    PrintNl()
  EndIf

  If HwUsbDescLoad(i) = 0
    PrintN("  its descriptors could not be read, so nothing below them is")
    PrintN("  shown. The device is enumerated - it answered enough to be")
    PrintN("  addressed - but it did not answer this. Try usb devices again;")
    PrintN("  if it keeps refusing, reseat it.")
    ProcedureReturn 0
  EndIf

  Print("  id        ")
  PutHexN(HwUsbDevVid(i) & $FFFF, 4)
  Print(":")
  PutHexN(HwUsbDevPid(i) & $FFFF, 4)
  Print("   bcdDevice ")
  PutUsbBcd(UsbDevWord(12))
  Print("   bcdUSB ")
  PutUsbBcd(UsbDevWord(2))
  PrintNl()

  cls   = UsbDescDevByte(4)
  sub   = UsbDescDevByte(5)
  proto = UsbDescDevByte(6)
  Print("  class     ")
  PutHexN(cls, 2)
  Print("/")
  PutHexN(sub, 2)
  Print("/")
  PutHexN(proto, 2)
  Print("  ")
  UartWriteStr(UsbClassText(cls, sub, proto))
  PrintNl()
  Print("  ep0       bMaxPacketSize0 ")
  PrintDec(UsbDescDevByte(7))
  Print("   configurations ")
  PrintDec(UsbDescDevByte(17))
  PrintNl()

  Print("  maker     ")
  PutUsbString(i, #USB_STR_MANUFACTURER)
  PrintNl()
  Print("  product   ")
  PutUsbString(i, #USB_STR_PRODUCT)
  PrintNl()
  Print("  serial    ")
  PutUsbString(i, #USB_STR_SERIAL)
  PrintNl()

  If UsbDescCfgHeld() < 9
    PrintN("  its configuration descriptor did not come back, so no interface")
    PrintN("  is shown. That is a refusal by the device, not an empty device.")
    ProcedureReturn 1
  EndIf

  attr = UsbCfgByte(7)
  Print("  config    value ")
  PrintDec(UsbCfgByte(5))
  Print("  ")
  If (attr & $40) <> 0
    Print("self powered")
  Else
    Print("bus powered")
  EndIf
  If (attr & $20) <> 0
    Print(", remote wakeup")
  EndIf
  Print(", up to ")
  ; bMaxPower is in 2 mA units on USB 2.0 and 8 mA on SuperSpeed - USB 3.2
  ; section 9.6.3. Getting this wrong by four times on a bus-powered
  ; device is the difference between "fine" and "over budget".
  If HwUsbDevSpeed(i) = #HW_USB_SPEED_SUPER
    PrintDec(UsbCfgByte(8) * 8)
  Else
    PrintDec(UsbCfgByte(8) * 2)
  EndIf
  Print(" mA, ")
  PrintDec(UsbCfgWord(2))
  Print(" descriptor bytes")
  If UsbDescCfgHeld() < UsbDescCfgWant()
    Print(" of which ")
    PrintDec(UsbDescCfgHeld())
    Print(" were read - THE REST IS NOT SHOWN")
  EndIf
  PrintNl()

  ; ---- the interfaces ------------------------------------------------
  off = UsbCfgNext(0)
  While off > 0
    If OutBreak() <> 0
      ProcedureReturn 1
    EndIf
    If UsbCfgByte(off + 1) = 4
      ifn   = UsbCfgByte(off + 2)
      alt   = UsbCfgByte(off + 3)
      cls   = UsbCfgByte(off + 5)
      sub   = UsbCfgByte(off + 6)
      proto = UsbCfgByte(off + 7)
      If ifn < 0 Or alt < 0 Or cls < 0 Or sub < 0 Or proto < 0
        PrintN("  the descriptor chain stops here - an interface record runs past")
        PrintN("  the end of what the device sent. Nothing after it is shown.")
        ProcedureReturn 1
      EndIf
      Print("    interface ")
      PrintDec(ifn)
      Print(" alt ")
      PrintDec(alt)
      Print("  ")
      PutHexN(cls, 2)
      Print("/")
      PutHexN(sub, 2)
      Print("/")
      PutHexN(proto, 2)
      Print("  ")
      UartWriteStr(UsbClassText(cls, sub, proto))
      Print("  ")
      UartWriteStr(HwUsbDevIfaceDriver(i, ifn))
      PrintNl()
      nxt = UsbCfgNext(off)
      If nxt < 0
        PrintN("  the descriptor chain is malformed after this interface - a")
        PrintN("  record gave a length of zero or ran past the end. Stopped.")
        ProcedureReturn 1
      EndIf
      If nxt = 0
        ProcedureReturn 1
      EndIf
      off = UsbPutEndpoints(nxt)
      If off < 0
        PrintN("  the descriptor chain is malformed inside this interface's")
        PrintN("  endpoints - a record gave a length of zero or ran past the")
        PrintN("  end of what was read. Stopped.")
        ProcedureReturn 1
      EndIf
    Else
      nxt = UsbCfgNext(off)
      If nxt < 0
        PrintN("  the descriptor chain is malformed - a record gave a length of")
        PrintN("  zero or ran past the end of what was read. Stopped.")
        ProcedureReturn 1
      EndIf
      off = nxt
    EndIf
  Wend
  ProcedureReturn 1
EndProcedure

Procedure UsbDevices()
  Define n.i
  Define i.i

  n = HwUsbTree()
  If n < 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  If n = 0
    PrintN("No USB device is addressed on this board, so there is nothing to")
    PrintN("list. Type usb tree for the ports themselves - a device on a port")
    PrintN("that did not answer enumeration is not a device yet.")
    ProcedureReturn
  EndIf
  PrintN("Every USB device on this board, as its own descriptors describe it.")
  PrintN("Type usb devices <n> for one device and its raw descriptor bytes.")
  PrintNl()
  i = 0
  While i < n
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    UsbPutDevice(i)
    PrintNl()
    i = i + 1
  Wend
EndProcedure

; One device, plus the bytes themselves. What a driver author needs when
; the decoded view is not enough - a vendor descriptor this monitor does
; not name, a field in a place the specification does not put it, a
; device that is lying about its own lengths.
Procedure UsbDeviceRaw(n.i)
  Define count.i
  Define i.i
  Define v.i
  Define line.i

  count = HwUsbTree()
  If count < 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  If n < 0 Or n >= count
    Print("!! there is no device ")
    PrintDec(n)
    PrintN(" on this board, so nothing was read. Devices are")
    Print("   numbered 0 to ")
    PrintDec(count - 1)
    PrintN(" in the order usb devices lists them.")
    ProcedureReturn
  EndIf
  If UsbPutDevice(n) = 0
    ProcedureReturn
  EndIf
  PrintNl()
  PrintN("  device descriptor, raw:")
  Print("   ")
  i = 0
  line = 0
  While i < UsbDescDevLen()
    Print(" ")
    PutHexN(UsbDescDevByte(i), 2)
    i = i + 1
    line = line + 1
    If line = 16 And i < UsbDescDevLen()
      PrintNl()
      Print("   ")
      line = 0
    EndIf
  Wend
  PrintNl()
  Print("  configuration descriptor, raw, ")
  PrintDec(UsbDescCfgHeld())
  Print(" of ")
  PrintDec(UsbDescCfgWant())
  PrintN(" bytes:")
  Print("   ")
  i = 0
  line = 0
  While i < UsbDescCfgHeld()
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    Print(" ")
    PutHexN(UsbCfgByte(i), 2)
    i = i + 1
    line = line + 1
    If line = 16 And i < UsbDescCfgHeld()
      PrintNl()
      Print("   ")
      line = 0
    EndIf
  Wend
  PrintNl()
EndProcedure

Procedure UsbStorageNotReady()
  PrintN("!! there is no USB mass-storage device up on this board. A stick may be")
  PrintN("   plugged in but not have enumerated as mass storage, or none is")
  PrintN("   plugged in at all.")
  Print("   The storage layer said: ")
  UartWriteStr(HwUsbStorageError())
  PrintNl()
EndProcedure

Procedure UsbStorage()
  Define bc.i
  Define bs.i
  If HwUsbEnumerate() = 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  If HwUsbStorageReady() = 0
    UsbStorageNotReady()
    ProcedureReturn
  EndIf
  bc = HwUsbStorageBlockCount()
  bs = HwUsbStorageBlockSize()
  PrintN("USB mass storage:")
  Print("  device    ")
  UartWriteStr(HwUsbStorageVendor())
  Print(" ")
  UartWriteStr(HwUsbStorageProduct())
  PrintNl()
  Print("  medium    ")
  PrintDec(bc)
  Print(" blocks of ")
  PrintDec(bs)
  PrintN(" bytes")
  Print("  capacity  ")
  ; blocks * 512 / 2^30, i.e. (blocks / 2048) / 1024. The stack refuses a
  ; medium that is not 512-byte blocks, so this stays exact.
  PrintDec((bc / 2048) / 1024)
  PrintN(" GB")
  Print("  transport Bulk-Only, interface protocol ")
  PutHexN(HwUsbStorageProtocol() & $FF, 2)
  Print(", descriptor ")
  PrintDec(HwUsbStorageConfigLen())
  PrintN(" bytes")
  If HwUsbStorageUas() <> 0
    PrintN("  THIS DEVICE ALSO ADVERTISES USB ATTACHED SCSI and is being driven")
    PrintN("  Bulk-Only anyway, because that is the transport this monitor has.")
    PrintN("  UAS queues several commands at once instead of one round trip per")
    PrintN("  command, so the stick is not being asked for everything it can do.")
  Else
    PrintN("  It advertises no other transport, so Bulk-Only is all it can do.")
  EndIf
  Print("  burst     ")
  If HwUsbBurstIn() < 0
    PrintN("no bulk endpoints are configured")
  Else
    Print("IN ")
    PrintDec(HwUsbBurstIn())
    Print(", OUT ")
    PrintDec(HwUsbBurstOut())
    PrintN(" (bMaxBurst; a burst is that many packets plus one)")
  EndIf
  PrintN("  Read a raw block with: usb read <block> <address> [count], all hex.")
EndProcedure

Procedure UsbRead()
  Define blk.i
  Define addr.i
  Define count.i
  Define bs.i
  Define lo.i
  Define hi.i
  Define i.i
  Define n.i

  If HwUsbReadAvailable() = 0
    PrintN("!! a raw block read is not exposed on this board's USB stack, so usb")
    PrintN("   read can do nothing here. usb storage still reports the device.")
    ProcedureReturn
  EndIf
  If HwUsbEnumerate() = 0
    PutUsbNoHost()
    ProcedureReturn
  EndIf
  If HwUsbStorageReady() = 0
    UsbStorageNotReady()
    ProcedureReturn
  EndIf

  blk = ParseHex()
  If gParseOk = 0
    PrintN("!! usb read needs a block number in hexadecimal, then a destination")
    PrintN("   address, then an optional count: usb read <block> <address> [count].")
    ProcedureReturn
  EndIf
  addr = ParseHex()
  If gParseOk = 0
    PrintN("!! usb read needs a destination address in hexadecimal after the block")
    PrintN("   number: usb read <block> <address> [count].")
    ProcedureReturn
  EndIf
  SkipSpace()
  If gLine[gPos] = 0
    count = 1
  Else
    count = ParseHex()
    If gParseOk = 0
      PrintN("!! the count after usb read <block> <address> must be hexadecimal too,")
      PrintN("   or left out to read one block.")
      ProcedureReturn
    EndIf
  EndIf
  If count <= 0
    PrintN("!! a count of zero reads nothing, so nothing was done.")
    ProcedureReturn
  EndIf
  If count > #USB_READ_MAX
    Print("!! usb read reads at most ")
    PrintDec(#USB_READ_MAX)
    PrintN(" blocks at once, so a mistyped count cannot")
    PrintN("   ask for the whole disk. Ask for fewer.")
    ProcedureReturn
  EndIf

  bs = HwUsbStorageBlockSize()
  lo = addr
  hi = addr + count * bs - 1

  ; SAME RANGE DISCIPLINE AS THE LOADERS. A raw block read lands in memory
  ; exactly like a file load, so the same two checks apply: inside a
  ; payload window, and clear of the monitor's own region.
  If InPayload(lo, hi) = 0
    PrintN("!! that destination is not inside a payload window, so usb read refused")
    PrintN("   to write there. A raw block read lands in memory just like a file")
    PrintN("   load, and the same windows apply:")
    PutWindows()
    ProcedureReturn
  EndIf
  If HitsMonitor(lo, hi) <> 0
    Print("!! that destination runs into the monitor's own region (")
    PutAddr(gMonHitLo)
    Print(" to ")
    PutAddr(gMonHitHi)
    PrintN("),")
    PrintN("   so usb read refused rather than overwrite the program that is")
    PrintN("   running. Pick an address in a payload window.")
    ProcedureReturn
  EndIf
  ; And the board's own answer about the destination, the third of the
  ; three and the only one that speaks to whether the memory can take the
  ; write at all rather than to whether it should.
  If AddrAllowed(lo, hi, 1, "usb read", "read") = 0
    ProcedureReturn
  EndIf
  If blk + count > HwUsbStorageBlockCount()
    Print("!! this medium has ")
    PrintDec(HwUsbStorageBlockCount())
    PrintN(" blocks, and that block-and-count runs off")
    PrintN("   the end of it, so nothing was read.")
    ProcedureReturn
  EndIf

  ; A RUN AT A TIME, #USB_READ_RUN blocks per call, with a break check
  ; between runs so a stopped read never leaves a half-written run behind
  ; - the DumpMem discipline. Until 2026-09-17 this was one block per
  ; call, and the board's driver answered each with its own device
  ; command: the instrument measured the command overhead, not the
  ; medium (forum 895).
  i = 0
  While i < count
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    n = count - i
    If n > #USB_READ_RUN
      n = #USB_READ_RUN
    EndIf
    If HwUsbReadBlocks(blk + i, n, addr + i * bs) = 0
      Print("!! reading blocks ")
      PutAddr(blk + i)
      Print(" to ")
      PutAddr(blk + i + n - 1)
      PrintN(" off the USB device failed, so the read")
      PrintN("   stopped there. What is in memory from that run on is not the")
      PrintN("   medium's; below it is what was read. The storage layer said: ")
      Print("   ")
      UartWriteStr(HwUsbStorageError())
      PrintNl()
      ProcedureReturn
    EndIf
    i = i + n
  Wend

  Print("Read ")
  PrintDec(count)
  Print(" block")
  If count <> 1
    Print("s")
  EndIf
  Print(" of ")
  PrintDec(bs)
  Print(" bytes from block ")
  PutAddr(blk)
  Print(" into ")
  PutAddr(addr)
  Print(" to ")
  PutAddr(hi)
  PrintN(".")
  PrintN("Use memory <address> <count> to look at it.")
EndProcedure

Procedure CmdUsb()
  ; THE GATE, FIRST. On a board without #CAP_USB this prints the honest
  ; "not available on this board" sentence and returns 0, and this command
  ; returns cleanly having touched no seam. The reason is generic to the
  ; hardware class, not to any chip, so this line is the same for every
  ; board.
  If RequireCap(#CAP_USB, "usb", "this board has no USB host controller Anvil can reach") = 0
    ProcedureReturn
  EndIf

  SkipSpace()
  If gLine[gPos] = 0
    ; No subcommand: the overview, which is the safe default.
    UsbInfo()
    ProcedureReturn
  EndIf

  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If WordIs("info") <> 0
    UsbInfo()
  ElseIf WordIs("tree") <> 0
    UsbTree()
  ElseIf WordIs("link") <> 0
    UsbLink()
  ElseIf WordIs("storage") <> 0
    UsbStorage()
  ElseIf WordIs("read") <> 0
    UsbRead()
  ElseIf WordIs("devices") <> 0 Or WordIs("device") <> 0
    SkipSpace()
    If gLine[gPos] = 0
      UsbDevices()
    Else
      ; The device number is DECIMAL, not hexadecimal like an address:
      ; it is an index into a list this command printed, not a place in
      ; memory, and a list of three devices numbered 0, 1, 2 has no
      ; business being typed in hex.
      UsbDeviceRaw(ParseDec())
      If gParseOk = 0
        PrintN("!! usb devices takes a device number in decimal, as the listing")
        PrintN("   prints it, and that was not one - so nothing was read.")
      EndIf
    EndIf
  ElseIf WordIs("timing") <> 0 Or WordIs("times") <> 0
    SkipSpace()
    gWordAt = gPos
    SkipWord()
    gWordLen = gPos - gWordAt
    If gWordLen > 0 And WordIs("reset") <> 0
      UsbTimingReset()
    ElseIf gWordLen > 0
      PrintN("!! usb timing takes nothing, or the single word reset, and that was")
      PrintN("   neither - so nothing was done and no row was zeroed.")
    Else
      UsbTiming()
    EndIf
  Else
    PrintN("!! usb takes info, tree, link, devices, storage, timing or read, and")
    PrintN("   nothing else was recognised, so nothing was done. usb devices lists")
    PrintN("   every device as its own descriptors describe it, and usb devices <n>")
    PrintN("   adds that one device's raw bytes.")
    PrintN("   usb on its own is the same as usb info. usb link prints the raw registers of the link the")
    PrintN("   controller sits on, which is what usb tree summarises in one")
    PrintN("   sentence. usb timing prints where the USB stack spent its time, on")
    PrintN("   the board's own clock, and usb timing reset zeroes it so that one")
    PrintN("   command can be measured on its own.")
    PrintN("   usb read <block> <address> [count] pulls raw blocks, all hex.")
  EndIf
EndProcedure
