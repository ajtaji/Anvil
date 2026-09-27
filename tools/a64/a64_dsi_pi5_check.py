#!/usr/bin/env python3
"""Desk gate: the Pi 5 DSI host in command mode - RaspberryPi4/Lib/dsi_dw.pi4
(RP1's Synopsys DesignWare MIPI DSI host and D-PHY), the official 7" panel
(RaspberryPi4/Lib/dsi_panel_rpi7.pi4: the Atmel at $45 and the TC358762
bridge), and the Waveshare v2 panel's DCS table (dsi_panel_v2_dcs.pi4,
unmodified, through dsi_host.pi4's #PMF_CHIP = 2712 DsiDcsWrite forward).

SILICON OWED. The -t pi5 compiled procedures run on tools/a64/a64_interp.py.
The model of the host is written from the pinned
vault Sources/rp1_dsi_dsi.c (raspberrypi/linux 7e030b60792d), not from the
library:

  * EXPECTED WRITE SEQUENCE. rp1dsi_dsi_setup (:459-579) and dphy_init
    (:348-376) are restated below in Python for the panel's mode; every
    register write DsiDwUp makes (host and MIPI CFG) must equal that list,
    value for value and in order. dphy_get_div (:201-248) and the
    hsfreq_table (:260-300, re-parsed from the C file) are restated too.
    Documented deviations (MIPI CFG INTE 0: polled) are in the list.
  * THE D-PHY TEST INTERFACE is a state machine: a code latches on TESTCLK
    falling with TESTEN set, data on TESTCLK rising with it clear; TESTCLR
    clears; a test write with the PHY out of reset is refused. PLL LOCK
    comes only for an M/N/DIV_CTRL that give an in-range VCO and the
    matching hsfreqrange, after PHYRSTZ went SHUTDOWNZ then RSTZ. PWR_UP
    before lock is refused. Lane 0's stop state comes before the others,
    so a driver that does not wait for every lane is caught.
  * PACKETS. A header is only accepted with PWR_UP, lock and every lane
    stopped, with the FIFOs drained from the last one (the driver waits),
    with LP commands selected (the panels' LPM flag) and virtual channel 0;
    a long packet's payload words must match its word count exactly.
    Packets go to a TC358762 model (6-byte generic long writes - lost if
    the Atmel has not powered the bridge) or a DCS panel model (short
    writes; one DCS read answered after the maximum return size is set).
  * The DMA front end of either host is never touched (step 3), and the
    other host's blocks never at all.

Also: the official panel's Atmel (REG_ID $DE, POWERON, PORTB bit 0 after
power-on, PWM, PORTA) and the Waveshare v2 MCU on the connector's RP1 I2C
through i2c.pi4's 2712 branches; a host whose version word reads 0 is
refused with nothing written; a PLL that never locks is refused with the
PHY back in reset; a transfer before the host is up is refused.

MUTANTS (--mutate): a mutant that does not build is an ERROR, not a kill.

  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_dsi_pi5_check.py --compiler <PureMetalForge.exe> [--mutate]
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
from gpio_rp1_check import Rp1Gpio                            # noqa: E402
from i2c_dw_check import DesignWare                           # noqa: E402

DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")
PANEL_REF = pathlib.Path(r"C:\Users\ajtaj\Desktop\Github\PureBasicCode\OpenGl Work\ArduinoBasic"
                         r"\RaspberryPi4\Reference\rpi-6.12.y_panel-raspberrypi-touchscreen.c")
BUF = 0x2800000
TICKS_PER_STEP = 64
BYTE_STEPS = 500

REL_DW = "RaspberryPi4/Lib/dsi_dw.pi4"
REL_HOST = "RaspberryPi4/Lib/dsi_host.pi4"
REL_RPI7 = "RaspberryPi4/Lib/dsi_panel_rpi7.pi4"
REL_V2 = "RaspberryPi4/Lib/dsi_panel_v2.pi4"
REL_DCS = "RaspberryPi4/Lib/dsi_panel_v2_dcs.pi4"
REL_I2C = "RaspberryPi4/Lib/i2c.pi4"
INCLUDES = ["RaspberryPi4/Lib/timer.pi4", "RaspberryPi4/Lib/mailbox.pi4", "RaspberryPi4/Lib/gpio.pi4",
            REL_I2C, "RaspberryPi4/Lib/gpio_rp1.pi4", "RaspberryPi4/Lib/i2c_dw.pi4",
            REL_V2, REL_HOST, REL_DCS, REL_DW, REL_RPI7]

# The blocks (rp1.dtsi:1152-1190 through the DTB ranges; the touch gate
# proves the translation for the I2C blocks the same way).
HOSTS = {1: dict(dma=0x1F_0013_0000, host=0x1F_0013_4000, cfg=0x1F_0013_8000, i2c=0x1F_0008_0000),
         0: dict(dma=0x1F_0011_8000, host=0x1F_0011_C000, cfg=0x1F_0012_0000, i2c=0x1F_0008_8000)}
REFCLK = 50_000_000
VERSION = 0x3133302A        # a DesignWare version word; RP1's own is a silicon question

# rp1_dsi_dsi.c register offsets.
R = dict(VERSION=0x000, PWR_UP=0x004, CLKMGR=0x008, COLOR=0x010, POL=0x014, LPCMDTIM=0x018,
         PCKHDL=0x02C, GEN_VCID=0x030, MODE=0x034, VID_MODE=0x038, PKT_SIZE=0x03C, CHUNKS=0x040,
         NULL=0x044, HSA=0x048, HBP=0x04C, HLINE=0x050, VSA=0x054, VBP=0x058, VFP=0x05C, VACT=0x060,
         CMD_MODE=0x068, GEN_HDR=0x06C, GEN_PLD=0x070, PKT_STATUS=0x074, TO_CNT=0x078, BTA_TO=0x08C,
         LPCLK=0x094, TMR_LPCLK=0x098, TMR=0x09C, PHYRSTZ=0x0A0, PHY_IF=0x0A4, PHY_STATUS=0x0B0,
         TST0=0x0B4, TST1=0x0B8)
ALL_LP = 0x10F7F00
F_LPM, F_SYNC_PULSE, F_BURST, F_NO_EOT, F_NONCONT = 1, 2, 4, 8, 16


def hsfreq_table(src):
    """rp1_dsi_dsi.c:260-300, parsed."""
    c = (src / "Sources" / "rp1_dsi_dsi.c").read_text(encoding="utf-8")
    body = c[c.index("hsfreq_table[] = {"):]
    body = body[:body.index("};")]
    rows = [tuple(int(x, 2) if i == 1 else int(x) for i, x in enumerate(r))
            for r in re.findall(r"\{\s*(\d+),\s*0b([01]+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", body)]
    if len(rows) != 39:
        d.die("rp1_dsi_dsi.c hsfreq_table has %d rows, not 39" % len(rows))
    return rows


def get_div(ref, vco):
    """dphy_get_div, restated."""
    best_err, best = vco, None
    n = 1 + ref // 40_000_000
    while n * 5_000_000 <= ref and n < 100:
        half_m = (n * vco + ref) // (2 * ref)
        if half_m < 150:
            f = (2 * half_m * ref) // n
            err = abs(f - vco)
            if err < best_err:
                best, best_err = (2 * half_m, n), err
                if err == 0:
                    break
        n += 1
    if best is None or 64 * best_err >= vco:
        return None
    m, n = best
    return m, n, (m * ref) // n


def hs_index(table, mhz):
    for i in range(len(table) - 1):
        if mhz <= table[i][0]:
            return i
    return len(table) - 1


def expected_up(table, mode, lanes, bpp, flags):
    """rp1dsi_dsi_setup + dphy_init as the ordered list of (block, off, value)."""
    clock, hd, hss, hse, ht, vd, vss, vse, vt = mode
    byte = (bpp * 125 * min(clock, 200000)) // lanes
    byte = max(10_000_000, min(187_500_000, byte))
    m, n, vco = get_div(REFCLK, 8 * byte)
    idx = hs_index(table, vco // 1_000_000)
    row = table[idx]
    w = [("cfg", 0x04, 0), ("cfg", 0x2C, 0),
         ("host", R["PHY_IF"], lanes - 1), ("host", R["POL"], 0), ("host", R["GEN_VCID"], 0),
         ("host", R["COLOR"], {24: 5, 16: 0}[bpp])]
    mask = 0x3F00
    if flags & F_LPM:
        mask |= 0x8000
    if flags & F_BURST:
        mask |= 2
    elif not flags & F_SYNC_PULSE:
        mask |= 1
    elif 8 * lanes > bpp:
        mask &= ~0x1000
    w += [("host", R["VID_MODE"], mask), ("host", R["CMD_MODE"], ALL_LP if flags & F_LPM else 0),
          ("host", R["PCKHDL"], 4 | (0 if flags & F_NO_EOT else 1)), ("host", R["MODE"], 1)]
    t = (bpp * ht * vd) // (7 * 0x50 * lanes)
    if t > 0xFFFF:
        t = 0
    clkdiv = max(2, 1 + byte // 20_000_000)
    w += [("host", R["TO_CNT"], (t << 16) | 0x40), ("host", R["BTA_TO"], 0xD00),
          ("host", R["CLKMGR"], (0x50 << 8) | clkdiv),
          ("host", R["PKT_SIZE"], hd), ("host", R["CHUNKS"], 0), ("host", R["NULL"], 0),
          ("host", R["HSA"], (bpp * (hse - hss)) // (8 * lanes)),
          ("host", R["HBP"], (bpp * (ht - hse)) // (8 * lanes)),
          ("host", R["HLINE"], (bpp * ht) // (8 * lanes)),
          ("host", R["VSA"], vse - vss), ("host", R["VBP"], vt - vse), ("host", R["VFP"], vss - vd),
          ("host", R["VACT"], vd),
          ("host", R["PHYRSTZ"], 0), ("host", R["TST0"], 2), ("host", R["TST1"], 0),
          ("host", R["TST0"], 3), ("host", R["TST0"], 2)]

    def tx(code, data):
        return [("host", R["TST1"], code | 0x10000), ("host", R["TST0"], 0),
                ("host", R["TST1"], data), ("host", R["TST0"], 2)]
    w += tx(0x44, row[1] << 1) + tx(0x19, 0x30) + tx(0x17, n - 1)
    w += tx(0x18, 0x80 | ((m - 1) >> 5)) + tx(0x18, (m - 1) & 0x1F)
    for code in (0x35, 0x45, 0x55, 0x85, 0x95):
        w += tx(code, 0)
    w += [("host", R["PHYRSTZ"], 1), ("host", R["PHYRSTZ"], 3),
          ("host", R["TMR_LPCLK"], row[2] | (row[3] << 16)),
          ("host", R["TMR"], row[4] | (row[5] << 16))]
    c = ht - ((hse - hss) if flags & F_SYNC_PULSE else 0)
    c = int((bpp * c - 64) / (8 * lanes))
    c -= row[5]
    c -= row[4]
    c = int(c / clkdiv) - 24
    c = max(0, c >> 4)
    w += [("host", R["LPCMDTIM"], c << 16),
          ("host", R["LPCLK"], 3 if flags & F_NONCONT else 1), ("host", R["TST0"], 2),
          ("host", R["PWR_UP"], 1)]
    return w, dict(m=m, n=n, vco=vco, idx=idx, byte=vco >> 3, clkdiv=clkdiv, cmdtim=c)


class Atmel:
    """The official 7" panel's microcontroller (panel-raspberrypi-touchscreen.c
    :61-81): REG_ID $80, PORTB bit 0 once the bridge is powered."""
    stretch = False

    def __init__(self, cpu, ident=0xDE):
        self.cpu = cpu
        self.reg = {0x80: ident, 0x81: 0, 0x82: 0, 0x85: 0, 0x86: 0}
        self.ptr = 0
        self.first = True
        self.log = []                       # (tick, reg, value)
        self.portb_reads = 0

    def start(self):
        self.first = True

    def write(self, b):
        if self.first:
            self.ptr = b
            self.first = False
        else:
            if self.ptr not in self.reg:
                d.die("Atmel register $%02X written - not one the driver uses" % self.ptr)
            self.reg[self.ptr] = b
            self.log.append((self.cpu.cntpct, self.ptr, b))
            if self.ptr == 0x85:
                self.portb_reads = 0
        return True

    def read(self):
        if self.ptr == 0x82:
            self.portb_reads += 1
            return 1 if self.reg[0x85] == 1 and self.portb_reads > 2 else 0
        return self.reg.get(self.ptr, 0)


class V2Mcu:
    """The Waveshare v2 MCU (8-bit regmap)."""
    stretch = False

    def __init__(self):
        self.mem = bytearray(256)
        self.mem[0x97], self.mem[0x98], self.mem[0x99] = 0x0A, 0xC3, 0x21
        self.ptr, self.first = 0, True

    def start(self):
        self.first = True

    def write(self, b):
        if self.first:
            self.ptr, self.first = b, False
        else:
            self.mem[self.ptr] = b
            self.ptr = (self.ptr + 1) & 0xFF
        return True

    def read(self):
        v = self.mem[self.ptr]
        self.ptr = (self.ptr + 1) & 0xFF
        return v


class DwDsi:
    """The DesignWare DSI host + D-PHY + MIPI CFG of one RP1 MIPI port."""

    def __init__(self, cpu, table, blocks, sink, version=VERSION, never_lock=False):
        self.cpu, self.table, self.b, self.sink = cpu, table, blocks, sink
        self.version, self.never_lock = version, never_lock
        self.r = {}
        self.cfg = {}
        self.log = []                 # every write: (block, off, value)
        self.identified = False
        self.tst0, self.tst1 = 0, 0
        self.code = None
        self.test = {}                # code -> [data...]
        self.cleared = False
        self.rstz = 0
        self.lock_reads = 0
        self.locked = False
        self.pwr = 0
        self.stop_reads = 0
        self.pld = []
        self.busy = 0
        self.rx = []
        self.rd_busy = 0
        self.packets = []

    def lanes(self):
        return self.r.get(R["PHY_IF"], 0) + 1

    def pll_ok(self):
        t = self.test
        if t.get(0x19, [None])[-1] != 0x30 or 0x17 not in t or len(t.get(0x18, [])) < 2:
            return False
        n = t[0x17][-1] + 1
        hi = [v for v in t[0x18] if v & 0x80]
        lo = [v for v in t[0x18] if not v & 0x80]
        if not hi or not lo:
            return False
        m = (((hi[-1] & 0x0F) << 5) | (lo[-1] & 0x1F)) + 1
        if m % 2 or not 2 <= m <= 300 or not 1 <= n <= 100:
            return False
        if not 5_000_000 <= REFCLK // n <= 40_000_000:
            return False
        vco = m * REFCLK // n
        mhz = vco // 1_000_000
        if not 80 <= mhz <= 1500:
            return False
        want = self.table[hs_index(self.table, mhz)][1] << 1
        return t.get(0x44, [None])[-1] == want

    def stop_mask(self):
        n = self.lanes()
        return 0x10 | (0x80 if n >= 2 else 0) | (0x200 if n >= 3 else 0) | (0x800 if n >= 4 else 0)

    def phy_status(self):
        v = 0
        if self.rstz == 3 and self.pll_ok() and not self.never_lock:
            self.lock_reads += 1
            if self.lock_reads > 3:
                self.locked = True
        if self.locked:
            v |= 1
        if self.pwr and self.locked:
            self.stop_reads += 1
            if self.stop_reads > 2:
                v |= 0x10
            if self.stop_reads > 6:
                v |= self.stop_mask()
        return v

    def all_stopped(self):
        return self.pwr and self.locked and (self.stop_reads > 6 or (self.lanes() == 1 and self.stop_reads > 2))

    def __call__(self, addr, size, value):
        if size != 4:
            d.die("DSI access of %d bytes at $%X" % (size, addr))
        if self.b["dma"] <= addr < self.b["dma"] + 0x1000:
            d.die("the DSI DMA front end at $%X was touched - that is step 3" % addr)
        if self.b["cfg"] <= addr < self.b["cfg"] + 0x1000:
            off = addr - self.b["cfg"]
            if value is None:
                return self.cfg.get(off, 0)
            if not self.identified:
                d.die("MIPI CFG written before the host's version word was read")
            self.cfg[off] = value
            self.log.append(("cfg", off, value))
            return
        off = addr - self.b["host"]
        if value is None:
            if off == R["VERSION"]:
                self.identified = True
                return self.version
            if off == R["PHY_STATUS"]:
                return self.phy_status()
            if off == R["PKT_STATUS"]:
                if self.busy:
                    self.busy -= 1
                    return 0x0 | (0 if self.rx else 0x10)
                if self.rd_busy:
                    self.rd_busy -= 1
                    return 0x5 | 0x40 | 0x10
                return 0x5 | (0 if self.rx else 0x10)
            if off == R["GEN_PLD"]:
                if not self.rx:
                    d.die("GEN_PLD_DATA read with the read FIFO empty")
                return self.rx.pop(0)
            return self.r.get(off, 0)
        if not self.identified:
            d.die("host register $%X written before its version word was read" % off)
        self.log.append(("host", off, value))
        if off == R["TST0"]:
            clk_was = self.tst0 & 2
            if value & 1:
                self.test, self.cleared, self.code = {}, True, None
            if (value & 2) == 0 and clk_was and self.tst1 & 0x10000:
                if self.rstz:
                    d.die("a D-PHY test code written with the PHY out of reset")
                if not self.cleared:
                    d.die("a D-PHY test code written before TESTCLR")
                self.code = self.tst1 & 0xFF
            if (value & 2) and not clk_was and not self.tst1 & 0x10000 and self.code is not None:
                self.test.setdefault(self.code, []).append(self.tst1 & 0xFF)
                self.code = None
            self.tst0 = value
        elif off == R["TST1"]:
            self.tst1 = value
        elif off == R["PHYRSTZ"]:
            if value == 3 and self.rstz != 1:
                d.die("PHYRSTZ RSTZ set without SHUTDOWNZ first (dphy_init's order)")
            if value & 3 and self.cfg.get(0x04, 1) != 0:
                d.die("the D-PHY started with MIPI CFG not selecting DSI")
            self.rstz = value & 3
            if not self.rstz:
                self.locked, self.lock_reads = False, 0
        elif off == R["PWR_UP"]:
            if value & 1 and not self.locked:
                d.die("PWR_UP with the PLL not locked")
            if value & 1 and R["LPCLK"] not in self.r:
                d.die("PWR_UP before LPCLK_CTRL was set")
            if not value & 1 and self.busy:
                d.die("the host powered down with a packet still in its FIFO (the send did not wait)")
            self.pwr = value & 1
            if not self.pwr:
                self.stop_reads = 0
        elif off == R["GEN_PLD"]:
            if self.busy:
                d.die("payload written with the last packet still in the FIFO")
            self.pld.append(value)
        elif off == R["GEN_HDR"]:
            self.packet(value)
        self.r[off] = value

    def packet(self, hdr):
        if self.busy:
            d.die("header written with the last packet still in the FIFO")
        if not self.all_stopped():
            d.die("packet sent before the host was up with every lane in stop state")
        if self.r.get(R["CMD_MODE"]) != ALL_LP or not self.r.get(R["VID_MODE"], 0) & 0x8000:
            d.die("packet sent without LP command mode (the panels ask for MIPI_DSI_MODE_LPM)")
        dt, vc = hdr & 0x3F, (hdr >> 6) & 3
        if vc:
            d.die("packet on virtual channel %d" % vc)
        if dt in (0x29, 0x39):
            wc = (hdr >> 8) & 0xFFFF
            words = (wc + 3) // 4
            if len(self.pld) != words:
                d.die("long packet of %d bytes with %d payload words queued" % (wc, len(self.pld)))
            data = b"".join(w.to_bytes(4, "little") for w in self.pld)[:wc]
        else:
            if self.pld:
                d.die("short packet $%02X with payload queued" % dt)
            data = bytes([(hdr >> 8) & 0xFF, (hdr >> 16) & 0xFF])
        self.pld = []
        self.busy = 3
        self.packets.append((dt, data))
        reply = self.sink(dt, data)
        if reply is not None:
            self.rd_busy = 4
            self.rx.append(reply)


class Bridge:
    """TC358762: 6-byte generic long writes, reg16 LE + val32 LE. Lost unless
    the Atmel has the bridge powered."""

    def __init__(self, atmel):
        self.atmel = atmel
        self.writes = []
        self.lost = 0
        self.first_tick = None

    def __call__(self, dt, data):
        if dt != 0x29 or len(data) != 6:
            d.die("the bridge got packet $%02X of %d bytes, not a 6-byte generic long write" % (dt, len(data)))
        if self.atmel.reg[0x85] != 1:
            self.lost += 1
            return None
        if self.first_tick is None:
            self.first_tick = self.atmel.cpu.cntpct
        self.writes.append((int.from_bytes(data[:2], "little"), int.from_bytes(data[2:], "little")))
        return None


class DcsPanel:
    POWER_MODE = 0x9C

    def __init__(self):
        self.cmds = []
        self.max_ret = None

    def __call__(self, dt, data):
        if dt == 0x05:
            self.cmds.append((data[0],))
        elif dt == 0x15:
            self.cmds.append((data[0], data[1]))
        elif dt == 0x37:
            self.max_ret = data[0] | (data[1] << 8)
        elif dt == 0x06:
            if self.max_ret != 1:
                d.die("DCS read without the maximum return size set to 1")
            return self.POWER_MODE if data[0] == 0x0A else 0
        else:
            d.die("the DCS panel got packet type $%02X" % dt)
        return None


def dcs_table(text):
    """dsi_panel_v2_dcs.pi4's Data.b stream -> the DCS commands it sends."""
    body = text[text.index("dsi_panel_v2_init:"):text.index("EndDataSection")]
    b = [int(x, 16) for x in re.findall(r"\$([0-9A-Fa-f]{2})", body)]
    out, i = [], 0
    while b[i] != 0xFF:
        if b[i] == 0xFE:
            i += 2
        elif b[i] == 1:
            out.append((b[i + 1],))
            i += 2
        elif b[i] == 2:
            out.append((b[i + 1], b[i + 2]))
            i += 3
        else:
            d.die("unparseable DCS table byte $%02X" % b[i])
    return out


