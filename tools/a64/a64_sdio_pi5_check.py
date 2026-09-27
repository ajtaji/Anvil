#!/usr/bin/env python3
"""Desk gate for the BCM2712 (Raspberry Pi 5) branch of RaspberryPi4/Lib/sdio.pi4.

SILICON OWED. Nothing here has run on a Pi 5. This gate compiles
RaspberryPi5/Examples/Diagnostics/pi5SdioHost.pi5 with `-t pi5` - the
SAME sdio.pi4 the Pi 4 uses, taking its `CompilerIf #PMF_CHIP = 2712`
branches, with Anvil/Net/cyw43.pbi linked above it - and runs the image
on tools/a64/a64_interp.py against a modelled board:

  * the SDIO2 SDHCI host at its DTB address, a standard SDHCI register
    file (the Pi 4 gate's Sdhci model, reused), gated on the cfg block's
    force-presence bits and on a powered, correctly muxed card
  * the "cfg" block, SD_PIN_SEL / SDIO_CFG_CTRL / CQ_CAPABILITY
  * gio (brcmstb GPIO) bank 0, whose GPIO28 is WL_ON, with the pin's
    effective level logged against the modelled counter
  * pinctrl@7d504100 in both chip steppings (C0 and D0), seeded with a
    pattern so that every field the library is NOT meant to touch is
    checked to be unmoved
  * an SDIO card (the Pi 4 gate's Cyw43Card) that answers only when
    WL_ON has been high for the regulator's startup delay and its six
    pins carry "sd2" - and a MUTE variant that never answers

Any access outside those windows is refused as an unmodelled MMIO access.
In particular $1000FFF000 - the SD-card host - is refused.

WHAT IS ASSERTED
  WL_ON: GPIO28 muxed to "gpio" before it is driven; the effective level
  goes LOW (no high glitch on the way), stays low >= LOW_MIN_MS, rises
  exactly once, and is high for >= the DTB's startup-delay-us before the
  host is powered and before the first command; nothing else in gio or
  pinctrl moves.
  PINS: GPIO30..35 carry the stepping's "sd2" fsel, CLK no pull, CMD and
  DAT pull-up in the brcmstb encoding.
  HOST: cfg force presence set, CQ_CAPABILITY = (3 << 12) | 200,
  SD_PIN_SEL = SD at every clock change, 400 kHz then 25 MHz from the
  200 MHz DTB clock, CMD52(abort) CMD0 CMD5 CMD5.. CMD3 CMD7(rca) then
  the CCCR bus-width and function-1 enable CMD52s, in that order.
  REFUSALS: mute card -> SdioInit 0 at CMD5, #SDIO_ERR_NO_CARD, no CMD3/CMD7; no
  pinctrl stepping -> #SDIO_ERR_PINCTRL with NO register touched at all;
  no DTB clock -> #SDIO_ERR_BASECLK with no command issued.
  MUTANTS (unless --no-mutants): nine edits of sdio.pi4's 2712 branch,
  each rebuilt and rerun; every one must turn a check red.

WHERE THE NUMBERS COME FROM. The PINNED table below, each with its file
and line in the pinned sources (raspberrypi/linux
7e030b60792de1c15b9ec1d8d5d34d63f0f0f1d8 and the three pinned firmware
DTBs). Those files are third-party and not in this repository; when the
vault's "Raspberry Pi 5" folder is present (--sources), every pinned value
is RE-DERIVED from them and a disagreement is a failure. The SDHCI
register map and the SDIO command set are the Pi 4 gate's, which pins
them from sdhci.h / sdio.h / sdio_ops.c independently of sdio.pi4.

Run from PowerShell:
  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_sdio_pi5_check.py --compiler <PureMetalForge.exe>
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "tools" / "a64"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "RaspberryPi5" / "Boot"))
from a64_interp import A64, AlignmentFault, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402
import a64_sdio_check as pi4gate  # noqa: E402  (SDHCI map, card model)

FIXTURE = pathlib.PurePosixPath("RaspberryPi5/Examples/Diagnostics/pi5SdioHost.pi5")
LIBRARY = pathlib.PurePosixPath("RaspberryPi4/Lib/sdio.pi4")
# What the fixture needs from PMF_ROOT, for the mutant builds.
MUTANT_FILES = (FIXTURE, LIBRARY,
                pathlib.PurePosixPath("Anvil/Net/cyw43.pbi"),
                pathlib.PurePosixPath("Anvil/Net/cyw43_rx_glom.pbi"),
                pathlib.PurePosixPath("RaspberryPi4/Intrinsics/bcm2711_hardware.def"))

DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")

LOAD = 0x00400000
STACK = 0x03000000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
CTL = 0x00E00000          # the fixture's #CTL
OUT = 0x00E00100          # the fixture's #OUT
DONE = 0x600DF00D

# 54 MHz: the BCM2712 crystal, TF-A plat/rpi/rpi5/rpi5_bl31_setup.c
# lines 118-126, as cited by tools/a64/a64_el3_pi5_check.py.
CNTFRQ = 54_000_000
# A knob, not a measurement - see TICKS_PER_STEP in a64_sdio_check.py.
# Every wait in sdio.pi4 is a deadline measured on this counter, so the
# millisecond figures asserted below are in the same modelled time.
TICKS_PER_STEP = 256

# The WL_ON low hold the gate demands. NOT the library's
# #SDIO_WL_ON_LOW_MS: the project's proven radio driver states the
# requirement as ">= 10 ms guarantees the regulator has actually
# dropped" (RP2040/Lib/cyw43.pico line 1973).
LOW_MIN_MS = 10

LINUX = "raspberrypi/linux 7e030b60"
DTB = "pinned firmware DTBs (bead6868)"
PINNED = {
    # name: (value, where)
    "HOST_PHYS": (0x1001100000, DTB + " /axi/mmc@1100000 reg[0] via /axi ranges"),
    "HOST_SIZE": (0x260, LINUX + " bcm2712-ds.dtsi:390"),
    "CFG_PHYS": (0x1001100400, DTB + " /axi/mmc@1100000 reg[1] via /axi ranges"),
    "CFG_SIZE": (0x200, LINUX + " bcm2712-ds.dtsi:391"),
    "SDCARD_HOST_PHYS": (0x1000FFF000, DTB + " /soc/mmc@fff000 - must NOT be touched"),
    "BASE_HZ": (200_000_000, DTB + " /clocks/clk-emmc2 clock-frequency"),
    "PINCTRL_PHYS": (0x107D504100, DTB + " /soc/pinctrl@7d504100 via /soc ranges"),
    "PINCTRL_SIZE_C0": (0x30, DTB + " bcm2712-rpi-5-b.dtb pinctrl@7d504100 reg"),
    "PINCTRL_SIZE_D0": (0x20, DTB + " bcm2712d0-rpi-5-b.dtb pinctrl@7d504100 reg"),
    "GIO_PHYS": (0x107D508500, DTB + " /soc/gpio@7d508500 via /soc ranges"),
    "GIO_SIZE": (0x40, LINUX + " bcm2712-ds.dtsi:185"),
    "WL_ON_GPIO": (28, LINUX + " bcm2712-rpi-5-b.dts:71 <&gio 28 GPIO_ACTIVE_HIGH>"),
    "WL_ON_STARTUP_US": (150000, LINUX + " bcm2712-rpi-5-b.dts:73 startup-delay-us"),
    "GIO_REG_DATA": (1, LINUX + " gpio-brcmstb.c:17 (enum index)"),
    "GIO_REG_IODIR": (2, LINUX + " gpio-brcmstb.c:18 (enum index)"),
    "GIO_BANK_REGS": (8, LINUX + " gpio-brcmstb.c:16-24 NUMBER_OF_GIO_REGISTERS"),
    "CFG_CTRL": (0x0, LINUX + " sdhci-brcmstb.c:40"),
    "CFG_TEST_EN": (1 << 31, LINUX + " sdhci-brcmstb.c:41"),
    "CFG_TEST_LEV": (1 << 30, LINUX + " sdhci-brcmstb.c:42"),
    "CFG_PIN_SEL": (0x44, LINUX + " sdhci-brcmstb.c:44"),
    "CFG_PIN_SEL_MASK": (0x3, LINUX + " sdhci-brcmstb.c:45"),
    "CFG_PIN_SEL_SD": (1 << 1, LINUX + " sdhci-brcmstb.c:46"),
    "CFG_CQ_CAP": (0x4C, LINUX + " sdhci-brcmstb.c:37"),
    "CFG_CQ_FMUL_SHIFT": (12, LINUX + " sdhci-brcmstb.c:38"),
    "CFG_CQ_FMUL": (3, LINUX + " sdhci-brcmstb.c:294"),
    "PULL_NONE": (0, LINUX + " pinctrl-brcmstb.c:30"),
    "PULL_DOWN": (1, LINUX + " pinctrl-brcmstb.c:31"),
    "PULL_UP": (2, LINUX + " pinctrl-brcmstb.c:32"),
    # (muxreg, muxshift, padreg, padshift) per pin, pinctrl-brcmstb-bcm2712.c
    "C0_REGS": ({28: (3, 4, 9, 5), 30: (3, 6, 9, 7), 31: (3, 7, 9, 8), 32: (4, 0, 9, 9),
                 33: (4, 1, 9, 10), 34: (4, 2, 9, 11), 35: (4, 3, 9, 12)},
                LINUX + " pinctrl-brcmstb-bcm2712.c:154-161"),
    "D0_REGS": ({28: (2, 4, 5, 10), 30: (2, 6, 5, 12), 31: (2, 7, 5, 13), 32: (3, 0, 5, 14),
                 33: (3, 1, 6, 0), 34: (3, 2, 6, 1), 35: (3, 3, 6, 2)},
                LINUX + " pinctrl-brcmstb-bcm2712.c:317-324"),
    # fsel of "sd2" (1-based position in BRCMSTB_PIN), "gpio" is 0.
    "C0_SD2": ({30: 4, 31: 4, 32: 4, 33: 3, 34: 4, 35: 3},
               LINUX + " pinctrl-brcmstb-bcm2712.c:546-551"),
    "D0_SD2": ({30: 1, 31: 1, 32: 1, 33: 1, 34: 1, 35: 1},
               LINUX + " pinctrl-brcmstb-bcm2712.c:613-618"),
    # sdio2_30_pins: clk bias-disable, cmd + dat bias-pull-up.
    "SDIO_PULLS": ({30: "none", 31: "up", 32: "up", 33: "up", 34: "up", 35: "up"},
                   LINUX + " bcm2712-ds.dtsi:164-181"),
}


def fail(msg: str) -> None:
    raise SystemExit("a64_sdio_pi5_check: FAIL - " + msg)


# =====================================================================
#  RE-DERIVE THE PINNED TABLE FROM THE SOURCES, WHEN THEY ARE HERE
# =====================================================================
def derive_from_sources(src: pathlib.Path) -> dict:
    from dtb_contract import parse, mapped_reg, strings
    d: dict = {}
    s = src / "Sources"
    ext = s                     # the same pinned linux commit, same folder

    def text(p: pathlib.Path) -> str:
        if not p.is_file():
            fail(f"--sources names {src} but {p} is missing")
        return p.read_text(encoding="utf-8", errors="replace")

    brcm = text(s / "sdhci-brcmstb.c")

    def define(name: str, body: str) -> int:
        m = re.search(r"#define\s+" + name + r"\s+(\S+)", body)
        if not m:
            fail(f"{name} is not defined where the gate expects it")
        v = m.group(1)
        b = re.fullmatch(r"BIT\((\d+)\)", v)
        return (1 << int(b.group(1))) if b else int(v, 0)

    d["CFG_CTRL"] = define("SDIO_CFG_CTRL", brcm)
    d["CFG_TEST_EN"] = define("SDIO_CFG_CTRL_SDCD_N_TEST_EN", brcm)
    d["CFG_TEST_LEV"] = define("SDIO_CFG_CTRL_SDCD_N_TEST_LEV", brcm)
    d["CFG_PIN_SEL"] = define("SDIO_CFG_SD_PIN_SEL", brcm)
    d["CFG_PIN_SEL_MASK"] = define("SDIO_CFG_SD_PIN_SEL_MASK", brcm)
    d["CFG_PIN_SEL_SD"] = define("SDIO_CFG_SD_PIN_SEL_SD", brcm)
    d["CFG_CQ_CAP"] = define("SDIO_CFG_CQ_CAPABILITY", brcm)
    d["CFG_CQ_FMUL_SHIFT"] = define("SDIO_CFG_CQ_CAPABILITY_FMUL_SHIFT", brcm)
    m = re.search(r"reg = \((\d+) << SDIO_CFG_CQ_CAPABILITY_FMUL_SHIFT\)", brcm)
    d["CFG_CQ_FMUL"] = int(m.group(1)) if m else -1

    pc = text(ext / "pinctrl-brcmstb.c")
    d["PULL_NONE"] = define("BRCMSTB_PULL_NONE", pc)
    d["PULL_DOWN"] = define("BRCMSTB_PULL_DOWN", pc)
    d["PULL_UP"] = define("BRCMSTB_PULL_UP", pc)

    b12 = text(ext / "pinctrl-brcmstb-bcm2712.c")

    def regs(array: str) -> dict:
        m = re.search(array + r"\[\] = \{(.*?)\n\};", b12, re.S)
        if not m:
            fail(f"{array} not found in pinctrl-brcmstb-bcm2712.c")
        out = {}
        for n, a, b, c, e in re.findall(
                r"GPIO_REGS\((\d+), (\d+), (\d+), (\d+), (\d+)\)", m.group(1)):
            if int(n) in (28, 30, 31, 32, 33, 34, 35):
                out[int(n)] = (int(a), int(b), int(c), int(e))
        return out

    def sd2(array: str) -> dict:
        m = re.search(array + r"\[\] = \{(.*?)\n\};", b12, re.S)
        if not m:
            fail(f"{array} not found in pinctrl-brcmstb-bcm2712.c")
        out = {}
        for n, funcs in re.findall(r"BRCMSTB_PIN\((\d+), ([^)]*)\)", m.group(1)):
            if int(n) in (30, 31, 32, 33, 34, 35):
                names = [f.strip() for f in funcs.split(",")]
                out[int(n)] = names.index("sd2") + 1
        return out

    d["C0_REGS"] = regs("bcm2712_c0_gpio_pin_regs")
    d["D0_REGS"] = regs("bcm2712_d0_gpio_pin_regs")
    d["C0_SD2"] = sd2("bcm2712_c0_gpio_pin_funcs")
    d["D0_SD2"] = sd2("bcm2712_d0_gpio_pin_funcs")

    gb = text(ext / "gpio-brcmstb.c")
    m = re.search(r"enum gio_reg_index \{(.*?)\};", gb, re.S)
    names = re.findall(r"GIO_REG_(\w+)", m.group(1)) if m else []
    d["GIO_REG_DATA"] = names.index("DATA") if "DATA" in names else -1
    d["GIO_REG_IODIR"] = names.index("IODIR") if "IODIR" in names else -1
    d["GIO_BANK_REGS"] = names.index("NUMBER_OF_GIO_REGISTERS") if "NUMBER_OF_GIO_REGISTERS" in names else -1
    if "NUMBER_OF_GIO_REGISTERS" not in names:
        m2 = re.search(r"GIO_REG_STAT,\s*NUMBER_OF_GIO_REGISTERS", gb)
        d["GIO_BANK_REGS"] = names.index("STAT") + 1 if m2 else -1

    ds = text(s / "bcm2712-ds.dtsi")
    m = re.search(r"sdio2: mmc@1100000 \{.*?reg = <0x10 0x01100000\s+0x0 (0x[0-9a-f]+)>,\s*"
                  r"<0x10 0x01100400\s+0x0 (0x[0-9a-f]+)>", ds, re.S)
    d["HOST_SIZE"], d["CFG_SIZE"] = (int(m.group(1), 16), int(m.group(2), 16)) if m else (-1, -1)
    m = re.search(r"gio: gpio@7d508500 \{.*?reg = <0x7d508500 (0x[0-9a-f]+)>", ds, re.S)
    d["GIO_SIZE"] = int(m.group(1), 16) if m else -1
    m = re.search(r"sdio2_30_pins: sdio2_30_pins \{(.*?)\n\t\t\};", ds, re.S)
    pulls = {}
    if m:
        for body in re.findall(r"\{(.*?)\}", m.group(1), re.S):
            fn = re.search(r'function = "(\w+)"', body).group(1)
            if fn != "sd2":
                fail("sdio2_30_pins has a group whose function is not sd2")
            pins = [int(p) for p in re.findall(r'"gpio(\d+)"', body)]
            bias = "none" if "bias-disable" in body else "up" if "bias-pull-up" in body else "?"
            for p in pins:
                pulls[p] = bias
    d["SDIO_PULLS"] = pulls

    dts = text(s / "bcm2712-rpi-5-b.dts")
    m = re.search(r"wl_on_reg: wl-on-reg \{(.*?)\n\t?\};", dts, re.S)
    if m:
        g = re.search(r"gpio = <&gio (\d+) GPIO_ACTIVE_HIGH>", m.group(1))
        u = re.search(r"startup-delay-us = <(\d+)>", m.group(1))
        d["WL_ON_GPIO"] = int(g.group(1)) if g else -1
        d["WL_ON_STARTUP_US"] = int(u.group(1)) if u else -1

    # The DTBs: all three must agree, and the D0 one supplies its pinctrl size.
    for name in ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb"):
        n = parse((src / "Boot staging" / name).read_bytes())
        host = "/axi/mmc@1100000"
        reg = n[host]["reg"]
        hbus, cbus = int.from_bytes(reg[0:8], "big"), int.from_bytes(reg[16:24], "big")
        hphys = mapped_reg(n, host)
        clk = int.from_bytes(n[host]["clocks"][:4], "big")
        freq = [int.from_bytes(p["clock-frequency"], "big") for p in n.values()
                if p.get("phandle") and int.from_bytes(p["phandle"], "big") == clk]
        pin = "/soc@107c000000/pinctrl@7d504100"
        gio = "/soc@107c000000/gpio@7d508500"
        found = {"HOST_PHYS": hphys, "CFG_PHYS": hphys + (cbus - hbus),
                 "BASE_HZ": freq[0] if freq else -1,
                 "PINCTRL_PHYS": mapped_reg(n, pin), "GIO_PHYS": mapped_reg(n, gio),
                 "SDCARD_HOST_PHYS": mapped_reg(n, "/soc@107c000000/mmc@fff000")}
        size = int.from_bytes(n[pin]["reg"][4:8], "big")
        compat = strings(n[pin]["compatible"])
        if "brcm,bcm2712c0-pinctrl" in compat:
            found["PINCTRL_SIZE_C0"] = size
        if "brcm,bcm2712d0-pinctrl" in compat:
            found["PINCTRL_SIZE_D0"] = size
        for key, v in found.items():
            if key in d and d[key] != v:
                fail(f"the pinned DTBs disagree about {key}: {d[key]:#x} vs {v:#x} in {name}")
            d[key] = v
    return d


def constants(sources: pathlib.Path | None) -> dict:
    k = {name: value for name, (value, _w) in PINNED.items()}
    if sources is None:
        print("  SOURCES NOT CROSS-CHECKED - --sources absent; running on the PINNED table only")
        return k
    got = derive_from_sources(sources)
    for name, (value, where) in PINNED.items():
        if name not in got:
            fail(f"{name} could not be re-derived from {sources} ({where})")
        if got[name] != value:
            fail(f"PINNED {name} = {value!r} but the sources say {got[name]!r} ({where})")
    print(f"  sources: {len(PINNED)} pinned values re-derived from {sources} - all agree")
    return k


def library_codes(lib_text: str) -> dict:
    return {m.group(1): int(m.group(2))
            for m in re.finditer(r"^#(SDIO_ERR_\w+)\s*=\s*(\d+)", lib_text, re.M)}


# =====================================================================
#  THE MODEL
# =====================================================================
class Board:
    def __init__(self, k: dict, stepping: str, warm: bool, mute: bool) -> None:
        self.k = k
        self.stepping = stepping          # "C0" or "D0"
        self.mute = mute
        self.steps = 0
        self.events: list[tuple[int, str, object]] = []
        self.cfg: dict[int, int] = {}
        self.pinsel_at_clock: list[int] = []
        self.divisors: list[int] = []
        self.first_power_tick = None
        self.touched: list[str] = []      # every peripheral window touched
        # pinctrl, seeded so that no target value is already present.
        # $55555555 is wrong under both readings: every 4-bit mux field
        # is 5 (no pin here wants 5) and every 2-bit pad field is 01,
        # pull-DOWN (no pin here wants that).
        size = k["PINCTRL_SIZE_" + stepping]
        self.pinctrl = {off: 0x55555555 for off in range(0, size, 4)}
        self.pinctrl_seed = dict(self.pinctrl)
        # gio bank 0: WL_ON found an output driving high (warm) or an input
        # with a stale high latched in DATA (cold) - the second is the
        # case where direction-before-value would glitch the radio on.
        bit = 1 << k["WL_ON_GPIO"]
        self.bit = bit
        self.gio = {off: 0 for off in range(0, k["GIO_SIZE"], 4)}
        self.gio[4 * k["GIO_REG_DATA"]] = 0xA5A5A5A5 | bit
        self.gio[4 * k["GIO_REG_IODIR"]] = (0x5A5A5A5A & ~bit) if warm else (0x5A5A5A5A | bit)
        self.gio_seed = dict(self.gio)
        self.levels: list[tuple[int, int]] = [(0, self.wl_level())]
        self.mux_at_first_drive = None
        self.first_drive_tick = None

    def tick(self) -> int:
        return self.steps * TICKS_PER_STEP

    def ms(self, ticks: int) -> float:
        return ticks * 1000.0 / CNTFRQ

    # -- the pins ---------------------------------------------------------
    def regs(self) -> dict:
        return self.k[self.stepping + "_REGS"]

    def mux(self, pin: int) -> int:
        mr, ms, _pr, _ps = self.regs()[pin]
        return (self.pinctrl[mr * 4] >> (ms * 4)) & 0xF

    def pad(self, pin: int) -> int:
        _mr, _ms, pr, ps = self.regs()[pin]
        return (self.pinctrl[pr * 4] >> (ps * 2)) & 0x3

    def sdio_pins_ok(self) -> bool:
        want = self.k[self.stepping + "_SD2"]
        pull = {"none": self.k["PULL_NONE"], "up": self.k["PULL_UP"]}
        return all(self.mux(p) == want[p] and self.pad(p) == pull[self.k["SDIO_PULLS"][p]]
                   for p in want)

    # -- WL_ON ------------------------------------------------------------
    def wl_level(self) -> int:
        out = (self.gio[4 * self.k["GIO_REG_IODIR"]] & self.bit) == 0
        return 1 if out and (self.gio[4 * self.k["GIO_REG_DATA"]] & self.bit) else 0

    def gio_write(self, off: int, v: int) -> None:
        before = self.wl_level()
        if off in (4 * self.k["GIO_REG_DATA"], 4 * self.k["GIO_REG_IODIR"]) \
                and ((self.gio[off] ^ v) & self.bit) and self.mux_at_first_drive is None:
            self.mux_at_first_drive = self.mux(self.k["WL_ON_GPIO"])
            self.first_drive_tick = self.tick()
        self.gio[off] = v
        after = self.wl_level()
        if after != before:
            self.levels.append((self.tick(), after))

    def high_since(self) -> int | None:
        """Tick at which WL_ON last rose, if it is high now."""
        if self.levels[-1][1] != 1:
            return None
        return self.levels[-1][0]

    def card_can_answer(self) -> bool:
        if self.mute:
            return False
        since = self.high_since()
        if since is None or self.first_drive_tick is None:
            return False              # never driven by the library
        need = self.k["WL_ON_STARTUP_US"] * CNTFRQ // 1_000_000
        if self.tick() - since < need:
            return False
        if not self.sdio_pins_ok():
            return False
        ctrl = self.cfg.get(self.k["CFG_CTRL"], 0)
        return bool(ctrl & self.k["CFG_TEST_EN"]) and not (ctrl & self.k["CFG_TEST_LEV"])


class Sdhci2712(pi4gate.Sdhci):
    """The Pi 4 gate's SDHCI register file, gated on presence and power."""

    def __init__(self, k: dict, card, base: int, board: Board) -> None:
        super().__init__(k, card, base)
        self.board = board
        self.silent: list[int] = []

    def read(self, off: int) -> int:
        v = super().read(off)
        if off == self.k["SDHCI_PRESENT_STATE"]:
            ctrl = self.board.cfg.get(self.board.k["CFG_CTRL"], 0)
            present = (ctrl & self.board.k["CFG_TEST_EN"]) and not (ctrl & self.board.k["CFG_TEST_LEV"])
            if not present:
                v &= ~0x00030000     # no card inserted, not stable
        return v

    def write(self, off: int, val: int) -> None:
        k = self.k
        if off == (k["SDHCI_POWER_CONTROL"] & ~3) and ((val >> 8) & k["SDHCI_POWER_ON"]) \
                and self.board.first_power_tick is None:
            self.board.first_power_tick = self.board.tick()
            self.board.events.append((self.board.tick(), "power", val))
        if off == (k["SDHCI_CLOCK_CONTROL"] & ~3) and (val & k["SDHCI_CLOCK_INT_EN"]) \
                and not (val >> 24):
            n = ((val >> k["SDHCI_DIVIDER_SHIFT"]) & k["SDHCI_DIV_MASK"]) | \
                (((val >> k["SDHCI_DIVIDER_HI_SHIFT"]) & (k["SDHCI_DIV_HI_MASK"] >> 8)) << 8)
            if not self.divisors_last_equal(n):
                self.board.divisors.append(n)
                self.board.pinsel_at_clock.append(self.board.cfg.get(self.board.k["CFG_PIN_SEL"], 0))
        super().write(off, val)

    def divisors_last_equal(self, n: int) -> bool:
        return bool(self.board.divisors) and self.board.divisors[-1] == n

    def _command(self, word: int) -> None:
        k = self.k
        cmdreg = (word >> 16) & 0xFFFF
        index = (cmdreg >> k["CMD_INDEX_SHIFT_IN_HALFWORD"]) & 0x3F
        self.board.events.append((self.board.tick(), "cmd", index))
        if not self.powered:
            raise SystemExit(f"CMD{index} was issued before the bus was powered")
        no_resp = (cmdreg & k["SDHCI_CMD_RESP_MASK"]) == k["SDHCI_CMD_RESP_NONE"]
        if not no_resp and not self.board.card_can_answer():
            # A command with no response (CMD0) completes on the host
            # whether or not anything is listening; the rest time out.
            # What silicon reports for no response: Command Timeout AND the
            # Error Interrupt summary bit 15 (the Pi 4 bench's $00048000
            # shows bit 15 accompanying every error bit).
            self.commands.append((index, cmdreg & 0xFF, self.reg.get(k["SDHCI_ARGUMENT"], 0)))
            self.silent.append(index)
            self.intstat |= k["SDHCI_INT_TIMEOUT"] | k["SDHCI_INT_ERROR"]
            return
        super()._command(word)


