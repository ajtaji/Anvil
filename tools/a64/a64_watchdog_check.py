#!/usr/bin/env python3
"""Executable gate for the BCM2711 PM watchdog in RaspberryPi4/Lib/safety.pi4.

    python tools/a64/a64_watchdog_check.py --compiler <PureMetalForge.exe>

There is no PM block on this machine.  It is modelled here, and the model
is deliberately STRICT in the one way the real hardware is not: the real
PM block silently IGNORES any write whose top byte is not $5A.  Ignored,
not faulted.  So a missing password produces a watchdog that arms
perfectly, reports armed, and never fires - which is indistinguishable
from having no watchdog at all right up until the moment something hangs
and nothing rescues it.  This model refuses such a write loudly instead.

NOTHING HERE IS TRANSCRIBED FROM safety.pi4.  Every constant the model
checks against is pinned below from the watchdog driver inside the loader
this board's firmware family boots, the same driver safety.pi4's header
cites:

    Das U-Boot v2025.01 (revision 6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72),
    drivers/watchdog/bcm2835_wdt.c, lines 14-27

That driver is third-party source and is not copied into this tree; the
seven register facts and the tick macro are pinned in UBOOT_BCM2835_WDT
with the line each came from.  The library and the gate therefore state
the same facts independently and can disagree, which is the whole point of
a gate.  If someone edits a constant in safety.pi4, this goes red.

WHAT IS ASSERTED

  * the password is in the top byte of EVERY write to the block
  * arming is PM_WDOG then a READ-MODIFY-WRITE of PM_RSTC that sets WRCFG
    to FULL_RESET
  * the tick conversion is 65536/second, and the 20-bit clamp is applied
    and REPORTED rather than letting the value wrap
  * stop writes PM_RSTC_RESET and does NOT touch PM_WDOG
  * petting a stopped watchdog does nothing at all
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4WatchdogProbe.pi4"

LOAD = 0x400000
LOADER_SP = 0x3000000
LOADER_LR = 0xDEADBEE0
PM_BASE = 0xFE100000
UART_DR = 0xFE201000
UART_FR = 0xFE201018
CNTFRQ = 54_000_000

# ----------------------------------------------------------------------
#  The expected constants, pinned from the cited driver.
#
#  Das U-Boot v2025.01, revision 6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72,
#  drivers/watchdog/bcm2835_wdt.c.  name: (value, line)
# ----------------------------------------------------------------------
UBOOT_BCM2835_WDT = {
    "PM_RSTC": (0x1C, 14),
    "PM_WDOG": (0x24, 15),
    "PM_PASSWORD": (0x5A000000, 17),
    "PM_WDOG_MAX_TICKS": (0x000FFFFF, 22),
    "PM_RSTC_WRCFG_CLR": (0xFFFFFFCF, 23),
    "PM_RSTC_WRCFG_FULL_RESET": (0x00000020, 24),
    "PM_RSTC_RESET": (0x00000102, 25),
}
# bcm2835_wdt.c:27  #define MS_TO_WDOG_TICKS(x) (((x) << 16) / 1000)
MS_TO_WDOG_TICKS_SHIFT = 16
MS_TO_WDOG_TICKS_DIV = 1000
CITED = ("Das U-Boot v2025.01 drivers/watchdog/bcm2835_wdt.c")


def driver_constants() -> dict[str, int]:
    out = {name: value for name, (value, _line) in UBOOT_BCM2835_WDT.items()}
    out["TICKS_PER_SEC"] = ((1 << MS_TO_WDOG_TICKS_SHIFT) * 1000
                            // MS_TO_WDOG_TICKS_DIV)
    return out


class PM:
    """The power-manager block, strict about the password."""

    def __init__(self, k: dict[str, int], uart: bytearray) -> None:
        self.k = k
        self.uart = uart
        self.rstc = 0x00000000
        self.wdog = 0
        # (reg, raw value written, console bytes printed before the write)
        self.writes: list[tuple[str, int, int]] = []
        self.reads: list[str] = []

    def _name(self, off: int) -> str | None:
        if off == self.k["PM_RSTC"]:
            return "RSTC"
        if off == self.k["PM_WDOG"]:
            return "WDOG"
        return None

    def read(self, off: int) -> int:
        n = self._name(off)
        if n is None:
            raise SystemExit(
                f"The probe read an unmodelled PM register at +${off:02X}.")
        self.reads.append(n)
        return self.rstc if n == "RSTC" else self.wdog

    def write(self, off: int, val: int) -> None:
        n = self._name(off)
        if n is None:
            raise SystemExit(
                f"The probe wrote an unmodelled PM register at +${off:02X}.")
        if (val & 0xFF000000) != self.k["PM_PASSWORD"]:
            raise SystemExit(
                f"The probe wrote PM_{n} with no password: ${val:08X}. The "
                f"real block would IGNORE this silently and the watchdog "
                f"would never fire.")
        self.writes.append((n, val, len(self.uart)))
        body = val & 0x00FFFFFF
        if n == "WDOG":
            self.wdog = body
        else:
            self.rstc = body


def build(compiler: str, source: pathlib.Path, image: pathlib.Path) -> None:
    r = subprocess.run(
        [compiler, "--compile", str(source), "-t", "pi4",
         "--load-addr", hex(LOAD), "--stack-addr", hex(LOADER_SP),
         "--entry-returns", "-o", str(image)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True)
    if r.returncode != 0 or not image.exists():
        raise SystemExit("The watchdog probe did not build:\n"
                         + r.stdout + r.stderr)


def run(img: pathlib.Path, k: dict[str, int], limit: int = 60_000_000):
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    mem = cpu.memory
    uart = bytearray()
    pm = PM(k, uart)

    def load(addr: int, size: int) -> int:
        # THE ALIGNMENT RULE: this closure replaces A64.load, so the guard
        # has to be called here or the gate models a machine more
        # permissive than the part.
        cpu.align_guard(addr, size, False)
        if addr >= 0xFE000000:
            if addr == UART_FR:
                return 0
            if PM_BASE <= addr < PM_BASE + 0x114:
                return pm.read(addr - PM_BASE)
            raise SystemExit(f"The probe read unmodelled MMIO at ${addr:08X}.")
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFE000000:
            if addr == UART_DR:
                uart.append(value & 0xFF)
                return
            if PM_BASE <= addr < PM_BASE + 0x114:
                pm.write(addr - PM_BASE, value & 0xFFFFFFFF)
                return
            raise SystemExit(
                f"The probe wrote unmodelled MMIO at ${addr:08X}.")
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    def step() -> None:
        # cpu.fetch, not load: an instruction fetch is not a data access.
        ins = cpu.fetch(cpu.pc)
        # MRS Xt, CNTFRQ_EL0 / CNTPCT_EL0, shimmed.
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:
            cpu.x[ins & 31] = 0
            cpu.pc += 4
            return
        plain_step()

    n = 0
    while cpu.pc != LOADER_LR:
        n += 1
        if n > limit:
            raise SystemExit("The watchdog probe never returned.")
        step()
    return pm, bytes(uart)


def grade(pm: PM, text: str, k: dict[str, int]) -> tuple[list[str], int]:
    fails: list[str] = []
    count = 0
    tps = k["TICKS_PER_SEC"]

    def expect(cond: bool, what: str) -> None:
        nonlocal count
        count += 1
        if not cond:
            fails.append(what)

    # -- what the program itself measured ------------------------------
    def said(label: str) -> int | None:
        m = re.search(re.escape(label) + r"\s+(-?\d+)", text)
        return int(m.group(1)) if m else None

    expect(said("1 s") == tps, "1 s should be %d ticks" % tps)
    expect(said("2 s") == 2 * tps, "2 s should be %d ticks" % (2 * tps))
    expect(said("15 s") == 15 * tps, "15 s should be %d ticks" % (15 * tps))
    expect(said("16 s CLAMPED") == k["PM_WDOG_MAX_TICKS"],
           "16 s must clamp to PM_WDOG_MAX_TICKS")
    expect(said("60 s CLAMPED") == k["PM_WDOG_MAX_TICKS"],
           "60 s must clamp to PM_WDOG_MAX_TICKS, not wrap")
    expect(said("running (want 0)") == 0, "not running before arming")
    expect(said("running (want 1)") == 1, "running after arming")
    expect(said("armed   (want 1)") == 1, "SafetyArmed follows the watchdog")
    expect(said("pet     (want 1)") == 1, "petting a running watchdog works")
    expect(said("pet stopped (want 0)") == 0,
           "petting a STOPPED watchdog must not restart it")

    # -- what actually went onto the bus -------------------------------
    arms = [v for n, v, _ in pm.writes if n == "WDOG"]
    rstc = [v for n, v, _ in pm.writes if n == "RSTC"]

    expect(len(arms) >= 3,
           "expected at least three PM_WDOG writes (arm, pet, clamped arm), "
           "got %d" % len(arms))
    if arms:
        expect((arms[0] & 0x00FFFFFF) == 2 * tps,
               "the first arm should load %d ticks, loaded %d"
               % (2 * tps, arms[0] & 0x00FFFFFF))
        expect((arms[-1] & 0x00FFFFFF) == k["PM_WDOG_MAX_TICKS"],
               "the clamped arm should load PM_WDOG_MAX_TICKS, loaded $%X"
               % (arms[-1] & 0x00FFFFFF))

    full = k["PM_RSTC_WRCFG_FULL_RESET"]
    stop = k["PM_RSTC_RESET"]
    wrcfg = ~k["PM_RSTC_WRCFG_CLR"] & 0x00FFFFFF
    arming_rstc = [v & 0x00FFFFFF for v in rstc if (v & 0x00FFFFFF) != stop]
    stopping = [v & 0x00FFFFFF for v in rstc if (v & 0x00FFFFFF) == stop]
    expect(bool(arming_rstc), "arming never wrote PM_RSTC")
    for v in arming_rstc:
        expect((v & wrcfg) == full,
               "an arming PM_RSTC write left WRCFG as $%02X, not FULL_RESET"
               % (v & wrcfg))
    expect(len(stopping) >= 2,
           "expected two PM_RSTC stop writes, saw %d" % len(stopping))
    expect("RSTC" in pm.reads,
           "arming never READ PM_RSTC - it must be read-modify-write, or "
           "the bits outside WRCFG are clobbered")

    # -- the first stop, located by the console, touches only RSTC ------
    # The probe prints "pet     (want 1)" and then calls
    # SafetyWatchdogStop() before printing the next "running (want 0)".
    # Every write made between those two console positions belongs to the
    # stop, and it must be exactly one PM_RSTC_RESET with no PM_WDOG.
    pet = text.find("pet     (want 1)")
    after = text.find("running (want 0)", pet if pet >= 0 else 0)
    expect(pet >= 0 and after > pet,
           "the probe's pet and stop lines are missing from its output")
    if pet >= 0 and after > pet:
        pet_end = text.find("\n", pet)
        window = [(n, v) for n, v, at in pm.writes if pet_end < at <= after]
        expect(window == [("RSTC", k["PM_PASSWORD"] | stop)],
               "SafetyWatchdogStop() wrote %s; it must write exactly one "
               "PM_RSTC_RESET and leave PM_WDOG alone"
               % (["%s=$%08X" % w for w in window],))
        # And the stopped pet that follows writes nothing at all.
        stopped = text.find("pet stopped (want 0)")
        again = text.find("SafetyWatchdogStart(60)")
        if stopped >= 0 and again > stopped:
            idle = [(n, v) for n, v, at in pm.writes
                    if text.find("\n", stopped) < at <= again]
            expect(not idle,
                   "petting a stopped watchdog wrote %s; it must write "
                   "nothing" % (["%s=$%08X" % w for w in idle],))
    return fails, count


def run_gate(compiler: str, probe: pathlib.Path = PROBE) -> int:
    k = driver_constants()
    print("constants, pinned from %s:" % CITED)
    for name, (value, line) in UBOOT_BCM2835_WDT.items():
        print("   %-26s $%08X   (:%d)" % (name, value, line))
    print("   %-26s %d" % ("ticks per second", k["TICKS_PER_SEC"]))
    print()
    with tempfile.TemporaryDirectory(prefix="wdogcheck-") as td:
        img = pathlib.Path(td) / "wdogcheck.img"
        build(compiler, probe, img)
        pm, uart = run(img, k)
    text = uart.decode("utf-8", "replace")
    print(text.rstrip())
    print()
    fails, count = grade(pm, text, k)
    print("register traffic: %d writes, %d reads"
          % (len(pm.writes), len(pm.reads)))
    if fails:
        print("\na64_watchdog_check: FAIL %d of %d" % (len(fails), count))
        for f in fails:
            print("   " + f)
        return 1
    print("\na64_watchdog_check: PASS %d checks - the PM sequence matches %s"
          % (count, CITED))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="PureMetalForge.exe (default: $PMF_COMPILER)")
    args = ap.parse_args(argv); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        ap.error("No compiler was named. Pass --compiler with the path to "
                 "PureMetalForge.exe, or set PMF_COMPILER.")
    return run_gate(args.compiler)


if __name__ == "__main__":
    sys.exit(main())
