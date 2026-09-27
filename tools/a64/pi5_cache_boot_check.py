#!/usr/bin/env python3
"""pi5_cache_boot_check.py - the Pi 5 boot's caches-on step, including its refusal, executed.

Builds the real RaspberryPi4/Board/board.pi4 -t pi5 and runs Pi5CachesOn
(board.pi4) under tools/a64/a64_interp.py:

  * as booted: CacheEnable succeeds, gCacheOn is 1, and nothing is printed;
  * with the adopted framebuffer moved above the first GiB (dsp_ready 1,
    dsp_base $5000_0000): MmuBuildTables refuses with #MMU_ERR_NC_HIGH,
    gCacheOn stays 0, Pi5CachesOn returns 0, and the console carries ONE
    sentence saying the caches are off and why (the non-cacheable region
    above the first GiB) - never a silent uncached boot.

It also requires Main to call Pi5CachesOn (not a bare CacheEnable) after
TouchBoot. MUTANTS (--mutants), each must go red: the refusal sentence
removed; the reason dropped; Main calling CacheEnable() directly.

The interpreter models no cache: SCTLR.M and the maintenance operations are
accepted and ignored, so this proves the decision and the message, not
coherence (tools/a64/a64_cache_2712_check.py walks the tables).

    py -3 tools/a64/pi5_cache_boot_check.py --compiler PureMetalForge.exe [--mutants]
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

MON_LOAD = 0x80000               # the Pi 5 firmware's load address = the link address
UART0 = 0x1F00030000
BOARD = "RaspberryPi4/Board/board.pi4"
# The Pi 5 monitor runs at EL3 under our stub. The register seeds are
# tools/a64/a64_cache_2712_check.py's: SCTLR_EL3 as the stub leaves it, a
# modelled two-level cache hierarchy for the set/way walk, DAIF masked.
SCTLR_EL3, SCTLR_STUB = 0xD51E1000, 0x30C50830
CLIDR, CCSIDR = 0xD5190020, 0xD5190000
CLIDR_VALUE = (2 << 24) | (4 << 3) | 3
CCSIDR_VALUE = (7 << 13) | (3 << 3) | 2


def build(cc, work: pathlib.Path, board_text: str):
    work.mkdir(parents=True, exist_ok=True)
    text = "\n".join(l for l in board_text.split("\n") if l.rstrip("\r") != "#PMF_CHIP = 2711")
    src = work / "board_pi5.pi4"
    src.write_text(text, encoding="utf-8")
    img = work / "anvil5.img"
    r = subprocess.run([cc, "--compile", str(src), "-t", "pi5", "-o", str(img)],
                       cwd=str(ROOT), env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        d.die("the -t pi5 monitor would not build:\n" + r.stdout[-2000:] + r.stderr[-600:])
    procs, syms = {}, {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = MON_LOAD + int(f[1])
    for line in pathlib.Path(str(img) + ".sym").read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                syms[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return img, procs, syms


class Board:
    """RP1 UART0 captured; any other device access answers 0 and is logged."""
    def __init__(self):
        self.tx = bytearray()
        self.other = []

    def __call__(self, addr, size, value):
        if UART0 <= addr < UART0 + 0x1000:
            off = addr - UART0
            if value is None:
                return 0x10 if off == 0x18 else 0
            if off == 0:
                self.tx.append(value & 0xFF)
            return 0
        self.other.append((addr, value))
        return 0


def g(syms, name):
    k = "global_" + name.lower()
    if k not in syms:
        d.die("the image has no global %s" % name)
    return syms[k]


def run(img, procs, syms, fb_high):
    d.LOAD = MON_LOAD
    b = Board()
    m = d.Machine(img, procs, b)
    m.cpu.enable_system_registers(el=3, preset={SCTLR_EL3: SCTLR_STUB, CLIDR: CLIDR_VALUE,
                                                CCSIDR: CCSIDR_VALUE, 0xD51B4220: 0x3C0})
    m.poke(g(syms, "gCacheOn"), (0).to_bytes(8, "little"))
    if fb_high:
        m.poke(g(syms, "dsp_ready"), (1).to_bytes(8, "little"))
        m.poke(g(syms, "dsp_base"), (0x50000000).to_bytes(8, "little"))
        m.poke(g(syms, "dsp_size"), (0x200000).to_bytes(8, "little"))
    rc = m.call("Pi5CachesOn", limit=300_000_000)
    on = int.from_bytes(m.peek(g(syms, "gCacheOn"), 8), "little")
    run.sctlr = m.cpu.system_registers.get(SCTLR_EL3, 0)
    return rc, on, b.tx.decode("ascii", "replace")


def gate(cc, work, board_text, quiet=False):
    fails = []

    def check(ok, what):
        if not quiet:
            print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    main = board_text[board_text.index("Procedure Main()"):]
    after = main[main.index("TouchBoot()"):]
    check(re.search(r"CompilerIf #PMF_CHIP = 2712\s+Pi5CachesOn\(\)", after[:600]) is not None,
          "Main calls Pi5CachesOn() on the 2712 after TouchBoot, not a bare CacheEnable()")
    img, procs, syms = build(cc, work, board_text)
    rc, on, out = run(img, procs, syms, fb_high=False)
    check(run.sctlr & 0x1005 == 0x1005,
          "as booted: SCTLR_EL3 has M, C and I set ($%X)" % run.sctlr)
    check(rc == 1 and on == 1 and "!!" not in out,
          "as booted: caches on (gCacheOn %d, returned %d), nothing printed (%r)" % (on, rc, out[:80]))
    rc, on, out = run(img, procs, syms, fb_high=True)
    check(run.sctlr == SCTLR_STUB, "framebuffer above 1 GiB: SCTLR_EL3 untouched ($%X)" % run.sctlr)
    check(rc == 0 and on == 0, "framebuffer above 1 GiB: CacheEnable refuses, gCacheOn stays 0 (%d, %d)" % (rc, on))
    check("caches are OFF" in out and "above the first GiB" in out and out.count("!!") == 1,
          "... and ONE sentence says the caches are off and why (%r)" % out.strip()[:200])
    if fails:
        d.die("%d check(s) red: %s" % (len(fails), fails[0]))


MUTANTS = [
    ("the refusal sentence removed", '    Print("!! the caches are OFF: ")\n', ""),
    ("the reason dropped",
     '          Print("a non-cacheable region (the framebuffer or a DMA buffer) lies above the first GiB, where the map has no 2 MiB split")\n',
     ""),
    ("Main calls CacheEnable() directly", "  CompilerIf #PMF_CHIP = 2712\n    Pi5CachesOn()\n",
     "  CompilerIf #PMF_CHIP = 2712\n    CacheEnable()\n"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()
    cc = d.compiler(args.compiler)
    text = (ROOT / BOARD).read_text(encoding="utf-8").replace("\r\n", "\n")
    work = ROOT / "_work" / "pi5_cache_boot"
    try:
        gate(cc, work, text)
    except d.GateFail as e:
        print("pi5_cache_boot_check: FAIL - %s" % e)
        return 1
    if args.mutants:
        survived = 0
        for i, (why, old, new) in enumerate(MUTANTS):
            if text.count(old) != 1:
                print("  %d  SURVIVED  %s (the edit matched %d times)" % (i, why, text.count(old)))
                survived += 1
                continue
            try:
                gate(cc, work / ("m%d" % i), text.replace(old, new), quiet=True)
            except d.GateFail as e:
                print("  %d  KILLED    %s (%s)" % (i, why, str(e).replace("\n", " ")[:110]))
                continue
            print("  %d  SURVIVED  %s" % (i, why))
            survived += 1
        print("mutants: %d killed, %d survived" % (len(MUTANTS) - survived, survived))
        if survived:
            print("pi5_cache_boot_check: FAIL - a mutant survived")
            return 1
    print("pi5_cache_boot_check: PASS - caches on at boot, and a refusal is one sentence with its reason. "
          "Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