def driver():
    return ("; a64_dsi_pi5_check driver - generated\n" +
            "".join('XIncludeFile "%s"\n' % r for r in INCLUDES) +
            "Global gate_never.i\n"
            "If gate_never = 1\n"
            "  I2cSelectBus(0) : I2cUp() : DwI2cSetDisplayPort(0) : DsiDwSetPort(0) : DsiDwPort()\n"
            "  DsiDwSetModeH(0, 0, 0, 0, 0) : DsiDwSetModeV(0, 0, 0, 0) : DsiDwUp(0, 0, 0)\n"
            "  DsiDwDown() : DsiDwError() : DsiDwVcoHz() : DsiDwByteHz() : DsiDwPllM() : DsiDwPllN()\n"
            "  DsiDwHsRow() : DsiDwEscDiv() : DsiDwCmdTime() : DsiDwSent() : DsiDwFails() : DsiDwIsUp()\n"
            "  DsiDwPllPlan(0, 0) : DsiDwHsIndex(0) : DsiDwGenericWrite(0, 0) : DsiDwVersion()\n"
            "  DsiDcsWrite(0, 0, 0) : DsiDcsRead(0) : DsiPanelPrepare() : DsiPanelSent() : DsiPanelFailed()\n"
            "  DsiV2Begin() : DsiV2Backlight(0) : DsiDwPhyStatus() : DsiDwSetPort(1)\n"
            "  Rpi7Probe() : Rpi7HostUp() : Rpi7Prepare() : Rpi7Enable() : Rpi7Disable() : Rpi7Id()\n"
            "  Rpi7PowerOk() : Rpi7BridgeOk() : Rpi7BridgeBad() : Rpi7Backlight(0) : Rpi7BusCode()\n"
            "EndIf\n")


