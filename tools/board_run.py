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
  5. arm and verify the deadman             `deadman <s>`
  6. note the capture sequence number       `shot status`
  7. note the run number                    `last run`
  8. boot it, capture armed in the same line `boot mem <addr> shot`
  9. wait for the return line and its x0    (a long timeout: a payload that
                                            works is allowed to take minutes)
     and if it does not come, ask the board  `last run`
 10. read the payload's trace, if asked     `readback <addr> <len>`
 11. read the kept picture                  `shot`
 12. write <name>.png, <name>.json and <name>.txt

and exit NON-ZERO if x0 is not the explicitly expected value (zero by
default), or if no picture came back.

WHAT IT LEAVES BEHIND WHILE IT IS STILL RUNNING. The record and the
transcript are rewritten after every numbered step above, each carrying a
`stage` field naming the step just reached, and the last write is in a
finally. A run killed at any point therefore leaves a directory that says
exactly where it stopped. An EMPTY directory now means one thing only: the
run never started.

    map -> listener armed -> sent -> verified -> deadman -> boot ->
    return -> trace -> picture

and the terminal stages `listener refused`, `no transfer verdict`,
`upload did not verify`, `deadman refused`, `boot refused`,
`unresolved silence`, `deadman reset`, `restarted`, `never entered`,
`processor exception` and `outcome unknown`. A payload whose return line was
lost but which the board says returned goes on through `return` as usual,
with `return_line_lost` set in the record.

A MISSING RETURN LINE IS NOT A VERDICT. On 2026-09-16 three long payloads
that had finished were reported as never having returned: the line had been
sent and was lost on the way in. So when no return line arrives inside
--timeout this tool asks the board what happened, and says one of

    returned with x0, and the line was lost     the board's run record
    unresolved silence                          no console answer or run record
    reset by the deadman                        the record, after a reset
    stopped at a processor exception            the record
    never entered                               the run number did not move

each as a sentence. A monitor too old to have `last run` gets the one
sentence that is true: the outcome is not known, and that is NOT evidence
that the payload never returned.

KEEPALIVE. The console is UDP, and the host's firewall lets the board's
datagrams in only while it remembers this socket's recent traffic to the
board. Measured on this bench: the reply to `sleep 120` arrived, and the
replies to `sleep 150` and `sleep 300` were dropped, for an interpreter the
firewall allowed on the private network profile only - with the cable on a
public one. For an interpreter allowed on both, the `sleep 300` reply
arrived. So every wait in the console sends an EMPTY datagram every
KEEPALIVE_SECONDS. The monitor takes an empty datagram as no keystrokes at
all - a `sleep 300` was not cut short by fourteen of them - and it refreshes
the flow the firewall keeps. See docs/BOARD_RUN.md. A record that also
carries a `finished` timestamp is one this tool wrote the ending of; a
record without one was killed where its `stage` says.

THE EXIT CODES

    0   the payload returned what was expected and its picture is on disk
    1   the run started and failed. The directory says where it stopped
    2   the run never started. Nothing was sent to the board and nothing
        was written - not even the directory

>>  NEVER WRAP THIS TOOL IN AN OUTER `timeout`, AND NEVER PIPE IT THROUGH
>>  `tail` WHILE IT RUNS.
    Its own `--timeout` is the bound on the payload and nothing else needs
    to impose one; a board that refuses to enter a payload now answers at
    once instead of running that bound out. An outer `timeout` kills this
    process where it stands, losing the picture, the verdict and any say in
    what the board is left doing - and `tail` shows nothing at all until
    the tool exits, so a long run that is working looks exactly like a
    hang, which is the state somebody kills a run in. Both happened on
    2026-09-16: `timeout 600 ... | tail -30` printed nothing, wrote
    nothing, and reported success, because the status it reported was
    tail's.

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
    --deadman S     deadman seconds, 1..15 (default 15); every run requires it.
    --trace HEX[:LEN]    read this many bytes (default 256) back after the
                    run - the payload's own trace record, KTRC or
                    otherwise - with `readback`, whose length and crc32
                    are checked here before a byte of it is kept.
    --expect-x0 N   accept this unsigned 64-bit return value. N uses Python
                    base-0 syntax (decimal or 0x-prefixed hexadecimal) and
                    defaults to zero.
    --timeout S     how long the payload may take. Default 600.
    --ask-seconds S when no return line came, how long to wait for the board
                    to answer before reporting an unresolved outcome.
                    Default 60, which covers a deadman reset and the boot
                    after it.
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
to be reassembled into lines. The one thing it borrows is the READBACK
reader, tools/anvil_readback.py, which is in this tree, needs nothing but
the standard library, and is the single implementation every host tool
uses to take bytes off the board.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anvil_readback import ReadbackError, read_range  # noqa: E402

DEFAULT_CONSOLE_PORT = 5555
DEFAULT_RECV_PORT = 5001
DEFAULT_TIMEOUT = 600.0
DEFAULT_TRACE_BYTES = 256
DEFAULT_DEADMAN_SECONDS = 15
# A TRACE RECORD IS SMALL, and this ceiling says so rather than the
# monitor's. It used to be memcmd's one-dump limit; `readback` has none.
# What it bounds now is the record: the trace is written into <name>.json
# as hex beside everything else the run found, and a megabyte of it there
# would bury the verdict. A bulk read belongs in a tool built for one -
# tools/anvil_readback.py's read_range is that tool.
MAX_TRACE_BYTES = 4096

# The monitor's own ceiling, not a taste: its watchdog counter is 20 bits at
# 65536 ticks a second, so it cannot be armed past a fraction under sixteen
# seconds and it reports the smaller whole number rather than the larger.
MAX_DEADMAN_SECONDS = 15

