#!/usr/bin/env python3
"""Desk gate for the live `pic` stream on the BCM2712's RGB565 surface
(-t pi5): CmdPic -> ScrCaptureSnapshot -> ScrCapturePixel (widening) ->
the PIC run stream -> tools/pmfshot.py's decode() and png() -> PNG.

THE WIRE FORMAT DID NOT CHANGE.  Every run still carries a 32-bit
$FFRRGGBB word: the 16 bpp surface is widened per pixel on the board
(bit replication, $1F -> $FF), so tools/pmfshot.py and the `picr` host
reader take a Pi 5 stream exactly as they take a Pi 4 one.  The header's
bytes-per-pixel field says 02 - the SOURCE depth; pmfshot only prints it.

WHAT IS BUILT.  A -t pi5 driver on tools/a64/pi5_desk.py linking the shipped
text of CmdPic (screen_cmd.pi4), ScrCaptureSnapshot and ScrPresentedPixel
(screen_source.pi4), ScrWiden565/ScrCapturePixel and the rotation map
(screen_geom.pi4), BannerOverlayRefuse16 (banner_clock.pi4) and PutHexN.
The surface, the UART plumbing and the cache clean are stubbed; the UART is
a modelled PL011 whose bytes are the stream.

WHAT IS CHECKED.
  * a 96 x 5 RGB565 surface at a padded pitch (poisoned padding; every red,
    green and blue level and a mixed ramp) streams, decodes and matches an
    independent widening in all 480 pixels;
  * a 32 bpp surface on the same build still streams its words unchanged;
  * ScrPresentedPixel stores ONE 2-byte pixel on the 16 bpp surface;
  * the V3D overlays refuse 2 bytes a pixel, say so once, and count it.
Desk proof only; silicon owed.

Run:  py -3 -B tools/a64/pi5_pic16_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import re
import shutil
import struct
import sys
import tempfile
import types
import zlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pi5_desk as d                               # noqa: E402

REL_SRC = "RaspberryPi4/Board/screen_source.pi4"
REL_CMD = "RaspberryPi4/Board/screen_cmd.pi4"
REL_GEOM = "RaspberryPi4/Board/screen_geom.pi4"
REL_BAN = "RaspberryPi4/Board/banner_clock.pi4"
REL_MEM = "RaspberryPi4/Board/memmap.pi4"
REL_FMT = "Anvil/Core/format.pbi"

UART = 0x107D001000
FB = 0x0200_0000
W, H, PITCH = 96, 5, 96 * 2 + 40
POISON = 0xDEAD


def proc(text, name, where):
    m = re.search(r"^Procedure(\.\w)?\s+%s\(" % re.escape(name), text, re.M)
    if not m:
        d.die("%s no longer defines %s" % (where, name))
    e = text.find("\nEndProcedure", m.start())
    return text[m.start():e + len("\nEndProcedure")] + "\n"


def consts(text, prefix):
    return "\n".join(ln.split(";")[0].rstrip() for ln in text.split("\n")
                     if re.match(r"^%s\w*\s*=" % re.escape(prefix), ln))


def driver(ov):
    src = d.source(REL_SRC, ov).replace("\r\n", "\n")
    cmd = d.source(REL_CMD, ov).replace("\r\n", "\n")
    geom = d.source(REL_GEOM, ov).replace("\r\n", "\n")
    ban = d.source(REL_BAN, ov).replace("\r\n", "\n")
    mem = d.source(REL_MEM, ov).replace("\r\n", "\n")
    parts = [
        "; pi5_pic16_check driver - generated, never committed.",
        consts(mem, "#MON_FB_"), consts(geom, "#SCR_SRC_"),
        "Global gScreen.i", "Global gScrSrc.i", "Global gScrRot.i", "Global gScrDsiUp.i",
        "Global gBannerOverlay16Refused.i",
        "Global gSurfBase.i", "Global gSurfW.i", "Global gSurfH.i", "Global gSurfPitch.i", "Global gSurfBpp.i",
        "Global gCleanAt.i", "Global gCleanLen.i",
        "Procedure SetSurf(base.i, w.i, h.i, pitch.i, bpp.i, src.i)",
        "  gSurfBase = base : gSurfW = w : gSurfH = h : gSurfPitch = pitch : gSurfBpp = bpp : gScrSrc = src : gScreen = 1",
        "EndProcedure",
        "Procedure.i DisplayMemorySafe()\n  ProcedureReturn 1\nEndProcedure",
        "Procedure.i DisplayViewBase()\n  ProcedureReturn gSurfBase\nEndProcedure",
        "Procedure.i DisplayWidth()\n  ProcedureReturn gSurfW\nEndProcedure",
        "Procedure.i DisplayHeight()\n  ProcedureReturn gSurfH\nEndProcedure",
        "Procedure.i DisplayPitch()\n  ProcedureReturn gSurfPitch\nEndProcedure",
        "Procedure.i DisplayBytesPerPixel()\n  ProcedureReturn gSurfBpp\nEndProcedure",
        "Procedure MmuCleanRange(a.i, n.i)\n  gCleanAt = a : gCleanLen = n\nEndProcedure",
        "Procedure UartWrite(c.i)\n  PokeL($107D001000, c)\nEndProcedure",
        "Procedure str_print_at(p.i)\n  Define c.i\n  Repeat\n    c = PeekA(p)\n"
        "    If c = 0 : Break : EndIf\n    UartWrite(c)\n    p = p + 1\n  ForEver\nEndProcedure",
        "Procedure PrintNl()\n  UartWrite(10)\nEndProcedure",
        "Procedure PrintDec(v.i)\nEndProcedure",
        "Procedure.i UartMirrorOn()\n  ProcedureReturn 0\nEndProcedure",
        "Procedure UartMirror(on.i)\nEndProcedure",
        "Procedure UartDrain()\nEndProcedure",
        "Procedure UartAuxBulk(on.i)\nEndProcedure",
        "Procedure.i OutBreakCtrlC()\n  ProcedureReturn 0\nEndProcedure",
        "Procedure.i OutBroke()\n  ProcedureReturn 0\nEndProcedure",
        'XIncludeFile "%s"' % REL_FMT,
        proc(geom, "ScrSideways", REL_GEOM), proc(geom, "ScrLogicalW", REL_GEOM),
        proc(geom, "ScrLogicalH", REL_GEOM), proc(geom, "ScrMapX", REL_GEOM),
        proc(geom, "ScrMapY", REL_GEOM), proc(geom, "ScrWiden565", REL_GEOM),
        proc(geom, "ScrCapturePixel", REL_GEOM),
        proc(src, "ScrCaptureSnapshot", REL_SRC), proc(src, "ScrPresentedPixel", REL_SRC),
        proc(ban, "BannerOverlayRefuse16", REL_BAN), proc(ban, "BannerOverlayRefused16Count", REL_BAN),
        proc(cmd, "CmdPic", REL_CMD),
        "Global gate_never.i",
        "If gate_never = 1",
        "  SetSurf(0, 0, 0, 0, 0, 0) : CmdPic() : ScrPresentedPixel(0, 0, 0)",
        "  BannerOverlayRefuse16(0) : BannerOverlayRefused16Count()",
        "EndIf",
    ]
    return "\n".join(parts) + "\n"


def widen(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def value16(x, y):
    if y == 0:
        return (x % 32) << 11
    if y == 1:
        return (x % 64) << 5
    if y == 2:
        return x % 32
    if y == 3:
        return ((x * 5) % 32) << 11 | ((x * 11) % 64) << 5 | ((x * 7) % 32)
    return 0xFFFF if x % 2 else 0


def load_pmfshot():
    if "serial" not in sys.modules:
        try:
            import serial  # noqa: F401
        except ImportError:
            sys.modules["serial"] = types.ModuleType("serial")
    spec = importlib.util.spec_from_file_location("pmfshot", str(d.ROOT / "tools" / "pmfshot.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_png(blob):
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        d.die("pmfshot.png did not write a PNG")
    pos, idat, ihdr = 8, b"", None
    while pos < len(blob):
        n = struct.unpack(">I", blob[pos:pos + 4])[0]
        kind, body = blob[pos + 4:pos + 8], blob[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    w, h = ihdr[0], ihdr[1]
    if ihdr[2] != 8 or ihdr[3] != 2:
        d.die("the PNG is not 8-bit RGB")
    raw = zlib.decompress(idat)
    rows = []
    for y in range(h):
        if raw[y * (w * 3 + 1)] != 0:
            d.die("pmfshot wrote a PNG filter this gate does not decode")
        rows.append(raw[y * (w * 3 + 1) + 1:(y + 1) * (w * 3 + 1)])
    return w, h, rows


def gate(ov, work, cc):
    n = [0]

    def expect(ok, msg):
        n[0] += 1
        if not ok:
            d.die(msg)

    img, procs = d.build(cc, driver(ov), "pic16", work, ov, [REL_FMT])
    uart = bytearray()

    def model(addr, size, value):
        if addr == UART:
            if value is not None:
                uart.append(value & 0xFF)
            return 0
        if addr == UART + 0x18:
            return 0
        d.die("the pic path touched device address $%X" % addr)

    hdmi = d.const_in(d.source(REL_GEOM, ov), "#SCR_SRC_HDMI", REL_GEOM)
    pm = load_pmfshot()

    def stream(mc):
        uart.clear()
        mc.call("CmdPic", limit=20_000_000)
        text = uart.decode("ascii", "replace")
        (work / "pic.txt").write_text(text)
        if "!!" in text:
            d.die("CmdPic refused: %s" % text.strip()[:160])
        w, h, rows = pm.decode(text)
        blob = pm.png(w, h, rows)
        return text, read_png(bytes(blob))

    # ---- 16 bpp: the Pi 5 surface -----------------------------------------
    mc = d.Machine(img, procs, model)
    for y in range(H):
        row = b"".join(value16(x, y).to_bytes(2, "little") for x in range(W))
        row += POISON.to_bytes(2, "little") * ((PITCH - W * 2) // 2)
        mc.poke(FB + y * PITCH, row)
    mc.call("SetSurf", FB, W, H, PITCH, 2, hdmi)
    text, (pw, ph, prow) = stream(mc)
    expect(re.search(r"^PIC %08X %08X 02\s*$" % (W, H), text, re.M) is not None,
           "the PIC header does not describe a %dx%d 2-byte source" % (W, H))
    expect((pw, ph) == (W, H), "the PNG is %dx%d" % (pw, ph))
    bad = [(x, y, tuple(prow[y][x * 3:x * 3 + 3]), widen(value16(x, y)))
           for y in range(H) for x in range(W)
           if tuple(prow[y][x * 3:x * 3 + 3]) != widen(value16(x, y))]
    expect(not bad, "%d of %d pixels differ from the RGB565 widening; first (x,y,got,want) %s"
           % (len(bad), W * H, bad[:1]))

    # ---- 32 bpp on the same build: unchanged --------------------------------
    mc = d.Machine(img, procs, model)
    words = {}
    for y in range(3):
        row = bytearray()
        for x in range(20):
            v = 0xFF000000 | ((x * 13) & 255) << 16 | ((y * 70 + x) & 255) << 8 | ((x * 29) & 255)
            words[(x, y)] = v
            row += v.to_bytes(4, "little")
        mc.poke(FB + y * 128, bytes(row))
    mc.call("SetSurf", FB, 20, 3, 128, 4, hdmi)
    text, (pw, ph, prow) = stream(mc)
    bad = [k for k, v in words.items()
           if tuple(prow[k[1]][k[0] * 3:k[0] * 3 + 3]) != ((v >> 16) & 255, (v >> 8) & 255, v & 255)]
    expect(not bad, "a 32 bpp surface no longer streams its own words (%d wrong)" % len(bad))

    # ---- ScrPresentedPixel on the 16 bpp surface -----------------------------
    mc = d.Machine(img, procs, model)
    mc.poke(FB, b"\x11" * PITCH * 3)
    mc.call("SetSurf", FB, W, H, PITCH, 2, hdmi)
    expect(mc.call("ScrPresentedPixel", 7, 2, 0xBEEF) == 1, "ScrPresentedPixel refused")
    got = mc.peek(FB + 2 * PITCH + 7 * 2 - 2, 6)
    expect(got == b"\x11\x11\xEF\xBE\x11\x11",
           "ScrPresentedPixel on RGB565 wrote %s around pixel (7,2), want one 2-byte store"
           % got.hex())

    # ---- the V3D overlay refusal --------------------------------------------
    mc = d.Machine(img, procs, model)
    uart.clear()
    expect(mc.call("BannerOverlayRefuse16", 4) == 0, "the overlay refused a 4-byte surface")
    expect(mc.call("BannerOverlayRefuse16", 2) == 1 and mc.call("BannerOverlayRefuse16", 2) == 1,
           "the V3D overlay did not refuse a 2-byte surface")
    said = uart.decode("ascii", "replace")
    expect(said.count("!!") == 1 and mc.call("BannerOverlayRefused16Count") == 2,
           "the refusal was not said once and counted twice: %r" % said[:120])
    return n[0]


MUTATIONS = [
    (REL_GEOM, "packing: red and blue fields swapped", "  r5 = (v >> 11) & $1F\n", "  r5 = v & $1F\n"),
    (REL_GEOM, "packing: green read as 5 bits", "  g6 = (v >> 5) & $3F\n", "  g6 = (v >> 5) & $1F\n"),
    (REL_GEOM, "stride: 32 bpp step on the 16 bpp surface",
     "    ProcedureReturn ScrWiden565(PeekW(fb + py * pitch + px * 2) & $FFFF)\n",
     "    ProcedureReturn ScrWiden565(PeekW(fb + py * pitch + px * 4) & $FFFF)\n"),
    (REL_GEOM, "pitch ignored (width * 2)",
     "    ProcedureReturn ScrWiden565(PeekW(fb + py * pitch + px * 2) & $FFFF)\n",
     "    ProcedureReturn ScrWiden565(PeekW(fb + py * panelW * 2 + px * 2) & $FFFF)\n"),
    (REL_GEOM, "no widening (plain shift)",
     "  ProcedureReturn (($FF << 24) | (((r5 << 3) | (r5 >> 2)) << 16)) | ((((g6 << 2) | (g6 >> 4)) << 8) | ((b5 << 3) | (b5 >> 2)))\n",
     "  ProcedureReturn (($FF << 24) | ((r5 << 3) << 16)) | (((g6 << 2) << 8) | (b5 << 3))\n"),
    (REL_GEOM, "16 bpp read as a 32-bit word", "  If fb = DisplayViewBase() And DisplayBytesPerPixel() = 2\n",
     "  If fb = DisplayViewBase() And DisplayBytesPerPixel() = 9\n"),
    (REL_SRC, "snapshot still refuses 2 bytes a pixel",
     "  If fb = 0 Or pw < 1 Or ph < 1 Or p < (pw * d) Or (d <> 4 And d <> 2)\n",
     "  If fb = 0 Or pw < 1 Or ph < 1 Or p < (pw * d) Or (d <> 4 And d <> 99)\n"),
    (REL_SRC, "presented pixel stores 32 bits on RGB565", "    PokeW(at, colour)\n", "    PokeL(at, colour)\n"),
    (REL_BAN, "overlay refusal disarmed", "  If bpp = 4\n    ProcedureReturn 0\n", "  If bpp <> 0\n    ProcedureReturn 0\n"),
    (REL_BAN, "overlay refusal silent", "  If gBannerOverlay16Refused = 0\n    PrintN(",
     "  If gBannerOverlay16Refused = -1\n    PrintN("),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-pic16-"))
    try:
        try:
            n = gate({}, top / "gate", cc)
        except d.GateFail as e:
            print("pi5_pic16_check: FAIL - %s" % e)
            return 1
        print("pi5_pic16_check: PASS - %d checks, %dx%d RGB565 at pitch %d streamed by CmdPic and "
              "decoded by tools/pmfshot.py (desk only; silicon owed)" % (n, W, H, PITCH))
        if a.mutate:
            left = d.run_mutations("pi5_pic16_check", MUTATIONS,
                                   lambda ov, w: gate(ov, w, cc), top / "mut")
            return 1 if left else 0
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
