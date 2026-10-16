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
;  ---- LINKS AND DATA (2026-10-16, Ron: "lets add it to anvil") ---------
;  The NES payload (NesEmulatorPicoSeries/anvil/bt_h4.pi4) had grown its
;  own H4 framing, ACL credits and pairing replies on top of this file's
;  UART and streamed A2DP to a speaker from them. Those now live HERE, so
;  every payload and the monitor share one stack:
;    - every packet, event or ACL, goes through one H4 assembler
;      (hci_RxByte); a blocking wait that meets a packet that is not its
;      answer hands it on (HciHandleEvent, or the ACL sink) instead of
;      calling the stream out of step,
;    - HciPoll() is the same without blocking - a streaming loop's pump,
;    - ACL out with the controller's credits (Read Buffer Size, Number Of
;      Completed Packets; the NES's offsets: total at return byte 3/4),
;    - ONE outgoing link to one peer (HciConnect / HciDisconnect) and the
;      replies Linux gives a peer it has no key for: no stored link key,
;      PIN "0000", Secure Simple Pairing as NoInputNoOutput, confirmation
;      accepted (the NES's sequence, which its speaker paired with),
;    - hooks instead of upward calls: *hci_aclIn (L2CAP, l2cap.pbi),
;      *hci_linkNote (link up/down), *hci_idle (a payload's watchdog and
;      input while a blocking wait spins) and HciAbort().
;  Higher layers: Anvil/Net/l2cap.pbi, Anvil/Net/a2dp.pbi.
;
;  ON SILICON 2026-10-16 (RaspberryPi4/Examples/Diagnostics/pi4BtProbe.pi4,
;  a RAM payload over these files unchanged): reset, patch, 3,000,000 baud,
;  HCI 5.0 / manufacturer 305 / subversion $6119, ACL 8 x 1021, event mask,
;  SSP, inquiry (found the headset), the link, pairing, a kept bond given
;  back on reconnection, and A2DP on top (a2dp.pbi).
; ======================================================================

EnableExplicit

#HCI_CMD_PKT = $01
#HCI_ACL_PKT = $02
#HCI_EVT_PKT = $04

#HCI_OP_RESET          = $0C03
#HCI_OP_READ_LOCAL_VER = $1001
#HCI_OP_READ_BD_ADDR   = $1009
#HCI_OP_INQUIRY        = $0401
#HCI_OP_BCM_MINIDRIVER = $FC2E
#HCI_OP_BCM_LAUNCH_RAM = $FC4E
#HCI_OP_BCM_SET_BAUD   = $FC18
#HCI_OP_BCM_WRITE_ADDR = $FC01
#HCI_OP_READ_BUFFER    = $1005
#HCI_OP_SET_EVENT_MASK = $0C01
#HCI_OP_WRITE_SSP_MODE = $0C56
#HCI_OP_CREATE_CONN    = $0405
#HCI_OP_DISCONNECT     = $0406
#HCI_OP_LINK_KEY_REPLY = $040B
#HCI_OP_LINK_KEY_NEG   = $040C
#HCI_OP_PIN_REPLY      = $040D
#HCI_OP_IO_CAP_REPLY   = $042B
#HCI_OP_USER_CONFIRM   = $042C

#HCI_EV_INQUIRY_COMPLETE = $01
#HCI_EV_INQUIRY_RESULT   = $02
#HCI_EV_CMD_COMPLETE     = $0E
#HCI_EV_CMD_STATUS       = $0F
#HCI_EV_HW_ERROR         = $10
#HCI_EV_INQUIRY_RSSI     = $22
#HCI_EV_INQUIRY_EXT      = $2F
#HCI_EV_CONN_COMPLETE    = $03
#HCI_EV_DISCONN_COMPLETE = $05
#HCI_EV_COMPLETED_PKTS   = $13
#HCI_EV_PIN_REQUEST      = $16
#HCI_EV_LINK_KEY_REQUEST = $17
#HCI_EV_IO_CAP_REQUEST   = $31
#HCI_EV_USER_CONFIRM     = $33
#HCI_EV_LINK_KEY_NOTIFY  = $18

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
#HCI_ERR_ABORTED      = 11    ; HciAbort(1) - the payload is leaving
#HCI_ERR_NO_CREDIT    = 12    ; the controller has no ACL buffer free
#HCI_ERR_NO_LINK      = 13    ; no link is up (or one is already being made)
#HCI_ERR_TOO_BIG      = 14    ; more than one ACL buffer's worth

#HCI_LINK_NONE       = 0
#HCI_LINK_CONNECTING = 1
#HCI_LINK_UP         = 2

#HCI_PKT_MAX = 1100           ; one ACL packet: 4 + the controller's 1021

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
Global Dim hci_par.a[32]        ; a command's parameters, built here
Global hci_rxType.i             ; the H4 assembler: 0 = between packets
Global hci_rxHave.i
Global hci_rxNeed.i
Global Dim hci_pkt.a[#HCI_PKT_MAX]   ; the packet being assembled
Global hci_pktType.i            ; the last complete packet: $04 or $02
Global hci_pktLen.i             ; ... its bytes after the indicator
Global hci_rxErrors.i           ; bytes that were not a packet's start
Global hci_rxBytes.i            ; every byte the controller has sent
Global Dim hci_rxRing.a[64]     ; the last 64 of them (HciRxRingByte)
Global hci_rxDropped.i          ; packets too long for hci_pkt
Global hci_abort.i
Global *hci_idle                ; ()                  while a wait spins
Global *hci_aclIn               ; (pb, *data, n)      one ACL packet's data;
                                ;   pb = packet boundary: 2 first, 1 more
Global *hci_linkNote            ; (up)                1 link up, 0 down
Global hci_aclMax.i             ; bytes in one controller ACL buffer
Global hci_aclTotal.i           ; how many buffers
Global hci_aclCredits.i         ; buffers free now
Global hci_aclSent.i
Global hci_linkState.i
Global hci_linkHandle.i = -1
Global hci_linkStatus.i         ; the last connect status / disconnect reason
Global Dim hci_linkAddr.a[6]    ; the peer, as on the wire (LSB first)
Global hci_pairings.i           ; pairing requests answered
Global Dim hci_keyAddr.a[6]     ; THE ONE BOND: the peer it is for (wire order)
Global Dim hci_key.a[16]        ;   and its link key
Global hci_haveKey.i
Global hci_keysGiven.i          ; link key requests answered with the key
Global hci_keysNew.i            ; link keys the controller reported

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
    Case #HCI_ERR_ABORTED : ProcedureReturn "the Bluetooth wait was abandoned because the program is leaving"
    Case #HCI_ERR_NO_CREDIT : ProcedureReturn "the controller has no ACL buffer free; it has not reported the earlier packets sent"
    Case #HCI_ERR_NO_LINK : ProcedureReturn "there is no Bluetooth link up (or one is still being made)"
    Case #HCI_ERR_TOO_BIG : ProcedureReturn "that is more data than one controller ACL buffer holds"
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

; ----------------------------------------------------------------------
;  THE H4 ASSEMBLER. One byte at a time into hci_pkt; 1 when a packet is
;  complete (hci_pktType, hci_pktLen). A byte that cannot start a packet
;  is counted and skipped - the next indicator resynchronises, as the NES
;  payload's adapter did for hours of streaming.
;    event: 04 code len params          hci_pkt = code len params
;    ACL:   02 handle(2) len(2) data    hci_pkt = handle len data
; ----------------------------------------------------------------------
Procedure.i hci_RxByte(b.i)
  If hci_rxType = 0
    If b = #HCI_EVT_PKT
      hci_rxType = b : hci_rxHave = 0 : hci_rxNeed = 2
    ElseIf b = #HCI_ACL_PKT
      hci_rxType = b : hci_rxHave = 0 : hci_rxNeed = 4
    Else
      hci_rxErrors = hci_rxErrors + 1
    EndIf
    ProcedureReturn 0
  EndIf
  If hci_rxHave < #HCI_PKT_MAX : hci_pkt[hci_rxHave] = b : EndIf
  hci_rxHave = hci_rxHave + 1
  If hci_rxType = #HCI_EVT_PKT And hci_rxHave = 2
    hci_rxNeed = 2 + hci_pkt[1]
  ElseIf hci_rxType = #HCI_ACL_PKT And hci_rxHave = 4
    hci_rxNeed = 4 + (hci_pkt[2] | (hci_pkt[3] << 8))
  EndIf
  If hci_rxHave < hci_rxNeed : ProcedureReturn 0 : EndIf
  hci_pktType = hci_rxType
  hci_pktLen = hci_rxHave
  hci_rxType = 0
  If hci_pktLen > #HCI_PKT_MAX
    hci_rxDropped = hci_rxDropped + 1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; Up to 512 waiting bytes; 1 as soon as a packet is complete, else 0.
Procedure.i hci_RxSome()
  Define n.i, b.i
  For n = 0 To 511
    b = HwBtGet()
    If b < 0 : ProcedureReturn 0 : EndIf
    hci_rxRing[hci_rxBytes & 63] = b & $FF
    hci_rxBytes = hci_rxBytes + 1
    If hci_RxByte(b & $FF) <> 0 : ProcedureReturn 1 : EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure HciAbort(on.i)
  hci_abort = on
EndProcedure

; The link-level events every reader handles, whoever was waiting:
; credits, the link coming and going, and the pairing questions.
Declare HciHandleEvent()

; An ACL packet goes to the sink above (l2cap.pbi), if one is set.
Procedure hci_AclArrived()
  Define handle.i, n.i
  handle = (hci_pkt[0] | (hci_pkt[1] << 8)) & $FFF
  n = hci_pktLen - 4
  If *hci_aclIn <> 0 And handle = hci_linkHandle
    hci_aclIn((hci_pkt[1] >> 4) & 3, @hci_pkt[4], n)
  EndIf
EndProcedure

; Copy the complete event into hci_evt/hci_evtCode/hci_evtLen.
Procedure hci_TakeEvent()
  Define i.i
  hci_evtCode = hci_pkt[0]
  hci_evtLen = hci_pkt[1]
  For i = 0 To hci_evtLen - 1 : hci_evt[i] = hci_pkt[2 + i] : Next
EndProcedure

; One whole EVENT into hci_evt/hci_evtCode/hci_evtLen, waiting until the
; deadline. ACL packets met on the way are handed on. 1, or 0 with hci_err.
Procedure.i HciReadEvent(deadline.i)
  Define spins.i = 0
  Repeat
    If hci_RxSome() <> 0
      If hci_pktType = #HCI_ACL_PKT
        hci_AclArrived()
      Else
        hci_TakeEvent()
        If hci_evtCode = #HCI_EV_HW_ERROR : hci_err = #HCI_ERR_HWERR : ProcedureReturn 0 : EndIf
        HciHandleEvent()
        ProcedureReturn 1
      EndIf
    Else
      If *hci_idle <> 0 : hci_idle() : EndIf
      If hci_abort <> 0 : hci_err = #HCI_ERR_ABORTED : ProcedureReturn 0 : EndIf
      spins + 1
      If spins > #HCI_SPIN_MAX : hci_err = #HCI_ERR_TIMEOUT : ProcedureReturn 0 : EndIf
      If deadline > 0 And Ticks() > deadline : hci_err = #HCI_ERR_TIMEOUT : ProcedureReturn 0 : EndIf
    EndIf
  ForEver
EndProcedure

; The streaming pump: every packet waiting now (up to 8), never blocking.
; Events are handled (HciHandleEvent), ACL data handed up. The number of
; packets taken.
Procedure.i HciPoll()
  Define k.i
  If hci_open = 0 : ProcedureReturn 0 : EndIf
  For k = 0 To 7
    If hci_RxSome() = 0 : ProcedureReturn k : EndIf
    If hci_pktType = #HCI_ACL_PKT
      hci_AclArrived()
    Else
      hci_TakeEvent()
      HciHandleEvent()
    EndIf
  Next
  ProcedureReturn 8
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

; Give the controller another address until its next reset: btbcm.c's
; btbcm_set_bdaddr (vendor $FC01, the 6 bytes in wire order). *addr is
; MOST significant first, as printed. 1, or 0 with hci_err.
Procedure.i HciWriteBdAddr(*addr)
  Define i.i
  For i = 0 To 5 : hci_par[i] = PeekA(*addr + 5 - i) & $FF : Next
  If HciCommand(#HCI_OP_BCM_WRITE_ADDR, @hci_par[0], 6) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn HciReadBdAddr()
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
  hci_rxType = 0
  hci_linkState = #HCI_LINK_NONE
  hci_linkHandle = -1
  hci_aclCredits = 0
  hci_aclTotal = 0
  If HwBtOpen() = 0 : hci_err = #HCI_ERR_TRANSPORT : ProcedureReturn 0 : EndIf
  hci_open = 1
  hci_baud = 115200
  HciDelayMs(120)                     ; bcm_gpio_set_power (100-120 ms)
  While HwBtGet() >= 0                ; whatever was half-said at power-on
  Wend
  ; ONLY THE RESET (found on the Pi 4, 2026-10-16, pi4BtProbe): the
  ; CYW43455 powers up in Broadcom's download state, where it answers
  ; HCI_Reset and Download_Minidriver and IGNORES everything else -
  ; Read_Local_Version, Read_BD_ADDR, Read_Local_Name and the vendor
  ; $FC79 all went unanswered (no byte at all) until the patch was in.
  ; So the version is read after the patch (HciBringUp), never here.
  If HciReset() = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

Procedure HciClose()
  If hci_open : HwBtClose() : EndIf
  hci_open = 0
  hci_linkState = #HCI_LINK_NONE
  hci_linkHandle = -1
EndProcedure

Procedure.i HciIsOpen()
  ProcedureReturn hci_open
EndProcedure

; ----------------------------------------------------------------------
;  The controller's ACL buffers (Read Buffer Size): return bytes 0-1 the
;  length of one, 3-4 how many. The NES payload found its first reading of
;  the count one byte off (14/15 instead of 13/14 of its whole packet).
; ----------------------------------------------------------------------
Procedure.i HciReadBufferSize()
  If HciCommand(#HCI_OP_READ_BUFFER, 0, 0) = 0 : ProcedureReturn 0 : EndIf
  If hci_retLen < 5 : hci_err = #HCI_ERR_STATUS : ProcedureReturn 0 : EndIf
  hci_aclMax = hci_ret[0] | (hci_ret[1] << 8)
  hci_aclTotal = hci_ret[3] | (hci_ret[4] << 8)
  If hci_aclMax < 27 Or hci_aclTotal < 1 : hci_err = #HCI_ERR_STATUS : ProcedureReturn 0 : EndIf
  hci_aclCredits = hci_aclTotal
  ProcedureReturn 1
EndProcedure

; Every event, and Secure Simple Pairing on (what the NES sent).
Procedure.i HciLinkSetup()
  Define i.i
  For i = 0 To 7 : hci_par[i] = $FF : Next
  If HciCommand(#HCI_OP_SET_EVENT_MASK, @hci_par[0], 8) = 0 : ProcedureReturn 0 : EndIf
  hci_par[0] = 1
  If HciCommand(#HCI_OP_WRITE_SSP_MODE, @hci_par[0], 1) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
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
  If HciReadBufferSize() = 0 : ProcedureReturn 0 : EndIf
  If HciLinkSetup() = 0 : ProcedureReturn 0 : EndIf
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

; ======================================================================
;  THE LINK. One outgoing ACL link to one peer at a time.
; ======================================================================

; 1 if the 6 bytes at hci_evt[at] are the peer's address.
Procedure.i hci_IsPeer(at.i)
  Define i.i
  For i = 0 To 5
    If hci_evt[at + i] <> hci_linkAddr[i] : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

; 1 if the bond is for the current peer.
Procedure.i hci_KeyIsPeer()
  Define i.i
  For i = 0 To 5
    If hci_keyAddr[i] <> hci_linkAddr[i] : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure hci_PeerToPar()
  Define i.i
  For i = 0 To 5 : hci_par[i] = hci_linkAddr[i] : Next
EndProcedure

Procedure hci_LinkDown(reason.i)
  hci_linkState = #HCI_LINK_NONE
  hci_linkHandle = -1
  hci_linkStatus = reason
  hci_aclCredits = hci_aclTotal
  If *hci_linkNote <> 0 : hci_linkNote(0) : EndIf
EndProcedure

Procedure HciHandleEvent()
  Define i.i, n.i, h.i
  Select hci_evtCode
    Case #HCI_EV_COMPLETED_PKTS
      n = hci_evt[0]
      For i = 0 To n - 1
        If 1 + i * 4 + 3 < hci_evtLen
          hci_aclCredits = hci_aclCredits + (hci_evt[3 + i * 4] | (hci_evt[4 + i * 4] << 8))
        EndIf
      Next
      If hci_aclCredits > hci_aclTotal : hci_aclCredits = hci_aclTotal : EndIf
    Case #HCI_EV_CONN_COMPLETE
      ; status, handle(2), address(6), link type, encryption
      If hci_linkState = #HCI_LINK_CONNECTING And hci_evtLen >= 9 And hci_IsPeer(3) <> 0
        If hci_evt[0] = 0
          hci_linkHandle = (hci_evt[1] | (hci_evt[2] << 8)) & $FFF
          hci_linkState = #HCI_LINK_UP
          hci_linkStatus = 0
          If *hci_linkNote <> 0 : hci_linkNote(1) : EndIf
        Else
          hci_LinkDown(hci_evt[0])
        EndIf
      EndIf
    Case #HCI_EV_DISCONN_COMPLETE
      ; status, handle(2), reason
      If hci_evtLen >= 4 And hci_evt[0] = 0
        h = (hci_evt[1] | (hci_evt[2] << 8)) & $FFF
        If h = hci_linkHandle : hci_LinkDown(hci_evt[3]) : EndIf
      EndIf
    Case #HCI_EV_CMD_STATUS
      ; Create Connection refused outright (no Connection Complete follows).
      If hci_evtLen >= 4 And (hci_evt[2] | (hci_evt[3] << 8)) = #HCI_OP_CREATE_CONN And hci_evt[0] <> 0
        If hci_linkState = #HCI_LINK_CONNECTING : hci_LinkDown(hci_evt[0]) : EndIf
      EndIf
    Case #HCI_EV_LINK_KEY_REQUEST
      ; The bond's key if it is this peer's; otherwise "none", and the peer
      ; pairs again. FOUND ON THE BOARD 2026-10-16: a headset that has
      ; paired once keeps its key and HANGS UP (reason $13) on "none" - it
      ; does not pair a second time - so a host that forgets keys gets one
      ; connection per device, ever. Keep the key (HciLinkKey*) and give it.
      If hci_evtLen >= 6 And hci_IsPeer(0) <> 0
        hci_PeerToPar()
        If hci_haveKey <> 0 And hci_KeyIsPeer() <> 0
          For i = 0 To 15 : hci_par[6 + i] = hci_key[i] : Next
          HciSend(#HCI_OP_LINK_KEY_REPLY, @hci_par[0], 22)
          hci_keysGiven = hci_keysGiven + 1
        Else
          HciSend(#HCI_OP_LINK_KEY_NEG, @hci_par[0], 6)
        EndIf
        hci_pairings = hci_pairings + 1
      EndIf
    Case #HCI_EV_LINK_KEY_NOTIFY
      ; address(6), key(16), type(1): a pairing finished - keep the bond.
      If hci_evtLen >= 22 And hci_IsPeer(0) <> 0
        For i = 0 To 5 : hci_keyAddr[i] = hci_evt[i] : Next
        For i = 0 To 15 : hci_key[i] = hci_evt[6 + i] : Next
        hci_haveKey = 1
        hci_keysNew = hci_keysNew + 1
      EndIf
    Case #HCI_EV_PIN_REQUEST
      ; A legacy peer: PIN "0000".
      If hci_evtLen >= 6 And hci_IsPeer(0) <> 0
        hci_PeerToPar()
        hci_par[6] = 4
        For i = 7 To 22 : hci_par[i] = 0 : Next
        For i = 7 To 10 : hci_par[i] = 48 : Next
        HciSend(#HCI_OP_PIN_REPLY, @hci_par[0], 23)
        hci_pairings = hci_pairings + 1
      EndIf
    Case #HCI_EV_IO_CAP_REQUEST
      ; Secure Simple Pairing: no display, no keyboard, no OOB, no MITM.
      If hci_evtLen >= 6 And hci_IsPeer(0) <> 0
        hci_PeerToPar()
        hci_par[6] = 3 : hci_par[7] = 0 : hci_par[8] = 0
        HciSend(#HCI_OP_IO_CAP_REPLY, @hci_par[0], 9)
        hci_pairings = hci_pairings + 1
      EndIf
    Case #HCI_EV_USER_CONFIRM
      If hci_evtLen >= 6 And hci_IsPeer(0) <> 0
        hci_PeerToPar()
        HciSend(#HCI_OP_USER_CONFIRM, @hci_par[0], 6)
        hci_pairings = hci_pairings + 1
      EndIf
  EndSelect
EndProcedure

; Start a link to the peer at *addr (6 bytes, MOST significant first, as
; printed). Answered later: HciLinkState() becomes #HCI_LINK_UP, or
; #HCI_LINK_NONE with HciLinkStatus() the controller's reason. The packet
; types, page-scan mode R1 and role switch allowed are the NES's (Linux's
; hci_connect_acl defaults for a BR/EDR peer).
Procedure.i HciConnect(*addr)
  Define i.i
  hci_err = #HCI_OK
  If hci_open = 0 : hci_err = #HCI_ERR_NOT_OPEN : ProcedureReturn 0 : EndIf
  If hci_linkState <> #HCI_LINK_NONE : hci_err = #HCI_ERR_NO_LINK : ProcedureReturn 0 : EndIf
  For i = 0 To 5 : hci_linkAddr[i] = PeekA(*addr + 5 - i) & $FF : Next
  hci_PeerToPar()
  hci_par[6] = $18 : hci_par[7] = $CC     ; DM1 DH1 DM3 DH3 DM5 DH5
  hci_par[8] = 1                          ; page scan repetition mode R1
  hci_par[9] = 0
  hci_par[10] = 0 : hci_par[11] = 0       ; clock offset unknown
  hci_par[12] = 1                         ; role switch allowed
  hci_linkState = #HCI_LINK_CONNECTING
  hci_linkStatus = 0
  If HciSend(#HCI_OP_CREATE_CONN, @hci_par[0], 13) = 0
    hci_linkState = #HCI_LINK_NONE
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; Wait (handling everything that arrives) until the link is up or failed.
Procedure.i HciConnectWait(ms.i)
  Define deadline.i = HciDeadline(ms)
  While hci_linkState = #HCI_LINK_CONNECTING
    If HciReadEvent(deadline) = 0 : ProcedureReturn 0 : EndIf
  Wend
  If hci_linkState = #HCI_LINK_UP : ProcedureReturn 1 : EndIf
  hci_err = #HCI_ERR_NO_LINK
  ProcedureReturn 0
EndProcedure

; End the link (reason $13, remote user terminated). Not waited for.
Procedure HciDisconnect()
  If hci_open = 0 Or hci_linkHandle < 0 : ProcedureReturn : EndIf
  hci_par[0] = hci_linkHandle & $FF
  hci_par[1] = (hci_linkHandle >> 8) & $FF
  hci_par[2] = $13
  HciSend(#HCI_OP_DISCONNECT, @hci_par[0], 3)
EndProcedure

Procedure.i HciLinkState() : ProcedureReturn hci_linkState : EndProcedure
Procedure.i HciLinkHandle() : ProcedureReturn hci_linkHandle : EndProcedure
Procedure.i HciLinkStatus() : ProcedureReturn hci_linkStatus : EndProcedure
Procedure.i HciAclCredits() : ProcedureReturn hci_aclCredits : EndProcedure
Procedure.i HciAclMax() : ProcedureReturn hci_aclMax : EndProcedure
Procedure.i HciAclTotal() : ProcedureReturn hci_aclTotal : EndProcedure
Procedure.i HciAclSent() : ProcedureReturn hci_aclSent : EndProcedure
Procedure.i HciRxErrors() : ProcedureReturn hci_rxErrors + hci_rxDropped : EndProcedure
Procedure.i HciRxBytes() : ProcedureReturn hci_rxBytes : EndProcedure
; Byte k (0 = the first ever, while fewer than 64 have arrived) of the ring.
Procedure.i HciRxRingByte(k.i) : ProcedureReturn hci_rxRing[k & 63] : EndProcedure
Procedure.i HciPairings() : ProcedureReturn hci_pairings : EndProcedure
Procedure.i HciKeysGiven() : ProcedureReturn hci_keysGiven : EndProcedure
Procedure.i HciKeysNew() : ProcedureReturn hci_keysNew : EndProcedure

; ----------------------------------------------------------------------
;  THE BOND, for whoever keeps it (a file, a payload's RAM): 22 bytes =
;  the peer's address (6, wire order) and the link key (16).
;    HciLinkKeyGet(*dst)  1 and the 22 bytes, or 0 if there is no bond
;    HciLinkKeySet(*src)  give a kept bond back (after HciOpen or before)
; ----------------------------------------------------------------------
Procedure.i HciLinkKeyGet(*dst)
  Define i.i
  If hci_haveKey = 0 : ProcedureReturn 0 : EndIf
  For i = 0 To 5 : PokeA(*dst + i, hci_keyAddr[i]) : Next
  For i = 0 To 15 : PokeA(*dst + 6 + i, hci_key[i]) : Next
  ProcedureReturn 1
EndProcedure

Procedure HciLinkKeySet(*src)
  Define i.i
  For i = 0 To 5 : hci_keyAddr[i] = PeekA(*src + i) & $FF : Next
  For i = 0 To 15 : hci_key[i] = PeekA(*src + 6 + i) & $FF : Next
  hci_haveKey = 1
EndProcedure

; One ACL packet on the link: the first (or only) fragment of an L2CAP
; frame, n bytes at *data. 1, or 0 with hci_err (no credit, no link, too
; big). The caller keeps the data until it is sent; nothing is queued.
Procedure.i HciAclSend(*data, n.i)
  Define i.i
  hci_err = #HCI_OK
  If hci_linkState <> #HCI_LINK_UP : hci_err = #HCI_ERR_NO_LINK : ProcedureReturn 0 : EndIf
  If n > hci_aclMax : hci_err = #HCI_ERR_TOO_BIG : ProcedureReturn 0 : EndIf
  If hci_aclCredits < 1 : hci_err = #HCI_ERR_NO_CREDIT : ProcedureReturn 0 : EndIf
  If HwBtPut(#HCI_ACL_PKT) = 0 Or HwBtPut(hci_linkHandle & $FF) = 0 Or HwBtPut(((hci_linkHandle >> 8) & $0F) | $20) = 0 Or HwBtPut(n & $FF) = 0 Or HwBtPut((n >> 8) & $FF) = 0
    hci_err = #HCI_ERR_TX
    ProcedureReturn 0
  EndIf
  For i = 0 To n - 1
    If HwBtPut(PeekA(*data + i) & $FF) = 0 : hci_err = #HCI_ERR_TX : ProcedureReturn 0 : EndIf
  Next
  hci_aclCredits = hci_aclCredits - 1
  hci_aclSent = hci_aclSent + 1
  ProcedureReturn 1
EndProcedure
