#!/usr/bin/env python3
"""pmfshot_wifi.py - take a screenshot of the Pi 4 over the network.

THE NAME IS HISTORICAL. This rides Anvil's network console, and since
2026-09-07 that console is armed on EVERY interface the board holds an
address on - the Ethernet cable AND the Wi-Fi radio at the same time,
neither displacing the other. Give it whichever of the board's addresses
you can reach and the picture comes back out of that same interface. The
file keeps its name so that every note and script that already says
pmfshot_wifi.py still works.

The network twin of pmfshot.py. Speaks Anvil's `pr` command - the
RELIABLE screenshot: the board sends the run-length picture as binary
datagrams, each tagged with its byte offset, and this script echoes the
tag back as the acknowledgement before the board sends the next one.
Stop-and-wait, exactly the discipline the image push uses, so a busy
screen (58k+ runs) survives a lossy link instead of losing one datagram
in the middle and wasting the whole capture. A CRC32 over the entire run
stream is checked before a PNG is written - the board computes it as it
sends, the end marker carries it.

    python tools/pmfshot_wifi.py <board-ip> anvil.png
    python tools/pmfshot_wifi.py <board-ip> kept.png --kept

The wire format, all little-endian, every datagram [tag:4][payload]:

    tag FFFFFFFE  header   [w:4][h:4][runs:4][recordBytes:4]
    tag <offset>  chunk    up to 127 records of [count:4][pixel:4]
    tag FFFFFFFF  end      [totalRuns:4][crc32:4][status:4]  (1 = whole)

With --kept, `sr` uses the same chunks, ACKs and end marker. Its 72-byte
header payload extends the first four words above with
[magic=PSR1][version=1][seq][pitch][rotation][tier][x0 low][x0 high]
[panel width][panel height][bpp][source][who][captured bytes], all u32.
The receiver validates these bounds, the complete CRC and every decoded
row before writing a PNG. board_run.py also requires a sequence newer
than the one held before its payload ran.

On a board older than `pr` (nothing binary answers within a few
seconds), this falls back to the legacy `p` text stream, whose run-count
check still refuses a torn capture rather than writing a corrupt PNG.
"""
import socket
import struct
import os
import re
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pmfshot import decode, png

PORT = 5555
TAG_HDR = 0xFFFFFFFE
TAG_END = 0xFFFFFFFF
SHOT_MAGIC = 0x31525350
SHOT_VERSION = 1
MAX_SHOT_PIXELS = 4_194_304
MAX_SHOT_BYTES = 16_777_216


class ReliableShotError(RuntimeError):
    """The kept capture was absent, stale, malformed or incomplete."""


SHOT_FIELDS = ("w", "h", "runs", "record_bytes", "magic", "version",
               "seq", "pitch", "rot", "tier", "x0_lo", "x0_hi",
               "panel_w", "panel_h", "bpp", "src", "who", "bytes")


def parse_kept_header(data):
    """Validate sr's complete tagged header before acknowledging it."""
    if len(data) != 76 or struct.unpack_from("<I", data)[0] != TAG_HDR:
        raise ReliableShotError("sr header has the wrong tag or length")
    head = dict(zip(SHOT_FIELDS, struct.unpack_from("<18I", data, 4)))
    w, h, runs = head["w"], head["h"], head["runs"]
    pw, ph, pitch = head["panel_w"], head["panel_h"], head["pitch"]
    if head["magic"] != SHOT_MAGIC or head["version"] != SHOT_VERSION:
        raise ReliableShotError("sr header magic or version is unknown")
    if head["record_bytes"] != 8 or not head["seq"]:
        raise ReliableShotError("sr header record size or sequence is invalid")
    if not (1 <= w <= 4096 and 1 <= h <= 4096 and
            w * h <= MAX_SHOT_PIXELS and h <= runs <= w * h):
        raise ReliableShotError("sr dimensions or run count exceed the capture bound")
    if head["rot"] in (0, 180):
        geometry_ok = (w, h) == (pw, ph)
    elif head["rot"] in (90, 270):
        geometry_ok = (w, h) == (ph, pw)
    else:
        geometry_ok = False
    if not geometry_ok:
        raise ReliableShotError("sr rotation and dimensions disagree")
    if not (0 < pw <= MAX_SHOT_BYTES // 4 and
            pw * 4 <= pitch <= MAX_SHOT_BYTES and
            0 < ph <= MAX_SHOT_BYTES // pitch and
            pitch * ph <= head["bytes"] <= MAX_SHOT_BYTES):
        raise ReliableShotError("sr capture geometry exceeds the byte bound")
    if head["bpp"] != 4 or head["src"] not in (1, 2) or head["who"] not in (0, 1):
        raise ReliableShotError("sr capture format is invalid")
    if head["tier"] not in (0, 1, 2):
        raise ReliableShotError("sr capture tier is invalid")
    head["x0"] = head.pop("x0_lo") | (head.pop("x0_hi") << 32)
    head.pop("magic")
    head.pop("version")
    head.pop("record_bytes")
    head.pop("runs")
    return head, runs


