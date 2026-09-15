#!/usr/bin/env python3
"""board_run.py - one whole board run, and it comes back with a picture.

    python tools/board_run.py <payload.pmf> --console-ip <board> --out runs/name

WHY THIS EXISTS, in the words that ordered it. A payload ran four times on
2026-09-11, returned cleanly every time, and nothing reached the panel; the
fifth drew a garbled frame. The transcripts of all five were the same three
lines. The ruling: "omg thats a garbled mess, you should build screen shots
into the tests" - so EVERY board run comes back with a picture, without a
person watching the panel.

WHAT ONE RUN IS

  1. ask the board where to stage           `map`
  2. arm a one-shot listener and send it    `net recv <port> <addr>` + TCP
  3. prove the bytes landed                 the board's own length and
                                            SHA-256 of the MEMORY, compared
                                            against this file on disk
  4. pick a renderer, if asked              `screen dma` / `screen v3d`
  5. arm the deadman, if asked              `deadman <s>`
  6. note the capture sequence number       `shot status`
  7. boot it, capture armed in the same line `boot mem <addr> shot`
  8. wait for the return line and its x0    (a long timeout: a payload that
                                            works is allowed to take minutes)
  9. read the payload's trace, if asked     `memory <addr> <len>`
 10. read the kept picture                  `shot`
 11. write <name>.png, <name>.json and <name>.txt

and exit NON-ZERO if x0 is not the explicitly expected value (zero by
default), or if no picture came back.

WHY THE PICTURE IS A PASS CONDITION AND NOT AN EXTRA. A run whose payload
returned 0 and left nothing on the screen is exactly the run this tool was
written after. "It returned cleanly" is not a result; it is half of one.

THE CAPTURE SEQUENCE NUMBER IS CHECKED, and that is the one failure a magic
number cannot catch. The capture area keeps the last picture until something
overwrites it, so a run whose capture silently failed would stream the
PREVIOUS run's picture, perfectly well formed, and a human comparing two PNGs
would see two identical screens and conclude the payload drew the same thing
twice. The board's sequence number rises on every completed capture; this
tool reads it before the run and refuses a picture whose number did not move.

    --twin          the payload never returns (a monitor twin). Nothing
                    special happens: the same run, without waiting for a
                    return line, and the picture is whatever the payload
                    kept for itself through the ABI's capture slot. The
                    sequence check is what makes that honest - a twin that
                    never called the slot comes back with no picture and
                    this tool fails, rather than handing back the screen as
                    it happened to look.

    --console-ip A  the board's UDP console. Default from --board-ip.
    --console-port N  5555 unless somebody has changed it.
    --board-ip A    where the image is streamed to. Defaults to --console-ip.
    --port N        the one-shot TCP listener's port. Default 5001.
    --addr HEX      where the container is staged. Default: ask the board
                    with `map` - the monitor has no fixed size and the first
                    free address above it moves with every build.
    --out DIR       where the run's files go. Default runs/<name>.
    --name NAME     what to call them. Default the payload's stem.
    --tier dma|v3d|cpu   send `screen <tier>` before the run.
    --deadman S     arm the deadman watchdog for the payload's window.
    --trace HEX[:LEN]    dump this many bytes (default 256) after the run -
                    the payload's own trace record, KTRC or otherwise.
    --expect-x0 N   accept this unsigned 64-bit return value. N uses Python
                    base-0 syntax (decimal or 0x-prefixed hexadecimal) and
                    defaults to zero.
    --timeout S     how long the payload may take. Default 600.
    --settle S      twin mode only: how long to let it draw. Default 20.
    --no-shot       do not arm a capture on return. THE RUN STILL NEEDS A
                    PICTURE: use it only with a payload that captures
                    itself, and expect the sequence check to say so if it
                    did not.

THE CONSOLE CLIENT IS THIS FILE'S OWN. Anvil's host tooling is being brought
into this repository beside the monitor it drives, so this speaks the UDP
console protocol directly rather than importing anything from outside the
tree: whoever sends a datagram to port 5555 becomes the board's peer, lines
go out with a carriage return, and replies come back as datagrams that have
to be reassembled into lines.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json

import re
import socket
import struct
import sys
import time
import zlib
from pathlib import Path

DEFAULT_CONSOLE_PORT = 5555
DEFAULT_RECV_PORT = 5001
DEFAULT_TIMEOUT = 600.0
DEFAULT_TRACE_BYTES = 256
MAX_TRACE_BYTES = 4096


def monitor_hex_count(byte_count: int) -> str:
    """Encode a monitor command count, whose command language is hexadecimal.

    The command parser has always treated an unprefixed count as hex.  Keeping
    this conversion named at the wire boundary prevents a decimal host length
    such as 672 from silently becoming 0x672 (1,650) on the board.
    """
    if byte_count < 0:
        raise ValueError("a monitor byte count cannot be negative")
    return f"{byte_count:X}"


def parse_trace_spec(value: str | None) -> tuple[int, int] | None:
    """Validate the host trace request before a console or upload exists.

    Addresses follow the monitor's hexadecimal command language. The optional
    CLI length remains an ordinary decimal count, bounded by memcmd's one-dump
    limit. Rejecting it here prevents a malformed evidence request from being
    discovered only after a payload has already run.
    """
    if value is None:
        return None
    parts = value.split(":")
    if len(parts) > 2 or not re.fullmatch(r"[0-9A-Fa-f]+", parts[0]):
        raise ValueError("--trace must be HEX[:DECIMAL_BYTES]")
    address = int(parts[0], 16)
    if len(parts) == 1:
        byte_count = DEFAULT_TRACE_BYTES
    else:
        if not re.fullmatch(r"[0-9]+", parts[1]):
            raise ValueError("--trace length must be a decimal byte count")
        byte_count = int(parts[1], 10)
    if not 1 <= byte_count <= MAX_TRACE_BYTES:
        raise ValueError(
            f"--trace length must be 1..{MAX_TRACE_BYTES} bytes, got {byte_count}")
    if address > 0xFFFFFFFFFFFFFFFF or address + byte_count - 1 > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("--trace address range overflows 64 bits")
    return address, byte_count


def parse_expected_x0(value: str) -> int:
    """Parse the expected payload return before any runner side effect."""
    try:
        expected = int(value, 0)
    except (TypeError, ValueError) as error:
        raise ValueError("--expect-x0 must be a base-0 integer") from error
    if not 0 <= expected <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("--expect-x0 must be an unsigned 64-bit value")
    return expected


# =====================================================================
#  THE WIRE FORMATS, PARSED BY PURE FUNCTIONS
# ---------------------------------------------------------------------
#  Everything in this section takes text and returns values. Nothing here
#  opens a socket, and that is what lets tools/board_run_parse_check.py
#  run the whole decoder against recorded streams with no board on the
#  bench - which is the only kind of test of a screenshot decoder anybody
#  can run twice and get the same answer from.
# =====================================================================

# The monitor's machine format, unchanged since 2026-08-26 and anchored
# whole-line at both ends. `shot` emits exactly what `p` emits so that one
# host decoder serves the live screen and the kept picture both.
PIC_RE = re.compile(r"^PIC ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{2})\s*$", re.M)
RUN_RE = re.compile(r"^([0-9A-F]{6}) ([0-9A-F]{8})\s*$", re.M)
END_RE = re.compile(r"^END ([0-9A-F]{8})\s*$", re.M)
ABORT_RE = re.compile(r"^ABORT ([0-9A-F]{8})\s*$", re.M)

# The one machine line `shot` puts in front of the picture. It is NOT part
# of the PIC stream: the three expressions above are anchored whole-line
# and cannot match it, so an older host decodes the picture and ignores
# this, while this tool reads both.
SHOT_RE = re.compile(
    r"^SHOT ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) "
    r"([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{16}) ([0-9A-F]{8}) ([0-9A-F]{8}) "
    r"([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{8})\s*$", re.M)

SHOT_FIELDS = ("seq", "w", "h", "pitch", "rot", "tier", "x0",
               "panel_w", "panel_h", "bpp", "src", "who", "bytes")

TIER_NAMES = {0: "cpu", 1: "dma", 2: "v3d"}
SRC_NAMES = {0: "none", 1: "hdmi", 2: "dsi"}
WHO_NAMES = {0: "the payload asked for it", 1: "the monitor took it on return"}

# The line RunAt prints on the way back. Sixteen digits, because x0 is a
# 64-bit register and the interesting half of a returned pointer is the one
# eight digits would drop.
RETURN_RE = re.compile(
    r"The payload returned to the monitor\. Its x0 register held ([0-9A-F]{16})")
FATAL_MARKER = "!! Anvil stopped after a processor exception. Record these values;"
FATAL_MARKER_RE = re.compile(r"(?m)^!! Anvil stopped after a processor exception\. Record these values;$")
FATAL_HEAD_RE = re.compile(
    r"(?m)^   EL=([0-9A-F]{16}) slot=([0-9A-F]{16}) ESR=([0-9A-F]{16})$")
FATAL_TAIL_RE = re.compile(
    r"(?m)^   PC=([0-9A-F]{16}) FAR=([0-9A-F]{16}) SP=([0-9A-F]{16})$")

# What `map` says about where to put a file, and how far this image reaches.
STAGE_RE = re.compile(r"^\s*stage a file at\s+\$?([0-9A-Fa-f]+)", re.M)
IMAGE_RE = re.compile(
    r"^\s*this image\s+\$?([0-9A-Fa-f]+)\s+to\s+\$?([0-9A-Fa-f]+)", re.M)

# The board's verdict on a transfer: the length it stored and the digest of
# the MEMORY it stored it in. Not of the bytes as they came off the wire -
# that is the whole point of asking.
RECV_LEN_RE = re.compile(r"Received\s+(\d+)\s+bytes.*?in\s+(\d+)\s+ms", re.S)
RECV_SHA_RE = re.compile(r"sha256\s+([0-9a-f]{64})")

# One line of the monitor's hex dump: an address, the bytes, and the ASCII
# column between bars.
DUMP_RE = re.compile(r"^([0-9A-F]{8,16}):\s+((?:[0-9A-F]{2} )+)\s*\|", re.M)


class StreamError(RuntimeError):
    """The board's answer was not a whole, well-formed picture."""


