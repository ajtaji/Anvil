#!/usr/bin/env python3
"""gen_anvil_fonts.py - anti-aliased fonts for Anvil's banner, baked on
the host into coverage tables the monitor blends onto the screen.

    python tools/gen_anvil_fonts.py [preview.png]

Anvil's console font is a single 8x16 one-bit bitmap; scaled 3x for the
banner title it is blocky. This bakes three smooth faces (DejaVu, freely
embeddable) into RaspberryPi4/Monitor/anvil_fonts.pi4 as per-glyph
coverage maps, which DrawSmoothText blends from the ink colour to the
background so the edges are anti-aliased.

FOUR BIT COVERAGE, PACKED TWO PIXELS TO A BYTE. Sixteen levels is plenty
for text and halves what full ASCII of three 48px faces would cost. The
maps are read a byte at a time (PeekA) - never a wider load - because
with the MMU off all memory is Device and an unaligned .l read faults;
the metrics records are byte fields for the same reason.

METRICS PER GLYPH, 8 bytes: advance, width, height, dx, dy (dx/dy are
signed: pen-x to ink-left, and baseline to ink-top, negative above), then
a 24-bit little-endian offset into the coverage blob.
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# The DejaVu faces are read from the system font directory. Set
# ANVIL_FONT_DIR to use another one; the Windows directory is the default.
FDIR = os.environ.get("ANVIL_FONT_DIR") or os.path.join(os.environ.get("SystemRoot", "C:/Windows"), "Fonts")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "RaspberryPi4", "Monitor", "anvil_fonts.pi4")
SIZE = 48
PAD = 6

# id, file, pixel size. Order is the font id the monitor
# uses. The fourth face is the same sans at a size that fits inside a touch
# keyboard key: at 48px a key would have to be over 60 pixels tall before
# the label had room, and the bitmap font at integer magnification - which
# is what the keys drew with until 2026-09-11 - is blocky at anything above
# 1x. Thirty pixels clears the descenders in a 40-pixel key.
FONTS = [
    ("sans",  "DejaVuSans-Bold.ttf", 48),           # 0 - the banner title
    ("serif", "DejaVuSerif-Bold.ttf", 48),           # 1
    ("cond",  "DejaVuSansCondensed-Bold.ttf", 48),   # 2
    ("keys",  "DejaVuSans-Bold.ttf", 30),            # 3 - touch keyboard labels
]


def build_font(path, size=SIZE):
    font = ImageFont.truetype(path, size)
    ascent, descent = font.getmetrics()
    lineh = ascent + descent
    canvasH = lineh + 2 * PAD
    glyphs = []          # (advance,w,h,dx,dy,coverage-bytes-8bit,w,h)
    for cp in range(32, 127):
        ch = chr(cp)
        adv = round(font.getlength(ch))
        canvasW = adv + 2 * PAD + 8
        img = Image.new("L", (canvasW, canvasH), 0)
        ImageDraw.Draw(img).text((PAD, PAD), ch, fill=255, font=font)
        bbox = img.getbbox()
        if bbox is None:
            glyphs.append((adv, 0, 0, 0, 0, b""))
            continue
        l, t, r, b = bbox
        crop = img.crop(bbox)
        dx = l - PAD
        dy = t - (PAD + ascent)          # baseline is PAD+ascent down the canvas
        glyphs.append((adv, r - l, b - t, dx, dy, crop.tobytes()))
    return lineh, ascent, glyphs


def pack4(cov8, w, h):
    """8-bit coverage -> 4-bit, two pixels per byte, row major."""
    out = bytearray()
    for y in range(h):
        x = 0
        while x < w:
            hi = cov8[y * w + x] >> 4
            lo = (cov8[y * w + x + 1] >> 4) if x + 1 < w else 0
            out.append((hi << 4) | lo)
            x += 2
    return bytes(out)


def emit_font(name, lineh, ascent, glyphs):
    meta = bytearray()
    blob = bytearray()
    for (adv, w, h, dx, dy, cov8) in glyphs:
        off = len(blob)
        if w and h:
            blob += pack4(cov8, w, h)
        meta += bytes([adv & 0xFF, w & 0xFF, h & 0xFF, dx & 0xFF, dy & 0xFF,
                       off & 0xFF, (off >> 8) & 0xFF, (off >> 16) & 0xFF])

    def rows(data, per=32):
        for i in range(0, len(data), per):
            yield "  Data.b " + ",".join("$%02X" % b for b in data[i:i + per])

    L = []
    a = L.append
    cap = name.capitalize()
    a("#FONT_%s_FIRST = 32" % name)
    a("#FONT_%s_COUNT = 95" % name)
    a("#FONT_%s_LINEH = %d" % (name, lineh))
    a("#FONT_%s_ASC   = %d" % (name, ascent))
    a("DataSection")
    a("font%sMeta:" % cap)
    L.extend(rows(meta))
    a("font%sPix:" % cap)
    if blob:
        L.extend(rows(blob))
    else:
        a("  Data.b $00")
    a("EndDataSection")
    a("")
    return "\n".join(L), len(meta), len(blob)


def main():
    out = []
    a = out.append
    a("; ======================================================================")
    a(";  ANVIL SMOOTH FONTS - anti-aliased, baked by tools/gen_anvil_fonts.py.")
    a(";")
    a(";  Do not hand-edit. DejaVu faces (freely embeddable): three at %dpx" % SIZE)
    a(";  for the banner and one at %dpx for the touch keyboard's key labels," % FONTS[3][2])
    a(";  full printable ASCII, 4-bit coverage packed two pixels to a byte,")
    a(";  read a byte at a time by DrawSmoothText (unaligned .l faults with the")
    a(";  MMU off). Per-glyph metrics are 8 bytes: adv,w,h,dx,dy,off24.")
    a("; ======================================================================")
    total = 0
    for name, fn, size in FONTS:
        lineh, ascent, glyphs = build_font(os.path.join(FDIR, fn), size)
        text, mlen, blen = emit_font(name, lineh, ascent, glyphs)
        out.append(text)
        total += mlen + blen
        print("  %-6s %-28s lineh=%d  %d bytes" % (name, fn, lineh, mlen + blen))
    with open(OUT, "w", newline="\n") as f:
        f.write("\n".join(out))
    print("%s: %d bytes of font data" % (OUT, total))

    # ---- round-trip self-check: rebuild a string from the baked 4-bit maps
    if len(sys.argv) > 1:
        lineh, ascent, glyphs = build_font(os.path.join(FDIR, FONTS[0][1]), FONTS[0][2])
        s = "PureMetal Forge 0123 gjpqy!"
        W = 900
        img = Image.new("RGB", (W, lineh + 20), (0, 0, 40))
        px = img.load()
        penx = 10
        baseline = 10 + ascent
        for ch in s:
            adv, w, h, dx, dy, cov8 = glyphs[ord(ch) - 32]
            packed = pack4(cov8, w, h)
            bpr = (w + 1) // 2
            for yy in range(h):
                for xx in range(w):
                    byte = packed[yy * bpr + (xx >> 1)]
                    nib = (byte >> 4) if (xx & 1) == 0 else (byte & 0xF)
                    c = nib * 17
                    if c:
                        X = penx + dx + xx
                        Y = baseline + dy + yy
                        if 0 <= X < W and 0 <= Y < img.height:
                            r0, g0, b0 = px[X, Y]
                            px[X, Y] = (r0 + (226 - r0) * c // 255,
                                        g0 + (232 - g0) * c // 255,
                                        b0 + (240 - b0) * c // 255)
            penx += adv
        img.save(sys.argv[1])
        print("round-trip preview: %s" % sys.argv[1])


if __name__ == "__main__":
    main()
