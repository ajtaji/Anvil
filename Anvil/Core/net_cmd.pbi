XIncludeFile "Anvil/Core/net_ipv4_cmd.pbi"
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
Global *gNetIPv6StatusHook=0,*gNetIPv6CommandHook=0
Procedure NetSetIPv6CommandHook(*fn)
 *gNetIPv6CommandHook=*fn
EndProcedure
Procedure NetSetIPv6StatusHook(*fn)
 *gNetIPv6StatusHook=*fn
EndProcedure

Procedure NetSayInterfaces()
  Define k.i
  Define n.i
  Define src.i
  If *gNetIPv6StatusHook<>0 : gNetIPv6StatusHook() : EndIf
  n = NetIfCount()
  If n = 0
    PrintN("No interface on this board holds an IPv4 address, so IPv4 is unavailable")
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
  Print("Queued TX: pending=") : PrintDec(gLinkTxPending)
  Print(" completed=") : PrintDec(gLinkTxCompleted)
  Print(" dropped=") : PrintDec(gLinkTxDropped)
  Print(" credit-busy=") : PrintDec(gLinkTxBusy) : PrintN("")
  Print("The console pump has taken ")
  PrintDec(NetConsoleRxFrames())
  PrintN(" frames off its interfaces.")
  Print("  Console output failures: ")
  PrintDec(NetConsoleOutputFailures())
  Print("; bytes discarded at command end: ")
  PrintDec(NetConsoleOutputDiscarded())
  PrintN(".")
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
  Define k.i
  If HwLinkOpen(1) = 0
    ProcedureReturn 0
  EndIf
  LinkSay()
  LinkSayRate()
  Print("  Frames leave with the hardware address ")
  PutLinkMac()
  PrintN(".")
  ; THE ADDRESSES COME OFF THE INTERFACE THAT WON, NOT OUT OF THE WIRED
  ; SETTINGS GLOBALS. gEthIp/gEthMask/gEthGw describe the wired settings
  ; page and were printed here under whichever link had been selected,
  ; so a board carrying traffic over the radio reported the cable's
  ; numbers as "its address". net.pi4's row for `k` is the address this
  ; interface will actually source from.
  k = LinkKind()
  If k <> #HW_LINK_NONE
    Print("  Its address is ")
    PutIp(NetIPv4(k))
    Print(", netmask ")
    PutIp(NetMask(k))
    Print(", gateway ")
    PutIp(NetGateway(k))
    PrintN(".")
  EndIf
  HwLinkSayDetail()
  ProcedureReturn 1
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
;  THE INTERFACE IS A PARAMETER, and it is the one EthStart routed this
;  transfer onto. It was LinkKind() until 2026-09-10 - the board's
;  default outbound door - which is a different question from "which
;  interface can reach this server" the moment a board holds an address
;  on more than one.
Procedure.i NetXferSend(kind.i)
  If TftpOutLen() = 0
    ProcedureReturn 0
  EndIf
  If NetUdpBuild(kind, TftpOutIp(), TftpOutPort(), TftpLocalPort(), TftpOutBuf(), TftpOutLen()) = 0
    gEthSendFail = gEthSendFail + 1
    ProcedureReturn 0
  EndIf
  If LinkTxStagedOn(kind) <> 1
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
;  IT PUMPS EVERY ADDRESSED INTERFACE, NOT THE SELECTED ONE. It called
;  LinkPumpNet until 2026-09-10, which reads gLinkKind, so a transfer
;  routed onto the radio while the cable was preferred would have sat
;  through its whole retransmit budget without ever looking at the wire
;  the answers were on. The pump hands NetInput the interface each
;  frame actually arrived on and leaves the operator's outbound
;  preference alone, which is the same rule the console's pump follows.
; ----------------------------------------------------------------------
;  AND IT NOW WAITS ON THE INTERFACE THE ANSWERS ARE ON - 2026-09-16. It
;  called LinkPumpAllNet(ms) until then, which is the FAIR pump: poll
;  every interface at zero wait, then block the whole slice on a rotating
;  cursor. On a board holding the cable AND a lease on the radio, that
;  cursor put the 200 ms wait on the RADIO on the turn after every block,
;  while the acknowledgement lay unread in the wired ring - so every
;  512-byte block cost a whole slice, about 2.5 KB/s, and a 1,812,000-
;  byte put ran past the ten-minute ceiling instead of finishing.
;
;  A STOP-AND-WAIT TRANSFER'S BLOCKING WAIT BELONGS ON THE WIRE ITS
;  ANSWERS ARRIVE ON, and `kind` is that wire: it is XferKind(), the
;  interface EthStart routed this transfer onto and claimed the receive
;  queue of. The cursor walk, the measurement and the reason the slice
;  stays at 200 ms are in LinkPumpAllNetPrefer's header in
;  RaspberryPi4/Lib/link.pi4.
;
;  EVERY INTERFACE IS STILL LISTENED TO. The zero-wait sweep inside
;  LinkPumpAllNetPrefer covers all of them before anything blocks, so
;  ARP, ICMP, the DHCP service this board runs on the cable and console
;  keystrokes on the radio are answered during a transfer exactly as
;  before. Only the WAITING moved.
Procedure.i NetXferPump(kind.i, ms.i)
  Define r.i
  Define t.i

  r = LinkPumpAllNetPrefer(kind, ms)
  If r <> #LINK_RX_NONE
    gEthFrames = gEthFrames + 1
    If r = #NET_IN_UDP
      gEthUdp = gEthUdp + 1
      TftpInput(NetUdpRxFrom(), NetUdpRxPort(), NetUdpRxDstPort(), NetUdpRxData(), NetUdpRxLen())
      NetXferSend(kind)
    EndIf
  EndIf

  t = TftpTick(millis())
  If t = 1
    NetXferSend(kind)
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
Procedure.i NetXferRun(kind.i)
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
        NetXferSend(kind)
      EndIf
      PrintN("The transfer was stopped part way and NOTHING IS COMPLETE. For a get,")
      PrintN("what is at the destination is the beginning of a file with whatever")
      PrintN("was there before underneath it - do not run it. The server has been")
      PrintN("told the transfer is over, as a courtesy it may or may not receive.")
      ProcedureReturn 0
    EndIf

    If NetXferPump(kind, #ETH_SLICE_MS) = 1
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
        NetXferSend(kind)
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
; ----------------------------------------------------------------------
;  THE TRANSFER SESSION'S INTERFACE. One transfer runs at a time -
;  tftp.pi4 keeps one transfer's state - so this is a field of that
;  session, written by EthStart and by nothing else, and read once by
;  each command before being passed down as a parameter. It is NOT a
;  second copy of the link selection: LinkKind() is still the board's
;  default outbound door and this is the answer to "which interface can
;  reach THIS server", which is a different question.
; ----------------------------------------------------------------------
Global gXferKind.i = #HW_LINK_NONE

Procedure.i XferKind()
  ProcedureReturn gXferKind
EndProcedure

Procedure.i EthStart()
  Define port.i
  Define k.i

  gEthFrames = 0
  gEthUdp = 0
  gEthArpOut = 0
  gEthSendFail = 0
  gXferKind = #HW_LINK_NONE

  ; ---- THE ONE FACT THE BOARD CANNOT DERIVE -------------------------
  ; Which machine is serving the file. Everything else a transfer needs
  ; is already per-interface state. See NetXferServer in netcfg.pbi for
  ; what this replaced and what typing four keys cost on 2026-09-10.
  gEthSrv = NetXferServer()
  If gEthSrv = 0
    ProcedureReturn 0
  EndIf

  ; ---- MAKE SURE SOMETHING IS UP ------------------------------------
  ; HwLinkOpen is the board's live re-check: one MDIO read on a link
  ; already up, the five-second bring-up only when it is worth paying.
  ; It selects the DEFAULT door and prints its own refusal; the route
  ; below is what decides where this transfer goes.
  If HwLinkOpen(1) = 0
    ProcedureReturn 0
  EndIf

  ; ---- AND WHICH INTERFACE CAN REACH THAT SERVER --------------------
  ; The destination's subnet decides, exactly as it does for `tcp
  ; connect`. A board holding a probed link-local address on the cable,
  ; a served alias beside it and a lease on the radio has three usable
  ; source addresses and only one of them can reach a given server.
  k = NetIfForDest(gEthSrv)
  If k = #HW_LINK_NONE
    Print("!! no interface on this board can reach ")
    PutIp(gEthSrv)
    PrintN(", so nothing was")
    PrintN("   transferred. That address is on none of this board's own segments")
    PrintN("   and no interface holding an address has a gateway to send it")
    PrintN("   through. These are the addresses this board holds right now:")
    NetSayInterfaces()
    PrintN("   Either give the server an address on one of those segments, or set")
    PrintN("   a gateway on the interface that should carry it.")
    ProcedureReturn 0
  EndIf
  gXferKind = k
  Print("The transfer goes out over ")
  UartWriteStr(HwLinkName(k))
  Print(" from ")
  PutIp(NetSrcFor(k, gEthSrv))
  PrintN(",")
  PrintN("  which is the interface that can reach that server.")

  ; ---- AND FROM HERE THIS COMMAND OWNS THAT INTERFACE'S QUEUE -------
  ; Everything below pumps: the resolve waits for an ARP reply, and the
  ; transfer waits for every acknowledgement. A second reader of the same
  ; queue takes frames this command is waiting for and drops the ones no
  ; automatic service claims - which is precisely a transfer's own
  ; acknowledgement. See ONE CONSUMER OF AN INTERFACE'S RECEIVE QUEUE in
  ; Anvil/Core/netif.pbi for the board run that measured it. The claim is
  ; released at NetConsoleCommandDone, the point every arm of every
  ; command converges on.
  NetIfClaimRx(k)

  If NetResolveHop(k, gEthSrv) = 0
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
  If NetUdpBind(k, port) = 0
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
  If NetXferSend(XferKind()) = 0
    PrintN("!! the read request would not go out on the wire, so nothing was")
    PrintN("   transferred.")
    EthWhyNet()
    LinkWhySay()
    ProcedureReturn
  EndIf

  If NetXferRun(XferKind()) = 0
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
  If NetXferSend(XferKind()) = 0
    PrintN("!! the write request would not go out on the wire, so nothing was")
    PrintN("   transferred.")
    EthWhyNet()
    LinkWhySay()
    ProcedureReturn
  EndIf

  If NetXferRun(XferKind()) = 0
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
  ; Selection is not address acquisition. HwLinkOpen has installed the
  ; selected interface's existing address row. Do not bind it again from
  ; gEthIp: that tuple belongs to wired, even when Wi-Fi was selected, and
  ; rebinding would overwrite the radio's lease and its address provenance.
  ; Static changes and DHCP acquisition keep their own NetAddressBound tail.
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
  ; THE ROW IS THE WIRED ONE, WHATEVER WON. gEthIp, gEthMask and gEthGw
  ; are the wired settings store's numbers (EthHasIpConfig), while k is
  ; the kind HwLinkOpen selected - which is the radio under `net link
  ; wifi`. Binding them to k would write the cable's address over the
  ; radio's lease row and leave the wired row empty, because HwLinkOpen
  ; fills only the row of the kind it selected. k is still what this
  ; answers: callers say which interface carries the traffic.
  NetAddressBound(#HW_LINK_WIRED, gEthIp, gEthMask, gEthGw, #NET_ADDR_SAVED)
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

  If WordIs("ipv6")<>0
    If *gNetIPv6CommandHook<>0
      gNetIPv6CommandHook()
    Else
      PrintN("IPv6 service is not active on this target.")
    EndIf
    ProcedureReturn
  EndIf

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

    ; ------------------------------------------------------------------
    ; WHAT A TRANSFER ACTUALLY NEEDS, AND IT IS ONE LINE OF THE FOUR.
    ; 2026-09-11.
    ;
    ; This paragraph said "not all four addresses are in the settings
    ; store, so get and put would refuse" and it was TRUE until
    ; 2026-09-10, when the transfer path stopped validating its
    ; configuration by applying it and started routing by the server.
    ; It went on being printed for a day after it stopped being true,
    ; under a board that was holding three usable addresses and had just
    ; completed the route it said would refuse - which is the monitor
    ; telling somebody to type three things they do not need.
    ;
    ; THE THREE ARE STILL WORTH SETTING and this says what for: they are
    ; the address this board answers to when no DHCP server does, saved
    ; so a reset brings it back. They are simply not a precondition of
    ; anything any more.
    ; ------------------------------------------------------------------
    If SettingsGet(EthKeyServer()) = 0
      PrintN("No TFTP server is set, so get and put have nowhere to go. Set one with")
      PrintN("net server <a.b.c.d> and they will work: a transfer needs THAT and")
      PrintN("nothing else, because the board already knows which of its own")
      PrintN("addresses can reach it and which interface carries them.")
    ElseIf set < 4
      PrintN("The server is set, so get and put will work. The other three are this")
      PrintN("board's OWN address, saved for a link where nothing hands one out -")
      PrintN("set them with net address, net netmask and net gateway, and use")
      PrintN("0.0.0.0 for the gateway when there is no router, which is the truth on")
      PrintN("a cable straight between this board and one other machine. They are")
      PrintN("not needed for a transfer and they are not needed by ping, the")
      PrintN("network console or net recv: those use whatever address the board is")
      PrintN("holding, however it got it.")
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
    If NetIfSrc(LinkKind()) <> #NET_ADDR_NONE
      Print("  ")
      UartWriteStr(NetAddrFromText(LinkKind()))
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
      If NetIfSrc(LinkKind()) <> #NET_ADDR_NONE
        Print("  ")
        UartWriteStr(NetAddrFromText(LinkKind()))
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

  ; ---- net stats ------------------------------------------------------
  ; WHAT THE CONTROLLERS COUNTED, which is a different question from what
  ; the IP layer counted, and the board answers it for every interface it
  ; has (HwLinkSayCounters).
  ;
  ; `net` already prints frames in, frames out, refusals and link changes:
  ; those are this monitor's own tallies, the same on every board, and
  ; about the software. This prints the HARDWARE's - pause frames, framing
  ; errors, overruns - and only the board knows whether it has any.
  ;
  ; A COMMAND OF ITS OWN, NOT MORE LINES UNDER `net`. `net` is what gets
  ; typed when a transfer failed, and it has to stay short enough to read.
  ; These counters are what gets typed when a LINK behaves strangely - or
  ; when the machine at the other end of a cable does - and on a healthy
  ; board almost every one of them is zero. Two questions, two commands.
  ;
  ; WHY IT EXISTS. 2026-09-08: this board on a cable straight into a
  ; laptop, whose Ethernet card reset twelve times in two and a half
  ; minutes and was then stopped by its operating system. Whether this
  ; board had sent it a single 802.3x PAUSE frame was the whole question,
  ; the number was sitting in a UniMAC counter, and nothing printed it.
  If WordIs("stats") <> 0 Or WordIs("counters") <> 0
    HwLinkSayCounters()
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
    ; ------------------------------------------------------------------
    ; THIS SAID "N OF THE FOUR ADDRESSES ARE STILL NOT SET, SO GET AND
    ; PUT WOULD REFUSE" AND IT WAS NOT TRUE ANY MORE. 2026-09-11.
    ;
    ; It was true until 2026-09-10, when the transfer path stopped
    ; validating its configuration by applying it. A transfer now asks
    ; which interface can reach the server and sources from the address
    ; that interface already holds, so the server is the only address it
    ; waits on. The sentence stayed for a day, and the board printed it
    ; on the bench the moment `net server` was typed - directly above a
    ; `put` that then went out over the cable exactly as the fix says.
    ; A monitor that tells somebody to type three keys they do not need,
    ; in the same breath as doing the thing it says is impossible, is
    ; the silent-wrong-answer failure wearing an instruction's clothes.
    ; ------------------------------------------------------------------
    If SettingsHas(EthKeyServer()) = 0
      PrintN("  There is no TFTP server set, and that is the one address get and")
      PrintN("  put cannot do without. Set it with net server <a.b.c.d>. The other")
      PrintN("  three are this board's own address and no transfer waits on them.")
      ProcedureReturn
    EndIf
    If n < 4
      PrintN("  get and put have what they need. A transfer asks which interface")
      PrintN("  can reach that server, leaves by it, and sources from the address")
      PrintN("  that interface is already holding, so the server is the only")
      PrintN("  address it waits on. Type net to see what this board holds.")
      Print("  ")
      PrintDec(4 - n)
      PrintN(" of the four are still not in the store, and the missing ones")
      PrintN("  are this board's OWN address - which a link with no DHCP server on")
      PrintN("  it needs in order to come back with one after a reset.")
      ProcedureReturn
    EndIf
    If EthConfig() = 1
      PrintN("  All four are set and this board's own three agree with each other.")
      PrintN("  get and put need the server alone, and it is there.")
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
    PrintN("untouched and stays up if it was up, and the addresses the board is")
    PrintN("HOLDING are untouched too - a lease and a link-local address are not")
    PrintN("in the store and were not forgotten. What has gone is the saved copy,")
    PrintN("so get and put refuse only if the TFTP server was one of them.")
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
  PrintN("  net stats                  what each network controller counted")
EndProcedure
