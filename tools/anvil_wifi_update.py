#!/usr/bin/env python3
"""anvil_wifi_update.py - replace Anvil with a new build, over the network.

    python tools/anvil_wifi_update.py <board-ip> [image]
    python tools/anvil_wifi_update.py --receive-only <board-ip> [image]

THE NAME IS HISTORICAL. This rides Anvil's network console, and since
2026-09-07 that console is armed on EVERY interface the board holds an
address on - the Ethernet cable AND the Wi-Fi radio at once. Point it at
whichever of the board's addresses you can reach. The file keeps its name
so that every note and script that already says anvil_wifi_update.py
still works.

The serial twin, tools/anvil_update.py, sends the image down the FTDI
cable. This sends it over the network instead, so the serial cable is
free for something else and a board with no serial attached can still be
reflashed. The steps are the same three the serial path uses - receive
into RAM, save that RAM to the boot file, reset into it - only the
receive rides UDP:

    wb 400000 <len> <crc>          # board: rdy
    <the image, as offset-tagged datagrams, each acked>
    save KERNEL8.IMG 400000 <len>  # board writes RAM -> file
    reset

The optional --receive-only mode uses the same `wb` protocol but stops
after the board's CRC verdict. It is limited to 2 MiB, must fit inside a
payload window printed by `map`, and never saves or resets the board.

STOP-AND-WAIT. Each datagram is [4-byte LE offset][data]; the board
echoes the offset once it has stored it, and only then is the next one
sent. That is what keeps the host from outrunning the board's SDIO
receive and losing frames. A datagram whose ack does not come back is
simply resent - the offset makes the rewrite land in the same place.

The whole-image CRC is the backstop: the board reads the bytes back out
of memory and checks them before it ever reports success, so a corrupt
transfer is caught in RAM, before save touches the file it boots from.
"""
import socket
import struct
import os
import sys
import time
import zlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# THIS TOOL PRINTS WHAT THE BOARD SAID, AND IT DOES IT WHILE REPLACING
# THE IMAGE THE BOARD BOOTS - the seam where dying costs the most.
# See console_out.py.
from console_out import relay_safe_output   # noqa: E402

relay_safe_output()

from anvil import read_map, stage_help                  # noqa: E402

PORT = 5555
SLOT_NAME = "KERNEL8.IMG"
PI3_RECEIVE_MAX = 0x00200000

# STAGE IS ASKED FOR, NOT CARRIED - 2026-09-08. It was 0x400000 here and
# in three other tools. The monitor's extent is now the size of its own
# image, so the first free address above it moves with the monitor and a
# constant here would eventually aim an image at the running monitor.
# stage_from_map is the one reader of `map`'s answer in this tree; see
# WHERE THE BOARD WANTS A FILE PUT in tools/anvil.py. It is imported
# rather than re-implemented even though this tool speaks UDP and that
# module speaks serial: the PARSE is transport-free on purpose, which is
# why it is a function of the text and not a method.
CHUNK_DATA = 1024                # image bytes per datagram (+4 header)
END = 0xFFFFFFFF                 # offset sentinel: no more chunks
RESULT_OK = 0xF0F0F0F0           # board -> host: received and verified
RESULT_BAD = 0xE1E1E1E1          # board -> host: received but CRC failed


def recv_text(s, want, timeout):
    """Collect UDP text until `want` appears or `timeout` elapses."""
    s.settimeout(0.3)
    buf = b""
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, _ = s.recvfrom(4096)
        except socket.timeout:
            continue
        buf += data
        if want.encode() in buf:
            return buf.decode("utf-8", "replace")
    return buf.decode("utf-8", "replace")


def drain(s):
    """Throw away anything already queued so a stale reply is not read
    as the next step's."""
    s.settimeout(0)
    try:
        while True:
            s.recvfrom(4096)
    except (socket.timeout, BlockingIOError, OSError):
        pass