def decode_kept_runs(blob, w, h):
    """Expand only complete, row-bounded records after CRC verification."""
    rows = []
    row = bytearray()
    pixels_in_row = 0
    for cnt, px in struct.iter_unpack("<II", blob):
        if cnt == 0 or cnt > w - pixels_in_row:
            raise ReliableShotError("sr run crosses a row or has zero pixels")
        row.extend(bytes(((px >> 16) & 255, (px >> 8) & 255, px & 255)) * cnt)
        pixels_in_row += cnt
        if pixels_in_row == w:
            rows.append(bytes(row))
            row.clear()
            pixels_in_row = 0
    if len(rows) != h or row:
        raise ReliableShotError("sr run stream does not fill the advertised rows")
    return rows


def grab_kept_reliable(ip, timeout=300, *, console=None, min_seq=None,
                       expected_x0=None):
    """Receive sr on the caller's console socket or a temporary UDP socket.

    A packet is acknowledged only after its tag, length, offset and content
    match the next expected packet or an exact retransmission. CRC and row
    bounds are checked before any PNG can be written by the caller.
    """
    owned = console is None
    sock = new_socket() if owned else console.sock
    peer = (ip, PORT if owned else console.addr[1])
    if owned:
        sock.settimeout(1.0)
        sock.sendto(b"sr\r", peer)
        recv = lambda: sock.recvfrom(2048)
        ack = lambda tag: sock.sendto(tag, peer)
    else:
        console.send("sr")
        recv = lambda: (console._recv_peer(), peer)
        ack = lambda tag: console._sendto(tag)
    header = None
    raw_header = None
    runs = 0
    blob = None
    offset = 0
    previous = None
    crc = 0
    heard = False
    preheader = ""
    sends = 1
    start = time.monotonic()
    last = start
    try:
        while time.monotonic() - start < timeout:
            try:
                data, source = recv()
            except socket.timeout:
                now = time.monotonic()
                if header is None:
                    if not heard and owned and sends < 3 and now - start > 2 * sends:
                        sock.sendto(b"sr\r", peer)
                        sends += 1
                    if (not heard and now - start > 8) or (heard and now - start > 30):
                        raise ReliableShotError("sr did not return a binary header")
                elif now - last > 10:
                    raise ReliableShotError("sr transfer stalled before its end marker")
                continue
            if data is None or source != peer:
                continue
            heard = True
            last = time.monotonic()
            if header is None and len(preheader) < 4096 and all(
                    byte in (9, 10, 13) or 32 <= byte < 127 for byte in data):
                # A refusal is text followed by the prompt. Require this
                # command's own echo before treating a prompt as its end:
                # the previous command's trailing prompt may still be here.
                fragment = data.decode("ascii")
                preheader = (preheader + fragment)[-4096:]
                if console is not None:
                    console.transcript.append(fragment)
                flat = preheader.replace("\r", "")
                echo = re.search(r"(?:^|\n)(?:pmf>[ \t]*)?sr[ \t]*\n", flat)
                if echo and re.search(
                        r"(?:^|\n)pmf>[ \t]*(?:\n|$)",
                        flat[echo.end() - 1:]):
                    body = flat[echo.end():]
                    reason = body.rsplit("pmf>", 1)[0].strip()
                    raise ReliableShotError(
                        f"sr was refused: {reason or 'the board returned to its prompt'}")
                continue
            if len(data) < 4:
                continue
            tag = struct.unpack_from("<I", data)[0]
            if tag == TAG_HDR:
                if header is None:
                    try:
                        candidate, count = parse_kept_header(data)
                    except ReliableShotError:
                        continue
                    if min_seq is not None and candidate["seq"] <= min_seq:
                        raise ReliableShotError(
                            f"sr capture {candidate['seq']} is stale; previous was {min_seq}")
                    if (expected_x0 is not None and candidate["who"] == 1 and
                            candidate["x0"] != expected_x0):
                        raise ReliableShotError(
                            f"sr capture x0 {candidate['x0']:016X} disagrees with "
                            f"the returned x0 {expected_x0:016X}")
                    header, runs, raw_header = candidate, count, data
                    blob = bytearray(runs * 8)
                if data == raw_header:
                    ack(data[:4])
                continue
            if header is None:
                continue            # command echo or a previous text reply
            if tag == TAG_END:
                if len(data) != 16:
                    continue
                total, wanted_crc, status = struct.unpack_from("<III", data, 4)
                if status == 0:
                    ack(data[:4])
                    raise ReliableShotError("sr was aborted on the board")
                if total != runs or status != 1 or offset != len(blob):
                    continue
                if crc != wanted_crc:
                    raise ReliableShotError(
                        f"sr CRC mismatch: board {wanted_crc:08X}, host {crc:08X}")
                ack(data[:4])
                rows = decode_kept_runs(blob, header["w"], header["h"])
                # Re-ack an END resend if our first acknowledgement was lost.
                end_until = time.monotonic() + 1.2
                while time.monotonic() < end_until:
                    try:
                        twin, twin_source = recv()
                    except socket.timeout:
                        continue
                    if twin is None or twin_source != peer:
                        continue
                    if twin == data:
                        ack(data[:4])
                    elif console is not None and twin:
                        console.transcript.append(twin.decode("utf-8", "replace"))
                return header, rows
            payload = data[4:]
            if (tag == offset and 8 <= len(payload) <= 1016 and
                    len(payload) % 8 == 0 and offset + len(payload) <= len(blob)):
                blob[offset:offset + len(payload)] = payload
                previous = (tag, payload)
                offset += len(payload)
                crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
                ack(data[:4])
            elif previous is not None and tag == previous[0] and payload == previous[1]:
                ack(data[:4])
        raise ReliableShotError("sr exceeded its transfer deadline")
    finally:
        if owned:
            sock.close()


