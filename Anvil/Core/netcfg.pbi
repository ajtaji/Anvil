; ======================================================================
;  WHERE AN ADDRESS CAME FROM, AND THE ONE PATH BOTH KINDS TAKE
; ======================================================================
;  A board can end up holding an IPv4 address two ways, and until
;  2026-09-07 only one of them worked properly.
;
;    A LEASE. `dhcp` runs DISCOVER/OFFER/REQUEST/ACK over whichever link
;    the policy layer chose, applies the result to THAT link's address
;    row in the IP layer, tells the board, and arms the console.
;
;    A STORED ADDRESS. `net address`, `net netmask` and `net gateway`
;    write three strings into the settings store, `settings save` keeps
;    them, and SettingsLoad brings them back at the next boot.
;
;  THE SECOND ONE WENT NOWHERE, and it cost the bench an evening on
;  2026-09-07. The stored address configured the IP layer eventually -
;  the next command that chose an interface applied it - so the board
;  answered ping on the cable and looked entirely healthy. What it did
;  NOT do was any of the three other things a lease does, and the one
;  that mattered was arming the console: the machine at the other end of
;  the cable could ping the board and could not talk to it, which is the
;  exact shape of unreachable this whole line of work exists to end.
;
;  THE FIX IS NOT A SECOND PATH. NetAddressBound below is the tail of
;  the lease path, lifted out and called by both, so a stored address
;  reaches precisely the same state a lease reaches. Two paths that are
;  meant to converge and are written twice do not stay converged; the
;  arming rule would have been fixed in one of them and not the other,
;  which is the same defect one layer up.
;
;  WHY THE SOURCE IS REMEMBERED AT ALL. See gEthAddrFrom in the board's
;  network globals: the two behave identically and FAIL differently.
; ======================================================================
; ----------------------------------------------------------------------
;  A THIRD SOURCE, 2026-09-07 EVENING: the board gave it to ITSELF.
;
;  RFC 3927 link-local. There is no DHCP server on a cable running
;  straight into a laptop - the board asked four times over twelve
;  seconds and nothing answered, because there was nothing there to
;  answer - and the laptop at the other end of that cable had already
;  done exactly this to itself and was sitting on a stale link-local address. So the
;  board does the same: pick an address out of 169.254/16, ARP-probe it
;  three times to establish that nobody else has it, announce it, defend
;  it. Anvil/Core/netll.pbi is the machine; RaspberryPi4/Lib/net.pi4
;  holds the packets, the conflict test and the RFC's numbers.
;
;  IT TAKES THE SAME TAIL, and that is the whole reason this is a third
;  CONSTANT rather than a third code path: NetAddressBound below does
;  not care where an address came from, and the console arms from an
;  interface HOLDING an address, never from the mechanism that produced
;  one.
;
;  THE ORDER IS LEASE, SAVED, LINK-LOCAL, and each step is a reason:
;    1. A LEASE, because a DHCP server is the only thing on a segment
;       that can say for certain that an address is free.
;    2. A SAVED ADDRESS, because somebody typed it on purpose and ran
;       `settings save`, which outranks anything the board invents.
;    3. LINK-LOCAL, because an address the board has proved free with
;       its own probes still beats NO address - and no address means no
;       console, which means a board nobody can reach.
;
;  A LEASE ARRIVING LATER REPLACES IT. NetAddressBound clears the
;  board's record of the link-local address whenever an address from any
;  other source is bound, so a board that comes up self-assigned and is
;  later plugged into a real network ends up on the real network.
;
;  ======================================================================
;  THE FOUR CODES THEMSELVES LIVE IN Anvil/Core/netif.pbi SINCE
;  2026-09-07, and only the numbers moved - all of the reasoning above
;  is about them and belongs here, beside the procedure that acts on it.
;
;    #NET_ADDR_NONE       0   nothing has been bound
;    #NET_ADDR_LEASE      1   a DHCP server said so
;    #NET_ADDR_SAVED      2   it was in the settings store
;    #NET_ADDR_LINKLOCAL  3   RFC 3927, picked and probed by us
;
;  WHY THEY HAD TO MOVE: a constant may not be USED before it is
;  DECLARED, and RaspberryPi4/Lib/wifi.pi4 - compiled long before this
;  file - binds the radio's own boot lease and has to name the code for
;  a lease. The alternative was a second copy of four numbers that mean
;  something, which is how a board comes to disagree with itself.
;  netif.pbi owns the field they go in, so it is the right home.
; ----------------------------------------------------------------------

