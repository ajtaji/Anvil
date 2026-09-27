; ======================================================================
;  hci.pbi - Bluetooth HCI over the UART H4 transport, and the Broadcom
;  (CYW43455) bring-up. SHARED AND CHIP-FREE: it names no UART and no
;  register. The board supplies the byte pipe as the HwBt* seam (Anvil/Hal/hal.pbi) -
;
;    HwBtOpen()        mux the pins, power the controller (BT_REG_ON),
;                      open the UART at 115200 8N1 with RTS/CTS flow
;                      control. 1, or 0 with HwBtWhy().
;    HwBtClose()       stop the UART, controller left powered
;    HwBtPut(b)        one byte out: 1, or 0 if the transmitter never
;                      drained (bounded)
;    HwBtGet()         one byte in, or -1 if none is waiting (never blocks)
;    HwBtSetBaud(baud) re-program the host side: 1, or 0 if unreachable
;    HwBtWhy()         ADDRESS of a sentence: why HwBtOpen said no
;
;  - RaspberryPi4/Board/hw_bt.pi4 on the Pi 4 and Pi 5, over
;  RaspberryPi4/Lib/bt_uart.pi4 (Pi 4, PL011 UART0 on GPIO 30-33) or
;  RaspberryPi4/Lib/bt_uart_7271.pi4 (Pi 5, BCM2712 uarta, a
;  brcm,bcm7271-uart) - and Ticks()/TickHz() (timer.pi4) for time.
;
;  ---- WHERE THE PROTOCOL COMES FROM (pinned Linux 7e030b60792d) --------
;    H4 framing: a command is 01, opcode (LITTLE-ENDIAN), plen, params; an
;      event is 04, code, plen, params. Command Complete $0E = ncmd,
;      opcode, status, return params; Command Status $0F = status, ncmd,
;      opcode; Hardware Error $10 = the controller lost sync.
;    drivers/bluetooth/btbcm.c
;      btbcm_patchram (217-275): Download_Minidriver $FC2E, THEN 50 ms,
;        then the .hcd file sent verbatim as HCI commands - each record
;        is opcode (LE, 2), plen (1), params - each answered by a Command
;        Complete; a short record is "Patch is corrupted"; THEN 250 ms
;        "after Launch Ram completes".
;      btbcm_reset (277-297): HCI_Reset, then 100 ms.
;      BDADDR_BCM4345C0 (33): the unpatched part answers Read_BD_ADDR with
;        ac 1f 00 c0 45 43 - 43:45:C0:00:1F:AC, a factory constant, not an
;        address. HciBdAddrIsPlaceholder() says so rather than print it.
;    drivers/bluetooth/hci_bcm.c
;      bcm_set_baudrate (178-221): Update_UART_Baud_Rate $FC18 with a zero
;        u16 and the rate as a LE u32; above 3 Mbaud first $FC45 (not
;        needed: both boards' max-speed is 3000000). The HOST changes its
;        own rate only after the controller's Command Complete, which
;        arrives at the OLD rate (bcm_setup 614-626).
;      bcm_setup (590-640): the operational rate is set only after the
;        firmware load - "if (!fw_load_done) return 0" - so this file
;        refuses a baud switch before the patch (#HCI_ERR_NEEDS_PATCH).
;      bcm_gpio_set_power (249-310): power on, then 100-120 ms before the
;        first byte.
;    The Bluetooth Core spec's Inquiry (OGF 1 OCF 1, $0401): LAP 9E8B33
;      (GIAC), length in 1.28 s units, 0 = unlimited responses; answered
;      by Command Status, then Inquiry Result ($02), Inquiry Result with
;      RSSI ($22) or Extended Inquiry Result ($2F), then Inquiry Complete
;      ($01). $02 and $22 lay their parameters out FIELD BY FIELD (all
;      the addresses, then all the scan modes, ...), not device by device.
;
;  ---- THE FIRMWARE (.hcd) --------------------------------------------
;  The CYW43455's Bluetooth patch is a separate file from its Wi-Fi image
;  (Firmware/CYW43455/ carries only the WLAN pair, loaded from the boot
;  medium as BRCMFW.BIN / BRCMCLM.BLB). It is NOT in this tree. Raspberry
;  Pi OS ships it as BCM4345C0.hcd (RPi-Distro/bluez-firmware,
;  broadcom/) under the same Cypress licence as the WLAN image; vendoring
;  it is the owner's decision. So this file takes the patch as a buffer
;  (HciLoadPatch(*hcd, n)); the board reads it from the boot medium.
;  With no patch the controller runs its ROM: Reset, version and inquiry
;  work, the address is the placeholder, and the baud switch is refused.
;
;  DESK PROOF ONLY (tools/a64/hci_bt_check.py). SILICON OWED.
; ======================================================================

EnableExplicit

#HCI_CMD_PKT = $01
#HCI_EVT_PKT = $04

#HCI_OP_RESET          = $0C03
#HCI_OP_READ_LOCAL_VER = $1001
#HCI_OP_READ_BD_ADDR   = $1009
#HCI_OP_INQUIRY        = $0401
#HCI_OP_BCM_MINIDRIVER = $FC2E
#HCI_OP_BCM_LAUNCH_RAM = $FC4E
#HCI_OP_BCM_SET_BAUD   = $FC18

#HCI_EV_INQUIRY_COMPLETE = $01
#HCI_EV_INQUIRY_RESULT   = $02
#HCI_EV_CMD_COMPLETE     = $0E
#HCI_EV_CMD_STATUS       = $0F
#HCI_EV_HW_ERROR         = $10
#HCI_EV_INQUIRY_RSSI     = $22
#HCI_EV_INQUIRY_EXT      = $2F

#HCI_GIAC = $9E8B33

#HCI_OK               = 0
#HCI_ERR_TRANSPORT    = 1     ; HwBtOpen said no (HwBtWhy has the reason)
#HCI_ERR_TX           = 2     ; a byte could not be sent
#HCI_ERR_TIMEOUT      = 3     ; no complete answer before the deadline
#HCI_ERR_INDICATOR    = 4     ; a packet that was not an event
#HCI_ERR_STATUS       = 5     ; the controller answered with a failure
#HCI_ERR_HWERR        = 6     ; HCI_Hardware_Error: the controller lost sync
#HCI_ERR_PATCH        = 7     ; the .hcd is corrupted (a short record)
#HCI_ERR_NEEDS_PATCH  = 8     ; baud switch before the firmware patch
#HCI_ERR_BAUD         = 9     ; the host side cannot make that rate
#HCI_ERR_NOT_OPEN     = 10

#HCI_CMD_TIMEOUT_MS = 2000
#HCI_SPIN_MAX       = 50000000
#HCI_MAX_DEVICES    = 16

Global hci_err.i
Global hci_status.i            ; the controller's status byte, last command
Global hci_open.i
Global hci_patched.i
Global hci_baud.i
Global Dim hci_evt.a[260]      ; the last event's parameters
Global hci_evtCode.i
Global hci_evtLen.i
Global Dim hci_ret.a[260]      ; Command Complete's return parameters
Global hci_retLen.i
Global hci_hciVer.i
Global hci_hciRev.i
Global hci_lmpVer.i
Global hci_manuf.i
Global hci_lmpSub.i
Global Dim hci_bd.a[6]
Global hci_haveBd.i
Global Dim hci_dev.a[96]
Global Dim hci_devCod.l[16]
Global Dim hci_devRssi.l[16]
Global hci_devN.i
Global hci_resultsSeen.i
Global Dim hci_par.a[8]         ; a command's parameters, built here

Procedure.i HciError()
  ProcedureReturn hci_err
EndProcedure

Procedure.i HciStatus()
  ProcedureReturn hci_status
EndProcedure

Procedure.i HciWhy()
  Select hci_err
    Case #HCI_OK : ProcedureReturn "nothing has gone wrong"
    Case #HCI_ERR_TRANSPORT : ProcedureReturn HwBtWhy()
    Case #HCI_ERR_TX : ProcedureReturn "a byte could not be sent: the Bluetooth controller never cleared its flow control (CTS), so check that it is powered"
    Case #HCI_ERR_TIMEOUT : ProcedureReturn "the Bluetooth controller did not answer in time"
    Case #HCI_ERR_INDICATOR : ProcedureReturn "the controller sent a packet that is not an HCI event, so the byte stream is out of step; an HCI_Reset resynchronises it"
    Case #HCI_ERR_STATUS : ProcedureReturn "the controller answered the command with a failure status"
    Case #HCI_ERR_HWERR : ProcedureReturn "the controller reported a hardware error: it lost synchronisation with this host"
    Case #HCI_ERR_PATCH : ProcedureReturn "the firmware patch (.hcd) is corrupted: a record runs past the end of the file"
    Case #HCI_ERR_NEEDS_PATCH : ProcedureReturn "the baud rate can only be raised after the firmware patch is loaded, as Linux does"
    Case #HCI_ERR_BAUD : ProcedureReturn "this board's UART cannot make that baud rate"
    Case #HCI_ERR_NOT_OPEN : ProcedureReturn "Bluetooth has not been brought up"
  EndSelect
  ProcedureReturn "an unknown Bluetooth error"
EndProcedure

Procedure.i HciDeadline(ms.i)
  Define hz.i = TickHz()
  If hz <= 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Ticks() + (hz / 1000) * ms
EndProcedure

Procedure HciDelayMs(ms.i)
  Define hz.i = TickHz()
  Define t.i
  If hz <= 0
    ProcedureReturn
  EndIf
  t = Ticks() + (hz / 1000) * ms
  While Ticks() < t
  Wend
EndProcedure

; One H4 command. The opcode goes out LOW BYTE FIRST.
Procedure.i HciSend(op.i, *p, plen.i)
  Define i.i
  If HwBtPut(#HCI_CMD_PKT) = 0 Or HwBtPut(op & $FF) = 0 Or HwBtPut((op >> 8) & $FF) = 0 Or HwBtPut(plen & $FF) = 0
    hci_err = #HCI_ERR_TX
    ProcedureReturn 0
  EndIf
  For i = 0 To plen - 1
    If HwBtPut(PeekA(*p + i) & $FF) = 0
      hci_err = #HCI_ERR_TX
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

; One byte, waiting until the deadline. -1 on timeout.
Procedure.i HciByte(deadline.i)
  Define b.i
  Define spins.i = 0
  Repeat
    b = HwBtGet()
    If b >= 0 : ProcedureReturn b & $FF : EndIf
    spins + 1
    If spins > #HCI_SPIN_MAX : ProcedureReturn -1 : EndIf
    If deadline > 0 And Ticks() > deadline : ProcedureReturn -1 : EndIf
  ForEver
EndProcedure

; One whole event into hci_evt/hci_evtCode/hci_evtLen. 1, or 0 with hci_err.
Procedure.i HciReadEvent(deadline.i)
  Define b.i, i.i
  b = HciByte(deadline)
  If b < 0 : hci_err = #HCI_ERR_TIMEOUT : ProcedureReturn 0 : EndIf
  If b <> #HCI_EVT_PKT : hci_err = #HCI_ERR_INDICATOR : ProcedureReturn 0 : EndIf
  hci_evtCode = HciByte(deadline)
  hci_evtLen = HciByte(deadline)
  If hci_evtCode < 0 Or hci_evtLen < 0 : hci_err = #HCI_ERR_TIMEOUT : ProcedureReturn 0 : EndIf
  For i = 0 To hci_evtLen - 1
    b = HciByte(deadline)
    If b < 0 : hci_err = #HCI_ERR_TIMEOUT : ProcedureReturn 0 : EndIf
    hci_evt[i] = b
  Next
  If hci_evtCode = #HCI_EV_HW_ERROR : hci_err = #HCI_ERR_HWERR : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; Send op and wait for ITS Command Complete. A credit-only Command
; Complete (opcode 0) and any unrelated event are skipped, bounded by the
; deadline. The return parameters after the status land in hci_ret[].
Procedure.i HciCommand(op.i, *p, plen.i)
  Define deadline.i, i.i
  hci_err = #HCI_OK
  If HciSend(op, *p, plen) = 0 : ProcedureReturn 0 : EndIf
  deadline = HciDeadline(#HCI_CMD_TIMEOUT_MS)
  Repeat
    If HciReadEvent(deadline) = 0 : ProcedureReturn 0 : EndIf
    If hci_evtCode = #HCI_EV_CMD_COMPLETE And hci_evtLen >= 4
      If (hci_evt[1] | (hci_evt[2] << 8)) = op
        hci_status = hci_evt[3]
        hci_retLen = hci_evtLen - 4
        For i = 0 To hci_retLen - 1 : hci_ret[i] = hci_evt[4 + i] : Next
        If hci_status <> 0 : hci_err = #HCI_ERR_STATUS : ProcedureReturn 0 : EndIf
        ProcedureReturn 1
      EndIf
    ElseIf hci_evtCode = #HCI_EV_CMD_STATUS And hci_evtLen >= 4
      If (hci_evt[2] | (hci_evt[3] << 8)) = op And hci_evt[0] <> 0
        hci_status = hci_evt[0]
        hci_err = #HCI_ERR_STATUS
        ProcedureReturn 0
      EndIf
    EndIf
  ForEver
EndProcedure

Procedure.i HciReset()
  If HciCommand(#HCI_OP_RESET, 0, 0) = 0 : ProcedureReturn 0 : EndIf
  HciDelayMs(100)                     ; btbcm_reset
  ProcedureReturn 1
EndProcedure

Procedure.i HciReadLocalVersion()
  If HciCommand(#HCI_OP_READ_LOCAL_VER, 0, 0) = 0 : ProcedureReturn 0 : EndIf
  If hci_retLen < 8 : hci_err = #HCI_ERR_STATUS : ProcedureReturn 0 : EndIf
  hci_hciVer = hci_ret[0]
  hci_hciRev = hci_ret[1] | (hci_ret[2] << 8)
  hci_lmpVer = hci_ret[3]
  hci_manuf  = hci_ret[4] | (hci_ret[5] << 8)
  hci_lmpSub = hci_ret[6] | (hci_ret[7] << 8)
  ProcedureReturn 1
EndProcedure

Procedure.i HciHciVer() : ProcedureReturn hci_hciVer : EndProcedure
Procedure.i HciHciRev() : ProcedureReturn hci_hciRev : EndProcedure
Procedure.i HciLmpVer() : ProcedureReturn hci_lmpVer : EndProcedure
Procedure.i HciManufacturer() : ProcedureReturn hci_manuf : EndProcedure
Procedure.i HciLmpSubver() : ProcedureReturn hci_lmpSub : EndProcedure

Procedure.i HciReadBdAddr()
  Define i.i
  hci_haveBd = 0
  If HciCommand(#HCI_OP_READ_BD_ADDR, 0, 0) = 0 : ProcedureReturn 0 : EndIf
  If hci_retLen < 6 : hci_err = #HCI_ERR_STATUS : ProcedureReturn 0 : EndIf
  For i = 0 To 5 : hci_bd[i] = hci_ret[i] : Next
  hci_haveBd = 1
  ProcedureReturn 1
EndProcedure

; Byte i of the address, i = 0 the MOST significant (as printed).
Procedure.i HciBdAddrByte(i.i)
  If hci_haveBd = 0 Or i < 0 Or i > 5 : ProcedureReturn -1 : EndIf
  ProcedureReturn hci_bd[5 - i]
EndProcedure

; 1 if the address is btbcm.c's BDADDR_BCM4345C0 factory constant.
Procedure.i HciBdAddrIsPlaceholder()
  If hci_haveBd = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(hci_bd[0] = $AC And hci_bd[1] = $1F And hci_bd[2] = $00 And hci_bd[3] = $C0 And hci_bd[4] = $45 And hci_bd[5] = $43)
EndProcedure

; ----------------------------------------------------------------------
;  HciLoadPatch(*hcd, n) - btbcm_patchram, record for record.
; ----------------------------------------------------------------------
Procedure.i HciLoadPatch(*hcd, n.i)
  Define pos.i, op.i, plen.i
  hci_err = #HCI_OK
  If hci_open = 0 : hci_err = #HCI_ERR_NOT_OPEN : ProcedureReturn 0 : EndIf
  If HciCommand(#HCI_OP_BCM_MINIDRIVER, 0, 0) = 0 : ProcedureReturn 0 : EndIf
  HciDelayMs(50)
  pos = 0
  While n - pos >= 3
    op = (PeekA(*hcd + pos) & $FF) | ((PeekA(*hcd + pos + 1) & $FF) << 8)
    plen = PeekA(*hcd + pos + 2) & $FF
    pos + 3
    If n - pos < plen : hci_err = #HCI_ERR_PATCH : ProcedureReturn 0 : EndIf
    If HciCommand(op, *hcd + pos, plen) = 0 : ProcedureReturn 0 : EndIf
    pos + plen
  Wend
  HciDelayMs(250)
  ; btbcm_finalize: the patched firmware starts from a reset.
  If HciReset() = 0 : ProcedureReturn 0 : EndIf
  hci_patched = 1
  ProcedureReturn 1
EndProcedure

Procedure.i HciPatched()
  ProcedureReturn hci_patched
EndProcedure

; ----------------------------------------------------------------------
;  HciSetBaud(baud) - bcm_set_baudrate, then the host. Only after a patch.
; ----------------------------------------------------------------------
Procedure.i HciSetBaud(baud.i)
  hci_err = #HCI_OK
  If hci_open = 0 : hci_err = #HCI_ERR_NOT_OPEN : ProcedureReturn 0 : EndIf
  If hci_patched = 0 : hci_err = #HCI_ERR_NEEDS_PATCH : ProcedureReturn 0 : EndIf
  If baud <= 0 Or baud > 3000000 : hci_err = #HCI_ERR_BAUD : ProcedureReturn 0 : EndIf
  hci_par[0] = 0 : hci_par[1] = 0
  hci_par[2] = baud & $FF : hci_par[3] = (baud >> 8) & $FF : hci_par[4] = (baud >> 16) & $FF : hci_par[5] = (baud >> 24) & $FF
  If HciCommand(#HCI_OP_BCM_SET_BAUD, @hci_par[0], 6) = 0 : ProcedureReturn 0 : EndIf
  If HwBtSetBaud(baud) = 0 : hci_err = #HCI_ERR_BAUD : ProcedureReturn 0 : EndIf
  hci_baud = baud
  ProcedureReturn 1
EndProcedure

Procedure.i HciBaud()
  ProcedureReturn hci_baud
EndProcedure

; ----------------------------------------------------------------------
;  HciOpen() - power, UART, HCI_Reset, version. 1, or 0 with HciWhy().
; ----------------------------------------------------------------------
Procedure.i HciOpen()
  hci_err = #HCI_OK
  hci_open = 0
  hci_patched = 0
  If HwBtOpen() = 0 : hci_err = #HCI_ERR_TRANSPORT : ProcedureReturn 0 : EndIf
  hci_open = 1
  hci_baud = 115200
  HciDelayMs(100)                     ; bcm_gpio_set_power
  While HwBtGet() >= 0                ; whatever was half-said at power-on
  Wend
  If HciReset() = 0 : ProcedureReturn 0 : EndIf
  If HciReadLocalVersion() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure HciClose()
  If hci_open : HwBtClose() : EndIf
  hci_open = 0
EndProcedure

; ----------------------------------------------------------------------
;  HciBringUp(*hcd, n, baud) - the whole sequence: open, patch (if a
;  file was given), raise the rate (only if patched), then version and
;  address. 1, or 0 with HciWhy().
; ----------------------------------------------------------------------
Procedure.i HciBringUp(*hcd, n.i, baud.i)
  If HciOpen() = 0 : ProcedureReturn 0 : EndIf
  If *hcd <> 0 And n > 0
    If HciLoadPatch(*hcd, n) = 0 : ProcedureReturn 0 : EndIf
    If baud > 115200
      If HciSetBaud(baud) = 0 : ProcedureReturn 0 : EndIf
    EndIf
  EndIf
  If HciReadLocalVersion() = 0 : ProcedureReturn 0 : EndIf
  If HciReadBdAddr() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  The inquiry. Devices are kept once each, in the order first heard.
; ----------------------------------------------------------------------
Procedure HciAddDevice(*addr, cod.i, rssi.i)
  Define i.i, k.i, same.i
  hci_resultsSeen + 1
  For i = 0 To hci_devN - 1
    same = 1
    For k = 0 To 5
      If hci_dev[i * 6 + k] <> (PeekA(*addr + k) & $FF) : same = 0 : Break : EndIf
    Next
    If same
      If rssi <> 127 : hci_devRssi[i] = rssi : EndIf
      ProcedureReturn
    EndIf
  Next
  If hci_devN >= #HCI_MAX_DEVICES
    ProcedureReturn
  EndIf
  For k = 0 To 5 : hci_dev[hci_devN * 6 + k] = PeekA(*addr + k) & $FF : Next
  hci_devCod[hci_devN] = cod
  hci_devRssi[hci_devN] = rssi
  hci_devN + 1
EndProcedure

Procedure.i HciSigned8(v.i)
  If v > 127 : ProcedureReturn v - 256 : EndIf
  ProcedureReturn v
EndProcedure

; lengthUnits x 1.28 s. Returns the number of distinct devices, or -1.
Procedure.i HciInquiry(lengthUnits.i)
  Define deadline.i, i.i, num.i, codOff.i, rssiOff.i, cod.i
  hci_err = #HCI_OK
  hci_devN = 0
  hci_resultsSeen = 0
  If hci_open = 0 : hci_err = #HCI_ERR_NOT_OPEN : ProcedureReturn -1 : EndIf
  If lengthUnits < 1 Or lengthUnits > $30 : hci_err = #HCI_ERR_STATUS : ProcedureReturn -1 : EndIf
  hci_par[0] = #HCI_GIAC & $FF : hci_par[1] = (#HCI_GIAC >> 8) & $FF : hci_par[2] = (#HCI_GIAC >> 16) & $FF
  hci_par[3] = lengthUnits : hci_par[4] = 0
  If HciSend(#HCI_OP_INQUIRY, @hci_par[0], 5) = 0 : ProcedureReturn -1 : EndIf
  deadline = HciDeadline(lengthUnits * 1280 + #HCI_CMD_TIMEOUT_MS)
  Repeat
    If HciReadEvent(deadline) = 0 : ProcedureReturn -1 : EndIf
    If hci_evtCode = #HCI_EV_CMD_STATUS
        If hci_evtLen >= 4 And (hci_evt[2] | (hci_evt[3] << 8)) = #HCI_OP_INQUIRY And hci_evt[0] <> 0
          hci_status = hci_evt[0] : hci_err = #HCI_ERR_STATUS : ProcedureReturn -1
        EndIf
    ElseIf hci_evtCode = #HCI_EV_INQUIRY_RESULT Or hci_evtCode = #HCI_EV_INQUIRY_RSSI
        ; Field by field: addr[6n] psrm[n] reserved[2n or n] cod[3n] clk[2n] (rssi[n])
        num = hci_evt[0]
        If hci_evtCode = #HCI_EV_INQUIRY_RESULT
          codOff = 1 + num * 6 + num + num * 2
          rssiOff = -1
          If hci_evtLen < 1 + num * 14 : hci_err = #HCI_ERR_STATUS : ProcedureReturn -1 : EndIf
        Else
          codOff = 1 + num * 6 + num + num
          rssiOff = codOff + num * 3 + num * 2
          If hci_evtLen < 1 + num * 14 : hci_err = #HCI_ERR_STATUS : ProcedureReturn -1 : EndIf
        EndIf
        For i = 0 To num - 1
          cod = hci_evt[codOff + i * 3] | (hci_evt[codOff + i * 3 + 1] << 8) | (hci_evt[codOff + i * 3 + 2] << 16)
          If rssiOff >= 0
            HciAddDevice(@hci_evt[1 + i * 6], cod, HciSigned8(hci_evt[rssiOff + i]))
          Else
            HciAddDevice(@hci_evt[1 + i * 6], cod, 127)
          EndIf
        Next
    ElseIf hci_evtCode = #HCI_EV_INQUIRY_EXT
        ; num(1)=1, addr 6, psrm 1, reserved 1, cod 3, clk 2, rssi 1, eir 240
        If hci_evtLen >= 15
          cod = hci_evt[9] | (hci_evt[10] << 8) | (hci_evt[11] << 16)
          HciAddDevice(@hci_evt[1], cod, HciSigned8(hci_evt[14]))
        EndIf
    ElseIf hci_evtCode = #HCI_EV_INQUIRY_COMPLETE
        If hci_evtLen >= 1 And hci_evt[0] <> 0
          hci_status = hci_evt[0] : hci_err = #HCI_ERR_STATUS : ProcedureReturn -1
        EndIf
        ProcedureReturn hci_devN
    EndIf
  ForEver
EndProcedure

Procedure.i HciDeviceCount() : ProcedureReturn hci_devN : EndProcedure

; Byte k (0 = most significant, as printed) of device i's address, or -1.
Procedure.i HciDeviceAddrByte(i.i, k.i)
  If i < 0 Or i >= hci_devN Or k < 0 Or k > 5 : ProcedureReturn -1 : EndIf
  ProcedureReturn hci_dev[i * 6 + 5 - k]
EndProcedure

Procedure.i HciDeviceClass(i.i)
  If i < 0 Or i >= hci_devN : ProcedureReturn -1 : EndIf
  ProcedureReturn hci_devCod[i]
EndProcedure

; dBm, or 127 when the controller reported no signal strength.
Procedure.i HciDeviceRssi(i.i)
  If i < 0 Or i >= hci_devN : ProcedureReturn 127 : EndIf
  ProcedureReturn hci_devRssi[i]
EndProcedure

Procedure.i HciResultsSeen() : ProcedureReturn hci_resultsSeen : EndProcedure
