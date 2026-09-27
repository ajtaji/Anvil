#!/usr/bin/env python3
"""Desk gate: the Pi 5 HwClock* backend - RaspberryPi4/Board/hw_clock.pi4,
the #PMF_CHIP = 2712 RTC source in Anvil/Core/wallclock.pbi, over
RaspberryPi4/Lib/rtc_fw.pi4 and the real mailbox.pi4.

The -t pi5 compiled code runs under tools/a64/a64_interp.py against the
modelled VideoCore of rtc_fw_check.py (the firmware's GET/SET_RTC_REG
messages from rtc-rpi.c). What is checked, and against what:

  * the seven-field UTC record (year..millisecond, 32-bit each, hal.pbi /
    abi.pbi slot 17) against Python's own calendar for the RTC's epoch -
    an independent civil conversion, not wallclock.pbi's;
  * provenance per hal.pbi's order: RTC -> #HW_CLK_RTC, RESTORED ->
    #HW_CLK_RESTORED, unset -> #HW_CLK_UNSET, with the record zeroed;
  * the seeder's 1980 floor: a flat-battery reading (1970 + uptime) is
    refused by name and the clock stays unset;
  * the boot-order hazard: TimeBoot's RESTORED anchor after the seed
    downgrades the clock (so the board must seed after TimeBoot), and a
    seed after it wins;
  * the lazy seed happens once; uncertainty and last-sync are -1.

#HW_CLK_* come from Anvil/Hal/hal.pbi, #WALLCLOCK_* from wallclock.pbi.
Desk proof only; silicon owed.

  py -3 -B tools/a64/hw_clock_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import datetime
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi5_desk as d                               # noqa: E402
import rtc_fw_check as r                           # noqa: E402

REL_HW = "RaspberryPi4/Board/hw_clock.pi4"
REL_WC = "Anvil/Core/wallclock.pbi"
REL_HAL = "Anvil/Hal/hal.pbi"
INCLUDES = ["RaspberryPi4/Lib/timer.pi4", REL_WC, r.REL_MBX, r.REL_LIB, REL_HW]
HAL_NAMES = ("#HW_CLK_UNSET", "#HW_CLK_RESTORED", "#HW_CLK_RTC", "#HW_CLK_GNSS")
REC = 0x2800000
RTC_EPOCH = 1790000000            # 2026-09-21 14:13:20 UTC


def driver(override):
    hal = d.source(REL_HAL, override)
    consts = "\n".join("%s = %d" % (n, d.const_in(hal, n, REL_HAL)) for n in HAL_NAMES)
    return ("; hw_clock_check driver - generated\n" + consts + "\n" +
            "".join('XIncludeFile "%s"\n' % i for i in INCLUDES) +
            "Global gate_never.i\n"
            "If gate_never = 1\n"
            "  MailboxInit() : HwClockSeed() : HwClockSeedResult() : HwClockProvenance()\n"
            "  HwClockUtc(0) : HwClockUncertaintyMs() : HwClockLastSyncTicks()\n"
            "  HwClockNotifyGnss(0) : HwClockRtcRaw() : WallClockSource() : WallClockTrusted()\n"
            "  WallClockSourceText() : WallClockSet(0, 0) : WallClockClear()\n"
            "EndIf\n")


def gate(cc, override, workdir):
    hal = d.source(REL_HAL, override)
    H = {n: d.const_in(hal, n, REL_HAL) for n in HAL_NAMES}
    wc = d.source(REL_WC, override)
    W = {n: d.const_in(wc, n, REL_WC) for n in
         ("#WALLCLOCK_SRC_NONE", "#WALLCLOCK_SRC_RESTORED", "#WALLCLOCK_SRC_RTC")}
    hw = d.source(REL_HW, override)
    S = {n: d.const_in(hw, n, REL_HW) for n in
         ("#HWCLK_SEED_OK", "#HWCLK_SEED_MAILBOX", "#HWCLK_SEED_FLOOR", "#HWCLK_SEED_NEVER")}
    mtext = d.source(r.REL_MBX, override)
    mbx = tuple(r.chip_const(mtext, n) for n in ("#MBX_READ", "#MBX_STATUS0", "#MBX_WRITE", "#MBX_STATUS1"))
    img, procs = d.build(cc, driver(override), "hw_clock_drv", workdir, override, INCLUDES)
    checks = [0]

    def check(ok, what):
        if not ok:
            d.die(what)
        checks[0] += 1

    def machine(rtc_value):
        box = {}
        windows = [(min(mbx) & ~0xFFF, (max(mbx) & ~0xFFF) + 0x1000)]
        m = d.Machine(img, procs, lambda a, s, v: box["model"](a, s, v), windows=windows)
        vc, box["model"] = r.build_model(m.cpu, mbx)
        vc.regs[r.REG_TIME] = rtc_value
        call = lambda name, *a: m.signed(m.call(name, *a))
        check(call("MailboxInit") == 1, "MailboxInit failed")
        return m, vc, call

    def record(m):
        return [int.from_bytes(m.peek(REC + 4 * i, 4), "little") for i in range(7)]

    # --- a good RTC, seeded lazily by the first question -------------------
    m, vc, call = machine(RTC_EPOCH)
    m.poke(REC, b"\xAA" * 28)
    prov = call("HwClockUtc", REC)
    check(prov == H["#HW_CLK_RTC"], "provenance %d, want #HW_CLK_RTC" % prov)
    check(len(vc.messages) == 1 and vc.messages[0][2] == (r.REG_TIME, 0),
          "the lazy seed was not one GET_RTC_REG {0,0}: %r" % vc.messages)
    want = datetime.datetime.fromtimestamp(RTC_EPOCH, datetime.timezone.utc)
    got = record(m)
    check(got[:6] == [want.year, want.month, want.day, want.hour, want.minute, want.second],
          "UTC record %r, the RTC's epoch is %s" % (got, want.isoformat()))
    check(0 <= got[6] < 1000, "millisecond field %d" % got[6])
    check(call("WallClockSource") == W["#WALLCLOCK_SRC_RTC"], "wall clock source is not RTC")
    check(call("WallClockTrusted") == 1, "an RTC time is not trusted")
    check("RTC" in m.cstr(call("WallClockSourceText")), "source text does not name the RTC")
    check(call("HwClockProvenance") == H["#HW_CLK_RTC"] and len(vc.messages) == 1,
          "the lazy seed ran more than once")
    check(call("HwClockUncertaintyMs") == -1 and call("HwClockLastSyncTicks") == -1,
          "an uncertainty or sync time was invented")
    check(call("HwClockNotifyGnss", REC) == 0, "a GNSS fix was accepted on a board without GNSS")

    # --- boot order: TimeBoot's RESTORED after the seed downgrades it -------
    check(call("WallClockSet", 1780000000, W["#WALLCLOCK_SRC_RESTORED"]) == 1, "restore refused")
    check(call("HwClockProvenance") == H["#HW_CLK_RESTORED"], "RESTORED not reported as a floor")
    check(call("HwClockSeed") == S["#HWCLK_SEED_OK"] and call("HwClockProvenance") == H["#HW_CLK_RTC"],
          "a seed after the restore did not win")

    # --- flat battery: 1970 + uptime is refused by name ---------------------
    m, vc, call = machine(4321)
    m.poke(REC, b"\xAA" * 28)
    check(call("HwClockUtc", REC) == H["#HW_CLK_UNSET"], "a 1970 RTC produced a time")
    check(record(m) == [0] * 7, "the record was not zeroed when there is no time")
    check(call("HwClockSeedResult") == S["#HWCLK_SEED_FLOOR"], "a flat battery was not named FLOOR")
    check(call("WallClockSource") == W["#WALLCLOCK_SRC_NONE"], "a 1970 RTC anchored the wall clock")
    check(call("HwClockRtcRaw") == 4321, "the raw reading was not kept")

    # --- firmware that does not answer -------------------------------------
    m, vc, call = machine(RTC_EPOCH)
    vc.fault = "error"
    check(call("HwClockProvenance") == H["#HW_CLK_UNSET"], "a failed mailbox produced a provenance")
    check(call("HwClockSeedResult") == S["#HWCLK_SEED_MAILBOX"], "a failed mailbox was not named")
    return checks[0]


MUTATIONS = [
    (REL_HW, "RTC anchored as RESTORED", "WallClockSet(t, #WALLCLOCK_SRC_RTC)", "WallClockSet(t, #WALLCLOCK_SRC_RESTORED)"),
    (REL_HW, "no 1980 floor in the seeder", "  If t < #WALLCLOCK_EPOCH_MIN\n", "  If t < 0\n"),
    (REL_HW, "RTC reported as GNSS", "    ProcedureReturn #HW_CLK_RTC\n", "    ProcedureReturn #HW_CLK_GNSS\n"),
    (REL_HW, "month and day swapped", "  PokeL(*out + 4, WallClockMonth())\n  PokeL(*out + 8, WallClockDay())",
     "  PokeL(*out + 4, WallClockDay())\n  PokeL(*out + 8, WallClockMonth())"),
    (REL_HW, "record not zeroed", "  While i < 28\n", "  While i < 0\n"),
    (REL_HW, "seeded on every question", "  If hwclk_seed = #HWCLK_SEED_NEVER\n    HwClockSeed()",
     "  If hwclk_seed >= 0\n    HwClockSeed()"),
    (REL_HW, "a restored floor reported as unset",
     "  If s = #WALLCLOCK_SRC_RESTORED\n    ProcedureReturn #HW_CLK_RESTORED", "  If s = 99\n    ProcedureReturn #HW_CLK_RESTORED"),
    (REL_HW, "an uncertainty invented", "Procedure.i HwClockUncertaintyMs()\n  ProcedureReturn -1",
     "Procedure.i HwClockUncertaintyMs()\n  ProcedureReturn 1000"),
    (REL_WC, "2712 WallClockSet still stops at SNTP",
     "  CompilerIf #PMF_CHIP = 2712\n  If source < #WALLCLOCK_SRC_MANUAL Or source > #WALLCLOCK_SRC_RTC",
     "  CompilerIf #PMF_CHIP = 2712\n  If source < #WALLCLOCK_SRC_MANUAL Or source > #WALLCLOCK_SRC_SNTP"),
    (REL_WC, "RTC not trusted", "  If wallclock_src = #WALLCLOCK_SRC_RTC\n    ProcedureReturn 1",
     "  If wallclock_src = -7\n    ProcedureReturn 1"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    top = pathlib.Path(tempfile.mkdtemp(prefix="hw-clock-"))
    try:
        try:
            n = gate(cc, {}, top / "gate")
        except d.GateFail as exc:
            print("hw_clock_check: FAIL - %s" % exc)
            return 1
        print("hw_clock_check: PASS - %d checks" % n)
        if a.mutate:
            if d.run_mutations("hw_clock_check", MUTATIONS,
                               lambda ov, wd: gate(cc, ov, wd), top / "mut"):
                return 1
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
