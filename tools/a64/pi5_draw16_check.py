#!/usr/bin/env python3
"""Desk gate AND cost model for drawing the BCM2712's 16 bpp console
(-t pi5): DisplayClear, DisplayScroll and a line of text, by the CPU and
by the DMA engine, on RaspberryPi4/Lib/display.pi4 + Lib/dma.pi4 as built
for the Pi 5.

THE GATE.  The same sequence - clears, odd-edged fills, a line of text,
single and multi-row scrolls - is drawn twice on a padded-pitch RGB565
surface, once with the engine off (the CPU path, which the Pi 4 has run
for weeks) and once with it on, and the two framebuffers must be equal
byte for byte, with the engine demonstrably used (control blocks
executed).  The engine is tools/a64/a64_dma_pi5_check.py's model of the
BCM2712 dma40 controller, imported rather than restated.

THE COST MODEL (--model).  The same operations at the real surface,
1920 x 1080, pitch 3840, counting what the -t pi5 build executes:
instructions, loads and stores (framebuffer and other RAM separately),
engine blocks and bytes.  With the MMU and caches off - stage 1 - EVERY
instruction fetch and EVERY load or store is a DRAM access.  Time is then
estimated with two figures, both stated where they come from:
  * T_OP  ns per instruction with the MMU off: 31 ns, from the Pi 4
          silicon measurement recorded in RaspberryPi4/Board/display.pi4
          (ScreenFastScroll: a ~30-instruction cache-walk loop body cost
          928 ns per iteration with the MMU off, 2026-08-28).  Pi 5 NOT
          MEASURED - its DRAM and clock differ; the ratio is the point.
  * DMA_BPS bytes per second for the engine: 600 MB/s, from the same
          note (a ~7 MB console scroll's two transfers took 12.0 ms).
and the caching column assumes 1 instruction per cycle at the firmware's
reported clock with the I- and D-caches on (framebuffer still written to
DRAM once).  Silicon owed for every number.

Run:  py -3 -B tools/a64/pi5_draw16_check.py --compiler <PureMetalForge.exe> [--mutate] [--model]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pi5_desk as d                                # noqa: E402
import a64_dma_pi5_check as dm                      # noqa: E402

REL_DISP = "RaspberryPi4/Lib/display.pi4"
REL_DMA = "RaspberryPi4/Lib/dma.pi4"
REL_MBX = "RaspberryPi4/Lib/mailbox.pi4"
REL_BOARD_DSP = "RaspberryPi4/Board/display.pi4"

FB = 0x3F80_0000            # where the Pi 5 firmware put it (silicon 2026-09-26)
SCRATCH = 0x0080_0000
T_OP_NS = 31
DMA_BPS = 600e6
CACHED_HZ = 2.4e9           # the A76's rated clock; see the vault note

DRIVER = r'''
; pi5_draw16_check driver - generated, never committed.
#DSP_DMA_LINKED = 1
XIncludeFile "RaspberryPi4/Lib/mailbox.pi4"
XIncludeFile "RaspberryPi4/Lib/dma.pi4"
XIncludeFile "RaspberryPi4/Lib/display.pi4"
Procedure str_print_at(p.i)
EndProcedure
Procedure.i Setup(base.i, pitch.i, w.i, h.i, useDma.i)
  If DisplayAdopt(base, pitch, w, h, 16) <> #DSP_OK
    ProcedureReturn -1
  EndIf
  If DisplayConsoleFull() = 0
    ProcedureReturn -2
  EndIf
  If useDma = 0
    ProcedureReturn 1
  EndIf
  If DmaSetScratch($800000, 512) = 0
    ProcedureReturn -3
  EndIf
  If DisplayDmaBind() = 0
    ProcedureReturn -4
  EndIf
  If DmaInit() = 0
    ProcedureReturn -5
  EndIf
  If DisplayUseDma(1) = 0
    ProcedureReturn -6
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i Pack(r.i, g.i, b.i)
  ProcedureReturn DisplayRGB(r, g, b)
EndProcedure
Procedure DoClear(c.i)
  DisplayClear(c)
EndProcedure
Procedure DoFill(x.i, y.i, w.i, h.i, c.i)
  DisplayFillRect(x, y, w, h, c)
EndProcedure
Procedure DoText(x.i, y.i, s.i, fg.i, bg.i)
  DisplayText(x, y, s, fg, bg)
EndProcedure
Procedure DoScroll(n.i)
  DisplayScroll(n)
EndProcedure
Procedure DoColour(fg.i, bg.i)
  DisplayColour(fg, bg)
EndProcedure
Procedure.i DoConsole(y.i)
  ProcedureReturn DisplayConsole(0, y, DisplayWidth(), DisplayHeight() - y)
EndProcedure
#BANNER_H = 16
Global gDma.i
Global gScreenBg.i
Procedure.i DmaOps()
  ProcedureReturn dsp_dmaOps
EndProcedure
Procedure SetFast(dma.i, bg.i)
  gDma = dma : gScreenBg = bg
EndProcedure
%(FAST)s
Global gate_never.i
If gate_never = 1
  Setup(0, 0, 0, 0, 0) : Pack(0, 0, 0) : DoClear(0) : DoFill(0, 0, 0, 0, 0)
  DoText(0, 0, 0, 0, 0) : DoScroll(0) : DoColour(0, 0) : DoConsole(0) : SetFast(0, 0) : ScreenFastScroll(0) : DmaOps()
EndIf
'''


class Rig:
    """One machine, the dma40 model on channel 6, and counters."""

    def __init__(self, img, procs):
        self.k = dm.constants(None) if False else {n: v for n, (v, _w) in dm.PINNED.items()}
        self.board = dm.Board(self.k, 6)
        self.base, self.size = self.k["CHAN0_PHYS"], self.k["CHAN_SIZE"]
        self.mc = d.Machine(img, procs, self.model)
        self.board.mem = self.mc.cpu.memory
        self.reset_counts()
        cpu = self.mc.cpu
        ld, st = cpu.load, cpu.store

        def load(a, n):
            if FB <= a < FB + self.fb_bytes:
                self.fb_loads += 1
            elif a < 0x1_0000_0000:
                self.ram_loads += 1
            return ld(a, n)

        def store(a, v, n):
            if FB <= a < FB + self.fb_bytes:
                self.fb_stores += 1
            elif a < 0x1_0000_0000:
                self.ram_stores += 1
            st(a, v, n)
        cpu.load, cpu.store = load, store
        plain = self.mc.step

        def step():
            self.steps += 1
            plain()
        self.mc.step = step
        self.fb_bytes = 0
        # The image's own top level first: the libraries' Global initialisers
        # (the console font, the defaults) live there, as on the board.
        c = self.mc.cpu
        c.pc, c.sp, c.x[30] = d.LOAD, d.STACK, d.RETURN
        n = 0
        while c.pc != d.RETURN:
            n += 1
            if n > 5_000_000:
                d.die("the image's top level never returned")
            self.mc.step()

    def reset_counts(self):
        self.steps = self.fb_loads = self.fb_stores = self.ram_loads = self.ram_stores = 0

    def model(self, addr, size, value):
        if self.base <= addr < self.base + 12 * self.size:
            ch, off = (addr - self.base) // self.size, (addr - self.base) % self.size
            if ch != 6:
                d.die("the display drove DMA channel %d; the build's channel is 6" % ch)
            if value is None:
                return self.board.engines[ch].read(off)
            self.board.engines[ch].write(off, value & 0xFFFFFFFF, self.mc.cpu.memory, self.board)
            return 0
        d.die("unmodelled device access at $%X" % addr)

    def blocks(self):
        return sum(len(c) for c in self.board.engines[6].chains)

    def dma_bytes(self):
        return sum(b["len"] for c in self.board.engines[6].chains for b in c)

    def faults(self):
        return self.board.engines[6].faults


def proc(text, name):
    import re
    m = re.search(r"^Procedure(\.\w)?\s+%s\(" % name, text, re.M)
    if not m:
        d.die("%s no longer defines %s" % (REL_BOARD_DSP, name))
    e = text.find("\nEndProcedure", m.start())
    return text[m.start():e + len("\nEndProcedure")]


def build(ov, work, cc):
    bd = d.source(REL_BOARD_DSP, ov).replace("\r\n", "\n")
    drv = DRIVER.replace("%(FAST)s", proc(bd, "LogoHeight") + "\n" + proc(bd, "ScreenFastScroll"))
    return d.build(cc, drv, "draw16", work, ov, [REL_MBX, REL_DMA, REL_DISP])


def setup(rig, w, h, pitch, dma):
    rig.fb_bytes = pitch * h
    rig.mc.poke(FB, b"\x5A" * (pitch * h))
    r = rig.mc.signed(rig.mc.call("Setup", FB, pitch, w, h, 1 if dma else 0))
    if r != 1:
        d.die("Setup failed at step %d (%s)" % (-r, "DMA" if dma else "CPU"))


SEQUENCE = [
    ("DoColour", "fg", "bg"),
    ("DoClear", "bg"),
    ("DoFill", 3, 5, 37, 9, "c1"),        # odd x, odd width
    ("DoFill", 101, 0, 60, 40, "c2"),
    ("DoText", 8, 20, "TEXT", "fg", "bg"),
    ("DoText", 8, 60, "TEXT", "c1", "bg"),
    ("DoScroll", 1),
    ("DoText", 8, 80, "TEXT", "fg", "c2"),
    ("DoScroll", 2),
    ("DoFill", 0, 0, 320, 7, "c2"),
    ("DoScroll", 1),
    ("DoFill", 61, 51, 200, 40, "c1"),     # after the scrolls, above the DMA threshold
]


def draw(rig, w, h, pitch, dma, text_addr):
    setup(rig, w, h, pitch, dma)
    col = {n: rig.mc.call("Pack", *rgb) for n, rgb in
           (("fg", (250, 240, 20)), ("bg", (0, 0, 40)), ("c1", (200, 30, 90)), ("c2", (8, 180, 250)))}
    for op in SEQUENCE:
        args = []
        for a in op[1:]:
            args.append(col[a] if a in col else text_addr if a == "TEXT" else a)
        rig.mc.call(op[0], *args, limit=60_000_000)
    return rig.mc.peek(FB, pitch * h)


def gate(ov, work, cc):
    n = [0]

    def expect(ok, msg):
        n[0] += 1
        if not ok:
            d.die(msg)

    img, procs = build(ov, work, cc)
    W, H, PITCH = 320, 120, 320 * 2 + 64
    text = b"Anvil on a Pi 5, 16 bpp: jumps over 0123456789 gy|"
    out = {}
    for dma in (False, True):
        rig = Rig(img, procs)
        rig.mc.poke(0x0200_0000, text + b"\0")
        out[dma] = draw(rig, W, H, PITCH, dma, 0x0200_0000)
        if dma:
            expect(not rig.faults(), "the engine model saw: %s" % rig.faults()[:2])
            expect(rig.blocks() >= 4, "the DMA run executed %d control blocks - the engine "
                   "was not used at 16 bpp" % rig.blocks())
            inc = rig.k["XI_INC"]
            chains = rig.board.engines[6].chains
            fills = sum(1 for c in chains if c and not (c[0]["srci"] & inc))
            copies = sum(1 for c in chains if c and (c[0]["srci"] & inc))
            expect(fills >= 5 and copies >= 3, "the engine ran %d fills and %d copies; the "
                   "clear, the three scrolls' vacated rows and the large fill (5) and the three "
                   "scroll moves (3) should all be DMA" % (fills, copies))
    a, b = out[False], out[True]
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    expect(not diff, "DMA and CPU framebuffers differ in %d bytes; first at row %d byte %d "
           "(cpu %02X dma %02X)" % (len(diff), diff[0] // PITCH if diff else 0,
                                    diff[0] % PITCH if diff else 0,
                                    a[diff[0]] if diff else 0, b[diff[0]] if diff else 0))
    pads = [i for i in range(len(b)) if (i % PITCH) >= W * 2 and b[i] != 0x5A]
    expect(not pads, "%d bytes of pitch padding were written" % len(pads))
    distinct = len(set(bytes(a[i:i + 2]) for i in range(0, W * 2 * 20, 2)))
    expect(distinct >= 3, "the reference picture is too plain (%d colours) to prove anything" % distinct)

    # ---- the board's fast scroll (ScreenFastScroll) against the library's ----
    FW, FH, FP = 320, 16 + 7 * 16, 640          # full-width console, unpadded, as it requires
    pics = {}
    for dma in (False, True):
        rig = Rig(img, procs)
        rig.mc.poke(0x0200_0000, text + b"\0")
        setup(rig, FW, FH, FP, dma)
        fg = rig.mc.call("Pack", 250, 240, 20)
        bg = rig.mc.call("Pack", 0, 0, 40)
        rig.mc.call("DoColour", fg, bg)
        expect(rig.mc.call("DoConsole", 16) == 1, "the fast-scroll console would not set up")
        rig.mc.call("DoClear", bg)
        for yy in (30, 50, 70, 90, 110):
            rig.mc.call("DoText", 4, yy, 0x0200_0000, fg, bg)
        if dma:
            rig.mc.call("SetFast", 1, bg)
            ops0 = rig.mc.call("DmaOps")
            got = rig.mc.call("ScreenFastScroll", 2, limit=60_000_000)
            expect(got == 1, "ScreenFastScroll declined on a 16 bpp surface")
            expect(rig.mc.call("DmaOps") == ops0, "the fast scroll fell back to the library's fill - "
                   "its own engine fill was refused at 16 bpp")
            inc = rig.k["XI_INC"]
            last = rig.board.engines[6].chains[-1]
            expect(last and not (last[0]["srci"] & inc), "the fast scroll's vacated rows were not "
                   "filled by the engine")
        else:
            rig.mc.call("DoScroll", 2)
        pics[dma] = rig.mc.peek(FB, FP * FH)
    a2, b2 = pics[False], pics[True]
    diff = [i for i in range(len(a2)) if a2[i] != b2[i]]
    expect(not diff, "ScreenFastScroll and DisplayScroll disagree in %d bytes; first at row %d"
           % (len(diff), diff[0] // FP if diff else 0))
    return n[0]

def model(work, cc):
    img, procs = build({}, work, cc)
    W, H, PITCH = 1920, 1080, 3840
    rows = []
    text = b"The quick brown fox jumps over the lazy dog 0123456789 " * 2
    for dma in (False, True):
        for name, call in (("clear 1920x1080", ("DoClear", "bg")),
                           ("scroll 1 row", ("DoScroll", 1)),
                           ("text line (%d ch)" % len(text), ("DoText", 0, 200, "TEXT", "fg", "bg"))):
            if name.startswith("text") and dma:
                continue            # text is drawn by the CPU either way
            rig = Rig(img, procs)
            rig.mc.poke(0x0200_0000, text + b"\0")
            setup(rig, W, H, PITCH, dma)
            fg = rig.mc.call("Pack", 250, 240, 20)
            bg = rig.mc.call("Pack", 0, 0, 40)
            rig.mc.call("DoColour", fg, bg)
            rig.reset_counts()
            args = [fg if a == "fg" else bg if a == "bg" else 0x0200_0000 if a == "TEXT" else a
                    for a in call[1:]]
            rig.mc.call(call[0], *args, limit=400_000_000)
            ops = rig.steps + rig.fb_loads + rig.fb_stores + rig.ram_loads + rig.ram_stores
            t_ms = ops * T_OP_NS / 1e6 if False else rig.steps * T_OP_NS / 1e6
            dma_ms = rig.dma_bytes() / DMA_BPS * 1e3
            cached_ms = rig.steps / CACHED_HZ * 1e3 + rig.fb_stores * 2 / 4e9 * 1e3
            rows.append((("DMA " if dma else "CPU ") + name, rig.steps, rig.fb_loads, rig.fb_stores,
                         rig.ram_loads + rig.ram_stores, rig.blocks(), rig.dma_bytes(),
                         t_ms, dma_ms, cached_ms))
    print("\n  %-26s %11s %9s %9s %9s %6s %10s %9s %8s %9s" % (
        "operation", "instrs", "fb ld", "fb st", "ram ld/st", "CBs", "DMA bytes",
        "uncached", "DMA", "cached*"))
    for r in rows:
        print("  %-26s %11d %9d %9d %9d %6d %10d %7.1fms %6.1fms %7.2fms" % r)
    print("  uncached = instrs x %d ns (MMU off, Pi 4 silicon figure); DMA = bytes / %.0f MB/s;"
          % (T_OP_NS, DMA_BPS / 1e6))
    print("  cached* = instrs at 1 IPC @ %.1f GHz + framebuffer bytes at 4 GB/s - a MODEL, silicon owed"
          % (CACHED_HZ / 1e9))


MUTATIONS = [
    (REL_DISP, "16 bpp fill word not doubled",
     "    ProcedureReturn ((colour & $FFFF) << 16) | (colour & $FFFF)\n",
     "    ProcedureReturn colour & $FFFF\n"),
    (REL_DISP, "fill word swapped halves",
     "    ProcedureReturn ((colour & $FFFF) << 16) | (colour & $FFFF)\n",
     "    ProcedureReturn ((colour & $FF) << 24) | ((colour & $FF00) << 8) | (colour & $FFFF)\n"),
    (REL_DISP, "fill word never applied", "  colour = DisplayFillWord(colour)\n", "  colour = colour\n"),
    (REL_DISP, "16 bpp still refused by the engine path",
     "  If dsp_bpp = 2\n    If (dsp_pitch & 1) <> 0 Or (dsp_base & 1) <> 0\n",
     "  If dsp_bpp = 99\n    If (dsp_pitch & 1) <> 0 Or (dsp_base & 1) <> 0\n"),
    (REL_DISP, "32 bpp row bytes on a 16 bpp fill", "  rowBytes = (x1 - x0) * dsp_bpp\n", "  rowBytes = (x1 - x0) * 4\n"),
    (REL_DISP, "pitch ignored in the fill", "  dst      = (dsp_base + (y0 * dsp_pitch)) + (x0 * dsp_bpp)\n",
     "  dst      = (dsp_base + (y0 * dsp_w * dsp_bpp)) + (x0 * dsp_bpp)\n"),
    (REL_BOARD_DSP, "fast scroll fills at 32 bpp",
     "    If DmaFillPattern32(dst + (keep * pitch), pitch, DisplayWidth() * 2, n * chgt, DisplayFillWord(gScreenBg)) = 0\n",
     "    If DmaFillPattern32(dst + (keep * pitch), pitch, DisplayWidth() * 4, n * chgt, DisplayFillWord(gScreenBg)) = 0\n"),
    (REL_BOARD_DSP, "fast scroll pattern not doubled",
     "    If DmaFillPattern32(dst + (keep * pitch), pitch, DisplayWidth() * 2, n * chgt, DisplayFillWord(gScreenBg)) = 0\n",
     "    If DmaFillPattern32(dst + (keep * pitch), pitch, DisplayWidth() * 2, n * chgt, gScreenBg) = 0\n"),
]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--model", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-draw16-"))
    try:
        try:
            n = gate({}, top / "gate", cc)
        except d.GateFail as e:
            print("pi5_draw16_check: FAIL - %s" % e)
            return 1
        print("pi5_draw16_check: PASS - %d checks: DMA and CPU draw the same 16 bpp console "
              "byte for byte (desk only; silicon owed)" % n)
        if a.model:
            model(top / "model", cc)
        if a.mutate:
            left = d.run_mutations("pi5_draw16_check", MUTATIONS,
                                   lambda ov, w: gate(ov, w, cc), top / "mut")
            return 1 if left else 0
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
