#!/usr/bin/env python3
"""pmfshot.py - take a screenshot of the Pi 4 over the serial line.

Drives Anvil's `p` command, decodes the run-length stream it sends back,
and writes a PNG.

    python tools/pmfshot.py COM7 anvil.png

WHY THIS EXISTS AT ALL. The board has no operating system, no network
stack and no filesystem it can write to. The only channel off it is a
115200 baud serial line, and the framebuffer is 1824 x 984 x 4 bytes -
7.18 MB, or 14 MB as hex, or about twenty minutes of wire time. So the
monitor run-length encodes it first; a console screen is overwhelmingly
one background colour in long horizontal runs and collapses to a few
tens of kilobytes.

THE PNG IS WRITTEN BY HAND, with zlib from the standard library and
nothing else. Pillow is not installed here and adding a dependency to
save one screenshot would be a poor trade. A PNG is four chunks and a
CRC; it is less code than the argument for a library would be.

PIXEL ORDER IS PLAIN ARGB: the low byte of each framebuffer word is
BLUE. Confirmed 2026-08-29 against the live monitor - navy background and
orange "Forge" only come out right this way. (An earlier version decoded
the low byte as RED and so swapped red and blue in every screenshot.)
"""
import binascii
import re
import struct
import sys
import time
import zlib

import serial


def png(width, height, rgb_rows):
    """A minimal but correct PNG: signature, IHDR, IDAT, IEND."""
    def chunk(tag, data):
        c = tag + data
        return (struct.pack(">I", len(data)) + c +
                struct.pack(">I", binascii.crc32(c) & 0xFFFFFFFF))

    raw = bytearray()
    for row in rgb_rows:
        raw.append(0)          # filter type 0, None - the rows are already small
        raw.extend(row)

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            chunk(b"IEND", b""))


def capture(port, timeout_s=420):
    ser = serial.Serial(port, 115200, timeout=1)
    ser.dtr = False
    ser.rts = False

    # Settle, then make sure we are at a prompt.
    ser.write(b"\r")
    time.sleep(0.5)
    ser.reset_input_buffer()

    ser.write(b"p\r")
    buf = bytearray()
    t0 = time.time()
    last_report = t0
    while time.time() - t0 < timeout_s:
        c = ser.read(65536)
        if c:
            buf.extend(c)
            if b"END " in buf:
                # Give the trailing newline a moment, then stop.
                time.sleep(0.3)
                buf.extend(ser.read(4096))
                break
        now = time.time()
        if now - last_report > 10:
            print("   %7d bytes ..." % len(buf))
            last_report = now
    ser.close()
    return buf.decode("ascii", "replace")


def decode(text):
    m = re.search(r"^PIC ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{2})\s*$",
                  text, re.M)
    if not m:
        raise SystemExit("no PIC header in the reply - is the screen up? "
                         "(the monitor refuses p with the screen off)")
    w, h, bpp = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)
    print("   %d x %d, %d bytes per pixel" % (w, h, bpp))

    runs = re.findall(r"^([0-9A-F]{6}) ([0-9A-F]{8})\s*$", text, re.M)
    end = re.search(r"^END ([0-9A-F]{8})\s*$", text, re.M)
    if not end:
        raise SystemExit("the stream stopped before END - %d runs arrived" %
                         len(runs))
    claimed = int(end.group(1), 16)
    if claimed != len(runs):
        raise SystemExit("the board said %d runs and %d parsed - the wire "
                         "dropped something" % (claimed, len(runs)))
    print("   %d runs" % len(runs))

    rows = []
    row = bytearray()
    for cnt_s, px_s in runs:
        cnt = int(cnt_s, 16)
        px = int(px_s, 16)
        # STANDARD ARGB: the low byte of the word is BLUE. Confirmed
        # 2026-08-29 against the live HDMI monitor - the navy console
        # background DisplayRGB(0,0,40) = $FF000028 shows as navy and the
        # orange "Forge" shows as orange only when the low byte is decoded
        # as blue. An earlier note here had it as low-byte-RED and swapped
        # every screenshot's red and blue; that was wrong (the on-board
        # pixel-order handling in display.pi4 packs plain ARGB now).
        b = px & 0xFF
        g = (px >> 8) & 0xFF
        r = (px >> 16) & 0xFF
        row.extend(bytes((r, g, b)) * cnt)
        while len(row) >= w * 3:
            rows.append(bytes(row[:w * 3]))
            del row[:w * 3]
    if len(rows) != h:
        print("   note: %d rows decoded, header said %d" % (len(rows), h))
        h = len(rows)
    return w, h, rows


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    port, out = sys.argv[1], sys.argv[2]
    print("asking the board for its screen ...")
    text = capture(port)
    raw = out + ".txt"
    with open(raw, "w", encoding="ascii", errors="replace") as f:
        f.write(text)
    print("   raw stream kept at %s (%d bytes)" % (raw, len(text)))
    w, h, rows = decode(text)
    with open(out, "wb") as f:
        f.write(png(w, h, rows))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
