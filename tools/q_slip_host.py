#!/usr/bin/env python3
"""q_slip_host.py - the HOST end of the Arduino UNO Q's SLIP link.

===============================================================================
WHAT THIS IS
===============================================================================
The Arduino UNO Q (QRB2210 / QCM2290) has no Ethernet MAC and no usable Wi-Fi.
Its only off-board signal is the GENI SE4 firmware-console UART, brought out on
the JCTL header.  The link chosen for it is SLIP - RFC 1055, two pages long,
END = 0xC0, ESC = 0xDB, ESC_END = 0xDC, ESC_ESC = 0xDD, and nothing else.

The board end already exists: ArduinoQ/Lib/qslip.pi4 does the framing and
synthesises the fourteen Ethernet header bytes that Anvil/Network/net.pbi
insists on.  This file is the other end of that wire: the program a bench
operator runs on a laptop so that the board has something to talk to.

It is written and proven BEFORE the wire exists, on purpose.  When the 1.8 V
adapter arrives, the first bench run is done with an instrument that has already
been executed, not with a program nobody has ever run.

===============================================================================
THE PINS - READ THIS BEFORE ANYTHING TOUCHES THE BOARD
===============================================================================
JCTL (silkscreen A1 / JCTL1) is a 2x5 ten-pin header.  Odd pins are one row,
even pins the other.  Identify pin 1 on the silkscreen before wiring.

    | Pin | Signal                        | Pin | Signal                     |
    |-----|-------------------------------|-----|----------------------------|
    |  1  | GND                           |  2  | USB_BOOT  (EDL strap)      |
    |  3  | VOL_DOWN                      |  4  | SOC_SE4_TX  - console TX   |
    |  5  | VOL_UP                        |  6  | SOC_SE4_RX  - console RX   |
    |  7  | GND                           |  8  | PMIC_RESET                 |
    |  9  | +1V8 OUT                      | 10  | VBUS_DISABLE               |

    adapter RX  (in)  <-  JCTL pin 4   (SOC_SE4_TX, GPIO_12, SoC out)
    adapter TX  (out) ->  JCTL pin 6   (SOC_SE4_RX, GPIO_13, SoC in)
    adapter GND        -  JCTL pin 1 or pin 7

    115200 baud, 8 data bits, no parity, 1 stop bit, NO FLOW CONTROL.
    SE4 is a two-wire serial engine.  There is no RTS and no CTS to find.

    If JCTL is not populated on your board, the same two nets land on test
    points TP2615 (TX) and TP2616 (RX).

*** DANGER - 1.8 V, UNSHIFTED, STRAIGHT OFF THE SoC PAD ***

    A 3.3 V or 5 V adapter connected directly to JCTL pin 4 or pin 6 can
    permanently destroy the QRB2210.  There is no series resistor, no clamp
    and no buffer anywhere between the header pin and the silicon; the SoC
    I/O bank is fed by a 1.8 V LDO, and forcing a pin above roughly 1.8 V
    plus a diode drop injects current into that rail through the pad's ESD
    structure.  "5 V tolerant" reasoning from the 3.3 V microcontroller side
    of this board does NOT transfer - the two domains are separate on
    purpose.

    Use an FT232H or FT2232H breakout with VCCIO strapped to 1.8 V, and
    verify VCCIO with a meter before a signal wire goes anywhere near the
    board.  Failing that, a BIDIRECTIONAL level shifter (TXB0102/TXB0104 or
    a BSS138 board) with its low side at 1.8 V - never a resistor divider,
    which leaves the board's RX driven at the adapter's full voltage.

    THE TRAP: the board's TX at 1.8 V usually clears a 3.3 V adapter's input
    threshold, so a wrong adapter prints perfectly readable text while it is
    quietly damaging the board on the other wire.  Readable output is not
    proof that the wiring is safe.  If you ever wire one way to sniff output
    only, leave the adapter's TX physically DISCONNECTED, not merely unused.

    Pins 2, 8 and 10 are hostile neighbours.  Slipping one pin sideways from
    TX (4) onto USB_BOOT (2) re-modes the board into EDL; from RX (6) onto
    PMIC_RESET (8) resets the PMIC.  Power the board down before connecting
    or disconnecting, connect ground first and remove it last.

===============================================================================
THE EXACT FIRST COMMANDS
===============================================================================
Desk, no hardware, nothing installed - this is the one that matters tonight:

    python tools/q_slip_host.py --self-test

Find the adapter, and read the voltage warning it prints:

    python tools/q_slip_host.py --list-ports

Answer the board (pure-Python peer, no TAP/TUN, no privileges).  The board is
10.0.0.2 and this host is 10.0.0.1 on a /30, which is what
ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqnetproof.unoq is built for:

    python tools/q_slip_host.py --port COM9 --baud 115200 --dump bench.cap
    python tools/q_slip_host.py --port /dev/ttyUSB0 --baud 115200

Drive the BOARD's stack from this side instead of waiting to be driven:

    python tools/q_slip_host.py --port COM9 --ping 4
    python tools/q_slip_host.py --port COM9 --connect 7 --send hello

Read a bench transcript back afterwards:

    python tools/q_slip_host.py --decode bench.cap

Linux only, if you would rather hand the datagrams to the kernel:

    sudo python3 tools/q_slip_host.py --port /dev/ttyUSB0 --tun qslip0
    sudo ip addr add 10.0.0.1/30 dev qslip0 && sudo ip link set qslip0 up

===============================================================================
WHAT THE SELF-TEST PROVES, CASE BY CASE
===============================================================================
The self-test runs with no hardware, no serial port, no privileges and no
third-party package, and it drives the SAME encoder, decoder and peer objects
the wire path drives.  There is no second copy of the protocol in here.

Part (a) - framing, written from RFC 1055 itself:
  frame/all-256      a datagram carrying every one of the 256 byte values.
                     Proves exactly two bytes in that datagram get escaped and
                     nothing else does.  Graded against a stated length (260)
                     and a stated SHA-256 of the encoded bytes.
  frame/only-END     a datagram that is one 0xC0 byte.  Byte-exact: c0dbdcc0.
  frame/only-ESC     a datagram that is one 0xDB byte.  Byte-exact: c0dbddc0.
  frame/plain        a datagram needing no escape at all.  Byte-exact: c000c0.
  frame/empty-enc    the encoder REFUSES a zero-length datagram loudly rather
                     than emitting a frame the far end will count as noise.
  frame/empty-dec    three ENDs in a row decode to no datagrams and three
                     counted empty frames - RFC 1055's recommended leading END
                     must not turn into a phantom packet.
  frame/oversize     a frame past the receive ceiling is DISCARDED with a
                     counter, and the good frame right behind it still decodes.
                     Half a datagram is not a small datagram.
  frame/bad-escape   ESC followed by a byte RFC 1055 does not define.  The byte
                     is kept, as every Berkeley implementation does and as
                     qslip.pi4 does, and it is COUNTED.  A decoder that hides
                     an escape violation is an instrument that lies.
  frame/incomplete   a stream that stops mid-frame yields no datagram and
                     reports bytes still pending.
  frame/roundtrip    encode then decode returns the original bytes, for every
                     vector above and for 1006 bytes of worst-case payload.

Part (a2) - the peer, so that a missing transcript cannot leave it unproven:
  peer/icmp-echo     an ICMP echo request in, an echo reply out, byte-exact,
                     with both the IP and the ICMP checksum recomputed.
  peer/icmp-cksum    a datagram with a wrong IP header checksum is refused
                     loudly, not answered.
  peer/tcp-syn       SYN in, SYN|ACK out, byte-exact, TCP checksum over the
                     pseudo-header.
  peer/tcp-echo      a data segment in, the same payload echoed out.
  peer/tcp-fin       FIN in, FIN|ACK out.
  peer/tcp-noport    a segment to a port nothing listens on is answered with
                     RST, which is the loud answer, not silence.
  peer/udp-unreach   UDP to a closed port is answered with ICMP type 3 code 3.
  peer/refuse        a fragment, a non-IPv4 datagram and an unknown protocol
                     are each refused with a full sentence.

Part (b) - the replay, and this is the one that makes the two ends agree:
  replay/NNNN        every board_tx event in _work/qslipgeni/transcript.json is
                     decoded by THIS decoder and must yield a well-formed IP
                     datagram; that datagram is handed to THIS peer; the peer's
                     reply, encoded by THIS encoder, must be byte-identical to
                     the next board_rx event.  That is the whole point: the
                     host tool and the board agree before either has met a
                     wire.  The transcript is written by the gate
                     tools/a64/a64_qslipgeni_check.py.  If the file is absent
                     part (b) reports itself SKIPPED and part (a) still counts
                     - it must never silently pass.

===============================================================================
THE DETERMINISTIC CONSTANTS THE REPLAY DEPENDS ON
===============================================================================
Byte-identity is only meaningful if the peer is deterministic, so every field
that a general-purpose stack would randomise is pinned here and stated so the
gate on the other side can pin the same ones:

  * host IP 10.0.0.1, board IP 10.0.0.2, mask 255.255.255.252 (a /30).
  * TTL 64 on everything this peer originates.
  * IP identification: an ICMP echo REPLY copies the request's identification
    field, its flags and its fragment offset verbatim, because the reply is
    the request with the addresses swapped and the type changed - that is also
    exactly how a64_qslip_check models the far end.  Everything else this peer
    originates uses a counter starting at 0x5100, incremented by one per
    datagram, with the Don't Fragment flag set.
  * TCP initial sequence number 0x51000000 for the first connection, plus
    0x00010000 for each connection after it.  Window 1024.  No TCP options at
    all, not even MSS, so that a segment's length is a function of its payload
    and nothing else.
  * ICMP echo requests this peer originates use identifier 0x5100, sequence
    numbers from 1, and a payload of 32 bytes counting 0x00 upward.

===============================================================================
UNITS AND CONVENTIONS
===============================================================================
Volts, amps, hertz, bytes, bits, baud and seconds are the American engineering
units already and are used as-is.  Every error this tool prints is a complete
sentence that keeps its numeric code, says what the code means, and names the
first thing to check.

Python 3, standard library only.  The wire path additionally needs pyserial;
the self-test needs nothing at all.
"""

