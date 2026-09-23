; ======================================================================
;  THE NETWORK WAIT LEDGER - WHERE THE BOOT'S NETWORK HALF SPENDS ITS
;  TIME, COUNTED ON THE BOARD'S OWN CLOCK.
; ----------------------------------------------------------------------
;  WHY IT EXISTS, AND IT IS ONE MEASUREMENT.  On 2026-09-18 this board's
;  own retained boot record said the whole boot took 43,456 ms and that
;  16,782 -> 43,390 ms of it - TWENTY-SIX AND A HALF SECONDS, sixty-one
;  per cent of the boot - was the network coming up. That record has two
;  rows for the network half, "network started" and "network done", so it
;  can say how much and it cannot say where. Nothing else could either:
;
;    THE BOOT TRAIL CANNOT.  It is a ring of 64 entries and a boot writes
;    161 of them, so the early part of a boot is overwritten by the late
;    part of the same boot. Every entry a reader finds afterwards lies in
;    the last few hundred milliseconds.
;
;    A HOST STOPWATCH CANNOT.  Every network figure this monitor has been
;    credited with was timed by a machine waiting on the console, and
;    that wait carries the console's own round trip - measured at 0.42 s
;    with one client on this bench. A wait of 0.4 s and a wait of 0.8 s
;    are then the same reading.
;
;    AND A TIMELINE WOULD NOT ANSWER IT EITHER.  "Three seconds passed
;    between these two lines" does not say whether one wait cost three
;    seconds or six waits cost half a second each, and those are
;    different faults with different fixes.
;
;  SO: ONE FIXED ROW PER WAIT SITE. Visits, total, worst single visit,
;  and when the site was first reached and last left. A fixed set of rows
;  CANNOT WRAP, which is the whole property the ring does not have. This
;  is the same instrument the USB stack keeps and prints as `usb timing`,
;  in the same shape and for the same reason, because two instruments
;  that answer the same question in two shapes are two things to learn.
;
; ----------------------------------------------------------------------
;  WHY IT IS HERE AND NOT IN A BOARD FILE
; ----------------------------------------------------------------------
;  Every row below names a NETWORK EVENT, not a part: "wired link and
;  auto-negotiation" is what a PHY finishing negotiation is on any board
;  with a wire, and "radio firmware upload" is what pushing a blob into a
;  wireless part is on any board with a radio. None of it is a register
;  of one chip, so by the rule that every library exists once it belongs
;  in the shared tree and the boards fill it.
;
;  THE DIRECTION OF THE CALL IS THE WHOLE POINT. This file names NOTHING
;  below it - no controller, no radio, no bus. The board's drivers call
;  UP into these two procedures, which is the direction that has always
;  been legal and is the direction the layering gate is built to keep.
;  A ledger that lived in a driver and was read back through a seam would
;  have needed a new seam per board; this needs none, and the command
;  that prints it reads rows it is handed and learns nothing about any
;  part.
;
;  ITS ONLY DEPENDENCE IS THE CLOCK - Ticks() and TickHz(), which are
;  declared seams every board answers, and which this bench proved honest
;  to about one part in ten thousand on 2026-09-18 (a fitted 0.99989 x N
;  over seven `sleep N` points). A ledger on a lying clock is worse than
;  no ledger, so that proof is named here rather than assumed.
;
; ----------------------------------------------------------------------
;  MICROSECONDS, NOT MILLISECONDS, IN THE STORE
; ----------------------------------------------------------------------
;  The rows this instrument was built to read are seconds long. The rows
;  BESIDE them - a register poll, a cable check - are tens of
;  microseconds, and a millisecond store rounds every one of those to
;  zero. A zero reads as "this costs nothing"; it has to read as what it
;  is. The printing side puts both in one column so they can be compared
;  by eye.
;
;  A ROW IS NEVER NESTED INSIDE ANOTHER ROW, deliberately, so that the
;  totals may be added up. The radio's bring-up is four rows that do not
;  overlap - the blobs, the bus, the upload, the configuration - and not
;  one enclosing row with three inside it, because a grand total that
;  counts the same second twice is a grand total nobody can use.
; ======================================================================

