#!/usr/bin/env python3
"""Executable gate for Anvil/Network/net.pbi - Ethernet, ARP, IPv4, ICMP, UDP.

There is no Pi 4 here and no network.  Neither is needed, and that is a
property of the library rather than a shortcut taken by the gate:
net.pi4 performs no input and no output.  It never calls GenetSend, it
never calls GenetRecv, it touches no MMIO.  It is a codec and a small
state machine over buffers, so the only thing that has to be fabricated
to test it is a PL011 that swallows characters.

WHAT THIS GATE DOES

  A fixed harness - written into _work by this script, never edited by
  hand - includes uart.pi4 and net.pi4 and executes a SCRIPT that this
  script writes into the machine's memory before the run.  Each script
  record names one library call and carries its arguments and, where
  there is one, a frame.  Each result record carries the return value,
  NetError(), one or two extra readings, and a byte-for-byte copy of
  whatever the library staged in NetOutBuf().

  So the gate hands the library REAL FRAMES, BYTE BY BYTE, and grades
  REAL FRAMES, BYTE BY BYTE.  Nothing is inspected through an accessor
  that could agree with the library by construction: an ARP reply is
  sixty bytes and all sixty are compared.

HOW HONEST THIS GATE IS, STATED PLAINLY

  A driver gate can PARSE its expectations out of the vendor driver, so
  the library and the gate are two independent readings of one source.
  THIS GATE CANNOT DO THAT FOR MOST CONSTANTS AND THE DIFFERENCE MATTERS.

  When this gate was written no machine-readable source for the
  EtherTypes, ARP opcodes or IP header layouts was at hand (no
  if_ether.h, ip.h, icmp.h, udp.h or lwIP tree); RFC 9293 and RFC 6298
  were the only protocol documents available.

  RFCs 791, 792, 768 and 826 are public documents that could supply a
  SECOND READING, and this gate still performs a second TRANSCRIPTION.
  They are not yet in RaspberryPi4/Reference/ because nothing parses
  them.  That is a named debt, not a
  discovered gap: see the paragraph below for what closing it means.

  Therefore:

    * the ones' complement checksum and the twelve-octet IPv4
      pseudo-header ARE cited, and this gate quotes the line numbers -
      RaspberryPi4/Reference/rfc9293-tcp.txt:407-415 and :426-449;
    * the Ethernet header length of 14 and the MTU of 1500 ARE cited,
      from U-Boot v2025.01 drivers/net/bcmgenet.c:102 when a local copy
      is placed at RaspberryPi4/Reference/v2025.01_bcmgenet.c (it is
      third-party source and is not shipped; without it that one
      cross-check is skipped with a printed note);
    * EVERYTHING ELSE - the EtherTypes, the ARP layout and opcodes, the
      IPv4 header layout, ICMP types 8 and 0, the UDP header - is
      written here from the protocol definitions, exactly as it is
      written in net.pi4.  THAT IS A SECOND TRANSCRIPTION, NOT A SECOND
      READING.  A gate and a library that made the same mistake would
      agree.

  What the gate still buys, even so, is worth having.  Its encoder and
  its checksum are written the other way round from the library's - it
  unpacks big-endian 16-bit words with struct and sums them, where the
  library walks bytes - so an arithmetic error, a fold error, an odd
  length handled at the wrong end, a byte-order slip, a missing
  pseudo-header, a length taken from the wrong header, and every
  refusal are all genuinely caught.  What it cannot catch is both files
  believing the same wrong constant.

  CLOSING THE DEBT, concretely, once the four RFCs are added:
  parse the ARP packet layout out of rfc826.txt, the IPv4 header field
  offsets out of rfc791.txt, the ICMP types out of rfc792.txt and the
  UDP header out of rfc768.txt, the way cited_eth_hlen_and_mtu() below
  already parses the Ethernet header length out of the GENET driver
  rather than typing it.  Until that is done the constants here and the
  constants in net.pi4 remain one reading written twice, and this
  paragraph stays.

WHAT IS ASSERTED

  * A REAL ARP REQUEST for our address produces a byte-exact reply, all
    sixty octets of it including the eighteen zero pad bytes.
  * AN ARP REQUEST FOR SOMEBODY ELSE PRODUCES NOTHING.  A stack that
    answers for addresses it does not own poisons the segment.
  * A REAL ICMP ECHO REQUEST - the thirty-two byte a..w payload
    Microsoft's ping sends - produces a byte-exact echo reply.  The
    identifier, sequence and payload must come back unchanged and the
    type must be the only thing that moved.
  * AN ODD-LENGTH PAYLOAD IS TESTED TOO.  The checksum's trailing byte
    is padded on its RIGHT (rfc9293-tcp.txt:411-413); getting that
    backwards is correct for every even-length packet and wrong for
    every odd one, which is a bug that hides.
  * IP OPTIONS ARE SKIPPED, NOT MISHANDLED.  An IHL of 6 with a real
    option must still be answered.
  * FRAGMENTS ARE REFUSED IN BOTH FORMS - More Fragments set, and a
    non-zero offset - and no reply is staged for either.
  * EVERY CHECKSUM IS MUTATED.  One byte is flipped in the IP header,
    in the ICMP message and in the UDP datagram, and each must produce
    its own distinct refusal code and no frame.
  * A FRAME FOR SOMEBODY ELSE'S MAC IS IGNORED; so is the real
    spanning-tree BPDU the board received off a live switch on
    2026-08-26, whose "EtherType" is $0026 and is therefore a length.
  * TRUNCATION IS TESTED AT FOUR PLACES - a 13-byte frame, an IP header
    cut short, an ARP cut short, and a total-length field that runs off
    the end of the frame it arrived in.
  * OFF-LINK TRAFFIC GOES TO THE GATEWAY'S MAC while the IP destination
    stays the far host.  This is the single most commonly wrong line in
    a first IP stack.
  * THE UDP PSEUDO-HEADER IS PROVEN by an independent computation, in
    both directions, and a datagram with checksum zero is accepted
    unchecked because IPv4 says it must be.
  * THE IP IDENTIFICATION FIELD MOVES.  It cannot be predicted from
    outside, so it is read out of each built frame, required to differ
    from the last, and then substituted into the expected bytes before
    the byte-exact compare - so everything else stays byte-exact.

Run:  python tools/a64/a64_net_check.py
      python tools/a64/a64_net_check.py --mutate

--mutate rebuilds the library with a deliberate defect in it, nine
times, and requires the gate to go RED each time.  A gate nobody has
ever seen fail is a gate nobody has any reason to believe.
"""

from __future__ import annotations
import os

import argparse
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN. A root pinned into
# the file made this gate build a DIFFERENT working copy, with that copy's
# compiler, and print the answer as this tree's. Override deliberately with
# PMF_REPO; the tree actually read is printed below so a wrong one is visible.
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
from a64_target import (TARGETS, apply_target,  # noqa: E402
                        patch_harness)

REFERENCE = ROOT / "RaspberryPi4" / "Reference"
RFC9293 = REFERENCE / "rfc9293-tcp.txt"
# U-Boot's GENET driver is third-party source code and is not redistributed
# with this repository.  When a local copy is placed here its comment is
# read as the citation for the header length and the MTU; when it is
# absent that one cross-check is skipped with a printed note.
GENET_DRIVER = REFERENCE / "v2025.01_bcmgenet.c"

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "Anvil" / "Network" / "net.pbi"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4NetProbe.pi4"
WORK = ROOT / "_work"

LOAD = 0x00400000
STACK = 0x03000000

# The board this run builds for.  Rebound by apply_target() from the
# --target flag before anything else runs; see tools/a64/a64_target.py.
# Two AArch64 boards now share these libraries - the Pi 4's A72 and the
# Arduino UNO Q's A53 - and they share the FILES, not copies of them, so
# this gate grades both rather than being duplicated.
TFLAG = "pi4"
TARGET_NAME = "pi4"
TARGET_WHAT = TARGETS["pi4"]["what"]
CONSOLE_INCLUDE = TARGETS["pi4"]["console"]

LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
CNTFRQ = 54_000_000
STEPS_PER_TICK = 8
STEP_LIMIT = 200_000_000

UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

# Where the script and the results live.  Far above the image at
# $400000, far above the stack top at $3000000, and nowhere near
# anything net.pi4 or uart.pi4 touches.
H_SCRIPT = 0x06000000
H_RESULT = 0x06800000


# =====================================================================
#  THE CITATIONS THIS GATE CAN ACTUALLY MAKE
# =====================================================================
# Two numbers here are read off the disk rather than typed.  It is a
# small proportion of the constants in play and that is the point of
# saying so - see HOW HONEST THIS GATE IS above.
def cited_eth_hlen_and_mtu() -> tuple[int | None, int | None]:
    """Ethernet header 14, body 1500, from the GENET driver's own comment.

    v2025.01_bcmgenet.c:102 reads
        /* Body(1500) + EH_SIZE(14) + VLANTAG(4) + BRCMTAG(6) + FCS(4) = 1528.
    which is the only place on this disk that states either number.
    """
    if not GENET_DRIVER.exists():
        return None, None
    body = hlen = None
    for line in GENET_DRIVER.read_text(errors="replace").splitlines():
        if "Body(" in line and "EH_SIZE(" in line:
            body = int(line.split("Body(")[1].split(")")[0])
            hlen = int(line.split("EH_SIZE(")[1].split(")")[0])
            break
    if body is None:
        raise SystemExit(
            "v2025.01_bcmgenet.c no longer carries the Body()/EH_SIZE() "
            "comment this gate cites for the MTU and the Ethernet header "
            "length.  Do not replace it with a literal - find the new "
            "citation.")
    return hlen, body


def confirm_checksum_citation() -> tuple[int, int]:
    """Locate the two passages in RFC 9293 the library cites, by content.

    Returns their line numbers.  If the file is replaced by a different
    revision the numbers move and this reports the new ones rather than
    silently letting net.pi4's comment go stale.
    """
    if not RFC9293.exists():
        raise SystemExit(f"the citation is missing: {RFC9293}")
    lines = RFC9293.read_text(errors="replace").splitlines()
    cksum = pseudo = 0
    for i, line in enumerate(lines, 1):
        # The sentence WRAPS in the RFC's own text - "...the ones'" ends
        # line 407 and "complement sum..." begins 408 - so this matches
        # the first half only.  Matching the whole sentence looked
        # correct and found nothing.
        if "16-bit ones' complement of the ones'" in line and not cksum:
            cksum = i
        if "Figure 2: IPv4 Pseudo-header" in line and not pseudo:
            pseudo = i
    if not cksum or not pseudo:
        raise SystemExit(
            "rfc9293-tcp.txt no longer contains the checksum definition or "
            "the IPv4 pseudo-header figure that net.pi4 cites.")
    return cksum, pseudo


