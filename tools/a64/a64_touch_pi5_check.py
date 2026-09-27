#!/usr/bin/env python3
"""Desk gate: Pi 5 display-connector I2C and touch - the #PMF_CHIP = 2712
branches of RaspberryPi4/Lib/i2c.pi4 forwarding to RP1 I2C4 / I2C6 through
RaspberryPi4/Lib/i2c_dw.pi4, with RaspberryPi4/Lib/dsi_panel_v2.pi4 (the
panel MCU at $45) and RaspberryPi4/Lib/touch_goodix.pi4 (GT9xx) running on
top UNMODIFIED.

SILICON OWED. The -t pi5 compiled procedures run on tools/a64/a64_interp.py
against the DesignWare model of tools/a64/i2c_dw_check.py (one instance per
RP1 block, header included) and the RP1 GPIO model of gpio_rp1_check.py.
Any other MMIO is refused.

WHERE THE NUMBERS COME FROM (re-derived here from the vault when present):
  the three Pi 5 DTBs   i2c_csi_dsi == i2c_csi_dsi1 == i2c@80000 (RP1 I2C4),
                        i2c_csi_dsi0 == i2c@88000 (RP1 I2C6); each node's
                        reg through the rp1 and pcie@1000120000 ranges to a
                        CPU address; pinctrl-0 -> rp1_i2c4_40_41 /
                        rp1_i2c6_38_39 (function, pins, 12 mA, pull-up);
                        clock-frequency 100000
  Sources/pinctrl-rp1.c the FUNCSEL: the column of "i2c4" in PIN(40)/PIN(41)
                        and of "i2c6" in PIN(38)/PIN(39)
  i2c-designware-master.c:527-573   DATA_CMD BIT(10) RESTART between
                        messages when IC_RESTART_EN is set
  goodix.c              the register read is ONE i2c_transfer of two msgs;
  the vc4-kms-dsi-ili9881-7inch overlay: MCU @45 + goodix,gt911 @5d on
                        i2c_csi_dsi (Touch Display 2)

THE DEVICE MODELS ENFORCE THE THING THAT MATTERS:
  GT9xx: a STOP makes it forget its 16-bit register pointer; a read with no
  pointer returns $A5 and is counted. It NACKs its address until the MCU's
  expander bit 9 (register $94 bit 1) releases its reset.
  MCU: an 8-bit regmap whose pointer survives a STOP (DsiV2Read's shape).

Asserted: bus identity and mux per connector (FUNCSEL 2 on 40/41, 3 on
38/39), the header block untouched by display traffic and vice versa, the
per-instance state kept across switches (rate, up), MCU identify + power-on,
the Goodix identity/config/frame reads as write + RESTART + read + STOP,
frame clear, not-ready, NACK and non-DesignWare refusals, the #I2C_* /
#DWI2C_* code equality i2c.pi4's pass-through depends on, and the trace's
"not sampled" BSC fields. NO-HOLD and HOLD bus variants.

  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_touch_pi5_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                                          # noqa: E402
from gpio_rp1_check import Rp1Gpio, IO_BANK0, PADS_BANK0      # noqa: E402
from i2c_dw_check import DesignWare, Device, clock_calc       # noqa: E402

sys.path.insert(0, str(d.ROOT / "RaspberryPi5" / "Boot"))

DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")
BUF = 0x2800000
# Model time. The interpreter advances the counter TICKS_PER_STEP per
# instruction (so the MCU's millisecond delays stay cheap to run), and a
# byte on the wire costs BYTE_STEPS instructions' worth of ticks - the same
# CPU-to-bus ratio the header gate uses, and slow enough for the NO-HOLD
# variant to catch a driver that lets the TX FIFO run dry mid-message.
TICKS_PER_STEP = 64
BYTE_STEPS = 500

REL_TIMER = "RaspberryPi4/Lib/timer.pi4"
REL_MBOX = "RaspberryPi4/Lib/mailbox.pi4"
REL_GPIO = "RaspberryPi4/Lib/gpio.pi4"
REL_I2C = "RaspberryPi4/Lib/i2c.pi4"
REL_RP1 = "RaspberryPi4/Lib/gpio_rp1.pi4"
REL_DW = "RaspberryPi4/Lib/i2c_dw.pi4"
REL_MCU = "RaspberryPi4/Lib/dsi_panel_v2.pi4"
REL_GT9 = "RaspberryPi4/Lib/touch_goodix.pi4"
INCLUDES = [REL_TIMER, REL_MBOX, REL_GPIO, REL_I2C, REL_RP1, REL_DW, REL_MCU, REL_GT9]

# What the sources say, pinned; re-derived by sources() when the vault is here.
PINNED = {
    "HEADER": 0x1F_0007_4000,
    "MIPI1": 0x1F_0008_0000,          # i2c_csi_dsi1 == i2c_csi_dsi, RP1 I2C4
    "MIPI0": 0x1F_0008_8000,          # i2c_csi_dsi0, RP1 I2C6
    "MIPI1_PINS": (40, 41), "MIPI1_FSEL": 2,
    "MIPI0_PINS": (38, 39), "MIPI0_FSEL": 3,
    "HZ": 100000, "DRIVE_MA": 12,
}
CODE_PAIRS = (("#I2C_OK", "#DWI2C_OK"), ("#I2C_NACK", "#DWI2C_NACK"),
              ("#I2C_TIMEOUT", "#DWI2C_TIMEOUT"), ("#I2C_ARG", "#DWI2C_ARG"),
              ("#I2C_RANGE", "#DWI2C_RANGE"), ("#I2C_NODEV", "#DWI2C_NODEV"),
              ("#I2C_ABORT", "#DWI2C_ABORT"))


def translate(n, path):
    """A node's first reg through every ancestor's ranges (#address-cells
    and #size-cells honoured), to a CPU address."""
    from dtb_contract import DtbError
    parts = path.split("/")

    def cells(node_path, key, default):
        v = n[node_path].get(key)
        return int.from_bytes(v, "big") if v is not None else default

    def num(b):
        return int.from_bytes(b, "big")
    parent = "/".join(parts[:-1]) or "/"
    ac = cells(parent, "#address-cells", 2)
    addr = num(n[path]["reg"][:4 * ac])
    child = parent
    while child != "/":
        up = "/".join(child.split("/")[:-1]) or "/"
        rng = n[child].get("ranges")
        if rng is None:
            raise DtbError("%s has no ranges" % child)
        cac = cells(child, "#address-cells", 2)
        pac = cells(up, "#address-cells", 2)
        csc = cells(child, "#size-cells", 1)
        if len(rng) == 0:
            child = up
            continue
        step = 4 * (cac + pac + csc)
        hit = None
        for i in range(0, len(rng), step):
            e = rng[i:i + step]
            c = num(e[:4 * cac])
            p = num(e[4 * cac:4 * (cac + pac)])
            s = num(e[4 * (cac + pac):])
            if cac == 3:                       # PCI: drop the space word
                c &= (1 << 64) - 1
            if pac == 3:                       # PCI parent: the space word is not address
                p &= (1 << 64) - 1
            if c <= addr < c + s:
                hit = p + (addr - c)
                break
        if hit is None:
            raise DtbError("$%X is in none of %s's ranges" % (addr, child))
        addr = hit
        child = up
    return addr


def sources(src):
    k = dict(PINNED)
    if src is None or not (src / "Boot staging").is_dir():
        print("  SOURCES NOT CROSS-CHECKED - PINNED table only")
        return k
    from dtb_contract import parse, strings
    pin_c = (src / "Sources" / "pinctrl-rp1.c").read_text(encoding="utf-8", errors="replace")

    def funcsel(pin, func):
        m = re.search(r"^\s*PIN\(%d,\s*([^)]*)\)" % pin, pin_c, re.M)
        if not m:
            d.die("pinctrl-rp1.c has no PIN(%d, ...)" % pin)
        cols = [c.strip() for c in m.group(1).split(",")]
        if func not in cols:
            d.die("pinctrl-rp1.c: %s is not a function of GPIO%d" % (func, pin))
        return cols.index(func)
    for name in ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb"):
        n = parse((src / "Boot staging" / name).read_bytes())
        sy = n["/__symbols__"]

        def lab(x):
            return strings(sy[x])[0]
        if lab("i2c_csi_dsi") != lab("i2c_csi_dsi1"):
            d.die("%s: i2c_csi_dsi is no longer i2c_csi_dsi1 - the default display bus moved" % name)
        by_ph = {int.from_bytes(v["phandle"], "big"): p for p, v in n.items() if "phandle" in v}
        for key, label, func in (("MIPI1", "i2c_csi_dsi1", "i2c4"), ("MIPI0", "i2c_csi_dsi0", "i2c6")):
            p = lab(label)
            node = n[p]
            if "snps,designware-i2c" not in strings(node["compatible"]):
                d.die("%s: %s is not snps,designware-i2c" % (name, label))
            got = translate(n, p)
            if got != k[key]:
                d.die("%s: %s is CPU $%X, PINNED says $%X" % (name, label, got, k[key]))
            if int.from_bytes(node["clock-frequency"], "big") != k["HZ"]:
                d.die("%s: %s clock-frequency changed" % (name, label))
            grp = n[by_ph[int.from_bytes(node["pinctrl-0"][:4], "big")]]
            pins = tuple(int(x[4:]) for x in strings(grp["pins"]))
            if strings(grp["function"]) != [func] or pins != k[key + "_PINS"]:
                d.die("%s: %s pinctrl is %s on %r" % (name, label, strings(grp["function"]), pins))
            if int.from_bytes(grp["drive-strength"], "big") != k["DRIVE_MA"] or "bias-pull-up" not in grp:
                d.die("%s: %s pad settings changed" % (name, label))
            for pin in pins:
                if funcsel(pin, func) != k[key + "_FSEL"]:
                    d.die("pinctrl-rp1.c: %s is column %d on GPIO%d, PINNED says %d"
                          % (func, funcsel(pin, func), pin, k[key + "_FSEL"]))
        if translate(n, "/axi/pcie@1000120000/rp1/i2c@74000") != k["HEADER"]:
            d.die("%s: RP1 I2C1 moved" % name)
    print("  sources: both connector buses, their pins, FUNCSELs and the default re-derived "
          "from the three DTBs and pinctrl-rp1.c in %s - all agree" % src)
    return k


class Mcu:
    """The panel MCU: an 8-bit regmap; the pointer survives a STOP."""
    stretch = False

    def __init__(self, size, ident, ver):
        self.mem = bytearray(256)
        self.mem[0x97], self.mem[0x98], self.mem[0x99] = size, ident, ver
        self.ptr = 0
        self.first = True
        self.writes = []

    def start(self):
        self.first = True

    def write(self, b):
        if self.first:
            self.ptr = b
            self.first = False
        else:
            self.writes.append((self.ptr, b))
            self.mem[self.ptr] = b
            self.ptr = (self.ptr + 1) & 0xFF
        return True

    def read(self):
        v = self.mem[self.ptr]
        self.ptr = (self.ptr + 1) & 0xFF
        return v


class Goodix:
    """A GT9xx: 16-bit big-endian register pointer set by the first two
    written bytes, FORGOTTEN AT A STOP. Held in reset (address NACK) until
    the MCU's expander bit 9 is set."""
    stretch = False

    def __init__(self, mcu, ident=b"911\x00", fw=0x1060, xmax=720, ymax=1280, contacts=5, trig=1):
        self.mcu = mcu
        self.mem = {}
        for i, b in enumerate(ident + bytes([fw & 0xFF, fw >> 8])):
            self.mem[0x8140 + i] = b
        cfg = [0x41, xmax & 0xFF, xmax >> 8, ymax & 0xFF, ymax >> 8, contacts, trig]
        for i, b in enumerate(cfg):
            self.mem[0x8047 + i] = b
        self.mem[0x814E] = 0
        self.ptr = None
        self.hdr = []
        self.blind = 0
        self.clears = 0

    def present(self):
        return bool(self.mcu.mem[0x94] & 0x02)

    def start(self):
        self.hdr = []

    def stop(self):
        self.ptr = None
        self.hdr = []

    def write(self, b):
        if len(self.hdr) < 2:
            self.hdr.append(b)
            if len(self.hdr) == 2:
                self.ptr = (self.hdr[0] << 8) | self.hdr[1]
            return True
        if self.ptr == 0x814E and b == 0:
            self.clears += 1
        self.mem[self.ptr] = b
        self.ptr += 1
        return True

    def read(self):
        if self.ptr is None:
            self.blind += 1
            return 0xA5
        v = self.mem.get(self.ptr, 0)
        self.ptr += 1
        return v

    def frame(self, points):
        self.mem[0x814E] = 0x80 | len(points)
        for i, (pid, x, y, sz) in enumerate(points):
            b = [pid, x & 0xFF, x >> 8, y & 0xFF, y >> 8, sz & 0xFF, sz >> 8, 0]
            for j, v in enumerate(b):
                self.mem[0x814F + 8 * i + j] = v


def driver():
    return ("; a64_touch_pi5_check driver - generated\n" +
            "".join('XIncludeFile "%s"\n' % r for r in INCLUDES) +
            "Global gate_never.i\n"
            "If gate_never = 1\n"
            "  I2cSelectBus(0) : I2cUp() : I2cInit() : I2cIsUp() : I2cWrite(0, 0, 0) : I2cRead(0, 0, 0)\n"
            "  I2cWriteRead(0, 0, 0, 0, 0) : I2cProbe(0) : I2cBus() : I2cBusBase() : I2cBusSda()\n"
            "  I2cBusScl() : I2cBusAlt() : I2cPinsMuxed() : I2cPadLevel(0) : I2cSnapshot(0)\n"
            "  I2cSetSpeed(0) : I2cGetSpeed() : I2cTraceEnable(0) : I2cTraceCount() : I2cTraceGet(0, 0)\n"
            "  I2cTraceGoodixWindow(0) : DwI2cSetDisplayPort(0) : DwI2cDisplayPort() : DwI2cUp()\n"
            "  DwI2cProbe(0) : DwI2cGetSpeed() : DwI2cAbortSourceOn(0) : DwI2cDisplayInst()\n"
            "  DsiV2Begin() : DsiV2Identify() : DsiV2Plausible() : DsiV2Id() : DsiV2Size()\n"
            "  DsiV2Version() : DsiV2Pins() : Gt9Begin() : Gt9Poll() : Gt9Addr() : Gt9Firmware()\n"
            "  Gt9XMax() : Gt9YMax() : Gt9MaxPoints() : Gt9RawX(0) : Gt9RawY(0) : Gt9Id(0) : Gt9Size(0)\n"
            "  Gt9ProdId() : Gt9LastBusCode() : Gt9ConfigVersion() : Gt9IntTrigger() : Gt9CodeHigh()\n"
            "EndIf\n")


def gate(cc, override, workdir, K):
    txt = {r: d.source(r, override) for r in (REL_I2C, REL_DW, REL_GT9)}
    C = lambda rel, name: d.const_in(txt[rel], name, rel)          # noqa: E731
    for a, b in CODE_PAIRS:
        if C(REL_I2C, a) != C(REL_DW, b):
            d.die("%s is %d but %s is %d - i2c.pi4's 2712 pass-through would relabel it"
                  % (a, C(REL_I2C, a), b, C(REL_DW, b)))
    if len({C(REL_I2C, a) for a, _ in CODE_PAIRS} | {C(REL_I2C, "#I2C_NOCHIP"), C(REL_I2C, "#I2C_NOSR"),
                                                      C(REL_I2C, "#I2C_CLKT")}) != len(CODE_PAIRS) + 3:
        d.die("two #I2C_* codes share a number")
    BUS_D, BUS_H = C(REL_I2C, "#I2C_BUS_DISPLAY"), C(REL_I2C, "#I2C_BUS_HEADER")
    NACK, OK, NODEV = C(REL_I2C, "#I2C_NACK"), C(REL_I2C, "#I2C_OK"), C(REL_I2C, "#I2C_NODEV")
    NOTREADY = C(REL_GT9, "#GT9_ENOTREADY")
    FIELD_C, FIELD_EDGE, FIELD_RESULT = (C(REL_I2C, "#I2C_TRACE_FIELD_C"), C(REL_I2C, "#I2C_TRACE_FIELD_EDGE"),
                                         C(REL_I2C, "#I2C_TRACE_FIELD_RESULT"))
    EDGE_END = C(REL_I2C, "#I2C_TRACE_EDGE_END")

    img, procs = d.build(cc, driver(), "touch_pi5_drv", workdir, override, INCLUDES)
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1

    def machine(hold, disp_comp=None):
        gpio = Rp1Gpio()
        mcu1, mcu0 = Mcu(0x07, 0xC3, 0x12), Mcu(0x0A, 0x5A, 0x21)
        gt1 = Goodix(mcu1)
        gt0 = Goodix(mcu0, ident=b"9271", fw=0x2201, xmax=800, ymax=1280, contacts=10, trig=0)
        box = {}

        def model(addr, size, value):
            for key in ("HEADER", "MIPI1", "MIPI0"):
                if K[key] <= addr < K[key] + 0x1000:
                    return box[key](addr, size, value)
            return gpio(addr, size, value)
        m = d.Machine(img, procs, model, ticks_per_step=TICKS_PER_STEP)
        bt = TICKS_PER_STEP * BYTE_STEPS
        box["HEADER"] = DesignWare(m.cpu, {0x50: Device()}, hold, base=K["HEADER"], byte_ticks=bt)
        box["MIPI1"] = DesignWare(m.cpu, {0x45: mcu1, 0x5D: gt1}, hold, base=K["MIPI1"], byte_ticks=bt,
                                  **({"comp_type": disp_comp} if disp_comp else {}))
        box["MIPI0"] = DesignWare(m.cpu, {0x45: mcu0, 0x14: gt0}, hold, base=K["MIPI0"], byte_ticks=bt)
        return m, box, gpio, (mcu1, gt1, mcu0, gt0)

    def ctrl(gpio, pin):
        bank = 0 if pin < 28 else (1 if pin < 34 else 2)
        first = (0, 28, 34)[bank]
        return gpio.reg.get(IO_BANK0 + bank * 0x4000 + (pin - first) * 8 + 4, 0x1F) & 0x1F

    def pad(gpio, pin):
        bank = 0 if pin < 28 else (1 if pin < 34 else 2)
        first = (0, 28, 34)[bank]
        return gpio.reg.get(PADS_BANK0 + bank * 0x4000 + 4 + (pin - first) * 4, 0)

    for hold in (False, True):
        tag = "HOLD" if hold else "NO-HOLD"
        m, dw, gpio, (mcu1, gt1, mcu0, gt0) = machine(hold)
        call = lambda name, *a: m.signed(m.call(name, *a))              # noqa: E731

        # --- identity of the display bus, before anything is touched -------
        check(call("I2cSelectBus", BUS_D) == 1 and call("I2cBus") == BUS_D, "display bus not selectable")
        check(call("DwI2cDisplayPort") == 1, "the default display connector is not CAM/DISP 1 (i2c_csi_dsi)")
        check(call("I2cBusBase") == K["MIPI1"], "%s: display base $%X, want RP1 I2C4 $%X"
              % (tag, call("I2cBusBase"), K["MIPI1"]))
        check((call("I2cBusSda"), call("I2cBusScl")) == K["MIPI1_PINS"], "display pins are not GPIO 40/41")
        check(call("I2cBusAlt") == K["MIPI1_FSEL"], "display function is not FUNCSEL 2 (i2c4)")
        check(call("I2cIsUp") == 0 and not gpio.log, "%s: asking whether the bus is up touched hardware" % tag)

        # --- up: the connector's pads, not the header's ---------------------
        check(call("I2cUp") == 1, "%s: I2cUp on the display bus failed" % tag)
        for p in K["MIPI1_PINS"]:
            check(ctrl(gpio, p) == K["MIPI1_FSEL"], "GPIO%d is FUNCSEL %d, want %d" % (p, ctrl(gpio, p), K["MIPI1_FSEL"]))
            v = pad(gpio, p)
            check((v >> 2) & 3 == 2 and (v >> 4) & 3 == 3 and v & 0x40 and not v & 0x80,
                  "GPIO%d pad $%X: want pull-up, 12 mA, input on, output enabled" % (p, v))
        for p in (2, 3) + K["MIPI0_PINS"]:
            check(ctrl(gpio, p) == 0x1F, "GPIO%d was muxed by the MIPI1 bring-up" % p)
        hc, lc, _ = clock_calc(100)
        check(dw["MIPI1"].r.get(0x00) == 0x63 and (dw["MIPI1"].r.get(0x14), dw["MIPI1"].r.get(0x18)) == (hc, lc),
              "MIPI1 CON/counts not 100 kHz standard mode with RESTART_EN")
        check(not dw["HEADER"].r and not dw["MIPI0"].r, "another block was programmed")
        check(call("I2cIsUp") == 1 and call("I2cPinsMuxed") == 1, "display bus does not read as up")
        check(call("I2cGetSpeed") == 100000, "display bus speed is not 100 kHz")
        gpio.pad_in = 1 << 40
        check(call("I2cPadLevel", 40) == 1 and call("I2cPadLevel", 41) == 0, "pad levels misread on the display pair")
        gpio.pad_in = 0
        check(call("I2cSnapshot", BUF) == 0, "I2cSnapshot claimed BSC registers on the BCM2712")

        # --- the MCU: probe, identify (pointer across a STOP), power-on ------
        check(call("I2cProbe", 0x45) == OK, "%s: panel MCU not found at $45" % tag)
        check(call("I2cProbe", 0x5D) == NACK, "%s: a Goodix held in reset answered" % tag)
        check(call("DsiV2Identify") == 1 and (call("DsiV2Size"), call("DsiV2Id"), call("DsiV2Version"))
              == (0x07, 0xC3, 0x12), "%s: MCU identity not read" % tag)
        check(call("DsiV2Plausible") == 1, "MCU identity not plausible")
        n0 = len(dw["MIPI1"].txns)
        check(call("DsiV2Begin") == 1, "%s: MCU power-on write failed" % tag)
        check(mcu1.mem[0x94] == 0x03 and mcu1.mem[0x95] == 0x00, "expander not $0300 after DsiV2Begin: %r %r" % (mcu1.writes, dw["MIPI1"].txns[n0:]))
        check(all(t[3] == "stop" for t in dw["MIPI1"].txns[n0:]), "an MCU write did not end in STOP")

        # --- the Goodix: identity and config as write + RESTART + read -------
        call("I2cTraceEnable", 1)
        call("I2cTraceGoodixWindow", 1)
        n0 = len(dw["MIPI1"].txns)
        check(call("Gt9Begin") == 0x5D, "%s: Gt9Begin did not find the GT911 at $5D (code %d)"
              % (tag, call("Gt9LastBusCode")))
        call("I2cTraceGoodixWindow", 0)
        t = dw["MIPI1"].txns[n0:]
        check(t[0] == (0x5D, "w", b"\x81\x40", "restart") and t[1][:2] == (0x5D, "r")
              and len(t[1][2]) == 6 and t[1][3] == "stop",
              "%s: the identity read was not write $8140, RESTART, read 6, STOP: %r" % (tag, t[:2]))
        check(gt1.blind == 0, "%s: %d Goodix bytes were read with no register pointer" % (tag, gt1.blind))
        check(m.cstr(call("Gt9ProdId")) == "911" and call("Gt9Firmware") == 0x1060, "GT911 identity misread")
        check((call("Gt9XMax"), call("Gt9YMax"), call("Gt9MaxPoints"), call("Gt9ConfigVersion"),
               call("Gt9IntTrigger")) == (720, 1280, 5, 0x41, 1), "GT911 config misread")
        check(gt1.clears == 1, "Gt9Begin did not clear the pending frame once")
        nt = call("I2cTraceCount")
        check(nt >= 2 and all(call("I2cTraceGet", i, FIELD_C) & 0xFFFFFFFF == 0xFFFFFFFF for i in range(nt)
                              if call("I2cTraceGet", i, FIELD_EDGE) in (1, EDGE_END)),
              "%s: trace missing, or a BSC field read as a value on the BCM2712" % tag)
        check(any(call("I2cTraceGet", i, FIELD_EDGE) == EDGE_END and call("I2cTraceGet", i, FIELD_RESULT) == OK
                  for i in range(nt)), "no traced Goodix read ended OK")
        call("I2cTraceEnable", 0)

        # --- frames ------------------------------------------------------------
        check(call("Gt9Poll") == NOTREADY and gt1.clears == 1, "a not-ready poll was not left alone")
        gt1.frame([(1, 100, 200, 30), (2, 700, 1279, 12)])
        n0 = len(dw["MIPI1"].txns)
        check(call("Gt9Poll") == 2, "%s: a two-contact frame was not read" % tag)
        got = [(call("Gt9Id", i), call("Gt9RawX", i), call("Gt9RawY", i), call("Gt9Size", i)) for i in (0, 1)]
        check(got == [(1, 100, 200, 30), (2, 700, 1279, 12)], "%s: contacts misread %r" % (tag, got))
        check(gt1.mem[0x814E] == 0 and gt1.clears == 2, "the frame was not cleared")
        t = dw["MIPI1"].txns[n0:]
        check(t[2] == (0x5D, "w", b"\x81\x4f", "restart") and len(t[3][2]) == 16,
              "%s: the contact read was not RESTART-joined 16 bytes: %r" % (tag, t))
        check(gt1.blind == 0, "blind Goodix reads during a frame")

        # --- a NACK in the combined transfer is a NACK -------------------------
        m.poke(BUF, b"\x81\x40")
        check(call("I2cWriteRead", 0x33, BUF, 2, BUF + 16, 4) == NACK, "%s: absent device not NACK" % tag)
        check(call("DwI2cAbortSourceOn", call("DwI2cDisplayInst")) & 1, "7B_ADDR_NOACK not kept")

        # --- the header is its own instance, untouched ---------------------
        check(not dw["HEADER"].txns and not dw["HEADER"].r, "display traffic reached the header block")
        check(call("DwI2cProbe", 0x50) == OK and dw["HEADER"].txns[-1][:2] == (0x50, "r"),
              "%s: the header wrapper did not probe the header block" % tag)
        n1 = len(dw["MIPI1"].txns)
        check(call("I2cSelectBus", BUS_H) == 1 and call("I2cBusBase") == K["HEADER"], "header base wrong")
        check(call("I2cProbe", 0x50) == OK and len(dw["MIPI1"].txns) == n1, "header I2cProbe went elsewhere")
        check(call("I2cSelectBus", BUS_D) == 1 and call("I2cIsUp") == 1, "display state lost across a header call")
        check(call("I2cSetSpeed", 400000) == 400000 and dw["MIPI1"].r.get(0x00) == 0x65, "display 400 kHz")
        check(call("DwI2cGetSpeed") == 100000 and dw["HEADER"].r.get(0x00) == 0x63,
              "the header's rate followed the display's")
        check(call("I2cGetSpeed") == 400000, "display rate lost across a header call")
        check(call("I2cSetSpeed", 100000) == 100000, "display back to 100 kHz")

        # --- the other connector ----------------------------------------------
        check(call("DwI2cSetDisplayPort", 5) == 0 and call("DwI2cDisplayPort") == 1, "port 5 accepted")
        check(call("DwI2cSetDisplayPort", 0) == 1 and call("I2cBusBase") == K["MIPI0"],
              "CAM/DISP 0 is not RP1 I2C6")
        check((call("I2cBusSda"), call("I2cBusScl"), call("I2cBusAlt")) == K["MIPI0_PINS"] + (K["MIPI0_FSEL"],),
              "CAM/DISP 0 pins/function wrong")
        check(call("I2cIsUp") == 0, "CAM/DISP 0 read as up before its bring-up")
        check(call("I2cUp") == 1, "%s: CAM/DISP 0 would not come up" % tag)
        for p in K["MIPI0_PINS"]:
            check(ctrl(gpio, p) == K["MIPI0_FSEL"], "GPIO%d is FUNCSEL %d, want %d" % (p, ctrl(gpio, p), K["MIPI0_FSEL"]))
        check(call("DsiV2Identify") == 1 and call("DsiV2Id") == 0x5A, "CAM/DISP 0 MCU not the one read")
        check(call("DsiV2Begin") == 1 and mcu0.mem[0x94] == 0x03 and mcu1.mem[0x94] == 0x03, "CAM/DISP 0 power-on")
        check(call("Gt9Begin") == 0x14 and m.cstr(call("Gt9ProdId")) == "9271" and call("Gt9MaxPoints") == 10,
              "%s: CAM/DISP 0 Goodix at $14 not found" % tag)
        check(gt0.blind == 0, "blind reads on CAM/DISP 0")
        check(call("DwI2cSetDisplayPort", 1) == 1 and call("I2cBusBase") == K["MIPI1"], "back to CAM/DISP 1")

    # --- a display block that is not DesignWare: refused loudly -------------
    m, dw, gpio, _ = machine(False, disp_comp=0x12345678)
    call = lambda name, *a: m.signed(m.call(name, *a))                  # noqa: E731
    call("I2cSelectBus", BUS_D)
    check(call("I2cUp") == 0, "a non-DesignWare display block came up")
    check(call("I2cProbe", 0x45) == NODEV and not dw["MIPI1"].txns,
          "a non-DesignWare display block was driven, or the refusal is not #I2C_NODEV")
    return checks[0]


MUTATIONS = [
    (REL_DW, "no RESTART on the first read", "              cmd = cmd | #DWI2C_CMD_RESTART\n",
     "              cmd = cmd\n"),
    (REL_DW, "a STOP after the write half", "          If issued = total - 1\n",
     "          If issued = total - 1 Or issued = wn - 1\n"),
    (REL_DW, "I2C4 on FUNCSEL 3 like I2C6", "#DWI2C_I2C4_FUNCSEL = 2", "#DWI2C_I2C4_FUNCSEL = 3"),
    (REL_DW, "I2C6 on FUNCSEL 2 like I2C4", "#DWI2C_I2C6_FUNCSEL = 3", "#DWI2C_I2C6_FUNCSEL = 2"),
    (REL_DW, "the two connectors' blocks swapped", "#DWI2C_I2C4_BASE = $1F00080000", "#DWI2C_I2C4_BASE = $1F00088000"),
    (REL_DW, "the default display is CAM/DISP 0",
     "  If dwi2c_disp_mipi0 <> 0\n    ProcedureReturn #DWI2C_INST_MIPI0",
     "  If dwi2c_disp_mipi0 = 0\n    ProcedureReturn #DWI2C_INST_MIPI0"),
    (REL_DW, "instance state never swapped", "  If inst <> dwi2c_inst\n", "  If inst = -99\n"),
    (REL_DW, "header wrappers left on the last display instance",
     "Procedure.i DwI2cXfer(addr.i, *buf, n.i, rd.i)\n  DwI2cUse(#DWI2C_INST_HEADER)\n",
     "Procedure.i DwI2cXfer(addr.i, *buf, n.i, rd.i)\n  DwI2cUse(dwi2c_inst)\n"),
    (REL_DW, "ABORT back to -9, i2c.pi4's NOCHIP",
     "#DWI2C_ABORT   = -11", "#DWI2C_ABORT   = -9 "),
    (REL_DW, "RX outstanding limit ignored in the combined transfer",
     "        If issued < wn Or (issued - wn - got) < dwi2c_rxdepth",
     "        If issued < wn Or (issued - wn - got) < 1000"),
    (REL_I2C, "the write-read forwarded as two transactions",
     "DwI2cWriteReadOn(I2cDwInst(), addr, *wbuf, wn, *rbuf, rn)",
     "DwI2cXferOn(I2cDwInst(), addr, *wbuf, wn, 0) + DwI2cXferOn(I2cDwInst(), addr, *rbuf, rn, 1)"),
    (REL_I2C, "the selector ignored - every bus is the display",
     "    ProcedureReturn DwI2cDisplayInst()\n  EndIf\n  ProcedureReturn DwI2cHeaderInst()",
     "    ProcedureReturn DwI2cDisplayInst()\n  EndIf\n  ProcedureReturn DwI2cDisplayInst()"),
    (REL_I2C, "I2cIsUp still refuses on 2712", "  ProcedureReturn DwI2cIsUpOn(I2cDwInst())", "  ProcedureReturn 0"),
    (REL_I2C, "the BCM alt reported on 2712",
     "  ProcedureReturn DwI2cFuncSelOf(I2cDwInst())", "  ProcedureReturn #I2C_DISP_PIN_ALT"),
    (REL_I2C, "the pad read through gpio.pi4", "  ProcedureReturn Rp1DigitalRead(pin)", "  ProcedureReturn DigitalRead(pin)"),
    (REL_I2C, "NODEV renumbered", "  #I2C_NODEV = -10", "  #I2C_NODEV = -12"),
    (REL_I2C, "BSC fields read as zero, not 'not sampled'",
     "  ProcedureReturn $FFFFFFFF   ; no BSC", "  ProcedureReturn 0   ; no BSC"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    K = sources(pathlib.Path(a.sources) if a.sources else None)
    top = pathlib.Path(tempfile.mkdtemp(prefix="touch-pi5-"))
    try:
        try:
            n = gate(cc, {}, top / "gate", K)
        except d.GateFail as exc:
            print("a64_touch_pi5_check: FAIL - %s" % exc)
            return 1
        print("a64_touch_pi5_check: PASS - %d checks, NO-HOLD and HOLD bus variants" % n)
        if a.mutate:
            survived = 0
            for i, (rel, why, old, new) in enumerate(MUTATIONS):
                text = (d.ROOT / rel).read_text(encoding="utf-8")
                if text.count(old) != 1:
                    print("  %2d  ERROR     %s: %s (matched %d times)" % (i, rel, why, text.count(old)))
                    survived += 1
                    continue
                try:
                    gate(cc, {rel: text.replace(old, new)}, top / ("m%02d" % i), K)
                except d.GateFail as exc:
                    msg = str(exc).replace("\n", " ")
                    if "would not build" in msg:
                        # A mutant that does not compile proves nothing.
                        print("  %2d  ERROR     %s: %s (did not build)" % (i, rel, why))
                        survived += 1
                        continue
                    print("  %2d  KILLED    %s: %s (%s)" % (i, rel, why, msg[:110]))
                    continue
                print("  %2d  SURVIVED  %s: %s" % (i, rel, why))
                survived += 1
            print("a64_touch_pi5_check mutations: %d killed, %d not" % (len(MUTATIONS) - survived, survived))
            if survived:
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
