#!/usr/bin/env python3
r"""The HOST end of the Arduino UNO Q's file-backed conformance channel.

    python tools/qnetfile_script.py write  <dir>       build qnet.in
    python tools/qnetfile_script.py grade  <dir>       grade qnet.out
    python tools/qnetfile_script.py show   <file>      dump either file

WHAT THIS IS FOR
----------------
Every layer of this project's IP stack builds for the Arduino UNO Q and
passes its gate built that way, and until now not one byte of it had
EXECUTED on a QCM2290.  The board has no wire yet.  It does have a file
channel to the EFI System Partition that is proven on this silicon, so
the stack can be run on the real core against byte-exact frames written
here, with no driver, no register, no new hardware and no link decision.

    host                                     board
    ----                                     -----
    write \EFI\anvil\qnet.in     ------>     QNetFileBegin
                                             LinkPumpNet -> NetInput
    read  \EFI\anvil\qnet.out    <------     QNetFileFlush

WHAT A GREEN RUN IS EVIDENCE OF, and both halves must be reported
together every single time:

  PROVES: the codecs, the checksums, the ARP cache, the byte order, the
  alignment behaviour of this compiler's output on a Cortex-A53, and the
  arithmetic - on the real part, at the real addresses, in the real
  image.

  DOES NOT PROVE: timing, a driver, an interrupt, a DMA engine, a
  cache-coherency question, or anything at all about a wire.  A frame
  that arrives from a file arrives instantly and perfectly, and no
  retransmission bug that only a lossy link produces can appear here.
  THIS IS NOT A NETWORK LINK.  Never describe it as one.

THE FILENAMES ARE qnet.in AND qnet.out, NOT net.in AND net.out.  The q is
not decoration: a string literal in the board's language translates \r,
\n and \t, so a path segment beginning with n, r or t loses its
separator to a control character and the firmware is asked for a file
that cannot exist.  That happened, it was silent, and it is forum 638.

HOW TO RUN IT ON THE BOARD

    python tools/qnetfile_script.py write _work/qnet
    bash tools/build_unoq_netproof.sh
    # claim the board, then:
    scp _work/qnet/qnet.in arduino@<host>:/boot/efi/EFI/anvil/qnet.in
    bash tools/deploy_unoq_efi.sh \
         ArduinoQ/Examples/Diagnostics/anvilqnetproof.efi anvilqnetproof \
         arduino@<host> --go \
         --pull EFI/anvil/qnet.out --pull EFI/anvil/qnetproof.log
    python tools/qnetfile_script.py grade _work/qnet

THE VECTORS ARE THE SAME ONES tools/a64/a64_qnetproof_check.py USES.
That is deliberate: the emulator run and the silicon run then answer the
same question, and a difference between them is the finding.  The two
files build their frames independently from the specifications rather
than sharing a module, so a mistake in one does not become the standard
the other is graded against.
"""

from __future__ import annotations

import pathlib
import struct
import sys

# The two-host subnet ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqnetproof.unoq
# declares.  If these ever disagree, every reply comes back addressed to
# a host that is not listening - which this script says out loud rather
# than counting as a silent zero.
BOARD_IP = 0x0A000002          # 10.0.0.2
PEER_IP = 0x0A000001           # 10.0.0.1

# The synthetic, locally administered addresses the board's link uses.
# Bit 1 of the first octet set (locally administered), bit 0 clear
# (unicast).  They are never on a wire; they exist so the fourteen bytes
# the 802.3 codec requires have something consistent in them.
BOARD_MAC = bytes([0x02, 0x00, 0x00, 0x51, 0x00, 0x01])
PEER_MAC = bytes([0x02, 0x00, 0x00, 0x51, 0x00, 0x02])
OTHER_MAC = bytes([0x02, 0x00, 0x00, 0x51, 0x00, 0x09])

ET_IPV4, ET_ARP = 0x0800, 0x0806
NAME_IN, NAME_OUT = "qnet.in", "qnet.out"


def ones_complement(data: bytes) -> int:
    total = 0
    if len(data) % 2:
        data += b"\x00"
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def eth(dst: bytes, src: bytes, et: int, payload: bytes) -> bytes:
    return dst + src + struct.pack(">H", et) + payload


def pad60(frame: bytes) -> bytes:
    return frame + b"\x00" * (60 - len(frame)) if len(frame) < 60 else frame


