; ======================================================================
;  THE LINK, AS THE COMMANDS SEE IT - 2026-09-05
; ======================================================================
;  THIS FILE STOPPED NAMING A BOARD ON 2026-09-05, and the change is
;  worth stating in full because "the core names no chip" had been true
;  of Anvil/ARCHITECTURE.md and not quite true of this file.
;
;  The 2026-09-04 pass put the WIRE behind Anvil/Hal/hal.pbi's HwLink*
;  seam, so RaspberryPi4/Lib/link.pi4 - the policy layer - stopped
;  naming Genet and Cyw43. The COMMAND layer did not. This file was
;  still calling, by name, seven procedures that lived in one board's
;  network file and two that lived in one board's MAC driver:
;
;    EthUp EthUpIp EthLinkUp EthDown EthResolve EthRun EthSendStaged
;                                        RaspberryPi4/Board/eth.pi4
;    GenetSpeed GenetFullDuplex          RaspberryPi4/Lib/genet.pi4
;
;  and four more with portable-looking names that were nonetheless
;  defined in that same board file, which is the harder version of the
;  same problem because nothing about the spelling gave it away:
;
;    LinkBringUp LinkSay LinkMacPtr PutLinkMac
;
;  NONE OF THEM TOUCHED A REGISTER. Every one was net.pi4, tftp.pi4 and
;  link.pi4 with sentences around it; they were in a board file because
;  that is where the network commands' caller half grew up. So the
;  bring-up and the teardown went behind six new HwLink* names, and
;  everything that was only ever a loop and some English came HERE, to
;  the command layer, which is what it always was.
;
;  WHAT THIS SECTION OWNS NOW, and why each is at this altitude:
;
;    LinkSay LinkWhySay LinkSayRate PutLinkMac
;        The status lines. They read the portable policy layer and the
;        HwLink* getters and print, in words that are the same on every
;        board. A board with a different thing to add says it through
;        HwLinkSayDetail and nothing here has to know what it is.
;    NetLinkUpFull NetLinkUpSay
;        The two shapes of bring-up the commands actually want: all four
;        addresses and the full banner for get and put, and choose-and-
;        say for ping, dns, tcp and http get. dhcp calls HwLinkOpen(0)
;        directly, because it wants a link with no address at all.
;    NetResolveHop
;        The ARP resolve. It is net.pi4's cache, this project's pump and
;        a keypress check - portable in every line.
;    NetXferSend NetXferPump NetXferRun
;        The TFTP pump. tftp.pi4 and net.pi4 are portable libraries and
;        the loop over them never was anything else.
;
;  WHY THESE ARE HERE AND NOT IN RaspberryPi4/Lib/link.pi4, which is the
;  obvious other home: they PRINT, and NetResolveHop and NetXferRun ask
;  OutBreak() whether the operator has pressed a key. A library that
;  printed could not be driven by a gate with no console in it, and that
;  property is what tools/a64/a64_netpump_check.py depends on to run the
;  pump against a fixture link on both targets.
;
;  WHAT IS STILL OWED, said here rather than left to be discovered. This
;  file no longer calls into a board, but it still READS one board's
;  globals - gEthIp, gEthMask, gEthGw, gEthSrv, gEthUp's tally
;  counters - and the #ETH_* constants beside them, all declared in
;  RaspberryPi4/Board/eth_globals.pi4. Those are a data leak of the same
;  shape as the call leak this pass closed, and closing them means
;  moving that file's contents into the core, which is a separate change
;  to a separate file. Until then this file compiles for the Pi 4 only,
;  for a reason that is now entirely about where four addresses are
;  declared and no longer about which MAC is on the board.
; ======================================================================