# =====================================================================
#  AN INDEPENDENT ENCODER AND AN INDEPENDENT CHECKSUM
# =====================================================================
# Written the other way round from the library's on purpose: this
# unpacks big-endian 16-bit words with struct and sums the list, where
# net.pi4 walks bytes and shifts.  Two implementations that share no
# code do not share an arithmetic slip.
def ones_complement(data: bytes, seed: int = 0) -> int:
    """The 16-bit ones' complement of the ones' complement sum.

    RaspberryPi4/Reference/rfc9293-tcp.txt:407-415.  An odd trailing octet is padded
    with zeros ON ITS RIGHT, i.e. it becomes the HIGH half of the last
    word, which is what ":411-413" says and what a naive implementation
    gets backwards.
    """
    if len(data) % 2:
        data = data + b"\x00"
    total = seed + sum(struct.unpack(">%dH" % (len(data) // 2), data))
    while total > 0xFFFF:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def pseudo_header(src: int, dst: int, proto: int, length: int) -> bytes:
    """The twelve octets of Figure 2, RaspberryPi4/Reference/rfc9293-tcp.txt:426-449.

    That figure is TCP's.  UDP's is the same twelve octets with PTCL 17
    and the UDP length; the authority for the substitution is RFC 768,
    which is not yet in RaspberryPi4/Reference/.  Recorded so the gap is
    visible.
    """
    return struct.pack(">IIBBH", src, dst, 0, proto, length)


def ip4(a: int, b: int, c: int, d: int) -> int:
    return (a << 24) | (b << 16) | (c << 8) | d


def dotted(v: int) -> str:
    return "%d.%d.%d.%d" % ((v >> 24) & 0xFF, (v >> 16) & 0xFF,
                            (v >> 8) & 0xFF, v & 0xFF)


def mac_str(b: bytes) -> str:
    return ":".join("%02X" % x for x in b)


ET_IPV4 = 0x0800        # [RFC 894, uncited]
ET_ARP = 0x0806         # [RFC 826, uncited]
PROTO_ICMP = 1          # [IANA Protocol Numbers, uncited]
PROTO_UDP = 17
BCAST = b"\xFF" * 6


def eth(dst: bytes, src: bytes, ethertype: int, payload: bytes) -> bytes:
    assert len(dst) == 6 and len(src) == 6
    return dst + src + struct.pack(">H", ethertype) + payload


def pad60(frame: bytes) -> bytes:
    """The 60-byte minimum, zero padded.

    genet.pi4:956-971 refuses anything shorter and will not pad it;
    net.pi4 pads in its own buffer instead, and the pad must be ZEROS
    rather than whatever was in the buffer last time.
    """
    if len(frame) < 60:
        frame = frame + b"\x00" * (60 - len(frame))
    return frame


def arp(op: int, sha: bytes, spa: int, tha: bytes, tpa: int) -> bytes:
    """28 octets.  [RFC 826, uncited]"""
    return (struct.pack(">HHBBH", 1, ET_IPV4, 6, 4, op)
            + sha + struct.pack(">I", spa)
            + tha + struct.pack(">I", tpa))


def ipv4(src: int, dst: int, proto: int, payload: bytes,
         ident: int = 0, ttl: int = 64, flags: int = 0x4000,
         options: bytes = b"", total_override: int | None = None,
         version: int = 4, ihl_override: int | None = None,
         bad_checksum: bool = False) -> bytes:
    """[RFC 791, uncited]  Everything is overridable so the gate can
    build malformed headers deliberately."""
    assert len(options) % 4 == 0
    ihl = 5 + len(options) // 4
    if ihl_override is not None:
        ihl = ihl_override
    total = 20 + len(options) + len(payload)
    if total_override is not None:
        total = total_override
    head = (struct.pack(">BBHHHBBH", ((version & 0xF) << 4) | (ihl & 0xF),
                        0, total, ident, flags, ttl, proto, 0)
            + struct.pack(">II", src, dst)
            + options)
    ck = ones_complement(head)
    if bad_checksum:
        ck ^= 0x0100
    head = head[:10] + struct.pack(">H", ck) + head[12:]
    return head + payload


def icmp_echo(msg_type: int, ident: int, seq: int, payload: bytes,
              bad_checksum: bool = False) -> bytes:
    """[RFC 792, uncited]"""
    body = struct.pack(">BBHHH", msg_type, 0, 0, ident, seq) + payload
    ck = ones_complement(body)
    if bad_checksum:
        ck ^= 0x0040
    return body[:2] + struct.pack(">H", ck) + body[4:]


def udp(src: int, dst: int, sport: int, dport: int, payload: bytes,
        checksum: int | None = None, length_override: int | None = None,
        bad_checksum: bool = False) -> bytes:
    """[RFC 768, uncited]  checksum=0 means "not computed"."""
    ulen = 8 + len(payload)
    wire_len = ulen if length_override is None else length_override
    body = struct.pack(">HHHH", sport, dport, wire_len, 0) + payload
    if checksum is None:
        ck = ones_complement(pseudo_header(src, dst, PROTO_UDP, ulen) + body)
        if ck == 0:
            ck = 0xFFFF
    else:
        ck = checksum
    if bad_checksum:
        ck ^= 0x0080
        if ck == 0:
            ck = 0x0080
    return body[:6] + struct.pack(">H", ck) + body[8:]


# The payload Microsoft's ping sends: the lower-case alphabet cycling
# a..w, 32 octets of it.  net.pi4 generates the same pattern for the
# pings it sends, so this doubles as the expectation for that.
LL_PAYLOAD = bytes(97 + (i % 23) for i in range(32))


def abc_payload(n: int) -> bytes:
    return bytes((97 + (i % 23)) for i in range(n))


WINDOWS_PING_PAYLOAD = abc_payload(32)


# =====================================================================
#  THE HARNESS
# =====================================================================
# A fixed source file.  Everything that varies between runs arrives as
# DATA in memory, so this text is the same for the clean library and for
# every mutant, and no test case is ever expressed in harness source.
OP_RESET, OP_SETMAC, OP_SETIP, OP_ARPSET, OP_INPUT = 1, 2, 3, 4, 5
OP_ARPREQ, OP_PING, OP_UDPBUILD, OP_UDPBIND, OP_LOOKUP = 6, 7, 8, 9, 10
OP_UDPRX, OP_PONG, OP_UDPCKTX, OP_CFG, OP_COUNTS = 11, 12, 13, 14, 15
OP_ROUTEMAC, OP_ARPCOUNT = 16, 17
OP_ARPTTL, OP_SPIN = 18, 19

HARNESS = r'''
; ======================================================================
;  netharness.pi4 - GENERATED BY tools/a64/a64_net_check.py. DO NOT EDIT.
; ======================================================================
;  It reads a script of library calls out of memory at #H_SCRIPT, runs
;  them, and writes a result record for each into #H_RESULT. The gate
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
; ======================================================================
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "__LIB__"

; Every call below names the interface.  Anvil/Network/net.pbi keeps one
; row of state per #HW_LINK_* kind; this harness drives the wired row.
#H_KIND = #HW_LINK_WIRED

#H_SCRIPT = $06000000
#H_RESULT = $06800000

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

  NetInit()
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

    If op = 1
      NetInit()
      r = 1
    ElseIf op = 2
      r = NetSetMac(#H_KIND, blob)
      e1 = NetError()
    ElseIf op = 3
      r = NetSetIPv4(#H_KIND, a, b, c)
      e1 = NetError()
    ElseIf op = 4
      r = NetArpSet(#H_KIND, a, blob)
      e1 = NetError()
    ElseIf op = 5
      r = NetInput(#H_KIND, blob, ln)
      e1 = NetError()
      e2 = NetLastProto()
      n = NetOutLen()
      src = NetOutBuf()
    ElseIf op = 6
      r = NetArpRequest(#H_KIND, a)
      e1 = NetError()
      n = NetOutLen()
      src = NetOutBuf()
    ElseIf op = 7
      r = NetPingBuild(#H_KIND, a, b, c, d)
      e1 = NetError()
      n = NetOutLen()
      src = NetOutBuf()
    ElseIf op = 8
      r = NetUdpBuild(#H_KIND, a, b, c, blob, ln)
      e1 = NetError()
      n = NetOutLen()
      src = NetOutBuf()
    ElseIf op = 9
      r = NetUdpBind(#H_KIND, a)
      e1 = NetError()
    ElseIf op = 10
      r = NetArpLookup(#H_KIND, a, @hMac[0])
      If r = 1
        n = 6
        src = @hMac[0]
      EndIf
    ElseIf op = 11
      r = NetUdpRxLen()
      e1 = NetUdpRxFrom()
      e2 = ((NetUdpRxPort() & $FFFF) << 16) | (NetUdpRxDstPort() & $FFFF)
      n = r
      src = NetUdpRxData()
    ElseIf op = 12
      r = NetPongBytes()
      e1 = NetPongFrom()
      e2 = ((NetPongIdent() & $FFFF) << 16) | (NetPongSeq() & $FFFF)
    ElseIf op = 13
      r = NetUdpChecksumTx(a)
    ElseIf op = 14
      r = NetConfigured(#H_KIND)
      e1 = NetIPv4(#H_KIND)
      e2 = NetSubnetBroadcast(#H_KIND)
    ElseIf op = 15
      r = NetInCount()
      e1 = NetReplyCount()
      e2 = NetDropCount()
    ElseIf op = 16
      r = NetRouteMac(#H_KIND, a, @hMac[0])
      e1 = NetError()
      If r = 1
        n = 6
        src = @hMac[0]
      EndIf
    ElseIf op = 17
      r = NetArpCount(#H_KIND)
    ElseIf op = 18
      r = NetArpTtlMs(a)
      e1 = NetError()
    ElseIf op = 19
      ; Burn `a` ticks of CNTPCT_EL0.  There is no other way to make
      ; time pass inside this harness, and until this existed the ARP
      ; cache's EXPIRY - the whole reason net.pi4 reads a clock at all -
      ; was the one behaviour in the file that no case could reach.  The
      ; defect found on silicon on 2026-08-26 lived in exactly that gap.
      e1 = net_Ticks()
      e2 = 0
      While (net_Ticks() - e1) < a
        e2 = e2 + 1
      Wend
      r = 1
    EndIf

    PokeN(q + 0, op)
    PokeN(q + 4, r)
    PokeN(q + 8, e1)
    PokeN(q + 12, e2)
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

  ; A terminator the gate can find, and one line on the console so a
  ; human running this by hand sees that it got to the end.
  PokeN(q, 0)
  UartWriteStr("netharness done")
  ProcedureReturn 0
EndProcedure
'''

# The six-byte scratch the harness needs for NetArpLookup / NetRouteMac.
# Declared before Main so it is a file-level global, matching the way
# the diagnostics in Examples/Diagnostics declare theirs.
HARNESS = HARNESS.replace("Procedure.i Main()",
                          "Global Dim hMac.a[6]\n\nProcedure.i Main()", 1)


class Script:
    """Builds the byte stream the harness walks, and remembers what
    each record was for so a failure can name itself."""

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
        if n > 4096:
            raise SystemExit(
                "a result record claims %d bytes of frame, which is longer "
                "than any frame can be.  The harness or the result stream "
                "has been corrupted." % n)
        blob = bytes(mem.get(addr + 20 + i, 0) for i in range(n))
        i = len(out)
        out.append(Result(op, r, w(8), w(12), blob,
                          labels[i] if i < len(labels) else "?"))
        addr += 20 + ((n + 3) // 4) * 4
    return out


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def write_harness(lib_include: str, path: pathlib.Path) -> None:
    WORK.mkdir(exist_ok=True)
    path.write_text(patch_harness(HARNESS.replace("__LIB__", lib_include),
                              globals()), encoding="utf-8")


def build(source: pathlib.Path, out: pathlib.Path) -> None:
    import subprocess
    WORK.mkdir(exist_ok=True)
    cmd = [str(PMFC), "--compile", str(source), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img: pathlib.Path, script: bytes):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    # Names for the alignment rule's message. "alignment fault at
    # $00484EDA" sends someone hunting; "cyw43seteventmask+332,
    # cyw43.pi4 line 4762" ends the search. Read from the `.dbg` pmfc
    # already writes - NOT the `.sym`, which mixes absolute BSS
    # addresses with load-relative code ones (A64Assembler.pbi:1994-1997)
    # and whose wrong half reads as a column of zeroes rather than an
    # error. A missing `.dbg` costs the name, not the check.
    attach_symbols(cpu, img, LOAD)
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    uart = bytearray()
    steps = [0]

    def load(addr, size):
        # THE ALIGNMENT RULE. This closure replaces A64.load, so the
        # guard has to be CALLED here - see a64_interp.py's ALIGNMENT
        # RULE note. With the MMU off every data access is
        # Device-nGnRnE and an unaligned wide one is a silent runaway
        # on the part; without this line the gate models a machine
        # more permissive than the board it certifies.
        cpu.align_guard(addr, size, False)
        if UART_LO <= addr <= UART_HI:
            # A PL011 that is never busy and never has a character.
            return 0
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
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
        # subject to the data alignment rule. It still goes through
        # the closure above, so MMIO decoding is unchanged.
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = steps[0] // STEPS_PER_TICK
            cpu.pc += 4
            return
        plain_step()

    cpu.step = step
    for _ in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, uart, steps[0]
        step()
    raise SystemExit("the harness never returned (%d steps)\n%s"
                     % (steps[0], uart.decode("latin-1")))


# =====================================================================
#  THE TEST CASES
# =====================================================================
OUR_MAC = bytes([0x02, 0x00, 0x4D, 0x46, 0x00, 0x01])
PC_MAC = bytes([0xDC, 0xA6, 0x32, 0x11, 0x22, 0x33])
GW_MAC = bytes([0x00, 0x1A, 0x2B, 0x3C, 0x4D, 0x5E])
OTHER_MAC = bytes([0x08, 0x00, 0x27, 0xAA, 0xBB, 0xCC])

OUR_IP = ip4(192, 168, 1, 50)
MASK = ip4(255, 255, 255, 0)
GW_IP = ip4(192, 168, 1, 1)
PC_IP = ip4(192, 168, 1, 20)
FAR_IP = ip4(8, 8, 8, 8)
SUBNET_BCAST = ip4(192, 168, 1, 255)

# ---- the bench geometry of 2026-08-26, which had never been tested ----
# A board and a laptop on the two ends of one direct cable, addressed
# link-local, with the laptop serving as gateway because on a cable with
# two machines on it there is nothing else to nominate.  Both MAC
# addresses are the ones that were actually on the wire that day.
#
# WHY THIS GEOMETRY IS ITS OWN CASE.  In every routing case above the
# gateway is a DIFFERENT machine from the host being addressed, so the
# on-link and off-link paths resolve different cache entries and a
# confusion between them shows up immediately.  Here the peer IS the
# gateway, so the two paths resolve the SAME entry - and everything the
# board says to that peer is ICMP and UDP, never ARP.  That combination
# is what went untested, and it is what broke.
LL_BOARD_MAC = bytes([0xDC, 0xA6, 0x32, 0x11, 0x22, 0x33])
LL_PEER_MAC = bytes([0xC4, 0xC6, 0xE6, 0x9D, 0xAB, 0x43])
LL_IP = ip4(169, 254, 183, 50)
LL_MASK = ip4(255, 255, 0, 0)
LL_PEER = ip4(169, 254, 183, 67)
LL_OTHER = ip4(169, 254, 183, 90)

# One ARP lifetime, in CNTPCT_EL0 ticks, at the shortest TTL the library
# will accept.  The real default is twenty seconds, which is 1.08e9
# ticks, and this emulator runs eight instructions per tick - so a real
# lifetime cannot be burned inside a run and a millisecond can.  Nothing
# is special-cased for the short value: NetArpTtlMs() feeds exactly the
# same arithmetic that the default feeds.
TTL_MS = 1
TTL_TICKS = (CNTFRQ // 1000) * TTL_MS
MOST_OF_A_LIFE = (TTL_TICKS * 4) // 5
A_BIT_LONGER = TTL_TICKS // 2
PAST_ITS_LIFE = TTL_TICKS + TTL_TICKS // 4

# The refusal codes.  Written here rather than parsed out of net.pi4 for
# the same reason as everything else - and, unlike the protocol
# constants, this is a value the two files are ALLOWED to state
# independently, because it is ours.  If they disagree the gate goes red
# and one of them is wrong.
E_ARG = -100
E_NO_MAC = -101
E_NO_IP = -102
E_MASK = -103
E_GATEWAY = -104
E_SHORT = -105
E_IP_VERSION = -106
E_IP_HEADER = -107
E_IP_LENGTH = -108
E_IP_CKSUM = -109
E_FRAGMENT = -110
E_ICMP_SHORT = -111
E_ICMP_CKSUM = -112
E_UDP_SHORT = -113
E_UDP_LENGTH = -114
E_UDP_CKSUM = -115
E_ARP_SHORT = -116
E_ARP_PROTO = -117
E_NO_ARP = -118
E_NO_ROUTE = -119
E_TOO_BIG = -120

IN_IGNORED, IN_REPLY, IN_UDP, IN_PONG, IN_LEARNED = 0, 1, 2, 3, 4


def build_script() -> tuple[Script, dict]:
    """The whole run, in order.  Returns the script and a name->index map."""
    s = Script()
    at: dict[str, int] = {}

    def a(name, *args, **kw):
        at[name] = s.add(*args, **kw)

    # ---- configure ------------------------------------------------
    a("reset", OP_RESET, "NetInit")
    a("setmac", OP_SETMAC, "NetSetMac", blob=OUR_MAC)
    a("setip", OP_SETIP, "NetSetIPv4", a=OUR_IP, b=MASK, c=GW_IP)
    a("cfg", OP_CFG, "NetConfigured / address / subnet broadcast")

    # ---- 1. a real ARP request for us ------------------------------
    # Byte for byte what a Windows host puts on the wire when it is
    # about to talk to 192.168.1.50 and does not know its hardware
    # address.  Broadcast destination, 28 octets of ARP, 18 octets of
    # zero pad to reach the 60-byte minimum.
    req = pad60(eth(BCAST, PC_MAC, ET_ARP,
                    arp(1, PC_MAC, PC_IP, b"\x00" * 6, OUR_IP)))
    a("arp_for_us", OP_INPUT, "ARP request for our address",
      blob=req)

    # ---- 2. an ARP request for somebody else -----------------------
    other = pad60(eth(BCAST, OTHER_MAC, ET_ARP,
                      arp(1, OTHER_MAC, ip4(192, 168, 1, 77),
                          b"\x00" * 6, ip4(192, 168, 1, 99))))
    a("arp_for_other", OP_INPUT, "ARP request for a neighbour", blob=other)
    a("arp_other_lookup", OP_LOOKUP, "the neighbour must NOT be cached",
      a=ip4(192, 168, 1, 77))

    # the asker from case 1 must now be in the cache
    a("arp_learned_pc", OP_LOOKUP, "the asker is cached", a=PC_IP)

    # ---- 3. a real ICMP echo request -------------------------------
    ping = eth(OUR_MAC, PC_MAC, ET_IPV4,
               ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                    icmp_echo(8, 0x0001, 0x0025, WINDOWS_PING_PAYLOAD),
                    ident=0x1234))
    a("ping", OP_INPUT, "ICMP echo request, 32-byte a..w payload", blob=ping)

    # an ODD payload, so the checksum's trailing-byte handling is graded
    ping_odd = eth(OUR_MAC, PC_MAC, ET_IPV4,
                   ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                        icmp_echo(8, 0x0002, 0x0026, abc_payload(31)),
                        ident=0x1235))
    a("ping_odd", OP_INPUT, "ICMP echo request, 31-byte payload (odd)",
      blob=ping_odd)

    # ---- 4. the checksum mutations ---------------------------------
    bad_icmp = eth(OUR_MAC, PC_MAC, ET_IPV4,
                   ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                        icmp_echo(8, 3, 1, WINDOWS_PING_PAYLOAD,
                                  bad_checksum=True),
                        ident=0x1236))
    a("ping_bad_icmp_ck", OP_INPUT, "ICMP checksum flipped", blob=bad_icmp)

    bad_ip = eth(OUR_MAC, PC_MAC, ET_IPV4,
                 ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                      icmp_echo(8, 4, 1, WINDOWS_PING_PAYLOAD),
                      ident=0x1237, bad_checksum=True))
    a("ping_bad_ip_ck", OP_INPUT, "IPv4 header checksum flipped", blob=bad_ip)

    # a payload byte flipped WITHOUT recomputing the ICMP checksum -
    # the shape a real corruption takes
    corrupt = bytearray(ping)
    corrupt[14 + 20 + 8 + 5] ^= 0x01
    a("ping_corrupt_payload", OP_INPUT,
      "one payload byte flipped, checksum untouched", blob=bytes(corrupt))

    # ---- 5. malformed and truncated --------------------------------
    a("short_frame", OP_INPUT, "13 bytes - shorter than an Ethernet header",
      blob=ping[:13])
    a("short_ip", OP_INPUT, "an IPv4 header cut to 19 octets",
      blob=ping[:14 + 19])
    a("short_arp", OP_INPUT, "an ARP packet cut to 20 octets",
      blob=req[:14 + 20])

    # ARP over something that is not Ethernet-and-IPv4.  Hardware type
    # 2 is experimental Ethernet; whatever it is, we have nothing to say
    # about it and must say so rather than parsing the fields anyway.
    not_ether = bytearray(req)
    not_ether[15] = 0x02
    a("arp_not_ether", OP_INPUT, "ARP with hardware type 2",
      blob=bytes(not_ether))

    long_total = eth(OUR_MAC, PC_MAC, ET_IPV4,
                     ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                          icmp_echo(8, 5, 1, WINDOWS_PING_PAYLOAD),
                          ident=0x1238, total_override=900))
    a("ip_total_too_long", OP_INPUT,
      "total length 900 in a 74-byte frame", blob=long_total)

    v6 = eth(OUR_MAC, PC_MAC, ET_IPV4,
             ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                  icmp_echo(8, 6, 1, WINDOWS_PING_PAYLOAD),
                  ident=0x1239, version=6))
    a("ip_version_6", OP_INPUT, "the version nibble is 6", blob=v6)

    ihl4 = eth(OUR_MAC, PC_MAC, ET_IPV4,
               ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                    icmp_echo(8, 7, 1, WINDOWS_PING_PAYLOAD),
                    ident=0x123A, ihl_override=4))
    a("ip_ihl_4", OP_INPUT, "IHL 4 - a header shorter than a header",
      blob=ihl4)

    icmp_stub = eth(OUR_MAC, PC_MAC, ET_IPV4,
                    ipv4(PC_IP, OUR_IP, PROTO_ICMP, b"\x08\x00\x00\x00",
                         ident=0x124A))
    a("icmp_short", OP_INPUT, "four octets where an ICMP header should be",
      blob=icmp_stub)

    # ---- 6. fragments ----------------------------------------------
    frag_mf = eth(OUR_MAC, PC_MAC, ET_IPV4,
                  ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                       icmp_echo(8, 8, 1, WINDOWS_PING_PAYLOAD),
                       ident=0x123B, flags=0x2000))
    a("frag_mf", OP_INPUT, "More Fragments set", blob=frag_mf)

    frag_off = eth(OUR_MAC, PC_MAC, ET_IPV4,
                   ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                        icmp_echo(8, 9, 1, WINDOWS_PING_PAYLOAD),
                        ident=0x123C, flags=0x0001))
    a("frag_offset", OP_INPUT, "a non-zero fragment offset", blob=frag_off)

    # ---- 7. IP options are skipped, not mishandled -----------------
    # Four octets of options: NOP, NOP, NOP, End of Option List.
    # [RFC 791, uncited]  IHL becomes 6.
    opts = eth(OUR_MAC, PC_MAC, ET_IPV4,
               ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                    icmp_echo(8, 0x000A, 0x0030, WINDOWS_PING_PAYLOAD),
                    ident=0x123D, options=b"\x01\x01\x01\x00"))
    a("ping_with_options", OP_INPUT, "IHL 6, four octets of IP options",
      blob=opts)

    # ---- 8. not for us ---------------------------------------------
    elsewhere = eth(OTHER_MAC, PC_MAC, ET_IPV4,
                    ipv4(PC_IP, OUR_IP, PROTO_ICMP,
                         icmp_echo(8, 0x000B, 1, WINDOWS_PING_PAYLOAD),
                         ident=0x123E))
    a("wrong_mac", OP_INPUT, "somebody else's MAC address", blob=elsewhere)

    # THE REAL FRAME THE BOARD RECEIVED ON 2026-08-26: a spanning-tree
    # BPDU.  Destination 01:80:C2:00:00:00 and an "EtherType" of $0026,
    # which is 38 and therefore an 802.3 LENGTH, not a type.
    bpdu = pad60(bytes([0x01, 0x80, 0xC2, 0, 0, 0]) + OTHER_MAC
                 + struct.pack(">H", 0x0026)
                 + bytes([0x42, 0x42, 0x03]) + b"\x00" * 35)
    a("bpdu", OP_INPUT, "the spanning-tree BPDU the board really saw",
      blob=bpdu)

    lldp = pad60(eth(BCAST, OTHER_MAC, 0x88CC, b"\x00" * 40))
    a("unknown_ethertype", OP_INPUT, "a broadcast we do not speak", blob=lldp)

    # a ping to the BROADCAST address must not be answered
    bping = eth(BCAST, PC_MAC, ET_IPV4,
                ipv4(PC_IP, SUBNET_BCAST, PROTO_ICMP,
                     icmp_echo(8, 0x000C, 1, WINDOWS_PING_PAYLOAD),
                     ident=0x123F))
    a("broadcast_ping", OP_INPUT, "a ping to the subnet broadcast", blob=bping)

    # ---- 9. UDP ----------------------------------------------------
    a("bind", OP_UDPBIND, "NetUdpBind(9000)", a=9000)

    payload = b"PureMetal Forge, UDP payload, 29"
    good_udp = eth(OUR_MAC, PC_MAC, ET_IPV4,
                   ipv4(PC_IP, OUR_IP, PROTO_UDP,
                        udp(PC_IP, OUR_IP, 40000, 9000, payload),
                        ident=0x1240))
    a("udp_good", OP_INPUT, "a UDP datagram for the bound port",
      blob=good_udp)
    a("udp_rx", OP_UDPRX, "the datagram the library kept")

    bad_udp = eth(OUR_MAC, PC_MAC, ET_IPV4,
                  ipv4(PC_IP, OUR_IP, PROTO_UDP,
                       udp(PC_IP, OUR_IP, 40000, 9000, payload,
                           bad_checksum=True),
                       ident=0x1241))
    a("udp_bad_ck", OP_INPUT, "UDP checksum flipped", blob=bad_udp)

    zero_udp = eth(OUR_MAC, PC_MAC, ET_IPV4,
                   ipv4(PC_IP, OUR_IP, PROTO_UDP,
                        udp(PC_IP, OUR_IP, 40001, 9000, b"nocksum",
                            checksum=0),
                        ident=0x1242))
    a("udp_zero_ck", OP_INPUT, "UDP checksum zero - not computed",
      blob=zero_udp)
    a("udp_zero_rx", OP_UDPRX, "the unchecked datagram")

    long_udp = eth(OUR_MAC, PC_MAC, ET_IPV4,
                   ipv4(PC_IP, OUR_IP, PROTO_UDP,
                        udp(PC_IP, OUR_IP, 40000, 9000, payload,
                            checksum=0, length_override=900),
                        ident=0x1243))
    a("udp_long_len", OP_INPUT, "a UDP length field of 900", blob=long_udp)

    short_udp = eth(OUR_MAC, PC_MAC, ET_IPV4,
                    ipv4(PC_IP, OUR_IP, PROTO_UDP, b"\x00\x01\x02\x03",
                         ident=0x1244))
    a("udp_short", OP_INPUT, "four octets where a UDP header should be",
      blob=short_udp)

    wrongport = eth(OUR_MAC, PC_MAC, ET_IPV4,
                    ipv4(PC_IP, OUR_IP, PROTO_UDP,
                         udp(PC_IP, OUR_IP, 40000, 9001, payload),
                         ident=0x1245))
    a("udp_wrong_port", OP_INPUT, "a datagram for a port nobody bound",
      blob=wrongport)

    # ---- 10. what we BUILD -----------------------------------------
    a("build_arp", OP_ARPREQ, "NetArpRequest(192.168.1.1)", a=GW_IP)
    a("build_ping", OP_PING, "NetPingBuild to a cached host",
      a=PC_IP, b=0x4321, c=7, d=32)
    a("build_udp", OP_UDPBUILD, "NetUdpBuild to a cached host",
      a=PC_IP, b=7777, c=5555, blob=b"forty-one bytes of outbound payload here!")

    # ---- 11. routing -----------------------------------------------
    a("route_unresolved", OP_ROUTEMAC, "an on-link host we have not resolved",
      a=ip4(192, 168, 1, 200))
    a("build_far_no_gw_mac", OP_UDPBUILD,
      "off-link, and the gateway is not resolved yet",
      a=FAR_IP, b=53, c=5555, blob=b"query")
    a("arpset_gw", OP_ARPSET, "pin the gateway's hardware address",
      a=GW_IP, blob=GW_MAC)
    a("build_far", OP_UDPBUILD, "off-link - must go to the GATEWAY's MAC",
      a=FAR_IP, b=53, c=5555, blob=b"query")

    # ---- 12. the refusals ------------------------------------------
    a("too_big", OP_UDPBUILD, "a payload one octet past the MTU",
      a=PC_IP, b=7777, c=5555, blob=b"x" * 1473)
    a("bad_port", OP_UDPBUILD, "destination port 0",
      a=PC_IP, b=0, c=5555, blob=b"x")
    a("ping_too_big", OP_PING, "an ICMP payload one octet past the MTU",
      a=PC_IP, b=1, c=1, d=1473)
    # The two broadcasts resolve without a cache entry, by definition.
    a("lookup_bcast", OP_LOOKUP, "255.255.255.255 needs no ARP",
      a=0xFFFFFFFF)
    a("lookup_subnet_bcast", OP_LOOKUP, "the subnet broadcast needs no ARP",
      a=SUBNET_BCAST)
    a("counts", OP_COUNTS, "the instrumentation")

    a("reset2", OP_RESET, "NetInit again - back to nothing configured")
    a("no_mac_input", OP_INPUT, "a frame before NetSetMac", blob=req)
    a("no_mac_arp", OP_ARPREQ, "NetArpRequest before NetSetMac", a=GW_IP)
    a("mcast_mac", OP_SETMAC, "a multicast MAC address",
      blob=bytes([0x01, 0x00, 0x5E, 0, 0, 1]))
    a("zero_mac", OP_SETMAC, "the all-zero MAC address", blob=b"\x00" * 6)
    a("setmac2", OP_SETMAC, "a good MAC address", blob=OUR_MAC)
    a("no_ip_arp", OP_ARPREQ, "NetArpRequest before NetSetIPv4", a=GW_IP)
    a("bad_mask", OP_SETIP, "the netmask 255.0.255.0",
      a=OUR_IP, b=ip4(255, 0, 255, 0), c=0)
    a("bad_gw", OP_SETIP, "a gateway outside our own subnet",
      a=OUR_IP, b=MASK, c=ip4(10, 0, 0, 1))
    a("net_addr", OP_SETIP, "our address IS the network number",
      a=ip4(192, 168, 1, 0), b=MASK, c=0)
    a("bcast_addr", OP_SETIP, "our address IS the subnet broadcast",
      a=SUBNET_BCAST, b=MASK, c=0)
    a("setip_nogw", OP_SETIP, "a good address with no gateway",
      a=OUR_IP, b=MASK, c=0)
    a("far_no_route", OP_UDPBUILD, "off-link with no gateway configured",
      a=FAR_IP, b=53, c=5555, blob=b"query")

    # ---- 13. THE ON-LINK PEER, AND THE CLOCK -----------------------
    # This group exists because of a defect found on silicon on
    # 2026-08-26, and its absence is why that defect shipped.
    #
    # WHAT WAS SEEN.  Consecutive lines of the probe's stage 7:
    #     peer resolved    1
    #     ping build       0   -> the hardware address is not known
    # NetArpLookup() said the address WAS resolved and NetPingBuild(),
    # called a moment later, refused because it was NOT.  Both could
    # not be true, and both were - a second apart.
    #
    # WHAT IT WAS.  The cache was refreshed by ARP frames and by
    # nothing else, so an entry died on a fixed twenty-second timer
    # however busy the conversation with that neighbour was.  The
    # board and the laptop were exchanging pings the whole time and
    # not one of those pings touched the deadline.
    #
    # WHY IT HAD NEVER BEEN SEEN.  Off-link, the entry the send path
    # needs is the GATEWAY's, and a gateway is a router that ARPs its
    # segment constantly, so ARP traffic keeps it alive as a side
    # effect of other machines' business.  On-link, the entry that
    # matters is the peer's own and the conversation is ICMP and UDP.
    # The one traffic class that could refresh the entry was the one
    # class the conversation never produced.
    #
    # SO THIS GROUP BURNS REAL TIME.  Nothing above it does, which is
    # why nothing above it could have caught this: with no clock
    # advancing, an entry never expires and the whole expiry mechanism
    # - the only reason net.pi4 reads CNTPCT_EL0 at all - was
    # unreachable by any case in the file.
    a("ol_reset", OP_RESET, "NetInit - into the bench geometry")
    a("ol_setmac", OP_SETMAC, "the board's MAC", blob=LL_BOARD_MAC)
    a("ol_setip", OP_SETIP, "169.254.183.50/16, gateway 169.254.183.67",
      a=LL_IP, b=LL_MASK, c=LL_PEER)
    a("ol_ttl", OP_ARPTTL, "NetArpTtlMs(1), so a lifetime fits in a run",
      a=TTL_MS)

    ll_req = pad60(eth(BCAST, LL_PEER_MAC, ET_ARP,
                       arp(1, LL_PEER_MAC, LL_PEER, b"\x00" * 6, LL_IP)))
    a("ol_arp", OP_INPUT, "the peer ARPs for us", blob=ll_req)
    a("ol_lookup", OP_LOOKUP, "the peer is cached", a=LL_PEER)
    a("ol_route", OP_ROUTEMAC,
      "on-link: its OWN MAC, even though it is also the gateway",
      a=LL_PEER)
    a("ol_ping", OP_PING, "an on-link ping, byte for byte",
      a=LL_PEER, b=0x4321, c=1, d=32)
    a("ol_udp", OP_UDPBUILD, "an on-link datagram, byte for byte",
      a=LL_PEER, b=9000, c=5555, blob=LL_PAYLOAD)

    # --- and now the clock, which is the whole point ---
    a("ol_spin1", OP_SPIN, "most of the entry's life burns",
      a=MOST_OF_A_LIFE)
    a("ol_lookup2", OP_LOOKUP, "still cached, with most of its life gone",
      a=LL_PEER)
    a("ol_pong", OP_INPUT, "the peer ANSWERS - proof that it is alive",
      blob=eth(LL_BOARD_MAC, LL_PEER_MAC, ET_IPV4,
               ipv4(LL_PEER, LL_IP, PROTO_ICMP,
                    icmp_echo(0, 0x4321, 1, abc_payload(32)),
                    ident=0x7001)))
    a("ol_spin2", OP_SPIN, "the pump runs on; the original life is over",
      a=A_BIT_LONGER)
    a("ol_lookup3", OP_LOOKUP, "the answer must have confirmed the entry",
      a=LL_PEER)
    a("ol_ping2", OP_PING, "THE BUILD THAT WAS REFUSED ON SILICON",
      a=LL_PEER, b=0x4321, c=2, d=32)
    a("ol_udp2", OP_UDPBUILD, "and the datagram refused with it",
      a=LL_PEER, b=9000, c=5555, blob=LL_PAYLOAD)

    # --- the two things the repair must NOT have bought ---
    # A cache that never forgets is the bug this expiry exists to
    # prevent, and "confirmed by traffic" must not become "confirmed by
    # anybody".  Both are graded here so that a later repair cannot
    # quietly buy the green by giving up either one.
    ll_other_req = pad60(eth(BCAST, OTHER_MAC, ET_ARP,
                             arp(1, OTHER_MAC, LL_OTHER, b"\x00" * 6, LL_IP)))
    a("ol_silent_arp", OP_INPUT, "a second host ARPs for us",
      blob=ll_other_req)
    a("ol_silent_ok", OP_LOOKUP, "it is cached", a=LL_OTHER)
    a("ol_silent_spin", OP_SPIN, "and then it says nothing at all",
      a=PAST_ITS_LIFE)
    a("ol_silent_gone", OP_LOOKUP, "a SILENT neighbour must still expire",
      a=LL_OTHER)

    a("ol_imp_arp", OP_INPUT, "the second host ARPs again",
      blob=ll_other_req)
    a("ol_imp_spin1", OP_SPIN, "most of its life burns", a=MOST_OF_A_LIFE)
    a("ol_imp_frame", OP_INPUT,
      "a datagram carrying its IP but a DIFFERENT source MAC",
      blob=eth(LL_BOARD_MAC, LL_PEER_MAC, ET_IPV4,
               ipv4(LL_OTHER, LL_IP, PROTO_ICMP,
                    icmp_echo(8, 0x1111, 1, abc_payload(8)),
                    ident=0x7002)))
    a("ol_imp_spin2", OP_SPIN, "a little longer", a=A_BIT_LONGER)
    a("ol_imp_gone", OP_LOOKUP,
      "an impostor's MAC must have confirmed NOTHING", a=LL_OTHER)

    return s, at