import argparse
import binascii
import hashlib
import json
import os
import platform
import sys
import time

# ---------------------------------------------------------------------------
# RFC 1055 - the whole protocol, in four constants.
# ---------------------------------------------------------------------------
SLIP_END = 0xC0
SLIP_ESC = 0xDB
SLIP_ESC_END = 0xDC
SLIP_ESC_ESC = 0xDD

# RFC 1055's stated minimum a receiver should accept, and the number
# ArduinoQ/Lib/qslip.pi4 uses for its send ceiling.
SLIP_MTU = 1006
# The receive ceiling is deliberately larger than the send ceiling, matching
# the board: a peer is entitled to send more than we would, and a frame that
# overruns is discarded with a counter rather than truncated.
SLIP_RX_MAX = 1600

DEFAULT_HOST_IP = "10.0.0.1"
DEFAULT_BOARD_IP = "10.0.0.2"
DEFAULT_ECHO_PORT = 7
DEFAULT_BAUD = 115200
DEFAULT_TRANSCRIPT = os.path.join("_work", "qslipgeni", "transcript.json")

TTL = 64
IP_ID_BASE = 0x5100
TCP_ISN_BASE = 0x51000000
TCP_ISN_STEP = 0x00010000
TCP_WINDOW = 1024
ICMP_ECHO_ID = 0x5100
ICMP_ECHO_PAYLOAD_LEN = 32

PROTO_ICMP = 1
PROTO_TCP = 6
PROTO_UDP = 17

TCP_FIN = 0x01
TCP_SYN = 0x02
TCP_RST = 0x04
TCP_PSH = 0x08
TCP_ACK = 0x10

# Exit codes, so a script driving this tool can tell the cases apart.
EXIT_OK = 0
EXIT_SELFTEST_FAILED = 1
EXIT_ENVIRONMENT = 2


class ToolError(Exception):
    """An operator-facing failure.  The message is always a full sentence."""


class Refusal(Exception):
    """The peer met traffic it will not answer, and says so out loud."""


# ===========================================================================
#  SLIP framing - one encoder and one decoder, used by every path in the file
# ===========================================================================

def slip_encode(datagram, mtu=SLIP_MTU):
    """One bare IP datagram to RFC 1055 wire bytes.

    The leading END is not optional.  RFC 1055 recommends it, and the reason
    is worth keeping: if line noise or a reset left half a datagram in the far
    end's decoder, this END terminates that garbage as its own empty frame
    instead of letting it become the first bytes of a real one.  An empty
    frame costs one byte; a corrupted first datagram costs a session.
    """
    if not isinstance(datagram, (bytes, bytearray)):
        raise ToolError(
            "q_slip_host error 20: slip_encode was handed a %s instead of "
            "bytes, which is a defect in the caller rather than in the link; "
            "check the code path that produced this datagram."
            % type(datagram).__name__)
    if len(datagram) == 0:
        raise ToolError(
            "q_slip_host error 21: refusing to SLIP-encode a zero-length "
            "datagram, because RFC 1055 gives an empty frame no meaning and "
            "the far end counts it as discarded line noise; check whichever "
            "caller built a packet with no bytes in it.")
    if len(datagram) > mtu:
        raise ToolError(
            "q_slip_host error 22: refusing to send a %d-byte datagram over a "
            "link whose SLIP transmit ceiling is %d bytes, which is RFC 1055's "
            "stated minimum and the same number ArduinoQ/Lib/qslip.pi4 "
            "enforces; check the sender's own maximum transmission unit "
            "before raising this ceiling."
            % (len(datagram), mtu))
    out = bytearray()
    out.append(SLIP_END)
    for b in datagram:
        if b == SLIP_END:
            out.append(SLIP_ESC)
            out.append(SLIP_ESC_END)
        elif b == SLIP_ESC:
            out.append(SLIP_ESC)
            out.append(SLIP_ESC_ESC)
        else:
            out.append(b)
    out.append(SLIP_END)
    return bytes(out)


class SlipDecoder(object):
    """A byte-at-a-time RFC 1055 decoder with the board's exact behaviour.

    Every departure from "just strip the escapes" mirrors qslip.pi4, because a
    host decoder that is more forgiving than the board's would hide precisely
    the faults the bench run exists to find.
    """

    def __init__(self, rx_max=SLIP_RX_MAX):
        self.rx_max = rx_max
        self.reset()

    def reset(self):
        self._buf = bytearray()
        self._esc = False
        self._overrun = False
        self.datagrams = 0
        self.empty_frames = 0
        self.overruns = 0
        self.bad_escapes = 0

    @property
    def pending(self):
        """Bytes collected so far in a frame that has not been ended yet."""
        return len(self._buf)

    def feed(self, data):
        """Feed wire bytes, get back a list of complete bare IP datagrams."""
        out = []
        for b in data:
            if self._esc:
                self._esc = False
                if b == SLIP_ESC_END:
                    b = SLIP_END
                elif b == SLIP_ESC_ESC:
                    b = SLIP_ESC
                else:
                    # RFC 1055: "if the byte is not one of these two ... the
                    # protocol is being violated".  Keep the byte, as the
                    # Berkeley implementations and qslip.pi4 both do, and
                    # count it.  A stream with escape violations in it has a
                    # bug at one end.
                    self.bad_escapes += 1
                self._store(b)
                continue
            if b == SLIP_END:
                if len(self._buf) == 0 and not self._overrun:
                    # The leading END of the next datagram, or the terminator
                    # of discarded noise.  Normal, and counted anyway.
                    self.empty_frames += 1
                    continue
                if self._overrun:
                    self.overruns += 1
                    self._buf = bytearray()
                    self._overrun = False
                    continue
                out.append(bytes(self._buf))
                self.datagrams += 1
                self._buf = bytearray()
                continue
            if b == SLIP_ESC:
                self._esc = True
                continue
            self._store(b)
        return out

    def _store(self, b):
        if len(self._buf) < self.rx_max:
            self._buf.append(b)
        else:
            # Past the buffer.  Write nothing and remember, so the closing END
            # discards the frame.  Truncating would be worse than losing it,
            # because the IP layer would happily parse the fragment.
            self._overrun = True


# ===========================================================================
#  Checksums and packet construction
# ===========================================================================