def send_image(s, ip, img, stage):
    crc = zlib.crc32(img) & 0xFFFFFFFF
    n = len(img)

    drain(s)
    s.sendto(("wb %X %X %08X\r" % (stage, n, crc)).encode(), (ip, PORT))
    reply = recv_text(s, "rdy", 4.0)
    if "rdy" not in reply:
        print("the board did not answer 'rdy' to wb:")
        print(" ", reply.strip() or "(nothing)")
        return False
    print("board ready; sending %d bytes in %d-byte datagrams ..."
          % (n, CHUNK_DATA))

    s.settimeout(0.5)
    off = 0
    t0 = time.monotonic()
    while off < n:
        chunk = img[off:off + CHUNK_DATA]
        pkt = struct.pack("<I", off) + chunk
        acked = False
        for _ in range(8):                       # resend until acked
            s.sendto(pkt, (ip, PORT))
            try:
                data, _ = s.recvfrom(64)
            except socket.timeout:
                continue
            if len(data) == 4 and struct.unpack("<I", data)[0] == off:
                acked = True
                break
        if not acked:
            print("\nno ack for the datagram at offset %d after 8 tries - "
                  "the link went quiet." % off)
            return False
        off += len(chunk)
        if (off // CHUNK_DATA) % 64 == 0 or off >= n:
            pct = 100 * off // n
            sys.stdout.write("\r  %d/%d bytes (%d%%)" % (off, n, pct))
            sys.stdout.flush()
    print()

    # End marker, then the verdict - a 4-byte code, not text. The board
    # reads the whole image back out of memory to check the CRC before it
    # answers, which is a few seconds with caches off, so wait well past
    # that. Resend the marker on the way in case that datagram was the one
    # that got lost: while the board is still polling for it, it will abort
    # if it hears nothing for a few seconds, so a periodic nudge keeps the
    # window open until the verdict comes.
    s.settimeout(1.0)
    deadline = time.time() + 45.0
    last_end = 0.0
    while time.time() < deadline:
        now = time.time()
        if now - last_end > 1.5:
            s.sendto(struct.pack("<I", END), (ip, PORT))
            last_end = now
        try:
            data, _ = s.recvfrom(64)
        except socket.timeout:
            continue
        if len(data) == 4:
            code = struct.unpack("<I", data)[0]
            if code == RESULT_OK:
                elapsed = max(time.monotonic() - t0, 0.000001)
                rate_mbps = (n * 8.0) / elapsed / 1000000.0
                print("received and CRC-verified on the board in %.1f s; "
                      "%.2f Mbit/s payload rate" % (elapsed, rate_mbps))
                return True
            if code == RESULT_BAD:
                print("the board received it but the CRC disagreed - "
                      "nothing was written. Try again.")
                return False
            # anything else 4 bytes long is a stale chunk ack; keep waiting
    print("no verdict from the board after the end marker.")
    return False


def cmd(s, ip, line, want, timeout):
    drain(s)
    s.sendto((line + "\r").encode(), (ip, PORT))
    return recv_text(s, want, timeout)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Transfer an Anvil image over the existing Wi-Fi console protocol.")
    parser.add_argument("board_ip", help="board address on an already-connected network")
    parser.add_argument("image", nargs="?", help="image/file to transfer")
    parser.add_argument("--receive-only", action="store_true",
                        help="use wb and verify CRC in RAM, then stop without save or reset")
    parser.add_argument("--stage", type=lambda value: int(value, 16),
                        help="receive address in hex (default: board's map stage address)")
    parser.add_argument("--avoid", action="append", default=[], metavar="LO:HI",
                        help="inclusive hex address range occupied by a running diagnostic payload; repeatable")
    args = parser.parse_args(argv)
    if (args.stage is not None or args.avoid) and not args.receive_only:
        parser.error("--stage and --avoid are only valid with --receive-only")
    ip = args.board_ip
    if args.image:
        src = args.image
    elif args.receive_only:
        src = os.path.join(REPO, "build", "pi3", "kernel8.img")
    else:
        src = os.path.join(REPO, "build", "pi4", "anvil.img")
    img = open(src, "rb").read()
    print("%s: %d bytes" % (src, len(img)))

    if args.receive_only:
        # This mode is intentionally restricted to the verified Pi3 low
        # payload window.  It only exercises the existing `wb` receiver;
        # the board still independently checks InPayload/HitsMonitor.
        if not img or len(img) > PI3_RECEIVE_MAX:
            print("receive-only accepts a non-empty file of at most 2 MiB")
            return 1

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 0))
    try:
        # WHERE TO PUT IT, FROM THE BOARD, BEFORE A BYTE MOVES. A
        # monitor that will not answer is a run that must not start:
        # sending two megabytes and then finding there is nowhere to put
        # them is the same failure with a longer wait in front of it.
        map_text = cmd(s, ip, "map", "ok", 8.0)
        board_map = read_map(map_text)
        if board_map is None:
            print(stage_help("the image"))
            return 1
        stage = board_map.stage if args.stage is None else args.stage
        if args.stage is None:
            print("staging at %08X, which is where this board said to put it" % stage)
        else:
            print("staging at the caller-selected address %08X" % stage)

        if args.receive_only:
            end = stage + len(img) - 1
            bad_map_window = any(lo < 0 or hi < lo or hi > 0xFFFFFFFFFFFFFFFF
                                 for lo, hi in board_map.payload_windows)
            if (stage < 0 or end < stage or end > 0xFFFFFFFFFFFFFFFF or
                    bad_map_window or not any(stage >= lo and end <= hi
                                              for lo, hi in board_map.payload_windows)):
                print("receive-only range is not wholly inside a payload window in the board's map; refusing")
                return 1
            for raw in args.avoid:
                try:
                    left, right = raw.split(":", 1)
                    lo, hi = int(left, 16), int(right, 16)
                except (ValueError, TypeError):
                    print("--avoid ranges must be inclusive hexadecimal LO:HI")
                    return 1
                if lo < 0 or hi < lo:
                    print("--avoid range is invalid; refusing")
                    return 1
                if stage <= hi and end >= lo:
                    print("receive-only range overlaps caller-declared occupied memory; refusing")
                    return 1

        if not send_image(s, ip, img, stage):
            return 1

        if args.receive_only:
            print("receive-only complete: board CRC-verified the bytes in RAM; no save or reset was sent")
            return 0

        # A resent end-marker or two may still be sitting in the board's
        # console input, unread, while it finished the CRC. Give it a moment
        # to take them in, then a bare Enter dispatches them as one harmless
        # garbage line and clears the buffer, so the save line lands clean.
        time.sleep(0.6)
        s.sendto(b"\r", (ip, PORT))
        time.sleep(0.4)
        drain(s)

        out = cmd(s, ip, "save %s %X %X" % (SLOT_NAME, stage, len(img)),
                  "written.", 90.0)
        print(out.strip())
        if "written." not in out:
            print("SAVE DID NOT COMPLETE - not resetting. The file may be part")
            print("old and part new; write it again before the board is reset.")
            return 1

        print("\nresetting into the new build ...")
        s.sendto(b"reset\r", (ip, PORT))
        print(recv_text(s, "\x00", 3.0).strip())
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
