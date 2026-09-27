#!/usr/bin/env python3
"""Desk gate: the status-LED and power-button seams (HwLedAct, HwLedPwr,
HwPwrButton - Anvil/Hal/hal.pbi, approved by the owner 2026-09-27) as
RaspberryPi4/Board/hw_led.pi4 implements them, on BOTH chips.

SILICON OWED. Each chip's build runs on tools/a64/a64_interp.py against a
model of the hardware written from the sources, not from the library:

  Pi 5 (-t pi5)  gio/gio_aon: tools/a64/gio_check.py's model (gpio-brcmstb.c,
                 the pinned DTBs) - ACT is gio_aon 9 active low, the button
                 gio 20 active low; RP1 GPIO44 (PWR, active low):
                 tools/a64/gpio_rp1_check.py's model.
  Pi 4 (-t pi4)  BCM2711 GPIO at $FE200000 (BCM2711 ARM Peripherals ch.5:
                 GPFSEL4 bits 8:6 for pin 42, GPSET1 $20, GPCLR1 $2C, GPLEV1
                 $38); ACT is GPIO 42 ACTIVE HIGH (PureBasicCode Reference
                 rpi-6.12.y_bcm2711-rpi-4-b.dts:163-164, re-read below).

Asserted: nothing is touched before the first call; the LED is taken
value-first then direction (never a flash); lit/dark follow the polarity;
a level that does not follow is #HW_LED_STUCK; the Pi 4's PWR LED and
button answer NONE and touch nothing; the Pi 5 button reads 1 held / 0
up / #HW_BTN_NONE when its line is an output, and never writes.

  py -3 -B tools/a64/a64_led_button_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                                          # noqa: E402
from gpio_rp1_check import Rp1Gpio                            # noqa: E402
from gio_check import Gio, PINNED as GIO_PINNED               # noqa: E402

PI4_DTS = pathlib.Path(r"C:\Users\ajtaj\Desktop\Github\PureBasicCode\OpenGl Work\ArduinoBasic"
                       r"\RaspberryPi4\Reference\rpi-6.12.y_bcm2711-rpi-4-b.dts")
REL_HAL = "Anvil/Hal/hal.pbi"
REL_LED = "RaspberryPi4/Board/hw_led.pi4"
REL_ACT = "RaspberryPi4/Lib/led_act.pi4"
REL_GIO = "RaspberryPi4/Lib/gio.pi4"
REL_RP1 = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_GPIO = "RaspberryPi4/Lib/gpio.pi4"
HAL_NAMES = ("#HW_LED_OK", "#HW_LED_NONE", "#HW_LED_STUCK", "#HW_BTN_NONE")
PWR_BIT = 1 << (44 - 34)
GPIO4 = 0xFE20_0000
PI4_ACT = 42


def consts(override):
    hal = d.source(REL_HAL, override)
    return {n: d.const_in(hal, n, REL_HAL) for n in HAL_NAMES}


def driver(includes, override, calls):
    H = consts(override)
    return ("; a64_led_button_check driver - generated\n" +
            "".join("%s = %d\n" % (k, v) for k, v in H.items()) +
            "".join('XIncludeFile "%s"\n' % r for r in includes) +
            "Global gate_never.i\nIf gate_never = 1\n  " + calls + "\nEndIf\n")


def build_pi4(cc, text, work, override, includes):
    """pi5_desk.build, with -t pi4 (the harness is otherwise target-neutral)."""
    work.mkdir(parents=True, exist_ok=True)
    for rel in includes:
        marker = 'XIncludeFile "%s"' % rel
        if rel in override:
            cp = work / ("mut_" + pathlib.Path(rel).name)
            cp.write_text(override[rel], encoding="utf-8")
            text = text.replace(marker, 'XIncludeFile "%s"' % cp.resolve().as_posix())
    src = work / "led4.pi4"
    src.write_text(text, encoding="utf-8")
    img = work / "led4.img"
    r = subprocess.run([cc, "--compile", str(src), "-t", "pi4", "--entry-returns",
                        "--load-addr", hex(d.LOAD), "--stack-addr", hex(d.STACK), "-o", str(img)],
                       cwd=str(d.ROOT), env=dict(os.environ, PMF_ROOT=str(d.ROOT)),
                       capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        d.die("the driver would not build:\n" + r.stdout[-2500:])
    procs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = d.LOAD + int(f[1])
    return img, procs


class StuckGio(Gio):
    """gio_aon whose line 9 will not become an output (IODIR bit 9 stays 1)."""

    def __call__(self, addr, size, value):
        if value is not None and addr - self.base == 8:
            value |= 1 << 9
        return Gio.__call__(self, addr, size, value)


class Gpio2711:
    """BCM2711 GPIO: FSEL, SET/CLR latch, LEV = latch for outputs, pad else."""

    def __init__(self, stuck=None):
        self.fsel = {i: 0 for i in range(6)}
        self.latch = 0
        self.pad = 0
        self.stuck = stuck
        self.log = []

    def out(self, pin):
        return (self.fsel[pin // 10] >> (3 * (pin % 10))) & 7 == 1

    def lev(self):
        v = 0
        for pin in range(58):
            if self.out(pin):
                v |= self.latch & (1 << pin)
            else:
                v |= self.pad & (1 << pin)
        if self.stuck is not None:
            v = (v & ~(1 << PI4_ACT)) | (self.stuck << PI4_ACT)
        return v

    def __call__(self, addr, size, value):
        off = addr - GPIO4
        if size != 4:
            d.die("a %d-byte GPIO access at +$%X" % (size, off))
        if value is None:
            if off < 0x18 and off % 4 == 0:
                return self.fsel[off // 4]
            if off in (0x34, 0x38):
                return (self.lev() >> (32 * (off == 0x38))) & 0xFFFFFFFF
            d.die("GPIO read at +$%X" % off)
        self.log.append((off, value))
        if off < 0x18 and off % 4 == 0:
            self.fsel[off // 4] = value
        elif off in (0x1C, 0x20):
            self.latch |= value << (32 * (off == 0x20))
        elif off in (0x28, 0x2C):
            self.latch &= ~(value << (32 * (off == 0x2C)))
        else:
            d.die("GPIO write at +$%X" % off)


def gate(cc, override, work):
    H = consts(override)
    n = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        n[0] += 1

    if PI4_DTS.exists():
        dts = PI4_DTS.read_text(encoding="utf-8")
        check(re.search(r"&led_act \{\s*gpios = <&gpio 42 GPIO_ACTIVE_HIGH>;", dts) is not None,
              "the Pi 4 DTS no longer puts the ACT LED on GPIO 42 active high")

    # ---------------- Pi 5 --------------------------------------------------
    inc5 = [REL_RP1, REL_GIO, REL_ACT, REL_LED]
    img, procs = d.build(cc, driver(inc5, override, "HwLedAct(0) : HwLedPwr(0) : HwPwrButton()"),
                         "led5", work / "p5", override, inc5)

    def m5(stuck=False):
        aon = (StuckGio if stuck else Gio)(GIO_PINNED["aon"][0], "gio_aon")
        blocks = {0: Gio(GIO_PINNED["main"][0], "gio"), 1: aon}
        rp1 = Rp1Gpio()

        def model(addr, size, value):
            for g in blocks.values():
                if g.owns(addr):
                    return g(addr, size, value)
            return rp1(addr, size, value)
        m = d.Machine(img, procs, model)
        return m, blocks, rp1
    m, g, rp1 = m5()
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    aon, main = g[1], g[0]
    check(call("HwLedAct", 1) == H["#HW_LED_OK"], "Pi 5: HwLedAct(1) failed")
    check([r for _, r, _ in aon.log][:2] == ["DATA", "IODIR"], "Pi 5: ACT taken direction-first (a flash)")
    check(not aon.r[(0, 4)] & (1 << 9) and not aon.r[(0, 8)] & (1 << 9), "Pi 5: ACT lit is not DATA low, output")
    check(call("HwLedAct", 0) == H["#HW_LED_OK"] and aon.r[(0, 4)] & (1 << 9), "Pi 5: ACT dark is not DATA high")
    check(not main.log, "Pi 5: the LED touched the main gio")
    check(call("HwLedPwr", 1) == H["#HW_LED_OK"] and not rp1.reg.get(0x1F_000E_0000 + 0x8000, 0) & PWR_BIT
          and rp1.reg.get(0x1F_000E_0000 + 0x8004, 0) & PWR_BIT, "Pi 5: PWR lit is not GPIO44 an output, low")
    check(call("HwLedPwr", 0) == H["#HW_LED_OK"] and rp1.reg.get(0x1F_000E_0000 + 0x8000, 0) & PWR_BIT,
          "Pi 5: PWR dark is not GPIO44 high")
    main.r[(0, 8)] |= 1 << 20                      # an input, as the firmware leaves it
    main.pad[0] = 0xFFFFFFFF & ~(1 << 20)
    before = len(main.log)
    check(call("HwPwrButton") == 1, "Pi 5: the button held did not read 1")
    main.pad[0] = 0xFFFFFFFF
    check(call("HwPwrButton") == 0, "Pi 5: the button up did not read 0")
    main.r[(0, 8)] &= ~(1 << 20)
    check(call("HwPwrButton") == H["#HW_BTN_NONE"], "Pi 5: a button line that is an output was read")
    check(len(main.log) == before, "Pi 5: the button read wrote a register")
    # A pin that will not become an output: the seam must say STUCK, not OK.
    m, g, rp1 = m5(stuck=True)
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    g[1].r[(0, 8)] |= 1 << 9
    check(call("HwLedAct", 1) == H["#HW_LED_STUCK"], "Pi 5: an ACT pin that stays an input was reported lit")

    # ---------------- Pi 4 --------------------------------------------------
    inc4 = [REL_GPIO, REL_LED]
    img4, procs4 = build_pi4(cc, driver(inc4, override, "HwLedAct(0) : HwLedPwr(0) : HwPwrButton()"),
                             work / "p4", override, inc4)

    def m4(stuck=None):
        gp = Gpio2711(stuck)
        m = d.Machine(img4, procs4, gp, windows=[(GPIO4, GPIO4 + 0x100)])
        return m, gp
    m, gp = m4()
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    check(call("HwLedPwr", 1) == H["#HW_LED_NONE"] and call("HwPwrButton") == H["#HW_BTN_NONE"] and not gp.log,
          "Pi 4: the PWR LED / button did not answer NONE, or touched a register")
    check(call("HwLedAct", 1) == H["#HW_LED_OK"], "Pi 4: HwLedAct(1) failed")
    offs = [o for o, _ in gp.log]
    check(offs and offs[0] == 0x20 and gp.log[0][1] == 1 << (PI4_ACT - 32) and 0x10 in offs
          and offs.index(0x10) > 0, "Pi 4: ACT not set HIGH (GPSET1 bit 10) before becoming an output: %r"
          % [(hex(o), hex(v)) for o, v in gp.log])
    check(gp.out(PI4_ACT) and gp.latch & (1 << PI4_ACT), "Pi 4: ACT lit is not GPIO 42 an output driving high")
    fsel_changed = gp.fsel[4] ^ (1 << 6)
    check(fsel_changed == 0 and all(v == 0 for k, v in gp.fsel.items() if k != 4),
          "Pi 4: another pin's function moved: %r" % gp.fsel)
    check(call("HwLedAct", 0) == H["#HW_LED_OK"] and not gp.latch & (1 << PI4_ACT), "Pi 4: ACT dark is not low")
    m, gp = m4(stuck=0)
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    check(call("HwLedAct", 1) == H["#HW_LED_STUCK"], "Pi 4: a pad stuck low was reported as lit")
    return n[0]


MUTATIONS = [
    (REL_LED, "Pi 4 ACT on GPIO 41", "#PI4_LED_ACT_PIN = 42 ", "#PI4_LED_ACT_PIN = 41 "),
    (REL_LED, "Pi 4 direction before value", "    DigitalWrite(#PI4_LED_ACT_PIN, level)\n    PinOutput(#PI4_LED_ACT_PIN)\n",
     "    PinOutput(#PI4_LED_ACT_PIN)\n    DigitalWrite(#PI4_LED_ACT_PIN, level)\n"),
    (REL_LED, "Pi 4 active low", "  level = 0\n  If on <> 0\n    level = 1\n  EndIf", "  level = 1\n  If on <> 0\n    level = 0\n  EndIf"),
    (REL_LED, "Pi 4 readback skipped", "  If PinModeGet(#PI4_LED_ACT_PIN) <> #PIN_OUTPUT Or DigitalRead(#PI4_LED_ACT_PIN) <> level\n",
     "  If 0\n"),
    (REL_LED, "Pi 5 ACT never taken", "  If led_act_begun = 0\n    c = LedActBegin()", "  If led_act_begun = 99\n    c = LedActBegin()"),
    (REL_LED, "Pi 5 PWR never taken", "  If led_pwr_begun = 0\n    c = LedPwrBegin()", "  If led_pwr_begun = 99\n    c = LedPwrBegin()"),
    (REL_LED, "Pi 5 button inverted", "  ProcedureReturn b\nEndProcedure", "  ProcedureReturn 1 - b\nEndProcedure"),
    (REL_LED, "Pi 5 a failed set reported OK", "  If c = #LED_ACT_OK\n    ProcedureReturn #HW_LED_OK\n  EndIf\n  ProcedureReturn #HW_LED_STUCK",
     "  ProcedureReturn #HW_LED_OK"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="ledbtn-"))
    try:
        try:
            n = gate(cc, {}, top / "g")
        except d.GateFail as exc:
            print("a64_led_button_check: FAIL - %s" % exc)
            return 1
        print("a64_led_button_check: PASS - %d checks" % n)
        if a.mutate:
            bad = 0
            for i, (rel, why, old, new) in enumerate(MUTATIONS):
                text = (d.ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
                if text.count(old) != 1:
                    print("  %2d  ERROR     %s (matched %d times)" % (i, why, text.count(old)))
                    bad += 1
                    continue
                try:
                    gate(cc, {rel: text.replace(old, new)}, top / ("m%02d" % i))
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
            print("a64_led_button_check mutations: %d killed, %d not" % (len(MUTATIONS) - bad, bad))
            if bad:
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
