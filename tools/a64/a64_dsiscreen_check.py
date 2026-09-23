#!/usr/bin/env python3
"""Executable gate for the Pi 4 display seam's arithmetic.

    python tools/a64/a64_dsiscreen_check.py --compiler <PureMetalForge.exe>

The seam is what lets Anvil's console be attached to EITHER of the two
kinds of screen a Raspberry Pi 4 has: HDMI, whose framebuffer the
VideoCore firmware allocates, and the Waveshare DSI panel, whose
framebuffer Anvil allocates itself because the firmware owns no DSI
display and never brings DSI1 up.

WHAT THIS GATE COVERS, AND WHAT IT DELIBERATELY DOES NOT.

It covers RaspberryPi4/Board/screen_geom.pi4 - the boot choice, the
DEFAULT ROTATION, THE FONT SIZE COMPUTED FROM HOW BIG THE GLASS IS, the
rotation map, the transpose and the scanned-row run addresses - and it
covers them by EXECUTING THE SHIPPED CODE, built from
RaspberryPi4/Examples/Diagnostics/pi4DsiScreenProbe.pi4, on Anvil's A64
model (tools/a64/a64_interp.py).  Nothing here is a re-implementation of
the arithmetic being checked; the probe's own tally is graded, and the
font rule and the rotation geometry are then re-derived here a different
way, which is a second opinion rather than an echo.

It does NOT cover the DSI bring-up itself - the power domain, the D-PHY,
the panel's init table, the HVS channel or the pixel valve.  Those are
registers on a block this machine does not have, and a gate that modelled
them would be grading a model.

WHY THE ARITHMETIC IS WORTH A GATE AT ALL: EVERY ONE OF ITS FAILURE MODES
IS INVISIBLE FROM A DESK.  A wrong boot choice is a dark panel and a
console on a socket nobody is watching.  A wrong default rotation is a
console standing on its side on a panel mounted the other way - it
builds, it boots, it lights the glass and it reports itself perfectly
happy.  A wrong font rule is a console that wraps every line of Anvil's
own eighty-column text.  A rotation off by one is a picture one pixel to
the left.  A run address off by one is a cache clean that misses the byte
the transpose just wrote.

THE MMIO HARD STOP.  screen_geom.pi4's header claims it touches no
hardware.  The model below answers the PL011 the tally is printed
through, and the GPIO block UartInit muxes on its way there, and NOTHING
ELSE: any other MMIO access raises.  Without that the claim would be an
assertion in a comment rather than a property under test.
"""

from __future__ import annotations

import argparse
import math
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

from a64_interp import A64, attach_symbols            # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

SRC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4DsiScreenProbe.pi4"

# The same link the bench sends a diagnostic with.
LOAD = 0x00400000
STACK = 0x03000000
LOADER_LR = 0xDEADBEE0

UART_DR = 0xFE201000
UART_FR = 0xFE201018
PL011_LO = 0xFE201000
PL011_HI = 0xFE201FFF
GPIO_LO = 0xFE200000
GPIO_HI = 0xFE2000FF

# FR with RXFE (bit 4) and TXFE (bit 7) set, TXFF and BUSY clear: the
# transmitter is idle and there is nothing to receive.
FR_IDLE = 0x90

# A budget and not a hope: a runaway loop in the transpose is a real
# possible defect and hanging the gate is not an acceptable way to report
# it.
STEP_LIMIT = 120_000_000

# The modelled panel the probe transposes over.  Kept here as well as in
# the .pi4 because the independent transpose below has to reproduce it.
PW, PH = 16, 24
PIX = PW * PH


# ---------------------------------------------------------------------
#  BUILD AND RUN
# ---------------------------------------------------------------------

def build(compiler: str, source: pathlib.Path, out: pathlib.Path) -> None:
    cmd = [compiler, "--compile", str(source), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out), "-s"]
    r = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    if r.returncode != 0 or not out.exists():
        raise SystemExit("The display seam probe did not build:\n" + r.stdout)


def run(img: pathlib.Path):
    """Execute the image.  Returns the CPU, the UART text and x0."""
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = 0x00100000
    cpu.x[30] = LOADER_LR

    mem = cpu.memory
    uart = bytearray()

    def load(addr: int, size: int) -> int:
        # THE ALIGNMENT RULE: this closure replaces A64.load, so the guard
        # has to be called here or the gate models a machine more
        # permissive than the part.
        cpu.align_guard(addr, size, False)
        if addr >= 0xFE000000:
            if addr == UART_FR:
                return FR_IDLE
            if PL011_LO <= addr <= PL011_HI:
                return 0
            if GPIO_LO <= addr <= GPIO_HI:
                return 0
            raise SystemExit(
                f"The probe read unmodelled MMIO at ${addr:08X}; "
                f"screen_geom.pi4 is supposed to touch no hardware at all.")
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFE000000:
            if addr == UART_DR:
                uart.append(value & 0xFF)
                return
            if PL011_LO <= addr <= PL011_HI:
                return
            if GPIO_LO <= addr <= GPIO_HI:
                return
            raise SystemExit(
                f"The probe wrote unmodelled MMIO at ${addr:08X}; "
                f"screen_geom.pi4 is supposed to touch no hardware at all.")
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    steps = 0
    while steps < STEP_LIMIT:
        if cpu.pc == LOADER_LR:
            return cpu, uart.decode("latin-1"), cpu.x[0]
        cpu.step()
        steps += 1
    raise SystemExit("The probe never returned (%d steps).\n%s"
                     % (steps, uart.decode("latin-1")))


