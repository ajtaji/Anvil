#!/usr/bin/env python3
"""Executable gate for the Pi 4 fan stack: PWM, the SoC temperature, the curve.

WHAT MAKES THIS A GATE AND NOT A MIRROR

  Nothing that matters here is transcribed from the libraries under test.
  Every hardware number comes from a PUBLISHED SOURCE - the Raspberry Pi
  device trees, the downstream kernel's own PWM, thermal and clock drivers,
  and the BCM2711 peripherals manual - pinned below with the file and line
  it was read from, and the model built from those numbers is what the
  payload executes against.  So a wrong offset in pwm.pi4 does not become a
  wrong offset in the model; it becomes an unmodelled MMIO access at an
  address the gate names.

  THE SOURCES ARE CITED, NOT COPIED.  They are third-party code and are not
  part of this tree.  The derivations the gate used to run over the files
  (the soc range translation, the pin table from pinctrl node names and
  bodies, the macros' strides) still run - over the pinned rows - so a
  pinned row that disagrees with another pinned row still fails by name.

  The arithmetic is checked twice over: once as PROPERTIES that hold
  whatever the implementation is (25 kHz must come out exactly; the duty
  rails must be exact; the ramp must be monotonic; the two hysteresis
  edges must be at the two temperatures the setting names), and once
  against an independent restatement of the documented rule.

THE TEMPERATURE REGISTER IS A DRIVER MODULE ON ANVIL MAIN

  RaspberryPi4/Lib/thermal.pi4 no longer reads the AVS monitor itself.  The
  register, its validity bits and its conversion moved whole into
  RaspberryPi4/Modules/thermal_avs.pi4 (THERMAL.MOD), which publishes one
  function into the thermal seam; thermal.pi4 reads that seam, binds it on
  its first good read, and falls back to the firmware when nothing fills it.
  The block's processor address moved to the board, as the device handle in
  RaspberryPi4/Board/hw_mod.pi4.

  So the payload (RaspberryPi4/Examples/Diagnostics/pi4FanSelfTest.pi4) is
  built here with the driver's OWN SOURCE linked in - its four module
  declaration lines removed, nothing else touched, because a `Module`
  declaration turns any build that includes it into a module build - and
  the handle hw_mod.pi4 declares.  Section B performs the loader's steps in
  the loader's order (allow, open the fill window, ModuleInit through a
  service table whose fill slot is ModSeamFill, close) before reading.  One
  further run builds the diagnostic exactly as committed, with no driver,
  and requires the firmware fallback.

WHAT IS ASSERTED

  * every register write the library makes lands at an address derived
    from a published source, and no other MMIO address is touched
  * a write to the clock manager WITHOUT the password is a hard failure,
    not a discarded write - the hardware would discard it silently
  * the clock generator is stopped, waited for, reprogrammed and only
    then re-enabled, in that order, with the source and the enable in
    SEPARATE writes as Table 99 requires
  * 25 kHz on GPIO 18 programs divisor 1, range 2160 and ALT5, byte for
    byte, and the duty at 0, 50 and 100 percent is 0, 1080 and 2160
  * the AVS conversion matches -487*code + 410040 over all 1024 codes,
    both validity bits are required, and a bigger code is a colder part
  * the driver probes, initialises and publishes exactly one function, and
    the consumer binds the seam only after a good reading
  * with the register invalid the library falls back to the firmware and
    SAYS it fell back; with no driver at all it does the same
  * the curve's edges, its hysteresis, its spin-up kick and its
    no-thermometer failsafe, as a scripted walk with the clock passed in
  * the refusals, each by its own code, touching no register
  * the software channel's toggle cadence, sample by sample, and its
    stall rule
  * the operator reads Fahrenheit: one conversion, in the seam

Run:            python tools/a64/a64_fan_check.py --compiler <PureMetalForge.exe>
Mutation sweep: python tools/a64/a64_fan_check.py --compiler <...> --mutate [--jobs N]
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
ROOT = pathlib.Path(__file__).resolve().parents[2]

LIB = ROOT / "RaspberryPi4" / "Lib"
CORE = ROOT / "Anvil" / "Core"
HAL = ROOT / "Anvil" / "Hal"
BOARD = ROOT / "RaspberryPi4" / "Board"
MODULES = ROOT / "RaspberryPi4" / "Modules"
DIAG = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics"
PROBE = DIAG / "pi4FanSelfTest.pi4"

sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols            # noqa: E402
import a64_mutate_pool as pool                        # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD = 0x400000
LOADER_SP = 0x3000000
LOADER_LR = 0xDEADBEE0
UART_DR = 0xFE201000
UART_FR = 0xFE201018
CNTFRQ = 54_000_000

# The mailbox, from bcm283x.dtsi's mailbox node through the same soc
# ranges.  Only what one property message needs.
MBX_READ = 0xFE00B880
MBX_STATUS0 = 0xFE00B898
MBX_WRITE = 0xFE00B8A0
MBX_STATUS1 = 0xFE00B8B8
MBX_EMPTY = 0x40000000
MBX_CHANNEL = 8
BUS_OFFSET = 0xC0000000

# What the modelled firmware answers.  Deliberately NOT the same value the
# modelled register converts to: the fallback test has to be able to tell
# which one was used.
FW_TEMP_MILLI = 61234
FW_TEMP_MAX_MILLI = 85000

TAG_TEMPERATURE = 0x00030006
TAG_MAX_TEMPERATURE = 0x0003000A

COMPILER = {"path": None}


def die(msg: str) -> "None":
    raise SystemExit("a64_fan_check: " + msg)


def read(p: pathlib.Path) -> str:
    if not p.exists():
        die("the file %s is missing, so this gate cannot run." % p)
    return p.read_text(errors="replace")


# ======================================================================
#  THE PUBLISHED FACTS, PINNED WITH THEIR CITATIONS
#
#  DT   raspberrypi/linux, branch rpi-6.12.y,
#       arch/arm/boot/dts/broadcom/bcm2711.dtsi and bcm283x.dtsi
#  THM  raspberrypi/linux rpi-6.12.y, drivers/thermal/broadcom/bcm2711_thermal.c
#  PWM  raspberrypi/linux rpi-6.12.y, drivers/pwm/pwm-bcm2835.c
#  CLK  raspberrypi/linux rpi-6.12.y, drivers/clk/bcm/clk-bcm2835.c
#  MAN  Raspberry Pi Ltd, "BCM2711 ARM Peripherals" (bcm2711-peripherals.pdf),
#       line numbers are of its plain-text extraction
#
#  Each value is written as the source spells it, so a reader can hold the
#  row against the line.  Nothing here is read out of the files under test.
# ======================================================================
PINNED = {
    # DT bcm2711.dtsi:41-43 - the soc node's three ranges, <bus hi arm size>.
    "soc_ranges": [(0x7E000000, 0xFE000000, 0x01800000),
                   (0x7C000000, 0xFC000000, 0x02000000),
                   (0x40000000, 0xFF800000, 0x00800000)],
    # DT bcm2711.dtsi:618-620 - &clk_osc { clock-frequency = <54000000>; }
    "clk_osc_hz": 54000000,
    # DT bcm2711.dtsi:68-77 - avs-monitor@7d5d2000, reg <0x7d5d2000 0xf00>,
    # with the child compatible "brcm,bcm2711-thermal" at :74.
    "avs_bus": 0x7D5D2000,
    "avs_len": 0xF00,
    "avs_compatible": "brcm,bcm2711-thermal",
    # DT bcm2711.dtsi:626-627 - &cpu_thermal { coefficients = <(-487) 410040>; }
    "coefficients": (-487, 410040),
    # DT bcm283x.dtsi:413 - pwm: pwm@7e20c000; bcm2711.dtsi:275 - pwm1: pwm@7e20c800
    "pwm0_bus": 0x7E20C000,
    "pwm1_bus": 0x7E20C800,
    # DT bcm283x.dtsi:86 - clocks: cprman@7e101000
    "cm_bus": 0x7E101000,
    # DT bcm2711.dtsi:842-905 - the pwm pinctrl nodes, as
    # (node label, pins = "...", function = "...").  The label carries
    # block, channel and pin; the body carries the pin again and the alt.
    "pinctrl": [("pwm0_0_gpio12", "gpio12", "alt0"),
                ("pwm0_0_gpio18", "gpio18", "alt5"),
                ("pwm1_0_gpio40", "gpio40", "alt0"),
                ("pwm0_1_gpio13", "gpio13", "alt0"),
                ("pwm0_1_gpio19", "gpio19", "alt5"),
                ("pwm1_1_gpio41", "gpio41", "alt0"),
                ("pwm0_1_gpio45", "gpio45", "alt0"),
                ("pwm0_0_gpio52", "gpio52", "alt1"),
                ("pwm0_1_gpio53", "gpio53", "alt1")],
    # THM bcm2711_thermal.c:25-27
    "AVS_RO_TEMP_STATUS": 0x200,
    "AVS_RO_TEMP_STATUS_VALID_MSK_bits": (16, 10),      # (BIT(16) | BIT(10))
    "AVS_RO_TEMP_STATUS_DATA_MSK_genmask": (9, 0),      # GENMASK(9, 0)
    # PWM pwm-bcm2835.c:14-24
    "PWM_CONTROL": 0x000,
    "PWM_CONTROL_SHIFT_mul": 8,                         # ((x) * 8)
    "PWM_MODE": 0x80,
    "PWM_ENABLE_shift": (1, 0),                         # (1 << 0)
    "PERIOD": (0x10, 0x10),                             # (((x) * 0x10) + 0x10)
    "DUTY": (0x10, 0x14),                               # (((x) * 0x10) + 0x14)
    "PERIOD_MIN": 0x2,
    # CLK clk-bcm2835.c:41, 45, 86, 87, 124, 126, 128, 135
    "CM_PASSWORD": 0x5A000000,
    "CM_DIV_FRAC_BITS": 12,
    "CM_PWMCTL": 0x0A0,
    "CM_PWMDIV": 0x0A4,
    "CM_ENABLE_bit": 4,
    "CM_GATE_BIT": 6,
    "CM_BUSY_bit": 7,
    "CM_SRC_OSC": 1,
    # MAN :8437 "The PWM0 register base address is 0x7e20c000 and the PWM1
    # register base address is 0x7e20c800."
    "man_pwm_bases": (0x7E20C000, 0x7E20C800),
    # MAN :8439-8447 Table 152, PWM Register Map (offset, name)
    "man_table152": [(0x00, "CTL"), (0x04, "STA"), (0x08, "DMAC"),
                     (0x10, "RNG1"), (0x14, "DAT1"), (0x18, "FIF1"),
                     (0x20, "RNG2"), (0x24, "DAT2")],
    # MAN :8601-8613 Table 154, STA register (bit, name)
    "man_table154": [(10, "STA2"), (9, "STA1"), (8, "BERR"), (5, "GAPO2"),
                     (4, "GAPO1"), (3, "RERR1"), (2, "WERR1"), (1, "EMPT1"),
                     (0, "FULL1")],
    # MAN :5401 "The General Purpose clocks register base address is
    # 0x7e101000." and :5414 PASSWD 31:24 "Clock Manager password "5a""
    "man_cm_base": 0x7E101000,
    "man_cm_password_byte": 0x5A,
}


class Facts:
    """Every hardware number this gate uses, derived from PINNED.

    The derivations are the same ones the gate ran when it parsed the
    sources: translate a bus address through the soc ranges, build the pin
    table from the node label and body as two independent halves, and turn
    each macro into offsets.  Where two published sources state one fact,
    both are pinned and they are required to agree.
    """

    def __init__(self) -> None:
        P = PINNED
        self.ranges = [(b, a, s) for b, a, s in P["soc_ranges"]]
        self.osc_hz = P["clk_osc_hz"]
        self.avs_bus, self.avs_len = P["avs_bus"], P["avs_len"]
        self.avs_base = self.translate(self.avs_bus)
        self.temp_status_off = P["AVS_RO_TEMP_STATUS"]
        self.temp_valid_mask = 0
        for b in P["AVS_RO_TEMP_STATUS_VALID_MSK_bits"]:
            self.temp_valid_mask |= 1 << b
        hi, lo = P["AVS_RO_TEMP_STATUS_DATA_MSK_genmask"]
        self.temp_data_mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
        self.slope, self.offset = P["coefficients"]

        self.pwm0_bus, self.pwm1_bus = P["pwm0_bus"], P["pwm1_bus"]
        self.pwm0 = self.translate(self.pwm0_bus)
        self.pwm1 = self.translate(self.pwm1_bus)
        self.cm_bus = P["cm_bus"]
        self.cm = self.translate(self.cm_bus)
        self.cm_pwmctl = P["CM_PWMCTL"]
        self.cm_pwmdiv = P["CM_PWMDIV"]
        self.cm_password = P["CM_PASSWORD"]
        self.cm_enable = 1 << P["CM_ENABLE_bit"]
        self.cm_gate = P["CM_GATE_BIT"]
        self.cm_busy = 1 << P["CM_BUSY_bit"]
        self.cm_src_osc = P["CM_SRC_OSC"]
        self.cm_div_frac_bits = P["CM_DIV_FRAC_BITS"]

        self.pwm_control_off = P["PWM_CONTROL"]
        self.pwm_mode_bit = P["PWM_MODE"]
        n, s = P["PWM_ENABLE_shift"]
        self.pwm_enable_bit = n << s
        self.pwm_period_min = P["PERIOD_MIN"]
        self.pwm_period_stride, self.pwm_period_base = P["PERIOD"]
        self.pwm_duty_stride, self.pwm_duty_base = P["DUTY"]
        self.pwm_ctl_shift = P["PWM_CONTROL_SHIFT_mul"]

        # THE STATUS REGISTER.  The kernel driver never reads it, so it has
        # no macro; this is the one part of the map that comes only from the
        # manual.
        t152 = dict((name, off) for off, name in P["man_table152"])
        if "STA" not in t152:
            die("the pinned Table 152 has no STA row")
        self.pwm_sta_off = t152["STA"]
        self.pwm_sta_bits = dict((name, bit) for bit, name in P["man_table154"])
        for want in ("STA1", "STA2", "BERR", "EMPT1"):
            if want not in self.pwm_sta_bits:
                die("the pinned Table 154 does not name the %s bit" % want)

        self.pinmap = self._pinmap()
        self._corroborate(t152)

    def translate(self, bus: int) -> int:
        for b, arm, size in self.ranges:
            if b <= bus < b + size:
                return arm + (bus - b)
        die("bus address 0x%08x is in none of the soc ranges" % bus)

    def _pinmap(self):
        out = {}
        for label, pins, fn in PINNED["pinctrl"]:
            m = re.match(r"pwm(\d)_(\d)_gpio(\d+)$", label)
            p = re.match(r"gpio(\d+)$", pins)
            f = re.match(r"alt(\d)$", fn)
            if not (m and p and f):
                die("the pinned pinctrl row %r does not parse" % (label,))
            block, chan, pin = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if int(p.group(1)) != pin:
                die("the pinctrl node named gpio%d lists pins %s" % (pin, pins))
            out[pin] = (block, chan, int(f.group(1)))
        if len(out) < 9:
            die("only %d pwm pinctrl rows are pinned" % len(out))
        return out

    def _corroborate(self, t152):
        """Two published sources, one fact: they must agree."""
        P = PINNED
        if (self.pwm0_bus, self.pwm1_bus) != P["man_pwm_bases"]:
            die("the device tree's PWM bases and the manual's disagree")
        if self.cm_bus != P["man_cm_base"]:
            die("the device tree's clock manager base and the manual's disagree")
        if (self.cm_password >> 24) != P["man_cm_password_byte"]:
            die("the clock driver's CM_PASSWORD and the manual's PASSWD disagree")
        # The driver's PERIOD()/DUTY() macros and the manual's RNGi/DATi rows.
        for chan in (0, 1):
            if t152.get("RNG%d" % (chan + 1)) != self.pwm_period_base + chan * self.pwm_period_stride:
                die("PERIOD(%d) and Table 152's RNG%d disagree" % (chan, chan + 1))
            if t152.get("DAT%d" % (chan + 1)) != self.pwm_duty_base + chan * self.pwm_duty_stride:
                die("DUTY(%d) and Table 152's DAT%d disagree" % (chan, chan + 1))
        if t152.get("CTL") != self.pwm_control_off:
            die("PWM_CONTROL and Table 152's CTL disagree")


# ======================================================================
#  THE SOURCES UNDER TEST, AS TEXT
#
#  A mutation sweep substitutes the text of ONE library.  Everything that
#  reads a library reads it through here, so the substitution reaches the
#  build and the policy constants alike, and no tracked file is ever opened
#  for writing.
# ======================================================================
OVERRIDE: dict = {}      # repo-relative posix path -> mutated text

REL_PWM = "RaspberryPi4/Lib/pwm.pi4"
REL_THERMAL = "RaspberryPi4/Lib/thermal.pi4"
REL_FAN = "Anvil/Core/fan.pbi"
REL_AVS = "RaspberryPi4/Modules/thermal_avs.pi4"
REL_HWMOD = "RaspberryPi4/Board/hw_mod.pi4"
REL_RUNTIME = "Anvil/Hal/module_format.pbi"


def source(rel: str) -> str:
    if rel in OVERRIDE:
        return OVERRIDE[rel]
    return read(ROOT / rel)


def const_in(text: str, name: str, where: str) -> int:
    m = re.search(r"^%s\s*=\s*(-?\$?[0-9A-Fa-f]+)" % re.escape(name), text, re.M)
    if not m:
        die("%s no longer defines %s" % (where, name))
    v = m.group(1)
    if v.startswith("$"):
        return int(v[1:], 16)
    if v.startswith("-$"):
        return -int(v[2:], 16)
    return int(v)


def const(rel: str, name: str) -> int:
    return const_in(source(rel), name, rel)


class Policy:
    """The libraries' DESIGN choices - no document to derive them from, so
    read from the files under test.  The useful checks are the PROPERTIES,
    which hold whatever these are."""

    def __init__(self) -> None:
        self.range_target = const(REL_PWM, "#PWM_RANGE_TARGET")
        self.range_min = const(REL_PWM, "#PWM_RANGE_MIN")
        self.range_max = const(REL_PWM, "#PWM_RANGE_MAX")
        self.divi_max = const(REL_PWM, "#CM_DIV_INT_MAX")
        self.duty_max = const(REL_PWM, "#PWM_DUTY_MAX")
        self.soft_hz_min = const(REL_PWM, "#PWM_SOFT_HZ_MIN")
        self.soft_hz_max = const(REL_PWM, "#PWM_SOFT_HZ_MAX")
        self.stall_periods = const(REL_PWM, "#PWM_SOFT_STALL_PERIODS")
        # FAHRENHEIT: the curve is stored, typed and printed in Fahrenheit;
        # the only Celsius below the seam is the sensor path.
        self.low = const(REL_FAN, "#FAN_LOW_F_DEFAULT")
        self.high = const(REL_FAN, "#FAN_HIGH_F_DEFAULT")
        self.hyst = const(REL_FAN, "#FAN_HYST_F_DEFAULT")
        self.min_duty = const(REL_FAN, "#FAN_MIN_DUTY")
        self.kick_duty = const(REL_FAN, "#FAN_KICK_DUTY")
        self.kick_ms = const(REL_FAN, "#FAN_KICK_MS")
        self.failsafe = const(REL_FAN, "#FAN_FAILSAFE_DUTY")
        self.fan_duty_max = const(REL_FAN, "#FAN_DUTY_MAX")


# ======================================================================
#  INDEPENDENT RESTATEMENTS of the documented rules
# ======================================================================
def divisor_for(hz: int, pol: Policy, osc: int) -> int:
    if hz <= 0:
        return 0
    d = osc // (hz * pol.range_target)
    return max(1, min(pol.divi_max, d))


def range_for(hz: int, pol: Policy, osc: int) -> int:
    if hz <= 0:
        return 0
    d = divisor_for(hz, pol, osc)
    r = osc // (d * hz)
    if r < pol.range_min or r > pol.range_max:
        return 0
    return r


def actual_hz(hz: int, pol: Policy, osc: int) -> int:
    r = range_for(hz, pol, osc)
    if r == 0:
        return 0
    return osc // (divisor_for(hz, pol, osc) * r)


def duty_counts(rng: int, permille: int, pol: Policy) -> int:
    if permille <= 0:
        return 0
    if permille >= pol.duty_max:
        return rng
    return (rng * permille + pol.duty_max // 2) // pol.duty_max


def ramp_duty(milli: int, pol: Policy, low=None, high=None) -> int:
    lo = (pol.low if low is None else low) * 1000
    hi = (pol.high if high is None else high) * 1000
    if milli <= lo:
        return pol.min_duty
    if milli >= hi:
        return pol.fan_duty_max
    return pol.min_duty + ((pol.fan_duty_max - pol.min_duty)
                           * (milli - lo)) // (hi - lo)


def whole_c(milli: int) -> int:
    if milli >= 0:
        return (milli + 500) // 1000
    return -((-milli + 500) // 1000)


# ======================================================================
#  THE MODELLED BOARD
# ======================================================================
class Board:
    """A PWM pair, a clock generator, a GPIO bank, a sensor and a firmware.

    Every address it answers is computed from Facts, so the model and the
    library are independent readings of the same documents.  An access to
    anything else stops the run and names the address.
    """

    def __init__(self, cpu, facts: Facts, avs_raw: int,
                 cm_start: int = None) -> None:
        self.cpu = cpu
        self.f = facts
        self.uart = bytearray()
        self.avs_raw = avs_raw
        self.avs_reads = 0
        self.reply = None
        self.steps = 0

        # PWM state, per block.  Reset values: RNG is 0x20 and DAT is 0.
        self.pwm = {facts.pwm0: {"ctl": 0, "rng": [0x20, 0x20],
                                 "dat": [0, 0], "dmac": 0},
                    facts.pwm1: {"ctl": 0, "rng": [0x20, 0x20],
                                 "dat": [0, 0], "dmac": 0}}
        self.pwm_writes: list[tuple[int, int, int]] = []   # base, off, value

        # THE STATUS REGISTER, AND THE ONE THING IN THIS MODEL THAT DOES NOT
        # SIMPLY REMEMBER WHAT WAS WRITTEN TO IT.  Measured on a board: a
        # control byte written to PWM0 while the clock generator was still
        # coming up read back perfectly ($81, MSEN1|PWEN1) and the channel
        # never started - STA read $102, BERR set and STA1 clear, and GPIO 18
        # sat at level 0 through a duty of 100 percent.  So the write lands
        # in `ctl` as on silicon, and starts the channel ONLY if clk_pwm is
        # running at that instant; otherwise BERR rises.
        self.sta = {facts.pwm0: {"berr": 0, "run": [0, 0]},
                    facts.pwm1: {"berr": 0, "run": [0, 0]}}
        self.chan_started: list[tuple[int, int]] = []
        self.chan_refused: list[tuple[int, int]] = []
        # Does the block have a clock right now?  It does from the moment the
        # generator's BUSY rises, and stops having one as soon as a control
        # write leaves no channel in the block enabled.
        self.block_clocked = {facts.pwm0: False, facts.pwm1: False}
        # What each PWM-capable pad showed, in order, with repeats collapsed:
        # 0 solid low, 1 solid high, -1 a real waveform.
        self.pad_trace: dict = {}

        # THE CLOCK GENERATOR STARTS RUNNING, because on a real board the
        # firmware has already been here.
        self.cm_ctl = facts.cm_enable | facts.cm_src_osc | facts.cm_busy
        if cm_start is not None:
            self.cm_ctl = cm_start
        self.cm_div = 0
        self.cm_writes: list[tuple[int, int]] = []
        self.cm_busy_countdown = 0
        # BUSY RISES LATE TOO.  Table 99 calls ENAB a REQUEST and BUSY the
        # answer; three reads, the same number the falling edge uses.
        self.cm_start_countdown = 0
        self.cm_gnd_stuck = bool(self.cm_ctl & facts.cm_busy) and not (self.cm_ctl & 0xF)
        self.cm_no_password: list[tuple[int, int]] = []
        self.cm_wrote_while_busy: list[tuple[int, int]] = []

        self.gpio_base = facts.translate(0x7E200000)
        self.fsel = [0] * 58
        self.fsel_history: dict = {}
        self.level = [0] * 58
        self.set_writes: list[int] = []
        self.clr_writes: list[int] = []

        self.mbx_tags: list[int] = []

    # -- the property mailbox -----------------------------------------
    def mailbox_write(self, msg: int) -> None:
        chan = msg & 0xF
        if chan != MBX_CHANNEL:
            die("the image used mailbox channel %d, not 8" % chan)
        arm = (msg & ~0xF) - BUS_OFFSET
        ld, st = self.cpu.load, self.cpu.store
        total = ld(arm, 4)
        if total < 12 or total % 4 or total > 4096:
            die("property buffer size word is %d" % total)
        if ld(arm + 4, 4) != 0:
            die("the request code word was not STATUS_REQUEST")
        off = 8
        while True:
            tag = ld(arm + off, 4)
            if tag == 0:
                break
            valbuf = ld(arm + off + 4, 4)
            self.mbx_tags.append(tag)
            if tag == TAG_TEMPERATURE:
                st(arm + off + 12, 0, 4)
                st(arm + off + 16, FW_TEMP_MILLI, 4)
            elif tag == TAG_MAX_TEMPERATURE:
                st(arm + off + 12, 0, 4)
                st(arm + off + 16, FW_TEMP_MAX_MILLI, 4)
            else:
                die("the image sent property tag $%08X, which this gate does "
                    "not model - the fan stack should only ever ask for the "
                    "temperature and the maximum" % tag)
            st(arm + off + 8, 0x80000000 | 8, 4)
            off += 12 + valbuf
        st(arm + 4, 0x80000000, 4)
        self.reply = msg

    # -- the channel start ----------------------------------------------
    def _wants(self, base: int, chan: int) -> bool:
        f = self.f
        byte = (self.pwm[base]["ctl"] >> (chan * f.pwm_ctl_shift)) & 0xFF
        return bool(byte & f.pwm_enable_bit)

    def _clock_arrived(self) -> None:
        """BUSY has risen.  Every channel already asking for it starts."""
        for base in self.pwm:
            started = False
            for chan in (0, 1):
                if self._wants(base, chan):
                    if not self.sta[base]["run"][chan]:
                        self.chan_started.append((base, chan))
                    self.sta[base]["run"][chan] = 1
                    started = True
            self.block_clocked[base] = started

    def _apply_ctl(self, base: int, value: int) -> None:
        """A control byte asking for PWEN starts its channel only if the
        block is CLOCKED at that instant, and the block is only clocked while
        at least one channel is enabled."""
        f = self.f
        for chan in (0, 1):
            byte = (value >> (chan * f.pwm_ctl_shift)) & 0xFF
            want = bool(byte & f.pwm_enable_bit)
            if not want:
                self.sta[base]["run"][chan] = 0
                continue
            if self.block_clocked[base]:
                if not self.sta[base]["run"][chan]:
                    self.chan_started.append((base, chan))
                self.sta[base]["run"][chan] = 1
            elif (self.cm_ctl & f.cm_enable) and (self.cm_ctl & f.cm_busy):
                self.sta[base]["berr"] = 1
                self.chan_refused.append((base, chan))
        if not any(self._wants(base, c) for c in (0, 1)):
            self.block_clocked[base] = False

    def _trace_pads(self) -> None:
        for pin in self.f.pinmap:
            lv = self.pad_level(pin)
            tr = self.pad_trace.setdefault(pin, [])
            if not tr or tr[-1] != lv:
                tr.append(lv)

    def pad_level(self, pin: int) -> int:
        f = self.f
        if pin not in f.pinmap:
            return self.level[pin]
        blk, chan, alt = f.pinmap[pin]
        base = f.pwm0 if blk == 0 else f.pwm1
        alt_codes = {0: 4, 1: 5, 2: 6, 3: 7, 4: 3, 5: 2}
        if self.fsel[pin] != alt_codes[alt]:
            return self.level[pin]
        if not self.sta[base]["run"][chan]:
            return 0
        rng = self.pwm[base]["rng"][chan]
        dat = self.pwm[base]["dat"][chan]
        if rng and dat >= rng:
            return 1
        return 0 if dat == 0 else -1

    # -- MMIO ----------------------------------------------------------
    def load(self, addr: int, size: int) -> int:
        f = self.f
        if addr == UART_FR:
            return 0
        if addr == MBX_STATUS1:
            return 0
        if addr == MBX_STATUS0:
            return 0 if self.reply is not None else MBX_EMPTY
        if addr == MBX_READ:
            if self.reply is None:
                die("the image read an empty mailbox")
            r, self.reply = self.reply, None
            return r
        if addr == f.avs_base + f.temp_status_off:
            self.avs_reads += 1
            return self.avs_raw
        if addr == f.cm + f.cm_pwmctl:
            v = self.cm_ctl
            if self.cm_busy_countdown > 0:
                self.cm_busy_countdown -= 1
                if self.cm_busy_countdown == 0:
                    self.cm_ctl &= ~f.cm_busy
            elif self.cm_start_countdown > 0:
                self.cm_start_countdown -= 1
                if self.cm_start_countdown == 0:
                    self.cm_ctl |= f.cm_busy
                    self._clock_arrived()
            return v
        if addr == f.cm + f.cm_pwmdiv:
            return self.cm_div
        for base, st in self.pwm.items():
            if base <= addr < base + 0x28:
                off = addr - base
                if off == 0x00:
                    return st["ctl"]
                if off == f.pwm_sta_off:
                    b = f.pwm_sta_bits
                    v = 1 << b["EMPT1"]
                    if self.sta[base]["berr"]:
                        v |= 1 << b["BERR"]
                    if self.sta[base]["run"][0]:
                        v |= 1 << b["STA1"]
                    if self.sta[base]["run"][1]:
                        v |= 1 << b["STA2"]
                    return v
                if off == 0x08:
                    return st["dmac"]
                if off in (0x10, 0x20):
                    return st["rng"][0 if off == 0x10 else 1]
                if off in (0x14, 0x24):
                    return st["dat"][0 if off == 0x14 else 1]
                die("read of PWM offset $%02X, which is the FIFO or a hole" % off)
        g = self.gpio_base
        if g <= addr < g + 0x100:
            off = addr - g
            if 0x00 <= off <= 0x14:
                reg = off // 4
                v = 0
                for i in range(10):
                    pin = reg * 10 + i
                    if pin < 58:
                        v |= (self.fsel[pin] & 7) << (i * 3)
                return v
            if off in (0x34, 0x38):
                bank = 0 if off == 0x34 else 1
                v = 0
                for i in range(32):
                    pin = bank * 32 + i
                    if pin < 58 and self.level[pin]:
                        v |= 1 << i
                return v
            if 0xE4 <= off <= 0xF0:
                return 0
            die("read of GPIO offset $%02X, which this gate does not model" % off)
        die("unmodelled MMIO read at $%08X" % addr)

    def store(self, addr: int, value: int, size: int) -> None:
        f = self.f
        value &= 0xFFFFFFFF
        if addr == UART_DR:
            self.uart.append(value & 0xFF)
            return
        if addr == MBX_WRITE:
            self.mailbox_write(value)
            return
        if addr == f.cm + f.cm_pwmctl or addr == f.cm + f.cm_pwmdiv:
            off = addr - f.cm
            # THE PASSWORD.  The hardware discards a write without it, in
            # silence; here it is recorded as a defect instead.
            if (value & 0xFF000000) != f.cm_password:
                self.cm_no_password.append((off, value))
                return
            if (self.cm_ctl & f.cm_busy) and off == f.cm_pwmdiv:
                self.cm_wrote_while_busy.append((off, value))
            body = value & 0x00FFFFFF
            self.cm_writes.append((off, body))
            if off == f.cm_pwmdiv:
                self.cm_div = body
                return
            was_on = bool(self.cm_ctl & f.cm_enable)
            self.cm_ctl = body | (self.cm_ctl & f.cm_busy)
            self.cm_busy_countdown = 0
            self.cm_start_countdown = 0
            if was_on and not (body & f.cm_enable):
                self.cm_busy_countdown = 3
            if not (body & f.cm_enable) and not (body & 0xF):
                # A GENERATOR PARKED ON GND DOES NOT STOP.  Measured on a
                # board: CM_PWMCTL written $5A000000 read back $00000080 -
                # BUSY - until a real source was named.
                self.cm_ctl |= f.cm_busy
                self.cm_busy_countdown = 0
                self.cm_gnd_stuck = True
            elif self.cm_gnd_stuck and (body & 0xF):
                self.cm_ctl &= ~f.cm_busy
                self.cm_gnd_stuck = False
            if body & f.cm_enable:
                self.cm_start_countdown = 3
            return
        for base, st in self.pwm.items():
            if base <= addr < base + 0x28:
                off = addr - base
                self.pwm_writes.append((base, off, value))
                if off == 0x00:
                    st["ctl"] = value
                    self._apply_ctl(base, value)
                elif off == f.pwm_sta_off:
                    # W1C.  STAi is read-only, which is why a driver cannot
                    # fake the one bit that matters.
                    if value & (1 << f.pwm_sta_bits["BERR"]):
                        self.sta[base]["berr"] = 0
                elif off == 0x08:
                    st["dmac"] = value
                elif off in (0x10, 0x20):
                    st["rng"][0 if off == 0x10 else 1] = value
                elif off in (0x14, 0x24):
                    st["dat"][0 if off == 0x14 else 1] = value
                elif off == 0x18:
                    die("the library wrote the PWM FIFO, which it says it never uses")
                else:
                    die("write to PWM offset $%02X, which is a hole" % off)
                self._trace_pads()
                return
        g = self.gpio_base
        if g <= addr < g + 0x100:
            off = addr - g
            if 0x00 <= off <= 0x14:
                reg = off // 4
                for i in range(10):
                    pin = reg * 10 + i
                    if pin < 58:
                        code = (value >> (i * 3)) & 7
                        if code != self.fsel[pin]:
                            self.fsel_history.setdefault(pin, []).append(code)
                        self.fsel[pin] = code
                self._trace_pads()
                return
            if off in (0x1C, 0x20):
                bank = 0 if off == 0x1C else 1
                for i in range(32):
                    if value & (1 << i):
                        pin = bank * 32 + i
                        if pin < 58:
                            self.level[pin] = 1
                            self.set_writes.append(pin)
                return
            if off in (0x28, 0x2C):
                bank = 0 if off == 0x28 else 1
                for i in range(32):
                    if value & (1 << i):
                        pin = bank * 32 + i
                        if pin < 58:
                            self.level[pin] = 0
                            self.clr_writes.append(pin)
                return
            if 0xE4 <= off <= 0xF0:
                return
            die("write to GPIO offset $%02X, which this gate does not model" % off)
        die("unmodelled MMIO write at $%08X" % addr)


def run(img: pathlib.Path, facts: Facts, avs_raw: int,
        ticks_per_step: int = 54, limit: int = 400_000_000,
        cm_start: int = None):
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    board = Board(cpu, facts, avs_raw, cm_start=cm_start)
    mem = cpu.memory
    ticks = [0]

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= 0xFC000000:
            return board.load(addr, size)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFC000000:
            board.store(addr, value, size)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    def step() -> None:
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # mrs Xt, cntfrq_el0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # mrs Xt, cntpct_el0
            cpu.x[ins & 31] = ticks[0]
            cpu.pc += 4
            return
        plain_step()

    n = 0
    while cpu.pc != LOADER_LR:
        n += 1
        if n > limit:
            die("the probe never returned after %d steps" % limit)
        ticks[0] += ticks_per_step
        step()
    board.steps = n
    return board, bytes(board.uart), n


# ======================================================================
#  BUILDING
# ======================================================================
DRIVER_MARKER = "; FAN-AVS-DRIVER-INCLUDE"
MODULE_DECL = re.compile(r"^(Module |ModuleABI |ModuleMatch |Seam )")


def board_device_handle() -> int:
    """The AVS block's handle, as RaspberryPi4/Board/hw_mod.pi4 declares it."""
    return const(REL_HWMOD, "#HWDEV_AVS_MONITOR")