# =====================================================================
#  THE ASSERTIONS
# =====================================================================
def expect(cond, what, fails):
    if not cond:
        fails.append(what)


def hexdiff(got: bytes, want: bytes) -> str:
    if len(got) != len(want):
        return "length %d, wanted %d" % (len(got), len(want))
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            return ("first difference at offset %d: got $%02X, wanted $%02X\n"
                    "        got  %s\n        want %s"
                    % (i, g, w, got.hex(), want.hex()))
    return ""


def check(res: list[Result], at: dict, fails: list[str]) -> None:
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

    def err(name, want):
        # NetError() is negative and the result record carries it as a
        # 32-bit word, so it comes back as its unsigned image.  Only
        # this reading is sign-extended: extra1 also carries IPv4
        # addresses, and 192.168.1.50 has its top bit set.
        r = R(name)
        v = r.e1 - 0x100000000 if r.e1 & 0x80000000 else r.e1
        if v != want:
            fails.append("%s (%s): NetError() is %d, wanted %d"
                         % (name, r.label, v, want))

    def no_frame(name):
        r = R(name)
        if r.blob:
            fails.append("%s (%s): staged a %d-byte frame and should have "
                         "staged nothing" % (name, r.label, len(r.blob)))

    def frame_is(name, want, note=""):
        r = R(name)
        d = hexdiff(r.blob, want)
        if d:
            fails.append("%s (%s)%s: %s"
                         % (name, r.label, "  " + note if note else "", d))

    # ---- configuration --------------------------------------------
    code("setmac", 1)
    code("setip", 1)
    cfg = R("cfg")
    expect(cfg.r == 1, "NetConfigured() is %d after both setters" % cfg.r,
           fails)
    expect(cfg.e1 == OUR_IP,
           "NetIPv4() is %s, wanted %s" % (dotted(cfg.e1), dotted(OUR_IP)),
           fails)
    expect(cfg.e2 == SUBNET_BCAST,
           "NetSubnetBroadcast() is %s, wanted %s"
           % (dotted(cfg.e2), dotted(SUBNET_BCAST)), fails)

    # ---- 1. the ARP reply, all sixty octets ------------------------
    code("arp_for_us", IN_REPLY, "an ARP request for our own address")
    frame_is("arp_for_us",
             pad60(eth(PC_MAC, OUR_MAC, ET_ARP,
                       arp(2, OUR_MAC, OUR_IP, PC_MAC, PC_IP))),
             "the reply must be unicast to the asker, 60 octets, "
             "zero padded")
    r = R("arp_for_us")
    expect(len(r.blob) == 60,
           "the ARP reply is %d octets; genet.pi4:971 (#GENET_MIN_FRAME) refuses anything "
           "under 60 and net.pi4 must pad in its own buffer"
           % len(r.blob), fails)
    expect(r.blob[42:] == b"\x00" * 18,
           "the ARP reply's pad is not zeros: %s - a short frame padded "
           "with whatever was in the buffer leaks the board's memory onto "
           "the network" % r.blob[42:].hex(), fails)
    expect(R("arp_for_us").e2 == ET_ARP,
           "NetLastProto() after an ARP frame is $%04X, wanted $0806"
           % R("arp_for_us").e2, fails)

    # ---- 2. not our address ----------------------------------------
    code("arp_for_other", IN_IGNORED,
         "an ARP request for a neighbour must be ignored, not answered")
    no_frame("arp_for_other")
    code("arp_other_lookup", 0,
         "a broadcast ARP from a stranger must not create a cache entry - "
         "eight slots fill in seconds on a busy segment otherwise")
    code("arp_learned_pc", 1,
         "the host that ARPed FOR US should have been cached")
    frame_is("arp_learned_pc", PC_MAC)

    # ---- 3. the echo replies ---------------------------------------
    ids = {}

    def check_echo(name, ident, seq, payload, want_ihl_note=""):
        r = R(name)
        if r.r != IN_REPLY:
            fails.append("%s (%s): returned %d, wanted %d (an echo reply)"
                         % (name, r.label, r.r, IN_REPLY))
            return
        if len(r.blob) < 34:
            fails.append("%s: the reply is only %d octets" % (name, len(r.blob)))
            return
        # THE IP IDENTIFICATION IS A COUNTER INSIDE THE LIBRARY and
        # cannot be predicted from out here.  It is read back, required
        # to be new, and then substituted - so every other octet stays
        # byte-exact.
        got_id = struct.unpack(">H", r.blob[18:20])[0]
        ids[name] = got_id
        want = eth(PC_MAC, OUR_MAC, ET_IPV4,
                   ipv4(OUR_IP, PC_IP, PROTO_ICMP,
                        icmp_echo(0, ident, seq, payload), ident=got_id))
        d = hexdiff(r.blob, want)
        if d:
            fails.append("%s (%s)%s: %s"
                         % (name, r.label, want_ihl_note, d))

    check_echo("ping", 0x0001, 0x0025, WINDOWS_PING_PAYLOAD)
    check_echo("ping_odd", 0x0002, 0x0026, abc_payload(31),
               " - an ODD payload length, so the checksum's trailing "
               "octet must be padded on its RIGHT")
    check_echo("ping_with_options", 0x000A, 0x0030, WINDOWS_PING_PAYLOAD,
               " - the request carried IP options; the reply must not")

    if len(ids) >= 2:
        vals = list(ids.values())
        expect(len(set(vals)) == len(vals),
               "the IPv4 Identification field repeated across replies: %s"
               % vals, fails)
        expect(all(v != 0 for v in vals),
               "the IPv4 Identification field is zero", fails)

    # the reply's TTL, flags and source, called out by name because a
    # byte-exact compare says "offset 22" and not what lives there
    pr = R("ping")
    if len(pr.blob) >= 34:
        expect(pr.blob[22] == 64,
               "the reply's TTL is %d, wanted 64" % pr.blob[22], fails)
        expect(struct.unpack(">H", pr.blob[20:22])[0] & 0x4000 != 0,
               "the reply does not set Don't Fragment.  This stack cannot "
               "reassemble, so it must ask not to be fragmented",
               fails)
        expect(pr.blob[0:6] == PC_MAC,
               "the echo reply went to %s and not to the frame's own "
               "source %s.  Answering from the ARP cache instead of from "
               "the frame means the very first ping of a session is "
               "refused" % (mac_str(pr.blob[0:6]), mac_str(PC_MAC)), fails)
        expect(pr.blob[14] == 0x45,
               "the reply's version/IHL octet is $%02X, wanted $45 - we "
               "emit no options" % pr.blob[14], fails)

    # ---- 4. the checksum mutations ---------------------------------
    code("ping_bad_icmp_ck", E_ICMP_CKSUM)
    no_frame("ping_bad_icmp_ck")
    code("ping_bad_ip_ck", E_IP_CKSUM)
    no_frame("ping_bad_ip_ck")
    code("ping_corrupt_payload", E_ICMP_CKSUM,
         "a flipped payload octet with the original checksum is exactly "
         "what corruption looks like")
    no_frame("ping_corrupt_payload")

    # ---- 5. malformed and truncated --------------------------------
    code("short_frame", E_SHORT)
    code("short_ip", E_SHORT)
    code("short_arp", E_ARP_SHORT)
    code("ip_total_too_long", E_IP_LENGTH)
    code("ip_version_6", E_IP_VERSION)
    code("ip_ihl_4", E_IP_HEADER)
    code("icmp_short", E_ICMP_SHORT)
    for n in ("short_frame", "short_ip", "short_arp", "ip_total_too_long",
              "ip_version_6", "ip_ihl_4", "icmp_short"):
        no_frame(n)

    # ---- 6. fragments ----------------------------------------------
    code("frag_mf", E_FRAGMENT,
         "a fragment must be REFUSED, not treated as a whole datagram")
    code("frag_offset", E_FRAGMENT)
    no_frame("frag_mf")
    no_frame("frag_offset")

    # ---- 8. not for us ---------------------------------------------
    code("wrong_mac", IN_IGNORED)
    no_frame("wrong_mac")
    code("bpdu", IN_IGNORED,
         "the real BPDU off the board: a multicast destination and an "
         "802.3 length field, not an EtherType")
    no_frame("bpdu")
    code("unknown_ethertype", IN_IGNORED)
    code("broadcast_ping", IN_IGNORED,
         "a ping to a broadcast address must not be answered")
    no_frame("broadcast_ping")

    # ---- 9. UDP ----------------------------------------------------
    code("bind", 1)
    code("udp_good", IN_UDP)
    ur = R("udp_rx")
    payload = b"PureMetal Forge, UDP payload, 29"
    expect(ur.r == len(payload),
           "NetUdpRxLen() is %d, wanted %d" % (ur.r, len(payload)), fails)
    expect(ur.blob == payload,
           "the delivered payload is %r, wanted %r" % (ur.blob, payload),
           fails)
    expect(ur.e1 == PC_IP,
           "NetUdpRxFrom() is %s, wanted %s" % (dotted(ur.e1), dotted(PC_IP)),
           fails)
    expect((ur.e2 >> 16) == 40000 and (ur.e2 & 0xFFFF) == 9000,
           "the ports came back as %d -> %d, wanted 40000 -> 9000"
           % (ur.e2 >> 16, ur.e2 & 0xFFFF), fails)

    code("udp_bad_ck", E_UDP_CKSUM,
         "a UDP checksum covers the pseudo-header too; if this passes, "
         "the pseudo-header is probably missing from the sum")
    code("udp_zero_ck", IN_UDP,
         "checksum zero means NOT COMPUTED for IPv4 UDP and the datagram "
         "must be accepted unchecked")
    zr = R("udp_zero_rx")
    expect(zr.blob == b"nocksum",
           "the unchecked datagram delivered %r" % zr.blob, fails)
    code("udp_long_len", E_UDP_LENGTH)
    code("udp_short", E_UDP_SHORT)
    code("udp_wrong_port", IN_IGNORED,
         "nothing is bound to 9001, and no ICMP port unreachable is sent")

    # ---- 10. what we build -----------------------------------------
    code("build_arp", 1)
    frame_is("build_arp",
             pad60(eth(BCAST, OUR_MAC, ET_ARP,
                       arp(1, OUR_MAC, OUR_IP, b"\x00" * 6, GW_IP))),
             "a broadcast request with a ZERO target hardware address")

    bp = R("build_ping")
    expect(bp.r == 1, "NetPingBuild returned %d (NetError %d)"
           % (bp.r, bp.e1), fails)
    if bp.blob:
        got_id = struct.unpack(">H", bp.blob[18:20])[0]
        want = eth(PC_MAC, OUR_MAC, ET_IPV4,
                   ipv4(OUR_IP, PC_IP, PROTO_ICMP,
                        icmp_echo(8, 0x4321, 7, abc_payload(32)),
                        ident=got_id))
        d = hexdiff(bp.blob, want)
        if d:
            fails.append("build_ping: %s" % d)

    bu = R("build_udp")
    outp = b"forty-one bytes of outbound payload here!"
    expect(bu.r == 1, "NetUdpBuild returned %d (NetError %d)"
           % (bu.r, bu.e1), fails)
    if bu.blob:
        got_id = struct.unpack(">H", bu.blob[18:20])[0]
        want = eth(PC_MAC, OUR_MAC, ET_IPV4,
                   ipv4(OUR_IP, PC_IP, PROTO_UDP,
                        udp(OUR_IP, PC_IP, 5555, 7777, outp),
                        ident=got_id))
        d = hexdiff(bu.blob, want)
        if d:
            fails.append("build_udp (the UDP checksum here is computed over "
                         "the pseudo-header of rfc9293-tcp.txt:426-449 with "
                         "PTCL 17): %s" % d)

    # ---- 11. routing -----------------------------------------------
    code("route_unresolved", 0)
    err("route_unresolved", E_NO_ARP)
    code("build_far_no_gw_mac", 0)
    err("build_far_no_gw_mac", E_NO_ARP)
    code("arpset_gw", 1)
    bf = R("build_far")
    expect(bf.r == 1, "the off-link build returned %d (NetError %d)"
           % (bf.r, bf.e1), fails)
    if len(bf.blob) >= 34:
        expect(bf.blob[0:6] == GW_MAC,
               "an off-link datagram was addressed to %s.  It must go to "
               "THE GATEWAY'S hardware address (%s) while the IP "
               "destination stays the far host - the commonest wrong line "
               "in a first IP stack"
               % (mac_str(bf.blob[0:6]), mac_str(GW_MAC)), fails)
        dst = struct.unpack(">I", bf.blob[30:34])[0]
        expect(dst == FAR_IP,
               "the off-link datagram's IP destination is %s, wanted %s - "
               "the frame goes to the router, the datagram does not"
               % (dotted(dst), dotted(FAR_IP)), fails)

    # ---- 12. the refusals ------------------------------------------
    code("arp_not_ether", E_ARP_PROTO)
    no_frame("arp_not_ether")
    code("too_big", 0)
    err("too_big", E_TOO_BIG)
    code("bad_port", 0)
    code("ping_too_big", 0)
    err("ping_too_big", E_TOO_BIG)
    code("lookup_bcast", 1,
         "255.255.255.255 maps to ff:ff:ff:ff:ff:ff by definition and "
         "there is nobody to ask")
    frame_is("lookup_bcast", BCAST)
    code("lookup_subnet_bcast", 1)
    frame_is("lookup_subnet_bcast", BCAST)
    code("no_mac_input", E_NO_MAC)
    code("no_mac_arp", 0)
    err("no_mac_arp", E_NO_MAC)
    code("mcast_mac", 0)
    code("zero_mac", 0)
    code("setmac2", 1)
    code("no_ip_arp", 0)
    err("no_ip_arp", E_NO_IP)
    code("bad_mask", 0)
    err("bad_mask", E_MASK)
    code("bad_gw", 0)
    err("bad_gw", E_GATEWAY)
    code("net_addr", 0)
    code("bcast_addr", 0)
    code("setip_nogw", 1)
    code("far_no_route", 0)
    err("far_no_route", E_NO_ROUTE)

    # ---- 13. the on-link peer, and the clock -----------------------
    code("ol_setip", 1)
    code("ol_ttl", 1)
    code("ol_arp", IN_REPLY)
    frame_is("ol_arp",
             pad60(eth(LL_PEER_MAC, LL_BOARD_MAC, ET_ARP,
                       arp(2, LL_BOARD_MAC, LL_IP, LL_PEER_MAC, LL_PEER))),
             "a unicast ARP reply to the peer")
    code("ol_lookup", 1)
    frame_is("ol_lookup", LL_PEER_MAC)

    code("ol_route", 1)
    frame_is("ol_route", LL_PEER_MAC,
             "an ON-LINK destination resolves to its own hardware "
             "address.  That it is ALSO the configured gateway must not "
             "route the frame anywhere else")

    def onlink_ping(name, seq):
        r = R(name)
        expect(r.r == 1,
               "%s (%s): NetPingBuild returned %d, NetError %d"
               % (name, r.label, r.r, r.e1), fails)
        if r.blob:
            got_id = struct.unpack(">H", r.blob[18:20])[0]
            want = eth(LL_PEER_MAC, LL_BOARD_MAC, ET_IPV4,
                       ipv4(LL_IP, LL_PEER, PROTO_ICMP,
                            icmp_echo(8, 0x4321, seq, abc_payload(32)),
                            ident=got_id))
            d = hexdiff(r.blob, want)
            if d:
                fails.append("%s: %s" % (name, d))

    def onlink_udp(name):
        r = R(name)
        expect(r.r == 1,
               "%s (%s): NetUdpBuild returned %d, NetError %d"
               % (name, r.label, r.r, r.e1), fails)
        if r.blob:
            got_id = struct.unpack(">H", r.blob[18:20])[0]
            want = eth(LL_PEER_MAC, LL_BOARD_MAC, ET_IPV4,
                       ipv4(LL_IP, LL_PEER, PROTO_UDP,
                            udp(LL_IP, LL_PEER, 5555, 9000, LL_PAYLOAD),
                            ident=got_id))
            d = hexdiff(r.blob, want)
            if d:
                fails.append("%s: %s" % (name, d))

    onlink_ping("ol_ping", 1)
    onlink_udp("ol_udp")

    code("ol_lookup2", 1, "most of a lifetime is not all of it")
    code("ol_pong", IN_PONG)

    # The three that reproduce 2026-08-26 exactly.  Before the repair
    # ol_lookup3 answered 0 and both builds refused with #NET_E_NO_ARP,
    # having been told by ol_lookup2 a moment earlier that the address
    # was known.
    ol3 = R("ol_lookup3")
    expect(ol3.r == 1,
           "ol_lookup3: the peer had just ANSWERED A PING and its entry "
           "was still allowed to expire.  This is the defect of "
           "2026-08-26: a cache refreshed by ARP frames and by nothing "
           "else dies in the middle of a conversation that is proving "
           "the neighbour alive.  See net_ConfirmNeighbour in net.pi4",
           fails)
    frame_is("ol_lookup3", LL_PEER_MAC)
    onlink_ping("ol_ping2", 2)
    onlink_udp("ol_udp2")

    code("ol_silent_ok", 1)
    sg = R("ol_silent_gone")
    expect(sg.r == 0,
           "ol_silent_gone: a neighbour that has said nothing for longer "
           "than the TTL is still in the cache.  Expiry has been "
           "disabled, which is not a repair - see #NET_ARP_TTL_MS_DEFAULT "
           "for why a bench stack forgets quickly", fails)

    ig = R("ol_imp_gone")
    expect(ig.r == 0,
           "ol_imp_gone: a datagram carrying a neighbour's IP address "
           "from a DIFFERENT hardware address renewed that neighbour's "
           "entry.  Confirmation must compare the stored MAC and refuse "
           "on a mismatch, or any host on the segment can keep any entry "
           "alive indefinitely", fails)

    # ---- the counters ----------------------------------------------
    cn = R("counts")
    expect(cn.r > 20,
           "NetInCount() is %d after more than twenty frames" % cn.r, fails)
    expect(cn.e1 >= 4,
           "NetReplyCount() is %d; four ARP/ICMP replies were staged"
           % cn.e1, fails)