# ---------------------------------------------------------------------
#  THE SECOND OPINION
#
#  The probe checks its own transpose against its own corner map, and
#  two procedures in one file agreeing is worth less than it looks.  So
#  the rotation is written again here, from the geometry rather than from
#  the code, in the SLOW, OBVIOUS form: one pixel at a time, straight out
#  of the rotation's definition, with no runs and no loop ordering.
# ---------------------------------------------------------------------

def reference_rotate(deg: int, draw: dict, lw: int, lh: int) -> dict:
    scan = {}
    for y in range(lh):
        for x in range(lw):
            if deg == 90:
                sx, sy = lh - 1 - y, x
            elif deg == 270:
                sx, sy = y, lw - 1 - x
            else:
                sx, sy = x, y
            scan[(sx, sy)] = draw[(x, y)]
    return scan


class Cases:
    def __init__(self, fails: list) -> None:
        self.fails = fails
        self.count = 0

    def check(self, name: str, ok: bool, detail: str) -> None:
        self.count += 1
        if not ok:
            self.fails.append("%s: %s" % (name, detail))


def grade(out: str, rc: int, c: Cases) -> None:
    check = c.check

    # ---- the probe's own verdict -------------------------------------
    nfail = out.count("** FAIL **")
    first = next((l for l in out.splitlines() if "** FAIL **" in l), "")
    check("the probe reports no failures of its own", nfail == 0,
          "the probe printed %d failing line(s); the first is %r"
          % (nfail, first))
    check("the probe's return value agrees with its tally", rc == 0,
          "the program returned %d, so it counted that many failures" % rc)
    check("the probe finished and printed a verdict",
          "VERDICT      GREEN" in out,
          "no GREEN verdict line - the probe returned early or was red")

    # THE COUNT, NOT ONLY THE ABSENCE OF FAILURES.  A probe that silently
    # stopped after section A would print no failures at all.
    m = re.search(r"checks run\s+(\d+)", out)
    ran = int(m.group(1)) if m else -1
    check("the probe ran its whole check list", ran >= 216,
          "it ran %d checks; the file's ten sections are two hundred and "
          "sixteen, so it stopped part way" % ran)
    m = re.search(r"passed\s+(\d+)", out)
    passed = int(m.group(1)) if m else -1
    check("every check it ran passed", passed == ran,
          "%d of %d passed" % (passed, ran))

    # ---- the sections are all present, by name -----------------------
    for name, tag in (("the boot choice", "-- A."),
                      ("the font size", "-- B."),
                      ("which rotations exist", "-- C."),
                      ("the console geometry", "-- D."),
                      ("the four corners", "-- E."),
                      ("the transpose", "-- F."),
                      ("the scanned-row runs", "-- G."),
                      ("which way up it comes up", "-- H."),
                      ("HDMI and the typed override", "-- I."),
                      ("a finger, mapped back", "-- J.")):
        check("section %s ran" % name, tag in out,
              "no %r heading in the output" % tag)

    # ---- THE ORIENTATION, ASSERTED HERE AS WELL AS IN THE PROBE ------
    # The panel on the reference bench is mounted LANDSCAPE.  The probe
    # checks ScrRotDefault by number; this checks that the check itself is
    # still in the image.  A section H deleted along with the default it
    # guards would leave every remaining assertion green.
    check("the probe asserts the landscape default by name",
          "defaults to LANDSCAPE (90)" in out,
          "section H's landscape assertion is not in the probe's output, so "
          "nothing in this gate is checking which way up the console comes "
          "up on the panel")
    check("the probe's landscape assertion passed",
          "defaults to LANDSCAPE (90)" in out
          and "** FAIL **" not in
          next((l for l in out.splitlines()
                if "defaults to LANDSCAPE (90)" in l), "** FAIL **"),
          "the DSI panel's default rotation is not 90 - the console comes "
          "up standing on its side on a panel that is mounted landscape")
    check("the verdict names the orientation",
          "LANDSCAPE on the panel" in out or "** FAIL **" in out,
          "the GREEN verdict no longer says the console comes up landscape")

    # THE TOUCH MAP IS ASSERTED BY NAME AS WELL AS BY COUNT, for the
    # same reason the landscape default is: a section deleted along with
    # the mapping it guards would leave every remaining assertion in this
    # file green. 180 is the one to name - it is the single case where
    # the touch map is NOT the mirror of the pixel map, because the
    # scaler turns the picture over after the pixel map has run, and it
    # is the case a copy of the forward map would get wrong.
    check("the probe asserts the 180 touch map by name",
          "180: but touch 0,0 is screen x 799" in out,
          "section J's 180 assertion is not in the probe's output, so "
          "nothing in this gate is checking the one rotation where a "
          "finger and a pixel do not map the same way")
    check("the probe's 180 touch assertion passed",
          "180: but touch 0,0 is screen x 799" in out
          and "** FAIL **" not in
          next((l for l in out.splitlines()
                if "180: but touch 0,0 is screen x 799" in l),
               "** FAIL **"),
          "at 180 the scaler mirrors the picture during scan-out, so a "
          "finger on the top left of the glass reports the controller's "
          "far corner and both axes have to be turned back")


