#!/usr/bin/env python3
"""Desk gate for the Raspberry Pi 5 screen capture of an RGB565 surface
(-t pi5): `shot now` / HwConCapture -> ScrCaptureToArea -> `shot`
(ShotDump) -> tools/pmfshot.py -> PNG, end to end.

WHAT IS BUILT.  A -t pi5 driver on tools/a64/pi5_desk.py linking the
SHIPPED TEXT of ScrCaptureToArea, ScrCaptureSnapshot (screen_source.pi4),
ShotDump, ScrShotValid/ScrShotField/ScrShotPixels (screen_cmd.pi4 and
screen_source.pi4), ScrCapturePixel and the rotation map (screen_geom.pi4),
the #MON_SHOT_* layout (Board/memmap.pi4) and PutHexN (Anvil/Core/
format.pbi).  The surface (Lib/display.pi4's answers), the sequence
counter and the UART plumbing are stubbed; the UART is a modelled PL011
whose bytes are the `shot` stream.

WHAT IS CHECKED.  A known 16 bpp surface - every RGB565 red, green and blue
level, and a padded pitch (pitch > width * 2) whose padding holds poison -
is captured; the stream is decoded by tools/pmfshot.py's own decode() and
written to a PNG with its own png(), and the gate inflates that PNG and
compares every pixel with an independent RGB565 -> RGB888 widening (bit
replication: $1F -> $FF, 0 -> 0).  The kept header must describe the copy
(4 bytes a pixel, pitch = width * 4).
Desk proof only; silicon owed.

Run:  py -3 -B tools/a64/pi5_shot16_check.py --compiler <PureMetalForge.exe> [--mutate]
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
REL_MEM = "RaspberryPi4/Board/memmap.pi4"
REL_FMT = "Anvil/Core/format.pbi"

UART = 0x107D001000
FB = 0x0200_0000
W, H, PITCH = 96, 5, 96 * 2 + 40          # padded pitch
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
    mem = d.source(REL_MEM, ov).replace("\r\n", "\n")
    parts = [
        "; pi5_shot16_check driver - generated, never committed.",
        consts(mem, "#MON_SHOT_"), consts(mem, "#MON_FB_"), consts(geom, "#SCR_SRC_"),
        "Global gScrSrc.i", "Global gScrRot.i", "Global gScrDsiUp.i",
        "Global gSurfBase.i", "Global gSurfW.i", "Global gSurfH.i", "Global gSurfPitch.i", "Global gSurfBpp.i",
        "Global gSeq.i",
        "Procedure SetSurf(base.i, w.i, h.i, pitch.i, bpp.i, src.i)",
        "  gSurfBase = base : gSurfW = w : gSurfH = h : gSurfPitch = pitch : gSurfBpp = bpp : gScrSrc = src",
        "EndProcedure",
        "Procedure.i DisplayMemorySafe()\n  ProcedureReturn 1\nEndProcedure",
        "Procedure.i DisplayViewBase()\n  ProcedureReturn gSurfBase\nEndProcedure",
        "Procedure.i DisplayWidth()\n  ProcedureReturn gSurfW\nEndProcedure",
        "Procedure.i DisplayHeight()\n  ProcedureReturn gSurfH\nEndProcedure",
        "Procedure.i DisplayPitch()\n  ProcedureReturn gSurfPitch\nEndProcedure",
        "Procedure.i DisplayBytesPerPixel()\n  ProcedureReturn gSurfBpp\nEndProcedure",
        "Procedure ShotSeqCarry(v.i)\n  gSeq = v\nEndProcedure",
        "Procedure.i ShotNextSeq()\n  gSeq = gSeq + 1\n  ProcedureReturn gSeq\nEndProcedure",
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
        "Procedure ShotPutHeader()\nEndProcedure",
        "Procedure ShotSayNothing()\n  UartWrite(33)\nEndProcedure",
        'XIncludeFile "%s"' % REL_FMT,
        proc(geom, "ScrSideways", REL_GEOM), proc(geom, "ScrLogicalW", REL_GEOM), proc(geom, "ScrLogicalH", REL_GEOM),
        proc(geom, "ScrMapX", REL_GEOM), proc(geom, "ScrMapY", REL_GEOM),
        proc(geom, "ScrWiden565", REL_GEOM), proc(geom, "ScrCapturePixel", REL_GEOM),
        proc(src, "ScrCaptureSnapshot", REL_SRC),
        proc(src, "ScrCaptureWiden16", REL_SRC),
        proc(src, "ScrCaptureToArea", REL_SRC),
        proc(src, "ScrShotValid", REL_SRC), proc(src, "ScrShotField", REL_SRC),
        proc(src, "ScrShotPixels", REL_SRC),
        proc(cmd, "ShotDump", REL_CMD),
        "Global gate_never.i",
        "If gate_never = 1",
        "  SetSurf(0, 0, 0, 0, 0, 0) : ScrCaptureToArea(0, 0, 0) : ShotDump() : ScrShotField(0)",
        "EndIf",
    ]
    return "\n".join(parts) + "\n"


def widen(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def surface_value(x, y):
    """Row 0 walks red 0..31, row 1 green 0..63, row 2 blue 0..31, row 3 a
    mixed ramp, row 4 white/black stripes - every field at every level."""
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
        kind = blob[pos + 4:pos + 8]
        body = blob[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype = ihdr[0], ihdr[1], ihdr[2], ihdr[3]
    if depth != 8 or ctype != 2:
        d.die("the PNG is not 8-bit RGB (depth %d, colour type %d)" % (depth, ctype))
    raw = zlib.decompress(idat)
    rows, stride, prev = [], w * 3, bytearray(w * 3)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(3, stride):
                line[i] = (line[i] + line[i - 3]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f != 0:
            d.die("PNG filter %d not handled by the gate" % f)
        rows.append(bytes(line))
        prev = line
    return w, h, rows


def gate(ov, work, cc):
    n = [0]

    def expect(ok, msg):
        n[0] += 1
        if not ok:
            d.die(msg)

    img, procs = d.build(cc, driver(ov), "shot16", work, ov, [REL_FMT])
    uart = bytearray()

    def model(addr, size, value):
        if addr == UART:
            if value is not None:
                uart.append(value & 0xFF)
            return 0
        if addr == UART + 0x18:
            return 0
        d.die("the capture touched device address $%X" % addr)

    mc = d.Machine(img, procs, model)
    for y in range(H):
        row = bytearray()
        for x in range(W):
            row += surface_value(x, y).to_bytes(2, "little")
        row += POISON.to_bytes(2, "little") * ((PITCH - W * 2) // 2)
        mc.poke(FB + y * PITCH, bytes(row))
    hdmi = d.const_in(d.source(REL_GEOM, ov), "#SCR_SRC_HDMI", REL_GEOM)
    mc.call("SetSurf", FB, W, H, PITCH, 2, hdmi)
    expect(mc.call("ScrCaptureToArea", 1, 0, 3) == 1, "ScrCaptureToArea refused a 16 bpp HDMI surface")
    mem = d.source(REL_MEM, ov)
    off = {k: d.const_in(mem, "#MON_SHOT_OFF_" + k, REL_MEM) for k in ("W", "H", "PITCH", "BPP", "BYTES")}
    fld = {k: mc.call("ScrShotField", v) for k, v in off.items()}
    expect(fld["W"] == W and fld["H"] == H, "header size %dx%d, want %dx%d" % (fld["W"], fld["H"], W, H))
    expect(fld["BPP"] == 4 and fld["PITCH"] == W * 4 and fld["BYTES"] == W * H * 4,
           "header says bpp %d pitch %d bytes %d; the kept copy is 4 bytes a pixel, pitch %d"
           % (fld["BPP"], fld["PITCH"], fld["BYTES"], W * 4))

    mc.call("ShotDump", limit=20_000_000)
    text = uart.decode("ascii", "replace")
    (work / "shot.txt").write_text(text)
    pm = load_pmfshot()
    w, h, rows = pm.decode(text)
    png_path = work / "shot.png"
    blob = pm.png(w, h, rows)
    if isinstance(blob, (bytes, bytearray)):
        png_path.write_bytes(blob)
    pw, ph, prow = read_png(png_path.read_bytes())
    expect((pw, ph) == (W, H), "the PNG is %dx%d, want %dx%d" % (pw, ph, W, H))
    bad = []
    for y in range(H):
        for x in range(W):
            got = tuple(prow[y][x * 3:x * 3 + 3])
            want = widen(surface_value(x, y))
            if got != want:
                bad.append((x, y, got, want))
    expect(not bad, "%d PNG pixels differ from the RGB565 widening; first (x,y,got,want) %s"
           % (len(bad), bad[:1]))
    return n[0]


MUTATIONS = [
    (REL_GEOM, "packing: red and blue fields swapped", "  r5 = (v >> 11) & $1F\n", "  r5 = v & $1F\n"),
    (REL_GEOM, "packing: green read as 5 bits", "  g6 = (v >> 5) & $3F\n", "  g6 = (v >> 5) & $1F\n"),
    (REL_SRC, "stride: 32 bpp source step", "      v = PeekW(fb + sy * pitch + sx * 2) & $FFFF\n",
     "      v = PeekW(fb + sy * pitch + sx * 4) & $FFFF\n"),
    (REL_SRC, "pitch ignored (width * 2)", "      v = PeekW(fb + sy * pitch + sx * 2) & $FFFF\n",
     "      v = PeekW(fb + sy * pw * 2 + sx * 2) & $FFFF\n"),
    (REL_GEOM, "no widening (plain shift)",
     "  ProcedureReturn (($FF << 24) | (((r5 << 3) | (r5 >> 2)) << 16)) | ((((g6 << 2) | (g6 >> 4)) << 8) | ((b5 << 3) | (b5 >> 2)))\n",
     "  ProcedureReturn (($FF << 24) | ((r5 << 3) << 16)) | (((g6 << 2) << 8) | (b5 << 3))\n"),
    (REL_SRC, "header keeps the source pitch", "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_PITCH,  pw * 4)\n", "  PokeI(#MON_SHOT_HDR + #MON_SHOT_OFF_PITCH,  pitch)\n"),
    (REL_SRC, "16 bpp still refused", "  If gScrSrc = #SCR_SRC_HDMI And DisplayBytesPerPixel() = 2\n    ProcedureReturn ScrCaptureWiden16",
     "  If gScrSrc = #SCR_SRC_HDMI And DisplayBytesPerPixel() = 3\n    ProcedureReturn ScrCaptureWiden16"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-shot16-"))
    try:
        try:
            n = gate({}, top / "gate", cc)
        except d.GateFail as e:
            print("pi5_shot16_check: FAIL - %s" % e)
            return 1
        print("pi5_shot16_check: PASS - %d checks, %dx%d surface at pitch %d decoded "
              "through tools/pmfshot.py (desk only; silicon owed)" % (n, W, H, PITCH))
        if a.mutate:
            left = d.run_mutations("pi5_shot16_check", MUTATIONS,
                                   lambda ov, w: gate(ov, w, cc), top / "mut")
            return 1 if left else 0
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
