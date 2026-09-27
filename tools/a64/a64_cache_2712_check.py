#!/usr/bin/env python3
"""Desk gate for turning the MMU and D-cache on for the BCM2712 (Pi 5, EL3).

Builds RaspberryPi5/Tests/cache2712_probe.pi5 (-t pi5) - the exact sequence
cache.pi4's CacheEnable() runs on a 2712 build: MmuSetRamBytes, the
framebuffer MmuAddNc, MmuBuildTables, MmuEnableCached - and runs it in
tools/a64/a64_interp.py with the system-register model at EL3 (Anvil's
level on the Pi 5, RaspberryPi5/Board/armstub8-2712.asm) and again at EL2.
Every cache/TLB maintenance instruction and every MSR is recorded in order.

Checked:
  THE SEQUENCE (RaspberryPi4/Lib/mmu.pi4 MmuEnableCached, U-Boot's order):
    * the D-cache is invalidated by set/way (`dc isw`) over every data or
      unified level CLIDR names up to LoC, all sets x all ways, BEFORE
      anything else - the reset-state lines are UNKNOWN (mmu.pi4:1810-1830,
      proven necessary on the Pi 4 2026-08-29);
    * then `tlbi alle3`, then TTBR0/TCR/MAIR, then `ic iallu`, then SCTLR;
    * at EL3 ONLY the _EL3 registers are written (no _EL2 write at all), at
      EL2 only the _EL2 ones;
    * TTBR0 = the level-0 table, TCR = $80823518, MAIR = $FF440C0400, and
      SCTLR = the stub's value | M | C | I ($1005), every other bit kept;
    * with the disable leg: SCTLR loses M|C|I FIRST, then the whole D-cache
      is cleaned+invalidated by set/way (`dc cisw`), then the TLB.
  THE TABLES the TTBR points at, walked as the hardware walks them (the
  walker is tools/a64/a64_mmu_2712_check.py's): the framebuffer Normal-NC,
  low-GiB RAM and RAM up to MmuSetRamBytes Normal-WB, the SoC (GIC, PM, V3D,
  SD, SDIO2) and the RP1 window Device-nGnRnE, nothing Normal at or above
  $10_0000_0000.

--mutate: framebuffer cacheable, device memory Normal, TLB invalidate
removed, invalidate-before-enable removed, EL2 registers on the EL3 path.

Desk only: the interpreter has no caches and no translation, so this proves
the program the A76 is given, not the A76's answer.
  py -3 -B tools/a64/a64_cache_2712_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB_REL = pathlib.Path("RaspberryPi4/Lib/mmu.pi4")
DEF_REL = pathlib.Path("RaspberryPi4/Intrinsics/bcm2711_hardware.def")
PROBE_REL = pathlib.Path("RaspberryPi5/Tests/cache2712_probe.pi5")

LOAD, STACK, LR = 0x400000, 0x3000000, 0xDEAD0000
IN = 0x5F0000
TABLES = 0x600000
GiB = 1 << 30
FB_LO, FB_HI = 0x3F800000, 0x3F800000 + 1920 * 1080 * 2
SCTLR_STUB = 0x30C50830

# MSR write bases (op0 3): SCTLR/TTBR0/TCR/MAIR at EL3 and EL2.
EL3 = {"sctlr": 0xD51E1000, "ttbr0": 0xD51E2000, "tcr": 0xD51E2040, "mair": 0xD51EA200}
EL2 = {"sctlr": 0xD51C1000, "ttbr0": 0xD51C2000, "tcr": 0xD51C2040, "mair": 0xD51CA200}
CLIDR, CCSIDR, CSSELR = 0xD5190020, 0xD5190000, 0xD51A0000
# A modelled hierarchy: L1 split I+D (Ctype 3), L2 unified (4), LoC 2;
# every level 4 ways x 8 sets of 64-byte lines (CCSIDR no-CCIDX layout).
CLIDR_VALUE = (2 << 24) | (4 << 3) | 3
CCSIDR_VALUE = (7 << 13) | (3 << 3) | 2
SETWAY_OPS = 2 * 8 * 4

WANT_TCR = 0x80823518
WANT_MAIR = 0xFF440C0400


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A = _load("cache2712_a64", ROOT / "tools/a64/a64_interp.py")
W = _load("cache2712_walk", ROOT / "tools/a64/a64_mmu_2712_check.py")


class Fail(Exception):
    pass


def build(root, compiler, out):
    r = subprocess.run([compiler, "--compile", str(root / PROBE_REL), "-t", "pi5", "--entry-returns",
                        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), capture_output=True, text=True)
    if r.returncode or not out.exists() or "target BCM2712" not in r.stdout:
        raise Fail("build failed\n" + r.stdout[-1500:] + r.stderr)
    return out


def sys_name(ins):
    if (ins & 0xFFF80000) != 0xD5080000:
        return None
    key = ((((ins >> 16) & 7) << 12) | (((ins >> 12) & 15) << 8)
           | (((ins >> 8) & 15) << 4) | ((ins >> 5) & 7))
    return A.SYS_MAINTENANCE.get(key)


def run(img, el, ram, disable):
    cpu = A.A64()
    mem = cpu.memory
    for i, b in enumerate(img.read_bytes()):
        mem[LOAD + i] = b

    def put(a, v):
        for i in range(8):
            mem[a + i] = (v >> (8 * i)) & 0xFF
    for off, v in ((0, ram), (8, FB_LO), (16, FB_HI), (24, TABLES), (32, int(disable))):
        put(IN + off, v)
    regs = EL3 if el == 3 else EL2
    cpu.enable_system_registers(el=el, preset={regs["sctlr"]: SCTLR_STUB, CLIDR: CLIDR_VALUE,
                                               CCSIDR: CCSIDR_VALUE, 0xD51B4220: 0x3C0})
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LR
    events = []
    for _ in range(20_000_000):
        if cpu.pc == LR:
            break
        ins = cpu.fetch(cpu.pc)
        name = sys_name(ins)
        if name:
            events.append((name, cpu.x[ins & 31] if ins & 31 != 31 else 0))
        elif (ins & 0xFFF00000) == 0xD5100000:          # MSR (register)
            base = ins & 0xFFFFFFE0
            rt = ins & 31
            events.append(("msr", base, cpu.x[rt] if rt != 31 else 0))
        cpu.step()
    else:
        raise Fail("the probe did not return")
    rc = cpu.x[0] - (1 << 64) if cpu.x[0] >> 63 else cpu.x[0]

    def rd(a):
        return sum(mem.get(a + i, 0) << (8 * i) for i in range(8))
    return rc, events, rd, cpu


def idx(events, pred, start=0):
    for i in range(start, len(events)):
        if pred(events[i]):
            return i
    return -1


def check(img, el, ram, disable, label):
    errs = []
    rc, ev, rd, cpu = run(img, el, ram, disable)
    tag = f"{label} EL{el}"
    if rc != 0:
        return [f"{tag}: MmuBuildTables returned {rc}"]
    regs, other = (EL3, EL2) if el == 3 else (EL2, EL3)
    msr = lambda k: (lambda e: e[0] == "msr" and e[1] == regs[k])
    first_isw = idx(ev, lambda e: e[0] == "dc isw")
    isw = [e for e in ev if e[0] == "dc isw"]
    tlbi = idx(ev, lambda e: e[0] == f"tlbi alle{el}")
    ttbr, tcr, mair = idx(ev, msr("ttbr0")), idx(ev, msr("tcr")), idx(ev, msr("mair"))
    icu = idx(ev, lambda e: e[0] == "ic iallu")
    sctlr = idx(ev, msr("sctlr"))
    if len(isw) != SETWAY_OPS:
        errs.append(f"{tag}: {len(isw)} dc isw operations, the modelled hierarchy needs {SETWAY_OPS}")
    # The operands themselves: level<<1 | way<<clz(ways-1) | set<<log2(line),
    # 4 ways -> way shift 30, 64-byte lines -> set shift 6. Every (level, set,
    # way) exactly once - a wrong shift aliases lines and leaves some dirty.
    want_ops = {(lv << 1) | (w << 30) | (st << 6) for lv in (0, 1) for w in range(4) for st in range(8)}
    if {e[1] for e in isw} != want_ops:
        errs.append(f"{tag}: the set/way operands do not cover each (level, set, way) once")
    if min(first_isw, tlbi, ttbr, tcr, mair, icu, sctlr) < 0:
        errs.append(f"{tag}: a step is missing (isw {first_isw}, tlbi {tlbi}, ttbr {ttbr}, tcr {tcr}, "
                    f"mair {mair}, ic {icu}, sctlr {sctlr})")
    elif not (first_isw < tlbi < ttbr < tcr < mair < icu < sctlr):
        errs.append(f"{tag}: wrong order (isw {first_isw}, tlbi {tlbi}, ttbr {ttbr}, tcr {tcr}, "
                    f"mair {mair}, ic {icu}, sctlr {sctlr})")
    elif max(i for i, e in enumerate(ev) if e[0] == "dc isw") > tlbi:
        errs.append(f"{tag}: set/way invalidate still running after the TLB invalidate")
    written = {e[1] for e in ev if e[0] == "msr"}
    if written & set(other.values()):
        errs.append(f"{tag}: wrote the EL{5 - el} translation registers "
                    f"{sorted(hex(k) for k in written & set(other.values()))}")
    if sctlr >= 0 and ev[sctlr][2] != SCTLR_STUB | 0x1005:
        errs.append(f"{tag}: SCTLR written ${ev[sctlr][2]:X}, want ${SCTLR_STUB | 0x1005:X}")
    if tcr >= 0 and ev[tcr][2] != WANT_TCR:
        errs.append(f"{tag}: TCR ${ev[tcr][2]:X}, want ${WANT_TCR:X}")
    if mair >= 0 and ev[mair][2] != WANT_MAIR:
        errs.append(f"{tag}: MAIR ${ev[mair][2]:X}, want ${WANT_MAIR:X}")
    if disable:
        s2 = idx(ev, msr("sctlr"), sctlr + 1)
        cisw = idx(ev, lambda e: e[0] == "dc cisw", sctlr + 1)
        n_cisw = sum(1 for e in ev[sctlr + 1:] if e[0] == "dc cisw")
        if s2 < 0 or ev[s2][2] & 0x1005:
            errs.append(f"{tag}: the disable did not clear M|C|I")
        elif cisw < s2:
            errs.append(f"{tag}: the set/way clean ran before C was cleared")
        if n_cisw != SETWAY_OPS:
            errs.append(f"{tag}: {n_cisw} dc cisw operations on disable, want {SETWAY_OPS}")
    if ttbr < 0 or tcr < 0:
        return errs

    # Walk the tables the TTBR hands the hardware.
    t, tc = ev[ttbr][2], ev[tcr][2]

    def kind(a):
        w = W.walk(rd, t, tc, a)
        if w is None:
            return None
        pa, attr, _ = w
        if pa != a:
            raise Fail(f"{tag}: ${a:X} translates to ${pa:X}")
        return W.KIND.get(W.MAIR_BYTE.get(attr), f"attr{attr}")
    want = [("framebuffer $3F800000", FB_LO, "Normal-NC"),
            ("framebuffer end", FB_HI - 64, "Normal-NC"),
            ("EL3 stub $0", 0x0, "Normal-WB"), ("image $200000", 0x200000, "Normal-WB"),
            ("BSS/tables $0D000000", 0x0D000000, "Normal-WB"), ("DTB $2EFEC600", 0x2EFEC600, "Normal-WB"),
            ("RAM just below the top", ram - 0x1000 if ram >= GiB else GiB - 0x1000, "Normal-WB"),
            ("first byte past RAM", max(ram, GiB), None)]
    want += [(name, a, "Device-nGnRnE") for name, a in W.DEVICE_ADDRS.items()]
    for name, a, k in want:
        got = kind(a)
        if got != k:
            errs.append(f"{tag}: {name} (${a:X}) is {got}, want {k}")
    for g in range(64, 512):
        got = kind(g * GiB)
        if got not in (None, "Device-nGnRnE"):
            errs.append(f"{tag}: GiB {g} is {got} - nothing at or above the SoC may be Normal")
            break
    return errs


def scenarios(img):
    errs = []
    for el in (3, 2):
        errs += check(img, el, 8 * GiB, False, "8 GiB, enable")
    errs += check(img, 3, 4 * GiB, True, "4 GiB, enable then payload-jump disable")
    errs += check(img, 3, 0, False, "no /memory (1 GiB default)")
    return errs


def _nth(text, old, new, n):
    at = -1
    for _ in range(n):
        at = text.find(old, at + 1)
        if at < 0:
            raise Fail(f"mutant pattern {old[:40]!r} occurrence {n} not found")
    return text[:at] + new + text[at + len(old):]


def _proc(text, name):
    s = text.index(f"Procedure {name}()")
    return s, text.index("EndProcedure", s)


def m_fb_cacheable(t):
    s = t.index("CompilerElse\nProcedure.i MmuBuildTables(base.i)")
    body = t[s:]
    old = "    If mmu_BlockNc(pa) <> 0\n      d = pa | #MMU_ATTR_NORMAL_NC\n"
    new = "    If 0\n      d = pa | #MMU_ATTR_NORMAL_NC\n"
    return t[:s] + body.replace(old, new, 1)


def m_device_normal(t):
    s = t.index("CompilerElse\nProcedure.i MmuBuildTables(base.i)")
    body = t[s:]
    old = "    ElseIf i >= #MMU_SOC_SLOT_LO And i <= #MMU_SOC_SLOT_HI\n      d = pa | #MMU_ATTR_DEVICE\n"
    new = "    ElseIf i >= #MMU_SOC_SLOT_LO And i <= #MMU_SOC_SLOT_HI\n      d = pa | #MMU_DRAM_ATTR\n"
    if old not in body:
        raise Fail("device-slot pattern not found")
    return t[:s] + body.replace(old, new, 1)


def m_no_tlbi(t):
    s, e = _proc(t, "MmuEnableCached")
    body = t[s:e]
    if body.count("tlbi alle3") != 1:
        raise Fail("tlbi alle3 not unique in MmuEnableCached")
    return t[:s] + body.replace("      tlbi alle3\n", "", 1) + t[e:]


def m_no_invalidate(t):
    s, e = _proc(t, "MmuEnableCached")
    body = t[s:e]
    old = "    MmuInvalidateDCacheAll()\n"
    if body.count(old) != 1:
        raise Fail("invalidate call not unique in MmuEnableCached")
    return t[:s] + body.replace(old, "", 1) + t[e:]


def m_el2_on_el3(t):
    s, e = _proc(t, "MmuEnableCached")
    body = t[s:e]
    if body.count("If MmuAtEl3() <> 0") != 1:
        raise Fail("EL3 choice not unique in MmuEnableCached")
    return t[:s] + body.replace("If MmuAtEl3() <> 0", "If 0", 1) + t[e:]


MUTANTS = [("framebuffer cacheable", m_fb_cacheable), ("device memory as Normal", m_device_normal),
           ("TLB invalidate removed", m_no_tlbi), ("invalidate-before-enable removed", m_no_invalidate),
           ("EL2 registers on the EL3 path", m_el2_on_el3)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    rc = 0
    with tempfile.TemporaryDirectory(prefix="cache2712-") as td:
        td = pathlib.Path(td)
        try:
            errs = scenarios(build(ROOT, compiler, td / "probe.img"))
        except Fail as e:
            errs = [str(e)]
        for e in errs:
            print("FAIL", e)
        print(f"a64_cache_2712_check: 4 runs (EL3, EL2, disable leg, default RAM), {len(errs)} failure(s)")
        rc = 1 if errs else 0
        if a.mutate:
            src = (ROOT / LIB_REL).read_text(encoding="utf-8").replace("\r\n", "\n")
            killed = 0
            for i, (label, fn) in enumerate(MUTANTS):
                mroot = td / f"m{i}"
                for rel in (LIB_REL, DEF_REL, PROBE_REL):
                    (mroot / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / rel, mroot / rel)
                try:
                    (mroot / LIB_REL).write_text(fn(src), encoding="utf-8")
                    merr = scenarios(build(mroot, compiler, td / f"m{i}.img"))
                except Fail as e:
                    merr = [str(e)]
                killed += bool(merr)
                print(f"MUTANT {label}: {'killed' if merr else 'SURVIVED'}"
                      + (f" ({merr[0][:110]})" if merr else ""))
            print(f"mutants: {killed}/{len(MUTANTS)} killed")
            if killed != len(MUTANTS):
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