def arp(op: int, sha: bytes, spa: int, tha: bytes, tpa: int) -> bytes:
    return (struct.pack(">HHBBH", 1, ET_IPV4, 6, 4, op)
            + sha + struct.pack(">I", spa) + tha + struct.pack(">I", tpa))


def ipv4(src: int, dst: int, proto: int, payload: bytes, ident: int,
         flags: int = 0x4000) -> bytes:
    h = bytearray(20)
    h[0] = 0x45
    struct.pack_into(">H", h, 2, 20 + len(payload))
    struct.pack_into(">H", h, 4, ident)
    struct.pack_into(">H", h, 6, flags)
    h[8], h[9] = 64, proto
    struct.pack_into(">I", h, 12, src)
    struct.pack_into(">I", h, 16, dst)
    struct.pack_into(">H", h, 10, ones_complement(bytes(h)))
    return bytes(h) + payload


def icmp_echo(t: int, ident: int, seq: int, payload: bytes) -> bytes:
    b = bytearray(8)
    b[0] = t
    struct.pack_into(">H", b, 4, ident)
    struct.pack_into(">H", b, 6, seq)
    b += payload
    struct.pack_into(">H", b, 2, ones_complement(bytes(b)))
    return bytes(b)


PING_PAYLOAD = bytes(range(0x61, 0x61 + 32))

# Five frames, chosen so that each reaches a DIFFERENT verdict and so
# that THREE OF THEM MUST PRODUCE NOTHING.  A script where everything
# answers proves less than one where the right things stay silent: a
# board that answers an ARP request for an address it does not hold
# poisons every cache on its segment, and one that answers a frame
# addressed to somebody else is worse.
SCRIPT = [
    ("an ARP request for the board's address", pad60(eth(
        b"\xFF" * 6, PEER_MAC, ET_ARP,
        arp(1, PEER_MAC, PEER_IP, b"\x00" * 6, BOARD_IP)))),
    ("an ARP request for an address the board does not hold", pad60(eth(
        b"\xFF" * 6, PEER_MAC, ET_ARP,
        arp(1, PEER_MAC, PEER_IP, b"\x00" * 6, 0x0A000009)))),
    ("an ICMP echo request to the board", eth(
        BOARD_MAC, PEER_MAC, ET_IPV4,
        ipv4(PEER_IP, BOARD_IP, 1,
             icmp_echo(8, 0x1234, 7, PING_PAYLOAD), 0x4321))),
    ("a frame addressed to a different card", eth(
        OTHER_MAC, PEER_MAC, ET_IPV4,
        ipv4(PEER_IP, 0x0A000009, 1, icmp_echo(8, 1, 1, b"xyz"), 9))),
    ("an ICMP echo reply to the board", eth(
        BOARD_MAC, PEER_MAC, ET_IPV4,
        ipv4(PEER_IP, BOARD_IP, 1,
             icmp_echo(0, 0x1234, 7, PING_PAYLOAD), 0x4322))),
]


def expected() -> list[tuple[str, bytes]]:
    """The two replies, and only two.  The IPv4 Identification field is
    the board's to choose and is substituted from what came back."""
    return [
        ("the ARP reply", pad60(eth(
            PEER_MAC, BOARD_MAC, ET_ARP,
            arp(2, BOARD_MAC, BOARD_IP, PEER_MAC, PEER_IP)))),
        ("the ICMP echo reply", eth(
            PEER_MAC, BOARD_MAC, ET_IPV4,
            ipv4(BOARD_IP, PEER_IP, 1,
                 icmp_echo(0, 0x1234, 7, PING_PAYLOAD), 0))),
    ]


def encode(frames: list[bytes]) -> bytes:
    out = bytearray()
    for f in frames:
        out += struct.pack("<I", len(f)) + f
    return bytes(out) + struct.pack("<I", 0)


def decode(blob: bytes) -> list[bytes]:
    out: list[bytes] = []
    at = 0
    while at + 4 <= len(blob):
        (n,) = struct.unpack_from("<I", blob, at)
        at += 4
        if n == 0:
            return out
        if n > 1536 or at + n > len(blob):
            raise SystemExit(
                "%s is malformed: a record at offset %d claims %d bytes "
                "and %d follow.  A length field written in the wrong byte "
                "order looks exactly like this."
                % (NAME_OUT, at - 4, n, len(blob) - at))
        out.append(blob[at:at + n])
        at += n
    raise SystemExit("%s has no terminating zero length, so the board did "
                     "not finish writing it" % NAME_OUT)