; ---- the sites. THESE ARE READ BACK BY A COMMAND AND BY A GATE, so add
; at the end and never renumber. Each is a place the network bring-up
; STOPS AND WAITS, named for what is being waited for and not for what is
; doing the waiting.
#NETW_CABLE       = 0    ; is there a cable in the socket at all
#NETW_LINK        = 1    ; the wire's link and auto-negotiation
#NETW_DHCP_WIRED  = 2    ; asking the wire for an address
#NETW_LL_WIRED    = 3    ; proving a self-chosen address free on the wire
#NETW_SERVE       = 4    ; taking the address-server role on the wire
#NETW_RADIO_BLOBS = 5    ; the radio's three files, off the boot medium
#NETW_RADIO_BUS   = 6    ; the radio's power line, its bus and its attach
#NETW_RADIO_FW    = 7    ; pushing the firmware and the country blob in
#NETW_RADIO_CFG   = 8    ; what is told to the firmware after it booted
#NETW_SCAN        = 9    ; listening for the networks on the air
#NETW_JOIN        = 10   ; associating and completing the key exchange
#NETW_DHCP_WIFI   = 11   ; asking the radio's network for an address
#NETW_LL_WIFI     = 12   ; proving a self-chosen address free on the air
#NETW_NTP_NAME    = 13   ; looking the time server's name up
#NETW_NTP_REPLY   = 14   ; waiting for the time server to answer
; Typed, not computed. A constant in this compiler takes no arithmetic in
; its initialiser, so this is one more than the last id above and the
; gate checks that it is.
#NETW_N           = 15

