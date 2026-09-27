#!/usr/bin/env python3
"""Desk gate for USB host on the Pi 5: the SHARED pcie.pi4 + xhci.pi4
built -t pi5, driving a modelled RP1 DWC3 controller.

The program (RaspberryPi4/Examples/Diagnostics/pi5UsbSelfTest.pi4) stubs
nothing: the real libraries' `CompilerIf #PMF_CHIP = 2712` branches run
on the project's A64 oracle against:

  * the BCM2712 pcie2 register block at $10_0012_0000 - PCIE_STATUS, the
    link word, the ten inbound windows (RC_BARn / UBUS_BARn) and the
    config index/data pair through which RP1 (1DE4:0001) answers;
  * RP1 usbhost0 at CPU $1F_0020_0000: DWC3 global registers (GSNPSID,
    GHWPARAMS0, GCTL, GUCTL1, GUSB2PHYCFG0, GUSB3PIPECTL0, DCTL) in front
    of the xHCI model from a64_xhci_check.py (capability, operational,
    runtime and doorbell registers, command/event rings, ports, a device);
  * RP1's DMA: every address the controller dereferences is an RP1 bus
    address and is translated back through &rp1 dma-ranges entry 1 +
    pcie2 dma-ranges (bus = CPU + $10_0000_0000). An untranslated pointer
    is REFUSED by the model, never silently served from the same memory.

It proves, on the model: DWC3 host-mode setup order and values, xHCI
halt/reset/run, the translated DCBAA/CRCR/ERST/ERDP/contexts/TRB
pointers and the back-translation of event pointers, ERSTBA written
high-dword first (dwc3 write-64-hi-lo-quirk), port status and reset,
Enable Slot, Address Device, control transfers through a wrapped ring,
stall recovery - and LOUD REFUSALS, without a hang, when the link is
down, the inbound window is missing, the controller never halts, never
runs, the DWC3 soft reset never clears, the core is not a DWC3, or it
lacks 64-bit addressing. Mutants of the 2712 branches must go red.

It does NOT prove anything about silicon: RP1's real register values,
which physical ports usbhost0 serves, VBUS, cache maintenance, bulk
transfers (Configure Endpoint is not modelled) or hubs.

Usage:
    py -3 -B tools/a64/a64_xhci_pi5_check.py --compiler <PureMetalForge.exe>
        [--scenario NAME] [--break NAME] [--no-breaks]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import a64_xhci_check as X  # noqa: E402  the xHCI model, reused
from a64_interp import A64, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD = 0x200000
SRC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi5UsbSelfTest.pi4"
PCIE = ROOT / "RaspberryPi4" / "Lib" / "pcie.pi4"
XHCI = ROOT / "RaspberryPi4" / "Lib" / "xhci.pi4"
GPIO = ROOT / "RaspberryPi4" / "Lib" / "gpio_rp1.pi4"

# ---- the addresses, each from the device tree (see pcie.pi4's 2712 header)
RC_BASE = 0x10_0012_0000          # bcm2712.dtsi pcie2 reg
RC_SIZE = 0x9310
RP1_CPU = 0x1F_0000_0000          # pcie2 ranges: PCIe 0 -> CPU 1f_0000_0000
RP1_SIZE = 0x410000               # &rp1 ranges
HOST0 = RP1_CPU + 0x200000        # rp1.dtsi usb@200000
HOST1 = RP1_CPU + 0x300000
HOST_SIZE = 0x100000
DMA_OFF = 0x10_0000_0000          # &rp1 dma-ranges 1 + pcie2 dma-ranges 2
DMA_WIN = 0x10_0000_0000          # 64 GiB

# pcie-brcmstb.c
PCIE_STATUS = 0x4068
LNK_WORD = 0xBC
CFG_INDEX = 0x9000
CFG_DATA = 0x8000


def rc_bar(n: int) -> int:
    return 0x402C + 8 * (n - 1) if n <= 3 else 0x40D4 + 8 * (n - 4)


def ubus_bar(n: int) -> int:
    return 0x40AC + 8 * (n - 1) if n <= 3 else 0x410C + 8 * (n - 4)


# dwc3/core.h
GCTL, GUCTL1, GSNPSID, GHWPARAMS0 = 0xC110, 0xC11C, 0xC120, 0xC140
GUSB2PHYCFG0, GUSB3PIPECTL0, DCTL = 0xC200, 0xC2C0, 0xC704
DWC3_REGS = {GCTL, GUCTL1, GSNPSID, GHWPARAMS0, GUSB2PHYCFG0,
             GUSB3PIPECTL0, DCTL}
PRTCAP_MASK, PRTCAP_HOST = 0x3000, 0x1000
CSFTRST = 1 << 30
U2_SUSPHY, U3_SUSPHY, U3_DISRXDET = 1 << 6, 1 << 17, 1 << 28
GUCTL1_WANT = (1 << 19) | (1 << 17) | (1 << 15)

RP1_ID = 0x00011DE4
GSNPSID_330B = 0x5533330B         # dwc_usb3 v3.30b (rp1-peripherals ch. 5)
HCS1_RP1 = X.MAX_SLOTS | (X.MAX_INTRS << 8) | (3 << 24)   # 3 root ports

SCENARIOS = ("healthy", "link-down", "no-inbound", "never-halts",
             "never-runs", "dwc3-reset-stuck", "not-dwc3", "no-ac64",
             "port-power-stuck")
# xHCI 1.2 5.4.8 / USB 2 root hub bPwrOn2PwrGood: nothing may trust a
# port's status sooner than 20 ms after its power switch was turned on.
POWER_GOOD_TICKS = 20 * X.CNTFRQ // 1000


class TransMem:
    """What the controller's DMA sees: RP1 bus addresses only."""

    def __init__(self, real: dict, ctl: "Rp1Ctl") -> None:
        self.real = real
        self.ctl = ctl

    def _map(self, addr: int) -> int | None:
        if DMA_OFF <= addr < DMA_OFF + DMA_WIN:
            return addr - DMA_OFF
        self.ctl.bad(f"the controller dereferenced ${addr:X}, which is not "
                     f"an RP1 bus address - a pointer was handed over "
                     f"untranslated (ARM physical, not CPU + $10_0000_0000)")
        return None

    def get(self, addr: int, default: int = 0) -> int:
        a = self._map(addr)
        return default if a is None else self.real.get(a, default)

    def __getitem__(self, addr: int) -> int:
        return self.get(addr, 0)

    def __setitem__(self, addr: int, v: int) -> None:
        a = self._map(addr)
        if a is not None:
            self.real[a] = v


