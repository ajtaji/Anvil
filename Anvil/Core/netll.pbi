; ======================================================================
;  THE LINK-LOCAL STATE MACHINE - RFC 3927, on whichever link is asked
; ======================================================================
;  THE BENCH, 2026-09-07 EVENING, and this is the whole reason it exists.
;  The requirement, in the words it was given in: "I WANT NETWORKING SO I
;  CAN USE WIFI OR ETHERNET, EITHER ONE TO TALK TO THE CONSOLE", and "no
;  I'm not internet sharing over that ethernet. and I dont want static ip
;  either, solve it another way."
;
;  The cable runs straight from this board into a laptop. There is no
;  DHCP server on it - the board asked four times over twelve seconds and
;  nothing answered, because there was nothing there to answer - and the
;  laptop, which had asked the same question and got the same silence,
;  had already given ITSELF a link-local address and carried on as though
;  nothing had happened. That is not a trick and it is not Windows being
;  odd; it is RFC 3927, and every operating system on that cable already
;  does it.
;
;  SO THE BOARD DOES IT TOO. Then the two ends of the cable are on one
;  segment, both self-assigned, and NOTHING ON THE LAPTOP HAS TO CHANGE:
;  no address typed, no connection sharing, no firewall rule, no service
;  left running. That was the requirement, in those words.
;
;  WHAT IS HERE AND WHAT IS NOT
;  ----------------------------------------------------------------------
;  Here: the machine - pick a candidate, wait, probe it three times,
;  wait, take it, announce it twice, hand it to the one path every
;  address takes. This needs a LINK to send on and a CLOCK to wait
;  against, which is why it is not in RaspberryPi4/Lib/net.pi4, exactly
;  as the DHCP exchange is in net_cmd.pbi and not in dhcp.pi4.
;
;  In net.pi4: the two packet forms (NetArpProbe, NetArpAnnounce), the
;  conflict test that has to sit inside the ARP receive path
;  (net_LlSeeArp), the address picker seeded from the MAC, and every one
;  of the RFC's numbers with its section beside it.
;
;  IT IS NOT A SECOND WAY TO HAVE AN ADDRESS
;  ----------------------------------------------------------------------
;  It ends in NetAddressBound, which is the tail a DHCP lease runs and
;  the tail a stored address runs: record the three numbers, tell the
;  board, arm the console. There is no fourth path and no second copy of
;  the arming rule, because
;  Memories\the-console-is-networking-not-a-driver-feature is exactly
;  about what happens when there is one.
;
;  EVERY WAIT IS BOUNDED AND THE ARITHMETIC IS ON THE SCREEN
;  ----------------------------------------------------------------------
;  House rule: nothing in a boot path may be able to strand the board.
;  Per candidate, using the RFC's own intervals (s2.2.1):
;
;    PROBE_WAIT           0 .. 1 s   random, before the first probe
;    2 probe gaps         1 .. 2 s   each, random
;    ANNOUNCE_WAIT            2 s    after the last probe
;    1 announce gap           2 s
;                         ----------
;    worst case               9 s    to take an address
;    a conflict is normally seen inside the probe phase, so a candidate
;    that is already taken costs at most 5 s before the next one.
;
;  #NETLL_CANDIDATES is 3, so the worst case for the whole procedure is
;  5 + 5 + 9 = 19 seconds, and the ordinary case - an empty segment, one
;  candidate, no objection - is 9. THE RFC'S MAX_CONFLICTS IS 10 AND
;  THIS IS NOT 10 ON PURPOSE: ten failures would be ninety seconds of a
;  board that looks hung during a boot, and on a two-host cable the
;  probability of three separate collisions out of 65,024 addresses is
;  not a number worth spending ninety seconds on. A board on a segment
;  busy enough to need ten tries has a DHCP server on it.
;
;  It says what it is about to wait for before it waits, because a boot
;  that pauses is indistinguishable from a hung one unless the
;  arithmetic is on the screen.
; ======================================================================

; How many candidates before giving up. See the arithmetic above; this
; is a bench decision and not the RFC's MAX_CONFLICTS, and the two are
; different numbers for the reason written there.
#NETLL_CANDIDATES = 3

; The receive slice while waiting. Long enough to take a whole frame off
; a gigabit MAC many times over, short enough that a conflict is noticed
; inside the interval it arrived in. #NET_SLICE_MS in net_cmd.pbi is the
; same idea and the same number, and it is not reachable from here - this
; file has to be included before eth.pi4 and net_cmd.pbi comes after it.
#NETLL_SLICE_MS = 50