def parse_shot_header(text: str) -> dict | None:
    """The SHOT line, as a dictionary. None when there is not one."""
    found = SHOT_RE.search(text)
    if not found:
        return None
    header = {name: int(found.group(i + 1), 16)
              for i, name in enumerate(SHOT_FIELDS)}
    header["tier_name"] = TIER_NAMES.get(header["tier"], "unknown")
    header["src_name"] = SRC_NAMES.get(header["src"], "unknown")
    header["who_name"] = WHO_NAMES.get(header["who"], "unknown")
    return header


def parse_pic_stream(text: str) -> tuple[int, int, int, list[bytes]]:
    """Decode a PIC/runs/END stream into rows of RGB bytes.

    THE RUN COUNT IS THE PROOF THE STREAM ARRIVED WHOLE. The board counts
    the runs it emitted and says so in the terminator; a datagram that went
    missing takes runs with it and the two numbers stop agreeing. A decoder
    that ignored the count would write a plausible PNG of a picture that is
    missing a band, which is worse than writing nothing.

    PIXEL ORDER IS PLAIN ARGB and the low byte is BLUE. Confirmed against
    the live monitor on 2026-08-29: the navy console background and the
    orange title only come out right this way.
    """
    head = PIC_RE.search(text)
    if not head:
        raise StreamError(
            "there is no PIC header in the board's reply, so no picture was "
            "decoded. The board refuses to stream one when its capture area "
            "holds nothing; `shot status` on the board says which it is.")
    w, h, bpp = (int(head.group(1), 16), int(head.group(2), 16),
                 int(head.group(3), 16))
    if w <= 0 or h <= 0:
        raise StreamError(
            f"the board's PIC header describes a {w} by {h} picture, which is "
            "not a picture. Nothing was written.")

    body = text[head.end():]
    runs = RUN_RE.findall(body)
    end = END_RE.search(body)
    if not end:
        if ABORT_RE.search(body):
            raise StreamError(
                "the board marked the stream ABORT, so it stopped before the "
                "picture was whole - somebody pressed Ctrl-C on the console, "
                "or the run was interrupted. Nothing was written.")
        raise StreamError(
            f"the stream stopped before its END marker; {len(runs)} runs "
            "arrived. Nothing was written, because half a picture that "
            "decodes looks exactly like a display fault.")
    claimed = int(end.group(1), 16)
    if claimed != len(runs):
        raise StreamError(
            f"the board said it sent {claimed} runs and {len(runs)} were "
            "parsed, so the wire dropped something. Nothing was written.")

    rows: list[bytes] = []
    row = bytearray()
    stride = w * 3
    for count_hex, pixel_hex in runs:
        count = int(count_hex, 16)
        pixel = int(pixel_hex, 16)
        blue = pixel & 0xFF
        green = (pixel >> 8) & 0xFF
        red = (pixel >> 16) & 0xFF
        row.extend(bytes((red, green, blue)) * count)
        while len(row) >= stride:
            rows.append(bytes(row[:stride]))
            del row[:stride]
    if row:
        raise StreamError(
            f"the last row of the picture is {len(row) // 3} pixels short of "
            f"the {w} the header promised, so the runs and the width "
            "disagree. Nothing was written.")
    if len(rows) != h:
        raise StreamError(
            f"{len(rows)} rows decoded and the header said {h}. The stream is "
            "not the picture it describes; nothing was written.")
    return w, h, bpp, rows