class _DmaView:
    def __init__(self, mem: TransMem) -> None:
        self.memory = mem


class Rp1Ctl(X.Ctl):
    def __init__(self, cpu: A64, scenario: str) -> None:
        super().__init__(cpu)
        self.real_cpu = cpu
        self.cpu = _DmaView(TransMem(cpu.memory, self))
        self.scenario = scenario
        self.cfg = {0x00: RP1_ID, 0x04: 0x00100002, 0x10: 0, 0x14: 0}
        self.cfg_index = None
        self.rc: dict[int, int] = {
            PCIE_STATUS: 0x80 if scenario == "link-down" else 0xB0,
            LNK_WORD: ((4 << 4 | 2) << 16),      # x4, 5 GT/s (max-link-speed 2)
        }
        if scenario != "no-inbound":
            # BAR1: PCIe $10_0000_0000, 64 GiB (size code 36 - 15 = 21),
            # remapped to CPU 0 with ACCESS_EN.
            self.rc[rc_bar(1)] = 21
            self.rc[rc_bar(1) + 4] = 0x10
            self.rc[ubus_bar(1)] = 1
            self.rc[ubus_bar(1) + 4] = 0
        self.dwc = {
            GSNPSID: 0x4F54330B if scenario == "not-dwc3" else GSNPSID_330B,
            GHWPARAMS0: 0x00000001,          # host-only core
            GCTL: 0x00002000,                # PRTCAP device at power-on
            GUCTL1: 0,
            GUSB2PHYCFG0: 0x00002440,        # SUSPHY set
            GUSB3PIPECTL0: 0x010E0002 | U3_SUSPHY,
            DCTL: 0,
        }
        self.csft_reads = 0
        self.hc1 = X.HCC1 & ~1 if scenario == "no-ac64" else X.HCC1
        # Ports: 1 = USB 2 with a high-speed device, 2 = USB 2 empty,
        # 3 = SuperSpeed with a device. PPC is set (HCC1 bit 3), and HCRST
        # leaves every port switch OFF - so a driver that does not power
        # the root ports sees nothing at all.
        self.port = {1: 0, 2: X.P_POWER,
                     3: X.P_POWER | X.P_CONNECT | X.P_PE | (X.SPEED_SS << 10)}
        self.port_dev = {1: X.SPEED_HS, 3: X.SPEED_SS}
        self.power_tick: dict[int, int] = {}
        if scenario == "never-halts":
            # The firmware left it running and it will not stop.
            self.reg[X.R_USBCMD] = X.CMD_RUN
            self.reg[X.R_USBSTS] = 0
        self.erstba_hi_first = False
        self.rp1_touched = False
        self.scratch_checked = False
        self.xhci_before_host = False

    # -- the pcie2 block ----------------------------------------------
    def link_up(self) -> bool:
        return (self.rc[PCIE_STATUS] & 0x30) == 0x30

    def rc_read(self, off: int) -> int:
        if CFG_DATA <= off < CFG_DATA + 0x1000:
            if not self.link_up():
                self.bad("RP1 config space read with the link down - on "
                         "silicon this aborts/hangs the core")
                return 0xFFFFFFFF
            self.rp1_touched = True
            idx = self.cfg_index or 0
            bdf = ((idx >> 20) & 0xFF, (idx >> 15) & 0x1F, (idx >> 12) & 7)
            if bdf != (1, 0, 0):
                return 0xFFFFFFFF
            return self.cfg.get(off - CFG_DATA, 0)
        return self.rc.get(off, 0)

    def rc_write(self, off: int, v: int) -> None:
        if off == CFG_INDEX:
            self.cfg_index = v
            return
        if CFG_DATA <= off < CFG_DATA + 0x1000:
            if not self.link_up():
                self.bad("RP1 config space written with the link down")
                return
            idx = self.cfg_index or 0
            if ((idx >> 20) & 0xFF, (idx >> 15) & 0x1F, (idx >> 12) & 7) == (1, 0, 0):
                self.cfg[off - CFG_DATA] = v
                if off - CFG_DATA == 0x04:
                    self.log.append("rp1-command")
            return
        self.bad(f"pcie2 register ${off:X} written - the BCM2712 path must "
                 f"verify the firmware's link and windows, never change them")

    # -- the DWC3 globals ----------------------------------------------
    def dwc_read(self, off: int) -> int:
        if off == DCTL and self.dwc[DCTL] & CSFTRST:
            self.csft_reads += 1
            if self.scenario != "dwc3-reset-stuck" and self.csft_reads >= 3:
                self.dwc[DCTL] &= ~CSFTRST
                self.log.append("dwc3-csftrst-cleared")
        return self.dwc[off]

    def dwc_write(self, off: int, v: int) -> None:
        if off in (GSNPSID, GHWPARAMS0):
            self.bad(f"write to read-only DWC3 register ${off:X}")
            return
        if self.dwc[DCTL] & CSFTRST and off != DCTL:
            self.bad(f"DWC3 register ${off:X} written while the core soft "
                     f"reset was still in progress")
        self.dwc[off] = v & 0xFFFFFFFF
        if off == DCTL and v & CSFTRST:
            self.csft_reads = 0
            self.log.append("dwc3-csftrst")
        if off == GCTL and (v & PRTCAP_MASK) == PRTCAP_HOST:
            self.log.append("dwc3-host")
        if off in (GUSB2PHYCFG0, GUSB3PIPECTL0):
            self.log.append("dwc3-phy")

    def host_mode(self) -> bool:
        return (self.dwc[GCTL] & PRTCAP_MASK) == PRTCAP_HOST

    # -- the xHCI block, gated by the wrapper ---------------------------
    def _port_write(self, n: int, value: int) -> None:
        was = self.port.get(n, 0) & X.P_POWER
        if self.scenario == "port-power-stuck":
            value &= ~X.P_POWER
        super()._port_write(n, value)
        if not was and self.port.get(n, 0) & X.P_POWER:
            self.power_tick[n] = self.ticks
            self.log.append(f"port{n}-powered")
            if self.port_dev.get(n) == X.SPEED_SS:
                # a SuperSpeed link trains by itself once powered
                self.port[n] |= X.P_PE | (X.SPEED_SS << 10)

    def reg_read(self, off: int) -> int:
        if X.R_PORTS <= off < X.R_PORTS + 3 * 0x10 and (off - X.R_PORTS) % 0x10 == 0:
            n = (off - X.R_PORTS) // 0x10 + 1
            t = self.power_tick.get(n)
            if t is not None and self.ticks - t < POWER_GOOD_TICKS:
                self.bad(f"port {n} status trusted before power-good "
                         f"({(self.ticks - t) * 1000 // X.CNTFRQ} ms after the switch)")
        if off == 0x04:
            return HCS1_RP1
        if off == 0x10:
            return self.hc1
        v = super().reg_read(off)
        if off == X.R_USBSTS:
            if self.scenario == "never-halts":
                v &= ~X.STS_HALT
                self.reg[X.R_USBSTS] = v
            elif self.scenario == "never-runs" and self.reg[X.R_USBCMD] & X.CMD_RUN:
                v |= X.STS_HALT
                self.reg[X.R_USBSTS] = v
        return v

    def reg_write(self, off: int, value: int) -> None:
        if off >= X.OP and not self.host_mode():
            self.xhci_before_host = True
            self.bad(f"xHCI register ${off:X} written before the DWC3 core "
                     f"was put in host mode (GCTL.PRTCAPDIR)")
        super().reg_write(off, value)
        if off == X.R_USBCMD and value & X.CMD_RESET:
            # HCRST: with PPC set, every port switch goes off (xHCI 1.2
            # 5.4.8 PP is 0 after reset when PPC = 1 - modelled that way).
            for n in self.port:
                self.port[n] = 0
            self.power_tick.clear()

    def _wide_written(self, base: int, half: int) -> None:
        v = self.wide[base]
        if base == X.R_ERSTBA:
            if half == 1:
                self.erstba_hi_first = True
                return
            if not self.erstba_hi_first:
                self.bad("ERSTBA low dword written without the high dword "
                         "first - a DWC3 xHCI needs hi-lo "
                         "(dwc3 host.c write-64-hi-lo-quirk)")
            self.erstba_hi_first = False
            half = 1
        elif half == 0:
            return
        ptr = v & ~0x3F
        if base == X.R_ERSTBA:
            ptr = v & ~0xF
        if base == X.R_ERDP:
            ptr = v & ~0xF
        if not (DMA_OFF <= ptr < DMA_OFF + DMA_WIN):
            names = {X.R_DCBAAP: "DCBAAP", X.R_CRCR: "CRCR",
                     X.R_ERSTBA: "ERSTBA", X.R_ERDP: "ERDP"}
            self.bad(f"{names[base]} holds ${ptr:X}, which RP1 cannot "
                     f"reach - not translated to CPU + $10_0000_0000")
            return
        if base == X.R_ERDP:
            seg = self.ev_base
            if seg and not (seg <= ptr < seg + 64 * 16):
                self.bad(f"ERDP ${ptr:X} is outside the event ring segment")
            self.log.append("erdp")
            return
        super()._wide_written(base, 1)

    def check_scratch(self) -> None:
        if self.scratch_checked:
            return
        self.scratch_checked = True
        dcbaa = self.wide[X.R_DCBAAP] & ~63
        arr = self.rd(dcbaa, 8)
        if not (DMA_OFF <= arr < DMA_OFF + DMA_WIN):
            self.bad(f"DCBAA[0] (scratchpad array) is ${arr:X}, untranslated")
            return
        for i in range(X.SCRATCHPADS):
            page = self.rd(arr + 8 * i, 8)
            if not (DMA_OFF <= page < DMA_OFF + DMA_WIN):
                self.bad(f"scratchpad page {i} is ${page:X}, untranslated")
        self.log.append("scratch-ok")

    def doorbell(self, index: int, value: int) -> None:
        self.check_scratch()
        super().doorbell(index, value)