# =====================================================================
#  MUTATION - proof the gate can go red
# =====================================================================
MUTATIONS = [
    # The three that guard 2026-08-26.  The first is the defect itself,
    # put back; the other two are the two ways a careless repair of it
    # would have been worse than the disease.
    ("traffic from a neighbour no longer confirms its cache entry",
     "  net_ConfirmNeighbour(kind, srcIp, *srcMac)",
     "  ; the confirmation, removed by a mutation"),

    ("any source MAC confirms the entry, not only the stored one",
     "  If net_Same(@net_arpMac[s * 6], *srcMac, 6) = 0\n"
     "    ProcedureReturn\n"
     "  EndIf",
     "  ; the hardware-address compare, removed by a mutation"),

    ("the ARP cache never expires at all",
     "      If (now - net_arpDeadline[i]) > 0\n"
     "        net_arpState[i] = 0\n"
     "        net_arpKind[i] = #HW_LINK_NONE\n"
     "      EndIf",
     "      ; the expiry, removed by a mutation"),

    ("the ICMP checksum never verified",
     "  If net_Cksum(net_Sum16(*p, n, 0)) <> 0\n"
     "    net_err = #NET_E_ICMP_CKSUM\n"
     "    ProcedureReturn #NET_E_ICMP_CKSUM\n"
     "  EndIf",
     "  ; the check, removed by a mutation"),

    ("the IPv4 header checksum never verified",
     "  If net_Cksum(net_Sum16(*a, ihl, 0)) <> 0\n"
     "    net_err = #NET_E_IP_CKSUM\n"
     "    ProcedureReturn #NET_E_IP_CKSUM\n"
     "  EndIf",
     "  ; the check, removed by a mutation"),

    # The one a future reader is most likely to delete as over-cautious,
    # and the one whose absence is silent corruption rather than a fault.
    ("the fragment refusal deleted - the first fragment treated as a "
     "whole datagram",
     "  If (ff & #NET_IP_FLAG_MF) <> 0\n"
     "    net_err = #NET_E_FRAGMENT\n"
     "    ProcedureReturn #NET_E_FRAGMENT\n"
     "  EndIf\n"
     "  If (ff & #NET_IP_FRAG_MASK) <> 0\n"
     "    net_err = #NET_E_FRAGMENT\n"
     "    ProcedureReturn #NET_E_FRAGMENT\n"
     "  EndIf",
     "  ; the refusals, removed by a mutation"),

    # Byte order.  The classic, and the one that produces a plausible
    # wrong number rather than a crash.
    ("net_PutBE16 writes LITTLE-endian",
     "Procedure net_PutBE16(*p, v.i)\n"
     "  PokeB(*p + 0, (v >> 8) & $FF)\n"
     "  PokeB(*p + 1, v & $FF)\n"
     "EndProcedure",
     "Procedure net_PutBE16(*p, v.i)\n"
     "  PokeB(*p + 0, v & $FF)\n"
     "  PokeB(*p + 1, (v >> 8) & $FF)\n"
     "EndProcedure"),

    # The odd trailing octet padded on the WRONG side.  Correct for
    # every even-length packet, wrong for every odd one.
    ("the checksum's odd trailing octet padded on the LEFT",
     "  If i < n\n"
     "    sum = sum + (PeekA(*p + i) << 8)\n"
     "  EndIf",
     "  If i < n\n"
     "    sum = sum + PeekA(*p + i)\n"
     "  EndIf"),

    ("the UDP pseudo-header dropped from the TRANSMIT checksum",
     "    sum = net_PseudoSum(src, dstIp & $FFFFFFFF, #NET_PROTO_UDP, ulen, 0)\n"
     "    sum = net_Sum16(@net_out[p], ulen, sum)",
     "    sum = net_Sum16(@net_out[p], ulen, 0)"),

    ("the UDP pseudo-header dropped from the RECEIVE check",
     "    sum = net_PseudoSum(srcIp, dstIp, #NET_PROTO_UDP, ulen, 0)\n"
     "    sum = net_Sum16(*p, ulen, sum)",
     "    sum = net_Sum16(*p, ulen, 0)"),

    ("off-link traffic addressed to the destination instead of the gateway",
     "      target = net_ifGw[kind]\n"
     "    EndIf\n"
     "  EndIf\n"
     "  If NetArpLookup(kind, target, *out) = 0",
     "      target = ip & $FFFFFFFF\n"
     "    EndIf\n"
     "  EndIf\n"
     "  If NetArpLookup(kind, target, *out) = 0"),

    ("short frames no longer padded to 60 octets",
     "  i = n\n"
     "  While i < #NET_FRAME_MIN\n"
     "    net_out[i] = 0\n"
     "    i = i + 1\n"
     "  Wend\n"
     "  If n < #NET_FRAME_MIN\n"
     "    net_outLen = #NET_FRAME_MIN\n"
     "  Else\n"
     "    net_outLen = n\n"
     "  EndIf",
     "  net_outLen = n"),

    # Anvil main answers ARP for either of an interface's two addresses and
    # records which one was asked for in `mine`; the refusal is the
    # `mine = 0` branch.  The same defect: claim whatever address was asked.
    ("ARP requests answered for addresses we do not own",
     "  If mine = 0\n"
     "    ; Somebody else's conversation. Extremely common - this is most of\n"
     "    ; the broadcast traffic on any segment - and NOT an error.\n"
     "    ProcedureReturn #NET_IN_IGNORED\n"
     "  EndIf",
     "  If mine = 0\n"
     "    mine = tpa\n"
     "  EndIf"),

    ("the echo reply left as type 8 - a request, not a reply",
     "  net_out[q + 0] = #NET_ICMP_ECHO_REPLY",
     "  net_out[q + 0] = #NET_ICMP_ECHO_REQUEST"),

    ("the TTL emitted as 1",
     "#NET_IP_TTL_DEFAULT  = 64",
     "#NET_IP_TTL_DEFAULT  = 1"),
]