def png(width: int, height: int, rows: list[bytes]) -> bytes:
    """A minimal, correct PNG: signature, IHDR, IDAT, IEND.

    Written by hand with zlib from the standard library, the way
    tools/pmfshot.py has always written one. Pillow is not installed on this
    bench and a dependency to save one screenshot would be a poor trade; a
    PNG is four chunks and a CRC.
    """
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (struct.pack(">I", len(data)) + body +
                struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF))

    raw = bytearray()
    for row in rows:
        raw.append(0)                  # filter type 0, None
        raw.extend(row)
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            chunk(b"IEND", b""))


def pixel_sha256(rows: list[bytes]) -> str:
    """The digest of the decoded pixels, so two runs can be compared.

    OF THE PIXELS AND NOT OF THE PNG. A PNG carries a compression choice and
    a filter byte per row; two identical screens compressed by two versions
    of zlib are different files and the same picture. The thing worth
    comparing across runs is what was on the glass.
    """
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row)
    return digest.hexdigest()


def parse_stage_address(text: str) -> int | None:
    found = STAGE_RE.search(text)
    return int(found.group(1), 16) if found else None


def parse_image_extent(text: str) -> tuple[int, int] | None:
    found = IMAGE_RE.search(text)
    if not found:
        return None
    return int(found.group(1), 16), int(found.group(2), 16)