def hexdiff(got: bytes, want: bytes) -> str:
    lines = []
    if len(got) != len(want):
        lines.append("    length got %d, want %d" % (len(got), len(want)))
    for i in range(0, max(len(got), len(want)), 16):
        g, w = got[i:i + 16], want[i:i + 16]
        if g != w:
            lines.append("    @%-4d got  %s" % (i, g.hex(" ")))
            lines.append("          want %s" % w.hex(" "))
    return "\n".join(lines[:12])


def cmd_write(d: pathlib.Path) -> int:
    d.mkdir(parents=True, exist_ok=True)
    p = d / NAME_IN
    p.write_bytes(encode([f for _n, f in SCRIPT]))
    print("wrote %s - %d frames, %d bytes" % (p, len(SCRIPT), p.stat().st_size))
    for i, (name, f) in enumerate(SCRIPT, 1):
        print("  %d. %-55s %4d bytes" % (i, name, len(f)))
    print("\nStage it on the board as \\EFI\\anvil\\%s, run" % NAME_IN)
    print("build/unoq/diagnostics/anvilqnetproof.efi (built by tools/build_unoq_netproof.sh), pull "
          "\\EFI\\anvil\\%s back" % NAME_OUT)
    print("into this directory, and grade it.")
    return 0


def cmd_grade(d: pathlib.Path) -> int:
    p = d / NAME_OUT
    if not p.exists():
        print("!! %s is not here.  The board writes it on every run, even "
              "when it has nothing to answer - a four-byte file holding a "
              "zero length is a RESULT.  Nothing at all means the image "
              "never got that far; read \\EFI\\anvil\\qnetproof.log." % p)
        return 1
    frames = decode(p.read_bytes())
    want = expected()
    fails: list[str] = []
    print("%s holds %d frames" % (p, len(frames)))
    if len(frames) != len(want):
        fails.append("the board answered %d frames and exactly %d of the %d "
                     "staged deserve an answer" % (len(frames), len(want),
                                                   len(SCRIPT)))
    for i, (name, w) in enumerate(want):
        if i >= len(frames):
            break
        g = frames[i]
        if name.startswith("the ICMP") and len(g) >= 34 and len(w) >= 34:
            # The Identification field is the board's to choose; take it
            # from what came back and repair the header checksum, which
            # is the only other thing that moves with it.
            w = bytearray(w)
            w[18:20] = g[18:20]
            w[24:26] = b"\x00\x00"
            struct.pack_into(">H", w, 24,
                             ones_complement(bytes(w[14:34])))
            w = bytes(w)
        if g == w:
            print("  OK   %s" % name)
        else:
            fails.append("%s is not what the protocol says\n%s"
                         % (name, hexdiff(g, w)))
    if fails:
        print("\nqnetfile_script: FAIL - %d" % len(fails))
        for f in fails:
            print("  * %s" % f)
        return 1
    print("""
qnetfile_script: PASS - the stack answered every frame correctly.

  WHERE THIS FILE CAME FROM IS THE WHOLE DIFFERENCE, AND THIS TOOL
  CANNOT TELL. Pulled off the EFI System Partition after a board run, it
  is a silicon result: codecs, checksums, byte order, the alignment
  behaviour of the compiler's output and the arithmetic, all on a real
  Cortex-A53. Produced by the emulator, it is the same evidence the
  gate already gives and no more. Say which one it was.

  EITHER WAY it is NOT evidence about timing, a driver, an interrupt, a
  DMA engine or a wire, and this channel is NOT a network link.""")
    return 0


def cmd_show(f: pathlib.Path) -> int:
    frames = decode(f.read_bytes())
    print("%s: %d frames" % (f, len(frames)))
    for i, fr in enumerate(frames, 1):
        print("  %d. %d bytes  %s" % (i, len(fr), fr[:32].hex(" ")))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    what, where = argv[1], pathlib.Path(argv[2])
    if what == "write":
        return cmd_write(where)
    if what == "grade":
        return cmd_grade(where)
    if what == "show":
        return cmd_show(where)
    print("!! %r is not a command this script knows.  It takes write, grade "
          "or show." % what)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
