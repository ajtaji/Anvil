#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/tcp.pi4 - the TCP state machine.

There is no Pi 4 here, no network and no link driver.  None of the three
is needed, and that is a property of the library rather than a shortcut
taken by the gate.  tcp.pi4's own header names the entire contract it has
with the wire:

    HwLinkReady(kind)   LinkTxMaxOn(kind)   LinkTxStagedOn(kind)   LinkPumpAllNet(ms)

Four names.  This gate defines all four itself and does NOT include
link.pi4, so the whole state machine is driven with byte-exact Ethernet
frames and graded on byte-exact Ethernet frames, with no device model at
all.  #LINK_RX_NONE lives in link.pi4, so the gate reads its value out of
that file and writes it into the harness, which is the one place a
constant is repeated rather than included.

WHAT IS PROVEN

  1. THE THREE-WAY HANDSHAKE.  TcpConnect's SYN is compared octet for
     octet - ports, data offset 6, the MSS option Kind 2 Len 4 value
     1460 big-endian, the advertised window, the empty acknowledgment
     field - and so is the bare ACK that answers a SYN-ACK.  The ISN and
     the ephemeral port cannot be predicted from outside, so they are
     READ OUT of the SYN the library produced and substituted into every
     later expectation, exactly the way a64_net_check.py handles the IPv4
     Identification field.
  2. A DATA EXCHANGE.  Twenty bytes out, the segment graded byte for
     byte; an ACK in, and SND.UNA proven to have moved by the sequence
     number of the NEXT segment; a data segment in, the acknowledgment
     it produces graded byte for byte (including the advertised window
     shrinking by exactly the buffered bytes) and TcpRead required to
     return the exact octets.
  3. A RETRANSMISSION.  Data is sent and never acknowledged, the clock
     is moved past #TCP_RTO_INIT_MS, and TcpPoll is called with no frame
     waiting.  The SAME twenty octets must go out again AT THE SAME
     SEQUENCE NUMBER, tcp_retrans must move 0 -> 1, and tcp_rto must
     have doubled 1000 -> 2000.  KARN'S ALGORITHM is then proven by
     acknowledging that retransmission after another 500 ms and
     requiring tcp_rto to be UNCHANGED: a stack that sampled the
     ambiguous acknowledgment would recompute the RTO and land on 1801.
  4. RESETS, BOTH DIRECTIONS.
     (a) A RST on an established connection: CLOSED, TcpWasReset() 1,
         TcpError() -304, and NO FRAME AT ALL - a RST is never answered
         with a RST.
     (b) A SYN for a port nobody has open: RST,ACK with SEQ=0 and
         ACK=SEG.SEQ+1, graded byte for byte, AND the live connection on
         the socket that happened to be current is UNDISTURBED - its
         state, its peer address, its ports, its hardware address and
         its RCV.NXT are all re-read afterwards through the next segment
         it sends.  That is TcpSendRstFor's save/restore, and it is the
         case most worth having: the current socket during TcpInput's
         no-match path is always socket #TCP_SOCKETS-1, so the live
         connection is deliberately parked THERE.
  5. A FIN CLOSE, ALL THE WAY TO CLOSED.  FIN,ACK out; the ACK in ->
     FIN-WAIT-2; the peer's FIN in -> our ACK out and TIME-WAIT; then
     2*MSL of emulated time and CLOSED.  The full four minutes PASS ON
     THE COUNTER, by a warp rather than by execution - see THE CLOCK
     below for how, and for what that costs in honesty.
  6. THE WIDTH RULE.  Ten pairs through TcpSeqLt / Gt / Le across the
     32-bit wrap, including the pair tcp.pi4's own header cites:
     TcpSeqLt($7FFFFFFF, $FFFFFFFF) must be 1 and TcpSeqGt must be 0,
     where a naive 64-bit subtraction gives exactly the opposite answer.
     This single case is why every sequence variable in that file is
     declared `.l`.
  7. THE SOCKET TABLE.  Two connections opened, driven alternately, and
     required never to see each other's bytes, ports or sequence
     numbers.  This is the only real check the park/unpark field list
     has.
  8. THE LINK CEILING.  LinkTxMaxOn() set to 1136 - the radio's number -
     and a 3000-byte send required to leave in segments of 1082 data
     octets, in frames of exactly 1136 octets, and not 1460.  The MSS
     WE ADVERTISE stays 1460 in the same run, because that is our
     receive capability and has nothing to do with the send ceiling;
     getting those two the same way round is the classic MSS bug.
     This connection is on #HW_LINK_WIFI, not the cable: the radio's
     row holds a MAC of its own, the fixture link delivers the replies
     as the radio, and every frame out must carry the radio's source
     address.
  9. A PASSIVE OPEN.  TcpListen, a SYN in, the SYN-ACK graded byte for
     byte, the ACK in, ESTABLISHED, then TcpAbort's RST and the listener
     re-arming itself.
 10. BOUNDED OUT-OF-ORDER REASSEMBLY.  A segment ahead of RCV.NXT with a
     gap is queued and duplicate-ACKed; the segment that fills the gap
     delivers both, in order, in one step.
 11. THE ACCEPTABILITY EDGE, FROM BOTH SIDES.  One octet at
     RCV.NXT+RCV.WND-1 is accepted; one octet at RCV.NXT+RCV.WND is
     refused, counted in tcp_unacceptable and answered with a bare ACK.
     Off by one in either direction moves a counter.
 12. A PEER WHOSE IPv4 ADDRESS HAS BIT 31 SET.  See THE HIGH-BIT
     ADDRESS REGRESSION below.  It is both the whole bench and a case of
     its own.
 13. THE ZERO-WINDOW PERSIST TIMER, RFC 9293 3.8.6.1 and MUST-36.  The
     peer acknowledges with a window of zero, more data is written, and
     NOTHING goes out; the persist timer arms at max(RTO, 1000 ms);
     after it expires ONE OCTET of new data is probed at SND.NXT and
     tcp_probes moves 0 -> 1; tcp_persist_ms has DOUBLED (SHLD-30); and
     the window-update ACK that follows releases the rest in one
     segment.  This is the deadlock no other timer breaks: with a zero
     window there is nothing outstanding, so the retransmission timer
     never runs and both ends wait forever.
 14. THE LOSS INJECTOR, TcpDropEvery.  With every data segment dropped,
     a twenty-octet write puts NO FRAME on the link at all and
     tcp_dropped moves 0 -> 1; the RTO then fires and the SAME twenty
     octets DO go out, byte for byte, at the same sequence number, with
     tcp_dropped STILL 1.  A RETRANSMISSION IS NEVER ITSELF DROPPED -
     that is what tcp_drop_hold is for, and a test that also lost the
     retransmissions would be testing backoff rather than recovery.
 15. THE KEEPALIVE, RFC 9293 3.8.4 and RFC 1122 4.2.3.6.  Ten seconds of
     idle time and the probe goes out at SND.NXT-1 - graded byte for
     byte, because SND.NXT would be an ordinary bare ACK that some
     middleboxes do not count as traffic.  Three unanswered probes at
     #TCP_KEEP_INTVL_MS apart and the connection is declared dead with
     #NET_TCP_E_TIMEOUT, CLOSED, and TcpWasReset() still 0: silence and
     a reset must never look the same from outside.

THE HIGH-BIT ADDRESS REGRESSION, AND WHY THE WHOLE BENCH IS 192.168.x.x

  On 2026-09-04 this gate found that A PEER WHOSE IPv4 ADDRESS HAS BIT
  31 SET COULD NOT CONNECT AT ALL.  tcp.pi4 declared `Global tcp_rip.l`,
  so storing a peer address narrowed it to 32 bits and SIGN-EXTENDED it:
  192.168.1.20 was held as -1062731500 while net.pi4's net_GetBE32 ends
  `ProcedureReturn v & $FFFFFFFF` and NetTcpRxFrom() answered
  3232235796.  `If tcp_rip = NetTcpRxFrom()` in tcp_Match was never
  true, no socket ever matched, and TcpInput answered every segment of
  its own conversation with a RST from the no-connection path.  The same
  narrowing broke a LISTENER from the third leg of the handshake on.

  It was confirmed on silicon the same evening, on the bench Pi 4 over
  Wi-Fi: `http get http://example.com/` (172.66.147.243, bit 31 set)
  reported that the connection was never established, and `tcp status`
  showed eight segments out, three retransmissions and FOUR RESETS SENT
  TO A CLOSED PORT - the board resetting its own connection once per
  SYN-ACK.  It is fixed: tcp_rip is `.i`, as are TcpConnect,
  TcpSendRstFor's toip, TcpPeerIp and http.pi4's http_ip and its
  callers.  THE WIDTH RULE at the top of tcp.pi4 is about SEQUENCE
  space and is right; an IPv4 address is not sequence space, is not
  modular, and is the one field where `.l` was the wrong type.

  TWO THINGS KEEP IT FIXED.  The bench is 192.168.1.x throughout, so
  every case in this file is now measured across the high-bit boundary
  rather than around it - the whole gate is the regression test.  And
  the group named `hb_` at the end drives a handshake and a data
  exchange on 172.20.0.20, a SECOND high-bit prefix, asserting that
  tcp_Match found the socket: ESTABLISHED, TcpPeerIp() unsigned, not one
  RST on the link and tcp_norst still 0.  10.0.0.0/8 would have found
  neither.

WHAT IS NOT PROVEN, AND SAYING SO IS THE POINT

  * NO CONGESTION CONTROL IS TESTED because there is none to test - see
    tcp.pi4's gap 1.  Nothing here would notice its absence.
  * SIMULTANEOUS OPEN and the CLOSING and LAST-ACK paths are NOT
    exercised.  They are reachable through the same harness; each needs
    its own case and nobody has written one.
  * THE CHECKSUM IS NOT INDEPENDENTLY RE-DERIVED FROM AN RFC.  This gate
    computes the TCP checksum its own way - big-endian 16-bit words
    unpacked with struct and summed - where net.pi4 walks octets, so an
    arithmetic slip is caught; but both are one reading of RFC 9293 3.1
    written twice.  a64_net_check.py's HOW HONEST THIS GATE IS applies
    here word for word.
  * THE FRAMING BELOW TCP IS net.pi4's AND IS GATED THERE.  If
    a64_net_check.py is red this gate's byte-exact comparisons mean
    nothing, because both files would have to be wrong in the same way
    for them to agree.
  * ONE MUTATION IN THE SWEEP CANNOT BE CAUGHT and is declared as such
    rather than quietly dropped: see EXPECT_GREEN.

THE CLOCK, AND THE ONE PLACE THIS GATE MODELS SOMETHING

  a64_net_check.py makes time pass by BURNING it: a loop that spins on
  net_Ticks() until enough have gone by.  That works there because one
  ARP lifetime at the shortest settable TTL is 54,000 ticks.  It does not
  work here.  CNTPCT_EL0 advances one tick per eight emulated
  instructions, so #TCP_RTO_INIT_MS - one second at 54 MHz - is 54
  million ticks and 432 million instructions, and 2*MSL is two hundred
  and forty times that.  Four minutes of emulated TIME-WAIT would be
  about three days of wall clock.

  So this harness ALSO has a WARP: a four-byte store to #H_CLOCK, which
  the Python side decodes and turns into an offset added to every later
  read of CNTPCT_EL0.  What that models is a counter that has advanced
  while nothing of ours ran, which is what a counter does.  What it does
  NOT model is the instructions the board would have executed in
  between, and no timer in tcp.pi4 depends on those.  OP_SPIN is kept as
  well and burns one real millisecond, so that the claim "the clock
  advances when instructions execute" is measured and not assumed, and
  every warp returns the microseconds it actually produced so the
  mechanism itself is graded.

  BE CLEAR ABOUT WHICH IS WHICH.  Case 5's 2*MSL expiry is proven by
  WARPING the counter, not by executing for four minutes.  The
  arithmetic inside TcpTimers is exercised in full; the passage of real
  time is not.

HOW TO ADD A CASE

  Add an op to HARNESS if you need a library call that is not there,
  give it a number in the OP_ block, add a record in build_script() with
  a name, and grade it in check().  Never express a test case in
  harness source: the harness is the same text for the clean library and for
  every mutant, and everything that varies arrives as DATA in memory.
  If your case needs an input frame to carry a value the library chose -
  our ISN, our ephemeral port - use the PATCH_ flags rather than
  guessing: the harness rewrites those fields and recomputes the TCP
  checksum with its own arithmetic, which is a third implementation
  again and refuses the frame if it disagrees with net.pi4's.

Run:  python tools/a64/a64_tcp_check.py
      python tools/a64/a64_tcp_check.py --mutate
      python tools/a64/a64_tcp_check.py --dump     (one line per record)
      python tools/a64/a64_tcp_check.py --cost     (instructions per
                                                    received octet; grades
                                                    nothing - see THE COST
                                                    MODE)

--mutate rebuilds the library with one deliberate defect in it, twenty
times, ACROSS ALL CORES - one worker and one directory per mutation, via
tools/a64/a64_mutate_pool.py, because a serial sweep is the wrong shape
for a new gate.  Nineteen of the twenty MUST go red; the twentieth is
declared in EXPECT_GREEN with the reason it cannot be caught, so that a
green there is a measured verdict and not an oversight.  THE FIRST
MUTATION IN THE LIST PUTS `Global tcp_rip.l` BACK, which is the defect
above; it is the single most valuable line in the sweep.  A mutation
whose anchor text has drifted is REPORTED, never silently skipped.  A
gate nobody has ever seen fail is a gate nobody has any reason to
believe.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import struct
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN.  A root pinned into
# the file made a sibling gate build a DIFFERENT working copy, with that
# copy's compiler, and print the answer as this tree's.  Override
# deliberately with PMF_REPO; the tree actually read is printed below so a
# wrong one is visible.
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols          # noqa: E402
import a64_mutate_pool as pool                      # noqa: E402

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "RaspberryPi4" / "Lib" / "tcp.pi4"
NETLIB = ROOT / "Anvil" / "Network" / "net.pbi"
# THE SECOND FILE UNDER TEST, since 2026-09-05: the upload receiver.  It
# is here rather than in a gate of its own because it has no meaning
# without a TCP connection under it, and this is the only harness in the
# tree that can produce one from byte-exact frames.
RECVLIB = ROOT / "Anvil" / "Core" / "netrecv.pbi"
LINKLIB = ROOT / "RaspberryPi4" / "Lib" / "link.pi4"
LIB_DEFAULT = "RaspberryPi4/Lib/tcp.pi4"
RECV_DEFAULT = "Anvil/Core/netrecv.pbi"
WORK = ROOT / "_work"


def _last_socket() -> int:
    """#TCP_SOCKETS - 1, read out of tcp.pi4.

    The main connection must live on the LAST socket, because TcpPoll's
    table walk leaves that socket current and a RST for a stranger is built
    on its working globals.  The table size is library configuration (4 in
    an older tcp.pi4, 16 in Anvil main), so it is read, not typed."""
    import re as _re
    text = LIB.read_text(encoding="utf-8", errors="replace")
    m = _re.search(r"^#TCP_SOCKETS\s*=\s*(\d+)", text, _re.M)
    if not m:
        raise SystemExit("%s no longer defines #TCP_SOCKETS; check the socket "
                         "table declaration in tcp.pi4." % LIB)
    return int(m.group(1)) - 1


LAST_SOCKET = _last_socket()

LOAD = 0x00400000
STACK = 0x03000000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
CNTFRQ = 54_000_000
STEPS_PER_TICK = 8
# The TCP harness burns ticks: OP_SPIN really executes a millisecond, and
# the 3000-byte send builds two full segments an octet at a time.
STEP_LIMIT = 400_000_000

UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

# Where the script, the results and the warp register live.  Far above the
# image at $400000, far above the stack top at $3000000, and nowhere near
# anything net.pi4, timer.pi4, uart.pi4 or tcp.pi4 touches.
H_SCRIPT = 0x06000000
H_RESULT = 0x06800000
H_CLOCK = 0x06F00000