Global Dim netw_visits.i[#NETW_N]   ; how many times the site was waited at
Global Dim netw_ticks.i[#NETW_N]    ; ticks spent there, summed
Global Dim netw_worst.i[#NETW_N]    ; the worst single visit, in ticks
Global Dim netw_first.i[#NETW_N]    ; the tick the first visit STARTED at
Global Dim netw_last.i[#NETW_N]     ; the tick the last visit ENDED at

; The tick the ledger's very first visit started at. Every FIRST and LAST
; this file reports is relative to it, so a row's place in the bring-up
; is as readable as its cost: two rows with the same total mean very
; different things depending on whether they overlap.
Global netw_origin.i = 0

; Bytes the radio's firmware upload moved, so the board can state that
; path's throughput with no host stopwatch in it. It is the one row whose
; cost is a transfer rather than a timeout, and a rate is the only way to
; tell a slow bus from a big file.
Global netw_fwBytes.i = 0

; ----------------------------------------------------------------------
;  NetWaitMark - the stamp a wait site takes BEFORE it waits.
;
;  It is a name of its own rather than Ticks() at the call site, and that
;  is not decoration: it means a search for this name finds every
;  accounted wait in the tree, and a wait that is not accounted for
;  stands out by not having one.
; ----------------------------------------------------------------------
Procedure.i NetWaitMark()
  ProcedureReturn Ticks()
EndProcedure

; ----------------------------------------------------------------------
;  NetWaitAccount - record one visit. t0 is what NetWaitMark() answered.
;
;  IT IS CALLED ON THE FAILING PATH TOO, and that is the half that
;  matters here. The waits this ledger was built to find are the ones
;  that ran to their full timeout because nothing was there to answer -
;  a site accounted only when it succeeds reports a network that is
;  always fast and a boot that is always slow.
; ----------------------------------------------------------------------
Procedure NetWaitAccount(site.i, t0.i)
  Define now.i
  Define d.i
  If site < 0 Or site >= #NETW_N
    ProcedureReturn
  EndIf
  now = Ticks()
  d = now - t0
  ; A COUNTER THAT WENT BACKWARDS IS NOT A NEGATIVE DURATION. The
  ; architectural counter does not wrap in any lifetime this board has,
  ; so a negative here can only be a mis-taken stamp. It is counted as a
  ; visit of no length rather than subtracted, because a total that can
  ; go DOWN is a total nobody can read.
  If d < 0
    d = 0
  EndIf
  If netw_origin = 0
    netw_origin = t0
  EndIf
  If netw_visits[site] = 0
    netw_first[site] = t0
  EndIf
  netw_visits[site] = netw_visits[site] + 1
  netw_ticks[site] = netw_ticks[site] + d
  netw_last[site] = now
  If d > netw_worst[site]
    netw_worst[site] = d
  EndIf
EndProcedure

; Bytes the firmware-upload row moved. Added where that upload is
; accounted, by the board that knows how big its own blob is.
Procedure NetWaitAccountFwBytes(n.i)
  If n > 0
    netw_fwBytes = netw_fwBytes + n
  EndIf
EndProcedure

; ---- reading it back --------------------------------------------------

Procedure.i NetWaitSites()
  ProcedureReturn #NETW_N
EndProcedure

Procedure.i NetWaitVisits(i.i)
  If i < 0 Or i >= #NETW_N : ProcedureReturn 0 : EndIf
  ProcedureReturn netw_visits[i]
EndProcedure

; Ticks to microseconds. The divide is by hz/1000000 rather than a
; multiply-then-divide, because a twenty-six second wait multiplied by a
; million is a number this board's integers would lose.
Procedure.i netw_UsOf(ticks.i)
  Define hz.i
  hz = TickHz()
  If hz < 1000000
    ProcedureReturn 0
  EndIf
  ProcedureReturn ticks / (hz / 1000000)
EndProcedure

Procedure.i NetWaitTotalUs(i.i)
  If i < 0 Or i >= #NETW_N : ProcedureReturn 0 : EndIf
  ProcedureReturn netw_UsOf(netw_ticks[i])
EndProcedure

Procedure.i NetWaitWorstUs(i.i)
  If i < 0 Or i >= #NETW_N : ProcedureReturn 0 : EndIf
  ProcedureReturn netw_UsOf(netw_worst[i])
EndProcedure

; When the site was FIRST REACHED and LAST LEFT, in microseconds since
; the ledger's own origin. A site that was never reached answers zero for
; both, and its visit count is what says so - see the printer, which
; prints no row at all for it.
Procedure.i NetWaitFirstUs(i.i)
  If i < 0 Or i >= #NETW_N : ProcedureReturn 0 : EndIf
  If netw_visits[i] = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn netw_UsOf(netw_first[i] - netw_origin)
EndProcedure

Procedure.i NetWaitLastUs(i.i)
  If i < 0 Or i >= #NETW_N : ProcedureReturn 0 : EndIf
  If netw_visits[i] = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn netw_UsOf(netw_last[i] - netw_origin)
EndProcedure

Procedure.i NetWaitFwBytes()
  ProcedureReturn netw_fwBytes
EndProcedure

; The site's name, in the words the boot log already uses for it, so a
; row of this table and the sentence the bring-up printed read as the
; same thing rather than as two.
;
; NOT ONE PART IS NAMED HERE. "the radio", "the wire" - a board with a
; different controller and a different radio prints these same rows, and
; a row that named a part would be wrong on the next board and would have
; to be duplicated to be right, which is the defect this whole file is
; positioned to avoid.
Procedure.i NetWaitName(i.i)
  Select i
    Case #NETW_CABLE       : ProcedureReturn "is a cable in the socket"
    Case #NETW_LINK        : ProcedureReturn "wired link and auto-negotiation"
    Case #NETW_DHCP_WIRED  : ProcedureReturn "wired: waiting for an address server"
    Case #NETW_LL_WIRED    : ProcedureReturn "wired: proving a self-chosen address free"
    Case #NETW_SERVE       : ProcedureReturn "wired: taking the address-server role"
    Case #NETW_RADIO_BLOBS : ProcedureReturn "radio: its three files off the boot medium"
    Case #NETW_RADIO_BUS   : ProcedureReturn "radio: power, bus and attach"
    Case #NETW_RADIO_FW    : ProcedureReturn "radio: firmware and country blob uploaded"
    Case #NETW_RADIO_CFG   : ProcedureReturn "radio: configured after its firmware booted"
    Case #NETW_SCAN        : ProcedureReturn "radio: listening for networks on the air"
    Case #NETW_JOIN        : ProcedureReturn "radio: associating and exchanging keys"
    Case #NETW_DHCP_WIFI   : ProcedureReturn "radio: waiting for an address server"
    Case #NETW_LL_WIFI     : ProcedureReturn "radio: proving a self-chosen address free"
    Case #NETW_NTP_NAME    : ProcedureReturn "time: looking the server's name up"
    Case #NETW_NTP_REPLY   : ProcedureReturn "time: waiting for the server to answer"
  EndSelect
  ProcedureReturn "a wait this build does not name"
EndProcedure

; ----------------------------------------------------------------------
;  NetWaitLedgerReset - zero every row.
;
;  For measuring ONE act - reset, type dhcp, read the table - instead of
;  the whole life of the board. The boot's own figures are gone when this
;  is used and only a restart brings them back, which the command says
;  out loud before anybody loses a boot they wanted.
; ----------------------------------------------------------------------
Procedure NetWaitLedgerReset()
  Define i.i
  i = 0
  While i < #NETW_N
    netw_visits[i] = 0
    netw_ticks[i] = 0
    netw_worst[i] = 0
    netw_first[i] = 0
    netw_last[i] = 0
    i = i + 1
  Wend
  netw_origin = 0
  netw_fwBytes = 0
EndProcedure
