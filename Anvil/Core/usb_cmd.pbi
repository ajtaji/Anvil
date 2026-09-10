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

  i = 0
  While i < count
    ; One break check per block, at the top, so a stopped read never
    ; leaves a half-written block behind - the DumpMem discipline.
    If OutBreak() <> 0
      ProcedureReturn
    EndIf
    If HwUsbReadBlock(blk + i, addr + i * bs) = 0
      Print("!! reading block ")
      PutAddr(blk + i)
      PrintN(" off the USB device failed, so the read stopped")
      PrintN("   there. What is in memory below that block is whatever was read up")
      Print("   to it. The storage layer said: ")
      UartWriteStr(HwUsbStorageError())
      PrintNl()
      ProcedureReturn
    EndIf
    i = i + 1
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
  ElseIf WordIs("storage") <> 0
    UsbStorage()
  ElseIf WordIs("read") <> 0
    UsbRead()
  Else
    PrintN("!! usb takes info, tree, storage, or read, and nothing else was")
    PrintN("   recognised, so nothing was done. usb on its own is the same as usb")
    PrintN("   info. usb read <block> <address> [count] pulls raw blocks, all hex.")
  EndIf
EndProcedure