; ----------------------------------------------------------------------
;  NetSayInterfaces - EVERY INTERFACE THAT HOLDS AN ADDRESS, AND WHERE
;  EACH ONE GOT IT.  Added 2026-09-07.
;
;  WHAT IT REPLACES IS A BOARD LYING ABOUT ITSELF. On the evening of
;  2026-09-07, with a cable into a laptop and a radio on the house
;  network, `net link` said: the console listens on the radio's lease, over
;  the wired Ethernet, and "this board has exactly one interface Anvil
;  can reach". Three things wrong in two lines - the radio's address had
;  displaced the cable's, the cable was named as the carrier of an
;  address that does not exist on it, and a board with two live
;  interfaces said it had one - and every one of them was a true report
;  of a stack that could only hold one address.
;
;  THE ADDRESSES ARE NOW PER INTERFACE, so this prints per interface,
;  and it prints from RaspberryPi4/Lib/net.pi4's address rows - one per
;  #HW_LINK_* kind - with the provenance beside them out of
;  Anvil/Core/netif.pbi, rather than from anybody's flag. A line here
;  that disagrees with what a host can reach is a defect in those rows,
;  which is exactly where a defect of this shape should show.
;
;  THE OUTBOUND CHOICE IS STILL ONE LINK and is still LinkSay's, printed
;  separately: "which addresses answer" and "which door does an outbound
;  frame leave by" are different questions and merging them is how the
;  old single-address report came to be believed.
; ----------------------------------------------------------------------
Procedure NetSayInterfaces()
  Define k.i
  Define n.i
  Define src.i
  n = NetIfCount()
  If n = 0
    PrintN("No interface on this board holds an address, so nothing can reach it")
    PrintN("over the network yet. Put a cable in, or join a wireless network.")
    For k = 1 To #DHCPC_IFS - 1
      If HwLinkHas(k) <> 0
        Print("DHCP state on ") : UartWriteStr(HwLinkName(k)) : PrintN(":")
        NetDhcpSay(k)
      EndIf
    Next
    ProcedureReturn
  EndIf
  Print("This board holds ")
  PrintDec(n)
  If n = 1
    PrintN(" address, on one interface:")
  Else
    PrintN(" addresses, one per interface, and NEITHER displaces")
    PrintN("the other - both answer at once:")
  EndIf
  k = NetIfNext(0)
  While k <> #HW_LINK_NONE
    Print("  ")
    UartWriteStr(HwLinkName(k))
    Print("   ")
    PutIp(NetIPv4(k))
    Print("  netmask ")
    PutIp(NetMask(k))
    If NetGateway(k) = 0
      Print("  no router")
    Else
      Print("  router ")
      PutIp(NetGateway(k))
    EndIf
    PrintNl()
    src = NetIfSrc(k)
    Print("    ")
    If src = #NET_ADDR_LEASE
      Print("a DHCP lease")
      If NetIfLeaseSecs(k) > 0
        Print(" of ")
        PrintDec(NetIfLeaseSecs(k))
        Print(" seconds")
      EndIf
      PrintN(".")
    ElseIf src = #NET_ADDR_SAVED
      PrintN("the address saved in SETTINGS.TXT, applied at boot.")
    ElseIf src = #NET_ADDR_LINKLOCAL
      PrintN("picked by this board out of 169.254.0.0/16 and ARP-probed (RFC 3927),")
      PrintN("    because nothing answered a DHCP discover on this link.")
    Else
      PrintN("bound, but by nothing that recorded where it came from.")
    EndIf
    If NetIPv4Alt(k) <> 0
      Print("    and a SECOND address, ")
      PutIp(NetIPv4Alt(k))
      Print(" netmask ")
      PutIp(NetMaskAlt(k))
      PrintN(":")
      PrintN("    this board is the DHCP server on this link, so it answers there too.")
    EndIf
    k = NetIfNext(k)
  Wend
  ; DHCP is protocol state, including interfaces that are selecting and do
  ; not hold an address yet. Report every hardware row so an operator can
  ; distinguish "no server answered" from an expired/offline lease.
  For k = 1 To #DHCPC_IFS - 1
    If HwLinkHas(k) <> 0
      Print("DHCP state on ") : UartWriteStr(HwLinkName(k)) : PrintN(":")
      NetDhcpSay(k)
    EndIf
  Next
  If DhcpdOn() <> 0
    Print("Handing out addresses on ")
    UartWriteStr(HwLinkName(DhcpdKind()))
    PrintN(", because nothing else on it does:")
    Print("  pool ")
    PutIp(#DHCPD_POOL_LO)
    Print(" to ")
    PutIp(#DHCPD_POOL_HI)
    Print(", ")
    PrintDec(DhcpdLeased())
    Print(" handed out, ")
    PrintDec(DhcpdOffers())
    Print(" offers, ")
    PrintDec(DhcpdAcks())
    Print(" acknowledgements and ")
    PrintDec(DhcpdNaks())
    PrintN(" refusals staged.")
    If DhcpdUnstaged() <> 0
      Print("  ")
      PrintDec(DhcpdUnstaged())
      PrintN(" replies were owed but could not be staged.")
    EndIf
    If DhcpdWrongLink() <> 0
      Print("  ")
      PrintDec(DhcpdWrongLink())
      PrintN(" DHCP messages arrived on another interface and were refused.")
    EndIf
    Print("  The console pump transmitted ")
    PrintDec(NetConsoleTxCount())
    Print(" staged replies; ")
    PrintDec(NetConsoleTxFails())
    PrintN(" were refused by a link.")
    PrintN("  A real DHCP server answering here ends this at once.")
  EndIf
  Print("The console pump has taken ")
  PrintDec(NetConsoleRxFrames())
  PrintN(" frames off its interfaces.")
  If NetConsoleRxFull() = 0
    PrintN("  Every drain ended on an empty ring, so nothing has been waiting")
    PrintN("  on this board's receive budget.")
  Else
    Print("  ")
    PrintDec(NetConsoleRxFull())
    PrintN(" drains stopped on the budget with frames still queued.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  LinkSay - which interface is carrying traffic and why.
;
;  BOTH HALVES, ALWAYS. The operator's real question is never "which
;  one" on its own; it is "which one, and what is wrong with the other".
;  LinkWhyText() answers the second half out of the reason that was
;  STORED at the moment the choice was made, not one recomputed now -
;  RaspberryPi4/Lib/link.pi4's header sets out why that distinction
;  matters and how a monitor lies without it.
;
;  THE PIN IS NAMED BY THE BOARD. It used to be two literals - "the
;  wired port", "the radio" - which is how a board with a serial link
;  and no radio would have been told its traffic was pinned to a radio.
;  HwLinkName of the pinned kind is the same answer with nothing
;  assumed.
; ----------------------------------------------------------------------
Procedure LinkSay()
  Define pin.i
  Print("Traffic goes out over ")
  UartWriteStr(LinkName())
  PrintN(":")
  Print("  ")
  UartWriteStr(LinkWhyText())
  PrintN(".")
  pin = LinkPin()
  If pin <> #HW_LINK_NONE
    Print("  The operator has pinned it to ")
    UartWriteStr(HwLinkName(pin))
    PrintN(" with net link, so nothing else")
    PrintN("  is considered at all until net link auto.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  LinkWhySay - what the DRIVER under the link in use last had to say.
;
;  THIS IS WHAT EthWhyGenet() WAS, at six call sites in this file. That
;  procedure printed GenetErrorText() - one board's MAC driver's error
;  string - from the shared core, which meant the shared core could not
;  be compiled anywhere that driver was absent, for the sake of one line
;  of diagnostic text.
;
;  AN EMPTY ANSWER PRINTS NOTHING AT ALL, and that is deliberate rather
;  than defensive. A board whose link driver keeps no last-error string
;  has nothing to contribute, and "The link driver said: " followed by
;  nothing is worse than silence - it reads as a driver that reported an
;  empty fault. The zero check is there as well because a backend that
;  has not implemented the getter returns an unspecified value, and
;  reading a string from address zero is a fault rather than a blank.
; ----------------------------------------------------------------------
Procedure LinkWhySay()
  Define t.i
  t = LinkWhyLink()
  If t = 0
    ProcedureReturn
  EndIf
  If PeekA(t) = 0
    ProcedureReturn
  EndIf
  Print("   The link driver said: ")
  UartWriteStr(t)
  PrintNl()
EndProcedure

; ----------------------------------------------------------------------
;  LinkSayRate - how fast the link in use is running, when the board can
;  actually say.
;
;  A LINK WITH NO MEASURABLE RATE PRINTS NO RATE LINE. #HW_LINK_SPEED_
;  UNKNOWN is a real answer, not a missing one: a radio's data rate is a
;  per-frame property of a modulation the firmware picks and does not
;  report, and a serial line's baud is a number somebody typed rather
;  than one two ends negotiated. Printing either as a link speed would
;  put an unmeasured figure on the terminal beside a wired board's real
;  measurement with nothing to tell them apart.
; ----------------------------------------------------------------------
Procedure LinkSayRate()
  Define s.i
  Define d.i
  s = LinkSpeed()
  d = LinkDuplex()
  If s = #HW_LINK_SPEED_UNKNOWN And d = #HW_LINK_DUPLEX_UNKNOWN
    ProcedureReturn
  EndIf
  Print("  It is running at ")
  If s = #HW_LINK_SPEED_UNKNOWN
    Print("a rate this board cannot measure")
  Else
    PrintDec(s)
    Print(" Mbit/s")
  EndIf
  If d = #HW_LINK_DUPLEX_FULL
    PrintN(", full duplex.")
  ElseIf d = #HW_LINK_DUPLEX_HALF
    PrintN(", half duplex.")
  Else
    PrintN(".")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  PutLinkMac - the hardware address frames ACTUALLY leave with.
;
;  NOT PutMac(), WHICH IS THE WIRED CARD'S. On a board where the radio
;  carries the traffic the wired card's six bytes are all zeros until
;  something brings the wired side up, and `dhcp` over Wi-Fi announced
;  itself as 00:00:00:00:00:00 on silicon on 2026-09-04 because of
;  exactly that. LinkMacPtr() asks the seam for the address of the kind
;  that won.
;
;  A LINK WITH NO HARDWARE ADDRESS SAYS SO IN WORDS. A point-to-point
;  serial line has none - there is no link header on the wire at all -
;  and the seam answers 0 for it. Six pairs of hex digits read out of
;  address zero would be a plausible-looking address that is not one.
; ----------------------------------------------------------------------
Procedure PutLinkMac()
  Define i.i
  Define p.i
  p = LinkMacPtr()
  If p = 0
    UartWriteStr("no hardware address - this link carries none")
    ProcedureReturn
  EndIf
  For i = 0 To 5
    PutHex2(PeekA(p + i) & $FF)
    If i < 5
      UartWrite(58)                    ; 58 is a colon
    EndIf
  Next
EndProcedure

; ----------------------------------------------------------------------
;  NetLinkUpSay - choose an interface and say which and why. For ping,
;  dns, tcp and http get: they need to be able to SEND from an address,
;  and they want one line about the link and no banner.
; ----------------------------------------------------------------------
Procedure.i NetLinkUpSay(needIp.i)
  If HwLinkOpen(needIp) = 0
    ProcedureReturn 0
  EndIf
  LinkSay()
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  NetLinkUpFull - the bring-up get, put and `net up` want: all four
;  addresses re-read and validated first, then the interface chosen,
;  then everything worth knowing about it.
;
;  THE ADDRESSES ARE RE-READ BEFORE THE BRING-UP and that order is the
;  point: they live in the settings store, which the operator can change
;  between one transfer and the next - `net server` is exactly the thing
;  somebody retypes after a get has failed - and a command that ignored
;  what was just typed would be the silent wrong answer this project
;  exists to refuse. EthConfig() also validates the four against
;  net.pi4's rules before a single register is touched.
;
;  THE BANNER IS ASSEMBLED FROM THE SEAM, NOT FROM A BOARD. Speed and
;  duplex come from HwLinkSpeed / HwLinkDuplex through the policy layer;
;  the hardware address comes from HwLinkMacPtr; the four configured
;  addresses are printed only when the WIRED link won, because they are
;  the wired side's configuration and printing them under a radio's
;  status line would describe an interface that is not carrying
;  anything. Whatever else a board wants to add, it adds through
;  HwLinkSayDetail - on the Pi 4 that is the receive region's address
;  and the warning that the hardware address is a made-up one.
; ----------------------------------------------------------------------
Procedure.i NetLinkUpFull()
  If EthConfig() = 0
    ProcedureReturn 0
  EndIf
  If HwLinkOpen(1) = 0
    ProcedureReturn 0
  EndIf
  LinkSay()
  LinkSayRate()
  Print("  Frames leave with the hardware address ")
  PutLinkMac()
  PrintN(".")
  If LinkKind() = #HW_LINK_WIRED
    Print("  Its address is ")
    PutIp(gEthIp)
    Print(", netmask ")
    PutIp(gEthMask)
    Print(", gateway ")
    PutIp(gEthGw)
    PrintN(".")
  EndIf
  HwLinkSayDetail()
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  NetResolveHop - learn the next hop's hardware address before a single
;  datagram is built.
;
;  WHY THIS IS A SEPARATE STEP. NetUdpBuild() refuses with
;  #NET_E_NO_ARP when the cache has no entry for the next hop, and it is
;  right to: resolving means transmitting and waiting, and net.pi4 does
;  no I/O. Without this the very first read request fails, the operator
;  sees a send failure rather than a network fault, and the retransmit
;  timer then fails identically eight more times.
;
;  IT ASKS FOR THE NEXT HOP, NOT THE SERVER. NetNextHop() returns the
;  server itself when the server is on our own segment and THE GATEWAY
;  when it is not (net.pi4:1316). ARPing for an off-link address is
;  answered by nobody - it is not on this segment - and the stack would
;  resolve forever. net.pi4:1271-1283 calls this the single most
;  commonly mis-implemented line in a first IP stack, and it is not
;  going to be re-derived here.
;
;  IT KEEPS FEEDING NetInput() WHILE IT WAITS, and answers whatever
;  net.pi4 stages - an ARP request of somebody else's, or a ping. A
;  board that goes deaf while resolving is a board that does not answer
;  the very request that would teach the other end where we are.
;
;  IT WAS EthResolve IN RaspberryPi4/Board/eth.pi4 UNTIL 2026-09-05 and
;  it named no chip even then: LinkTxStaged and LinkPumpNet carry the
;  frames and net.pi4 owns the cache. Nothing about it changed in the
;  move except the one line that printed one board's MAC driver's error
;  text, which is now LinkWhySay over the seam.
; ----------------------------------------------------------------------
Procedure.i NetResolveHop(ip.i)
  Define k.i
  Define hop.i
  Define tries.i
  Define deadline.i
  Define r.i

  ; THE INTERFACE IS THE ONE THE REQUEST WILL PHYSICALLY LEAVE BY, and it
  ; has to be: LinkTxStaged below transmits over LinkKind(), so asking
  ; net.pi4 for any other interface's next hop would resolve an address
  ; against one interface's subnet and gateway and then put the frame out
  ; of another. Every caller of this procedure has already chosen a link
  ; through HwLinkOpen - NetLinkUpFull for get and put, NetLinkUpSay for
  ; ping and dns - so the choice is made and this reads it rather than
  ; making a second one that could differ.
  k = LinkKind()
  hop = NetNextHop(k, ip)
  If hop = 0
    PrintN("!! there is no route to that address at all, so nothing was sent. It")
    PrintN("   is not on this board's own subnet and no gateway is configured.")
    PrintN("   Set one with net gateway <router>, or give the server an address on")
    PrintN("   this board's own segment.")
    ProcedureReturn 0
  EndIf
  If NetArpLookup(k, hop, @gEthPeer[0]) = 1
    ProcedureReturn 1
  EndIf

  Print("Asking the network who has ")
  PutIp(hop)
  PrintN(" before anything is sent, because")
  PrintN("a datagram cannot be addressed until its hardware address is known.")
  UartDrain()

  tries = 0
  While tries < #ETH_ARP_TRIES
    tries = tries + 1
    gEthArpOut = gEthArpOut + 1
    If NetArpRequest(k, hop) = 0
      PrintN("!! the network stack would not build an address request, so nothing")
      PrintN("   was sent.")
      EthWhyNet()
      ProcedureReturn 0
    EndIf
    If LinkTxStaged() <> 1
      Print("!! the address request would not go out over ")
      UartWriteStr(LinkName())
      PrintN(", so nothing")
      PrintN("   was sent. The link is up, so this is the interface itself and not")
      PrintN("   the cable or the access point.")
      LinkWhySay()
      ProcedureReturn 0
    EndIf

    ; SUBTRACT AND COMPARE AGAINST ZERO rather than comparing the two
    ; numbers, so the wait is correct across a wrap of the millisecond
    ; counter. Same reasoning, same shape, as tftp.pi4:1946-1951.
    deadline = millis() + #ETH_ARP_MS
    While (millis() - deadline) < 0
      r = LinkPumpNet(50)
      If r <> #LINK_RX_NONE
        gEthFrames = gEthFrames + 1
      EndIf
      If NetArpLookup(k, hop, @gEthPeer[0]) = 1
        ProcedureReturn 1
      EndIf
    Wend

    If OutBreak() <> 0
      PrintN("  The address request was stopped, so nothing was transferred.")
      ProcedureReturn 0
    EndIf
  Wend

  Print("!! nothing answered for ")
  PutIp(hop)
  PrintN(", so nothing was transferred. Eight")
  PrintN("   address requests went out over four seconds and none came back. The")
  PrintN("   link is up, so the cable and the switch are fine and the machine at")
  PrintN("   that address is the thing that is not there. Check the address, check")
  PrintN("   the machine is on, and check it is on this segment - a firewall on")
  PrintN("   the other end that drops everything will also drop these.")
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  NetXferSend - put whatever tftp.pi4 has staged onto the wire.
;
;  FOUR LINES, AND EVERY ONE OF THEM IS LOAD BEARING.
;
;  THE LENGTH IS CHECKED FIRST AND ZERO IS THE NORMAL ANSWER. "Nothing
;  to send" is what a duplicate produces, and sending anyway is the
;  Sorcerer's Apprentice bug - see rule 2 in eth_globals.pi4's header.
;
;  TftpOutIp() AND TftpOutPort() ARE READ HERE AND NOWHERE ELSE, on
;  every call, never cached. Nearly every packet goes to the server and
;  then one does not: the ERROR 5 for a stranger who used the wrong
;  transfer identifier goes to the stranger [rfc1350.txt:239-246]. That
;  is the entire reason those two accessors exist (tftp.pi4:106-113).
;
;  TftpLocalPort() IS THE SOURCE PORT and it has to be, not because UDP
;  cares but because it is OUR transfer identifier: the server sends the
;  next block to whatever it sees here, and net.pi4 is bound to that
;  same port so that a datagram for anything else is dropped before
;  tftp.pi4 ever sees it.
; ----------------------------------------------------------------------
Procedure.i NetXferSend()
  If TftpOutLen() = 0
    ProcedureReturn 0
  EndIf
  If NetUdpBuild(LinkKind(), TftpOutIp(), TftpOutPort(), TftpLocalPort(), TftpOutBuf(), TftpOutLen()) = 0
    gEthSendFail = gEthSendFail + 1
    ProcedureReturn 0
  EndIf
  If LinkTxStaged() <> 1
    gEthSendFail = gEthSendFail + 1
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  NetXferPump - one slice of the transfer loop. 1 when it is over.
;
;  THIS IS THE WHOLE OF THE WIRING and it is the sequence tftp.pi4's
;  header sets out. Nothing here is clever and nothing here may be
;  reordered:
;
;    a frame in            LinkPumpNet  - whichever link is up
;    what is it            NetInput     - inside LinkPumpNet, with its
;                                         reply, if one was staged
;    a datagram for us     TftpInput    - which stages the answer
;    the answer out        NetXferSend
;    our own timer         TftpTick     - and its retransmission out
;
;  EVERY FRAME GOES TO NetInput() EVEN WHEN IT IS NOT OURS. An ARP
;  request from the server is answered there; a ping is answered there;
;  and any frame at all from a neighbour refreshes that neighbour's
;  cache entry through net_ConfirmNeighbour (net.pi4:1391, called from
;  net.pi4:2106). That last one is why a long transfer no longer loses
;  its next hop halfway through, and it happens as a side effect of
;  calling NetInput - which is exactly the kind of thing somebody
;  optimises away.
;
;  TftpTick() IS CALLED ON EVERY SLICE, INCLUDING THE ONES WITH NO
;  FRAME. It is the entire reason a lost acknowledgement does not hang
;  this loop forever. See rule 3 in eth_globals.pi4's header.
;
;  A STRANGER IS COUNTED, NOT PRINTED. TftpInput() has already staged an
;  ERROR 5 addressed to whoever it was and NetXferSend() sends it; a
;  line of output per stranger would let anybody on the segment fill the
;  terminal. TftpStrangerCount() is in the tally at the end.
; ----------------------------------------------------------------------
Procedure.i NetXferPump(ms.i)
  Define r.i
  Define t.i

  r = LinkPumpNet(ms)
  If r <> #LINK_RX_NONE
    gEthFrames = gEthFrames + 1
    If r = #NET_IN_UDP
      gEthUdp = gEthUdp + 1
      TftpInput(NetUdpRxFrom(), NetUdpRxPort(), NetUdpRxDstPort(), NetUdpRxData(), NetUdpRxLen())
      NetXferSend()
    EndIf
  EndIf

  t = TftpTick(millis())
  If t = 1
    NetXferSend()
  EndIf

  If TftpComplete() = 1
    ProcedureReturn 1
  EndIf
  If TftpFailed() = 1
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  NetXferRun - pump until it is over, one way or another. 1 if it
;  finished.
;
;  THREE WAYS OUT AND ALL THREE SAY SO. The transfer completes or fails,
;  the operator presses a key, or the ceiling expires. There is no
;  fourth way and in particular there is no way for this to sit at the
;  prompt with nothing happening: tftp.pi4's own retransmit budget -
;  #ETH_RETRY_MS times #ETH_RETRIES - fails a dead transfer in sixteen
;  seconds without any help from here.
;
;  A KEYPRESS CANCELS POLITELY. TftpCancel() stages an ERROR packet for
;  the server, which is a courtesy and nothing more - "it will not be
;  retransmitted or acknowledged, so it may never be received"
;  [rfc1350.txt:439-441] - but a server that does get it stops holding
;  the transfer open, which matters when the next thing the operator
;  does is try again.
; ----------------------------------------------------------------------
Procedure.i NetXferRun()
  Define deadline.i
  Define dots.i
  Define blocks.i

  dots = 0
  deadline = millis() + #ETH_MAX_MS
  Repeat
    If OutBreak() <> 0
      If dots > 0
        PrintNl()
      EndIf
      If TftpCancel() = 1
        NetXferSend()
      EndIf
      PrintN("The transfer was stopped part way and NOTHING IS COMPLETE. For a get,")
      PrintN("what is at the destination is the beginning of a file with whatever")
      PrintN("was there before underneath it - do not run it. The server has been")
      PrintN("told the transfer is over, as a courtesy it may or may not receive.")
      ProcedureReturn 0
    EndIf

    If NetXferPump(#ETH_SLICE_MS) = 1
      If dots > 0
        PrintNl()
      EndIf
      ProcedureReturn 1
    EndIf

    ; A dot per #ETH_DOT_BLOCKS blocks. Written as a While rather than
    ; an If because a fast server can deliver more than one dot's worth
    ; of blocks inside a single slice, and a progress indicator that
    ; falls behind the thing it is indicating is worse than none.
    blocks = TftpBlocksDone()
    While blocks >= (dots + 1) * #ETH_DOT_BLOCKS
      dots = dots + 1
      UartWrite(46)                ; 46 is a full stop
    Wend

    If (millis() - deadline) >= 0
      If dots > 0
        PrintNl()
      EndIf
      PrintN("The transfer ran for ten minutes without finishing, so it was stopped.")
      PrintN("That is not a timeout on a dead network - a dead one gives up in")
      PrintN("sixteen seconds - it means blocks kept arriving and the file never")
      PrintN("ended. Nothing is complete and the destination holds part of a file.")
      If TftpCancel() = 1
        NetXferSend()
      EndIf
      ProcedureReturn 0
    EndIf
  ForEver
EndProcedure


; ----------------------------------------------------------------------
;  EthCount / EthTally - the counters, after a transfer of either kind.
;
;  PRINTED WHETHER IT WORKED OR NOT, and that is the point. A transfer
;  that failed with "nothing came back" and one that failed after four
;  hundred blocks are completely different faults, and the only thing
;  that tells them apart is these numbers. They cost nine lines.
; ----------------------------------------------------------------------
Procedure EthPad(*name)
  Define n.i
  Print("  ")
  UartWriteStr(*name)
  n = 0
  While PeekA(*name + n) <> 0
    n = n + 1
  Wend
  While n < 26
    UartWrite(32)                  ; 32 is a space
    n = n + 1
  Wend
EndProcedure

; PutPadded() does this job for the settings table and is NOT used here.
; It takes its string as an `a.i`, and every caller of EthCount passes a
; literal through an untyped `*name` parameter; handing one to the other
; is the shape that produced the PutClockRow defect recorded in this
; file's header, where an untyped pointer parameter reached Print() and
; was formatted as a decimal number. Six lines is cheaper than finding
; that out on a bench.
Procedure EthCount(*name, v.i)
  EthPad(*name)
  PrintDec(v)
  PrintNl()
EndProcedure

Procedure EthTally()
  EthCount("frames received", gEthFrames)
  EthCount("datagrams for us", gEthUdp)
  EthCount("address requests sent", gEthArpOut)
  EthCount("blocks", TftpBlocksDone())
  EthCount("bytes", TftpBytes())
  EthCount("duplicates ignored", TftpDupCount())
  EthCount("gaps", TftpGapCount())
  EthCount("strangers answered", TftpStrangerCount())
  EthCount("retransmissions", TftpRetransmitCount())
  EthCount("frames that would not send", gEthSendFail)
  EthCount("the server's port", TftpServerPort())
  EthPad("what it is doing now")
  UartWriteStr(TftpStateText())
  PrintNl()
  ; THE SERVER'S PORT IS NOT 69 AND MUST NOT BE, once a transfer has
  ; started. It is printed because a client still talking to 69 is the
  ; classic first-TFTP-client failure and this is the line that shows
  ; whether it happened. 69 here with blocks above zero would be a bug
  ; in tftp.pi4 and not in the network.
  If TftpTidLocked() = 1
    Print("  The server answered from port ")
    PrintDec(TftpServerPort())
    PrintN(", not from 69, which is what RFC 1350")
    PrintN("  requires and what every packet after the first request was sent to.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  EthSayServer - the server's own refusal, in its own words and in
;  English.
;
;  TWO SEPARATE THINGS AND BOTH ARE PRINTED. The numbered code is one of
;  eight [rfc1350.txt:511-522] and TftpCodeText() turns it into a
;  sentence; the message string beside it is "intended for human
;  consumption" [rfc1350.txt:412-413] and a real server puts genuinely
;  useful things in it, like the path it actually tried.
;
;  AND WHETHER IT IS WORTH RETRYING. Codes 1 and 2 - file not found and
;  access violation - mean stop; everything else means the same command
;  may well work a second time. That is U-Boot's judgement at
;  v2025.01_net_tftp.c:681-697 and TftpRetryWorthwhile() reports it.
; ----------------------------------------------------------------------
Procedure EthSayServer()
  If TftpServerCode() = 0 And TftpServerMessageLen() = 0
    ProcedureReturn
  EndIf
  Print("  The server refused it: ")
  UartWriteStr(TftpCodeText(TftpServerCode()))
  PrintNl()
  If TftpServerMessageLen() > 0
    Print("  In the server's own words: ")
    UartWriteStr(TftpServerMessage())
    PrintNl()
  EndIf
  If TftpRetryWorthwhile() = 1
    PrintN("  That is worth trying again - it is not a refusal about the file")
    PrintN("  itself, so the same command may well work a second time.")
  Else
    PrintN("  That is not worth trying again until something changes at the server:")
    PrintN("  the file is not there, or this board is not allowed to have it.")
  EndIf
EndProcedure

; PayloadTop MOVED to Anvil/Core/memrange.pi4 on 2026-09-05, beside
; InPayload and PutWindows, which are the same question asked two other
; ways. It moved because Anvil/Core/netrecv.pi4 needs it and is included
; BEFORE this file - this language resolves a call to a procedure it has
; already seen, so a caller ahead of its callee does not link - and
; because a window question that lives in the file which happens to hold
; the TFTP commands is where the second copy of it eventually gets
; written. Nothing about it changed and its whole header went with it.

; ----------------------------------------------------------------------
;  EthStart - everything both transfer commands do before the first
;  packet: the wire, the addresses, the timer, our own port, and the
;  next hop. 1 if the transfer may begin.
;
;  ONE PROCEDURE BECAUSE THERE ARE TWO CALLERS AND THEY MUST NOT DRIFT.
;  A get and a put that disagreed about which of these steps happens, or
;  in what order, would be two different clients sharing a name.
;
;  OUR TRANSFER IDENTIFIER IS U-BOOT'S ARITHMETIC on the millisecond
;  clock, 1024 + (millis() % 3072) [v2025.01_net_tftp.c:924, reproduced
;  at tftp.pi4:1033]. net.pi4 is then bound to it so that a datagram
;  addressed to any other port of ours is dropped before tftp.pi4 sees
;  it.
; ----------------------------------------------------------------------
Procedure.i EthStart()
  Define port.i

  gEthFrames = 0
  gEthUdp = 0
  gEthArpOut = 0
  gEthSendFail = 0

  If NetLinkUpFull() = 0
    ProcedureReturn 0
  EndIf
  If NetResolveHop(gEthSrv) = 0
    ProcedureReturn 0
  EndIf

  TftpInit()
  If TftpSetTimeout(#ETH_RETRY_MS, #ETH_RETRIES) = 0
    PrintN("!! the transfer timer was refused, which is a fault in this monitor")
    PrintN("   rather than in anything you typed. Nothing was transferred.")
    EthWhyTftp()
    ProcedureReturn 0
  EndIf

  port = TftpSuggestPort(millis())
  If NetUdpBind(LinkKind(), port) = 0
    PrintN("!! the network stack would not listen on this transfer's own port, so")
    PrintN("   nothing was transferred.")
    EthWhyNet()
    ProcedureReturn 0
  EndIf
  ProcedureReturn port
EndProcedure

; ======================================================================
;  get - pull a file off a TFTP server into memory
; ======================================================================
;  U-Boot spells this tftpboot and takes its arguments the other way
;  round - "[loadAddress] [[hostIPaddr:]bootfilename]"
;  [Reference/v2025.01_cmd_net.c:61-65]. Anvil spells it get and takes
;  the NAME FIRST, because that is the shape `load` and `save` already
;  have in this monitor and a person types those far more often than
;  they type U-Boot. Two commands in one prompt that take a name and an
;  address in opposite orders is a trap.
;
;  AND FOR THAT REASON tftpboot IS NOT ACCEPTED AS AN ALIAS. An alias
;  whose arguments mean something different from the command it is
;  imitating is worse than no alias: a line pasted out of a U-Boot
;  session would run, and would fetch a file called 0x400000. The
;  settings family refuses setenv for the same reason and the help says
;  so out loud.
;
;  THE DEFAULT ADDRESS IS HwStageAddr(), exactly as `load`'s is, so the two
;  ways of getting a payload onto this board put it in the same place.
; ======================================================================
Procedure CmdGet()
  Define nm.i
  Define a.i
  Define top.i
  Define cap.i
  Define port.i

  nm = ArgWord()
  If nm = 0
    PrintN("get <name> [address]")
    PrintN("  fetch a file from the TFTP server into memory, over Ethernet. The")
    PrintN("  name is the file as the server knows it and the address is hex.")
    Print("  Without an address it loads at ")
    PutAddr(HwStageAddr())
    PrintN(", which is where load puts")
    PrintN("  things too.")
    PrintN("  Nothing was transferred, because no filename was given.")
    PrintN("  Type net to see which server it would ask and what this board's own")
    PrintN("  address is.")
    ProcedureReturn
  EndIf

  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was transferred.")
      ProcedureReturn
    EndIf
    a = HwStageAddr()
  EndIf

  ; NO AddBase HERE, and it is said rather than left to be found. The
  ; default address belongs to the memory family - memory, write, fill,
  ; copy and compare - and get is a loader like load and receive, none
  ; of which add it either. A silent exception is a trap; a stated one
  ; is a rule.
  If gBase <> 0
    Print("  note: get does NOT add the default address ")
    PutAddr(gBase)
    PrintNl()
    PrintN("  - no loader in this monitor does. The address used is the one typed.")
  EndIf

  If HitsMonitor(a, a) <> 0
    Print("!! ")
    PutAddr(a)
    PrintN(" is inside the monitor itself, so nothing was transferred.")
    Print("   Anvil occupies ")
    PutAddr(gMonHitLo)
    Print(" to ")
    PutAddr(gMonHitHi)
    PrintN(", and a file written there")
    PrintN("   would overwrite the code that is reading this line to you. These")
    PrintN("   are the windows a file may go into:")
    PutWindows()
    ProcedureReturn
  EndIf
  top = PayloadTop(a)
  If top = 0
    Print("!! ")
    PutAddr(a)
    PrintN(" is not inside either payload window, so nothing was")
    PrintN("   transferred. A TFTP transfer does not know how long the file is")
    PrintN("   until it ends, so the destination has to be somewhere the whole of")
    PrintN("   it is allowed to land. These are the windows:")
    PutWindows()
    ProcedureReturn
  EndIf
  cap = top - a + 1

  port = EthStart()
  If port = 0
    ProcedureReturn
  EndIf

  If TftpSetMemory(a, cap) = 0
    PrintN("!! the destination was refused, so nothing was transferred.")
    EthWhyTftp()
    ProcedureReturn
  EndIf

  Print("Fetching ")
  UartWriteStr(nm)
  Print(" from ")
  PutIp(gEthSrv)
  PrintN(" into memory.")
  Print("  It will be written from ")
  PutAddr(a)
  Print(" upwards, and at most ")
  PrintDec(cap)
  PrintNl()
  PrintN("  bytes of it will fit before the end of that window. A file longer")
  PrintN("  than that stops at the edge and the transfer fails rather than")
  PrintN("  writing past it.")
  UartDrain()

  If TftpBeginRead(gEthSrv, nm, port) = 0
    PrintN("!! the read request could not be built, so nothing was transferred.")
    EthWhyTftp()
    ProcedureReturn
  EndIf
  ; The read request, and it is the ONE packet in a transfer that goes
  ; to port 69 [rfc1350.txt:206]. Everything after it goes to whatever
  ; port the server answers from.
  If NetXferSend() = 0
    PrintN("!! the read request would not go out on the wire, so nothing was")
    PrintN("   transferred.")
    EthWhyNet()
    LinkWhySay()
    ProcedureReturn
  EndIf

  If NetXferRun() = 0
    PrintN("The transfer did not complete.")
    EthWhyTftp()
    EthSayServer()
    EthTally()
    ProcedureReturn
  EndIf

  If TftpComplete() <> 1
    PrintN("!! the transfer ended without completing, so what is in memory is part")
    PrintN("   of a file and NOT a file. Do not run it.")
    EthWhyTftp()
    EthSayServer()
    EthTally()
    ProcedureReturn
  EndIf

  ; A ZERO-LENGTH FILE IS A COMPLETED TRANSFER. RFC 1350 ends a transfer
  ; on a DATA packet carrying nought to 511 bytes, and nought is a legal
  ; count [rfc1350.txt:361-364], so an empty file on the server arrives
  ; here as one four-byte, all-header block and completes. Nothing was
  ; written, so there is nothing to print a range for and nothing to arm
  ; run with - and saying so is better than printing "00400000 through
  ; 003FFFFF", which is what the ordinary line below would produce.
  If TftpBytes() = 0
    Print("The file ")
    UartWriteStr(nm)
    PrintN(" is EMPTY - the server had it, and it is nought bytes")
    PrintN("long. Nothing was written into memory and run has not been armed.")
    EthTally()
    ProcedureReturn
  EndIf

  Print("Fetched ")
  PrintDec(TftpBytes())
  Print(" bytes into memory, filling ")
  PutAddr(a)
  Print(" through ")
  PutAddr(a + TftpBytes() - 1)
  PrintN(".")
  EthTally()
  gEntry = a
  gHaveEntry = 1
  Print("  Its entry point is ")
  PutAddr(a)
  PrintN(", which is where run will jump if you")
  PrintN("  type run with no address of your own.")
  PrintN("  Nothing here has checked that the bytes in memory are the bytes on the")
  PrintN("  server. Type crc32 with this address and that byte count and compare")
  PrintN("  it against the same file on the host - TFTP has no checksum of its")
  PrintN("  own, only UDP's, which covers one datagram at a time and not the file.")
EndProcedure

; ======================================================================
;  put - send a block of memory to a TFTP server as a file
; ======================================================================
;  THE JUNIOR PARTNER, and tftp.pi4:19-24 says so itself: the write
;  direction earns its place mostly because the canonical fix for the
;  Sorcerer's Apprentice bug lives on the sending side. It is genuinely
;  useful here all the same - it is how a memory image, a screenshot
;  buffer or a dump gets off this board and onto a machine with a disk,
;  without the eleven-kilobyte-a-second serial line.
;
;  THE ADDRESS IS NOT WINDOW-CHECKED, and that is deliberate and it
;  matches this monitor's existing rule. `memory` and `crc32` read any
;  address at all because being able to point them at a register block
;  is most of their value, and put only READS. It refuses nothing about
;  where the bytes come from; it is the length that is guarded, because
;  the length is what the arithmetic can overflow.
;
;  MOST TFTP SERVERS REFUSE A WRITE BY DEFAULT. tftpd64 needs the file
;  to exist already, or its overwrite option turned on; dnsmasq's TFTP
;  server has no write support at all. That is not a fault in this
;  command and the server says so itself in its ERROR packet, which is
;  printed in full.
; ======================================================================
Procedure CmdPut()
  Define nm.i
  Define a.i
  Define n.i
  Define port.i

  nm = ArgWord()
  If nm = 0
    PrintN("put <name> <address> <length>")
    PrintN("  send that many bytes of memory to the TFTP server as a file. The")
    PrintN("  address and the length are both hex, and the length is in bytes.")
    PrintN("  Nothing was transferred, because no filename was given.")
    PrintN("  Most servers refuse to be written to until they are told to allow")
    PrintN("  it, and some cannot be written to at all. The server's own refusal")
    PrintN("  is printed here in full when that happens.")
    ProcedureReturn
  EndIf

  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was transferred.")
      ProcedureReturn
    EndIf
    PrintN("!! put needs an address to send from, in hex, and none was given, so")
    PrintN("   nothing was transferred.")
    PrintN("   put <name> <address> <length>")
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    PrintN("!! put needs a length in bytes, in hex, and none was given, so nothing")
    PrintN("   was transferred. There is no default: sending the wrong number of")
    PrintN("   bytes writes a wrong file onto somebody else's disk and nothing")
    PrintN("   here could guess the right one.")
    PrintN("   put <name> <address> <length>")
    ProcedureReturn
  EndIf
  If n <= 0
    PrintN("!! a length of zero bytes would create an empty file on the server,")
    PrintN("   which is legal TFTP and almost always a mistyped length. Nothing")
    PrintN("   was transferred. Give the number of bytes in hex.")
    ProcedureReturn
  EndIf
  ; The same ceiling the memory family uses, and for the same reason:
  ; "addr + length - 1" with a sixteen-digit length wraps past the top
  ; of a signed .i, and a wrapped sum makes every range test agree with
  ; it. See the note above #LEN_MAX.
  If n > #LEN_MAX
    PrintN("!! that is more than a gigabyte, which is more than the address")
    PrintN("   arithmetic here will stay honest over. Nothing was transferred.")
    ProcedureReturn
  EndIf

  If gBase <> 0
    Print("  note: put does NOT add the default address ")
    PutAddr(gBase)
    PrintNl()
    PrintN("  - no loader in this monitor does. The address used is the one typed.")
  EndIf

  port = EthStart()
  If port = 0
    ProcedureReturn
  EndIf

  Print("Sending ")
  PrintDec(n)
  Print(" bytes from ")
  PutAddr(a)
  Print(" to ")
  PutAddr(a + n - 1)
  PrintNl()
  Print("  to ")
  PutIp(gEthSrv)
  Print(" as the file ")
  UartWriteStr(nm)
  PrintN(".")
  PrintN("  The memory being sent is read again on every retransmission, so do not")
  PrintN("  type anything that changes it while this is running.")
  UartDrain()

  If TftpBeginWrite(gEthSrv, nm, port, a, n) = 0
    PrintN("!! the write request could not be built, so nothing was transferred.")
    EthWhyTftp()
    ProcedureReturn
  EndIf
  If NetXferSend() = 0
    PrintN("!! the write request would not go out on the wire, so nothing was")
    PrintN("   transferred.")
    EthWhyNet()
    LinkWhySay()
    ProcedureReturn
  EndIf

  If NetXferRun() = 0
    PrintN("The transfer did not complete, so the file on the server is either")
    PrintN("absent or part of what was meant to be sent. Do not trust it.")
    EthWhyTftp()
    EthSayServer()
    EthTally()
    ProcedureReturn
  EndIf

  If TftpComplete() <> 1
    PrintN("!! the transfer ended without completing, so the file on the server is")
    PrintN("   part of what was meant to be sent. Do not trust it.")
    EthWhyTftp()
    EthSayServer()
    EthTally()
    ProcedureReturn
  EndIf

  Print("Sent ")
  PrintDec(TftpBytes())
  Print(" bytes to ")
  PutIp(gEthSrv)
  Print(" as ")
  UartWriteStr(nm)
  PrintN(".")
  EthTally()
  PrintN("  The server acknowledged the last block, which is what completes a")
  PrintN("  write, so it has all of it. Whether it wrote all of it to a disk is")
  PrintN("  the server's business and not something TFTP reports. Type crc32 with")
  PrintN("  this address and this length and compare it against the file on the")
  PrintN("  host if it matters.")
EndProcedure

; ----------------------------------------------------------------------
;  net_PinApply - APPLY A `net link` PIN NOW, NOT AT THE NEXT COMMAND.
;
;  Until 2026-09-07 the pin was recorded and the interface changed at
;  whatever command happened next, which was defensible and useless in
;  the one case it exists for: an operator plugs a cable in mid-session,
;  types `net link wired`, and wants THE CONSOLE on it. Recording the
;  intention and then answering out of the old interface leaves that
;  person waiting for something that will never print.
;
;  So the bring-up is paid here, where the person typing can see the
;  five-second wait they have just asked for, and the console re-derives
;  itself onto whatever the stack now holds. HwLinkOpen prints its own
;  refusal in a full sentence when the pinned interface has no address,
;  and that refusal is the honest answer - `net link wired` followed by
;  `dhcp` is then the two-command sequence, and the second one arms the
;  console by itself.
; ----------------------------------------------------------------------
Procedure net_PinApply()
  If HwLinkOpen(1) = 0
    ProcedureReturn
  EndIf
  ; A PIN THAT LANDS ON A LINK WITH A STORED ADDRESS TAKES THE SAME TAIL
  ; A LEASE TAKES. HwLinkOpen has already put the three numbers into the
  ; IP layer; this is the rest of it - record them, tell the board, arm
  ; the console - and it is the one copy of that list.
  If LinkKind() <> #HW_LINK_NONE And EthHasIpConfig() <> 0
    NetAddressBound(LinkKind(), gEthIp, gEthMask, gEthGw, #NET_ADDR_SAVED)
  EndIf
  LinkSay()
  NetConsoleRearm()
  NetConsoleSay()
EndProcedure

; ----------------------------------------------------------------------
;  NetStaticApply - PUT THE STORED ADDRESS ON THE WIRE NOW, and take the
;  same tail a lease takes. Returns the #HW_LINK_* kind now carrying it,
;  or #HW_LINK_NONE.
;
;  WHAT IT IS FOR, and it is the whole of the 2026-09-07 evening. Typing
;  `net address 192.168.137.2`, `net netmask 255.255.255.0` and `net
;  gateway 192.168.137.1` into a board with a cable running straight to
;  the machine trying to reach it produced a board that ANSWERED PING ON
;  THAT CABLE AND HAD NO CONSOLE ON IT. Three strings went into the
;  settings store and nothing else happened: the interface was not
;  re-chosen, the board was not told, and the console - which arms from
;  the interface holding the address - had nothing new to derive from.
;  The bench spent an evening with a board it could ping and could not
;  talk to, which is the exact failure this whole lane exists to end.
;
;  IT IS NOT A SECOND PATH TO A LEASE'S. HwLinkStaticUp brings the link
;  up and lets the ordinary preference order choose; NetAddressBound is
;  the same tail `dhcp` runs. Nothing here is a copy of anything there,
;  which is why the two cannot drift.
;
;  IT PRINTS NOTHING. Its two callers want different sentences - a
;  command at the prompt, and one line in the boot log - and a procedure
;  that printed would force one of them to say the wrong thing. Bounded
;  in every arm; see HwLinkStaticUp for the arithmetic.
; ----------------------------------------------------------------------
Procedure.i NetStaticApply()
  Define k.i
  If EthHasIpConfig() = 0
    ProcedureReturn #HW_LINK_NONE
  EndIf
  k = HwLinkStaticUp()
  If k = #HW_LINK_NONE
    ProcedureReturn #HW_LINK_NONE
  EndIf
  NetAddressBound(k, gEthIp, gEthMask, gEthGw, #NET_ADDR_SAVED)
  ProcedureReturn k
EndProcedure

; ======================================================================
;  net - the four addresses, and the state of the wire
; ======================================================================
;  This is printenv, setenv and "mii info" all at once, and it is the
;  command to type when get or put has failed, because it names which
;  step is missing. `mount` is the same idea for the boot medium and
;  the help text says so about that one too.
; ======================================================================
Procedure CmdNet()
  Define v.i
  Define ip.i
  Define n.i
  Define k.i
  Define kk.i
  Define isOurs.i
  Define set.i

  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt

  ; ---- net, or net show ---------------------------------------------
  If gWordLen = 0 Or WordIs("show") <> 0
    set = 0
    Print("  this board   ")
    v = SettingsGet(EthKeyAddress())
    If v = 0
      PrintN("not set")
    Else
      UartWriteStr(v)
      PrintNl()
      set = set + 1
    EndIf
    Print("  netmask      ")
    v = SettingsGet(EthKeyNetmask())
    If v = 0
      PrintN("not set")
    Else
      UartWriteStr(v)
      PrintNl()
      set = set + 1
    EndIf
    Print("  gateway      ")
    v = SettingsGet(EthKeyGateway())
    If v = 0
      PrintN("not set")
    Else
      UartWriteStr(v)
      PrintNl()
      set = set + 1
    EndIf
    Print("  TFTP server  ")
    v = SettingsGet(EthKeyServer())
    If v = 0
      PrintN("not set")
    Else
      UartWriteStr(v)
      PrintNl()
      set = set + 1
    EndIf

    ; The DNS server is a fifth, optional thing - not one of the four get
    ; and put need, so it is not counted toward `set`. ping and dns use
    ; it; dhcp fills it in.
    Print("  DNS server   ")
    v = SettingsGet(EthKeyDns())
    If v = 0
      PrintN("not set (optional - set with net dns, or run dhcp)")
    Else
      UartWriteStr(v)
      PrintNl()
    EndIf

    ; ------------------------------------------------------------------
    ; THE FOUR LINES ABOVE ARE THE SETTINGS STORE, AND THE BOARD MAY HOLD
    ; AN ADDRESS THAT IS NOT IN IT.  2026-09-07.
    ;
    ; Until tonight the two could not disagree: an address was either
    ; leased - and `dhcp` writes its result into the store - or typed,
    ; and went into the store as it was typed. So "this board: not set"
    ; meant "this board has no address". A LINK-LOCAL ADDRESS IS
    ; DELIBERATELY NOT STORED: saving it would make the next boot read it
    ; as somebody's considered choice and put it on the wire without a
    ; single probe, which is the collision RFC 3927 exists to prevent.
    ; So the store now legitimately says nothing while the board is
    ; answering on 169.254.x.y with its console listening there.
    ;
    ; PRINTING "not set" AND STOPPING WOULD BE THE MONITOR LYING ABOUT
    ; THE ONE THING SOMEBODY TYPES `net` TO FIND OUT. The live address is
    ; named here, and the advice below is narrowed so that it no longer
    ; reads as "this board has no address" when it plainly has one.
    ;
    ; ONE ADDRESS IS NAMED HERE AND THE BOARD MAY HOLD SEVERAL, so the one
    ; named is the PREFERRED interface's - the address an outbound datagram
    ; with no better claim leaves with, which is what "in use now" can only
    ; mean on a board with two live interfaces. Every address on every
    ; interface is printed in full by NetSayInterfaces() further down, so
    ; nothing is hidden by naming one here.
    ; ------------------------------------------------------------------
    ip = NetIPv4(NetIfPreferred())
    If ip <> 0 And SettingsGet(EthKeyAddress()) = 0
      Print("  IN USE NOW   ")
      PutIp(ip)
      PrintN("   - held by the interface below, not from the store.")
      PrintN("  It is not in SETTINGS.TXT and it is not meant to be. The sentence")
      PrintN("  further down says where it came from.")
    EndIf

    If set < 4
      PrintN("Not all four addresses are in the settings store, so get and put would")
      PrintN("refuse - they need a TFTP server and three addresses of their own. Set")
      PrintN("them with net address, net netmask, net gateway and net server. Use")
      PrintN("0.0.0.0 for the gateway when there is no router, which is the truth on")
      PrintN("a cable straight between this board and one other machine. None of this")
      PrintN("affects ping, the network console or net recv: those use whatever")
      PrintN("address the board is holding, however it got it.")
    EndIf

    If gEthMacKnown = 1
      Print("  hardware address ")
      PutMac()
      If gEthMacFirmware = 1
        PrintN("   (the firmware's, for this board)")
      Else
        PrintN("   (MADE UP - the firmware would not say)")
      EndIf
    EndIf

    ; ---- WHICH LINK CARRIES TRAFFIC, AND WHY -------------------------
    ; THIS USED TO BE TWO BLOCKS AND ONE OF THEM NAMED A BOARD. The
    ; first read gEthUp - the Pi 4's wired flag - and printed
    ; GenetSpeed() and GenetFullDuplex() and the address of that MAC's
    ; receive region, all from a file that is supposed to name no chip;
    ; the second, below, already asked the portable policy layer. Two
    ; reports about one link is also how they come to disagree, and on a
    ; board carrying traffic over the radio the first one said "the
    ; Ethernet is not up" underneath a line saying the radio was
    ; carrying everything. There is now one report. The speed and the
    ; duplex come from the seam, and whatever else THIS board wants to
    ; say about the link in use it says through HwLinkSayDetail.
    ; The brief for the TCP work asks for this line by name, and it is
    ; here rather than in `wifi` or in `net up` because "which way is my
    ; traffic going" is the first question anybody has on a board with
    ; two interfaces, and `net` is where they will look for it.
    PrintNl()
    ; EVERY INTERFACE THAT HOLDS AN ADDRESS, FIRST. It is the question
    ; `net` is typed to answer and the one the old report got wrong.
    NetSayInterfaces()
    PrintNl()
    ; ------------------------------------------------------------------
    ; RE-DERIVE THE CHOICE BEFORE REPORTING IT, EVERY TIME. 2026-09-07.
    ;
    ; This used to run only when nothing had been chosen since the last
    ; reset, and the rest of the time it printed LinkWhyText() - the
    ; reason STAMPED at the moment of the last choice. On a board whose
    ; radio leases AFTER the cable came up, that stamp says "the radio is
    ; not joined to a network with an address of its own", and `net`
    ; printed exactly that sentence underneath its own line reporting the
    ; radio's lease. A report that contradicts itself two lines apart is
    ; worse than no report: it is the monitor lying about the one thing
    ; somebody typed `net` to find out, which is the fault this whole
    ; lane exists to end.
    ;
    ; IT COSTS ONE MDIO READ on a link that is already up - HwLinkOpen's
    ; own re-check - and it prints nothing on success. needIp is 0, so an
    ; interface with a link and no address still counts: `net` is a
    ; report and not a refusal.
    ; ------------------------------------------------------------------
    HwLinkOpen(0)
    If LinkUp() = 0
      PrintN("NOTHING IS CARRYING TRAFFIC AT THE MOMENT.")
      Print("  ")
      UartWriteStr(LinkWhyText())
      PrintN(".")
      PrintN("  net has just tried to choose one and could not, so this is the")
      PrintN("  live answer and not a stale one.")
    Else
      LinkSay()
      LinkSayRate()
      HwLinkSayDetail()
      Print("  Neighbours known right now: ")
      PrintDec(NetArpCount(LinkKind()))
      PrintN(". An entry expires if nothing is heard")
      PrintN("  from that neighbour, so this number going down on its own is normal.")
      Print("  Frames in ")
      PrintDec(LinkRxFrames())
      Print(", out ")
      PrintDec(LinkTxCount())
      Print(", refused ")
      PrintDec(LinkTxFails())
      Print(", link changes ")
      PrintDec(LinkSwaps())
      PrintN(".")
      If LinkEapolCount() > 0
        Print("  Wireless rekeys serviced while a command was running: ")
        PrintDec(LinkEapolCount())
        PrintN(".")
      EndIf
      Print("  The largest frame this interface will carry is ")
      PrintDec(LinkTxMax())
      PrintN(" bytes,")
      Print("  so the most TCP data one segment can hold on it is ")
      PrintDec(LinkTxMax() - 54)
      PrintN(".")
    EndIf

    ; ---- AND WHERE THE ADDRESS IN USE CAME FROM ----------------------
    ; A lease and a stored address behave identically from here on - the
    ; same three numbers, the same console, arrived at by the same path -
    ; and they FAIL differently. Saying which costs one line and answers
    ; the first question anybody has about a board that has gone quiet.
    ; Nothing is printed when nothing has been bound, because "no address
    ; has been bound" is already the subject of every line above.
    If gEthAddrFrom <> #NET_ADDR_NONE
      Print("  ")
      UartWriteStr(NetAddrFromText())
      PrintNl()
    EndIf

    ; ---- AND WHERE THE CONSOLE IS ------------------------------------
    ; "Can I reach this board, and at what address" is the other first
    ; question on a board with two interfaces, and until 2026-09-07 the
    ; only place it was answered was `wifi ip` - which could only ever
    ; give one interface's answer, and gave it whether or not the console
    ; was actually there. This is the console's own account of itself.
    PrintNl()
    NetConsoleSay()

    If SettingsDirty() <> 0
      PrintN("There are changes here that are not in the file. Type settings save.")
    EndIf
    PrintN("Nothing loads the settings file for you. After a reset, type settings")
    PrintN("load to bring these four addresses back.")
    ProcedureReturn
  EndIf

  ; ---- net link auto | wired | wifi -----------------------------------
  ; The override. It exists because the automatic choice deliberately
  ; does NOT spend five seconds hunting for a cable when the radio is
  ; already working (the reasoning is written out above HwLinkOpen in
  ; the board file), so plugging a cable in mid-session needs one word
  ; from the operator to be noticed.
  ;
  ; THE PIN IS A #HW_LINK_* KIND AND NOT A WORD OF ITS OWN. It was
  ; #LINK_PREF_AUTO / _WIRED / _WIFI and a gLinkPref in the Pi 4's board
  ; file until 2026-09-05, which was a second vocabulary for a thing the
  ; kinds already name, and half of one decision living where the other
  ; half could not see it. LinkSetPin takes the kind; the words typed at
  ; the prompt are this command's business and the kinds are the seam's.
  ; A board that refuses the kind says so at the next command through
  ; HwLinkOpen, in a full sentence, rather than being contradicted here
  ; by a list of what this monitor thinks boards have.
  If WordIs("link") <> 0
    SkipSpace()
    gWordAt = gPos
    SkipWord()
    gWordLen = gPos - gWordAt
    If gWordLen = 0
      NetSayInterfaces()
      PrintNl()
      LinkSay()
      ; WHERE THE ADDRESS ON IT CAME FROM, in the same breath as which
      ; link it is. `net link` on a board that had taken no lease used to
      ; report "the cable is in but no address is set for it yet" while
      ; three perfectly good addresses sat in the settings store, which
      ; is a true sentence about a stale decision and reads as a fault.
      ; The decision is not stale any more - a stored address is applied
      ; the moment it is complete - and this line says which kind of
      ; address the answer is about.
      If gEthAddrFrom <> #NET_ADDR_NONE
        Print("  ")
        UartWriteStr(NetAddrFromText())
        PrintNl()
      EndIf
      NetConsoleSay()
      Print("  net link wired   pin it to ")
      UartWriteStr(HwLinkName(#HW_LINK_WIRED))
      PrintNl()
      Print("  net link wifi    pin it to ")
      UartWriteStr(HwLinkName(#HW_LINK_WIFI))
      PrintNl()
      PrintN("  net link auto    choose again each time, wired preferred")
      ProcedureReturn
    EndIf
    If WordIs("auto") <> 0
      LinkSetPin(#HW_LINK_NONE)
      PrintN("The interface will be chosen again the next time a network command")
      PrintN("runs: the wired port when the cable is in and it has an address,")
      PrintN("otherwise the radio.")
      net_PinApply()
      ProcedureReturn
    EndIf
    If WordIs("wired") <> 0 Or WordIs("eth") <> 0 Or WordIs("ethernet") <> 0
      LinkSetPin(#HW_LINK_WIRED)
      Print("Pinned to ")
      UartWriteStr(HwLinkName(#HW_LINK_WIRED))
      PrintN(". Bringing that interface up now, which")
      PrintN("on a wired port takes up to five seconds while it waits for the link")
      PrintN("and for auto-negotiation. From here on it will REFUSE rather than fall")
      PrintN("back to anything else. net link auto undoes this.")
      net_PinApply()
      ProcedureReturn
    EndIf
    If WordIs("wifi") <> 0 Or WordIs("radio") <> 0
      LinkSetPin(#HW_LINK_WIFI)
      Print("Pinned to ")
      UartWriteStr(HwLinkName(#HW_LINK_WIFI))
      PrintN(". Bringing that interface up now. From here")
      PrintN("on it will REFUSE rather than fall back to anything else if it is not")
      PrintN("joined or has no address. net link auto undoes this.")
      net_PinApply()
      ProcedureReturn
    EndIf
    PrintN("!! net link takes auto, wired or wifi, so nothing was changed.")
    ProcedureReturn
  EndIf

  ; ---- net recv -------------------------------------------------------
  ; An image over a TCP connection, into a bounded window of DRAM. The
  ; whole of it is in Anvil/Core/netrecv.pi4, which is included ahead of
  ; this file; this line is the dispatch and nothing else.
  If WordIs("recv") <> 0 Or WordIs("receive") <> 0
    CmdNetRecv()
    ProcedureReturn
  EndIf

  ; ---- net up / net down ---------------------------------------------
  If WordIs("up") <> 0
    NetLinkUpFull()
    ProcedureReturn
  EndIf

  ; WHETHER THERE WAS ANYTHING TO STOP IS THE BOARD'S ANSWER, not a
  ; global read from here. HwLinkClose() returns 1 when it actually
  ; stopped something and 0 when there was nothing running, which is the
  ; whole difference between the two sentences below - and it used to be
  ; decided by reading gEthUp, one board's wired flag, from a shared
  ; command. A board with nothing to stop is not a board that failed.
  If WordIs("down") <> 0
    If HwLinkClose() = 0
      PrintN("Nothing was running, so nothing was stopped and nothing changed. No")
      PrintN("interface on this board had been brought up since the last reset.")
      ProcedureReturn
    EndIf
    LinkForget()
    PrintN("The interface has been stopped. It is no longer sending or receiving")
    PrintN("and its receive engine is no longer writing into memory. The next get")
    PrintN("or put brings one back up by itself.")
    ProcedureReturn
  EndIf

  ; ---- the four setters ----------------------------------------------
  ; ONE BLOCK, FOUR KEYS. The validation, the refusal wording and the
  ; confirmation are identical for all four and writing them out four
  ; times is four chances for them to drift apart.
  ;
  ; THREE OF THE FIVE MAKE UP THIS BOARD'S OWN ADDRESS and the other two
  ; name other machines, so `isOurs` is carried alongside the key rather
  ; than re-derived by comparing key pointers later. Only the three put
  ; anything on the wire.
  k = 0
  isOurs = 0
  If WordIs("address") <> 0
    k = EthKeyAddress()
    isOurs = 1
  ElseIf WordIs("netmask") <> 0 Or WordIs("mask") <> 0
    k = EthKeyNetmask()
    isOurs = 1
  ElseIf WordIs("gateway") <> 0 Or WordIs("router") <> 0
    k = EthKeyGateway()
    isOurs = 1
  ElseIf WordIs("server") <> 0
    k = EthKeyServer()
  ElseIf WordIs("dns") <> 0
    k = EthKeyDns()
  EndIf

  If k <> 0
    v = ArgWord()
    If v = 0
      ; THE COMMAND WORD IS ECHOED, NOT THE KEY NAME. ArgWord() moved
      ; gPos but left gWordAt and gWordLen alone, so the word the
      ; operator actually typed is still there to be printed - and "net
      ; address needs an address" is a sentence about what was typed,
      ; where "net.address needs an address" is a sentence about a
      ; storage key nobody mentioned.
      Print("!! net ")
      n = 0
      While n < gWordLen And n < 24
        UartWrite(gLine[gWordAt + n] & $FF)
        n = n + 1
      Wend
      PrintN(" needs an address, and none was given, so nothing")
      PrintN("   was changed. Write it as four numbers nought to 255 separated by")
      PrintN("   full stops, for example 192.168.1.50. Type net to see what is set")
      PrintN("   now.")
      ProcedureReturn
    EndIf
    ip = ParseDotted(v)
    If ip < 0
      Print("!! ")
      UartWriteStr(v)
      PrintN(" is not an address, so nothing was changed. It has to")
      PrintN("   be exactly four numbers, each nought to 255, separated by three")
      PrintN("   full stops and with nothing else in it - 192.168.1.50 and not")
      PrintN("   192.168.1 and not 192.168.1.50/24.")
      ProcedureReturn
    EndIf
    If SettingsSet(k, v) = 0
      SettingsSayWhyNot()
      PrintN("   Nothing was changed.")
      ProcedureReturn
    EndIf
    Print("Set. ")
    UartWriteStr(k)
    Print(" is now ")
    PutIp(ip)
    PrintN(".")
    PrintN("  This is in memory only. Type settings save to write it to the medium.")

    ; ------------------------------------------------------------------
    ; AND PUT IT ON THE WIRE, NOW, IF IT CAN GO ON THE WIRE.
    ;
    ; Until 2026-09-07 these three commands wrote a string into a store
    ; and stopped there. Whether the board ever used the address depended
    ; on some later command choosing an interface, and the automatic
    ; choice will not pay the five-second wired bring-up while a radio is
    ; working - which is right for `ping` and useless here, because
    ; typing this command IS the operator saying which address this board
    ; answers to. The measured cost of the gap: a board with a cable
    ; running straight to the machine trying to reach it, answering that
    ; machine's pings, with no console on the cable at all.
    ;
    ; IT TAKES THE SAME PATH A LEASE TAKES. NetStaticApply brings the
    ; link up, lets the ordinary preference order choose, and runs the
    ; tail `dhcp` runs. Nothing here is a second copy of either.
    ;
    ; ONLY THE THREE THAT MAKE UP THIS BOARD'S ADDRESS, so `net server`
    ; and `net dns` - which name other machines and change nothing about
    ; this one - still cost nothing at all.
    ; ------------------------------------------------------------------
    If isOurs <> 0
      kk = NetStaticApply()
      If kk <> #HW_LINK_NONE
        Print("  It is on the wire now, over ")
        UartWriteStr(HwLinkName(kk))
        PrintN(".")
        NetConsoleSay()
      ElseIf SettingsHas(EthKeyAddress()) = 0 Or SettingsHas(EthKeyNetmask()) = 0 Or SettingsHas(EthKeyGateway()) = 0
        PrintN("  It is not on the wire yet: an address, a netmask and a gateway are")
        PrintN("  all three needed before this board can answer to one. Use 0.0.0.0")
        PrintN("  for the gateway when there is no router, which is the truth on a")
        PrintN("  cable straight between this board and one other machine.")
      Else
        PrintN("  All three are set but nothing is carrying them: there is no cable")
        PrintN("  in the Ethernet socket, or the link did not come up. Plug one in")
        PrintN("  and type net link wired, or reset with the cable in - the boot")
        PrintN("  applies a stored address by itself when no DHCP server answers.")
      EndIf
    EndIf

    ; Every one of the four is checked against the other three the
    ; moment the fourth is set, because a netmask and a gateway that
    ; disagree are only wrong TOGETHER and finding that out at the
    ; moment of typing is worth far more than finding it out at the
    ; moment of transferring.
    n = 0
    If SettingsHas(EthKeyAddress()) <> 0
      n = n + 1
    EndIf
    If SettingsHas(EthKeyNetmask()) <> 0
      n = n + 1
    EndIf
    If SettingsHas(EthKeyGateway()) <> 0
      n = n + 1
    EndIf
    If SettingsHas(EthKeyServer()) <> 0
      n = n + 1
    EndIf
    If n < 4
      Print("  ")
      PrintDec(4 - n)
      PrintN(" of the four addresses are still not set, so get and put would")
      PrintN("  refuse. Type net to see which.")
      ProcedureReturn
    EndIf
    If EthConfig() = 1
      PrintN("  All four addresses are set and they agree with each other. get and")
      PrintN("  put will bring the Ethernet up by themselves from here.")
    EndIf
    ProcedureReturn
  EndIf

  ; ---- net forget -----------------------------------------------------
  If WordIs("forget") <> 0
    n = 0
    If SettingsHas(EthKeyAddress()) <> 0
      SettingsRemove(EthKeyAddress())
      n = n + 1
    EndIf
    If SettingsHas(EthKeyNetmask()) <> 0
      SettingsRemove(EthKeyNetmask())
      n = n + 1
    EndIf
    If SettingsHas(EthKeyGateway()) <> 0
      SettingsRemove(EthKeyGateway())
      n = n + 1
    EndIf
    If SettingsHas(EthKeyServer()) <> 0
      SettingsRemove(EthKeyServer())
      n = n + 1
    EndIf
    If n = 0
      PrintN("There was no network configuration, so nothing was forgotten and")
      PrintN("nothing changed.")
      ProcedureReturn
    EndIf
    Print("Forgotten ")
    PrintDec(n)
    PrintN(" of the four network addresses. The Ethernet itself is")
    PrintN("untouched and stays up if it was up; it is the configuration that has")
    PrintN("gone, and get and put will refuse until it is set again.")
    PrintN("  A copy is still in SETTINGS.TXT on the medium until you type")
    PrintN("  settings save. Until then a reset and a settings load bring it back.")
    ProcedureReturn
  EndIf

  Print("? net does not know the word ")
  n = 0
  While n < gWordLen And n < 24
    UartWrite(gLine[gWordAt + n] & $FF)
    n = n + 1
  Wend
  PrintN(", so nothing was done and nothing was changed.")
  PrintN("  net                        show the four addresses and the wire")
  PrintN("  net show                   the same thing, spelled out")
  PrintN("  net address <a.b.c.d>      the address this board answers to")
  PrintN("  net netmask <a.b.c.d>      also spelled net mask")
  PrintN("  net gateway <a.b.c.d>      also spelled net router. 0.0.0.0 for none")
  PrintN("  net server <a.b.c.d>       the machine serving the files")
  PrintN("  net dns <a.b.c.d>          the DNS resolver, for dns and ping by name")
  PrintN("  net recv <port> <addr>     receive one image over TCP into memory,")
  PrintN("                             hash it, and print the length and digest")
  PrintN("  net up                     bring the Ethernet up now and report")
  PrintN("  net down                   stop it")
  PrintN("  net forget                 take all four addresses back out")
EndProcedure


; ======================================================================
;  ping, dns, dhcp - the three network commands that ride the same pump
;  as get and put, gated by #CAP_NET.
; ======================================================================
;  These are CORE. They name no chip and touch no register. Each asks the
;  board whether it has a network interface at all (RequireCap over
;  #CAP_NET), and if so it drives net.pi4 for IP/ARP/ICMP/UDP and
;  dns.pi4 and dhcp.pi4 for the two payload codecs, through the same
;  pump get and put use. On a board that declares #CAP_NET = 0 the same
;  command, compiled from the same bytes, refuses cleanly.
;
;  THE PUMP IS NOW LinkPumpNet, NOT GenetRecvWait - 2026-09-04, the
;  ruling of 2026-09-02 and forum topic 591. Until that change these
;  named the wired driver directly, at thirteen call sites in this file
;  and four more in eth.pi4, so on a bench with no cable `ping` and
;  `dns` could not run AT ALL while the board sat at an address it had
;  been given over Wi-Fi and answered pings on it. The IP layer was
;  never the problem - net.pi4 has always been one layer and the
;  wireless console has always driven it - the problem was that the
;  COMMANDS could only reach one interface. They now go through
;  RaspberryPi4/Lib/link.pi4, which picks the interface and carries the
;  frames, and `net` prints which one and why.
;
;  WHAT IS PROVEN AND WHAT IS OWED. The board ANSWERS a ping on silicon
;  (net.pi4 header, 2026-08-26). SENDING a ping, resolving a name, and
;  acquiring a lease are COMPILE-VERIFIED ONLY - the Ethernet cable was
;  out of the board when this was written and no OFFER, no A record and
;  no echo REPLY to a request of ours has ever been parsed off a wire.
;  The codecs are checkable with byte-exact vectors, but the live round
;  trip is owed. Every claim these commands print is a real measurement
;  AT RUN TIME - a measured RTT, the server's own numbers - and none of
;  it is a stand-in for a bench run that has not happened.
; ----------------------------------------------------------------------

#PING_PAYLOAD     = 56        ; bytes of ICMP data, like a typical ping
#PING_REPLY_MS    = 1000      ; how long to wait for one reply
#PING_INTERVAL_MS = 1000      ; between one request and the next
#NET_SLICE_MS     = 50        ; one receive slice while pumping

#DNS_TRIES        = 3
#DNS_REPLY_MS     = 2000

#DHCP_TRIES       = 4
#DHCP_REPLY_MS    = 3000

; A scratch buffer for turning an address back into "a.b.c.d" so a DHCP
; result can be written into the settings store, which holds strings.
Global Dim net_ipStr.a[16]

; ----------------------------------------------------------------------
;  net_PutByteDec - write v (0..255) as decimal into buf at `at`, no
;  leading zeros, and return the next offset. The one place a byte of an
;  address becomes its digits.
; ----------------------------------------------------------------------
Procedure.i net_PutByteDec(*buf, at.i, v.i)
  Protected o.i
  Protected h.i
  Protected t.i
  Protected wrote.i
  o = at
  wrote = 0
  h = v / 100
  If h > 0
    PokeB(*buf + o, 48 + h)
    o = o + 1
    wrote = 1
  EndIf
  t = (v / 10) % 10
  If t > 0 Or wrote = 1
    PokeB(*buf + o, 48 + t)
    o = o + 1
  EndIf
  PokeB(*buf + o, 48 + (v % 10))
  o = o + 1
  ProcedureReturn o
EndProcedure

; ----------------------------------------------------------------------
;  IpToStr - an address to "a.b.c.d" in net_ipStr, NUL-terminated. The
;  inverse of ParseDotted, needed because the settings store holds the
;  strings a person would type and DHCP produces a number. Returns the
;  buffer address. The buffer is reused each call; SettingsSet copies.
; ----------------------------------------------------------------------
Procedure.i IpToStr(ip.i)
  Protected o.i
  o = 0
  o = net_PutByteDec(@net_ipStr[0], o, (ip >> 24) & $FF)
  PokeB(@net_ipStr[0] + o, 46)
  o = o + 1
  o = net_PutByteDec(@net_ipStr[0], o, (ip >> 16) & $FF)
  PokeB(@net_ipStr[0] + o, 46)
  o = o + 1
  o = net_PutByteDec(@net_ipStr[0], o, (ip >> 8) & $FF)
  PokeB(@net_ipStr[0] + o, 46)
  o = o + 1
  o = net_PutByteDec(@net_ipStr[0], o, ip & $FF)
  PokeB(@net_ipStr[0] + o, 0)
  ProcedureReturn @net_ipStr[0]
EndProcedure

Procedure DhcpStore(key.i, ip.i)
  SettingsSet(key, IpToStr(ip))
EndProcedure

; ----------------------------------------------------------------------
;  PutRttNum - a round-trip time in microseconds as "milliseconds.
;  thousandths", the fraction zero-padded to three digits so 834 us reads
;  0.834 and 2 us reads 0.002. No unit is printed - the caller adds " ms"
;  once - so a min/avg/max line does not repeat it three times.
; ----------------------------------------------------------------------
Procedure PutRttNum(us.i)
  Protected ms.i
  Protected fr.i
  ms = us / 1000
  fr = us % 1000
  PrintDec(ms)
  Print(".")
  If fr < 100
    Print("0")
  EndIf
  If fr < 10
    Print("0")
  EndIf
  PrintDec(fr)
EndProcedure

; ----------------------------------------------------------------------
;  net_TicksToUs - a span of CNTPCT ticks to microseconds, using the same
;  clock net.pi4 times its ARP cache with. The fallback frequency is
;  net.pi4's, so a part that will not report its timer frequency gives a
;  plausible number rather than a divide by zero.
; ----------------------------------------------------------------------
Procedure.i net_TicksToUs(dt.i)
  Protected hz.i
  hz = net_TickHz()
  If hz <= 0
    hz = #NET_HZ_FALLBACK
  EndIf
  ProcedureReturn (dt * 1000000) / hz
EndProcedure

; ----------------------------------------------------------------------
;  ResolveName - a name to an IPv4 address through the configured DNS
;  server, or a negative value with an honest reason ALREADY PRINTED.
;
;  THE STACK MUST BE UP before this is called: it sends a real query and
;  waits for a real reply. ping and dns both NetLinkUpSay(1) first. It
;  ARPs the resolver's next hop (NetResolveHop), sends the query, and
;  pumps for the
;  answer with a bounded timeout and a few retries. A reply that is an
;  error code, or that has no A record, is reported as such rather than
;  as a made-up address.
; ----------------------------------------------------------------------
Procedure.i ResolveName(name.i)
  Define dnsStr.i
  Define dnsIp.i
  Define qid.i
  Define srcPort.i
  Define tries.i
  Define deadline.i
  Define n.i
  Define r.i
  Define c.i

  ; A leased resolver belongs to the interface that granted it. Fall back
  ; to the stored resolver only when this interface has none of its own.
  dnsIp = NetIfDns(LinkKind())
  dnsStr = 0
  If dnsIp = 0
    dnsStr = SettingsGet(EthKeyDns())
  EndIf
  If dnsIp = 0 And dnsStr = 0
    Print("!! ")
    UartWriteStr(name)
    PrintN(" is a name, not an address, and no DNS server is set, so it")
    PrintN("   could not be looked up and nothing was done. Set one with net dns")
    PrintN("   <a.b.c.d>, or type dhcp to be given one, or give a dotted-quad")
    PrintN("   address instead.")
    ProcedureReturn -1
  EndIf
  If dnsIp = 0
    dnsIp = ParseDotted(dnsStr)
    If dnsIp <= 0
      PrintN("!! the stored DNS server address is not a usable dotted-quad, so")
      PrintN("   nothing was done. Set it again with net dns <a.b.c.d>.")
      ProcedureReturn -1
    EndIf
  EndIf

  If NetResolveHop(dnsIp) = 0
    ProcedureReturn -1
  EndIf

  ; A source port in the dynamic range, bound so only the reply to it is
  ; delivered. The clock varies it run to run.
  srcPort = $C000 | (millis() & $3FFF)
  qid = millis() & $FFFF
  NetUdpBind(LinkKind(), srcPort)

  If DnsBuildQuery(name, qid) = 0
    Print("!! that name could not be turned into a DNS query: ")
    UartWriteStr(DnsErrorText())
    PrintNl()
    ProcedureReturn -1
  EndIf

  tries = 0
  While tries < #DNS_TRIES
    tries = tries + 1
    If NetUdpBuild(LinkKind(), dnsIp, #DNS_PORT, srcPort, DnsQueryBuf(), DnsQueryLen()) = 0
      PrintN("!! the DNS query could not be built, so nothing was done.")
      EthWhyNet()
      ProcedureReturn -1
    EndIf
    If LinkTxStaged() <> 1
      Print("!! the DNS query would not go out over ")
      UartWriteStr(LinkName())
      PrintN(", so nothing")
      PrintN("   was done.")
      LinkWhySay()
      ProcedureReturn -1
    EndIf

    deadline = millis() + #DNS_REPLY_MS
    While (millis() - deadline) < 0
      If OutBreak() <> 0
        PrintN("  The lookup was stopped, so nothing was done.")
        ProcedureReturn -1
      EndIf
      r = LinkPumpNet(#NET_SLICE_MS)
      If r <> #LINK_RX_NONE
        gEthFrames = gEthFrames + 1
        If r = #NET_IN_UDP
          If NetUdpRxFrom() = dnsIp And NetUdpRxPort() = #DNS_PORT And NetUdpRxDstPort() = srcPort
            c = DnsParseReply(NetUdpRxData(), NetUdpRxLen(), qid)
            If c > 0
              ProcedureReturn DnsResultIp(0)
            EndIf
            Print("!! ")
            UartWriteStr(DnsErrorText())
            PrintNl()
            If c = 0
              Print("   The server answered but had no address for ")
              UartWriteStr(name)
              PrintN(".")
            EndIf
            ProcedureReturn -1
          EndIf
        EndIf
      EndIf
    Wend
  Wend

  Print("!! ")
  UartWriteStr(name)
  PrintN(" did not resolve: the DNS server did not answer in time.")
  PrintN("   Check net dns is the right address and that the server is reachable")
  PrintN("   - ping it by its dotted-quad to see. Nothing was done.")
  ProcedureReturn -1
EndProcedure

; ----------------------------------------------------------------------
;  ping_Idle - pump one receive slice between pings: answer anything the
;  network asks of us (an ARP request, a ping to us), ignore echo replies
;  because their sequence is already accounted for.
; ----------------------------------------------------------------------
Procedure ping_Idle(ms.i)
  Protected r.i
  r = LinkPumpNet(ms)
  If r <> #LINK_RX_NONE
    gEthFrames = gEthFrames + 1
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  ping_WaitReply - wait for the echo reply that matches this request,
;  measuring from t0. Returns the RTT in microseconds, -1 on timeout, or
;  -2 if a key was pressed. A reply is ours only if its source, its
;  identifier AND its sequence all match; anything else is answered if it
;  needs answering and otherwise stepped over.
; ----------------------------------------------------------------------
Procedure.i ping_WaitReply(ip.i, ident.i, seq.i, t0.i)
  Protected deadline.i
  Protected n.i
  Protected r.i
  deadline = millis() + #PING_REPLY_MS
  While (millis() - deadline) < 0
    If OutBreak() <> 0
      ProcedureReturn -2
    EndIf
    r = LinkPumpNet(#NET_SLICE_MS)
    If r <> #LINK_RX_NONE
      gEthFrames = gEthFrames + 1
      If r = #NET_IN_PONG
        If NetPongFrom() = ip And NetPongIdent() = ident And NetPongSeq() = seq
          ProcedureReturn net_TicksToUs(net_Ticks() - t0)
        EndIf
      EndIf
    EndIf
  Wend
  ProcedureReturn -1
EndProcedure

; ======================================================================
;  ping - ICMP echo, one a second, until a key is pressed
; ======================================================================
Procedure CmdPing()
  Define host.i
  Define ip.i
  Define ident.i
  Define seq.i
  Define t0.i
  Define rtt.i
  Define sent.i
  Define recv.i
  Define lost.i
  Define rmin.i
  Define rmax.i
  Define rsum.i
  Define stop.i
  Define wait.i

  If RequireCap(#CAP_NET, "ping", "this board has no network interface Anvil can use") = 0
    ProcedureReturn
  EndIf

  host = ArgWord()
  If host = 0
    PrintN("ping <host>")
    PrintN("  send ICMP echo requests to a host and time the replies, one a second,")
    PrintN("  until you press a key. The host is a dotted-quad address, or a name if")
    PrintN("  a DNS server is set - net dns <a.b.c.d>, or dhcp.")
    PrintN("  Nothing was sent, because no host was given.")
    ProcedureReturn
  EndIf

  ip = ParseDotted(host)
  If ip < 0
    ip = ResolveName(host)
    If ip < 0
      ProcedureReturn
    EndIf
    Print("  ")
    UartWriteStr(host)
    Print(" is ")
    PutIp(ip)
    PrintNl()
  EndIf

  If NetLinkUpSay(1) = 0
    ProcedureReturn
  EndIf
  If NetResolveHop(ip) = 0
    ProcedureReturn
  EndIf

  ident = millis() & $FFFF
  seq = 0
  sent = 0
  recv = 0
  rmin = 0
  rmax = 0
  rsum = 0
  stop = 0

  Print("Pinging ")
  PutIp(ip)
  Print(" with ")
  PrintDec(#PING_PAYLOAD)
  PrintN(" bytes of data, one a second. Press a key to stop.")
  UartDrain()

  Repeat
    If OutBreak() <> 0
      stop = 1
      Break
    EndIf
    seq = (seq + 1) & $FFFF
    If NetPingBuild(LinkKind(), ip, ident, seq, #PING_PAYLOAD) = 0
      PrintN("!! the echo request could not be built, so this ping stops.")
      EthWhyNet()
      Break
    EndIf
    t0 = net_Ticks()
    If LinkTxStaged() <> 1
      Print("!! the echo request would not go out over ")
      UartWriteStr(LinkName())
      PrintN(", so this")
      PrintN("   ping stops.")
      LinkWhySay()
      Break
    EndIf
    sent = sent + 1

    rtt = ping_WaitReply(ip, ident, seq, t0)
    If rtt = -2
      stop = 1
      Break
    EndIf
    If rtt = -1
      Print("  no reply for seq ")
      PrintDec(seq)
      Print(" within ")
      PrintDec(#PING_REPLY_MS)
      PrintN(" ms")
    Else
      recv = recv + 1
      rsum = rsum + rtt
      If recv = 1
        rmin = rtt
        rmax = rtt
      Else
        If rtt < rmin
          rmin = rtt
        EndIf
        If rtt > rmax
          rmax = rtt
        EndIf
      EndIf
      Print("  reply from ")
      PutIp(NetPongFrom())
      Print(": seq ")
      PrintDec(seq)
      Print(", ")
      PrintDec(NetPongBytes())
      Print(" bytes, time ")
      PutRttNum(rtt)
      PrintN(" ms")
    EndIf

    ; The rest of the second, staying responsive to a keypress and
    ; answering anything the network asks of us in the meantime.
    wait = millis() + #PING_INTERVAL_MS
    While (millis() - wait) < 0
      If OutBreak() <> 0
        stop = 1
        Break
      EndIf
      ping_Idle(#NET_SLICE_MS)
    Wend
    If stop = 1
      Break
    EndIf
  ForEver

  PrintNl()
  Print("--- ")
  PutIp(ip)
  PrintN(" ping statistics ---")
  PrintDec(sent)
  Print(" transmitted, ")
  PrintDec(recv)
  Print(" received, ")
  lost = sent - recv
  If sent > 0
    PrintDec((lost * 100) / sent)
  Else
    PrintDec(0)
  EndIf
  PrintN("% loss")
  If recv > 0
    Print("round-trip min/avg/max = ")
    PutRttNum(rmin)
    Print(" / ")
    PutRttNum(rsum / recv)
    Print(" / ")
    PutRttNum(rmax)
    PrintN(" ms")
  EndIf
  PrintN("These are measured round-trip times, not request times: each is the")
  PrintN("clock between the echo request leaving and its reply arriving back.")
EndProcedure

; ======================================================================
;  dns - resolve a name and print the address(es)
; ======================================================================
Procedure CmdDns()
  Define host.i
  Define ip.i
  Define i.i
  Define c.i

  If RequireCap(#CAP_NET, "dns", "this board has no network interface Anvil can use") = 0
    ProcedureReturn
  EndIf

  host = ArgWord()
  If host = 0
    PrintN("dns <hostname>")
    PrintN("  look a name up in the DNS and print the address or addresses it")
    PrintN("  resolves to. A DNS server must be set - net dns <a.b.c.d>, or run dhcp")
    PrintN("  to be given one.")
    PrintN("  Nothing was looked up, because no name was given.")
    ProcedureReturn
  EndIf

  ip = ParseDotted(host)
  If ip >= 0
    Print("  ")
    UartWriteStr(host)
    PrintN(" is already a dotted-quad address, so there is nothing to")
    PrintN("  look up. dns turns a NAME into an address; this is one already.")
    ProcedureReturn
  EndIf

  If NetLinkUpSay(1) = 0
    ProcedureReturn
  EndIf

  ip = ResolveName(host)
  If ip < 0
    ProcedureReturn
  EndIf

  Print("  ")
  UartWriteStr(host)
  Print(" resolves to ")
  PutIp(ip)
  PrintNl()
  c = DnsResultCount()
  If c > 1
    Print("  and ")
    PrintDec(c - 1)
    PrintN(" more:")
    i = 1
    While i < c
      Print("    ")
      PutIp(DnsResultIp(i))
      PrintNl()
      i = i + 1
    Wend
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  dhcp_Await - pump until the interface client produces `wantAction`,
;  rejects the lease, or the window ends. The client owns XID, hardware
;  identity, selected server and state; this loop owns only waiting.
; ----------------------------------------------------------------------
Procedure dhcp_Abort(kind.i)
  NetDhcpMode(kind, 0)
  NetUdpListen(kind, #DHCP_PORT_CLIENT, 0)
  DhcpClientReset(kind)
EndProcedure

Procedure.i dhcp_Await(wantAction.i)
  Define deadline.i
  Define n.i
  Define r.i
  Define action.i
  deadline = millis() + #DHCP_REPLY_MS
  While (millis() - deadline) < 0
    If OutBreak() <> 0
      ProcedureReturn -2
    EndIf
    ; NetServiceInput owns port 68 and records the resulting transition in
    ; the interface row. Take that event before and after pumping so an ACK
    ; is acted on once regardless of which receive loop consumed it.
    action = DhcpClientTakeEvent(LinkKind())
    If action = wantAction Or action = #DHCPC_ACT_DROP
      ProcedureReturn action
    EndIf
    r = LinkPumpNet(#NET_SLICE_MS)
    If r <> #LINK_RX_NONE
      gEthFrames = gEthFrames + 1
    EndIf
    action = DhcpClientTakeEvent(LinkKind())
    If action = wantAction Or action = #DHCPC_ACT_DROP
      ProcedureReturn action
    EndIf
  Wend
  ProcedureReturn -1
EndProcedure

; ======================================================================
;  dhcp - acquire an address by DHCP and report the lease
; ======================================================================
Procedure.i CmdDhcp()
  Define kind.i
  Define ip.i
  Define mask.i
  Define gw.i
  Define dns.i
  Define ntp.i
  Define serverId.i
  Define lease.i

  If RequireCap(#CAP_NET, "dhcp", "this board has no network interface Anvil can use") = 0
    ProcedureReturn 0
  EndIf
  If HwLinkOpen(0) = 0
    ProcedureReturn 0
  EndIf
  kind = LinkKind()

  If DhcpClientState(kind) >= #DHCPC_BOUND
    PrintN("This interface already has a tracked DHCP lease. Its renewal and")
    PrintN("rebind are automatic; the live lease was left unchanged.")
    NetDhcpSay(kind)
    ProcedureReturn 1
  EndIf

  ; A direct-cable server is an explicit interface role. Silently stopping
  ; it before an unanswered DISCOVER removes the address and server the
  ; operator is using to reach this command. Refuse the incompatible role
  ; change and leave the reachable configuration intact.
  If DhcpdOn() <> 0 And DhcpdKind() = kind
    PrintN("!! this interface is serving direct-cable DHCP, so it cannot also be a")
    PrintN("   DHCP client. The server and its reachable address were left unchanged.")
    PrintN("   Connect another interface to the upstream network, or explicitly stop")
    PrintN("   direct-cable service before selecting client mode.")
    ProcedureReturn 0
  EndIf

  Print("Asking for an address by DHCP as ")
  PutLinkMac()
  Print(" over ")
  UartWriteStr(LinkName())
  PrintN(". The same per-interface client used at boot will keep the lease renewed.")
  UartDrain()

  If NetDhcpAcquire(kind, #DHCP_TRIES * #DHCP_REPLY_MS, 0) = 0
    PrintN("!! no DHCP server completed a lease exchange. The interface's previous")
    PrintN("   saved or link-local address, if any, was left unchanged.")
    NetDhcpSay(kind)
    ProcedureReturn 0
  EndIf

  ip = DhcpClientIp(kind)
  mask = DhcpClientMask(kind)
  gw = DhcpClientGateway(kind)
  dns = DhcpClientDns(kind)
  ntp = DhcpClientNtp(kind)
  serverId = DhcpClientServer(kind)
  lease = DhcpClientLeaseLeft(kind)

  Print("Lease accepted on ")
  UartWriteStr(LinkName())
  PrintN(":")
  Print("  address   ") : PutIp(ip) : PrintNl()
  Print("  netmask   ") : PutIp(mask) : PrintNl()
  Print("  gateway   ")
  If gw = 0 : PrintN("none given") : Else : PutIp(gw) : PrintNl() : EndIf
  Print("  DNS       ")
  If dns = 0 : PrintN("none given") : Else : PutIp(dns) : PrintNl() : EndIf
  Print("  NTP       ")
  If ntp = 0 : PrintN("none given") : Else : PutIp(ntp) : PrintN(" (DHCP option 42)") : EndIf
  Print("  server    ") : PutIp(serverId) : PrintNl()
  Print("  lease     ") : PrintDec(lease) : PrintN(" seconds remaining")
  PrintN("The lease is runtime protocol state and is not written over saved static")
  PrintN("settings. Renewal, rebinding and expiry continue automatically.")
  ProcedureReturn 1
EndProcedure
