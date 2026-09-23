#!/usr/bin/env python3
"""anvil_readback.py - bytes OFF an Anvil board, verified: `readback`.

    from anvil_readback import read_range
    data, stats = read_range(console, 0x57400000, 1812000)

ONE READER FOR EVERY HOST TOOL. tools/pi4_upload.py, tools/board_run.py,
tools/pi4_svcprobe_proof.py and the compiler repository's readback tool all
read memory off the board, and all of them use this. It is its own module
because the tools that need it do not share dependencies - board_run.py
runs without pyserial and pi4_upload.py does not - and this needs nothing
but the standard library.

THE CONSOLE IT IS HANDED needs three methods, which the serial console, the
UDP console and board_run's console all have:

    settle(quiet, cap)   read until the line has been quiet for `quiet` s
    send(line)           one command line
    recv_some()          whatever has arrived, or "" after one short wait

THE MEASUREMENT THAT PRODUCED IT, 2026-09-16 (forum topic 839). Reading
1,812,000 bytes with `memory` over the UDP console took 1,048 s - 1,729
bytes a second on a gigabit cable. 74% of that was the board's serial port:
every character the monitor prints goes through a 115,200-baud UART before
the network console's tap sees it, and the hex dump spends 78 characters on
16 bytes. 25% was this side waiting 0.6 s of silence before each of the 443
commands. `readback` sends base64 to the peer that asked, never through the
UART, and this reader stops at the verdict line instead of waiting for
silence.
"""
import base64
import binascii
import re
import socket
import time
import zlib


# =====================================================================
#  Getting bytes OFF the board: `readback`
# =====================================================================
#  The monitor's `readback <addr> <len>` prints (Anvil/Core/readback.pbi):
#
#    readback 57400000 1812000 bytes base64
#    <64 base64 characters>           48 bytes of memory a line
#    ...
#    readback end 1812000 bytes crc32 A1B2C3D4
#
#  and over the network console the base64 goes ONLY to the peer that
#  typed it, never through the board's serial port. That is the whole of
#  the speed: `memory` was 1.7 KB/s over a gigabit cable because every
#  character of its hex went through a 115200-baud UART first.
#
#  THE VERDICT IS TWO COMPARISONS, BOTH MADE HERE. The length of what was
#  decoded against the length the board says it sent, and zlib.crc32 of
#  it against the board's crc32 - the same polynomial computed twice,
#  independently. A lost datagram takes whole lines with it and leaves a
#  stream that still looks orderly, and the length catches that first.
#
#  THIS READER STOPS AT THE VERDICT LINE. It does not wait for silence to
#  decide a reply has ended, which is what cost `memory` 0.6 s per 4 KB
#  chunk, and for the same reason it settles only briefly before sending:
#  the reply names its own address and length in the header and its own
#  length and checksum at the end, so stale output from an earlier
#  command cannot be mistaken for it. A retry, which only happens after
#  something already went wrong, settles for the full quiet period.
# =====================================================================
# THE CHUNK AND THE HOST'S RECEIVE BUFFER ARE ONE DECISION. Measured on build
# 151, 2026-09-16: a 1 MiB readback through the UDP console lost 345,600 of
# 1,048,576 bytes to dropped datagrams, twice, and the second attempt had no
# verdict at all. The board sends a chunk as one burst at the link's speed; the
# host socket's default receive buffer (64 KB on Windows) overflows whenever
# the reader falls a moment behind, and the operating system drops the rest
# without a word. The same read with 262,144-byte chunks and an 8 MiB receive
# buffer took 3.8 s for 2.38 MB with no retries. So the buffer is raised ONCE,
# on the console's own socket, before the first chunk, and the chunk is then
# capped so its whole reply fits in HALF of what the operating system actually
# granted - even if nothing at all is read until the verdict line has arrived.
READBACK_CHUNK_BYTES = 1 << 18
READBACK_RECEIVE_BUFFER = 8 << 20
READBACK_LINE_BYTES = 48          # memory bytes per base64 line
READBACK_LINE_WIRE = 66           # 64 characters, CR, LF
READBACK_MIN_CHUNK = 4096
READBACK_CHUNK_SECONDS = 120.0
READBACK_LINE_CHARS = 64
READBACK_END = re.compile(
    r"(?m)^readback end ([0-9]+) bytes crc32 ([0-9A-Fa-f]{8})$")
READBACK_STOPPED = re.compile(
    r"(?m)^readback stopped after ([0-9]+) of ([0-9]+) bytes crc32 ([0-9A-Fa-f]{8})$")
