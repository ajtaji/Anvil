; ======================================================================
;  netif.pbi - WHICH INTERFACE, AND WHY. THE POLICY OVER net.pi4'S ROWS.
; ======================================================================
;
;  WHY THIS FILE EXISTS, and it is one measurement.
;  ----------------------------------------------------------------------
;  2026-09-07, a cold boot with a cable running straight to a laptop and
;  a radio joined to the house network. The board had taken a link-local
;  address on the cable (probed and announced per RFC
;  3927) and the console was answering on it. Then the radio finished
;  joining and took its lease, and the board reported:
;
;      the network console is listening on the radio's lease,
;      over the wired Ethernet
;      "this board has exactly one interface Anvil can reach"
;
;  Three things wrong in two lines. The radio's address had displaced the
;  cable's; the cable was named as the carrier of an address that does
;  not exist on it; and a board with two live interfaces said it had one.
;  From the laptop the board had simply vanished.
;
;  THE DEFECT WAS "THE ONE IP LAYER" ITSELF, not the order in which the
;  two links were applied to it - and the cure is in
;  RaspberryPi4/Lib/net.pi4, which now holds ONE ADDRESS ROW PER
;  INTERFACE and takes `kind` as the first parameter of everything that
;  has an identity in it. Read the header over #NET_IF_KINDS there; it
;  is the account of the shape, and of the swap that briefly stood in
;  for it.
;
;  WHAT THIS FILE IS, AFTER 2026-09-08
;  ----------------------------------------------------------------------
;  Between 2026-09-07 and 2026-09-08 this file held a SECOND COPY of the
;  addresses - ip, mask, gw, alt, altMask - and an operation,
;  NetIfActivate(kind), that copied a row into net.pi4's globals before
;  every frame was parsed, with a counter, netif_swaps, whose whole job
;  was to prove to a reader that the copying was happening. That worked,
;  and it was measured working on silicon. It was still two stores of
;  one fact, kept in step by a procedure every caller had to remember to
;  call, in an order nothing could check.
;
;  The addresses now live in net.pi4 and only there. What is left here
;  is what this file actually owns and net.pi4 has no business knowing:
;
;      src             WHERE the address came from - one of the
;                      #NET_ADDR_* codes: a lease, the settings store,
;                      RFC 3927. net.pi4 holds a number; this holds the
;                      sentence `net` prints under it.
;      leaseSecs       what a server granted, 0 when it was not a lease
;      leaseAt         millis() when it was granted
;      rxOwner         WHICH interface a running command is taking frames
;                      off, so that the console's pump does not read the
;                      same queue and throw away what it cannot deliver.
;                      See ONE CONSUMER OF AN INTERFACE'S RECEIVE QUEUE
;                      below for the transfer this was measured on.
;
;  and the POLICY questions, which are the reason a caller comes here at
;  all: does this interface hold an address, can it carry a frame right
;  now, which one should an outbound datagram with no better claim leave
;  by, which one can reach a given address, and how do you walk them.
;
;  SO THE STACK IS SINGULAR AND THE BOARD IS NOT. There is one
;  ARP/IPv4/ICMP/UDP/TCP implementation and one copy of every protocol
;  rule; each interface has its own identity in that implementation's
;  table, and `kind` reaches it as a parameter from the caller that
;  knows it - the pump that just received the frame, or the routing
;  decision that chose where it leaves by. Nothing is copied anywhere,
;  so nothing can be out of step.
;
;  WHY NOT A SECOND COPY OF net.pi4. Because the rules would drift. The
;  ARP merge rule, the fragment refusal, the broadcast-source forgery
;  test, the neighbour confirmation - every one of them would then exist
;  twice and be fixed once. This project has already paid for that
;  lesson twice over (see the header of RaspberryPi4/Lib/link.pi4 on the
;  "two IP stacks" that were never quite two).
;
;  THE SECOND ADDRESS, AND WHY AN INTERFACE HAS TWO
;  ----------------------------------------------------------------------
;  The alias is net.pi4's field and its rules are NetSetIPv4Alt's. It
;  exists for one situation the bench asked for by name: a cable with no
;  DHCP server on it, where the board has given itself a link-local
;  address AND is about to hand out leases of its own on
;  192.168.137.0/24 (Anvil/Core/dhcpd.pbi). The board must answer at
;  BOTH addresses at once, because the two peers it might meet are:
;
;    a machine that is a DHCP client and will take 192.168.137.2 - it
;    then cannot reach 169.254.x.y at all, because Windows drops its
;    self-assigned address the moment it gets a lease;
;
;    a machine that is not, and is sitting on its own link-local
;    address, which is what the laptop on this bench was doing all
;    evening.
;
;  Serving one of them and not the other is the half this lane exists to
;  end, so the interface holds both. NetIfForDest below counts the alias
;  as a directly connected subnet for exactly that reason.
;
;  WHAT DOES **NOT** LIVE HERE
;  ----------------------------------------------------------------------
;  No addresses, no settings store, no driver, no printing. This file is
;  provenance and arithmetic over it, so a gate can drive it with no
;  board underneath. The FACTS - is there a cable, is the radio joined -
;  are the board's and reach here as calls to HwLink*; the DECISION
;  about which interface an operator has pinned is
;  RaspberryPi4/Lib/link.pi4's and is read, not owned.
;
;  REQUIRES - the main program includes these BEFORE this file
;  ----------------------------------------------------------------------
;      Anvil/Hal/hal.pbi             the #HW_LINK_* kinds
;      RaspberryPi4/Lib/net.pi4      the IP layer and its address rows
;      the board's HwLink* backend   HwLinkHas, HwLinkReady, HwLinkMacPtr
;      RaspberryPi4/Lib/link.pi4     LinkPin
;
;  House rule 10: a library never includes a library.
; ======================================================================