; ----------------------------------------------------------------------
;  NetAddressBound - THE TAIL EVERY ADDRESS TAKES. The caller has already
;  put `ip`, `mask` and `gw` into `kind`'s address row with
;  NetSetIPv4(kind, ...) and has had its refusal printed if that failed;
;  this is everything that happens afterwards, and it is the same list
;  whatever the source.
;
;    1. RECORD the three numbers where `net`, `get` and `put` read them.
;    2. TELL THE BOARD, because on some boards an address is not just
;       three numbers in the IP layer - a radio keeps its own answer to
;       "do I have one" and things hang off it (Anvil/Hal/hal.pbi,
;       HwLinkAddressBound).
;    3. ARM THE CONSOLE. The prompt re-derives this on its next spin
;       anyway, so this call is not what makes it correct - it is what
;       makes the "listening on ..." line land inside the output of the
;       command that caused it, where the person who typed it is
;       looking, rather than one keystroke later.
;
;  IT MUST BE IDEMPOTENT and it is: every step is a store or an
;  idempotent re-derivation, so a lease renewal of an address the board
;  already holds re-records the same numbers and finds the console
;  already listening on the same link.
; ----------------------------------------------------------------------
Procedure NetAddressBound(kind.i, ip.i, mask.i, gw.i, src.i)
  ; ------------------------------------------------------------------
  ; STEP ZERO, ADDED 2026-09-07: RECORD IT AGAINST THE INTERFACE.
  ;
  ; This is the one procedure every address on this board goes through,
  ; whatever produced it, so it is the one place the per-interface table
  ; can be kept true without a path being forgotten - which is the same
  ; argument that put the other three steps here in the first place.
  ;
  ; AND IT IS WHAT STOPS ONE LINK DISPLACING THE OTHER. Before the
  ; table, "binding an address" meant writing the board's ONLY address,
  ; so the radio taking its lease took the cable's identity with it and
  ; the laptop on the cable lost the board mid-session (2026-09-07,
  ; measured). NetIfSet writes THIS interface's record and leaves every
  ; other interface's alone. Nothing is pointed anywhere: the IP layer
  ; holds one address row per interface, and the frame that arrives next
  ; is parsed as whichever interface it arrived on.
  ;
  ; A REFUSAL IS NOT FATAL HERE. NetIfSet refuses what NetSetIPv4 would
  ; refuse, and the caller has already put these numbers into the IP
  ; layer and had its own refusal printed if they were bad - so this
  ; failing means the table is unchanged, which the board would rather
  ; have than a record of an address it does not hold.
  ; ------------------------------------------------------------------
  NetIfSet(kind, ip, mask, gw, src)
  ; AND HOW LONG THE LEASE IS FOR, WHEN IT IS ONE. `net` prints it, and
  ; a lease whose length is not recorded is a board that can say it has
  ; a lease and not say when the thing it depends on runs out - which is
  ; the first question about a board that has gone quiet. DhcpLease() is
  ; the option 51 out of the reply that has only just been accepted, so
  ; this is the one instant it is certainly about THIS address.
  If src = #NET_ADDR_LEASE
    NetIfSetLease(kind, DhcpClientLeaseLeft(kind), millis())
    NetIfSetDns(kind, DhcpClientDns(kind))
  Else
    NetIfSetLease(kind, 0, 0)
    NetIfSetDns(kind, 0)
  EndIf
  ; These compatibility globals describe the wired settings page. A
  ; lease on the radio must not rewrite them: the authoritative rows are
  ; already per-interface above, and copying Wi-Fi into gEth* recreates
  ; the very global-address alias this layer removed.
  If kind = #HW_LINK_WIRED
    gEthIp = ip
    gEthMask = mask
    gEthGw = gw
    gEthAddrFrom = src
  EndIf
  ; ------------------------------------------------------------------
  ; A LEASE, OR A SAVED ADDRESS, REPLACES A LINK-LOCAL ONE - and the
  ; board's record of the link-local address has to go with it, because
  ; that record is what EthHasIpConfig() falls back to. Left behind, it
  ; would keep answering "the wired side has an address" with the OLD
  ; self-assigned number after the board had been moved onto a real
  ; network, which is the stale-fact failure this whole evening is
  ; about. Cleared here, in the one procedure every address goes
  ; through, rather than in each caller.
  ;
  ; The link-local path itself sets gEthLlIp AFTER calling this, so its
  ; own record survives; see NetLinkLocalAcquire.
  ; ------------------------------------------------------------------
  If kind = #HW_LINK_WIRED And src <> #NET_ADDR_LINKLOCAL
    gEthLlIp = 0
  EndIf
  ; ------------------------------------------------------------------
  ; A REAL LEASE ON THE LINK WE ARE SERVING ENDS THE SERVER ROLE.
  ;
  ; The other half of this is in the receive path - an OFFER or an ACK
  ; from anybody else ends it too (DhcpdSawServer) - and this half
  ; catches the case where the board's own client took the lease, which
  ; is what happens the moment somebody plugs the cable into a network
  ; that has a server on it and types `dhcp`. Two DHCP servers on one
  ; segment is a genuinely bad thing to leave running.
  ; ------------------------------------------------------------------
  If src = #NET_ADDR_LEASE And DhcpdOn() <> 0 And kind = DhcpdKind()
    DhcpdStop()
    PrintN("  This board was handing out addresses on this link because nothing")
    PrintN("  else was. A real DHCP server has now answered, so it has stopped.")
  EndIf
  HwLinkAddressBound(kind, ip, mask, gw)
  NetConsoleRearm()