# =====================================================================
#  AN INDEPENDENT ENCODER AND AN INDEPENDENT CHECKSUM
# =====================================================================
# Written the other way round from the library's on purpose: this unpacks
# big-endian 16-bit words with struct and sums the list, where net.pi4
# walks octets and shifts and the harness's own hFixTcpSum walks array
# elements.  Three implementations that share no code do not share an
# arithmetic slip.
def ones_complement(data: bytes, seed: int = 0) -> int:
    if len(data) % 2:
        data = data + b"\x00"
    total = seed + sum(struct.unpack(">%dH" % (len(data) // 2), data))
    while total > 0xFFFF:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def pseudo_header(src: int, dst: int, proto: int, length: int) -> bytes:
    """The twelve octets of RFC 9293 Figure 2."""
    return struct.pack(">IIBBH", src, dst, 0, proto, length)


def ip4(a: int, b: int, c: int, d: int) -> int:
    return (a << 24) | (b << 16) | (c << 8) | d


def dotted(v: int) -> str:
    return "%d.%d.%d.%d" % ((v >> 24) & 0xFF, (v >> 16) & 0xFF,
                            (v >> 8) & 0xFF, v & 0xFF)


def mac_str(b: bytes) -> str:
    return ":".join("%02X" % x for x in b)


ET_IPV4 = 0x0800
PROTO_TCP = 6
BCAST = b"\xFF" * 6

FIN, SYN, RST, PSH, ACK, URG = 1, 2, 4, 8, 16, 32


def eth(dst: bytes, src: bytes, ethertype: int, payload: bytes) -> bytes:
    assert len(dst) == 6 and len(src) == 6
    return dst + src + struct.pack(">H", ethertype) + payload


def pad60(frame: bytes) -> bytes:
    """The 60-octet minimum, zero padded, as net_Finish does."""
    if len(frame) < 60:
        frame = frame + b"\x00" * (60 - len(frame))
    return frame


def ipv4(src: int, dst: int, proto: int, payload: bytes,
         ident: int = 0, ttl: int = 64, flags: int = 0x4000) -> bytes:
    total = 20 + len(payload)
    head = (struct.pack(">BBHHHBBH", 0x45, 0, total, ident, flags, ttl,
                        proto, 0)
            + struct.pack(">II", src, dst))
    head = head[:10] + struct.pack(">H", ones_complement(head)) + head[12:]
    return head + payload


def tcp_seg(sport: int, dport: int, seq: int, ack: int, flags: int,
            window: int, payload: bytes = b"", options: bytes = b"",
            urg: int = 0) -> bytes:
    """RFC 9293 3.1, Figure 1.  Options must be a whole number of words."""
    assert len(options) % 4 == 0
    off = 5 + len(options) // 4
    hdr = struct.pack(">HHIIBBHHH", sport, dport, seq & 0xFFFFFFFF,
                      ack & 0xFFFFFFFF, (off << 4) & 0xFF, flags & 0xFF,
                      window, 0, urg)
    return hdr + options + payload


MSS_OPTION = struct.pack(">BBH", 2, 4, 1460)        # Kind 2, Length 4, 1460


def tcp_frame(dstmac: bytes, srcmac: bytes, srcip: int, dstip: int,
              seg: bytes, ident: int) -> bytes:
    """One whole Ethernet frame, checksummed, padded to the 60-octet
    minimum the way a real interface delivers it.  net.pi4 drives every
    length off the IPv4 total length, so the pad is invisible above it."""
    ck = ones_complement(pseudo_header(srcip, dstip, PROTO_TCP, len(seg))
                         + seg)
    # TCP NEVER GAVE ZERO A SECOND MEANING, so there is no $0000 -> $FFFF
    # alias here and there must not be one in net.pi4 either.
    seg = seg[:16] + struct.pack(">H", ck) + seg[18:]
    return pad60(eth(dstmac, srcmac, ET_IPV4,
                     ipv4(srcip, dstip, PROTO_TCP, seg, ident=ident)))


# =====================================================================
#  THE HARNESS
# =====================================================================
# A fixed source file.  Everything that varies between runs arrives as
# DATA in memory, so this text is the same for the clean library and for
# every mutant, and no test case is ever expressed in harness source.
(OP_RESET, OP_SETMAC, OP_SETIP, OP_ARPSET, OP_TXMAX, OP_USE,
 OP_LISTEN, OP_CONNECT, OP_INJECT, OP_SEND, OP_READ, OP_CLOSE,
 OP_ABORT, OP_STATE, OP_COUNTS, OP_COUNTS2, OP_OOO, OP_SPIN,
 OP_TICK, OP_MSS, OP_SEQ, OP_WARP, OP_COUNTS3, OP_COUNTS4,
 OP_ZWIN, OP_KEEP, OP_DROP, OP_PEER,
 # 16. THE UPLOAD RECEIVER - Anvil/Core/netrecv.pbi, driven over this
 # same state machine by the same scripted peer.  See THE UPLOAD
 # RECEIVER in build_script.
 OP_RECV_ARM, OP_RECV_STEP, OP_RECV_STATE, OP_RECV_HASH, OP_RECV_MEM,
 OP_RECV_RELEASE, OP_UNLISTEN,
 # --cost ONLY.  It never appears in build_script, so the graded run's
 # case count is not changed by its existence.  See THE COST MODE.
 OP_COST_COPY,
 # Which #HW_LINK_* kind the fixture link IS, so that a connection made
 # over the radio has its replies arrive over the radio too.
 OP_LINKKIND) = range(1, 38)

# Anvil/Hal/hal.pbi's #HW_LINK_* numbering, restated for the script.  The
# harness includes the HAL and uses the names; these two are what the
# script records carry, and both halves have to agree on them.
HW_LINK_WIRED = 1
HW_LINK_WIFI = 2

# The NetRecv* states, from Anvil/Core/netrecv.pbi.  Written out here
# rather than parsed because they are a five-line block of constants
# whose numbers are declared stable in that file's own comment.
NR_WAIT, NR_RECV, NR_DONE, NR_OVER = 1, 2, 3, 4

# The patch flags OP_INJECT understands, because two fields of an inbound
# frame are values the LIBRARY chose and the gate cannot know when the
# script is built.
PATCH_DPORT = 1         # TCP destination port <- the socket's tcp_lport
PATCH_ACK_ISS = 2       # TCP acknowledgment  <- the socket's tcp_iss + d

HARNESS = r'''
; ======================================================================
;  tcpharness.pi4 - GENERATED BY tools/a64/a64_tcp_check.py. DO NOT EDIT.
; ======================================================================
;  It reads a script of library calls out of memory at #H_SCRIPT, runs
;  them, and writes a result record for each into #H_RESULT.  The gate
;  puts the script there before the run and reads the results out
;  afterwards, so every frame in every test case is DATA and this file
;  never has to change to add one.
;
;  SCRIPT RECORD, 24 bytes then `ln` bytes of blob, padded to 4:
;     +0 op  +4 a  +8 b  +12 c  +16 d  +20 ln  +24 blob
;  op 0 ends the script.
;
;  RESULT RECORD, 20 bytes then `n` bytes of blob, padded to 4:
;     +0 op  +4 result  +8 extra1  +12 extra2  +16 n  +20 blob
;
;  THE RESULT BLOB IS EVERY FRAME THE LINK WAS HANDED DURING THAT OP,
;  each one preceded by its length as two big-endian octets.  A single
;  frame is the common case and an empty blob means NOTHING WAS SENT -
;  which is a verdict several cases turn on, so the capture is cleared
;  at the top of every op and never carries the previous one's frame.
;
;  THE LINK SEAM.  tcp.pi4 names four link procedures it does not define:
;  HwLinkReady, LinkTxMaxOn, LinkTxStagedOn and LinkPumpAllNet, each of
;  which takes (or implies) an #HW_LINK_* interface kind.  All four are
;  here and link.pi4 is NOT included, which is the whole reason this gate
;  needs no device model.  #LINK_RX_BUDGET comes from Anvil/Hal/hal.pbi;
;  #LINK_RX_NONE lives in link.pi4, so the gate reads its value out of
;  that file and writes it in below.
; ======================================================================
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/timer.pi4"
XIncludeFile "Anvil/Network/net.pbi"

#H_SCRIPT = $06000000
#H_RESULT = $06800000
#H_CLOCK  = $06F00000
#H_CAPMAX = 16384
; THE DEFAULT INTERFACE KIND.  Every connection in this harness is on
; the wired interface unless a script record names another: ops 2, 3, 4
; and 8 take the kind in `d` (0 means this one), and op 37 changes which
; kind the fixture link delivers frames on.
#H_KIND = #HW_LINK_WIRED

#LINK_RX_NONE = __LINK_RX_NONE__

Global Dim stubCap.a[#H_CAPMAX]
Global stubCapLen.i
Global stubCapN.i
Global stubOvf.i
Global stubMax.i
Global stubRxPtr.i
Global stubRxLen.i
Global stubLastIn.i
; WHICH KIND THE FIXTURE LINK IS.  LinkPumpAllNet on a real board hands
; NetInput the kind the frame arrived on, and tcp.pi4 re-latches tcp_kind
; from NetRxKind() on every accepted segment - so a stub that always said
; "wired" would quietly move a radio connection back onto the cable
; between its SYN and its SYN-ACK.  The script sets this, so the radio
; case is a radio case in both directions.
Global stubKind.i

Global Dim hRx.a[2048]
Global Dim hScratch.a[4096]

Procedure.i HwLinkReady(kind.i)
  ProcedureReturn 1
EndProcedure

Procedure.i LinkTxMaxOn(kind.i)
  ProcedureReturn stubMax
EndProcedure

; Copy whatever net.pbi staged into the capture, length-prefixed.  The
; return value is the link's, so a refusal could be modelled here too;
; nothing in this gate needs one yet.
Procedure.i LinkTxStagedOn(kind.i)
  Define n.i
  Define i.i
  Define b.i
  n = NetOutLen()
  If n <= 0
    ProcedureReturn 0
  EndIf
  If (stubCapLen + 2 + n) > #H_CAPMAX
    stubOvf = 1
    ProcedureReturn 1
  EndIf
  b = NetOutBuf()
  stubCap[stubCapLen] = (n >> 8) & $FF
  stubCap[stubCapLen + 1] = n & $FF
  i = 0
  While i < n
    stubCap[stubCapLen + 2 + i] = PeekA(b + i) & $FF
    i = i + 1
  Wend
  stubCapLen = stubCapLen + 2 + n
  stubCapN = stubCapN + 1
  ProcedureReturn 1
EndProcedure

; One frame, once, on the interface stubKind names; then #LINK_RX_NONE.
Procedure.i LinkPumpAllNet(ms.i)
  Define n.i
  If stubRxLen <= 0
    ProcedureReturn #LINK_RX_NONE
  EndIf
  n = NetInput(stubKind, stubRxPtr, stubRxLen)
  stubRxLen = 0
  stubLastIn = n
  ProcedureReturn n
EndProcedure

XIncludeFile "__LIB__"

; ----------------------------------------------------------------------
;  THE UPLOAD RECEIVER, COMPILED INTO THIS HARNESS.
;
;  Anvil/Core/netrecv.pbi calls the Tcp* family, millis() and Sha256Of()
;  and nothing else - no console, no parser, no chip - which is why it
;  can be here at all.  So the scripted peer below drives the REAL
;  receiver over the REAL state machine with byte-exact frames and still
;  no device model.  Its console half, netrecv_cmd.pbi, is deliberately
;  NOT here: it needs the console and the command parser, which this
;  harness does not carry.
;
;  sha256.pbi comes with it because the receiver hashes what it stored,
;  and this gate checks that digest against Python's hashlib - which
;  makes it an end-to-end check that the bytes hashed are the bytes
;  received, not a second copy of the SHA-256 known-answer test.
; ----------------------------------------------------------------------
XIncludeFile "Anvil/Core/sha256.pbi"
XIncludeFile "__RECV__"

; ----------------------------------------------------------------------
;  Recompute the TCP checksum of the frame sitting in hRx, after the
;  patcher has rewritten a field the library chose.  This is a THIRD
;  implementation of the ones' complement sum - net.pi4 walks octets
;  through PeekA, the gate unpacks 16-bit words with struct, this walks
;  array elements - so a frame it builds and net.pi4 accepts has been
;  agreed on by two independent sums.
;
;  The segment length comes from the IPv4 TOTAL LENGTH field and never
;  from the frame length, because a frame delivered by a real interface
;  is padded to sixty octets and the pad is not part of the segment.
; ----------------------------------------------------------------------
Procedure hFixTcpSum()
  Define seglen.i
  Define sum.i
  Define i.i
  seglen = (((hRx[16] & $FF) << 8) | (hRx[17] & $FF)) - 20
  If seglen < 20
    ProcedureReturn
  EndIf
  hRx[50] = 0
  hRx[51] = 0
  sum = 0
  i = 26
  While i < 34
    sum = sum + (((hRx[i] & $FF) << 8) | (hRx[i + 1] & $FF))
    i = i + 2
  Wend
  sum = sum + 6
  sum = sum + seglen
  i = 0
  While i < (seglen - 1)
    sum = sum + (((hRx[34 + i] & $FF) << 8) | (hRx[34 + i + 1] & $FF))
    i = i + 2
  Wend
  If (seglen & 1) <> 0
    sum = sum + ((hRx[34 + seglen - 1] & $FF) << 8)
  EndIf
  While (sum >> 16) <> 0
    sum = (sum & $FFFF) + (sum >> 16)
  Wend
  sum = ($FFFF - sum) & $FFFF
  hRx[50] = (sum >> 8) & $FF
  hRx[51] = sum & $FF
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define a.i
  Define b.i
  Define c.i
  Define d.i
  Define ln.i
  Define blob.i
  Define r.i
  Define e1.i
  Define e2.i
  Define n.i
  Define src.i
  Define i.i
  Define t0.i
  Define k.i

  NetInit()
  TcpInit()
  stubMax = 1514
  stubKind = #H_KIND
  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    op = PeekN(p)
    If op = 0
      Break
    EndIf
    a    = PeekN(p + 4)
    b    = PeekN(p + 8)
    c    = PeekN(p + 12)
    d    = PeekN(p + 16)
    ln   = PeekN(p + 20)
    blob = p + 24

    r = 0
    e1 = 0
    e2 = 0
    n = 0
    src = 0
    ; THE CAPTURE IS CLEARED HERE AND NOWHERE ELSE.  "no frame was sent"
    ; and "the previous frame is still there" must never look alike.
    stubCapLen = 0
    stubCapN = 0

    If op = 1
      NetInit()
      TcpInit()
      stubMax = 1514
      stubKind = #H_KIND
      stubRxLen = 0
      stubLastIn = 0
      r = 1
    ElseIf op = 2
      ; `d` IS THE #HW_LINK_* KIND THIS IDENTITY BELONGS TO, 0 meaning
      ; #H_KIND.  It comes from the record so that a case can give a
      ; SECOND interface an identity of its own - which case 8 does,
      ; because a connection "over the radio" that borrowed the cable's
      ; row would prove nothing about the kind tcp.pi4 latched.
      k = d
      If k = 0
        k = #H_KIND
      EndIf
      r = NetSetMac(k, blob)
      e1 = NetError()
    ElseIf op = 3
      k = d
      If k = 0
        k = #H_KIND
      EndIf
      r = NetSetIPv4(k, a, b, c)
      e1 = NetError()
    ElseIf op = 4
      ; The ARP cache is per interface too, so a peer reached over the
      ; radio has to be pinned on the radio's row.
      k = d
      If k = 0
        k = #H_KIND
      EndIf
      r = NetArpSet(k, a, blob)
      e1 = NetError()
    ElseIf op = 5
      stubMax = a
      r = stubMax
    ElseIf op = 6
      r = TcpUse(a)
      e1 = TcpCurrent()
    ElseIf op = 7
      r = TcpListen(a)
      e1 = TcpState()
    ElseIf op = 8
      ; `d` is the kind, as in ops 2, 3 and 4.  TcpConnect latches it into
      ; tcp_kind alongside the peer's address and port, so it is part of
      ; the identity of the connection and not a per-call detail.
      k = d
      If k = 0
        k = #H_KIND
      EndIf
      r = TcpConnect(k, a, b)
      e1 = TcpState()
      e2 = TcpError()
    ElseIf op = 9
      i = 0
      While i < ln
        hRx[i] = PeekA(blob + i) & $FF
        i = i + 1
      Wend
      If c <> 0
        If (c & 1) <> 0
          hRx[36] = (tcp_lport >> 8) & $FF
          hRx[37] = tcp_lport & $FF
        EndIf
        If (c & 2) <> 0
          k = tcp_iss + d
          hRx[42] = (k >> 24) & $FF
          hRx[43] = (k >> 16) & $FF
          hRx[44] = (k >> 8) & $FF
          hRx[45] = k & $FF
        EndIf
        hFixTcpSum()
      EndIf
      stubRxPtr = @hRx[0]
      stubRxLen = ln
      stubLastIn = 0
      r = TcpPoll(0)
      e1 = stubLastIn
      e2 = TcpState()
    ElseIf op = 10
      r = TcpSend(blob, ln)
      e1 = TcpState()
    ElseIf op = 11
      ; A READ CAN TRANSMIT.  RFC 1122 4.2.2.17: reading is what reopens
      ; the receive window, and a receiver that reopens it has to say so,
      ; so TcpRead sends the window update from inside itself.  e1
      ; carries HOW MANY frames it sent - the only place this gate can
      ; see that number - and the blob below stays the octets that were
      ; READ.
      r = TcpRead(@hScratch[0], a)
      e1 = stubCapN
      If r > 0
        n = r
        src = @hScratch[0]
      EndIf
    ElseIf op = 12
      r = TcpClose()
      e1 = TcpState()
    ElseIf op = 13
      r = TcpAbort()
      e1 = TcpState()
    ElseIf op = 14
      r = TcpState()
      e1 = TcpError()
      e2 = TcpWasReset()
    ElseIf op = 15
      r = tcp_seg_rx
      e1 = tcp_seg_tx
      e2 = tcp_retrans
    ElseIf op = 16
      r = tcp_dupacks
      e1 = tcp_rst_tx
      e2 = tcp_unacceptable
    ElseIf op = 17
      r = tcp_ooo_queued
      e1 = tcp_ooo_deliver
      e2 = tcp_ooo_drop
    ElseIf op = 18
      ; Burn `a` ticks of CNTPCT_EL0 by EXECUTING.  This is the only op
      ; that makes time pass the way the board makes it pass, and it is
      ; kept - even though the warp below is what the long timers need -
      ; so that "the clock advances while instructions run" is measured
      ; rather than assumed.  r is the microseconds it actually produced.
      t0 = Micros()
      k = net_Ticks()
      While (net_Ticks() - k) < a
        e2 = e2 + 1
      Wend
      r = Micros() - t0
      e1 = 0
      e2 = 0
    ElseIf op = 19
      r = TcpPoll(0)
      e1 = TcpState()
      e2 = TcpError()
    ElseIf op = 20
      r = tcp_snd_mss
      e1 = tcp_rcv_wnd
      e2 = tcp_rto
    ElseIf op = 21
      r = TcpSeqLt(a, b)
      e1 = TcpSeqGt(a, b)
      e2 = TcpSeqLe(a, b)
    ElseIf op = 22
      ; THE WARP.  A store to #H_CLOCK, which the model decodes into an
      ; offset added to every later read of CNTPCT_EL0.  See THE CLOCK
      ; in the gate's own header for exactly what this does and does not
      ; model.  r is the milliseconds Micros() actually moved, so the
      ; mechanism is graded and not trusted.
      t0 = Micros()
      PokeN(#H_CLOCK, a)
      r = (Micros() - t0) / 1000
    ElseIf op = 23
      r = tcp_norst
      e1 = tcp_zerowin
      e2 = tcp_probes
    ElseIf op = 24
      r = tcp_dropped
      e1 = tcp_keeps
      e2 = tcp_txfail
    ElseIf op = 25
      r = tcp_persist_armed
      e1 = tcp_persist_ms
      e2 = tcp_snd_wnd
    ElseIf op = 26
      r = TcpKeepalive(a)
      e1 = TcpKeepaliveMs()
      e2 = TcpState()
    ElseIf op = 27
      r = TcpDropEvery(a)
      e1 = TcpState()
    ElseIf op = 28
      ; e1, NOT r: TcpPeerIp() is an IPv4 address in 0..$FFFFFFFF and the
      ; gate sign-extends r.  An address with bit 31 set read back as a
      ; negative number is the whole defect this op exists to watch.
      r = TcpState()
      e1 = TcpPeerIp()
      e2 = TcpPeerPort()

    ; ---- 16. THE UPLOAD RECEIVER ------------------------------------
    ElseIf op = 29
      r = NetRecvArm(a, b, c)
      e1 = TcpState()
      e2 = NetRecvCeil()
    ElseIf op = 30
      ; A frame in, then ONE NetRecvStep - which is what CmdNetRecv's
      ; loop does and all it does.  The patcher selects the RECEIVER'S
      ; socket before reading tcp_lport and tcp_iss, because the frames
      ; have to carry the port and the acknowledgment THAT socket chose
      ; and the receiver picks its own socket out of the table.
      i = 0
      While i < ln
        hRx[i] = PeekA(blob + i) & $FF
        i = i + 1
      Wend
      If c <> 0
        k = TcpCurrent()
        TcpUse(NetRecvSock())
        If (c & 1) <> 0
          hRx[36] = (tcp_lport >> 8) & $FF
          hRx[37] = tcp_lport & $FF
        EndIf
        If (c & 2) <> 0
          i = tcp_iss + d
          hRx[42] = (i >> 24) & $FF
          hRx[43] = (i >> 16) & $FF
          hRx[44] = (i >> 8) & $FF
          hRx[45] = i & $FF
        EndIf
        TcpUse(k)
        hFixTcpSum()
      EndIf
      stubRxPtr = @hRx[0]
      stubRxLen = ln
      stubLastIn = 0
      r = NetRecvStep()
      e1 = NetRecvCount()
      e2 = stubLastIn
    ElseIf op = 31
      r = NetRecvState()
      e1 = NetRecvCount()
      e2 = tcp_listen_port
    ElseIf op = 32
      NetRecvHash()
      r = NetRecvCount()
      e1 = NetRecvBase()
      n = 32
      src = NetRecvDigest()
    ElseIf op = 33
      ; Read `b` octets back out of DRAM at `a`.  This is how "the bytes
      ; landed where they were sent AND NOWHERE ELSE" is graded: the
      ; window past the ceiling is read too, and it must still be zero.
      r = a
      e1 = b
      n = b
      src = a
    ElseIf op = 34
      NetRecvRelease()
      r = TcpState()
      e1 = tcp_listen_port
      e2 = tcp_inuse
    ElseIf op = 35
      r = TcpUnlisten()
      e1 = tcp_listen_port
      e2 = TcpState()
    ElseIf op = 36
      ; THE HARNESS'S OWN COST, AND NOTHING ELSE. This is op 30 with the
      ; single call `NetRecvStep()` and the two result reads after it
      ; removed and nothing else changed - the frame copy into hRx, the
      ; socket switch the patcher needs, the two field rewrites, the
      ; re-sum and the hand-off to the link stub. A --cost run measures
      ; this slope the same way it measures op 30's and subtracts it, so
      ; what is reported is the LIBRARY'S receive path and not this
      ; file's scaffolding. Keep the two bodies identical apart from that
      ; call: the moment they drift, the subtraction stops being one.
      i = 0
      While i < ln
        hRx[i] = PeekA(blob + i) & $FF
        i = i + 1
      Wend
      If c <> 0
        k = TcpCurrent()
        TcpUse(NetRecvSock())
        If (c & 1) <> 0
          hRx[36] = (tcp_lport >> 8) & $FF
          hRx[37] = tcp_lport & $FF
        EndIf
        If (c & 2) <> 0
          i = tcp_iss + d
          hRx[42] = (i >> 24) & $FF
          hRx[43] = (i >> 16) & $FF
          hRx[44] = (i >> 8) & $FF
          hRx[45] = i & $FF
        EndIf
        TcpUse(k)
        hFixTcpSum()
      EndIf
      stubRxPtr = @hRx[0]
      stubRxLen = ln
      stubLastIn = 0
      r = ln
    ElseIf op = 37
      ; WHICH KIND THE FIXTURE LINK IS FROM HERE ON.  It changes what
      ; LinkPumpAllNet tells NetInput, which is what NetRxKind() answers,
      ; which is what tcp.pi4 re-latches into tcp_kind.  A case that
      ; opened a connection on the radio and then fed its replies in as
      ; wired would be testing nothing about the kind.
      stubKind = a
      r = stubKind
    EndIf

    PokeN(q + 0, op)
    PokeN(q + 4, r)
    PokeN(q + 8, e1)
    PokeN(q + 12, e2)
    ; WHAT WENT OUT WINS OVER WHAT CAME BACK - EXCEPT ON A READ, where
    ; the octets that came back ARE the assertion.  TcpRead sends its own
    ; window update; without this exception a read that crosses the
    ; threshold reports that ACK instead of the ring's contents, and the
    ; ring-wrap group goes red on a stack that is right.  The count of
    ; frames a read sent is in e1 instead.
    If stubCapLen > 0 And op <> 11
      n = stubCapLen
      src = @stubCap[0]
    EndIf
    PokeN(q + 16, n)
    If n > 0
      i = 0
      While i < n
        PokeB(q + 20 + i, PeekA(src + i))
        i = i + 1
      Wend
    EndIf

    p = p + 24 + (((ln + 3) / 4) * 4)
    q = q + 20 + (((n + 3) / 4) * 4)
  ForEver

  PokeN(q, 0)
  If stubOvf <> 0
    UartWriteStr("TXOVERFLOW ")
  EndIf
  UartWriteStr("tcpharness done")
  ProcedureReturn 0
EndProcedure
'''


class Script:
    """Builds the octet stream the harness walks, and remembers what each
    record was for so a failure can name itself."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []

    def add(self, op: int, label: str, a: int = 0, b: int = 0, c: int = 0,
            d: int = 0, blob: bytes = b"") -> int:
        idx = len(self.labels)
        self.labels.append(label)
        self.buf += struct.pack("<6I", op, a & 0xFFFFFFFF, b & 0xFFFFFFFF,
                                c & 0xFFFFFFFF, d & 0xFFFFFFFF, len(blob))
        self.buf += blob
        while len(self.buf) % 4:
            self.buf.append(0)
        return idx

    def finish(self) -> bytes:
        return bytes(self.buf) + struct.pack("<I", 0)


class Result:
    __slots__ = ("op", "r", "e1", "e2", "blob", "label")

    def __init__(self, op, r, e1, e2, blob, label):
        self.op, self.r, self.e1, self.e2 = op, r, e1, e2
        self.blob, self.label = blob, label

    def frames(self) -> list[bytes]:
        """Split the length-prefixed capture back into whole frames."""
        out, i = [], 0
        while i + 2 <= len(self.blob):
            n = (self.blob[i] << 8) | self.blob[i + 1]
            if n == 0 or i + 2 + n > len(self.blob):
                break
            out.append(bytes(self.blob[i + 2:i + 2 + n]))
            i += 2 + n
        return out


def read_results(mem, labels: list[str]) -> list[Result]:
    out: list[Result] = []
    addr = H_RESULT
    while True:
        def w(off):
            return sum(mem.get(addr + off + i, 0) << (8 * i) for i in range(4))
        op = w(0)
        if op == 0:
            break
        raw = w(4)
        r = raw - 0x100000000 if raw & 0x80000000 else raw
        n = w(16)
        if n > 65536:
            raise SystemExit(
                "a result record claims %d octets of capture, which is more "
                "than the harness's buffer can hold.  The harness or the "
                "result stream has been corrupted." % n)
        blob = bytes(mem.get(addr + 20 + i, 0) for i in range(n))
        i = len(out)
        out.append(Result(op, r, w(8), w(12), blob,
                          labels[i] if i < len(labels) else "?"))
        addr += 20 + ((n + 3) // 4) * 4
    return out


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def link_rx_none() -> int:
    """#LINK_RX_NONE, read out of link.pi4.

    The harness replaces link.pi4 with a stub, so the constant tcp.pi4
    reads from it is restated in the harness; reading it from the real
    file keeps the restatement from drifting."""
    text = LINKLIB.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^#LINK_RX_NONE\s*=\s*(-?\d+)", text, re.M)
    if not m:
        raise SystemExit(
            "%s no longer defines #LINK_RX_NONE, which tcp.pi4 reads and "
            "this harness restates.  Check link.pi4 and update the harness."
            % LINKLIB.relative_to(ROOT).as_posix())
    return int(m.group(1))


def write_harness(lib_include: str, path: pathlib.Path,
                  recv_include: str = RECV_DEFAULT) -> None:
    """TWO includes, because there are two files under test.

    A mutation replaces exactly one of them with its own copy and leaves
    the other pointing at the tree, so a defect in tcp.pi4 and a defect
    in netrecv.pi4 are separate verdicts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = HARNESS.replace("__LIB__", lib_include)
    text = text.replace("__RECV__", recv_include)
    text = text.replace("__LINK_RX_NONE__", str(link_rx_none()))
    path.write_text(text, encoding="utf-8")


def build(source: pathlib.Path, out: pathlib.Path) -> None:
    import subprocess
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(PMFC), "--compile", str(source), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img: pathlib.Path, script: bytes, step_limit: int = STEP_LIMIT):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    # Names for the alignment rule's message.  Read from the `.dbg` pmfc
    # already writes - NOT the `.sym`, whose wrong half reads as a column
    # of zeroes rather than an error.
    attach_symbols(cpu, img, LOAD)
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    uart = bytearray()
    steps = [0]
    skew = [0]              # CNTPCT_EL0 ticks added by the warp

    def load(addr, size):
        # THE ALIGNMENT RULE.  This closure replaces A64.load, so the
        # guard has to be CALLED here.  With the MMU off every data
        # access is Device-nGnRnE and an unaligned wide one is a silent
        # runaway on the part; without this line the gate models a
        # machine more permissive than the board it certifies.
        cpu.align_guard(addr, size, False)
        if UART_LO <= addr <= UART_HI:
            return 0                        # a PL011 that is never busy
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if addr == H_CLOCK:
            # THE WARP.  `value` is milliseconds; the counter jumps by
            # that many milliseconds' worth of ticks and stays jumped.
            skew[0] += (CNTFRQ // 1000) * (value & 0xFFFFFFFF)
            return
        if UART_LO <= addr <= UART_HI:
            if addr == UART_DR:
                uart.append(value & 0xFF)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    def step():
        steps[0] += 1
        # cpu.fetch, not load: an instruction fetch is Normal
        # Non-Cacheable with the MMU off, not Device, so it is not
        # subject to the data alignment rule.
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = steps[0] // STEPS_PER_TICK + skew[0]
            cpu.pc += 4
            return
        plain_step()

    cpu.step = step
    for _ in range(step_limit):
        if cpu.pc == LOADER_LR:
            return cpu, uart, steps[0]
        step()
    raise SystemExit("the harness never returned (%d steps)\n%s"
                     % (steps[0], uart.decode("latin-1")))


# =====================================================================
#  THE BENCH
# =====================================================================
OUR_MAC = bytes([0x02, 0x00, 0x4D, 0x46, 0x00, 0x01])
PEER_MAC = bytes([0xDC, 0xA6, 0x32, 0x11, 0x22, 0x33])
# THE RADIO'S OWN HARDWARE ADDRESS.  A board with two interfaces has two
# of these, and case 8 - the link-ceiling group - is the one group here
# that is not on the cable.  It differs from OUR_MAC in one octet so
# that a hexdump of a failing frame says at a glance which row built it.
RADIO_MAC = bytes([0x02, 0x00, 0x4D, 0x46, 0x00, 0x02])
STRANGER_MAC = bytes([0x08, 0x00, 0x27, 0xAA, 0xBB, 0xCC])

# THE BENCH IS 192.168.x.x AND THAT IS NOT A PREFERENCE EITHER.
# 192.168.1.20 is $C0A80114 and its TOP BIT IS SET, so every case in this
# file - the handshake, the retransmission, the socket table, the RSTs,
# the reassembly, the edge - is now measured ACROSS the high-bit boundary
# that a `.l` tcp_rip narrowed and sign-extended.  See THE HIGH-BIT
# ADDRESS REGRESSION in this file's header.  A bench on 10.0.0.0/8 passes
# that defect without noticing it, which is exactly what happened, so
# moving back to a 10-net for convenience would silently retire the
# strongest property this gate has.
OUR_IP = ip4(192, 168, 1, 50)
MASK = ip4(255, 255, 255, 0)
GW_IP = ip4(192, 168, 1, 1)
PEER_IP = ip4(192, 168, 1, 20)
STRANGER_IP = ip4(192, 168, 1, 77)

# A SECOND HIGH-BIT PREFIX, for the named regression group at the end.
# 172.20.0.20 is $AC140014: bit 31 set, 172.16.0.0/12, a different octet
# pattern from the bench above, so a repeat of the defect that somehow
# survived in only one address family still has somewhere to show.
HB_OUR_IP = ip4(172, 20, 0, 50)
HB_MASK = ip4(255, 240, 0, 0)
HB_GW_IP = ip4(172, 20, 0, 1)
HB_PEER_IP = ip4(172, 20, 0, 20)
HB_PEER_ISN = 0x71000000

# The peer's initial sequence numbers.  Ours are the library's business
# and are read out of the frames it produces; these are the gate's and are
# chosen far apart so a socket reading another socket's sequence space is
# obvious in a failure message rather than plausible.
P_MAIN = 0x21000000         # socket LAST_SOCKET, the main connection, peer port 80
P_LISTEN = 0x31000000       # the passive open on socket 2, port 8000
P_S0 = 0x41000000           # socket 0, peer port 8080
P_S1 = 0x51000000           # socket 1, peer port 8081
P_CEIL = 0x61000000         # socket 2 again, peer port 7000, the ceiling
P_ZW = 0x81000000           # the persist-timer group
P_DROP = 0x91000000         # the loss-injector group
P_KEEP = 0xA1000000         # the keepalive group
P_UP = 0xB1000000           # the upload receiver, the good transfer
P_UP2 = 0xB2000000          # ... the connection that must NOT be accepted
P_OV = 0xC1000000           # the upload receiver, over the ceiling
P_WRAP = 0xE1000000         # group 17, the ring wrap

STRANGER_SEQ = 0x0BADF00D

# ---------------------------------------------------------------------
#  THE UPLOAD RECEIVER'S BENCH.  Two windows of flat memory nothing else
#  in this harness touches: the image is at $400000, the stack top at
#  $3000000, and the script, the results and the warp register are at
#  $6000000 and above.  The second window is where the OVER-THE-CEILING
#  case aims, and its last ten octets are read back and required to be
#  UNTOUCHED - which is only a meaningful check because memory in this
#  model starts at zero and every octet the peer sends is non-zero.
# ---------------------------------------------------------------------
RECV_BASE = 0x05000000
OVER_BASE = 0x05100000
UP_A = bytes(range(0x41, 0x41 + 20))          # 'A'..'T'
UP_B = bytes(range(0x61, 0x61 + 20))          # 'a'..'t'
UPLOAD = UP_A + UP_B
OVER_ROOM = 30              # ... so UP_B's last ten octets have nowhere
RECV_PORT = 5001
OVER_PORT = 5002

# The states, as tcp.pi4 numbers them.  Stated here independently: if the
# two files disagree the gate goes red and one of them is wrong.
S_CLOSED, S_LISTEN, S_SYN_SENT, S_SYN_RECEIVED = 0, 1, 2, 3
S_ESTABLISHED, S_FIN_WAIT_1, S_FIN_WAIT_2, S_CLOSE_WAIT = 4, 5, 6, 7
S_CLOSING, S_LAST_ACK, S_TIME_WAIT = 8, 9, 10

E_RESET = -304
E_TIMEOUT = -305
NET_IN_TCP = 5

RCVBUF = 16384              # #TCP_RCVBUF in Anvil main's tcp.pi4 (the receive
                            # ring, so also the window a fresh socket offers)
MSS_RX = 1460               # #TCP_MSS_RX, what we ADVERTISE
RTO_INIT = 1000             # #TCP_RTO_INIT_MS
TIMEWAIT_MS = 240000        # #TCP_TIMEWAIT_MS, 2*MSL
# A LINK THAT CANNOT CARRY A FULL MTU.  Until 2026-09-07 this WAS the
# radio's number - #CYW43_TXBUF was 1152, so Cyw43DataMax() answered 1136
# and the bench read back `send MSS 1082`.  The radio now carries a full
# 1514-octet frame, so 1136 is no longer any real link on this board.
# IT IS KEPT ANYWAY, and deliberately: the property group 8 exists for is
# that TcpTxCap() OBEYS whatever LinkTxMax() says rather than assuming an
# Ethernet MTU, and a ceiling equal to the MTU proves nothing at all.
# Setting this to 1514 would retire the only case in this file that can
# catch a send path which ignores the seam.
RADIO_FRAME = 1136          # a link narrower than the MTU - see above
RADIO_MSS = RADIO_FRAME - 14 - 20 - 20      # 1082
PERSIST_MIN = 1000          # #TCP_PERSIST_MIN_MS
KEEP_PROBES = 3             # #TCP_KEEP_PROBES
KEEP_INTVL = 5000           # #TCP_KEEP_INTVL_MS
KEEP_IDLE_S = 10            # what this gate asks TcpKeepalive for

# THE RING-WRAP GROUP'S SEGMENT LENGTHS.  They must total MORE than
# #TCP_RCVBUF so that both ring pointers cross zero - asserted below
# rather than left to whoever next changes the constant - and the first
# four are deliberately not multiples of four, so that every later offset
# into the ring lands on a different residue and tcp_Move's 8-, 4-, 2-
# and 1-octet rungs all execute.
WRAP_LENS = [1459, 1460, 1457, 1458] + [1460] * 8
assert sum(WRAP_LENS) > RCVBUF, (
    "group 17 must move more than #TCP_RCVBUF octets through one socket "
    "or the ring never wraps and the group proves nothing: %d <= %d"
    % (sum(WRAP_LENS), RCVBUF))
assert max(WRAP_LENS) <= 4096, "OP_READ reads into hScratch, which is 4096"


def wrap_body(k, ln):
    """Distinct octets per segment, none of them zero-heavy, so a copy
    that lands one run in the wrong place shows up as a mismatch rather
    than as a plausible repeat."""
    return bytes(((k * 31 + i * 7 + 3) & 0xFF) for i in range(ln))

# The payloads.  Fixed text rather than counters, so a socket that reads
# another socket's ring says so in words.
D_FIRST = b"PureMetal Forge, TCP"          # 20
D_AGAIN = b"AGAIN"                         # 5
D_IN = b"hello, board"                     # 12
D_LOST = b"twenty bytes of data"           # 20
D_UNDIST = b"UNDIST"                       # 6
D_S0_OUT = b"socket ZERO out!"             # 16
D_S1_OUT = b"socket ONE  out!"             # 16
D_S0_IN = b"zero  data in!!!"              # 16
D_S1_IN = b"one   data in!!!"              # 16
D_OOO_2 = b"SECOND!!"                      # 8
D_OOO_1 = b"FIRST!!!"                      # 8
D_HB_OUT = b"high bit set, 172.20"         # 20
D_HB_IN = b"and the reply came"            # 18
D_ZW_OPEN = b"openwide"                    # 8, sent while the window is open
D_ZW_HELD = b"persist probe payload"       # 21, written into a zero window
D_DROPPED = b"deliberately lost!!!"        # 20
BULK = bytes((32 + (i % 90)) for i in range(3000))

# The width-rule pairs.  Every one is a pair of 32-bit sequence numbers
# whose ORDER IN SEQUENCE SPACE is not the order a 64-bit subtraction
# would give, or an exact boundary where it is easy to be off by one.
# The pair 2**31 apart is deliberately absent: modulo 2**32 it is
# genuinely ambiguous and no answer would be wrong.
SEQ_PAIRS = [
    (0x7FFFFFFF, 0xFFFFFFFF, 1, 0, 1,
     "tcp.pi4's own worked example: at 64 bits a - b is +2147483648 and "
     "says a is AFTER b; modulo 2**32 it is -2147483648 and a is BEFORE"),
    # NOT ($FFFFFFFF, $7FFFFFFF).  Those two are EXACTLY 2**31 apart and
    # modulo 2**32 the question has no answer - the difference is
    # -2147483648 whichever way round it is asked, so both orders report
    # "before" and neither is wrong.  RFC 9293 3.4's arithmetic is exact
    # only inside 2**31, which is a gigabyte against a four-kilobyte
    # window, so the case cannot arise; it is left out rather than
    # asserted, because asserting either answer would be asserting a
    # coincidence.
    (0x7FFFFFFE, 0xFFFFFFFF, 0, 1, 0,
     "one short of that ambiguity, and the sign flips: at 64 bits "
     "a - b is -2147483649 and says BEFORE, modulo 2**32 it is "
     "+2147483647 and says AFTER"),
    (0xFFFFFF00, 0x00000100, 1, 0, 1, "straddling the wrap, 512 apart"),
    (0x00000100, 0xFFFFFF00, 0, 1, 0, "and back the other way"),
    (0x00000005, 0x00000005, 0, 0, 1, "equality: neither before nor after"),
    (0xFFFFFFFF, 0x00000000, 1, 0, 1, "the wrap itself, one apart"),
    (0x00000000, 0xFFFFFFFF, 0, 1, 0, "the wrap itself, the other way"),
    (0x7FFFFFFF, 0x80000000, 1, 0, 1, "adjacent across the sign bit"),
    (0x80000000, 0x7FFFFFFF, 0, 1, 0, "adjacent across the sign bit, back"),
    (0xFFFFFFF0, 0x0000000F, 1, 0, 1, "thirty-one apart, across the wrap"),
]


# =====================================================================
#  THE COST MODE - `--cost`, and it grades nothing
# =====================================================================
#  WHY IT EXISTS. Every other mode in this file asks whether the library
#  is CORRECT. This one asks what it COSTS, because on the radio the
#  board's own per-segment work is not a detail on top of the round trip,
#  it IS most of the round trip: an image upload measured 622 KB/s with
#  the caches on and 207 KB/s with them off, and a three-fold change from
#  turning caches on and off cannot be a property of the wire.
#
#  WHAT IS MEASURED. The interpreter already counts every instruction it
#  executes and `run` already returns that count. So a receive of N full
#  segments and a receive of M full segments differ, in instructions, by
#  exactly what the library spends on (N-M) segments - every fixed cost,
#  every build difference, every line of the harness's own preamble
#  cancels in the subtraction. That slope, divided by the octets, is
#  INSTRUCTIONS PER RECEIVED OCTET, and it is the number that turns into
#  a throughput ceiling the moment the board says how many instructions a
#  second it retires.
#
#  WHAT IS SUBTRACTED, AND WHY IT HAS TO BE. The harness carries each
#  frame into hRx with a byte loop of its own before it calls anything,
#  and that loop is not the library's cost. OP_COST_COPY is that loop
#  with the library call removed, so its slope is measured the same way
#  and taken off. Without it every improvement to the library's copies
#  would be diluted by a loop this gate wrote.
#
#  IT IS NOT A BENCHMARK OF THE PART. The interpreter is not a timing
#  model of a Cortex-A72 and this file does not pretend it is: no
#  pipeline, no cache, no memory system. An instruction COUNT is still
#  the right instrument for the change being made here, because what is
#  being removed is instructions.
COST_SEG = 1460             # a full 1460-octet segment, what the peer sends
COST_LO = 4                 # the two segment counts the slope is taken over
COST_HI = 12
P_COST = 0xD1000000


def build_cost_script(nseg: int) -> Script:
    """N full segments into the upload receiver, and nothing graded."""
    s = Script()
    s.add(OP_RESET, "reset")
    s.add(OP_SETMAC, "mac", blob=OUR_MAC)
    s.add(OP_SETIP, "ip", a=OUR_IP, b=MASK, c=GW_IP)
    top = RECV_BASE + nseg * COST_SEG - 1
    s.add(OP_RECV_ARM, "arm", a=RECV_PORT, b=RECV_BASE, c=top)

    def upeer(seq, flags, payload=b"", options=b"", ident=0):
        return tcp_frame(OUR_MAC, PEER_MAC, PEER_IP, OUR_IP,
                         tcp_seg(40300, RECV_PORT, seq, 0, flags, 5840,
                                 payload, options), ident)

    s.add(OP_RECV_STEP, "syn", blob=upeer(P_COST, SYN, options=MSS_OPTION,
                                          ident=0xF000))
    s.add(OP_RECV_STEP, "ack", c=PATCH_ACK_ISS, d=1,
          blob=upeer(P_COST + 1, ACK, ident=0xF001))
    body = bytes((i * 7 + 11) & 0xFF for i in range(COST_SEG))
    seq = P_COST + 1
    for k in range(nseg):
        s.add(OP_RECV_STEP, "d%d" % k, c=PATCH_ACK_ISS, d=1,
              blob=upeer(seq, PSH | ACK, payload=body, ident=0xF010 + k))
        seq += COST_SEG
    s.add(OP_RECV_STEP, "fin", c=PATCH_ACK_ISS, d=1,
          blob=upeer(seq, FIN | ACK, ident=0xF0F0))
    s.add(OP_RECV_STATE, "state")
    s.add(OP_RECV_RELEASE, "release")
    return s


def build_harness_cost_script(nseg: int) -> Script:
    """THE SAME SCRIPT with NetRecvStep taken out of the loop.

    Same reset, same arm, same handshake, same N frames with the same
    patch - so the only difference between this slope and the one above
    is the library call itself."""
    s = Script()
    s.add(OP_RESET, "reset")
    s.add(OP_SETMAC, "mac", blob=OUR_MAC)
    s.add(OP_SETIP, "ip", a=OUR_IP, b=MASK, c=GW_IP)
    top = RECV_BASE + nseg * COST_SEG - 1
    s.add(OP_RECV_ARM, "arm", a=RECV_PORT, b=RECV_BASE, c=top)

    def upeer(seq, flags, payload=b"", options=b"", ident=0):
        return tcp_frame(OUR_MAC, PEER_MAC, PEER_IP, OUR_IP,
                         tcp_seg(40300, RECV_PORT, seq, 0, flags, 5840,
                                 payload, options), ident)

    s.add(OP_RECV_STEP, "syn", blob=upeer(P_COST, SYN, options=MSS_OPTION,
                                          ident=0xF000))
    s.add(OP_RECV_STEP, "ack", c=PATCH_ACK_ISS, d=1,
          blob=upeer(P_COST + 1, ACK, ident=0xF001))
    body = bytes((i * 7 + 11) & 0xFF for i in range(COST_SEG))
    seq = P_COST + 1
    for k in range(nseg):
        s.add(OP_COST_COPY, "copy%d" % k, c=PATCH_ACK_ISS, d=1,
              blob=upeer(seq, PSH | ACK, payload=body, ident=0xF010 + k))
        seq += COST_SEG
    return s


def cost() -> int:
    """Print instructions per received octet.  Grades nothing, returns 0
    unless a run failed to complete."""
    WORK.mkdir(exist_ok=True)
    out = {}
    for tag, builder in (("library", build_cost_script),
                         ("harness", build_harness_cost_script)):
        lo = one_run(LIB_DEFAULT, WORK / "tcpcost.pi4",
                     WORK / "tcpcost.img", builder(COST_LO))[2]
        hi = one_run(LIB_DEFAULT, WORK / "tcpcost.pi4",
                     WORK / "tcpcost.img", builder(COST_HI))[2]
        out[tag] = (hi - lo) / float((COST_HI - COST_LO) * COST_SEG)
        print("  %-8s %d segments %12d instructions" % (tag, COST_LO, lo))
        print("  %-8s %d segments %12d instructions" % (tag, COST_HI, hi))

    gross = out["library"]
    harness = out["harness"]
    net = gross - harness
    print()
    print("  instructions per received octet")
    print("    measured slope, library + harness   %8.2f" % gross)
    print("    the harness's own frame copy        %8.2f" % harness)
    print("    THE LIBRARY'S RECEIVE PATH          %8.2f" % net)
    print()
    print("  A full %d-octet segment therefore costs about %d instructions"
          % (COST_SEG, int(net * COST_SEG)))
    print("  in the receive path, and the board's per-segment service time")
    print("  is what the round trip is made of at this window size.")
    print()
    print("  THIS IS AN INSTRUCTION COUNT AND NOT A TIME.  The interpreter")
    print("  models no pipeline, no cache and no memory system.  It is the")
    print("  right instrument for a change that removes instructions and")
    print("  the wrong one for a change that removes stalls.")
    return 0


def build_script() -> tuple[Script, dict, dict]:
    """The whole run, in order.

    Returns the script, a name->index map, and a small book of facts the
    checker needs that are easier to state here than to recompute:
    which injected records were expected to match a socket at all."""
    s = Script()
    at: dict[str, int] = {}
    book: dict[str, object] = {"matched": 0}
    # The late groups at the end each begin with a NetInit of their own,
    # which resets every counter the main run's cross-check reads.  This
    # goes False there so `matched` stays the main run's number.
    counting = [True]

    def a(name, *args, **kw):
        at[name] = s.add(*args, **kw)

    def inject(name, label, frame, patch=0, delta=0, matched=True):
        if matched and counting[0]:
            book["matched"] = book["matched"] + 1
        a(name, OP_INJECT, label, c=patch, d=delta, blob=frame)

    def peer(sport, seq, ack, flags, window, payload=b"", options=b"",
             ident=0x4000, dport=0, tomac=None):
        """A frame from the peer to us.  The destination port and the
        acknowledgment field are placeholders whenever PATCH_DPORT and
        PATCH_ACK_ISS are used - both name values the LIBRARY chose - and
        the harness rewrites them and re-sums the segment.  A frame aimed
        at a LISTENER needs neither, because the gate chose that port.

        `tomac` is the hardware address the frame is ADDRESSED to, and it
        defaults to the cable's because almost every case here is on the
        cable.  The radio holds a MAC of its own, and net.pbi checks an
        arriving frame's destination against the row for the kind it
        arrived on - so a frame for the radio has to carry the radio's
        address or the stack will correctly ignore it."""
        return tcp_frame(OUR_MAC if tomac is None else tomac,
                         PEER_MAC, PEER_IP, OUR_IP,
                         tcp_seg(sport, dport, seq, ack, flags, window,
                                 payload, options), ident)

    # ---- configure -------------------------------------------------
    a("reset", OP_RESET, "NetInit + TcpInit")
    a("setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("setip", OP_SETIP, "NetSetIPv4 192.168.1.50/24 gw .1",
      a=OUR_IP, b=MASK, c=GW_IP)
    a("arpset", OP_ARPSET, "pin the peer's hardware address",
      a=PEER_IP, blob=PEER_MAC)

    # ---- 6. THE WIDTH RULE, first because it needs no state ---------
    for i, (x, y, _lt, _gt, _le, _why) in enumerate(SEQ_PAIRS):
        a("seq%d" % i, OP_SEQ, "TcpSeq*($%08X, $%08X)" % (x, y), a=x, b=y)

    # ---- the clock itself, before anything depends on it ------------
    a("spin", OP_SPIN, "burn one real millisecond of CNTPCT_EL0",
      a=CNTFRQ // 1000)

    # =================================================================
    #  1. THE THREE-WAY HANDSHAKE, on socket LAST_SOCKET
    # =================================================================
    # THE LAST SOCKET ON PURPOSE.  TcpPoll's table walk leaves socket
    # #TCP_SOCKETS-1 current, so a segment for a connection that does not
    # exist is answered with TcpSendRstFor running on THIS socket's
    # working globals.  Parking the live connection here is what makes
    # case 4b's save/restore a real test instead of a coincidence.
    a("use3", OP_USE, "TcpUse(%d), the last socket" % LAST_SOCKET, a=LAST_SOCKET)
    a("connect3", OP_CONNECT, "TcpConnect(192.168.1.20, 80)",
      a=PEER_IP, b=80)
    a("state3_syn", OP_STATE, "SYN-SENT after an active open")
    inject("synack3", "the peer's SYN-ACK, MSS 1460, window 8192",
           peer(80, P_MAIN, 0, SYN | ACK, 8192, options=MSS_OPTION),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("mss3", OP_MSS, "SND.MSS, RCV.WND and RTO once established")

    # =================================================================
    #  2. A DATA EXCHANGE
    # =================================================================
    a("send3a", OP_SEND, "TcpSend, twenty octets", blob=D_FIRST)
    inject("ack3a", "the peer acknowledges all twenty",
           peer(80, P_MAIN + 1, 0, ACK, 8192),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=21)
    a("mss3b", OP_MSS, "the RTO after a round-trip measurement")
    a("send3b", OP_SEND, "TcpSend again - SND.UNA must have moved",
      blob=D_AGAIN)
    inject("data3", "twelve octets in, acknowledging our five",
           peer(80, P_MAIN + 1, 0, ACK, 8192, payload=D_IN),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=26)
    a("read3", OP_READ, "TcpRead - the exact octets, in order", a=64)

    # =================================================================
    #  3. A RETRANSMISSION AFTER A DROPPED SEGMENT
    # =================================================================
    a("counts_pre", OP_COUNTS, "the counters before anything is lost")
    a("send3c", OP_SEND, "twenty octets that will never be acknowledged",
      blob=D_LOST)
    a("mss3c", OP_MSS, "RTO before the timer fires")
    a("warp_rto", OP_WARP, "past #TCP_RTO_INIT_MS", a=RTO_INIT + 100)
    a("tick_rto", OP_TICK, "TcpPoll with no frame - the timer must fire")
    a("counts_post", OP_COUNTS, "tcp_retrans must have moved")
    a("mss3d", OP_MSS, "the RTO must have DOUBLED (RFC 6298 5.5)")
    a("warp_karn", OP_WARP, "another 500 ms before the acknowledgment",
      a=500)
    inject("ack3c", "the peer finally acknowledges the retransmission",
           peer(80, P_MAIN + 13, 0, ACK, 8192),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=46)
    a("mss3e", OP_MSS, "KARN: no sample may be taken from that ACK")

    # =================================================================
    #  4b. A RST FOR A PORT NOBODY HAS OPEN, WITHOUT DISTURBING THE
    #      CONNECTION THAT IS UP
    # =================================================================
    inject("stranger", "a SYN from 192.168.1.77 to port 9999",
           tcp_frame(OUR_MAC, STRANGER_MAC, STRANGER_IP, OUR_IP,
                     tcp_seg(5000, 9999, STRANGER_SEQ, 0, SYN, 1024),
                     0x5000),
           matched=False)
    a("state3_after_rst", OP_STATE,
      "the live connection must be untouched by that")
    a("send3d", OP_SEND, "and its next segment must still be ITS segment",
      blob=D_UNDIST)
    inject("ack3d", "acknowledged",
           peer(80, P_MAIN + 13, 0, ACK, 8192),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=52)

    # =================================================================
    #  9. A PASSIVE OPEN, on socket 2
    # =================================================================
    a("use2", OP_USE, "TcpUse(2)", a=2)
    a("listen2", OP_LISTEN, "TcpListen(8000)", a=8000)
    a("state2_listen", OP_STATE, "LISTEN")
    inject("syn_in", "a SYN arriving for the listener, MSS 1460",
           peer(40000, P_LISTEN, 0, SYN, 5840, options=MSS_OPTION,
                ident=0x6000, dport=8000))
    inject("ack_in", "the third leg of the handshake",
           peer(40000, P_LISTEN + 1, 0, ACK, 5840, ident=0x6001,
                dport=8000),
           patch=PATCH_ACK_ISS, delta=1)
    a("state2_est", OP_STATE, "ESTABLISHED by a passive open")
    a("abort2", OP_ABORT, "TcpAbort - a RST, and the listener re-arms")
    a("state2_relisten", OP_STATE, "back to LISTEN with no reflash")
    a("close2", OP_CLOSE, "TcpClose on a listener frees the socket")
    a("state2_closed", OP_STATE, "CLOSED")

    # =================================================================
    #  5. A FIN CLOSE, ALL THE WAY TO CLOSED
    # =================================================================
    a("use3b", OP_USE, "back to the live connection", a=LAST_SOCKET)
    a("close3", OP_CLOSE, "TcpClose - the FIN goes out")
    a("state3_fw1", OP_STATE, "FIN-WAIT-1")
    inject("finack3", "the peer acknowledges our FIN",
           peer(80, P_MAIN + 13, 0, ACK, 8192),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=53)
    inject("peerfin3", "and then sends its own FIN",
           peer(80, P_MAIN + 13, 0, FIN | ACK, 8192),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=53)
    a("warp_msl", OP_WARP, "2*MSL of emulated time", a=TIMEWAIT_MS + 1)
    a("tick_msl", OP_TICK, "TIME-WAIT must expire into CLOSED")
    a("state3_closed", OP_STATE, "CLOSED, and not by a reset")

    # The ARP entry pinned at the top of the run is twenty seconds old by
    # default and four minutes of warp has just gone past it.  Pin it
    # again; net.pi4's expiry is a64_net_check.py's business, not this
    # gate's, and a #NET_TCP_E_ARP here would be this gate's own fault.
    a("arpset2", OP_ARPSET, "re-pin the peer after 2*MSL of warp",
      a=PEER_IP, blob=PEER_MAC)

    # =================================================================
    #  7. THE SOCKET TABLE - two connections, driven alternately
    # =================================================================
    a("use0", OP_USE, "TcpUse(0)", a=0)
    a("connect0", OP_CONNECT, "TcpConnect(peer, 8080)", a=PEER_IP, b=8080)
    a("use1", OP_USE, "TcpUse(1)", a=1)
    a("connect1", OP_CONNECT, "TcpConnect(peer, 8081)", a=PEER_IP, b=8081)
    a("use0b", OP_USE, "TcpUse(0)", a=0)
    inject("synack0", "socket 0's SYN-ACK",
           peer(8080, P_S0, 0, SYN | ACK, 8192, options=MSS_OPTION,
                ident=0x7000),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("use1b", OP_USE, "TcpUse(1)", a=1)
    inject("synack1", "socket 1's SYN-ACK",
           peer(8081, P_S1, 0, SYN | ACK, 8192, options=MSS_OPTION,
                ident=0x7001),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("use0c", OP_USE, "TcpUse(0)", a=0)
    a("send0", OP_SEND, "sixteen octets on socket 0", blob=D_S0_OUT)
    a("use1c", OP_USE, "TcpUse(1)", a=1)
    a("send1", OP_SEND, "sixteen octets on socket 1", blob=D_S1_OUT)
    a("use0d", OP_USE, "TcpUse(0)", a=0)
    inject("data0", "sixteen octets in for socket 0",
           peer(8080, P_S0 + 1, 0, ACK, 8192, payload=D_S0_IN,
                ident=0x7002),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=17)
    a("use1d", OP_USE, "TcpUse(1)", a=1)
    inject("data1", "sixteen octets in for socket 1",
           peer(8081, P_S1 + 1, 0, ACK, 8192, payload=D_S1_IN,
                ident=0x7003),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=17)
    a("use0e", OP_USE, "TcpUse(0)", a=0)
    a("read0", OP_READ, "socket 0's ring", a=64)
    a("use1e", OP_USE, "TcpUse(1)", a=1)
    a("read1", OP_READ, "socket 1's ring", a=64)
    a("use0f", OP_USE, "TcpUse(0)", a=0)
    a("read0_again", OP_READ, "socket 0 has nothing left", a=64)

    # =================================================================
    #  10. BOUNDED OUT-OF-ORDER REASSEMBLY, on socket 0
    # =================================================================
    a("ooo_pre", OP_OOO, "the reassembly counters before the hole")
    inject("ooo_second", "eight octets EIGHT AHEAD of RCV.NXT",
           peer(8080, P_S0 + 25, 0, ACK, 8192, payload=D_OOO_2,
                ident=0x7004),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=17)
    a("ooo_mid", OP_OOO, "one segment queued, none delivered")
    inject("ooo_first", "the octets that fill the hole",
           peer(8080, P_S0 + 17, 0, ACK, 8192, payload=D_OOO_1,
                ident=0x7005),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=17)
    a("ooo_post", OP_OOO, "and the queued segment is delivered behind it")
    a("read_ooo", OP_READ, "sixteen octets, IN ORDER", a=64)
    a("mss0", OP_MSS, "the window the acceptability edge is measured from")

    # =================================================================
    #  11. THE ACCEPTABILITY EDGE, FROM BOTH SIDES
    # =================================================================
    # RCV.NXT is P_S0+33 and RCV.WND is RCVBUF-32 at this point, so the
    # last acceptable sequence number is P_S0+RCVBUF and the first
    # unacceptable one is P_S0+RCVBUF+1.  Both are exercised; a `<` turned
    # into a `<=` moves tcp_unacceptable and tcp_ooo_queued in opposite
    # directions.
    a("edge_pre", OP_COUNTS2, "the duplicate-ACK and refusal counters")
    inject("edge_in", "one octet at the LAST acceptable sequence number",
           peer(8080, P_S0 + RCVBUF, 0, ACK, 8192, payload=b"I",
                ident=0x7006),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=17)
    inject("edge_out", "one octet ONE PAST the right edge",
           peer(8080, P_S0 + RCVBUF + 1, 0, ACK, 8192, payload=b"X",
                ident=0x7007),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=17)
    a("edge_post", OP_COUNTS2, "exactly one refusal, and one more dupack")
    a("edge_ooo", OP_OOO, "and exactly one more segment queued")

    # =================================================================
    #  4a. A RST ON AN ESTABLISHED CONNECTION
    # =================================================================
    a("use1f", OP_USE, "TcpUse(1)", a=1)
    inject("rst_in", "the peer resets socket 1",
           peer(8081, P_S1 + 17, 0, RST, 0, ident=0x7008),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=17)
    a("state1_reset", OP_STATE, "CLOSED, latched as a RESET")
    a("use0g", OP_USE, "TcpUse(0)", a=0)
    a("state0_alive", OP_STATE, "socket 0 must not have noticed")

    # =================================================================
    #  8. THE LINK CEILING, AND IT IS THE RADIO'S
    # =================================================================
    # THIS GROUP IS THE ONE THAT IS NOT ON THE CABLE, and it says so in
    # the only way that means anything: net.pbi holds an address row and
    # an ARP cache per #HW_LINK_* kind and tcp.pi4 latches one kind into
    # tcp_kind alongside the peer, so "over the radio" is a fact about the
    # connection rather than a remark in a label.  The radio is therefore
    # given an identity of its OWN here and the fixture link is told it is
    # the radio, so that the connection is opened on #HW_LINK_WIFI, its
    # replies arrive on #HW_LINK_WIFI, and tcp.pi4 re-latches the same
    # kind from NetRxKind() rather than quietly moving the connection
    # back onto the cable between its SYN and its SYN-ACK.
    #
    # THE RADIO'S ADDRESS IS THE SAME 192.168.1.50 AND ITS MAC IS NOT,
    # deliberately.  Holding the IP still keeps every other byte of every
    # graded frame in this group identical - the ceiling, the MSS and the
    # segmentation are what this group is about - while the DIFFERENT
    # hardware address makes the source MAC the one field that can only
    # be right if the radio's row was the row that built the frame.  A
    # stack that ignored the kind and used the cable's row would emit
    # 02:00:4D:46:00:01 here and be caught by the byte-exact compare.
    a("radio_mac", OP_SETMAC, "the radio's own hardware address, on the "
      "radio's row", d=HW_LINK_WIFI, blob=RADIO_MAC)
    a("radio_ip", OP_SETIP, "and 192.168.1.50/24 on that row too",
      a=OUR_IP, b=MASK, c=GW_IP, d=HW_LINK_WIFI)
    a("radio_arp", OP_ARPSET, "pin the peer in the radio's ARP cache",
      a=PEER_IP, blob=PEER_MAC, d=HW_LINK_WIFI)
    a("radio_link", OP_LINKKIND,
      "the fixture link IS the radio from here on", a=HW_LINK_WIFI)
    a("use2b", OP_USE, "TcpUse(2)", a=2)
    a("txmax", OP_TXMAX, "LinkTxMaxOn() becomes 1136 - the radio's number",
      a=RADIO_FRAME)
    a("connect2", OP_CONNECT,
      "TcpConnect(#HW_LINK_WIFI, peer, 7000) - over the radio",
      a=PEER_IP, b=7000, d=HW_LINK_WIFI)
    inject("synack2", "the peer offers an MSS of 1460 anyway",
           peer(7000, P_CEIL, 0, SYN | ACK, 65535, options=MSS_OPTION,
                ident=0x8000, tomac=RADIO_MAC),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("mss2", OP_MSS, "SND.MSS must be the LINK's 1082, not the peer's 1460")
    a("bulk", OP_SEND, "three thousand octets down a 1136-octet link",
      blob=BULK)
    a("txmax_back", OP_TXMAX, "back to Ethernet", a=1514)
    a("radio_link_back", OP_LINKKIND,
      "and the fixture link is the cable again", a=HW_LINK_WIRED)

    # ---- the instrumentation ----------------------------------------
    a("counts_final", OP_COUNTS, "segments in, segments out, retransmissions")
    a("counts2_final", OP_COUNTS2, "duplicate ACKs, resets sent, refusals")

    # =================================================================
    #  THE LATE GROUPS.  EACH BEGINS WITH A NetInit OF ITS OWN, which
    #  resets every counter the cross-check above reads, so nothing
    #  after this line may assert a counter belonging to the main run.
    #  Each group is therefore free to read tcp_probes, tcp_dropped and
    #  tcp_keeps from zero, which is what makes them legible.
    # =================================================================
    book["late_start"] = len(s.labels)
    counting[0] = False

    def hbpeer(sport, seq, ack, flags, window, payload=b"", options=b"",
               ident=0x9000, dport=0):
        return tcp_frame(OUR_MAC, PEER_MAC, HB_PEER_IP, HB_OUR_IP,
                         tcp_seg(sport, dport, seq, ack, flags, window,
                                 payload, options), ident)

    # =================================================================
    #  12. THE HIGH-BIT ADDRESS REGRESSION - 2026-09-04
    # =================================================================
    # FOUND BY THIS GATE on 2026-09-04 and CONFIRMED ON SILICON THE SAME
    # EVENING, on the bench Pi 4 over Wi-Fi: `http get
    # http://example.com/` - 172.66.147.243, bit 31 set - reported that
    # the connection was never established, and `tcp status` showed
    # eight segments out, three retransmissions and FOUR RESETS SENT TO
    # A CLOSED PORT, the board resetting its own connection once per
    # SYN-ACK.  The cause was `Global tcp_rip.l` in tcp.pi4: an IPv4
    # address with bit 31 set was stored SIGN-EXTENDED and never again
    # equalled the unsigned value net.pi4's NetTcpRxFrom() hands back,
    # so tcp_Match found nothing and TcpInput answered from its
    # no-connection path.
    #
    # A BENCH ON 10.0.0.0/8 WOULD NOT HAVE FOUND IT and did not, for as
    # long as this file existed.  That is why the bench above is
    # 192.168.x.x and why this group uses 172.20.0.20 - a second
    # high-bit prefix, so the property is asserted twice over.
    #
    # WHAT THIS GROUP PROVES, and it is the second half that matters:
    # not merely that the segments carry the address (byte-exact
    # grading does that anywhere), but that tcp_Match FOUND THE SOCKET -
    # ESTABLISHED, TcpPeerIp() unsigned, data delivered both ways, NOT
    # ONE RST on the link and tcp_norst still 0.
    a("hb_reset", OP_RESET, "NetInit + TcpInit, into the 172.20 bench")
    a("hb_setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("hb_setip", OP_SETIP, "NetSetIPv4 172.20.0.50/12",
      a=HB_OUR_IP, b=HB_MASK, c=HB_GW_IP)
    a("hb_arpset", OP_ARPSET, "pin 172.20.0.20", a=HB_PEER_IP,
      blob=PEER_MAC)
    a("hb_use", OP_USE, "TcpUse(0)", a=0)
    a("hb_connect", OP_CONNECT, "TcpConnect(172.20.0.20, 80) - $AC140014",
      a=HB_PEER_IP, b=80)
    inject("hb_synack", "the SYN-ACK from a peer whose bit 31 is set",
           hbpeer(80, HB_PEER_ISN, 0, SYN | ACK, 8192, options=MSS_OPTION),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("hb_state", OP_STATE, "ESTABLISHED - tcp_Match found the socket")
    a("hb_peer", OP_PEER, "TcpPeerIp() must read back UNSIGNED")
    a("hb_send", OP_SEND, "twenty octets to the high-bit peer",
      blob=D_HB_OUT)
    inject("hb_data", "eighteen octets back, acknowledging ours",
           hbpeer(80, HB_PEER_ISN + 1, 0, ACK, 8192, payload=D_HB_IN,
                  ident=0x9001),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=21)
    a("hb_read", OP_READ, "TcpRead - the exact octets", a=64)
    a("hb_norst", OP_COUNTS3, "tcp_norst MUST still be 0")

    # =================================================================
    #  13. THE ZERO-WINDOW PERSIST TIMER (RFC 9293 3.8.6.1, MUST-36)
    # =================================================================
    # The deadlock nothing else breaks.  With SND.WND 0 there is nothing
    # outstanding, so the retransmission timer never runs; if the
    # window-update ACK is lost, the receiver believes it has told us to
    # carry on and we believe we must wait.  Both sides then wait
    # forever.  A probe is the only way out.
    a("zw_reset", OP_RESET, "NetInit + TcpInit")
    a("zw_setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("zw_setip", OP_SETIP, "NetSetIPv4 192.168.1.50/24",
      a=OUR_IP, b=MASK, c=GW_IP)
    a("zw_arpset", OP_ARPSET, "pin the peer", a=PEER_IP, blob=PEER_MAC)
    a("zw_use", OP_USE, "TcpUse(0)", a=0)
    a("zw_connect", OP_CONNECT, "TcpConnect(peer, 80)", a=PEER_IP, b=80)
    inject("zw_synack", "the peer's SYN-ACK, window 8192",
           peer(80, P_ZW, 0, SYN | ACK, 8192, options=MSS_OPTION,
                ident=0xA000),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("zw_send_open", OP_SEND, "eight octets while the window is open",
      blob=D_ZW_OPEN)
    # THE ACK MUST ADVANCE SND.UNA or the window update never happens:
    # TcpAckArm returns early on a duplicate ACK, before the WL1/WL2
    # guard, exactly as 3.10.7.4 says it should.  A bare duplicate ACK
    # carrying window 0 would be ignored and this case would be vacuous.
    inject("zw_close", "acknowledged, AND THE WINDOW SHUTS TO ZERO",
           peer(80, P_ZW + 1, 0, ACK, 0, ident=0xA001),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=9)
    a("zw_send_held", OP_SEND, "twenty-one octets into a closed window",
      blob=D_ZW_HELD)
    a("zw_arm", OP_TICK, "the first poll ARMS the persist timer")
    a("zw_state_arm", OP_ZWIN, "armed, at max(RTO, 1000 ms), window 0")
    a("zw_warp", OP_WARP, "past the persist interval", a=PERSIST_MIN + 100)
    a("zw_probe", OP_TICK, "and ONE OCTET is probed at SND.NXT")
    a("zw_state_probe", OP_ZWIN, "still armed, and the interval DOUBLED")
    a("zw_counts", OP_COUNTS3, "tcp_zerowin 1, tcp_probes 1")
    inject("zw_open", "the window reopens and the rest goes out at once",
           peer(80, P_ZW + 1, 0, ACK, 8192, ident=0xA002),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=10)
    a("zw_state_open", OP_ZWIN, "disarmed, window 8192")

    # =================================================================
    #  14. TcpDropEvery - A DELIBERATELY LOST SEGMENT
    # =================================================================
    # The only way to prove the retransmit path FIRES rather than to
    # reason that it would: a kernel socket on the far end cannot be
    # made to withhold an acknowledgment.  The two halves of this case
    # are equally important - the segment really is lost, and THE
    # RETRANSMISSION IS NOT.  A harness that dropped the retransmissions
    # too would be testing backoff and would never let the transfer end.
    a("dr_reset", OP_RESET, "NetInit + TcpInit")
    a("dr_setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("dr_setip", OP_SETIP, "NetSetIPv4 192.168.1.50/24",
      a=OUR_IP, b=MASK, c=GW_IP)
    a("dr_arpset", OP_ARPSET, "pin the peer", a=PEER_IP, blob=PEER_MAC)
    a("dr_use", OP_USE, "TcpUse(0)", a=0)
    a("dr_connect", OP_CONNECT, "TcpConnect(peer, 80)", a=PEER_IP, b=80)
    inject("dr_synack", "the peer's SYN-ACK",
           peer(80, P_DROP, 0, SYN | ACK, 8192, options=MSS_OPTION,
                ident=0xB000),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("dr_arm", OP_DROP, "TcpDropEvery(1) - lose EVERY data segment", a=1)
    a("dr_send", OP_SEND, "twenty octets that never reach the link",
      blob=D_DROPPED)
    a("dr_counts_lost", OP_COUNTS4, "tcp_dropped must be 1")
    a("dr_warp", OP_WARP, "past #TCP_RTO_INIT_MS", a=RTO_INIT + 100)
    a("dr_retrans", OP_TICK, "and the RETRANSMISSION is NOT dropped")
    a("dr_counts_rx", OP_COUNTS4, "tcp_dropped is STILL 1")
    a("dr_counts_re", OP_COUNTS, "tcp_retrans 1")
    a("dr_disarm", OP_DROP, "TcpDropEvery(0) - the injector goes back off",
      a=0)
    inject("dr_ack", "the peer acknowledges what finally arrived",
           peer(80, P_DROP + 1, 0, ACK, 8192, ident=0xB001),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=21)
    a("dr_state", OP_STATE, "ESTABLISHED, and the transfer completed")

    # =================================================================
    #  15. THE KEEPALIVE (RFC 9293 3.8.4, RFC 1122 4.2.3.6)
    # =================================================================
    # OFF unless the application asks (MUST-24) and 0 is the default, so
    # this group has to arm it.  A probe is a DELIBERATELY WRONG
    # segment at SND.NXT-1: the peer answers with an ACK naming a byte
    # it has already had, which costs nothing and proves the far end and
    # every NAT in between are still there.  SND.NXT would be an
    # ordinary bare ACK and some middleboxes do not count it as traffic.
    a("ka_reset", OP_RESET, "NetInit + TcpInit")
    a("ka_setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("ka_setip", OP_SETIP, "NetSetIPv4 192.168.1.50/24",
      a=OUR_IP, b=MASK, c=GW_IP)
    a("ka_arpset", OP_ARPSET, "pin the peer", a=PEER_IP, blob=PEER_MAC)
    a("ka_use", OP_USE, "TcpUse(0)", a=0)
    a("ka_connect", OP_CONNECT, "TcpConnect(peer, 80)", a=PEER_IP, b=80)
    inject("ka_synack", "the peer's SYN-ACK",
           peer(80, P_KEEP, 0, SYN | ACK, 8192, options=MSS_OPTION,
                ident=0xC000),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
    a("ka_off", OP_KEEP, "TcpKeepalive(0) is off, and 0 is the default", a=0)
    a("ka_on", OP_KEEP, "TcpKeepalive(10 seconds)", a=KEEP_IDLE_S)
    a("ka_warp0", OP_WARP, "nine seconds of idle", a=KEEP_IDLE_S * 1000 - 1000)
    a("ka_early", OP_TICK, "nine seconds of idle is not ten")
    a("ka_warp1", OP_WARP, "past the idle time", a=1100)
    a("ka_probe1", OP_TICK, "the first probe, at SND.NXT-1")
    a("ka_warp2", OP_WARP, "one probe interval", a=KEEP_INTVL + 100)
    a("ka_probe2", OP_TICK, "the second probe")
    a("ka_warp3", OP_WARP, "another", a=KEEP_INTVL + 100)
    a("ka_probe3", OP_TICK, "the third and last probe")
    a("ka_counts", OP_COUNTS4, "tcp_keeps must be 3")
    a("ka_warp4", OP_WARP, "and one interval more", a=KEEP_INTVL + 100)
    a("ka_dead", OP_TICK, "three unanswered probes and the peer is gone")
    a("ka_state", OP_STATE, "CLOSED, #NET_TCP_E_TIMEOUT, NOT a reset")

    # =================================================================
    #  16. THE UPLOAD RECEIVER - Anvil/Core/netrecv.pbi
    # =================================================================
    # `net recv <port> <address>` is how an image gets onto this board in
    # seconds instead of the two minutes the serial line costs, and the
    # thing it must never do is write one octet outside the window it was
    # given.  The receiver is compiled into this harness (see THE UPLOAD
    # RECEIVER in the harness text) and driven by the SAME scripted peer
    # as everything above, so what is graded here is the real state
    # machine over the real TCP, with no device model.
    #
    # THE GOOD TRANSFER, in the order a host does it:
    #   arm -> SYN -> ACK -> two data segments -> the peer's FIN.
    # THE FIN IS THE END-OF-FILE MARKER and that is the property this
    # group exists for: nothing on the wire says how long the file is, so
    # a receiver that treated CLOSE-WAIT as anything but "that was all of
    # it" would report a short image as a whole one.
    #
    # Then three things that are each their own kind of wrong:
    #   * the bytes must be AT the address and NOWHERE ELSE;
    #   * the digest must be the digest of THOSE bytes;
    #   * the listener must be GONE afterwards - a second connection to
    #     the same port is refused with a reset.
    def recvinject(name, label, frame, patch=0, delta=0):
        a(name, OP_RECV_STEP, label, c=patch, d=delta, blob=frame)

    def upeer(sport, seq, flags, payload=b"", options=b"", ident=0,
              dport=RECV_PORT):
        return tcp_frame(OUR_MAC, PEER_MAC, PEER_IP, OUR_IP,
                         tcp_seg(sport, dport, seq, 0, flags, 5840,
                                 payload, options), ident)

    a("nr_reset", OP_RESET, "NetInit + TcpInit, a clean table")
    a("nr_setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("nr_setip", OP_SETIP, "NetSetIPv4 192.168.1.50/24",
      a=OUR_IP, b=MASK, c=GW_IP)
    a("nr_arm", OP_RECV_ARM,
      "NetRecvArm(%d, %08X, ceiling %08X)"
      % (RECV_PORT, RECV_BASE, RECV_BASE + len(UPLOAD) - 1),
      a=RECV_PORT, b=RECV_BASE, c=RECV_BASE + len(UPLOAD) - 1)
    recvinject("nr_syn", "a SYN for the receiver's port",
               upeer(40100, P_UP, SYN, options=MSS_OPTION, ident=0xD000))
    recvinject("nr_ack", "the third leg of the handshake",
               upeer(40100, P_UP + 1, ACK, ident=0xD001),
               patch=PATCH_ACK_ISS, delta=1)
    recvinject("nr_d1", "the first twenty octets of the image",
               upeer(40100, P_UP + 1, PSH | ACK, payload=UP_A, ident=0xD002),
               patch=PATCH_ACK_ISS, delta=1)
    recvinject("nr_d2", "the second twenty",
               upeer(40100, P_UP + 21, PSH | ACK, payload=UP_B, ident=0xD003),
               patch=PATCH_ACK_ISS, delta=1)
    recvinject("nr_fin", "the peer closes - THIS is the end of the file",
               upeer(40100, P_UP + 41, FIN | ACK, ident=0xD004),
               patch=PATCH_ACK_ISS, delta=1)
    a("nr_state", OP_RECV_STATE, "#NR_DONE with every octet stored")
    a("nr_mem", OP_RECV_MEM, "read the image back out of DRAM",
      a=RECV_BASE, b=len(UPLOAD) + 8)
    a("nr_hash", OP_RECV_HASH, "SHA-256 of what landed, from the board")
    a("nr_rel", OP_RECV_RELEASE, "NetRecvRelease - the listener is taken away")
    inject("nr_syn2", "a SECOND connection to the same port, after the "
                      "transfer - it must be REFUSED",
           tcp_frame(OUR_MAC, PEER_MAC, PEER_IP, OUR_IP,
                     tcp_seg(40101, RECV_PORT, P_UP2, 0, SYN, 5840,
                             b"", MSS_OPTION), 0xD005))
    a("nr_after", OP_RECV_STATE, "still DONE; nothing was re-armed")

    # ---- THE CEILING, which is the whole safety argument -------------
    # Forty octets are sent into thirty octets of room.  The transfer
    # must stop AT the ceiling - thirty stored, #NR_OVER - and the ten
    # octets past it must still read zero.  A receiver that clamped the
    # first segment but not the second, or that clamped nothing, differs
    # from this one only in memory nobody would look at.
    a("ov_reset", OP_RESET, "NetInit + TcpInit for the ceiling case")
    a("ov_setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("ov_setip", OP_SETIP, "NetSetIPv4 192.168.1.50/24",
      a=OUR_IP, b=MASK, c=GW_IP)
    a("ov_arm", OP_RECV_ARM,
      "NetRecvArm(%d, %08X, ceiling %08X) - thirty octets of room"
      % (OVER_PORT, OVER_BASE, OVER_BASE + OVER_ROOM - 1),
      a=OVER_PORT, b=OVER_BASE, c=OVER_BASE + OVER_ROOM - 1)
    recvinject("ov_syn", "a SYN",
               upeer(40200, P_OV, SYN, options=MSS_OPTION, ident=0xE000,
                     dport=OVER_PORT))
    recvinject("ov_ack", "the third leg",
               upeer(40200, P_OV + 1, ACK, ident=0xE001, dport=OVER_PORT),
               patch=PATCH_ACK_ISS, delta=1)
    recvinject("ov_d1", "twenty octets, which fit",
               upeer(40200, P_OV + 1, PSH | ACK, payload=UP_A, ident=0xE002,
                     dport=OVER_PORT),
               patch=PATCH_ACK_ISS, delta=1)
    recvinject("ov_d2", "twenty more, of which only ten may be written",
               upeer(40200, P_OV + 21, PSH | ACK, payload=UP_B, ident=0xE003,
                     dport=OVER_PORT),
               patch=PATCH_ACK_ISS, delta=1)
    a("ov_state", OP_RECV_STATE, "#NR_OVER, stopped at the ceiling")
    a("ov_mem", OP_RECV_MEM,
      "the thirty stored octets AND the ten past the ceiling",
      a=OVER_BASE, b=len(UPLOAD))
    a("ov_rel", OP_RECV_RELEASE, "the refused transfer is reset, not left open")

    # =================================================================
    #  17. THE RECEIVE RING WRAPS - and the copy that crosses the seam
    # =================================================================
    # WHY THIS GROUP EXISTS. Until 2026-09-07 TcpRcvPush and TcpRead
    # walked the ring one octet at a time and masked the index on every
    # one of them, so the wrap was not a case - it was every iteration,
    # and any test at all covered it. They copy in RUNS now, with the
    # wrap decided once per run, and a run-based ring copy has a shape
    # the old one did not: a length that is right for the flat case and
    # wrong at the seam writes straight past the end of one socket's ring
    # and into the next socket's. Nothing else in this file would notice,
    # because no other group moves #TCP_RCVBUF octets through one socket.
    #
    # WHAT IS DRIVEN. Segments in, each read straight back out, until
    # more than #TCP_RCVBUF octets in total have been through the ring -
    # so the write pointer AND the read pointer each cross zero. Every
    # read is compared octet for octet with what was sent.
    #
    # THE LENGTHS ARE NOT ALL THE SAME, AND THAT IS THE SECOND POINT.
    # tcp_Move takes the widest access the two addresses allow, so the
    # rung it lands on is a property of the OFFSETS, not of the code. A
    # ring walked in equal 1460-octet steps would sit on a multiple of
    # four for ever and the 2- and 1-octet rungs would never execute.
    # Three odd lengths early on push every later offset through all four
    # residues, and the alignment rule is armed in this interpreter, so a
    # rung that reaches for a width its address cannot take is an
    # Alignment fault here rather than a dead board on the bench.
    a("wrap_reset", OP_RESET, "NetInit + TcpInit for the ring-wrap group")
    a("wrap_setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("wrap_setip", OP_SETIP, "NetSetIPv4 192.168.1.50/24",
      a=OUR_IP, b=MASK, c=GW_IP)
    a("wrap_arp", OP_ARPSET, "pin the peer", a=PEER_IP, blob=PEER_MAC)
    a("wrap_use", OP_USE, "TcpUse(0)", a=0)
    a("wrap_connect", OP_CONNECT, "TcpConnect(peer, 9100)",
      a=PEER_IP, b=9100)
    inject("wrap_synack", "the peer completes the handshake",
           peer(9100, P_WRAP, 0, SYN | ACK, 8192, options=MSS_OPTION,
                ident=0x9000),
           patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)

    seq = P_WRAP + 1
    for k, ln in enumerate(WRAP_LENS):
        body = wrap_body(k, ln)
        inject("wrap_in%d" % k,
               "%d octets in, ring offset %d"
               % (ln, sum(WRAP_LENS[:k]) % RCVBUF),
               peer(9100, seq, 0, ACK, 8192, payload=body,
                    ident=0x9010 + k),
               patch=PATCH_DPORT | PATCH_ACK_ISS, delta=1)
        a("wrap_out%d" % k, OP_READ, "and the same %d octets back" % ln,
          a=ln)
        seq += ln

    return s, at, book


# =====================================================================
#  THE ASSERTIONS
# =====================================================================
def expect(cond, what, fails):
    if not cond:
        fails.append(what)


def hexdiff(got: bytes, want: bytes) -> str:
    if len(got) != len(want):
        return "length %d, wanted %d\n        got  %s\n        want %s" % (
            len(got), len(want), got.hex(), want.hex())
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            return ("first difference at offset %d (%s): got $%02X, "
                    "wanted $%02X\n        got  %s\n        want %s"
                    % (i, field_at(i), g, w, got.hex(), want.hex()))
    return ""


def field_at(off: int) -> str:
    """Name the octet a byte-exact compare tripped on, so a failure says
    'the window' rather than 'offset 48'."""
    names = [
        (0, 6, "destination MAC"), (6, 12, "source MAC"),
        (12, 14, "EtherType"), (14, 15, "IP version/IHL"),
        (16, 18, "IP total length"), (18, 20, "IP identification"),
        (20, 22, "IP flags/fragment"), (22, 23, "IP TTL"),
        (23, 24, "IP protocol"), (24, 26, "IP header checksum"),
        (26, 30, "IP source"), (30, 34, "IP destination"),
        (34, 36, "TCP source port"), (36, 38, "TCP destination port"),
        (38, 42, "TCP sequence number"), (42, 46, "TCP acknowledgment"),
        (46, 47, "TCP data offset"), (47, 48, "TCP control bits"),
        (48, 50, "TCP window"), (50, 52, "TCP checksum"),
        (52, 54, "TCP urgent pointer"),
    ]
    for lo, hi, name in names:
        if lo <= off < hi:
            return name
    return "TCP options or data at +%d" % (off - 54)


def signed32(v: int) -> int:
    """A result-record extra carries a 32-bit word.  TcpError() is
    negative and TcpState() is not, so only the readings that can be
    negative go through this - a blanket sign-extension would turn an
    IPv4 address with its top bit set into a refusal code."""
    return v - 0x100000000 if v & 0x80000000 else v


def be16(b: bytes, off: int) -> int:
    return struct.unpack(">H", b[off:off + 2])[0]


def be32(b: bytes, off: int) -> int:
    return struct.unpack(">I", b[off:off + 4])[0]


def check(res: list[Result], at: dict, book: dict,
          fails: list[str]) -> None:
    def R(name) -> Result:
        i = at[name]
        if i >= len(res):
            fails.append("%s: the harness never ran this record" % name)
            return Result(0, 0, 0, 0, b"", name)
        return res[i]

    def code(name, want, note=""):
        r = R(name)
        if r.r != want:
            fails.append("%s (%s): returned %d, wanted %d%s"
                         % (name, r.label, r.r, want,
                            "  [" + note + "]" if note else ""))

    def frames(name) -> list[bytes]:
        return R(name).frames()

    def no_frame(name, why=""):
        f = frames(name)
        if f:
            fails.append("%s (%s): put %d frame(s) on the link and should "
                         "have put none.%s  First was %s"
                         % (name, R(name).label, len(f),
                            "  " + why if why else "", f[0].hex()))

    def one_frame(name, why="") -> bytes | None:
        f = frames(name)
        if len(f) != 1:
            fails.append("%s (%s): put %d frames on the link, wanted exactly "
                         "one.%s" % (name, R(name).label, len(f),
                                     "  " + why if why else ""))
            return f[0] if f else None
        return f[0]

    def graded(name, got: bytes | None, sport, dport, seq, ack, flags,
               window, data=b"", options=b"", dstmac=PEER_MAC,
               dstip=PEER_IP, srcip=None, srcmac=OUR_MAC, note=""):
        """Byte-exact, with the IPv4 Identification read out of the frame
        the library produced - it is a counter inside net.pi4 and cannot
        be predicted from here, exactly as a64_net_check.py does.

        `srcmac` defaults to the cable's hardware address.  It is a
        parameter because net.pbi sources the sender's MAC from the row
        of the #HW_LINK_* kind the connection latched, so the radio group
        expects the radio's - and that expectation is the one field in
        those frames that can only be right if the right row was read."""
        if got is None:
            return
        if len(got) < 54:
            fails.append("%s: the frame is only %d octets" % (name, len(got)))
            return
        ident = be16(got, 18)
        want = tcp_frame(dstmac, srcmac,
                         OUR_IP if srcip is None else srcip, dstip,
                         tcp_seg(sport, dport, seq, ack, flags, window,
                                 data, options), ident)
        d = hexdiff(got, want)
        if d:
            fails.append("%s (%s)%s: %s"
                         % (name, R(name).label,
                            "  [" + note + "]" if note else "", d))

    # ---- configuration ---------------------------------------------
    code("reset", 1)
    code("setmac", 1)
    code("setip", 1)
    code("arpset", 1)

    # =================================================================
    #  6. THE WIDTH RULE
    # =================================================================
    for i, (x, y, lt, gt, le, why) in enumerate(SEQ_PAIRS):
        r = R("seq%d" % i)
        if (r.r, r.e1, r.e2) != (lt, gt, le):
            fails.append(
                "seq%d: TcpSeqLt/Gt/Le($%08X, $%08X) gave %d/%d/%d, wanted "
                "%d/%d/%d.  %s.  THE WIDTH RULE at the top of tcp.pi4 says "
                "why: every sequence variable is `.l` so that the difference "
                "is reduced modulo 2**32 before its sign is tested"
                % (i, x, y, r.r, r.e1, r.e2, lt, gt, le, why))

    # ---- the clock -------------------------------------------------
    sp = R("spin")
    expect(900 <= sp.r <= 1200,
           "OP_SPIN burned one millisecond of CNTPCT_EL0 and Micros() moved "
           "%d us, wanted about 1000.  Either the counter is not advancing "
           "with execution or CNTFRQ and the model disagree" % sp.r, fails)
    expect(R("warp_rto").r == RTO_INIT + 100,
           "the warp asked for %d ms and Micros() moved %d"
           % (RTO_INIT + 100, R("warp_rto").r), fails)
    expect(R("warp_msl").r == TIMEWAIT_MS + 1,
           "the 2*MSL warp asked for %d ms and Micros() moved %d"
           % (TIMEWAIT_MS + 1, R("warp_msl").r), fails)

    # =================================================================
    #  1. THE THREE-WAY HANDSHAKE
    # =================================================================
    code("connect3", 0, "#NET_TCP_OK")
    syn = one_frame("connect3", "an active open is exactly one SYN")
    if syn is None or len(syn) < 60:
        fails.append("connect3: no SYN to grade; nothing below it can run")
        return
    lport3 = be16(syn, 34)
    iss3 = be32(syn, 38)
    expect(49152 <= lport3 <= 65535,
           "the ephemeral port is %d; RFC 6335 4.2's Dynamic range is "
           "49152-65535 and tcp.pi4 says it picks from there" % lport3, fails)
    graded("connect3", syn, lport3, 80, iss3, 0, SYN, RCVBUF,
           options=MSS_OPTION,
           note="data offset 6, MSS Kind 2 Length 4 value 1460 BIG-endian, "
                "no ACK bit and an empty acknowledgment field")
    expect(syn[46] == 0x60,
           "the SYN's data offset octet is $%02X, wanted $60 - twenty octets "
           "of header and one four-octet option" % syn[46], fails)
    expect(syn[54:58] == MSS_OPTION,
           "the SYN's options are %s, wanted %s (Kind 2, Length 4, 1460)"
           % (syn[54:58].hex(), MSS_OPTION.hex()), fails)
    code("state3_syn", S_SYN_SENT)

    code("synack3", S_ESTABLISHED, "TcpPoll returns the socket's state")
    expect(R("synack3").e1 == NET_IN_TCP,
           "NetInput returned %d for the SYN-ACK, wanted #NET_IN_TCP (%d).  "
           "A frame net.pi4 refused never reaches the state machine, so "
           "every case below it would be vacuous"
           % (R("synack3").e1, NET_IN_TCP), fails)
    graded("synack3", one_frame("synack3", "a SYN-ACK is answered by one "
                                "bare ACK and nothing else"),
           lport3, 80, iss3 + 1, P_MAIN + 1, ACK, RCVBUF)

    m = R("mss3")
    expect(m.r == MSS_RX, "SND.MSS is %d, wanted 1460 - the peer offered "
           "1460 and Ethernet can carry it" % m.r, fails)
    expect(m.e1 == RCVBUF, "RCV.WND is %d, wanted %d" % (m.e1, RCVBUF), fails)
    expect(m.e2 == RTO_INIT,
           "the RTO is %d ms before any measurement, wanted %d (RFC 6298 "
           "2.1)" % (m.e2, RTO_INIT), fails)

    # =================================================================
    #  2. A DATA EXCHANGE
    # =================================================================
    code("send3a", len(D_FIRST), "TcpSend returns the octets it TOOK")
    graded("send3a", one_frame("send3a"),
           lport3, 80, iss3 + 1, P_MAIN + 1, ACK, RCVBUF, data=D_FIRST,
           note="tcp.pi4's TcpOutput sets ACK and nothing else - there is "
                "no PSH anywhere in that file, and this gate grades what "
                "the source does rather than what a stack usually does")
    no_frame("ack3a", "a pure acknowledgment that empties the pipe needs no "
                      "answer; an unsolicited bare ACK here would be a "
                      "packet storm at line rate")
    expect(R("mss3b").e2 == RTO_INIT,
           "after one round-trip measurement of about zero milliseconds the "
           "RTO is %d, wanted %d - RFC 6298 2.4 rounds anything under a "
           "second up to a second" % (R("mss3b").e2, RTO_INIT), fails)

    code("send3b", len(D_AGAIN))
    graded("send3b", one_frame("send3b"),
           lport3, 80, iss3 + 21, P_MAIN + 1, ACK, RCVBUF, data=D_AGAIN,
           note="THE SEQUENCE NUMBER IS THE PROOF SND.UNA MOVED: it is "
                "ISS+21, so the twenty octets before it are gone from the "
                "ring and are not being re-sent")

    graded("data3", one_frame("data3", "one segment in, one ACK out"),
           lport3, 80, iss3 + 26, P_MAIN + 13, ACK, RCVBUF - len(D_IN),
           note="the advertised window has shrunk by exactly the twelve "
                "octets now sitting in the receive ring")
    rd = R("read3")
    expect(rd.r == len(D_IN) and rd.blob == D_IN,
           "TcpRead returned %d octets %r, wanted %d %r"
           % (rd.r, rd.blob, len(D_IN), D_IN), fails)

    # =================================================================
    #  3. A RETRANSMISSION, AND KARN
    # =================================================================
    expect(R("counts_pre").e2 == 0,
           "tcp_retrans is %d before anything has been lost"
           % R("counts_pre").e2, fails)
    code("send3c", len(D_LOST))
    lost = one_frame("send3c")
    graded("send3c", lost, lport3, 80, iss3 + 26, P_MAIN + 13, ACK,
           RCVBUF - len(D_IN), data=D_LOST)
    expect(R("mss3c").e2 == RTO_INIT,
           "the RTO is %d ms with a segment outstanding, wanted %d"
           % (R("mss3c").e2, RTO_INIT), fails)

    again = one_frame("tick_rto",
                      "the retransmission timer must put back exactly one "
                      "segment - RFC 6298 5.4, 'the earliest segment that "
                      "has not been acknowledged'")
    graded("tick_rto", again, lport3, 80, iss3 + 26, P_MAIN + 13, ACK,
           RCVBUF - len(D_IN), data=D_LOST,
           note="THE SAME OCTETS AT THE SAME SEQUENCE NUMBER")
    if lost and again:
        expect(again[38:42] == lost[38:42],
               "the retransmission went out at sequence number $%08X and the "
               "original at $%08X.  They must be the same number: a "
               "retransmission that moves is a new segment and the peer has "
               "no way to fill the hole"
               % (be32(again, 38), be32(lost, 38)), fails)
        expect(again[54:] == lost[54:],
               "the retransmission's payload differs from the original's",
               fails)
    expect(R("counts_post").e2 == 1,
           "tcp_retrans is %d after one retransmission, wanted 1.  This "
           "counter is the only proof the recovery path FIRED rather than "
           "being reasoned about" % R("counts_post").e2, fails)
    expect(R("mss3d").e2 == 2 * RTO_INIT,
           "the RTO is %d ms after the timer fired, wanted %d.  RFC 6298 "
           "5.5: 'the host MUST set RTO <- RTO * 2'"
           % (R("mss3d").e2, 2 * RTO_INIT), fails)
    no_frame("ack3c", "the acknowledgment empties the pipe and needs no "
                      "answer")
    expect(R("mss3e").e2 == 2 * RTO_INIT,
           "KARN'S ALGORITHM: the RTO is %d ms after an acknowledgment of a "
           "RETRANSMITTED segment, wanted it UNCHANGED at %d.  RFC 6298 3.1: "
           "'TCP MUST NOT use retransmitted segments' for a round-trip "
           "sample.  A stack that sampled this ambiguous 1600 ms would land "
           "near 1801 and its RTO would collapse under loss"
           % (R("mss3e").e2, 2 * RTO_INIT), fails)

    # =================================================================
    #  4b. THE RST FOR A STRANGER, AND THE CONNECTION IT MUST NOT TOUCH
    # =================================================================
    rst = one_frame("stranger", "a segment for a connection that does not "
                                "exist gets exactly one RST")
    graded("stranger", rst, 9999, 5000, 0, STRANGER_SEQ + 1, RST | ACK, 0,
           dstmac=STRANGER_MAC, dstip=STRANGER_IP,
           note="RFC 9293 3.10.7.1: 'If the ACK bit is off, sequence number "
                "zero is used: <SEQ=0><ACK=SEG.SEQ+SEG.LEN><CTL=RST,ACK>'. "
                "SEG.LEN is 1 because the SYN occupies a sequence number, "
                "and a RST carries no window")
    st = R("state3_after_rst")
    expect(st.r == S_ESTABLISHED and st.e1 == 0 and st.e2 == 0,
           "after answering a stranger the live connection is state %d, "
           "error %d, reset-seen %d; wanted ESTABLISHED, 0, 0"
           % (st.r, st.e1, st.e2), fails)
    code("send3d", len(D_UNDIST))
    graded("send3d", one_frame("send3d"),
           lport3, 80, iss3 + 46, P_MAIN + 13, ACK, RCVBUF - len(D_IN),
           data=D_UNDIST,
           note="THIS IS TcpSendRstFor's SAVE AND RESTORE.  The RST above "
                "was built on THIS socket's working globals - tcp_rip, "
                "tcp_rport, tcp_lport, tcp_rmac and tcp_rcv_nxt - because "
                "TcpPoll's table walk leaves the last socket current.  Every "
                "one of those five is re-read here: the peer address, the "
                "hardware address, both ports and the acknowledgment field")
    no_frame("ack3d")

    # =================================================================
    #  9. THE PASSIVE OPEN
    # =================================================================
    code("listen2", 0)
    code("state2_listen", S_LISTEN)
    code("syn_in", S_SYN_RECEIVED)
    synack = one_frame("syn_in", "a SYN to a listener is answered with one "
                                 "SYN-ACK")
    if synack and len(synack) >= 60:
        iss2 = be32(synack, 38)
        graded("syn_in", synack, 8000, 40000, iss2, P_LISTEN + 1, SYN | ACK,
               RCVBUF, options=MSS_OPTION,
               note="a listener needs no ARP at all: the peer's hardware "
                    "address arrived free in the SYN's own frame")
        code("ack_in", S_ESTABLISHED)
        no_frame("ack_in", "the third leg completes the handshake silently")
        code("state2_est", S_ESTABLISHED)
        code("abort2", 0)
        graded("abort2", one_frame("abort2"),
               8000, 40000, iss2 + 1, P_LISTEN + 1, RST, 0,
               note="RFC 9293 3.10.5: 'Send a reset segment "
                    "<SEQ=SND.NXT><CTL=RST>'")
    code("state2_relisten", S_LISTEN,
         "a listener re-arms itself after an abort - that is what "
         "'reconnect without a reflash' means in practice")
    code("close2", 0)
    code("state2_closed", S_CLOSED)

    # =================================================================
    #  5. THE FIN CLOSE
    # =================================================================
    code("close3", 0)
    graded("close3", one_frame("close3"),
           lport3, 80, iss3 + 52, P_MAIN + 13, FIN | ACK, RCVBUF - len(D_IN),
           note="the FIN rides on a segment of its own because the send "
                "ring had already drained")
    code("state3_fw1", S_FIN_WAIT_1)
    code("finack3", S_FIN_WAIT_2,
         "the acknowledgment of our FIN moves SND.UNA past tcp_fin_seq, "
         "which only happens if the FIN occupied a sequence number")
    no_frame("finack3")
    code("peerfin3", S_TIME_WAIT)
    graded("peerfin3", one_frame("peerfin3"),
           lport3, 80, iss3 + 53, P_MAIN + 14, ACK, RCVBUF - len(D_IN) - 1,
           note="RCV.NXT advanced over the peer's FIN, so the advertised "
                "window is one octet smaller than it was")
    code("tick_msl", S_CLOSED,
         "2*MSL has passed and TIME-WAIT must end (RFC 9293 3.6, MUST-13)")
    no_frame("tick_msl")
    tc = R("state3_closed")
    expect(tc.r == S_CLOSED and tc.e2 == 0,
           "after an orderly close the socket is state %d with "
           "TcpWasReset() %d; wanted CLOSED and 0.  An orderly close and a "
           "reset must never look the same from outside"
           % (tc.r, tc.e2), fails)

    # =================================================================
    #  7. THE SOCKET TABLE
    # =================================================================
    code("connect0", 0)
    code("connect1", 0)
    syn0 = one_frame("connect0")
    syn1 = one_frame("connect1")
    if not syn0 or not syn1 or len(syn0) < 60 or len(syn1) < 60:
        fails.append("the two-socket case has no SYNs to work from")
        return
    l0, iss0 = be16(syn0, 34), be32(syn0, 38)
    l1, iss1 = be16(syn1, 34), be32(syn1, 38)
    expect(l0 != l1,
           "both sockets picked local port %d.  tcp.pi4 keeps ONE ephemeral "
           "counter for the whole table precisely so that cannot happen"
           % l0, fails)
    graded("connect0", syn0, l0, 8080, iss0, 0, SYN, RCVBUF,
           options=MSS_OPTION)
    graded("connect1", syn1, l1, 8081, iss1, 0, SYN, RCVBUF,
           options=MSS_OPTION)

    code("synack0", S_ESTABLISHED)
    graded("synack0", one_frame("synack0"),
           l0, 8080, iss0 + 1, P_S0 + 1, ACK, RCVBUF)
    code("synack1", S_ESTABLISHED)
    graded("synack1", one_frame("synack1"),
           l1, 8081, iss1 + 1, P_S1 + 1, ACK, RCVBUF)

    code("send0", len(D_S0_OUT))
    graded("send0", one_frame("send0"),
           l0, 8080, iss0 + 1, P_S0 + 1, ACK, RCVBUF, data=D_S0_OUT)
    code("send1", len(D_S1_OUT))
    graded("send1", one_frame("send1"),
           l1, 8081, iss1 + 1, P_S1 + 1, ACK, RCVBUF, data=D_S1_OUT)

    graded("data0", one_frame("data0"),
           l0, 8080, iss0 + 17, P_S0 + 17, ACK, RCVBUF - 16)
    graded("data1", one_frame("data1"),
           l1, 8081, iss1 + 17, P_S1 + 17, ACK, RCVBUF - 16)

    r0, r1 = R("read0"), R("read1")
    expect(r0.blob == D_S0_IN,
           "socket 0 read %r, wanted %r.  If it read socket 1's text the "
           "park/unpark field list has a hole in it" % (r0.blob, D_S0_IN),
           fails)
    expect(r1.blob == D_S1_IN,
           "socket 1 read %r, wanted %r" % (r1.blob, D_S1_IN), fails)
    code("read0_again", 0, "socket 0's ring must be empty now")

    # =================================================================
    #  10. OUT-OF-ORDER REASSEMBLY
    # =================================================================
    pre = R("ooo_pre")
    expect((pre.r, pre.e1, pre.e2) == (0, 0, 0),
           "the reassembly counters are %d/%d/%d before any hole"
           % (pre.r, pre.e1, pre.e2), fails)
    graded("ooo_second", one_frame("ooo_second"),
           l0, 8080, iss0 + 17, P_S0 + 17, ACK, RCVBUF - 16,
           note="A DUPLICATE ACK, naming RCV.NXT UNCHANGED.  The segment is "
                "held, not acknowledged: queuing changes what we KEEP, not "
                "what we ACKNOWLEDGE (RFC 5681 3.2)")
    mid = R("ooo_mid")
    expect((mid.r, mid.e1, mid.e2) == (1, 0, 0),
           "after one out-of-order segment the counters are %d queued, %d "
           "delivered, %d dropped; wanted 1/0/0"
           % (mid.r, mid.e1, mid.e2), fails)
    graded("ooo_first", one_frame("ooo_first"),
           l0, 8080, iss0 + 17, P_S0 + 33, ACK, RCVBUF - 32,
           note="ONE acknowledgment naming the FURTHEST RCV.NXT reachable: "
                "the queue was drained before the ACK was formed")
    post = R("ooo_post")
    expect((post.r, post.e1, post.e2) == (1, 1, 0),
           "after the hole was filled the counters are %d/%d/%d; wanted "
           "1 queued, 1 delivered, 0 dropped"
           % (post.r, post.e1, post.e2), fails)
    ro = R("read_ooo")
    expect(ro.blob == D_OOO_1 + D_OOO_2,
           "the reassembled octets are %r, wanted %r - in order, with no "
           "duplication and no gap" % (ro.blob, D_OOO_1 + D_OOO_2), fails)

    # =================================================================
    #  11. THE ACCEPTABILITY EDGE
    # =================================================================
    wnd = R("mss0").e1
    expect(wnd == RCVBUF - 32,
           "RCV.WND is %d where this gate's edge arithmetic assumes %d.  The "
           "two edge cases below are built from that number, so fix this "
           "line before reading them" % (wnd, RCVBUF - 32), fails)
    ep, epost = R("edge_pre"), R("edge_post")
    expect(ep.e2 == 0,
           "tcp_unacceptable is %d before the edge cases" % ep.e2, fails)
    graded("edge_in", one_frame("edge_in"),
           l0, 8080, iss0 + 17, P_S0 + 33, ACK, RCVBUF - 32,
           note="one octet at RCV.NXT+RCV.WND-1 is the LAST acceptable "
                "sequence number and must be taken")
    graded("edge_out", one_frame("edge_out"),
           l0, 8080, iss0 + 17, P_S0 + 33, ACK, RCVBUF - 32,
           note="RFC 9293 3.10.7.4: 'If an incoming segment is not "
                "acceptable, an acknowledgment should be sent in reply'")
    expect(epost.e2 == ep.e2 + 1,
           "tcp_unacceptable moved from %d to %d across one acceptable and "
           "one unacceptable segment; wanted exactly one refusal.  A `<` "
           "made `<=` in TcpAcceptable accepts the octet AT the right edge "
           "and this is the only case that says so"
           % (ep.e2, epost.e2), fails)
    expect(epost.r == ep.r + 2,
           "tcp_dupacks moved from %d to %d; wanted two more - one for the "
           "queued segment and one for the refused one"
           % (ep.r, epost.r), fails)
    eo = R("edge_ooo")
    expect((eo.r, eo.e1, eo.e2) == (2, 1, 0),
           "the reassembly counters after the edge cases are %d/%d/%d; "
           "wanted 2 queued (the acceptable octet joined the queue), 1 "
           "delivered, 0 dropped.  A right edge that accepts one octet too "
           "many queues three" % (eo.r, eo.e1, eo.e2), fails)

    # =================================================================
    #  4a. A RST ON AN ESTABLISHED CONNECTION
    # =================================================================
    code("rst_in", S_CLOSED)
    no_frame("rst_in",
             "A RST IS NEVER ANSWERED WITH A RST (RFC 9293 3.5.2, and "
             "3.10.7.1's opening line).  Without that rule two stacks trade "
             "resets forever")
    rr = R("state1_reset")
    rr_err = signed32(rr.e1)
    expect(rr.r == S_CLOSED and rr_err == E_RESET and rr.e2 == 1,
           "after a reset the socket is state %d, TcpError() %d, "
           "TcpWasReset() %d; wanted CLOSED, %d, 1.  CLOSED alone does not "
           "carry the difference between an orderly close and a peer that "
           "pulled the plug, which is the whole of the robustness "
           "requirement" % (rr.r, rr_err, rr.e2, E_RESET), fails)
    code("state0_alive", S_ESTABLISHED,
         "socket 1 was reset; socket 0 must not have noticed")

    # =================================================================
    #  8. THE LINK CEILING, AND IT IS THE RADIO'S
    # =================================================================
    # The radio's own row has to have taken the identity before any of
    # this means anything: a refused NetSetMac, NetSetIPv4 or NetArpSet
    # would leave every frame below missing, which is a legible failure
    # but not the one this group is for.  So the setters are graded
    # first.
    code("radio_mac", 1, "the radio's row must accept a MAC of its own")
    code("radio_ip", 1,
         "and an address of its own - one row per #HW_LINK_* kind is the "
         "whole point, and two rows holding the same IPv4 address on two "
         "different interfaces is a board with two ways to the same "
         "subnet, not an error")
    code("radio_arp", 1, "the radio's ARP cache must take the peer")
    code("radio_link", HW_LINK_WIFI,
         "the fixture link must now BE the radio, or the SYN-ACK would "
         "arrive as wired and tcp.pi4 would re-latch tcp_kind onto the "
         "cable from NetRxKind()")
    code("radio_link_back", HW_LINK_WIRED)
    code("txmax", RADIO_FRAME)
    code("connect2", 0)
    syn2 = one_frame("connect2")
    if syn2 and len(syn2) >= 60:
        l2, iss2b = be16(syn2, 34), be32(syn2, 38)
        graded("connect2", syn2, l2, 7000, iss2b, 0, SYN, RCVBUF,
               options=MSS_OPTION, srcmac=RADIO_MAC,
               note="THE MSS WE ADVERTISE IS STILL 1460 ON A 1136-OCTET "
                    "LINK.  RFC 9293 3.7.1: the option is about our RECEIVE "
                    "path, and both interfaces can receive a full frame.  "
                    "Making it follow the send ceiling is the classic MSS "
                    "bug and presents as a peer that stalls on large replies.  "
                    "AND THE SENDER'S HARDWARE ADDRESS IS THE RADIO'S: this "
                    "connection was opened on #HW_LINK_WIFI and net.pbi "
                    "sources the MAC from that kind's row, so the cable's "
                    "02:00:4D:46:00:01 here would mean the kind was ignored")
        graded("synack2", one_frame("synack2"),
               l2, 7000, iss2b + 1, P_CEIL + 1, ACK, RCVBUF,
               srcmac=RADIO_MAC)
        expect(R("mss2").r == RADIO_MSS,
               "SND.MSS is %d after a peer offered 1460 over a %d-octet "
               "link, wanted %d - TcpTxCap() is LinkTxMaxOn() less the "
               "Ethernet, IPv4 and TCP headers"
               % (R("mss2").r, RADIO_FRAME, RADIO_MSS), fails)
        code("bulk", len(BULK), "TcpSend takes what the ring can hold")
        bf = frames("bulk")
        if len(bf) != 2:
            fails.append(
                "bulk (%s): three thousand octets left in %d segments, "
                "wanted 2 - two full ones of %d and a short tail that Nagle "
                "holds back because something is in flight"
                % (R("bulk").label, len(bf), RADIO_MSS))
        for k, f in enumerate(bf[:2]):
            payload = f[54:]
            expect(len(f) == RADIO_FRAME,
                   "bulk segment %d is a %d-octet frame; LinkTxMaxOn() is %d "
                   "and a frame longer than that is REFUSED by the radio, "
                   "not truncated" % (k, len(f), RADIO_FRAME), fails)
            expect(len(payload) == RADIO_MSS,
                   "bulk segment %d carries %d octets of TCP data, wanted "
                   "%d.  1460 here would mean TcpTxCap() is ignoring "
                   "LinkTxMaxOn()" % (k, len(payload), RADIO_MSS), fails)
            graded("bulk", f, l2, 7000, iss2b + 1 + k * RADIO_MSS,
                   P_CEIL + 1, ACK, RCVBUF, srcmac=RADIO_MAC,
                   data=BULK[k * RADIO_MSS:(k + 1) * RADIO_MSS])

    # ---- the instrumentation, cross-checked -------------------------
    cf = R("counts_final")
    expect(cf.r == book["matched"],
           "tcp_seg_rx is %d and %d injected segments were expected to reach "
           "a socket.  A segment for a connection that does not exist is "
           "answered with a RST and is deliberately NOT counted"
           % (cf.r, book["matched"]), fails)
    # Everything before the late groups' first NetInit, which resets
    # every counter these two lines read.
    total_tx = sum(len(r.frames()) for r in res[:int(book["late_start"])])
    expect(cf.e1 == total_tx,
           "tcp_seg_tx is %d and the link was handed %d frames.  Those must "
           "agree: the counter is incremented in TcpSendSeg immediately "
           "after LinkTxStaged succeeds, so a difference means a frame was "
           "staged without being counted or counted without being staged"
           % (cf.e1, total_tx), fails)
    expect(cf.e2 == 1,
           "tcp_retrans is %d at the end of the run, wanted exactly 1"
           % cf.e2, fails)
    c2 = R("counts2_final")
    expect(c2.e1 == 2,
           "tcp_rst_tx is %d, wanted 2 - one RST for the stranger's SYN and "
           "one from TcpAbort" % c2.e1, fails)

    # =================================================================
    #  12. THE HIGH-BIT ADDRESS REGRESSION - 2026-09-04
    # =================================================================
    # A PERMANENT CASE, not a note.  Found by this gate on 2026-09-04
    # from the desk and confirmed on silicon the same evening: `Global
    # tcp_rip.l` sign-extended every IPv4 address with bit 31 set, so
    # tcp_Match never matched and the board answered its own peer with a
    # RST once per SYN-ACK.  10.0.0.0/8 would not have found it, and for
    # as long as this file was driven on a 10-net nothing did.
    #
    # THE SECOND HALF IS THE POINT.  Byte-exact grading alone would pass
    # on the broken library, because the SYN it sends is correct; it is
    # the INBOUND direction that failed.  So this group asserts that the
    # socket was FOUND: ESTABLISHED, TcpPeerIp() read back unsigned,
    # data delivered in both directions, not one RST on the link and
    # tcp_norst still 0.
    code("hb_setip", 1)
    code("hb_arpset", 1)
    code("hb_connect", 0, "#NET_TCP_OK")
    hbsyn = one_frame("hb_connect", "an active open is exactly one SYN")
    if hbsyn and len(hbsyn) >= 60:
        hbl, hbiss = be16(hbsyn, 34), be32(hbsyn, 38)
        expect(be32(hbsyn, 30) == HB_PEER_IP,
               "the SYN's IPv4 destination is %s ($%08X); wanted %s "
               "($%08X).  An address stored in a `.l` and written back out "
               "through a 32-bit field still LOOKS right on the wire, which "
               "is why this line is not the interesting one"
               % (dotted(be32(hbsyn, 30)), be32(hbsyn, 30),
                  dotted(HB_PEER_IP), HB_PEER_IP), fails)
        graded("hb_connect", hbsyn, hbl, 80, hbiss, 0, SYN, RCVBUF,
               options=MSS_OPTION, dstip=HB_PEER_IP, srcip=HB_OUR_IP)
        code("hb_synack", S_ESTABLISHED,
             "THE REGRESSION.  A peer whose address has bit 31 set must "
             "reach ESTABLISHED.  With `Global tcp_rip.l` back in place "
             "this returns SYN-SENT and the frame below is a RST")
        graded("hb_synack", one_frame("hb_synack",
                                      "a SYN-ACK is answered by one bare "
                                      "ACK - NOT by a reset"),
               hbl, 80, hbiss + 1, HB_PEER_ISN + 1, ACK, RCVBUF,
               dstip=HB_PEER_IP, srcip=HB_OUR_IP)
        code("hb_send", len(D_HB_OUT))
        graded("hb_send", one_frame("hb_send"),
               hbl, 80, hbiss + 1, HB_PEER_ISN + 1, ACK, RCVBUF,
               data=D_HB_OUT, dstip=HB_PEER_IP, srcip=HB_OUR_IP)
        graded("hb_data", one_frame("hb_data", "one segment in, one ACK out"),
               hbl, 80, hbiss + 21, HB_PEER_ISN + 1 + len(D_HB_IN), ACK,
               RCVBUF - len(D_HB_IN), dstip=HB_PEER_IP, srcip=HB_OUR_IP,
               note="the inbound half of the conversation, which is the "
                    "half tcp_Match decides")
    hbst = R("hb_state")
    expect(hbst.r == S_ESTABLISHED and signed32(hbst.e1) == 0
           and hbst.e2 == 0,
           "a peer on %s reached state %d with error %d and reset-seen %d; "
           "wanted ESTABLISHED (%d), 0, 0.  THIS IS THE 2026-09-04 "
           "REGRESSION: with tcp_rip declared `.l` the address is held "
           "sign-extended, tcp_Match never matches, and every segment of "
           "the connection is answered with a RST from TcpInput's "
           "no-connection path"
           % (dotted(HB_PEER_IP), hbst.r, signed32(hbst.e1), hbst.e2,
              S_ESTABLISHED), fails)
    hbp = R("hb_peer")
    expect(hbp.e1 == HB_PEER_IP,
           "TcpPeerIp() returned $%08X for a peer on %s ($%08X).  An IPv4 "
           "address is NOT sequence space and is not modular: it lives in "
           "0..$FFFFFFFF, which is what net.pi4's `& $FFFFFFFF` produces "
           "and what a `.i` holds.  THE WIDTH RULE at the top of tcp.pi4 "
           "is about sequence numbers and does not reach this field"
           % (hbp.e1, dotted(HB_PEER_IP), HB_PEER_IP), fails)
    expect(hbp.e2 == 80,
           "TcpPeerPort() is %d, wanted 80" % hbp.e2, fails)
    hbrd = R("hb_read")
    expect(hbrd.blob == D_HB_IN,
           "TcpRead on the high-bit peer returned %r, wanted %r"
           % (hbrd.blob, D_HB_IN), fails)
    expect(R("hb_norst").r == 0,
           "tcp_norst is %d after a whole conversation with a high-bit "
           "peer, wanted 0.  That counter is incremented once per segment "
           "arriving for a port nobody has open, and on the broken library "
           "it reached FOUR on the bench Pi 4 - once per SYN-ACK - because "
           "the board could not recognise its own connection"
           % R("hb_norst").r, fails)
    for rec in res[at["hb_reset"]:at["hb_norst"] + 1]:
        for f in rec.frames():
            if len(f) >= 54 and (f[47] & RST):
                fails.append(
                    "%s (%s) put a RST ($%02X) on the link during the "
                    "high-bit regression group.  Not one segment of that "
                    "conversation may be answered with a reset; four of them "
                    "were, on silicon, on 2026-09-04.  %s"
                    % (rec.label, "high-bit group", f[47], f.hex()))

    # =================================================================
    #  13. THE ZERO-WINDOW PERSIST TIMER (RFC 9293 3.8.6.1, MUST-36)
    # =================================================================
    code("zw_connect", 0)
    zsyn = one_frame("zw_connect")
    if zsyn and len(zsyn) >= 60:
        zl, ziss = be16(zsyn, 34), be32(zsyn, 38)
        code("zw_synack", S_ESTABLISHED)
        graded("zw_synack", one_frame("zw_synack"),
               zl, 80, ziss + 1, P_ZW + 1, ACK, RCVBUF)
        code("zw_send_open", len(D_ZW_OPEN))
        graded("zw_send_open", one_frame("zw_send_open"),
               zl, 80, ziss + 1, P_ZW + 1, ACK, RCVBUF, data=D_ZW_OPEN)
        no_frame("zw_close", "an acknowledgment that empties the pipe needs "
                             "no answer, whatever window it carries")
        code("zw_send_held", len(D_ZW_HELD),
             "TcpSend BUFFERS what it cannot send and says so by returning "
             "the octets it took")
        no_frame("zw_send_held",
                 "THE WINDOW IS ZERO.  Not one octet may go out here, and a "
                 "stack that sent anyway would be ignoring the only thing "
                 "the receiver said")
        no_frame("zw_arm",
                 "the first poll after the window shuts only ARMS the "
                 "timer.  SHLD-29: the first probe comes after the zero "
                 "window has existed for the retransmission timeout")
        za = R("zw_state_arm")
        expect(za.r == 1 and za.e1 == PERSIST_MIN and za.e2 == 0,
               "after the window shut the persist timer is armed=%d at %d "
               "ms with SND.WND %d; wanted 1, %d, 0.  The interval is "
               "max(RTO, #TCP_PERSIST_MIN_MS)"
               % (za.r, za.e1, za.e2, PERSIST_MIN), fails)
        probe = one_frame("zw_probe",
                          "RFC 9293 3.8.6.1: 'transmit at least one octet "
                          "of new data ... in order to probe the window'")
        graded("zw_probe", probe, zl, 80, ziss + 9, P_ZW + 1, ACK, RCVBUF,
               data=D_ZW_HELD[:1],
               note="EXACTLY ONE OCTET, at SND.NXT, deliberately outside "
                    "the advertised window.  This is the only thing that "
                    "breaks the deadlock: with nothing outstanding the "
                    "retransmission timer never runs, so if the window "
                    "update that reopens the window is lost both ends wait "
                    "forever and no other mechanism in the file notices")
        zp = R("zw_state_probe")
        expect(zp.r == 1 and zp.e1 == 2 * PERSIST_MIN,
               "after one probe the persist timer is armed=%d at %d ms; "
               "wanted 1 and %d.  RFC 9293 SHLD-30: 'increase "
               "exponentially the interval between successive probes'"
               % (zp.r, zp.e1, 2 * PERSIST_MIN), fails)
        zc = R("zw_counts")
        expect(zc.e1 == 1 and zc.e2 == 1 and zc.r == 0,
               "tcp_norst/tcp_zerowin/tcp_probes are %d/%d/%d; wanted "
               "0/1/1 - one zero window seen and exactly one probe sent"
               % (zc.r, zc.e1, zc.e2), fails)
        graded("zw_open", one_frame("zw_open",
                                    "the window update releases the "
                                    "remainder in one segment"),
               zl, 80, ziss + 10, P_ZW + 1, ACK, RCVBUF,
               data=D_ZW_HELD[1:],
               note="the probe octet was acknowledged, so the twenty behind "
                    "it follow at SND.UNA and the deadlock is over")
        zo = R("zw_state_open")
        expect(zo.r == 0 and zo.e2 == 8192,
               "after the window reopened the persist timer is armed=%d "
               "with SND.WND %d; wanted 0 and 8192" % (zo.r, zo.e2), fails)

    # =================================================================
    #  14. TcpDropEvery - A DELIBERATELY LOST SEGMENT
    # =================================================================
    code("dr_connect", 0)
    dsyn = one_frame("dr_connect")
    if dsyn and len(dsyn) >= 60:
        dl, diss = be16(dsyn, 34), be32(dsyn, 38)
        code("dr_synack", S_ESTABLISHED)
        graded("dr_synack", one_frame("dr_synack"),
               dl, 80, diss + 1, P_DROP + 1, ACK, RCVBUF)
        code("dr_arm", 0, "TcpDropEvery returns #NET_TCP_OK")
        code("dr_send", len(D_DROPPED),
             "TcpSend still takes the octets: from the application's side "
             "a lost segment is indistinguishable from a sent one")
        no_frame("dr_send",
                 "TcpDropEvery(1) builds the segment, checksums it and then "
                 "does NOT hand it to the link.  The segment is complete "
                 "before it is discarded, so what is being tested is the "
                 "loss of a CORRECT segment and not a shortcut past the "
                 "arithmetic")
        expect(R("dr_counts_lost").r == 1,
               "tcp_dropped is %d after one deliberately lost segment, "
               "wanted 1" % R("dr_counts_lost").r, fails)
        rf = one_frame("dr_retrans",
                       "the retransmission timer must put the lost segment "
                       "back, and the injector must not eat that one too")
        graded("dr_retrans", rf, dl, 80, diss + 1, P_DROP + 1, ACK, RCVBUF,
               data=D_DROPPED,
               note="THE SAME OCTETS AT THE SAME SEQUENCE NUMBER, and the "
                    "recovery is only real because this frame reached the "
                    "link")
        expect(R("dr_counts_rx").r == 1,
               "tcp_dropped is %d after the retransmission, wanted it "
               "UNCHANGED at 1.  A RETRANSMISSION IS NEVER DROPPED - that "
               "is what tcp_drop_hold is for.  Dropping them as well tests "
               "the backoff rather than the recovery, and a transfer that "
               "is never allowed to finish proves the wrong thing"
               % R("dr_counts_rx").r, fails)
        expect(R("dr_counts_re").e2 == 1,
               "tcp_retrans is %d, wanted 1" % R("dr_counts_re").e2, fails)
        code("dr_disarm", 0, "the injector goes back off")
        no_frame("dr_ack")
        code("dr_state", S_ESTABLISHED,
             "the transfer completed THROUGH a deliberate loss")

    # =================================================================
    #  15. THE KEEPALIVE (RFC 9293 3.8.4, RFC 1122 4.2.3.6)
    # =================================================================
    code("ka_connect", 0)
    ksyn = one_frame("ka_connect")
    if ksyn and len(ksyn) >= 60:
        kl, kiss = be16(ksyn, 34), be32(ksyn, 38)
        code("ka_synack", S_ESTABLISHED)
        graded("ka_synack", one_frame("ka_synack"),
               kl, 80, kiss + 1, P_KEEP + 1, ACK, RCVBUF)
        ko = R("ka_off")
        expect(ko.r == 0 and ko.e1 == 0,
               "TcpKeepalive(0) returned %d and left the idle time at %d "
               "ms; wanted 0 and 0.  RFC 9293 MUST-24 requires keepalives "
               "OFF unless the application asks, and the whole run above "
               "burned four minutes of TIME-WAIT without one going out"
               % (ko.r, ko.e1), fails)
        kn = R("ka_on")
        expect(kn.r == 0 and kn.e1 == KEEP_IDLE_S * 1000,
               "TcpKeepalive(%d) returned %d and set the idle time to %d "
               "ms; wanted 0 and %d"
               % (KEEP_IDLE_S, kn.r, kn.e1, KEEP_IDLE_S * 1000), fails)
        no_frame("ka_early",
                 "nine seconds of idle is not ten.  A keepalive measures "
                 "IDLE time and one that fires early is a battery bill and "
                 "a NAT table entry nobody asked for")
        for nm in ("ka_probe1", "ka_probe2", "ka_probe3"):
            graded(nm, one_frame(nm, "one probe, and nothing else"),
                   kl, 80, kiss, P_KEEP + 1, ACK, RCVBUF,
                   note="RFC 1122 4.2.3.6: a probe carries no data and "
                        "SEG.SEQ = SND.NXT-1, so the peer answers with an "
                        "ACK naming a byte it has already had.  SND.NXT "
                        "would be an ordinary bare ACK, which some "
                        "middleboxes do not count as traffic at all")
        expect(R("ka_counts").e1 == KEEP_PROBES,
               "tcp_keeps is %d, wanted %d - RFC 1122 4.2.3.6 wants a "
               "COUNT of unanswered probes, not a single one"
               % (R("ka_counts").e1, KEEP_PROBES), fails)
        no_frame("ka_dead",
                 "a connection declared dead sends nothing: there is "
                 "nobody there to send it to, which is the finding")
        ks = R("ka_state")
        expect(ks.r == S_CLOSED and signed32(ks.e1) == E_TIMEOUT
               and ks.e2 == 0,
               "after %d unanswered keepalives the socket is state %d, "
               "TcpError() %d, TcpWasReset() %d; wanted CLOSED, %d and 0.  "
               "A peer that went silent and a peer that sent a reset must "
               "never look the same from outside"
               % (KEEP_PROBES, ks.r, signed32(ks.e1), ks.e2, E_TIMEOUT),
               fails)

    # =================================================================
    #  16. THE UPLOAD RECEIVER
    # =================================================================
    ar = R("nr_arm")
    expect(ar.r == NR_WAIT and ar.e1 == S_LISTEN
           and ar.e2 == RECV_BASE + len(UPLOAD) - 1,
           "NetRecvArm answered state %d with the socket in state %d and a "
           "ceiling of %08X; wanted %d (WAIT), %d (LISTEN) and %08X.  The "
           "ceiling is settled BEFORE a byte arrives because a TCP stream "
           "does not say how long it is"
           % (ar.r, ar.e1, ar.e2, NR_WAIT, S_LISTEN,
              RECV_BASE + len(UPLOAD) - 1), fails)

    nsyn = one_frame("nr_syn", "a SYN to the receiver's listener is "
                               "answered with one SYN-ACK")
    if nsyn and len(nsyn) >= 60:
        niss = be32(nsyn, 38)
        graded("nr_syn", nsyn, RECV_PORT, 40100, niss, P_UP + 1, SYN | ACK,
               RCVBUF, options=MSS_OPTION,
               note="the receiver's socket is an ordinary passive open; "
                    "nothing about `net recv` is a second TCP")
        code("nr_ack", NR_RECV,
             "the third leg of the handshake moves the RECEIVER from "
             "waiting to receiving, and it does that from the socket's "
             "state and not from a byte having arrived")
        d1 = R("nr_d1")
        expect(d1.r == NR_RECV and d1.e1 == len(UP_A),
               "after the first data segment the receiver is state %d with "
               "%d octets stored; wanted %d (RECV) and %d"
               % (d1.r, d1.e1, NR_RECV, len(UP_A)), fails)
        d2 = R("nr_d2")
        expect(d2.r == NR_RECV and d2.e1 == len(UPLOAD),
               "after the second data segment the receiver is state %d "
               "with %d octets stored; wanted %d (RECV) and %d"
               % (d2.r, d2.e1, NR_RECV, len(UPLOAD)), fails)
        fin = R("nr_fin")
        expect(fin.r == NR_DONE and fin.e1 == len(UPLOAD),
               "the peer's FIN left the receiver in state %d with %d "
               "octets; wanted %d (DONE) and %d.  THE CLOSE IS THE ONLY "
               "END-OF-FILE MARKER there is - nothing on the wire says how "
               "long the image was - so a receiver that does not finish "
               "here reports a whole image as an unfinished one, or worse"
               % (fin.r, fin.e1, NR_DONE, len(UPLOAD)), fails)
        ns = R("nr_state")
        expect(ns.r == NR_DONE and ns.e1 == len(UPLOAD),
               "NetRecvState/Count read back %d and %d; wanted %d and %d"
               % (ns.r, ns.e1, NR_DONE, len(UPLOAD)), fails)

        got = R("nr_mem").blob
        want = UPLOAD + b"\x00" * 8
        if got != want:
            fails.append(
                "nr_mem: the image in DRAM at %08X is not the image the "
                "peer sent.  %s" % (RECV_BASE, hexdiff(got, want)))

        hr = R("nr_hash")
        want_digest = hashlib.sha256(UPLOAD).hexdigest()
        expect(hr.r == len(UPLOAD) and hr.e1 == RECV_BASE,
               "NetRecvHash hashed %d octets at %08X; wanted %d at %08X"
               % (hr.r, hr.e1, len(UPLOAD), RECV_BASE), fails)
        expect(hr.blob.hex() == want_digest,
               "the board's digest is %s and Python's over the same %d "
               "octets is %s.  The receiver hashes THE MEMORY, so this is "
               "an end-to-end check that the bytes it hashed are the bytes "
               "it stored - not a second copy of the SHA-256 known-answer "
               "test, which lives in its own gate"
               % (hr.blob.hex(), len(UPLOAD), want_digest), fails)

        rel = R("nr_rel")
        expect(rel.e1 == 0,
               "after NetRecvRelease the socket's tcp_listen_port is %d and "
               "must be 0.  A PASSIVE OPEN RE-ARMS ITSELF ON CLOSE by "
               "design, which is right for a server and wrong for a "
               "bootloader: a board that goes on accepting images on a port "
               "for the rest of its uptime is a different program from the "
               "one that was asked for" % rel.e1, fails)

        again = one_frame("nr_syn2", "the second connection attempt must be "
                                     "answered, and answered with a refusal")
        if again and len(again) >= 54:
            expect((again[47] & (RST | ACK)) == (RST | ACK),
                   "a SYN to port %d after the transfer was answered with "
                   "control bits $%02X; wanted RST|ACK.  The listener was "
                   "for ONE image" % (RECV_PORT, again[47]), fails)
        na = R("nr_after")
        expect(na.r == NR_DONE and na.e2 == 0,
               "after the refused second connection the receiver reads "
               "state %d with tcp_listen_port %d; wanted %d (DONE, "
               "unchanged) and 0" % (na.r, na.e2, NR_DONE), fails)

    # ---- the ceiling -------------------------------------------------
    ov1 = R("ov_d1")
    expect(ov1.r == NR_RECV and ov1.e1 == len(UP_A),
           "the first twenty octets fit in thirty of room and left the "
           "receiver at state %d with %d stored; wanted %d and %d"
           % (ov1.r, ov1.e1, NR_RECV, len(UP_A)), fails)
    ov2 = R("ov_d2")
    expect(ov2.r == NR_OVER and ov2.e1 == OVER_ROOM,
           "twenty more octets into ten of room left the receiver at state "
           "%d with %d stored; wanted %d (OVER) and exactly %d.  It must "
           "stop AT the ceiling: not before it, which would lose bytes it "
           "had room for, and not past it, which is the whole reason the "
           "ceiling exists" % (ov2.r, ov2.e1, NR_OVER, OVER_ROOM), fails)
    ovs = R("ov_state")
    expect(ovs.r == NR_OVER and ovs.e1 == OVER_ROOM,
           "NetRecvState/Count read back %d and %d after the ceiling was "
           "hit; wanted %d and %d" % (ovs.r, ovs.e1, NR_OVER, OVER_ROOM),
           fails)
    got = R("ov_mem").blob
    want = UPLOAD[:OVER_ROOM] + b"\x00" * (len(UPLOAD) - OVER_ROOM)
    if got != want:
        fails.append(
            "ov_mem: THE CEILING WAS CROSSED, or the bytes below it are "
            "wrong.  Memory in this model starts at zero and every octet "
            "the peer sent is non-zero, so a non-zero byte past offset %d "
            "is a write outside the window the command was given.  %s"
            % (OVER_ROOM - 1, hexdiff(got, want)))
    ovr = one_frame("ov_rel", "a refused transfer is RESET, not left open "
                              "for the peer to go on filling")
    if ovr and len(ovr) >= 54:
        expect((ovr[47] & RST) != 0,
               "the frame that ended the refused transfer carries control "
               "bits $%02X and must carry RST" % ovr[47], fails)

    # =================================================================
    #  17. THE RECEIVE RING WRAPS
    # =================================================================
    # Every segment must come back out of the ring EXACTLY as it went in,
    # including the ones whose run-based copy crossed the end of the ring
    # and continued at its start.  A length that is right for the flat
    # case and wrong at the seam corrupts one segment and one only, so
    # each read is compared on its own rather than concatenated.
    ws = R("wrap_synack")
    expect(ws.e2 == S_ESTABLISHED,
           "the ring-wrap group never reached ESTABLISHED (state %d), so "
           "nothing below it measured anything" % ws.e2, fails)
    crossed = False
    for k, ln in enumerate(WRAP_LENS):
        before = sum(WRAP_LENS[:k]) % RCVBUF
        if before + ln > RCVBUF:
            crossed = True
        got = R("wrap_out%d" % k).blob
        want = wrap_body(k, ln)
        if got != want:
            fails.append(
                "wrap_out%d: %d octets written into the ring at offset %d "
                "%s did not come back out unchanged.  %s"
                % (k, ln, before,
                   "AND WRAPPING ITS END" if before + ln > RCVBUF
                   else "(flat, no wrap)",
                   hexdiff(got, want)))
            break
    expect(crossed,
           "group 17 never actually wrapped the ring, so it graded the "
           "flat copy twelve times and the seam not at all.  WRAP_LENS "
           "totals %d against a #TCP_RCVBUF of %d"
           % (sum(WRAP_LENS), RCVBUF), fails)

    # -----------------------------------------------------------------
    #  THE WINDOW UPDATE - RFC 1122 4.2.2.17, RFC 9293 3.8.6.2.2.
    # -----------------------------------------------------------------
    #  READING IS WHAT REOPENS THE WINDOW, AND A RECEIVER THAT REOPENS IT
    #  AND SAYS NOTHING HANDS THE RATE TO THE SENDER'S PERSIST TIMER.
    #  Measured on silicon 2026-09-09: a 256 KB `net recv` over a gigabit
    #  cable advanced in bursts separated by stalls of 5,010 / 5,003 /
    #  5,001 / 5,006 ms - the peer's persist timer, four times - while
    #  the board answered 119 of 120 pings under five milliseconds
    #  through them.  12.8 KB/s on a link that had measured 2,401 KB/s,
    #  with no drops, no retransmissions and nothing non-zero in any
    #  counter at either end.  THAT is why this is graded by COUNTING
    #  SEGMENTS OUT OF A READ and not by any throughput number.
    #
    #  IT IS GRADED AGAINST THE RULE, NOT AGAINST A LIST.  3.8.6.2.2 says
    #  the offered window is not increased until it can grow by at least
    #  min(Fr * RCV.BUFF, Eff.snd.MSS), which here is min(RCVBUF/2, 1460)
    #  = 1460, so the expectation is computed from WRAP_LENS by the same
    #  rule TcpAdvertiseWnd applies: consumption accumulates until it
    #  passes the threshold, and only then does the edge move and a
    #  segment go out.  Three of the twelve reads in this group are 1459,
    #  1457 and 1458 octets long ON PURPOSE, so a read that stays SILENT
    #  is graded here too - an implementation that acknowledges every
    #  read is the silly-window failure at the other end of the same
    #  rule, and a list of twelve ones would have called it correct.
    lim = min(RCVBUF // 2, 1460)
    want_sent = []
    acc = 0
    for ln in WRAP_LENS:
        acc += ln
        if acc >= lim:
            want_sent.append(1)
            acc = 0
        else:
            want_sent.append(0)
    sent = [R("wrap_out%d" % k).e1 for k in range(len(WRAP_LENS))]
    expect(sent == want_sent,
           "TcpRead is not announcing the window it reopens.  Over the "
           "twelve reads of the ring-wrap group, RFC 9293 3.8.6.2.2's "
           "threshold of min(RCVBUF/2, MSS) = %d octets is passed on the "
           "reads marked 1 in %s, so that is how many segments each read "
           "must emit - and this build emitted %s.  RFC 1122 4.2.2.17: a "
           "peer is not allowed to guess that a window has reopened, and "
           "waits out its persist timer instead"
           % (lim, want_sent, sent), fails)


# =====================================================================
#  MUTATION - proof the gate can go red
# =====================================================================
# (name, old, new, how many times the anchor must occur, why)
MUTATIONS = [
    # THE MOST VALUABLE LINE IN THIS LIST.  It puts the 2026-09-04 defect
    # back exactly as it was.  If this ever goes GREEN the gate has
    # stopped watching the one thing it actually caught, and the most
    # likely cause is somebody moving the bench back to a 10-net for
    # convenience: on 10.0.0.0/8 `.l` and `.i` behave identically.
    ("`Global tcp_rip.l` PUT BACK - the 2026-09-04 high-bit defect",
     "Global tcp_rip.i",
     "Global tcp_rip.l",
     1,
     "an IPv4 address with bit 31 set is stored sign-extended and never "
     "again equals the unsigned value NetTcpRxFrom() returns, so "
     "tcp_Match matches nothing and the board answers its own peer with "
     "a RST once per SYN-ACK.  Found from the desk and confirmed on "
     "silicon the same evening; 10.0.0.0/8 hides it completely"),

    ("TcpSeqLt subtracts into a plain `.i` local - THE WIDTH BUG",
     "Procedure.i TcpSeqLt(a.l, b.l)\n"
     "  Define d.l\n"
     "  d = a - b\n",
     "Procedure.i TcpSeqLt(a.l, b.l)\n"
     "  Define d.i\n"
     "  d = a - b\n",
     1,
     "at 64 bits $7FFFFFFF - $FFFFFFFF is +2147483648 and the ordering "
     "comes out backwards; the whole file is `.l` to stop exactly this"),

    ("the MSS option written LITTLE-endian",
     "    tcp_PutBE16(p + 22, #TCP_MSS_RX)",
     "    PokeB(p + 22, #TCP_MSS_RX & $FF)\n"
     "    PokeB(p + 23, (#TCP_MSS_RX >> 8) & $FF)",
     1,
     "1460 byte-swapped is 46085 and no peer complains - it just sends "
     "enormous segments"),

    ("the FIN does not occupy a sequence number",
     "      tcp_fin_seq = tcp_snd_nxt\n"
     "      nx = tcp_snd_nxt + 1              ; 3.6: the FIN occupies one\n"
     "      tcp_snd_nxt = nx                  ; sequence number",
     "      tcp_fin_seq = tcp_snd_nxt\n"
     "      nx = tcp_snd_nxt                  ; the +1 removed by a mutation\n"
     "      tcp_snd_nxt = nx",
     1,
     "RFC 9293 3.6; without it the peer's acknowledgment of the FIN acks "
     "something never sent and FIN-WAIT-2 is never reached"),

    ("the RTO does not double on backoff",
     "  tcp_rto = tcp_rto * 2",
     "  tcp_rto = tcp_rto * 1",
     1,
     "RFC 6298 5.5, 'the host MUST set RTO <- RTO * 2'"),

    ("Karn's line deleted - a sample taken from a retransmission",
     "  tcp_rtt_timing = 0\n"
     "  tcp_rto = tcp_rto * 2",
     "  tcp_rto = tcp_rto * 2",
     1,
     "RFC 6298 3.1; this one line is the difference between an RTO that "
     "recovers and one that collapses under loss"),

    ("TcpSendRstFor does not put the peer's address back",
     "  tcp_rip = saved_rip",
     "  ; the restore, removed by a mutation",
     1,
     "one stray probe from the LAN then re-points a live connection at "
     "whoever sent it, with no error anywhere"),

    ("the acceptability test's `<` made `<=`",
     "  If wnd = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  If TcpSeqGe(seq, tcp_rcv_nxt) <> 0\n"
     "    If TcpSeqLt(seq, edge) <> 0\n"
     "      ProcedureReturn 1\n"
     "    EndIf\n"
     "  EndIf\n"
     "  lastseq = seq + seglen - 1",
     "  If wnd = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  If TcpSeqGe(seq, tcp_rcv_nxt) <> 0\n"
     "    If TcpSeqLe(seq, edge) <> 0\n"
     "      ProcedureReturn 1\n"
     "    EndIf\n"
     "  EndIf\n"
     "  lastseq = seq + seglen - 1",
     1,
     "RFC 9293 Table 6's window is half open; one octet too many is "
     "accepted and the receive ring is overrun by exactly one segment"),

    ("the receive window edge allowed to move backwards",
     "  If TcpSeqGe(newedge, tcp_rcv_edge + lim) <> 0\n"
     "    tcp_rcv_edge = newedge\n"
     "  EndIf",
     "  tcp_rcv_edge = newedge",
     1,
     "RFC 9293 3.8.6.2.2; the one property that makes a dynamic window as "
     "safe as a fixed one is that the right edge never retreats"),

    ("TcpAckArm removes the SYN from `acked` unconditionally",
     "  If TcpSeqLe(tcp_snd_una, tcp_iss) <> 0\n"
     "    acked = acked - 1\n"
     "  EndIf",
     "  acked = acked - 1",
     1,
     "one acknowledged octet is left in the send ring and is transmitted "
     "again as a one-octet segment nobody asked for"),

    ("TcpTxCap ignores LinkTxMax and assumes Ethernet",
     "  m = LinkTxMaxOn(tcp_kind) - 14 - 20 - 20",
     "  m = 1514 - 14 - 20 - 20",
     1,
     "a 1460-octet segment over a 1136-octet link is REFUSED by the radio, "
     "not shortened, so the connection stalls the first time it is busy"),

    ("the acknowledgment field written from SND.NXT",
     "  tcp_PutBE32(p + #TCP_H_ACK, tcp_rcv_nxt)",
     "  tcp_PutBE32(p + #TCP_H_ACK, tcp_snd_nxt)",
     1,
     "the peer is told we have received our own sequence space"),

    ("a RST answered with an ACK",
     "  If (tcp_seg_flags & #TCP_RST) <> 0\n"
     "    tcp_rst_rx = tcp_rst_rx + 1\n"
     "    tcp_reset_seen = 1\n"
     "    tcp_err = #NET_TCP_E_RESET\n"
     "    If tcp_state = #TCP_SYN_RECEIVED",
     "  If (tcp_seg_flags & #TCP_RST) <> 0\n"
     "    TcpSendAck()\n"
     "    tcp_rst_rx = tcp_rst_rx + 1\n"
     "    tcp_reset_seen = 1\n"
     "    tcp_err = #NET_TCP_E_RESET\n"
     "    If tcp_state = #TCP_SYN_RECEIVED",
     1,
     "two stacks that answer a reset with anything can trade segments "
     "forever; RFC 9293 3.5.2 forbids it"),

    ("the retransmission sent from SND.NXT instead of SND.UNA",
     "    TcpSendSeg(tcp_snd_una, #TCP_ACK, n, 0)",
     "    TcpSendSeg(tcp_snd_nxt, #TCP_ACK, n, 0)",
     1,
     "RFC 6298 5.4 wants 'the earliest segment that has not been "
     "acknowledged'; sending a new one leaves the hole open forever"),

    ("the SYN carries no MSS option at all",
     "  ; <SEQ=ISS><CTL=SYN>, with our MSS on it.\n"
     "  TcpSendSeg(tcp_iss, #TCP_SYN, 0, 1)",
     "  ; <SEQ=ISS><CTL=SYN>, with our MSS on it.\n"
     "  TcpSendSeg(tcp_iss, #TCP_SYN, 0, 0)",
     1,
     "the peer then assumes 536 (RFC 9293 3.7.1's MUST) and every reply "
     "arrives in third-sized segments"),

    ("the zero-window persist timer never expires",
     "      ElseIf (now - tcp_persist_t0) >= (tcp_persist_ms * 1000)",
     "      ElseIf (now - tcp_persist_t0) >= (tcp_persist_ms * 1000000)",
     1,
     "RFC 9293 3.8.6.1 and MUST-36.  With a zero window there is nothing "
     "outstanding, so no other timer runs: if the window update is lost "
     "both ends wait forever and only a probe breaks the tie"),

    ("the persist interval does not back off",
     "        tcp_persist_ms = tcp_persist_ms * 2",
     "        tcp_persist_ms = tcp_persist_ms * 1",
     1,
     "RFC 9293 SHLD-30, 'increase exponentially the interval between "
     "successive probes'; without it a wedged peer is probed at a fixed "
     "rate for as long as it stays wedged"),

    ("the loss injector eats RETRANSMISSIONS too",
     "      If tcp_drop_hold = 0\n",
     "      If 1 = 1\n",
     1,
     "tcp_drop_hold is what makes TcpDropEvery a test of RECOVERY rather "
     "than of backoff.  Dropping the retransmissions as well means the "
     "transfer never completes, and a bench that cannot finish proves "
     "the wrong thing"),

    ("the keepalive probe sent at SND.NXT, not SND.NXT-1",
     "          TcpSendSeg(TcpSeqAdd(tcp_snd_nxt, -1), #TCP_ACK, 0, 0)",
     "          TcpSendSeg(tcp_snd_nxt, #TCP_ACK, 0, 0)",
     1,
     "RFC 1122 4.2.3.6 wants SEG.SEQ = SND.NXT-1 so the peer is obliged "
     "to answer; at SND.NXT it is an ordinary bare ACK and some "
     "middleboxes do not count it as traffic at all"),
]

# ONE MUTATION CANNOT BE CAUGHT AND IS DECLARED RATHER THAN DROPPED.
#
# `If tcp_fin_sent <> 0 / If TcpSeqGt(tcp_seg_ack, tcp_fin_seq) <> 0 /
#  acked = acked - 1` in TcpAckArm is UNREACHABLE AS A BEHAVIOUR: two
# lines below it, `If acked > tcp_snd_cnt : acked = tcp_snd_cnt` clamps
# the count to the octets actually in the ring, and the FIN is never one
# of those.  Every path this gate can build reaches the clamp with the
# same answer either way, and tcp_bytes_tx is accumulated AFTER the clamp
# so it does not diverge either.  Deleting the adjustment is therefore
# not observable from outside the file.
#
# It is left in MUTATIONS so the sweep prints it, and listed here so that
# "green" is a measured verdict and not an oversight.  Removing the
# adjustment from tcp.pi4 would be safe today and unsafe the moment the
# clamp moves, which is exactly the sort of thing a comment cannot hold
# on its own - the finding belongs in the report, not in a silent skip.
MUTATIONS.append(
    ("TcpAckArm does not remove the FIN from `acked`",
     "  If tcp_fin_sent <> 0\n"
     "    If TcpSeqGt(tcp_seg_ack, tcp_fin_seq) <> 0\n"
     "      acked = acked - 1\n"
     "    EndIf\n"
     "  EndIf",
     "  ; the FIN adjustment, removed by a mutation",
     1,
     "EXPECTED GREEN: `If acked > tcp_snd_cnt : acked = tcp_snd_cnt` two "
     "lines below already clamps the count to the octets in the ring, and "
     "tcp_bytes_tx is accumulated after that clamp, so the adjustment "
     "changes nothing observable.  It is defensive, not load bearing"))

# ---- THE RUN-BASED RING COPY, 2026-09-07 --------------------------
# Four mutations for four lines, because a run-based ring copy can fail
# in ways a per-octet one could not: the old loop masked the index on
# every single octet, so "the wrap" was not a case anybody could get
# wrong.  Group 17 is the only group that moves more than #TCP_RCVBUF
# octets through one socket, so it is the only group these can go red in.
MUTATIONS.extend([
    ("TcpRcvPush ignores the end of the ring - THE WRAP",
     "    run = #TCP_RCVBUF - w\n",
     "    run = left\n",
     1,
     "one run is written past the end of this socket's ring and into the "
     "next socket's, and nothing else in this gate moves enough octets "
     "to notice"),

    ("TcpRead ignores the end of the ring - THE WRAP, reading",
     "    run = #TCP_RCVBUF - tcp_rcv_tail\n",
     "    run = left\n",
     1,
     "the tail of a wrapped read comes out of the NEXT socket's ring "
     "instead of the start of this one, so the caller is handed somebody "
     "else's data with no error anywhere"),

    ("tcp_Move's 8-octet rung stops checking the SOURCE alignment",
     "  If (d & 7) = 0 And (s & 7) = 0\n",
     "  If (d & 7) = 0\n",
     1,
     "an eight-byte load from an address that is not eight-aligned is an "
     "Alignment fault on this part with the MMU off, and no exception "
     "vector is installed - the board stops mid-line and needs a power "
     "cycle.  The interpreter raises the same fault, which is the only "
     "reason a width ladder is safe to write here at all"),

    ("tcp_Move drops the octets the wide rungs could not take",
     "  e = d + left\n"
     "  While d < e\n"
     "    PokeB(d, PeekA(s))\n",
     "  e = d\n"
     "  While d < e\n"
     "    PokeB(d, PeekA(s))\n",
     1,
     "every copy whose length or alignment leaves a remainder loses it "
     "silently.  An even length on an aligned ring is unharmed, which is "
     "why three of group 17's lengths are odd"),
])

EXPECT_GREEN = {
    "TcpAckArm does not remove the FIN from `acked`",
}

# =====================================================================
#  THE RECEIVER'S MUTATIONS - the same sweep, the other file
# =====================================================================
#  Anvil/Core/netrecv.pbi is under test here too, so it gets mutated
#  here too.  Its entries are marked by naming it as the target; a
#  mutation names ONE file and the other is taken from the tree, so a
#  defect in the receiver and a defect in tcp.pi4 are separate verdicts
#  and a receiver mutation that goes green cannot be excused by tcp.pi4.
#
#  RECV_MUTATIONS ARE APPENDED to the same list rather than kept in a
#  second one, because the pool indexes MUTATIONS and a second list
#  would need a second sweep, a second reaping and a second place to
#  forget something.
RECV_TARGET = set()


def _recv_mutation(name, old, new, count, why):
    RECV_TARGET.add(name)
    MUTATIONS.append((name, old, new, count, why))


_recv_mutation(
    "netrecv: the ceiling clamp deleted - THE WINDOW STOPS MEANING ANYTHING",
    "  want = avail\n"
    "  If want > room\n"
    "    want = room\n"
    "  EndIf",
    "  want = avail",
    1,
    "the whole safety argument of `net recv` is that a peer cannot make "
    "it write outside the range the command named.  Without the clamp a "
    "peer decides how much of DRAM to overwrite, and the requested "
    "ceiling is decoration")

_recv_mutation(
    "netrecv: a peer sending past the ceiling is not noticed",
    "  If avail > got\n"
    "    gNrState = #NR_OVER\n"
    "    ProcedureReturn -1\n"
    "  EndIf",
    "  ; the over-the-ceiling test, removed by a mutation",
    1,
    "the clamp still stops the write, so nothing is corrupted - but the "
    "transfer then reports DONE with a digest of the FIRST PART of the "
    "file, and a truncated image that verifies against nothing is worse "
    "than one that refuses")

_recv_mutation(
    "netrecv: CLOSE-WAIT is not treated as the end of the file",
    "  If st = #TCP_CLOSE_WAIT Or st = #TCP_CLOSED Or st = #TCP_LAST_ACK",
    "  If st = #TCP_CLOSED Or st = #TCP_LAST_ACK",
    1,
    "the peer's FIN is the ONLY end-of-file marker this protocol has.  A "
    "receiver that does not finish on it sits waiting for a byte that is "
    "never coming and eventually reports a complete transfer as a timeout")

MUTATIONS.append(
    ("the window update is COUNTED but never SENT - the 2026-09-09 defect",
     "      tcp_wndup = tcp_wndup + 1\n"
     "      TcpSendAck()",
     "      tcp_wndup = tcp_wndup + 1",
     1,
     "this is the shape the defect actually had: the right edge moved, "
     "everything on this board agreed that it had moved, and the peer "
     "was never told - so it waited out its persist timer, five seconds "
     "at a time, and a gigabit cable measured 12.8 KB/s with no drops, "
     "no retransmissions and every counter at zero.  IT IS MUTATED HERE "
     "WITH THE COUNTER LEFT CLIMBING on purpose: a gate that graded "
     "tcp_wndup instead of counting the frames out of the read would "
     "stay green through it, and that is the whole reason the harness "
     "learned to report how many segments a read emitted"))

MUTATIONS.append(
    ("a segment is built from the CABLE's row whatever kind it latched",
     "  If NetTcpBuildFrom(tcp_kind, tcp_lip, tcp_rip, seglen, "
     "@tcp_rmac[0]) = 0",
     "  If NetTcpBuildFrom(#HW_LINK_WIRED, tcp_lip, tcp_rip, seglen, "
     "@tcp_rmac[0]) = 0",
     1,
     "a connection opened on the radio would leave with the cable's "
     "hardware address as its source, which a real access point drops "
     "as a frame from a station that never associated.  Group 8 is the "
     "only connection here that is not on the cable, and its radio row "
     "holds a MAC of its own for exactly this: every other byte of those "
     "frames is identical from either row"))

MUTATIONS.append(
    ("TcpUnlisten does not actually clear the passive open",
     "  tcp_listen_port = 0\n"
     "  If tcp_state = #TCP_LISTEN\n"
     "    TcpWipe()",
     "  ; the clear, removed by a mutation\n"
     "  If tcp_state = #TCP_LISTEN\n"
     "    TcpWipe()",
     1,
     "the socket goes back to LISTEN when the transfer ends, so the board "
     "accepts a second image on that port - and every one after it - for "
     "the rest of its uptime.  Nothing visible happens until somebody "
     "connects, which is what makes it worth a mutation"))


def one_run(lib_include: str, harness: pathlib.Path, img: pathlib.Path,
            script: Script, step_limit: int = STEP_LIMIT,
            recv_include: str = RECV_DEFAULT):
    write_harness(lib_include, harness, recv_include)
    build(harness, img)
    cpu, uart, steps = run(img, script.finish(), step_limit)
    res = read_results(cpu.memory, script.labels)
    return res, uart, steps


def mutate_one(idx: int, workdir: pathlib.Path) -> int:
    """Score ONE mutation, in a directory of this worker's own, and print
    a single machine-readable verdict line for the parent.

    This is the entry point a64_mutate_pool.run_parallel spawns.  It reads
    the library, writes the MUTATED COPY into workdir, and NEVER OPENS THE
    LIBRARY FOR WRITING."""
    name, old, new, count, _why = MUTATIONS[idx]
    # WHICH OF THE TWO FILES THIS ONE BREAKS.  The other is taken from
    # the tree unmutated, so the verdict names one file and not a pair.
    target = RECVLIB if name in RECV_TARGET else LIB
    src = target.read_text(encoding="utf-8", errors="replace")
    mutated, why_not = pool.apply_edits(src, old, new, count)
    if why_not:
        # A mutation whose anchor has drifted has stopped testing
        # anything.  Report it; never let it read as a pass.
        print("%sERROR\tCANNOT APPLY - %s" % (pool.VERDICT, why_not))
        return 1

    workdir = pathlib.Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    if target is RECVLIB:
        mut = workdir / "netrecv_mut.pi4"
        mut.write_text(mutated, encoding="utf-8")
        include = LIB_DEFAULT
        recv_include = mut.relative_to(ROOT).as_posix()
    else:
        mut = workdir / "tcp_mut.pi4"
        mut.write_text(mutated, encoding="utf-8")
        include = mut.relative_to(ROOT).as_posix()
        recv_include = RECV_DEFAULT

    budget = int(os.environ.get("TCP_MUT_BUDGET", str(STEP_LIMIT)))
    script, at, book = build_script()

    red, note = None, ""
    try:
        one = one_run(include, workdir / "tcpharness_mut.pi4",
                      workdir / "tcpcheck_mut.img", script, budget,
                      recv_include)
    except SystemExit as exc:
        red = True
        note = str(exc).splitlines()[0][:70]
        one = None
    except Exception as exc:                             # noqa: BLE001
        # A MUTANT THAT FAULTS IS RED, NOT A CRASH.  With the MMU off an
        # unaligned wide access is a fault with no vector installed; on
        # the board that is silence.
        red = True
        note = "%s: %s" % (type(exc).__name__, str(exc)[:60])
        one = None
    if red is None and one is not None:
        res, uart, _steps = one
        fails: list[str] = []
        if b"TXOVERFLOW" in bytes(uart):
            fails.append("the capture buffer overflowed")
        try:
            check(res, at, book, fails)
        except Exception as exc:                         # noqa: BLE001
            fails.append("the checker itself refused it: %r" % (exc,))
        red = bool(fails)
        note = "%d assertion(s) failed" % len(fails) if fails else "clean"
    print("%s%s\t%s" % (pool.VERDICT, "RED" if red else "GREEN", note))
    return 0


def mutate(clean_steps: int) -> int:
    """Fan the mutations out across the machine and collect the verdicts
    in index order.  ONE WORKER PER MUTATION, ONE DIRECTORY PER WORKER;
    see a64_mutate_pool for why it is subprocesses and why the
    directories matter."""
    budget = max(clean_steps * 4, 50_000_000)
    os.environ["TCP_MUT_BUDGET"] = str(budget)
    procs = pool.worker_count()
    root = WORK / "tcp"
    t0 = time.time()
    print("MUTATION TEST - %d mutations, step budget %d (the clean run was "
          "%d)" % (len(MUTATIONS), budget, clean_steps))
    print("  %d workers on %d logical CPUs; each mutant is a COPY in "
          "%s/<n>/ and the library is never opened for writing"
          % (procs, os.cpu_count() or 0, root.relative_to(ROOT).as_posix()))
    print()

    # Every worker is handed the SAME compiler this run resolved, so a
    # sweep never builds its mutants with a different compiler from the
    # clean run it is compared against.
    lines = pool.run_parallel(pathlib.Path(__file__).resolve(), ROOT,
                              len(MUTATIONS), root, procs, label="mutation",
                              extra_args=["--compiler", str(PMFC)])

    failures = 0
    print()
    for (name, _old, _new, _count, why), line in zip(MUTATIONS, lines):
        parts = line.split("\t")
        verdict = parts[1] if len(parts) > 1 else "ERROR"
        note = parts[2] if len(parts) > 2 else ""
        if verdict == "ERROR":
            print("  %-58s *** %s ***" % (name[:58], note))
            failures += 1
            continue
        red = verdict == "RED"
        want_red = name not in EXPECT_GREEN
        if red == want_red:
            print("  %-58s %-5s (%s)" % (name[:58], verdict, note))
            if not want_red:
                print("        EXPECTED GREEN, and here is why:")
                print("        %s" % why)
        else:
            failures += 1
            print("  %-58s *** %s ***"
                  % (name[:58], "GREEN - THE GATE DOES NOT SEE THIS"
                     if want_red else "RED, EXPECTED GREEN"))
            print("        %s" % why)

    # THE TREE IS PASSED, and that is the fix for the false failure this
    # gate's own note filed as owed on 2026-09-04: the reap check used to
    # count every PureMetalForge.exe on the machine, so a clean sweep here was
    # failed by another worktree's build. It counts OUR processes now.
    # THE SWEEP'S OWN WORK DIRECTORY, not the tree: other gates may be
    # compiling in the same tree at the same time, and only a compiler
    # whose command line names this sweep's directory is this sweep's.
    alive = pool.report_reaped(root)
    # The mutants are copies under _work/, which is in .gitignore, but a
    # sweep that leaves fifteen mutated libraries lying about is a sweep
    # somebody will one day read as the real file.
    import shutil
    shutil.rmtree(root, ignore_errors=True)
    print()
    print("  %d mutations across %d workers in %.0f s"
          % (len(MUTATIONS), procs, time.time() - t0))
    print("  pool reaped: %s build processes still alive"
          % ("could not check" if alive < 0 else alive))
    if alive > 0:
        print("  *** WORKERS WERE LEFT BEHIND - that is a defect, not noise")
        failures += 1
    return failures


# =====================================================================
def resolve_compiler(requested):
    """Resolve the PureMetal compiler. A named compiler (explicit or
    PMF_COMPILER) is routed through the shared, validating resolver
    (tools/pmf_compiler.py): refuses a missing, retired, or
    untracked/stale executable (forum 977). With nothing named, this
    falls back to tools/build.py's bare-PATH search, unchanged."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    if requested or os.environ.get("PMF_COMPILER"):
        from pmf_compiler import resolve_compiler as _pmf_resolve_compiler  # noqa: E402
        return _pmf_resolve_compiler(requested)
    return anvil_build.find_compiler(requested)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--mutate", action="store_true",
                    help="prove the gate can fail, by breaking the library")
    ap.add_argument("--dump", action="store_true",
                    help="print every frame the library staged")
    ap.add_argument("--cost", action="store_true",
                    help="measure instructions per received octet; grades "
                         "nothing")
    # The two below are how a64_mutate_pool spawns one worker; they are
    # not meant to be typed by hand.
    ap.add_argument("--mutate-one", type=int, default=None, dest="mutate_one",
                    help=argparse.SUPPRESS)
    ap.add_argument("--mutate-dir", default=None, dest="mutate_dir",
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    globals()["PMFC"] = resolve_compiler(args.compiler)
    if args.mutate_one is not None:
        if not args.mutate_dir:
            raise SystemExit("--mutate-one needs --mutate-dir")
        return mutate_one(args.mutate_one, pathlib.Path(args.mutate_dir))

    if args.cost:
        return cost()

    if not LIB.exists():
        raise SystemExit("there is no %s to gate" % LIB)
    if not NETLIB.exists():
        raise SystemExit("tcp.pi4 sits on %s and it is not there" % NETLIB)
    if not RECVLIB.exists():
        raise SystemExit("the upload receiver %s is not there, and group 16 "
                         "is about it" % RECVLIB)

    script, at, book = build_script()
    WORK.mkdir(exist_ok=True)
    res, uart, steps = one_run(LIB_DEFAULT,
                               WORK / "tcpharness.pi4",
                               WORK / "tcpcheck.img", script)

    console = uart.decode("latin-1")
    print("%d script records, %d results, %d instructions, console %r"
          % (len(script.labels), len(res), steps, console))
    print()

    if args.dump:
        for r in res:
            print("  %-30s r=%-8d e1=%-10d e2=%-8d %s"
                  % (r.label[:30], r.r, r.e1, r.e2,
                     " ".join("%d octets" % len(f) for f in r.frames())))
        print()

    # A transcript a human can read, of the half that matters most.
    for name in ("connect3", "synack3", "send3a", "tick_rto", "stranger",
                 "close3", "hb_synack", "zw_probe", "dr_retrans",
                 "ka_probe1"):
        r = res[at[name]]
        f = r.frames()
        print("  %-11s %-48s %s" % (name, r.label[:48],
                                    "%d octets" % len(f[0]) if f
                                    else "NO FRAME"))
        if f:
            for off in range(0, min(len(f[0]), 64), 16):
                print("      %04X  %s" % (off, f[0][off:off + 16].hex(" ")))
    print()

    fails: list[str] = []
    if "TXOVERFLOW" in console:
        fails.append("the harness's capture buffer overflowed, so at least "
                     "one frame was never graded.  Raise #H_CAPMAX")
    if "tcpharness done" not in console:
        fails.append("the harness did not reach its own last line; the "
                     "results below are a fragment")
    check(res, at, book, fails)

    if fails:
        print("a64_tcp_check: FAIL")
        for f in fails:
            print("   " + f)
        return 1

    print("a64_tcp_check: PASS - %d cases, every frame byte-exact"
          % len(script.labels))
    print("           the handshake, a data exchange, a retransmission with")
    print("           Karn, both directions of RST, a FIN close through")
    print("           TIME-WAIT, the 32-bit width rule, the socket table,")
    print("           the 1136-octet link ceiling, a passive open, bounded")
    print("           reassembly, the acceptability edge, the zero-window")
    print("           persist timer, the TcpDropEvery loss injector and the")
    print("           keepalive to its third unanswered probe.")
    print("           AND THE UPLOAD RECEIVER, Anvil/Core/netrecv.pbi: an")
    print("           image arriving over a scripted connection, the FIN as")
    print("           the end-of-file marker, the bytes read back out of")
    print("           DRAM, the board's own SHA-256 against Python's, the")
    print("           listener REFUSING a second connection, and a peer")
    print("           sending past the ceiling stopped AT it with the")
    print("           memory beyond it proven untouched.")
    print("           2*MSL, THE RTO, THE PERSIST INTERVAL AND THE KEEPALIVE")
    print("           ARE PROVEN BY WARPING CNTPCT_EL0, not by executing for")
    print("           four minutes - see THE CLOCK in this file's header for")
    print("           exactly what that models.")
    print("           NOT covered: congestion control (there is none),")
    print("           simultaneous open, CLOSING and LAST-ACK.")
    print("           THE BENCH IS 192.168.x.x, so EVERY case above is")
    print("           measured across the bit-31 boundary that the")
    print("           2026-09-04 tcp_rip defect narrowed; the hb_ group")
    print("           asserts it again on 172.20.0.20.  A 10-net bench")
    print("           would retire that property in silence.")

    if args.mutate:
        print()
        return 1 if mutate(steps) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