; ----------------------------------------------------------------------
;  netll_Watch - pump the link for `ms`, watching for a conflict.
;
;    1  a conflict was seen - the caller must abandon the candidate
;    0  the time passed quietly
;   -1  the operator pressed a key
;
;  IT PUMPS RATHER THAN SLEEPS, and that is the point of it: the ARP
;  frame that says "I already have that address" is only seen if
;  somebody is reading frames. A wait implemented as a delay would make
;  every probe come back clean on a segment where the address was taken.
;
;  A DEFENSIVE ANNOUNCEMENT STAGED BY net_LlSeeArp GOES OUT FROM HERE
;  without this procedure knowing what it is: LinkPumpNet sends whatever
;  NetInput staged, which is the same door an ARP reply and an ICMP echo
;  reply leave by.
; ----------------------------------------------------------------------
; Six bytes as aa:bb:cc:dd:ee:ff, from a pointer. PutLinkMac in
; net_cmd.pbi does the same for the link in use, and that file comes
; AFTER this one - so this is four lines rather than an include-order
; rearrangement of two working files.
Procedure netll_PutMac(p.i)
  Define i.i
  If p = 0
    UartWriteStr("unknown")
    ProcedureReturn
  EndIf
  For i = 0 To 5
    PutHex2(PeekA(p + i) & $FF)
    If i < 5
      UartWrite(58)                      ; 58 is a colon
    EndIf
  Next
EndProcedure