# THE CONSOLE'S KEEPALIVE. The host's stateful firewall forgets a UDP flow it
# has seen no traffic on; measured on this bench, a reply after 120 s of
# silence arrived and replies after 150 s and 300 s were dropped. RFC 8085
# section 3.5 puts the floor for a keepalive at 15 s; 20 s is well inside the
# shortest loss measured here and costs one 28-byte datagram. EMPTY, because
# the monitor takes it as no keystrokes - anything else would type into
# whatever is running.
KEEPALIVE_SECONDS = 20.0

# How long to wait, after a missing return line, for the board to answer at
# all before reporting silence as unresolved. A deadman is at most 15 s and
# the boot after its reset reaches the console in well under a minute.
DEFAULT_ASK_SECONDS = 60.0


def binary_preview(data: bytes) -> str:
    """Render binary evidence without asking a console to encode binary data.

    Printable ASCII stays readable. Every other byte is an ASCII-only hex
    escape, so the preview is safe on Windows consoles regardless of their
    active code page and the trace file itself remains untouched.
    """
    return "".join(chr(byte) if 0x20 <= byte <= 0x7E else f"\\x{byte:02x}"
                   for byte in data)


def parse_trace_spec(value: str | None) -> tuple[int, int] | None:
    """Validate the host trace request before a console or upload exists.

    Addresses follow the monitor's hexadecimal command language. The optional
    CLI length remains an ordinary decimal count, bounded by MAX_TRACE_BYTES.
    Rejecting it here prevents a malformed evidence request from being
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

# The prompt, and the monitor's two refusal markers.
#
# A PROMPT IS THE BOARD SAYING IT IS FINISHED WITH A COMMAND, and that is
# the only general thing there is to say about a command that was refused:
# it printed why, and then it printed this. Every step below that waits for
# a particular line waits for this as well, so that a step whose line never
# comes back ends when the board does rather than when a clock does.
PROMPT_RE = re.compile(r"(?:^|\n)pmf>[ \t]*(?:\n|$)")

# `!!` is something the monitor would not do; `? ` is a word it does not
# know. Those are its only two, they are used by every command in the tree,
# and nothing else in the monitor's output begins a line with either.
REFUSAL_RE = re.compile(r"(?m)^[ \t]*(?:!!|\?)[ \t].*$")


def needle_found(text: str, needle) -> bool:
    """A needle is a substring, or a compiled expression that must match.

    AN EXPRESSION FOR ANY LINE WHOSE VALUE IS THE POINT. The return line was
    waited for as the words "Its x0 register held", and those words can end a
    datagram with the sixteen digits in the next one: the wait then stopped
    with the value unread and the run looked as if it had returned nothing.
    The monitor sends a whole line per datagram today, so the board never did
    it - the scripted board in tools/board_run_outcome_check.py, which splits
    replies every 64 bytes, did it on the first run.
    """
    if isinstance(needle, str):
        return needle in text
    return needle.search(text) is not None


def echo_pattern(line: str) -> "re.Pattern[str]":
    """Match the monitor's echo of one typed command line.

    THE PROMPT ALONE CANNOT SAY WHETHER A COMMAND IS FINISHED. The monitor
    echoes what is typed at the prompt it is typed at, so the reply opens
    `pmf> boot mem 500000 shot` and a bare `pmf>` needle matches the prompt
    from BEFORE the command ran. Anchoring on the echoed line and looking
    for a prompt after it is the difference between "the board is ready for
    this command" and "the board is finished with it".
    """
    return re.compile(r"(?:^|\n)(?:pmf>[ \t]*)?" + re.escape(line) + r"[ \t]*\n")


def command_body(text: str, line: str) -> str:
    """What the board printed for `line`: after its echo, before its prompt.

    Carriage returns are dropped, because the console sends them and no
    caller here wants them. Text before the echo belongs to whatever came
    before, and text after the prompt to whatever comes next.
    """
    flat = text.replace("\r", "")
    echoed = echo_pattern(line).search(flat)
    body = flat[echoed.end():] if echoed else flat
    ended = PROMPT_RE.search(body)
    if ended:
        body = body[:ended.start()]
    return "\n".join(piece.rstrip() for piece in body.splitlines()
                     if piece.strip())


def refusal_reason(text: str, line: str) -> str:
    """The board's own words for why a command did not do what was asked.

    THIS TOOL KEEPS NO LIST OF REFUSAL STRINGS AND IS NOT GOING TO. `boot
    mem` alone refuses for eight different reasons - the address lands in
    the monitor, the last transfer did not arrive cleanly, the resident
    secondary cores own the board until it restarts - and the monitor grows
    more of them every month. A host tool that matched on their text would
    go silent again the first time one was reworded, which is the same
    failure wearing a newer sentence. What is generic is the SHAPE, "the
    prompt came back and the line I was waiting for did not"; what is
    specific is quoted, verbatim, from the board.
    """
    return command_body(text, line)


def board_refusal(text: str, line: str = "") -> str:
    """The refusal lines in one command's reply, or an empty string.

    Used only for steps whose whole output is the monitor's - `map`,
    `deadman`. NOT for the boot step: a payload prints whatever it likes,
    `!!` included, and failing a run over the payload's own words would be
    a new silent-wrong-answer of this tool's own making. That step decides
    on the prompt and the return line instead.
    """
    body = command_body(text, line) if line else text.replace("\r", "")
    return "\n".join(found.strip() for found in REFUSAL_RE.findall(body))


def deadman_armed_seconds(text: str, line: str, requested: int) -> int | None:
    """Return the confirmed one-shot timeout, or None for an ambiguous reply.

    A prompt is not proof that `deadman <seconds>` succeeded. Require the
    monitor's explicit effective-seconds sentence, the exact requested value,
    and its statement that the arm covers only the NEXT payload.
    """
    body = command_body(text, line)
    if board_refusal(text, line):
        return None
    match = re.search(
        r"(?im)^The deadman watchdog is armed for ([0-9]+) seconds\.$", body)
    if match is None or int(match.group(1)) != requested:
        return None
    if re.search(r"(?i)\bIt covers the NEXT payload only\.", body) is None:
        return None
    return int(match.group(1))


class StreamError(RuntimeError):
    """The board's answer was not a whole, well-formed picture."""