READBACK_VERDICT = re.compile(
    r"(?m)^readback (?:end [0-9]+ bytes|stopped after [0-9]+ of [0-9]+ bytes)"
    r" crc32 [0-9A-Fa-f]{8}\r?\n")
BASE64_LINE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


class ReadbackError(ValueError):
    """A readback that cannot be accepted. Always a full sentence."""


class ReadbackTimeout(ReadbackError):
    """No verdict line for THIS readback arrived in time."""


def readback_header_re(address, count):
    """The header line of THIS readback and no other."""
    return re.compile(r"(?m)^readback 0*%X %d bytes base64\r?\n"
                      % (address, count), re.IGNORECASE)


def readback_reply(con, address, count, seconds=READBACK_CHUNK_SECONDS,
                   quiet=0.05):
    """Send one `readback` and collect its reply through its verdict line.

    Returns the text. Raises ReadbackTimeout if no verdict for THIS
    readback arrived in time, naming how far it got. The caller may ask
    again: `readback` changes nothing on the board.
    """
    line = "readback %X %X" % (address, count)
    con.settle(quiet=quiet, cap=8)
    con.send(line)
    header = readback_header_re(address, count)
    parts = []
    scan = ""
    found_header = False
    end = time.monotonic() + seconds
    got = 0
    while time.monotonic() < end:
        piece = con.recv_some()
        if not piece:
            continue
        parts.append(piece)
        got += len(piece)
        scan += piece
        if not found_header:
            m = header.search(scan)
            if m is None:
                scan = scan[-256:]
                continue
            found_header = True
            scan = scan[m.end():]
        if READBACK_VERDICT.search(scan):
            # The prompt normally rides in the verdict's own datagram or
            # the next one. Pick it up if it is there so the transcript
            # ends where the command did; it decides nothing.
            tail_end = time.monotonic() + 1.0
            while "pmf>" not in scan[-64:] and time.monotonic() < tail_end:
                more = con.recv_some()
                if more:
                    parts.append(more)
                    scan += more
            return "".join(parts)
        scan = scan[-256:]
    raise ReadbackTimeout(
        "Error 30: no complete readback of %d bytes at %08X arrived within "
        "%.0f s - %s, and %d characters came back in all. readback reads and "
        "changes nothing, so it is safe to ask again; if it keeps happening, "
        "check that no other session is using the board's console and that "
        "the link is up."
        % (count, address, seconds,
           "its header never appeared" if not found_header
           else "the header arrived but no verdict line followed it", got))


def parse_readback(reply, address, count):
    """The bytes of one readback reply, or a ReadbackError saying why not."""
    text = reply.replace("\r", "")
    header = readback_header_re(address, count).search(text + "\n")
    if header is None:
        raise ReadbackError(
            "Error 31: the reply has no 'readback %08X %d bytes base64' header, "
            "so nothing in it can be attributed to this read. Check that the "
            "board's monitor has the readback command (type help on it)."
            % (address, count))
    body = text[header.end():]
    stopped = READBACK_STOPPED.search(body)
    ended = READBACK_END.search(body)
    if stopped and (not ended or stopped.start() < ended.start()):
        raise ReadbackError(
            "Error 32: the board stopped this readback part way: %r. Ctrl-C "
            "reached its console while it was sending. Nothing was accepted."
            % stopped.group(0).strip())
    if not ended:
        raise ReadbackError(
            "Error 33: the reply has a header but no 'readback end' line, so "
            "the stream's length and checksum are unknown. Nothing was "
            "accepted.")
    lines = body[:ended.start()].split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for index, row in enumerate(lines):
        if not BASE64_LINE.match(row):
            raise ReadbackError(
                "Error 34: line %d of the stream is not base64: %r. Anything "
                "the board prints inside a readback is a sentence about a "
                "problem, and it is quoted here rather than skipped. Nothing "
                "was accepted." % (index + 1, row[:120]))
        last = index == len(lines) - 1
        if (not last and (len(row) != READBACK_LINE_CHARS or "=" in row)) \
                or (last and len(row) > READBACK_LINE_CHARS):
            raise ReadbackError(
                "Error 35: base64 line %d is %d characters, and every line but "
                "the last must be exactly %d with no padding - a datagram was "
                "lost or two streams were interleaved. Nothing was accepted."
                % (index + 1, len(row), READBACK_LINE_CHARS))
    try:
        data = base64.b64decode("".join(lines), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ReadbackError(
            "Error 36: the stream does not decode as base64 (%s). Nothing was "
            "accepted." % error)
    said = int(ended.group(1))
    crc_said = int(ended.group(2), 16)
    if said != count:
        raise ReadbackError(
            "Error 37: the board says it sent %d bytes and %d were asked for. "
            "Nothing was accepted." % (said, count))
    if len(data) != said:
        raise ReadbackError(
            "Error 38: %d bytes decoded and the board says it sent %d, so %d "
            "bytes were lost on the way - whole lines go with a lost datagram. "
            "Nothing was accepted; ask again."
            % (len(data), said, said - len(data)))
    crc_here = zlib.crc32(data) & 0xFFFFFFFF
    if crc_here != crc_said:
        raise ReadbackError(
            "Error 39: the bytes decoded here have crc32 %08X and the board "
            "computed %08X over what it sent. The length matched, so bytes were "
            "changed rather than lost. Nothing was accepted."
            % (crc_here, crc_said))
    return data


def receive_buffer(con):
    """Raise the console socket's receive buffer once; return what was granted.

    None when the console has no socket to ask (a scripted console, or a
    serial port - a UART does not drop a burst this way). The value is the
    operating system's answer, not the request: Linux caps it at
    net.core.rmem_max, and the chunk is sized from what is really there.
    """
    granted = getattr(con, "readback_receive_buffer", None)
    if granted is not None:
        return granted
    sock = getattr(con, "sock", None)
    if not isinstance(sock, socket.socket):
        return None
    try:
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF) < READBACK_RECEIVE_BUFFER:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, READBACK_RECEIVE_BUFFER)
        granted = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    except OSError:
        return None
    try:
        con.readback_receive_buffer = granted
    except AttributeError:
        pass
    return granted