def one_run(lib_include: str, harness: pathlib.Path, img: pathlib.Path,
            script: Script):
    write_harness(lib_include, harness)
    build(harness, img)
    cpu, uart, steps = run(img, script.finish())
    res = read_results(cpu.memory, script.labels)
    return res, uart, steps


def mutate_run(name, old, new, script: Script) -> bool:
    """Returns True if the gate went red, which is what we want."""
    WORK.mkdir(exist_ok=True)
    src = LIB.read_text(encoding="utf-8", errors="replace")
    if src.count(old) != 1:
        print("   SKIPPED - the anchor text appears %d times in net.pbi, "
              "not once" % src.count(old))
        return False
    (WORK / "net_mut.pi4").write_text(src.replace(old, new), encoding="utf-8")
    try:
        res, _uart, _steps = one_run("_work/net_mut.pi4",
                                     WORK / "netharness_mut.pi4",
                                     WORK / "netcheck_mut.img", script)
    except SystemExit as e:
        print("   (the harness refused it: %s)" % str(e).splitlines()[0][:90])
        return True
    fails: list[str] = []
    check(res, MUT_AT, fails)
    return bool(fails)


MUT_AT: dict = {}


# =====================================================================
#  THE LOOPBACK LINK
# =====================================================================
#  Added 2026-09-04 with the Arduino UNO Q, and it is a different KIND
#  of evidence from the 88 cases above, not more of the same.
#
#  Those 88 compare what the library emits against what THIS FILE says
#  the bytes should be.  The honesty note at the top of this gate is
#  blunt about the limit: for everything but the checksum and the
#  Ethernet header length that is a SECOND TRANSCRIPTION, and a gate and
#  a library that made the same mistake would agree.
#
#  The loopback closes the other axis.  It feeds the library's OWN
#  output back into the library's input and asserts the payload survives
#  the round trip.  The gate contributes no protocol knowledge at all -
#  its entire model of the wire is:
#
#      swap the two six-byte Ethernet addresses,
#      and, if this is IPv4, the two four-byte IPv4 addresses.
#
#  NO CHECKSUM IS RECOMPUTED, AND THAT IS A PROPERTY OF THE PROTOCOL
#  RATHER THAN A SHORTCUT.  The IPv4 header checksum and the UDP
#  pseudo-header checksum are both one's-complement sums over the whole
#  set of 16-bit words, and a sum does not care what order its terms
#  arrive in - so exchanging source and destination leaves both
#  checksums correct.  If either check started failing on a swapped
#  frame, that alone would be a finding.
#
#  WHY THIS IS THE RIGHT SHAPE FOR "A LOOPBACK LINK" AND A SECOND
#  INSTANCE OF THE STACK IS NOT.  net.pi4 keeps its state in file-level
#  globals - one MAC, one address, one ARP cache, one staging buffer -
#  so two conversing instances cannot exist in one image.  Feeding the
#  wire back to the same instance is the loopback that this library can
#  actually have, and it exercises exactly the join the 88 cases cannot:
#  encoder against decoder.
#
#  It runs in TWO PASSES because the frame to feed in is not known until
#  the first pass has staged it.  Pass 1 builds; pass 2 replays.
LB_PEER_IP = PC_IP
LB_PEER_MAC = PC_MAC
LB_PORT = 5555