class RunStopped(StreamError):
    """A step ended the run and has already said why.

    ONE ENDING FOR EVERY FAILURE. The steps used to print their sentence and
    `return 1` on the spot, which skipped the reporting at the bottom and
    made the number of ways a run can end the same as the number of places
    it can fail. Raising this instead sends every one of them through the
    same finally, the same record, and the same "THIS RUN FAILED" report.
    """


class ConsoleUnreachable(StreamError):
    """Nothing is listening on the board's console port.

    A UDP console has no connection to refuse, so the refusal arrives as an
    ICMP port-unreachable that the operating system reports back on the
    next receive - as WinError 10054, "an existing connection was forcibly
    closed", which is a confusing thing to be told about a datagram and an
    even more confusing thing to be shown as a traceback.
    """


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


# `last run`'s machine line. Fixed-width hex fields on one anchored line, the
# same shape as SHOT, so the prose around it is for people and is not read.
LASTRUN_RE = re.compile(
    r"^LASTRUN ([0-9A-F]{8}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) "
    r"([0-9A-F]{16}) ([0-9A-F]{16}) ([0-9A-F]{16}) ([0-9A-F]{16}) "
    r"([0-9A-F]{16}) ([0-9A-F]{16})[ \t]*$", re.M)

LASTRUN_NONE = 0
LASTRUN_ENTERED = 1
LASTRUN_RETURNED = 2
LASTRUN_EXCEPTION = 3


def parse_last_run(text: str) -> dict | None:
    """The run record `last run` prints, or None when there is no such line.

    None means the monitor has no `last run` - it refused the word - and is
    kept apart from a record that says nothing has ever been entered.
    """
    found = LASTRUN_RE.search(text.replace("\r", ""))
    if not found:
        return None
    g = [int(value, 16) for value in found.groups()]
    return {
        "run": g[0], "state": g[1], "restarted": bool(g[2]), "deadman": g[3],
        "x0": g[4], "addr": g[5],
        "ms": None if g[6] == 0xFFFFFFFFFFFFFFFF else g[6],
        "esr": g[7], "pc": g[8], "far": g[9],
    }