def parse_return_x0(text: str) -> int | None:
    found = RETURN_RE.search(text)
    return int(found.group(1), 16) if found else None


def parse_recv_verdict(text: str) -> tuple[int | None, int | None, str | None]:
    length = RECV_LEN_RE.search(text)
    digest = RECV_SHA_RE.search(text)
    return ((int(length.group(1)) if length else None),
            (int(length.group(2)) if length else None),
            (digest.group(1) if digest else None))


def parse_dump(text: str, expected_address: int | None = None,
               expected_bytes: int | None = None) -> bytes:
    """Decode one bounded monitor dump without discarding its addresses."""
    rows = [(int(address, 16), bytes.fromhex(body))
            for address, body in DUMP_RE.findall(text)]
    if not rows:
        raise StreamError("the monitor's reply contains no memory dump rows")
    start = rows[0][0] if expected_address is None else expected_address
    total = sum(len(data) for _, data in rows) if expected_bytes is None else expected_bytes
    expected_rows = (total + 15) // 16
    if len(rows) != expected_rows:
        raise StreamError(
            f"the monitor returned {len(rows)} dump rows, expected {expected_rows}")
    for index, (address, data) in enumerate(rows):
        want_address = start + index * 16
        want_bytes = min(16, total - index * 16)
        if address != want_address:
            raise StreamError(
                f"dump row {index} starts at {address:08X}, expected {want_address:08X}")
        if len(data) != want_bytes:
            raise StreamError(
                f"dump row {index} has {len(data)} bytes, expected {want_bytes}")
    blob = b"".join(data for _, data in rows)
    if len(blob) != total:
        raise StreamError(f"the monitor returned {len(blob)} dump bytes, expected {total}")
    return blob


def parse_fatal_exception(text: str) -> dict[str, str | None]:
    """Require exception_support's exact marker and structured register rows."""
    flat = text.replace("\r", "")
    if FATAL_MARKER_RE.search(flat) is None:
        raise StreamError("the exact Anvil processor-exception marker is absent")
    head = FATAL_HEAD_RE.search(flat)
    tail = FATAL_TAIL_RE.search(flat)
    if head is None or tail is None:
        raise StreamError("the exception report is incomplete (EL/slot/ESR or PC/FAR missing)")
    return {
        "el": head.group(1), "slot": head.group(2), "esr": head.group(3),
        "pc": tail.group(1), "far": tail.group(2), "sp": tail.group(3),
    }


def has_fatal_marker(text: str) -> bool:
    return FATAL_MARKER_RE.search(text.replace("\r", "")) is not None


def parse_shot_status_seq(text: str) -> int:
    """The capture sequence number `shot status` reports, or 0 for none.

    A board that has never captured anything says so in a sentence and this
    answers 0 - which is the right baseline, because the first capture is
    number 1 and any number at all is then a move.
    """
    found = re.search(r"holds picture number (\d+)", text)
    return int(found.group(1)) if found else 0