# payload lengths worth carrying: empty, one byte, an ODD length (the
# checksum's trailing-byte pad is padded on its RIGHT and getting that
# backwards is correct for every even length), a typical one, and the
# largest that still fits one frame.
LB_LENS = [0, 1, 7, 32, 1472]


def wire_swap(frame: bytes) -> bytes:
    """The whole wire model.  See the block comment above."""
    f = bytearray(frame)
    dst, src = bytes(f[0:6]), bytes(f[6:12])
    f[0:6], f[6:12] = src, dst
    if bytes(f[12:14]) == b"\x08\x00":
        s, d = bytes(f[26:30]), bytes(f[30:34])
        f[26:30], f[30:34] = d, s
    return bytes(f)


def loopback_setup(s: Script) -> None:
    s.add(OP_RESET, "lb reset")
    s.add(OP_SETMAC, "lb mac", blob=OUR_MAC)
    s.add(OP_SETIP, "lb ip", a=OUR_IP, b=MASK, c=GW_IP)
    s.add(OP_ARPSET, "lb arp seed", a=LB_PEER_IP, blob=LB_PEER_MAC)
    s.add(OP_UDPBIND, "lb bind", a=LB_PORT)


def loopback(harness: pathlib.Path, img: pathlib.Path) -> list[str]:
    """Two passes.  Returns a list of failures, empty when green."""
    fails: list[str] = []

    # ---- pass 1: the library BUILDS ---------------------------------
    s1 = Script()
    loopback_setup(s1)
    built = {}
    for n in LB_LENS:
        built["udp%d" % n] = s1.add(
            OP_UDPBUILD, "lb build udp %d" % n,
            a=LB_PEER_IP, b=LB_PORT, c=LB_PORT, blob=abc_payload(n))
    for i, n in enumerate([0, 1, 7, 32]):
        built["icmp%d" % n] = s1.add(
            OP_PING, "lb build ping %d" % n,
            a=LB_PEER_IP, b=0x4D46 + i, c=100 + i, d=n)
    # NetPingBuild's payload is generated by the library, so the gate
    # must read it back rather than assume it - which is the point.
    r1 = one_run("Anvil/Network/net.pbi", harness, img, s1)[0]

    # ---- pass 2: the same frames come back in -----------------------
    s2 = Script()
    loopback_setup(s2)
    at = {}
    for n in LB_LENS:
        frame = r1[built["udp%d" % n]].blob
        if not frame:
            fails.append("loopback: nothing was staged for a %d-byte UDP "
                         "payload, so there is nothing to send back" % n)
            continue
        at["udp_in%d" % n] = s2.add(OP_INPUT, "lb udp in %d" % n,
                                    blob=wire_swap(frame))
        at["udp_rx%d" % n] = s2.add(OP_UDPRX, "lb udp rx %d" % n)
    for n in [0, 1, 7, 32]:
        frame = r1[built["icmp%d" % n]].blob
        if not frame:
            fails.append("loopback: nothing was staged for a %d-byte echo "
                         "request" % n)
            continue
        at["icmp_in%d" % n] = s2.add(OP_INPUT, "lb echo in %d" % n,
                                     blob=wire_swap(frame))
    r2 = one_run("Anvil/Network/net.pbi", harness, img, s2)[0]

    # ---- what has to be true ----------------------------------------
    for n in LB_LENS:
        if "udp_in%d" % n not in at:
            continue
        rin = r2[at["udp_in%d" % n]]
        rrx = r2[at["udp_rx%d" % n]]
        if rin.r != 2:                                    # #NET_IN_UDP
            fails.append("loopback udp %d: NetInput returned %d, wanted "
                         "#NET_IN_UDP (2), err %d - the library did not "
                         "recognise its own datagram coming back"
                         % (n, rin.r, rin.e1))
            continue
        if rrx.blob != abc_payload(n):
            fails.append("loopback udp %d: the payload did not survive the "
                         "round trip\n%s"
                         % (n, hexdiff(rrx.blob, abc_payload(n))))
        if rrx.e1 != LB_PEER_IP:
            fails.append("loopback udp %d: NetUdpRxFrom is %s, wanted %s"
                         % (n, dotted(rrx.e1), dotted(LB_PEER_IP)))
        if (rrx.e2 & 0xFFFF) != LB_PORT:
            fails.append("loopback udp %d: it arrived on port %d, not %d"
                         % (n, rrx.e2 & 0xFFFF, LB_PORT))

    for n in [0, 1, 7, 32]:
        if "icmp_in%d" % n not in at:
            continue
        rin = r2[at["icmp_in%d" % n]]
        if rin.r != 1:                                    # #NET_IN_REPLY
            fails.append("loopback echo %d: NetInput returned %d, wanted "
                         "#NET_IN_REPLY (1), err %d" % (n, rin.r, rin.e1))
            continue
        sent = r1[built["icmp%d" % n]].blob
        got = rin.blob
        if len(got) != len(sent):
            fails.append("loopback echo %d: the reply is %d octets and the "
                         "request was %d" % (n, len(got), len(sent)))
            continue
        # Everything from the ICMP identifier onwards must come back
        # unchanged: ident, sequence and payload.  The type, the code and
        # the checksum are the only things allowed to have moved, and the
        # 88 cases already grade those byte-exactly.
        if got[38:] != sent[38:]:
            fails.append("loopback echo %d: identifier, sequence or payload "
                         "changed in the round trip\n%s"
                         % (n, hexdiff(got[38:], sent[38:])))
        if got[34] != 0 or sent[34] != 8:
            fails.append("loopback echo %d: type went %d -> %d, wanted 8 -> 0"
                         % (n, sent[34], got[34]))
    return fails