EndProcedure

; A leased address is no longer valid on exactly one interface. This is
; deliberately different from taking the hardware link down: Wi-Fi may
; remain associated while a lease expires, and Ethernet may remain
; electrically up while its server sends a NAK. Clear the IP row and the
; board's matching address latch, leave the other interface untouched,
; then re-derive console reachability from the remaining rows.
Procedure NetAddressLost(kind.i)
  Define wasLease.i
  wasLease = 0
  If NetIfSrc(kind) = #NET_ADDR_LEASE
    wasLease = 1
  EndIf
  NetIfClear(kind)
  If kind = #HW_LINK_WIRED And wasLease <> 0
    gEthIp = 0
    gEthMask = 0
    gEthGw = 0
    gEthAddrFrom = #NET_ADDR_NONE
    gEthLlIp = 0
  EndIf
  HwLinkAddressBound(kind, 0, 0, 0)
  NetConsoleRearm()
EndProcedure

; ----------------------------------------------------------------------
;  The sentence `net` and `net link` print about where the address on an
;  INTERFACE came from. It reads after "  ".
;
;  THE INTERFACE IS A PARAMETER SINCE 2026-09-10, AND THAT IS THE FIX.
;  It used to read gEthAddrFrom and gEthIp - the wired port's two
;  compatibility globals - and both of its callers print it directly
;  underneath LinkSay(), which names the SELECTED interface. On a board
;  carrying traffic over the radio with a self-assigned address on the
;  cable, `net` therefore printed the whole RFC 3927 paragraph - "this
;  board gave itself this address out of 169.254.0.0/16" - about an
;  address the line above had just said was not in use. That is the
;  recorded misleading-status defect, and it is the same shape as every
;  other one in this stack: a per-board global answering a question that
;  is per interface.
;
;  netif.pbi's row is the authority. NetIfSrc(kind) is written by
;  NetAddressBound for every source there is, and NetIPv4(kind) is the
;  address the IP layer will actually source from - so the sentence is
;  now derived from what the interface holds rather than from what the
;  wired port last held. Nothing about the link is changed to make the
;  message true; the message is read off the link.
; ----------------------------------------------------------------------
Procedure.i NetAddrFromText(kind.i)
  Define src.i
  src = NetIfSrc(kind)
  If src = #NET_ADDR_LEASE
    ProcedureReturn "This address is a DHCP lease. If the board stops answering, the lease is the first thing to suspect - type dhcp to ask again."
  EndIf
  If src = #NET_ADDR_SAVED
    ; A STORED ADDRESS INSIDE 169.254/16 IS A DIFFERENT AND SHARPER
    ; WARNING, and it is worth its own sentence because it is a trap
    ; somebody will fall into: typing `net address 169.254.x.y` and
    ; running `settings save` looks like it does what the link-local
    ; machinery does, and it skips the only part that matters. The
    ; probes are what establish that nobody else has it, and a stored
    ; address is not probed at any boot - so this is the one shape of
    ; address that can collide with a neighbour that DID probe.
    If NetIsLinkLocal(NetIPv4(kind)) <> 0
      ProcedureReturn "This address is the one stored in the settings, and it is inside 169.254.0.0/16 - the link-local block. Nothing probed it: a stored address is applied at boot without asking the segment whether anyone else has it, which is exactly what the link-local machinery does ask. Clear net address and let the board pick one for itself, and it will be probed and defended."
    EndIf
    ProcedureReturn "This address is the one stored in the settings, not a lease. Nothing on this segment agreed to it, so a second machine using it would collide silently - and settings save is what keeps it across a reset."
  EndIf
  If src = #NET_ADDR_LINKLOCAL
    ProcedureReturn "This board gave itself this address out of 169.254.0.0/16, because nothing answered its DHCP discovers on this link (RFC 3927 link-local). It was ARP-probed three times before it was taken and it is defended, so it is not a guess - but a 169.254 address is not routable and nothing off this segment can reach it. Plug into a network with a DHCP server, or type dhcp, and a lease replaces it."
  EndIf
  ProcedureReturn ""