def install(cpu: A64, ctl: Rp1Ctl) -> None:
    raw_load = cpu.raw_load
    raw_store = cpu.raw_store
    orig_step = A64.step.__get__(cpu, A64)

    def host_off(addr: int, size: int, what: str) -> int | None:
        if size != 4:
            ctl.bad(f"a {size}-byte {what} RP1 USB register - every register "
                    f"access must be 32 bits")
            return None
        if not ctl.link_up():
            ctl.bad("RP1 USB register accessed with the link down - on "
                    "silicon this hangs the core")
            return None
        ctl.rp1_touched = True
        return addr - HOST0

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if RC_BASE <= addr < RC_BASE + RC_SIZE:
            if size != 4:
                ctl.bad(f"a {size}-byte pcie2 register load")
                return 0
            return ctl.rc_read(addr - RC_BASE)
        if HOST0 <= addr < HOST0 + HOST_SIZE:
            off = host_off(addr, size, "load from an")
            if off is None:
                return 0
            if off in DWC3_REGS:
                return ctl.dwc_read(off)
            if off >= 0x8000:
                ctl.bad(f"load from unmodelled RP1 USB offset ${off:X}")
                return 0
            return ctl.reg_read(off)
        if RP1_CPU <= addr < RP1_CPU + RP1_SIZE:
            ctl.bad(f"load from RP1 ${addr - RP1_CPU:X}, not usbhost0 - "
                    f"the gate brings up host 0 only")
            return 0
        return raw_load(addr, size)

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if RC_BASE <= addr < RC_BASE + RC_SIZE:
            if size != 4:
                ctl.bad(f"a {size}-byte pcie2 register store")
                return
            ctl.rc_write(addr - RC_BASE, value & 0xFFFFFFFF)
            return
        if HOST0 <= addr < HOST0 + HOST_SIZE:
            off = host_off(addr, size, "store to an")
            if off is None:
                return
            if off in DWC3_REGS:
                ctl.dwc_write(off, value)
                return
            if X.DBOFF <= off < X.DBOFF + 0x400:
                if not ctl.host_mode():
                    ctl.bad("doorbell rung before the DWC3 core was in host mode")
                ctl.doorbell((off - X.DBOFF) // 4, value & 0xFFFFFFFF)
                return
            if off >= 0x8000:
                ctl.bad(f"store to unmodelled RP1 USB offset ${off:X}")
                return
            ctl.reg_write(off, value)
            return
        if RP1_CPU <= addr < RP1_CPU + RP1_SIZE:
            ctl.bad(f"store to RP1 ${addr - RP1_CPU:X}, not usbhost0")
            return
        raw_store(addr, value, size)

    counter = [0]

    def step() -> None:
        counter[0] += 1
        if counter[0] % 64 == 0:
            ctl.poll_ep0_race()
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:      # cntfrq_el0
            cpu.put(ins & 31, X.CNTFRQ, 1)
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:      # cntpct_el0
            ctl.ticks += X.TICK_STEP
            cpu.put(ins & 31, ctl.ticks, 1)
            cpu.pc += 4
            return
        orig_step()

    cpu.load = load
    cpu.store = store
    cpu.step = step


# ---------------------------------------------------------------------
# Expected results per scenario. A refusal scenario is an exact prefix:
# the program records its codes and stops.
# ---------------------------------------------------------------------
E_HALT, E_RUN, E_NO_CONNECT, E_STALL, E_DMA_OFFSET = 12, 17, 20, 29, 48
E_DMA_RANGE = 10
E_PORT_POWER = 21
E_RP1_HOST, E_DWC3_ID, E_DWC3_RESET, E_AC64 = 60, 61, 63, 65
PCIE_ERR_LINK, PCIE_ERR_INBOUND = -4, -16

HEAD_OK = [
    ("PcieInit verified the firmware's link", 1),
    ("no pcie error", 0),
    ("inbound window found: 64 GiB", 1 << 36),
    ("in RC_BAR1", 1),
    ("link speed from LNKSTA", 2),
    ("link width from LNKSTA", 4),
    ("PcieEnumerate found RP1", 1),
    ("no pcie error", 0),
    ("PcieDmaBus(CPU $12340) is $10_0001_2340", DMA_OFF + 0x12340),
    ("PcieDmaCpu inverts it", 0x12340),
]


def expect(scenario: str) -> list[tuple[str, int]]:
    # With no verified window the arena check refuses first (the Pi 4
    # order: reachability before locate), so RP1 is never read.
    if scenario == "link-down":
        return [("PcieInit refuses", 0), ("the link error", PCIE_ERR_LINK),
                ("XhciInit refuses", 0), ("arena not reachable", E_DMA_RANGE)]
    if scenario == "no-inbound":
        return [("PcieInit refuses", 0), ("the inbound-window error", PCIE_ERR_INBOUND),
                ("XhciInit refuses", 0), ("arena not reachable", E_DMA_RANGE)]
    fail = {"never-halts": E_HALT, "never-runs": E_RUN,
            "dwc3-reset-stuck": E_DWC3_RESET, "not-dwc3": E_DWC3_ID,
            "no-ac64": E_AC64, "port-power-stuck": E_PORT_POWER}
    if scenario in fail:
        return HEAD_OK + [("XhciInit refuses", 0), ("with the named error", fail[scenario])]
    ex = HEAD_OK + [
        ("XhciInit brought usbhost0 up", 1),
        ("no xhci error", 0),
        ("GSNPSID as read", GSNPSID_330B),
        ("AC64", 1),
        ("the capability base is usbhost0 at $1F_0020_0000", HOST0),
        ("the device id is RP1's", RP1_ID),
        ("three root ports", 3),
        ("host 0 selected", 0),
        ("host switch refused while running", 0),
        ("the board's VBUS hook ran once", 1),
        ("VBUS state 0: gpio_rp1.pi4 has no bank-2 setter for GPIO42/43", 0),
        ("both VBUS pins refused by gpio_rp1 (and RP1 untouched)", 2),
        ("XhciInit powered all three root ports", 3),
        ("a No-Op completed", 1),
        ("Success", 1),
        ("seventy more, wrapping both rings", 70),
        ("nothing skipped", 0),
        ("the first connected port is port 1 - powered by XhciInit", 1),
        ("port 3 SuperSpeed", X.SPEED_SS),
        ("port 1 already connected, before any reset", 1),
        ("port 1 resets", 1),
        ("port 1 enabled", 1),
        ("port 1 high speed", X.SPEED_HS),
        ("resetting empty port 2 fails", 0),
        ("and says nothing is connected", E_NO_CONNECT),
        ("Enable Slot gave slot 1", 1),
        ("Address Device succeeded", 1),
        ("device address 1", 1),
        ("slot state Addressed", 2),
        ("18 bytes of device descriptor", 18),
        ("Success", 1),
        ("idProduct low byte", 0xA5),
        ("idProduct high byte", 0x90),
        ("thirty control transfers through the wrapped EP0 ring", 30),
        ("an unknown descriptor stalls", -1),
        ("completion code Stall", 6),
        ("named a stall", E_STALL),
        ("and the endpoint works again after recovery", 8),
        ("the Pi 4 XhciInitAt refuses on BCM2712", 0),
        ("with the DMA-offset error", E_DMA_OFFSET),
    ]
    ex.append(("check count", len(ex)))
    return ex


def build(compiler: pathlib.Path, src: pathlib.Path, img: pathlib.Path, root: pathlib.Path) -> None:
    r = subprocess.run([str(compiler), "--compile", str(src), "-t", "pi5",
                        "--load-addr", hex(LOAD), "-s", "-o", str(img)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)),
                       text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    if r.returncode != 0 or not img.exists() or "pmfc: OK" not in r.stdout:
        raise SystemExit(f"The compiler did not build {src.name} -t pi5:\n{r.stdout}")
    if "target BCM2712" not in r.stdout:
        raise SystemExit("the image is not a BCM2712 build - #PMF_CHIP would "
                         "not be 2712 and the Pi 4 branches would run")


def run(img: pathlib.Path, scenario: str, budget: int) -> list[str]:
    sym = X.load_syms(img)
    blob = img.read_bytes()
    cpu = A64(pc=LOAD)
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    ctl = Rp1Ctl(cpu, scenario)
    install(cpu, ctl)
    trap = LOAD + sym["_a64_end_trap"]
    finished = False
    steps = 0
    for steps in range(budget):
        if cpu.pc == trap:
            finished = True
            break
        cpu.step()
    got = X.collect(cpu, sym)
    fails: list[str] = []
    if not finished:
        fails.append(f"did not reach the end trap in {budget} steps - HUNG")
    want = expect(scenario)
    if len(got) != len(want):
        fails.append(f"check count: program made {len(got)}, expected {len(want)}")
    for i, (label, w) in enumerate(want):
        if i >= len(got):
            fails.append(f"#{i} {label}: never ran")
        elif got[i] != w:
            fails.append(f"#{i} {label}: got {got[i]:#x}, want {w:#x}")

    def need(name: str, ok: bool) -> None:
        if not ok:
            fails.append(f"model: {name}")

    def before(a: str, b: str) -> bool:
        return a in ctl.log and b in ctl.log and ctl.log.index(a) < ctl.log.index(b)

    if scenario in ("link-down", "no-inbound"):
        need("RP1 was never touched after the refusal", not ctl.rp1_touched)
    elif scenario in ("dwc3-reset-stuck", "not-dwc3", "no-ac64"):
        need("a refused controller was never given bus mastering",
             "rp1-command" not in ctl.log)
    else:
        need("RP1 bus mastering was left untouched until after DWC3 setup",
             before("dwc3-host", "rp1-command"))
    if scenario == "healthy":
        need("PHY setup before the core soft reset", before("dwc3-phy", "dwc3-csftrst"))
        need("the soft reset completed", "dwc3-csftrst-cleared" in ctl.log)
        need("the soft reset before host mode", before("dwc3-csftrst-cleared", "dwc3-host"))
        need("host mode before the xHCI reset", before("dwc3-host", "hcrst"))
        need("the root ports were powered after the reset",
             before("hcrst", "port1-powered") and "port3-powered" in ctl.log)
        need("GUSB2PHYCFG0.SUSPHY cleared", not ctl.dwc[GUSB2PHYCFG0] & U2_SUSPHY)
        need("GUSB3PIPECTL0.SUSPHY cleared", not ctl.dwc[GUSB3PIPECTL0] & U3_SUSPHY)
        need("GUSB3PIPECTL0.DISRXDETINP3 set", bool(ctl.dwc[GUSB3PIPECTL0] & U3_DISRXDET))
        need("GUCTL1 quirk bits set", ctl.dwc[GUCTL1] & GUCTL1_WANT == GUCTL1_WANT)
        need("GCTL host", ctl.host_mode())
        need("RP1 bus master enabled", bool(ctl.cfg[0x04] & 4))
        need("RP1 memory decode kept", bool(ctl.cfg[0x04] & 2))
        need("reset exactly once", ctl.reset_count == 1)
        need("running", not ctl.reg[X.R_USBSTS] & X.STS_HALT)
        need("DCBAAP translated", DMA_OFF <= ctl.wide[X.R_DCBAAP] < DMA_OFF + DMA_WIN)
        need("the ERST names the event ring", ctl.erst_entry.get("seg") == ctl.ev_base)
        need("scratchpad pointers checked", "scratch-ok" in ctl.log)
        need("Address Device named root port 1", ctl.in_ctx_seen.get("port") == 1)
        need("stall recovered: Reset Endpoint then Set TR Dequeue",
             before("stall", "reset-ep") and before("reset-ep", "set-deq"))
        need("endpoint 0 not left halted", not ctl.ep0_halted)
    for v in ctl.violations:
        fails.append("model refused: " + v)
    return fails


# ---------------------------------------------------------------------
# Mutants of the 2712 branches (anchored, exactly once, into a copy).
# ---------------------------------------------------------------------
MUTANTS = {
    "wr64-untranslated": (XHCI, "  d = xh_Dma(v)\n  xh_Wr(base, off, d",
                          "  d = v\n  xh_Wr(base, off, d"),
    "erstba-lo-hi": (XHCI, "  xh_Wr64HiLo(xh_ir, #XHCI_ERSTBA, v)\nCompilerElse",
                     "  xh_Wr64(xh_ir, #XHCI_ERSTBA, v)\nCompilerElse"),
    "link-trb-untranslated": (XHCI, "  PokeN(lnk + 0, xh_Dma(base) & $FFFFFFFF)\n  PokeN(lnk + 4, (xh_Dma(base) >> 32)",
                              "  PokeN(lnk + 0, base & $FFFFFFFF)\n  PokeN(lnk + 4, (base >> 32)"),
    # The offset lives wholly in the HIGH dword (bit 36), so a mutant that
    # untranslates only a low half changes nothing - measured, and why
    # these two mutate both halves.
    "erst-entry-untranslated": (XHCI, "  PokeN(xh_erst + 0, xh_Dma(xh_evBase) & $FFFFFFFF)\n  PokeN(xh_erst + 4, (xh_Dma(xh_evBase) >> 32)",
                                "  PokeN(xh_erst + 0, xh_evBase & $FFFFFFFF)\n  PokeN(xh_erst + 4, (xh_evBase >> 32)"),
    "event-not-back-translated": (XHCI, "        xh_evTrb = xh_DmaCpu((xh_evF1 << 32) | (xh_evF0 & $FFFFFFFF))",
                                  "        xh_evTrb = (xh_evF1 << 32) | (xh_evF0 & $FFFFFFFF)"),
    "input-ctx-untranslated": (XHCI, "  If addr <> 0\n    addr = xh_Dma(addr)\n  EndIf\n",
                               "\n"),
    "ep0-deq-untranslated": (XHCI, "  deq = xh_Dma(xh_ringBase[slot]) | xh_ringCycle[slot]",
                             "  deq = xh_ringBase[slot] | xh_ringCycle[slot]"),
    "devctx-untranslated": (XHCI, "  PokeX(xh_dcbaa + (slot * 8), xh_Dma(xh_devCtx[slot]))",
                            "  PokeX(xh_dcbaa + (slot * 8), xh_devCtx[slot])"),
    "scratch-untranslated": (XHCI, "    PokeX(xh_dcbaa + 0, xh_Dma(xh_spArray))",
                             "    PokeX(xh_dcbaa + 0, xh_spArray)"),
    "bounce-untranslated": (XHCI, "    sf0 = xh_Dma(xh_bounce) & $FFFFFFFF\n    sf1 = (xh_Dma(xh_bounce) >> 32)",
                            "    sf0 = xh_bounce & $FFFFFFFF\n    sf1 = (xh_bounce >> 32)"),
    "set-deq-untranslated": (XHCI, "  deq = xh_Dma(xh_TrbAddr(ring, xh_ringEnq[ring])) | xh_ringCycle[ring]",
                             "  deq = xh_TrbAddr(ring, xh_ringEnq[ring]) | xh_ringCycle[ring]"),
    "no-host-mode": (XHCI, "    xh_Wr(xh_cap, #DWC3_GCTL, (v & (~#DWC3_GCTL_PRTCAP_MASK)) | #DWC3_GCTL_PRTCAP_HOST)\n",
                     "\n"),
    "no-soft-reset-wait": (XHCI, "    While (xh_Rd(xh_cap, #DWC3_DCTL) & #DWC3_DCTL_CSFTRST) <> 0\n"
                                 "      If xh_Expired(d) <> 0\n"
                                 "        ProcedureReturn xh_Fail(#XHCI_ERR_DWC3_RESET)\n"
                                 "      EndIf\n"
                                 "    Wend\n", "\n"),
    "no-rp1-bus-master": (PCIE, "    PcieCfgWrite32(1, 0, 0, #PCI_CFG_COMMAND, cmd | #PCI_CMD_BUS_MASTER)\n    ProcedureReturn Bool(",
                          "    ProcedureReturn Bool("),
    "dma-offset-zero": (PCIE, "  #PCIE_DMA_BUS  = $1000000000", "  #PCIE_DMA_BUS  = $0000000000"),
    "no-link-check": (PCIE, "    If PcieLinkUp() = 0\n      pcie_err = #PCIE_ERR_LINK\n",
                      "    If 0 = 1\n      pcie_err = #PCIE_ERR_LINK\n"),
    "no-inbound-check": (PCIE, "    If pcie_FindDmaWindow() = 0\n      pcie_err = #PCIE_ERR_INBOUND\n",
                         "    If pcie_FindDmaWindow() = 2\n      pcie_err = #PCIE_ERR_INBOUND\n"),
    "no-ac64-check": (XHCI, "    If xh_ac64 = 0\n      xh_Fail(#XHCI_ERR_AC64)", "    If xh_ac64 = 2\n      xh_Fail(#XHCI_ERR_AC64)"),
    "no-vbus-hook-call": (XHCI, "    If *xh_vbusHook <> 0\n      xh_vbusHook()\n    EndIf\n", "\n"),
    "no-root-port-power": (XHCI, "    If xh_PowerRootPorts() = 0\n", "    If 1 = 0\n"),
    "no-power-good-wait": (XHCI, "      xh_DelayMs(#XHCI_TMO_ROOTPWR_MS)\n", "\n"),
    "no-power-readback": (XHCI, "      If (xh_Rd(xh_op, xh_PortOff(p) + #XHCI_PORTSC) & #XHCI_PORT_POWER) = 0\n        ProcedureReturn xh_Fail(#XHCI_ERR_PORT_POWER)",
                          "      If 0 = 1\n        ProcedureReturn xh_Fail(#XHCI_ERR_PORT_POWER)"),
}
# Which scenario exposes each mutant (healthy unless named).
MUTANT_SCENARIO = {"no-link-check": "link-down", "no-inbound-check": "no-inbound",
                   "no-ac64-check": "no-ac64", "no-power-readback": "port-power-stuck"}
# The CRLF/LF of the libraries is kept; anchors are matched on LF text.


def make_mutant(name: str, work: pathlib.Path) -> pathlib.Path:
    """A private tree: the program plus mutated copies of both libraries."""
    lib, old, new = MUTANTS[name]
    for f in (PCIE, XHCI, GPIO):
        text = f.read_bytes().decode("utf-8").replace("\r\n", "\n")
        if f == lib:
            hits = text.count(old)
            if hits != 1:
                raise SystemExit(f"mutant {name!r}: anchor matched {hits} times "
                                 f"in {f.name}, not once - re-aim it")
            text = text.replace(old, new, 1)
        dst = work / "RaspberryPi4" / "Lib" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
    prog = work / "RaspberryPi4" / "Examples" / "Diagnostics" / SRC.name
    prog.parent.mkdir(parents=True, exist_ok=True)
    prog.write_bytes(SRC.read_bytes())
    intr = ROOT / "RaspberryPi4" / "Intrinsics"
    dst_i = work / "RaspberryPi4" / "Intrinsics"
    dst_i.mkdir(parents=True, exist_ok=True)
    for f in intr.iterdir():
        if f.is_file():
            (dst_i / f.name).write_bytes(f.read_bytes())
    return prog


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--scenario", choices=SCENARIOS)
    ap.add_argument("--break", dest="only", choices=sorted(MUTANTS))
    ap.add_argument("--no-breaks", action="store_true")
    a = ap.parse_args(argv[1:])
    if not a.compiler:
        ap.error("pass --compiler or set PMF_COMPILER")
    compiler = pathlib.Path(resolve_compiler(a.compiler))
    with tempfile.TemporaryDirectory(prefix="a64-xhci-pi5-") as tmp:
        work = pathlib.Path(tmp)
        img = work / "pi5usb.img"
        if a.only:
            mroot = work / "m"
            prog = make_mutant(a.only, mroot)
            build(compiler, prog, img, mroot)
            sc = MUTANT_SCENARIO.get(a.only, "healthy")
            fails = run(img, sc, 3_000_000)
            print(f"--break {a.only} ({sc}): {len(fails)} failure(s)")
            for f in fails[:8]:
                print("  " + f)
            return 0 if fails else 1
        build(compiler, SRC, img, ROOT)
        red = 0
        for sc in ([a.scenario] if a.scenario else SCENARIOS):
            fails = run(img, sc, 40_000_000)
            if fails:
                red += 1
                print(f"FAIL {sc}:")
                for f in fails:
                    print("   " + f)
            else:
                print(f"PASS {sc}: {len(expect(sc))} results as expected, model clean")
        if red:
            print(f"FAILED: {red} scenario(s)")
            return 1
        if a.no_breaks or a.scenario:
            return 0
        print("\nmutants - each must go RED:")
        weak = []
        for name in MUTANTS:
            mroot = work / ("m_" + name)
            prog = make_mutant(name, mroot)
            try:
                build(compiler, prog, img, mroot)
            except SystemExit:
                print(f"  {name:28s} refused at compile time")
                continue
            sc = MUTANT_SCENARIO.get(name, "healthy")
            fails = run(img, sc, 3_000_000)
            if fails:
                print(f"  {name:28s} red ({len(fails)})  e.g. {fails[0][:90]}")
            else:
                print(f"  {name:28s} *** STILL PASSED ***")
                weak.append(name)
        if weak:
            print(f"GATE IS WEAK: {', '.join(weak)}")
            return 1
        print(f"\nPASS: {len(SCENARIOS)} scenarios; {len(MUTANTS)} of "
              f"{len(MUTANTS)} mutants red.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
