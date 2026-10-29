; Shared address binding, lease metadata and console-rearm policy.
; Requires netif, DHCP client/server and the HwLink address notification seam.
XIncludeFile "Anvil/Core/net_address_state.pbi"

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
