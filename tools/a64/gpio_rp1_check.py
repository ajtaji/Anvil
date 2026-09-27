#!/usr/bin/env python3
"""Desk gate: RP1 (Pi 5) GPIO - RaspberryPi4/Lib/gpio_rp1.pi4 and the
#PMF_CHIP = 2712 branch of RaspberryPi4/Board/hw_gpio.pi4.

The compiled procedures (-t pi5) run under tools/a64/a64_interp.py against a
MODEL of RP1's three GPIO windows. The model is written from the published
sources, not from the library under test:

  rp1.dtsi (vault Sources/)  gpio@d0000 reg = 0xc0_400d0000 / 400e0000 /
                             400f0000, each 0xc000 long. The Pi 5 DTB's
                             rp1 `ranges` maps 0xc0_40000000 to PCI 0, and
                             pcie@1000120000 maps PCI 0 to CPU 0x1f_00000000,
                             so the three windows are at 0x1F_000D0000,
                             0x1F_000E0000 and 0x1F_000F0000.
  pinctrl-rp1.c              CTRL = IO_BANK0 + pin*8 + 4 (STATUS at +0);
                             FUNCSEL = CTRL[4:0], 5 = GPIO, 0..8 the nine
                             table columns, >= 9 "none"; SYS_RIO0 OUT +0,
                             OE +4, IN +8, one bit per pin; PAD = PADS_BANK0
                             + 4 + pin*4, PULL = PAD[3:2] with 1 = DOWN,
                             2 = UP; DRIVE = PAD[5:4], 0..3 = 2/4/8/12 mA
                             (RP1_PAD_DRIVE_2MA..12MA, lines 140-143);
                             IN_ENABLE bit 6, OUT_DISABLE bit 7;
                             every block aliased RW +0, XOR +$1000,
                             SET +$2000, CLR +$3000.

So a wrong offset in the library is an access the model names as
unmodelled, not a matching wrong offset in a mirror. The HW-level vocabulary
(#HW_GPIO_*, #HW_PULL_*) is read from Anvil/Hal/hal.pbi, the file that owns
it. A mutation sweep proves the gate goes red on each named defect,
including the RP1/BCM2711 pull-encoding swap.

Desk proof only: nothing here has driven a real RP1 pin. Silicon owed.

  py -3 -B tools/a64/gpio_rp1_check.py --compiler <PureMetalForge.exe> [--mutate]
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

IO_BANK0 = 0x1F_000D_0000
SYS_RIO0 = 0x1F_000E_0000
PADS_BANK0 = 0x1F_000F_0000
WINDOW = 0xC000
PINS = 28

REL_LIB = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_HW = "RaspberryPi4/Board/hw_gpio.pi4"
REL_HAL = "Anvil/Hal/hal.pbi"
HAL_NAMES = ("#HW_GPIO_IN", "#HW_GPIO_OUT", "#HW_GPIO_ALT",
             "#HW_PULL_NONE", "#HW_PULL_UP", "#HW_PULL_DOWN")


class Rp1Gpio:
    """RP1 bank 0 as pinctrl-rp1.c describes it."""

    def __init__(self):
        self.reg = {}            # RW address -> 32-bit value
        self.log = []            # (op, address as accessed, value)
        self.pad_in = 0          # external level on each pin's pad (bit per pin)

    def _decode(self, addr):
        # Bank 0 of each window is its first $4000: registers in +$000..$FFF,
        # then the XOR/SET/CLR copies at +$1000/+$2000/+$3000. Banks 1 and 2
        # (+$4000, +$8000) are not modelled - gpio_rp1.pi4 does not drive them.
        for base in (IO_BANK0, SYS_RIO0, PADS_BANK0):
            if base <= addr < base + 0x4000:
                off = addr - base
                return base, base + (off & 0xFFF), off & 0x3000
        d.die("unmodelled access at $%X (not RP1 bank 0 GPIO)" % addr)

    def _valid(self, base, rw):
        off = rw - base
        if base == IO_BANK0:
            if off % 8 not in (0, 4) or off // 8 >= PINS:
                d.die("IO_BANK0 access at +$%X is not a bank-0 STATUS/CTRL word" % off)
        elif base == SYS_RIO0:
            if off not in (0, 4, 8):
                d.die("SYS_RIO0 access at +$%X is not OUT/OE/IN" % off)
        else:
            if off < 4 or off % 4 or (off - 4) // 4 >= PINS:
                d.die("PADS_BANK0 access at +$%X is not a bank-0 pad word "
                      "(+$0 is the bank voltage select, which nothing here owns)" % off)

    def rio_in(self):
        oe = self.reg.get(SYS_RIO0 + 4, 0)
        out = self.reg.get(SYS_RIO0 + 0, 0)
        v = 0
        for p in range(PINS):
            bit = 1 << p
            ctrl = self.reg.get(IO_BANK0 + p * 8 + 4, 0x1F)
            if (ctrl & 0x1F) == 5 and oe & bit:
                v |= out & bit
            else:
                v |= self.pad_in & bit
        return v

    def __call__(self, addr, size, value):
        if size != 4:
            d.die("RP1 access of %d bytes at $%X: every RP1 register is 32-bit" % (size, addr))
        base, rw, alias = self._decode(addr)
        self._valid(base, rw)
        if value is None:
            if alias:
                d.die("read through the alias window at $%X" % addr)
            self.log.append(("r", addr, None))
            if rw == SYS_RIO0 + 8:
                return self.rio_in()
            return self.reg.get(rw, 0x1F if base == IO_BANK0 and (rw - base) % 8 == 4 else 0)
        self.log.append(("w", addr, value))
        if rw == SYS_RIO0 + 8:
            d.die("write to RIO_IN, which is read-only")
        old = self.reg.get(rw, 0)
        if alias == 0:
            new = value
        elif alias == 0x1000:
            new = old ^ value
        elif alias == 0x2000:
            new = old | value
        else:
            new = old & ~value
        self.reg[rw] = new & 0xFFFFFFFF

    def writes_to(self, addr):
        return [v for op, a, v in self.log if op == "w" and a == addr]


def driver(override):
    hal = d.source(REL_HAL, override)
    consts = "\n".join("%s = %d" % (n, d.const_in(hal, n, REL_HAL)) for n in HAL_NAMES)
    return ("; gpio_rp1_check driver - generated\n" + consts + "\n"
            'XIncludeFile "%s"\nXIncludeFile "%s"\n' % (REL_LIB, REL_HW) +
            "Global gate_never.i\n"
            "If gate_never = 1\n"
            "  HwGpioCount() : HwGpioUserMax() : HwGpioModeGet(0) : HwGpioAltGet(0)\n"
            "  HwGpioLevelGet(0) : HwGpioPullGet(0) : HwGpioMode(0, 0)\n"
            "  HwGpioWrite(0, 0) : HwGpioToggle(0) : HwGpioReservedReason(0)\n"
            "  Rp1CtrlAddr(0) : Rp1PadAddr(0) : Rp1FuncSelSet(0, 0) : Rp1PinPull(0, 0)\n"
            "  Rp1GpioBadPinCount() : Rp1PinDrive(0, 0) : Rp1PinDriveGet(0)\n"
            "EndIf\n")


def gate(cc, override, workdir):
    hal = d.source(REL_HAL, override)
    H = {n: d.const_in(hal, n, REL_HAL) for n in HAL_NAMES}
    img, procs = d.build(cc, driver(override), "gpio_rp1_drv", workdir,
                         override, [REL_LIB, REL_HW])
    rp1 = Rp1Gpio()
    m = d.Machine(img, procs, rp1)
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1

    def call(name, *a):
        return m.signed(m.call(name, *a))

    ctrl = lambda p: IO_BANK0 + p * 8 + 4
    pad = lambda p: PADS_BANK0 + 4 + p * 4
    OUT, OE = SYS_RIO0, SYS_RIO0 + 4

    # --- extent -----------------------------------------------------------
    check(call("HwGpioCount") == 28, "HwGpioCount is not RP1 bank 0's 28 lines")
    check(call("HwGpioUserMax") == 27, "HwGpioUserMax is not 27")

    # --- address arithmetic ----------------------------------------------
    for p in (0, 2, 3, 14, 27):
        check(call("Rp1CtrlAddr", p) == ctrl(p), "CTRL address for pin %d" % p)
        check(call("Rp1PadAddr", p) == pad(p), "PAD address for pin %d" % p)

    # --- output: pad, FUNCSEL, OE through SET, neighbours untouched --------
    rp1.reg[OE] = (1 << 9) | (1 << 20)            # two other outputs already
    rp1.reg[pad(17)] = 2 << 2 | 0x80              # pull UP, output disabled
    rp1.log.clear()
    check(call("HwGpioMode", 17, H["#HW_GPIO_OUT"]) == 1, "HwGpioMode(17, OUT) refused")
    check(rp1.reg[ctrl(17)] == 5, "CTRL(17) is $%X, want exactly FUNCSEL 5 with "
          "OUTOVER/OEOVER/INOVER = PERI (0)" % rp1.reg[ctrl(17)])
    check(rp1.reg[pad(17)] == (2 << 2) | 0x40, "PAD(17) is $%X: want IN_ENABLE set, "
          "OUT_DISABLE clear and the pull left alone" % rp1.reg[pad(17)])
    check(rp1.reg[OE] == (1 << 9) | (1 << 20) | (1 << 17), "OE is $%X after output(17)"
          % rp1.reg[OE])
    check(not rp1.writes_to(OE), "OE was written through its RW address - a "
          "read-modify-write race pinctrl-rp1.c avoids with SET/CLR")
    check(rp1.writes_to(OE + 0x2000) == [1 << 17], "OE SET alias not written with bit 17")
    check(call("HwGpioModeGet", 17) == H["#HW_GPIO_OUT"], "ModeGet(17) is not OUT")
    check(call("HwGpioAltGet", 17) == -1, "AltGet on a plain output is not -1")

    # --- level: SET/CLR on OUT, read back through RIO_IN ---------------------
    rp1.log.clear()
    check(call("HwGpioWrite", 17, 1) == 1, "HwGpioWrite(17,1) refused")
    check(rp1.writes_to(OUT + 0x2000) == [1 << 17] and not rp1.writes_to(OUT),
          "a high write did not go through RIO_OUT's SET alias alone")
    check(call("HwGpioLevelGet", 17) == 1, "LevelGet(17) after a high write is not 1")
    check(call("HwGpioToggle", 17) == 1 and call("HwGpioLevelGet", 17) == 0,
          "Toggle from high did not read back low")
    check(rp1.writes_to(OUT + 0x3000) == [1 << 17], "the low half did not use CLR")
    check(call("HwGpioToggle", 17) == 1 and call("HwGpioLevelGet", 17) == 1,
          "Toggle from low did not read back high")
    check(call("HwGpioWrite", 17, 7) == 1 and call("HwGpioLevelGet", 17) == 1,
          "a non-zero level other than 1 did not set the pin")

    # --- input: OE CLR, the pad's own level ----------------------------------
    rp1.log.clear()
    check(call("HwGpioMode", 17, H["#HW_GPIO_IN"]) == 1, "HwGpioMode(17, IN) refused")
    check(rp1.writes_to(OE + 0x3000) == [1 << 17], "input did not clear OE via CLR")
    check(rp1.reg[OE] == (1 << 9) | (1 << 20), "input disturbed another pin's OE")
    check(call("HwGpioModeGet", 17) == H["#HW_GPIO_IN"], "ModeGet(17) is not IN")
    rp1.pad_in = 1 << 17
    check(call("HwGpioLevelGet", 17) == 1, "an input did not read its pad high")
    rp1.pad_in = 0
    check(call("HwGpioLevelGet", 17) == 0, "an input did not read its pad low")
    check(call("HwGpioMode", 17, H["#HW_GPIO_ALT"]) == 0, "HwGpioMode(ALT) was not refused")

    # --- pull: RP1 raw 1 = DOWN, 2 = UP (the REVERSE of BCM2711) -------------
    for raw, want in ((0, "#HW_PULL_NONE"), (1, "#HW_PULL_DOWN"), (2, "#HW_PULL_UP")):
        rp1.reg[pad(5)] = 0x40 | (raw << 2)
        check(call("HwGpioPullGet", 5) == H[want], "pad pull field %d did not read as %s"
              % (raw, want))
    rp1.reg[pad(5)] = 0x40 | (3 << 2)
    check(call("HwGpioPullGet", 5) == -1, "reserved pull field 3 did not read as -1")
    rp1.reg[pad(5)] = 0x41 | 0x30          # slewfast + 12 mA, no pull
    check(call("Rp1PinPull", 5, 2) == 1 and
          rp1.reg[pad(5)] == 0x41 | 0x30 | (2 << 2),
          "Rp1PinPull(5, 2) did not program field 2 (UP) and keep the other pad bits")
    check(call("HwGpioPullGet", 5) == H["#HW_PULL_UP"], "a field-2 pull did not report UP")
    check(call("Rp1PinPull", 5, 3) == 0, "pull encoding 3 (reserved) was accepted")

    # --- drive strength: mA in, PAD[5:4] = 0..3 for 2/4/8/12 ----------------
    for ma, code in ((2, 0), (4, 1), (8, 2), (12, 3)):
        rp1.reg[pad(6)] = 0x41 | (2 << 2) | 0x80 | (((code + 1) & 3) << 4)
        check(call("Rp1PinDrive", 6, ma) == 1, "Rp1PinDrive(6, %d) refused" % ma)
        check(rp1.reg[pad(6)] == 0x41 | (2 << 2) | 0x80 | (code << 4),
              "%d mA left PAD(6) = $%X: want field %d and every other bit kept"
              % (ma, rp1.reg[pad(6)], code))
        check(call("Rp1PinDriveGet", 6) == ma, "DriveGet did not read back %d mA" % ma)
    before = rp1.reg[pad(6)]
    for ma in (0, 3, 6, 16, -4):
        check(call("Rp1PinDrive", 6, ma) == 0 and rp1.reg[pad(6)] == before,
              "a %d mA drive was accepted (Linux: -ENOTSUPP)" % ma)

    # --- alternate functions -------------------------------------------------
    for f in (0, 3, 4, 8):
        rp1.reg[ctrl(2)] = f
        check(call("HwGpioModeGet", 2) == H["#HW_GPIO_ALT"], "FUNCSEL %d not ALT" % f)
        check(call("HwGpioAltGet", 2) == f, "FUNCSEL %d did not report alt %d" % (f, f))
    for f in (9, 0x1F):
        rp1.reg[ctrl(2)] = f
        check(call("HwGpioModeGet", 2) == -1 and call("HwGpioAltGet", 2) == -1,
              "FUNCSEL %d (no function) was reported as a mode" % f)
    rp1.reg[pad(3)] = 0x80
    check(call("Rp1FuncSelSet", 3, 3) == 1 and rp1.reg[ctrl(3)] == 3,
          "Rp1FuncSelSet(3, i2c1) did not write FUNCSEL 3")
    check(rp1.reg[pad(3)] == 0x40, "Rp1FuncSelSet did not enable the pad as "
          "rp1_set_fsel does (PAD(3) = $%X)" % rp1.reg[pad(3)])
    check(call("Rp1FuncSelSet", 3, 9) == 0 and rp1.reg[ctrl(3)] == 3,
          "FUNCSEL 9 was written")

    # --- bad pins touch nothing -----------------------------------------------
    rp1.log.clear()
    for p in (28, 40, -1):
        check(call("HwGpioModeGet", p) == -1, "ModeGet(%d) is not -1" % p)
        check(call("HwGpioLevelGet", p) == -1, "LevelGet(%d) is not -1" % p)
        check(call("HwGpioPullGet", p) == -1, "PullGet(%d) is not -1" % p)
        check(call("HwGpioMode", p, H["#HW_GPIO_OUT"]) == 0, "Mode(%d) accepted" % p)
        check(call("HwGpioWrite", p, 1) == 0, "Write(%d) accepted" % p)
        check(call("Rp1PinDrive", p, 12) == 0 and call("Rp1PinDriveGet", p) == -1,
              "drive on bad pin %d accepted" % p)
    check(not rp1.log, "a bad pin reached RP1: %r" % rp1.log[:3])
    check(call("Rp1GpioBadPinCount") >= 21, "bad pins were not counted")

    # --- the console is reserved --------------------------------------------
    for p in (14, 15):
        r = call("HwGpioReservedReason", p)
        check(r != 0 and "UART0" in m.cstr(r), "GPIO %d is not reserved for the console" % p)
    for p in (2, 3, 13, 16, 27):
        check(call("HwGpioReservedReason", p) == 0, "GPIO %d reserved for no reason" % p)
    return checks[0]


MUTATIONS = [
    (REL_LIB, "pull encoding swapped to the BCM2711's",
     "#RP1_PULL_DOWN = 1 ", "#RP1_PULL_DOWN = 2 "),
    (REL_LIB, "pull UP given the BCM2711 value",
     "#RP1_PULL_UP   = 2 ", "#RP1_PULL_UP   = 1 "),
    (REL_LIB, "IO_BANK0 at SYS_RIO0's address",
     "#RP1_IO_BANK0_BASE   = $1F000D0000", "#RP1_IO_BANK0_BASE   = $1F000E0000"),
    (REL_LIB, "PADS_BANK0 without the $1F prefix",
     "#RP1_PADS_BANK0_BASE = $1F000F0000", "#RP1_PADS_BANK0_BASE = $1F0000F0000"),
    (REL_LIB, "CTRL read at STATUS (+0)",
     "ProcedureReturn #RP1_IO_BANK0_BASE + pin * 8 + 4", "ProcedureReturn #RP1_IO_BANK0_BASE + pin * 8"),
    (REL_LIB, "pad word without the bank voltage-select skip",
     "ProcedureReturn #RP1_PADS_BANK0_BASE + 4 + pin * 4", "ProcedureReturn #RP1_PADS_BANK0_BASE + pin * 4"),
    (REL_LIB, "GPIO function is FUNCSEL 0",
     "#RP1_FUNCSEL_GPIO = 5 ", "#RP1_FUNCSEL_GPIO = 0 "),
    (REL_LIB, "output-enable written through RW",
     "PokeL(#RP1_SYS_RIO0_BASE + #RP1_RIO_OE_OFF + #RP1_SET_OFF, Rp1RioBit(pin))",
     "PokeL(#RP1_SYS_RIO0_BASE + #RP1_RIO_OE_OFF, Rp1RioBit(pin))"),
    (REL_LIB, "high and low swapped (SET/CLR)",
     "PokeL(#RP1_SYS_RIO0_BASE + #RP1_RIO_OUT_OFF + #RP1_CLR_OFF, Rp1RioBit(pin))",
     "PokeL(#RP1_SYS_RIO0_BASE + #RP1_RIO_OUT_OFF + #RP1_SET_OFF, Rp1RioBit(pin))"),
    (REL_LIB, "level read from RIO_OUT, not RIO_IN",
     "v = Rp1ReadReg(#RP1_SYS_RIO0_BASE + #RP1_RIO_IN_OFF)",
     "v = Rp1ReadReg(#RP1_SYS_RIO0_BASE + #RP1_RIO_OUT_OFF)"),
    (REL_LIB, "bank 1 admitted", "#RP1_PIN_MAX = 27", "#RP1_PIN_MAX = 53"),
    (REL_LIB, "pad left disabled by a mode change",
     "  v = v & ~#RP1_PAD_OUT_DISABLE\n", "\n"),
    (REL_LIB, "FuncSelSet skips the pad", "  Rp1PadInit(pin)\n  PokeL(Rp1CtrlAddr(pin), funcsel)",
     "  PokeL(Rp1CtrlAddr(pin), funcsel)"),
    (REL_LIB, "drive field at bit 3", "#RP1_PAD_DRIVE_SHIFT  = 4 ", "#RP1_PAD_DRIVE_SHIFT  = 3 "),
    (REL_LIB, "12 mA encoded as 8 mA", "    Case 12\n      code = 3", "    Case 12\n      code = 2"),
    (REL_LIB, "unsupported current rounded to 2 mA", "    Default\n      ProcedureReturn 0\n  EndSelect\n  Rp1GpioBarrier()\n  a = Rp1PadAddr(pin)\n  v = Rp1ReadReg(a)\n  v = v & ~(#RP1_PAD_DRIVE_MASK2",
     "    Default\n      code = 0\n  EndSelect\n  Rp1GpioBarrier()\n  a = Rp1PadAddr(pin)\n  v = Rp1ReadReg(a)\n  v = v & ~(#RP1_PAD_DRIVE_MASK2"),
    (REL_LIB, "drive written over the whole pad", "  v = v & ~(#RP1_PAD_DRIVE_MASK2 << #RP1_PAD_DRIVE_SHIFT)\n", "  v = 0\n"),
    (REL_HW, "2712 ModeGet reads OE inverted",
     "    If Rp1PinModeGet(pin) = 1\n      ProcedureReturn #HW_GPIO_OUT",
     "    If Rp1PinModeGet(pin) = 0\n      ProcedureReturn #HW_GPIO_OUT"),
    (REL_HW, "2712 pull Select crossed",
     "    Case #RP1_PULL_UP\n      ProcedureReturn #HW_PULL_UP",
     "    Case #RP1_PULL_UP\n      ProcedureReturn #HW_PULL_DOWN"),
    (REL_HW, "2712 no-function reported as ALT",
     "  If f <= 8\n    ProcedureReturn #HW_GPIO_ALT\n  EndIf\n  ProcedureReturn -1",
     "  ProcedureReturn #HW_GPIO_ALT"),
    (REL_HW, "2712 console not reserved",
     "  If pin = 14 Or pin = 15\n    ProcedureReturn \"the serial console this prompt is arriving on: RP1",
     "  If pin = 99\n    ProcedureReturn \"the serial console this prompt is arriving on: RP1"),
    (REL_HW, "2712 write treats 7 as low",
     "  If level = 0\n    ProcedureReturn Rp1DigitalWrite(pin, #RP1_PIN_LOW)",
     "  If level <> 1\n    ProcedureReturn Rp1DigitalWrite(pin, #RP1_PIN_LOW)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="gpio-rp1-"))
    try:
        # Source text is read with universal newlines, so a CRLF checkout
        # and the mutation strings above agree.
        try:
            n = gate(cc, {}, top / "gate")
        except d.GateFail as exc:
            print("gpio_rp1_check: FAIL - %s" % exc)
            return 1
        print("gpio_rp1_check: PASS - %d checks against the RP1 model" % n)
        if a.mutate:
            left = d.run_mutations("gpio_rp1_check", MUTATIONS,
                                   lambda ov, wd: gate(cc, ov, wd), top / "mut")
            if left:
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
