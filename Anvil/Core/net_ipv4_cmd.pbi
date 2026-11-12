; Shared IPv4 console commands and next-hop resolution.
XIncludeFile "Anvil/Core/dns_policy.pbi"

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
Procedure.i NetResolveHop(k.i, ip.i)
  Define hop.i
  Define tries.i
  Define deadline.i
  Define r.i

  ; THE INTERFACE IS THE ONE THE REQUEST WILL PHYSICALLY LEAVE BY, and
  ; since 2026-09-10 IT IS A PARAMETER rather than a read of LinkKind().
  ; It has to be: resolving an address against one interface's subnet and
  ; gateway and then putting the frame out of another is the whole class
  ; of fault the per-interface rows exist to make unsayable, and
  ; LinkKind() is the board's DEFAULT outbound door, not an answer about
  ; a particular destination. The caller has the destination in its hand,
  ; so the caller asks NetIfForDest() and passes what it was told - the
  ; same shape `tcp connect` has used since 2026-09-08. A procedure that
  ; read the selection would silently disagree with a caller that had
  ; routed, and the disagreement would present as ARP that never answers.
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
    ; OVER THE INTERFACE THIS RESOLVE IS ABOUT, not over the selected
    ; one. LinkTxStagedOn(k) is the same transmit with the kind named.
    If LinkTxStagedOn(k) <> 1
      Print("!! the address request would not go out over ")
      UartWriteStr(HwLinkName(k))
      PrintN(", so nothing")
      PrintN("   was sent. The link is up, so this is the interface itself and not")
      PrintN("   the cable or the access point.")
      LinkWhySay()
      ProcedureReturn 0
    EndIf

    ; SUBTRACT AND COMPARE AGAINST ZERO rather than comparing the two
    ; numbers, so the wait is correct across a wrap of the millisecond
    ; counter. Same reasoning, same shape, as tftp.pi4:1946-1951.
    ; EVERY ADDRESSED INTERFACE IS PUMPED while we wait, because a frame
    ; arrives on whichever interface it arrives on and a wait that
    ; listened only to one would leave the others unanswered - but the
    ; SLICE is spent on k, because the request went out over k and the
    ; answer to it can arrive nowhere else. This is the same rule as
    ; NetXferPump's, applied to the other thing in this file that sends
    ; and then waits; see LinkPumpAllNetPrefer in RaspberryPi4/Lib/link.pi4.
    ; It was LinkPumpAllNet(50) until 2026-09-16, so on a two-interface
    ; board half of every resolve's budget was spent listening to the
    ; wire the request had not gone out of.
    deadline = millis() + #ETH_ARP_MS
    While (millis() - deadline) < 0
      r = LinkPumpAllNetPrefer(k, 50)
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
  Define dnsIp.i
  Define qid.i
  Define srcPort.i
  Define tries.i
  Define deadline.i
  Define n.i
  Define r.i
  Define c.i

  dnsIp=NetDnsResolverFor(LinkKind())
  If dnsIp=0
    PrintN("!! no usable DNS resolver is selected on this interface.")
    PrintN("   Set net dns to a reachable address, or remove net.dns from")
    PrintN("   settings to use the resolver supplied by DHCP.")
    ProcedureReturn -1
  EndIf

  ; This lookup pumps its own interface from here on, so it owns that
  ; queue until the command ends - the same rule a transfer takes, and
  ; for the same reason: a DNS reply is a datagram no automatic service
  ; claims, so a second reader of the queue would drop it. See ONE
  ; CONSUMER OF AN INTERFACE'S RECEIVE QUEUE in Anvil/Core/netif.pbi.
  NetIfClaimRx(LinkKind())
  If NetResolveHop(LinkKind(), dnsIp) = 0
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
            c = DnsParseReplyFor(NetUdpRxData(), NetUdpRxLen(), qid, name)
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
  ; An echo reply is not a datagram any automatic service owns either, so
  ; this command takes its interface's queue for as long as it pumps it.
  ; See ONE CONSUMER OF AN INTERFACE'S RECEIVE QUEUE in netif.pbi.
  NetIfClaimRx(LinkKind())
  If NetResolveHop(LinkKind(), ip) = 0
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

  If DhcpClientState(kind) >= #DHCPC_BOUND And DhcpClientState(kind) <= #DHCPC_REBINDING
    PrintN("This interface already has a tracked DHCP lease. Its renewal and")
    PrintN("rebind are automatic; the live lease was left unchanged.")
    NetDhcpSay(kind)
    ProcedureReturn 1
  EndIf
  ; OFFLINE and REBOOTING are numbered above BOUND but are NOT a live lease:
  ; the link was lost and only a remembered address is kept for INIT-REBOOT.
  ; Until 2026-10-15 the test above was ">= BOUND", so `dhcp` typed in exactly
  ; that state said "already has a lease" and did nothing. Typing it is an
  ; explicit request for a fresh exchange: forget the remembered lease and
  ; start a new DISCOVER below.
  If DhcpClientState(kind) = #DHCPC_OFFLINE Or DhcpClientState(kind) = #DHCPC_REBOOTING
    PrintN("The remembered lease is not in use (the link was lost); starting a fresh DISCOVER.")
    NetDhcpCancel(kind)
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
