#!/usr/bin/env python3
"""Desk gate: the Pi 5's Ethernet - RP1's Cadence GEM (RaspberryPi4/Lib/gem.pi4)
through the ONE link seam (RaspberryPi4/Board/hw_link.pi4) into the ONE stack
(Anvil/Network/net.pbi), built -t pi5.

SILICON OWED. Builds RaspberryPi5/Tests/gem2712_probe.pi5 and runs it on
tools/a64/a64_interp.py against models built here from the pinned sources,
never from gem.pi4:

  pcie2 + RP1   PCIE_STATUS, the inbound window, RP1's config space (1DE4:0001,
                COMMAND). Any RP1 access with the link down is refused (on the
                board it hangs the core); every GEM DMA needs RP1's Bus Master
                Enable and an RP1 BUS address (CPU + $10_0000_0000, &rp1 and
                pcie2 dma-ranges) inside the region the board handed over.
  RP1 GPIO 32   the PHY's ETH_RST_N (active low, 5 ms, dts phy-reset-*): CTRL,
                PAD and the bank-1 SYS_RIO OUT/OE with their SET/CLR aliases.
                No other pin may be touched.
  eth_cfg       CONTROL / STATUS / CLKGEN (rp1-peripherals.pdf Tables 133-139).
  GEM           the registers gem.pi4 names, the MDIO shift register, both
                DMA engines over 16-byte (ADDR64) or 8-byte descriptors, the
                SA1 filter, clear-on-read statistics. THE INIT ORDER IS
                ENFORCED: MDIO only with NCR.MPE and MDC <= 2.5 MHz; queue
                pointers only with RE/TE off; RE/TE only with DMACFG, NCFGR
                (bus width, speed, duplex), SA1, the tie-offs, bus mastering,
                the RGMII clocks and the PHY's delays all right.
  BCM54213PE    at the DTB's MDIO address, held in reset while GPIO 32 is low,
                negotiating after reset or ANRESTART, BMSR's latched-low link
                bit, the AUXCTL MISC and CLK_CTL shadows (the rgmii-id delays).
  THE CACHE     a write-back, write-allocate data cache over the DMA region:
                the GEM reads and writes DRAM only; the CPU sees DRAM only
                through `dc civac` / `dc cvac` / `dc ivac`. A missing clean or
                invalidate shows up as a frame the wire never sees or a
                descriptor the CPU never sees change.

Frames go in on the model's wire and come out on it: real ARP requests and
ICMP echo requests, answered by net.pbi through HwLinkRecv/HwLinkSend, every
ARP reply compared byte for byte and every echo reply parsed and checksummed.
130 ARP requests wrap the 128-entry receive ring and the 8-entry transmit ring.

Scenarios: healthy (PHY held in reset at power-up, 1000/full), phy-hung (line high,
PHY wedged until a real reset), fw-linked (PHY
answering but powered down, 100/full partner, no reset owed), no-cable,
rp1-down, not-gem, tx-stuck, clock-stopped.

MUTANTS (each must go red on a check; a mutant that fails to BUILD is an
ERROR, not a kill): wrong base, the Pi 4 GENET base, RX and TX ownership bits
inverted, TX-buffer clean missing, RX-ring clean missing, RX invalidate
missing, wrong PHY address, PHY delays skipped, DMA address untranslated,
reset pulse too short, SA1 top before bottom, ADDR64 missing.

Run from PowerShell:
  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_gem_pi5_check.py --compiler <PureMetalForge.exe>
"""
from __future__ import annotations

import argparse
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "a64"))
sys.path.insert(0, str(ROOT / "tools"))
from a64_interp import A64, AlignmentFault, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402
import fdt_check as FC  # noqa: E402  (the N-cell ranges oracle, and dtb_contract)

FIXTURE = pathlib.PurePosixPath("RaspberryPi5/Tests/gem2712_probe.pi5")
LIBRARY = pathlib.PurePosixPath("RaspberryPi4/Lib/gem.pi4")
SEAM = pathlib.PurePosixPath("RaspberryPi4/Board/hw_link.pi4")
HAL = pathlib.PurePosixPath("Anvil/Hal/hal.pbi")
DEFAULT_SOURCES = pathlib.Path(os.environ.get("PI5_SOURCES", str(ROOT / "RaspberryPi5" / "Reference")))

LOAD, STACK, LOADER_SP, LOADER_LR = 0x00400000, 0x03000000, 0x00100000, 0xDEADBEE0
CTL, OUT, DONE = 0x00E00000, 0x00E00100, 0x600DF00D
CNTFRQ, TICKS = 54_000_000, 128        # BCM2712 TF-A counter rate; ticks per step
MS = CNTFRQ // 1000
AN_MS = 300                            # model negotiation time (a real one is ~2-3 s)
DELIVER_EVERY = 6000                   # steps between frames arriving on the wire
REGION, REGION_BYTES = 0x08100000, 0x80000   # eth_globals.pi4 #ETH_RX_BASE / _BYTES
LINE = 64

# ---- pinned, and re-derived from the three DTBs below when they are present
PINNED = {
    "GEM": (0x1F00100000, "rp1.dtsi ethernet@100000 reg through &rp1 + pcie2 ranges"),
    "PHY_ADDR": (1, "ethernet-phy@1 reg (phy-handle)"),
    "RESET_GPIO": (32, "phy-reset-gpios <&rp1_gpio 32 ...>"),
    "RESET_ACTIVE_LOW": (1, "phy-reset-gpios flags (GPIO_ACTIVE_LOW)"),
    "RESET_MS": (5, "phy-reset-duration"),
    "PHY_MODE": ("rgmii-id", "phy-mode"),
    "PCLK": (200_000_000, "clocks[pclk] -> rp1 clocks assigned-clock-rates"),
    "TX_CLK": (125_000_000, "clocks[tx_clk] -> rp1 clocks assigned-clock-rates"),
    "DMA_OFF": (0x10_0000_0000, "&rp1 dma-ranges 1 + pcie2 dma-ranges 2"),
}
# rp1-peripherals.pdf Table 132 - eth_cfg is not in the DTB
ETH_CFG = 0x1F00104000
RP1_CPU, RP1_SIZE = 0x1F00000000, 0x410000
RC_BASE, RC_SIZE = 0x10_0012_0000, 0x9310    # bcm2712.dtsi pcie2 reg (pcie.pi4)
PCIE_STATUS, LNK_WORD, CFG_INDEX, CFG_DATA = 0x4068, 0xBC, 0x9000, 0x8000
RP1_ID = 0x00011DE4
DMA_WIN = 0x10_0000_0000
# RP1 GPIO: pinctrl-rp1.c rp1_iobanks[] - bank 1 is GPIO 28..33 at +$4000.
IO_BANK0, RIO0, PADS0 = RP1_CPU + 0xD0000, RP1_CPU + 0xE0000, RP1_CPU + 0xF0000


def fail(msg):
    raise SystemExit("a64_gem_pi5_check: FAIL - " + msg)


def rc_bar(n):
    return 0x402C + 8 * (n - 1) if n <= 3 else 0x40D4 + 8 * (n - 4)


def ubus_bar(n):
    return 0x40AC + 8 * (n - 1) if n <= 3 else 0x410C + 8 * (n - 4)