def build(compiler: str, root: pathlib.Path, out: pathlib.Path) -> None:
    r = subprocess.run(
        [compiler, "--compile", str(FIXTURE), "-t", "pi5",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
         "--entry-returns", "-o", str(out)],
        cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.is_file():
        raise SystemExit("BUILD FAILED:\n" + r.stdout[-3000:])
    if "BCM2712" not in r.stdout:
        fail("the fixture was not built for BCM2712")


def run(img: pathlib.Path, k: dict, ctl: int, stepping: str, warm: bool, mute: bool,
        limit: int = 30_000_000):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    for i in range(4):
        cpu.memory[CTL + i] = (ctl >> (8 * i)) & 0xFF
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    board = Board(k, stepping, warm, mute)
    card = pi4gate.Cyw43Card(pi4gate.read_constants())
    hc = Sdhci2712(pi4gate.read_constants(), card, k["HOST_PHYS"], board)
    windows = [
        ("host", k["HOST_PHYS"], k["HOST_SIZE"]),
        ("cfg", k["CFG_PHYS"], k["CFG_SIZE"]),
        ("pinctrl", k["PINCTRL_PHYS"], k["PINCTRL_SIZE_" + stepping]),
        ("gio", k["GIO_PHYS"], k["GIO_SIZE"]),
    ]

    def window(addr: int):
        for name, base, size in windows:
            if base <= addr < base + size:
                return name, addr - base
        return None, 0

    def mmio(addr: int) -> bool:
        return addr >= 0x40000000

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if mmio(addr):
            name, off = window(addr)
            if name is None:
                raise SystemExit(f"unmodelled MMIO read at ${addr:X}")
            if size != 4:
                raise SystemExit(f"{size}-byte MMIO read at ${addr:X} - 32-bit only")
            board.touched.append(name)
            if name == "host":
                return hc.read(off)
            if name == "cfg":
                return board.cfg.get(off, 0)
            if name == "pinctrl":
                return board.pinctrl[off]
            return board.gio[off]
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        v = value & 0xFFFFFFFF
        if mmio(addr):
            name, off = window(addr)
            if name is None:
                raise SystemExit(f"unmodelled MMIO write at ${addr:X} - a store to a "
                                 f"peripheral that is not the intended one")
            if size != 4:
                raise SystemExit(f"{size}-byte MMIO write at ${addr:X} - 32-bit only")
            board.touched.append(name)
            if name == "host":
                hc.write(off, v)
            elif name == "cfg":
                board.cfg[off] = v
                board.events.append((board.tick(), "cfg", (off, v)))
            elif name == "pinctrl":
                board.pinctrl[off] = v
            else:
                board.gio_write(off, v)
            return
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain = A64.step.__get__(cpu)

    def step() -> None:
        board.steps += 1
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = board.tick()
            cpu.pc += 4
            return
        plain()

    n = 0
    try:
        while cpu.pc != LOADER_LR:
            n += 1
            if n > limit:
                raise SystemExit("the fixture never returned")
            step()
    except AlignmentFault as fault:
        raise SystemExit(fault.message())
    outw = [sum(cpu.memory.get(OUT + 4 * j + i, 0) << (8 * i) for i in range(4)) for j in range(11)]
    return board, hc, card, outw


# =====================================================================
#  THE ASSERTIONS
# =====================================================================
class Checks:
    def __init__(self, verbose: bool) -> None:
        self.bad: list[str] = []
        self.n = 0
        self.verbose = verbose

    def __call__(self, cond: bool, msg: str) -> None:
        self.n += 1
        if not cond:
            self.bad.append(msg)
        elif self.verbose:
            print("    ok  " + msg)


def check_wl_on(ck: Checks, tag: str, b: Board, k: dict) -> None:
    lv = b.levels
    ck(b.mux_at_first_drive == 0, f"{tag}: GPIO28 was muxed to gpio (fsel 0) before WL_ON was driven "
                                  f"(found {b.mux_at_first_drive})")
    # The level history after the found state must be exactly: low, high.
    # Found high: exactly one fall then one rise. Found low (or an
    # input): exactly one rise, and the hold runs from the first drive.
    tail = [lvl for _t, lvl in lv[1:]]
    want = [1] if lv[0][1] == 0 else [0, 1]
    ck(tail == want, f"{tag}: WL_ON effective level went {[lv[0][1]] + tail}, want "
                     f"{[lv[0][1]] + want} - one low phase, one rise, no glitch")
    rise = lv[-1][0] if lv and lv[-1][1] == 1 else None
    if lv[0][1] == 1 and len(lv) >= 3:
        low_ticks = lv[2][0] - lv[1][0]
    elif rise is not None and b.first_drive_tick is not None:
        low_ticks = rise - b.first_drive_tick
    else:
        low_ticks = 0
    ck(b.ms(low_ticks) >= LOW_MIN_MS, f"{tag}: WL_ON held low {b.ms(low_ticks):.1f} ms (>= {LOW_MIN_MS})")
    need = k["WL_ON_STARTUP_US"] / 1000.0
    if rise is not None and b.first_power_tick is not None:
        ck(b.ms(b.first_power_tick - rise) >= need,
           f"{tag}: host powered {b.ms(b.first_power_tick - rise):.1f} ms after WL_ON rose (>= {need:.0f})")
    else:
        ck(False, f"{tag}: WL_ON never rose or the host was never powered")
    first_cmd = next((t for t, kind, _ in b.events if kind == "cmd"), None)
    if rise is not None and first_cmd is not None:
        ck(first_cmd >= rise and b.ms(first_cmd - rise) >= need,
           f"{tag}: first command {b.ms(first_cmd - rise):.1f} ms after WL_ON rose (>= {need:.0f})")
    ck(lv[-1][1] == 1, f"{tag}: WL_ON is high at the end")
    changed = {off: (b.gio_seed[off], v) for off, v in b.gio.items()
               if (b.gio_seed[off] ^ v) & ~b.bit}
    ck(not changed, f"{tag}: no gio bit other than GPIO28 moved {changed}")


def check_pins(ck: Checks, tag: str, b: Board, k: dict) -> None:
    ck(b.sdio_pins_ok(), f"{tag}: GPIO30..35 carry sd2 with the DTB's pulls ({b.stepping})")
    allowed: dict[int, int] = {}
    for pin, (mr, ms, pr, ps) in b.regs().items():
        allowed[mr * 4] = allowed.get(mr * 4, 0) | (0xF << (ms * 4))
        if pin != k["WL_ON_GPIO"]:
            allowed[pr * 4] = allowed.get(pr * 4, 0) | (0x3 << (ps * 2))
    moved = {off: (b.pinctrl_seed[off], v) for off, v in b.pinctrl.items()
             if (b.pinctrl_seed[off] ^ v) & ~allowed.get(off, 0)}
    ck(not moved, f"{tag}: no pinctrl field outside the seven pins moved (and GPIO28's pad kept) {moved}")


def scenario_success(ck: Checks, img, k, codes, stepping: str, warm: bool) -> None:
    tag = f"{stepping} {'warm' if warm else 'cold'}"
    ctl = (1 if stepping == "C0" else 2) | 4
    b, hc, card, out = run(img, k, ctl, stepping, warm, mute=False)
    ck(out[10] == DONE, f"{tag}: the fixture ran to its end")
    ck(out[0] == 1, f"{tag}: SdioInit returned 1 (got {out[0]}, err {out[1]}, wl_on step {out[2]})")
    ck(out[16 // 4] == 1, f"{tag}: SdioEnableFunction(1) returned 1")
    ck(out[20 // 4] == 4, f"{tag}: the bus is four bits wide (got {out[5]})")
    ck(out[24 // 4] == pi4gate.MODEL_RCA, f"{tag}: RCA is the card's")
    check_wl_on(ck, tag, b, k)
    check_pins(ck, tag, b, k)
    ctrl = b.cfg.get(k["CFG_CTRL"], 0)
    ck(bool(ctrl & k["CFG_TEST_EN"]) and not (ctrl & k["CFG_TEST_LEV"]),
       f"{tag}: cfg force presence (TEST_EN set, TEST_LEV clear) = ${ctrl:08X}")
    want_cq = (k["CFG_CQ_FMUL"] << k["CFG_CQ_FMUL_SHIFT"]) | (k["BASE_HZ"] // 1_000_000)
    ck(b.cfg.get(k["CFG_CQ_CAP"]) == want_cq, f"{tag}: CQ_CAPABILITY = ${want_cq:X}")
    ck(bool(b.pinsel_at_clock) and all((p & k["CFG_PIN_SEL_MASK"]) == k["CFG_PIN_SEL_SD"]
                                        for p in b.pinsel_at_clock),
       f"{tag}: SD_PIN_SEL = SD at every divisor change {b.pinsel_at_clock}")
    base = k["BASE_HZ"]
    rates = [base // (2 * n) if n else base for n in b.divisors]
    ck(len(rates) >= 2 and rates[0] <= 400_000 and rates[-1] <= 25_000_000 and rates[-1] >= 20_000_000,
       f"{tag}: SD clock {rates} Hz from the {base // 1_000_000} MHz DTB base (<= 400 kHz, then 25 MHz)")
    idx = [c[0] for c in hc.commands]
    try:
        order = [idx.index(0), idx.index(5), idx.index(3), idx.index(7)]
    except ValueError:
        order = []
    ck(order == sorted(order) and len(order) == 4 and idx[0] == 52,
       f"{tag}: CMD52(abort) CMD0 CMD5 CMD3 CMD7 in order {idx[:12]}")
    sel = [c for c in hc.commands if c[0] == 7]
    ck(bool(sel) and (sel[0][2] >> 16) == pi4gate.MODEL_RCA, f"{tag}: CMD7 carries the RCA")
    after7 = idx[idx.index(7) + 1:] if 7 in idx else []
    ck(bool(after7) and all(i == 52 for i in after7),
       f"{tag}: only CMD52 after CMD7 (bus width, function enable) {after7}")
    ck((card.cccr_if & 0x3) == 0x2 and bool(card.ioe & 0x2), f"{tag}: the card is four-bit and function 1 is enabled")
    ck("host" in b.touched and not hc.silent, f"{tag}: no command went unanswered {hc.silent}")


def scenario_refusals(ck: Checks, img, k, codes) -> None:
    # The mute card: powered and muxed, never answers.
    b, hc, _card, out = run(img, k, 1 | 4, "C0", warm=True, mute=True)
    idx = [c[0] for c in hc.commands]
    ck(out[10] == DONE and out[0] == 0, "mute card: SdioInit refuses (returns 0)")
    ck(5 in idx and 3 not in idx and 7 not in idx, f"mute card: stopped at CMD5, no CMD3/CMD7 {idx}")
    ck(out[3] == 5, f"mute card: SdioLastCmd is 5 (got {out[3]})")
    # The model reports no response as silicon does - Command Timeout
    # AND Error Interrupt bit 15 - so this checks that the refusal is
    # NAMED "no card" (sdio_Command masks bit 15 out of its timeout
    # compare since 2026-09-26; before that it said CMD_ERROR).
    ck(out[1] == codes["SDIO_ERR_NO_CARD"],
       f"mute card: error {out[1]} is #SDIO_ERR_NO_CARD ({codes['SDIO_ERR_NO_CARD']})")
    check_wl_on(ck, "mute card", b, k)

    # No pinctrl stepping: refuse before ANY register is written.
    b, hc, _card, out = run(img, k, 4, "C0", warm=True, mute=False)
    ck(out[0] == 0 and out[1] == codes["SDIO_ERR_PINCTRL"],
       f"no stepping: #SDIO_ERR_PINCTRL (got {out[1]})")
    ck(b.pinctrl == b.pinctrl_seed and b.gio == b.gio_seed and not b.cfg and not hc.commands
       and hc.reg == {}, "no stepping: nothing was written anywhere")

    # No DTB clock: refuse before any command.
    b, hc, _card, out = run(img, k, 1, "C0", warm=True, mute=False)
    ck(out[0] == 0 and out[1] == codes["SDIO_ERR_BASECLK"], f"no clock: #SDIO_ERR_BASECLK (got {out[1]})")
    ck(not hc.commands and b.first_power_tick is None, "no clock: no command, bus never powered")


def gate(img: pathlib.Path, k: dict, codes: dict, verbose: bool, quick: bool = False) -> Checks:
    ck = Checks(verbose)
    scenario_success(ck, img, k, codes, "C0", warm=True)
    scenario_success(ck, img, k, codes, "D0", warm=False)
    scenario_refusals(ck, img, k, codes)
    return ck


# =====================================================================
#  MUTANTS - edits of the 2712 branch; each must go red
# =====================================================================
def _in_2712_wlon(text: str, old: str, new: str) -> str:
    start = text.index("; ---- BCM2712: WL_ON is gio GPIO28")
    end = text.index("CompilerElse", start)
    seg = text[start:end]
    if old not in seg:
        raise SystemExit(f"mutant anchor not found: {old!r}")
    return text[:start] + seg.replace(old, new, 1) + text[end:]


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"mutant anchor not unique: {old!r} ({text.count(old)})")
    return text.replace(old, new)


MUTANTS = [
    ("no WL_ON low hold",
     lambda t: _in_2712_wlon(t, "  sdio_DelayMs(#SDIO_WL_ON_LOW_MS)\n", "")),
    ("no 150 ms after WL_ON rises",
     lambda t: _in_2712_wlon(t, "  sdio_DelayMs(#SDIO_WL_ON_HIGH_MS)\n", "")),
    ("WL_ON direction before value (glitch)",
     lambda t: _in_2712_wlon(
         t,
         "  d = PeekN(#SDIO_GIO_BASE + #SDIO_GIO_DATA) & (~#SDIO_WL_ON_BIT)\n"
         "  PokeL(#SDIO_GIO_BASE + #SDIO_GIO_DATA, d)\n"
         "  d = PeekN(#SDIO_GIO_BASE + #SDIO_GIO_IODIR) & (~#SDIO_WL_ON_BIT)\n"
         "  PokeL(#SDIO_GIO_BASE + #SDIO_GIO_IODIR, d)\n",
         "  d = PeekN(#SDIO_GIO_BASE + #SDIO_GIO_IODIR) & (~#SDIO_WL_ON_BIT)\n"
         "  PokeL(#SDIO_GIO_BASE + #SDIO_GIO_IODIR, d)\n"
         "  d = PeekN(#SDIO_GIO_BASE + #SDIO_GIO_DATA) & (~#SDIO_WL_ON_BIT)\n"
         "  PokeL(#SDIO_GIO_BASE + #SDIO_GIO_DATA, d)\n")),
    ("host at the SD-card controller",
     lambda t: _once(t, "#SDIO_BASE     = $1001100000", "#SDIO_BASE     = $1000FFF000")),
    ("no cfg force presence",
     lambda t: _once(t, "v | #SDIO_CFG_CTRL_SDCD_TEST_EN)", "v)")),
    ("C0 GPIO30 fsel 3, not sd2",
     lambda t: _once(t, "sdio_PinField($0C, 24, #SDIO_BRCM_FIELD_MUX, 4)",
                     "sdio_PinField($0C, 24, #SDIO_BRCM_FIELD_MUX, 3)")),
    ("BCM2711 pull encoding (1 = pull-down here)",
     lambda t: _once(t, "#SDIO_BRCM_PULL_UP   = 2", "#SDIO_BRCM_PULL_UP   = 1")),
    ("timeout compare includes Error Interrupt bit 15 (the pre-fix label)",
     lambda t: _once(t, "If (intr & #SDIO_INT_ERROR_MASK & (~#SDIO_INT_ERROR)) = #SDIO_INT_TIMEOUT",
                     "If (intr & #SDIO_INT_ERROR_MASK) = #SDIO_INT_TIMEOUT")),
    ("SD_PIN_SEL never written",
     lambda t: _once(t, "  PokeL(#SDIO_CFG_BASE + #SDIO_CFG_SD_PIN_SEL, c1 | #SDIO_CFG_SD_PIN_SEL_SD)\n", "")),
]


def mutants(compiler: str, k: dict, codes: dict, work: pathlib.Path) -> list[str]:
    src_lib = (ROOT / LIBRARY).read_bytes().decode("latin-1")
    crlf = "\r\n" in src_lib
    lib = src_lib.replace("\r\n", "\n")
    survivors = []
    for name, edit in MUTANTS:
        root = work / "mutant"
        if root.exists():
            shutil.rmtree(root)
        for rel in MUTANT_FILES:
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dst)
        text = edit(lib)
        if crlf:
            text = text.replace("\n", "\r\n")
        (root / LIBRARY).write_bytes(text.encode("latin-1"))
        img = work / "mutant.img"
        try:
            build(compiler, root, img)
            ck = gate(img, k, codes, verbose=False, quick=True)
            red = bool(ck.bad)
            why = ck.bad[0] if ck.bad else "every check passed"
        except SystemExit as e:
            red, why = True, str(e).splitlines()[0][:160]
        print(f"  mutant {'RED  ' if red else 'ALIVE'} {name}: {why}")
        if not red:
            survivors.append(name)
    return survivors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES),
                    help="the vault's 'Raspberry Pi 5' folder; 'none' to skip the cross-check")
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if not a.compiler:
        fail("pass --compiler or set PMF_COMPILER")
    compiler = str(resolve_compiler(a.compiler))
    src = None if a.sources == "none" else pathlib.Path(a.sources)
    if src is not None and not src.is_dir():
        print(f"  --sources {src} is not a folder here")
        src = None
    k = constants(src)
    codes = library_codes((ROOT / LIBRARY).read_text(encoding="latin-1"))
    for need in ("SDIO_ERR_NO_CARD", "SDIO_ERR_CMD_ERROR", "SDIO_ERR_PINCTRL", "SDIO_ERR_BASECLK"):
        if need not in codes:
            fail(f"#{need} is not declared in {LIBRARY}")
    with tempfile.TemporaryDirectory(prefix="pmf_sdio_pi5_") as td:
        work = pathlib.Path(td)
        img = work / "pi5sdio.img"
        build(compiler, ROOT, img)
        ck = gate(img, k, codes, a.verbose)
        for m in ck.bad:
            print("  FAIL " + m)
        survivors = [] if a.no_mutants else mutants(compiler, k, codes, work)
    if ck.bad or survivors:
        print(f"a64_sdio_pi5_check: FAIL - {len(ck.bad)} of {ck.n} checks red, "
              f"{len(survivors)} mutant(s) alive")
        return 1
    print(f"a64_sdio_pi5_check: PASS - {ck.n} checks"
          + ("" if a.no_mutants else f", {len(MUTANTS)}/{len(MUTANTS)} mutants red")
          + ". Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