def gate(cc, override, workdir, src):
    table = hsfreq_table(src)
    dw_text = d.source(REL_DW, override)
    lib = re.findall(r"^\s*Data\.b ([^;\r\n]+)", dw_text[dw_text.index("dsidw_hsfreq:"):], re.M)
    lib_rows = [tuple(int(x.strip()[1:], 16) for x in line.split(",")) for line in lib]
    want_rows = [(r[0] & 0xFF, r[0] >> 8) + r[1:] for r in table]
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1
    check(lib_rows == want_rows, "dsi_dw.pi4's hsfreq DataSection differs from rp1_dsi_dsi.c's table")
    C = lambda name: d.const_in(dw_text, name, REL_DW)                # noqa: E731
    E = {k: C("#DSIDW_" + k) for k in ("ERR_NOHOST", "ERR_NOLOCK", "ERR_NOTUP", "ERR_PLL")}
    dcs_want = dcs_table(d.source(REL_DCS, override))
    rpi7_text = PANEL_REF.read_text(encoding="utf-8") if PANEL_REF.exists() else None

    img, procs = d.build(cc, driver(), "dsi_pi5_drv", workdir, override, INCLUDES)

    def machine(port, sinkname, version=VERSION, never_lock=False, atmel_id=0xDE):
        gpio = Rp1Gpio()
        box = {}
        blocks = HOSTS[port]
        other = HOSTS[1 - port]

        def model(addr, size, value):
            for k in ("dma", "host", "cfg"):
                if other[k] <= addr < other[k] + 0x1000:
                    d.die("the other MIPI port's %s block at $%X was touched" % (k, addr))
            for k in ("dma", "host", "cfg"):
                if blocks[k] <= addr < blocks[k] + 0x1000:
                    return box["dsi"](addr, size, value)
            if blocks["i2c"] <= addr < blocks["i2c"] + 0x1000:
                return box["i2c"](addr, size, value)
            return gpio(addr, size, value)
        m = d.Machine(img, procs, model, ticks_per_step=TICKS_PER_STEP)
        atmel = Atmel(m.cpu, atmel_id)
        v2 = V2Mcu()
        box["i2c"] = DesignWare(m.cpu, {0x45: atmel if sinkname == "bridge" else v2}, True,
                                base=blocks["i2c"], byte_ticks=TICKS_PER_STEP * BYTE_STEPS)
        sink = Bridge(atmel) if sinkname == "bridge" else DcsPanel()
        box["dsi"] = DwDsi(m.cpu, table, blocks, sink, version, never_lock)
        return m, box["dsi"], sink, atmel, v2

    # --- pure arithmetic against the restatement --------------------------
    m, dsi, sink, atmel, v2 = machine(1, "bridge")
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    for mhz in list(range(80, 1501, 37)) + [623, 840, 1500]:
        want = get_div(REFCLK, mhz * 1_000_000)
        got = call("DsiDwPllPlan", REFCLK, mhz * 1_000_000)
        check(got == (want[2] if want else 0) and (not want or (call("DsiDwPllM"), call("DsiDwPllN")) == want[:2]),
              "DsiDwPllPlan(%d MHz) = %d M %d N %d, dphy_get_div says %r"
              % (mhz, got, call("DsiDwPllM"), call("DsiDwPllN"), want))
    for mhz in (0, 80, 89, 90, 649, 650, 1499, 1500, 9999):
        check(call("DsiDwHsIndex", mhz) == hs_index(table, mhz), "DsiDwHsIndex(%d)" % mhz)

    # --- a transfer before the host is up ---------------------------------
    check(call("DsiDcsWrite", 0x11, 0, 0) == 0 and call("DsiDcsRead", 0x0A) == -1 and not dsi.log,
          "DsiDcsWrite/Read with no RP1 host registered did not refuse")
    m.poke(BUF, b"\x10\x02\x03\x00\x00\x00")
    check(call("DsiDwGenericWrite", BUF, 6) == 0 and call("DsiDwError") == E["ERR_NOTUP"] and not dsi.log,
          "a transfer with the host down was not refused as NOTUP with nothing written")

    # --- the official 7" panel on CAM/DISP 1 ------------------------------
    rpi7_mode = (25979, 800, 801, 803, 849, 480, 487, 489, 510)
    if rpi7_text is not None:
        mm = re.search(r"\.clock = 25979400 / 1000,.*?\.hdisplay = (\d+),.*?\.htotal = ([\d +]+),"
                       r".*?\.vdisplay = (\d+),.*?\.vtotal = ([\d +]+),", rpi7_text, re.S)
        check(mm is not None and int(mm.group(1)) == 800 and eval(mm.group(2)) == 849
              and int(mm.group(3)) == 480 and eval(mm.group(4)) == 510,
              "the reference driver's mode is not 800x480, htotal 849, vtotal 510 any more")
    call("I2cSelectBus", 0)
    check(call("I2cUp") == 1, "the display bus would not come up")
    check(call("Rpi7Probe") == 1 and call("Rpi7Id") == 0xDE, "the Atmel ($DE) was not recognised")
    check(atmel.reg[0x85] == 0, "probe did not switch the bridge off first")
    n0 = len(dsi.log)
    check(call("Rpi7HostUp") == 1, "Rpi7HostUp failed (DsiDwError %d, PHY_STATUS $%X)"
          % (call("DsiDwError"), call("DsiDwPhyStatus")))
    want, facts = expected_up(table, rpi7_mode, 1, 24, F_LPM | F_SYNC_PULSE)
    got = dsi.log[n0:]
    first_bad = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), None)
    check(got == want, "DsiDwUp's writes differ from rp1dsi_dsi_setup at #%s: got %r want %r (of %d/%d)"
          % (first_bad, got[first_bad] if first_bad is not None and first_bad < len(got) else got[len(want):len(want) + 2],
             want[first_bad] if first_bad is not None and first_bad < len(want) else None, len(got), len(want)))
    check((call("DsiDwPllM"), call("DsiDwPllN"), call("DsiDwVcoHz"), call("DsiDwHsRow"), call("DsiDwByteHz"),
           call("DsiDwEscDiv"), call("DsiDwCmdTime")) ==
          (facts["m"], facts["n"], facts["vco"], facts["idx"], facts["byte"], facts["clkdiv"], facts["cmdtim"]),
          "the PLL/escape/command-window facts differ from the restatement %r" % facts)
    check(facts["m"] == 112 and facts["n"] == 9, "the 7\" PLL is not M 112 / N 9 (622.2 MHz): %r" % facts)
    check(call("DsiDwIsUp") == 1, "the host is not recorded as up")
    check(call("Rpi7Prepare") == 1, "Rpi7Prepare failed (bridge ok %d bad %d)"
          % (call("Rpi7BridgeOk"), call("Rpi7BridgeBad")))
    bridge_want = [(0x0210, 0x03), (0x0164, 0x05), (0x0168, 0x05), (0x0144, 0x00), (0x0148, 0x00),
                   (0x0114, 0x03), (0x0450, 0x00), (0x0420, 0x00100150), (0x0464, 0x040F),
                   (0x0104, 0x01), (0x0204, 0x01)]
    check(sink.writes == bridge_want and sink.lost == 0,
          "the TC358762 got %r (lost %d), rpi_touchscreen_prepare sends %r" % (sink.writes, sink.lost, bridge_want))
    pon = [t for t, r, v in atmel.log if r == 0x85 and v == 1]
    check(pon and sink.first_tick - pon[-1] >= 54_000 * 20,
          "the first bridge write came less than 20 ms after POWERON")
    check(call("Rpi7PowerOk") == 1, "PORTB bit 0 was not seen after POWERON")
    check(all(p[0] == 0x29 for p in dsi.packets) and len(dsi.packets) == 11, "not eleven generic long writes")
    check(call("Rpi7Enable") == 1 and atmel.reg[0x86] == 255 and atmel.reg[0x81] == 0x04,
          "enable did not set PWM 255 (backlight) and PORTA BIT(2)")
    check(call("Rpi7Backlight", 40) == 1 and atmel.reg[0x86] == 40 and call("Rpi7Backlight", 256) == 0
          and atmel.reg[0x86] == 40, "backlight level not written, or 256 accepted")
    call("DsiDwDown")
    check(dsi.r[R["PWR_UP"]] == 0 and dsi.r[R["PHYRSTZ"]] == 0 and call("DsiDwIsUp") == 0, "DsiDwDown")
    check(call("Rpi7Disable") == 1 and atmel.reg[0x86] == 0 and atmel.reg[0x85] == 0, "disable")

    # --- the Waveshare v2 panel's DCS table on CAM/DISP 0 ------------------
    m, dsi, sink, atmel, v2 = machine(0, "dcs")
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    check(call("DsiDwSetPort", 0) == 1 and call("DsiDwPort") == 0 and call("DwI2cSetDisplayPort", 0) == 1,
          "CAM/DISP 0 not selectable")
    call("I2cSelectBus", 0)
    check(call("I2cUp") == 1 and call("DsiV2Begin") == 1, "the v2 MCU did not power up on CAM/DISP 0")
    ws_mode = (70000, 800, 840, 860, 880, 1280, 1300, 1320, 1324)
    call("DsiDwSetModeH", *ws_mode[:5])
    call("DsiDwSetModeV", *ws_mode[5:])
    n0 = len(dsi.log)
    check(call("DsiDwUp", 2, 24, F_LPM | F_NONCONT) == 1, "DsiDwUp for the Waveshare mode failed (%d)"
          % call("DsiDwError"))
    want, facts = expected_up(table, ws_mode, 2, 24, F_LPM | F_NONCONT)
    check(dsi.log[n0:] == want, "the Waveshare DsiDwUp writes differ from rp1dsi_dsi_setup")
    check(dsi.r[R["LPCLK"]] == 3, "non-continuous clock not selected")
    check(call("DsiDwSetPort", 1) == 0, "the port changed with a host up")
    check(call("DsiPanelPrepare") == 1 and call("DsiPanelFailed") == 0, "DsiPanelPrepare failed (%d sent, %d failed)"
          % (call("DsiPanelSent"), call("DsiPanelFailed")))
    check(sink.cmds == dcs_want, "the panel got %d DCS commands, the table has %d (first difference %r)"
          % (len(sink.cmds), len(dcs_want),
             next(((i, a, b) for i, (a, b) in enumerate(zip(sink.cmds, dcs_want)) if a != b), None)))
    check(call("DsiDcsRead", 0x0A) == DcsPanel.POWER_MODE, "the DCS read of $0A did not return the panel's byte")
    check(call("DsiV2Backlight", 200) == 1 and v2.mem[0x96] == 200, "the v2 backlight (PWM $96) not written")

    # --- refusals -----------------------------------------------------------
    m, dsi, sink, atmel, v2 = machine(1, "bridge", version=0)
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    check(call("Rpi7HostUp") == 0 and call("DsiDwError") == E["ERR_NOHOST"] and not dsi.log,
          "a host whose version word reads 0 was not refused, or was written")
    m, dsi, sink, atmel, v2 = machine(1, "bridge", never_lock=True)
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    check(call("Rpi7HostUp") == 0 and call("DsiDwError") == E["ERR_NOLOCK"] and dsi.r[R["PHYRSTZ"]] == 0
          and dsi.r.get(R["PWR_UP"], 0) == 0, "a PLL that never locks was not refused with the PHY back in reset")
    m, dsi, sink, atmel, v2 = machine(1, "bridge", atmel_id=0x55)
    call = lambda name, *a: m.signed(m.call(name, *a))                 # noqa: E731
    call("I2cSelectBus", 0)
    call("I2cUp")
    check(call("Rpi7Probe") == 0 and atmel.reg[0x85] == 0 and not atmel.log,
          "an Atmel answering $55 was accepted, or written")
    call("DsiDwSetModeH", 25979, 800, 801, 803, 849)
    call("DsiDwSetModeV", 480, 487, 489, 510)
    check(call("DsiDwUp", 5, 24, F_LPM) == 0 and call("DsiDwUp", 1, 18, F_LPM) == 0,
          "five lanes, or 18 bpp (ambiguous 666), accepted")
    return checks[0]