Procedure.i netll_Watch(ms.i)
  Define deadline.i
  deadline = millis() + ms
  While (millis() - deadline) < 0
    If OutBreak() <> 0
      ProcedureReturn -1
    EndIf
    LinkPumpNet(#NETLL_SLICE_MS)
    ; LinkPumpNet has completed its receive transaction. Service only at this
    ; boundary; never render while the link backend owns a frame pointer.
    netwait_Progress()
    If NetLlConflict() <> 0
      ProcedureReturn 1
    EndIf
  Wend
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  netll_TryOne - the RFC's sequence for ONE candidate address.
;
;     1  it is ours: probed, unclaimed by anyone else, announced
;     0  somebody objected - try another address
;    -1  the operator pressed a key
;    -2  a frame would not go out at all, which is a link fault and not
;        a conflict; trying another address cannot help
;
;  THE PROBES CARRY A ZERO SENDER ADDRESS so that asking does not itself
;  claim the address in every ARP cache on the segment - see NetArpProbe.
;  The ANNOUNCEMENTS carry it in both fields, which is what tells the
;  segment to update. Between the two the watcher's mode changes from
;  PROBING to CLAIMED, which is what changes the meaning of a conflicting
;  frame from "give this address up" to "defend it once".
; ----------------------------------------------------------------------
Procedure.i netll_TryOne(kind.i, cand.i)
  Define i.i
  Define r.i

  NetLlWatch(kind, cand, #NET_LL_PROBING)

  ; [s2.2.1] "wait for a random time interval selected uniformly in the
  ; range zero to PROBE_WAIT seconds" - so that a rack of boards powered
  ; up together do not all probe in the same millisecond.
  r = netll_Watch(NetLlRandMs(0, #NET_LL_PROBE_WAIT_MS))
  If r <> 0
    ProcedureReturn r
  EndIf

  i = 0
  While i < #NET_LL_PROBE_NUM
    If NetArpProbe(kind, cand) = 0
      ProcedureReturn -2
    EndIf
    If LinkTxStaged() <> 1
      ProcedureReturn -2
    EndIf
    i = i + 1
    If i < #NET_LL_PROBE_NUM
      r = netll_Watch(NetLlRandMs(#NET_LL_PROBE_MIN_MS, #NET_LL_PROBE_MAX_MS))
    Else
      ; [s2.2.1] ANNOUNCE_WAIT after the LAST probe, before the address
      ; may be used. This is the window a slow host's reply arrives in.
      r = netll_Watch(#NET_LL_ANNOUNCE_WAIT_MS)
    EndIf
    If r <> 0
      ProcedureReturn r
    EndIf
  Wend

  ; Nobody objected in any of the four windows. It is ours from here,
  ; and from here a conflicting frame is defended against rather than
  ; fled from. The defence clock starts empty so that the ten-second
  ; window belongs to THIS address.
  NetLlWatch(kind, cand, #NET_LL_CLAIMED)
  NetLlDefendReset()

  i = 0
  While i < #NET_LL_ANNOUNCE_NUM
    If NetArpAnnounce(kind, cand) = 0
      ProcedureReturn -2
    EndIf
    If LinkTxStaged() <> 1
      ProcedureReturn -2
    EndIf
    i = i + 1
    If i < #NET_LL_ANNOUNCE_NUM
      r = netll_Watch(#NET_LL_ANNOUNCE_INTERVAL_MS)
      If r = -1
        ProcedureReturn -1
      EndIf
    EndIf
  Wend

  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  netll_Unpin - GIVE THE LINK BACK TO THE POLICY LAYER.
;
;  MEASURED ON THE BOARD, 2026-09-07, and it is the fault this procedure
;  exists to close. LinkUseKind is the ONE-LINK BOARD's version of
;  LinkSelect: it names a kind directly and records the reason
;  #LINK_WHY_ONLY_ONE, "this board has exactly one link and it is it".
;  On a board with two interfaces that reason is FALSE, and worse, the
;  override outlives the procedure that set it.
;
;  The machine below has to name its link - a probe for the radio must
;  not leave by the Ethernet socket - so it uses LinkUseKind for the
;  duration of the probes and that much is right. What was wrong was
;  putting the OLD kind back the same way afterwards: `LinkUseKind(prev)`
;  re-applies the one-link override rather than undoing it, and the board
;  was found afterwards reporting "traffic goes out over the wired
;  Ethernet ... this board has exactly one interface Anvil can reach" at
;  1000 Mbit/s while the one IP layer held the RADIO's address. That is
;  the exact MAC-and-address mismatch HwLinkOpen's header says must be
;  impossible.
;
;  LinkForget() records NOTHING instead - no kind, no reason - so the
;  next thing to want an interface asks HwLinkOpen and gets an answer
;  derived from live facts: the cable, the PHY's link bit, both
;  addresses, the operator's pin. A stale answer is worse than no answer,
;  because only one of the two announces itself.
; ----------------------------------------------------------------------
Procedure netll_Unpin()
  LinkForget()
EndProcedure

; ----------------------------------------------------------------------
;  NetLinkLocalAcquire - take a link-local address on `kind`, and arm
;  everything that hangs off holding one. Returns the address, or 0.
;
;  IT NAMES THE LINK RATHER THAN LETTING THE PREFERENCE ORDER CHOOSE,
;  and that is not a shortcut - it is a correctness requirement. This is
;  called twice at boot: once for the cable and once for the radio. By
;  the time the radio's turn comes the wired side may already be holding
;  a link-local address of its own, and the ordinary preference order
;  prefers the wire - so an unpinned acquisition for the radio would
;  send its probes out of the Ethernet socket, claim an address there,
;  and announce it with the wrong hardware address. Naming the kind is
;  the only way to ask the question "is this address free ON THIS LINK",
;  which is the only question RFC 3927 is about.
;
;  THE MAC MUST BE THE ONE THE FRAMES WILL LEAVE WITH. A probe answered
;  by nobody because the reply went to a hardware address on the other
;  interface is a probe that always says "free" - and two boards would
;  then take the same address and both be certain. LinkMacPtr() is the
;  seam's answer for the link now selected, and NetSetMac makes the IP
;  layer agree with it before a single frame is built.
;
;  IT REFUSES RATHER THAN GUESSES when the link has no hardware address
;  yet (nothing has chosen an interface, so the backend's pointer is
;  still zero). A made-up MAC here would be a board announcing an
;  address under an identity no switch will forward to.
; ----------------------------------------------------------------------
Procedure.i NetLinkLocalAcquire(kind.i)
  Define cand.i
  Define tries.i
  Define r.i
  Define mac.i

  If kind = #HW_LINK_NONE
    ProcedureReturn 0
  EndIf

  If LinkUseKind(kind) <> kind
    PrintN("!! this board has no such link, so no link-local address was asked")
    PrintN("   for and nothing was changed.")
    netll_Unpin()
    ProcedureReturn 0
  EndIf

  mac = LinkMacPtr()
  If mac = 0
    PrintN("!! this link has no hardware address yet, so a link-local address")
    PrintN("   could not be asked for - an ARP probe has to be sent FROM")
    PrintN("   somewhere. Nothing was changed.")
    netll_Unpin()
    ProcedureReturn 0
  EndIf
  If NetSetMac(kind, mac) = 0
    PrintN("!! the network stack refused this link's hardware address, so no")
    PrintN("   link-local address was asked for and nothing was changed.")
    netll_Unpin()
    ProcedureReturn 0
  EndIf

  ; SEEDED FROM THAT SAME HARDWARE ADDRESS, so this board comes back to
  ; the same 169.254.x.y after every reset all evening - which is what
  ; makes "the console is at the address it was at before the flash"
  ; true. [RFC 3927 s2.1]
  NetLlSeedFromMac(kind)

  PrintN("No DHCP server answered on this link, so this board is picking an")
  PrintN("address for itself out of 169.254.0.0/16 and asking the segment")
  PrintN("whether anyone already has it (RFC 3927). Three ARP probes, then")
  PrintN("two announcements - about nine seconds if nobody objects, and at")
  PrintN("most nineteen if the first two addresses are taken. Press a key to")
  PrintN("stop.")
  UartDrain()

  tries = 0
  While tries < #NETLL_CANDIDATES
    tries = tries + 1
    cand = NetLlPick()
    ; THE PICKER IS SELECTABLE BY CONSTRUCTION AND THIS ASKS ANYWAY.
    ; [RFC 3927 s2.1] reserves the first and last 256 addresses of the
    ; block, and the arithmetic that keeps a candidate out of them is
    ; two constants wide - so an edit to either one, made for a good
    ; reason by somebody who did not know about the reservation, would
    ; put this board on 169.254.0.x with nothing anywhere complaining.
    ; A refusal here costs one compare and names the actual fault.
    If NetLlSelectable(cand) = 0
      Print("!! the address picker produced ")
      PutIp(cand)
      PrintN(", which is outside the range")
      PrintN("   RFC 3927 allows a host to select - the first and last 256")
      PrintN("   addresses of 169.254.0.0/16 are reserved. That is a fault in")
      PrintN("   this monitor and not in the network. Nothing was changed.")
      NetLlWatch(0, 0, #NET_LL_OFF)
      netll_Unpin()
      ProcedureReturn 0
    EndIf
    Print("  trying ")
    PutIp(cand)
    PrintN(" ...")
    UartDrain()

    r = netll_TryOne(kind, cand)

    If r = 1
      Break
    EndIf
    If r = -1
      PrintN("  stopped, so this board has no link-local address. Nothing was")
      PrintN("  changed and nothing was left half-configured.")
      NetLlWatch(0, 0, #NET_LL_OFF)
      netll_Unpin()
      ProcedureReturn 0
    EndIf
    If r = -2
      PrintN("!! an ARP probe would not go out over this link at all, so no")
      PrintN("   link-local address could be taken. That is the link and not the")
      PrintN("   address - another one would fail the same way. Nothing changed.")
      LinkWhySay()
      NetLlWatch(0, 0, #NET_LL_OFF)
      netll_Unpin()
      ProcedureReturn 0
    EndIf
    Print("  ")
    PutIp(cand)
    PrintN(" is already in use on this segment, so it was not taken.")
  Wend

  If r <> 1
    Print("!! ")
    PrintDec(#NETLL_CANDIDATES)
    PrintN(" addresses were tried and every one of them is already in use on")
    PrintN("   this segment, so this board has no link-local address. Nothing")
    PrintN("   was changed. A segment this crowded has a DHCP server on it -")
    PrintN("   type dhcp.")
    NetLlWatch(0, 0, #NET_LL_OFF)
    netll_Unpin()
    ProcedureReturn 0
  EndIf

  ; ---- it is ours. Put it on the stack and take the one tail. --------
  If NetSetIPv4(kind, cand, #NET_LL_MASK, 0) = 0
    PrintN("!! the network stack refused the link-local address, which cannot")
    PrintN("   happen unless the range constants have been edited - 169.254.x.y")
    PrintN("   with a /16 mask and no gateway is exactly what it is written to")
    PrintN("   accept. Nothing was changed.")
    EthWhyNet()
    NetLlWatch(0, 0, #NET_LL_OFF)
    netll_Unpin()
    ProcedureReturn 0
  EndIf

  ; THE BOARD'S RECORD OF IT, and it goes in memory only - never into
  ; the settings store. See gEthLlIp in
  ; RaspberryPi4/Board/eth_globals.pi4 for why writing it to SETTINGS.TXT
  ; would be a collision waiting to happen at the next boot.
  If kind = #HW_LINK_WIRED
    gEthLlIp = cand
  EndIf

  ; THE TAIL EVERY ADDRESS TAKES. Record, tell the board, arm the
  ; console - the same three acts a lease runs and a stored address
  ; runs, out of the one copy of them.
  NetAddressBound(kind, cand, #NET_LL_MASK, 0, #NET_ADDR_LINKLOCAL)

  ; ------------------------------------------------------------------
  ; AND HAND THE LINK BACK TO THE POLICY LAYER ON THE WAY OUT. The pin
  ; above was for the PROBES - they had to leave by a named interface -
  ; and it is not a decision about which link should carry traffic. That
  ; decision is HwLinkOpen's, it is re-derived from live facts, and it is
  ; the only thing that pairs the right hardware address with the right
  ; IPv4 address. Leaving the override in place produced a board
  ; reporting the wired link at 1000 Mbit/s while the stack held the
  ; radio's address - see netll_Unpin.
  ;
  ; It re-selects what was just bound in the ordinary case, so this is
  ; not a second policy; it is the first one being allowed to run. The
  ; console is armed again afterwards because the arming NetAddressBound
  ; did was against the state before this call.
  ; ------------------------------------------------------------------
  HwLinkOpen(1)
  NetConsoleRearm()

  ; The watcher stays in CLAIMED mode from here, for as long as the
  ; board holds this address: that is what defends it.
  ProcedureReturn cand
EndProcedure

; ----------------------------------------------------------------------
;  NetLinkLocalTick - the surrender, and the recovery from it.
;
;  [RFC 3927 s2.5] A host that sees a second conflicting ARP inside
;  DEFEND_INTERVAL "MUST immediately cease using the address". net.pi4
;  has already decided that - it declined to send a second defence and
;  raised NetLlGiveUp() - and this is where the monitor acts on it,
;  because ceasing to use an address means undoing four things that are
;  not net.pi4's: the board's record of it, the IP layer, the console
;  bound to it, and the sentence `net` prints.
;
;  IT RUNS FROM THE PROMPT'S SPIN, through the pointer registered below,
;  and that is the whole reason a pointer is involved: the spin lives in
;  Anvil/Core/parse.pi4, which has to be included BEFORE the settings
;  store and this file, because those two use its parser. The same
;  include-order fact produced HwLinkSetWiredMacPtr in
;  RaspberryPi4/Board/hw_link.pi4, and it is solved the same way rather
;  than by a second home for the knowledge.
;
;  IT COSTS ONE LOAD AND A COMPARE on every spin in which nothing has
;  gone wrong, which is every spin.
;
;  IT TAKES A NEW ADDRESS RATHER THAN LEAVING THE BOARD DEAF. Ceasing is
;  the RFC's requirement; stopping there would leave a board that had
;  been reachable a second ago with no console and no way to be told to
;  get one. So it re-runs the machine - which is bounded at nineteen
;  seconds and says what it is doing - and the odds of losing the second
;  address as well are 65,024 to one against.
; ----------------------------------------------------------------------
Procedure NetLinkLocalTick()
  Define kind.i
  If NetLlGiveUp() = 0
    ProcedureReturn
  EndIf
  ; The link the address was taken on. LinkKind() is what the console is
  ; riding, which is that link by construction - it is the link holding
  ; the address, and holding it is what armed the console.
  kind = LinkKind()

  PrintNl()
  Print("!! another machine on this segment claimed ")
  PutIp(NetLlAddr())
  PrintN(" twice inside ten")
  PrintN("   seconds, so this board has GIVEN THAT ADDRESS UP - RFC 3927 says a")
  PrintN("   second conflict inside DEFEND_INTERVAL must end in the address")
  PrintN("   being surrendered, not defended again. It was defended once. The")
  Print("   other machine's hardware address was ")
  netll_PutMac(NetLlConflictMacPtr())
  PrintN(".")

  ; Cease. The console goes with it - it is bound to this address and
  ; answering on an address somebody else is using is worse than being
  ; silent.
  NetLlWatch(0, 0, #NET_LL_OFF)
  NetLlDefendReset()
  gEthLlIp = 0
  gEthAddrFrom = #NET_ADDR_NONE

  PrintN("   Taking another address now.")
  If NetLinkLocalAcquire(kind) = 0
    PrintN("!! and no replacement could be taken, so this board has no address on")
    PrintN("   that link and its network console is not listening. The serial")
    PrintN("   console still works. Type dhcp, or net address, to fix it.")
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  The registration itself is ONE LINE IN BootBringUp()
;  (RaspberryPi4/Board/boot.pi4), and it is there rather than at this
;  file's scope for two reasons. A procedure's address cannot be taken
;  before the procedure exists, and NetLinkLocalTick calls
;  NetLinkLocalAcquire above it - so whichever of the two came first,
;  the other could not name it from this file's top level. And the boot
;  is where every other "the monitor is now running, wire it up" act
;  already happens, which is the place somebody looks.
; ----------------------------------------------------------------------
