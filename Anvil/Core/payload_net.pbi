XIncludeFile "Anvil/Core/network_service_profile.pbi"
XIncludeFile "Anvil/Core/dns_policy.pbi"
XIncludeFile "Anvil/Services/wifi_maintenance.pbi"
XIncludeFile "Anvil/Network/ipv6_address.pbi"
; ======================================================================
;  payload_net.pbi - THE NETWORK A PAYLOAD REACHES. The engine behind the
;  service table's net group (base 72, Anvil/Hal/abi.pbi).
;
;  The slots in abi.pbi ask the capability question and call in here, and
;  nothing else; every rule a payload can observe is in this file, which is
;  why the desk gate (tools/payload_net_emitted_check.py) compiles THIS FILE
;  against stubs and drives it, rather than a copy of its logic.
;
; ----------------------------------------------------------------------
;  THE ONE RULE EVERY PROCEDURE HERE KEEPS: NOTHING WAITS.
; ----------------------------------------------------------------------
;  A payload calls these from its draw loop, sixty times a second. A slot
;  that waited for a reply would freeze the screen for as long as the far
;  end took to answer, which on a dead route is the whole retransmission
;  schedule. So every operation is STARTED by one call and FINISHED by
;  later ones:
;
;    * a name is resolved by asking for it again until it answers - the
;      first call sends the query and returns #SVC_EAGAIN, a later call
;      with the same name returns the address (see DNS below);
;    * a connection is opened by a call that returns a handle at once; the
;      handshake runs in the background and SvcTcpState says how far it
;      has got;
;    * a send copies into the connection's ring and returns how much it
;      took; a receive returns what has already arrived, 0 meaning nothing
;      yet;
;    * and the network itself only moves when SvcNetService runs, which
;      the payload calls once a frame - see THE SERVICE SLOT.
;
;  The monitor's own sends are already non-blocking (TcpConnect stages a
;  SYN and returns; the DNS query is one datagram), so "nothing waits" is
;  true of the work done in here. What it CANNOT promise is the cost of the
;  monitor's own services that SvcNetService runs, and that is stated
;  there, with the number.
;
; ----------------------------------------------------------------------
;  THE TWO IP LAYERS HAVE MERGED, AND THIS FILE IS WRITTEN AGAINST THE ONE
; ----------------------------------------------------------------------
;  abi.pbi kept these slots empty "until the two IP layers merge" (ruling
;  2026-09-02, Anvil todo 119). That merge is in: net.pbi holds an address
;  row per interface, netif.pbi answers which interface reaches a
;  destination (NetIfForDest) and which is preferred (wired first), tcp.pi4
;  latches the interface with the peer (TcpConnect(kind, ip, port)), the
;  link pump reads every addressed interface and hands every frame to the
;  one dispatcher (NetServiceInput), and the DHCP lease on the radio sets
;  that row's resolver (netcfg.pbi -> NetIfSetDns). The NTP service already
;  resolves its server over the radio that way. So a board whose only link
;  is Wi-Fi resolves and connects through exactly the code below; nothing
;  here names an interface.
;
;  WHAT A PAYLOAD CANNOT HAVE IN THIS BUILD: THE CABLE. RunAt
;  (RaspberryPi4/Board/cache.pi4) stops the wired controller before the
;  jump - its receive DMA is a bus master writing into monitor memory on
;  its own schedule, and the restart is a bounded but multi-second link
;  wait that prints. So while a payload runs the wired row is not usable
;  and "Ethernet preferred when both" can only ever pick the radio.
;  SvcNetUp says so in its refusal rather than pretending.
;
; ----------------------------------------------------------------------
;  DNS - ONE QUESTION IN FLIGHT, FOUR ANSWERS REMEMBERED
; ----------------------------------------------------------------------
;  Modelled on Anvil/Core/ntp_service.pbi, deliberately and closely: the
;  query is built and sent by a STEP that runs outside the receive path,
;  the reply enters through the shared UDP dispatcher (NetServiceInput,
;  through the hook netconsole.pbi offers) and that callback only
;  validates and copies - it never builds, sends, or changes a listener,
;  because the frame it is reading is the receive scratch and a send would
;  overwrite it.
;
;  WHY THE POLL IS THE SAME SLOT AND NOT ONE OF THE RESERVED THREE. The
;  brief gives slot 75 as "SvcDnsResolve(*name) -> IPv4, or negative", and
;  "not yet" is a negative answer like any other: #SVC_EAGAIN (-110), new at
;  1.5. A separate poll slot would mean a second procedure whose argument
;  is a ticket the payload has to keep, for no gain - the name IS the
;  ticket. And it leaves 87 of the merge's three reserved slots spare.
;
;  So for one name, call after call:
;    dotted quad          answered at once, never sent anywhere
;    in the cache         answered at once (five minutes, four names)
;    not yet asked        query sent, #SVC_EAGAIN
;    asked, not answered  #SVC_EAGAIN
;    answered             the address, and it goes in the cache
;    failed               the code ONCE (#SVC_ETIMEOUT, #SVC_EIO ...), and
;                         the next call asks again from the start
;  A DIFFERENT name while one is in flight is #SVC_EBUSY: one question at a
;  time, and the payload asks the next when the first has answered.
;  Three tries of 1.5 s each, then #SVC_ETIMEOUT.
;
; ----------------------------------------------------------------------
;  TCP - FOUR HANDLES OVER THE MONITOR'S SIXTEEN SOCKETS
; ----------------------------------------------------------------------
;  The handle is 1..4 and is the payload's; the socket under it is
;  tcp.pi4's, chosen the way Anvil/Core/tcp_cmd.pbi chooses one (TcpAlloc,
;  then TcpUse around every touch, the caller's current socket put back).
;  Four, not sixteen: the monitor's own HTTP server and console run while
;  a payload does, and a payload that could take every socket would be a
;  payload that could make the monitor unreachable.
;
;  THE HANDSHAKE DOES NOT START UNTIL THE NEXT HOP ANSWERS ARP, and that
;  is tcp.pi4's rule, not this file's: TcpConnect sends the ARP request and
;  answers #NET_TCP_E_ARP without taking the socket. The handle holds the
;  destination meanwhile and asks again every 250 ms, for five seconds.
;
;  A CONNECTION THAT ENDS IS SEEN BY ITS SOCKET'S GENERATION, which tcp.pi4
;  bumps on every wipe (a reset, a timeout, a lost address). One bump past
;  the generation latched at connect means our connection ended and its
;  reason (TcpWasReset, TcpError) is still in the socket and is read at
;  once and kept with the handle. More than one bump means somebody else
;  has the socket now, and the reason is gone - which is said, not
;  guessed.
;
;  States, SvcTcpState's answer:
;    #SVC_TCP_CONNECTING  ARP or the handshake still in progress
;    #SVC_TCP_OPEN        established; sends are taken
;    #SVC_TCP_PEER_CLOSED the peer has finished sending. Whatever it sent
;                         is still readable, and this end may still send;
;                         close the handle when done
;    negative             the connection failed or ended badly; the code
;                         and SvcErrDetail's fragment say how, and every
;                         later send and receive answers the same code
;
;  CLOSE RELEASES THE HANDLE AT ONCE and the orderly close carries on in
;  the background - the FIN goes out behind whatever was still queued, as
;  RFC 9293 3.10.4 requires. A connection this end closed first then holds
;  its socket for TIME-WAIT, four minutes; that is TCP and not a leak, and
;  it is why the open refusal for "no socket free" says so.
;
;  WHEN THE PAYLOAD RETURNS its connections die with it: PayNetPayloadReturned
;  resets every one still open and forgets the handles, so the next payload
;  starts with four free ones and nobody's half-open connection.
;
; ----------------------------------------------------------------------
;  THE SERVICE SLOT - WHY IT EXISTS
; ----------------------------------------------------------------------
;  While a payload runs, the monitor's prompt is not spinning, so nothing
;  services the network: no Wi-Fi keepalive, no answer to the access
;  point's group rekey, no DHCP renewal, no TCP retransmission. A
;  ninety-second payload lost the board's association that way: the
;  firmware still said "associated", the link carried nothing, and the
;  auto-reconnect never asked because it only asks from the prompt.
;
;  PayNetService runs, once, THE SAME PROCEDURES the prompt's scheduler
;  runs for the network (AnvilPromptServiceOne in Anvil/Core/parse.pbi,
;  its slots 2 and 4), in the same order, inside the same message bracket
;  - so a lease renewing or the radio re-associating goes to the message
;  log and never onto the payload's screen. It runs NOTHING the payload
;  owns: not the screen service, not touch, not the mouse, not the fan. The
;  desk gate compares the two lists so they cannot drift apart.
;
;  Then, for whatever is left of sliceMs (at most #PAYNET_SLICE_MAX), it
;  drains the receive path while frames keep arriving and stops the moment
;  one pass finds none.
;
;  ITS COST, honestly. In steady state every one of those services is
;  self-rate-limited and costs microseconds. Two can cost more and neither
;  is this file's to shorten: every twenty seconds WifiLinkTick asks the
;  radio firmware whether it is still associated, one SDIO control call
;  bounded at 400 ms that normally answers in about a millisecond; and
;  while the radio is RE-ASSOCIATING, WifiLinkTick advances one phase of
;  that recovery per call, and a phase (a scan, a key install) is bounded
;  by the firmware's own timeout. Those are the frames that will stutter,
;  and they are the frames in which the link is being saved.
; ======================================================================

EnableExplicit

#PAYNET_TCP_HANDLES   = 4
#PAYNET_TCP_RETRY_MS  = 250      ; spacing of ARP-pending connect attempts
#PAYNET_TCP_OPEN_MS   = 5000     ; a next hop that never answers ARP
#PAYNET_DNS_PORT_BASE = 49240    ; + interface kind. NTP owns 49200.. and 49216..
#PAYNET_DNS_TRY_MS    = 1500
#PAYNET_DNS_TRIES     = 3
#PAYNET_DNS_ARP_MS    = 250
#PAYNET_DNS_NAME      = 256      ; 253 characters, the terminator, and slack
#PAYNET_DNS_CACHE     = 4
#PAYNET_DNS_CACHE_MS  = 300000   ; local upper bound; shorter DNS TTLs win
#PAYNET_SLICE_MAX     = 50       ; the most SvcNetService may spend draining
#PAYNET_DRAIN_PASSES  = 64       ; and the most receive passes it will make

#PAYNET_DNS_IDLE = 0
#PAYNET_DNS_SEND = 1             ; due to send (first try, retry, or ARP wait)
#PAYNET_DNS_WAIT = 2             ; sent; waiting for the reply
#PAYNET_DNS_DONE = 3             ; answered; the next step caches it
#PAYNET_DNS_TCP = 5             ; truncated UDP answer, retrying over TCP
#PAYNET_DNS_FAIL = 4             ; failed; the next ask for that name hears why

; ---- DNS -------------------------------------------------------------
Global paynet_dnsTcp.i
Global paynet_dnsTcpTxLen.i
Global paynet_dnsTcpTxOff.i
Global paynet_dnsTcpRxLen.i
Global paynet_dnsTcpRxWant.i
Global Dim paynet_dnsTcpTx.a[#DNS_OUT_MAX+2]
Global Dim paynet_dnsTcpRx.a[65537]
Global paynet_dnsState.i
Global paynet_dnsKind.i
Global paynet_dnsFamily.i = 4
Global paynet_dnsLearned.i
Global paynet_dnsLease.NetDns6Lease
Global Dim paynet_dnsServer6.a[16]
Global paynet_dnsServer.i
Global paynet_dnsLocalIp.i
Global paynet_dnsPort.i
Global paynet_dnsQid.i
Global paynet_dnsTries.i
Global paynet_dnsStart.i
Global paynet_dnsDue.i
Global paynet_dnsDeadline.i
Global paynet_dnsType.i = #DNS_QTYPE_A
Global Dim paynet_dnsAnswer6.a[16]
Global paynet_dnsAnswer.i
Global paynet_dnsTtl.i
Global paynet_dnsAnswerAt.i
Global paynet_dnsErr.i
Global paynet_dnsWhy.i
Global paynet_dnsQueries.i       ; queries sent, ever
Global paynet_dnsRejects.i       ; datagrams on our port that were not our answer
Global Dim paynet_dnsName.a[#PAYNET_DNS_NAME]
Global Dim paynet_cacheName.a[#PAYNET_DNS_CACHE * #PAYNET_DNS_NAME]
Global Dim paynet_cacheIp.i[#PAYNET_DNS_CACHE]
Global Dim paynet_cacheType.i[#PAYNET_DNS_CACHE]
Global Dim paynet_cacheIp6.a[#PAYNET_DNS_CACHE*16]
Global Dim paynet_cacheAt.i[#PAYNET_DNS_CACHE]
Global Dim paynet_cacheMs.i[#PAYNET_DNS_CACHE]
Global Dim paynet_cacheUsed.i[#PAYNET_DNS_CACHE]
Global paynet_cacheNext.i

; ---- TCP -------------------------------------------------------------
Global Dim paynet_tcpUsed.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpSock.i[#PAYNET_TCP_HANDLES]   ; -1 while ARP is pending
Global Dim paynet_tcpGen.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpKind.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpFamily.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpSource6.a[#PAYNET_TCP_HANDLES*16]
Global Dim paynet_tcpDest6.a[#PAYNET_TCP_HANDLES*16]
Global Dim paynet_tcpIp.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpPort.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpT0.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpNext.i[#PAYNET_TCP_HANDLES]
Global Dim paynet_tcpFail.i[#PAYNET_TCP_HANDLES]   ; 0, or the latched #SVC_* code
Global Dim paynet_tcpWhy.i[#PAYNET_TCP_HANDLES]    ; the fragment that goes with it

; ======================================================================
;  NAMES
; ======================================================================
Procedure.i paynet_Lower(c.i)
  If c >= 65 And c <= 90
    ProcedureReturn c + 32
  EndIf
  ProcedureReturn c
EndProcedure

; Length of a NUL-terminated name, or -1 past 253 characters (RFC 1035
; 2.3.4 allows 255 octets on the wire, which is 253 characters written out).
Procedure.i paynet_NameLen(*name)
  Define i.i
  i = 0
  While (PeekA(*name + i) & $FF) <> 0
    i = i + 1
    If i > 253
      ProcedureReturn -1
    EndIf
  Wend
  ProcedureReturn i
EndProcedure

; Host names are compared without regard to case (RFC 4343).
Procedure.i paynet_SameName(*a, *b)
  Define i.i
  Define ca.i
  Define cb.i
  i = 0
  Repeat
    ca = paynet_Lower(PeekA(*a + i) & $FF)
    cb = paynet_Lower(PeekA(*b + i) & $FF)
    If ca <> cb
      ProcedureReturn 0
    EndIf
    If ca = 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  Until i >= #PAYNET_DNS_NAME
  ProcedureReturn 0
EndProcedure

Procedure paynet_CopyName(*dst, *src)
  Define i.i
  Define c.i
  i = 0
  c = PeekA(*src) & $FF
  While c <> 0 And i < #PAYNET_DNS_NAME - 1
    PokeA(*dst + i, c)
    i = i + 1
    c = PeekA(*src + i) & $FF
  Wend
  PokeA(*dst + i, 0)
EndProcedure

Procedure.i paynet_CacheSlot(*name, now.i, qtype.i)
  Define i.i
  For i = 0 To #PAYNET_DNS_CACHE - 1
    If paynet_cacheUsed[i] <> 0
      If ((now - paynet_cacheAt[i]) & $FFFFFFFF) >= paynet_cacheMs[i]
        paynet_cacheUsed[i] = 0
      ElseIf paynet_cacheType[i]=qtype And paynet_SameName(@paynet_cacheName[i * #PAYNET_DNS_NAME], *name) <> 0
        ; TTL zero is a one-delivery transaction result, never reusable.
        If paynet_cacheUsed[i]=2 : paynet_cacheUsed[i]=0 : EndIf
        ProcedureReturn i+1
      EndIf
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i paynet_CacheFind(*name,now.i)
  Define slot.i
  slot=paynet_CacheSlot(*name,now,#DNS_QTYPE_A)
  If slot=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn paynet_cacheIp[slot-1]
EndProcedure

Procedure.i paynet_CacheFind6(*name,now.i,destination.i)
  Define slot.i,j.i
  If destination=0 : ProcedureReturn 0 : EndIf
  slot=paynet_CacheSlot(*name,now,#DNS_QTYPE_AAAA)
  If slot=0 : ProcedureReturn 0 : EndIf
  For j=0 To 15 : PokeA(destination+j,paynet_cacheIp6[(slot-1)*16+j]) : Next
  ProcedureReturn 16
EndProcedure

Procedure.i paynet_CacheStore(*name,now.i,ttl.i,qtype.i)
  Define i.i
  Define slot.i
  slot = -1
  For i = 0 To #PAYNET_DNS_CACHE - 1
    If paynet_cacheUsed[i] <> 0
      If paynet_cacheType[i]=qtype And paynet_SameName(@paynet_cacheName[i * #PAYNET_DNS_NAME], *name) <> 0
        slot = i
      EndIf
    EndIf
  Next
  If slot < 0
    slot = paynet_cacheNext
    paynet_cacheNext = (paynet_cacheNext + 1) % #PAYNET_DNS_CACHE
  EndIf
  paynet_CopyName(@paynet_cacheName[slot * #PAYNET_DNS_NAME], *name)
  paynet_cacheType[slot] = qtype
  paynet_cacheAt[slot] = now
  If ttl<1
    paynet_cacheUsed[slot]=2
    paynet_cacheMs[slot]=#PAYNET_DNS_TRY_MS * #PAYNET_DNS_TRIES
  Else
    If ttl>#PAYNET_DNS_CACHE_MS/1000 : ttl=#PAYNET_DNS_CACHE_MS/1000 : EndIf
    paynet_cacheMs[slot]=ttl*1000
    paynet_cacheUsed[slot]=1
  EndIf
  ProcedureReturn slot
EndProcedure

Procedure paynet_CachePut(*name,ip.i,now.i,ttl.i)
  Define slot.i
  slot=paynet_CacheStore(*name,now,ttl,#DNS_QTYPE_A)
  paynet_cacheIp[slot]=ip
EndProcedure

Procedure paynet_CachePut6(*name,source.i,now.i,ttl.i)
  Define slot.i,j.i
  slot=paynet_CacheStore(*name,now,ttl,#DNS_QTYPE_AAAA)
  For j=0 To 15 : paynet_cacheIp6[slot*16+j]=PeekA(source+j) : Next
EndProcedure

; ======================================================================
;  DNS
; ======================================================================

; Shared explicit-override/lease policy, also used by console DNS and NTP.
Procedure.i paynet_DnsFor(kind.i)
  ProcedureReturn NetDnsResolverFor(kind)
EndProcedure

Procedure paynet_DnsCloseListener()
  If paynet_dnsPort <> 0 And paynet_dnsKind <> #HW_LINK_NONE
    NetUdpListen(paynet_dnsKind, paynet_dnsPort, 0)
  EndIf
  paynet_dnsPort = 0
EndProcedure

Procedure paynet_DnsCloseTcp()
  If paynet_dnsTcp>0 : PayNetTcpClose(paynet_dnsTcp) : EndIf
  paynet_dnsTcp=0
EndProcedure

Procedure paynet_DnsFail(code.i, *why)
  NetDnsTraceFinish(code)
  paynet_DnsCloseTcp()
  paynet_DnsCloseListener()
  paynet_dnsErr = code
  paynet_dnsWhy = *why
  paynet_dnsState = #PAYNET_DNS_FAIL
EndProcedure

; ----------------------------------------------------------------------
;  PayNetDnsInput - THE RECEIVE CALLBACK. Registered with the dispatcher
;  (NetServiceSetUdpHook) when the first query starts and left there.
;  VALIDATES AND COPIES ONLY: no listener change, no build, no send - the
;  datagram it is reading is the receive scratch. The step owns the rest.
;  1 = the datagram was ours (consumed, accepted or not), 0 = not ours.
; ----------------------------------------------------------------------
; Copy the selected record before another codec user reuses its storage.
Procedure paynet_DnsCaptureAnswer(now.i)
  NetDnsTraceFinish(0)
  If paynet_dnsType=#DNS_QTYPE_AAAA
    DnsResultIp6(0,@paynet_dnsAnswer6[0])
    paynet_dnsAnswer=0
  Else
    paynet_dnsAnswer=DnsResultIp(0)
  EndIf
  paynet_dnsTtl=DnsResultTtl(0)
  paynet_dnsAnswerAt=now
EndProcedure

Procedure.i PayNetDnsInput(kind.i)
  Define c.i
  If paynet_dnsState <> #PAYNET_DNS_WAIT And paynet_dnsState <> #PAYNET_DNS_SEND
    ProcedureReturn 0
  EndIf
  If kind <> paynet_dnsKind Or paynet_dnsPort = 0
    ProcedureReturn 0
  EndIf
  If NetUdpRxDstPort() <> paynet_dnsPort Or NetRxTo() <> paynet_dnsLocalIp
    ProcedureReturn 0
  EndIf
  If NetUdpRxFrom() <> paynet_dnsServer Or NetUdpRxPort() <> #DNS_PORT
    paynet_dnsRejects = paynet_dnsRejects + 1
    ProcedureReturn 1
  EndIf
  c = DnsParseReplyTypeFor(NetUdpRxData(), NetUdpRxLen(), paynet_dnsQid, @paynet_dnsName[0],paynet_dnsType)
  If c > 0
    paynet_DnsCaptureAnswer(millis())
    paynet_dnsState = #PAYNET_DNS_DONE
    ProcedureReturn 1
  EndIf
  If c = 0
    paynet_dnsErr = #SVC_EIO
    paynet_dnsWhy = "the DNS server answered and had no address of the requested type for that name"
    paynet_dnsState = #PAYNET_DNS_FAIL
    NetDnsTraceFinish(paynet_dnsErr)
    ProcedureReturn 1
  EndIf
  If c = #DNS_E_TRUNCATED
    paynet_dnsState=#PAYNET_DNS_TCP
    ProcedureReturn 1
  EndIf
  If c = #DNS_E_RCODE
    paynet_dnsErr = #SVC_EIO
    paynet_dnsWhy = "the DNS server refused the name: it does not exist, or the server would not look it up"
    paynet_dnsState = #PAYNET_DNS_FAIL
    NetDnsTraceFinish(paynet_dnsErr)
    ProcedureReturn 1
  EndIf
  ; A reply to an older try (another ID), or one that does not parse. Not
  ; an answer and not a verdict: keep waiting for the real one, and count
  ; it so a resolver sending garbage shows up somewhere.
  paynet_dnsRejects = paynet_dnsRejects + 1
  ProcedureReturn 1
EndProcedure

Procedure paynet_DnsSend(now.i)
  Define n.i
  Define hop.i
  If NetIfUsable(paynet_dnsKind) = 0
    paynet_DnsFail(#SVC_ESTATE, "the interface the query was going out of lost its address")
    ProcedureReturn
  EndIf
  n = DnsBuildQueryType(@paynet_dnsName[0], paynet_dnsQid,paynet_dnsType)
  If n <= 0
    paynet_DnsFail(#SVC_EARG, "that is not a host name DNS can carry: a part between two dots is empty or longer than 63 characters")
    ProcedureReturn
  EndIf
  paynet_dnsLocalIp = NetSrcFor(paynet_dnsKind, paynet_dnsServer)
  If NetUdpBuild(paynet_dnsKind, paynet_dnsServer, #DNS_PORT, paynet_dnsPort, DnsQueryBuf(), n) = 0
    If NetError() = #NET_E_NO_ARP
      ; The next hop is not known yet. Ask for it, and try again shortly;
      ; the overall bound below still applies.
      hop = NetNextHop(paynet_dnsKind, paynet_dnsServer)
      If hop <> 0
        If NetArpRequest(paynet_dnsKind, hop) <> 0
          LinkTxStagedOn(paynet_dnsKind)
        EndIf
      EndIf
      paynet_dnsDue = now + #PAYNET_DNS_ARP_MS
      ProcedureReturn
    EndIf
    paynet_DnsFail(#SVC_EIO, "the network stack refused to build the DNS query for the route it was given")
    ProcedureReturn
  EndIf
  If LinkTxStagedOn(paynet_dnsKind) = 0
    paynet_DnsFail(#SVC_EIO, "the interface did not transmit the DNS query")
    ProcedureReturn
  EndIf
  paynet_dnsTries = paynet_dnsTries + 1
  paynet_dnsQueries = paynet_dnsQueries + 1
  paynet_dnsDeadline = now + #PAYNET_DNS_TRY_MS
  paynet_dnsState = #PAYNET_DNS_WAIT
EndProcedure

; One bounded step: finish an answer or a failure, retry, time out, or send.
; RFC 1035 section 4.2.2: a two-byte network-order message length on TCP.
; At most one send and one bounded receive per service step. The original
; DNS deadline also covers fallback; packet progress never extends it.
Procedure paynet_DnsTcpStep(now.i)
  Define rc.i,st.i,n.i,i.i,capacity.i
  paynet_DnsCloseListener()
  If paynet_dnsLearned<>0
    If NetDnsLearned6Valid(@paynet_dnsLease)<>1
      paynet_DnsFail(#SVC_ESTATE,"the learned IPv6 DNS resolver expired or its link changed")
      ProcedureReturn
    EndIf
  EndIf
  If ((now-paynet_dnsStart) & $FFFFFFFF)>=(#PAYNET_DNS_TRY_MS * #PAYNET_DNS_TRIES)
    paynet_DnsFail(#SVC_ETIMEOUT,"the DNS TCP retry exceeded the query deadline")
    ProcedureReturn
  EndIf
  If paynet_dnsTcp=0
    n=DnsBuildQueryType(@paynet_dnsName[0],paynet_dnsQid,paynet_dnsType)
    If n<=0 Or n>#DNS_OUT_MAX
      paynet_DnsFail(#SVC_EARG,"the DNS TCP query could not be serialized")
      ProcedureReturn
    EndIf
    NetWriteBE16(@paynet_dnsTcpTx[0],n)
    For i=0 To n-1 : paynet_dnsTcpTx[i+2]=PeekA(DnsQueryBuf()+i) : Next
    If paynet_dnsFamily=6
      rc=PayNetTcpOpen6On(paynet_dnsKind,@paynet_dnsServer6[0],#DNS_PORT)
    Else
      rc=PayNetTcpOpen(paynet_dnsServer,#DNS_PORT)
    EndIf
    If rc=#SVC_EBUSY : ProcedureReturn : EndIf
    If rc<0
      paynet_DnsFail(rc,"TCP to the DNS resolver could not be opened")
      ProcedureReturn
    EndIf
    paynet_dnsTcp=rc : paynet_dnsTcpTxLen=n+2 : paynet_dnsTcpTxOff=0
    paynet_dnsTcpRxLen=0 : paynet_dnsTcpRxWant=2
  EndIf
  st=PayNetTcpState(paynet_dnsTcp)
  If st<0
    paynet_DnsFail(st,"TCP to the DNS resolver failed")
    ProcedureReturn
  EndIf
  If st=#SVC_TCP_CONNECTING : ProcedureReturn : EndIf
  If st<>#SVC_TCP_OPEN And st<>#SVC_TCP_PEER_CLOSED
    paynet_DnsFail(#SVC_EIO,"the DNS TCP connection entered an invalid state")
    ProcedureReturn
  EndIf
  If paynet_dnsTcpTxOff<paynet_dnsTcpTxLen And st=#SVC_TCP_OPEN
    n=PayNetTcpSend(paynet_dnsTcp,@paynet_dnsTcpTx[paynet_dnsTcpTxOff],paynet_dnsTcpTxLen-paynet_dnsTcpTxOff)
    If n<0 Or n>paynet_dnsTcpTxLen-paynet_dnsTcpTxOff
      paynet_DnsFail(#SVC_EIO,"the DNS TCP query could not be transmitted")
      ProcedureReturn
    EndIf
    paynet_dnsTcpTxOff=paynet_dnsTcpTxOff+n
    If n>0 And paynet_dnsTcpTxOff=paynet_dnsTcpTxLen : paynet_dnsQueries=paynet_dnsQueries+1 : EndIf
  EndIf
  capacity=paynet_dnsTcpRxWant-paynet_dnsTcpRxLen
  If capacity>2048 : capacity=2048 : EndIf
  n=PayNetTcpRecv(paynet_dnsTcp,@paynet_dnsTcpRx[paynet_dnsTcpRxLen],capacity)
  If n<0 Or n>capacity
    paynet_DnsFail(#SVC_EIO,"receiving the DNS TCP answer failed")
    ProcedureReturn
  EndIf
  paynet_dnsTcpRxLen=paynet_dnsTcpRxLen+n
  If paynet_dnsTcpRxLen=2 And paynet_dnsTcpRxWant=2
    i=NetReadBE16(@paynet_dnsTcpRx[0])
    If i<#DNS_HDR
      paynet_DnsFail(#SVC_EIO,"the DNS TCP answer has an invalid message length")
      ProcedureReturn
    EndIf
    paynet_dnsTcpRxWant=i+2
  EndIf
  If paynet_dnsTcpRxLen=paynet_dnsTcpRxWant
    If paynet_dnsTcpTxOff<>paynet_dnsTcpTxLen
      paynet_DnsFail(#SVC_EIO,"the resolver replied before the DNS query was transmitted")
      ProcedureReturn
    EndIf
    rc=DnsParseReplyTypeFor(@paynet_dnsTcpRx[2],paynet_dnsTcpRxLen-2,paynet_dnsQid,@paynet_dnsName[0],paynet_dnsType)
    If rc<=0
      paynet_DnsFail(#SVC_EIO,"the DNS TCP answer was refused or contained no matching address")
      ProcedureReturn
    EndIf
    paynet_DnsCaptureAnswer(now)
    paynet_DnsCloseTcp()
    paynet_dnsState=#PAYNET_DNS_DONE
  ElseIf n=0 And st=#SVC_TCP_PEER_CLOSED
    paynet_DnsFail(#SVC_EIO,"the DNS resolver closed an incomplete TCP answer")
  EndIf
EndProcedure


Procedure paynet_DnsStep(now.i)
  If paynet_dnsState=#PAYNET_DNS_TCP
    paynet_DnsTcpStep(now)
    ; A reply may complete inside this call. Stage its result before the
    ; resolver checks the cache, or it can replace DONE with a new query.
    If paynet_dnsState<>#PAYNET_DNS_DONE : ProcedureReturn : EndIf
  EndIf
  If paynet_dnsState = #PAYNET_DNS_DONE
    paynet_DnsCloseListener()
    If paynet_dnsType=#DNS_QTYPE_AAAA
      paynet_CachePut6(@paynet_dnsName[0],@paynet_dnsAnswer6[0],paynet_dnsAnswerAt,paynet_dnsTtl)
    Else
      paynet_CachePut(@paynet_dnsName[0],paynet_dnsAnswer,paynet_dnsAnswerAt,paynet_dnsTtl)
    EndIf
    paynet_dnsState = #PAYNET_DNS_IDLE
    ProcedureReturn
  EndIf
  If paynet_dnsState = #PAYNET_DNS_FAIL
    paynet_DnsCloseListener()
    ProcedureReturn
  EndIf
  If paynet_dnsState = #PAYNET_DNS_IDLE
    ProcedureReturn
  EndIf
  If NetIfUsable(paynet_dnsKind) = 0
    paynet_DnsFail(#SVC_ESTATE, "the interface the query went out of lost its address before the answer came")
    ProcedureReturn
  EndIf
  If (now - paynet_dnsStart) >= (#PAYNET_DNS_TRY_MS * #PAYNET_DNS_TRIES)
    paynet_DnsFail(#SVC_ETIMEOUT, "no DNS answer came back in three tries of one and a half seconds; the resolver or the route to it is not answering")
    ProcedureReturn
  EndIf
  If paynet_dnsState = #PAYNET_DNS_WAIT
    If (now - paynet_dnsDeadline) >= 0
      If paynet_dnsTries >= #PAYNET_DNS_TRIES
        paynet_DnsFail(#SVC_ETIMEOUT, "no DNS answer came back in three tries of one and a half seconds; the resolver or the route to it is not answering")
        ProcedureReturn
      EndIf
      paynet_dnsState = #PAYNET_DNS_SEND
      paynet_dnsDue = now
    Else
      ProcedureReturn
    EndIf
  EndIf
  If paynet_dnsState = #PAYNET_DNS_SEND
    If (now - paynet_dnsDue) >= 0
      paynet_DnsSend(now)
    EndIf
  EndIf
EndProcedure

Procedure paynet_DnsCancel()
  NetDnsTraceFinish(#SVC_ESTATE)
  paynet_DnsCloseTcp()
  paynet_DnsCloseListener()
  paynet_dnsState = #PAYNET_DNS_IDLE
  paynet_dnsKind = #HW_LINK_NONE
EndProcedure

; ----------------------------------------------------------------------
;  PayNetDnsResolve(*name) - slot 75. An IPv4 address (positive), or a
;  negative #SVC_* code; #SVC_EAGAIN means "asked, ask again".
; ----------------------------------------------------------------------
Procedure.i paynet_DnsResolveType(*name,qtype.i,destination.i)
  Define now.i
  Define n.i
  Define ip.i
  Define kind.i
  Define dns.i
  Define code.i
  Define resolver6.IPv6AddressStorage,source6.IPv6AddressStorage
  Define family.i,i.i,origin.i,generation.i

  now = millis()
  If qtype<>#DNS_QTYPE_A And qtype<>#DNS_QTYPE_AAAA
    gSvcDetail="unsupported address query type" : ProcedureReturn #SVC_EARG
  EndIf
  If qtype=#DNS_QTYPE_AAAA And destination=0
    gSvcDetail="the IPv6 result pointer was zero" : ProcedureReturn #SVC_EARG
  EndIf
  If *name = 0
    gSvcDetail = "the name pointer was zero"
    ProcedureReturn #SVC_EARG
  EndIf
  n = paynet_NameLen(*name)
  If n = 0
    gSvcDetail = "the name is empty"
    ProcedureReturn #SVC_EARG
  EndIf
  If n < 0
    gSvcDetail = "the name is longer than the 253 characters a DNS name can be"
    ProcedureReturn #SVC_EARG
  EndIf

  ; A dotted quad is already an address and is never sent anywhere.
  ip=-1
  If qtype=#DNS_QTYPE_A : ip=ParseDotted(*name) : EndIf
  If ip >= 0
    If ip = 0 Or ip = $FFFFFFFF
      gSvcDetail = "0.0.0.0 and 255.255.255.255 are not the address of any one host"
      ProcedureReturn #SVC_EARG
    EndIf
    gSvcDetail = 0
    ProcedureReturn ip
  EndIf

  paynet_DnsStep(now)
  If qtype=#DNS_QTYPE_AAAA
    ip=paynet_CacheFind6(*name,now,destination)
  Else
    ip=paynet_CacheFind(*name,now)
  EndIf
  If ip > 0
    gSvcDetail = 0
    ProcedureReturn ip
  EndIf

  If paynet_dnsState = #PAYNET_DNS_SEND Or paynet_dnsState = #PAYNET_DNS_WAIT Or paynet_dnsState = #PAYNET_DNS_TCP
    If paynet_dnsType=qtype And paynet_SameName(@paynet_dnsName[0], *name) <> 0
      gSvcDetail = "the query for that name is still in flight; ask again with the same name"
      ProcedureReturn #SVC_EAGAIN
    EndIf
    gSvcDetail = "another name is being resolved; keep asking for that one until it answers, then ask for this one"
    ProcedureReturn #SVC_EBUSY
  EndIf
  If paynet_dnsState = #PAYNET_DNS_FAIL
    If paynet_dnsType=qtype And paynet_SameName(@paynet_dnsName[0], *name) <> 0
      ; Said once. The next call for this name starts again from nothing.
      code = paynet_dnsErr
      gSvcDetail = paynet_dnsWhy
      paynet_dnsState = #PAYNET_DNS_IDLE
      ProcedureReturn code
    EndIf
    paynet_dnsState = #PAYNET_DNS_IDLE
  EndIf

  ; ---- a new question ----
  ; Query type and resolver transport are independent. The explicit IPv6
  ; resolver takes precedence, including on links with no IPv4 address.
  ; A bad explicit setting is refused, never silently replaced by DHCP.
  family=4 : code=NetDnsResolver6(@resolver6)
  If code<0
    gSvcDetail="net.dns6 is not a valid unicast IPv6 resolver address"
    ProcedureReturn #SVC_EARG
  EndIf
  paynet_dnsKind=#HW_LINK_NONE : paynet_dnsLearned=0
  If code=16
    family=6
    kind=NetTcp6Select(@resolver6,@source6)
    If kind<1
      gSvcDetail="no assigned IPv6 source and route can reach net.dns6"
      ProcedureReturn #SVC_ESTATE
    EndIf
    paynet_dnsKind=kind
  Else
    ; Explicit IPv4 settings and usable DHCP resolvers precede learned RDNSS.
    kind=NetIfNext(0)
    While kind<>#HW_LINK_NONE
      dns=paynet_DnsFor(kind)
      If dns<>0 And NetNextHop(kind,dns)<>0
        paynet_dnsKind=kind : paynet_dnsServer=dns
        Break
      EndIf
      kind=NetIfNext(kind)
    Wend
    If paynet_dnsKind=#HW_LINK_NONE And SettingsGet(EthKeyDns())=0
      kind=NetDnsLearned6Select(@paynet_dnsLease)
      If kind>0
        family=6 : paynet_dnsLearned=1 : paynet_dnsKind=kind
        For i=0 To 15 : PokeA(@resolver6+i,PeekA(@paynet_dnsLease\address+i)) : Next
      EndIf
    EndIf
    If paynet_dnsKind=#HW_LINK_NONE
      gSvcDetail="no configured or learned DNS resolver has a usable route"
      ProcedureReturn #SVC_ESTATE
    EndIf
  EndIf
  ; Refuse a malformed name now, at the call that made it, not a second later.
  If DnsBuildQueryType(*name, 1,qtype) <= 0
    paynet_dnsKind = #HW_LINK_NONE
    gSvcDetail = "that is not a host name DNS can carry: a part between two dots is empty or longer than 63 characters"
    ProcedureReturn #SVC_EARG
  EndIf
  paynet_dnsPort=0 : paynet_dnsFamily=family
  If family=6
    For i=0 To 15 : paynet_dnsServer6[i]=PeekA(@resolver6+i) : Next
  Else
    paynet_dnsPort=#PAYNET_DNS_PORT_BASE+paynet_dnsKind
    If NetUdpListen(paynet_dnsKind,paynet_dnsPort,1)=0
      paynet_dnsPort=0 : paynet_dnsKind=#HW_LINK_NONE
      gSvcDetail="no UDP listener slot is free for the DNS reply"
      ProcedureReturn #SVC_EBUSY
    EndIf
    NetServiceSetUdpHook(@PayNetDnsInput)
  EndIf
  paynet_CopyName(@paynet_dnsName[0], *name)
  paynet_dnsQid = (now ! (paynet_dnsQueries << 7) ! (paynet_dnsServer & $FFFF)) & $FFFF
  If paynet_dnsQid = 0
    paynet_dnsQid = 1
  EndIf
  origin=2 : generation=0
  If family=6
    origin=3
    If paynet_dnsLearned<>0 : origin=4 : generation=paynet_dnsLease\generation : EndIf
  ElseIf SettingsGet(EthKeyDns())<>0
    origin=1
  EndIf
  NetDnsTraceStart(family,paynet_dnsKind,origin,generation,qtype,paynet_dnsServer,@paynet_dnsServer6[0])
  paynet_dnsType=qtype
  paynet_dnsTries = 0
  paynet_dnsStart = now
  paynet_dnsDue = now
  paynet_dnsLocalIp = 0
  paynet_dnsState = #PAYNET_DNS_SEND
  If family=6 : paynet_dnsState=#PAYNET_DNS_TCP : EndIf
  paynet_DnsStep(now)
  If paynet_dnsState = #PAYNET_DNS_FAIL
    code = paynet_dnsErr
    gSvcDetail = paynet_dnsWhy
    paynet_dnsState = #PAYNET_DNS_IDLE
    ProcedureReturn code
  EndIf
  gSvcDetail = "the query has been sent; ask again with the same name"
  ProcedureReturn #SVC_EAGAIN
EndProcedure

; A and AAAA share one bounded query owner; cache and in-flight identity
; include the requested type. AAAA success copies 16 bytes and returns 16.
Procedure.i PayNetDnsResolve(*name)
  ProcedureReturn paynet_DnsResolveType(*name,#DNS_QTYPE_A,0)
EndProcedure

Procedure.i PayNetDnsResolve6(*name,destination.i)
  ProcedureReturn paynet_DnsResolveType(*name,#DNS_QTYPE_AAAA,destination)
EndProcedure

Procedure.i PayNetDnsState() : ProcedureReturn paynet_dnsState : EndProcedure
Procedure.i PayNetDnsQueries() : ProcedureReturn paynet_dnsQueries : EndProcedure
Procedure.i PayNetDnsRejects() : ProcedureReturn paynet_dnsRejects : EndProcedure

; ======================================================================
;  TCP
; ======================================================================

; tcp.pi4's refusal, in the service table's vocabulary. The sentence that
; goes with it is TcpErrorText's, which keeps tcp.pi4's own number.
Procedure.i paynet_TcpCode(rc.i)
  If rc = #NET_TCP_E_RESET
    ProcedureReturn #SVC_EIO
  EndIf
  If rc = #NET_TCP_E_TIMEOUT
    ProcedureReturn #SVC_ETIMEOUT
  EndIf
  If rc = #NET_TCP_E_NOADDR Or rc = #NET_TCP_E_NOLINK Or rc = #NET_TCP_E_ROUTE
    ProcedureReturn #SVC_ESTATE
  EndIf
  If rc = #NET_TCP_E_BUSY
    ProcedureReturn #SVC_EBUSY
  EndIf
  If rc = #NET_TCP_E_PORT Or rc = #NET_TCP_E_ARG
    ProcedureReturn #SVC_EARG
  EndIf
  ProcedureReturn #SVC_EIO
EndProcedure

Procedure paynet_TcpLatch(i.i, code.i, *why)
  paynet_tcpFail[i] = code
  paynet_tcpWhy[i] = *why
EndProcedure

Procedure paynet_TcpFree(i.i)
  paynet_tcpFamily[i]=4
  paynet_tcpUsed[i] = 0
  paynet_tcpSock[i] = -1
  paynet_tcpGen[i] = 0
  paynet_tcpFail[i] = 0
  paynet_tcpWhy[i] = 0
EndProcedure

; A handle's slot (0..3), or a negative #SVC_* code with the detail set.
; REFUSED BY NAME: the two fragments say which of the two mistakes it was.
Procedure.i paynet_TcpSlot(h.i)
  If h < 1 Or h > #PAYNET_TCP_HANDLES
    gSvcDetail = "that is not a TCP handle: a payload's handles are 1 to 4, and only the TCP open service hands them out"
    ProcedureReturn #SVC_EARG
  EndIf
  If paynet_tcpUsed[h - 1] = 0
    gSvcDetail = "that TCP handle is not open: it was never opened, or it has already been closed"
    ProcedureReturn #SVC_EARG
  EndIf
  ProcedureReturn h - 1
EndProcedure

; Move one handle on: start the connect once the next hop answers, or
; notice that the connection under it has ended. Bounded; never waits.
Procedure paynet_TcpAdvance(i.i, now.i)
  Define keep.i
  Define s.i
  Define rc.i
  Define g.i
  If paynet_tcpUsed[i] = 0 Or paynet_tcpFail[i] <> 0
    ProcedureReturn
  EndIf
  keep = TcpCurrent()
  If paynet_tcpSock[i] < 0
    rc=NetIfUsable(paynet_tcpKind[i])
    If paynet_tcpFamily[i]=6 : rc=NetTcp6SourceValid(paynet_tcpKind[i],@paynet_tcpSource6[i*16]) : EndIf
    If rc = 0
      paynet_TcpLatch(i, #SVC_ESTATE, "the interface toward that address lost its address before the connection was made")
      ProcedureReturn
    EndIf
    If (now - paynet_tcpT0[i]) >= #PAYNET_TCP_OPEN_MS
      paynet_TcpLatch(i, #SVC_ETIMEOUT, "the next hop toward that address never answered the hardware-address request, so no connection was attempted; the machine is not on this network or is switched off")
      ProcedureReturn
    EndIf
    If (now - paynet_tcpNext[i]) < 0
      ProcedureReturn
    EndIf
    paynet_tcpNext[i] = now + #PAYNET_TCP_RETRY_MS
    s = TcpAlloc()
    If s < 0
      TcpUse(keep)
      paynet_TcpLatch(i, #SVC_EBUSY, "every TCP socket in the monitor is in use; a connection this end closed first holds its socket for four minutes of TIME-WAIT")
      ProcedureReturn
    EndIf
    TcpUse(s)
    If paynet_tcpFamily[i]=6
      rc=TcpConnect6(paynet_tcpKind[i],@paynet_tcpSource6[i*16],@paynet_tcpDest6[i*16],paynet_tcpPort[i])
    Else
      rc = TcpConnect(paynet_tcpKind[i], paynet_tcpIp[i], paynet_tcpPort[i])
    EndIf
    If rc = #NET_TCP_OK
      paynet_tcpSock[i] = s
      paynet_tcpGen[i] = TcpGeneration()
    ElseIf rc <> #NET_TCP_E_ARP
      paynet_TcpLatch(i, paynet_TcpCode(rc), TcpErrorText(rc))
    EndIf
    TcpUse(keep)
    ProcedureReturn
  EndIf
  TcpUse(paynet_tcpSock[i])
  g = TcpGeneration()
  If g <> paynet_tcpGen[i]
    If g = paynet_tcpGen[i] + 1
      ; Our connection was wiped and nobody has opened the socket since:
      ; its reason is still there. Read it now, before it can be reused.
      rc = TcpError()
      If TcpWasReset() <> 0
        rc = #NET_TCP_E_RESET
      EndIf
      If rc = #NET_TCP_OK
        paynet_TcpLatch(i, #SVC_EIO, "the connection ended without the TCP layer recording why, which is itself a defect worth reporting")
      Else
        paynet_TcpLatch(i, paynet_TcpCode(rc), TcpErrorText(rc))
      EndIf
    Else
      paynet_TcpLatch(i, #SVC_EIO, "the connection ended and its socket was taken by another connection before the reason could be read")
    EndIf
    paynet_tcpSock[i] = -2
  EndIf
  TcpUse(keep)
EndProcedure

Procedure paynet_TcpAdvanceAll(now.i)
  Define i.i
  For i = 0 To #PAYNET_TCP_HANDLES - 1
    paynet_TcpAdvance(i, now)
  Next
EndProcedure

; ----------------------------------------------------------------------
;  PayNetTcpOpen(ip, port) - slot 76. A handle 1..4 AT ONCE, or a negative
;  code when the open cannot even begin. The handshake runs in the
;  background; SvcTcpState says when it is done.
; ----------------------------------------------------------------------
Procedure.i PayNetTcpOpen(ip.i, port.i)
  Define i.i
  Define h.i
  Define k.i
  Define now.i
  Define code.i
  If ip <= 0 Or ip >= $FFFFFFFF
    gSvcDetail = "the address must be one host's IPv4 address, not 0.0.0.0 or 255.255.255.255"
    ProcedureReturn #SVC_EARG
  EndIf
  If ((ip >> 24) & $FF) >= 224
    gSvcDetail = "that is a multicast or reserved address, and TCP connects to one host"
    ProcedureReturn #SVC_EARG
  EndIf
  If port < 1 Or port > 65535
    gSvcDetail = "a port must be 1 to 65535"
    ProcedureReturn #SVC_EARG
  EndIf
  h = -1
  For i = #PAYNET_TCP_HANDLES - 1 To 0 Step -1
    If paynet_tcpUsed[i] = 0
      h = i
    EndIf
  Next
  If h < 0
    gSvcDetail = "all four of the payload's TCP handles are open; close one first"
    ProcedureReturn #SVC_EBUSY
  EndIf
  k = NetIfForDest(ip)
  If k = #HW_LINK_NONE
    gSvcDetail = "no interface can reach that address: none holds an address on its subnet and none has a gateway; ask the net-up service first"
    ProcedureReturn #SVC_ESTATE
  EndIf
  now = millis()
  paynet_TcpFree(h)
  paynet_tcpUsed[h] = 1
  paynet_tcpKind[h] = k
  paynet_tcpIp[h] = ip
  paynet_tcpPort[h] = port
  paynet_tcpT0[h] = now
  paynet_tcpNext[h] = now
  paynet_TcpAdvance(h, now)
  If paynet_tcpFail[h] <> 0
    ; It could not even begin - no socket, no address. No handle for that.
    code = paynet_tcpFail[h]
    gSvcDetail = paynet_tcpWhy[h]
    paynet_TcpFree(h)
    ProcedureReturn code
  EndIf
  gSvcDetail = 0
  ProcedureReturn h + 1
EndProcedure

; Kernel IPv6 open shares the existing handle/timeout/cleanup owner.
; Address bytes are copied before return; callers need not retain storage.
Procedure.i paynet_TcpOpen6(destination.i,port.i,requiredKind.i)
 Define source.IPv6AddressStorage
 Define k.i,h.i,i.i,now.i,code.i
 If destination=0 Or port<1 Or port>65535 : ProcedureReturn #SVC_EARG : EndIf
 If requiredKind=0
  k=NetTcp6Select(destination,@source)
 Else
  k=NetTcp6SelectOn(requiredKind,destination,@source)
 EndIf
 If k<1
  gSvcDetail="no assigned IPv6 source and route can reach that destination"
  ProcedureReturn #SVC_ESTATE
 EndIf
 h=-1
 For i=#PAYNET_TCP_HANDLES-1 To 0 Step -1
  If paynet_tcpUsed[i]=0 : h=i : EndIf
 Next
 If h<0 : ProcedureReturn #SVC_EBUSY : EndIf
 now=millis() : paynet_TcpFree(h)
 paynet_tcpUsed[h]=1 : paynet_tcpFamily[h]=6 : paynet_tcpKind[h]=k
 For i=0 To 15
  paynet_tcpSource6[h*16+i]=PeekA(@source+i) : paynet_tcpDest6[h*16+i]=PeekA(destination+i)
 Next
 paynet_tcpPort[h]=port : paynet_tcpT0[h]=now : paynet_tcpNext[h]=now
 paynet_TcpAdvance(h,now)
 If paynet_tcpFail[h]<>0
  code=paynet_tcpFail[h] : gSvcDetail=paynet_tcpWhy[h] : paynet_TcpFree(h) : ProcedureReturn code
 EndIf
 gSvcDetail=0 : ProcedureReturn h+1
EndProcedure

Procedure.i PayNetTcpOpen6(destination.i,port.i)
 ProcedureReturn paynet_TcpOpen6(destination,port,0)
EndProcedure
Procedure.i PayNetTcpOpen6On(kind.i,destination.i,port.i)
 If kind<=0 : ProcedureReturn #SVC_EARG : EndIf
 ProcedureReturn paynet_TcpOpen6(destination,port,kind)
EndProcedure
; Slot 86. Where the connection is - see the header for the three states.
Procedure.i PayNetTcpState(h.i)
  Define i.i
  Define keep.i
  Define st.i
  i = paynet_TcpSlot(h)
  If i < 0
    ProcedureReturn i
  EndIf
  paynet_TcpAdvance(i, millis())
  If paynet_tcpFail[i] <> 0
    gSvcDetail = paynet_tcpWhy[i]
    ProcedureReturn paynet_tcpFail[i]
  EndIf
  gSvcDetail = 0
  If paynet_tcpSock[i] < 0
    ProcedureReturn #SVC_TCP_CONNECTING
  EndIf
  keep = TcpCurrent()
  TcpUse(paynet_tcpSock[i])
  st = TcpState()
  TcpUse(keep)
  If st = #TCP_ESTABLISHED
    ProcedureReturn #SVC_TCP_OPEN
  EndIf
  If st = #TCP_CLOSE_WAIT
    ProcedureReturn #SVC_TCP_PEER_CLOSED
  EndIf
  If st = #TCP_SYN_SENT Or st = #TCP_SYN_RECEIVED
    ProcedureReturn #SVC_TCP_CONNECTING
  EndIf
  gSvcDetail = "the connection is in a closing state that only a closed handle can reach, which is a defect worth reporting"
  ProcedureReturn #SVC_ESTATE
EndProcedure

; Slot 77. Bytes accepted (0..n) - fewer than asked is not an error, the
; ring is four kilobytes and the window is the peer's. 0 while connecting.
Procedure.i PayNetTcpSend(h.i, *b, n.i)
  Define i.i
  Define keep.i
  Define took.i
  i = paynet_TcpSlot(h)
  If i < 0
    ProcedureReturn i
  EndIf
  If n < 0 Or (*b = 0 And n > 0)
    gSvcDetail = "a zero buffer pointer or a negative length"
    ProcedureReturn #SVC_EARG
  EndIf
  paynet_TcpAdvance(i, millis())
  If paynet_tcpFail[i] <> 0
    gSvcDetail = paynet_tcpWhy[i]
    ProcedureReturn paynet_tcpFail[i]
  EndIf
  gSvcDetail = 0
  If n = 0 Or paynet_tcpSock[i] < 0
    ProcedureReturn 0
  EndIf
  keep = TcpCurrent()
  TcpUse(paynet_tcpSock[i])
  took = TcpSend(*b, n)
  TcpUse(keep)
  ProcedureReturn took
EndProcedure

; Slot 78. Bytes delivered (0..n), 0 meaning nothing has arrived yet. A
; failed connection answers its code instead, so a loop that only reads
; still finds out.
Procedure.i PayNetTcpRecv(h.i, *b, n.i)
  Define i.i
  Define keep.i
  Define got.i
  i = paynet_TcpSlot(h)
  If i < 0
    ProcedureReturn i
  EndIf
  If n < 0 Or (*b = 0 And n > 0)
    gSvcDetail = "a zero buffer pointer or a negative length"
    ProcedureReturn #SVC_EARG
  EndIf
  paynet_TcpAdvance(i, millis())
  If paynet_tcpFail[i] <> 0
    gSvcDetail = paynet_tcpWhy[i]
    ProcedureReturn paynet_tcpFail[i]
  EndIf
  gSvcDetail = 0
  If n = 0 Or paynet_tcpSock[i] < 0
    ProcedureReturn 0
  EndIf
  keep = TcpCurrent()
  TcpUse(paynet_tcpSock[i])
  got = TcpRead(*b, n)
  TcpUse(keep)
  ProcedureReturn got
EndProcedure

; Slot 79. #SVC_OK, and the handle is free at once. An open connection gets
; its orderly close - queued behind anything still unsent - in the
; background; a failed or still-ARPing one simply goes.
Procedure.i PayNetTcpClose(h.i)
  Define i.i
  Define keep.i
  i = paynet_TcpSlot(h)
  If i < 0
    ProcedureReturn i
  EndIf
  If paynet_tcpFail[i] = 0 And paynet_tcpSock[i] >= 0
    keep = TcpCurrent()
    TcpUse(paynet_tcpSock[i])
    If TcpGeneration() = paynet_tcpGen[i]
      TcpClose()
    EndIf
    TcpUse(keep)
  EndIf
  paynet_TcpFree(i)
  gSvcDetail = 0
  ProcedureReturn #SVC_OK
EndProcedure

Procedure.i PayNetTcpOpenCount()
  Define i.i
  Define n.i
  n = 0
  For i = 0 To #PAYNET_TCP_HANDLES - 1
    If paynet_tcpUsed[i] <> 0
      n = n + 1
    EndIf
  Next
  ProcedureReturn n
EndProcedure

; ======================================================================
;  THE SERVICE SLOT
; ======================================================================

; ----------------------------------------------------------------------
;  PayNetService(sliceMs) - slot 85. Frames received while it ran (0 or
;  more), or #SVC_EARG for a negative slice. sliceMs above
;  #PAYNET_SLICE_MAX is taken as #PAYNET_SLICE_MAX. 0 runs each service
;  once and drains nothing more. See THE SERVICE SLOT in the header for
;  what it costs.
; ----------------------------------------------------------------------
Procedure.i PayNetService(sliceMs.i)
  Define profiling.i,profileStart.i,phaseStart.i
  Define t0.i
  Define frames.i
  Define before.i
  Define passes.i
  If sliceMs < 0
    gSvcDetail = "the time slice must be zero or more milliseconds"
    ProcedureReturn #SVC_EARG
  EndIf
  If sliceMs > #PAYNET_SLICE_MAX
    sliceMs = #PAYNET_SLICE_MAX
  EndIf
  profiling=NetServiceProfileBegin()
  profileStart=HwMicros()
  t0 = millis()
  frames = LinkRxFrames()
  phaseStart=HwMicros()
  UartMessageBegin()
  NetServiceProfileRecord(profiling,1,phaseStart)
  ; ---- THE PROMPT'S NETWORK SERVICES. The same calls, in the same order,
  ; as AnvilPromptServiceOne's slots 2 and 4 in Anvil/Core/parse.pbi; the
  ; desk gate compares the two lists. Slots 0, 1 and 3 there are the
  ; mouse, touch, screen, fan and temperature - the payload's, or not the
  ; network's - and are deliberately absent.
  phaseStart=HwMicros()
  WifiMaintenanceTick()
  NetServiceProfileRecord(profiling,2,phaseStart)
  phaseStart=HwMicros()
  NetDhcpTick()
  NetServiceProfileRecord(profiling,3,phaseStart)
  CompilerIf #CAP_NET = 1
    phaseStart=HwMicros()
    NtpServiceTick()
    NetServiceProfileRecord(profiling,4,phaseStart)
  CompilerEndIf
  phaseStart=HwMicros()
  NetConsoleRearm()
  NetServiceProfileRecord(profiling,5,phaseStart)
  phaseStart=HwMicros()
  NetConsolePump()
  NetServiceProfileRecord(profiling,6,phaseStart)
  phaseStart=HwMicros()
  NetConsoleLlTick()
  NetServiceProfileRecord(profiling,7,phaseStart)
  CompilerIf #CAP_NET = 1
    phaseStart=HwMicros()
    HttpServerPoll()
    NetServiceProfileRecord(profiling,8,phaseStart)
  CompilerElse
    phaseStart=HwMicros()
    TcpTick()
    NetServiceProfileRecord(profiling,8,phaseStart)
  CompilerEndIf
  ; ---- the payload's own: a query to send or retry, connects to start.
  phaseStart=HwMicros()
  paynet_DnsStep(millis())
  NetServiceProfileRecord(profiling,9,phaseStart)
  phaseStart=HwMicros()
  paynet_TcpAdvanceAll(millis())
  NetServiceProfileRecord(profiling,10,phaseStart)
  phaseStart=HwMicros()
  TlsClientAdvance()                ; the TLS connection, if one is open
  NetServiceProfileRecord(profiling,11,phaseStart)
  ; ---- the rest of the slice: drain while frames keep coming.
  phaseStart=HwMicros()
  passes = 0
  While sliceMs > 0 And (millis() - t0) < sliceMs And passes < #PAYNET_DRAIN_PASSES
    before = LinkRxFrames()
    TcpPoll(0)
    passes = passes + 1
    If LinkRxFrames() = before
      Break
    EndIf
  Wend
  NetServiceProfileRecord(profiling,12,phaseStart)
  If passes > 0
    phaseStart=HwMicros()
    paynet_DnsStep(millis())
    NetServiceProfileRecord(profiling,9,phaseStart)
    phaseStart=HwMicros()
    paynet_TcpAdvanceAll(millis())
    NetServiceProfileRecord(profiling,10,phaseStart)
    phaseStart=HwMicros()
    TlsClientAdvance()
    NetServiceProfileRecord(profiling,11,phaseStart)
  EndIf
  phaseStart=HwMicros()
  UartMessageEnd()
  NetServiceProfileRecord(profiling,13,phaseStart)
  gSvcDetail = 0
  NetServiceProfileEnd(profiling,profileStart)
  ProcedureReturn LinkRxFrames() - frames
EndProcedure

; ----------------------------------------------------------------------
;  PayNetCommandPump(sliceMs) - the same engine, driven from a MONITOR
;  COMMAND (`https get`) rather than a payload. The prompt is the caller,
;  and the network console is the very thing printing the command's
;  output, so the console pump, its re-arm and the message bracket that
;  PayNetService runs are NOT run here: pumping the console from inside a
;  command it is executing swallowed that command's output. What runs is
;  the receive drain (TcpPoll), then this engine's own steps and the TLS
;  connection.
; ----------------------------------------------------------------------
Procedure PayNetCommandPump(sliceMs.i)
  TcpPoll(sliceMs)
  ; Lease and protocol progress includes IPv6 neighbor discovery. This does
  ; not re-enter the console dispatcher while its command owns the output.
  NetDhcpTick()
  paynet_DnsStep(millis())
  paynet_TcpAdvanceAll(millis())
  TlsClientAdvance()
EndProcedure

; ----------------------------------------------------------------------
;  PayNetUp() - slot 72. Run the network services once, then say where the
;  link stands:
;    #SVC_OK      an interface holds an address and carries traffic
;    #SVC_EAGAIN  a link is up and is still being given an address -
;                 keep calling the service slot and ask again
;    #SVC_ESTATE  no link is up. Nothing here can power one up inside a
;                 frame: joining a radio network is seconds of scanning and
;                 handshaking, and the cable is stopped while a payload
;                 runs (see the header). Join at the prompt first; a radio
;                 that drops while the payload runs re-associates by itself
;                 as long as the service slot is called.
; ----------------------------------------------------------------------
Procedure.i PayNetUp()
  Define k.i
  PayNetService(0)
  If NetIfPreferred() <> #HW_LINK_NONE
    gSvcDetail = 0
    ProcedureReturn #SVC_OK
  EndIf
  For k = 1 To #NETIF_KINDS - 1
    If HwLinkHas(k) <> 0 And HwLinkReady(k) <> 0
      gSvcDetail = "a link is up and is still being given an address; keep calling the network service slot and ask again"
      ProcedureReturn #SVC_EAGAIN
    EndIf
  Next
  gSvcDetail = "no network link is up: join a Wi-Fi network at the monitor prompt before starting the payload (the wired port is stopped while a payload runs); a radio that drops re-associates by itself while the network service slot is called"
  ProcedureReturn #SVC_ESTATE
EndProcedure

; Slot 73. #HW_LINK_NONE, _WIRED or _WIFI: the interface an outbound
; connection with no better claim leaves by.
Procedure.i PayNetLink()
  ProcedureReturn NetIfPreferred()
EndProcedure

; Slot 74. That interface's IPv4 address, or 0.
Procedure.i PayNetAddr()
  Define k.i
  k = NetIfPreferred()
  If k = #HW_LINK_NONE
    ProcedureReturn 0
  EndIf
  ProcedureReturn NetIPv4(k)
EndProcedure

; ----------------------------------------------------------------------
;  PayNetPayloadReturned - RunAt calls this when a payload comes back,
;  inside its message bracket, after the lease worker.
;
;  1. The payload's connections die with it: each still open is reset
;     (a peer left waiting on a program that no longer exists learns so
;     now, not after its own timeout) and every handle is forgotten.
;  2. A question still in flight is dropped and its listener closed.
;  3. THE HEALTH CHECK RUNS NOW. A payload that never called the service
;     slot has left the radio unserviced for as long as it ran, and the
;     association poll's twenty-second cadence would otherwise put the
;     first question that long after the prompt is back.
; ----------------------------------------------------------------------
Procedure PayNetPayloadReturned()
  Define i.i
  Define keep.i
  ; The TLS connection rides on one of the TCP handles below; it is closed
  ; first, with its close_notify, while that handle still exists.
  TlsClientPayloadReturned()
  keep = TcpCurrent()
  For i = 0 To #PAYNET_TCP_HANDLES - 1
    If paynet_tcpUsed[i] <> 0
      If paynet_tcpFail[i] = 0 And paynet_tcpSock[i] >= 0
        TcpUse(paynet_tcpSock[i])
        If TcpGeneration() = paynet_tcpGen[i]
          TcpAbort()
        EndIf
      EndIf
      paynet_TcpFree(i)
    EndIf
  Next
  TcpUse(keep)
  paynet_DnsCancel()
  UartMessageBegin()
  WifiMaintenanceCheckNow()
  WifiMaintenanceTick()
  UartMessageEnd()
EndProcedure
