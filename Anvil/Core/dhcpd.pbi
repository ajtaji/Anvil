; ======================================================================
;  dhcpd.pbi - WHEN NOTHING ON THE CABLE HANDS OUT ADDRESSES, THIS BOARD
;              DOES.  RFC 2131, the server half, the small way.
; ======================================================================
;
;  WHERE THIS CAME FROM - a bench ruling of 2026-09-07 (~21:00), in
;  the words it was given in:
;
;      "if the pi is getting that 169 address it changes over to dhcp
;       and divvy out an address."
;
;  And it is the right idea, because of what the alternative costs. A
;  cable between this board and a laptop has no DHCP server on it, so
;  both ends fall back to RFC 3927 and sit on 169.254.x.y addresses they
;  chose for themselves. That WORKS - it is what the bench proved on the
;  evening of 2026-09-07 - but it works only for as long as the laptop
;  stays self-assigned, and the moment anything on that machine hands its
;  Ethernet port a real lease, or somebody plugs a second cable in, or a
;  VPN client rewrites the interface metric, the 169.254 address is gone
;  and the board is unreachable again with nothing on the board changed.
;
;  A LEASE IS THE ONLY THING ON A SEGMENT THAT BOTH MACHINES AGREE
;  ABOUT. So the board offers one. The laptop's Ethernet port is already
;  a DHCP client - that is its default and nobody has to touch it - and a
;  DHCP client that is offered an address takes it. Nothing is configured
;  on the other machine, which is the entire requirement:
;  Memories\the-console-is-networking-not-a-driver-feature.
;
;  ======================================================================
;  WHEN IT RUNS, AND WHEN IT STOPS - THIS IS THE PART THAT MATTERS
;  ======================================================================
;  IT STARTS only on a link where THIS BOARD'S OWN DISCOVERS WENT
;  UNANSWERED. That is the measurement, not an assumption: the board asks
;  first, the way any client does, and only a segment that answered
;  nothing gets a server. Two DHCP servers on one segment is a genuinely
;  bad thing - a machine gets whichever OFFER arrives first and the two
;  pools overlap - so the board earns the role by proving the seat is
;  empty.
;
;  IT STOPS the moment a real server is heard. Any DHCPOFFER or DHCPACK
;  seen on the segment that did not come from us is proof that the seat
;  is no longer empty (DhcpdSawServer). The board drops the role, gives
;  up the server address, and takes a lease like everybody else. This is
;  the "a real server appearing later" half of the bench's requirement
;  and it is what makes the feature safe to leave switched on: carry this
;  board to an office network and it becomes a client again by itself.
;
;  IT NEVER RUNS ON THE RADIO. A radio is joined to somebody else's
;  network - there is an access point, and behind it a router that is
;  almost certainly the DHCP server - and a board handing out leases into
;  a home network is a fault report from everybody in the house. The
;  caller passes the kind and the start refuses anything but a wired
;  link, out loud, rather than trusting every future caller to remember.
;
;  ======================================================================
;  THE ADDRESSES, AND WHY THESE PARTICULAR ONES
;  ======================================================================
;      the board          192.168.137.1 / 255.255.255.0
;      the pool           192.168.137.2 .. 192.168.137.20   (19 addresses)
;      no router option
;      the lease          3600 seconds
;      no DNS option at all
;
;  192.168.137.0/24 IS WINDOWS INTERNET CONNECTION SHARING'S OWN SUBNET,
;  and that is the reason for it rather than a coincidence. It is the
;  block a Windows machine on this bench has already used for exactly
;  this cable (see the lock entries of 2026-09-07 19:50), so it collides
;  with nothing here and it is the one an operator will recognise.
;
;  THE POOL IS NINETEEN ADDRESSES because a cable has two ends. It is
;  sized for "a laptop, and then the same laptop again after it changed
;  its hardware address", not for a network. A pool that cannot be
;  exhausted by the machine it exists for is large enough.
;
;  NO DNS OPTION IS SENT, and that is deliberate rather than unfinished.
;  This board is not a resolver and it has no upstream to name; a server
;  that offered itself as a DNS server would make every name lookup on
;  the laptop time out, which is a far worse failure than having no
;  answer at all. RFC 2131 does not require the option.
;
;  NO ROUTER OPTION IS SENT. This board does not forward packets, so it
;  is not a router. Advertising it as one installs a dead default route
;  on the client; that route can outrank a working Wi-Fi route and send
;  unrelated Internet and overlay traffic into this two-machine cable.
;  A direct link needs an address and mask, not a fictitious gateway.
;
;  ======================================================================
;  WHAT IS IMPLEMENTED, AND WHAT IS DELIBERATELY NOT
;  ======================================================================
;  DONE: DISCOVER -> OFFER, REQUEST -> ACK, and a NAK for a REQUEST that
;  names an address this server cannot give. A lease table of nineteen
;  entries keyed on the client's hardware address, so the same machine
;  gets the same address every time - which matters because the operator
;  types that address into a tool.
;
;  NOT DONE, and each is a decision: no relay agents (giaddr must be
;  zero; a relayed request is somebody else's network); no BOOTP-only
;  clients (a request with no option 53 is not answered); no DECLINE
;  handling beyond dropping the offer's reservation; no INFORM. Every
;  one of them is a path that cannot occur on a cable between two
;  machines, and an unimplemented path that says nothing is better than
;  a half-implemented one that answers wrongly.
;
;  ======================================================================
;  REQUIRES - the main program includes these BEFORE this file
;  ======================================================================
;      Anvil/Hal/hal.pbi             the #HW_LINK_* kinds
;      RaspberryPi4/Lib/net.pi4      NetUdpBuildBcast,
;                                    NetUdpRx*, NetOutLen
;      RaspberryPi4/Lib/dhcp.pi4     the #DHCP_* constants and layout
;      Anvil/Core/netif.pbi          NetIfSetAlt
;      millis()
;
;  House rule 10: a library never includes a library.
; ======================================================================

; The three numbers, spelled as constants so the gate reads the same ones
; the board serves. 192.168.137.1 = $C0A88901.
#DHCPD_SELF     = $C0A88901
#DHCPD_MASK     = $FFFFFF00
#DHCPD_POOL_LO  = $C0A88902     ; .2
#DHCPD_POOL_HI  = $C0A88914     ; .20
#DHCPD_SLOTS    = 19            ; .2 .. .20 inclusive
#DHCPD_LEASE    = 3600          ; seconds, RFC 2131 option 51
#DHCPD_OFFER_MS = 30000         ; unaccepted offer reservation

; The reply buffer. 300 octets is #DHCP_MIN_LEN and every reply this
; server builds is padded to it, which is what the client half does and
; what elderly relay agents were written to expect.
#DHCPD_OUT_MAX  = 300

Global dhcpd_on.i = 0             ; the server role is held
Global dhcpd_kind.i = #HW_LINK_NONE
Global dhcpd_offers.i             ; OFFERs staged, for `net`
Global dhcpd_acks.i               ; ACKs staged, for `net`
Global dhcpd_naks.i               ; NAKs staged
Global dhcpd_unstaged.i           ; replies owed that could not be staged
Global dhcpd_wrongLink.i          ; DHCP messages refused on another link
Global Dim dhcpd_out.a[#DHCPD_OUT_MAX]

; The lease table. Parallel arrays, the way every other table in this
; tree is written. A slot's address is #DHCPD_POOL_LO + the index.
;   state 0 = free, 1 = offered (not yet requested), 2 = leased
Global Dim dhcpd_state.a[#DHCPD_SLOTS]
Global Dim dhcpd_mac.a[#DHCPD_SLOTS * 6]
Global Dim dhcpd_until.i[#DHCPD_SLOTS]     ; millis() when it expires

Procedure.i dhcpd_SlotIp(s.i)
  ProcedureReturn #DHCPD_POOL_LO + s
EndProcedure

Procedure.i dhcpd_MacEq(s.i, *mac)
  Define i.i
  For i = 0 To 5
    If dhcpd_mac[s * 6 + i] <> PeekA(*mac + i)
      ProcedureReturn 0
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure dhcpd_MacSet(s.i, *mac)
  Define i.i
  For i = 0 To 5
    dhcpd_mac[s * 6 + i] = PeekA(*mac + i)
  Next
EndProcedure

; Every deadline here is less than 2^31 milliseconds away. The low
; 32-bit modular delta therefore remains unambiguous across tick wrap.
Procedure.i dhcpd_Expired(s.i, now.i)
  Define delta.i
  If dhcpd_state[s] = 0
    ProcedureReturn 1
  EndIf
  delta = (now - dhcpd_until[s]) & $FFFFFFFF
  If delta < $80000000
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  dhcpd_Find - THE SAME MACHINE GETS THE SAME ADDRESS. -1 if this
;  hardware address has no slot yet.
;
;  It is worth more here than on a real server: the address this hands
;  out is an address a person then types into `anvil_wifi.py`, and one
;  that changed every time the laptop's cable was replugged would make
;  the tools' saved arguments wrong at random.
; ----------------------------------------------------------------------
Procedure.i dhcpd_Find(*mac)
  Define s.i
  For s = 0 To #DHCPD_SLOTS - 1
    If dhcpd_state[s] <> 0
      If dhcpd_MacEq(s, *mac) <> 0
        ProcedureReturn s
      EndIf
    EndIf
  Next
  ProcedureReturn -1
EndProcedure

; A free or expired slot. Active offers and leases are never evicted: a
; full pool is a full pool, not permission to give one address to two
; clients.
Procedure.i dhcpd_Alloc(*mac)
  Define s.i
  Define now.i
  now = millis()
  For s = 0 To #DHCPD_SLOTS - 1
    If dhcpd_state[s] = 0
      dhcpd_MacSet(s, *mac)
      ProcedureReturn s
    EndIf
  Next
  For s = 0 To #DHCPD_SLOTS - 1
    If dhcpd_Expired(s, now) <> 0
      dhcpd_state[s] = 0
      dhcpd_until[s] = 0
      dhcpd_MacSet(s, *mac)
      ProcedureReturn s
    EndIf
  Next
  ProcedureReturn -1
EndProcedure

; Is `ip` one of ours to give, and whose is it? -1 for an address outside
; the pool entirely.
Procedure.i dhcpd_SlotOf(ip.i)
  Define s.i
  If ip < #DHCPD_POOL_LO Or ip > #DHCPD_POOL_HI
    ProcedureReturn -1
  EndIf
  s = ip - #DHCPD_POOL_LO
  ProcedureReturn s
EndProcedure

; ----------------------------------------------------------------------
;  THE REQUEST, PARSED. The fields this server reads out of a BOOTP
;  message, filled by dhcpd_Parse and read by nothing else.
; ----------------------------------------------------------------------
Global dhcpd_rqType.i             ; option 53
Global dhcpd_rqXid.i
Global dhcpd_rqFlags.i
Global dhcpd_rqCiaddr.i
Global dhcpd_rqReqIp.i            ; option 50
Global dhcpd_rqServerId.i         ; option 54
Global Dim dhcpd_rqMac.a[6]

; ----------------------------------------------------------------------
;  dhcpd_Parse - 1 if this is a BOOTREQUEST from a DHCP client that this
;  server is allowed to answer.
;
;  EVERY REFUSAL BELOW IS A REASON, not a tidiness check:
;
;    too short / no cookie / no option 53   it is not DHCP at all, and a
;                                           server that answered it would
;                                           be answering BOOTP or noise.
;    op is not BOOTREQUEST                  it is a REPLY - somebody
;                                           else's server, or our own
;                                           broadcast coming back to us.
;    hlen is not 6                          this is Ethernet.
;    giaddr is not zero                     it came through a relay, so
;                                           it belongs to another
;                                           segment and its addresses
;                                           are not ours to hand out.
;    an option runs past the end            malformed; nothing after that
;                                           point can be believed.
; ----------------------------------------------------------------------
Procedure.i dhcpd_Parse(*p, n.i)
  Define i.i
  Define op.i
  Define code.i
  Define len.i
  Define b0.i
  Define b1.i
  Define b2.i
  Define b3.i
  dhcpd_rqType = 0
  dhcpd_rqXid = 0
  dhcpd_rqFlags = 0
  dhcpd_rqCiaddr = 0
  dhcpd_rqReqIp = 0
  dhcpd_rqServerId = 0
  For i = 0 To 5
    dhcpd_rqMac[i] = 0
  Next
  If n < #DHCP_FIXED + 4
    ProcedureReturn 0
  EndIf
  If PeekA(*p + #DHCP_OFF_OP) <> #DHCP_OP_REQUEST
    ProcedureReturn 0
  EndIf
  If PeekA(*p + #DHCP_OFF_HTYPE) <> #DHCP_HTYPE_ETHER
    ProcedureReturn 0
  EndIf
  If PeekA(*p + #DHCP_OFF_HLEN) <> #DHCP_HLEN_ETHER
    ProcedureReturn 0
  EndIf
  ; The magic cookie, four octets at 236, most significant first.
  b0 = PeekA(*p + #DHCP_OFF_COOKIE + 0) & $FF
  b1 = PeekA(*p + #DHCP_OFF_COOKIE + 1) & $FF
  b2 = PeekA(*p + #DHCP_OFF_COOKIE + 2) & $FF
  b3 = PeekA(*p + #DHCP_OFF_COOKIE + 3) & $FF
  If ((b0 << 24) | (b1 << 16) | (b2 << 8) | b3) <> #DHCP_COOKIE
    ProcedureReturn 0
  EndIf
  ; giaddr - four octets at 24. A relayed request is not ours.
  For i = 0 To 3
    If PeekA(*p + #DHCP_OFF_GIADDR + i) <> 0
      ProcedureReturn 0
    EndIf
  Next
  b0 = PeekA(*p + #DHCP_OFF_XID + 0) & $FF
  b1 = PeekA(*p + #DHCP_OFF_XID + 1) & $FF
  b2 = PeekA(*p + #DHCP_OFF_XID + 2) & $FF
  b3 = PeekA(*p + #DHCP_OFF_XID + 3) & $FF
  dhcpd_rqXid = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
  dhcpd_rqFlags = ((PeekA(*p + #DHCP_OFF_FLAGS) & $FF) << 8) | (PeekA(*p + #DHCP_OFF_FLAGS + 1) & $FF)
  b0 = PeekA(*p + #DHCP_OFF_CIADDR + 0) & $FF
  b1 = PeekA(*p + #DHCP_OFF_CIADDR + 1) & $FF
  b2 = PeekA(*p + #DHCP_OFF_CIADDR + 2) & $FF
  b3 = PeekA(*p + #DHCP_OFF_CIADDR + 3) & $FF
  dhcpd_rqCiaddr = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
  For i = 0 To 5
    dhcpd_rqMac[i] = PeekA(*p + #DHCP_OFF_CHADDR + i)
  Next

  ; ---- the options ----
  i = #DHCP_FIXED + 4
  While i < n
    code = PeekA(*p + i) & $FF
    If code = #DHCP_OPT_END
      Break
    EndIf
    If code = #DHCP_OPT_PAD
      i = i + 1
      Continue
    EndIf
    If i + 1 >= n
      ProcedureReturn 0
    EndIf
    len = PeekA(*p + i + 1) & $FF
    If i + 2 + len > n
      ProcedureReturn 0
    EndIf
    If code = #DHCP_OPT_MSG_TYPE And len = 1
      dhcpd_rqType = PeekA(*p + i + 2) & $FF
    ElseIf code = #DHCP_OPT_REQ_IP And len = 4
      b0 = PeekA(*p + i + 2) & $FF
      b1 = PeekA(*p + i + 3) & $FF
      b2 = PeekA(*p + i + 4) & $FF
      b3 = PeekA(*p + i + 5) & $FF
      dhcpd_rqReqIp = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
    ElseIf code = #DHCP_OPT_SERVER_ID And len = 4
      b0 = PeekA(*p + i + 2) & $FF
      b1 = PeekA(*p + i + 3) & $FF
      b2 = PeekA(*p + i + 4) & $FF
      b3 = PeekA(*p + i + 5) & $FF
      dhcpd_rqServerId = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
    EndIf
    i = i + 2 + len
  Wend

  If dhcpd_rqType = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure dhcpd_PutBE32(p.i, v.i)
  dhcpd_out[p + 0] = (v >> 24) & $FF
  dhcpd_out[p + 1] = (v >> 16) & $FF
  dhcpd_out[p + 2] = (v >> 8) & $FF
  dhcpd_out[p + 3] = v & $FF
EndProcedure

; ----------------------------------------------------------------------
;  dhcpd_Build - one BOOTREPLY. Returns its length.
;
;  yiaddr IS THE ONLY THING THAT DIFFERS between an OFFER and an ACK
;  here, plus option 53 - and a NAK carries neither an address nor a
;  netmask, because RFC 2131 4.3.2 says a NAK's other fields are
;  meaningless and a client that read them would act on rubbish.
;
;  THE CLIENT'S xid AND chaddr ARE COPIED BACK EXACTLY. A client matches
;  the reply to its request on the transaction id and drops anything
;  else, which is precisely why a server has nothing to gain by
;  inventing one.
; ----------------------------------------------------------------------
Procedure.i dhcpd_Build(msgType.i, yourIp.i)
  Define i.i
  Define p.i
  For i = 0 To #DHCPD_OUT_MAX - 1
    dhcpd_out[i] = 0
  Next
  dhcpd_out[#DHCP_OFF_OP] = #DHCP_OP_REPLY
  dhcpd_out[#DHCP_OFF_HTYPE] = #DHCP_HTYPE_ETHER
  dhcpd_out[#DHCP_OFF_HLEN] = #DHCP_HLEN_ETHER
  dhcpd_out[#DHCP_OFF_HOPS] = 0
  dhcpd_PutBE32(#DHCP_OFF_XID, dhcpd_rqXid)
  ; secs is zero and flags are echoed: RFC 2131 4.1 says a server sends
  ; the reply the way the client's broadcast flag asked for it, and this
  ; server broadcasts every reply regardless (see DhcpdInput), so the
  ; echo is honesty about what was asked rather than a decision.
  dhcpd_out[#DHCP_OFF_FLAGS] = (dhcpd_rqFlags >> 8) & $FF
  dhcpd_out[#DHCP_OFF_FLAGS + 1] = dhcpd_rqFlags & $FF
  If msgType = #DHCP_ACK
    dhcpd_PutBE32(#DHCP_OFF_CIADDR, dhcpd_rqCiaddr)
  Else
    dhcpd_PutBE32(#DHCP_OFF_CIADDR, 0)
  EndIf
  dhcpd_PutBE32(#DHCP_OFF_YIADDR, yourIp)
  dhcpd_PutBE32(#DHCP_OFF_SIADDR, 0)      ; no boot file server
  dhcpd_PutBE32(#DHCP_OFF_GIADDR, 0)
  For i = 0 To 5
    dhcpd_out[#DHCP_OFF_CHADDR + i] = dhcpd_rqMac[i]
  Next
  dhcpd_PutBE32(#DHCP_OFF_COOKIE, #DHCP_COOKIE)

  p = #DHCP_FIXED + 4
  dhcpd_out[p] = #DHCP_OPT_MSG_TYPE
  dhcpd_out[p + 1] = 1
  dhcpd_out[p + 2] = msgType & $FF
  p = p + 3
  dhcpd_out[p] = #DHCP_OPT_SERVER_ID
  dhcpd_out[p + 1] = 4
  dhcpd_PutBE32(p + 2, #DHCPD_SELF)
  p = p + 6
  If msgType <> #DHCP_NAK
    dhcpd_out[p] = #DHCP_OPT_LEASE
    dhcpd_out[p + 1] = 4
    dhcpd_PutBE32(p + 2, #DHCPD_LEASE)
    p = p + 6
    dhcpd_out[p] = #DHCP_OPT_SUBNET
    dhcpd_out[p + 1] = 4
    dhcpd_PutBE32(p + 2, #DHCPD_MASK)
    p = p + 6
  EndIf
  dhcpd_out[p] = #DHCP_OPT_END
  p = p + 1
  ; Padded to the minimum every DHCP message on this board is padded to.
  If p < #DHCP_MIN_LEN
    p = #DHCP_MIN_LEN
  EndIf
  ProcedureReturn p
EndProcedure

Procedure.i DhcpdOn()
  ProcedureReturn dhcpd_on
EndProcedure

Procedure.i DhcpdKind()
  ProcedureReturn dhcpd_kind
EndProcedure

Procedure.i DhcpdSelf()
  ProcedureReturn #DHCPD_SELF
EndProcedure

Procedure.i DhcpdMask()
  ProcedureReturn #DHCPD_MASK
EndProcedure

Procedure.i DhcpdOffers()
  ProcedureReturn dhcpd_offers
EndProcedure

Procedure.i DhcpdAcks()
  ProcedureReturn dhcpd_acks
EndProcedure

Procedure.i DhcpdNaks()
  ProcedureReturn dhcpd_naks
EndProcedure

Procedure.i DhcpdUnstaged()
  ProcedureReturn dhcpd_unstaged
EndProcedure

Procedure.i DhcpdWrongLink()
  ProcedureReturn dhcpd_wrongLink
EndProcedure

; How many addresses are currently handed out, for `net`.
Procedure.i DhcpdLeased()
  Define s.i
  Define n.i
  Define now.i
  now = millis()
  n = 0
  For s = 0 To #DHCPD_SLOTS - 1
    If dhcpd_state[s] = 2 And dhcpd_Expired(s, now) = 0
      n = n + 1
    EndIf
  Next
  ProcedureReturn n
EndProcedure

; The address slot `s` holds, or 0. For `net` and for the gate.
Procedure.i DhcpdLeaseIp(s.i)
  If s < 0 Or s >= #DHCPD_SLOTS
    ProcedureReturn 0
  EndIf
  If dhcpd_state[s] = 0
    ProcedureReturn 0
  EndIf
  If dhcpd_Expired(s, millis()) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn dhcpd_SlotIp(s)
EndProcedure

; ----------------------------------------------------------------------
;  DhcpdStart - take the server role on this link. 1 if it was taken.
;
;  IT REFUSES A RADIO, out loud in the caller's return value, for the
;  reason in the header: a board handing out leases into somebody's home
;  network is a fault everybody else in the house reports.
;
;  IT TAKES THE SERVER ADDRESS AS THE INTERFACE'S SECOND ADDRESS, not as
;  its primary. The primary is the link-local address the board probed
;  and defends, and a peer that is NOT a DHCP client can still only
;  reach the board there - so both must answer at once, which is what
;  the alias is for (Anvil/Core/netif.pbi, THE SECOND ADDRESS).
;
;  IT BINDS PORT 67 AS THE SERVICE PORT rather than as the bound port,
;  because a server has to be listening across every ping, dns lookup
;  and console exchange the board does in between (net.pi4,
;  NetUdpListen).
; ----------------------------------------------------------------------
Procedure.i DhcpdStart(kind.i)
  Define s.i
  If kind <> #HW_LINK_WIRED
    ProcedureReturn 0
  EndIf
  If dhcpd_on <> 0
    ProcedureReturn 1
  EndIf
  ; Client and server are mutually exclusive roles on one interface. A
  ; tracked lease must be released by policy before direct-cable service
  ; can start; silently running both is a competing DHCP configuration.
  If DhcpClientState(kind) <> #DHCPC_INIT
    ProcedureReturn 0
  EndIf
  If NetIfSetAlt(kind, #DHCPD_SELF, #DHCPD_MASK) = 0
    ProcedureReturn 0
  EndIf
  If NetUdpListen(kind, #DHCP_PORT_SERVER, 1) = 0
    NetIfSetAlt(kind, 0, 0)
    ProcedureReturn 0
  EndIf
  For s = 0 To #DHCPD_SLOTS - 1
    dhcpd_state[s] = 0
    dhcpd_until[s] = 0
  Next
  dhcpd_on = 1
  dhcpd_kind = kind
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  DhcpdStop - give the role up. Idempotent.
;
;  THE ALIAS GOES WITH IT. A board still answering at 192.168.137.1
;  after it had stopped serving that subnet would be an address `net`
;  reports and nothing hands out - and worse, an address a machine that
;  had a lease keeps talking to while its lease quietly runs down.
; ----------------------------------------------------------------------
Procedure DhcpdStop()
  Define s.i
  If dhcpd_on = 0
    ProcedureReturn
  EndIf
  NetIfSetAlt(dhcpd_kind, 0, 0)
  NetUdpListen(dhcpd_kind, #DHCP_PORT_SERVER, 0)
  For s = 0 To #DHCPD_SLOTS - 1
    dhcpd_state[s] = 0
    dhcpd_until[s] = 0
  Next
  dhcpd_on = 0
  dhcpd_kind = #HW_LINK_NONE
EndProcedure

; ----------------------------------------------------------------------
;  DhcpdSawServer - A REAL DHCP SERVER HAS SPOKEN ON THIS SEGMENT.
;  1 if that ended the server role.
;
;  The one piece of evidence that matters, and it is evidence rather
;  than a guess: a BOOTREPLY carrying option 53 = OFFER or ACK, from a
;  source address that is not this board. Nothing else on a segment
;  produces one.
;
;  CALLED FROM THE RECEIVE PATH on every DHCP datagram, including the
;  ones this server is about to answer, so a board that has taken the
;  role and then meets a real server gives it up within one exchange
;  rather than at the next boot.
; ----------------------------------------------------------------------
Procedure.i DhcpdSawServer(*p, n.i, fromIp.i)
  Define i.i
  Define code.i
  Define len.i
  Define t.i
  If dhcpd_on = 0
    ProcedureReturn 0
  EndIf
  If fromIp = #DHCPD_SELF
    ProcedureReturn 0
  EndIf
  If n < #DHCP_FIXED + 4
    ProcedureReturn 0
  EndIf
  If PeekA(*p + #DHCP_OFF_OP) <> #DHCP_OP_REPLY
    ProcedureReturn 0
  EndIf
  t = 0
  i = #DHCP_FIXED + 4
  While i < n
    code = PeekA(*p + i) & $FF
    If code = #DHCP_OPT_END
      Break
    EndIf
    If code = #DHCP_OPT_PAD
      i = i + 1
      Continue
    EndIf
    If i + 1 >= n
      Break
    EndIf
    len = PeekA(*p + i + 1) & $FF
    If i + 2 + len > n
      Break
    EndIf
    If code = #DHCP_OPT_MSG_TYPE And len = 1
      t = PeekA(*p + i + 2) & $FF
      Break
    EndIf
    i = i + 2 + len
  Wend
  If t <> #DHCP_OFFER And t <> #DHCP_ACK
    ProcedureReturn 0
  EndIf
  DhcpdStop()
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  DhcpdInput - one datagram on port 67, already delivered by the IP
;  layer. Returns 1 with a reply STAGED in net.pi4's output buffer, which
;  the caller sends the same way it sends every other staged reply.
;
;  IT DOES NOT SEND. That is the same seam every other protocol in this
;  tree draws: whoever is pumping the wire owns the wire, and a library
;  that transmitted would have to know which link it was on. The console
;  pump calls this and sends what it stages.
;
;  EVERY REPLY IS BROADCAST. RFC 2131 4.1 permits a unicast reply to
;  yiaddr with the client's chaddr written into the ARP cache by hand,
;  and this board deliberately does not: the client does not have the
;  offered address yet, so a unicast reply is a frame addressed to an
;  address nobody holds, and getting it through means poking a neighbour
;  cache entry for an address that may yet be refused. A broadcast is
;  correct for every client and needs none of it. On a cable with two
;  machines on it there is nobody to inconvenience.
;
;  THE SOURCE ADDRESS IS NAMED IN THE CALL. The reply goes to
;  255.255.255.255, which is on no subnet, so nothing in the destination
;  can tell the IP layer which of this interface's two addresses to
;  source it from - and a DHCP reply whose source is the board's
;  169.254 address is one every client discards, because it does not
;  match the server identifier inside the message. So #DHCPD_SELF is
;  passed to NetUdpBuildBcast, which refuses any address the interface
;  does not actually hold. It used to be said by setting a mode,
;  NetUseIPv4(#DHCPD_SELF), that the next frame built would read; the
;  frame and the source it leaves with are now one statement, and a
;  build that happened between the two can no longer take the wrong
;  one.
; ----------------------------------------------------------------------
Procedure.i DhcpdInput(kind.i, *p, n.i, fromIp.i)
  Define s.i
  Define want.i
  Define len.i
  Define reply.i
  If dhcpd_on = 0
    ProcedureReturn 0
  EndIf
  ; A server role belongs to one segment. Broadcast DHCP traffic heard
  ; through the other interface must neither receive an offer nor cause
  ; this interface's server role to stand down.
  If kind <> dhcpd_kind
    dhcpd_wrongLink = dhcpd_wrongLink + 1
    ProcedureReturn 0
  EndIf
  ; A REAL SERVER ENDS THE ROLE, and it is tested before anything is
  ; answered so that the board cannot reply to a client in the same
  ; instant it learns it should not be serving at all.
  If DhcpdSawServer(*p, n, fromIp) <> 0
    ProcedureReturn 0
  EndIf
  If dhcpd_Parse(*p, n) = 0
    ProcedureReturn 0
  EndIf

  If dhcpd_rqType = #DHCP_DISCOVER
    s = dhcpd_Find(@dhcpd_rqMac[0])
    If s < 0
      s = dhcpd_Alloc(@dhcpd_rqMac[0])
    EndIf
    If s < 0
      ProcedureReturn 0
    EndIf
    ; Duplicate discovery by a current lessee keeps both its address and
    ; its deadline. A new or expired reservation gets a short offer
    ; lifetime until REQUEST proves that the client accepted it.
    If dhcpd_state[s] <> 2 Or dhcpd_Expired(s, millis()) <> 0
      dhcpd_state[s] = 1
      dhcpd_until[s] = (millis() + #DHCPD_OFFER_MS) & $FFFFFFFF
    EndIf
    reply = #DHCP_OFFER
    want = dhcpd_SlotIp(s)
  ElseIf dhcpd_rqType = #DHCP_REQUEST
    ; WHICH ADDRESS IS BEING ASKED FOR. RFC 2131 4.3.2: option 50 in the
    ; SELECTING and INIT-REBOOT states, ciaddr in RENEWING and
    ; REBINDING. Both are read, option 50 first, because a client in
    ; SELECTING sets ciaddr to zero and one that reads ciaddr only
    ; would NAK every first-time client on the segment.
    want = dhcpd_rqReqIp
    If want = 0
      want = dhcpd_rqCiaddr
    EndIf
    ; ----------------------------------------------------------------
    ; A REQUEST NAMING ANOTHER SERVER ENDS THE ROLE, AND IT IS THE ONLY
    ; PROOF OF A RIVAL THIS BOARD CAN ACTUALLY RECEIVE.
    ;
    ; A rival server's OFFER is addressed to port 68 - the CLIENT's port
    ; - so it never reaches this server, which listens on 67 (RFC 2131
    ; 4.1). What does reach it is what the client does next: in the
    ; SELECTING state a client broadcasts its REQUEST to port 67 with
    ; option 54 set to the server it chose, precisely so that every
    ; other server on the segment learns it lost. That message is
    ; addressed to this board as much as to the winner, and it is
    ; conclusive: a client cannot name a server identifier it was not
    ; offered.
    ;
    ; So this is not merely "not ours to answer" - answering it would be
    ; arguing with a server this board has already lost to - it is the
    ; board finding out that the seat it took is no longer empty, and
    ; standing down is what makes the whole feature safe to leave
    ; switched on. DhcpdSawServer above is the other half, for a
    ; BOOTREPLY that does arrive here.
    ; ----------------------------------------------------------------
    If dhcpd_rqServerId <> 0 And dhcpd_rqServerId <> #DHCPD_SELF
      DhcpdStop()
      ProcedureReturn 0
    EndIf
    s = dhcpd_SlotOf(want)
    If s < 0
      ; Outside the pool entirely - a client remembering a lease from
      ; another network. RFC 2131 4.3.2 says NAK, and a NAK is what
      ; makes that client restart and get a usable address in one more
      ; exchange instead of failing quietly for its whole lease time.
      reply = #DHCP_NAK
      want = 0
    ElseIf dhcpd_state[s] <> 0 And dhcpd_Expired(s, millis()) = 0 And dhcpd_MacEq(s, @dhcpd_rqMac[0]) = 0
      ; Somebody else holds it. NAK rather than a silent drop: the
      ; client is entitled to find out now.
      reply = #DHCP_NAK
      want = 0
    Else
      dhcpd_MacSet(s, @dhcpd_rqMac[0])
      dhcpd_state[s] = 2
      dhcpd_until[s] = (millis() + #DHCPD_LEASE * 1000) & $FFFFFFFF
      reply = #DHCP_ACK
    EndIf
  ElseIf dhcpd_rqType = #DHCP_RELEASE
    s = dhcpd_Find(@dhcpd_rqMac[0])
    If s >= 0
      dhcpd_state[s] = 0
      dhcpd_until[s] = 0
    EndIf
    ProcedureReturn 0
  ElseIf dhcpd_rqType = #DHCP_DECLINE
    ; The client found the address in use by somebody else. Drop it and
    ; never hand it out again this session - the slot is marked leased
    ; to a hardware address of all ones, which no card has.
    s = dhcpd_SlotOf(dhcpd_rqReqIp)
    If s >= 0
      dhcpd_state[s] = 2
      dhcpd_until[s] = millis() + #DHCPD_LEASE * 1000
      dhcpd_mac[s * 6 + 0] = $FF
      dhcpd_mac[s * 6 + 1] = $FF
      dhcpd_mac[s * 6 + 2] = $FF
      dhcpd_mac[s * 6 + 3] = $FF
      dhcpd_mac[s * 6 + 4] = $FF
      dhcpd_mac[s * 6 + 5] = $FF
    EndIf
    ProcedureReturn 0
  Else
    ProcedureReturn 0
  EndIf

  len = dhcpd_Build(reply, want)
  If NetUdpBuildBcast(kind, #DHCPD_SELF, #DHCP_PORT_CLIENT, #DHCP_PORT_SERVER, @dhcpd_out[0], len) = 0
    dhcpd_unstaged = dhcpd_unstaged + 1
    ProcedureReturn 0
  EndIf
  If reply = #DHCP_OFFER
    dhcpd_offers = dhcpd_offers + 1
  ElseIf reply = #DHCP_ACK
    dhcpd_acks = dhcpd_acks + 1
  ElseIf reply = #DHCP_NAK
    dhcpd_naks = dhcpd_naks + 1
  EndIf
  ProcedureReturn 1
EndProcedure
