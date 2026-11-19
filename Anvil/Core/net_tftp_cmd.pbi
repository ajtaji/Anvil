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
  CompilerIf Defined(ANVIL_ZENTAJI_NET, #PB_Constant)
  PrintN("  Use save to keep the file, or boot mem with its address for a PMF payload.")
  CompilerElse
  gEntry = a
  gHaveEntry = 1
  Print("  Its entry point is ")
  PutAddr(a)
  PrintN(", which is where run will jump if you")
  PrintN("  type run with no address of your own.")
  CompilerEndIf
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