; ONE ROW PER KIND, THE SAME SIX ROWS net.pi4 HOLDS. Spelled against
; net.pi4's own constant rather than repeated, so the two tables cannot
; come to disagree about how many interfaces there are.
; Shared-core files cannot depend on a target library's private constant
; namespace. This mirrors the six #HW_LINK_* values (NONE through FILE).
#NETIF_KINDS = 6

; ======================================================================
;  WHERE AN ADDRESS CAME FROM - THE FOUR CODES THE `src` FIELD HOLDS
; ======================================================================
;  THEY LIVE HERE BECAUSE THIS FILE OWNS THE FIELD. They were in
;  Anvil/Core/netcfg.pbi until 2026-09-07, beside the procedure that
;  used to be the only writer of them, and that stopped working the
;  moment a driver had to record its own address: a constant may not be
;  USED before it is DECLARED, so RaspberryPi4/Lib/wifi.pi4 - which is
;  compiled long before netcfg.pbi and which binds the radio's own boot
;  lease - could not name the code for a lease at all. Two ways out of
;  that: a second copy of the numbers, or the vocabulary living with the
;  record it describes. A second copy of a number that means something
;  is how a board comes to disagree with itself.
;
;  netcfg.pbi still holds the REASONING - what each source means, how
;  they fail differently, and why the board remembers which it was - and
;  it is worth reading there.
;
;  THE ORDER THEY ARE PREFERRED IN IS NOT HERE and is not a property of
;  the codes: it is RaspberryPi4/Board/eth.pi4's boot order, which is a
;  lease, then a saved address, then link-local, each for a reason
;  written out at that call site.
; ======================================================================
#NET_ADDR_NONE      = 0    ; nothing has been bound
#NET_ADDR_LEASE     = 1    ; a DHCP server said so
#NET_ADDR_SAVED     = 2    ; it was in the settings store
#NET_ADDR_LINKLOCAL = 3    ; RFC 3927, picked and probed by this board

