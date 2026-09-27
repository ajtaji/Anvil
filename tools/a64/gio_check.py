#!/usr/bin/env python3
"""Desk gate: RaspberryPi4/Lib/gio.pi4 - the BCM2712's gio and gio_aon
(brcmstb GPIO) blocks, -t pi5.

SILICON OWED. The model is written from the pinned sources (vault
"Raspberry Pi 5/Sources", raspberrypi/linux 7e030b60792d), not from the
library:
  gpio-brcmstb.c:15-36    eight 32-bit registers per bank, $20 per bank,
                          ODEN +0, DATA +4, IODIR +8
  gpio-brcmstb.c:59-62, 700-701   pin = bank*32 + bit, bit < bank width
  gpio-brcmstb.c:670-681  IODIR 0 = output, 1 = input; DATA is the only
                          data register (no set/clear)
and the three pinned DTBs (re-derived below): gio at $107D508500 with bank
widths <32 4>, gio_aon at $107D517C00 with <17 6> (C0) or <15 6> (D0, D) -
the library must take the narrower, 15 - and the consumers -
wl-on-reg <&gio 28 HIGH>, pwr_button <&gio 20 LOW>, led-act <&gio_aon 9
LOW>, sd-vcc-reg <&gio_aon 4>, sd-io-1v8-reg <&gio_aon 3>.

THE MODEL: both blocks, two banks each. Every other bit of every register
starts at a live pattern and must never change (the banks carry RP1_RUN,
SD power, the PMIC interrupt) - except an input's DATA latch taking its
pad level, which a DATA read-modify-write cannot avoid (see changed()); DATA reads back the latch for outputs and
the pad for inputs; any access outside the eight named registers, or to a
bank past the block, is refused; every write is logged in order.

Asserted: which pins exist (and that a refused pin touches nothing); the
bank-1 addressing; GioOutput writes DATA before IODIR, one bit each;
GioWrite leaves the direction; GioInput; reads of inputs and outputs; the
power-button read (active low, never writes, -1 when the pin is an
output); led_act.pi4's ACT LED through this file. sdio.pi4's WL_ON cold
start through it is a64_sdio_pi5_check.py's and a64_wifi_pi5_check.py's.

  py -3 -B tools/a64/gio_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                               # noqa: E402

sys.path.insert(0, str(d.ROOT / "RaspberryPi5" / "Boot"))

DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")
TREES = ("bcm2712-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb")
REL_GIO = "RaspberryPi4/Lib/gio.pi4"
REL_GPIO = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_LED = "RaspberryPi4/Lib/led_act.pi4"
INCLUDES = [REL_GPIO, REL_GIO, REL_LED]

PINNED = {"main": (0x10_7D50_8500, (32, 4)), "aon": (0x10_7D51_7C00, (15, 6)),
          "wl_on": ("main", 28, 0), "pwr": ("main", 20, 1), "act": ("aon", 9, 1)}
LIVE = 0xA5C3_5A3C


def sources(src):
    k = dict(PINNED)
    if not (src / "Boot staging").is_dir():
        print("  SOURCES NOT CROSS-CHECKED - PINNED table only")
        return k
    from dtb_contract import parse, strings, mapped_reg
    narrowest = {}
    for name in TREES:
        n = parse((src / "Boot staging" / name).read_bytes())
        ph = {}
        for key, path in (("main", "/soc@107c000000/gpio@7d508500"), ("aon", "/soc@107c000000/gpio@7d517c00")):
            v = n.get(path)
            if v is None or "brcm,brcmstb-gpio" not in strings(v["compatible"]):
                d.die("%s: %s is not a brcmstb gpio" % (name, path))
            w = v["brcm,gpio-bank-widths"]
            widths = tuple(int.from_bytes(w[i:i + 4], "big") for i in range(0, len(w), 4))
            if mapped_reg(n, path) != k[key][0]:
                d.die("%s: %s is at $%X, PINNED says $%X" % (name, path, mapped_reg(n, path), k[key][0]))
            prev = narrowest.get(key, widths)
            narrowest[key] = tuple(min(a, b) for a, b in zip(prev, widths))
            ph[int.from_bytes(v["phandle"], "big")] = key
        for key, path, prop in (("wl_on", "/wl-on-reg", "gpio"), ("pwr", "/pwr_button/pwr", "gpios"),
                                ("act", "/leds/led-act", "gpios")):
            raw = n[path][prop]
            got = (ph.get(int.from_bytes(raw[0:4], "big")), int.from_bytes(raw[4:8], "big"),
                   int.from_bytes(raw[8:12], "big"))
            if got != k[key]:
                d.die("%s: %s %s is %r, PINNED says %r" % (name, path, prop, got, k[key]))
    for key in ("main", "aon"):
        if narrowest[key] != k[key][1]:
            d.die("%s: the narrowest bank widths over the three trees are %r, PINNED says %r"
                  % (key, narrowest[key], k[key][1]))
    print("  sources: both blocks, their bank widths and the WL_ON / power button / ACT lines "
          "re-derived from the three DTBs in %s - all agree" % src)
    return k


class Gio:
    """One brcmstb block: two banks of ODEN/DATA/IODIR, live neighbours."""

    def __init__(self, base, name):
        self.base, self.name = base, name
        self.r = {(b, o): LIVE ^ (b * 0x1111) ^ o for b in (0, 1) for o in (0, 4, 8)}
        self.r0 = dict(self.r)
        self.pad = {0: 0xFFFFFFFF, 1: 0xFFFFFFFF}
        self.log = []

    def owns(self, addr):
        return self.base <= addr < self.base + 0x40

    def __call__(self, addr, size, value):
        if size != 4:
            d.die("%s: a %d-byte access at $%X" % (self.name, size, addr))
        off = addr - self.base
        bank, reg = off // 0x20, off % 0x20
        if reg not in (0, 4, 8):
            d.die("%s: bank %d register +$%X is not ODEN/DATA/IODIR" % (self.name, bank, reg))
        if value is None:
            if reg == 4:
                io = self.r[(bank, 8)]
                return (self.r[(bank, 4)] & ~io | self.pad[bank] & io) & 0xFFFFFFFF
            return self.r[(bank, reg)]
        self.log.append((bank, {0: "ODEN", 4: "DATA", 8: "IODIR"}[reg], value & 0xFFFFFFFF))
        self.r[(bank, reg)] = value & 0xFFFFFFFF

    def changed(self):
        """{(bank, reg): changed-bits mask} against the live start - less the
        one change a DATA read-modify-write cannot avoid: an INPUT's latch
        bit taking the pad level the read returned (gpio_generic's shadow
        does the same when it is first loaded). Harmless while the line
        stays an input; whether DATA reads back latch or pad for an input is
        a silicon question."""
        out = {}
        for k in self.r:
            diff = self.r[k] ^ self.r0[k]
            if k[1] == 4:
                inp = self.r0[(k[0], 8)] & self.r[(k[0], 8)]
                diff &= ~(inp & ~(self.r[k] ^ self.pad[k[0]]))
            if diff:
                out[k] = diff
        return out


def driver():
    return ("; gio_check driver - generated\n" +
            "".join('XIncludeFile "%s"\n' % r for r in INCLUDES) +
            "Global gate_never.i\nIf gate_never = 1\n"
            "  GioValid(0, 0) : GioRead(0, 0) : GioIsOutput(0, 0) : GioWrite(0, 0, 0) : GioOutput(0, 0, 0)\n"
            "  GioInput(0, 0) : GioPwrButton() : LedActBegin() : LedActSet(0) : LedActLit()\n"
            "EndIf\n")


def gate(cc, override, workdir, K):
    img, procs = d.build(cc, driver(), "gio_drv", workdir, override, INCLUDES)
    n = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        n[0] += 1

    def machine():
        blocks = {0: Gio(K["main"][0], "gio"), 1: Gio(K["aon"][0], "gio_aon")}

        def model(addr, size, value):
            for g in blocks.values():
                if g.owns(addr):
                    return g(addr, size, value)
            d.die("an access at $%X - not gio or gio_aon" % addr)
        m = d.Machine(img, procs, model)
        return m, blocks

    m, g = machine()
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    B = {"main": 0, "aon": 1}

    # --- which lines exist ---------------------------------------------
    for key in ("main", "aon"):
        w0, w1 = K[key][1]
        for pin in list(range(-1, 66)):
            want = 1 if (0 <= pin < w0 or 32 <= pin < 32 + w1) else 0
            check(call("GioValid", B[key], pin) == want, "GioValid(%s, %d) is not %d" % (key, pin, want))
    check(call("GioValid", 2, 0) == 0, "a third block accepted")
    for f, a in (("GioRead", (0, 40)), ("GioIsOutput", (1, 20)), ("GioWrite", (0, 36, 1)),
                 ("GioOutput", (1, 17, 0)), ("GioInput", (0, 64))):
        check(call(f, *a) in (0, -1), "%s%r on a line that does not exist did not refuse" % (f, a))
    check(not g[0].log and not g[1].log, "a refused line was written")

    # --- output: value, then direction, one bit each; bank 1 addressing ---
    for key, pin in (("main", 28), ("aon", 9), ("main", 33), ("aon", 34)):
        m, g = machine()
        call = lambda name, *a: m.signed(m.call(name, *a))             # noqa: E731
        blk, bank, bit = g[B[key]], pin >> 5, 1 << (pin & 31)
        for level in (0, 1):
            blk.log.clear()
            check(call("GioOutput", B[key], pin, level) == 1, "GioOutput(%s, %d, %d)" % (key, pin, level))
            names = [(b, r) for b, r, v in blk.log]
            check(names == [(bank, "DATA"), (bank, "IODIR")],
                  "GioOutput(%s %d) wrote %r - want DATA then IODIR of bank %d" % (key, pin, names, bank))
            check(call("GioIsOutput", B[key], pin) == 1 and call("GioRead", B[key], pin) == level,
                  "%s %d is not an output at %d" % (key, pin, level))
        ch = blk.changed()
        check(set(ch) <= {(bank, 4), (bank, 8)} and all(v & ~bit == 0 for v in ch.values()),
              "%s %d: bits other than %d moved: %r" % (key, pin, pin & 31, {k: hex(v) for k, v in ch.items()}))
        check(not g[1 - B[key]].log, "%s %d: the other block was touched" % (key, pin))
        blk.log.clear()
        check(call("GioWrite", B[key], pin, 0) == 1 and [r for _, r, _ in blk.log] == ["DATA"],
              "GioWrite touched more than DATA")
        check(call("GioInput", B[key], pin) == 1 and [r for _, r, _ in blk.log] == ["DATA", "IODIR"]
              and call("GioIsOutput", B[key], pin) == 0, "GioInput")
        blk.pad[bank] = 0xFFFFFFFF & ~bit
        check(call("GioRead", B[key], pin) == 0, "an input read the latch, not the pad")
        blk.pad[bank] = 0xFFFFFFFF
        check(call("GioRead", B[key], pin) == 1, "an input high read low")

    # --- the power button -----------------------------------------------
    m, g = machine()
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    _, ppin, _ = K["pwr"]
    blk = g[0]
    blk.r[(0, 8)] |= 1 << ppin                     # an input, as the firmware leaves it
    blk.r0 = dict(blk.r)
    blk.pad[0] = 0xFFFFFFFF & ~(1 << ppin)
    check(call("GioPwrButton") == 1, "the button held (pad low) did not read pressed")
    blk.pad[0] = 0xFFFFFFFF
    check(call("GioPwrButton") == 0, "the button released (pad high) read pressed")
    blk.pad[0] = 0xFFFFFFFF & ~(1 << (ppin + 1))
    check(call("GioPwrButton") == 0, "the neighbouring pin's level was read as the button")
    blk.r[(0, 8)] &= ~(1 << ppin)
    check(call("GioPwrButton") == -1, "a button pin that is an output was read as the button")
    check(not blk.log and not g[1].log, "the button read wrote a register")

    # --- the ACT LED through gio.pi4 (led_act.pi4) ------------------------
    m, g = machine()
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    _, apin, _ = K["act"]
    abit = 1 << apin
    check(call("LedActBegin") == 0, "LedActBegin failed")
    check([(b, r) for b, r, _ in g[1].log] == [(0, "DATA"), (0, "IODIR")] and g[1].r[(0, 4)] & abit,
          "the ACT LED was not taken dark (DATA high) before becoming an output")
    check(call("LedActSet", 1) == 0 and not g[1].r[(0, 4)] & abit, "ACT not lit by a low")
    check(call("LedActSet", 0) == 0 and g[1].r[(0, 4)] & abit, "ACT not dark by a high")
    ch = g[1].changed()
    check(all(v & ~abit == 0 for v in ch.values()) and not g[0].log, "the ACT LED moved another line")
    return n[0]


MUTATIONS = [
    (REL_GIO, "direction before value", "  If GioWrite(block, pin, level) = 0\n    ProcedureReturn 0\n  EndIf\n  a = gio_Reg(block, pin, #GIO_IODIR)\n  PokeL(a, (PeekN(a) & $FFFFFFFF) & (~gio_Bit(pin)))\n",
     "  a = gio_Reg(block, pin, #GIO_IODIR)\n  PokeL(a, (PeekN(a) & $FFFFFFFF) & (~gio_Bit(pin)))\n  If GioWrite(block, pin, level) = 0\n    ProcedureReturn 0\n  EndIf\n"),
    (REL_GIO, "gio_aon at the main gio's address", "#GIO_AON_BASE  = $107D517C00", "#GIO_AON_BASE  = $107D508500"),
    (REL_GIO, "banks $10 apart", "#GIO_BANK_BYTES = $20", "#GIO_BANK_BYTES = $10"),
    (REL_GIO, "IODIR sense inverted", "  If (PeekN(gio_Reg(block, pin, #GIO_IODIR)) & gio_Bit(pin)) = 0\n    ProcedureReturn 1",
     "  If (PeekN(gio_Reg(block, pin, #GIO_IODIR)) & gio_Bit(pin)) <> 0\n    ProcedureReturn 1"),
    (REL_GIO, "a whole-register DATA write", "  PokeL(a, v)\n  ProcedureReturn 1", "  PokeL(a, gio_Bit(pin))\n  ProcedureReturn 1"),
    (REL_GIO, "the main gio's second bank 22 wide (the dtsi, not the Pi 5)", "#GIO_MAIN_W1 = 4", "#GIO_MAIN_W1 = 22"),
    (REL_GIO, "gio_aon bank 0 17 wide (the C0 tree only)", "#GIO_AON_W0  = 15", "#GIO_AON_W0  = 17"),
    (REL_GIO, "the power button active high", "  If GioRead(#GIO_MAIN, #GIO_PIN_PWR_BUTTON) = 0\n    ProcedureReturn 1",
     "  If GioRead(#GIO_MAIN, #GIO_PIN_PWR_BUTTON) = 1\n    ProcedureReturn 1"),
    (REL_GIO, "the power button on gio 21", "#GIO_PIN_PWR_BUTTON = 20", "#GIO_PIN_PWR_BUTTON = 21"),
    (REL_GIO, "an output pin read as the button", "  If GioIsOutput(#GIO_MAIN, #GIO_PIN_PWR_BUTTON) <> 0\n    ProcedureReturn -1\n  EndIf\n", ""),
    (REL_GIO, "an invalid pin not refused", "  If bit >= w\n    ProcedureReturn 0", "  If bit >= 32\n    ProcedureReturn 0"),
    (REL_LED, "ACT on the main gio", "  GioOutput(#GIO_AON, #LED_ACT_PIN, 1)", "  GioOutput(#GIO_MAIN, #LED_ACT_PIN, 1)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    K = sources(pathlib.Path(a.sources))
    top = pathlib.Path(tempfile.mkdtemp(prefix="gio-"))
    try:
        try:
            n = gate(cc, {}, top / "gate", K)
        except d.GateFail as exc:
            print("gio_check: FAIL - %s" % exc)
            return 1
        print("gio_check: PASS - %d checks" % n)
        if a.mutate:
            bad = 0
            for i, (rel, why, old, new) in enumerate(MUTATIONS):
                text = (d.ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
                if text.count(old) != 1:
                    print("  %2d  ERROR     %s: %s (matched %d times)" % (i, rel, why, text.count(old)))
                    bad += 1
                    continue
                try:
                    gate(cc, {rel: text.replace(old, new)}, top / ("m%02d" % i), K)
                except d.GateFail as exc:
                    msg = str(exc).replace("\n", " ")
                    if "would not build" in msg:
                        print("  %2d  ERROR     %s: %s (did not build)" % (i, rel, why))
                        bad += 1
                        continue
                    print("  %2d  KILLED    %s: %s (%s)" % (i, rel, why, msg[:100]))
                    continue
                print("  %2d  SURVIVED  %s: %s" % (i, rel, why))
                bad += 1
            print("gio_check mutations: %d killed, %d not" % (len(MUTATIONS) - bad, bad))
            if bad:
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