def new_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # A capture is ~500 KB of payload; give the OS room to queue a burst
    # while we process, though stop-and-wait means it never actually needs
    # much. Cheap insurance either way.
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    except OSError:
        pass
    s.bind(("0.0.0.0", 0))
    return s


def grab_reliable(ip, timeout=300):
    """Drive `pr`. Returns (w, h, rows) or None if the board does not
    speak pr / the transfer failed. Every board datagram is acked by
    echoing its 4-byte tag; duplicates (resends whose ack was lost) are
    simply re-acked.

    THE COMMAND ITSELF IS RESENT while nothing at all has come back -
    the one datagram carrying "pr" has no ack of its own, and losing it
    used to waste the whole attempt (seen on silicon: one lost command
    cascaded into the fallback flooding the air and poisoning the next
    two attempts). Once ANY datagram arrives the board clearly heard
    us, so the resend stops and only the header deadline remains -
    generous, because a busy screen's counting pass and a queued
    command both take real time."""
    s = new_socket()
    s.sendto(b"pr\r", (ip, PORT))
    s.settimeout(1.0)

    hdr = None
    end = None
    chunks = {}
    heard = False        # any datagram at all - proof the board got the command
    sends = 1
    t0 = time.time()
    last_report = t0
    while time.time() - t0 < timeout:
        try:
            data, _ = s.recvfrom(2048)
        except socket.timeout:
            waited = time.time() - t0
            if hdr is None:
                if not heard and sends < 3 and waited > 2.0 * sends:
                    s.sendto(b"pr\r", (ip, PORT))
                    sends += 1
                elif not heard and waited > 8.0:
                    s.close()
                    return None      # nothing ever answered - board absent or no pr
                elif heard and waited > 25.0:
                    s.close()
                    return None      # text but never a header: build without pr
            continue
        heard = True
        if len(data) < 4:
            continue
        tag = struct.unpack("<I", data[:4])[0]
        if tag == TAG_HDR:
            if len(data) >= 20:
                hdr = struct.unpack("<IIII", data[4:20])
            s.sendto(data[:4], (ip, PORT))
        elif tag == TAG_END:
            if hdr is None:
                continue
            if len(data) >= 16:
                end = struct.unpack("<III", data[4:16])
            s.sendto(data[:4], (ip, PORT))
            # The board resends END if our ack is lost; stay a moment to
            # re-ack the twins so it finishes cleanly instead of retrying out.
            s.settimeout(0.6)
            t_end = time.time() + 2.0
            while time.time() < t_end:
                try:
                    d2, _ = s.recvfrom(2048)
                except socket.timeout:
                    break
                if len(d2) >= 4 and d2[:4] == data[:4]:
                    s.sendto(d2[:4], (ip, PORT))
            break
        else:
            # A chunk - but only once the header has framed the stream;
            # before it, console text (the command echo) is still flowing.
            if hdr is None:
                continue
            chunks[tag] = data[4:]
            s.sendto(data[:4], (ip, PORT))
            now = time.time()
            if now - last_report > 5:
                print("   %7d bytes, acked ..." % sum(len(v) for v in chunks.values()))
                last_report = now
    s.close()

    if hdr is None or end is None:
        print("   the reliable transfer did not finish (no %s)."
              % ("header" if hdr is None else "end marker"))
        return None
    w, h, runs1, rec = hdr
    total, crc_want, status = end
    if status != 1:
        print("   the board aborted the capture (Ctrl-C on its console).")
        return None
    if rec != 8:
        print("   unknown record size %d - tool and board disagree." % rec)
        return None

    # Assemble by offset and demand contiguity - stop-and-wait means the
    # offsets must tile [0, total*8) exactly.
    expected = total * 8
    blob = bytearray()
    prev_end = 0
    for off in sorted(chunks):
        if off != prev_end:
            print("   gap in the stream at byte %d - assembly refused." % prev_end)
            return None
        blob += chunks[off]
        prev_end = off + len(chunks[off])
    if prev_end != expected:
        print("   stream is %d bytes, end marker said %d - assembly refused."
              % (prev_end, expected))
        return None
    crc_got = zlib.crc32(bytes(blob)) & 0xFFFFFFFF
    if crc_got != crc_want:
        print("   CRC mismatch (board %08X, assembled %08X) - refused."
              % (crc_want, crc_got))
        return None
    print("   %d runs, %d bytes, CRC32 %08X verified" % (total, expected, crc_got))

    # Records to pixel rows, the same ARGB order pmfshot.decode proved on
    # silicon: low byte BLUE.
    rows = []
    row = bytearray()
    wbytes = w * 3
    for i in range(total):
        cnt, px = struct.unpack_from("<II", blob, i * 8)
        b = px & 0xFF
        g = (px >> 8) & 0xFF
        r = (px >> 16) & 0xFF
        row.extend(bytes((r, g, b)) * cnt)
        while len(row) >= wbytes:
            rows.append(bytes(row[:wbytes]))
            del row[:wbytes]
    if len(rows) != h:
        print("   note: %d rows decoded, header said %d" % (len(rows), h))
        h = len(rows)
    return w, h, rows