def linked_driver(workdir: pathlib.Path) -> pathlib.Path:
    """The driver's own source with its module declaration lines removed."""
    text = source(REL_AVS)
    lines = text.split("\n")
    kept = [ln for ln in lines if not MODULE_DECL.match(ln)]
    if len(lines) - len(kept) != 4:
        die("%s no longer carries exactly four module declaration lines "
            "(Module, ModuleABI, ModuleMatch, Seam); %d were found, so the "
            "linked copy would not be the driver with only those removed"
            % (REL_AVS, len(lines) - len(kept)))
    dst = workdir / "thermal_avs_linked.pbi"
    dst.write_text("\n".join(kept))
    return dst


def probe_source(pin: int, workdir: pathlib.Path, with_driver: bool) -> str:
    text = read(PROBE)
    # WHOLE LINES ONLY. The diagnostic's own comments quote these settings,
    # and a substitution that also rewrote a comment would be harmless - but
    # a count that included one would hide a second, real definition.
    def setting(src, line, new):
        pat = re.compile(r"^%s[ \t]*$" % re.escape(line), re.M)
        if len(pat.findall(src)) != 1:
            die("pi4FanSelfTest.pi4 no longer has exactly one line reading %r "
                "for this gate to set" % line)
        return pat.sub(new, src)

    text = setting(text, "#FAN_TEST_PIN = -1",
                   "#FAN_TEST_PIN = %d" % pin if pin >= 0 else "#FAN_TEST_PIN = -1")
    if with_driver:
        text = setting(text, "#FAN_AVS_DRIVER = 0", "#FAN_AVS_DRIVER = 1")
        text = setting(text, "#FAN_AVS_DEVICE = 0",
                       "#FAN_AVS_DEVICE = $%08X" % board_device_handle())
        text = setting(text, DRIVER_MARKER, 'XIncludeFile "%s"'
                       % linked_driver(workdir).resolve().as_posix())
    else:
        for line in ("#FAN_AVS_DRIVER = 0", "#FAN_AVS_DEVICE = 0", DRIVER_MARKER):
            text = setting(text, line, line)
    # A mutated library replaces its include with the mutated copy.
    for rel, body in OVERRIDE.items():
        if rel in (REL_AVS, REL_HWMOD):
            continue            # reached through linked_driver / the handle
        marker = 'XIncludeFile "%s"' % rel
        if text.count(marker) != 1:
            die("the probe does not include %s exactly once" % rel)
        copy = workdir / pathlib.Path(rel).name
        copy.write_text(body)
        text = text.replace(marker, 'XIncludeFile "%s"' % copy.resolve().as_posix())
    return text


