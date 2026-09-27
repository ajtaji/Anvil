#!/usr/bin/env python3
"""Desk gate for the Raspberry Pi 5 board identity and the ACT LED
(-t pi5, #PMF_CHIP = 2712), on the shared tools/a64/pi5_desk.py harness.

WHAT IS BUILT. One small driver program, compiled -t pi5, that links:
  * RaspberryPi4/Board/hw_id.pi4 WHOLE (its few board dependencies are
    stubbed by name below), so the identity seam is the file's own code;
  * PutRevision and PiRevBoardName2712, cut out of
    RaspberryPi4/Board/clock_info.pi4 as TEXT (the rest of that file is
    the `info` command and its dependencies), so `info`'s board row is the
    shipped decoder;
  * RaspberryPi4/Lib/sdio.pi4 (the gio offsets, one definition) and
    RaspberryPi4/Lib/led_act.pi4.
Printing lands on a modelled PL011 at $107D001000.

WHAT THE MODEL IS BUILT FROM (pinned below with their sources): the gio_aon
bank from the DTS/dtsi/compiled DTBs and gpio-brcmstb.c, the revision-code
bit layout, and the identity facts.  The other gio_aon lines (RP1_RUN, SD
power, the PMIC interrupt) are live in the model and must never move.

Run:     py -3 -B tools/a64/pi5_board_id_check.py --compiler <PureMetalForge.exe> [--mutate]
Desk proof only; silicon owed.
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

REL_ID = "RaspberryPi4/Board/hw_id.pi4"
REL_INFO = "RaspberryPi4/Board/clock_info.pi4"
REL_SDIO = "RaspberryPi4/Lib/sdio.pi4"
REL_LED = "RaspberryPi4/Lib/led_act.pi4"
REL_GPIO = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_FMT = "Anvil/Core/format.pbi"
REL_SAFETY = "RaspberryPi4/Lib/safety.pi4"

PINNED = {
    # bcm2712-rpi-5-b.dts: model = "Raspberry Pi 5"; led_act gpios =
    # <&gio_aon 9 GPIO_ACTIVE_LOW>; line name AON_GPIO_09 "2712_STAT_LED".
    "model": "Raspberry Pi 5",
    "act": ("gio_aon", 9, "GPIO_ACTIVE_LOW"),
    # bcm2712-rpi.dtsi gpio2 = &gio_aon; gpiomem2 reg <0x7d517c00 0x40>;
    # compiled DTBs carry gpio@7d517c00. /soc: bus 0x7d001000 = CPU $107D001000.
    "gio_aon_bus": 0x7D517C00, "soc_example": (0x7D001000, 0x107D001000),
    # gpio-brcmstb.c: GIO_BANK_OFF(bank, reg) = bank*8*4 + reg*4; ODEN 0,
    # DATA 1, IODIR 2 (IODIR 1 = input).
    "GIO_REG": {"ODEN": 0, "DATA": 1, "IODIR": 2}, "GIO_REGS_PER_BANK": 8,
    # keywords.def #PMF_CHIP: 2712 for -t pi5.
    "pmf_chip": 2712, "target": "pi5",
    # Cortex-A76: MIDR part $D0B (vault "GPU - V3D 7.1 port plan").
    "cpu": "Cortex-A76",
    # New-style revision code layout: bit 23 new-style, type 11:4,
    # processor 15:12 (4 = BCM2712), memory 22:20 (256 MB << n), rev 3:0.
    "types": {0x17: "Pi 5 Model B", 0x18: "Compute Module 5",
              0x19: "Pi 500", 0x1A: "Compute Module 5 Lite"},
    "procs": {3: "BCM2711", 4: "BCM2712"},
    # bcm2712-ds.dtsi pm: watchdog@7d200000 "brcm,bcm2712-pm"; bcm2835_wdt.c
    # PM_RSTC 0x1c, PM_WDOG 0x24, PM_PASSWORD 0x5a000000, WRCFG_CLR 0xffffffcf,
    # WRCFG_FULL_RESET 0x20; restart arms 10 ticks.
    "pm_bus": 0x7D200000, "PM_RSTC": 0x1C, "PM_WDOG": 0x24, "PM_PASSWORD": 0x5A000000,
    "WRCFG_CLR": 0xFFFFFFCF, "WRCFG_FULL": 0x20, "expire": 10,
}

UART = 0x107D001000
UART_FR = UART + 0x18
AON = PINNED["soc_example"][1] - PINNED["soc_example"][0] + PINNED["gio_aon_bus"]
DATA = AON + PINNED["GIO_REG"]["DATA"] * 4
IODIR = AON + PINNED["GIO_REG"]["IODIR"] * 4
ACT = 1 << PINNED["act"][1]
LIT_LEVEL = 0 if PINNED["act"][2] == "GPIO_ACTIVE_LOW" else 1

DRIVER = r'''
; pi5_board_id_check driver - generated, never committed.
#MON_LO = $200000
#UART_BASE = $1F00030000
Procedure UartWrite(c.i)
  PokeL($107D001000, c)
EndProcedure
Procedure UartWriteStr(p.i)
  Define c.i
  Repeat
    c = PeekA(p)
    If c = 0 : Break : EndIf
    UartWrite(c)
    p = p + 1
  ForEver
EndProcedure
Procedure str_print_at(p.i)
  UartWriteStr(p)
EndProcedure
Procedure PrintNl()
  UartWrite(10)
EndProcedure
Procedure PrintDec(v.i)
  Define d.i
  Define s.i
  If v < 0
    UartWrite(45)
    v = 0 - v
  EndIf
  d = 1000000000000000000
  s = 0
  While d > 0
    If (v / d) % 10 <> 0 Or s = 1 Or d = 1
      UartWrite(48 + (v / d) % 10)
      s = 1
    EndIf
    d = d / 10
  Wend
EndProcedure
Procedure.i MmuEl()
  ProcedureReturn 3
EndProcedure
Procedure.i HwMonLo()
  ProcedureReturn #MON_LO
EndProcedure
Procedure.i HwMonBytes()
  ProcedureReturn 4096
EndProcedure
XIncludeFile "Anvil/Core/format.pbi"
XIncludeFile "RaspberryPi4/Board/hw_id.pi4"
XIncludeFile "RaspberryPi4/Lib/sdio.pi4"
XIncludeFile "RaspberryPi4/Lib/gpio_rp1.pi4"
XIncludeFile "RaspberryPi4/Lib/led_act.pi4"
XIncludeFile "RaspberryPi4/Lib/safety.pi4"
; --- cut from clock_info.pi4 ---
%(REVISION)s
; --- end cut ---
; Keep every procedure the gate calls: reachable, never run.
Global gate_never.i
If gate_never = 1
  HwIdBoard() : HwIdCpu() : HwIdTarget() : HwPmfTargetId() : HwIdSayImage()
  PutRevision(0) : LedActBegin() : LedActSet(0) : LedActToggle() : safety_WdogArm(10)
  LedPwrBegin() : LedPwrSet(0) : LedPwrToggle() : LedPwrLit() : LedPwrIsOutput()
EndIf
'''


# ---- the PWR LED: RP1 GPIO44, from the sources, never from the library ----
# bcm2712-rpi-5-b.dts led_pwr gpios = <&rp1_gpio 44 GPIO_ACTIVE_LOW>;
# pinctrl-rp1.c rp1_iobanks[2] = {34, 20, gpio $8000, rio $8000, pads $8004},
# so GPIO44 is bank 2 index 10; CTRL = IO + $8000 + 10*8 + 4, PAD = PADS +
# $8004 + 10*4, RIO OUT/OE/IN at SYS_RIO + $8000 + 0/4/8, bit 10, with the
# SET/CLR aliases at +$2000/+$3000; FUNCSEL 5 = GPIO. RP1 is CPU $1F_00xxxxxx.
PWR_BIT = 1 << 10
PWR_CTRL = 0x1F_000D_0000 + 0x8000 + 10 * 8 + 4
PWR_PAD = 0x1F_000F_0000 + 0x8004 + 10 * 4
PWR_RIO = 0x1F_000E_0000 + 0x8000


class PwrModel:
    """GPIO44 and its bank-2 neighbours; anything else RP1 is refused."""

    def __init__(self, oe=1 << 11, out=1 << 11, stuck=None):
        self.ctrl, self.pad = 0x1F, 0x80               # reset: no function, pad off
        self.oe, self.out = oe, out                    # GPIO45's bits are someone else's
        self.oe0, self.out0 = oe, out
        self.stuck = stuck                             # None, or the level the pad is stuck at
        self.log = []

    def rio_in(self):
        if self.stuck is not None:
            return self.stuck
        if self.ctrl & 0x1F == 5 and self.oe & PWR_BIT:
            return self.out
        return PWR_BIT                                 # an undriven LED pad reads high

    def lit(self):
        return self.ctrl & 0x1F == 5 and bool(self.oe & PWR_BIT) and not self.out & PWR_BIT

    def __call__(self, addr, size, value):
        if size != 4:
            d.die("a %d-byte RP1 access at $%X" % (size, addr))
        regs = {PWR_CTRL: "ctrl", PWR_PAD: "pad"}
        if addr in regs:
            if value is None:
                return getattr(self, regs[addr])
            self.log.append((regs[addr], value))
            setattr(self, regs[addr], value & 0xFFFFFFFF)
            return 0
        off = addr - PWR_RIO
        if off in (0, 4, 8) and value is None:
            return {0: self.out, 4: self.oe, 8: self.rio_in()}[off]
        if off in (0x2000, 0x3000, 0x2004, 0x3004) and value is not None:
            which = "out" if (off & 0xF) == 0 else "oe"
            self.log.append((which + ("+" if off & 0x2000 and not off & 0x1000 else "-"), value))
            cur = getattr(self, which)
            setattr(self, which, cur | value if off < 0x3000 else cur & ~value)
            return 0
        d.die("the PWR LED touched $%X (%s), not GPIO44's CTRL/PAD or bank 2's RIO "
              "OUT/OE/IN through SET/CLR" % (addr, "read" if value is None else "write"))


def cut_revision(text: str) -> str:
    a = text.find("Procedure.i PiRevBoardName2712")
    if a < 0:
        d.die("%s has no PiRevBoardName2712" % REL_INFO)
    a = text.rfind("CompilerIf #PMF_CHIP = 2712", 0, a)
    b = text.find("Procedure CmdInfo()", a)
    if a < 0 or b < 0 or "Procedure PutRevision(r.i)" not in text[a:b]:
        d.die("%s no longer has the Pi 5 names block followed by PutRevision" % REL_INFO)
    return text[a:b]


def expected_revision(code: int) -> str:
    if not code & 0x800000:
        return "an old-style revision code, which this monitor does not decode"
    t, p, mem = (code >> 4) & 0xFF, (code >> 12) & 0xF, (code >> 20) & 7
    name = PINNED["types"].get(t, "a board this monitor does not have a name for, type $%02X" % t)
    proc = {0: "BCM2835", 1: "BCM2836", 2: "BCM2837", 3: "BCM2711", 4: "BCM2712"}.get(
        p, "a processor this monitor does not have a name for, type $%02X" % p)
    mb = 256 << mem
    size = "%d GB" % (mb // 1024) if mb >= 1024 else "%d MB" % mb
    return "%s, %s, %s, rev 1.%d (board revision; the SoC stepping, C1 or D0, is not in this code)" % (
        name, proc, size, code & 0xF)


class Model:
    def __init__(self, data=0x0000_0015, iodir=0xFFFF_FFEB, ignore_iodir=False):
        self.uart = bytearray()
        self.data, self.iodir = data, iodir
        self.data0, self.iodir0 = data, iodir
        self.ignore_iodir = ignore_iodir
        self.log = []

    def __call__(self, addr, size, value):
        if addr == UART:
            if value is None:
                return 0
            self.uart.append(value & 0xFF)
            return 0
        if addr == UART_FR:
            return 0
        if addr in (DATA, IODIR):
            if value is None:
                return self.data if addr == DATA else self.iodir
            self.log.append(("DATA" if addr == DATA else "IODIR", value))
            if addr == DATA:
                self.data = value
            elif not self.ignore_iodir:
                self.iodir = value
            return 0
        d.die("unmodelled access at $%X (%s)" % (addr, "read" if value is None else "write $%X" % value))

    def text(self):
        s = self.uart.decode(errors="replace")
        self.uart.clear()
        return s

    def lit(self):
        return ((self.data & ACT) != 0) == bool(LIT_LEVEL) and not (self.iodir & ACT)


def gate(override: dict, work: pathlib.Path, cc: str) -> int:
    n = [0]

    def expect(ok, msg):
        n[0] += 1
        if not ok:
            d.die(msg)

    info = d.source(REL_INFO, override)
    text = DRIVER.replace("%(REVISION)s", cut_revision(info))
    img, procs = d.build(cc, text, "boardid", work, override,
                         [REL_FMT, REL_ID, REL_SDIO, REL_GPIO, REL_LED, REL_SAFETY])

    # ---- identity ------------------------------------------------------
    m = Model()
    mc = d.Machine(img, procs, m)
    board = mc.cstr(mc.call("HwIdBoard"))
    expect(board == PINNED["model"] + " Model B", "HwIdBoard says %r" % board)
    expect(mc.cstr(mc.call("HwIdCpu")) == PINNED["cpu"], "HwIdCpu is not the Cortex-A76")
    expect(mc.cstr(mc.call("HwIdTarget")) == PINNED["target"], "HwIdTarget is not pi5")
    expect(mc.call("HwPmfTargetId") == PINNED["pmf_chip"], "HwPmfTargetId is not 2712")
    mc.call("HwIdSayImage")
    say = m.text()
    expect("kernel8.img" not in say and "0x" not in say and "00200000" in say,
           "HwIdSayImage on a Pi 5: %r" % say[:120])

    # ---- the revision code, as `info` prints it -------------------------
    codes = [0xC04170, 0xD04170, 0xB04171, 0xE04171, 0xC04180, 0xD04190,
             0xB041A0, 0x9020E0, 0xB03115, 0x0010]
    for code in codes:
        mc.call("PutRevision", code)
        got, want = m.text(), expected_revision(code)
        expect(got == want, "PutRevision($%06X) printed %r, want %r" % (code, got, want))

    # ---- the ACT LED -----------------------------------------------------
    m = Model()
    mc = d.Machine(img, procs, m)
    st = d.const_in(d.source(REL_LED, override), "#LED_ACT_STATE", REL_LED)
    stuck = d.const_in(d.source(REL_LED, override), "#LED_ACT_STUCK", REL_LED)
    expect(mc.signed(mc.call("LedActSet", 1)) == st and not m.log,
           "LedActSet before LedActBegin was not refused, or it wrote")
    expect(mc.call("LedActBegin") == 0, "LedActBegin failed")
    kinds = [k for k, v in m.log]
    expect(kinds == ["DATA", "IODIR"], "Begin wrote %s, want DATA then IODIR" % kinds)
    expect(not m.lit() and not (m.iodir & ACT) and (m.data & ACT) == (0 if LIT_LEVEL else ACT),
           "after Begin the LED is lit or the pin is not an output")
    first_dir = m.log[1][1]
    expect(m.log[0][1] & ACT if not LIT_LEVEL else not m.log[0][1] & ACT,
           "Begin drove the pin before setting it dark (a flash)")
    expect(not first_dir & ACT, "IODIR bit 9 not cleared")
    for want in (1, 0, 1):
        expect(mc.call("LedActSet", want) == 0 and m.lit() == bool(want),
               "LedActSet(%d) left the LED %s" % (want, "lit" if m.lit() else "dark"))
    expect(mc.call("LedActToggle") == 0 and not m.lit(), "LedActToggle did not toggle")
    expect(mc.call("LedActSet", 7) == 0 and m.lit(), "LedActSet(7) is not 'on'")
    expect((m.data & ~ACT) == (m.data0 & ~ACT) and (m.iodir & ~ACT) == (m.iodir0 & ~ACT),
           "another gio_aon line moved: DATA $%X->$%X IODIR $%X->$%X"
           % (m.data0, m.data, m.iodir0, m.iodir))
    # A pin whose direction will not change is refused by name.
    m2 = Model(ignore_iodir=True)
    mc2 = d.Machine(img, procs, m2)
    expect(mc2.signed(mc2.call("LedActBegin")) == stuck, "a pin that stays an input was accepted")
    expect(mc2.signed(mc2.call("LedActSet", 1)) == st, "Set after a failed Begin was accepted")
    # ---- the PWR LED (RP1 GPIO44, active low) ------------------------------
    p = PwrModel()
    mp = d.Machine(img, procs, p)
    expect(mp.signed(mp.call("LedPwrSet", 1)) == st and not p.log,
           "LedPwrSet before LedPwrBegin was not refused, or it wrote")
    expect(mp.call("LedPwrBegin") == 0, "LedPwrBegin failed")
    kinds = [k for k, v in p.log]
    expect(kinds and kinds[0] == "out+" and p.log[0][1] == PWR_BIT,
           "Begin did not set GPIO44 high (dark) first: %s" % kinds)
    expect(kinds.index("ctrl") < kinds.index("oe+"),
           "Begin enabled the output before selecting the GPIO function: %s" % kinds)
    expect(p.ctrl == 5 and p.pad & 0xC0 == 0x40 and p.oe & PWR_BIT and not p.lit(),
           "after Begin GPIO44 is not a dark GPIO output (CTRL $%X PAD $%X)" % (p.ctrl, p.pad))
    for want in (1, 0, 1):
        expect(mp.call("LedPwrSet", want) == 0 and p.lit() == bool(want),
               "LedPwrSet(%d) left the PWR LED %s" % (want, "lit" if p.lit() else "dark"))
    expect(mp.call("LedPwrLit") == 1, "LedPwrLit does not read lit from the pad")
    expect(mp.call("LedPwrToggle") == 0 and not p.lit(), "LedPwrToggle did not toggle")
    expect(mp.call("LedPwrSet", 7) == 0 and p.lit(), "LedPwrSet(7) is not 'on'")
    expect(p.oe & ~PWR_BIT == p.oe0 & ~PWR_BIT and p.out & ~PWR_BIT == p.out0 & ~PWR_BIT,
           "another bank-2 line (GPIO45, the fan) moved")
    # A pad stuck LOW reads lit from the start: Begin refuses, and nothing
    # after it is accepted. A pad stuck HIGH passes Begin (dark is what
    # Begin asks for) and is caught by the first Set that asks for lit.
    p2 = PwrModel(stuck=0)
    mp2 = d.Machine(img, procs, p2)
    expect(mp2.signed(mp2.call("LedPwrBegin")) == stuck and
           mp2.signed(mp2.call("LedPwrSet", 1)) == st,
           "a PWR LED pad stuck lit was accepted by Begin")
    p3 = PwrModel(stuck=PWR_BIT)
    mp3 = d.Machine(img, procs, p3)
    expect(mp3.call("LedPwrBegin") == 0 and mp3.signed(mp3.call("LedPwrSet", 1)) == stuck,
           "a PWR LED pad stuck dark was reported lit")
    # ---- reset: the PM watchdog on a BCM2712 -----------------------------
    saf = d.source(REL_SAFETY, override)
    if re.search(r"CompilerIf #PMF_CHIP = 2712\s*\n#SAFETY_PM_BASE", saf):
        pm = PINNED["soc_example"][1] - PINNED["soc_example"][0] + PINNED["pm_bus"]
        regs = {pm + PINNED["PM_RSTC"]: 0x0000_0102, pm + PINNED["PM_WDOG"]: 0}
        writes = []

        def pmodel(addr, size, value):
            if addr in regs:
                if value is None:
                    return regs[addr]
                writes.append((addr - pm, value))
                regs[addr] = value
                return 0
            d.die("reset touched $%X, not the BCM2712 PM block" % addr)
        mp = d.Machine(img, procs, pmodel)
        mp.call("safety_WdogArm", PINNED["expire"])
        pw = PINNED["PM_PASSWORD"]
        want = [(PINNED["PM_WDOG"], pw | PINNED["expire"]),
                (PINNED["PM_RSTC"], pw | (0x102 & PINNED["WRCFG_CLR"]) | PINNED["WRCFG_FULL"])]
        expect(writes == want, "reset wrote %s, want %s" % (
            [(hex(o), hex(v)) for o, v in writes], [(hex(o), hex(v)) for o, v in want]))
    else:
        print("   OWED: safety.pi4 has no #PMF_CHIP = 2712 PM base yet (the port "
              "worker's file; patch prepared) - the reset section did not run")
    return n[0]

MUTATIONS = [
    (REL_ID, "Pi 4 board name on a Pi 5", 'ProcedureReturn "Raspberry Pi 5 Model B"', 'ProcedureReturn "Raspberry Pi 4"'),
    (REL_ID, "A72 on a Pi 5", 'ProcedureReturn "Cortex-A76"', 'ProcedureReturn "Cortex-A72"'),
    (REL_ID, "pi4 target word", 'ProcedureReturn "pi5"', 'ProcedureReturn "pi4"'),
    (REL_ID, "2711 target id", "ProcedureReturn 2712", "ProcedureReturn 2711"),
    (REL_INFO, "CM5 and Pi 500 swapped", 'Case $18\n      ProcedureReturn "Compute Module 5"', 'Case $19\n      ProcedureReturn "Compute Module 5"'),
    (REL_INFO, "stepping claimed from the board revision", "the SoC stepping, C1 or D0, is not in this code", "C1 stepping"),
    (REL_LED, "PWR/ACT pin 9 read as 8", "#LED_ACT_BIT      = 1 << 9", "#LED_ACT_BIT      = 1 << 8"),
    (REL_LED, "the main gio instead of gio_aon", "#LED_ACT_AON_BASE = $107D517C00", "#LED_ACT_AON_BASE = $107D508500"),
    (REL_LED, "active high assumed", "    v = v & (~#LED_ACT_BIT)\n  Else\n    v = v | #LED_ACT_BIT", "    v = v | #LED_ACT_BIT\n  Else\n    v = v & (~#LED_ACT_BIT)"),
    (REL_LED, "a whole-register write", "PokeL(#LED_ACT_AON_BASE + #SDIO_GIO_IODIR, v & (~#LED_ACT_BIT))", "PokeL(#LED_ACT_AON_BASE + #SDIO_GIO_IODIR, 0)"),
    (REL_LED, "direction before value (a flash)", "  v = PeekN(#LED_ACT_AON_BASE + #SDIO_GIO_DATA)\n  PokeL(#LED_ACT_AON_BASE + #SDIO_GIO_DATA, v | #LED_ACT_BIT)\n  v = PeekN(#LED_ACT_AON_BASE + #SDIO_GIO_IODIR)\n  PokeL(#LED_ACT_AON_BASE + #SDIO_GIO_IODIR, v & (~#LED_ACT_BIT))\n", "  v = PeekN(#LED_ACT_AON_BASE + #SDIO_GIO_IODIR)\n  PokeL(#LED_ACT_AON_BASE + #SDIO_GIO_IODIR, v & (~#LED_ACT_BIT))\n  v = PeekN(#LED_ACT_AON_BASE + #SDIO_GIO_DATA)\n  PokeL(#LED_ACT_AON_BASE + #SDIO_GIO_DATA, v | #LED_ACT_BIT)\n"),
    (REL_LED, "the readback skipped", "  If LedActIsOutput() = 0 Or LedActLit() <> 0\n", "  If 0\n"),
    (REL_LED, "PWR LED active high", "    Rp1DigitalWrite(#RP1_GPIO_PWR_LED, #RP1_PIN_LOW)\n  Else\n    Rp1DigitalWrite(#RP1_GPIO_PWR_LED, #RP1_PIN_HIGH)",
     "    Rp1DigitalWrite(#RP1_GPIO_PWR_LED, #RP1_PIN_HIGH)\n  Else\n    Rp1DigitalWrite(#RP1_GPIO_PWR_LED, #RP1_PIN_LOW)"),
    (REL_LED, "PWR LED output before its level (a flash)",
     "  If Rp1DigitalWrite(#RP1_GPIO_PWR_LED, #RP1_PIN_HIGH) = 0\n    ProcedureReturn #LED_ACT_STUCK\n  EndIf\n  If Rp1PinOutput(#RP1_GPIO_PWR_LED) = 0\n    ProcedureReturn #LED_ACT_STUCK\n  EndIf\n",
     "  If Rp1PinOutput(#RP1_GPIO_PWR_LED) = 0\n    ProcedureReturn #LED_ACT_STUCK\n  EndIf\n  If Rp1DigitalWrite(#RP1_GPIO_PWR_LED, #RP1_PIN_HIGH) = 0\n    ProcedureReturn #LED_ACT_STUCK\n  EndIf\n"),
    (REL_LED, "PWR LED readback skipped", "  If LedPwrIsOutput() = 0 Or LedPwrLit() <> 0\n", "  If 0\n"),
    (REL_GPIO, "PWR LED on GPIO43", "#RP1_GPIO_PWR_LED     = 44", "#RP1_GPIO_PWR_LED     = 43"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-pi5id-"))
    try:
        try:
            n = gate({}, top / "gate", cc)
        except d.GateFail as e:
            print("pi5_board_id_check: FAIL - %s" % e)
            return 1
        print("pi5_board_id_check: PASS - %d checks (desk only; silicon owed)" % n)
        if a.mutate:
            left = d.run_mutations("pi5_board_id_check", MUTATIONS,
                                   lambda ov, w: gate(ov, w, cc), top / "mut")
            return 1 if left else 0
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