def grade_scale(out: str, c: Cases) -> None:
    """A SECOND OPINION ON THE FONT SIZE, WORKED IN FLOATING POINT.

    The probe checks the shipped integer arithmetic against numbers
    written into it by hand.  This checks those numbers - it re-derives
    the whole rule in floats, a genuinely different calculation rather
    than the same expression typed twice, and it fails if the constants
    the probe asserts are not the ones the rule actually produces.

    THE RULE, RESTATED FROM THE PHYSICS AND NOT FROM THE SOURCE: the
    magnification is the whole number nearest (target inches * pixels
    per inch) / 16, floored at 1, and then capped so the console keeps
    eighty columns.
    """
    check = c.check

    TARGET_IN = 0.110      # RaspberryPi4/Board/screen_geom.pi4, #SCR_GLYPH_THOU
    FONT_W, FONT_H = 8, 16
    MIN_COLS = 80

    def ppi(w, h, diag_tenths):
        return math.hypot(w, h) / (diag_tenths / 10.0)

    def scale(w, h, diag_tenths, logical_w):
        ideal = max(1, int(round(TARGET_IN * ppi(w, h, diag_tenths) / FONT_H)))
        cap = max(1, logical_w // (FONT_W * MIN_COLS))
        return min(ideal, cap)

    # ---- THE PANEL, BOTH WAYS ROUND ----------------------------------
    # $65 = 101 tenths = 10.1 inches, the diagonal the panel's own
    # controller reports.  The panel is 800 x 1280 whatever the console
    # does.
    land = scale(800, 1280, 101, 1280)
    port = scale(800, 1280, 101, 800)
    check("the panel's landscape console is magnification 1", land == 1,
          "the rule gives %d landscape, so the probe's expectation of 1 is "
          "wrong and the type on the glass will not be the size intended"
          % land)
    check("the panel's portrait console is the same magnification",
          land == port,
          "landscape is %d and portrait is %d - the console's letters change "
          "physical size when the picture is turned, which is exactly the "
          "defect the font rule exists to remove" % (land, port))

    # THE GLYPH HEIGHT IN INCHES, WHICH IS THE NUMBER A PERSON AT THE
    # PANEL ACTUALLY SEES.
    h_land = land * FONT_H / ppi(800, 1280, 101)
    h_port = port * FONT_H / ppi(800, 1280, 101)
    check("both orientations draw the same height of type",
          abs(h_land - h_port) < 1e-9,
          "landscape draws %.4f inch to a line and portrait %.4f"
          % (h_land, h_port))
    check("that height is the target it was chosen for",
          abs(h_land - TARGET_IN) < 0.010,
          "the type comes out %.4f inch to a line against a target of %.3f, "
          "which is more than a hundredth of an inch out - the rounding is "
          "landing on the wrong whole magnification" % (h_land, TARGET_IN))

    # ---- THE COLUMNS AND ROWS THE BENCH WILL SEE ---------------------
    BANNER = 120
    cols_land = 1280 // (FONT_W * land)
    rows_land = (800 - BANNER) // (FONT_H * land)
    cols_port = 800 // (FONT_W * port)
    rows_port = (1280 - BANNER) // (FONT_H * port)
    check("landscape comes out 160 columns by 42 lines",
          (cols_land, rows_land) == (160, 42),
          "the rule gives %d x %d, so the geometry the probe asserts for the "
          "bench to grade against is wrong" % (cols_land, rows_land))
    check("portrait is unchanged at 100 columns by 72 lines",
          (cols_port, rows_port) == (100, 72),
          "the rule gives %d x %d; portrait must not have moved"
          % (cols_port, rows_port))

    # ---- AN HDMI MONITOR DOES NOT CHANGE -----------------------------
    # Magnification 1 is what an HDMI console draws at, so every ordinary
    # desktop mode on the stated 24 inch default has to stay there.
    for w, h in ((1920, 1080), (1824, 984), (1280, 720), (3840, 2160),
                 (2560, 1440)):
        s = scale(w, h, 240, w)
        check("HDMI %dx%d stays at magnification 1" % (w, h), s == 1,
              "it comes out %d, so plugging a monitor into this board would "
              "change the console somebody was already using" % s)

    # ---- THE CAP STILL BITES WHERE IT SHOULD -------------------------
    # A four inch 720 x 720 panel is dense enough to ask for 2, which
    # would be 45 columns - and Anvil's own text is written to eighty.
    check("a small dense panel is capped back to eighty columns",
          scale(720, 720, 40, 720) == 1
          and int(round(TARGET_IN * ppi(720, 720, 40) / FONT_H)) == 2,
          "either the density no longer asks for 2 on a 4 inch 720x720 "
          "panel, or the eighty-column cap is not holding it back to 1")

    # ---- THE ASSERTIONS ARE STILL IN THE IMAGE, BY NAME --------------
    for phrase, why in (
        ("portrait, 800 across: scale 1 - THE SAME",
         "nothing in the probe is checking that turning the console leaves "
         "the size of the type alone"),
        ("both orientations draw 0.107 inch of type",
         "the probe no longer asserts the two orientations draw the same "
         "physical height of type"),
        ("landscape console is 160 columns",
         "the probe no longer says what the bench should see on the glass"),
    ):
        line = next((l for l in out.splitlines() if phrase in l), "")
        check("the probe asserts %r" % phrase, bool(line), why)
        check("...and it passed", "** FAIL **" not in (line or "** FAIL **"),
              "that assertion is in the image and it FAILED: %s" % line)


def grade_pixels(c: Cases) -> None:
    """The rotation geometry the transpose relies on, from its definition."""
    check = c.check

    for deg in (90, 270):
        lw, lh = (PH, PW)
        draw = {(x, y): y * 1000 + x + 1 for y in range(lh) for x in range(lw)}
        scan = reference_rotate(deg, draw, lw, lh)
        check("a %d degree rotation covers every panel pixel" % deg,
              len(scan) == PIX,
              "%d distinct panel pixels were written, not %d - the map is "
              "not a bijection" % (len(scan), PIX))
        inside = all(0 <= sx < PW and 0 <= sy < PH for (sx, sy) in scan)
        check("a %d degree rotation stays inside the panel" % deg, inside,
              "at least one console pixel maps outside 0..%d by 0..%d"
              % (PW - 1, PH - 1))

    # 90 AND 270 MUST NOT BE THE SAME MAP.
    lw, lh = PH, PW
    draw = {(x, y): y * 1000 + x + 1 for y in range(lh) for x in range(lw)}
    a = reference_rotate(90, draw, lw, lh)
    b = reference_rotate(270, draw, lw, lh)
    check("90 and 270 are different rotations", a != b,
          "the two maps produce identical panels, so one of them is wrong")

    # AND 270 MUST BE 90 WITH THE PANEL TURNED ROUND:
    #     rot270(x, y) == 180-flip of rot90(x, y) on the panel
    ok = True
    for y in range(lh):
        for x in range(lw):
            sx90, sy90 = lh - 1 - y, x
            sx270, sy270 = y, lw - 1 - x
            if (sx270, sy270) != (PW - 1 - sx90, PH - 1 - sy90):
                ok = False
    check("270 is 90 with the panel turned round", ok,
          "at least one pixel breaks it, so the two rotations are not "
          "opposite quarter turns of the same picture")


def run_gate(compiler: str, source: pathlib.Path = SRC) -> int:
    with tempfile.TemporaryDirectory(prefix="dsiscreen-") as td:
        img = pathlib.Path(td) / "dsiscreen.img"
        build(compiler, source, img)
        _cpu, out, rc = run(img)

    fails: list = []
    c = Cases(fails)
    grade(out, rc, c)
    grade_scale(out, c)
    grade_pixels(c)

    print(out)
    print("a64_dsiscreen_check: %d harness cases over the probe's own tally"
          % c.count)
    if fails:
        print("FAIL %d of %d" % (len(fails), c.count))
        for f in fails:
            print("  " + f)
        return 1
    print("PASS %d of %d" % (c.count, c.count))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="PureMetalForge.exe (default: $PMF_COMPILER)")
    args = ap.parse_args(argv); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        ap.error("No compiler was named. Pass --compiler with the path to "
                 "PureMetalForge.exe, or set PMF_COMPILER.")
    return run_gate(args.compiler)


if __name__ == "__main__":
    raise SystemExit(main())
