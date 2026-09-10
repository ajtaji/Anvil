; ======================================================================
; netconsole.pbi - THE NETWORK CONSOLE. One console, whichever link
;                  holds the address.
; ======================================================================
;
; WHAT THIS IS. A UDP console on port #NETCON_PORT (5555). Once the board
; has an address, it listens. Whoever sends it a datagram becomes the
; peer, and from then on everything the monitor prints goes to that peer
; as UDP - through the aux output tap in the UART library - and every byte
; the peer sends is fed into the command input exactly as if it had been
; typed on the serial line. The serial console keeps working at the same
; time: it is ONE shared console with a second wire.
;
; NO TCP AND NO ARP, ON PURPOSE. UDP needs no connection state, and the
; peer's hardware address is taken from the datagram it sent us - we only
; ever reply to somebody who spoke first, which is exactly the "connect to
; the board" model a com port wants. A fresh board with an empty neighbour
; cache is therefore reachable with nothing typed at it.
;
; A host talks to it with tools/anvil_wifi.py. THE WIRE PROTOCOL HAS NOT
; CHANGED - same port, same datagrams, same acknowledged binary framing
; underneath `pr` and the image push - so every host tool keeps working.
;
; ======================================================================
; WHY THIS FILE EXISTS, AND WHAT IT COST NOT TO HAVE IT
; ======================================================================
; Until 2026-09-07 this code lived inside RaspberryPi4/Lib/wifi.pi4 and
; was called the WIRELESS console. It named the radio in every line: the
; frame was built inside the radio driver's transmit buffer, sent with
; the radio's own send, received from the radio's own receive, and armed
; only when a flag private to that file's DHCP client said the RADIO had
; an address.
;
; THE BENCH FOUND THE HOLE ON 2026-09-07 and it cost an afternoon. The PC
; moved to a VPN on another subnet, so the board's radio was out of reach;
; the serial adapter was failing enumeration; and the Ethernet cable was
; plugged straight into the PC with an address on it at both ends. The
; board was, by every physical measure, connected to the machine trying to
; reach it - and it had NO CONSOLE AT ALL, because the only UDP console it
; had could ride one of its two interfaces.
;
; THE FIX IS NOT A SECOND CONSOLE. Two consoles would be two arming
; rules, two peer records and two flush paths, and the one on the link
; nobody was watching would rot. There is ONE console. It asks which
; interface the ONE IP layer is currently configured for and binds itself
; there, and every frame it sends and receives goes through the HwLink*
; seam addressed to that kind.
;
; ======================================================================
; HOW IT DECIDES WHERE TO LIVE - AND WHY IT ASKS THE IP LAYER
; ======================================================================
; net.pi4 holds exactly ONE hardware address and ONE IPv4 address, and
; whoever configured it last decided which interface those belong to.
; That is not a limitation to be worked around here; it is the answer.
; The console compares net.pi4's hardware address against each link's
; own (HwLinkMacPtr) and takes the kind that matches.
;
; So the console rides whichever interface the policy layer chose, for
; free, and the preference order lives in exactly one place -
; RaspberryPi4/Lib/link.pi4's LinkSelect, which prefers the WIRED side
; when the cable is in and it has an address. A console that had its own
; opinion about which link to prefer would be a second copy of a decision
; that must not be made twice.
;
; THREE THINGS ARE REQUIRED AND ALL THREE ARE MEASURED, NEVER ASSUMED:
;
;   1. the IP layer holds a hardware address and an IPv4 address;
;   2. some link's own hardware address is that hardware address;
;   3. that link says it can carry a frame RIGHT NOW (HwLinkReady) -
;      the radio is keyed, or the wired driver started and the PHY still
;      sees a link.
;
; Point 3 is the one that reads like belt and braces and is not. Arming a
; console on an interface that cannot transmit produces a board that
; announces it is listening and answers nobody, which is the precise
; shape of the defect this whole line of work exists to end.
;
; WIRED IS TRIED FIRST in the sweep below. In practice only one kind can
; match, because two interfaces do not share a hardware address - so the
; order is a statement of intent rather than a tie-break, and it is
; written the same way round as LinkSelect's so that the two cannot be
; read as disagreeing.
;
; ======================================================================
; RE-DERIVED EVERY SPIN, NEVER LATCHED BY A PATH
; ======================================================================
; NetConsoleRearm() runs on every spin of the prompt (Anvil/Core/parse.pi4)
; and once in the boot log (the board's boot file). It answers the whole
; question from the board's actual state:
;
;   ARMED AND STILL ON THE RIGHT LINK AT THE RIGHT ADDRESS
;       put the bound UDP port back. ping, dns and dhcp each call
;       NetUdpBind with a port of their own so that only their own reply
;       is delivered to them, and none of them puts it back - without
;       this the console went permanently deaf after the first `ping`.
;
;   ARMED, BUT THE STACK HAS MOVED to another interface or another
;   address - `net link wired` then `dhcp`, a lease on the other link,
;   a cable pulled
;       re-arm onto where the board actually is, announce it, and FORGET
;       THE PEER. The peer was reached over the old link and its
;       hardware address belongs to that link's segment; replying to it
;       out of the new one would send frames to a machine that is not
;       there. The host gets the board back by sending it anything at
;       all, which is the same handshake it used the first time.
;
;   NOT ARMED, AND THE BOARD HAS AN ADDRESS
;       arm, and say on which link and at which address.
;
;   NOT ARMED AND NO ADDRESS
;       nothing, cheaply.
;
; THE SHAPE THIS REPLACES, and it is worth stating because it grew back
; twice: arming used to be LATCHED BY WHOEVER COMPLETED DHCP - each path
; saying "I got the address, so I will arm". That construction can only
; ever cover the paths somebody thought of, and the tree kept growing
; paths that acquire an address another way. Re-deriving from state costs
; two loads and a compare on a board already listening, and cannot be
; forgotten by a path nobody has written yet.
;
; ======================================================================
; REQUIRES - the main program includes these BEFORE the prompt runs
; ======================================================================
;     Anvil/Hal/hal.pbi          #HW_LINK_* and #NETCON_PORT
;     the board's HwLink* backend
;     the IP layer               NetInput, NetUdpBind, NetUdpRx*, NetIPv4,
;                                NetGetMac, NetMacSet, NetOutBuf/Len,
;                                NetUdpChecksumTx
;     the UART                   UartAuxMirror, UartAuxSetFlush, UartAuxGet
;     millis(), delayMicroseconds()
;
; THIS FILE NAMES NO CHIP AND NO BOARD. That is the whole point of it and
; it is worth keeping: every wire access below is HwLink*(kind, ...).
; ======================================================================

; Most one datagram carries. 1024 leaves room for the 42 bytes of
; Ethernet, IPv4 and UDP header inside every link's frame ceiling this
; project has met; netcon_BuildUdp asks the link anyway rather than
; trusting that, because a link with a small frame is a refusal and not a
; truncation - a truncated console line is a corrupt one.
#NETCON_OUT_MAX = 1024

; The keystroke ring. A human types slower than this drains.
#NETCON_IN_RING = 256

; Bulk-mode inter-datagram pace, microseconds. About 866 datagrams for a
; full screenshot, so a quarter of a second added to it - negligible, and
; it keeps the host's UDP socket buffer from overrunning. Nothing paces
; ordinary interactive output.
#NETCON_PACE_US = 250

; The receive staging buffer. A link that hands back a pointer into its
; own buffer needs none of this; a link that fills the caller's buffer
; needs somebody to own one. 1536 is the ceiling the wired MAC will
; receive, so a frame the controller was willing to take can never be too
; large for the buffer it lands in.
#NETCON_RX_MAX = 1536

; The transmit staging buffer: one full console datagram, headers and all.
#NETCON_TX_MAX = 14 + 20 + 8 + #NETCON_OUT_MAX

Global gConOn.i = 0                ; the console is listening
; THE INTERFACE AND ADDRESS IT NAMES IN ITS ANNOUNCEMENT, which is the
; PREFERRED one - the cable whenever the cable is up. It is NOT the only
; one it listens on: since 2026-09-07 the console listens on EVERY
; interface that holds an address, and these two exist so that `net`,
; `info` and the boot log have one line to put first.
Global gConKind.i = #HW_LINK_NONE
Global gConIp.i = 0
; Bit set for each interface the last actual receive walk consumed. This is
; dispatcher ownership, not route preference, and is published to drivers
; that otherwise run an independent hardware receive pump.
Global gConMemberMask.i = 0
Global gConPeerOk.i = 0            ; a peer has been seen
Global gConPeerIp.i = 0
Global gConPeerPort.i = 0
; ----------------------------------------------------------------------
;  WHERE THE PEER IS, AND WHICH OF OUR ADDRESSES IT SPOKE TO.
;
;  THE REPLY LEAVES BY THE INTERFACE THE REQUEST ARRIVED ON, SOURCED
;  FROM THE ADDRESS IT WAS ADDRESSED TO. Both halves are needed and
;  neither can be derived later: a board with a cable and a radio both
;  addressed has two hardware addresses and up to three IPv4 addresses,
;  and a reply built from the wrong one of either is a frame the asker
;  discards with nothing logged at either end. That is the exact failure
;  of 2026-09-07 - the radio's lease displaced the cable's address and
;  the laptop on the cable simply stopped being answered.
;
;  THEY ARE CAPTURED FROM THE FRAME ITSELF, in the same place and for
;  the same reason the peer's hardware address is: the datagram in hand
;  is the only thing that knows.
; ----------------------------------------------------------------------
Global gConPeerKind.i = #HW_LINK_NONE
Global gConPeerDstIp.i = 0
Global Dim gConPeerMac.a[6]
#NETCON_OWNER_NONE  = 0
#NETCON_OWNER_NET   = 1
#NETCON_OWNER_LOCAL = 2
Global gConOwner.i = #NETCON_OWNER_NONE
Global Dim gConBusy.a[6]
Global Dim gConIn.a[#NETCON_IN_RING]
Global gConInHead.i = 0
Global gConInTail.i = 0
Global Dim gConOut.a[#NETCON_OUT_MAX]
Global Dim gConTx.a[#NETCON_TX_MAX]
Global Dim gConRx.a[#NETCON_RX_MAX]
Global Dim gConNetMac.a[6]         ; scratch for NetGetMac
Global gConFlushing.i = 0
Global gConLastPump.i = 0
Global gConArms.i = 0              ; how many times it has armed, for `net`
Global gConTxOk.i = 0              ; staged replies accepted by a link
Global gConTxFail.i = 0            ; staged replies a link refused
Global gConRxFrames.i = 0          ; frames taken from all interface rings
Global gConRxFull.i = 0            ; drains that spent the whole budget

; ----------------------------------------------------------------------
;  THE LINK-LOCAL SURRENDER HOOK, 2026-09-07. Zero unless a link-local
;  address has been taken; see NetLinkLocalTick in Anvil/Core/netll.pbi
;  for what it does.
;
;  WHY IT IS A POINTER. The prompt's spin lives in Anvil/Core/parse.pi4,
;  which is included BEFORE the settings store, netcfg.pbi and netll.pbi
;  - it has to be, because all three use its parser - so the spin cannot
;  name a procedure in netll.pbi. The same include-order fact produced
;  HwLinkSetWiredMacPtr in RaspberryPi4/Board/hw_link.pi4, and it is
;  solved the same way rather than by giving one piece of knowledge two
;  homes. It is registered once, from BootBringUp().
;
;  IT LIVES IN THE CONSOLE'S OWN FILE because what the hook protects is
;  the console: an address surrendered under RFC 3927 section 2.5 is an
;  address the console must stop answering on.
; ----------------------------------------------------------------------
Global *gConLlTick

Procedure NetConsoleSetLlTick(*fn)
  *gConLlTick = *fn
EndProcedure

; Called from the prompt's spin. One load and a compare on a board that
; has never taken a link-local address, which is most of them.
Procedure NetConsoleLlTick()
  If *gConLlTick = 0
    ProcedureReturn
  EndIf
  gConLlTick()
EndProcedure

Procedure netcon_InPush(c.i)
  Define nxt.i
  nxt = gConInHead + 1
  If nxt >= #NETCON_IN_RING
    nxt = 0
  EndIf
  If nxt = gConInTail
    ProcedureReturn                ; full; drop
  EndIf
  gConIn[gConInHead] = c & $FF
  gConInHead = nxt
EndProcedure

Procedure netcon_PutBE16(p.i, v.i)
  PokeB(p + 0, (v >> 8) & $FF)
  PokeB(p + 1, v & $FF)
EndProcedure

Procedure netcon_PutBE32(p.i, v.i)
  PokeB(p + 0, (v >> 24) & $FF)
  PokeB(p + 1, (v >> 16) & $FF)
  PokeB(p + 2, (v >> 8) & $FF)
  PokeB(p + 3, v & $FF)
EndProcedure

; The IPv4 header checksum over the twenty bytes at `ip`, with the
; checksum field itself already zero. RFC 1071.
Procedure.i netcon_IpChecksum(ip.i)
  Define sum.i
  Define i.i
  sum = 0
  i = 0
  While i < 20
    sum = sum + ((PeekA(ip + i) << 8) | PeekA(ip + i + 1))
    i = i + 2
  Wend
  While (sum >> 16) <> 0
    sum = (sum & $FFFF) + (sum >> 16)
  Wend
  ProcedureReturn (sum ! $FFFF) & $FFFF
EndProcedure

; ----------------------------------------------------------------------
;  netcon_BuildUdp - one console datagram to the peer, in gConTx.
;
;  Returns the frame length, or 0 if there is no peer or no link. The
;  destination hardware address is the peer's own, captured from the
;  datagram it sent us, so nothing here consults or needs a neighbour
;  cache.
;
;  THE LENGTH IS CAPPED AGAINST THE LINK IN USE, ASKED AT RUN TIME. The
;  radio's transmit buffer is smaller than a classic Ethernet frame and
;  its driver REFUSES anything longer rather than truncating it, which is
;  right; the cap here is so the refusal never has to happen.
; ----------------------------------------------------------------------
Procedure.i netcon_BuildUdpTo(src.i, len.i, kind.i, localIp.i, peerIp.i, peerPort.i, peerMac.i)
  Define p.i
  Define ip.i
  Define u.i
  Define i.i
  Define room.i
  Define src6.i
  ; THE PEER'S OWN INTERFACE, NOT THE PREFERRED ONE. gConKind names the
  ; interface the console ANNOUNCES; a peer may be on the other one, and
  ; building its reply with the announced interface's hardware address
  ; and address is how a board answers a laptop on its cable as if it
  ; were the access point.
  If kind = #HW_LINK_NONE Or peerMac = 0
    ProcedureReturn 0
  EndIf
  src6 = HwLinkMacPtr(kind)
  If src6 = 0
    ProcedureReturn 0
  EndIf
  room = HwLinkTxMax(kind) - (14 + 20 + 8)
  If room > #NETCON_OUT_MAX
    room = #NETCON_OUT_MAX
  EndIf
  If room <= 0
    ProcedureReturn 0
  EndIf
  If len > room
    len = room
  EndIf
  p = @gConTx[0]
  For i = 0 To 5
    PokeB(p + i, PeekA(peerMac + i))
    PokeB(p + 6 + i, PeekA(src6 + i))
  Next
  PokeB(p + 12, $08)
  PokeB(p + 13, $00)
  ip = p + 14
  For i = 0 To 19
    PokeB(ip + i, 0)
  Next
  PokeB(ip + 0, $45)
  netcon_PutBE16(ip + 2, 20 + 8 + len)
  netcon_PutBE16(ip + 4, $C0DE)
  PokeB(ip + 8, 64)
  PokeB(ip + 9, 17)
  netcon_PutBE32(ip + 12, localIp)
  netcon_PutBE32(ip + 16, peerIp)
  netcon_PutBE16(ip + 10, netcon_IpChecksum(ip))
  u = p + 34
  netcon_PutBE16(u + 0, #NETCON_PORT)
  netcon_PutBE16(u + 2, peerPort)
  netcon_PutBE16(u + 4, 8 + len)
  netcon_PutBE16(u + 6, 0)          ; UDP checksum optional over IPv4
  For i = 0 To len - 1
    PokeB(u + 8 + i, PeekA(src + i))
  Next

  ; ==================================================================
  ;  PAD TO THE 60-OCTET MINIMUM FRAME. A SHORT CONSOLE REPLY IS A RUNT
  ;  AND A RUNT IS DISCARDED.
  ; ==================================================================
  ;  MEASURED OVER THE CABLE, 2026-09-07, and it took most of an evening
  ;  because the symptom looks like an intermittent console rather than
  ;  an arithmetic one:
  ;
  ;    `uptime`  seven lines            arrived, every one
  ;    `net`     thirty lines           arrived
  ;    `echo hello world this is ...`   arrived, 70 octets of payload
  ;    `echo AA`                        NOTHING, ever
  ;    `pmf> `   the prompt             NOTHING, ever, in any capture
  ;
  ;  14 + 20 + 8 = 42 octets of headers, so a payload of 18 makes a
  ;  60-octet frame and anything shorter is BELOW THE MINIMUM 802.3
  ;  FRAME. "pmf> " is five characters - a 47-octet frame - and "echo
  ;  AA" plus its echo is 18, right on the edge. Runts are discarded,
  ;  silently, by everything on the path.
  ;
  ;  THE CONSEQUENCE WAS NOT COSMETIC. "pmf> " is the protocol string
  ;  four host tools wait for, so the ONE string they need was the one
  ;  string short enough to always be dropped: `pi4_upload.py --console
  ;  net` gave up with "no Anvil prompt" against a board answering
  ;  `version` on that address in the same second, and it would have
  ;  gone on doing that for ever.
  ;
  ;  IT NEVER SHOWED OVER THE RADIO, which is why it survived from the
  ;  day this file was written: 802.11 has no 60-octet minimum and the
  ;  CYW43's firmware builds its own frame, so the wireless console has
  ;  always delivered its short lines. One file, two links, and the fault
  ;  only exists on one of them.
  ;
  ;  THE PAD IS INVISIBLE TO THE RECEIVER and this is not a trick: the
  ;  IP total-length field above says 20 + 8 + len and the UDP length
  ;  says 8 + len, both already written, so a receiver takes exactly
  ;  `len` octets of payload and ignores whatever follows. It is what
  ;  RaspberryPi4/Lib/net.pi4's net_Finish has always done for every
  ;  frame IT builds - the zeroing loop and the #NET_FRAME_MIN it
  ;  compares against - and this builder simply never had it. The pad is
  ;  ZEROED rather than left as whatever was in the buffer, because
  ;  otherwise every short reply would carry a few octets of the last
  ;  long one off the board.
  ; ------------------------------------------------------------------
  ;  The buffer is 14 + 20 + 8 + #NETCON_OUT_MAX octets, so a pad to 60
  ;  is in bounds for every length this can produce, the empty one
  ;  included.
  i = 14 + 20 + 8 + len
  While i < 60
    PokeB(p + i, 0)
    i = i + 1
  Wend
  ProcedureReturn i
EndProcedure

Procedure.i netcon_BuildUdp(src.i, len.i)
  If gConPeerOk = 0 Or gConOwner <> #NETCON_OWNER_NET
    ProcedureReturn 0
  EndIf
  ProcedureReturn netcon_BuildUdpTo(src, len, gConPeerKind, gConPeerDstIp, gConPeerIp, gConPeerPort, @gConPeerMac[0])
EndProcedure

Procedure.i netcon_PeerMatches(*frame, kind.i)
  Define i.i
  If gConOwner <> #NETCON_OWNER_NET Or gConPeerOk = 0
    ProcedureReturn 0
  EndIf
  If kind <> gConPeerKind Or NetRxTo() <> gConPeerDstIp
    ProcedureReturn 0
  EndIf
  If NetUdpRxFrom() <> gConPeerIp Or NetUdpRxPort() <> gConPeerPort
    ProcedureReturn 0
  EndIf
  For i = 0 To 5
    If PeekA(*frame + 6 + i) <> gConPeerMac[i]
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure netcon_ForgetOwner()
  Define i.i
  gConOwner = #NETCON_OWNER_NONE
  gConPeerOk = 0
  gConPeerIp = 0
  gConPeerPort = 0
  gConPeerKind = #HW_LINK_NONE
  gConPeerDstIp = 0
  gConInHead = 0
  gConInTail = 0
  For i = 0 To 5 : gConPeerMac[i] = 0 : Next
EndProcedure

; Reply to a rejected endpoint without ever copying it into the active
; owner row. Delayed command queuing is intentionally absent: a host may
; retry after timeout, and executing the original later could duplicate a
; destructive operation.
Procedure netcon_SendBusy(*frame, kind.i)
  Define fn.i
  gConBusy[0] = 66 : gConBusy[1] = 85 : gConBusy[2] = 83 : gConBusy[3] = 89
  gConBusy[4] = 13 : gConBusy[5] = 10
  fn = netcon_BuildUdpTo(@gConBusy[0], 6, kind, NetRxTo(), NetUdpRxFrom(), NetUdpRxPort(), *frame + 6)
  If fn > 0
    HwLinkSend(kind, @gConTx[0], fn, 100)
  EndIf
EndProcedure

Procedure netcon_CaptureOwner(*frame, kind.i)
  Define i.i
  gConOwner = #NETCON_OWNER_NET
  gConPeerIp = NetUdpRxFrom()
  gConPeerPort = NetUdpRxPort()
  gConPeerKind = kind
  gConPeerDstIp = NetRxTo()
  gConPeerOk = 1
  For i = 0 To 5 : gConPeerMac[i] = PeekA(*frame + 6 + i) : Next
EndProcedure

; Put whatever the IP layer staged ONTO THE INTERFACE THE FRAME THAT
; caused it arrived on. Used for the ARP and ICMP replies NetInput
; builds, and for the DHCP server's OFFER and ACK, while the console
; pump is the thing consuming frames.
;
; THE KIND IS AN ARGUMENT AND NOT gConKind. An ARP reply for the cable's
; address sent out of the radio is a frame the access point drops and
; the asker never sees, and the board would report having answered.
Procedure.i netcon_SendStaged(kind.i)
  Define n.i
  n = NetOutLen()
  If n <= 0
    ProcedureReturn 0
  EndIf
  If kind = #HW_LINK_NONE
    gConTxFail = gConTxFail + 1
    ProcedureReturn 0
  EndIf
  If HwLinkSend(kind, NetOutBuf(), n, 100) <> 1
    gConTxFail = gConTxFail + 1
    ProcedureReturn 0
  EndIf
  gConTxOk = gConTxOk + 1
  ProcedureReturn 1
EndProcedure

Procedure.i NetConsoleTxCount()
  ProcedureReturn gConTxOk
EndProcedure

Procedure.i NetConsoleTxFails()
  ProcedureReturn gConTxFail
EndProcedure

; ----------------------------------------------------------------------
;  NetConsoleFlush - send whatever the aux tap captured to the peer.
;
;  Called from the pump at the prompt AND, per line, from the UART during
;  a long command's output (through UartAuxSetFlush) so nothing overflows
;  the mirror ring. IT MUST NOT PRINT - it can run inside UartWrite - and
;  it is re-entry guarded so a print from deep in the send path cannot
;  recurse back into it.
; ----------------------------------------------------------------------
Procedure NetConsoleFlush()
  Define c.i
  Define nOut.i
  Define fn.i
  If gConOn = 0 Or gConFlushing <> 0
    ProcedureReturn
  EndIf
  gConFlushing = 1
  ; With no peer, still drain so the ring cannot fill and start dropping.
  If gConPeerOk = 0
    c = UartAuxGet()
    While c >= 0
      c = UartAuxGet()
    Wend
    gConFlushing = 0
    ProcedureReturn
  EndIf
  ; Drain the WHOLE ring, a datagram at a time. Ordinary per-line output
  ; leaves one short line here and this sends a single datagram; a
  ; coalesced bulk dump (the screenshot) leaves several KB and this sends
  ; it as back-to-back full datagrams IN ORDER, so the terminator the
  ; emitter prints after the last run really does follow every run on the
  ; wire rather than being stranded behind an un-flushed tail.
  Repeat
    nOut = 0
    While nOut < #NETCON_OUT_MAX
      c = UartAuxGet()
      If c < 0
        Break
      EndIf
      gConOut[nOut] = c
      nOut = nOut + 1
    Wend
    If nOut = 0
      Break
    EndIf
    fn = netcon_BuildUdp(@gConOut[0], nOut)
    If fn > 0
      ; OUT OF THE PEER'S OWN INTERFACE, NOT THE ANNOUNCED ONE. This is
      ; where the board's OUTPUT goes back to whoever is driving it, and
      ; a board with a cable and a radio both addressed has two doors: a
      ; peer that spoke over the radio and is answered out of the cable
      ; gets nothing, and the board reports having answered. gConKind
      ; was right while the console could only be in one place, and the
      ; gate catches this one directly - a64_wificon_check case D.
      HwLinkSend(gConPeerKind, @gConTx[0], fn, 100)
    EndIf
    If uart_auxBulk <> 0
      delayMicroseconds(#NETCON_PACE_US)
    EndIf
  ForEver
  gConFlushing = 0
EndProcedure

; ----------------------------------------------------------------------
;  NetConsoleTakeUdp - is this datagram the console's? 1 if it took it.
;
;  Called ONLY after NetInput has returned #NET_IN_UDP for the frame at
;  *frame, from the console's own pump and from the link layer's pump
;  through the board's HwLinkOfferUdp.
;
;  THE DESTINATION PORT IS CHECKED HERE, AND IT COST AN EVENING. Until
;  2026-09-04 this ran for ANY datagram the IP layer delivered, on the
;  reasoning that the bound port had already decided. That was true while
;  the console was the only thing that ever bound a port. It stopped being
;  true the moment ping, dns and dhcp started riding the same pump: each
;  binds a port of its own, so the datagram arriving is THEIR reply - and
;  it was being swallowed into the keystroke ring instead of delivered to
;  them. The symptom was comic and the diagnosis was in it: `dns
;  example.com` timed out and the prompt filled with `fexample`, `comhB` -
;  the LABELS out of the DNS reply, arriving as if somebody had typed
;  them.
; ----------------------------------------------------------------------
Procedure.i NetConsoleTakeUdp(*frame, kind.i)
  Define i.i
  Define plen.i
  Define pd.i
  If gConOn = 0
    ProcedureReturn 0
  EndIf
  If NetUdpRxDstPort() <> #NETCON_PORT
    ProcedureReturn 0
  EndIf
  If gConOwner = #NETCON_OWNER_NONE
    netcon_CaptureOwner(*frame, kind)
  ElseIf netcon_PeerMatches(*frame, kind) = 0
    netcon_SendBusy(*frame, kind)
    ProcedureReturn 1
  EndIf
  plen = NetUdpRxLen()
  pd = NetUdpRxData()
  For i = 0 To plen - 1
    netcon_InPush(PeekA(pd + i))
  Next
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  NetConsoleOfferUdp - WHO OWNS THIS UDP DATAGRAM?
;
;      0   nobody here - it belongs to whatever command bound that port
;      1   the console took it, and there is nothing to send
;      2   a SERVICE took it and has STAGED a reply the caller must send
;
;  IT EXISTS BECAUSE THERE ARE TWO PUMPS AND THERE MUST NOT BE TWO
;  ANSWERS. This file's own pump reads every addressed interface at the
;  prompt; RaspberryPi4/Lib/link.pi4's LinkPumpNet reads the selected one
;  from TcpTick() on the same spin. They RACE for each frame, so a
;  datagram this board owns has to be recognised identically whichever
;  one gets it - and on 2026-09-07 it was not: the DHCP server was fed
;  from this file's pump alone, so a laptop's DISCOVER that LinkPumpNet
;  happened to take was silently dropped and `ipconfig /renew` timed out
;  against a board that was serving addresses.
;
;  THE SERVICE PORT IS ANSWERED EVEN WHEN THE SERVER DECLINES. Port 67 is
;  never the console's, whatever dhcpd.pbi makes of the message, so a
;  BOOTP frame this board will not answer is still not fed into the
;  command input as keystrokes - which is the defect that put a DNS
;  reply on the prompt as typed characters in the first place.
; ----------------------------------------------------------------------
Procedure.i NetConsoleOfferUdp(*frame, kind.i)
  If NetUdpRxDstPort() = #DHCP_PORT_SERVER
    If DhcpdInput(kind, NetUdpRxData(), NetUdpRxLen(), NetUdpRxFrom()) <> 0
      ProcedureReturn 2
    EndIf
    ProcedureReturn 1
  EndIf
  ProcedureReturn NetConsoleTakeUdp(*frame, kind)
EndProcedure

Procedure netcon_SendOwnerBusy()
  Define fn.i
  If gConOwner <> #NETCON_OWNER_NET Or gConPeerOk = 0
    ProcedureReturn
  EndIf
  gConBusy[0] = 66 : gConBusy[1] = 85 : gConBusy[2] = 83 : gConBusy[3] = 89
  gConBusy[4] = 13 : gConBusy[5] = 10
  fn = netcon_BuildUdpTo(@gConBusy[0], 6, gConPeerKind, gConPeerDstIp, gConPeerIp, gConPeerPort, @gConPeerMac[0])
  If fn > 0
    HwLinkSend(gConPeerKind, @gConTx[0], fn, 100)
  EndIf
EndProcedure

; The local serial/keyboard console is an explicit owner too. It wins on
; the first local character, but does so safely: a partial network line is
; discarded and its peer is told BUSY, never left queued for later.
Procedure NetConsoleClaimLocal()
  If gConOwner = #NETCON_OWNER_LOCAL
    ProcedureReturn
  EndIf
  If gConOwner = #NETCON_OWNER_NET
    netcon_SendOwnerBusy()
    netcon_ForgetOwner()
  EndIf
  gConOwner = #NETCON_OWNER_LOCAL
EndProcedure

; Called after the completed command's prompt has been flushed. This is
; the only normal release point, so error returns and every command arm
; converge without each handler having to remember session cleanup.
Procedure NetConsoleCommandDone()
  netcon_ForgetOwner()
EndProcedure

; One automatic protocol dispatcher for every hardware consumer. ARP and
; ICMP replies, TCP, the DHCP service and console UDP therefore have one
; ownership decision. Command-owned UDP returns 0 to its waiting caller.
Procedure.i NetServiceInput(kind.i, *frame, rc.i)
  Define own.i
  If rc = #NET_IN_REPLY
    netcon_SendStaged(kind)
    ProcedureReturn 1
  EndIf
  If rc = #NET_IN_TCP
    TcpInput()
    ProcedureReturn 1
  EndIf
  If rc = #NET_IN_UDP
    ; Port 68 belongs to the per-interface DHCP client while that row has
    ; an active transaction or lease. Parse it here, in the one dispatcher,
    ; then leave only an action value behind: the CYW43 receive pointer is
    ; invalidated by the next read and must never be queued itself.
    If NetUdpRxPort() = #DHCP_PORT_SERVER And NetUdpRxDstPort() = #DHCP_PORT_CLIENT
      If DhcpClientState(kind) <> #DHCPC_INIT
        DhcpClientInput(kind, NetUdpRxData(), NetUdpRxLen(), millis())
        ProcedureReturn 1
      EndIf
    EndIf
    ; DNS/SNTP ownership is exact-interface and exact-tuple. This callback
    ; validates and copies bounded state only; packet construction and sends
    ; remain in NtpServiceTick after receive scratch is no longer live.
    If NtpServiceInput(kind) <> 0
      ProcedureReturn 1
    EndIf
    own = NetConsoleOfferUdp(*frame, kind)
    If own = 2
      netcon_SendStaged(kind)
    EndIf
    If own <> 0
      ProcedureReturn 1
    EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

; ======================================================================
; PER-INTERFACE DHCP LEASE WORKER
; ======================================================================
; Optional cooperative service for bounded foreground network waits. The
; callback is deliberately not a network pump: the board may use it to paint
; an already-up display after a complete receive/protocol iteration. It must
; not call back into networking. Unset is inert, and the busy guard refuses a
; recursive service call.
#NETWAIT_PROGRESS_MS = 50
Global *gNetWaitProgressHook = 0
Global gNetWaitProgressBusy.i = 0
Global gNetWaitProgressAt.i = 0

Procedure.i NetWaitSetProgressHook(*fn)
  Define old.i
  old = *gNetWaitProgressHook
  *gNetWaitProgressHook = *fn
  gNetWaitProgressBusy = 0
  If *fn <> 0
    ; Make the first completed iteration due immediately. All arithmetic is
    ; in the 32-bit millis domain so registration beside a wrap is ordinary.
    gNetWaitProgressAt = (millis() - #NETWAIT_PROGRESS_MS) & $FFFFFFFF
  EndIf
  ProcedureReturn old
EndProcedure

Procedure netwait_Progress()
  Define now.i
  Define elapsed.i
  If *gNetWaitProgressHook = 0 Or gNetWaitProgressBusy <> 0
    ProcedureReturn
  EndIf
  now = millis() & $FFFFFFFF
  elapsed = (now - gNetWaitProgressAt) & $FFFFFFFF
  If elapsed < #NETWAIT_PROGRESS_MS
    ProcedureReturn
  EndIf
  gNetWaitProgressAt = now
  gNetWaitProgressBusy = 1
  gNetWaitProgressHook()
  gNetWaitProgressBusy = 0
EndProcedure

; The codec/state machine owns protocol validity; this layer owns only
; transport and applying a completed transition. It runs from the prompt
; and never waits. One pending action per interface is retried until an
; ACK changes the state or the next RFC deadline changes the action.
#NETDHCP_RETRY_BASE_MS = 4000
#NETDHCP_RETRY_MAX_MS  = 64000
; RFC 2131 section 3.2 gives retransmitting over about one minute as an
; example bound for verifying a remembered configuration. A server with no
; record of this client MUST stay silent (section 4.3.2), so REBOOT cannot
; use the ordinary indefinitely-capped retry cadence. The RFC permits reuse
; of the unexpired address after that silence; Anvil deliberately chooses
; the conservative alternative and discovers afresh rather than using an
; address the present network never confirmed.
#NETDHCP_REBOOT_WINDOW_MS = 60000
Global Dim netdhcp_pending.a[#DHCPC_IFS]
Global Dim netdhcp_sentAt.i[#DHCPC_IFS]
Global Dim netdhcp_sent.a[#DHCPC_IFS]
Global Dim netdhcp_due.i[#DHCPC_IFS]
Global Dim netdhcp_attempts.i[#DHCPC_IFS]
Global Dim netdhcp_phaseAt.i[#DHCPC_IFS]
Global Dim netdhcp_auto.a[#DHCPC_IFS]
Global Dim netdhcp_tx.i[#DHCPC_IFS]
Global Dim netdhcp_txFail.i[#DHCPC_IFS]
Global Dim netdhcp_binds.i[#DHCPC_IFS]
Global Dim netdhcp_drops.i[#DHCPC_IFS]

Procedure.i netdhcp_IsDue(now.i, due.i)
  ProcedureReturn (((now - due) & $FFFFFFFF) < $80000000)
EndProcedure

; RFC 2131's selecting retransmission starts at about four seconds,
; doubles, and stops growing at 64 seconds. The transaction/interface XID
; supplies deterministic +/-1 second jitter, so simultaneous interfaces
; and neighbouring boards do not settle into a broadcast lockstep.
Procedure.i netdhcp_RetryDelay(kind.i, action.i)
  Define base.i
  Define jitter.i
  Define left.i
  If action = #DHCPC_ACT_RENEW
    left = DhcpClientT2Left(kind)
  ElseIf action = #DHCPC_ACT_REBIND
    left = DhcpClientLeaseLeft(kind)
  EndIf
  If left > 0
    ; Retry halfway to the next state deadline. Cap at sixty seconds so a
    ; long lease does not wait hours after one lost request; never schedule
    ; beyond the deadline that DhcpClientTick enforces independently.
    base = (left * 1000) / 2
    If base > 60000 : base = 60000 : EndIf
    If base < 1000 : base = 1000 : EndIf
    ProcedureReturn base
  EndIf
  base = #NETDHCP_RETRY_BASE_MS
  If netdhcp_attempts[kind] > 5
    ; The fifth retry is already 64 seconds. Do not shift by an
    ; ever-growing count during a long outage: large shifts wrap or are
    ; target-dependent, while the protocol wants a stable capped cadence.
    base = #NETDHCP_RETRY_MAX_MS
  ElseIf netdhcp_attempts[kind] > 1
    base = base << (netdhcp_attempts[kind] - 1)
  EndIf
  If base > #NETDHCP_RETRY_MAX_MS
    base = #NETDHCP_RETRY_MAX_MS
  EndIf
  jitter = ((DhcpClientXid(kind) ! (netdhcp_attempts[kind] * 1103515245)) & $7FF) - 1024
  base = base + jitter
  If base < 1000 : base = 1000 : EndIf
  If base > #NETDHCP_RETRY_MAX_MS : base = #NETDHCP_RETRY_MAX_MS : EndIf
  ProcedureReturn base
EndProcedure

Procedure.i netdhcp_Send(kind.i, action.i)
  Define n.i
  Define hop.i
  Define src.i
  n = DhcpClientBuild(kind, action)
  If n <= 0
    ProcedureReturn 0
  EndIf
  If action = #DHCPC_ACT_RENEW
    ; RENEWING is unicast to the granting server. If its next-hop MAC has
    ; aged out, stage one ARP request and let the retry cadence try the
    ; DHCP request again after the reply has repopulated the cache.
    If NetUdpBuild(kind, DhcpClientServer(kind), #DHCP_PORT_SERVER, #DHCP_PORT_CLIENT, DhcpBuf(), n) = 0
      If NetError() = #NET_E_NO_ARP
        hop = NetNextHop(kind, DhcpClientServer(kind))
        If hop <> 0 And NetArpRequest(kind, hop) <> 0
          netcon_SendStaged(kind)
        EndIf
      EndIf
      ProcedureReturn 0
    EndIf
  Else
    src = 0
    If action = #DHCPC_ACT_REBIND
      src = DhcpClientIp(kind)
    EndIf
    If NetUdpBuildBcast(kind, src, #DHCP_PORT_SERVER, #DHCP_PORT_CLIENT, DhcpBuf(), n) = 0
      ProcedureReturn 0
    EndIf
  EndIf
  ProcedureReturn netcon_SendStaged(kind)
EndProcedure

Procedure netdhcp_Drop(kind.i)
  netdhcp_pending[kind] = #DHCPC_ACT_NONE
  netdhcp_sent[kind] = 0
  NetDhcpMode(kind, 0)
  ; A failed attempt does not revoke an independently configured saved or
  ; RFC3927 address. Only a lease transition can invalidate a lease.
  If NetIfSrc(kind) = #NET_ADDR_LEASE
    NetAddressLost(kind)
  EndIf
  netdhcp_drops[kind] = netdhcp_drops[kind] + 1
EndProcedure

Procedure.i NetDhcpStart(kind.i, automatic.i)
  Define action.i
  If kind <= 0 Or kind >= #DHCPC_IFS Or HwLinkHas(kind) = 0
    ProcedureReturn 0
  EndIf
  If DhcpdOn() <> 0 And DhcpdKind() = kind
    ProcedureReturn -1
  EndIf
  netdhcp_auto[kind] = automatic & 1
  If DhcpClientState(kind) <> #DHCPC_INIT
    ProcedureReturn 1
  EndIf
  If HwLinkReady(kind) = 0 Or HwLinkMacPtr(kind) = 0
    ProcedureReturn 0
  EndIf
  NetSetMac(kind, HwLinkMacPtr(kind))
  If NetUdpListen(kind, #DHCP_PORT_CLIENT, 1) = 0
    ProcedureReturn 0
  EndIf
  NetDhcpMode(kind, 1)
  action = DhcpClientBegin(kind, HwLinkMacPtr(kind), millis())
  If action <> #DHCPC_ACT_DISCOVER
    NetUdpListen(kind, #DHCP_PORT_CLIENT, 0)
    NetDhcpMode(kind, 0)
    ProcedureReturn 0
  EndIf
  netdhcp_pending[kind] = action
  netdhcp_sent[kind] = 0
  netdhcp_attempts[kind] = 0
  netdhcp_due[kind] = millis()
  netdhcp_phaseAt[kind] = netdhcp_due[kind]
  ProcedureReturn 1
EndProcedure

Procedure NetDhcpCancel(kind.i)
  If kind <= 0 Or kind >= #DHCPC_IFS
    ProcedureReturn
  EndIf
  netdhcp_auto[kind] = 0
  netdhcp_pending[kind] = #DHCPC_ACT_NONE
  netdhcp_sent[kind] = 0
  netdhcp_attempts[kind] = 0
  netdhcp_phaseAt[kind] = 0
  NetDhcpMode(kind, 0)
  NetUdpListen(kind, #DHCP_PORT_CLIENT, 0)
  DhcpClientReset(kind)
EndProcedure

; Explicit carrier-loss edge for a driver that tears down and restores an
; association inside one prompt turn. Without this edge the periodic tick
; could observe only the restored link and incorrectly keep using the old
; address without INIT-REBOOT verification.
Procedure NetDhcpLinkDown(kind.i)
  If kind <= 0 Or kind >= #DHCPC_IFS
    ProcedureReturn
  EndIf
  If DhcpClientTick(kind, millis(), 0) = #DHCPC_ACT_DROP
    netdhcp_Drop(kind)
  EndIf
EndProcedure

Procedure NetDhcpTick()
  Define kind.i
  Define state.i
  Define event.i
  Define action.i
  Define now.i
  now = millis()
  For kind = 1 To #DHCPC_IFS - 1
    If HwLinkHas(kind) = 0
      Continue
    EndIf
    state = DhcpClientState(kind)
    event = DhcpClientTakeEvent(kind)
    If state = #DHCPC_INIT And event = #DHCPC_ACT_NONE
      If netdhcp_auto[kind] <> 0 And HwLinkReady(kind) <> 0
        NetDhcpStart(kind, 1)
      EndIf
      Continue
    EndIf
    If event = #DHCPC_ACT_BOUND
      netdhcp_pending[kind] = #DHCPC_ACT_NONE
      netdhcp_sent[kind] = 0
      netdhcp_attempts[kind] = 0
      NetDhcpMode(kind, 0)
      If NetSetIPv4(kind, DhcpClientIp(kind), DhcpClientMask(kind), DhcpClientGateway(kind)) <> 0
        NetAddressBound(kind, DhcpClientIp(kind), DhcpClientMask(kind), DhcpClientGateway(kind), #NET_ADDR_LEASE)
        netdhcp_binds[kind] = netdhcp_binds[kind] + 1
      Else
        DhcpClientReset(kind)
        NetUdpListen(kind, #DHCP_PORT_CLIENT, 0)
        NetAddressLost(kind)
        Continue
      EndIf
    ElseIf event = #DHCPC_ACT_SELECT
      netdhcp_pending[kind] = #DHCPC_ACT_SELECT
      netdhcp_sent[kind] = 0
      netdhcp_attempts[kind] = 0
      netdhcp_phaseAt[kind] = now
    ElseIf event = #DHCPC_ACT_DROP
      netdhcp_Drop(kind)
      state = DhcpClientState(kind)
      If netdhcp_auto[kind] <> 0 And state = #DHCPC_INIT And HwLinkReady(kind) <> 0
        If DhcpdOn() = 0 Or DhcpdKind() <> kind
          NetSetMac(kind, HwLinkMacPtr(kind))
          NetUdpListen(kind, #DHCP_PORT_CLIENT, 1)
          NetDhcpMode(kind, 1)
          netdhcp_pending[kind] = DhcpClientBegin(kind, HwLinkMacPtr(kind), now)
          netdhcp_sent[kind] = 0
          netdhcp_attempts[kind] = 0
          netdhcp_phaseAt[kind] = now
        EndIf
      EndIf
    EndIf

    action = DhcpClientTick(kind, now, HwLinkReady(kind))
    If action = #DHCPC_ACT_DROP
      netdhcp_Drop(kind)
      If netdhcp_auto[kind] <> 0 And DhcpClientState(kind) = #DHCPC_INIT And HwLinkReady(kind) <> 0
        If DhcpdOn() = 0 Or DhcpdKind() <> kind
          NetSetMac(kind, HwLinkMacPtr(kind))
          NetUdpListen(kind, #DHCP_PORT_CLIENT, 1)
          NetDhcpMode(kind, 1)
          netdhcp_pending[kind] = DhcpClientBegin(kind, HwLinkMacPtr(kind), now)
          netdhcp_sent[kind] = 0
          netdhcp_attempts[kind] = 0
          netdhcp_phaseAt[kind] = now
        EndIf
      EndIf
      Continue
    EndIf
    If action <> #DHCPC_ACT_NONE
      netdhcp_pending[kind] = action
      netdhcp_sent[kind] = 0
      netdhcp_attempts[kind] = 0
      netdhcp_phaseAt[kind] = now
      If action = #DHCPC_ACT_REBOOT
        NetDhcpMode(kind, 1)
      EndIf
    EndIf

    action = netdhcp_pending[kind]
    ; A silent INIT-REBOOT server is not evidence that the remembered
    ; address is valid. Once the bounded verification window closes,
    ; discard that protocol state and start a new DISCOVER with a new XID.
    ; NetConsolePump runs before this worker at the prompt, so a valid ACK
    ; already received at the deadline has become BOUND above and wins.
    If action = #DHCPC_ACT_REBOOT
      If ((now - netdhcp_phaseAt[kind]) & $FFFFFFFF) >= #NETDHCP_REBOOT_WINDOW_MS
        DhcpClientReset(kind)
        NetSetMac(kind, HwLinkMacPtr(kind))
        NetUdpListen(kind, #DHCP_PORT_CLIENT, 1)
        NetDhcpMode(kind, 1)
        action = DhcpClientBegin(kind, HwLinkMacPtr(kind), now)
        netdhcp_pending[kind] = action
        netdhcp_sent[kind] = 0
        netdhcp_attempts[kind] = 0
        netdhcp_phaseAt[kind] = now
      EndIf
    EndIf
    If action <> #DHCPC_ACT_NONE
      If netdhcp_sent[kind] = 0 Or netdhcp_IsDue(now, netdhcp_due[kind]) <> 0
        If netdhcp_Send(kind, action) <> 0
          netdhcp_tx[kind] = netdhcp_tx[kind] + 1
        Else
          netdhcp_txFail[kind] = netdhcp_txFail[kind] + 1
        EndIf
        netdhcp_sentAt[kind] = now
        netdhcp_sent[kind] = 1
        netdhcp_attempts[kind] = netdhcp_attempts[kind] + 1
        netdhcp_due[kind] = (now + netdhcp_RetryDelay(kind, action)) & $FFFFFFFF
      EndIf
    EndIf
  Next
EndProcedure

; Bounded foreground wait used by boot and the `dhcp` command. It advances
; the same machine and dispatcher the prompt uses; it never parses a packet
; itself. keepRunning leaves an unanswered exchange to recover in the
; background (Wi-Fi boot). A manual command can cancel it without changing
; a pre-existing saved or link-local address.
Procedure.i NetDhcpAcquire(kind.i, waitMs.i, keepRunning.i)
  Define start.i
  If NetDhcpStart(kind, keepRunning) <= 0
    ProcedureReturn 0
  EndIf
  start = millis()
  Repeat
    netcon_PumpOne(kind)
    NetDhcpTick()
    ; Both calls above have returned: no receive pointer or partially handled
    ; protocol transition is live across the cooperative service boundary.
    netwait_Progress()
    If DhcpClientState(kind) = #DHCPC_BOUND And NetIfSrc(kind) = #NET_ADDR_LEASE
      ; A successfully acquired lease is always maintained and reacquired
      ; after expiry; keepRunning controls only an unanswered foreground
      ; attempt, not whether a valid lease deserves renewal.
      netdhcp_auto[kind] = 1
      ProcedureReturn 1
    EndIf
    If ((millis() - start) & $FFFFFFFF) >= waitMs
      If keepRunning = 0
        NetDhcpCancel(kind)
      EndIf
      ProcedureReturn 0
    EndIf
  ForEver
EndProcedure

Procedure.i NetDhcpAutomatic(kind.i)
  If kind <= 0 Or kind >= #DHCPC_IFS : ProcedureReturn 0 : EndIf
  ProcedureReturn netdhcp_auto[kind]
EndProcedure

Procedure.i NetDhcpAttempts(kind.i)
  If kind <= 0 Or kind >= #DHCPC_IFS : ProcedureReturn 0 : EndIf
  ProcedureReturn netdhcp_attempts[kind]
EndProcedure

Procedure.i NetDhcpStateText(kind.i)
  Select DhcpClientState(kind)
    Case #DHCPC_INIT       : ProcedureReturn "idle"
    Case #DHCPC_SELECTING  : ProcedureReturn "selecting"
    Case #DHCPC_REQUESTING : ProcedureReturn "requesting"
    Case #DHCPC_BOUND      : ProcedureReturn "bound"
    Case #DHCPC_RENEWING   : ProcedureReturn "renewing"
    Case #DHCPC_REBINDING  : ProcedureReturn "rebinding"
    Case #DHCPC_OFFLINE    : ProcedureReturn "offline (lease retained only for INIT-REBOOT)"
    Case #DHCPC_REBOOTING  : ProcedureReturn "INIT-REBOOT verification"
  EndSelect
  ProcedureReturn "invalid"
EndProcedure

Procedure NetDhcpSay(kind.i)
  Print("  DHCP client: ")
  UartWriteStr(NetDhcpStateText(kind))
  Print(", automatic ")
  If netdhcp_auto[kind] <> 0 : Print("on") : Else : Print("off") : EndIf
  Print(", XID ") : PutHex8(DhcpClientXid(kind)) : PrintNl()
  Print("    sends ") : PrintDec(netdhcp_tx[kind])
  Print(", send failures ") : PrintDec(netdhcp_txFail[kind])
  Print(", current attempts ") : PrintDec(netdhcp_attempts[kind])
  Print(", accepted binds ") : PrintDec(netdhcp_binds[kind])
  Print(", drops ") : PrintDec(netdhcp_drops[kind]) : PrintNl()
  If DhcpClientState(kind) >= #DHCPC_BOUND
    Print("    address ") : PutIp(DhcpClientIp(kind))
    Print(", server ") : PutIp(DhcpClientServer(kind))
    If DhcpClientNtp(kind) <> 0
      Print(", NTP ") : PutIp(DhcpClientNtp(kind))
    EndIf
    PrintNl()
    Print("    lease ") : PrintDec(DhcpClientLeaseLeft(kind))
    Print("/") : PrintDec(DhcpClientLease(kind))
    Print(" s; T1 ") : PrintDec(DhcpClientT1Left(kind))
    Print("/") : PrintDec(DhcpClientT1(kind))
    Print(" s; T2 ") : PrintDec(DhcpClientT2Left(kind))
    Print("/") : PrintDec(DhcpClientT2(kind)) : PrintN(" s")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  NetConsolePump - one slice: frames in, output out.
;
;  Rate limited to 5 ms because on a radio this is a bus poll in the
;  prompt's tightest spin, and a console does not need finer.
;
;  GATE ON NetInput's RETURN VALUE, NOT ON NetUdpRxLen(). NetUdpRxLen
;  keeps the LAST datagram's length across later frames, so testing it
;  made every subsequent broadcast - ARP, mDNS, router chatter - re-feed
;  the stale command. One `uptime` ran sixty-six times.
; ----------------------------------------------------------------------
; ----------------------------------------------------------------------
;  netcon_PumpOne - ONE INTERFACE, ONE FRAME.
;
;  THE INTERFACE THE FRAME ARRIVED ON IS HANDED TO NetInput AND IS THE
;  WHOLE POINT OF THE PER-INTERFACE LAYER. net.pi4 holds one address row
;  per interface - hardware address and IPv4 address together - and
;  parses this frame AS that row. So an ARP request for the cable's
;  address is answered as the cable, an ICMP echo to the radio's address
;  is answered as the radio, and a console datagram on either is
;  answered on that one, in the same spin of the same prompt, whatever
;  the other interface has been doing.
;
;  IT USED TO BE TWO LINES IN A FIXED ORDER - NetIfActivate(kind) and
;  then NetInput(p, nRx) - because the IP layer had one identity that
;  had to be pointed at this interface first. It is one line now, and
;  the order it depended on cannot be got wrong because there is no
;  longer an order.
;
;  WITHOUT IT there is one address and the last thing to take one owns
;  the board. That is not a policy that can be tuned - it is the shape
;  of the defect, and it is what put the board's radio lease "over the
;  wired Ethernet" on 2026-09-07 with a laptop on the cable that could
;  no longer see it at all.
; ----------------------------------------------------------------------
Procedure netcon_PumpOne(kind.i)
  Define nRx.i
  Define rc.i
  Define p.i
  Define took.i
  took = 0
  While took < #LINK_RX_BUDGET
    nRx = HwLinkRecv(kind, @gConRx[0], #NETCON_RX_MAX, 0)
    If nRx < 14
      Break
    EndIf
    took = took + 1
    gConRxFrames = gConRxFrames + 1
    p = HwLinkRxPtr(kind)
    If p = 0
      p = @gConRx[0]
    EndIf
    ; Raw link protocols such as an 802.11 EAPOL rekey are consumed
    ; before the IP layer and do not stop this interface's drain.
    If HwLinkOfferRaw(kind, p, nRx) <> 0
      Continue
    EndIf
    rc = NetInput(kind, p, nRx)
    HwLinkNoteRx(kind, rc)
    NetServiceInput(kind, p, rc)
  Wend
  If took >= #LINK_RX_BUDGET
    gConRxFull = gConRxFull + 1
  EndIf
EndProcedure

Procedure NetConsolePump()
  Define k.i
  Define members.i
  If gConOn = 0
    ProcedureReturn
  EndIf
  If (millis() - gConLastPump) < 5
    ProcedureReturn
  EndIf
  gConLastPump = millis()

  ; ------------------------------------------------------------------
  ; EVERY ADDRESSED INTERFACE, EVERY SLICE. Not the preferred one, not
  ; the one the last address landed on: every one that holds an address
  ; and can carry a frame. A board that pumped only its preferred
  ; interface would be a board whose second link answers nothing, which
  ; is a console on one link wearing the paint of a console on two.
  ;
  ; THE WALK IS NetIfNext's so that the pump, the arming and `net`
  ; cannot disagree about which interfaces are in play.
  ; ------------------------------------------------------------------
  members = 0
  k = NetIfNext(0)
  While k <> #HW_LINK_NONE
    members = members | (1 << k)
    ; Publish the on edge before consuming this queue, so the driver pump
    ; cannot also consume it later in the same prompt spin.
    If (gConMemberMask & (1 << k)) = 0
      HwLinkConsoleArmed(k, 1)
    EndIf
    netcon_PumpOne(k)
    k = NetIfNext(k)
  Wend

  ; Rows absent from this completed walk are no longer console consumers.
  ; No extra HwLinkReady/PHY query is made: membership is derived from the
  ; exact NetIfNext walk the console already had to perform.
  For k = 1 To #NETIF_KINDS - 1
    If (gConMemberMask & (1 << k)) <> 0 And (members & (1 << k)) = 0
      HwLinkConsoleArmed(k, 0)
    EndIf
  Next
  gConMemberMask = members

  NetConsoleFlush()
EndProcedure

; ======================================================================
;  RAW DATAGRAM PRIMITIVES - the wire under a binary protocol
; ======================================================================
;  The pump above turns datagrams into keystrokes, which is the whole of
;  what a text console needs. A binary protocol - the acknowledged
;  screenshot and the over-the-air image push - needs the datagram
;  itself, not a byte stream, and needs to answer the exact host that
;  sent it. These two give it that and nothing more, so they carry no
;  policy: WHAT to do with a datagram and WHERE its bytes may land are
;  the caller's.

; Wait up to `ms` milliseconds for one UDP datagram on the console port.
; Returns its payload length with the bytes at NetUdpRxData() - a copy
; that stays valid until the NEXT call here, so consume it before asking
; again - and captures the sender as the reply peer. ARP and ICMP are
; answered while it waits, so the link does not go deaf. Returns -1 on
; timeout. Does NOT feed the keystroke ring: the caller owns the payload.
Procedure.i NetConsolePollUdp(ms.i)
  Define nRx.i
  Define rc.i
  Define t0.i
  Define p.i
  Define k.i
  If gConOn = 0
    ProcedureReturn -1
  EndIf
  t0 = millis()
  Repeat
    ; EVERY ADDRESSED INTERFACE, for the reason the pump walks them all:
    ; `net recv` and the image push are the two commands a host runs
    ; over whichever link it can reach the board on, and a wait that
    ; listened to one interface would sit out its whole timeout while
    ; the bytes arrived on the other.
    k = NetIfNext(0)
    While k <> #HW_LINK_NONE
      nRx = HwLinkRecv(k, @gConRx[0], #NETCON_RX_MAX, 0)
      If nRx >= 14
        p = HwLinkRxPtr(k)
        If p = 0
          p = @gConRx[0]
        EndIf
        If HwLinkOfferRaw(k, p, nRx) = 0
          rc = NetInput(k, p, nRx)
          HwLinkNoteRx(k, rc)
          If rc = #NET_IN_REPLY
            netcon_SendStaged(k)
          ElseIf rc = #NET_IN_TCP
            ; A binary console wait must not starve an unrelated socket.
            TcpInput()
          ElseIf rc = #NET_IN_UDP
            If NetUdpRxDstPort() = #DHCP_PORT_SERVER
              If NetConsoleOfferUdp(p, k) = 2
                netcon_SendStaged(k)
              EndIf
            ElseIf NetUdpRxDstPort() = #NETCON_PORT
              ; Binary payload/ACK traffic belongs only to the endpoint
              ; that submitted this command. A spoof or a second console
              ; receives BUSY and cannot redirect the current transfer.
              If netcon_PeerMatches(p, k) <> 0
                ProcedureReturn NetUdpRxLen()
              EndIf
              netcon_SendBusy(p, k)
            EndIf
          EndIf
        EndIf
      EndIf
      k = NetIfNext(k)
    Wend
    If (millis() - t0) >= ms
      ProcedureReturn -1
    EndIf
  ForEver
EndProcedure

; Send `len` raw bytes at `src` straight to the current console peer over
; UDP, addressed by the hardware address captured from its last datagram -
; no ARP, the com-port model. 1 if it went, 0 if there is no peer yet.
; `len` is capped at one datagram by netcon_BuildUdp.
Procedure.i NetConsoleSendPeer(src.i, len.i)
  Define fn.i
  fn = netcon_BuildUdp(src, len)
  If fn <= 0
    ProcedureReturn 0
  EndIf
  ; OUT OF THE PEER'S OWN INTERFACE. netcon_BuildUdp has already refused
  ; unless gConPeerKind names one that can carry a frame.
  If HwLinkSend(gConPeerKind, @gConTx[0], fn, 100) <> 1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; The next byte the peer sent, or -1. The prompt reads it like a
; keystroke.
Procedure.i NetConsoleGetc()
  Define c.i
  If gConInTail = gConInHead
    ProcedureReturn -1
  EndIf
  c = gConIn[gConInTail] & $FF
  gConInTail = gConInTail + 1
  If gConInTail >= #NETCON_IN_RING
    gConInTail = 0
  EndIf
  ProcedureReturn c
EndProcedure

Procedure.i NetConsoleOn()
  ProcedureReturn gConOn
EndProcedure

Procedure.i NetConsolePeerOk()
  ProcedureReturn gConPeerOk
EndProcedure

Procedure.i NetConsoleKind()
  ProcedureReturn gConKind
EndProcedure

Procedure.i NetConsoleIp()
  ProcedureReturn gConIp
EndProcedure

Procedure.i NetConsoleArmCount()
  ProcedureReturn gConArms
EndProcedure

Procedure.i NetConsoleRxFrames()
  ProcedureReturn gConRxFrames
EndProcedure

Procedure.i NetConsoleRxFull()
  ProcedureReturn gConRxFull
EndProcedure

; ----------------------------------------------------------------------
;  WHERE THE ARMING QUESTION WENT, 2026-09-07 (the second time).
;
;  This file used to answer "which interface holds the address the IP
;  layer is configured with" by comparing net.pi4's hardware address
;  against each link's own - netcon_LinkOwns and
;  netcon_KindHoldingAddress, both now gone. That question had exactly
;  one answer by construction, because there was one address, and so the
;  console could only ever be on one link.
;
;  THE QUESTION IS NOW "WHICH INTERFACES HOLD AN ADDRESS", plural, and
;  it is Anvil/Core/netif.pbi's: NetIfUsable(kind) is HAS AN ADDRESS and
;  CAN CARRY A FRAME, which is the same three measurements the old
;  procedure made - the link exists, it is ready, it has a hardware
;  address - plus the one it could not make, because there was nowhere
;  to record a second interface's address.
;
;  NOTHING IS ASSUMED ABOUT WHICH LINK ANY OF IT IS. The console arms
;  when at least one interface is usable, pumps every usable one, and
;  ANNOUNCES the preferred one (NetIfPreferred: the operator's pin, else
;  the wire whenever the cable is up, else the radio).
; ----------------------------------------------------------------------

; The addresses the console is listening on, printed one to a line. Used
; by the arming announcement, by `net` and by the boot log, so the three
; cannot describe the board differently.
Procedure NetConsoleSayLinks()
  Define k.i
  k = NetIfNext(0)
  While k <> #HW_LINK_NONE
    Print("    ")
    PutIp(NetIPv4(k))
    Print(" port ")
    PrintDec(#NETCON_PORT)
    Print(", over ")
    UartWriteStr(HwLinkName(k))
    If NetIPv4Alt(k) <> 0
      Print(" (and ")
      PutIp(NetIPv4Alt(k))
      Print(", which this board is serving DHCP on)")
    EndIf
    PrintN("")
    k = NetIfNext(k)
  Wend
EndProcedure

; Publish an all-off edge without querying hardware. Used only when the
; wildcard listener itself is disarmed; ordinary membership is derived by
; NetConsolePump from its existing interface walk.
Procedure netcon_PublishDisarmed()
  Define k.i
  For k = 1 To #NETIF_KINDS - 1
    If (gConMemberMask & (1 << k)) <> 0
      HwLinkConsoleArmed(k, 0)
    EndIf
  Next
  gConMemberMask = 0
EndProcedure

; ----------------------------------------------------------------------
;  NetConsoleStart - listen, on this kind, at the address the IP layer
;  holds. Idempotent: it prints its announcement exactly once per arming.
; ----------------------------------------------------------------------
Procedure NetConsoleStart(kind.i)
  Define k.i
  If gConOn <> 0
    ProcedureReturn
  EndIf
  If kind = #HW_LINK_NONE
    ProcedureReturn
  EndIf
  ; THE READINESS TEST IS REPEATED HERE AND THAT IS NOT REDUNDANT.
  ; NetConsoleRearm has already asked, but this procedure is public and
  ; takes the kind from its caller: a caller that names a link which
  ; cannot carry a frame would get a console announced on an interface
  ; that answers nobody, which is the whole defect. Caught by the gate,
  ; 2026-09-07, on the case that asks for a kind by name with the link
  ; down - the first cut of this file trusted its caller and armed.
  If NetIfUsable(kind) = 0
    ProcedureReturn
  EndIf
  gConKind = kind
  gConIp = NetIPv4(kind)
  ; UDP checksum off - legal over IPv4 and one less thing to get wrong.
  NetUdpChecksumTx(0)
  NetUdpBind(#HW_LINK_NONE, #NETCON_PORT)
  UartAuxMirror(1)
  ; Flush per line DURING command output, not only at the prompt.
  UartAuxSetFlush(@NetConsoleFlush)
  gConOn = 1
  gConArms = gConArms + 1
  ; DRIVER RECEIVE OWNERSHIP IS PUBLISHED BY NetConsolePump's ACTUAL WALK,
  ; not by this announcement. On a board whose radio services its own
  ; rekeys, that pump stands down immediately before this console consumes
  ; the radio queue; route preference and the sentence printed below have
  ; no authority over hardware ownership.
  PrintN("Network console listening on UDP, on every interface that holds an")
  PrintN("address:")
  NetConsoleSayLinks()
  PrintN("  A host reaches it with tools/anvil_wifi.py <ip> - send it a line")
  PrintN("  and the prompt answers over the wire, out of the interface it came")
  PrintN("  in on. The serial console still works.")
EndProcedure

; Stop listening. The aux tap stays on and the mirror keeps draining
; through NetConsoleFlush's no-peer path, so nothing backs up.
Procedure netcon_Disarm()
  Define i.i
  If gConOn = 0
    ProcedureReturn
  EndIf
  gConOn = 0
  ; gConOn is already clear, so every row receives its exact off edge even
  ; if its address disappeared before the console itself was disarmed.
  netcon_PublishDisarmed()
  gConKind = #HW_LINK_NONE
  gConIp = 0
  gConPeerKind = #HW_LINK_NONE
  gConPeerDstIp = 0
  ; FORGET THE PEER COMPLETELY, not just the flag. Its address and its
  ; hardware address belong to the segment it was learned on, and a
  ; half-forgotten peer is a set of numbers that look valid to anything
  ; that reads them without checking the flag first. Clearing the flag
  ; alone was the first cut and the gate caught it.
  gConPeerOk = 0
  gConOwner = #NETCON_OWNER_NONE
  gConInHead = 0
  gConInTail = 0
  gConPeerIp = 0
  gConPeerPort = 0
  For i = 0 To 5
    gConPeerMac[i] = 0
  Next
EndProcedure

; ----------------------------------------------------------------------
;  NetConsoleRearm - the whole arming question, answered from the board's
;  state, on every spin of the prompt. See the header for the four cases.
;
;  IDEMPOTENT AND CHEAP. A board already listening on the right link at
;  the right address pays a hardware-address compare and NetUdpBind's two
;  stores; a board with no address pays two loads and a return.
; ----------------------------------------------------------------------
Procedure NetConsoleRearm()
  Define k.i
  ; A session is bound to the exact local address it arrived on. Losing
  ; that interface/address releases it even when another interface keeps
  ; the console globally armed; sending its output through the survivor
  ; would violate endpoint ownership.
  If gConOwner = #NETCON_OWNER_NET
    If NetIfUsable(gConPeerKind) = 0
      netcon_ForgetOwner()
    ElseIf NetIPv4(gConPeerKind) <> gConPeerDstIp And NetIPv4Alt(gConPeerKind) <> gConPeerDstIp
      netcon_ForgetOwner()
    EndIf
  EndIf
  k = NetIfPreferred()
  If gConOn <> 0
    If k = #HW_LINK_NONE
      ; No interface holds a usable address at this instant - a lease
      ; being renewed, a cable pulled, a command that took the interface
      ; down. KEEP LISTENING and put the bound port back: tearing the
      ; console down for a gap that usually closes within a command is
      ; how a board becomes unreachable for the one minute somebody
      ; needed it.
      NetUdpBind(#HW_LINK_NONE, #NETCON_PORT)
      ProcedureReturn
    EndIf
    ; ----------------------------------------------------------------
    ; A SECOND INTERFACE COMING UP DOES NOT RE-ARM THE CONSOLE, AND
    ; THAT IS THE 2026-09-07 FIX IN ONE COMPARE.
    ;
    ; What was here tore the console down and rebuilt it whenever the IP
    ; layer's single address changed - which, with one address, was what
    ; "the board has moved" meant. With one address PER INTERFACE the
    ; radio taking its lease changes nothing about the cable, so the
    ; only thing that can move is the ANNOUNCED interface, and the only
    ; reason to say anything is that the preferred one is now different
    ; or its address is. Even then the peer is NOT forgotten: it is
    ; reached over its own interface (gConPeerKind), which this has not
    ; touched.
    ; ----------------------------------------------------------------
    If k <> gConKind Or NetIPv4(k) <> gConIp
      gConKind = k
      gConIp = NetIPv4(k)
      PrintN("The network console is now listening on:")
      NetConsoleSayLinks()
    EndIf
    NetUdpBind(#HW_LINK_NONE, #NETCON_PORT)
    ProcedureReturn
  EndIf
  If k = #HW_LINK_NONE
    ProcedureReturn
  EndIf
  NetConsoleStart(k)
EndProcedure

; ----------------------------------------------------------------------
;  NetConsoleSay - the status line `net` and `info` print. One sentence
;  that answers "can I reach this board, and where".
; ----------------------------------------------------------------------
Procedure NetConsoleSay()
  If gConOn = 0
    PrintN("  The network console is NOT listening: this board has no address on")
    PrintN("  any interface it could answer from. Put a cable in and run dhcp, or")
    PrintN("  join a wireless network, and it arms itself.")
    ProcedureReturn
  EndIf
  ; EVERY INTERFACE, NOT THE PREFERRED ONE. A board that listens on two
  ; and reports one is a board whose operator types the wrong address
  ; into a tool and concludes the other link is broken - which is what
  ; `net link` did on 2026-09-07 when it said the console was on
  ; the previous radio lease "over the wired Ethernet".
  PrintN("  The network console is listening on UDP:")
  NetConsoleSayLinks()
  If gConPeerOk = 0
    PrintN("  No host has spoken to it yet.")
  Else
    Print("  The host it answers is ")
    PutIp(gConPeerIp)
    Print(", reached over ")
    UartWriteStr(HwLinkName(gConPeerKind))
    Print(" as ")
    PutIp(gConPeerDstIp)
    PrintN(".")
  EndIf
EndProcedure