def parse_shot_status_x0(text: str) -> int | None:
    """The x0 `shot status` says a capture taken ON RETURN recorded, or None."""
    found = re.search(r"as a payload returned \(its x0 was ([0-9A-F]{16})\)", text)
    return int(found.group(1), 16) if found else None


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

    # A console that has sent nothing has no flow for a firewall to forget,
    # so there is nothing to keep alive until its first datagram has gone.
    keepalive_seconds = KEEPALIVE_SECONDS
    keepalives = 0
    last_sent: float | None = None
    # A KEEPALIVE ONLY WHILE A COMMAND OF OURS IS OUTSTANDING (forum 888).
    # The monitor gives the console to whichever endpoint sends it a
    # datagram while nobody owns it, and releases it only when a command
    # finishes - so an empty datagram sent at an idle prompt takes the
    # console and never gives it back, and every other host is answered
    # BUSY until the board restarts. While our own command runs we already
    # own it, and that is the only time the flow needs keeping.
    command_open = False

    def __init__(self, ip: str, port: int = DEFAULT_CONSOLE_PORT):
        self.addr = (ip, port)
        self.name = f"{ip}:{port}"
        self.sock = self._bound_socket(ip)
        self.sock.settimeout(0.2)
        self.transcript: list[str] = []
        self.accepted_datagrams: list[bytes] = []
        self._sendto(b"\r")
        self.last_sent = time.monotonic()

    def keepalive(self) -> None:
        """An empty datagram, if nothing has gone to the board for a while.

        Called from every receive, which is where all of this class's waiting
        happens, so no wait - a five-minute payload, a slow picture - can let
        the host's firewall forget the flow the board's answer comes back on.
        """
        if self.last_sent is None or not self.command_open:
            return
        if time.monotonic() - self.last_sent >= self.keepalive_seconds:
            if self._sendto(b""):
                self.keepalives += 1
            self.last_sent = time.monotonic()

    # THE PC'S OWN ADDRESS ON THE CABLE CAN VANISH FOR A FEW SECONDS. When the
    # board resets - a deadman, an exception parked under a deadman - its
    # Ethernet link drops, the PC takes the cable's address down with the
    # link, and a socket bound to that address is refused by the operating
    # system: WinError 10049, "the requested address is not valid in its
    # context". Measured on the bench board 2026-09-16: the tool died with a
    # traceback in the middle of asking the board what had happened, which is
    # the one moment it most needs to wait. These are the numbers that mean
    # "this machine has no route to the board RIGHT NOW", not a defect.
    _ADDRESS_GONE = {10049, 10051, 10065, 99, 101, 113}

    def _address_gone(self, error: OSError) -> bool:
        code = getattr(error, "winerror", None) or error.errno
        return code in self._ADDRESS_GONE

    def _rebind(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = self._bound_socket(self.addr[0])
        self.sock.settimeout(0.2)

    def _sendto(self, data: bytes) -> bool:
        """Send one datagram; False, with the socket rebound, if this
        machine's address toward the board is gone for the moment."""
        try:
            self.sock.sendto(data, self.addr)
            return True
        except ConnectionError:
            raise
        except OSError as error:
            if not self._address_gone(error):
                raise
            self._rebind()
            return False

    def _recv_peer(self) -> bytes | None:
        """Receive and byte-preserve one datagram from the selected board.

        THE ONE NON-TIMEOUT ERROR THIS SEAM CAN GIVE IS "NOBODY IS THERE",
        and it is caught HERE rather than anywhere broader. A datagram sent
        at a host with no console listening comes back as an ICMP
        port-unreachable, which the operating system hands to the next
        receive on the socket - ConnectionResetError, WinError 10054, or
        ConnectionRefusedError where the socket is connected. Caught here it
        can name the address and the port; caught in a blanket `except` far
        above it would also swallow the programming errors that must stay
        loud.
        """
        self.keepalive()
        try:
            data, peer = self.sock.recvfrom(65535)
        except socket.timeout:
            raise
        except ConnectionError as error:
            raise ConsoleUnreachable(
                f"nothing is listening on the Anvil console at {self.name}: "
                f"this machine's datagram came back unreachable ({error}). "
                "Either the board is not powered or not on this network, or "
                "the address or the port is not its console's - check the "
                "board's own `net` output for the address it answers on, and "
                "that UDP 5555 is the port. Nothing was sent to any board and "
                "nothing was written.") from error
        except OSError as error:
            if not self._address_gone(error):
                raise
            self._rebind()
            time.sleep(0.2)
            return None
        if peer != self.addr:
            return None
        immutable = bytes(data)
        if b"pmf>" in immutable:
            # The board is back at its prompt: our command is finished and
            # the console is nobody's, so a keepalive now would take it.
            self.command_open = False
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
        sent = self._sendto(line.encode() + b"\r")
        self.last_sent = time.monotonic()
        if not sent:
            # A probe (an empty line) may simply go unanswered while the link
            # is down - at_prompt keeps trying. A real command that did not
            # leave this machine is said so, not waited for.
            if line.strip():
                raise StreamError(
                    f"`{line}` could not be sent to {self.name}: this machine "
                    "had no address toward the board at that moment (its "
                    "cable link was down - the board may be resetting). "
                    "Nothing was sent; check the board and run again.")
            return
        self.command_open = bool(line.strip())

    def recv_some(self) -> str:
        """One datagram from the board as text, or "" after one timeout.

        The primitive tools/anvil_readback.py reads a bulk reply with. It
        keeps the transcript and the accepted datagrams exactly as
        read_until does, one datagram at a time.
        """
        try:
            data = self._recv_peer()
        except socket.timeout:
            return ""
        if data is None:
            return ""
        text = data.decode("utf-8", "replace")
        self.transcript.append(text)
        return text

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
            if any(needle_found(out, needle) for needle in needles):
                break
        self.transcript.append(out)
        return out

    def read_until_or_prompt(self, line: str, needles, timeout: float,
                             seen: str = "") -> tuple[str, str]:
        """Read until one of `needles` arrives, or until `line` is finished.

        Returns the text and why it stopped: "needle", "prompt" or
        "timeout". Only the NEW text is returned; `seen` is what has already
        been read for this same command and is used for the decision alone,
        so that a step reading a second answer out of one command - the
        listener's verdict after its "listening" line - can tell that the
        command has already ended rather than waiting out its own bound.

        A REFUSAL IS AN ANSWER AND IT ARRIVES AT ONCE. Every way the monitor
        can decline to enter a payload ends the same way - a sentence saying
        why, and then the prompt - and none of those sentences is the line a
        run is waiting for. Waiting only for that line means waiting the
        whole of `--timeout` at a board which answered in a millisecond and
        has been sitting at its prompt ever since. That is exactly what
        happened on 2026-09-16: two runs, ten minutes each, at a board that
        had refused both instantly.

        THE ECHO IS THE ANCHOR. The prompt a command was typed at comes back
        in the same datagram as the echo of the command itself, so a bare
        `pmf>` would match before the command had run at all. Only a prompt
        after the echoed line belongs to this command. Where the echo never
        arrives this waits the full timeout, which is the old behaviour and
        the right way round: a missed echo must never be read as a refusal.
        """
        pattern = echo_pattern(line)
        end = time.monotonic() + timeout
        out = ""
        while True:
            flat = (seen + out).replace("\r", "")
            for needle in needles:
                if needle_found(flat, needle):
                    return out, "needle"
            echoed = pattern.search(flat)
            # FROM THE ECHO'S OWN NEWLINE, not from after it. The prompt
            # expression needs a line boundary in front of `pmf>`, and the
            # only one a bare prompt directly after the echo has is the
            # newline the echo just consumed - `re.search`'s `^` does not
            # match at a start position, only at the start of the string. A
            # board that refuses with no words at all prints exactly that
            # shape, and searching one character further on made it the one
            # refusal this could not see.
            if echoed and PROMPT_RE.search(flat, max(0, echoed.end() - 1)):
                return out, "prompt"
            left = end - time.monotonic()
            if left <= 0.0:
                return out, "timeout"
            out += self.read_until(list(needles) + ["pmf>"], left)

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
        prompt_seen = bool(PROMPT_RE.search(initial.replace("\r", "")))
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
            if PROMPT_RE.search((initial + tail).replace("\r", "")):
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
        echo = echo_pattern(line)
        end = time.monotonic() + seconds
        out = ""
        while time.monotonic() < end:
            out += self.read_until(["\n", "pmf>"], max(0.0, end - time.monotonic()))
            flat = out.replace("\r", "")
            start = echo.search(flat)
            # From the echo's own newline - see read_until_or_prompt.
            if start and PROMPT_RE.search(flat, max(0, start.end() - 1)):
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


def ask_after_silence(console: NetConsole, args: argparse.Namespace,
                      record: dict, failures: list[str],
                      before: dict | None, seq_before: int
                      ) -> tuple[str, int | None]:
    """No return line inside --timeout: find out from the board what happened.

    Returns (stage, x0). x0 is the payload's return value when the board says
    it returned - the run then goes on to its trace and picture exactly as if
    the line had arrived - and None for every other ending, each of which has
    already put its sentence in `failures`.

    THE ORDER IS THE EVIDENCE'S. Silence first: a payload that still holds the
    processor cannot answer, and nor can a board part-way through the boot
    after a deadman reset, so the question waits --ask-seconds before it takes
    silence for an answer. Then the run record, which is the only thing that
    was there. A monitor without one is told so, and "not known" is what this
    says - never "never returned", which is the sentence that was wrong three
    times on 2026-09-16.
    """
    waited = args.timeout
    answered = console.at_prompt(timeout=args.ask_seconds)
    if not answered:
        failures.append(
            f"no return line arrived inside {waited:.0f} s and the board has "
            f"not answered its console for a further {args.ask_seconds:.0f} s. "
            "The payload may still be running, or the watchdog may have reset "
            "the board and it may still be booting; silence does not prove either "
            "state or that the watchdog fired. Nothing was sent to the board.")
        record["outcome"] = {"kind": "unresolved silence",
                             "silent_seconds": waited + args.ask_seconds,
                             "deadman_armed_seconds": record.get("deadman_armed_seconds")}
        return "unresolved silence", None

    reply = console.command("last run", 10)
    after = parse_last_run(reply)
    record["last_run_after"] = after
    if after is None:
        # A MONITOR WITHOUT THE RECORD. The capture on return is the one other
        # thing that is written only by a payload coming back, so when it was
        # armed and its number moved it is still evidence of a return.
        status = console.command("shot status", 10)
        seq = parse_shot_status_seq(status)
        shot_x0 = parse_shot_status_x0(status)
        if not args.no_shot and seq > seq_before and shot_x0 is not None:
            record["outcome"] = {"kind": "returned, line lost",
                                 "evidence": "capture on return", "x0": f"{shot_x0:016X}"}
            print(f"  no return line arrived inside {waited:.0f} s, but the board "
                  f"took its capture on return (picture {seq}, x0 = {shot_x0:016X}): "
                  "THE PAYLOAD RETURNED and its line was lost on the way here.")
            return "return", shot_x0
        failures.append(
            f"no return line arrived inside {waited:.0f} s, the board is back at "
            "its prompt, and this monitor has no `last run` to say what happened "
            "- so THE OUTCOME IS NOT KNOWN. That is NOT evidence that the payload "
            "never returned: on 2026-09-16 three payloads that had finished were "
            "reported that way. The payload's own result block, read from memory, "
            "is the evidence now; a monitor that has `last run` answers this "
            "directly.")
        record["outcome"] = {"kind": "outcome unknown"}
        return "outcome unknown", None

    run_before = before["run"] if before else None
    if run_before is not None and after["run"] == run_before and after["state"] != LASTRUN_NONE:
        failures.append(
            f"no return line arrived inside {waited:.0f} s, and the board's run "
            f"record still names run {after['run']}, the one before this boot "
            "command - so THE MONITOR NEVER ENTERED THE PAYLOAD. Whatever it said "
            "instead is in the transcript.")
        record["outcome"] = {"kind": "never entered", "run": after["run"]}
        return "never entered", None
    if after["state"] == LASTRUN_NONE:
        failures.append(
            f"no return line arrived inside {waited:.0f} s, and the board's run "
            "record is empty - it has not entered a payload since its memory last "
            "lost power - so THE MONITOR NEVER ENTERED THE PAYLOAD, or the board "
            "lost power while it ran.")
        record["outcome"] = {"kind": "never entered", "run": 0}
        return "never entered", None

    took = ("" if after["ms"] is None else f" after {after['ms'] / 1000:.1f} s")
    if after["state"] == LASTRUN_RETURNED:
        record["outcome"] = {"kind": "returned, line lost", "evidence": "run record",
                             "run": after["run"], "ms": after["ms"],
                             "x0": f"{after['x0']:016X}"}
        print(f"  no return line arrived inside {waited:.0f} s, but the board's run "
              f"record says run {after['run']} RETURNED{took} with x0 = "
              f"{after['x0']:016X}. The payload came back; its line was lost on "
              "the way here.")
        return "return", after["x0"]
    if after["state"] == LASTRUN_EXCEPTION:
        record["outcome"] = {"kind": "processor exception", "run": after["run"],
                             "esr": f"{after['esr']:016X}", "pc": f"{after['pc']:016X}",
                             "far": f"{after['far']:016X}",
                             "restarted": after["restarted"]}
        failures.append(
            f"run {after['run']} STOPPED AT A PROCESSOR EXCEPTION{took}: ESR="
            f"{after['esr']:016X} PC={after['pc']:016X} FAR={after['far']:016X}. " + (
                "The board then reset - the deadman fired, because nothing pets it "
                "once the monitor has stopped. " if after["restarted"] else "") +
            "Check PC against the payload's symbols.")
        return "processor exception", None
    if after["restarted"]:
        if after["deadman"]:
            failures.append(
                f"run {after['run']} NEVER CAME BACK: the board restarted underneath "
                f"it with a {after['deadman']} s deadman armed, so THE DEADMAN RESET "
                "THE BOARD. The payload stopped petting it - it hung, or spent "
                "longer than the deadman between two pets.")
            record["outcome"] = {"kind": "deadman reset", "run": after["run"],
                                 "deadman": after["deadman"]}
            return "deadman reset", None
        failures.append(
            f"run {after['run']} NEVER CAME BACK and the board was restarted "
            "underneath it with no deadman armed - a reset or a power cycle from "
            "outside this tool.")
        record["outcome"] = {"kind": "restarted", "run": after["run"]}
        return "restarted", None
    failures.append(
        f"the board answered its prompt while its run record says run "
        f"{after['run']} is still inside and the board has not restarted, which "
        "the monitor cannot do. The record and the board disagree; both are in "
        "the transcript.")
    record["outcome"] = {"kind": "outcome unknown", "run": after["run"]}
    return "outcome unknown", None


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
#  THE RECORD, WRITTEN AS THE RUN HAPPENS
# =====================================================================
class RunJournal:
    """The run record and the transcript, on disk after every step.

    A RUN THAT IS KILLED MUST STILL SAY WHERE IT GOT TO. This used to write
    both files once, in a finally, which is correct for every ending the
    tool controls and worth nothing against the one it does not: an outer
    `timeout` ends the process with TerminateProcess and no finally runs. On
    2026-09-16 that left an empty directory, no output, and a shell status
    of zero from the `tail` on the end of the pipe - a run about which
    literally nothing was known afterwards, including whether the board had
    ever been sent anything.

    So the record is rewritten and the transcript appended after each step,
    and each write carries the stage just reached. The finally stays: it is
    what adds the ending. What has changed is that it is no longer the only
    write, and an empty directory now means the run never started.

    THE TRANSCRIPT IS APPENDED, NOT REWRITTEN. A streamed picture is tens of
    thousands of lines and rewriting the whole file after every step would
    make the last step quadratic in the picture - so the console's transcript
    list is consumed by index and only the new pieces are written out.
    """

    def __init__(self, out_dir: Path, name: str, record: dict,
                 console: "NetConsole"):
        self.record = record
        self.console = console
        self.out_dir = out_dir
        self.json_path = out_dir / f"{name}.json"
        self.txt_path = out_dir / f"{name}.txt"
        self.consumed = 0
        out_dir.mkdir(parents=True, exist_ok=True)
        # A previous run's transcript in this directory is replaced, not
        # appended to, exactly as the single final write used to replace it.
        self.txt_path.write_text("", encoding="utf-8")

    def step(self, stage: str) -> None:
        self.record["stage"] = stage
        self.flush()

    def flush(self) -> None:
        pieces = self.console.transcript[self.consumed:]
        if pieces:
            with self.txt_path.open("a", encoding="utf-8",
                                    errors="replace") as handle:
                handle.write("".join(pieces))
            self.consumed = len(self.console.transcript)
        self.json_path.write_text(
            json.dumps(self.record, indent=2, sort_keys=True), encoding="utf-8")


# =====================================================================
#  THE RUN
# =====================================================================
def run(args: argparse.Namespace) -> int:
    # Missing Namespace fields from older callers inherit the CLI's safe
    # default. Zero is never an implicit or explicit opt-out for a returning
    # payload run: without a positive watchdog, a non-returning payload can
    # leave the monitor unreachable indefinitely.
    args.deadman = getattr(args, "deadman", DEFAULT_DEADMAN_SECONDS)
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

    if not 1 <= args.deadman <= MAX_DEADMAN_SECONDS:
        # REFUSED HERE RATHER THAN BY THE BOARD, because the board's answer
        # to a number it cannot honour is a sentence and a prompt, and the
        # run would go on without the watchdog it was asked for. The bound
        # is the monitor's own: its counter is 20 bits at 65536 ticks a
        # second, so it cannot be set past a fraction under 16 seconds and
        # says so.
        print(f"!! --deadman must be a whole number of seconds from 1 to "
              f"{MAX_DEADMAN_SECONDS}, and {args.deadman} is not. The counter "
              "behind the board's watchdog is 20 bits wide at 65536 ticks a "
              "second, so it cannot be armed for longer. Nothing was sent or "
              "run.")
        return 2

    name = args.name or payload.stem
    out_dir = Path(args.out) if args.out else Path("runs") / name

    console_ip = args.console_ip or args.board_ip
    board_ip = args.board_ip or args.console_ip
    if not console_ip:
        print("!! this tool needs the board's address: pass --console-ip "
              "(and --board-ip if the image goes somewhere else). Nothing was "
              "sent or run.")
        return 2

    record: dict = {
        "stage": "starting",
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
    journal: RunJournal | None = None
    picture = None
    header = None
    # ONE FLAG FOR "THE PAYLOAD DID NOT RUN, OR DID NOT SURVIVE". A
    # processor exception and a refused boot are different endings and both
    # mean the same thing to everything after them: there is no new capture
    # to read and no trace worth dumping, and streaming the previous run's
    # picture back would hand a failed run a screenshot it has no right to.
    skip_evidence = False

    try:
        print(f"{payload}: {len(data)} bytes, sha256 {want}")
        print(f"  console {console.name}")
        if not console.at_prompt():
            print(f"!! no Anvil prompt answered on {console.name} within 30 s, "
                  "so this run never started and nothing was sent. Is the "
                  "board powered, is it on this network, and is this its "
                  "console address and port? Nothing was written.")
            return 2

        record["version"] = console.command("version", 10).strip()

        # ---- where the container goes ------------------------------------
        board_map = console.command("map", 12)
        stage = parse_stage_address(board_map)
        extent = parse_image_extent(board_map)
        addr = int(args.addr, 16) if args.addr else stage
        if addr is None:
            refused = board_refusal(board_map, "map")
            print("!! the board did not say where to stage a file and no "
                  "--addr was given, so this run never started and nothing "
                  "was sent. `map` on the board prints the address; a board "
                  "too old to print one needs --addr.")
            if refused:
                print("   The board said:\n" + indent(refused))
            return 2
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
                      "this board says to put it. This run never started and "
                      "nothing was written.")
                return 2
        print(f"  stage   {addr:08X}")

        # ---- FROM HERE THE RUN HAS STARTED, so it leaves a record ----------
        # NOTHING IS CREATED BEFORE THIS LINE. Everything above can only
        # decide that the run cannot start - a bad argument, no payload, no
        # prompt, no address, an address that lands on the monitor - and each
        # of those exits 2 having sent nothing and written nothing. A run
        # directory is therefore evidence that a board was spoken to, and an
        # empty one is not a thing this tool can produce.
        journal = RunJournal(out_dir, name, record, console)
        journal.step("map")

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
        # that says it is listening and starts streaming against that. A
        # prompt arriving INSTEAD of that line is the board refusing, and it
        # ends this step at once rather than at the fifteen-second bound.
        recv_line = f"net recv {args.port} {addr:X}"
        console.settle(quiet=0.3, cap=3.0)
        console.send(recv_line)
        listen, why = console.read_until_or_prompt(
            recv_line, ["for ONE connection"], 15)
        if why != "needle":
            reason = refusal_reason(listen, recv_line)
            failures.append(
                "the board did not arm a listener, so nothing was sent and "
                "nothing was booted. " + (
                    "Its prompt came back instead, and it said:\n" + indent(reason)
                    if why == "prompt" and reason else
                    "Its prompt came back and it gave no reason at all."
                    if why == "prompt" else
                    "It said nothing this tool recognised within 15 s; the "
                    "whole reply is in the transcript beside this record."))
            journal.step("listener refused")
            raise RunStopped()
        journal.step("listener armed")
        elapsed = stream_file(board_ip, args.port, data)
        print(f"  sent {len(data)} bytes in {elapsed:.2f} s")
        record["sent_seconds"] = elapsed
        journal.step("sent")

        # HOW LONG TO WAIT FOR THE VERDICT IS A FUNCTION OF THE IMAGE, not a
        # constant: SHA-256 is 61 KB/s on this part with the caches off and
        # 4 MB/s with them on, so the digest is the slow half of a cold run.
        verdict, _why = console.read_until_or_prompt(
            recv_line, ["sha256 "], 30.0 + len(data) / 40000.0, seen=listen)
        verdict = listen + verdict
        got_len, got_ms, got_sha = parse_recv_verdict(verdict)
        record["transfer"] = {"bytes": got_len, "ms": got_ms, "sha256": got_sha}
        if got_len is None or got_sha is None:
            failures.append(
                "the board never printed a length and a digest, so this "
                "transfer HAS NO VERDICT AT ALL - which is not the same as a "
                "good one. Nothing was booted.")
            journal.step("no transfer verdict")
            raise RunStopped()
        if got_len != len(data) or got_sha != want:
            failures.append(
                f"THE UPLOAD DID NOT VERIFY, so nothing was booted: this host "
                f"sent {len(data)} bytes with digest {want} and the board read "
                f"back {got_len} bytes with digest {got_sha} out of the memory "
                "it is about to be told to enter.")
            journal.step("upload did not verify")
            raise RunStopped()
        print(f"  verified on the board: {got_len} bytes, digest matches")
        journal.step("verified")

        # ---- the deadman ---------------------------------------------------
        deadman_line = f"deadman {args.deadman}"
        try:
            reply = console.command(deadman_line, 10)
        except StreamError as error:
            record["deadman"] = {"requested_seconds": args.deadman,
                                  "confirmed": False, "error": str(error)}
            failures.append(
                f"the board did not provide a complete response confirming a "
                f"{args.deadman} s deadman; nothing was booted. {error}")
            journal.step("deadman refused")
            raise RunStopped()
        record["deadman"] = reply.strip()
        refused = board_refusal(reply, deadman_line)
        effective_deadman = deadman_armed_seconds(reply, deadman_line, args.deadman)
        if refused or effective_deadman is None:
            record["deadman_confirmed"] = False
            details = ("The board said:\n" + indent(refused)) if refused else (
                "The reply did not affirm the exact requested timeout and that it "
                "covers the next payload only:\n" + indent(reply))
            failures.append(
                f"the board did not affirmatively confirm a {args.deadman} s "
                f"deadman, so nothing was booted. {details}")
            journal.step("deadman refused")
            raise RunStopped()
        record["deadman_confirmed"] = True
        record["deadman_armed_seconds"] = effective_deadman
        print(f"  deadman {effective_deadman} s confirmed")
        journal.step("deadman")

        # ---- the run number, before the boot -------------------------------
        # WHAT "NEVER ENTERED" IS MEASURED AGAINST. The monitor raises it at
        # the jump and at nothing else, so if the return line goes missing
        # and this number has not moved, nothing was entered. A monitor
        # without `last run` refuses the word, and that is recorded as None.
        before_run = parse_last_run(console.command("last run", 10))
        record["last_run_before"] = before_run

        # ---- the run --------------------------------------------------------
        line = f"boot mem {addr:X}" + ("" if args.no_shot else " shot")
        print(f"  {line}")
        console.settle(quiet=0.3, cap=3.0)
        started = time.monotonic()
        exception_datagram_start = len(console.accepted_datagrams)
        journal.step("boot")
        console.send(line)
        # THE PROMPT ENDS THIS STEP AS SURELY AS THE RETURN LINE DOES, and
        # that is the whole of the fix. Every refusal `boot mem` has - the
        # address is inside the monitor, the last transfer did not arrive
        # cleanly, the resident secondary cores own the board until it
        # restarts, the word after the address was not `shot` - prints its
        # sentence and goes straight back to the prompt. None of them is the
        # return line, so waiting only for that ran the full `--timeout` at a
        # board which had answered instantly and was idle the entire time.
        # The condition is generic: THE PROMPT CAME BACK AND THE PAYLOAD'S
        # RETURN LINE DID NOT. The reason is whatever the board said.
        if args.twin:
            # A TWIN NEVER COMES BACK, so there is no line to wait for - and
            # a prompt is therefore itself the refusal. Otherwise: let it
            # draw, then read what it kept for itself. The sequence check
            # below is what turns "it drew something" into a fact.
            body, why = console.read_until_or_prompt(
                line, [FATAL_MARKER], args.settle)
            record["boot_seconds"] = time.monotonic() - started
            record["x0"] = None
        else:
            body, why = console.read_until_or_prompt(
                line, [RETURN_RE, FATAL_MARKER], args.timeout)
            record["boot_seconds"] = time.monotonic() - started
            x0 = parse_return_x0(body)
            record["x0"] = None if x0 is None else f"{x0:016X}"

        if why == "prompt" and not has_fatal_marker(body):
            reason = refusal_reason(body, line)
            record["boot_refusal"] = reason
            failures.append(
                f"the board's prompt came back {record['boot_seconds']:.1f} s "
                f"after `{line}` and the payload's return line never did, so "
                "the board REFUSED TO ENTER THE PAYLOAD and nothing ran. " + (
                    "The board said:\n" + indent(reason) if reason else
                    "It gave no reason at all, which is itself worth "
                    "reporting."))
            journal.step("boot refused")
            skip_evidence = True
        elif not args.twin:
            if has_fatal_marker(body):
                capture_fatal_exception(
                    console, body, exception_datagram_start, args.deadman,
                    record, failures)
                skip_evidence = True
                journal.step("processor exception")
            elif x0 is None:
                # NOT "NEVER RETURNED". A line that did not arrive is a line
                # that did not arrive; the board is asked what happened.
                journal.step("asking the board")
                outcome, x0 = ask_after_silence(
                    console, args, record, failures, before_run, before)
                if x0 is None:
                    skip_evidence = True
                    journal.step(outcome)
                else:
                    record["x0"] = f"{x0:016X}"
                    record["return_line_lost"] = True
            if x0 is not None and not skip_evidence:
                if x0 != expected_x0:
                    failures.append(
                        f"the payload returned x0 = {x0:016X}, expected "
                        f"{expected_x0:016X}. Whatever those numbers mean is "
                        "the payload's to say; this run failed.")
                elif "return_line_lost" not in record:
                    print(f"  returned expected x0 = {x0:016X} after "
                          f"{record['boot_seconds']:.1f} s")
                journal.step("return")

        if args.twin and not skip_evidence:
            if has_fatal_marker(body):
                capture_fatal_exception(
                    console, body, exception_datagram_start, args.deadman,
                    record, failures)
                skip_evidence = True
                journal.step("processor exception")
            else:
                journal.step("return")

        # ---- the payload's own trace ----------------------------------------
        if trace_request is not None and not skip_evidence:
            trace_addr, trace_len = trace_request
            try:
                blob, _stats = read_range(console, trace_addr, trace_len,
                                          seconds=30.0, progress=None)
            except ReadbackError as error:
                raise StreamError(
                    f"the payload's trace at {trace_addr:08X} could not be "
                    f"read back: {error}") from error
            record["trace"] = {
                "addr": f"{trace_addr:08X}",
                "bytes": len(blob),
                "hex": blob.hex(),
                "ascii_magic": binary_preview(blob[:4]),
            }
            (out_dir / f"{name}.trace.bin").write_bytes(blob)
            print(f"  trace   {len(blob)} bytes from {trace_addr:08X} "
                  f"(first four: {record['trace']['ascii_magic']!r})")
            journal.step("trace")

        # ---- the picture -----------------------------------------------------
        # A PICTURE IS SENT AS TENS OF THOUSANDS OF LINES and takes minutes on
        # a big screen, so the wait is generous and ends at the terminator
        # rather than at a prompt: the prompt comes after the last of three
        # repeated END markers, and waiting for it doubles the timeout risk
        # for nothing.
        if not skip_evidence:
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
            journal.step("picture")

        # THE SEQUENCE CHECK, and it is the one a magic number cannot do. A
        # capture that silently failed leaves the PREVIOUS run's picture in
        # place, perfectly well formed, and two identical PNGs read as a
        # payload that drew the same thing twice.
        if not skip_evidence and header is not None:
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
        elif not skip_evidence and not failures:
            failures.append(
                "the board streamed a picture with no SHOT header line, so "
                "there is no way to say which run it is of.")

    except RunStopped:
        # A step has already said why, in `failures`, and named the stage it
        # stopped at. There is one ending for every failure and this is it.
        pass
    except StreamError as error:
        failures.append(str(error))
    finally:
        # THE LAST WRITE, AND NO LONGER THE ONLY ONE. `stage` is left at the
        # step the run actually reached; the presence of `finished` is what
        # says this tool wrote its own ending rather than being killed.
        if journal is not None:
            record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            record["failures"] = failures
            if picture is not None:
                (out_dir / f"{name}.png").write_bytes(picture)
            journal.flush()
        console.close()

    if journal is None:
        # NOTHING WAS EVER STAGED, so nothing was sent and nothing was
        # written - not a directory, and no longer a WinError 10054
        # traceback either. This is the only ending with no evidence, and it
        # is the one ending that does not need any.
        print("!! THIS RUN NEVER STARTED, so nothing was sent to the board and "
              "nothing was written:")
        for entry in failures:
            print(f"   {entry}")
        return 2

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


def argument_parser() -> argparse.ArgumentParser:
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
    parser.add_argument("--deadman", type=int, default=DEFAULT_DEADMAN_SECONDS,
                        help=f"arm the board's watchdog for the payload's "
                             f"window, 1 to {MAX_DEADMAN_SECONDS} whole "
                             f"seconds (default: {DEFAULT_DEADMAN_SECONDS}; zero is refused)")
    parser.add_argument("--trace", default=None)
    parser.add_argument("--expect-x0", dest="expect_x0", default="0",
                        help="expected unsigned 64-bit return (base-0; default 0)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--ask-seconds", dest="ask_seconds", type=float,
                        default=DEFAULT_ASK_SECONDS)
    parser.add_argument("--shot-timeout", dest="shot_timeout", type=float,
                        default=900.0)
    parser.add_argument("--settle", type=float, default=20.0)
    parser.add_argument("--twin", action="store_true")
    parser.add_argument("--no-shot", dest="no_shot", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    # LINE BUFFERING, ONCE, AT THE ENTRY POINT - not `flush=True` on every
    # print. Python block-buffers stdout when it is not a terminal, so every
    # line this tool had printed was still sitting in a 8 KB buffer when an
    # outer `timeout` killed the process on 2026-09-16 and the run's whole
    # output was lost with it. Either fix works; this one is a single line
    # that covers every print in the file including the ones somebody adds
    # next year, and the `flush=True` spelling is the one that gets left off
    # exactly the print that mattered. Guarded because stdout is not always a
    # text stream that can be reconfigured - a harness may have replaced it.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(line_buffering=True)
        except (ValueError, OSError):
            pass

    args = argument_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