MUTATIONS = [
    (REL_DW, "PLL M rounded down, not to nearest",
     "    halfM = (n * vco + ref) / (2 * ref)", "    halfM = (n * vco) / (2 * ref)"),
    (REL_DW, "N programmed without the minus one",
     "dsidw_PhyTest(#DSIDW_TC_PLL_INPUT_DIV, dsidw_n - 1)", "dsidw_PhyTest(#DSIDW_TC_PLL_INPUT_DIV, dsidw_n)"),
    (REL_DW, "hsfreqrange not shifted", "dsidw_Hs(dsidw_hsidx, 2) << 1)", "dsidw_Hs(dsidw_hsidx, 2))"),
    (REL_DW, "PHY out of reset without SHUTDOWNZ first",
     "  DsiDwWr(#DSIDW_PHYRSTZ, #DSIDW_PHYRSTZ_SHUTDOWNZ)\n  delayMicroseconds(1)\n", ""),
    (REL_DW, "MIPI CFG left on CSI-2", "  dsidw_CfgWr(#DSIDW_MIPICFG_CFG, 0)", "  dsidw_CfgWr(#DSIDW_MIPICFG_CFG, 1)"),
    (REL_DW, "no wait for PLL lock", "dsidw_WaitPhy(#DSIDW_PHY_LOCK, #DSIDW_LOCK_US)", "dsidw_WaitPhy(0, #DSIDW_LOCK_US)"),
    (REL_DW, "lane 1's stop state not waited for", "    mask = mask | $80\n", "    mask = mask | $0\n"),
    (REL_DW, "no FIFO wait after a send",
     "  DsiDwWr(#DSIDW_GEN_HDR, hdr)\n  If dsidw_WaitIdle() = 0\n    dsidw_fails = dsidw_fails + 1\n    ProcedureReturn dsidw_Fail(#DSIDW_ERR_FIFO)\n  EndIf\n",
     "  DsiDwWr(#DSIDW_GEN_HDR, hdr)\n"),
    (REL_DW, "commands in HS, not LP",
     "  If (dsidw_flags & #DSIDW_F_LPM) <> 0\n    DsiDwWr(#DSIDW_CMD_MODE_CFG, #DSIDW_CMD_MODE_ALL_LP)\n  Else\n    DsiDwWr(#DSIDW_CMD_MODE_CFG, 0)\n  EndIf\n  DsiDwRd",
     "  DsiDwWr(#DSIDW_CMD_MODE_CFG, 0)\n  DsiDwRd"),
    (REL_DW, "payload bytes 1 and 2 swapped",
     "      v = v | ((PeekA(*buf + i + 1) & $FF) << 8)", "      v = v | ((PeekA(*buf + i + 1) & $FF) << 16)"),
    (REL_DW, "long-write word count in the wrong byte",
     "#MIPI_DSI_GENERIC_LONG_WRITE | ((n & $FF) << 8)", "#MIPI_DSI_GENERIC_LONG_WRITE | ((n & $FF) << 16)"),
    (REL_DW, "DCS with a parameter sent as the no-parameter type",
     "#MIPI_DSI_DCS_SHORT_WRITE_PARAM | ((cmd & $FF) << 8)", "#MIPI_DSI_DCS_SHORT_WRITE | ((cmd & $FF) << 8)"),
    (REL_DW, "the version check skipped", "  If dsidw_version = 0 Or dsidw_version = $FFFFFFFF",
     "  If dsidw_version = -99"),
    (REL_DW, "escape divider without the plus one", "  dsidw_clkdiv = 1 + byte / #DSIDW_ESC_MAX",
     "  dsidw_clkdiv = byte / #DSIDW_ESC_MAX"),
    (REL_DW, "a PLL that never locks leaves the PHY running",
     "    DsiDwWr(#DSIDW_PHYRSTZ, 0)\n    ProcedureReturn dsidw_Fail(#DSIDW_ERR_NOLOCK)",
     "    ProcedureReturn dsidw_Fail(#DSIDW_ERR_NOLOCK)"),
    (REL_DW, "the hsfreq table row shifted",
     "  Data.b $89, $02, $08, $5A, $26, $49, $1B   ;  649 MHz", "  Data.b $89, $02, $18, $5A, $26, $49, $1B   ;  649 MHz"),
    (REL_HOST, "the 2712 DsiDcsWrite forward fakes success",
     "  ProcedureReturn dsi_rp1_dcsw(cmd, param, nparam)", "  ProcedureReturn 1"),
    (REL_HOST, "DsiDcsWrite with no RP1 host claims success",
     "  If *dsi_rp1_dcsw = 0\n    ProcedureReturn 0", "  If *dsi_rp1_dcsw = 0\n    ProcedureReturn 1"),
    (REL_RPI7, "bridge register bytes swapped",
     "  m[0] = reg & $FF\n  m[1] = (reg >> 8) & $FF", "  m[0] = (reg >> 8) & $FF\n  m[1] = reg & $FF"),
    (REL_RPI7, "the bridge never powered", "  If Rpi7Write(#RPI7_REG_POWERON, 1) = 0",
     "  If Rpi7Write(#RPI7_REG_POWERON, 0) = 0"),
    (REL_RPI7, "backlight at half", "  If Rpi7Backlight(255) = 0", "  If Rpi7Backlight(128) = 0"),
    (REL_RPI7, "no settle after POWERON", "    ProcedureReturn 0\n  EndIf\n  delay(25)\n  i = 0",
     "    ProcedureReturn 0\n  EndIf\n  i = 0"),
    (REL_RPI7, "any Atmel id accepted",
     "  If rpi7_id <> #RPI7_ID_V1 And rpi7_id <> #RPI7_ID_V2", "  If rpi7_id < 0"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    src = pathlib.Path(a.sources)
    if not (src / "Sources" / "rp1_dsi_dsi.c").exists():
        print("a64_dsi_pi5_check: needs the vault's pinned Sources/rp1_dsi_dsi.c under --sources")
        return 1
    top = pathlib.Path(tempfile.mkdtemp(prefix="dsi-pi5-"))
    try:
        try:
            n = gate(cc, {}, top / "gate", src)
        except d.GateFail as exc:
            print("a64_dsi_pi5_check: FAIL - %s" % exc)
            return 1
        print("a64_dsi_pi5_check: PASS - %d checks" % n)
        if a.mutate:
            bad = 0
            for i, (rel, why, old, new) in enumerate(MUTATIONS):
                text = (d.ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
                if text.count(old) != 1:
                    print("  %2d  ERROR     %s: %s (matched %d times)" % (i, rel, why, text.count(old)))
                    bad += 1
                    continue
                try:
                    gate(cc, {rel: text.replace(old, new)}, top / ("m%02d" % i), src)
                except d.GateFail as exc:
                    msg = str(exc).replace("\n", " ")
                    if "would not build" in msg:
                        print("  %2d  ERROR     %s: %s (did not build)" % (i, rel, why))
                        bad += 1
                        continue
                    print("  %2d  KILLED    %s: %s (%s)" % (i, rel, why, msg[:110]))
                    continue
                print("  %2d  SURVIVED  %s: %s" % (i, rel, why))
                bad += 1
            print("a64_dsi_pi5_check mutations: %d killed, %d not" % (len(MUTATIONS) - bad, bad))
            if bad:
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