# =====================================================================
def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    return anvil_build.find_compiler(requested)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--target", choices=sorted(TARGETS),
                    default="pi4",
                    help="which AArch64 board's image contract "
                         "to build and grade against")
    ap.add_argument("--mutate", action="store_true",
                    help="prove the gate can fail, by breaking the library")
    ap.add_argument("--dump", action="store_true",
                    help="print every frame the library staged")
    ap.add_argument("--no-loopback", action="store_true", dest="no_loopback",
                    help="skip the loopback link - it costs a second build "
                         "and two more runs")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    apply_target(globals(), args.target)
    # A GATE THAT DOES NOT SAY WHICH BOARD IT GRADED IS A RESULT
    # THAT CAN BE FILED AGAINST THE WRONG ONE.  Printed before any
    # work, so it is at the top of the transcript even on a failure.
    print("[gate] target %s - %s, image at $%08X, stack $%08X"
          % (TARGET_NAME, TARGET_WHAT, LOAD, STACK))

    hlen, mtu = cited_eth_hlen_and_mtu()
    ck_line, ps_line = confirm_checksum_citation()
    print("the things this gate can actually cite:")
    if hlen is None:
        print("   NOTE: %s is not present (third-party source, not "
              "redistributed), so the Ethernet header length and MTU "
              "cross-check is skipped" % GENET_DRIVER.relative_to(ROOT).as_posix())
    else:
        print("   Ethernet header %d, MTU %d      %s:102"
              % (hlen, mtu, GENET_DRIVER.name))
    print("   ones' complement checksum      %s:%d" % (RFC9293.name, ck_line))
    print("   IPv4 pseudo-header, Figure 2   %s:%d" % (RFC9293.name, ps_line))
    print("   everything else is a SECOND TRANSCRIPTION, not a second")
    print("   reading - this gate does not yet parse RFCs 791, 792, 768")
    print("   and 826.  See HOW HONEST THIS GATE IS at the top of this file.")
    print()
    if hlen is not None and (hlen != 14 or mtu != 1500):
        print("the driver's comment now says header %d body %d; net.pi4's "
              "#NET_ETH_HDR and #NET_MTU must follow it" % (hlen, mtu))
        return 1

    script, at = build_script()
    MUT_AT.clear()
    MUT_AT.update(at)

    res, uart, steps = one_run("Anvil/Network/net.pbi",
                               WORK / "netharness.pi4",
                               WORK / "netcheck.img", script)

    print("%d script records, %d results, %d instructions, console %r"
          % (len(script.labels), len(res), steps,
             uart.decode("latin-1")))
    print()

    if args.dump:
        for r in res:
            print("  %-26s r=%-6d err=%-5d %s"
                  % (r.label[:26], r.r, r.e1,
                     r.blob.hex() if r.blob else ""))
        print()

    # A transcript a human can read, of the half that matters most.
    for name in ("arp_for_us", "ping", "build_arp", "build_ping",
                 "build_udp", "build_far"):
        r = res[at[name]]
        print("  %-12s %-46s %d octets" % (name, r.label[:46], len(r.blob)))
        if r.blob:
            for off in range(0, min(len(r.blob), 80), 16):
                print("      %04X  %s" % (off, r.blob[off:off + 16].hex(" ")))
    print()

    fails: list[str] = []
    check(res, at, fails)

    if fails:
        print("a64_net_check: FAIL")
        for f in fails:
            print("   " + f)
        return 1
    print("a64_net_check: PASS - %d cases, every frame byte-exact"
          % len(script.labels))

    if not args.no_loopback:
        lb = loopback(WORK / "netharness.pi4", WORK / "netcheck.img")
        if lb:
            print("a64_net_check: LOOPBACK FAIL")
            for f in lb:
                print("   " + f)
            return 1
        print("           loopback link: %d UDP round trips and %d echo "
              "round trips through the library's own frames, payload "
              "byte-identical, no checksum recomputed by the gate"
              % (len(LB_LENS), 4))

    # The probe is BUILT here, not run.  Running it needs the whole
    # GENET register model, which belongs in a driver gate; duplicating
    # it here would be a second model to keep in step.  Building it
    # still catches the thing that actually goes wrong with a probe -
    # that somebody changed an API in net.pi4 and did not change its
    # caller.
    # AND IT IS BUILT ONLY FOR THE PI 4.  pi4NetProbe.pi4 pumps net.pi4
    # through genet.pi4, so a -t unoq build of it would put a BCM2711
    # Ethernet MAC into an image claiming to be a QCM2290's, and the
    # header assertion below quotes Pi 4 addresses.  The library graded
    # above is shared between the two boards; its Pi 4 CALLER is not.
    if TARGET_NAME != "pi4":
        print("           pi4NetProbe.pi4 not built - it is a Pi 4 caller, "
              "and this run graded %s" % TARGET_NAME)
    elif PROBE.exists():
        build(PROBE, WORK / "netprobe.img")
        head = PROBE.read_text(encoding="utf-8", errors="replace")[:4000]
        need = ("--load-addr 0x400000", "--stack-addr 0x3000000",
                "--entry-returns")
        missing = [n for n in need if n not in head]
        if missing:
            print("a64_net_check: FAIL - pi4NetProbe.pi4's header does not "
                  "document %s in its build line" % ", ".join(missing))
            return 1
        print("           pi4NetProbe.pi4 builds, and its header documents "
              "its own build line")
    else:
        print("           pi4NetProbe.pi4 is not there yet")

    if args.mutate:
        print()
        print("--mutate: breaking the library on purpose; each must go RED")
        bad = 0
        for name, old, new in MUTATIONS:
            print("  * %s" % name)
            if mutate_run(name, old, new, script):
                print("    RED, as required")
            else:
                print("    *** STILL GREEN - the gate does not catch this ***")
                bad += 1
        for leftover in ("net_mut.pi4", "netharness_mut.pi4",
                         "netcheck_mut.img", "netcheck_mut.img.dbg",
                         "netcheck_mut.img.sym", "netcheck_mut.img.sym.meta",
                         "netcheck_mut.img.asm"):
            p = WORK / leftover
            if p.exists():
                p.unlink()
        if bad:
            return 1
        print("  all %d mutations caught" % len(MUTATIONS))

    return 0


if __name__ == "__main__":
    sys.exit(main())
