#!/usr/bin/env python3
"""Desk gate: the 40-pin header's hardware PWM on the Pi 5 - RP1 PWM0 on
GPIO 12, 13, 18 and 19, through RaspberryPi4/Lib/rp1_pwm.pi4 (the one RP1
PWM file, which also drives the fan's PWM1) and the HwPwm* seam in
RaspberryPi4/Board/hw_pwm_rp1.pi4.

SILICON OWED. Asserted against a model written from the pinned sources:
the clock sequence on clk_pwm0 (drivers/clk/clk-rp1.c, vault Sources,
CLK_PWM0_CTRL $74 / DIV_INT $78 / DIV_FRAC $7C, re-derived below), the
channel registers of the right channel in PWM0's block in pwm-rp1.c's
order, NOT inverted, the pin on the right function with its pull left as
found, Duty/End on that channel, one pin at a time, PWM1 (the fan) and
clk_pwm1 untouched by a header pin, and the fan still on PWM1 channel 3.

Re-derived from the vault when present: clk-rp1.c's three clk_pwm0
offsets (and that they equal rp1_pwm.pi4's); rp1.dtsi rp1_pwm0 at
c0_40098000 (CPU $1F00098000); pinctrl-rp1.c PIN(12/13) pwm0 in column 0
and PIN(18/19) in column 3; rp1-peripherals.pdf's GPIO table PWM0[0..3]
on GPIO 12, 13, 18, 19 (text pulled from the pinned PDF's streams).

A mutant that does not build is an ERROR, not a kill.

  py -3 -B tools/a64/a64_pwm0_pi5_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys
import tempfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                                          # noqa: E402
from gpio_rp1_check import Rp1Gpio, IO_BANK0, PADS_BANK0      # noqa: E402

DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")
REL_TIMER = "RaspberryPi4/Lib/timer.pi4"
REL_GPIO = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_PWM = "RaspberryPi4/Lib/rp1_pwm.pi4"
INCLUDES = [REL_TIMER, REL_GPIO, REL_PWM]

PWM0, PWM1, CLOCKS = 0x1F_0009_8000, 0x1F_0009_C000, 0x1F_0001_8000
PINS = {12: (0, 0), 13: (1, 0), 18: (2, 3), 19: (3, 3)}      # pin: (channel, FUNCSEL)
FAN = 45
ARM = {"#RP1PWM0_CLK_CTRL": 0x74, "#RP1PWM0_CLK_DIV_INT": 0x78, "#RP1PWM0_CLK_DIV_FRAC": 0x7C}   # clk-rp1.c:70-73
CLK1 = (0x84, 0x88, 0x8C)                                        # clk_pwm1, pinned by rp1_pwm.pi4
CLK_HZ = 50_000_000
CTRL_DEFAULT, INVERT, SET_UPDATE = 0x101, 0x8, 0x80000000
ERR = {"CLOCK_OWED": -9, "PIN": -4, "INUSE": -6, "HZ": -2, "OK": 0}


def sources(src):
    if not (src / "Sources").is_dir():
        print("  SOURCES NOT CROSS-CHECKED")
        return
    dt = (src / "Sources" / "rp1.dtsi").read_text(encoding="utf-8")
    if not re.search(r"rp1_pwm0: pwm@98000 \{\s*compatible = \"raspberrypi,rp1-pwm\";\s*reg = <0xc0 0x40098000", dt):
        d.die("rp1.dtsi: rp1_pwm0 is no longer pwm@98000 at c0_40098000")
    ck = (src / "Sources" / "clk-rp1.c").read_text(encoding="utf-8")
    base = re.search(r"#define CLK_PWM0_OFFSET\s+0x([0-9a-fA-F]+)", ck)
    if not base:
        d.die("clk-rp1.c: no CLK_PWM0_OFFSET")
    b = int(base.group(1), 16)
    for name, add in (("CTRL", 0), ("DIV_INT", 4), ("DIV_FRAC", 8)):
        m = re.search(r"#define CLK_PWM0_%s\s+\(CLK_PWM0_OFFSET \+ 0x([0-9a-fA-F]+)\)" % name, ck)
        if not m or b + int(m.group(1), 16) != ARM["#RP1PWM0_CLK_" + name] or int(m.group(1), 16) != add:
            d.die("clk-rp1.c: CLK_PWM0_%s is not $%X" % (name, ARM["#RP1PWM0_CLK_" + name]))
    lib = d.source(REL_PWM, {})
    for k, v in ARM.items():
        if d.const_in(lib, k, REL_PWM) != v:
            d.die("rp1_pwm.pi4's %s is not clk-rp1.c's $%X" % (k, v))
    pc = (src / "Sources" / "pinctrl-rp1.c").read_text(encoding="utf-8")
    for pin, (_, fsel) in PINS.items():
        m = re.search(r"^\s*PIN\(%d,\s*([^)]*)\)" % pin, pc, re.M)
        cols = [c.strip() for c in m.group(1).split(",")]
        if cols.index("pwm0") != fsel:
            d.die("pinctrl-rp1.c: pwm0 is column %d on GPIO%d, the gate says %d" % (cols.index("pwm0"), pin, fsel))
    # The PDF's page streams, their TJ/Tj strings joined one per line - the
    # GPIO table then reads "12", "PWM0[0]", ... row by row.
    pdf = (src / "References" / "rp1-peripherals.pdf").read_bytes()
    strs = re.compile(rb"\(((?:\\.|[^\\)])*)\)")
    ops = re.compile(rb"\[(.*?)\]\s*TJ|\(((?:\\.|[^\\)])*)\)\s*Tj|(T\*|Td|TD|ET)", re.S)
    parts = []
    for s in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            body = zlib.decompress(s)
        except Exception:                                     # noqa: BLE001
            continue
        for mm in ops.finditer(body):
            if mm.group(1) is not None:
                parts.append(b"".join(strs.findall(mm.group(1))))
            elif mm.group(2) is not None:
                parts.append(mm.group(2))
            else:
                parts.append(b"\n")
    text = b"".join(parts).decode("latin-1")
    for pin, (ch, _) in PINS.items():
        # the table row: the pin number on its own line, then its functions
        # up to the next pin's number (a page number "12" is no row).
        found = False
        for m in re.finditer(r"\n%d\n" % pin, text):
            nxt = text.find("\n%d\n" % (pin + 1), m.end())
            row = text[m.end():nxt] if nxt > 0 else ""
            if 0 < len(row) < 400 and ("PWM0[%d]" % ch) in row:
                found = True
                break
        if not found:
            d.die("rp1-peripherals.pdf: GPIO%d's row does not show PWM0[%d]" % (pin, ch))
    print("  sources: clk_pwm0's registers, PWM0's base, the four pins' functions and channels "
          "re-derived from clk-rp1.c, rp1.dtsi, pinctrl-rp1.c and rp1-peripherals.pdf in %s" % src)


class Pwm:
    def __init__(self, base, clk_on):
        self.base, self.clk_on = base, clk_on
        self.r = {}
        self.log = []

    def __call__(self, off, value):
        if value is None:
            if off == 0 and self.r.get(0, 0) & SET_UPDATE and self.clk_on():
                self.r[0] &= ~SET_UPDATE                      # the clock domain takes it
                return self.r[0] | SET_UPDATE                 # ... after one more read
            return self.r.get(off, 0)
        if off not in (0,) and not (0x14 <= off < 0x54 and (off - 0x14) % 16 in (0, 4, 8, 12)):
            d.die("PWM block $%X: write to +$%X, not GLOBAL_CTRL or a channel register" % (self.base, off))
        self.log.append((off, value))
        self.r[off] = value


class Clocks:
    def __init__(self):
        self.r = {}
        self.log = []

    def on(self, ctrl):
        return (self.r.get(ctrl, 0) & 0xBE0) == (0x800 | (2 << 5))

    def __call__(self, off, value):
        if value is None:
            return self.r.get(off, 0)
        self.log.append((off, value))
        self.r[off] = value


def driver():
    return ("; a64_pwm0_pi5_check driver - generated\n" +
            "".join('XIncludeFile "%s"\n' % r for r in INCLUDES) +
            "Global gate_never.i\nIf gate_never = 1\n"
            "  Rp1PwmBeginPin(0, 0) : Rp1PwmDuty(0) : Rp1PwmEnd() : Rp1PwmPinValid(0) : Rp1PwmPin()\n"
            "  Rp1PwmOn() : Rp1PwmRange() : Rp1PwmHz() : Rp1PwmClockHz() : Rp1PwmBegin(0)\n"
            "EndIf\n")


def gate(cc, override, work):
    ov = dict(override)
    img, procs = d.build(cc, driver(), "pwm0_drv", work, ov, INCLUDES)
    n = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        n[0] += 1

    def machine():
        gpio = Rp1Gpio()
        clk = Clocks()
        p0 = Pwm(PWM0, lambda: clk.on(ARM["#RP1PWM0_CLK_CTRL"]))
        p1 = Pwm(PWM1, lambda: clk.on(CLK1[0]))

        def model(addr, size, value):
            if size != 4:
                d.die("a %d-byte access at $%X" % (size, addr))
            for blk, base, span in ((p0, PWM0, 0x100), (p1, PWM1, 0x100), (clk, CLOCKS, 0x1000)):
                if base <= addr < base + span:
                    return blk(addr - base, value)
            return gpio(addr, size, value)
        m = d.Machine(img, procs, model)
        return m, gpio, clk, p0, p1

    def ctrl(gpio, pin):
        first, off = (0, 0) if pin < 28 else ((28, 0x4000) if pin < 34 else (34, 0x8000))
        return gpio.reg.get(IO_BANK0 + off + (pin - first) * 8 + 4, 0x1F) & 0x1F

    m, gpio, clk, p0, p1 = machine()
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    for pin in range(0, 54):
        want = 1 if pin in PINS or pin == FAN else 0
        check(call("Rp1PwmPinValid", pin) == want, "Rp1PwmPinValid(%d) is not %d" % (pin, want))
    check(call("Rp1PwmBeginPin", 5, 25000) == ERR["PIN"], "GPIO5 was not refused as no PWM pin")
    check(call("Rp1PwmBeginPin", 12, 100000) == ERR["HZ"], "100 kHz (RANGE under 1000) accepted")
    for pin, (ch, fsel) in PINS.items():
        m, gpio, clk, p0, p1 = machine()
        call = lambda name, *a: m.signed(m.call(name, *a))             # noqa: E731
        pad0 = 0x5A                                    # pull-up (field 2), as a user might have left it
        gpio.reg[PADS_BANK0 + 4 + pin * 4] = pad0
        check(call("Rp1PwmBeginPin", pin, 25000) == ERR["OK"], "GPIO%d Begin failed" % pin)
        c, dv, fr = ARM["#RP1PWM0_CLK_CTRL"], ARM["#RP1PWM0_CLK_DIV_INT"], ARM["#RP1PWM0_CLK_DIV_FRAC"]
        check([o for o, _ in clk.log] == [c, dv, fr, c] and clk.log[1][1] == 1 and clk.log[2][1] == 0
              and clk.on(c), "GPIO%d: clk_pwm0 not (CTRL, DIV_INT 1, DIV_FRAC 0, CTRL|ENABLE) on the crystal: %r"
              % (pin, clk.log))
        rng = (1_000_000_000 // 25000 + 10) // 20
        co = 16 * ch
        want = [(0x14 + co, CTRL_DEFAULT), (0x20 + co, 0), (0x18 + co, rng), (0x14 + co, CTRL_DEFAULT),
                (0, 1 << ch), (0, (1 << ch) | SET_UPDATE)]
        check(p0.log == want, "GPIO%d: PWM0 writes %r, want %r (channel %d, not inverted)"
              % (pin, [(hex(o), hex(v)) for o, v in p0.log], [(hex(o), hex(v)) for o, v in want], ch))
        check(not p1.log and not any(o in CLK1 for o, _ in clk.log), "GPIO%d: PWM1 or clk_pwm1 touched" % pin)
        check(ctrl(gpio, pin) == fsel, "GPIO%d is FUNCSEL %d, want %d" % (pin, ctrl(gpio, pin), fsel))
        pad = gpio.reg.get(PADS_BANK0 + 4 + pin * 4)
        check((pad >> 2) & 3 == (pad0 >> 2) & 3, "GPIO%d's pull was changed" % pin)
        check(call("Rp1PwmPin") == pin and call("Rp1PwmHz") == CLK_HZ // rng, "GPIO%d: pin/Hz readers" % pin)
        p0.log.clear()
        check(call("Rp1PwmDuty", 250) == 0 and p0.log == [(0x20 + co, (rng * 250 + 500) // 1000)],
              "GPIO%d: Duty did not write channel %d's DUTY" % (pin, ch))
        other = [p for p in PINS if p != pin][0]
        check(call("Rp1PwmBeginPin", other, 25000) == ERR["INUSE"], "a second header pin was not refused while one is on")
        p0.log.clear()
        check(call("Rp1PwmEnd") == 0 and p0.log == [(0x20 + co, rng)], "GPIO%d: End did not leave DUTY = RANGE" % pin)

    # the fan still goes to PWM1 channel 3, inverted, never PWM0
    m, gpio, clk, p0, p1 = machine()
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    check(call("Rp1PwmBegin", 24058) == 0 and not p0.log and (0x44, CTRL_DEFAULT | INVERT) in p1.log
          and ctrl(gpio, FAN) == 0, "the fan did not start on PWM1 channel 3, inverted")
    return n[0]


MUTATIONS = [
    (REL_PWM, "GPIO18 on PWM0 channel 0", "    Case #RP1PWM_HDR_GPIO2\n      rp1pwm_pChan = 2", "    Case #RP1PWM_HDR_GPIO2\n      rp1pwm_pChan = 0"),
    (REL_PWM, "GPIO18/19 on function 0 like 12/13", "      rp1pwm_pChan = 2\n      rp1pwm_pFsel = 3", "      rp1pwm_pChan = 2\n      rp1pwm_pFsel = 0"),
    (REL_PWM, "PWM0 at PWM1's base", "#RP1PWM0_BASE  = $1F00098000", "#RP1PWM0_BASE  = $1F0009C000"),
    (REL_PWM, "the header inverted like the fan", "    Case #RP1PWM_HDR_GPIO0\n      rp1pwm_pChan = 0", "    Case #RP1PWM_HDR_GPIO0\n      rp1pwm_pInv = 1\n      rp1pwm_pChan = 0"),
    (REL_PWM, "clk_pwm0 programmed at clk_pwm1's CTRL", "#RP1PWM0_CLK_CTRL     = $74", "#RP1PWM0_CLK_CTRL     = $84"),
    (REL_PWM, "clk_pwm0's divider at the wrong offset", "#RP1PWM0_CLK_DIV_INT  = $78", "#RP1PWM0_CLK_DIV_INT  = $88"),
    (REL_PWM, "a header pin on the fan's clock", "    c = rp1pwm_Clock(#RP1PWM0_CLK_CTRL, #RP1PWM0_CLK_DIV_INT, #RP1PWM0_CLK_DIV_FRAC)",
     "    c = rp1pwm_Clock(#RP1PWM_CLK_CTRL, #RP1PWM_CLK_DIV_INT, #RP1PWM_CLK_DIV_FRAC)"),
    (REL_PWM, "a second pin not refused", "  If rp1pwm_on <> 0 And pin <> rp1pwm_pin\n", "  If 0\n"),
    (REL_PWM, "the header pad pulled down like the fan", "  If pin = #RP1PWM_FAN_GPIO\n    Rp1PinPull(#RP1PWM_FAN_GPIO", "  If 1\n    Rp1PinPull(pin"),
    (REL_PWM, "Duty on the fan's channel whatever the pin", "  PokeL(rp1pwm_base + $20 + rp1pwm_coff, rp1pwm_counts)", "  PokeL(#RP1PWM_BASE + #RP1PWM_CHAN_DUTY, rp1pwm_counts)"),
    (REL_PWM, "GPIO13 not a PWM pin", "#RP1PWM_HDR_GPIO1 = 13", "#RP1PWM_HDR_GPIO1 = 14"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    sources(pathlib.Path(a.sources))
    top = pathlib.Path(tempfile.mkdtemp(prefix="pwm0-"))
    try:
        try:
            n = gate(cc, {}, top / "g")
        except d.GateFail as exc:
            print("a64_pwm0_pi5_check: FAIL - %s" % exc)
            return 1
        print("a64_pwm0_pi5_check: PASS - %d checks" % n)
        if a.mutate:
            bad = 0
            for i, (rel, why, old, new) in enumerate(MUTATIONS):
                text = (d.ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
                if text.count(old) != 1:
                    print("  %2d  ERROR     %s (matched %d times)" % (i, why, text.count(old)))
                    bad += 1
                    continue
                ov = {rel: text.replace(old, new)}
                try:
                    gate(cc, ov, top / ("m%02d" % i))
                except d.GateFail as exc:
                    msg = str(exc).replace("\n", " ")
                    if "would not build" in msg:
                        print("  %2d  ERROR     %s (did not build)" % (i, why))
                        bad += 1
                        continue
                    print("  %2d  KILLED    %s (%s)" % (i, why, msg[:100]))
                    continue
                print("  %2d  SURVIVED  %s" % (i, why))
                bad += 1
            print("a64_pwm0_pi5_check mutations: %d killed, %d not" % (len(MUTATIONS) - bad, bad))
            if bad:
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
