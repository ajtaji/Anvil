#!/usr/bin/env python3
"""Executable desk gate for the Raspberry Pi 5 fan: RP1 PWM1 channel 3 on
GPIO45, the tachometer on GPIO29, the BCM2712 temperature, and the ONE
shared fan curve (Anvil/Core/fan.pbi) driving them - built -t pi5 and run
under the AArch64 model against a modelled register file.

THE MODEL IS BUILT FROM THE PUBLISHED SOURCES, NOT FROM THE LIBRARY.
Every address, offset, bit and number below is pinned with the file it was
read from (vault "Raspberry Pi 5/Sources" and "References", and
raspberrypi/linux at 7e030b60792de1c15b9ec1d8d5d34d63f0f0f1d8).  An access
the model was not built to expect stops the run and names the address, so
a wrong offset in RaspberryPi4/Lib/rp1_pwm.pi4 fails here rather than
becoming the model's opinion.

WHAT THE MODEL DOES THAT A REGISTER STORE WOULD NOT
  * GLOBAL_CTRL.SET_UPDATE self-clears ONLY while clk_pwm1 runs from the
    crystal with ENABLE set (rp1-peripherals.pdf Table 26: the update is
    taken in the PWM clock domain).  Channel enables and CHAN3_CTRL take
    effect only through that update; RANGE/DUTY take effect at once.
  * A four-wire fan sits on the connector: its speed follows the duty the
    PAD is really producing - through the channel's INVERT and the board's
    inverted FAN_PWM line (the DTB's PWM_POLARITY_INVERTED) - and its tach
    toggles GPIO29 at two pulses per revolution in simulated time.  A pad
    not muxed to pwm1 is not driving the fan, and is recorded.
  * The AVS monitor answers one code per read in section C, so the curve is
    walked from a register to the DUTY register end to end.

WHAT IT CANNOT DO: say anything about silicon.  Desk proof only; silicon owed.

THE FIRMWARE FALLBACK.  thermal.pi4 falls back to the property mailbox,
and RaspberryPi4/Lib/mailbox.pi4 carries the BCM2712 transport.  The model is
the published one: mailbox@7c013880 (bcm2712.dtsi) through /soc, the
bcm2835-mailbox.c register map, channel 8, and bus address = ARM address for
DRAM (bcm2712.dtsi /soc dma-ranges map 0 -> 0; a BCM2711 $C0000000 alias
in the message is refused by name).  A second run serves an INVALID AVS
reading, so the firmware must answer and the source must say so.

Run:     py -3 -B tools/a64/a64_fan_pi5_check.py --compiler <PureMetalForge.exe>
Mutants: add --mutate (every one must be killed).
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

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("PMF_REPO") or pathlib.Path(__file__).resolve().parents[2])
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols            # noqa: E402
sys.path.insert(0, str(HERE.parent))
from pmf_compiler import resolve_compiler             # noqa: E402

PROBE_REL = "RaspberryPi4/Examples/Diagnostics/pi5FanSelfTest.pi4"
REL_LIB = "RaspberryPi4/Lib/rp1_pwm.pi4"
REL_HOST = "RaspberryPi4/Board/hw_pwm_rp1.pi4"
REL_AVS = "RaspberryPi4/Modules/thermal_avs.pi4"
REL_HWMOD = "RaspberryPi4/Board/hw_mod.pi4"
REL_FAN = "Anvil/Core/fan.pbi"
REL_HAL = "Anvil/Hal/hal.pbi"
REL_MBX = "RaspberryPi4/Lib/mailbox.pi4"

LOAD = 0x400000
STACK = 0x3000000
LR = 0xDEADBEE0
CNTFRQ = 54_000_000
TICKS_PER_STEP = 54           # 1 us per instruction (pessimistic by ~1000x)
MMIO_FLOOR = 0x10_0000_0000

COMPILER = {"path": None}
OVERRIDE: dict = {}


def die(msg: str):
    raise SystemExit("a64_fan_pi5_check: " + msg)


# ======================================================================
#  PINNED FACTS
#  DTS  bcm2712-rpi-5-b.dts   RP1D rp1.dtsi   DS bcm2712-ds.dtsi
#  PWM  drivers/pwm/pwm-rp1.c CLK drivers/clk/clk-rp1.c
#  PIN  drivers/pinctrl/rp1/pinctrl-rp1.c (vault Sources/pinctrl-rp1.c)
#  THM  drivers/thermal/broadcom/bcm2711_thermal.c
#  FAN  drivers/hwmon/pwm-fan.c
#  MAN  rp1-peripherals.pdf (3.4 PWM, Tables 25/26/31)
#  HB   vault Raspberry Pi 5/HARDWARE-BRINGUP.md
# ======================================================================
PINNED = {
    # DTS cooling_fan: pwms = <&rp1_pwm1 3 41566 PWM_POLARITY_INVERTED>;
    "fan_pwm": ("rp1_pwm1", 3, 41566, "PWM_POLARITY_INVERTED"),
    # DTS gpio-line-names: GPIO29 "FAN_TACH", GPIO45 "FAN_PWM"
    "line_names": {29: "FAN_TACH", 45: "FAN_PWM"},
    # DTS &rp1_pwm1 pinctrl-0 = <&rp1_pwm1_gpio45>; RP1D rp1_pwm1_gpio45
    # { function = "pwm1"; pins = "gpio45"; bias-pull-down; }
    "pwm_pinctrl": ("gpio45", "pwm1", "bias-pull-down"),
    # RP1D pwm@9c000 reg = <0xc0 0x4009c000 0x0 0x100>; rate 50000000
    "rp1_pwm1_reg": 0xC04009C000,
    "rp1_pwm0_reg": 0xC040098000,
    "pwm_clk_rate": 50_000_000,
    # RP1D clocks@18000 reg <0xc0 0x40018000 ...>; rp1_gpio reg d0000/e0000/f0000
    "rp1_clocks_reg": 0xC040018000,
    "rp1_gpio_regs": (0xC0400D0000, 0xC0400E0000, 0xC0400F0000),
    # HB: "CPU $1F_00xxxxxx = RP1 c0_40xxxxxx"
    "rp1_window": (0xC040000000, 0x1F00000000),
    # PWM macros
    "PWM_GLOBAL_CTRL": 0x000,
    "PWM_CHANNEL_CTRL": (0x014, 16),
    "PWM_RANGE": (0x018, 16),
    "PWM_DUTY": (0x020, 16),
    "PWM_CHANNEL_DEFAULT": (1 << 8) + (1 << 0),
    "PWM_POLARITY": 1 << 3,
    "SET_UPDATE": 1 << 31,
    # MAN Table 25 - the offsets a channel owns (CTRL, RANGE, PHASE, DUTY)
    "man_chan_regs": [(0x14, 0x18, 0x1C, 0x20), (0x24, 0x28, 0x2C, 0x30),
                      (0x34, 0x38, 0x3C, 0x40), (0x44, 0x48, 0x4C, 0x50)],
    # CLK
    "CLK_PWM1_CTRL": 0x84, "CLK_PWM1_DIV_INT": 0x88, "CLK_PWM1_DIV_FRAC": 0x8C,
    "CLK_CTRL_ENABLE": 1 << 11, "CLK_CTRL_AUXSRC": (9, 5),
    "clk_pwm1_aux_xosc_index": 2,        # parents { -1, pll_video_sec, index 0 = xosc }
    "xosc_hz": 50_000_000,
    # PIN
    "banks": [(0, 28, 0x0000, 0x0000, 0x0004), (28, 6, 0x4000, 0x4000, 0x4004),
              (34, 20, 0x8000, 0x8000, 0x8004)],   # min, n, gpio, rio, pads
    "GPIO_CTRL": 0x0004, "RIO_OE": 0x04, "RIO_IN": 0x08, "CLR_OFFSET": 0x3000,
    "FUNCSEL_MASK": 0x1F, "OUTOVER_MASK": 0x3000, "OEOVER_MASK": 0xC000,
    "FSEL_GPIO": 5,
    "pin45_funcs": ["pwm1", "i2c5", "spi7", "spi6", "i2s2", "gpio", "proc_rio"],
    "PAD_PULL": (0x0C, 2), "PUD_DOWN": 1, "PUD_UP": 2,
    "PAD_IN_ENABLE": 0x40, "PAD_OUT_DISABLE": 0x80,
    # FAN pulses-per-revolution default
    "tach_ppr": 2,
    # DS avs-monitor@7d542000, child "brcm,bcm2711-thermal";
    # cpu-thermal coefficients = <(-550) 450000>;
    "avs_bus": 0x7D542000, "coefficients": (-550, 450000),
    # HB: the PL011 at bus 0x7d001000 is CPU $107D001000 (the /soc ranges)
    "soc_example": (0x7D001000, 0x107D001000),
    # THM
    "AVS_RO_TEMP_STATUS": 0x200, "VALID_bits": (16, 10), "DATA_genmask": (9, 0),
    # bcm2712.dtsi: mailbox: mailbox@7c013880 { "brcm,bcm2835-mbox" };
    # /soc dma-ranges = <0x00 0x00000000  0x00 0x00000000  0x10 0x00000000> -
    # DRAM is at bus 0, no alias.
    "mbox_bus": 0x7C013880, "dram_bus_offset": 0,
    # bcm2835-mailbox.c: MAIL0_RD 0x00, MAIL0_STA 0x18, MAIL1_WRT 0x20,
    # MAIL1_STA 0x38; ARM_MS_EMPTY BIT(30).  Channel 8 = property tags.
    "MAIL0_RD": 0x00, "MAIL0_STA": 0x18, "MAIL1_WRT": 0x20, "MAIL1_STA": 0x38,
    "ARM_MS_EMPTY": 1 << 30, "channel": 8,
    # raspberrypi-firmware.h
    "TAG_TEMPERATURE": 0x00030006, "TAG_MAX_TEMPERATURE": 0x0003000A,
}

# What the modelled firmware answers - not a value any AVS code converts to
# exactly, so the fallback run can tell which source answered.
FW_TEMP_MILLI = 61234
FW_TEMP_MAX_MILLI = 85000


class Facts:
    def __init__(self) -> None:
        P = PINNED
        rbus, rcpu = P["rp1_window"]
        self.rp1 = lambda bus: rcpu + (bus - rbus)
        self.pwm1 = self.rp1(P["rp1_pwm1_reg"])
        self.pwm0 = self.rp1(P["rp1_pwm0_reg"])
        self.clocks = self.rp1(P["rp1_clocks_reg"])
        self.iobank, self.rio, self.pads = (self.rp1(r) for r in P["rp1_gpio_regs"])
        blk, chan, period, pol = P["fan_pwm"]
        if blk != "rp1_pwm1":
            die("the pinned fan node no longer names rp1_pwm1")
        self.chan, self.period_ns = chan, period
        self.inverted = pol == "PWM_POLARITY_INVERTED"
        cb, cs = P["PWM_CHANNEL_CTRL"]
        self.ctrl_off = cb + chan * cs
        self.range_off = P["PWM_RANGE"][0] + chan * P["PWM_RANGE"][1]
        self.duty_off = P["PWM_DUTY"][0] + chan * P["PWM_DUTY"][1]
        man = P["man_chan_regs"][chan]
        if (self.ctrl_off, self.range_off, self.duty_off) != (man[0], man[1], man[3]):
            die("pwm-rp1.c's macros and the manual's Table 25 disagree for channel %d" % chan)
        self.all_chan = {o for regs in P["man_chan_regs"] for o in regs}
        self.clk_period_ns = (10**9 + P["pwm_clk_rate"] // 2) // P["pwm_clk_rate"]
        self.range = (period + self.clk_period_ns // 2) // self.clk_period_ns
        hi, lo = P["CLK_CTRL_AUXSRC"]
        self.auxsrc_mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
        self.aux_xosc = P["clk_pwm1_aux_xosc_index"] << lo
        pin, fn, bias = P["pwm_pinctrl"]
        self.fan_gpio = int(pin[4:])
        if P["line_names"].get(self.fan_gpio) != "FAN_PWM":
            die("the pinctrl pin is not the line the DTB names FAN_PWM")
        self.fan_fsel = P["pin45_funcs"].index(fn)
        self.tach_gpio = [g for g, n in P["line_names"].items() if n == "FAN_TACH"][0]
        mask, shift = P["PAD_PULL"]
        self.pull_mask = mask
        self.pull_down = P["PUD_DOWN"] << shift
        self.pull_up = P["PUD_UP"] << shift
        if bias != "bias-pull-down":
            die("the pinned pinctrl bias changed")
        # AVS through the /soc ranges: the same 0x7c000000 window the PL011 proves.
        b, c = P["soc_example"]
        self.soc = lambda bus: bus + (c - b)
        self.avs_status = self.soc(P["avs_bus"]) + P["AVS_RO_TEMP_STATUS"]
        self.valid = sum(1 << x for x in P["VALID_bits"])
        self.slope, self.offset = P["coefficients"]
        self.uart_dr = self.soc(0x7D001000)
        self.mbox = self.soc(P["mbox_bus"])
        self.uart_fr = self.uart_dr + 0x18

    def bank(self, g):
        for mn, n, go, ro, po in PINNED["banks"]:
            if mn <= g < mn + n:
                j = g - mn
                return (self.iobank + go + j * 8 + PINNED["GPIO_CTRL"],
                        self.pads + po + j * 4, self.rio + ro, j)
        die("gpio %d is in no bank" % g)


# ======================================================================
#  SOURCES UNDER TEST
# ======================================================================
def read(p: pathlib.Path) -> str:
    if not p.exists():
        die("%s is missing" % p)
    return p.read_text(errors="replace")


def source(rel: str) -> str:
    return OVERRIDE.get(rel) or read(ROOT / rel)


def pi5_view(text: str) -> str:
    """The text as -t pi5 compiles it: CompilerElse branches of a
    `CompilerIf #PMF_CHIP = 2712` dropped."""
    out, state = [], 0
    for ln in text.split("\n"):
        s = ln.strip()
        if re.match(r"CompilerIf\s+#PMF_CHIP\s*=\s*2712\b", s):
            state = 1
            continue
        if state == 1 and s.startswith("CompilerElse"):
            state = 2
            continue
        if state and s.startswith("CompilerEndIf"):
            state = 0
            continue
        if state != 2:
            out.append(ln)
    return "\n".join(out)


def const(rel: str, name: str) -> int:
    m = re.search(r"^%s\s*=\s*(-?\$?[0-9A-Fa-f]+)" % re.escape(name), pi5_view(source(rel)), re.M)
    if not m:
        die("%s no longer defines %s" % (rel, name))
    v = m.group(1)
    neg = v.startswith("-")
    v = v.lstrip("-")
    n = int(v[1:], 16) if v.startswith("$") else int(v)
    return -n if neg else n


class Policy:
    def __init__(self) -> None:
        self.low = const(REL_FAN, "#FAN_LOW_F_DEFAULT") * 1000
        self.high = const(REL_FAN, "#FAN_HIGH_F_DEFAULT") * 1000
        self.hyst = const(REL_FAN, "#FAN_HYST_F_DEFAULT") * 1000
        self.min_duty = const(REL_FAN, "#FAN_MIN_DUTY")
        self.kick_duty = const(REL_FAN, "#FAN_KICK_DUTY")
        self.kick_ms = const(REL_FAN, "#FAN_KICK_MS")
        self.failsafe = const(REL_FAN, "#FAN_FAILSAFE_DUTY")
        self.dmax = const(REL_FAN, "#FAN_DUTY_MAX")
        self.running = 0
        self.kicking = 0
        self.kick_start = 0

    def ramp(self, mf):
        if mf <= self.low:
            return self.min_duty
        if mf >= self.high:
            return self.dmax
        return self.min_duty + (self.dmax - self.min_duty) * (mf - self.low) // (self.high - self.low)

    def auto(self, mf, ms):
        """fan.pbi's documented rule: start AT low, stop strictly below
        low - hyst, a full-duty kick for kick_ms after a start."""
        if self.running:
            want = not (mf < self.low - self.hyst)
        else:
            want = mf >= self.low
        if not want:
            self.running = self.kicking = 0
            return 0
        if not self.running:
            self.running, self.kicking, self.kick_start = 1, 1, ms
        d = self.ramp(mf)
        if self.kicking:
            if ms - self.kick_start < self.kick_ms:
                d = max(d, self.kick_duty)
            else:
                self.kicking = 0
        return d


def milli_f(mc: int) -> int:
    # F = C * 9/5 + 32, milli, nearest (the ruling's one conversion).
    n = mc * 9
    q = (abs(n) * 2 + 5) // 10
    return (q if n >= 0 else -q) + 32000


def counts(rng: int, permille: int) -> int:
    if permille <= 0:
        return 0
    if permille >= 1000:
        return rng
    return (rng * permille + 500) // 1000


# ======================================================================
#  THE MODELLED BOARD
# ======================================================================
RPM_FULL = 6000
# What the modelled firmware keeps in rp1_pwm1 + $3C (dts rpm-offset) - a
# value no counted tach in this run can produce, so the row names its source.
FW_RPM_WORD = 2718
B_CODE = 739
C_CODES = [780, 740, 736, 720, 700, 680, 700, 736, 740, 745, 736, 600]


class Board:
    def __init__(self, cpu, f: Facts, avs_b_valid: bool = True):
        self.cpu, self.f = cpu, f
        self.avs_b_valid = avs_b_valid
        self.reply = None
        self.tags: list[int] = []
        self.uart = bytearray()
        self.ticks = 0
        self.fails: list[str] = []
        self.writes: list[tuple] = []          # (uart_len, addr, value)
        self.glob = 0                          # GLOBAL_CTRL as written
        self.upd_pending = False
        self.committed_en = 0
        self.committed_ctrl = {}
        self.ctrl = {}
        self.rng = {}
        self.duty = {}
        self.clk = {0x84: 0x0, 0x88: 0x0, 0x8C: 0x0}
        self.fan_ctrl, self.fan_pad, _, _ = f.bank(f.fan_gpio)
        self.tach_ctrl, self.tach_pad, self.tach_rio, self.tach_j = f.bank(f.tach_gpio)
        self.gctrl = {self.fan_ctrl: 0x1F, self.tach_ctrl: 0x1F}
        self.gpad = {self.fan_pad: 0x9A, self.tach_pad: 0x16}
        self.tach_oe = 1                       # left as an output: the library must clear it
        self.rpm = 0.0
        self.undriven_reads = 0
        self.avs_reads = 0
        self.c_codes = list(C_CODES)
        self.c_served: list[int] = []

    # -- time and the fan --------------------------------------------
    def us(self):
        return self.ticks / (CNTFRQ / 1e6)

    def clock_running(self):
        c = self.clk[0x84]
        return bool(c & PINNED["CLK_CTRL_ENABLE"]) and (c & self.f.auxsrc_mask) == self.f.aux_xosc \
            and self.clk[0x88] != 0

    def pad_driven(self):
        f = self.f
        c = self.gctrl[self.fan_ctrl]
        return ((c & PINNED["FUNCSEL_MASK"]) == f.fan_fsel and (c & 0xF000) == 0
                and not (self.gpad[self.fan_pad] & PINNED["PAD_OUT_DISABLE"]))

    def fan_fraction(self):
        f = self.f
        ch = f.chan
        if not self.pad_driven():
            return None
        if not (self.committed_en & (1 << ch)) or not self.clock_running():
            return 0.0 if f.inverted else 1.0      # channel output 0 -> pad idle
        rng = self.rng.get(ch, 0)
        d = self.duty.get(ch, 0)
        frac = 0.0 if rng == 0 else min(1.0, d / rng)
        inv = bool(self.committed_ctrl.get(ch, 0) & PINNED["PWM_POLARITY"])
        # The board inverts FAN_PWM (the DTB's PWM_POLARITY_INVERTED), so the
        # fan sees the channel's own duty exactly when the channel inverts.
        return frac if inv == f.inverted else 1.0 - frac

    def refresh_fan(self):
        fr = self.fan_fraction()
        self.rpm = RPM_FULL if fr is None else RPM_FULL * fr

    def tach_level(self):
        if self.rpm <= 0:
            return 1
        hz = self.rpm * PINNED["tach_ppr"] / 60.0
        return 1 if ((self.us() / 1e6) * hz) % 1.0 < 0.5 else 0

    # -- MMIO ----------------------------------------------------------
    def phase_c(self):
        return b"=== C curve ===" in self.uart

    def mailbox_write(self, msg):
        P = PINNED
        if msg & 0xF != P["channel"]:
            die("the image used mailbox channel %d, not %d" % (msg & 0xF, P["channel"]))
        bus = msg & ~0xF
        if bus & 0xC0000000:
            die("the mailbox message carries $%08X - the BCM2711's $C0000000 alias; "
                "on a BCM2712 DRAM is at bus 0 (dma-ranges)" % bus)
        arm = bus - P["dram_bus_offset"]
        ld, st = self.cpu.load, self.cpu.store
        total = ld(arm, 4)
        if total < 12 or total % 4 or total > 4096 or ld(arm + 4, 4) != 0:
            die("a malformed property buffer at $%X" % arm)
        off = 8
        while True:
            tag = ld(arm + off, 4)
            if tag == 0:
                break
            vb = ld(arm + off + 4, 4)
            self.tags.append(tag)
            if tag == P["TAG_TEMPERATURE"]:
                val = FW_TEMP_MILLI
            elif tag == P["TAG_MAX_TEMPERATURE"]:
                val = FW_TEMP_MAX_MILLI
            else:
                die("the fan stack sent tag $%08X; it should only ask for the "
                    "temperature and the maximum" % tag)
            st(arm + off + 12, 0, 4)
            st(arm + off + 16, val, 4)
            st(arm + off + 8, 0x80000000 | 8, 4)
            off += 12 + vb
        st(arm + 4, 0x80000000, 4)
        self.reply = msg

    def load(self, a, size):
        f = self.f
        if a == f.uart_fr:
            return 0
        P = PINNED
        if f.mbox <= a < f.mbox + 0x40:
            off = a - f.mbox
            if off == P["MAIL1_STA"]:
                return 0
            if off == P["MAIL0_STA"]:
                return 0 if self.reply is not None else P["ARM_MS_EMPTY"]
            if off == P["MAIL0_RD"]:
                if self.reply is None:
                    die("the image read an empty mailbox")
                r, self.reply = self.reply, None
                return r
            die("read of mailbox +$%02X, which the transport never needs" % off)
        if a == f.avs_status:
            self.avs_reads += 1
            if not self.phase_c():
                return (f.valid if self.avs_b_valid else 0) | B_CODE
            code = self.c_codes.pop(0) if self.c_codes else C_CODES[-1]
            self.c_served.append(code)
            return f.valid | code
        if f.pwm1 <= a < f.pwm1 + 0x100:
            off = a - f.pwm1
            if off == 0x3C:
                # bcm2712-rpi-5-b.dts cooling_fan rpm-regmap = <&rp1_pwm1>,
                # rpm-offset = <0x3c>: the firmware's RPM word.
                self.rpm_reads = getattr(self, "rpm_reads", 0) + 1
                return FW_RPM_WORD
            if off == 0:
                # The update is taken in the PWM clock domain: only a running
                # clk_pwm1 ever clears SET_UPDATE.
                if self.upd_pending and self.clock_running():
                    self.upd_pending = False
                    self.committed_en = self.glob & 0xF
                    self.committed_ctrl = dict(self.ctrl)
                    self.refresh_fan()
                return self.glob | (PINNED["SET_UPDATE"] if self.upd_pending else 0)
            ch, k = self.chan_reg(off)
            return {0: self.ctrl, 1: self.rng, 3: self.duty}.get(k, {}).get(ch, 0)
        if f.clocks <= a < f.clocks + 0x10038:
            off = a - f.clocks
            if off in self.clk:
                return self.clk[off]
            die("read of RP1 clocks +$%X, which is not clk_pwm1" % off)
        if a in self.gctrl:
            return self.gctrl[a]
        if a in self.gpad:
            return self.gpad[a]
        if a == self.tach_rio + PINNED["RIO_IN"]:
            c = self.gctrl[self.tach_ctrl]
            ok = ((c & PINNED["FUNCSEL_MASK"]) == PINNED["FSEL_GPIO"] and not self.tach_oe
                  and (self.gpad[self.tach_pad] & PINNED["PAD_IN_ENABLE"]))
            lv = self.tach_level() if ok else 0
            return lv << self.tach_j
        die("unmodelled MMIO read at $%X" % a)

    def chan_reg(self, off):
        for ch, regs in enumerate(PINNED["man_chan_regs"]):
            if off in regs:
                return ch, regs.index(off)
        die("PWM1 offset $%02X is not a channel register this fan uses" % off)

    def store(self, a, v, size):
        f = self.f
        v &= 0xFFFFFFFF
        if a == f.uart_dr:
            self.uart.append(v & 0xFF)
            return
        if a == f.mbox + PINNED["MAIL1_WRT"]:
            self.mailbox_write(v)
            return
        if f.mbox <= a < f.mbox + 0x40:
            die("write to mailbox +$%02X, which is not MAIL1_WRT" % (a - f.mbox))
        self.writes.append((len(self.uart), a, v))
        if f.pwm0 <= a < f.pwm0 + 0x100:
            die("a write to rp1_pwm0 (+$%X): the fan is on rp1_pwm1" % (a - f.pwm0))
        if f.pwm1 <= a < f.pwm1 + 0x100:
            off = a - f.pwm1
            if off == 0:
                if v & 0x7FFFFFF0:
                    die("GLOBAL_CTRL written with reserved bits: $%08X" % v)
                self.glob = v & 0xF
                if v & PINNED["SET_UPDATE"]:
                    self.upd_pending = True
                return
            ch, k = self.chan_reg(off)
            if ch != f.chan:
                self.fails.append("wrote PWM1 channel %d (+$%02X); the DTB gives the fan channel %d"
                                  % (ch, off, f.chan))
            if k == 0:
                self.ctrl[ch] = v
            elif k == 1:
                self.rng[ch] = v
            elif k == 3:
                self.duty[ch] = v
            else:
                self.fails.append("wrote CHAN%d_PHASE, which the fan never needs" % ch)
            self.refresh_fan()
            return
        if f.clocks <= a < f.clocks + 0x10038:
            off = a - f.clocks
            if off not in self.clk:
                die("write to RP1 clocks +$%X, which is not clk_pwm1" % off)
            self.clk[off] = v
            self.refresh_fan()
            return
        if a in self.gctrl:
            self.gctrl[a] = v
            self.refresh_fan()
            return
        if a in self.gpad:
            self.gpad[a] = v
            self.refresh_fan()
            return
        if a == self.tach_rio + PINNED["CLR_OFFSET"] + PINNED["RIO_OE"]:
            if v & (1 << self.tach_j):
                self.tach_oe = 0
            if v & ~(1 << self.tach_j):
                die("SYS_RIO1 OE clear touched pins other than the tach: $%X" % v)
            return
        die("unmodelled MMIO write at $%X = $%X" % (a, v))


def run(img: pathlib.Path, f: Facts, limit=60_000_000, avs_b_valid=True):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LR
    board = Board(cpu, f, avs_b_valid)
    mem = cpu.memory

    def bcm2711(a):
        if 0xFC000000 <= a < 0x100000000:
            die("an access at $%X, in the BCM2711's peripheral window, which a "
                "BCM2712 does not have" % a)

    def load(a, size):
        cpu.align_guard(a, size, False)
        bcm2711(a)
        if a >= MMIO_FLOOR:
            return board.load(a, size)
        return sum(mem.get(a + i, 0) << (8 * i) for i in range(size))

    def store(a, v, size):
        cpu.align_guard(a, size, True)
        bcm2711(a)
        if a >= MMIO_FLOOR:
            board.store(a, v, size)
            return
        for i in range(size):
            mem[a + i] = (v >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu)
    n = 0
    while cpu.pc != LR:
        n += 1
        if n > limit:
            die("the probe never returned after %d steps; UART so far:\n%s"
                % (limit, board.uart.decode(errors="replace")[-600:]))
        board.ticks += TICKS_PER_STEP
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            continue
        if (ins & 0xFFFFFFE0) == 0xD53BE020:
            cpu.x[ins & 31] = board.ticks
            cpu.pc += 4
            continue
        plain()
    return board, cpu.x[0], n


# ======================================================================
#  BUILDING
# ======================================================================
MODULE_DECL = re.compile(r"^(Module |ModuleABI |ModuleMatch |Seam )")


def probe_source(work: pathlib.Path) -> str:
    text = source(PROBE_REL)

    def setting(src, line, new):
        pat = re.compile(r"^%s[ \t]*$" % re.escape(line), re.M)
        if len(pat.findall(src)) != 1:
            die("%s no longer has exactly one line %r" % (PROBE_REL, line))
        return pat.sub(lambda _m: new, src)

    lines = source(REL_AVS).split("\n")
    kept = [ln for ln in lines if not MODULE_DECL.match(ln)]
    if len(lines) - len(kept) != 4:
        die("%s no longer has exactly four module declaration lines" % REL_AVS)
    drv = work / "thermal_avs_linked.pbi"
    drv.write_text("\n".join(kept))
    text = setting(text, "#FAN_AVS_DRIVER = 0", "#FAN_AVS_DRIVER = 1")
    text = setting(text, "#FAN_AVS_DEVICE = 0",
                   "#FAN_AVS_DEVICE = $%X" % const(REL_HWMOD, "#HWDEV_AVS_MONITOR"))
    text = setting(text, "; FAN-AVS-DRIVER-INCLUDE", 'XIncludeFile "%s"' % drv.resolve().as_posix())
    for rel, body in OVERRIDE.items():
        if rel in (REL_AVS, REL_HWMOD, PROBE_REL):
            continue
        marker = 'XIncludeFile "%s"' % rel
        if text.count(marker) != 1:
            die("the probe does not include %s exactly once" % rel)
        cp = work / pathlib.Path(rel).name
        cp.write_text(body)
        text = text.replace(marker, 'XIncludeFile "%s"' % cp.resolve().as_posix())
    return text


def build(work: pathlib.Path) -> pathlib.Path:
    work.mkdir(parents=True, exist_ok=True)
    src = work / "fan5probe.pi4"
    src.write_text(probe_source(work))
    out = work / "fan5probe.img"
    r = subprocess.run([COMPILER["path"], "--compile", str(src), "-t", "pi5",
                        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
                        "--entry-returns", "-o", str(out)],
                       cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.exists():
        die("the probe would not build:\n" + r.stdout[-2500:] + r.stderr[-800:])
    return out


# ======================================================================
#  THE CHECK
# ======================================================================
class Said:
    def __init__(self, text):
        self.rows = {}
        for line in text.splitlines():
            m = re.match(r"^([A-Z][A-Za-z0-9 ]*?)((?:\s+-?\d+)+)\s*$", line)
            if m:
                self.rows.setdefault(m.group(1).strip(), []).append(
                    [int(x) for x in m.group(2).split()])

    def one(self, k):
        v = self.rows.get(k)
        return v[0][0] if v and len(v[0]) == 1 else None

    def all(self, k):
        return self.rows.get(k, [])


def check(fails: list, work: pathlib.Path) -> int:
    f = Facts()
    n = [0]

    def expect(ok, msg):
        n[0] += 1
        if not ok:
            fails.append(msg)

    hal = {k: const(REL_HAL, k) for k in (
        "#HW_PWM_OK", "#HW_PWM_PIN", "#HW_PWM_HZ", "#HW_PWM_DUTY", "#HW_PWM_STATE", "#HW_PWM_BUSY",
        "#HW_PWM_KIND_NONE", "#HW_PWM_KIND_HARD", "#HW_TEMP_SRC_REGISTER",
        "#HW_TEMP_SRC_FIRMWARE")}

    # The firmware transport must exist on this chip, or the probe's
    # mailbox rows would talk to the BCM2711's addresses.
    mbx = pi5_view(source(REL_MBX)) != source(REL_MBX)
    expect(mbx, "RaspberryPi4/Lib/mailbox.pi4 has no #PMF_CHIP = 2712 branch, so the "
           "Pi 5 firmware fallback cannot be asked")

    img = build(work)
    board, x0, steps = run(img, f)
    text = board.uart.decode("utf-8", "replace")
    (work / "transcript.txt").write_text(text)
    s = Said(text)
    print("probe: %d instructions, %d bytes of transcript, x0=%d" % (steps, len(text), x0))
    if not OVERRIDE:
        for line in text.splitlines():
            if line.startswith(("P range", "P hz ", "T ", "C step", "B milli")):
                print("   | " + line)
    for m in board.fails:
        expect(False, m)
    expect(s.one("END fails") == 0 and x0 == 0,
           "the probe counted %s internal disagreements" % s.one("END fails"))
    for line in text.splitlines():
        if line.startswith("!!"):
            expect(False, "probe: " + line)

    # ---- A: the conversion, from the DTB's coefficients ------------------
    want_fold = 0
    for i in range(1024):
        want_fold = (want_fold * 131 + (f.slope * i + f.offset + 1000000)) % 1000000007
    expect(s.one("A fold") == want_fold, "A: the AVS line over all 1024 codes is not "
           "-550*code + 450000 (bcm2712-ds.dtsi cpu-thermal)")
    for code, got in [(r[0], r[1]) for r in s.all("A code")]:
        expect(got == f.slope * code + f.offset, "A: code %d gave %d" % (code, got))
    for w, got in [(r[0], r[1]) for r in s.all("A validof")]:
        expect(got == int((w & f.valid) == f.valid), "A: validity of $%X gave %d" % (w, got))

    # ---- B: the register reached through the board's device handle --------
    expect(s.one("B init") == 0 and s.one("B fills") == 1,
           "B: the driver did not initialise and publish exactly one function")
    expect(s.one("B milli") == f.slope * B_CODE + f.offset,
           "B: HwTempMilliC gave %s, the modelled AVS code %d is %d mC"
           % (s.one("B milli"), B_CODE, f.slope * B_CODE + f.offset))
    expect(s.one("B source") == hal["#HW_TEMP_SRC_REGISTER"], "B: the source is not the register")
    expect(s.one("B bound") == 1, "B: the thermal seam was not bound after a good read")
    expect(s.one("B mbxinit") == 1, "B: MailboxInit failed on the BCM2712 transport")
    expect(s.one("B mbxmilli") == FW_TEMP_MILLI and s.one("B maxmilli") == FW_TEMP_MAX_MILLI,
           "B: the firmware said %s / %s, want %d / %d"
           % (s.one("B mbxmilli"), s.one("B maxmilli"), FW_TEMP_MILLI, FW_TEMP_MAX_MILLI))

    # ---- B, again: the register answers INVALID, the firmware must answer --
    fb, fx0, _ = run(img, f, avs_b_valid=False)
    ft = fb.uart.decode("utf-8", "replace")
    fs = Said(ft)
    expect(fs.one("B milli") == FW_TEMP_MILLI,
           "fallback: with the AVS invalid HwTempMilliC gave %s, the firmware says %d"
           % (fs.one("B milli"), FW_TEMP_MILLI))
    expect(fs.one("B source") == hal["#HW_TEMP_SRC_FIRMWARE"],
           "fallback: the source is %s, not the firmware" % fs.one("B source"))
    expect(fs.one("B bound") == 0, "fallback: the seam was bound with no good reading")
    expect(fs.one("END fails") == 0 and fx0 == 0, "fallback run: the probe disagreed with itself")
    expect(set(fb.tags) == {PINNED["TAG_TEMPERATURE"], PINNED["TAG_MAX_TEMPERATURE"]},
           "fallback: tags asked %s" % sorted("%08X" % x for x in set(fb.tags)))

    # ---- P: refusals touch nothing; the begin programs the DTB's channel ----
    first_hw = min((u for u, a, v in board.writes), default=None)
    marker = text.find("P hzmax")
    expect(first_hw is not None and marker >= 0 and first_hw > marker,
           "P: a register was written before the begin (a refusal touched hardware)")
    expect(s.one("P duty early") == hal["#HW_PWM_STATE"], "P: Duty before Begin is not STATE")
    expect(s.one("P end early") == hal["#HW_PWM_STATE"], "P: End before Begin is not STATE")
    # GPIO18 is a header PWM0 pin since 2026-09-27: offered as hardware PWM.
    # Beginning it is PWM0's gate (a64_pwm0_pi5_check.py), not this one's,
    # whose model holds only the fan's clock and block.
    expect(s.one("P hard pin18") == 1, "P: pin 18 (header PWM0) is not offered as hardware PWM")
    expect(s.one("P begin pin5") == hal["#HW_PWM_PIN"], "P: pin 5 was not refused as PIN")
    expect(s.one("P begin hz0") == hal["#HW_PWM_HZ"], "P: 0 Hz was not refused as HZ")
    expect(s.one("P begin hzhigh") == hal["#HW_PWM_HZ"], "P: past HzMax was not refused")
    expect(s.one("P count") == 5 and s.one("P pinat") == f.fan_gpio
           and s.one("P default") == f.fan_gpio,
           "P: the fan pin GPIO%d (the DTB's FAN_PWM) is not the first and default of the "
           "five offered (it and the header's PWM0 pins)" % f.fan_gpio)
    hz = s.one("P hzdefault") or 0
    expect(hz > 0 and (10**9 + hz // 2) // hz == f.period_ns,
           "P: HwPwmHzDefault %d Hz is not the DTB's %d ns period" % (hz, f.period_ns))
    expect(s.one("P begin") == hal["#HW_PWM_OK"], "P: Begin on the fan pin failed (%s)" % s.one("P begin"))
    expect(s.one("P kind") == hal["#HW_PWM_KIND_HARD"] and s.one("P pin") == f.fan_gpio,
           "P: kind/pin after Begin")
    expect(s.one("P range") == f.range,
           "P: RANGE %s, pwm-rp1.c gives round(%d / %d) = %d"
           % (s.one("P range"), f.period_ns, f.clk_period_ns, f.range))
    expect(board.rng.get(f.chan) == f.range, "P: CHAN%d_RANGE register is %s, want %d"
           % (f.chan, board.rng.get(f.chan), f.range))
    expect(s.one("P hz") == PINNED["pwm_clk_rate"] // f.range, "P: the Hz read back")
    expect(s.one("P divisor") == 1 and s.one("P srchz") == PINNED["xosc_hz"],
           "P: clk_pwm1 not read back as the crystal divided by one")
    expect(s.one("P stalls") == -1, "P: a hardware channel reported a software detail")
    c = board.clk
    expect((c[0x84] & (PINNED["CLK_CTRL_ENABLE"] | f.auxsrc_mask)) == PINNED["CLK_CTRL_ENABLE"] | f.aux_xosc
           and c[0x88] == 1 and c[0x8C] == 0,
           "P: clk_pwm1 CTRL/DIV_INT/DIV_FRAC = $%X/%d/%d" % (c[0x84], c[0x88], c[0x8C]))
    clk_w = [(i, a - f.clocks, v) for i, (u, a, v) in enumerate(board.writes) if f.clocks <= a < f.clocks + 0x100]
    en_i = [i for i, o, v in clk_w if o == 0x84 and v & PINNED["CLK_CTRL_ENABLE"]]
    div_i = [i for i, o, v in clk_w if o == 0x88]
    expect(en_i and div_i and min(div_i) < min(en_i), "P: clk_pwm1 enabled before its divider was written")
    want_ctrl = PINNED["PWM_CHANNEL_DEFAULT"] | (PINNED["PWM_POLARITY"] if f.inverted else 0)
    expect(board.committed_ctrl.get(f.chan) == want_ctrl,
           "P: CHAN%d_CTRL took effect as $%s, want $%X (mode 1, FIFO_POP_MASK, INVERT per "
           "the DTB's PWM_POLARITY_INVERTED)" % (f.chan, "%X" % board.committed_ctrl.get(f.chan, -1), want_ctrl))
    gpad, gctl = board.gpad[board.fan_pad], board.gctrl[board.fan_ctrl]
    expect((gctl & PINNED["FUNCSEL_MASK"]) == f.fan_fsel and (gctl & 0xF000) == 0,
           "P: GPIO%d CTRL $%X is not FUNCSEL %d (pwm1) with peripheral OE/OUT" % (f.fan_gpio, gctl, f.fan_fsel))
    expect((gpad & f.pull_mask) == f.pull_down and gpad & PINNED["PAD_IN_ENABLE"]
           and not gpad & PINNED["PAD_OUT_DISABLE"],
           "P: GPIO%d pad $%X is not pull-down, input on, output on" % (f.fan_gpio, gpad))
    # Duty rows: each code, and the DUTY register after each call.
    dw = [(u, v) for u, a, v in board.writes if a == f.pwm1 + f.duty_off]
    for p, code in [(r[0], r[1]) for r in s.all("P duty")]:
        row = text.find("P duty %d %d" % (p, code))
        last = [v for u, v in dw if u <= row]
        reg = last[-1] if last else None
        if 0 <= p <= 1000:
            expect(code == hal["#HW_PWM_OK"] and reg == counts(f.range, p),
                   "P: duty %d permille -> code %d, DUTY %s, want %d" % (p, code, reg, counts(f.range, p)))
        else:
            expect(code == hal["#HW_PWM_DUTY"], "P: duty %d permille was not refused" % p)
    expect(s.one("P dutynow") == 1000, "P: a refused duty changed the duty in force")

    # ---- T: the tach, the loop closed through the modelled fan ------------
    win = const(PROBE_REL, "#FAN_TACH_WINDOW_US")
    tol_edge = 60_000_000 // (PINNED["tach_ppr"] * win)
    for p, rpm in [(r[0], r[1]) for r in s.all("T rpm")]:
        want = RPM_FULL * counts(f.range, p) / f.range
        expect(rpm >= 0 and abs(rpm - want) <= tol_edge + want * 0.01 + 1,
               "T: at %d permille the tach said %d rpm, the modelled fan turns at %d"
               % (p, rpm, round(want)))
    expect(len(s.all("T rpm")) == 4, "T: four tach measurements were expected")
    tc, tp = board.gctrl[board.tach_ctrl], board.gpad[board.tach_pad]
    expect((tc & PINNED["FUNCSEL_MASK"]) == PINNED["FSEL_GPIO"] and board.tach_oe == 0
           and tp & PINNED["PAD_IN_ENABLE"] and tp & PINNED["PAD_OUT_DISABLE"],
           "T: GPIO%d is not a plain input (CTRL $%X, pad $%X, OE %d)"
           % (f.tach_gpio, tc, tp, board.tach_oe))
    coarse = s.one("T coarse")
    expect(coarse is not None and coarse < 0 and coarse == const(REL_LIB, "#RP1_TACH_COARSE"),
           "T: a window polled every 5 ms answered %s, not COARSE" % coarse)

    # ---- R: the firmware's RPM word, read raw ------------------------------
    expect(s.one("R rpmreg") == FW_RPM_WORD,
           "R: Rp1FanRpmRegister gave %s, the word at rp1_pwm1 + $3C is %d"
           % (s.one("R rpmreg"), FW_RPM_WORD))
    expect(getattr(board, "rpm_reads", 0) == 1,
           "R: rp1_pwm1 + $3C was read %d times, want exactly once"
           % getattr(board, "rpm_reads", 0))
    expect(not [a for u, a, v in board.writes if a == f.pwm1 + 0x3C],
           "R: rp1_pwm1 + $3C was written - it is a read-only report here")

    # ---- C: register -> milli C -> milli F -> curve -> DUTY register -------
    pol = Policy()
    steps_c = s.all("C step")
    expect(len(steps_c) == len(C_CODES), "C: %d steps, want %d" % (len(steps_c), len(C_CODES)))
    dw = [(u, v) for u, a, v in board.writes if a == f.pwm1 + f.duty_off]
    pos = 0
    for i, (row, code) in enumerate(zip(steps_c, C_CODES)):
        t, mf, d = row
        want_t = f.slope * code + f.offset
        want_f = milli_f(want_t)
        want_d = pol.auto(want_f, i * 1000)
        expect(t == want_t, "C%d: code %d read as %d mC, want %d" % (i, code, t, want_t))
        expect(mf == want_f, "C%d: %d mC converted to %d mF, want %d" % (i, t, mf, want_f))
        expect(d == want_d, "C%d: %d mF gave duty %d, the curve says %d" % (i, mf, d, want_d))
        at = text.find("C set", text.find("C step %d %d %d" % (t, mf, d), pos))
        pos = at + 1
        last = [v for u, v in dw if u <= at]
        expect(last and last[-1] == counts(f.range, want_d),
               "C%d: DUTY register %s after duty %d, want %d"
               % (i, last[-1] if last else None, want_d, counts(f.range, want_d)))
    expect(board.c_served == C_CODES, "C: the AVS was read %d times in C, want once per step"
           % len(board.c_served))
    expect(s.one("C blindduty") == pol.failsafe, "C: no thermometer did not give the failsafe")

    # ---- E: release leaves the fan at full ---------------------------------
    expect(s.one("E end") == hal["#HW_PWM_OK"] and s.one("E kind") == hal["#HW_PWM_KIND_NONE"],
           "E: End did not release")
    expect(board.duty.get(f.chan) == f.range and board.fan_fraction() == 1.0,
           "E: after End the fan sees %s of full, not full" % board.fan_fraction())
    expect(s.one("E duty after") == hal["#HW_PWM_STATE"] and s.one("E end again") == hal["#HW_PWM_STATE"],
           "E: a released channel still accepted Duty/End")
    return n[0]


# ======================================================================
#  MUTANTS - each must turn the gate red
# ======================================================================
MUTATIONS = [
    (REL_LIB, "channel 2 instead of the DTB's 3", "#RP1PWM_CHAN        = 3", "#RP1PWM_CHAN        = 2"),
    (REL_LIB, "INVERT dropped", "    ctl = #RP1PWM_CTRL_DEFAULT | #RP1PWM_CTRL_INVERT\n", "    ctl = #RP1PWM_CTRL_DEFAULT\n"),
    (REL_LIB, "clk_pwm1 on aux parent 1", "#RP1PWM_CLK_XOSC     = 2 << 5", "#RP1PWM_CLK_XOSC     = 1 << 5"),
    (REL_LIB, "SET_UPDATE on the wrong bit", "#RP1PWM_SET_UPDATE  = $80000000", "#RP1PWM_SET_UPDATE  = $40000000"),
    (REL_LIB, "a 54 MHz PWM clock assumed", "#RP1PWM_CLK_HZ       = 50000000", "#RP1PWM_CLK_HZ       = 54000000"),
    (REL_LIB, "duty truncated instead of rounded", "(range * permille + #RP1PWM_DUTY_MAX / 2)", "(range * permille)"),
    (REL_LIB, "tach read from GPIO28", "#RP1PWM_TACH_GPIO  = 29", "#RP1PWM_TACH_GPIO  = 28"),
    (REL_LIB, "tach pad left able to drive", "  Rp1PinOutputDisable(#RP1PWM_TACH_GPIO, 1)\n", "\n"),
    (REL_LIB, "tach pad disabled before the mode (the mode re-enables it)",
     "  Rp1PinInput(#RP1PWM_TACH_GPIO)\n  Rp1PinOutputDisable(#RP1PWM_TACH_GPIO, 1)\n",
     "  Rp1PinOutputDisable(#RP1PWM_TACH_GPIO, 1)\n  Rp1PinInput(#RP1PWM_TACH_GPIO)\n"),
    (REL_LIB, "both tach edges counted", "If lv = 1 And rp1tach_last = 0", "If lv <> rp1tach_last"),
    (REL_LIB, "coarse guard disarmed", "If rp1tach_maxGap > #RP1_TACH_GAP_US", "If rp1tach_maxGap > #RP1_TACH_GAP_US * 100"),
    (REL_LIB, "one pulse per revolution", "#RP1_TACH_PPR       = 2", "#RP1_TACH_PPR       = 1"),
    (REL_LIB, "fan pad pulled up", "Rp1PinPull(#RP1PWM_FAN_GPIO, #RP1_PULL_DOWN)", "Rp1PinPull(#RP1PWM_FAN_GPIO, #RP1_PULL_UP)"),
    (REL_LIB, "fan pin left on FUNCSEL 5", "#RP1PWM_FAN_FSEL   = 0", "#RP1PWM_FAN_FSEL   = 5"),
    (REL_LIB, "End stops the fan", "PokeL(rp1pwm_base + $20 + rp1pwm_coff, rp1pwm_range)", "PokeL(rp1pwm_base + $20 + rp1pwm_coff, 0)"),
    (REL_HOST, "a 25 kHz default instead of the DTB period", "#PI5_FAN_HZ  = 24058", "#PI5_FAN_HZ  = 25000"),
    (REL_AVS, "the Pi 4 line on a Pi 5", "#AVS_TEMP_SLOPE  = -550", "#AVS_TEMP_SLOPE  = -487"),
    (REL_HOST, "the firmware reported as the register",
     "    Case #THERM_SRC_MAILBOX\n      ProcedureReturn #HW_TEMP_SRC_FIRMWARE",
     "    Case #THERM_SRC_MAILBOX\n      ProcedureReturn #HW_TEMP_SRC_REGISTER"),
    (REL_HWMOD, "the Pi 4 AVS address on a Pi 5", "#HWDEV_AVS_MONITOR = $107D542000", "#HWDEV_AVS_MONITOR = $FD5D2000"),
    (REL_LIB, "rpm word read at CHAN2_RANGE ($38)", "#RP1PWM_RPM_REG = $3C", "#RP1PWM_RPM_REG = $38"),
    (REL_LIB, "rpm word read from rp1_pwm0", "  ProcedureReturn PeekN(#RP1PWM_BASE + #RP1PWM_RPM_REG) & $FFFFFFFF",
     "  ProcedureReturn PeekN(#RP1PWM_BASE - $4000 + #RP1PWM_RPM_REG) & $FFFFFFFF"),
    (REL_LIB, "rpm word scaled", "  ProcedureReturn PeekN(#RP1PWM_BASE + #RP1PWM_RPM_REG) & $FFFFFFFF",
     "  ProcedureReturn (PeekN(#RP1PWM_BASE + #RP1PWM_RPM_REG) & $FFFFFFFF) * 2"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()
    if not args.compiler:
        raise SystemExit("Name the compiler with --compiler or PMF_COMPILER.")
    COMPILER["path"] = str(pathlib.Path(resolve_compiler(args.compiler)).resolve())
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-fan5-"))
    try:
        fails: list[str] = []
        n = check(fails, top / "gate")
        if fails:
            print("a64_fan_pi5_check: FAIL - %d of %d checks" % (len(fails), n))
            for m in fails:
                print("   " + m)
            return 1
        print("a64_fan_pi5_check: PASS - %d checks (desk only; silicon owed)" % n)
        if not args.mutate:
            return 0
        survived = 0
        for i, (rel, why, old, new) in enumerate(MUTATIONS):
            text = read(ROOT / rel)
            if text.count(old) != 1:
                print("  %2d  ERROR    %s: the text to mutate is not in %s exactly once" % (i, why, rel))
                survived += 1
                continue
            OVERRIDE.clear()
            OVERRIDE[rel] = text.replace(old, new)
            mf: list[str] = []
            try:
                check(mf, top / ("mut%d" % i))
                verdict = "KILLED" if mf else "SURVIVED"
                detail = mf[0] if mf else ""
            except SystemExit as e:
                verdict, detail = "KILLED", str(e).splitlines()[0]
            OVERRIDE.clear()
            if verdict == "SURVIVED":
                survived += 1
            print("  %2d  %-8s %s  [%s]" % (i, verdict, why, detail[:110]))
        print("mutations: %d killed, %d survived" % (len(MUTATIONS) - survived, survived))
        return 1 if survived else 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