def ones_complement_sum(data):
    total = 0
    n = len(data)
    if n & 1:
        data = bytes(data) + b"\x00"
        n += 1
    for i in range(0, n, 2):
        total += (data[i] << 8) | data[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return total & 0xFFFF


def checksum16(data):
    return (~ones_complement_sum(data)) & 0xFFFF


def ip_to_bytes(text):
    parts = text.split(".")
    if len(parts) != 4:
        raise ToolError(
            "q_slip_host error 30: the address '%s' does not have the four "
            "dotted parts an IPv4 address needs; check the --our-ip or "
            "--board-ip argument you passed." % text)
    out = bytearray()
    for p in parts:
        if not p.isdigit() or not 0 <= int(p) <= 255:
            raise ToolError(
                "q_slip_host error 31: '%s' is not a number from 0 to 255, so "
                "the address '%s' cannot be an IPv4 address; check the "
                "--our-ip or --board-ip argument you passed." % (p, text))
        out.append(int(p))
    return bytes(out)


def bytes_to_ip(raw):
    return "%d.%d.%d.%d" % (raw[0], raw[1], raw[2], raw[3])


def ip_build(src, dst, proto, payload, ident, flags_frag=0x4000, ttl=TTL):
    """A 20-byte IPv4 header with no options, plus its payload."""
    total = 20 + len(payload)
    header = bytearray(20)
    header[0] = 0x45
    header[1] = 0x00
    header[2] = (total >> 8) & 0xFF
    header[3] = total & 0xFF
    header[4] = (ident >> 8) & 0xFF
    header[5] = ident & 0xFF
    header[6] = (flags_frag >> 8) & 0xFF
    header[7] = flags_frag & 0xFF
    header[8] = ttl
    header[9] = proto
    header[10] = 0
    header[11] = 0
    header[12:16] = src
    header[16:20] = dst
    c = checksum16(bytes(header))
    header[10] = (c >> 8) & 0xFF
    header[11] = c & 0xFF
    return bytes(header) + bytes(payload)


class IPv4(object):
    """A parsed IPv4 datagram.  Parsing refuses rather than guesses."""

    def __init__(self, raw):
        if len(raw) < 20:
            raise Refusal(
                "q_slip_host error 40: a %d-byte datagram arrived, which is "
                "shorter than the 20-byte minimum IPv4 header, so there is "
                "nothing to parse; check whether the far end is framing with "
                "RFC 1055's leading END byte."
                % len(raw))
        if (raw[0] >> 4) != 4:
            raise Refusal(
                "q_slip_host error 41: the datagram's version nibble is %d, "
                "not 4, and a SLIP wire carries no ethertype to tell IPv4 "
                "from anything else; check that the board is not trying to "
                "send IPv6 over a link that cannot carry it."
                % (raw[0] >> 4))
        self.ihl = (raw[0] & 0x0F) * 4
        if self.ihl < 20 or self.ihl > len(raw):
            raise Refusal(
                "q_slip_host error 42: the datagram claims a %d-byte IPv4 "
                "header inside %d bytes of datagram, which cannot be true; "
                "check the sender's header-length field."
                % (self.ihl, len(raw)))
        self.total_length = (raw[2] << 8) | raw[3]
        if self.total_length != len(raw):
            raise Refusal(
                "q_slip_host error 43: the IPv4 total-length field says %d "
                "bytes but the SLIP frame delivered %d, and SLIP frames are "
                "exact because END delimits them; check for a decoder that "
                "is losing or adding bytes rather than for a lossy wire."
                % (self.total_length, len(raw)))
        if checksum16(raw[:self.ihl]) != 0:
            raise Refusal(
                "q_slip_host error 44: the IPv4 header checksum does not "
                "verify, so this datagram is corrupt and will not be "
                "answered; check the baud rate first, because 115200 8N1 with "
                "no flow control is the setting the board's console uses.")
        self.ident = (raw[4] << 8) | raw[5]
        self.flags_frag = (raw[6] << 8) | raw[7]
        if (self.flags_frag & 0x2000) or (self.flags_frag & 0x1FFF):
            raise Refusal(
                "q_slip_host error 45: this datagram is a fragment (flags and "
                "offset field 0x%04X) and this peer does not reassemble "
                "fragments; check the sender's maximum transmission unit, "
                "which should be at or under %d bytes for this link."
                % (self.flags_frag, SLIP_MTU))
        self.ttl = raw[8]
        self.proto = raw[9]
        self.src = bytes(raw[12:16])
        self.dst = bytes(raw[16:20])
        self.header = bytes(raw[:self.ihl])
        self.payload = bytes(raw[self.ihl:])
        self.raw = bytes(raw)


def tcp_build(src, dst, sport, dport, seq, ack, flags, window, payload):
    header = bytearray(20)
    header[0] = (sport >> 8) & 0xFF
    header[1] = sport & 0xFF
    header[2] = (dport >> 8) & 0xFF
    header[3] = dport & 0xFF
    header[4] = (seq >> 24) & 0xFF
    header[5] = (seq >> 16) & 0xFF
    header[6] = (seq >> 8) & 0xFF
    header[7] = seq & 0xFF
    header[8] = (ack >> 24) & 0xFF
    header[9] = (ack >> 16) & 0xFF
    header[10] = (ack >> 8) & 0xFF
    header[11] = ack & 0xFF
    header[12] = 0x50           # data offset 5, no options at all
    header[13] = flags & 0xFF
    header[14] = (window >> 8) & 0xFF
    header[15] = window & 0xFF
    segment = bytes(header) + bytes(payload)
    pseudo = bytes(src) + bytes(dst) + bytes([0, PROTO_TCP,
                                              (len(segment) >> 8) & 0xFF,
                                              len(segment) & 0xFF])
    c = checksum16(pseudo + segment)
    header[16] = (c >> 8) & 0xFF
    header[17] = c & 0xFF
    return bytes(header) + bytes(payload)


class TcpSegment(object):
    def __init__(self, ip):
        raw = ip.payload
        if len(raw) < 20:
            raise Refusal(
                "q_slip_host error 50: a TCP segment arrived with only %d "
                "bytes, which is shorter than the 20-byte minimum header; "
                "check the IPv4 total-length field of the datagram carrying "
                "it." % len(raw))
        pseudo = ip.src + ip.dst + bytes([0, PROTO_TCP,
                                          (len(raw) >> 8) & 0xFF,
                                          len(raw) & 0xFF])
        if checksum16(pseudo + raw) != 0:
            raise Refusal(
                "q_slip_host error 51: the TCP checksum does not verify over "
                "the pseudo-header, so this segment is corrupt and will not "
                "be answered; check that the sender includes the source "
                "address, destination address, protocol 6 and the segment "
                "length in its pseudo-header the way RFC 793 requires.")
        self.sport = (raw[0] << 8) | raw[1]
        self.dport = (raw[2] << 8) | raw[3]
        self.seq = (raw[4] << 24) | (raw[5] << 16) | (raw[6] << 8) | raw[7]
        self.ack = (raw[8] << 24) | (raw[9] << 16) | (raw[10] << 8) | raw[11]
        self.offset = (raw[12] >> 4) * 4
        if self.offset < 20 or self.offset > len(raw):
            raise Refusal(
                "q_slip_host error 52: the TCP data offset claims a %d-byte "
                "header inside a %d-byte segment, which cannot be true; check "
                "the sender's data-offset nibble."
                % (self.offset, len(raw)))
        self.flags = raw[13]
        self.window = (raw[14] << 8) | raw[15]
        self.payload = bytes(raw[self.offset:])

    def flag_text(self):
        names = []
        for bit, name in ((TCP_FIN, "FIN"), (TCP_SYN, "SYN"), (TCP_RST, "RST"),
                          (TCP_PSH, "PSH"), (TCP_ACK, "ACK")):
            if self.flags & bit:
                names.append(name)
        return "|".join(names) if names else "none"


# ===========================================================================
#  The peer.  No TAP, no TUN, no privileges, no ARP - SLIP carries bare IP.
# ===========================================================================

class TcpConnection(object):
    def __init__(self, key, iss, role):
        self.key = key
        self.iss = iss
        self.snd_nxt = iss
        self.rcv_nxt = 0
        self.state = "CLOSED"
        self.role = role        # "server" for the echo service, "client" for us
        self.bytes_echoed = 0


class SlipPeer(object):
    """The whole far end of the link, in one deterministic object.

    There is no ARP here and there is nothing missing: RFC 1055 carries a bare
    IP datagram between two machines on one wire, so there is no link-layer
    address to resolve and nowhere else for a packet to go.  The board's
    qslip.pi4 synthesises fourteen Ethernet bytes on its own side purely to
    satisfy net.pbi's 802.3 codec, and answers its own ARP requests locally.
    Not one of those bytes ever reaches this program.  A reader who finds a MAC
    address in a capture from this link has found a bug.
    """

    def __init__(self, our_ip=DEFAULT_HOST_IP, board_ip=DEFAULT_BOARD_IP,
                 echo_port=DEFAULT_ECHO_PORT, log=None):
        self.our_ip = ip_to_bytes(our_ip)
        self.board_ip = ip_to_bytes(board_ip)
        self.echo_port = echo_port
        self.log = log if log is not None else (lambda text: None)
        self.ip_id = IP_ID_BASE
        self.next_isn = TCP_ISN_BASE
        self.conns = {}
        self.next_client_port = 40000
        self.icmp_seq = 0
        self.stats = {
            "in": 0, "out": 0, "icmp_echo_answered": 0, "icmp_echo_replies": 0,
            "tcp_segments": 0, "tcp_bytes_echoed": 0, "refused": 0,
        }

    # -- helpers ----------------------------------------------------------
    def _ident(self):
        ident = self.ip_id & 0xFFFF
        self.ip_id = (self.ip_id + 1) & 0xFFFF
        return ident

    def _isn(self):
        isn = self.next_isn & 0xFFFFFFFF
        self.next_isn = (self.next_isn + TCP_ISN_STEP) & 0xFFFFFFFF
        return isn

    # -- the one entry point both the wire path and the replay use --------
    def handle_datagram(self, data):
        """One bare IP datagram in, a list of bare IP datagrams out.

        Raises Refusal, with a full sentence, for anything it will not answer.
        It never drops a datagram silently.
        """
        self.stats["in"] += 1
        ip = IPv4(data)
        if ip.dst != self.our_ip:
            raise Refusal(
                "q_slip_host error 60: a datagram addressed to %s arrived on a "
                "point-to-point link whose host end is %s, and this peer will "
                "not route; check the board's configured peer address, which "
                "should be this host's address."
                % (bytes_to_ip(ip.dst), bytes_to_ip(self.our_ip)))
        if ip.proto == PROTO_ICMP:
            return self._handle_icmp(ip)
        if ip.proto == PROTO_TCP:
            return self._handle_tcp(ip)
        if ip.proto == PROTO_UDP:
            return self._handle_udp(ip)
        raise Refusal(
            "q_slip_host error 61: IPv4 protocol number %d arrived and this "
            "peer answers only ICMP (1), TCP (6) and UDP (17); check what the "
            "board's stack was asked to send, because nothing was dropped "
            "quietly here." % ip.proto)

    # -- ICMP -------------------------------------------------------------
    def _handle_icmp(self, ip):
        body = ip.payload
        if len(body) < 8:
            raise Refusal(
                "q_slip_host error 62: an ICMP message arrived with only %d "
                "bytes, which is shorter than the 8-byte header every ICMP "
                "type needs; check the IPv4 total-length field of the "
                "datagram carrying it." % len(body))
        if checksum16(body) != 0:
            raise Refusal(
                "q_slip_host error 63: the ICMP checksum does not verify, so "
                "this message is corrupt and will not be answered; check the "
                "baud rate and the ground connection before suspecting the "
                "sender's arithmetic.")
        icmp_type = body[0]
        code = body[1]
        if icmp_type == 8:
            # The reply IS the request with the addresses swapped and the type
            # turned from 8 into 0.  Identification, flags and fragment offset
            # are copied verbatim; only the time to live is set to this peer's
            # own, and both checksums are recomputed.  A one's-complement sum
            # does not care about the order of its terms, so the IP checksum
            # would in fact survive the swap untouched - it is recomputed
            # anyway, because relying on that would make the next change to
            # this function silently wrong.
            reply_body = bytearray(body)
            reply_body[0] = 0
            reply_body[2] = 0
            reply_body[3] = 0
            c = checksum16(bytes(reply_body))
            reply_body[2] = (c >> 8) & 0xFF
            reply_body[3] = c & 0xFF
            out = ip_build(self.our_ip, ip.src, PROTO_ICMP, bytes(reply_body),
                           ip.ident, flags_frag=ip.flags_frag)
            self.stats["icmp_echo_answered"] += 1
            self.stats["out"] += 1
            ident = (body[4] << 8) | body[5]
            seq = (body[6] << 8) | body[7]
            self.log("ICMP echo request from %s id=%d seq=%d %d bytes, "
                     "answered." % (bytes_to_ip(ip.src), ident, seq,
                                    len(body) - 8))
            return [out]
        if icmp_type == 0:
            ident = (body[4] << 8) | body[5]
            seq = (body[6] << 8) | body[7]
            self.stats["icmp_echo_replies"] += 1
            self.log("ICMP echo reply from %s id=%d seq=%d %d bytes."
                     % (bytes_to_ip(ip.src), ident, seq, len(body) - 8))
            return []
        if icmp_type in (3, 11):
            self.log("ICMP type %d code %d from %s - the board is reporting a "
                     "delivery problem." % (icmp_type, code,
                                            bytes_to_ip(ip.src)))
            return []
        raise Refusal(
            "q_slip_host error 64: ICMP type %d code %d arrived and this peer "
            "answers only echo request (type 8); check what the board's stack "
            "was asked to send, because nothing was dropped quietly here."
            % (icmp_type, code))

    # -- UDP --------------------------------------------------------------
    def _handle_udp(self, ip):
        if len(ip.payload) < 8:
            raise Refusal(
                "q_slip_host error 65: a UDP datagram arrived with only %d "
                "bytes, which is shorter than its 8-byte header; check the "
                "IPv4 total-length field of the datagram carrying it."
                % len(ip.payload))
        dport = (ip.payload[2] << 8) | ip.payload[3]
        # ICMP destination unreachable, code 3 (port unreachable), carrying the
        # offending header and the first eight bytes of its payload, which is
        # what RFC 792 asks for.  This is the loud answer: the board learns
        # immediately that nothing is listening instead of retransmitting into
        # silence.
        quote = ip.raw[:ip.ihl + 8]
        body = bytearray(8) + quote
        body[0] = 3
        body[1] = 3
        c = checksum16(bytes(body))
        body[2] = (c >> 8) & 0xFF
        body[3] = c & 0xFF
        out = ip_build(self.our_ip, ip.src, PROTO_ICMP, bytes(body),
                       self._ident())
        self.stats["out"] += 1
        self.log("UDP to port %d has no listener on this peer; answered with "
                 "ICMP destination unreachable, port unreachable." % dport)
        return [out]

    # -- TCP --------------------------------------------------------------
    def _handle_tcp(self, ip):
        seg = TcpSegment(ip)
        self.stats["tcp_segments"] += 1
        key = (bytes(ip.src), seg.sport, seg.dport)
        conn = self.conns.get(key)

        if seg.flags & TCP_RST:
            if conn is not None:
                del self.conns[key]
            self.log("TCP reset from %s:%d to port %d; the connection is gone."
                     % (bytes_to_ip(ip.src), seg.sport, seg.dport))
            return []

        if conn is None:
            if (seg.flags & TCP_SYN) and not (seg.flags & TCP_ACK):
                if seg.dport != self.echo_port:
                    return [self._reset(ip, seg)]
                conn = TcpConnection(key, self._isn(), "server")
                conn.rcv_nxt = (seg.seq + 1) & 0xFFFFFFFF
                conn.state = "SYN_RCVD"
                self.conns[key] = conn
                out = self._segment(ip.src, seg, conn,
                                    TCP_SYN | TCP_ACK, b"")
                conn.snd_nxt = (conn.snd_nxt + 1) & 0xFFFFFFFF
                self.log("TCP connection opened from %s:%d to the echo "
                         "service on port %d." % (bytes_to_ip(ip.src),
                                                  seg.sport, seg.dport))
                return [out]
            return [self._reset(ip, seg)]

        if seg.flags & TCP_SYN and seg.flags & TCP_ACK and conn.role == "client":
            conn.rcv_nxt = (seg.seq + 1) & 0xFFFFFFFF
            conn.snd_nxt = (conn.iss + 1) & 0xFFFFFFFF
            conn.state = "ESTABLISHED"
            self.log("TCP connect to %s:%d accepted by the board."
                     % (bytes_to_ip(ip.src), seg.sport))
            return [self._segment(ip.src, seg, conn, TCP_ACK, b"")]

        if seg.seq != conn.rcv_nxt:
            raise Refusal(
                "q_slip_host error 66: a TCP segment arrived with sequence "
                "number %u when %u was expected, and this peer has no "
                "reassembly queue; check for a dropped frame on the SLIP wire, "
                "which at 115200 baud with no flow control is the usual cause."
                % (seg.seq, conn.rcv_nxt))

        replies = []
        if seg.payload:
            conn.rcv_nxt = (conn.rcv_nxt + len(seg.payload)) & 0xFFFFFFFF
            if conn.role == "server":
                if len(seg.payload) > SLIP_MTU - 40:
                    raise Refusal(
                        "q_slip_host error 67: a %d-byte TCP payload cannot be "
                        "echoed inside this link's %d-byte datagram ceiling; "
                        "check the maximum segment size the board announced, "
                        "which should leave room for 40 bytes of headers."
                        % (len(seg.payload), SLIP_MTU))
                out = self._segment(ip.src, seg, conn,
                                    TCP_PSH | TCP_ACK, seg.payload)
                conn.snd_nxt = (conn.snd_nxt + len(seg.payload)) & 0xFFFFFFFF
                conn.bytes_echoed += len(seg.payload)
                self.stats["tcp_bytes_echoed"] += len(seg.payload)
                replies.append(out)
                self.log("TCP echo of %d bytes back to %s:%d."
                         % (len(seg.payload), bytes_to_ip(ip.src), seg.sport))
            else:
                replies.append(self._segment(ip.src, seg, conn, TCP_ACK, b""))
                self.log("TCP data from the board, %d bytes: %r"
                         % (len(seg.payload), seg.payload[:64]))

        if seg.flags & TCP_FIN:
            conn.rcv_nxt = (conn.rcv_nxt + 1) & 0xFFFFFFFF
            out = self._segment(ip.src, seg, conn, TCP_FIN | TCP_ACK, b"")
            conn.snd_nxt = (conn.snd_nxt + 1) & 0xFFFFFFFF
            conn.state = "LAST_ACK"
            replies.append(out)
            self.log("TCP close from %s:%d after %d bytes echoed."
                     % (bytes_to_ip(ip.src), seg.sport, conn.bytes_echoed))
            return replies

        if not replies and (seg.flags & TCP_ACK):
            if conn.state == "SYN_RCVD":
                conn.state = "ESTABLISHED"
            elif conn.state == "LAST_ACK":
                conn.state = "CLOSED"
                del self.conns[key]
            return []
        return replies

    def _segment(self, dst_ip, seg, conn, flags, payload):
        tcp = tcp_build(self.our_ip, dst_ip, seg.dport, seg.sport,
                        conn.snd_nxt, conn.rcv_nxt, flags, TCP_WINDOW, payload)
        self.stats["out"] += 1
        return ip_build(self.our_ip, dst_ip, PROTO_TCP, tcp, self._ident())

    def _reset(self, ip, seg):
        """A segment to a port nothing listens on gets a reset, not silence."""
        if seg.flags & TCP_ACK:
            seq = seg.ack
            ack = 0
            flags = TCP_RST
        else:
            seq = 0
            consumed = len(seg.payload)
            if seg.flags & TCP_SYN:
                consumed += 1
            if seg.flags & TCP_FIN:
                consumed += 1
            ack = (seg.seq + consumed) & 0xFFFFFFFF
            flags = TCP_RST | TCP_ACK
        tcp = tcp_build(self.our_ip, ip.src, seg.dport, seg.sport,
                        seq, ack, flags, 0, b"")
        self.stats["out"] += 1
        self.log("TCP segment to port %d, where nothing is listening; "
                 "answered with a reset." % seg.dport)
        return ip_build(self.our_ip, ip.src, PROTO_TCP, tcp, self._ident())

    # -- origination, so the board's own stack can be driven from here ----
    def originate_ping(self, payload_len=ICMP_ECHO_PAYLOAD_LEN,
                       ident=ICMP_ECHO_ID):
        self.icmp_seq += 1
        body = bytearray(8)
        body[0] = 8
        body[4] = (ident >> 8) & 0xFF
        body[5] = ident & 0xFF
        body[6] = (self.icmp_seq >> 8) & 0xFF
        body[7] = self.icmp_seq & 0xFF
        body += bytes(i & 0xFF for i in range(payload_len))
        c = checksum16(bytes(body))
        body[2] = (c >> 8) & 0xFF
        body[3] = c & 0xFF
        self.stats["out"] += 1
        return ip_build(self.our_ip, self.board_ip, PROTO_ICMP, bytes(body),
                        self._ident())

    def originate_connect(self, dport):
        sport = self.next_client_port
        self.next_client_port += 1
        key = (bytes(self.board_ip), dport, sport)
        conn = TcpConnection(key, self._isn(), "client")
        conn.state = "SYN_SENT"
        conn.snd_nxt = conn.iss
        self.conns[key] = conn
        tcp = tcp_build(self.our_ip, self.board_ip, sport, dport,
                        conn.iss, 0, TCP_SYN, TCP_WINDOW, b"")
        self.stats["out"] += 1
        return ip_build(self.our_ip, self.board_ip, PROTO_TCP, tcp,
                        self._ident()), key

    def originate_send(self, key, payload):
        conn = self.conns.get(key)
        if conn is None or conn.state != "ESTABLISHED":
            raise ToolError(
                "q_slip_host error 68: there is no established connection to "
                "send %d bytes on, so nothing was written; check that the "
                "board answered the SYN this tool sent."
                % len(payload))
        tcp = tcp_build(self.our_ip, self.board_ip, key[2], key[1],
                        conn.snd_nxt, conn.rcv_nxt, TCP_PSH | TCP_ACK,
                        TCP_WINDOW, payload)
        conn.snd_nxt = (conn.snd_nxt + len(payload)) & 0xFFFFFFFF
        self.stats["out"] += 1
        return ip_build(self.our_ip, self.board_ip, PROTO_TCP, tcp,
                        self._ident())


# ===========================================================================
#  Human-readable rendering, used by the live monitor and by --decode
# ===========================================================================

def describe_datagram(data):
    try:
        ip = IPv4(data)
    except Refusal as exc:
        return "unparsable (%s)" % str(exc).split(":", 1)[-1].strip()
    head = "%s > %s" % (bytes_to_ip(ip.src), bytes_to_ip(ip.dst))
    if ip.proto == PROTO_ICMP and len(ip.payload) >= 8:
        b = ip.payload
        names = {0: "echo reply", 3: "destination unreachable",
                 8: "echo request", 11: "time exceeded"}
        name = names.get(b[0], "type %d" % b[0])
        extra = ""
        if b[0] in (0, 8):
            extra = " id=%d seq=%d %d bytes" % (((b[4] << 8) | b[5]),
                                                ((b[6] << 8) | b[7]),
                                                len(b) - 8)
        return "%s ICMP %s%s" % (head, name, extra)
    if ip.proto == PROTO_TCP:
        try:
            seg = TcpSegment(ip)
        except Refusal:
            return "%s TCP (checksum does not verify)" % head
        return ("%s TCP %d > %d [%s] seq=%u ack=%u win=%d len=%d"
                % (head, seg.sport, seg.dport, seg.flag_text(), seg.seq,
                   seg.ack, seg.window, len(seg.payload)))
    if ip.proto == PROTO_UDP and len(ip.payload) >= 8:
        b = ip.payload
        return ("%s UDP %d > %d len=%d"
                % (head, (b[0] << 8) | b[1], (b[2] << 8) | b[3], len(b) - 8))
    return "%s IP protocol %d, %d bytes" % (head, ip.proto, len(ip.payload))


# ===========================================================================
#  The capture file
# ===========================================================================
CAPTURE_MAGIC = "# q_slip_host capture v1"


class Capture(object):
    """Every byte in both directions, with a timestamp, in a text file.

    host_rx is what the board put on the wire; host_tx is what this tool sent
    to the board.  Those are the same two directions the gate's transcript
    calls board_tx and board_rx, seen from the other end of the cable.
    """

    def __init__(self, path, port, baud):
        try:
            self.fh = open(path, "w", encoding="ascii")
        except OSError as exc:
            raise ToolError(
                "q_slip_host error 10: the capture file '%s' could not be "
                "opened for writing, error %d (%s); check that the directory "
                "exists and is writable."
                % (path, exc.errno or 0, exc.strerror or "no system message"))
        self.t0 = time.time()
        self.fh.write("%s port=%s baud=%d started=%s\n"
                      % (CAPTURE_MAGIC, port, baud,
                         time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.fh.flush()

    def write(self, direction, data):
        if not data:
            return
        self.fh.write("%.6f %s %s\n" % (time.time() - self.t0, direction,
                                        binascii.hexlify(data).decode()))
        self.fh.flush()

    def close(self):
        try:
            self.fh.close()
        except OSError:
            pass


def decode_capture(path):
    """Render a capture, or a gate transcript, as decoded frames."""
    try:
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        raise ToolError(
            "q_slip_host error 11: the capture file '%s' could not be read, "
            "error %d (%s); check the path you passed to --decode."
            % (path, exc.errno or 0, exc.strerror or "no system message"))

    stripped = text.lstrip()
    if stripped.startswith("{"):
        return _decode_transcript(path, text)

    if not stripped.startswith("# q_slip_host capture"):
        raise ToolError(
            "q_slip_host error 12: the file '%s' does not begin with the "
            "line '%s' and is not a JSON transcript either, so it is not "
            "something this tool wrote; check that you passed the file named "
            "by --dump." % (path, CAPTURE_MAGIC))

    decoders = {"host_rx": SlipDecoder(), "host_tx": SlipDecoder()}
    labels = {"host_rx": "board -> host", "host_tx": "host  -> board"}
    frames = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            if line.startswith("#"):
                print(line)
            continue
        parts = line.split()
        if len(parts) != 3 or parts[1] not in decoders:
            raise ToolError(
                "q_slip_host error 13: line %d of '%s' is not a timestamp, a "
                "direction of host_rx or host_tx, and a hex string; check "
                "whether the file was edited after it was captured."
                % (lineno, path))
        try:
            raw = binascii.unhexlify(parts[2])
        except (binascii.Error, ValueError):
            raise ToolError(
                "q_slip_host error 14: line %d of '%s' does not hold valid "
                "hexadecimal, so it cannot be decoded; check whether the file "
                "was truncated while it was being written."
                % (lineno, path))
        for dg in decoders[parts[1]].feed(raw):
            frames += 1
            print("%9s %s  %4d bytes  %s"
                  % (parts[0], labels[parts[1]], len(dg),
                     describe_datagram(dg)))
    print("")
    for name, dec in decoders.items():
        print("%s: %d datagrams, %d empty frames, %d overruns, "
              "%d escape violations, %d bytes still pending"
              % (labels[name], dec.datagrams, dec.empty_frames, dec.overruns,
                 dec.bad_escapes, dec.pending))
    print("%d frames rendered from '%s'." % (frames, path))
    return EXIT_OK


def _decode_transcript(path, text):
    doc = load_transcript_text(path, text)
    print("# gate transcript '%s' from %s, target %s, %d baud"
          % (path, doc.get("source", "an unnamed source"),
             doc.get("target", "unnamed"), doc.get("baud", 0)))
    if doc.get("note"):
        print("# note: %s" % doc["note"])
    decoders = {"board_tx": SlipDecoder(), "board_rx": SlipDecoder()}
    labels = {"board_tx": "board -> host", "board_rx": "host  -> board"}
    for ev in doc["events"]:
        raw = binascii.unhexlify(ev["hex"])
        for dg in decoders[ev["dir"]].feed(raw):
            print("seq %4d %s  %4d bytes  %s"
                  % (ev["seq"], labels[ev["dir"]], len(dg),
                     describe_datagram(dg)))
    return EXIT_OK


# ===========================================================================
#  The gate transcript
# ===========================================================================

def load_transcript_text(path, text):
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise ToolError(
            "q_slip_host error 15: the transcript '%s' is not valid JSON (%s); "
            "check whether the gate that writes it, "
            "tools/a64/a64_qslipgeni_check.py, finished its run."
            % (path, exc))
    if not isinstance(doc, dict) or "events" not in doc:
        raise ToolError(
            "q_slip_host error 16: the transcript '%s' has no 'events' list, "
            "so there is nothing to replay; check that the gate wrote the "
            "agreed format, which is a JSON object carrying source, target, "
            "baud, note and events." % path)
    for i, ev in enumerate(doc["events"]):
        for field in ("seq", "dir", "hex"):
            if field not in ev:
                raise ToolError(
                    "q_slip_host error 17: event %d of the transcript '%s' has "
                    "no '%s' field; check that the gate wrote the agreed "
                    "format, which is seq, dir and hex on every event."
                    % (i, path, field))
        if ev["dir"] not in ("board_tx", "board_rx"):
            raise ToolError(
                "q_slip_host error 18: event %d of the transcript '%s' has "
                "direction '%s', and only 'board_tx' and 'board_rx' are "
                "defined; check the gate that wrote it."
                % (i, path, ev["dir"]))
        try:
            binascii.unhexlify(ev["hex"])
        except (binascii.Error, ValueError):
            raise ToolError(
                "q_slip_host error 19: event %d of the transcript '%s' does "
                "not hold valid hexadecimal in its 'hex' field; check the gate "
                "that wrote it." % (i, path))
    return doc


def load_transcript(path):
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        return load_transcript_text(path, fh.read())


# ===========================================================================
#  The self-test
# ===========================================================================

class Grader(object):
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def check(self, name, ok, detail=""):
        if ok:
            self.passed += 1
            print("PASS  %-20s %s" % (name, detail))
        else:
            self.failed += 1
            print("FAIL  %-20s %s" % (name, detail))
        return ok

    def skip(self, name, sentence):
        self.skipped += 1
        print("SKIP  %-20s %s" % (name, sentence))


# The byte-exact expectations, stated here and nowhere else.
EXPECT_ALL256_LEN = 260
EXPECT_ALL256_SHA256 = \
    "bc5f891e2a3f9165bdd5a6deba8cc976604743da3d6642b6f1c6ef2b719e007a"
EXPECT_ONLY_END = "c0dbdcc0"
EXPECT_ONLY_ESC = "c0dbddc0"
EXPECT_PLAIN = "c000c0"


def selftest_framing(g):
    # ---- every byte value, escaped exactly twice ------------------------
    payload = bytes(range(256))
    enc = slip_encode(payload)
    # The expectation is built here by hand, from the RFC's four rules, and
    # not by calling the encoder a second time.
    hand = bytearray([SLIP_END])
    for b in range(256):
        if b == SLIP_END:
            hand += bytes([SLIP_ESC, SLIP_ESC_END])
        elif b == SLIP_ESC:
            hand += bytes([SLIP_ESC, SLIP_ESC_ESC])
        else:
            hand.append(b)
    hand.append(SLIP_END)
    sha = hashlib.sha256(enc).hexdigest()
    g.check("frame/all-256",
            enc == bytes(hand) and len(enc) == EXPECT_ALL256_LEN
            and sha == EXPECT_ALL256_SHA256,
            "%d bytes, sha256 %s" % (len(enc), sha[:16]))

    g.check("frame/only-END",
            binascii.hexlify(slip_encode(b"\xc0")).decode() == EXPECT_ONLY_END,
            "expected %s" % EXPECT_ONLY_END)
    g.check("frame/only-ESC",
            binascii.hexlify(slip_encode(b"\xdb")).decode() == EXPECT_ONLY_ESC,
            "expected %s" % EXPECT_ONLY_ESC)
    g.check("frame/plain",
            binascii.hexlify(slip_encode(b"\x00")).decode() == EXPECT_PLAIN,
            "expected %s" % EXPECT_PLAIN)

    # ---- an empty datagram is refused, not framed -----------------------
    try:
        slip_encode(b"")
        g.check("frame/empty-enc", False, "the encoder framed nothing at all")
    except ToolError as exc:
        g.check("frame/empty-enc", "error 21" in str(exc),
                "refused with a full sentence carrying its code")

    # ---- three ENDs are three empty frames and no datagram --------------
    d = SlipDecoder()
    got = d.feed(b"\xc0\xc0\xc0")
    g.check("frame/empty-dec", got == [] and d.empty_frames == 3,
            "%d datagrams, %d empty frames" % (len(got), d.empty_frames))

    # ---- an oversize frame is discarded, the good one behind it is not --
    d = SlipDecoder()
    stream = (bytes([SLIP_END]) + b"\x41" * (SLIP_RX_MAX + 1)
              + bytes([SLIP_END]) + slip_encode(b"\xde\xad\xbe\xef"))
    got = d.feed(stream)
    g.check("frame/oversize",
            got == [b"\xde\xad\xbe\xef"] and d.overruns == 1
            and d.datagrams == 1,
            "%d overruns, then %r" % (d.overruns, got))

    # ---- ESC followed by a byte RFC 1055 does not define ----------------
    d = SlipDecoder()
    got = d.feed(b"\xc0\xdb\x41\xc0")
    g.check("frame/bad-escape",
            got == [b"\x41"] and d.bad_escapes == 1,
            "byte kept, %d escape violation counted" % d.bad_escapes)

    # ---- a stream that stops mid-frame ----------------------------------
    d = SlipDecoder()
    got = d.feed(b"\xc0\x11\x22")
    g.check("frame/incomplete", got == [] and d.pending == 2,
            "%d datagrams, %d bytes pending" % (len(got), d.pending))

    # ---- round trip, every vector plus a worst-case MTU payload ---------
    worst = bytes([SLIP_END, SLIP_ESC] * (SLIP_MTU // 2))
    ok = True
    for p in (payload, b"\xc0", b"\xdb", b"\x00", b"\xde\xad\xbe\xef", worst):
        d = SlipDecoder()
        if d.feed(slip_encode(p)) != [p]:
            ok = False
    g.check("frame/roundtrip", ok,
            "six vectors, including %d bytes of alternating END and ESC"
            % len(worst))


def selftest_peer(g):
    log_lines = []
    peer = SlipPeer(log=log_lines.append)

    # ---- ICMP echo ------------------------------------------------------
    # An echo request as the board would have sent it: 10.0.0.2 to 10.0.0.1.
    body = bytearray(8)
    body[0] = 8
    body[4] = 0x51
    body[6] = 0x00
    body[7] = 0x07
    body += bytes(i & 0xFF for i in range(16))
    c = checksum16(bytes(body))
    body[2] = (c >> 8) & 0xFF
    body[3] = c & 0xFF
    request = ip_build(ip_to_bytes(DEFAULT_BOARD_IP),
                       ip_to_bytes(DEFAULT_HOST_IP), PROTO_ICMP, bytes(body),
                       0x1234)
    replies = peer.handle_datagram(request)
    ok = len(replies) == 1
    if ok:
        r = replies[0]
        rip = IPv4(r)
        ok = (rip.src == ip_to_bytes(DEFAULT_HOST_IP)
              and rip.dst == ip_to_bytes(DEFAULT_BOARD_IP)
              and rip.ident == 0x1234
              and rip.payload[0] == 0
              and rip.payload[4:] == bytes(body)[4:]
              and checksum16(rip.payload) == 0
              and checksum16(r[:20]) == 0)
    g.check("peer/icmp-echo", ok,
            "type 8 answered with type 0, both checksums recomputed")

    # ---- a corrupt header is refused, not answered ----------------------
    bad = bytearray(request)
    bad[10] ^= 0xFF
    try:
        peer.handle_datagram(bytes(bad))
        g.check("peer/icmp-cksum", False, "a corrupt header was answered")
    except Refusal as exc:
        g.check("peer/icmp-cksum", "error 44" in str(exc),
                "refused with a full sentence carrying its code")

    # ---- TCP: SYN, data, FIN --------------------------------------------
    board = ip_to_bytes(DEFAULT_BOARD_IP)
    host = ip_to_bytes(DEFAULT_HOST_IP)
    syn = ip_build(board, host, PROTO_TCP,
                   tcp_build(board, host, 4096, DEFAULT_ECHO_PORT,
                             1000, 0, TCP_SYN, 2048, b""), 0x2000)
    replies = peer.handle_datagram(syn)
    ok = len(replies) == 1
    if ok:
        seg = TcpSegment(IPv4(replies[0]))
        ok = (seg.flags == (TCP_SYN | TCP_ACK) and seg.seq == TCP_ISN_BASE
              and seg.ack == 1001 and seg.window == TCP_WINDOW
              and seg.offset == 20)
    g.check("peer/tcp-syn", ok,
            "SYN answered with SYN|ACK, seq 0x%08X, no options" % TCP_ISN_BASE)

    data = ip_build(board, host, PROTO_TCP,
                    tcp_build(board, host, 4096, DEFAULT_ECHO_PORT,
                              1001, TCP_ISN_BASE + 1, TCP_PSH | TCP_ACK,
                              2048, b"forge"), 0x2001)
    replies = peer.handle_datagram(data)
    ok = len(replies) == 1
    if ok:
        seg = TcpSegment(IPv4(replies[0]))
        ok = (seg.payload == b"forge" and seg.flags == (TCP_PSH | TCP_ACK)
              and seg.ack == 1006)
    g.check("peer/tcp-echo", ok, "five bytes in, the same five bytes out")

    fin = ip_build(board, host, PROTO_TCP,
                   tcp_build(board, host, 4096, DEFAULT_ECHO_PORT,
                             1006, TCP_ISN_BASE + 6, TCP_FIN | TCP_ACK,
                             2048, b""), 0x2002)
    replies = peer.handle_datagram(fin)
    ok = len(replies) == 1
    if ok:
        seg = TcpSegment(IPv4(replies[0]))
        ok = seg.flags == (TCP_FIN | TCP_ACK) and seg.ack == 1007
    g.check("peer/tcp-fin", ok, "FIN answered with FIN|ACK")

    # ---- a port with nothing behind it gets a reset ----------------------
    stray = ip_build(board, host, PROTO_TCP,
                     tcp_build(board, host, 5000, 9999, 77, 0, TCP_SYN,
                               2048, b""), 0x2003)
    replies = peer.handle_datagram(stray)
    ok = len(replies) == 1
    if ok:
        seg = TcpSegment(IPv4(replies[0]))
        ok = (seg.flags & TCP_RST) != 0 and seg.ack == 78
    g.check("peer/tcp-noport", ok, "answered with a reset, never with silence")

    # ---- UDP to a closed port -------------------------------------------
    udp = ip_build(board, host, PROTO_UDP,
                   bytes([0x30, 0x39, 0x00, 0x35, 0x00, 0x0C, 0x00, 0x00])
                   + b"abcd", 0x2004)
    replies = peer.handle_datagram(udp)
    ok = len(replies) == 1
    if ok:
        rip = IPv4(replies[0])
        ok = (rip.proto == PROTO_ICMP and rip.payload[0] == 3
              and rip.payload[1] == 3 and checksum16(rip.payload) == 0)
    g.check("peer/udp-unreach", ok, "ICMP type 3 code 3, port unreachable")

    # ---- three things it will not handle, each refused loudly ------------
    refusals = 0
    frag = bytearray(ip_build(board, host, PROTO_ICMP, bytes(body), 0x2005,
                              flags_frag=0x2000))
    frag[10] = 0
    frag[11] = 0
    c = checksum16(bytes(frag[:20]))
    frag[10] = (c >> 8) & 0xFF
    frag[11] = c & 0xFF
    for probe, code in ((bytes(frag), "error 45"),
                        (b"\x60" + bytes(19) + bytes(20), "error 41"),
                        (ip_build(board, host, 47, b"\x00" * 8, 0x2006),
                         "error 61")):
        try:
            peer.handle_datagram(probe)
        except Refusal as exc:
            if code in str(exc):
                refusals += 1
    g.check("peer/refuse", refusals == 3,
            "%d of 3 unhandleable datagrams refused with their codes"
            % refusals)


def first_difference(expected, produced):
    """Name the offset that differs, because two long hex strings do not."""
    n = min(len(expected), len(produced))
    for i in range(n):
        if expected[i] != produced[i]:
            lo = max(0, i - 4)
            return ("byte %d of %d differs: the transcript has 0x%02X where "
                    "this peer produced 0x%02X (transcript ...%s..., peer "
                    "...%s...)"
                    % (i, len(expected), expected[i], produced[i],
                       binascii.hexlify(expected[lo:i + 5]).decode(),
                       binascii.hexlify(produced[lo:i + 5]).decode()))
    return ("the first %d bytes agree but the transcript holds %d bytes and "
            "this peer produced %d" % (n, len(expected), len(produced)))


def selftest_replay(g, path):
    if not os.path.exists(path):
        g.skip("replay",
               "The transcript '%s' does not exist, so the replay against the "
               "emulator's UART capture did not run; produce it first by "
               "running the gate tools/a64/a64_qslipgeni_check.py, which "
               "writes that file, and then run this self-test again."
               % path)
        return
    doc = load_transcript(path)
    events = doc["events"]
    print("      transcript '%s' from %s, target %s, %d baud, %d events"
          % (path, doc.get("source", "an unnamed source"),
             doc.get("target", "unnamed"), doc.get("baud", 0), len(events)))
    if doc.get("note"):
        print("      note: %s" % doc["note"])

    peer = SlipPeer(log=lambda text: None)
    decoder = SlipDecoder()
    i = 0
    while i < len(events):
        ev = events[i]
        if ev["dir"] != "board_tx":
            g.check("replay/%04d" % ev.get("seq", i), False,
                    "a board_rx event was found where a board_tx event was "
                    "expected, so the transcript's turn order is not what the "
                    "replay assumes")
            i += 1
            continue
        name = "replay/%04d" % ev.get("seq", i)
        raw = binascii.unhexlify(ev["hex"])
        try:
            datagrams = decoder.feed(raw)
        except Exception as exc:                   # pragma: no cover - defence
            g.check(name, False, "the decoder raised %s" % exc)
            i += 1
            continue
        if not datagrams:
            g.check(name, False,
                    "%d wire bytes decoded to no complete datagram at all, so "
                    "the board's frame is not terminated by an END byte"
                    % len(raw))
            i += 1
            continue

        expected = b""
        j = i + 1
        while j < len(events) and events[j]["dir"] == "board_rx":
            expected += binascii.unhexlify(events[j]["hex"])
            j += 1

        produced = b""
        detail = ""
        failed = False
        for dg in datagrams:
            try:
                for reply in peer.handle_datagram(dg):
                    produced += slip_encode(reply)
            except (Refusal, ToolError) as exc:
                failed = True
                detail = str(exc)
                break
        if failed:
            g.check(name, False, detail)
        else:
            g.check(name, produced == expected,
                    "%s -> %d reply bytes%s"
                    % (describe_datagram(datagrams[0]), len(produced),
                       "" if produced == expected
                       else "; " + first_difference(expected, produced)))
        i = j if j > i + 1 else i + 1


def run_selftest(transcript_path):
    print("q_slip_host self-test - no hardware, no serial port, no privileges.")
    print("Part (a): RFC 1055 framing vectors.")
    g = Grader()
    selftest_framing(g)
    print("Part (a2): the peer, so a missing transcript cannot leave it "
          "unproven.")
    selftest_peer(g)
    print("Part (b): replay against the emulator's UART transcript.")
    selftest_replay(g, transcript_path)
    print("")
    print("%d passed, %d failed, %d skipped."
          % (g.passed, g.failed, g.skipped))
    if g.failed:
        print("The self-test FAILED. Do not take this tool to the bench until "
              "every case above passes, because a failing case means the host "
              "and the board disagree about the protocol.")
        return EXIT_SELFTEST_FAILED
    print("The self-test PASSED.")
    return EXIT_OK


# ===========================================================================
#  Serial, and the port list
# ===========================================================================

def import_pyserial():
    try:
        import serial                                  # noqa: F401
        import serial.tools.list_ports                 # noqa: F401
        return serial
    except ImportError:
        raise ToolError(
            "q_slip_host error 1: the pyserial package is not installed, and "
            "this tool will not fall back to anything else because a silent "
            "fallback on a serial link is how a bench session gets attributed "
            "to the wrong cause; install it with 'python -m pip install "
            "pyserial' and run the command again. The --self-test and "
            "--decode modes need no package at all and work right now.")


def list_ports():
    serial = import_pyserial()
    from serial.tools import list_ports as lp
    ports = sorted(lp.comports(), key=lambda p: p.device)
    print("Serial ports on this %s host:" % platform.system())
    if not ports:
        print("  (none)")
    for p in ports:
        vidpid = "----:----"
        if p.vid is not None and p.pid is not None:
            vidpid = "%04X:%04X" % (p.vid, p.pid)
        print("  %-16s  %s  %s" % (p.device, vidpid,
                                   p.description or "no description"))
        if p.manufacturer or p.serial_number:
            print("  %-16s  %s" % ("", " ".join(
                x for x in (p.manufacturer, p.serial_number) if x)))
    print("")
    print("VOLTAGE WARNING, and it is the whole of the bench safety brief:")
    print("  NEVER connect a 3.3 V or 5 V adapter to JCTL pin 4 or pin 6.")
    print("  Those two pins are the QRB2210's own pads at 1.8 V with no series")
    print("  resistor, no clamp and no buffer anywhere in the path, so 3.3 V on")
    print("  either of them can permanently destroy the SoC. Use an FT232H or")
    print("  FT2232H with VCCIO strapped to 1.8 V, or a bidirectional level")
    print("  shifter with its low side at 1.8 V - never a resistor divider.")
    print("  Measure VCCIO before a signal wire goes near the board.")
    print("  The board's TX at 1.8 V usually reads fine on a 3.3 V input, so")
    print("  readable output is NOT proof that the wiring is safe.")
    print("  JCTL pin 4 = board TX, pin 6 = board RX, pin 1 or 7 = ground.")
    print("  115200 8N1, no flow control. There is no RTS and no CTS on SE4.")
    return EXIT_OK


def open_serial(port, baud):
    serial = import_pyserial()
    try:
        return serial.Serial(port=port, baudrate=baud, bytesize=8,
                             parity="N", stopbits=1, timeout=0,
                             rtscts=False, dsrdtr=False, xonxoff=False)
    except Exception as exc:
        code = getattr(exc, "errno", None) or 0
        raise ToolError(
            "q_slip_host error 2: the serial port '%s' could not be opened at "
            "%d baud, error %d (%s); check that no other program holds the "
            "port, that the adapter is plugged in, and that --list-ports shows "
            "the device name you passed."
            % (port, baud, code, exc))


# ===========================================================================
#  TUN, where the platform allows it
# ===========================================================================
TUNSETIFF = 0x400454CA
IFF_TUN = 0x0001
IFF_NO_PI = 0x1000


def check_tun_available():
    """Refuse --tun on a platform with no TUN device, before anything opens.

    This is checked before the serial port is opened so that the operator gets
    the sentence about the platform rather than a port error that hides it.
    """
    if sys.platform == "linux" and os.path.exists("/dev/net/tun"):
        return
    reason = ("publishes no /dev/net/tun device"
              if sys.platform != "linux"
              else "has no /dev/net/tun device present")
    raise ToolError(
        "q_slip_host error 3: this host runs %s, which %s, so the --tun "
        "bring-up path is not available here; use this tool's built-in "
        "pure-Python peer instead, which answers ICMP echo requests and serves "
        "a TCP echo service with no TUN device, no driver and no administrator "
        "rights - just drop the --tun argument and run the same command again."
        % (platform.system(), reason))


def open_tun(name):
    """Layer 3, no Ethernet header - which is exactly SLIP's shape.

    No shelling out to slattach: this opens /dev/net/tun directly so that the
    tool owns the interface for as long as it runs and the interface goes away
    with it.
    """
    check_tun_available()
    try:
        import fcntl
        import struct
    except ImportError:                              # pragma: no cover
        raise ToolError(
            "q_slip_host error 4: the fcntl module is not available on this "
            "Python build, so /dev/net/tun cannot be configured; use the "
            "built-in pure-Python peer instead by dropping --tun.")
    try:
        fd = os.open("/dev/net/tun", os.O_RDWR)
    except OSError as exc:
        raise ToolError(
            "q_slip_host error 5: /dev/net/tun could not be opened, error %d "
            "(%s); check that the tun module is loaded ('sudo modprobe tun') "
            "and that this command is running with the privileges to open it."
            % (exc.errno or 0, exc.strerror or "no system message"))
    try:
        ifr = struct.pack("16sH22s", name.encode("ascii"),
                          IFF_TUN | IFF_NO_PI, b"")
        fcntl.ioctl(fd, TUNSETIFF, ifr)
    except OSError as exc:
        os.close(fd)
        raise ToolError(
            "q_slip_host error 6: the interface '%s' could not be created on "
            "/dev/net/tun, error %d (%s); check that the name is at most 15 "
            "characters and that no interface of that name already exists."
            % (name, exc.errno or 0, exc.strerror or "no system message"))
    print("TUN interface '%s' is up in layer 3 mode with no packet "
          "information header, which is exactly the shape SLIP carries."
          % name)
    print("Give it an address before anything will route through it:")
    print("    sudo ip addr add %s/30 dev %s" % (DEFAULT_HOST_IP, name))
    print("    sudo ip link set %s up" % name)
    return fd


# ===========================================================================
#  The wire path
# ===========================================================================

def run_wire(args):
    if args.tun:
        check_tun_available()
    port = open_serial(args.port, args.baud)
    capture = Capture(args.dump, args.port, args.baud) if args.dump else None
    tun_fd = open_tun(args.tun) if args.tun else None
    decoder = SlipDecoder()

    def log(text):
        print("  %s" % text)

    peer = SlipPeer(our_ip=args.our_ip, board_ip=args.board_ip,
                    echo_port=args.listen_port, log=log)

    print("SLIP host on %s at %d baud, 8N1, no flow control." % (args.port,
                                                                 args.baud))
    print("This host is %s, the board is %s, echo service on TCP port %d."
          % (args.our_ip, args.board_ip, args.listen_port))
    if tun_fd is None:
        print("Running the pure-Python peer: no TAP, no TUN, no ARP because "
              "SLIP carries a bare IP datagram with no link header at all.")

    def send(datagram):
        wire = slip_encode(datagram)
        port.write(wire)
        if capture:
            capture.write("host_tx", wire)
        print("  host  -> board  %4d bytes  %s"
              % (len(datagram), describe_datagram(datagram)))

    pending_connect = None
    if args.ping:
        for _ in range(args.ping):
            send(peer.originate_ping())
    if args.connect is not None:
        dg, pending_connect = peer.originate_connect(args.connect)
        send(dg)

    deadline = time.time() + args.seconds if args.seconds else None
    sent_payload = False
    try:
        while True:
            if deadline is not None and time.time() > deadline:
                break
            waiting = port.in_waiting if hasattr(port, "in_waiting") else 0
            chunk = port.read(waiting if waiting else 1)
            if chunk:
                if capture:
                    capture.write("host_rx", chunk)
                for dg in decoder.feed(chunk):
                    print("  board -> host   %4d bytes  %s"
                          % (len(dg), describe_datagram(dg)))
                    try:
                        for reply in peer.handle_datagram(dg):
                            send(reply)
                    except (Refusal, ToolError) as exc:
                        print("  REFUSED: %s" % exc)
                        peer.stats["refused"] += 1
            else:
                time.sleep(0.002)
            if (pending_connect and args.send and not sent_payload
                    and peer.conns.get(pending_connect)
                    and peer.conns[pending_connect].state == "ESTABLISHED"):
                send(peer.originate_send(pending_connect,
                                         args.send.encode("utf-8")))
                sent_payload = True
            if tun_fd is not None:
                import select
                r, _, _ = select.select([tun_fd], [], [], 0)
                if r:
                    send(os.read(tun_fd, SLIP_MTU))
    except KeyboardInterrupt:
        print("")
        print("Stopped at the keyboard.")
    finally:
        if capture:
            capture.close()
        if tun_fd is not None:
            os.close(tun_fd)
        port.close()

    print("Datagrams in %d, out %d, echo requests answered %d, TCP segments "
          "%d, TCP bytes echoed %d, refused %d."
          % (peer.stats["in"], peer.stats["out"],
             peer.stats["icmp_echo_answered"], peer.stats["tcp_segments"],
             peer.stats["tcp_bytes_echoed"], peer.stats["refused"]))
    print("Framing: %d datagrams decoded, %d empty frames, %d overruns, "
          "%d escape violations, %d bytes pending."
          % (decoder.datagrams, decoder.empty_frames, decoder.overruns,
             decoder.bad_escapes, decoder.pending))
    if args.dump:
        print("Every byte in both directions is in '%s'; render it with "
              "'--decode %s'." % (args.dump, args.dump))
    return EXIT_OK


# ===========================================================================
#  Command line
# ===========================================================================

def build_parser():
    p = argparse.ArgumentParser(
        prog="q_slip_host.py",
        description="The host end of the Arduino UNO Q's SLIP link over the "
                    "1.8 V GENI SE4 console UART on JCTL. Read the module "
                    "docstring before wiring anything: JCTL pins 4 and 6 are "
                    "1.8 V SoC pads and a 3.3 V adapter can destroy the SoC.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="serial port, for example COM9 or "
                                  "/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD,
                   help="baud rate, default %d" % DEFAULT_BAUD)
    p.add_argument("--list-ports", action="store_true",
                   help="enumerate serial ports with VID:PID and description")
    p.add_argument("--self-test", action="store_true",
                   help="run every graded case with no hardware and no "
                        "third-party package")
    p.add_argument("--transcript", default=DEFAULT_TRANSCRIPT,
                   help="the gate transcript the self-test replays, default "
                        "%s" % DEFAULT_TRANSCRIPT)
    p.add_argument("--decode", metavar="FILE",
                   help="render a capture, or a gate transcript, as decoded "
                        "frames")
    p.add_argument("--dump", metavar="FILE",
                   help="write every byte in both directions to a capture "
                        "file")
    p.add_argument("--tun", metavar="NAME",
                   help="Linux only: hand datagrams to a TUN interface of "
                        "this name instead of to the built-in peer")
    p.add_argument("--our-ip", default=DEFAULT_HOST_IP,
                   help="this host's address, default %s" % DEFAULT_HOST_IP)
    p.add_argument("--board-ip", default=DEFAULT_BOARD_IP,
                   help="the board's address, default %s" % DEFAULT_BOARD_IP)
    p.add_argument("--listen-port", type=int, default=DEFAULT_ECHO_PORT,
                   help="TCP port the echo service answers on, default %d"
                        % DEFAULT_ECHO_PORT)
    p.add_argument("--ping", type=int, default=0, metavar="N",
                   help="originate N ICMP echo requests to the board")
    p.add_argument("--connect", type=int, metavar="PORT",
                   help="originate a TCP connection to this port on the board")
    p.add_argument("--send", metavar="TEXT",
                   help="text to send once a --connect connection is up")
    p.add_argument("--seconds", type=float, default=0,
                   help="stop after this many seconds; the default of 0 runs "
                        "until the keyboard stops it")
    return p


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            return run_selftest(args.transcript)
        if args.list_ports:
            return list_ports()
        if args.decode:
            return decode_capture(args.decode)
        if args.port:
            return run_wire(args)
        parser.print_help()
        print("")
        print("q_slip_host error 7: no mode was chosen, so nothing was done; "
              "pass --self-test to grade the protocol with no hardware, "
              "--list-ports to find the adapter, --decode to read a capture, "
              "or --port to speak SLIP on a wire.")
        return EXIT_ENVIRONMENT
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ENVIRONMENT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