Global Dim netif_src.i[#NETIF_KINDS]
Global Dim netif_leaseSecs.i[#NETIF_KINDS]
Global Dim netif_leaseAt.i[#NETIF_KINDS]
Global Dim netif_dns.i[#NETIF_KINDS]

Procedure.i netif_Valid(kind.i)
  If kind <= #HW_LINK_NONE
    ProcedureReturn 0
  EndIf
  If kind >= #NETIF_KINDS
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  NetIfSet - give this interface an address and record where it came
;  from. 1 if it was recorded.
;
;  IT VALIDATES BY ASKING net.pi4, not by re-implementing the rules. The
;  netmask contiguity test, the "an address may not be its own subnet's
;  network number or broadcast" test and the "a gateway must be on our
;  own subnet" test all live in NetSetIPv4 and are worth exactly one
;  copy - so a record is admitted here only if the IP layer accepted it,
;  and the way to find that out is to hand it over.
;
;  THE MAC GOES IN FIRST AND FROM THE SAME KIND. An interface's six
;  bytes and its IPv4 address are two fields of one row in net.pi4, and
;  a frame built for that row reads both out of it; putting them in
;  together here is what makes "the wired card's MAC with the radio's
;  address" - a board whose every reply is filtered out by its own
;  access point, silently - unsayable rather than merely unwise.
;
;  A REFUSED RECORD CHANGES NOTHING. The old row stands and the caller
;  prints net.pi4's own refusal.
; ----------------------------------------------------------------------
Procedure.i NetIfSet(kind.i, ip.i, mask.i, gw.i, src.i)
  Define m.i
  If netif_Valid(kind) = 0
    ProcedureReturn 0
  EndIf
  If ip = 0
    ProcedureReturn 0
  EndIf
  m = HwLinkMacPtr(kind)
  If m = 0
    ProcedureReturn 0
  EndIf
  If NetSetMac(kind, m) = 0
    ProcedureReturn 0
  EndIf
  If NetSetIPv4(kind, ip, mask, gw) = 0
    ProcedureReturn 0
  EndIf
  netif_src[kind] = src
  ProcedureReturn 1
EndProcedure

; The second address on an interface. `ip` of 0 removes it. See THE
; SECOND ADDRESS in the header for the one case this is for.
;
; THE ALIAS BELONGS TO THE INTERFACE AND NOT TO THE ADDRESS, so it
; SURVIVES a new primary address being bound: a board that is serving
; DHCP on 192.168.137.1 and then takes a link-local address of its own
; is still the server. That is now true by construction rather than by
; NetIfSet remembering to re-apply it - the two are separate fields of
; one row in net.pi4 and neither writer touches the other.
Procedure.i NetIfSetAlt(kind.i, ip.i, mask.i)
  If netif_Valid(kind) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn NetSetIPv4Alt(kind, ip, mask)
EndProcedure

; Record what a DHCP server granted, so `net` can say how much of the
; lease is left rather than only that there is one.
Procedure NetIfSetLease(kind.i, secs.i, atMs.i)
  If netif_Valid(kind) = 0
    ProcedureReturn
  EndIf
  netif_leaseSecs[kind] = secs
  netif_leaseAt[kind] = atMs
EndProcedure

Procedure NetIfSetDns(kind.i, ip.i)
  If netif_Valid(kind) = 0
    ProcedureReturn
  EndIf
  netif_dns[kind] = ip & $FFFFFFFF
EndProcedure

Procedure.i NetIfDns(kind.i)
  If netif_Valid(kind) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn netif_dns[kind]
EndProcedure

; ----------------------------------------------------------------------
;  NetIfClear - this interface has no address any more.
;
;  IT CLEARS THE ALIAS TOO. An interface with no address of its own that
;  went on answering at a second one would be a board reachable at an
;  address `net` does not print, which is worse than unreachable.
; ----------------------------------------------------------------------
Procedure NetIfClear(kind.i)
  If netif_Valid(kind) = 0
    ProcedureReturn
  EndIf
  NetClearIPv4(kind)
  netif_src[kind] = #NET_ADDR_NONE
  netif_leaseSecs[kind] = 0
  netif_leaseAt[kind] = 0
  netif_dns[kind] = 0
EndProcedure

Procedure.i NetIfSrc(kind.i)
  If netif_Valid(kind) = 0
    ProcedureReturn #NET_ADDR_NONE
  EndIf
  ProcedureReturn netif_src[kind]
EndProcedure

Procedure.i NetIfLeaseSecs(kind.i)
  If netif_Valid(kind) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn netif_leaseSecs[kind]
EndProcedure

Procedure.i NetIfLeaseAt(kind.i)
  If netif_Valid(kind) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn netif_leaseAt[kind]
EndProcedure

; DOES THIS INTERFACE HOLD AN ADDRESS. The one question everything that
; needs an address asks, and it asks it about an INTERFACE - never about
; the mechanism that produced the address. That rule is
; Memories\the-console-is-networking-not-a-driver-feature and it is the
; reason a console armed off a DHCP lease cost the bench a night.
Procedure.i NetIfHas(kind.i)
  If netif_Valid(kind) = 0
    ProcedureReturn 0
  EndIf
  If NetIPv4(kind) = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ...AND CAN IT CARRY A FRAME RIGHT NOW. An address on an interface the
; board cannot transmit through is a number in a table; this is the test
; anything about to send or arm must use.
Procedure.i NetIfUsable(kind.i)
  If NetIfHas(kind) = 0
    ProcedureReturn 0
  EndIf
  If HwLinkHas(kind) = 0
    ProcedureReturn 0
  EndIf
  If HwLinkReady(kind) = 0
    ProcedureReturn 0
  EndIf
  If HwLinkMacPtr(kind) = 0
    ; This layer builds Ethernet frames. A point-to-point link with no
    ; hardware address is a different shape of interface and is said out
    ; loud here rather than left to a comparison against address zero.
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i NetIfCount()
  Define k.i
  Define n.i
  n = 0
  For k = 1 To #NETIF_KINDS - 1
    If NetIfHas(k) <> 0
      n = n + 1
    EndIf
  Next
  ProcedureReturn n
EndProcedure

Procedure.i NetIfUsableCount()
  Define k.i
  Define n.i
  n = 0
  For k = 1 To #NETIF_KINDS - 1
    If NetIfUsable(k) <> 0
      n = n + 1
    EndIf
  Next
  ProcedureReturn n
EndProcedure

; ----------------------------------------------------------------------
;  NetIfPreferred - which interface an outbound datagram with no better
;  claim should leave by, or #HW_LINK_NONE.
;
;  WIRED FIRST, and it is the 2026-09-02 ruling's "Ethernet preferred
;  when both" unchanged. What HAS changed is that preferring one no
;  longer costs the other its address: this answers a question about
;  which door to leave by, not about who the board is.
;
;  THE OPERATOR'S PIN WINS OUTRIGHT and is read from
;  RaspberryPi4/Lib/link.pi4 rather than copied - `net link wired` is one
;  decision and it must not have two homes. A pin to an interface that
;  holds no address answers NONE rather than quietly using the other
;  one, because "use the cable" and "use whatever works" are different
;  instructions and only one of them was given.
; ----------------------------------------------------------------------
Procedure.i NetIfPreferred()
  Define k.i
  Define pin.i
  pin = LinkPin()
  If pin <> #HW_LINK_NONE
    If NetIfUsable(pin) <> 0
      ProcedureReturn pin
    EndIf
    ProcedureReturn #HW_LINK_NONE
  EndIf
  If NetIfUsable(#HW_LINK_WIRED) <> 0
    ProcedureReturn #HW_LINK_WIRED
  EndIf
  If NetIfUsable(#HW_LINK_WIFI) <> 0
    ProcedureReturn #HW_LINK_WIFI
  EndIf
  For k = 1 To #NETIF_KINDS - 1
    If NetIfUsable(k) <> 0
      ProcedureReturn k
    EndIf
  Next
  ProcedureReturn #HW_LINK_NONE
EndProcedure

; ----------------------------------------------------------------------
;  NetIfForDest - which interface can reach `ip`, or #HW_LINK_NONE.
;
;  THE DESTINATION'S SUBNET DECIDES, and that is the whole of routing on
;  a board with two directly connected networks. A board holding
;  a link-local address on a cable and a private /24 lease on a radio,
;  asked to reach that radio subnet, must not send it out of the cable - and until
;  this procedure existed it did exactly that whenever the cable happened
;  to be the preferred link, because the preference was the only rule
;  there was.
;
;  THIS IS THE PROCEDURE A CALLER WITH A DESTINATION IN ITS HAND ASKS,
;  and its answer is the `kind` it then passes to net.pi4's builders. It
;  used to be wrapped in NetIfOpenFor(), which asked this and then
;  ACTIVATED the answer - pointed the one IP layer at it. There is
;  nothing to point any more: the kind IS the parameter, so the wrapper
;  is gone and the caller passes on what it was told.
;
;  THE ALIAS COUNTS. An interface serving 192.168.137.0/24 as its second
;  address can reach 192.168.137.2 and no other interface can.
;
;  OFF EVERY DIRECTLY CONNECTED SUBNET, the answer is the first usable
;  interface with a GATEWAY, wired first, and #HW_LINK_NONE if none has
;  one. A board whose only address is link-local has no route to the
;  internet and the honest answer is to say so rather than to hand the
;  frame to an interface that will drop it.
; ----------------------------------------------------------------------
Procedure.i NetIfForDest(ip.i)
  Define k.i
  If ip = 0
    ProcedureReturn NetIfPreferred()
  EndIf
  ; A broadcast belongs to the preferred interface: 255.255.255.255 is
  ; on every subnet at once and nothing in the address says which.
  If ip = $FFFFFFFF
    ProcedureReturn NetIfPreferred()
  EndIf
  For k = 1 To #NETIF_KINDS - 1
    If NetIfUsable(k) <> 0
      If (ip & NetMask(k)) = (NetIPv4(k) & NetMask(k))
        ProcedureReturn k
      EndIf
      If NetIPv4Alt(k) <> 0
        If (ip & NetMaskAlt(k)) = (NetIPv4Alt(k) & NetMaskAlt(k))
          ProcedureReturn k
        EndIf
      EndIf
    EndIf
  Next
  If NetIfUsable(#HW_LINK_WIRED) <> 0 And NetGateway(#HW_LINK_WIRED) <> 0
    ProcedureReturn #HW_LINK_WIRED
  EndIf
  If NetIfUsable(#HW_LINK_WIFI) <> 0 And NetGateway(#HW_LINK_WIFI) <> 0
    ProcedureReturn #HW_LINK_WIFI
  EndIf
  For k = 1 To #NETIF_KINDS - 1
    If NetIfUsable(k) <> 0 And NetGateway(k) <> 0
      ProcedureReturn k
    EndIf
  Next
  ProcedureReturn #HW_LINK_NONE
EndProcedure

; ----------------------------------------------------------------------
;  NetIfNext - walk the interfaces that hold a usable address.
;
;  Start with kind 0 and feed the answer back in; #HW_LINK_NONE ends the
;  walk. Written as a procedure rather than left to each caller's own
;  For loop because the console's pump, the console's arming and `net`
;  must agree exactly about which interfaces are in play, and three
;  copies of a loop is three chances to disagree.
; ----------------------------------------------------------------------
Procedure.i NetIfNext(after.i)
  Define k.i
  For k = after + 1 To #NETIF_KINDS - 1
    If NetIfUsable(k) <> 0
      ProcedureReturn k
    EndIf
  Next
  ProcedureReturn #HW_LINK_NONE
EndProcedure

; ======================================================================
;  ONE CONSUMER OF AN INTERFACE'S RECEIVE QUEUE AT A TIME
; ======================================================================
;  A frame comes off a queue exactly once. So a queue with two readers
;  has a rule whether anybody writes one down or not, and when nobody
;  does, the rule is "whichever reader got there first decides" - which
;  means the reader that cannot deliver what it took throws it away and
;  nothing anywhere reports a loss.
;
;  THAT RULE IS ALREADY WRITTEN ONCE IN THIS TREE, one layer down, in
;  HwLinkConsoleArmed's header: "two consumers of one firmware queue
;  means whichever one does not deliver keystrokes silently eats them",
;  which is why the radio's own rekey pump stands down when the console
;  consumes the radio's queue. This is the same rule for the other pair
;  of readers, and it was missing.
;
;  WHAT IT COST - MEASURED ON THE BOARD, 2026-09-11, build 55.
;  `put` over the direct cable acknowledged three blocks and then stalled
;  for its whole retransmit budget with "every retry was spent with no
;  answer". There are two frame consumers inside a transfer's loop: the
;  transfer's own pump, and the CONSOLE's pump, which every turn of that
;  loop reaches through OutBreak() while asking whether a key has been
;  pressed. The console's pump drains the whole queue, hands each frame
;  to the one dispatcher, and drops whatever the dispatcher does not
;  claim - and a transfer's acknowledgement is exactly that: a datagram
;  no automatic service owns, because a command is waiting for it. One
;  stolen acknowledgement was enough. The board went on resending the
;  same block into a receiver that does not answer a duplicate, so the
;  two ends sat in silence until the budget ran out.
;
;  SO A RUNNING COMMAND SAYS WHICH QUEUE IS ITS OWN, and the console's
;  pump leaves that one alone for as long as it is claimed. Nothing is
;  lost by standing down: the command's pump feeds the SAME dispatcher,
;  so console keystrokes, ARP, ICMP, TCP and the DHCP service are all
;  still answered on that interface during the command - and the
;  console's output flush is not a consumer of the queue at all and
;  keeps running.
;
;  ONE SCALAR, BECAUSE THERE IS ONE COMMAND. This monitor runs one
;  command at a time and a transfer holds one interface, so an owner is
;  a single kind rather than a flag per interface - a table would be a
;  second way to say something that cannot be true twice. The other
;  interfaces are untouched: a transfer on the cable does not stop the
;  console pumping the radio.
;
;  IT IS RELEASED BY THE COMMAND THAT TOOK IT, on every way out. A claim
;  that leaked would be a console that had gone deaf on one interface
;  with nothing to see, so the release is not left to a success path.
; ======================================================================
Global netif_rxOwner.i = #HW_LINK_NONE

Procedure NetIfClaimRx(kind.i)
  If netif_Valid(kind) = 0
    ProcedureReturn
  EndIf
  netif_rxOwner = kind
EndProcedure

Procedure NetIfReleaseRx()
  netif_rxOwner = #HW_LINK_NONE
EndProcedure

; Which interface a running command is consuming, or #HW_LINK_NONE.
Procedure.i NetIfRxOwner()
  ProcedureReturn netif_rxOwner
EndProcedure

; ----------------------------------------------------------------------
;  NetIfReset - forget every interface. Called from the same places
;  NetInit() is: a controller that has been restarted holds nothing.
;
;  THE ADDRESSES ARE net.pi4's AND NetReset() CLEARS THEM. This clears
;  the provenance beside them, and the two are called together for the
;  same reason they are written together.
;
;  THE RECEIVE CLAIM GOES WITH THEM. A controller that has been
;  restarted is carrying nobody's conversation, so a claim that survived
;  it would silence the console's pump on an interface with no command
;  behind it.
; ----------------------------------------------------------------------
Procedure NetIfReset()
  Define k.i
  For k = 0 To #NETIF_KINDS - 1
    netif_src[k] = #NET_ADDR_NONE
    netif_leaseSecs[k] = 0
    netif_leaseAt[k] = 0
  Next
  netif_rxOwner = #HW_LINK_NONE
EndProcedure