def build(src: pathlib.Path, out: pathlib.Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [COMPILER["path"], "--compile", str(src), "-t", "pi4",
         "--load-addr", hex(LOAD), "--stack-addr", hex(LOADER_SP),
         "--entry-returns", "-o", str(out)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.exists():
        die("the probe would not build:\n" + r.stdout[-3000:] + r.stderr[-1000:])


def probe_image(pin: int, workdir: pathlib.Path, with_driver: bool = True) -> pathlib.Path:
    tag = "%d_%s" % (pin, "drv" if with_driver else "nodrv")
    d = workdir / ("probe_" + tag)
    d.mkdir(parents=True, exist_ok=True)
    src = d / ("fanprobe_%s.pi4" % tag)
    src.write_text(probe_source(pin, d, with_driver))
    img = d / ("fanprobe_%s.img" % tag)
    build(src, img)
    return img


# ======================================================================
#  READING THE TRANSCRIPT
# ======================================================================
class Said:
    def __init__(self, text: str) -> None:
        self.text = text
        self.rows: dict[str, list[list[int]]] = {}
        for line in text.splitlines():
            # THE LABEL MAY CONTAIN DIGITS - "E pin4", "F duty2160" - so the
            # label is non-greedy and the values are what is left.
            m = re.match(r"^([A-Z][A-Za-z0-9 ]*?)((?:\s+-?\d+)+)\s*$", line)
            if not m:
                continue
            key = m.group(1).strip()
            vals = [int(v) for v in m.group(2).split()]
            self.rows.setdefault(key, []).append(vals)

    def one(self, key: str):
        v = self.rows.get(key)
        if not v or len(v[0]) != 1:
            return None
        return v[0][0]

    def pair(self, key: str, first: int):
        for row in self.rows.get(key, []):
            if len(row) == 2 and row[0] == first:
                return row[1]
        return None

    def all(self, key: str):
        return self.rows.get(key, [])


# ======================================================================
def main_check(fails: list, facts: Facts, pol: Policy,
               work: pathlib.Path) -> int:
    checked = [0]

    def expect(cond, what):
        checked[0] += 1
        if not cond:
            fails.append(what)

    osc = facts.osc_hz
    slope, offset = facts.slope, facts.offset
    mod_ok = const(REL_RUNTIME, "#MOD_OK")
    therm_none = const(REL_THERMAL, "#THERM_NONE")

    print("derived: oscillator %d Hz, PWM0 $%08X, PWM1 $%08X, CM $%08X"
          % (osc, facts.pwm0, facts.pwm1, facts.cm))
    print("derived: AVS $%08X + $%03X, valid mask $%05X, %d*code + %d"
          % (facts.avs_base, facts.temp_status_off, facts.temp_valid_mask,
             slope, offset))
    print("derived: CM_PWMCTL $%03X  CM_PWMDIV $%03X  password $%08X"
          % (facts.cm_pwmctl, facts.cm_pwmdiv, facts.cm_password))
    print("derived: pins " + ", ".join(
        "%d=b%dc%d/alt%d" % (p, b, c, a)
        for p, (b, c, a) in sorted(facts.pinmap.items())))
    print()

    # -- the premise ----------------------------------------------------
    expect(osc == 54_000_000,
           "the device tree says the BCM2711 oscillator is %d Hz, and this "
           "gate's whole frequency envelope assumes 54 MHz" % osc)
    expect(slope < 0,
           "the thermal slope is %d, which is not negative - every direction "
           "check below is upside down" % slope)
    # THE HANDLE THE BOARD HANDS THE DRIVER must be the device tree's own
    # translation of avs-monitor@7d5d2000 - through the SECOND soc range.
    expect(board_device_handle() == facts.avs_base,
           "RaspberryPi4/Board/hw_mod.pi4 hands the thermal driver $%08X, and "
           "the device tree's avs-monitor node translates to $%08X"
           % (board_device_handle(), facts.avs_base))
    avs_text = source(REL_AVS)
    expect(('ModuleMatch "%s"' % PINNED["avs_compatible"]) in avs_text,
           "the thermal driver no longer matches %r, the compatible the device "
           "tree gives the block" % PINNED["avs_compatible"])

    # ==================================================================
    #  RUN 1 - a valid sensor reading, no pin driven, the driver linked
    # ==================================================================
    code = 739
    raw_valid = facts.temp_valid_mask | code
    img = probe_image(-1, work)
    board, uart, steps = run(img, facts, raw_valid)
    s = Said(uart.decode("utf-8", "replace"))
    print("run 1 (register valid, driver linked, no pin): %d instructions, %d bytes"
          % (steps, len(uart)))

    expect(s.one("PIN") == -1, "the base probe was built with a pin set")

    # -- A, the conversion ---------------------------------------------
    for c in (0, 1, 512, 698, 739, 842, 843, 1023):
        want = slope * c + offset
        expect(s.pair("A code", c) == want,
               "code %d converts to %r; %d*%d + %d is %d"
               % (c, s.pair("A code", c), slope, c, offset, want))
    fold = 0
    for c in range(1024):
        fold = (fold * 131 + (slope * c + offset + 1000000)) % 1000000007
    expect(s.one("A fold") == fold,
           "the conversion fold over all 1024 codes is %r; the device tree's "
           "own coefficients give %d" % (s.one("A fold"), fold))

    vm = facts.temp_valid_mask
    for word, want in ((vm, 1), (vm & ~0x400, 0), (vm & ~0x10000, 0),
                       (0, 0), (0xFFFFFFFF, 1)):
        got = s.pair("A validof", word)
        expect(got == want,
               "validity of $%08X read as %r and should be %d - BOTH of the "
               "driver's two bits are required" % (word, got, want))

    for milli in (52341, 52500, 52499, 0, 499, 500, -499, -500, -1600):
        expect(s.pair("A whole", milli) == whole_c(milli),
               "%d millidegrees rounds to %r whole degrees, not %d"
               % (milli, s.pair("A whole", milli), whole_c(milli)))
    expect(s.one("A whole none") == therm_none,
           "the no-reading sentinel must pass through the rounding unchanged, "
           "and it came back %r" % s.one("A whole none"))

    # -- B, the driver and the two sources -----------------------------
    expect(s.one("B valid") == 1, "a valid modelled reading read as invalid")
    expect(s.one("B probe") == 1,
           "the driver's probe declined a block answering a valid reading")
    expect(s.one("B allow") == mod_ok, "the registry refused to allow the thermal seam")
    expect(s.one("B init") == mod_ok,
           "the driver's init answered %r; it must publish and answer 0" % s.one("B init"))
    expect(s.one("B fills") == 1,
           "the driver's init published %r functions; the thermal seam is one"
           % s.one("B fills"))
    expect(s.one("B regmilli") == slope * code + offset,
           "the seam path gave %r for code %d" % (s.one("B regmilli"), code))
    expect(s.one("B milli") == slope * code + offset,
           "with a valid register the library must not use the firmware")
    expect(s.one("B source") == 1,
           "the source should be the direct path (1) and was %r" % s.one("B source"))
    expect(s.one("B regfails") == 0, "a valid register read was counted as a failure")
    expect(s.one("B bound") == 1,
           "after a good reading the consumer must hold exactly one binding on "
           "the thermal seam, or an unload could pull the driver out from under "
           "it; it holds %r" % s.one("B bound"))
    expect(s.one("B mbxmilli") == FW_TEMP_MILLI,
           "the modelled firmware answered %r, not %d" % (s.one("B mbxmilli"), FW_TEMP_MILLI))
    expect(s.one("B maxmilli") == FW_TEMP_MAX_MILLI,
           "the throttle temperature is mailbox-only and came back %r" % s.one("B maxmilli"))
    expect(TAG_TEMPERATURE in board.mbx_tags,
           "the probe never asked the firmware for a temperature")
    expect(TAG_MAX_TEMPERATURE in board.mbx_tags,
           "the probe never asked the firmware for the maximum")
    expect(board.avs_reads >= 3,
           "the AVS status register was read %d times; the raw read, the probe "
           "and the seam reads are at least three" % board.avs_reads)

    # -- C, the curve ---------------------------------------------------
    expect(s.pair("C low", pol.low) == pol.high,
           "the default curve is not %d..%d" % (pol.low, pol.high))
    expect(s.one("C hyst") == pol.hyst, "the default hysteresis moved")
    for milli in (0, 112999, 113000, 113001, 122000, 135500, 157999,
                  158000, 158001, 248000):
        want = ramp_duty(milli, pol)
        expect(s.pair("C ramp", milli) == want,
               "the ramp at %d milli-Fahrenheit is %r, and a straight line "
               "from %d at %d F to %d at %d F gives %d"
               % (milli, s.pair("C ramp", milli), pol.min_duty, pol.low,
                  pol.fan_duty_max, pol.high, want))
    expect(s.pair("C ramp", pol.low * 1000) == pol.min_duty,
           "at the low point exactly, the ramp must be the minimum duty")
    expect(s.pair("C ramp", pol.high * 1000) == pol.fan_duty_max,
           "at the high point exactly, the ramp must be full")
    fold = 0
    for t in range(104000, 167001, 100):
        fold = (fold * 131 + ramp_duty(t, pol)) % 1000000007
    expect(s.one("C fold") == fold,
           "the ramp fold over 104..167 F is %r; an independent straight line "
           "gives %d" % (s.one("C fold"), fold))
    expect(s.one("C setnarrow") == 0, "a one-degree span must be accepted")
    expect(s.pair("C narrow", 30000) == pol.min_duty, "the narrow curve's low end")
    expect(s.pair("C narrow", 31000) == pol.fan_duty_max, "the narrow curve's high end")
    expect(s.pair("C narrow", 30500) == ramp_duty(30500, pol, 30, 31),
           "the narrow curve's midpoint is %r, not %d"
           % (s.pair("C narrow", 30500), ramp_duty(30500, pol, 30, 31)))

    # -- D, hysteresis and the kick -------------------------------------
    steps_d = s.all("D step")
    expect(len(steps_d) == 14, "the hysteresis walk printed %d steps, not 14" % len(steps_d))
    lo_m = pol.low * 1000
    hy_m = pol.hyst * 1000
    running = 0
    kick_from = None
    for milli, ms, duty, run_flag in steps_d:
        if running:
            want_run = 0 if milli < lo_m - hy_m else 1
        else:
            want_run = 1 if milli >= lo_m else 0
        started = want_run and not running
        if started:
            kick_from = ms
        if not want_run:
            want_duty = 0
            kick_from = None
        else:
            want_duty = ramp_duty(milli, pol)
            if kick_from is not None and ms - kick_from < pol.kick_ms:
                want_duty = max(want_duty, pol.kick_duty)
            elif kick_from is not None:
                kick_from = None
        expect(run_flag == want_run,
               "at %d milli-Fahrenheit and %d ms the policy said running=%d; "
               "the start edge is %d and the stop edge is strictly below %d"
               % (milli, ms, run_flag, lo_m, lo_m - hy_m))
        expect(duty == want_duty,
               "at %d milli-Fahrenheit and %d ms the duty was %d, and the curve "
               "with its %d ms kick gives %d" % (milli, ms, duty, pol.kick_ms, want_duty))
        running = want_run
    if len(steps_d) == 14:
        expect(steps_d[1][3] == 0 and steps_d[2][3] == 1,
               "the fan must start AT the low point (%d) and not above it" % lo_m)
        expect(steps_d[8][3] == 1 and steps_d[9][3] == 0,
               "the fan must keep running at exactly low-minus-hysteresis (%d) "
               "and stop one thousandth of a degree below it" % (lo_m - hy_m))
    expect(s.pair("D starts", 2) == 1,
           "the walk should be two starts and one stop, and it was %r"
           % s.all("D starts"))
    expect(s.one("D blind") == pol.failsafe,
           "WITH NO TEMPERATURE THE FAN MUST RUN. The policy answered %r" % s.one("D blind"))
    expect(s.one("D blindticks") == 1, "the blind decision was not counted")
    expect(s.one("D off") == 0, "fan off must be off at 194 F")
    expect(s.one("D offblind") == 0,
           "OFF OUTRANKS THE FAILSAFE, and the policy answered %r" % s.one("D offblind"))
    expect(s.one("D on") == pol.fan_duty_max, "fan on must be full at 32 F")
    expect(s.one("D fixed") == 370, "a held duty must be held at 194 F")
    expect(s.one("D reauto") == pol.kick_duty,
           "a mode change back to auto is a fresh start and must kick; it "
           "answered %r" % s.one("D reauto"))

    # -- E, the refusals -------------------------------------------------
    ERR_PIN = const(REL_PWM, "#PWM_ERR_PIN")
    ERR_HZ = const(REL_PWM, "#PWM_ERR_HZ")
    ERR_STATE = const(REL_PWM, "#PWM_ERR_STATE")
    E_RANGE = const(REL_FAN, "#FAN_ERR_RANGE")
    E_SPAN = const(REL_FAN, "#FAN_ERR_SPAN")
    E_HYST = const(REL_FAN, "#FAN_ERR_HYST")
    E_DUTY = const(REL_FAN, "#FAN_ERR_DUTY")
    E_MODE = const(REL_FAN, "#FAN_ERR_MODE")
    for key, want in (("E dutynostate", ERR_STATE), ("E endnostate", ERR_STATE),
                      ("E softdutynostate", ERR_STATE),
                      ("E pin4", ERR_PIN), ("E pin17", ERR_PIN),
                      ("E pin2", ERR_PIN), ("E pinneg", ERR_PIN),
                      ("E pin99", ERR_PIN),
                      ("E hz0", ERR_HZ), ("E hzneg", ERR_HZ),
                      ("E hztoohigh", ERR_HZ), ("E hzway", ERR_HZ),
                      ("E softhz0", ERR_HZ), ("E softhzhigh", ERR_HZ),
                      ("E softpin", ERR_PIN),
                      ("E curveinvert", E_SPAN), ("E curveequal", E_SPAN),
                      ("E curvelow", E_RANGE), ("E curvehigh", E_RANGE),
                      ("E hystbig", E_HYST), ("E hystneg", E_HYST),
                      ("E hystzero", 0),
                      ("E modebad", E_MODE), ("E modeneg", E_MODE),
                      ("E fixedbig", E_DUTY), ("E fixedneg", E_DUTY)):
        expect(s.one(key) == want,
               "%s answered %r and the contract is %d" % (key, s.one(key), want))
    expect(not board.pwm_writes,
           "the refusal section wrote %d PWM registers; a refused request must "
           "change nothing" % len(board.pwm_writes))
    expect(not board.cm_writes,
           "the refusal section wrote the clock manager %d times; a refused "
           "frequency must not reprogram clk_pwm" % len(board.cm_writes))

    # -- F, the divisor arithmetic ---------------------------------------
    for row in s.all("F hz"):
        hz, divi, rng, act = row
        expect(divi == divisor_for(hz, pol, osc),
               "at %d Hz the divisor is %d; osc/(hz*%d) clamped to 1..%d is %d"
               % (hz, divi, pol.range_target, pol.divi_max, divisor_for(hz, pol, osc)))
        expect(rng == range_for(hz, pol, osc),
               "at %d Hz the range is %d, not %d" % (hz, rng, range_for(hz, pol, osc)))
        expect(act == actual_hz(hz, pol, osc),
               "at %d Hz the achievable frequency is reported %d, not %d"
               % (hz, act, actual_hz(hz, pol, osc)))
        if rng:
            expect(pol.range_min <= rng <= pol.range_max,
                   "at %d Hz the range %d is outside the stated bounds" % (hz, rng))
            expect(1 <= divi <= pol.divi_max,
                   "at %d Hz the divisor %d does not fit CM_PWMDIV's twelve bits" % (hz, divi))
            expect(osc // (divi * rng) == act,
                   "the reported frequency at %d Hz is not osc/(divi*range)" % hz)
    expect(s.all("F hz") and any(r[0] == 25000 and r[3] == 25000 for r in s.all("F hz")),
           "25000 Hz does not come out exactly, and it must: 54 MHz over a "
           "divisor of 1 and a range of 2160 is 25000 with no remainder")
    expect(any(r[0] == 25000 and r[1] == 1 and r[2] == 2160 for r in s.all("F hz")),
           "25 kHz should be divisor 1, range 2160")
    expect(s.pair("F hz", 27000001) is None
           or [r for r in s.all("F hz") if r[0] == 27000001][0][2] == 0,
           "one hertz past the oscillator over the smallest legal range must be refused")
    for rng, pm in ((2160, 0), (2160, 1), (2160, 500), (2160, 999), (2160, 1000)):
        got = s.pair("F duty2160", pm)
        expect(got == duty_counts(rng, pm, pol),
               "%d permille of a %d-count range is %r, not %d"
               % (pm, rng, got, duty_counts(rng, pm, pol)))
    expect(s.pair("F duty2160", 0) == 0 and s.pair("F duty2160", 1000) == 2160,
           "THE TWO RAILS MUST BE EXACT: 0 permille is 0 counts and 1000 "
           "permille is the whole range")
    for pm in (125, 749, 750):
        expect(s.pair("F duty4", pm) == duty_counts(4, pm, pol),
               "%d permille of a 4-count range is %r, not %d"
               % (pm, s.pair("F duty4", pm), duty_counts(4, pm, pol)))

    # -- G, the pin table -------------------------------------------------
    for pin, (blk, chan, alt) in sorted(facts.pinmap.items()):
        row = [r for r in s.all("G pin") if r[0] == pin]
        if not row:
            continue
        _p, base, ch, a = row[0]
        want_base = facts.pwm0 if blk == 0 else facts.pwm1
        expect(base == want_base,
               "GPIO %d is on PWM%d ($%08X) by the device tree and the library "
               "put it at $%08X" % (pin, blk, want_base, base))
        expect(ch == chan, "GPIO %d is channel %d by the device tree and the "
                           "library says %d" % (pin, chan, ch))
        expect(a == alt, "GPIO %d needs alt%d by the device tree and the "
                         "library says alt%d" % (pin, alt, a))
    for pin in (4, 14, 0):
        row = [r for r in s.all("G pin") if r[0] == pin]
        if row:
            expect(row[0][1] == 0 and row[0][2] == -1 and row[0][3] == -1,
                   "GPIO %d has no PWM function in the device tree and the "
                   "library offered one" % pin)

    # ==================================================================
    #  RUN 2 - the register invalid, so the firmware has to answer
    # ==================================================================
    board2, uart2, steps2 = run(probe_image(-1, work), facts, 0)
    s2 = Said(uart2.decode("utf-8", "replace"))
    print("run 2 (register invalid, driver linked): %d instructions" % steps2)
    expect(s2.one("B valid") == 0, "an all-zero status word read as valid")
    expect(s2.one("B probe") == 0,
           "the driver's probe CLAIMED a block whose status word is not valid; "
           "a probe that claims a silent block is a loader that binds nothing")
    expect(s2.one("B regmilli") == therm_none,
           "an invalid register must answer the no-reading sentinel, not a "
           "temperature; it gave %r" % s2.one("B regmilli"))
    expect(s2.one("B milli") == FW_TEMP_MILLI,
           "WITH THE REGISTER INVALID THE FIRMWARE MUST ANSWER. The library "
           "gave %r" % s2.one("B milli"))
    expect(s2.one("B source") == 2,
           "the library fell back and did not SAY it fell back: the source "
           "reads %r and should be the firmware (2)" % s2.one("B source"))
    expect(s2.one("B regfails") == 2,
           "two seam reads answer no reading in that section and %r were counted"
           % s2.one("B regfails"))
    expect(s2.one("B bound") == 0,
           "the consumer bound the thermal seam although the driver never gave "
           "it a reading; it holds %r bindings" % s2.one("B bound"))
    expect(s2.one("A fold") == s.one("A fold"),
           "the conversion changed between two runs of the same code")

    # ==================================================================
    #  RUN 7 - THE DIAGNOSTIC AS COMMITTED: NO DRIVER AT ALL
    #
    #  The state of a board with no THERMAL.MOD on its card.  The seam is
    #  empty, nothing is counted as a failure (nothing was asked), nothing
    #  is bound, and the firmware answers - with the source saying so.
    # ==================================================================
    board7, uart7, steps7 = run(probe_image(-1, work, with_driver=False), facts, raw_valid)
    s7 = Said(uart7.decode("utf-8", "replace"))
    print("run 7 (as committed, no driver): %d instructions" % steps7)
    t7 = uart7.decode("utf-8", "replace")
    expect("A skipped" in t7 and "B driver none" in t7,
           "the driverless build did not SAY its register half was skipped")
    expect(s7.one("B regmilli") == therm_none,
           "with no driver the seam must be empty, and it answered %r" % s7.one("B regmilli"))
    expect(s7.one("B milli") == FW_TEMP_MILLI and s7.one("B source") == 2,
           "with no driver the firmware must answer and the source must say "
           "so; it gave %r from source %r" % (s7.one("B milli"), s7.one("B source")))
    expect(s7.one("B regfails") == 0,
           "an EMPTY seam was counted as %r failures; nothing was asked, so "
           "nothing failed" % s7.one("B regfails"))
    expect(s7.one("B bound") == 0, "the driverless build holds a binding on an empty seam")
    expect(board7.avs_reads == 0,
           "the driverless build read the AVS register %d times; with no "
           "driver nothing in the core may touch it" % board7.avs_reads)

    # ==================================================================
    #  RUNS 3 AND 4 - a real channel at 25 kHz, byte for byte, on BOTH
    #  channels: every per-channel address is derived from the channel
    #  index, so a wrong stride is invisible on channel 1.
    # ==================================================================
    P = REL_PWM
    hard_boards = {}
    for hard_pin in (18, 19):
        if hard_pin not in facts.pinmap:
            die("the device tree no longer puts a PWM channel on GPIO %d" % hard_pin)
        blk, chan, alt = facts.pinmap[hard_pin]
        base = facts.pwm0 if blk == 0 else facts.pwm1
        b, u, st = run(probe_image(hard_pin, work), facts, raw_valid)
        hard_boards[hard_pin] = (b, u, st)
        sh = Said(u.decode("utf-8", "replace"))
        print("run %d (GPIO %d, PWM%d channel %d, at 25 kHz): %d instructions"
              % (2 + len(hard_boards), hard_pin, blk, chan + 1, st))

        expect(sh.one("H begin") == 0, "PwmBegin on GPIO %d at 25 kHz refused" % hard_pin)
        hs = sh.all("H state")
        expect(hs and hs[0] == [hard_pin, 2160, 1, 25000],
               "after begin on GPIO %d the library reports %r; 54 MHz at divisor "
               "1 and range 2160 is exactly 25000 Hz" % (hard_pin, hs[0] if hs else None))
        expect(sh.one("H clockhz") == osc,
               "clk_pwm read back as %r; at divisor 1 off the oscillator it is %d"
               % (sh.one("H clockhz"), osc))

        expect(not b.cm_no_password,
               "THE CLOCK MANAGER WAS WRITTEN WITHOUT THE PASSWORD at offsets %r."
               % [hex(o) for o, _v in b.cm_no_password])
        expect(not b.cm_wrote_while_busy,
               "CM_PWMDIV was written while BUSY was still set, which Table 99 forbids")
        seq = b.cm_writes
        expect(len(seq) == 4,
               "the clock start should be four writes - stop, divisor, source, "
               "enable - and it was %d: %r" % (len(seq), [(hex(o), hex(v)) for o, v in seq]))
        if len(seq) == 4:
            (o0, v0), (o1, v1), (o2, v2), (o3, v3) = seq
            expect(o0 == facts.cm_pwmctl and not (v0 & facts.cm_enable),
                   "the first write must clear ENAB on CM_PWMCTL, and it was "
                   "offset $%03X value $%06X" % (o0, v0))
            expect(o1 == facts.cm_pwmdiv, "the divisor must be written second, before the source")
            expect(v1 == (1 << facts.cm_div_frac_bits),
                   "CM_PWMDIV was $%06X; divisor 1 in DIVI (bits 23:12) is $%06X"
                   % (v1, 1 << facts.cm_div_frac_bits))
            expect(o2 == facts.cm_pwmctl and v2 == facts.cm_src_osc,
                   "the source must be selected on its own, with MASH zero and "
                   "ENAB clear; it was $%06X" % v2)
            expect(o3 == facts.cm_pwmctl
                   and v3 == (facts.cm_src_osc | facts.cm_enable | (1 << facts.cm_gate)),
                   "the enable must be a SEPARATE write, and it was $%06X" % v3)

        ctl_off = facts.pwm_control_off
        rng_off = facts.pwm_period_base + chan * facts.pwm_period_stride
        dat_off = facts.pwm_duty_base + chan * facts.pwm_duty_stride
        shift = chan * facts.pwm_ctl_shift
        want_on = (facts.pwm_mode_bit | facts.pwm_enable_bit) << shift

        writes = b.pwm_writes
        expect(all(bb == base for bb, _o, _v in writes),
               "GPIO %d is on PWM%d but the library wrote another block: %r"
               % (hard_pin, blk, sorted({hex(bb) for bb, _o, _v in writes})))
        sta_off = facts.pwm_sta_off
        berr_bit = 1 << facts.pwm_sta_bits["BERR"]
        prog_all = [(o, v) for _b, o, v in writes]
        expect(prog_all and prog_all[0] == (sta_off, berr_bit),
               "the first PWM write should clear BERR at $%02X with $%X, and it was %r"
               % (sta_off, berr_bit, prog_all[0] if prog_all else None))
        prog = [(o, v) for o, v in prog_all if o != sta_off]
        expect(len(prog) >= 4,
               "the channel programming was %d writes, which is too few to be "
               "off/range/duty/on" % len(prog))
        if len(prog) >= 4:
            expect(prog[0] == (ctl_off, 0),
                   "the channel must be DISABLED before its range is written - "
                   "the first write was $%02X = $%08X" % prog[0])
            expect(prog[1] == (rng_off, 2160),
                   "channel %d's range register is $%02X by the driver's PERIOD(x) "
                   "macro, and the library wrote $%02X = %d"
                   % (chan + 1, rng_off, prog[1][0], prog[1][1]))
            expect(prog[2] == (dat_off, 0),
                   "channel %d's data register is $%02X by the driver's DUTY(x) "
                   "macro and the duty must start at zero; the library wrote "
                   "$%02X = %d" % (chan + 1, dat_off, prog[2][0], prog[2][1]))
            expect(prog[3] == (ctl_off, want_on),
                   "the enable write should be $%02X = $%08X and it was $%02X = $%08X"
                   % (ctl_off, want_on, prog[3][0], prog[3][1]))
            other_mask = 0xFF << ((1 - chan) * facts.pwm_ctl_shift)
            expect(not (prog[3][1] & other_mask),
                   "enabling channel %d also set bits in channel %d's control "
                   "byte: $%08X" % (chan + 1, 2 - chan, prog[3][1]))

        # THE CHANNEL HAS TO ACTUALLY START - STAi is the one bit a driver
        # cannot make up by writing to it.
        expect((base, chan) in b.chan_started,
               "PWM%d channel %d never began transmitting. Every register read "
               "back correct and the pad stayed low - which is what a board does "
               "when the control byte is written while the clock generator is "
               "still coming up." % (blk, chan + 1))
        expect(prog.count((ctl_off, want_on)) == 1,
               "the enabling control byte $%08X was written %d times; on a part "
               "whose clock is up it should take once"
               % (want_on, prog.count((ctl_off, want_on))))
        expect(not b.chan_refused,
               "%d control write(s) asked a channel to run with no clock behind "
               "them: %r" % (len(b.chan_refused),
                             [(hex(bb), cc + 1) for bb, cc in b.chan_refused]))

        trace = [lv for lv in b.pad_trace.get(hard_pin, []) if lv is not None]
        expect(trace[:3] == [0, -1, 1],
               "GPIO %d's pad should go solid low at duty 0, into a real waveform "
               "at 50 percent, then solid high at 100. The trace began %r "
               "(0 low, 1 high, -1 modulating)." % (hard_pin, trace[:3]))

        duties = [v for o, v in prog[4:] if o == dat_off]
        expect(duties == [0, 1080, 2160, 0],
               "channel %d's data register at $%02X received %r; 0, 50 and 100 "
               "percent of a 2160-count range are 0, 1080 and 2160, and PwmEnd "
               "writes one more zero" % (chan + 1, dat_off, duties))
        expect(sh.one("H dutybad") == const(P, "#PWM_ERR_DUTY")
               and sh.one("H dutyneg") == const(P, "#PWM_ERR_DUTY"),
               "an out-of-range duty must be refused rather than clamped")
        expect(sh.one("H readafterbad") == 1000, "a refused duty changed the remembered one")

        alt_codes = {0: 4, 1: 5, 2: 6, 3: 7, 4: 3, 5: 2}
        expect(b.fsel[hard_pin] == 0,
               "after PwmEnd the pad must be an INPUT, and GPIO %d's function "
               "select is %d" % (hard_pin, b.fsel[hard_pin]))
        expect(sh.one("H mode") == 0, "PinModeGet after end should read input")
        expect(sh.one("H end") == 0, "PwmEnd refused")
        expect(sh.one("H kindafter") == 0, "the kind should be none after end")
        expect(alt in alt_codes, "alt%d has no BCM2711 function-select code" % alt)
        expect(alt_codes[alt] in b.fsel_history.get(hard_pin, []),
               "GPIO %d was never switched to alt%d, whose function-select code "
               "is %d; the codes it passed through were %r"
               % (hard_pin, alt, alt_codes[alt], b.fsel_history.get(hard_pin, [])))

    uart3 = hard_boards[18][1]

    # ==================================================================
    #  RUN 5 - the software channel on a pin with no modulator
    # ==================================================================
    soft_pin = 5
    if soft_pin in facts.pinmap:
        die("GPIO %d now has a PWM channel; pick another for the software test" % soft_pin)
    board4, uart4, steps4 = run(probe_image(soft_pin, work), facts, raw_valid)
    s4 = Said(uart4.decode("utf-8", "replace"))
    print("run 5 (software toggle on GPIO %d): %d instructions" % (soft_pin, steps4))

    expect(s4.one("H begin") is None,
           "GPIO %d has no PWM channel and the hardware section ran anyway" % soft_pin)
    expect(not board4.pwm_writes, "the software run wrote %d PWM registers" % len(board4.pwm_writes))
    expect(not board4.cm_writes, "the software run reprogrammed the clock manager")
    expect(s4.one("J begin") == 0, "PwmSoftBegin refused a plain pin")
    expect(s4.one("J kind") == const(P, "#PWM_KIND_SOFT"),
           "the software channel did not report itself as software")
    expect(s4.one("J hz") == 100, "the software channel is not at 100 Hz")
    expect(s4.one("J duty") == 0, "PwmSoftDuty refused 250 permille")

    samples = s4.all("J svc")
    expect(len(samples) == 240, "the cadence run printed %d samples, not 240" % len(samples))
    period = 1000000 // 100
    high = duty_counts(period, 250, pol)
    # THE PHASE IS SEARCHED FOR, NOT TAKEN FROM THE LIBRARY: is there ANY
    # single phase under which a 10 ms period with a 2.5 ms high time
    # explains every sample?  A handful of edge-adjacent mismatches are
    # allowed, because each sample's clock is read after the service call.
    best = None
    for off in range(0, period, 5):
        bad = 0
        for us, lvl in samples:
            phase = (us - off) % period
            if lvl != (1 if phase < high else 0):
                bad += 1
        if best is None or bad < best[1]:
            best = (off, bad)
    expect(best is not None and best[1] <= 5,
           "no phase explains the software toggle: the closest fit left %r of %d "
           "samples disagreeing with a %d us period at a %d us high time"
           % (best[1] if best else None, len(samples), period, high))
    highs = sum(1 for _u, lv in samples if lv)
    frac = (1000 * highs) // max(1, len(samples))
    expect(200 <= frac <= 300,
           "over 240 samples the pin was high %d permille of the time, and the "
           "duty asked for was 250" % frac)
    edges = s4.all("J edges")
    expect(edges and edges[0][0] >= 4,
           "the software channel drove %r edges over several periods"
           % (edges[0][0] if edges else None))
    expect(edges and edges[0][1] == 0,
           "the cadence run stalled %r times" % (edges[0][1] if edges else None))
    stall = s4.all("J stall")
    expect(stall and stall[0][0] == 1,
           "a gap of three periods must be counted as exactly one stall, and it "
           "counted %r" % (stall[0][0] if stall else None))
    expect(stall and stall[0][1] == 1,
           "A STALL MUST PARK THE PIN AT ITS IDLE LEVEL, which for a fan is high; "
           "it parked at %r" % (stall[0][1] if stall else None))
    expect(s4.one("J end") == 0, "PwmSoftEnd refused")
    expect(s4.one("J mode") == 0, "the software channel must hand the pad back as an input")
    expect(board4.set_writes or board4.clr_writes,
           "the software channel never touched GPSET or GPCLR")

    # ==================================================================
    #  RUN 6 - THE GENERATOR FOUND PARKED ON GND, WHICH DOES NOT STOP
    # ==================================================================
    wedged = facts.cm_busy                      # BUSY, ENAB clear, SRC GND
    board5, uart5, steps5 = run(probe_image(18, work), facts, raw_valid, cm_start=wedged)
    print("run 6 (GPIO 18, the clock generator found wedged on GND): %d instructions" % steps5)
    s5 = Said(uart5.decode("utf-8", "replace"))
    expect(s5.one("H begin") == 0,
           "PwmBegin refused (%r) with the clock generator parked on GND and "
           "BUSY held" % s5.one("H begin"))
    expect(board5.chan_started,
           "no channel started on the run that begins with the generator wedged on GND")
    expect(not board5.cm_no_password, "the recovery wrote the clock manager without the password")
    expect(any(v & 0xF for o, v in board5.cm_writes if o == facts.cm_pwmctl),
           "nothing ever named a real clock source, so BUSY could not have been "
           "released; the CM writes were %r"
           % [(hex(o), hex(v)) for o, v in board5.cm_writes])

    # -- the probe's own self-checks -------------------------------------
    for tag, txt in (("run 1", uart), ("run 2", uart2), ("run 3", uart3),
                     ("run 4", hard_boards[19][1]), ("run 5", uart4),
                     ("run 6", uart5), ("run 7", uart7)):
        m = re.search(r"=== (\d+) internal disagreements ===", txt.decode("utf-8", "replace"))
        checked[0] += 1
        if not m:
            fails.append("%s never printed its own verdict line" % tag)
        elif int(m.group(1)) != 0:
            fails.append("%s: the probe reported %s internal disagreements" % (tag, m.group(1)))
    print("checks: %d" % checked[0])
    return checked[0]


# ======================================================================
#  THE UNIT THE OPERATOR READS
# ======================================================================
#  Every temperature a person reads is Fahrenheit.  Sections C and D prove
#  the POLICY is Fahrenheit, but a policy in Fahrenheit behind a report in
#  Celsius would pass every one of them, so the words are checked
#  separately.  IT IS A SOURCE-TEXT CHECK: the payload includes the curve
#  and not the command, because fan_cmd.pbi needs the settings store, the
#  parser and a board's whole seam.  It catches a Celsius line coming back;
#  it will not catch a Fahrenheit line printing a number from the wrong
#  place, which sections C and D catch.
# ----------------------------------------------------------------------
def unit_check(fails: list) -> int:
    checked = [0]
    Q = chr(34)

    def expect(cond, what):
        checked[0] += 1
        if not cond:
            fails.append(what)

    cmd = read(CORE / "fan_cmd.pbi")
    fan = source(REL_FAN)
    hal = read(HAL / "hal.pbi")

    # -- ONE conversion, and it is in the seam --------------------------
    expect(hal.count("Procedure.i HwTempMilliF(") == 1,
           "Anvil/Hal/hal.pbi must define HwTempMilliF exactly once - it is THE "
           "conversion")
    formula = re.compile(r"\*\s*9\s*\)?\s*/\s*5")
    skip_dirs = ("RaspberryPi4/Reference/", "ArduinoQ/Reference/", "_work/",
                 "build/", ".git/")
    files = []
    for pattern in ("*.pi4", "*.pbi", "*.unoq"):
        files.extend(ROOT.rglob(pattern))
    for path in sorted(set(files)):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(skip_dirs):
            continue
        # The diagnostics keep their own tiny formatters on purpose: they are
        # built standalone, against no seam, and do not ship.
        if "/Diagnostics/" in rel:
            continue
        if rel == "Anvil/Hal/hal.pbi":
            continue
        body = read(path)
        checked[0] += 1
        for line in body.splitlines():
            if line.lstrip().startswith(";"):
                continue
            if formula.search(line) and "32000" in line:
                fails.append("%s computes Fahrenheit from millidegrees itself: %r. "
                             "There is one conversion and it is hal.pbi's "
                             "HwTempMilliF()." % (rel, line.strip()))

    # -- the read line: F first, then the sensor truth ------------------
    # Anvil/Core/fan_cmd.pbi:264-276 on Anvil main.
    read_site = cmd.split("Procedure PutFanRead(")
    expect(len(read_site) == 2,
           "Anvil/Core/fan_cmd.pbi no longer has a PutFanRead - the fan "
           "temperature read line is where the Fahrenheit leads")
    if len(read_site) == 2:
        body = read_site[1].split("EndProcedure")[0]
        code = chr(10).join(l for l in body.splitlines() if not l.lstrip().startswith(";"))
        expect("HwTempWholeF(" in code,
               "the fan read line must take its number from HwTempWholeF()")
        f_at = code.find(Q + " F (" + Q)
        c_at = code.find(Q + " C, " + Q)
        expect(f_at >= 0, "the fan read line must print the Fahrenheit followed by \" F (\"")
        expect(c_at >= 0, "the fan read line must carry the Celsius in the bracket")
        expect(f_at >= 0 and c_at >= 0 and f_at < c_at,
               "FAHRENHEIT LEADS. The read line puts the Celsius first")
        expect("millidegrees from the sensor" in code,
               "the fan read line must name the raw millidegrees as the sensor's answer")

    # -- the curve line, and the throttle line: F alone -----------------
    # Anvil/Core/fan_cmd.pbi:622-659 on Anvil main.
    status = cmd.split("Procedure FanStatus()")
    expect(len(status) == 2, "fan_cmd.pbi no longer has a FanStatus")
    if len(status) == 2:
        body = status[1].split(chr(10) + "EndProcedure")[0]
        code = chr(10).join(l for l in body.splitlines() if not l.lstrip().startswith(";"))
        expect(Q + "curve         off below " + Q in code,
               "the fan status must still print a curve line beginning \"curve         off below \"")
        expect(Q + " F, full at " + Q in code and Q + " F of hysteresis" + Q in code,
               "the curve line must read 'off below N F, full at N F, N F of "
               "hysteresis' - Fahrenheit alone")
        expect(" C, full at " not in code and " C of hysteresis" not in code,
               "the curve line is printing Celsius again")
        expect("PutFanTempF(tmax)" in code,
               "the throttle point must print through PutFanTempF, Fahrenheit alone")

    # -- the arguments are Fahrenheit too -------------------------------
    expect("#FAN_LOW_F_DEFAULT  = 113" in fan and "#FAN_HIGH_F_DEFAULT = 158" in fan
           and "#FAN_HYST_F_DEFAULT = 5" in fan,
           "the curve defaults must be 113 F, 158 F and 5 F")
    expect("#FAN_LOW_C_DEFAULT" not in fan and "#FAN_HIGH_C_DEFAULT" not in fan
           and "#FAN_HYST_C_DEFAULT" not in fan,
           "the Celsius curve constants are back in fan.pbi")
    expect("degrees FAHRENHEIT" in cmd,
           "the fan curve and hyst refusals must say which unit they take, in a full sentence")

    # -- an older card cannot be misread --------------------------------
    expect('ProcedureReturn "fan.lowF"' in cmd and 'ProcedureReturn "fan.highF"' in cmd
           and 'ProcedureReturn "fan.hystF"' in cmd,
           "the saved curve keys must carry the unit in the NAME")
    expect("FanKeyLowCelsiusOld" in cmd,
           "FanBoot must still recognise the superseded Celsius keys")
    expect(cmd.count("HwTempWholeF(old * 1000)") == 3,
           "each of the three saved curve values must be converted from an older "
           "card's Celsius through the one conversion, and %d of the three are"
           % cmd.count("HwTempWholeF(old * 1000)"))
    expect("HwTempWholeF(old * 1000) - HwTempWholeF(0)" in cmd,
           "A HYSTERESIS IS A DIFFERENCE, NOT A TEMPERATURE: the 32 must be "
           "subtracted back off an older card's hysteresis")

    print("unit checks: %d" % checked[0])
    return checked[0]


# ======================================================================
#  THE MUTATIONS
#
#  Each is one edit to a COPY of one source, chosen because it is a
#  plausible mistake.  A survivor is a hole in the gate.  Anchors follow
#  Anvil main: the AVS arithmetic lives in the driver module and the block's
#  address in the board's device table.
# ======================================================================
MUTATIONS = [
    (REL_AVS, "the thermal slope loses its sign",
     "#AVS_TEMP_SLOPE  = -487", "#AVS_TEMP_SLOPE  = 487", 1),
    (REL_AVS, "the offset is off by a factor of ten",
     "#AVS_TEMP_OFFSET = 410040", "#AVS_TEMP_OFFSET = 41004", 1),
    (REL_AVS, "only one validity bit is required",
     "#AVS_TEMP_VALID_MASK  = $10400", "#AVS_TEMP_VALID_MASK  = $10000", 1),
    (REL_AVS, "the data field is eleven bits, not ten",
     "#AVS_TEMP_DATA_MASK   = $3FF", "#AVS_TEMP_DATA_MASK   = $7FF", 1),
    (REL_HWMOD, "the AVS block is handed to the driver through the wrong soc range",
     "#HWDEV_AVS_MONITOR = $FD5D2000", "#HWDEV_AVS_MONITOR = $FE5D2000", 1),
    (REL_AVS, "an invalid register answers zero instead of the sentinel",
     "  If AvsValid(raw) = 0\n    ProcedureReturn #MOD_TEMP_NONE",
     "  If AvsValid(raw) = 0\n    ProcedureReturn 0", 1),
    (REL_AVS, "the probe claims a block whatever its status word says",
     "  If AvsValid(AvsStatus(device)) = 0\n    ProcedureReturn 0",
     "  If 0 <> 0\n    ProcedureReturn 0", 1),
    (REL_THERMAL, "the consumer turns the driver's no-reading into zero degrees",
     "  If t = #MOD_TEMP_NONE\n    therm_seamFails = therm_seamFails + 1\n    ProcedureReturn #THERM_NONE",
     "  If t = #MOD_TEMP_NONE\n    therm_seamFails = therm_seamFails + 1\n    ProcedureReturn 0", 1),
    (REL_THERMAL, "the consumer never binds the seam, so an unload could pull the driver out from under it",
     "    therm_bind = ModSeamBind(#SVCCAP_THERMAL, @ThermalSaySelf, @ThermalSeamDetach)",
     "    therm_bind = -1", 1),
    (REL_THERMAL, "negative millidegrees round the positive way",
     "  ProcedureReturn -((-milli + 500) / 1000)",
     "  ProcedureReturn (milli + 500) / 1000", 1),
    (REL_PWM, "the clock manager password is left off",
     "  PokeN(#CM_BASE + off, #CM_PASSWD | (value & $00FFFFFF))",
     "  PokeN(#CM_BASE + off, value & $00FFFFFF)", 1),
    (REL_PWM, "the source write carries the enable, which Table 99 forbids",
     "  PwmCmWrite(#CM_PWMCTL_OFF, #CM_SRC_OSC)\n  ProcedureReturn #PWM_OK",
     "  PwmCmWrite(#CM_PWMCTL_OFF, #CM_SRC_OSC | #CM_CTL_ENAB | #CM_CTL_GATE)\n  ProcedureReturn #PWM_OK", 1),
    (REL_PWM, "the divisor is written before the clock is stopped",
     "  rc = PwmClockStop()\n  If rc <> #PWM_OK\n    ProcedureReturn rc\n  EndIf\n  PwmCmWrite(#CM_PWMDIV_OFF, divi << #CM_DIV_INT_SHIFT)",
     "  PwmCmWrite(#CM_PWMDIV_OFF, divi << #CM_DIV_INT_SHIFT)\n  rc = PwmClockStop()\n  If rc <> #PWM_OK\n    ProcedureReturn rc\n  EndIf", 1),
    (REL_PWM, "the DIVI field sits at the wrong bit",
     "#CM_DIV_INT_SHIFT = 12", "#CM_DIV_INT_SHIFT = 8", 1),
    (REL_PWM, "the channel is enabled before its range is set",
     "  PwmCtlWrite(base, chan, 0)                        ; channel off",
     "  PwmCtlWrite(base, chan, #PWM_CTL_MSEN | #PWM_CTL_PWEN)", 1),
    (REL_PWM, "M/S mode is dropped and the distributed algorithm runs",
     "  PwmCtlWrite(base, chan, #PWM_CTL_MSEN | #PWM_CTL_PWEN)\n  pwm_startWrites = 1",
     "  PwmCtlWrite(base, chan, #PWM_CTL_PWEN)\n  pwm_startWrites = 1", 1),
    (REL_PWM, "the generator is asked to start and never waited for",
     "  t0 = Micros()\n  While (PwmCmRead(#CM_PWMCTL_OFF) & #CM_CTL_BUSY) = 0\n    If Micros() - t0 > #PWM_BUSY_TIMEOUT_US\n      ProcedureReturn #PWM_ERR_CLOCK\n    EndIf\n  Wend\n  delayMicroseconds(#PWM_CLOCK_SETTLE_US)\n",
     "", 1),
    (REL_PWM, "the channel is programmed AFTER the generator is started, not before",
     "  PwmProgramChannel(base, chan, rng)\n  rc = PwmClockRun()",
     "  rc = PwmClockRun()\n  PwmProgramChannel(base, chan, rng)", 1),
    (REL_PWM, "the channel-state bit is looked for at twice the channel's stride",
     "  ProcedureReturn #PWM_STA_STA1 << chan",
     "  ProcedureReturn #PWM_STA_STA1 << (chan * 2)", 1),
    (REL_PWM, "the confirm gives up waiting and re-writes the control byte at once",
     "    While Micros() - t0 <= #PWM_START_TIMEOUT_US",
     "    While Micros() - t0 <= 0", 1),
    (REL_PWM, "a generator parked on GND is not recovered",
     "    PwmCmWrite(#CM_PWMCTL_OFF, #CM_SRC_OSC)\n    tries = tries + 1",
     "    tries = tries + 1", 1),
    (REL_PWM, "the two channels' registers are 0x08 apart, not 0x10",
     "  ProcedureReturn base + #PWM_RNG1_OFF + chan * $10",
     "  ProcedureReturn base + #PWM_RNG1_OFF + chan * $08", 1),
    (REL_PWM, "GPIO 18's alternate function is 0, like GPIO 12's",
     "    Case 18\n      ProcedureReturn 5", "    Case 18\n      ProcedureReturn 0", 1),
    (REL_PWM, "the duty truncates instead of rounding",
     "  ProcedureReturn (range * permille + #PWM_DUTY_MAX / 2) / #PWM_DUTY_MAX",
     "  ProcedureReturn (range * permille) / #PWM_DUTY_MAX", 1),
    (REL_PWM, "full duty is one count short of the range",
     "  If permille >= #PWM_DUTY_MAX\n    ProcedureReturn range\n  EndIf",
     "  If permille >= #PWM_DUTY_MAX\n    ProcedureReturn range - 1\n  EndIf", 1),
    (REL_PWM, "the smallest legal range is 1",
     "#PWM_RANGE_MIN    = 2", "#PWM_RANGE_MIN    = 1", 1),
    (REL_PWM, "the pad is left as an output when the channel ends",
     "  PinInput(pwm_pin)\n  pwm_pin      = -1", "  PinLow(pwm_pin)\n  pwm_pin      = -1", 1),
    (REL_PWM, "the software stall resets the phase instead of parking",
     "    PwmSoftDrive(pwmsoft_idle)\n    ProcedureReturn 1",
     "    PwmSoftDrive(0)\n    ProcedureReturn 1", 1),
    (REL_PWM, "the software period is re-anchored to now, losing the phase",
     "  While since >= pwmsoft_periodUs\n    pwmsoft_markUs = pwmsoft_markUs + pwmsoft_periodUs\n    since = since - pwmsoft_periodUs\n  Wend",
     "  If since >= pwmsoft_periodUs\n    pwmsoft_markUs = now\n    since = 0\n  EndIf", 1),
    (REL_FAN, "the hysteresis is applied to the start edge as well",
     "  If milliF >= fan_lowMilliF\n    ProcedureReturn 1\n  EndIf",
     "  If milliF >= fan_lowMilliF + fan_hystMilliF\n    ProcedureReturn 1\n  EndIf", 1),
    (REL_FAN, "there is no hysteresis at all",
     "    If milliF < fan_lowMilliF - fan_hystMilliF",
     "    If milliF < fan_lowMilliF", 1),
    (REL_FAN, "a fan with no thermometer stops instead of running",
     "    fan_running = 1\n    fan_kicking = 0\n    ProcedureReturn #FAN_FAILSAFE_DUTY",
     "    fan_running = 0\n    fan_kicking = 0\n    ProcedureReturn 0", 1),
    (REL_FAN, "the ramp starts from nothing rather than the minimum duty",
     "  ProcedureReturn #FAN_MIN_DUTY + ((#FAN_DUTY_MAX - #FAN_MIN_DUTY) * above) / span",
     "  ProcedureReturn (#FAN_DUTY_MAX * above) / span", 1),
    (REL_FAN, "the spin-up kick never fires",
     "    fan_kicking   = 1\n    fan_kickStart = nowMs",
     "    fan_kicking   = 0\n    fan_kickStart = nowMs", 1),
    (REL_FAN, "the kick never ends",
     "    If nowMs - fan_kickStart < #FAN_KICK_MS",
     "    If nowMs - fan_kickStart < #FAN_KICK_MS * 1000", 1),
    (REL_FAN, "off no longer outranks the failsafe",
     "  If fan_mode = #FAN_MODE_OFF\n    If fan_running <> 0",
     "  If fan_mode = #FAN_MODE_OFF And haveTemp <> 0\n    If fan_running <> 0", 1),
    (REL_FAN, "an inverted curve is accepted",
     "  If highF - lowF < #FAN_SPAN_MIN_F\n    ProcedureReturn #FAN_ERR_SPAN\n  EndIf",
     "  If highF = lowF\n    ProcedureReturn #FAN_ERR_SPAN\n  EndIf", 1),
    (REL_FAN, "a mode change keeps the running bit, so no kick on re-auto",
     "  fan_mode = mode\n  fan_running = 0\n  fan_kicking = 0",
     "  fan_mode = mode\n  fan_kicking = 0", 1),
]


def mutate_one(index: int, workdir: pathlib.Path) -> int:
    """Apply ONE edit to a COPY of one source and re-run the whole gate."""
    rel, why, old, new, count = MUTATIONS[index]
    text = read(ROOT / rel)
    mutated, err = pool.apply_edits(text, old, new, count)
    if err is None and mutated == text:
        err = "the edit changed nothing"
    if err:
        print("%sSURVIVED\t%s\t%s (the mutation could not be applied: %s)"
              % (pool.VERDICT, rel, why, err))
        return 1
    OVERRIDE[rel] = mutated
    fails = []
    try:
        facts = Facts()
        pol = Policy()
        main_check(fails, facts, pol, workdir)
    except SystemExit as exc:
        print("%sKILLED\t%s\t%s (the model refused: %s)"
              % (pool.VERDICT, rel, why, str(exc).replace("\n", " ")[:160]))
        return 0
    except Exception as exc:                                 # noqa: BLE001
        print("%sKILLED\t%s\t%s (%r)" % (pool.VERDICT, rel, why, exc))
        return 0
    if fails:
        print("%sKILLED\t%s\t%s (%s)"
              % (pool.VERDICT, rel, why, fails[0].replace("\n", " ")[:160]))
        return 0
    print("%sSURVIVED\t%s\t%s" % (pool.VERDICT, rel, why))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge compiler (default: $PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true", help="run the mutation sweep after the gate")
    ap.add_argument("--mutate-only", action="store_true")
    ap.add_argument("--mutate-one", type=int, default=None)
    ap.add_argument("--mutate-dir", default=None)
    ap.add_argument("--jobs", type=int, default=None)
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        raise SystemExit("No compiler was named. Pass --compiler with the path "
                         "to PureMetalForge.exe, or set PMF_COMPILER.")
    if not pathlib.Path(args.compiler).is_file():
        raise SystemExit(f"The compiler {args.compiler} does not exist, so "
                         "nothing can be built.")
    COMPILER["path"] = str(pathlib.Path(args.compiler).resolve())

    if args.mutate_one is not None:
        if not args.mutate_dir:
            raise SystemExit("--mutate-one needs --mutate-dir, the worker's own directory.")
        d = pathlib.Path(args.mutate_dir)
        d.mkdir(parents=True, exist_ok=True)
        return mutate_one(args.mutate_one, d)

    facts = Facts()
    pol = Policy()
    fails: list[str] = []
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-fancheck-"))
    try:
        if not args.mutate_only:
            n = main_check(fails, facts, pol, top / "gate")
            n = n + unit_check(fails)
            print()
            if fails:
                print("a64_fan_check: FAIL - %d of %d checks" % (len(fails), n))
                for f in fails:
                    print("   " + f)
                return 1
            print("a64_fan_check: PASS - %d checks, seven runs of the payload "
                  "under the model" % n)

        if args.mutate or args.mutate_only:
            print()
            print("mutation sweep: %d mutations, %d workers"
                  % (len(MUTATIONS), args.jobs or pool.worker_count()))
            lines = pool.run_parallel(pathlib.Path(__file__), ROOT,
                                      len(MUTATIONS), top / "mut",
                                      procs=args.jobs, label="mutation",
                                      extra_args=["--compiler", COMPILER["path"]])
            survived = 0
            for i, line in enumerate(lines):
                body = line[len(pool.VERDICT):] if line.startswith(pool.VERDICT) else line
                print("  %2d  %s" % (i, body))
                if body.startswith("SURVIVED") or body.startswith("ERROR"):
                    survived += 1
            left = pool.report_reaped(COMPILER["path"])
            print("  build processes left behind: %s"
                  % ("could not look" if left < 0 else left))
            print("mutations: %d killed, %d survived" % (len(lines) - survived, survived))
            if survived:
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