def grab(ip, timeout=90):
    """The legacy `p` text stream - the fallback for boards without pr."""
    s = new_socket()
    s.sendto(b"p\r", (ip, PORT))
    s.settimeout(2.0)
    buf = b""
    t0 = time.time()
    last = t0
    while time.time() - t0 < timeout:
        try:
            d, _ = s.recvfrom(4096)
        except socket.timeout:
            if b"END " in buf:
                break
            continue
        buf += d
        if b"END " in buf:
            # Drain the tail so the run-count line is not clipped.
            s.settimeout(0.5)
            try:
                while True:
                    buf += s.recvfrom(4096)[0]
            except socket.timeout:
                pass
            break
        now = time.time()
        if now - last > 10:
            print("   %7d bytes ..." % len(buf))
            last = now
    s.close()
    return buf.decode("ascii", "replace")


def main():
    if len(sys.argv) < 3 or len(sys.argv) > 4 or (
            len(sys.argv) == 4 and sys.argv[3] != "--kept"):
        print(__doc__)
        return 1
    ip, out = sys.argv[1], sys.argv[2]

    if len(sys.argv) == 4:
        print("asking the board for its kept capture (reliable sr) ...")
        try:
            head, rows = grab_kept_reliable(ip)
        except ReliableShotError as error:
            print(f"no verified kept capture: {error}")
            return 1
        with open(out, "wb") as f:
            f.write(png(head["w"], head["h"], rows))
        print("wrote %s (%d x %d, capture %d, x0 %016X)" %
              (out, head["w"], head["h"], head["seq"], head["x0"]))
        return 0

    print("asking the board for its screen over the air (reliable pr) ...")
    # ALL the reliable attempts come FIRST. The legacy fallback streams
    # fire-and-forget for half a minute, and running it between reliable
    # attempts poisoned them on silicon: the board was still blasting the
    # old text stream at a dead socket while the next pr command sat
    # queued behind it. Legacy is the last resort for a board that never
    # answered pr at all, not a between-tries filler.
    for attempt in range(1, 4):
        got = grab_reliable(ip)
        if got is not None:
            w, h, rows = got
            with open(out, "wb") as f:
                f.write(png(w, h, rows))
            print("wrote %s (%d x %d)" % (out, w, h))
            return 0
        print("   reliable attempt %d failed; retrying ..." % attempt)
        time.sleep(2.0)
    print("falling back to the legacy p stream (board without pr?) ...")
    text = grab(ip)
    try:
        w, h, rows = decode(text)
    except SystemExit as e:
        print("   legacy stream did not decode: %s" % e)
        print("no verified capture.")
        return 1
    with open(out, "wb") as f:
        f.write(png(w, h, rows))
    print("wrote %s (%d x %d)" % (out, w, h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