EndProcedure

Procedure PutMac()
  Define i.i
  i = 0
  While i < 6
    If i > 0
      UartWrite(58)              ; 58 is a colon
    EndIf
    PutHex2(gEthMac[i] & $FF)
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  EthConfig - the four addresses, read out of the settings store and
;  put to net.pi4 for judgement.
;
;  IT IS NO LONGER A TRANSFER'S PRECONDITION - 2026-09-10. It used to be
;  called from three places: both transfer commands and the four
;  setters. `get` and `put` now ask NetXferServer() below for the one
;  address they genuinely need and route by NetIfForDest(); see that
;  procedure's header for what demanding four keys cost. The ONE caller
;  left is `net <setter>`, checking that the four saved wired addresses
;  agree with each other at the moment the fourth is typed.
;
;  SILENT WHEN IT WORKS, LOUD WHEN IT DOES NOT. Its caller wants the
;  refusal printed and does not want a confirmation printed twice.
;
;  KNOWN, RECORDED, NOT YET FIXED: this procedure still VALIDATES BY
;  APPLYING - its NetSetIPv4(#HW_LINK_WIRED, ...) below is how it gets
;  net.pi4's rules without a second copy of them, and that write does not
;  go through NetAddressBound. On the setter path NetStaticApply() has
;  normally already bound the same tuple properly, so the write is
;  redundant; when the cable is out NetStaticApply refuses and this then
;  leaves the wired address row holding a tuple whose provenance in
;  netif.pbi was never updated. The right shape is a rule that can be
;  ASKED as well as applied - a NetCheckIPv4 in net.pi4 that NetSetIPv4
;  itself calls - which is a change to the file that owns the rule and is
;  a separate slice.
;
;  THE MASK AND GATEWAY RULES ARE NOT RE-IMPLEMENTED HERE. NetSetIPv4()
;  refuses a non-contiguous netmask (#NET_E_MASK), an address that is
;  its own subnet's network number or broadcast, and a gateway outside
;  our own subnet (#NET_E_GATEWAY) - net.pi4:895-935, with the reasoning
;  at :857-893, including the first version of the contiguity test that
;  was wrong in the worst direction and rejected 255.255.255.0. One copy
;  of a rule is one thing to be right about.
;
;  A GATEWAY OF 0.0.0.0 IS LEGAL AND MEANS "there is not one":
;  everything off-link is then refused with #NET_E_NO_ROUTE rather than
;  sent into the void (net.pi4:886-888). On a direct cable between two
;  machines that is the honest configuration, and it is why the gateway
;  is a required key rather than an optional one - being made to type
;  0.0.0.0 is being made to say out loud that there is no router.
; ----------------------------------------------------------------------
Procedure.i EthConfig()
  Define a.i
  Define m.i
  Define g.i
  Define s.i
  Define missing.i

  missing = 0
  If SettingsHas(EthKeyAddress()) = 0
    missing = 1
  EndIf
  If SettingsHas(EthKeyNetmask()) = 0
    missing = 1
  EndIf
  If SettingsHas(EthKeyGateway()) = 0
    missing = 1
  EndIf
  If SettingsHas(EthKeyServer()) = 0
    missing = 1
  EndIf
  If missing <> 0
    PrintN("!! this board has no network configuration, so nothing was done. Four")
    PrintN("   addresses are needed and each one is set on its own line:")
    PrintN("     net address <this board>       the address this board answers to")
    PrintN("     net netmask <mask>             255.255.255.0 on an ordinary")
    PrintN("                                    private network")
    PrintN("     net gateway <router>           or 0.0.0.0 if there is no router,")
    PrintN("                                    which is the truth on a direct cable")
    PrintN("     net server <tftp server>       the machine serving the files")
    PrintN("   Type net on its own to see which of the four are already set.")
    ProcedureReturn 0
  EndIf

  a = ParseDotted(SettingsGet(EthKeyAddress()))
  m = ParseDotted(SettingsGet(EthKeyNetmask()))
  g = ParseDotted(SettingsGet(EthKeyGateway()))
  s = ParseDotted(SettingsGet(EthKeyServer()))
  If a < 0 Or m < 0 Or g < 0 Or s < 0
    PrintN("!! one of the stored addresses is not four numbers separated by full")
    PrintN("   stops, so nothing was done. Type net to see them and set the bad one")
    PrintN("   again. A value can get into the store by hand as well - through")
    PrintN("   settings set, or by editing SETTINGS.TXT on another machine - and")
    PrintN("   that path does not check it, which is why it is checked here.")
    ProcedureReturn 0
  EndIf
  If s = 0
    PrintN("!! the TFTP server address is 0.0.0.0, which is not a machine. Type")
    PrintN("   net server <address> with the address of the computer that is")
    PrintN("   serving the file. Nothing was done.")
    ProcedureReturn 0
  EndIf

  ; ------------------------------------------------------------------
  ; THE STORED ADDRESS IS THE WIRED PORT'S, and it is named here rather
  ; than passed in. The four keys this procedure reads - EthKeyAddress,
  ; EthKeyNetmask, EthKeyGateway, EthKeyServer - are the cable's: they
  ; are the same numbers RaspberryPi4/Board/eth.pi4 keeps in gEthIp,
  ; gEthMask and gEthGw, and HwLinkStaticUp, the one procedure that puts
  ; them on a wire, refuses unless EthCableIn() and then brings up the
  ; wired port. Neither caller has an interface in its hand - one runs
  ; BEFORE the bring-up, deliberately, and the other is only checking
  ; that the four agree - so asking them for one would be asking them to
  ; invent it.
  ; ------------------------------------------------------------------
  If NetSetIPv4(#HW_LINK_WIRED, a, m, g) = 0
    PrintN("!! the network stack refused these four addresses, so nothing was done.")
    EthWhyNet()
    Print("   board ")
    PutIp(a)
    Print("   netmask ")
    PutIp(m)
    Print("   gateway ")
    PutIp(g)
    PrintNl()
    PrintN("   The two rules that catch most of this: a netmask must be a run of")
    PrintN("   ones followed by a run of zeroes, and a gateway must be on this")
    PrintN("   board's own subnet - a router you could only reach through a router")
    PrintN("   is not a router. Use 0.0.0.0 when there is no router at all.")
    ProcedureReturn 0
  EndIf

  gEthIp = a
  gEthMask = m
  gEthGw = g
  gEthSrv = s
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  NetXferServer - THE ONE ADDRESS A TRANSFER CANNOT DERIVE. Returns the
;  stored TFTP server address, or 0 with the refusal already printed.
;
;  WHAT THIS REPLACES, AND WHY IT IS A CHANGE OF SHAPE AND NOT A RELAXED
;  CHECK. `get` and `put` went through EthConfig() above, which demands
;  FOUR keys - net.address, net.netmask, net.gateway, net.server - and
;  then writes the first three into the WIRED interface's address row.
;  Both halves of that are wrong now and the second one is the worse:
;
;    THE BOARD ALREADY HAS ADDRESSES. Since 2026-09-08 every interface
;    owns its own row, and a board on a bare cable comes up holding a
;    probed link-local address, a served 192.168.137.1 alias, and a
;    lease on the radio - three addresses, none of which is in the
;    settings store, all of which the console answers on. Refusing a
;    transfer for want of net.address on that board is refusing for want
;    of a fact the board is standing on.
;
;    SO THE OPERATOR TYPES THE KEYS, AND THAT IS THE DAMAGE. Measured on
;    2026-09-10 (build 41): four temporary net.* keys had to be typed to
;    get one file off the board, and EthConfig's NetSetIPv4 then wrote
;    them over the wired row - replacing a probed, defended link-local
;    address with an unprobed typed one, with no NetAddressBound tail and
;    therefore no provenance, no console re-derivation and no record in
;    netif.pbi. The keys then had to be removed again by hand.
;
;  WHAT A TRANSFER ACTUALLY NEEDS is the thing nothing on this board can
;  know: WHICH MACHINE IS SERVING THE FILE. Everything else - this
;  board's own address, its netmask, its gateway, and which interface to
;  leave by - is already per-interface state, and NetIfForDest() is the
;  procedure that turns a destination into an interface. That is the
;  shape `tcp connect` has used since 2026-09-08 and it is the one this
;  path should have been converted to at the same time.
;
;  net.address, net.netmask and net.gateway are NOT removed and are not
;  deprecated: they are the SAVED-ADDRESS source, applied at boot and by
;  NetStaticApply through the same tail a lease takes. They simply stop
;  being a precondition for a transfer, because they never described one.
; ----------------------------------------------------------------------
Procedure.i NetXferServer()
  Define s.i
  If SettingsHas(EthKeyServer()) = 0
    PrintN("!! this board does not know which machine is serving the file, so")
    PrintN("   nothing was transferred. That is the one address a transfer cannot")
    PrintN("   work out for itself, and it is set on one line:")
    PrintN("     net server <a.b.c.d>           the machine serving the files")
    PrintN("   Nothing else is needed. This board's own address, its netmask, its")
    PrintN("   gateway and the interface to send over are all read from the")
    PrintN("   interface that can reach that server - type net to see them.")
    ProcedureReturn 0
  EndIf
  s = ParseDotted(SettingsGet(EthKeyServer()))
  If s < 0
    PrintN("!! the stored server address is not four numbers separated by full")
    PrintN("   stops, so nothing was transferred. Type net server <a.b.c.d> again.")
    PrintN("   A value can get into the store by hand as well - through settings")
    PrintN("   set, or by editing SETTINGS.TXT on another machine - and that path")
    PrintN("   does not check it, which is why it is checked here.")
    ProcedureReturn 0
  EndIf
  If s = 0
    PrintN("!! the TFTP server address is 0.0.0.0, which is not a machine. Type")
    PrintN("   net server <address> with the address of the computer that is")
    PrintN("   serving the file. Nothing was transferred.")
    ProcedureReturn 0
  EndIf
  ProcedureReturn s
EndProcedure

; ----------------------------------------------------------------------
;  EthConfigIp - the THREE addresses ping and dns need, without the TFTP
;  server that get and put require.
;
;  WHY A SECOND CONFIG READER. EthConfig() above insists on all four
;  addresses because a transfer cannot happen without a server. ping and
;  dns need only this board's own address, its netmask and its gateway -
;  a DNS server address is a fifth thing, read separately - so requiring
;  net.server for them would refuse a perfectly pingable board for want
;  of a TFTP server it is never going to talk to. After dhcp, which sets
;  the first three and not the fourth, that refusal would be routine.
;
;  THE MASK AND GATEWAY RULES ARE STILL NetSetIPv4's, exactly as in
;  EthConfig - one copy of a rule. gEthSrv is left untouched: a server
;  set earlier stays set, and one never set stays zero.
;
;  THE INTERFACE IS A PARAMETER SINCE 2026-09-08, because the IP layer
;  holds one address row per interface and there is no longer a single
;  identity for three stored numbers to land in. The caller has to say
;  which interface the stored address belongs to, and it is the only
;  thing that can: this file reads the settings store and knows nothing
;  about which link is carrying traffic.
; ----------------------------------------------------------------------
; ----------------------------------------------------------------------
;  EthHasIpConfig - IS there a usable wired address? QUIET, and it
;  CONFIGURES NOTHING.
;
;  FOUND ON SILICON, 2026-09-04. LinkBringUp needs to know whether the
;  wired side has an address before it can apply the ruling's "Ethernet
;  preferred when both", and the obvious thing to ask was EthConfigIp().
;  That was wrong twice over: EthConfigIp PRINTS eight lines of guidance
;  when the addresses are unset, and it CALLS NetSetIPv4 when they are.
;  On a bench that runs on Wi-Fi with no wired addresses stored - which
;  is this bench - every single network command therefore began by
;  telling the operator to go and set three addresses it did not need,
;  and on a bench that had them it would have written an interface's
;  address row before deciding whether that interface was carrying
;  anything.
;
;  A PREDICATE THAT PRINTS IS NOT A PREDICATE. Splitting the question
;  from the action is the fix, and the two now share their parsing so
;  they cannot disagree about what counts as usable.
; ----------------------------------------------------------------------
;
;  AND SINCE 2026-09-07 IT ANSWERS YES FOR A LINK-LOCAL ADDRESS TOO,
;  which is one `If` and is the whole of what makes RFC 3927 work here.
;
;  Everything downstream asks THIS ONE PREDICATE whether the wired side
;  has an address: HwLinkOpen's preference order, HwLinkStaticUp,
;  NetStaticApply, and through them the console's arming. A self-
;  assigned address that this predicate said no to would be an address
;  the board held and could not use - it would not be preferred over a
;  radio, it would not configure the IP layer, and the console would not
;  arm on it. That is the same shape of defect as the lease-only console
;  one layer down, so the fix is in the same place: the question is "is
;  there a usable wired address", never "where did it come from".
;
;  THE STORE STILL WINS. A saved static address is somebody's considered
;  choice and outranks an address the board invented, so the settings
;  are read first and the fallback is only reached when they are absent
;  or unparseable. gEthLlIp is set only by the link-local machinery and
;  cleared by NetAddressBound the moment an address from anywhere else
;  is bound, so the two cannot both be live.
;
;  THE MASK AND GATEWAY ARE NOT STORED ANYWHERE - they are constants of
;  the RFC, /16 and no router - so they are written here rather than
;  kept in two more globals that could disagree with the address.
; ----------------------------------------------------------------------
Procedure.i EthHasIpConfig()
  Define a.i
  Define m.i
  Define g.i
  If SettingsHas(EthKeyAddress()) = 0 Or SettingsHas(EthKeyNetmask()) = 0 Or SettingsHas(EthKeyGateway()) = 0
    If gEthLlIp <> 0
      gEthIp = gEthLlIp
      gEthMask = #NET_LL_MASK
      gEthGw = 0
      ProcedureReturn 1
    EndIf
    ProcedureReturn 0
  EndIf
  a = ParseDotted(SettingsGet(EthKeyAddress()))
  m = ParseDotted(SettingsGet(EthKeyNetmask()))
  g = ParseDotted(SettingsGet(EthKeyGateway()))
  If a < 0 Or m < 0 Or g < 0
    If gEthLlIp <> 0
      gEthIp = gEthLlIp
      gEthMask = #NET_LL_MASK
      gEthGw = 0
      ProcedureReturn 1
    EndIf
    ProcedureReturn 0
  EndIf
  gEthIp = a
  gEthMask = m
  gEthGw = g
  ProcedureReturn 1
EndProcedure

Procedure.i EthConfigIp(kind.i)
  Define a.i
  Define m.i
  Define g.i
  Define missing.i

  missing = 0
  If SettingsHas(EthKeyAddress()) = 0
    missing = 1
  EndIf
  If SettingsHas(EthKeyNetmask()) = 0
    missing = 1
  EndIf
  If SettingsHas(EthKeyGateway()) = 0
    missing = 1
  EndIf
  If missing <> 0
    PrintN("!! this board has no network address, so nothing was done. Three")
    PrintN("   addresses are needed and each is set on its own line:")
    PrintN("     net address <this board>       the address this board answers to")
    PrintN("     net netmask <mask>             255.255.255.0 on an ordinary")
    PrintN("                                    private network")
    PrintN("     net gateway <router>           or 0.0.0.0 if there is no router")
    PrintN("   Or type dhcp to have all three assigned automatically. Type net on")
    PrintN("   its own to see which are already set.")
    ProcedureReturn 0
  EndIf

  a = ParseDotted(SettingsGet(EthKeyAddress()))
  m = ParseDotted(SettingsGet(EthKeyNetmask()))
  g = ParseDotted(SettingsGet(EthKeyGateway()))
  If a < 0 Or m < 0 Or g < 0
    PrintN("!! one of the stored addresses is not four numbers separated by full")
    PrintN("   stops, so nothing was done. Type net to see them and set the bad one")
    PrintN("   again.")
    ProcedureReturn 0
  EndIf

  If NetSetIPv4(kind, a, m, g) = 0
    PrintN("!! the network stack refused these addresses, so nothing was done.")
    EthWhyNet()
    Print("   board ")
    PutIp(a)
    Print("   netmask ")
    PutIp(m)
    Print("   gateway ")
    PutIp(g)
    PrintNl()
    ProcedureReturn 0
  EndIf

  gEthIp = a
  gEthMask = m
  gEthGw = g
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  EthDown - stop the MAC. Safe to call when it was never up.
;
;  CALLED BEFORE EVERY JUMP INTO A PAYLOAD, from RunAt(). The receive
;  DMA engine is a bus master writing into #ETH_RX_BASE on its own
;  schedule, and handing the machine to arbitrary code while that is
;  running means two writers in one address space with no agreement
;  between them. Stopping it costs two register writes and removes the
;  whole class.
;
;  GenetStop() clears TX_EN and RX_EN and then disables the DMA, in that
;  order, because stopping the DMA first would leave a MAC still
;  accepting frames with nowhere to put them (genet.pi4:2739-2745).
; ----------------------------------------------------------------------
