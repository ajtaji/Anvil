#!/usr/bin/env python3
"""pmfboot_2712_check.py - PMFBOOT's target admission, both chips, both directions.

Anvil/Core/pmfboot.pbi's PmfCheckV2Metadata() decides whether a version-2
container's compiler target may run on this monitor. A -t pi5 monitor
(#PMF_CHIP = 2712) must admit target 2712 and refuse 2711; a -t pi4 monitor
must admit 2711 and refuse 2712 - an image built for one chip carries that
chip's MMIO, map and start-up code and must never run on the other.

The gate EXECUTES the shipped procedure: it lifts the exact text of
PmfCheckV2Metadata() out of pmfboot.pbi (never a copy kept here), compiles it
into a small driver with RaspberryPi4/Lib/uart.pi4 for its sentences and a
HwPmfTargetId() that answers the chip the build is for (the board's own
answer - RaspberryPi4/Board/hw_id.pi4 - is 2711 / 2712 the same way), then
runs it under tools/a64/a64_interp.py through pi5_desk's Machine with the
container fields poked into the procedure's globals.

Mutation control: with the 2712 arm removed from pmfboot.pbi, the -t pi5
build must refuse 2712 and the gate must go red.

    py -3 tools/a64/pmfboot_2712_check.py --compiler PureMetalForge.exe
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import pi5_desk as d                                   # noqa: E402

REL = "Anvil/Core/pmfboot.pbi"
ARCH = 1        # read from the source below, checked


def lift(text: str) -> str:
    m = re.search(r"^Procedure\.i PmfCheckV2Metadata\(\)\n.*?^EndProcedure\n", text, re.M | re.S)
    if not m:
        d.die("pmfboot.pbi no longer has PmfCheckV2Metadata() at column 0")
    return m.group(0)


def consts(text: str) -> str:
    out = []
    for name in ("#PMF_ARCH_AARCH64", "#PMF_TARGET_BCM2837", "#PMF_TARGET_BCM2711",
                 "#PMF_TARGET_BCM2712", "#PMF_TARGET_QCM2290"):
        out.append("%s = %d" % (name, d.const_in(text, name, REL)))
    return "\n".join(out) + "\n"


def driver(text: str) -> str:
    return (
        "XIncludeFile \"RaspberryPi4/Lib/uart.pi4\"\n"
        + consts(text) +
        "Global gPmfReserved.i\nGlobal gPmfExtReservedOk.i\nGlobal gPmfArchitecture.i\n"
        "Global gPmfTarget.i\nGlobal gPmfStack.i\n"
        "Procedure PutAddr(a.i)\n  PrintDec(a)\nEndProcedure\n"
        "Procedure.i HwPmfTargetId()\n  ProcedureReturn #PMF_CHIP\nEndProcedure\n"
        + lift(text) +
        "Procedure.i Probe(target.i)\n"
        "  gPmfReserved = 0\n  gPmfExtReservedOk = 1\n  gPmfArchitecture = #PMF_ARCH_AARCH64\n"
        "  gPmfTarget = target\n  gPmfStack = $8000000\n"
        "  ProcedureReturn PmfCheckV2Metadata()\nEndProcedure\n"
        "Procedure Main()\n  If gPmfStack = -1          ; never: keeps Probe linked\n    Probe(0)\n  EndIf\nEndProcedure\nMain()\n")


def build(cc: str, text: str, chip: str, work: pathlib.Path):
    work.mkdir(parents=True, exist_ok=True)
    src = work / ("pmfboot_probe_%s.pi4" % chip)
    src.write_text(driver(text), encoding="utf-8")
    img = work / ("pmfboot_probe_%s.img" % chip)
    r = subprocess.run([cc, "--compile", str(src), "-t", chip, "--entry-returns",
                        "--load-addr", hex(d.LOAD), "--stack-addr", hex(d.STACK), "-o", str(img)],
                       cwd=str(ROOT), env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        d.die("the probe would not build for %s:\n%s%s" % (chip, r.stdout[-2500:], r.stderr[-800:]))
    procs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = d.LOAD + int(f[1])
    return img, procs


def device(addr, size, value):
    # Only the console PL011 is touched (RP1 UART0 on 2712): FR reads 0,
    # so every byte is taken; writes vanish.
    return 0


def gate(cc: str, text: str, work: pathlib.Path, verbose=True) -> int:
    fails = []
    for chip, good, bad in (("pi5", 2712, 2711), ("pi4", 2711, 2712)):
        img, procs = build(cc, text, chip, work)
        m = d.Machine(img, procs, device)
        for target, want in ((good, 1), (bad, 0), (2837, 0), (9999, 0)):
            got = m.signed(m.call("Probe", target))
            ok = (got == want)
            if verbose:
                print("  %s  -t %s monitor, container target %4d -> %d (want %d)"
                      % ("ok  " if ok else "FAIL", chip, target, got, want))
            if not ok:
                fails.append((chip, target, got, want))
    return len(fails)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    args = ap.parse_args()
    cc = d.compiler(args.compiler)
    work = ROOT / "_work" / "pmfboot_2712"
    text = (ROOT / REL).read_text(encoding="utf-8")
    try:
        n = gate(cc, text, work)
    except d.GateFail as e:
        print("pmfboot_2712_check: FAIL - %s" % e)
        return 1
    if n:
        print("pmfboot_2712_check: FAIL - %d admission case(s) wrong" % n)
        return 1
    # Mutation: the 2712 arm removed - the -t pi5 monitor must then refuse 2712.
    arm = re.search(r"  CompilerIf #PMF_CHIP = 2712\n    If gPmfTarget = #PMF_TARGET_BCM2712\n"
                    r"      knownTarget = 1\n    EndIf\n  CompilerEndIf\n", text)
    if not arm:
        print("pmfboot_2712_check: FAIL - the 2712 admission arm is not where the mutation expects it")
        return 1
    try:
        red = gate(cc, text.replace(arm.group(0), ""), work / "mutant", verbose=False)
    except d.GateFail as e:
        print("pmfboot_2712_check: FAIL - mutant would not run: %s" % e)
        return 1
    if red == 0:
        print("pmfboot_2712_check: FAIL - the mutant (2712 arm removed) still passed")
        return 1
    print("  mutant (2712 arm removed): %d case(s) red, as required" % red)
    print("pmfboot_2712_check: PASS - 8 admission cases on two chips, mutation red. Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