# =====================================================================
#  THE CONSOLE
# =====================================================================
class NetConsole:
    """Anvil's UDP console, port 5555.

    WHOEVER SENDS A DATAGRAM BECOMES THE PEER, so the board has to be
    nudged once before it knows where to print. Every line goes out with a
    carriage return and replies arrive as datagrams that this class
    reassembles; nothing above it knows about packet boundaries.
    """

    def __init__(self, ip: str, port: int = DEFAULT_CONSOLE_PORT):
        self.addr = (ip, port)
        self.name = f"{ip}:{port}"
        self.sock = self._bound_socket(ip)
        self.sock.settimeout(0.2)
        self.transcript: list[str] = []
        self.accepted_datagrams: list[bytes] = []
        self.sock.sendto(b"\r", self.addr)

    def _recv_peer(self) -> bytes | None:
        """Receive and byte-preserve one datagram from the selected board."""
        data, peer = self.sock.recvfrom(65535)
        if peer != self.addr:
            return None
        immutable = bytes(data)
        self.accepted_datagrams.append(immutable)
        return immutable

    @staticmethod
    def _bound_socket(ip: str) -> socket.socket:
        """Bind to the interface on the board's segment where there is one.

        A socket bound to 0.0.0.0 on a machine with a VPN up can send the
        console's datagrams down the tunnel, and a console that never
        answers looks exactly like a board that never armed one. Measured on
        this bench: two tunnel interfaces and a default route through them,
        with the board on a link-local cable.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        source = local_bind_for(ip)
        if source:
            try:
                sock.bind((source, 0))
            except OSError:
                pass
        return sock

    def settle(self, quiet: float = 0.6, cap: float = 8.0) -> str:
        end = time.time() + cap
        last = time.time()
        got = ""
        while time.time() < end and time.time() - last < quiet:
            try:
                data = self._recv_peer()
            except socket.timeout:
                continue
            if data is None:
                continue
            got += data.decode("utf-8", "replace")
            last = time.time()
        if got:
            self.transcript.append(got)
        return got

    def send(self, line: str) -> None:
        self.transcript.append(f"\n>>> {line}\n")
        self.sock.sendto(line.encode() + b"\r", self.addr)

    def read_until(self, needles, timeout: float) -> str:
        end = time.time() + timeout
        out = ""
        while time.time() < end:
            try:
                data = self._recv_peer()
            except socket.timeout:
                continue
            if data is None:
                continue
            out += data.decode("utf-8", "replace")
            if any(needle in out for needle in needles):
                break
        self.transcript.append(out)
        return out

    def collect_exception(self, initial: str, quiet: float = 2.0,
                          cap: float = 30.0,
                          reset_wait: float = 0.0) -> tuple[str, str]:
        """Drain a fragmented exception report instead of losing its tail.

        The first ``!!`` often arrives alone, with EL/SLOT/ESR/PC/FAR in later
        UDP datagrams. A returned monitor ends the report with its prompt. A
        deadman reset may never produce that prompt on the old peer socket, so
        a full quiet interval after the watchdog window is recorded honestly
        as an unobserved-reset boundary. ``timeout`` is reported distinctly if
        datagrams never become quiet; every byte received before it is kept.
        """
        end = time.monotonic() + cap
        quiet_end = time.monotonic() + quiet
        no_prompt_before = time.monotonic() + reset_wait
        tail = ""
        boundary = "timeout"
        prompt_seen = bool(re.search(
            r"(?:^|\n)pmf>[ \t]*(?:\n|$)", initial.replace("\r", "")))
        while time.monotonic() < end:
            try:
                data = self._recv_peer()
            except socket.timeout:
                now = time.monotonic()
                try:
                    parse_fatal_exception(initial + tail)
                    complete = True
                except StreamError:
                    complete = False
                if complete and now >= quiet_end and (prompt_seen or now >= no_prompt_before):
                    if prompt_seen:
                        boundary = "prompt+quiet"
                    elif reset_wait > 0:
                        boundary = "deadman-window quiet (reset unobserved)"
                    else:
                        boundary = "complete-record parked quiet"
                    break
                continue
            if data is None:
                continue
            fragment = data.decode("utf-8", "replace")
            tail += fragment
            quiet_end = time.monotonic() + quiet
            if re.search(r"(?:^|\n)pmf>[ \t]*(?:\n|$)",
                         (initial + tail).replace("\r", "")):
                prompt_seen = True
        if tail:
            self.transcript.append(tail)
        return initial + tail, boundary

    def command(self, line: str, seconds: float = 8.0) -> str:
        """Send one line and read through to the prompt that ends it.

        A LEFTOVER PROMPT DOES NOT ACKNOWLEDGE A LATER COMMAND. The reply is
        only this command's once the echoed line has been seen AND a prompt
        after it; anything earlier belongs to whatever came before. A
        command that times out is NEVER resent - it may have executed, and
        a second `boot` is not a retry, it is a second boot.
        """
        self.settle(quiet=0.3, cap=3.0)
        self.send(line)
        echo = re.compile(r"(?:^|\n)(?:pmf>[ \t]*)?" + re.escape(line) + r"[ \t]*\n")
        prompt = re.compile(r"(?:^|\n)pmf>[ \t]*(?:\n|$)")
        end = time.monotonic() + seconds
        out = ""
        while time.monotonic() < end:
            out += self.read_until(["\n", "pmf>"], max(0.0, end - time.monotonic()))
            flat = out.replace("\r", "")
            start = echo.search(flat)
            if start and prompt.search(flat, start.end()):
                return flat[start.start():]
        raise StreamError(
            f"Error 1: no complete response to {line!r} arrived within "
            f"{seconds:.0f} s. The command may have executed; it was NOT "
            "retried, because a repeated boot is a second boot and not a "
            "retry. Check the board's console before sending another.")

    def at_prompt(self, timeout: float = 30.0) -> bool:
        end = time.time() + timeout
        tail = ""
        while time.time() < end:
            self.send("")
            tail = (tail + self.read_until(["pmf>"], 1.0))[-400:]
            if "pmf>" in tail:
                self.settle()
                return True
        return False

    def close(self) -> None:
        self.sock.close()


def capture_fatal_exception(console: NetConsole, initial: str,
                            datagram_start: int, deadman_seconds: int,
                            record: dict, failures: list[str]) -> None:
    """Finish and publish one terminal exception without transmitting."""
    reset_wait = float(deadman_seconds + 5) if deadman_seconds > 0 else 0.0
    evidence, boundary = console.collect_exception(
        initial, cap=max(30.0, reset_wait + 5.0), reset_wait=reset_wait)
    try:
        fields = parse_fatal_exception(evidence)
        complete = True
    except StreamError as error:
        fields = None
        complete = False
        failures.append(str(error))
    raw = console.accepted_datagrams[datagram_start:]
    record["exception"] = {
        "boundary": boundary, "complete": complete,
        "fields": fields, "text": evidence,
        "datagrams": [{"bytes": len(data), "hex": data.hex()} for data in raw],
    }
    if complete:
        failures.append(
            "the payload stopped at a complete processor-exception record; "
            f"evidence was preserved through the {boundary} boundary. "
            "No trace or screenshot command was sent.")
    else:
        failures.append(
            "the payload stopped at an incomplete processor-exception record; "
            f"all available evidence was preserved through the {boundary} boundary. "
            "No trace or screenshot command was sent.")


def local_bind_for(ip: str) -> str | None:
    """This machine's address on the board's segment, or None.

    Asked of the routing table by opening an unconnected UDP socket at the
    board and reading back the local address the kernel chose. It sends
    nothing. A /32 tunnel endpoint answers here too, which is why the caller
    treats a failure to bind as "let the routing table decide" rather than
    as an error.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((ip, 9))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def stream_file(ip: str, port: int, data: bytes,
                connect_timeout: float = 20.0) -> float:
    """Queue every byte to the board's one-shot listener and half-close.

    THE CLOSE IS THE END-OF-FILE MARKER, and it is a half close: the FIN
    goes out and this socket can still see the board's own. sendall proves
    only that the host's socket accepted the bytes. The verdict is the
    board's length and the digest of the MEMORY it wrote them into, read
    afterwards over the console.
    """
    source = local_bind_for(ip)
    end = time.monotonic() + connect_timeout
    last: OSError | None = None
    sock = None
    while time.monotonic() < end:
        try:
            sock = socket.create_connection(
                (ip, port), timeout=5.0,
                source_address=((source, 0) if source else None))
            break
        except OSError as error:            # the listener may not be up yet
            last = error
            sock = None
            time.sleep(0.15)
    if sock is None:
        raise StreamError(
            f"could not connect to {ip} port {port}: {last}. The board said "
            "it was listening, so something between this machine and it is "
            "dropping the connection. Nothing was booted.")
    started = time.monotonic()
    with sock:
        sock.settimeout(60.0)
        sock.sendall(data)
        sock.shutdown(socket.SHUT_WR)
        try:
            while sock.recv(4096):
                pass
        except OSError:
            pass
    return time.monotonic() - started