def constants(src):
    k = {n: v for n, (v, _w) in PINNED.items()}
    if src is None:
        print("  SOURCES NOT CROSS-CHECKED - PINNED table only")
        return k
    DC = FC.DC
    for name in FC.DTBS:
        n = DC.parse((src / "Boot staging" / name).read_bytes())
        p = FC.compat_first(n, "raspberrypi,rp1-gem")
        if p is None:
            fail(f"{name}: no raspberrypi,rp1-gem node")
        pr = n[p]

        def byph(ph):
            for q, qp in n.items():
                if qp.get("phandle") and int.from_bytes(qp["phandle"], "big") == ph:
                    return q
            return None
        phy = byph(int.from_bytes(pr["phy-handle"], "big"))
        rg = pr["phy-reset-gpios"]
        ctl = byph(int.from_bytes(rg[:4], "big"))
        clk = [(int.from_bytes(pr["clocks"][i:i + 4], "big"), int.from_bytes(pr["clocks"][i + 4:i + 8], "big"))
               for i in range(0, len(pr["clocks"]), 8)]
        names = DC.strings(pr["clock-names"])
        cn = byph(clk[0][0])
        ac, ar = n[cn]["assigned-clocks"], n[cn]["assigned-clock-rates"]
        rates = {}
        for i in range(len(ar) // 4):
            rates[int.from_bytes(ac[8 * i + 4:8 * i + 8], "big")] = int.from_bytes(ar[4 * i:4 * i + 4], "big")
        rp1 = p.rsplit("/", 1)[0]
        pcie = rp1.rsplit("/", 1)[0]
        dr = n[rp1]["dma-ranges"]          # child 2, parent 3, size 2 cells
        rp1_child = int.from_bytes(dr[0:8], "big")
        rp1_pci = int.from_bytes(dr[12:20], "big")
        pdr = n[pcie]["dma-ranges"]        # child 3, parent 2, size 2 cells: 7 cells each
        off = None
        for o in range(0, len(pdr), 28):
            hi = int.from_bytes(pdr[o:o + 4], "big")
            pci = int.from_bytes(pdr[o + 4:o + 12], "big")
            cpu = int.from_bytes(pdr[o + 12:o + 20], "big")
            if (hi & 0x03000000) == 0x03000000 and pci == rp1_pci and rp1_child == rp1_pci:
                off = pci - cpu
            if hi == 0x43000000 and pci == rp1_pci:
                off = pci - cpu
        got = {
            "GEM": FC.xlate(n, p, 0),
            "PHY_ADDR": int.from_bytes(n[phy]["reg"], "big") if phy else -1,
            "RESET_GPIO": int.from_bytes(rg[4:8], "big") if ctl and "raspberrypi,rp1-gpio" in DC.strings(n[ctl]["compatible"]) else -1,
            "RESET_ACTIVE_LOW": int.from_bytes(rg[8:12], "big") & 1,
            "RESET_MS": int.from_bytes(pr["phy-reset-duration"], "big"),
            "PHY_MODE": DC.strings(pr["phy-mode"])[0],
            "PCLK": rates.get(clk[names.index("pclk")][1], -1),
            "TX_CLK": rates.get(clk[names.index("tx_clk")][1], -1),
            "DMA_OFF": off if off is not None else -1,
        }
        if DC.strings(pr.get("status", b"okay"))[0] != "okay":
            fail(f"{name}: the ethernet node is not okay")
        for key, v in got.items():
            if v != k[key]:
                fail(f"{name}: {key} is {v!r}, PINNED says {k[key]!r}")
    print(f"  sources: GEM base, PHY address, reset GPIO/polarity/duration, phy-mode, pclk, "
          f"tx_clk and the DMA offset re-derived from the three DTBs in {src} - all agree")
    return k


# ======================================================================
#  THE CACHE
# ======================================================================
class Cache:
    """Write-back, write-allocate, never evicts: the worst case for staleness."""

    def __init__(self, mem, lo, hi):
        self.mem, self.lo, self.hi = mem, lo, hi
        self.lines = {}
        self.ops = 0

    def covers(self, a):
        return self.lo <= a < self.hi

    def _line(self, base):
        ln = self.lines.get(base)
        if ln is None:
            ln = [bytearray(self.mem.get(base + i, 0) for i in range(LINE)), False]
            self.lines[base] = ln
        return ln

    def load(self, a, n):
        v = 0
        for i in range(n):
            b = a + i
            ln = self._line(b & ~(LINE - 1))
            v |= ln[0][b & (LINE - 1)] << (8 * i)
        return v

    def store(self, a, v, n):
        for i in range(n):
            b = a + i
            ln = self._line(b & ~(LINE - 1))
            ln[0][b & (LINE - 1)] = (v >> (8 * i)) & 0xFF
            ln[1] = True

    def dc(self, kind, a):
        self.ops += 1
        base = a & ~(LINE - 1)
        ln = self.lines.get(base)
        if ln is None:
            return
        if kind in ("cvac", "civac") and ln[1]:
            for i, b in enumerate(ln[0]):
                self.mem[base + i] = b
            ln[1] = False
        if kind in ("ivac", "civac"):
            del self.lines[base]


DC_OPS = {0xD50B7E20: "civac", 0xD50B7A20: "cvac", 0xD5087620: "ivac"}

# ======================================================================
#  GEM REGISTER MAP (macb.h names - see gem.pi4's [M] note: not pinned)
# ======================================================================
NCR, NCFGR, NSR, USRIO, DMACFG, TSR, RBQP, TBQP = 0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C
RSR, ISR, IDR, MAN, AMP, MID, DCFG1, DCFG6 = 0x20, 0x24, 0x2C, 0x34, 0x54, 0xFC, 0x280, 0x294
TBQPH, RBQPH = 0x4C8, 0x4D4
SA = [(0x88 + 8 * i, 0x8C + 8 * i) for i in range(4)]
STATS = range(0x100, 0x1A8, 4)
NCR_RE, NCR_TE, NCR_MPE, NCR_CLRSTAT, NCR_TSTART = 4, 8, 0x10, 0x20, 0x200
NCFGR_SPD, NCFGR_FD, NCFGR_BIG, NCFGR_GBE, NCFGR_DRFCS = 1, 2, 0x100, 0x400, 0x20000
MDC_DIV = [8, 16, 32, 48, 64, 96, 128, 224]
ADDR64 = 1 << 30
RX_USED, RX_WRAP, RX_SOF, RX_EOF = 1, 2, 1 << 14, 1 << 15
TX_USED, TX_WRAP, TX_LAST = 1 << 31, 1 << 30, 1 << 15
QUEUES = (1, 2, 3)                      # the model's DCFG6 says queues 1..3 exist
DCFG6_VAL = (1 << 23) | 0x0E
DCFG1_VAL = (4 << 25)                  # 128-bit AXI data (rp1-peripherals ch. 7)
MID_GEM, MID_MACB = (0x7 << 16) | 0x0109, (0x1 << 16) | 0x0119
PHY_ID = (0x600D, 0x84A2)              # BCM54213PE, under the BCM54210E entry

SCENARIOS = ("healthy", "fw-linked", "phy-hung", "no-cable", "rp1-down", "not-gem", "tx-stuck", "clock-stopped")


class Board:
    def __init__(self, cpu, scen, k):
        self.cpu, self.scen, self.k = cpu, scen, k
        self.mem = cpu.memory
        self.cache = Cache(self.mem, REGION, REGION + REGION_BYTES)
        self.bad = []
        self.log = []
        # pcie2 + RP1
        self.rc = {PCIE_STATUS: 0x80 if scen == "rp1-down" else 0xB0, LNK_WORD: ((4 << 4 | 2) << 16),
                   rc_bar(1): 21, rc_bar(1) + 4: 0x10, ubus_bar(1): 1, ubus_bar(1) + 4: 0,
                   0x18: 0x00010100}   # root port buses 0/1/1 - see a64_xhci_pi5_check
        self.cfg = {0x00: RP1_ID, 0x04: 0x00100002}
        self.cfg_index = 0
        self.rp1_touched = False
        # GPIO 32
        bank_j = k["RESET_GPIO"] - 28
        self.bit = 1 << bank_j
        self.ctrl_addr = IO_BANK0 + 0x4000 + bank_j * 8 + 4
        self.pad_addr = PADS0 + 0x4000 + 4 + bank_j * 4
        self.rio = RIO0 + 0x4000
        self.funcsel, self.pad, self.out, self.oe = 0x1F, 0x80, 0, 0
        self.default_level = 0 if scen == "healthy" else 1   # undriven: pulled low = held in reset
        self.asserted = None
        self.assert_tick = -10 ** 12
        self.resets = 0
        # phy-hung: the line is high (out of reset) but the PHY is wedged and
        # silent on MDIO until it gets a proper >= 5 ms reset.
        self.hung = scen == "phy-hung"
        # eth_cfg
        self.ecfg = {0x00: 0, 0x14: 0x80}
        if scen == "clock-stopped":
            self.ecfg[0x14] = 0x200 | 0x40 | 0x08 | 1        # TXCLKDELEN, KILL, override 100M, not enabled
            self.ecfg[0x00] = 0x10                           # memory powered down
        # GEM
        self.g = {NCR: 0, NCFGR: 0x00080000, USRIO: 0, DMACFG: 0x00020784, TSR: 0, RSR: 0, ISR: 0,
                  MAN: 0, AMP: 0, IDR: 0, RBQP: 0, TBQP: 0, RBQPH: 0, TBQPH: 0,
                  MID: MID_MACB if scen == "not-gem" else MID_GEM, DCFG1: DCFG1_VAL, DCFG6: DCFG6_VAL}
        for b, t in SA:
            self.g[b] = 0
            self.g[t] = 0
        for q in QUEUES:
            for base in (0x400, 0x440, 0x480, 0x620):
                self.g[base + 4 * (q - 1)] = 0
        self.stats = {o: 0 for o in STATS}
        self.sa1_active = False
        self.sa1b_written = False
        self.mdio_busy = 0
        self.tx_idx = self.rx_idx = 0
        self.tx_base = self.rx_base = 0
        self.tx_wraps = self.rx_wraps = 0
        self.gem_writes = 0
        self.dma_touched = False
        self.ever_enabled = False
        # PHY
        self.cable = scen != "no-cable"
        self.partner = (100, True) if scen == "fw-linked" else (1000, True)
        self.phy = {0: 0x1140 | (0x0800 if scen == "fw-linked" else 0), 2: PHY_ID[0], 3: PHY_ID[1],
                    4: 0x01E1, 9: 0x0200}
        self.misc = 0x0000
        self.shd = {3: 0x0000}
        self.aux_sel = 0
        self.shd_sel = 0
        self.an_start = None if scen in ("healthy", "phy-hung") else -10 ** 12
        self.latched_low = False
        # wire
        self.pending = []
        self.wire = []
        self.garbled = 0
        self.filtered = 0
        self.nobuf = 0
        self.delivered = 0
        self._gpio_update(0)

    def fail(self, msg):
        if msg not in self.bad:
            self.bad.append(msg)

    # ---- time
    def now(self):
        return self.cpu.cntpct

    # ---- GPIO 32 and the PHY's reset
    def _gpio_update(self, now):
        driven = self.funcsel == 5 and (self.oe & self.bit)
        level = ((self.out & self.bit) != 0) if driven else self.default_level
        asserted = not level     # active low
        if self.asserted is None:
            self.asserted = asserted
            return
        if asserted and not self.asserted:
            self.assert_tick = now
            self.log.append("phy-reset-assert")
        elif not asserted and self.asserted:
            held = now - self.assert_tick
            if held < self.k["RESET_MS"] * MS:
                self.fail(f"the PHY reset was released after {held / MS:.2f} ms - dts phy-reset-duration is "
                          f"{self.k['RESET_MS']} ms, so the BCM54213PE stays in reset")
                self.asserted = asserted
                return
            self.resets += 1
            self.hung = False
            self.log.append("phy-reset-release")
            # out of reset: defaults, and the PHY negotiates by itself
            self.phy[0] = 0x1140
            self.misc, self.shd = 0, {3: 0}
            self.an_start = now
            self.latched_low = True
        self.asserted = asserted

    def phy_in_reset(self):
        return bool(self.asserted) or self.hung

    def phy_link(self):
        if not self.cable or self.phy_in_reset() or self.an_start is None:
            return False
        if self.phy[0] & 0x0C00:          # PDOWN or ISOLATE
            return False
        return self.now() - self.an_start >= AN_MS * MS

    def phy_read(self, reg):
        if self.phy_in_reset():
            return 0xFFFF
        if reg == 1:
            up = self.phy_link()
            v = 0x7949
            if up and not self.latched_low:
                v |= 0x0004
            if up:
                v |= 0x0020
            if up:
                self.latched_low = False
            return v
        if reg == 5:
            return 0xC5E1 if self.partner[0] >= 100 else 0xC061
        if reg == 10:
            return 0x3800 if self.partner[0] == 1000 else 0x3000
        if reg == 0x18:
            return (self.misc & ~0x7) | 0x7 if self.aux_sel == 7 else 0
        if reg == 0x1C:
            return (self.shd.get(self.shd_sel, 0) & 0x3FF) | (self.shd_sel << 10)
        return self.phy.get(reg, 0)

    def phy_write(self, reg, v):
        if self.phy_in_reset():
            return
        if reg == 0:
            if v & 0x8000:
                self.fail("the PHY was soft-reset through BMCR - nothing here asks for that")
            if v & 0x0200:
                self.an_start = self.now()
                self.latched_low = True
                self.log.append("phy-anrestart")
            self.phy[0] = v & ~0x0200
            return
        if reg == 0x18:
            if (v & 0x7) == 0x7 and not (v & 0x8000):
                self.aux_sel = (v >> 12) & 0x7
            elif (v & 0x7) == 0x7:
                self.misc = v & ~0x8007
            return
        if reg == 0x1C:
            if v & 0x8000:
                self.shd[(v >> 10) & 0x1F] = v & 0x3FF
            else:
                self.shd_sel = (v >> 10) & 0x1F
            return
        if reg in (4, 9):
            self.phy[reg] = v
            return
        self.fail(f"PHY register {reg} written ({v:#x}) - not part of this bring-up")

    def phy_delays_ok(self):
        return bool(self.misc & 0x0100) and bool(self.shd.get(3, 0) & 0x0200)

    def phy_resolved(self):
        return self.partner

    # ---- the RGMII clocks and data path
    def rgmii_ok(self):
        c = self.ecfg[0x14]
        if not (c & 0x80) or (c & 0x40) or (c & 0x200) or (c & 0x08):
            return False
        if self.ecfg[0x00] & 0x10:
            return False
        if not self.phy_delays_ok() or not self.phy_link():
            return False
        spd, fd = self.phy_resolved()
        n = self.g[NCFGR]
        mac = 1000 if n & NCFGR_GBE else (100 if n & NCFGR_SPD else 10)
        return mac == spd and bool(n & NCFGR_FD) == fd

    # ---- RP1 DMA
    def bus(self, a, n, what):
        if not (self.cfg[0x04] & 4):
            self.fail(f"the GEM mastered the bus ({what}) before RP1's Bus Master Enable was set")
        if not (self.k["DMA_OFF"] <= a < self.k["DMA_OFF"] + DMA_WIN):
            self.fail(f"the GEM dereferenced ${a:X} for {what} - not an RP1 bus address "
                      f"(a pointer was handed over untranslated)")
            return None
        c = a - self.k["DMA_OFF"]
        if not (REGION <= c and c + n <= REGION + REGION_BYTES):
            self.fail(f"the GEM's DMA for {what} reached ${c:X}, outside the region the board handed over")
            return None
        self.dma_touched = True
        return c

    def dram_rd32(self, a, what):
        c = self.bus(a, 4, what)
        if c is None:
            return None
        return sum(self.mem.get(c + i, 0) << (8 * i) for i in range(4))

    def dram_wr32(self, a, v, what):
        c = self.bus(a, 4, what)
        if c is not None:
            for i in range(4):
                self.mem[c + i] = (v >> (8 * i)) & 0xFF

    # ---- pcie2
    def link_up(self):
        return (self.rc[PCIE_STATUS] & 0x30) == 0x30

    def rc_read(self, off):
        if CFG_DATA <= off < CFG_DATA + 0x1000:
            if not self.link_up():
                self.fail("RP1 config space read with the link down - on silicon this hangs the core")
                return 0xFFFFFFFF
            idx = self.cfg_index
            if ((idx >> 20) & 0xFF, (idx >> 15) & 0x1F, (idx >> 12) & 7) != (1, 0, 0):
                return 0xFFFFFFFF
            return self.cfg.get(off - CFG_DATA, 0)
        return self.rc.get(off, 0)

    def rc_write(self, off, v):
        if off == CFG_INDEX:
            self.cfg_index = v
            return
        if CFG_DATA <= off < CFG_DATA + 0x1000:
            if not self.link_up():
                self.fail("RP1 config space written with the link down")
                return
            if off - CFG_DATA == 0x04:
                self.cfg[0x04] = (self.cfg[0x04] & 0xFFFF0000) | (v & 0xFFFF)
            return
        self.fail(f"pcie2 register ${off:X} written - the BCM2712 path must not change the link")

    # ---- the GEM
    def gem_ready(self, which):
        g = self.g
        probs = []
        d = g[DMACFG]
        if not d & ADDR64:
            probs.append("DMACFG.ADDR64 clear (RP1 needs 64-bit descriptors)")
        if d & (0x40 | 0x80):
            probs.append("DMACFG endian swap set")
        if d & (3 << 28):
            probs.append("DMACFG timestamp words enabled")
        if (d & 0x1F) not in (1, 2, 4, 8, 16):
            probs.append(f"DMACFG burst {d & 0x1F} - RP1 refuses AXI bursts over 16 beats")
        if which == "RE" and ((d >> 16) & 0xFF) * 64 < 1518:
            probs.append(f"DMACFG.RXBS {(d >> 16) & 0xFF} x 64 bytes is under a whole frame")
        n = g[NCFGR]
        want_dbw = {4: 2, 2: 1}.get((g[DCFG1] >> 25) & 7, 0)
        if (n >> 21) & 3 != want_dbw:
            probs.append(f"NCFGR.DBW {(n >> 21) & 3}, DCFG1 says {want_dbw}")
        if which == "RE" and not (n & NCFGR_DRFCS):
            probs.append("NCFGR.DRFCS clear - the FCS would be handed to the stack")
        if not (n & NCFGR_BIG):
            probs.append("NCFGR.BIG clear")
        if which == "RE" and not self.sa1_active:
            probs.append("SA1 not active (bottom then top) - the MAC filter would drop our own frames")
        base = (g[RBQPH] << 32) | g[RBQP] if which == "RE" else (g[TBQPH] << 32) | g[TBQP]
        if base == 0:
            probs.append("queue 0's pointer is zero")
        for q in QUEUES:
            tq = (g[TBQPH] << 32) | g[0x440 + 4 * (q - 1)]
            rq = (g[RBQPH] << 32) | g[0x480 + 4 * (q - 1)]
            if which == "TE":
                c = self.dram_rd32(tq + 4, f"queue {q}'s TX tie-off") if tq else None
                if c is None or not (c & TX_USED):
                    probs.append(f"queue {q}'s TX pointer is not a USED descriptor")
            else:
                a = self.dram_rd32(rq, f"queue {q}'s RX tie-off") if rq else None
                if a is None or not (a & RX_USED):
                    probs.append(f"queue {q}'s RX pointer is not a USED descriptor")
        if not (self.cfg[0x04] & 4):
            probs.append("RP1 Bus Master Enable clear")
        if not self.phy_link():
            probs.append("the PHY has no link")
        if not self.rgmii_ok():
            probs.append("the RGMII path is wrong (eth_cfg CLKGEN, the PHY's rgmii-id delays, or NCFGR "
                         "speed/duplex against the PHY's resolution)")
        for p in probs:
            self.fail(f"NCR.{which} set with {p}")

    def gem_read(self, off):
        g = self.g
        if off == NSR:
            v = 0x2 | (0 if self.mdio_busy else 0x4)
            if self.mdio_busy:
                self.mdio_busy -= 1
            return v
        if off in self.stats:
            v = self.stats[off]
            self.stats[off] = 0
            return v
        if off in g:
            return g[off]
        self.fail(f"GEM register ${off:X} read - not one gem.pi4 should need")
        return 0

    def gem_write(self, off, v):
        g = self.g
        self.gem_writes += 1
        en = g[NCR] & (NCR_RE | NCR_TE)
        if off == NCR:
            old = g[NCR]
            if (v & NCR_RE) and not (old & NCR_RE):
                self.gem_ready("RE")
                self.rx_base, self.rx_idx = (g[RBQPH] << 32) | g[RBQP], 0
                self.ever_enabled = True
            if (v & NCR_TE) and not (old & NCR_TE):
                self.gem_ready("TE")
                self.tx_base, self.tx_idx = (g[TBQPH] << 32) | g[TBQP], 0
                self.ever_enabled = True
            if v & NCR_CLRSTAT:
                for o in self.stats:
                    self.stats[o] = 0
            g[NCR] = v & ~(NCR_CLRSTAT | NCR_TSTART)
            if v & NCR_TSTART:
                if not (v & NCR_TE):
                    self.fail("NCR.TSTART written with transmit disabled")
                else:
                    self.tx_start()
            return
        if off in (RBQP, TBQP, RBQPH, TBQPH) or 0x440 <= off < 0x4C0:
            if en:
                self.fail(f"queue pointer ${off:X} written with RE/TE on - the GEM takes it only while disabled")
            g[off] = v
            return
        if off == MAN:
            if not (g[NCR] & NCR_MPE):
                self.fail("an MDIO frame was written with NCR.MPE clear")
            div = MDC_DIV[(g[NCFGR] >> 18) & 7]
            if self.k["PCLK"] / div > 2_500_000:
                self.fail(f"MDIO clocked at {self.k['PCLK'] / div / 1e6:.2f} MHz - IEEE 802.3 allows 2.5")
            if (v >> 30) != 1 or ((v >> 16) & 3) != 2:
                self.fail(f"MAN ${v:08X} is not a clause-22 frame")
            phya, rega, rw = (v >> 23) & 0x1F, (v >> 18) & 0x1F, (v >> 28) & 3
            data = 0xFFFF
            if phya == self.k["PHY_ADDR"]:
                if rw == 2:
                    data = self.phy_read(rega)
                elif rw == 1:
                    self.phy_write(rega, v & 0xFFFF)
            g[MAN] = (v & 0xFFFF0000) | (data if rw == 2 else (v & 0xFFFF))
            self.mdio_busy = 1
            return
        if off in (TSR, RSR, ISR):
            g[off] &= ~v
            return
        if off == SA[0][0]:
            g[off] = v
            self.sa1_active = False
            self.sa1b_written = True
            return
        if off == SA[0][1]:
            g[off] = v
            self.sa1_active = self.sa1b_written
            return
        if off in (MID, DCFG1, DCFG6) or off in self.stats:
            self.fail(f"read-only GEM register ${off:X} written")
            return
        if off in g:
            g[off] = v
            return
        self.fail(f"GEM register ${off:X} written - not one gem.pi4 should touch")

    def dsize(self):
        return 16 if self.g[DMACFG] & ADDR64 else 8

    def desc_addr(self, d):
        lo = self.dram_rd32(d, "a descriptor")
        if lo is None:
            return None, None
        hi = self.dram_rd32(d + 8, "a descriptor") if self.dsize() == 16 else 0
        return lo, hi

    def tx_start(self):
        if self.scen == "tx-stuck":
            return
        frame = bytearray()
        first = None
        for _ in range(64):
            d = self.tx_base + self.tx_idx * self.dsize()
            ctrl = self.dram_rd32(d + 4, "a TX descriptor")
            if ctrl is None:
                return
            if ctrl & TX_USED:
                self.g[TSR] |= 1
                return
            lo, hi = self.desc_addr(d)
            if lo is None:
                return
            ln = ctrl & 0x3FFF
            c = self.bus(((hi or 0) << 32) | lo, ln, "a TX buffer")
            if c is None:
                return
            frame += bytes(self.mem.get(c + i, 0) for i in range(ln))
            if first is None:
                first = (d, ctrl)
            if ctrl & TX_LAST:
                fd, fc = first
                self.dram_wr32(fd + 4, fc | TX_USED, "a TX descriptor")
                if self.rgmii_ok():
                    self.wire.append(bytes(frame))
                    self.stats[0x108] += 1
                else:
                    self.garbled += 1
                self.g[TSR] |= 0x20
                frame, first = bytearray(), None
            if ctrl & TX_WRAP:
                self.tx_idx = 0
                self.tx_wraps += 1
            else:
                self.tx_idx += 1
        self.fail("64 TX descriptors in one TSTART - the ring has no USED end marker")

    def deliver(self):
        if not self.pending or not (self.g[NCR] & NCR_RE):
            return
        f = self.pending.pop(0)
        if not self.rgmii_ok():
            self.garbled += 1
            return
        mac = self.g[SA[0][0]].to_bytes(4, "little") + (self.g[SA[0][1]] & 0xFFFF).to_bytes(2, "little")
        if f[:6] != b"\xff" * 6 and not (self.sa1_active and f[:6] == mac):
            self.filtered += 1
            return
        d = self.rx_base + self.rx_idx * self.dsize()
        lo, hi = self.desc_addr(d)
        if lo is None:
            return
        if lo & RX_USED:
            self.nobuf += 1
            self.stats[0x1A0] += 1
            return
        data = bytes(f) if self.g[NCFGR] & NCFGR_DRFCS else bytes(f) + b"\xde\xad\xbe\xef"
        if ((self.g[DMACFG] >> 16) & 0xFF) * 64 < len(data):
            self.fail("a frame larger than DMACFG.RXBS arrived - it would span buffers")
            return
        c = self.bus(((hi or 0) << 32) | (lo & ~3), len(data), "an RX buffer")
        if c is None:
            return
        for i, b in enumerate(data):
            self.mem[c + i] = b
        self.dram_wr32(d + 4, len(data) | RX_SOF | RX_EOF, "an RX descriptor")
        self.dram_wr32(d, lo | RX_USED, "an RX descriptor")
        self.stats[0x158] += 1
        self.delivered += 1
        if lo & RX_WRAP:
            self.rx_idx = 0
            self.rx_wraps += 1
        else:
            self.rx_idx += 1

    # ---- the bus
    def mmio(self, addr, size, value):
        """value None = read."""
        now = self.now()
        if 0xFC000000 <= addr < 0x1_0000_0000:
            self.fail(f"a BCM2711 peripheral address ${addr:X} on a BCM2712 build")
            return 0
        if RC_BASE <= addr < RC_BASE + RC_SIZE:
            off = addr - RC_BASE
            if value is None:
                return self.rc_read(off)
            self.rc_write(off, value)
            return 0
        if RP1_CPU <= addr < RP1_CPU + RP1_SIZE:
            self.rp1_touched = True
            if not self.link_up():
                self.fail(f"RP1 ${addr:X} accessed with the PCIe link down - on silicon this hangs the core")
                return 0xFFFFFFFF
            if size != 4:
                self.fail(f"a {size}-byte access to RP1 ${addr:X} - its registers are 32 bits")
            gb = self.k["GEM"]
            if gb <= addr < gb + 0x4000:
                if value is None:
                    return self.gem_read(addr - gb)
                self.gem_write(addr - gb, value)
                return 0
            if ETH_CFG <= addr < ETH_CFG + 0x2C:
                off = addr - ETH_CFG
                if value is None:
                    if off == 0x04:
                        v = 0
                        if self.phy_link():
                            v |= 1 | ({1000: 2, 100: 1}.get(self.partner[0], 0) << 1) | (8 if self.partner[1] else 0)
                        return v
                    return self.ecfg.get(off, 0)
                if off == 0x04:
                    self.fail("eth_cfg STATUS written - it is read-only")
                self.ecfg[off] = value
                return 0
            if addr == self.ctrl_addr:
                if value is None:
                    return self.funcsel
                self.funcsel = value & 0x1F
                self._gpio_update(now)
                return 0
            if addr == self.pad_addr:
                if value is None:
                    return self.pad
                self.pad = value
                return 0
            rel = addr - self.rio
            if 0 <= rel < 0x4000 and (rel & 0xFFF) in (0, 4, 8):
                alias, reg = rel & 0x3000, rel & 0xFFF
                if value is None:
                    if alias:
                        self.fail("a read through a SYS_RIO SET/CLR/XOR alias")
                    return {0: self.out, 4: self.oe, 8: self.out if (self.oe & self.bit) else 0}[reg]
                if reg == 8:
                    self.fail("SYS_RIO IN written")
                    return 0
                if value & ~self.bit:
                    self.fail(f"SYS_RIO bank 1 bits {value & ~self.bit:#x} written - only GPIO {self.k['RESET_GPIO']} is the GEM's")
                cur = self.out if reg == 0 else self.oe
                cur = {0: value, 0x1000: cur ^ value, 0x2000: cur | value, 0x3000: cur & ~value}[alias]
                if reg == 0:
                    self.out = cur
                else:
                    self.oe = cur
                self._gpio_update(now)
                return 0
            self.fail(f"unmodelled RP1 address ${addr:X} - not the GEM, eth_cfg, or GPIO "
                      f"{self.k['RESET_GPIO']}'s CTRL/PAD/SYS_RIO")
            return 0
        self.fail(f"unmodelled device address ${addr:X}")
        return 0


def build(compiler, root, out, fixture=FIXTURE):
    r = subprocess.run([compiler, "--compile", str(fixture), "-t", "pi5", "--load-addr", hex(LOAD),
                        "--stack-addr", hex(STACK), "--entry-returns", "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("BUILD FAILED:\n" + r.stdout[-2500:])


# ======================================================================
#  FRAMES
# ======================================================================
OUR_MAC = bytes.fromhex("02a1b2c3d4e5")
OUR_IP = bytes([192, 168, 137, 2])
HOST_MAC = bytes.fromhex("020000000001")
HOST_IP = bytes([192, 168, 137, 1])


def csum(b):
    if len(b) % 2:
        b += b"\0"
    s = sum(struct.unpack(">%dH" % (len(b) // 2), b))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def arp_request(smac, sip, tip):
    body = struct.pack(">HHBBH", 1, 0x0800, 6, 4, 1) + smac + sip + b"\0" * 6 + tip
    return b"\xff" * 6 + smac + b"\x08\x06" + body


def arp_reply_expected(smac, sip):
    body = struct.pack(">HHBBH", 1, 0x0800, 6, 4, 2) + OUR_MAC + OUR_IP + smac + sip
    f = smac + OUR_MAC + b"\x08\x06" + body
    return f + b"\0" * (60 - len(f))


def icmp_request(seq):
    payload = b"abcdefghijklmnopqrstuvwabcdefghi"
    icmp = struct.pack(">BBHHH", 8, 0, 0, 1, seq) + payload
    icmp = icmp[:2] + struct.pack(">H", csum(icmp)) + icmp[4:]
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(icmp), 0x1234 + seq, 0, 128, 1, 0, HOST_IP, OUR_IP)
    ip = ip[:10] + struct.pack(">H", csum(ip)) + ip[12:]
    return OUR_MAC + HOST_MAC + b"\x08\x00" + ip + icmp


def icmp_reply_ok(f, seq):
    if len(f) < 14 + 20 + 8 + 32 or f[:6] != HOST_MAC or f[6:12] != OUR_MAC or f[12:14] != b"\x08\x00":
        return "ethernet header"
    ip = f[14:34]
    if ip[0] != 0x45 or ip[9] != 1 or ip[12:16] != OUR_IP or ip[16:20] != HOST_IP or csum(ip) != 0:
        return "IP header"
    tl = struct.unpack(">H", ip[2:4])[0]
    icmp = f[34:14 + tl]
    if icmp[0] != 0 or icmp[1] != 0 or csum(bytes(icmp)) != 0:
        return "ICMP type/checksum"
    if struct.unpack(">HH", icmp[4:8]) != (1, seq) or icmp[8:] != b"abcdefghijklmnopqrstuvwabcdefghi":
        return "ICMP id/seq/payload"
    return None


def traffic(n_arp):
    """(frames on the wire in, expected replies out as (kind, data))."""
    frames, want = [], []
    for i in range(n_arp):
        smac = bytes([0x02, 0, 0, 0, 1, i & 0xFF])
        sip = bytes([192, 168, 137, 10 + (i % 200)])
        frames.append(arp_request(smac, sip, OUR_IP))
        want.append(("arp", arp_reply_expected(smac, sip)))
        if i == 1:
            frames.append(icmp_request(7))
            want.append(("icmp", 7))
            frames.append(bytes.fromhex("029999999999") + HOST_MAC + b"\x08\x00" + b"\x45" + b"\0" * 45)
            frames.append(arp_request(HOST_MAC, HOST_IP, bytes([192, 168, 137, 77])))
    frames.append(icmp_request(8))
    want.append(("icmp", 8))
    return frames, want


# ======================================================================
#  ONE RUN
# ======================================================================
def run(img, k, scen, frames, cablein, txonly, limit=40_000_000):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.cntpct_per_instruction = TICKS
    ip = int.from_bytes(OUR_IP, "big")
    ctl = struct.pack("<II", SCENARIOS.index(scen) + 1, len(frames)) + OUR_MAC + b"\0\0"
    ctl += struct.pack("<IIIII", ip, 0xFFFFFF00, 0, 1 if cablein else 0, 1 if txonly else 0)
    for i, b in enumerate(ctl):
        cpu.memory[CTL + i] = b
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, LOADER_SP, LOADER_LR
    bd = Board(cpu, scen, k)
    bd.pending = list(frames)
    cache = bd.cache

    def load(addr, sz):
        cpu.align_guard(addr, sz, False)
        if addr >= 0xFC000000:
            return bd.mmio(addr, sz, None) & ((1 << (8 * sz)) - 1)
        if cache.covers(addr) and not cpu.fetching:
            return cache.load(addr, sz)
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(sz))

    def store(addr, value, sz):
        cpu.align_guard(addr, sz, True)
        value &= (1 << (8 * sz)) - 1
        if addr >= 0xFC000000:
            bd.mmio(addr, sz, value)
            return
        if cache.covers(addr):
            cache.store(addr, value, sz)
            return
        for i in range(sz):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu)
    n = 0
    try:
        while cpu.pc != LOADER_LR:
            n += 1
            if n > limit:
                bd.fail(f"the probe never returned ({limit} steps)")
                break
            if n % DELIVER_EVERY == 0:
                bd.deliver()
            ins = load(cpu.pc, 4)
            if (ins & 0xFFFFFFE0) == 0xD53BE000:          # mrs Xt, cntfrq_el0
                cpu.x[ins & 31] = CNTFRQ
                cpu.pc += 4
                cpu.cntpct += TICKS
                continue
            op = DC_OPS.get(ins & 0xFFFFFFE0)
            if op is not None:
                cache.dc(op, cpu.x[ins & 31])
                cpu.pc += 4
                cpu.cntpct += TICKS
                continue
            plain()
    except AlignmentFault as f:
        bd.fail(f.message())
    except RuntimeError as e:
        bd.fail(f"the interpreter stopped: {e}")
    out = []
    for j in range(22):
        v = struct.unpack_from("<I", bytes(cpu.memory.get(OUT + 4 * j + i, 0) for i in range(4)))[0]
        out.append(v - (1 << 32) if v & 0x80000000 else v)
    return out, bd, n


class Checks:
    def __init__(self, verbose):
        self.bad, self.n, self.verbose = [], 0, verbose

    def __call__(self, cond, msg):
        self.n += 1
        if not cond:
            self.bad.append(msg)
        elif self.verbose:
            print("    ok  " + msg)


def hal_const(name):
    import re
    t = (ROOT / HAL).read_text(encoding="utf-8")
    m = re.search(r"^[ \t]*%s\s*=\s*(-?\$?[0-9A-Fa-f]+)" % re.escape(name), t, re.M)
    if not m:
        fail(f"hal.pbi no longer defines {name}")
    v = m.group(1)
    return int(v[1:], 16) if v.startswith("$") else int(v)


def wire_ok(ck, bd, want, sc):
    ck(len(bd.wire) == len(want), f"{sc}: {len(bd.wire)} frames on the wire, {len(want)} replies owed")
    for i, (kind, w) in enumerate(want):
        if i >= len(bd.wire):
            break
        f = bd.wire[i]
        if kind == "arp":
            ck(f == w, f"{sc}: reply {i} is the byte-exact ARP reply ({f[:42].hex()} vs {w[:42].hex()})")
        else:
            why = icmp_reply_ok(f, w)
            ck(why is None, f"{sc}: reply {i} is a valid echo reply to seq {w} ({why})")


def gate(img, k, verbose, only=None, stop_on_red=False):
    ck = Checks(verbose)
    full = hal_const("#HW_LINK_DUPLEX_FULL")
    RE_TE = NCR_RE | NCR_TE

    def clean(bd, sc, steps):
        for b in bd.bad:
            ck(False, f"{sc}: {b}")
        ck(not bd.bad, f"{sc}: the model saw no fault ({steps} steps)")

    for sc in SCENARIOS:
        if only and sc not in only:
            continue
        before = len(ck.bad)
        if sc == "healthy":
            frames, want = traffic(130)
            o, bd, steps = run(img, k, sc, frames, cablein=True, txonly=False)
            clean(bd, sc, steps)
            ck(o[18] == DONE, f"{sc}: the probe finished ({o[18]:#x})")
            ck((o[0], o[2], o[3]) == (1, 1, 1), f"{sc}: GemProbe, GemSetMac, GemSetRegion all 1 ({o[0]}, {o[2]}, {o[3]}; err {o[1]})")
            ck(o[4] == 1, f"{sc}: GemCableIn found the cable after resetting a silent PHY ({o[4]})")
            ck(o[5] == 1, f"{sc}: GemStart 1 (err {o[6]})")
            ck(bd.resets == 1 and o[15] == 1, f"{sc}: the PHY was held low >= 5 ms and released exactly once ({bd.resets}, {o[15]})")
            ck(o[11] == 1, f"{sc}: HwLinkReady(wired) 1 ({o[11]})")
            ck(o[12] == 1000 and o[13] == full, f"{sc}: HwLinkSpeed 1000, HwLinkDuplex full ({o[12]}, {o[13]})")
            ck((bd.g[NCFGR] & (NCFGR_GBE | NCFGR_SPD | NCFGR_FD)) == (NCFGR_GBE | NCFGR_FD),
               f"{sc}: NCFGR gigabit full duplex ({bd.g[NCFGR]:#x})")
            ck(bd.filtered == 1, f"{sc}: the frame for another station was dropped by the SA1 filter ({bd.filtered})")
            ck(o[7] == bd.delivered == len(frames) - 1, f"{sc}: frames in {o[7]}, delivered {bd.delivered}, sent {len(frames) - 1}")
            ck(o[8] == len(want) and o[9] == 0 and o[10] == 0, f"{sc}: replies out {o[8]} of {len(want)}, refusals {o[9]}/{o[10]}")
            wire_ok(ck, bd, want, sc)
            ck(bd.rx_wraps >= 1 and bd.tx_wraps >= 1, f"{sc}: both rings wrapped (rx {bd.rx_wraps}, tx {bd.tx_wraps})")
            ck(bd.nobuf == 0 and bd.garbled == 0, f"{sc}: no frame found its buffer still the CPU's, none garbled ({bd.nobuf}, {bd.garbled})")
            ck(bd.cache.ops > 0, f"{sc}: cache maintenance was issued ({bd.cache.ops} lines)")
            ck(o[14] == 1 and not (bd.g[NCR] & RE_TE) and o[21] == 0, f"{sc}: GemStopChecked 1, RE/TE clear, not started ({o[14]}, {bd.g[NCR]:#x}, {o[21]})")
        elif sc == "fw-linked":
            frames, want = traffic(3)
            o, bd, steps = run(img, k, sc, frames, cablein=True, txonly=False)
            clean(bd, sc, steps)
            ck(o[18] == DONE, f"{sc}: the probe finished")
            ck(o[4] == 0 and bd.resets == 0 and o[15] == 0, f"{sc}: an answering, powered-down PHY is not reset and reports no cable ({o[4]}, {bd.resets})")
            ck(o[5] == 1 and not (bd.phy[0] & 0x0800), f"{sc}: GemStart powered the PHY up and linked (err {o[6]}, BMCR {bd.phy[0]:#x})")
            ck(o[12] == 100 and o[13] == full, f"{sc}: 100 full against a 100-only partner ({o[12]}, {o[13]})")
            ck((bd.g[NCFGR] & (NCFGR_GBE | NCFGR_SPD | NCFGR_FD)) == (NCFGR_SPD | NCFGR_FD), f"{sc}: NCFGR 100 full ({bd.g[NCFGR]:#x})")
            wire_ok(ck, bd, want, sc)
        elif sc == "phy-hung":
            frames, want = traffic(2)
            o, bd, steps = run(img, k, sc, frames, cablein=False, txonly=False)
            clean(bd, sc, steps)
            ck(o[18] == DONE and o[5] == 1, f"{sc}: a wedged PHY (line high, MDIO silent) is reset and GemStart links (err {o[6]})")
            ck(bd.resets == 1 and o[15] == 1, f"{sc}: one reset, driven low from high and held >= 5 ms ({bd.resets}, {o[15]})")
            wire_ok(ck, bd, want, sc)
        elif sc == "no-cable":
            o, bd, steps = run(img, k, sc, [], cablein=True, txonly=False)
            clean(bd, sc, steps)
            ck(o[18] == DONE, f"{sc}: the probe finished - no hang")
            ck(o[4] == 0 and o[5] == 0 and o[6] == -10, f"{sc}: no cable, GemStart 0 with gem error -10 ({o[4]}, {o[5]}, {o[6]})")
            ck(not bd.ever_enabled and not bd.dma_touched, f"{sc}: RE/TE never set and no DMA")
            ck(o[14] == 1, f"{sc}: the checked stop still answers 1")
        elif sc == "rp1-down":
            o, bd, steps = run(img, k, sc, [], cablein=True, txonly=False)
            clean(bd, sc, steps)
            ck(o[18] == DONE and o[0] == 0 and o[1] == -3, f"{sc}: GemProbe 0 with gem error -3 ({o[0]}, {o[1]})")
            ck(not bd.rp1_touched, f"{sc}: nothing on RP1 was touched with its link down")
        elif sc == "not-gem":
            o, bd, steps = run(img, k, sc, [], cablein=True, txonly=False)
            clean(bd, sc, steps)
            ck(o[18] == DONE and o[0] == 0 and o[1] == -5, f"{sc}: GemProbe 0 with gem error -5 ({o[0]}, {o[1]})")
            ck(bd.gem_writes == 0, f"{sc}: no GEM register was written ({bd.gem_writes})")
        elif sc == "tx-stuck":
            o, bd, steps = run(img, k, sc, [], cablein=False, txonly=True)
            clean(bd, sc, steps)
            ck(o[18] == DONE and o[5] == 1, f"{sc}: started (err {o[6]})")
            ck(o[17] == 0 and o[16] == -16, f"{sc}: HwLinkSend 0 with gem error -16 ({o[17]}, {o[16]})")
            ck(o[21] == 0 and not (bd.g[NCR] & RE_TE), f"{sc}: the timeout stopped the MAC ({o[21]}, {bd.g[NCR]:#x})")
            ck(not bd.wire, f"{sc}: nothing reached the wire")
        elif sc == "clock-stopped":
            frames, want = traffic(3)
            o, bd, steps = run(img, k, sc, frames, cablein=False, txonly=False)
            clean(bd, sc, steps)
            ck(o[18] == DONE and o[5] == 1, f"{sc}: GemStart 1 (err {o[6]})")
            c = bd.ecfg[0x14]
            ck((c & 0x80) and not (c & (0x40 | 0x200 | 0x08)) and not (bd.ecfg[0] & 0x10),
               f"{sc}: eth_cfg clock enabled, not killed, no MAC TX delay, no override, memory powered ({c:#x}, {bd.ecfg[0]:#x})")
            wire_ok(ck, bd, want, sc)
        if stop_on_red and len(ck.bad) > before:
            break
    return ck


# ======================================================================
#  MUTANTS - each edits ONE source; the build must succeed
# ======================================================================
MUTANTS = [
    ("wrong base: RP1 $40110000 (CSI) instead of the GEM", LIBRARY,
     "#GEM_BASE       = $1F00100000", "#GEM_BASE       = $1F00110000"),
    ("the Pi 4 GENET base on a Pi 5 build", LIBRARY,
     "#GEM_BASE       = $1F00100000", "#GEM_BASE       = $FD580000"),
    ("RX ownership inverted: buffers handed to the GEM with USED set", LIBRARY,
     "    gem_DescAddr(d, PcieDmaBus(gem_RxBuf(i)), f)", "    gem_DescAddr(d, PcieDmaBus(gem_RxBuf(i)), f | #GEM_RX_USED)"),
    ("TX ownership inverted: a frame armed with USED set", LIBRARY,
     "  ctrl = (n & #GEM_TX_LEN) | #GEM_TX_LAST\n", "  ctrl = (n & #GEM_TX_LEN) | #GEM_TX_LAST | #GEM_TX_USED\n"),
    ("missing cache clean: the TX buffer never cleaned", LIBRARY,
     "  gem_CacheRange(buf, n)\n", "\n"),
    ("missing cache clean: an armed RX line never cleaned", LIBRARY,
     "  gem_CacheRange(gem_region + #GEM_OFF_RXRING + first * #GEM_DESC_SIZE, #GEM_LINE)\n", "\n"),
    ("missing invalidate: the RX descriptor read from a stale line", LIBRARY,
     "  gem_CacheRange(d, #GEM_DESC_SIZE)\n  a = PeekN(d + #GEM_DESC_ADDR)", "  a = PeekN(d + #GEM_DESC_ADDR)"),
    ("wrong PHY address (0)", LIBRARY,
     "#GEM_PHY_ADDR      = 1", "#GEM_PHY_ADDR      = 0"),
    ("the PHY's rgmii-id delays skipped", LIBRARY,
     "  If gem_PhyRgmiiDelays() = 0\n    ProcedureReturn 0\n  EndIf\n", "\n"),
    ("a DMA address handed over untranslated", LIBRARY,
     "  gem_DescAddr(d, PcieDmaBus(buf), 0)", "  gem_DescAddr(d, buf, 0)"),
    ("the PHY reset pulse 1 ms, not 5", LIBRARY,
     "#GEM_PHY_RESET_MS  = 5", "#GEM_PHY_RESET_MS  = 1"),
    ("SA1 top written before bottom", LIBRARY,
     "  gem_Wr(#GEM_SA1B, gem_sab)\n  gem_Wr(#GEM_SA1T, gem_sat)\n", "  gem_Wr(#GEM_SA1T, gem_sat)\n  gem_Wr(#GEM_SA1B, gem_sab)\n"),
    ("DMACFG without ADDR64", LIBRARY,
     " | #GEM_DMACFG_TXPBMS | #GEM_DMACFG_ADDR64\n", " | #GEM_DMACFG_TXPBMS\n"),
    ("the seam's wired receive calls the waiting form for a poll", SEAM,
     "    If ms <= 0\n      n = GemRecv(buf, max)\n", "    If ms <= 0\n      n = GemRecvWait(buf, max, ms)\n"),
]


def mutant_build(compiler, rel, text, work):
    """Build the probe with `rel` replaced by `text`, redirecting the includes
    that lead to it (probe -> hw_link.pi4 -> gem.pi4) to absolute copies."""
    work.mkdir(parents=True, exist_ok=True)
    lib = (ROOT / LIBRARY).read_text(encoding="utf-8").replace("\r\n", "\n")
    seam = (ROOT / SEAM).read_text(encoding="utf-8").replace("\r\n", "\n")
    probe = (ROOT / FIXTURE).read_text(encoding="utf-8").replace("\r\n", "\n")
    if rel == LIBRARY:
        lib = text
    elif rel == SEAM:
        seam = text
    lib_p = work / "mut_gem.pi4"
    lib_p.write_text(lib, encoding="utf-8")
    inc = 'XIncludeFile "RaspberryPi4/Lib/gem.pi4"'
    if seam.count(inc) != 1:
        fail("hw_link.pi4 no longer includes gem.pi4 exactly once")
    seam = seam.replace(inc, 'XIncludeFile "%s"' % lib_p.resolve().as_posix())
    seam_p = work / "mut_hw_link.pi4"
    seam_p.write_text(seam, encoding="utf-8")
    inc = 'XIncludeFile "RaspberryPi4/Board/hw_link.pi4"'
    if probe.count(inc) != 1:
        fail("the probe no longer includes hw_link.pi4 exactly once")
    probe = probe.replace(inc, 'XIncludeFile "%s"' % seam_p.resolve().as_posix())
    probe_p = work / "mut_probe.pi5"
    probe_p.write_text(probe, encoding="utf-8")
    img = work / "m.img"
    build(compiler, ROOT, img, fixture=probe_p.resolve())
    return img


def mutants(compiler, k, work, only_mut=None):
    alive, errors = [], []
    for i, (name, rel, old, new) in enumerate(MUTANTS):
        if only_mut and not any(s in name for s in only_mut):
            continue
        base = (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        if base.count(old) != 1:
            errors.append(f"mutant '{name}': anchor matched {base.count(old)} times")
            print(f"  mutant ERROR {name}: the edit's anchor matched {base.count(old)} times, not once")
            continue
        try:
            img = mutant_build(compiler, rel, base.replace(old, new), work / ("m%02d" % i))
        except SystemExit as e:
            errors.append(f"mutant '{name}' did not build")
            print(f"  mutant ERROR {name}: it did not build - a mutant that does not build proves nothing: {str(e)[:300]}")
            continue
        try:
            ck = gate(img, k, False, stop_on_red=True)
            red, why = bool(ck.bad), (ck.bad[0] if ck.bad else "every check passed")
        except SystemExit as e:
            red, why = True, str(e).splitlines()[0]
        print(f"  mutant {'RED  ' if red else 'ALIVE'} {name}: {why[:160]}")
        if not red:
            alive.append(name)
    return alive, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--only", nargs="*", help="scenarios to run")
    ap.add_argument("--mutant", nargs="*", help="run only mutants whose name contains one of these")
    a = ap.parse_args()
    if not a.compiler:
        fail("pass --compiler or set PMF_COMPILER")
    compiler = str(resolve_compiler(a.compiler))
    src = None if a.sources == "none" else pathlib.Path(a.sources)
    if src is not None and not src.is_dir():
        src = None
    k = constants(src)
    with tempfile.TemporaryDirectory(prefix="pmf_gem_") as td:
        work = pathlib.Path(td)
        img = work / "gem.img"
        build(compiler, ROOT, img)
        ck = gate(img, k, a.verbose, only=a.only)
        for m in ck.bad:
            print("  FAIL " + m)
        alive, errors = ([], []) if a.no_mutants else mutants(compiler, k, work, a.mutant)
    n_mut = len(MUTANTS) if not a.mutant else sum(1 for m in MUTANTS if any(s in m[0] for s in a.mutant))
    if ck.bad or alive or errors:
        print(f"a64_gem_pi5_check: FAIL - {len(ck.bad)} of {ck.n} checks red, {len(alive)} mutant(s) alive, "
              f"{len(errors)} mutant error(s)")
        return 1
    print(f"a64_gem_pi5_check: PASS - {ck.n} checks"
          + ("" if a.no_mutants else f", {n_mut}/{n_mut} mutants red")
          + ". Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
