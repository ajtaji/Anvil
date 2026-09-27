#!/usr/bin/env python3
"""Desk gate for the payload console at 16 bpp on the BCM2712 (-t pi5).

The Pi 5 firmware grants a 1920 x 1080 surface with pitch 3840: two bytes a
pixel, RGB565 (Lib/display.pi4 takes the size from the pitch; vault
HARDWARE-BRINGUP.md, silicon 2026-09-26).  The HwCon* seam's two drawing
paths - HwConRect (RaspberryPi4/Board/hw_con.pi4) and HwConText, which is
DrawSmoothText (RaspberryPi4/Board/display.pi4) - must write that surface.

WHAT IS BUILT.  A -t pi5 driver on tools/a64/pi5_desk.py that links the
SHIPPED TEXT of: DisplayRGB (Lib/display.pi4, the surface's packer),
HwConDamage/HwConRect/HwConText (hw_con.pi4), FontSelect/SmoothTextWidth/
DrawSmoothText and their globals (Board/display.pi4), and the real fonts
(RaspberryPi4/Monitor/anvil_fonts.pi4).  The surface itself - base, size,
pitch, bytes a pixel - is the one thing stubbed: it is what the mailbox
would have handed Lib/display.pi4, and the gate sets it per run.

WHAT IS CHECKED, WITH AN INDEPENDENT RESTATEMENT.
  * RGB565 packing: R 15:11, G 10:5, B 4:0, top bits of each channel;
    little-endian halfwords at base + y*pitch + x*2.
  * Opaque and translucent rectangles, on the real 3840-byte pitch AND on a
    padded pitch (pitch > width*2), so a stride computed from the width is
    caught; nothing outside the rectangle moves.
  * Text: the same string rendered at 32 bpp (the path the Pi 4 has run
    on silicon) and at 16 bpp lands on the SAME pixel positions, and every
    16 bpp pixel is the 565 packing of the 32 bpp one.
Desk proof only; silicon owed.

Run:  py -3 -B tools/a64/pi5_console16_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pi5_desk as d                               # noqa: E402

REL_LIB = "RaspberryPi4/Lib/display.pi4"
REL_CON = "RaspberryPi4/Board/hw_con.pi4"
REL_DSP = "RaspberryPi4/Board/display.pi4"
REL_FONTS = "RaspberryPi4/Monitor/anvil_fonts.pi4"

# The Pi 5 surface (vault HARDWARE-BRINGUP.md: 1920 wide, pitch 3840).
PI5_W, PI5_H, PI5_PITCH = 1920, 1080, 3840
FB = 0x0100_0000          # where the model puts the surface in RAM
SENTINEL = 0xA5


def proc(text: str, name: str, where: str) -> str:
    m = re.search(r"^Procedure(\.\w)?\s+%s\(" % re.escape(name), text, re.M)
    if not m:
        d.die("%s no longer defines %s" % (where, name))
    e = text.find("\nEndProcedure", m.start())
    return text[m.start():e + len("\nEndProcedure")] + "\n"


def driver(ov: dict) -> str:
    lib = d.source(REL_LIB, ov).replace("\r\n", "\n")
    con = d.source(REL_CON, ov).replace("\r\n", "\n")
    dsp = d.source(REL_DSP, ov).replace("\r\n", "\n")
    parts = [
        "; pi5_console16_check driver - generated, never committed.",
        "#HW_TIER_CPU = 3",
        "Global dsp_bpp.i", "Global dsp_swap.i",
        "Global gSurfBase.i", "Global gSurfW.i", "Global gSurfH.i", "Global gSurfPitch.i",
        "Procedure SetSurf(base.i, w.i, h.i, pitch.i, bpp.i)",
        "  gSurfBase = base : gSurfW = w : gSurfH = h : gSurfPitch = pitch : dsp_bpp = bpp",
        "EndProcedure",
        "Procedure.i DisplayReady()\n  ProcedureReturn 1\nEndProcedure",
        "Procedure.i DisplayBase()\n  ProcedureReturn gSurfBase\nEndProcedure",
        "Procedure.i DisplayWidth()\n  ProcedureReturn gSurfW\nEndProcedure",
        "Procedure.i DisplayHeight()\n  ProcedureReturn gSurfH\nEndProcedure",
        "Procedure.i DisplayPitch()\n  ProcedureReturn gSurfPitch\nEndProcedure",
        "Procedure.i DisplayBytesPerPixel()\n  ProcedureReturn dsp_bpp\nEndProcedure",
        proc(lib, "DisplayRGB", REL_LIB),
        'XIncludeFile "%s"' % REL_FONTS,
        "Global gFntMeta.i", "Global gFntPix.i", "Global gFntFirst.i", "Global gFntCount.i",
        proc(dsp, "FontSelect", REL_DSP),
        proc(dsp, "SmoothTextWidth", REL_DSP),
        proc(dsp, "DrawSmoothText", REL_DSP),
        "Global hwConDmg.i", "Global hwConDmgY0.i", "Global hwConDmgY1.i",
        proc(con, "HwConDamage", REL_CON),
        proc(con, "HwConTextHeight", REL_CON),
        proc(con, "HwConRect", REL_CON),
        proc(con, "HwConText", REL_CON),
        "Global gate_never.i",
        "If gate_never = 1",
        '  SetSurf(0, 0, 0, 0, 0) : HwConRect(0, 0, 0, 0, 0) : HwConText(0, 0, 0, 0, 0)',
        "EndIf",
    ]
    return "\n".join(parts) + "\n"


def pack565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def unpack565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def blend(a, s, dch):
    return (a * s + (255 - a) * dch + 127) // 255


class Surface:
    def __init__(self, mc, w, h, pitch, bpp):
        self.mc, self.w, self.h, self.pitch, self.bpp = mc, w, h, pitch, bpp
        mc.call("SetSurf", FB, w, h, pitch, bpp)

    def addr(self, x, y):
        return FB + y * self.pitch + x * self.bpp

    def get(self, x, y):
        return int.from_bytes(self.mc.peek(self.addr(x, y), self.bpp), "little")

    def put(self, x, y, v):
        self.mc.poke(self.addr(x, y), v.to_bytes(self.bpp, "little"))

    def fill_rows(self, y0, y1, byte):
        """Every byte of rows y0..y1, INCLUDING the pitch padding."""
        for y in range(y0, y1 + 1):
            self.mc.poke(FB + y * self.pitch, bytes([byte]) * self.pitch)

    def dump(self, y0, y1):
        return {(y, i): b for y in range(y0, y1 + 1)
                for i, b in enumerate(self.mc.peek(FB + y * self.pitch, self.pitch))}


def no_device(addr, size, value):
    d.die("the console touched device address $%X; it should write RAM only" % addr)


def gate(ov: dict, work: pathlib.Path, cc: str) -> int:
    n = [0]

    def expect(ok, msg):
        n[0] += 1
        if not ok:
            d.die(msg)

    img, procs = d.build(cc, driver(ov), "con16", work, ov, [REL_FONTS])

    def fresh():
        return d.Machine(img, procs, no_device)

    # ---- opaque rectangle on the Pi 5 surface -----------------------------
    for (pw, ph, pitch, label) in ((PI5_W, PI5_H, PI5_PITCH, "pitch 3840"),
                                   (300, 64, 1024, "padded pitch 1024")):
        mc = fresh()
        s = Surface(mc, pw, ph, pitch, 2)
        x, y, w, h = 37, 11, 23, 5
        s.fill_rows(y - 2, y + h + 1, SENTINEL)
        before = s.dump(y - 2, y + h + 1)
        rgb = (0x12, 0xC4, 0xF9)
        mc.call("HwConRect", x, y, w, h, 0xFF000000 | (rgb[0] << 16) | (rgb[1] << 8) | rgb[2])
        want = pack565(*rgb)
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                got = s.get(xx, yy)
                expect(got == want, "%s: opaque pixel (%d,%d) is $%04X, RGB565 of #%02X%02X%02X "
                       "is $%04X" % (label, xx, yy, got, *rgb, want))
        after = s.dump(y - 2, y + h + 1)
        inside = {(yy, i) for yy in range(y, y + h) for i in range(x * 2, (x + w) * 2)}
        moved = [k for k in after if k not in inside and after[k] != before[k]]
        expect(not moved, "%s: %d bytes outside the rectangle changed, first at row %d byte %d"
               % (label, len(moved), *(moved[0] if moved else (0, 0))))

    # ---- translucent rectangles over every 565 level ---------------------
    mc = fresh()
    s = Surface(mc, PI5_W, PI5_H, PI5_PITCH, 2)
    for yy, a, src in ((3, 0x60, (0xF0, 0x10, 0x88)), (5, 0xC0, (0x08, 0xE7, 0x31))):
        bgs = {}
        for xx in range(100, 164):
            k = xx - 100
            bgs[xx] = (k % 32) << 11 | ((k * 7) % 64) << 5 | ((k * 3) % 32)
            s.put(xx, yy, bgs[xx])
        mc.call("HwConRect", 100, yy, 64, 1, (a << 24) | (src[0] << 16) | (src[1] << 8) | src[2])
        for xx in range(100, 164):
            dr, dg, db = unpack565(bgs[xx])
            want = pack565(blend(a, src[0], dr), blend(a, src[1], dg), blend(a, src[2], db))
            got = s.get(xx, yy)
            expect(got == want, "alpha $%02X: #%02X%02X%02X over $%04X gave $%04X, want $%04X"
                   % (a, *src, bgs[xx], got, want))
    # ---- text: 32 bpp (the Pi 4's proven path) against 16 bpp ------------
    text = b"Anvil 5 gy|"
    fg, bgc = 0xE0C040, 0x102030

    def render(bpp, pitch):
        mc = fresh()
        s = Surface(mc, 400, 90, pitch, bpp)
        buf = 0x2000000
        mc.poke(buf, text + b"\0")
        s.fill_rows(0, 89, 0)
        w = mc.call("HwConText", 13, 60, buf, fg, bgc)
        pix = {}
        for yy in range(90):
            row = mc.peek(FB + yy * pitch, pitch)
            for xx in range(400):
                v = int.from_bytes(row[xx * bpp:(xx + 1) * bpp], "little")
                if v:
                    pix[(xx, yy)] = v
            pad = row[400 * bpp:]
            if any(pad):
                d.die("bpp %d: text wrote into the pitch padding of row %d" % (bpp, yy))
        return w, pix

    w32, p32 = render(4, 400 * 4 + 64)
    w16, p16 = render(2, 400 * 2 + 96)
    expect(w32 > 0 and w16 == w32, "text width: %d at 16 bpp, %d at 32 bpp" % (w16, w32))
    expect(len(p32) > 200, "the 32 bpp reference drew only %d pixels" % len(p32))
    expect(set(p16) == set(p32), "text: %d pixels at 16 bpp vs %d at 32 bpp; first "
           "difference at %s" % (len(p16), len(p32), sorted(set(p16) ^ set(p32))[:1]))
    bad = [(k, p16[k], p32[k]) for k in p32 if k in p16 and
           p16[k] != pack565((p32[k] >> 16) & 255, (p32[k] >> 8) & 255, p32[k] & 255)]
    expect(not bad, "text: %d pixels are not the 565 of the 32 bpp pixel; first %s"
           % (len(bad), bad[:1]))
    xs = [k[0] for k in p16]
    expect(min(xs) >= 13 and max(xs) < 13 + w16 + 8, "text: glyphs outside x %d..%d"
           % (13, 13 + w16))
    return n[0]


MUTATIONS = [
    (REL_CON, "wrong packing: green in 5 bits", "  px16 = DisplayRGB(sr, sg, sb)\n",
     "  px16 = ((sr >> 3) << 11) | ((sg >> 3) << 5) | (sb >> 3)\n"),
    (REL_LIB, "wrong packing: red and blue swapped in 565",
     "ProcedureReturn (((rr >> 3) << 11) | ((gg >> 2) << 5)) | (bb >> 3)",
     "ProcedureReturn (((bb >> 3) << 11) | ((gg >> 2) << 5)) | (rr >> 3)"),
    (REL_CON, "32 bpp column stride on a 16 bpp surface", "      p = p + bpp\n", "      p = p + 4\n"),
    (REL_CON, "32 bpp x offset on a 16 bpp surface", "    p = base + (y + row) * pitch + x * bpp\n",
     "    p = base + (y + row) * pitch + x * 4\n"),
    (REL_CON, "pitch ignored (width * bpp)", "    p = base + (y + row) * pitch + x * bpp\n",
     "    p = base + (y + row) * DisplayWidth() * bpp + x * bpp\n"),
    (REL_DSP, "text: 32 bpp stride on a 16 bpp surface",
     "                  PokeW(fbBase + gy * pitch + gx * 2, DisplayRGB(outR, outG, outB))\n",
     "                  PokeW(fbBase + gy * pitch + gx * 4, DisplayRGB(outR, outG, outB))\n"),
    (REL_DSP, "text: pitch ignored",
     "                  PokeW(fbBase + gy * pitch + gx * 2, DisplayRGB(outR, outG, outB))\n",
     "                  PokeW(fbBase + gy * DisplayWidth() * 2 + gx * 2, DisplayRGB(outR, outG, outB))\n"),
    (REL_DSP, "text: 16 bpp still refused", "  If bpp <> 2 And bpp <> 4\n    ProcedureReturn 0\n",
     "  If bpp <> 4\n    ProcedureReturn 0\n"),
    (REL_CON, "translucent read-back not widened", "          dr = (dr << 3) | (dr >> 2)\n", "          dr = dr << 3\n"),
    (REL_CON, "a 32-bit store on a 16 bpp surface", "          PokeW(p, px16)\n", "          PokeL(p, px16)\n"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-con16-"))
    try:
        try:
            n = gate({}, top / "gate", cc)
        except d.GateFail as e:
            print("pi5_console16_check: FAIL - %s" % e)
            return 1
        print("pi5_console16_check: PASS - %d checks (desk only; silicon owed)" % n)
        if a.mutate:
            left = d.run_mutations("pi5_console16_check", MUTATIONS,
                                   lambda ov, w: gate(ov, w, cc), top / "mut")
            return 1 if left else 0
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