# =====================================================================
#  THE RUN
# =====================================================================
def run(args: argparse.Namespace) -> int:
    try:
        trace_request = parse_trace_spec(args.trace)
    except ValueError as error:
        print(f"!! invalid trace request: {error}. Nothing was sent or run.")
        return 2
    try:
        expected_x0 = parse_expected_x0(args.expect_x0)
    except ValueError as error:
        print(f"!! invalid expected return: {error}. Nothing was sent or run.")
        return 2

    payload = Path(args.payload)
    if not payload.is_file():
        print(f"!! there is no file at {payload}, so nothing was run.")
        return 2
    data = payload.read_bytes()
    if not data:
        print(f"!! {payload} is empty, so there is nothing to send.")
        return 2
    want = hashlib.sha256(data).hexdigest()

    name = args.name or payload.stem
    out_dir = Path(args.out) if args.out else Path("runs") / name
    out_dir.mkdir(parents=True, exist_ok=True)

    console_ip = args.console_ip or args.board_ip
    board_ip = args.board_ip or args.console_ip
    if not console_ip:
        print("!! this tool needs the board's address: pass --console-ip "
              "(and --board-ip if the image goes somewhere else).")
        return 2

    record: dict = {
        "name": name,
        "payload": str(payload),
        "payload_bytes": len(data),
        "payload_sha256": want,
        "console": f"{console_ip}:{args.console_port}",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "twin": bool(args.twin),
        "expected_x0": f"{expected_x0:016X}",
    }
    failures: list[str] = []
    console = NetConsole(console_ip, args.console_port)
    picture = None
    exception_terminal = False

    try:
        print(f"{payload}: {len(data)} bytes, sha256 {want}")
        print(f"  console {console.name}")
        if not console.at_prompt():
            print(f"!! no Anvil prompt on {console.name}. Is the board powered "
                  "and is this the right console? Nothing was sent.")
            return 1

        record["version"] = console.command("version", 10).strip()

        # ---- where the container goes ------------------------------------
        board_map = console.command("map", 12)
        stage = parse_stage_address(board_map)
        extent = parse_image_extent(board_map)
        addr = int(args.addr, 16) if args.addr else stage
        if addr is None:
            print("!! the board did not say where to stage a file and no "
                  "--addr was given, so nothing was sent. `map` on the board "
                  "prints the address; a board too old to print one needs "
                  "--addr.")
            return 1
        record["stage_addr"] = f"{addr:08X}"
        if extent:
            record["monitor_image"] = [f"{extent[0]:08X}", f"{extent[1]:08X}"]
            # STAGING ON TOP OF THE RUNNING MONITOR DOES NOT LOOK LIKE A
            # FAILURE, WHICH IS THE PROBLEM. Measured 2026-09-08: a board
            # that had its last few kilobytes overwritten kept its address,
            # kept answering, and could not execute a single command,
            # because the command names are strings near the end of the
            # image. It cost a human at the power lead.
            if addr <= extent[1] and addr + len(data) - 1 >= extent[0]:
                print(f"!! REFUSING TO SEND: staging {len(data)} bytes at "
                      f"{addr:08X} would land on the monitor that is running "
                      f"this run ({extent[0]:08X}..{extent[1]:08X}). Leave "
                      f"--addr out and it goes to {stage:08X}, which is where "
                      "this board says to put it.")
                return 1
        print(f"  stage   {addr:08X}")

        # ---- the renderer, if one was asked for ---------------------------
        if args.tier:
            record["tier_reply"] = console.command(f"screen {args.tier}", 20).strip()
            print(f"  screen {args.tier}")

        # ---- what the capture area holds BEFORE the run -------------------
        before = parse_shot_status_seq(console.command("shot status", 10))
        record["shot_seq_before"] = before

        # ---- the transfer -------------------------------------------------
        # THE LISTENER IS ARMED WITHOUT WAITING FOR A PROMPT, because the
        # prompt does not come back until the connection has been taken -
        # `net recv` arms and then waits. So this reads through to the line
        # that says it is listening and starts streaming against that.
        console.settle(quiet=0.3, cap=3.0)
        console.send(f"net recv {args.port} {addr:X}")
        listen = console.read_until(["for ONE connection", "!!", "? net"], 15)
        if "for ONE connection" not in listen:
            print("!! the board did not arm a listener, so nothing was sent. "
                  "It said:\n" + indent(listen))
            return 1
        elapsed = stream_file(board_ip, args.port, data)
        print(f"  sent {len(data)} bytes in {elapsed:.2f} s")

        # HOW LONG TO WAIT FOR THE VERDICT IS A FUNCTION OF THE IMAGE, not a
        # constant: SHA-256 is 61 KB/s on this part with the caches off and
        # 4 MB/s with them on, so the digest is the slow half of a cold run.
        verdict = listen + console.read_until(["sha256 ", "!!"],
                                              30.0 + len(data) / 40000.0)
        got_len, got_ms, got_sha = parse_recv_verdict(verdict)
        record["transfer"] = {"bytes": got_len, "ms": got_ms, "sha256": got_sha}
        if got_len is None or got_sha is None:
            print("!! the board never printed a length and a digest, so this "
                  "transfer HAS NO VERDICT AT ALL - which is not the same as "
                  "a good one. Nothing was booted.")
            return 1
        if got_len != len(data) or got_sha != want:
            print("!! THE UPLOAD DID NOT VERIFY, so nothing was booted.")
            print(f"   host  {len(data)} bytes {want}")
            print(f"   board {got_len} bytes {got_sha}")
            return 1
        print(f"  verified on the board: {got_len} bytes, digest matches")

        # ---- the deadman ---------------------------------------------------
        if args.deadman:
            record["deadman"] = console.command(
                f"deadman {args.deadman}", 10).strip()
            print(f"  deadman {args.deadman} s")

        # ---- the run --------------------------------------------------------
        line = f"boot mem {addr:X}" + ("" if args.no_shot else " shot")
        print(f"  {line}")
        console.settle(quiet=0.3, cap=3.0)
        started = time.monotonic()
        exception_datagram_start = len(console.accepted_datagrams)
        console.send(line)
        if args.twin:
            # A TWIN NEVER COMES BACK, so there is no line to wait for. Let it
            # draw, then read what it kept for itself. The sequence check
            # below is what turns "it drew something" into a fact.
            body = console.read_until(["\x00nothing\x00", FATAL_MARKER], args.settle)
            record["boot_seconds"] = time.monotonic() - started
            record["x0"] = None
        else:
            body = console.read_until(
                ["Its x0 register held", FATAL_MARKER, "? boot"], args.timeout)
            record["boot_seconds"] = time.monotonic() - started
            x0 = parse_return_x0(body)
            record["x0"] = None if x0 is None else f"{x0:016X}"
            if has_fatal_marker(body):
                capture_fatal_exception(
                    console, body, exception_datagram_start, args.deadman,
                    record, failures)
                exception_terminal = True
            elif x0 is None:
                failures.append(
                    f"the payload never returned inside {args.timeout:.0f} s, "
                    "so this run has no result. A deadman would have reset the "
                    "board rather than left it sitting there; --deadman arms "
                    "one.")
            elif x0 != expected_x0:
                failures.append(
                    f"the payload returned x0 = {x0:016X}, expected "
                    f"{expected_x0:016X}. Whatever those numbers mean is the "
                    "payload's to say; this run failed.")
            else:
                print(f"  returned expected x0 = {x0:016X} after "
                      f"{record['boot_seconds']:.1f} s")

        if args.twin and has_fatal_marker(body):
            capture_fatal_exception(
                console, body, exception_datagram_start, args.deadman,
                record, failures)
            exception_terminal = True

        # ---- the payload's own trace ----------------------------------------
        if trace_request is not None and not exception_terminal:
            trace_addr, trace_len = trace_request
            dump = console.command(
                f"memory {trace_addr:X} {monitor_hex_count(trace_len)}", 30)
            blob = parse_dump(dump, trace_addr, trace_len)
            record["trace"] = {
                "addr": f"{trace_addr:08X}",
                "bytes": len(blob),
                "hex": blob.hex(),
                "ascii_magic": blob[:4].decode("ascii", "replace"),
            }
            (out_dir / f"{name}.trace.bin").write_bytes(blob)
            print(f"  trace   {len(blob)} bytes from {trace_addr:08X} "
                  f"(first four: {record['trace']['ascii_magic']!r})")

        # ---- the picture -----------------------------------------------------
        # A PICTURE IS SENT AS TENS OF THOUSANDS OF LINES and takes minutes on
        # a big screen, so the wait is generous and ends at the terminator
        # rather than at a prompt: the prompt comes after the last of three
        # repeated END markers, and waiting for it doubles the timeout risk
        # for nothing.
        if not exception_terminal:
            console.settle(quiet=0.3, cap=3.0)
            console.send("shot")
            reply = console.read_until(["END ", "ABORT ", "!! there is no kept"],
                                       args.shot_timeout)
            reply += console.read_until(["pmf>"], 5.0)
            (out_dir / f"{name}.shot.txt").write_text(reply, encoding="utf-8",
                                                      errors="replace")
            header = parse_shot_header(reply)
            record["shot_header"] = header
            try:
                w, h, bpp, rows = parse_pic_stream(reply)
                picture = png(w, h, rows)
                record["picture"] = {
                    "width": w, "height": h, "bytes_per_pixel": bpp,
                    "pixel_sha256": pixel_sha256(rows),
                }
            except StreamError as error:
                failures.append(f"no picture came back: {error}")

        # THE SEQUENCE CHECK, and it is the one a magic number cannot do. A
        # capture that silently failed leaves the PREVIOUS run's picture in
        # place, perfectly well formed, and two identical PNGs read as a
        # payload that drew the same thing twice.
        if not exception_terminal and header is not None:
            if header["seq"] <= before:
                failures.append(
                    f"the picture that came back is number {header['seq']} and "
                    f"the board already held number {before} before this run, "
                    "so no new capture was taken. What was streamed is the "
                    "PREVIOUS run's screen; this run has no picture.")
            else:
                print(f"  picture {header['w']} x {header['h']}, capture "
                      f"number {header['seq']}, {header['tier_name']} tier, "
                      f"{header['rot']} degrees, {header['who_name']}")
        elif not exception_terminal and not failures:
            failures.append(
                "the board streamed a picture with no SHOT header line, so "
                "there is no way to say which run it is of.")

    except StreamError as error:
        failures.append(str(error))
    finally:
        record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        record["failures"] = failures
        if picture is not None:
            (out_dir / f"{name}.png").write_bytes(picture)
        (out_dir / f"{name}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        (out_dir / f"{name}.txt").write_text(
            "".join(console.transcript), encoding="utf-8", errors="replace")
        console.close()

    written = [out_dir / (name + ".json"), out_dir / (name + ".txt")]
    if picture is not None:
        written.insert(0, out_dir / (name + ".png"))
    print("  wrote " + ", ".join(str(path) for path in written))
    if failures:
        print("!! THIS RUN FAILED:")
        for entry in failures:
            print(f"   {entry}")
        return 1
    print(f"Run complete: the payload returned expected x0 "
          f"{expected_x0:016X} and the picture it left behind is on disk.")
    return 0


def indent(text: str) -> str:
    return "\n".join("   " + line for line in text.strip().splitlines())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("payload", help="the .pmf container to run")
    parser.add_argument("--console-ip", dest="console_ip", default=None)
    parser.add_argument("--console-port", dest="console_port", type=int,
                        default=DEFAULT_CONSOLE_PORT)
    parser.add_argument("--board-ip", dest="board_ip", default=None)
    parser.add_argument("--port", type=int, default=DEFAULT_RECV_PORT)
    parser.add_argument("--addr", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--tier", choices=("dma", "v3d", "cpu"), default=None)
    parser.add_argument("--deadman", type=int, default=0)
    parser.add_argument("--trace", default=None)
    parser.add_argument("--expect-x0", dest="expect_x0", default="0",
                        help="expected unsigned 64-bit return (base-0; default 0)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--shot-timeout", dest="shot_timeout", type=float,
                        default=900.0)
    parser.add_argument("--settle", type=float, default=20.0)
    parser.add_argument("--twin", action="store_true")
    parser.add_argument("--no-shot", dest="no_shot", action="store_true")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