def chunk_limit(granted):
    """The largest chunk whose whole reply fits in half of `granted` bytes."""
    lines = max(1, (granted // 2 - 256) // READBACK_LINE_WIRE)
    size = lines * READBACK_LINE_BYTES
    return max(READBACK_MIN_CHUNK, size - size % READBACK_MIN_CHUNK)


def read_range(con, address, count, chunk_bytes=READBACK_CHUNK_BYTES,
               seconds=READBACK_CHUNK_SECONDS, evidence=None, progress=print):
    """`count` bytes from `address`, verified, in chunks of `chunk_bytes`.

    evidence(command, reply), if given, is called with every exchange -
    a retried one included - so a caller can keep a transcript. A chunk
    that fails is asked for ONCE more after a full settle; a second
    failure raises, naming both. Returns (bytes, statistics).
    """
    if count <= 0:
        raise ReadbackError(
            "Error 40: a readback of %d bytes reads nothing; give a length of "
            "at least one byte." % count)
    granted = receive_buffer(con)
    if granted is not None:
        chunk_bytes = min(chunk_bytes, chunk_limit(granted))
    data = bytearray()
    retries = 0
    chunks = (count + chunk_bytes - 1) // chunk_bytes
    began_all = time.monotonic()
    offset = 0
    index = 0
    while offset < count:
        size = min(chunk_bytes, count - offset)
        index += 1
        here = address + offset
        line = "readback %X %X" % (here, size)
        block = None
        first = None
        failure = None
        began = time.monotonic()
        for attempt in (1, 2):
            began = time.monotonic()
            try:
                reply = readback_reply(con, here, size, seconds,
                                       quiet=0.05 if attempt == 1 else 0.6)
            except ReadbackTimeout as error:
                if evidence is not None:
                    evidence(line, "# no complete reply: %s" % error)
                failure = error
            else:
                if evidence is not None:
                    evidence(line, reply)
                try:
                    block = parse_readback(reply, here, size)
                    break
                except ReadbackError as error:
                    failure = error
            if attempt == 1:
                first = failure
                retries += 1
                if progress:
                    progress("  !! chunk %d/%d at %08X: %s"
                             % (index, chunks, here, failure))
                    progress("     Asking once more - readback changes "
                             "nothing on the board.")
        if block is None:
            raise ReadbackError(
                "Error 41: chunk %d of %d, %d bytes at %08X, failed twice. "
                "First: %s Second: %s" % (index, chunks, size, here, first,
                                          failure))
        data += block
        offset += size
        if progress:
            took = time.monotonic() - began
            progress("  chunk %d/%d  %08X +%d bytes in %.2f s (%.0f KB/s), "
                     "crc32 verified"
                     % (index, chunks, here, size, took,
                        size / took / 1024.0 if took > 0 else 0.0))
    seconds_all = time.monotonic() - began_all
    statistics = {
        "command": "readback",
        "chunk_bytes": chunk_bytes,
        "receive_buffer": granted,
        "chunks": chunks,
        "retries": retries,
        "seconds": round(seconds_all, 3),
        "bytes_per_second": (round(count / seconds_all, 1)
                             if seconds_all > 0 else None),
    }
    return bytes(data), statistics
