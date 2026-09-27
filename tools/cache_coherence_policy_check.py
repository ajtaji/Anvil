#!/usr/bin/env python3
"""Framebuffer coherence while the cache is on, and the DMA walk skip.

Two defects share one owner (RaspberryPi4/Board/cache.pi4) and one gate:

 1. A `screen` re-bring-up (screen_cmd.pi4 ScreenOn) or a V3D double-buffer
    request (v3d_console.pi4 V3dConTryDouble) re-runs DisplayInit with the
    cache ON. The firmware may hand back a new base; the live tables still
    mark only the OLD range Non-Cacheable, so the new surface was Write-Back
    and the display controller, V3D and the DMA engine read stale DRAM.
    Both chips. The fix, CacheDisplayMoved, tears the cache down and brings
    it back (CacheDisable = M|C|I off then clean+invalidate by set/way;
    CacheEnable = CacheMapNc sees the new base, tables rebuilt, TLB
    invalidated) - only when the new range is not already covered.
 2. dma.pi4's dc civac walk over every fill/copy rectangle buys nothing
    when the D-cache is off or the range is mapped Non-Cacheable (~16 ms of
    a ~23 ms full-screen clear on the Pi 5, 81802f4 --model). The board
    declares both through CacheDmaPolicy; the library default still walks.

The fixture executes the REAL procedures, cut from the sources:
cache.pi4 CacheMapNc/CacheDmaPolicy/CacheEnable/CacheDisable/
CacheDisplayMoved, mmu.pi4 MmuClearNc/MmuAddNc/mmu_BlockNc/MmuBuildTables
(the -t pi4 arm) and dma.pi4 DmaSetCacheOff/DmaClearUncached/DmaAddUncached/
dma_NeedsWalk/DmaCacheLines/DmaCacheRange/DmaCacheRect. Only the silicon
enable/disable are stubs, which record the order they were called in (their
own instruction sequence is a64_cache_2712_check's and a64_mmu_check's).
The interpreter counts every `dc civac` the walk issues. The callers are
checked in the source: every DisplayInit in screen_cmd.pi4 and
v3d_console.pi4 is followed by CacheDisplayMoved(), and ScreenDmaUp calls
CacheDmaPolicy() once the engine is up.

--mutate: remap removed (the new framebuffer stays cacheable), remap without
teardown, the walk skipped with the cache ON, a stale Non-Cacheable range
kept after a move, the cache-off skip ignored, the screen_cmd call removed,
the boot policy call removed. Desk only.
  py -3 -B tools/cache_coherence_policy_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

CACHE = "RaspberryPi4/Board/cache.pi4"
MMU = "RaspberryPi4/Lib/mmu.pi4"
DMA = "RaspberryPi4/Lib/dma.pi4"
MEMMAP = "RaspberryPi4/Board/memmap.pi4"
SCREEN = "RaspberryPi4/Board/screen_cmd.pi4"
V3DCON = "RaspberryPi4/Board/v3d_console.pi4"
BDISPLAY = "RaspberryPi4/Board/display.pi4"

LOAD, BSS, STACK, RETURN = 0x400000, 0x800000, 0x3000000, 0xDEAD0000
TABLE = 0xA00000
NC, WB = 0x70D, 0x711
FB_A, FB_B, FB_C, FB_SIZE = 0x10000000, 0x20000000, 0x28000000, 0x800000
BUF = 0x30000000                        # an ordinary Write-Back buffer
LINES_64K = 0x10000 // 64


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A = _load("ccp_a64", ROOT / "tools/a64/a64_interp.py")


class Fail(Exception):
    pass


def proc(text, name):
    m = re.search(rf"(?ms)^Procedure(?:\.i)? {name}\([^\n]*\)\n.*?^EndProcedure", text)
    if not m:
        raise Fail("missing real procedure " + name)
    return m.group(0)


def const(text, name):
    m = re.search(rf"(?m)^#{name}\s*=.*$", text)
    if not m:
        raise Fail("missing real constant " + name)
    return m.group(0)


def fixture(src):
    mmu, memmap, dma, cache = src[MMU], src[MEMMAP], src[DMA], src[CACHE]
    names = ("MMU_ATTR_DEVICE", "MMU_ATTR_NORMAL_NC", "MMU_DRAM_ATTR", "MMU_DESC_TABLE",
             "MMU_DESC_FAULT", "MMU_L1_ENTRIES", "MMU_L2_ENTRIES", "MMU_TABLE_BYTES",
             "MMU_SPLIT_SLOT", "MMU_PERIPH_BASE", "MMU_PCIE_SLOT_LO", "MMU_PCIE_SLOT_HI",
             "MMU_ERR_NULL", "MMU_ERR_ALIGN", "MMU_ERR_LOW", "MMU_NC_MAX", "MMU_TCR_EL2",
             "MMU_MAIR_EL2")
    fb = ("MON_FB_LO", "MON_FB_HI", "MON_FB_SCAN", "MON_FB_DRAW", "MON_FB_BYTES")
    return ("EnableExplicit\n" + "\n".join(const(mmu, n) for n in names) + "\n"
            + "\n".join(const(memmap, n) for n in fb) + "\n"
            + const(dma, "DMA_CACHE_LINE") + "\n" + const(dma, "DMA_NC_MAX") + "\n"
            + "#ANVIL_CACHE = 1\n"
            "Global Dim mmu_ncLo.i[#MMU_NC_MAX]\nGlobal Dim mmu_ncHi.i[#MMU_NC_MAX]\n"
            "Global mmu_ncN.i\nGlobal mmu_ttbr.i\nGlobal mmu_tcr.i\nGlobal mmu_mair.i\n"
            "Global gCacheOn.i\nGlobal gCacheDspLo.i\nGlobal gCacheDspHi.i\n"
            "Global dma_walklo.i\nGlobal dma_walkhi.i\nGlobal dma_cacheOff.i\n"
            "Global Dim dma_ncLo.i[#DMA_NC_MAX]\nGlobal Dim dma_ncHi.i[#DMA_NC_MAX]\nGlobal dma_ncN.i\n"
            "Global tReady.i\nGlobal tBase.i\nGlobal tSize.i\n"
            "Global gEvN.i\nGlobal Dim gEv.i[64]\n"
            "Procedure Ev(code.i)\n  If gEvN < 64\n    gEv[gEvN] = code\n    gEvN = gEvN + 1\n  EndIf\nEndProcedure\n"
            "Procedure.i DisplayReady()\n ProcedureReturn tReady\nEndProcedure\n"
            "Procedure.i DisplayBase()\n ProcedureReturn tBase\nEndProcedure\n"
            "Procedure.i DisplaySize()\n ProcedureReturn tSize\nEndProcedure\n"
            "Procedure.i MmuBuildable()\n ProcedureReturn 1\nEndProcedure\n"
            "Procedure.i CacheTablesBase()\n ProcedureReturn $A00000\nEndProcedure\n"
            "Procedure MmuEnableCached()\n Ev(1)\nEndProcedure\n"
            "Procedure MmuDisableCachedFlushed()\n Ev(2)\nEndProcedure\n"
            + "\n".join(proc(mmu, n) for n in ("MmuClearNc", "MmuAddNc", "mmu_BlockNc", "MmuBuildTables"))
            + "\n" + "\n".join(proc(dma, n) for n in ("DmaSetCacheOff", "DmaClearUncached", "DmaAddUncached",
                                                        "dma_NeedsWalk", "DmaCacheLines", "DmaCacheRange",
                                                        "DmaCacheRect"))
            + "\n" + "\n".join(proc(cache, n) for n in ("CacheMapNc", "CacheDmaPolicy", "CacheEnable",
                                                          "CacheDisable", "CacheDisplayMoved"))
            + r"""
Procedure.i Op(op.i, a.i, b.i)
  Select op
    Case 1
      tReady = Bool(a <> 0)
      tBase = a
      tSize = b
    Case 2
      ProcedureReturn CacheEnable()
    Case 3
      CacheDisable()
    Case 4
      CacheDisplayMoved()
    Case 5
      DmaCacheRange(a, b)
    Case 6
      DmaCacheRect(a, 4096, 1024, b)
    Case 7
      ProcedureReturn PeekI($A00000 + 8192 + ((a >> 21) << 3))
    Case 8
      ProcedureReturn gEvN
    Case 9
      ProcedureReturn gEv[a]
    Case 10
      ProcedureReturn gCacheOn
    Case 11
      CacheDmaPolicy()
  EndSelect
  ProcedureReturn 0
EndProcedure
Procedure.i Main()
  ProcedureReturn Op(0, 0, 0)
EndProcedure
""")


def build(compiler, work, name, src):
    s, img = work / (name + ".pi4"), work / (name + ".img")
    s.write_text(fixture(src), encoding="utf-8")
    r = subprocess.run([str(compiler), "--compile", str(s), "-t", "pi4", "-s", "--entry-returns",
                        "--load-addr", hex(LOAD), "--bss-addr", hex(BSS), "--stack-addr", hex(STACK),
                        "-o", str(img)], cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True, timeout=300)
    if r.returncode or not img.exists():
        raise Fail("fixture compile failed\n" + (r.stdout + r.stderr)[-2500:])
    entries = {}
    for line in Path(str(img) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        f = line.split("|")
        if len(f) >= 4 and f[0] == "1" and f[1].isdigit():
            entries[f[2].lower()] = LOAD + int(f[1])
    if "op" not in entries:
        raise Fail("fixture has no Op entry in its .dbg")
    return img.read_bytes(), entries["op"]


class Machine:
    def __init__(self, product):
        blob, self.entry = product
        self.cpu = A.A64()
        self.cpu.memory = {LOAD + i: b for i, b in enumerate(blob)}

    def op(self, op, a=0, b=0):
        cpu = self.cpu
        cpu.pc, cpu.sp, cpu.x[30] = self.entry, STACK, RETURN
        cpu.x[0], cpu.x[1], cpu.x[2] = op, a, b
        civac = 0
        for _ in range(5_000_000):
            if cpu.pc == RETURN:
                return cpu.x[0], civac
            ins = cpu.fetch(cpu.pc)
            if (ins & 0xFFFFFFE0) == 0xD50B7E20:        # dc civac, xN
                civac += 1
            cpu.step()
        raise Fail(f"Op({op}) did not return")

    def events(self):
        n = self.op(8)[0]
        return [self.op(9, i)[0] for i in range(n)]


def desc(addr, attr):
    return (addr & ~0x1FFFFF) | attr


def scenarios(product):
    errs = []

    def want(label, got, exp):
        if got != exp:
            errs.append(f"{label}: got {got if not isinstance(got, int) else hex(got)}, "
                        f"want {exp if not isinstance(exp, int) else hex(exp)}")

    m = Machine(product)
    # S0: the library default, no policy declared - walk as before.
    want("default: 64 KiB range walked", m.op(5, FB_A, 0x10000)[1], LINES_64K)
    # S1: boot, cache off - nothing to walk.
    m.op(11)
    want("cache off: 64 KiB range", m.op(5, FB_A, 0x10000)[1], 0)
    want("cache off: 8-row rectangle", m.op(6, BUF, 8)[1], 0)
    # S2: HDMI framebuffer A, cache on.
    m.op(1, FB_A, FB_SIZE)
    want("enable", m.op(2)[0], 1)
    want("enable events", m.events(), [1])
    want("framebuffer A Non-Cacheable", m.op(7, FB_A)[0], desc(FB_A, NC))
    want("cache on: range inside framebuffer A", m.op(5, FB_A + 0x1000, 0x10000)[1], 0)
    want("cache on: Write-Back buffer range walked", m.op(5, BUF, 0x10000)[1], LINES_64K)
    want("cache on: Write-Back rectangle walked", m.op(6, BUF, 8)[1], 8 * (1024 // 64))
    # S3: DisplayInit handed back the same surface - no churn.
    m.op(4)
    want("same surface: no teardown", m.events(), [1])
    # S4: DisplayInit moved the surface to B while the cache is on.
    m.op(1, FB_B, FB_SIZE)
    m.op(4)
    want("moved surface: teardown then rebuild", m.events(), [1, 2, 1])
    want("moved surface: cache back on", m.op(10)[0], 1)
    want("framebuffer B Non-Cacheable after the move", m.op(7, FB_B)[0], desc(FB_B, NC))
    want("framebuffer B end Non-Cacheable", m.op(7, FB_B + FB_SIZE - 64)[0], desc(FB_B + FB_SIZE - 64, NC))
    want("old framebuffer A Write-Back again", m.op(7, FB_A)[0], desc(FB_A, WB))
    want("cache on: range inside framebuffer B skipped", m.op(5, FB_B, 0x10000)[1], 0)
    want("cache on: old framebuffer A walked", m.op(5, FB_A, 0x10000)[1], LINES_64K)
    # S5: a move inside the fixed DSI band - already Non-Cacheable, no churn.
    m.op(1, _MON["MON_FB_DRAW"], _MON["MON_FB_BYTES"])
    m.op(4)
    want("DSI band surface: no teardown", m.events(), [1, 2, 1])
    # S6: cache off, surface moves - nothing to remap, nothing to walk.
    m.op(3)
    want("disable event", m.events(), [1, 2, 1, 2])
    m.op(1, FB_C, FB_SIZE)
    m.op(4)
    want("cache off: a move does not enable", m.events(), [1, 2, 1, 2])
    want("cache off: stays off", m.op(10)[0], 0)
    want("cache off after disable: range", m.op(5, BUF, 0x10000)[1], 0)
    # S7: not ready - nothing.
    m.op(2)
    m.op(1, 0, 0)
    before = m.events()
    m.op(4)
    want("display not ready: no teardown", m.events(), before)
    return errs


_MON = {}          # memmap.pi4's DSI band constants, read in main()


def callers(src):
    errs = []
    for rel in (SCREEN, V3DCON):
        lines = src[rel].replace("\r\n", "\n").split("\n")
        for i, line in enumerate(lines):
            if re.match(r"\s*DisplayInit\(", line):
                follow = [l for l in lines[i + 1:i + 6] if l.strip() and not l.strip().startswith(";")]
                if not any(l.strip().startswith("CacheDisplayMoved()") for l in follow[:2]):
                    errs.append(f"{rel}:{i + 1}: DisplayInit is not followed by CacheDisplayMoved()")
    body = proc(src[BDISPLAY], "ScreenDmaUp")
    at_init, at_pol = body.find("If DmaInit() = 0"), body.find("CacheDmaPolicy()")
    if at_pol < 0 or at_pol < at_init:
        errs.append("ScreenDmaUp does not call CacheDmaPolicy() after DmaInit")
    for name in ("CacheEnable", "CacheDisable"):
        if "CacheDmaPolicy()" not in proc(src[CACHE], name):
            errs.append(f"{name} does not refresh CacheDmaPolicy()")
    return errs


def run_all(compiler, work, name, src):
    try:
        errs = callers(src)
        errs += scenarios(build(compiler, work, name, src))
    except Fail as e:
        errs = [str(e)]
    return errs


def sub(src, rel, old, new, proc_name=None):
    t = src[rel]
    if proc_name:
        body = proc(t, proc_name)
        if body.count(old) != 1:
            raise Fail(f"mutant anchor not unique in {proc_name}: {old!r}")
        t = t.replace(body, body.replace(old, new, 1), 1)
    else:
        if t.count(old) != 1:
            raise Fail(f"mutant anchor not unique in {rel}: {old!r}")
        t = t.replace(old, new, 1)
    return dict(src, **{rel: t})


MUTANTS = [
    ("remap removed - the new framebuffer stays cacheable",
     lambda s: sub(s, CACHE, "  CacheDisable()\n  CacheEnable()\n", "", "CacheDisplayMoved")),
    ("remap without teardown (CacheEnable alone is a no-op while on)",
     lambda s: sub(s, CACHE, "  CacheDisable()\n  CacheEnable()\n", "  CacheEnable()\n", "CacheDisplayMoved")),
    ("walk skipped with the cache ON",
     lambda s: sub(s, CACHE, "DmaSetCacheOff(0)", "DmaSetCacheOff(1)", "CacheDmaPolicy")),
    ("stale Non-Cacheable range kept after a move",
     lambda s: sub(s, CACHE, "  DmaClearUncached()\n", "", "CacheDmaPolicy")),
    ("cache-off skip ignored",
     lambda s: sub(s, DMA, "If dma_cacheOff <> 0", "If 0", "dma_NeedsWalk")),
    ("screen_cmd re-bring-up does not remap",
     lambda s: sub(s, SCREEN, "  CacheDisplayMoved()\n  BootTimingMark(", "  BootTimingMark(")),
    ("boot policy call removed",
     lambda s: sub(s, BDISPLAY, "  CacheDmaPolicy()\n", "", "ScreenDmaUp")),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    src = {rel: (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
           for rel in (CACHE, MMU, DMA, MEMMAP, SCREEN, V3DCON, BDISPLAY)}
    for n in ("MON_FB_DRAW", "MON_FB_BYTES"):
        v = const(src[MEMMAP], n).split("=", 1)[1].split(";")[0].strip()
        _MON[n] = int(v.replace("$", "0x"), 16) if v.startswith("$") else int(v, 0)
    rc = 0
    with tempfile.TemporaryDirectory(prefix="cache-coherence-") as td:
        work = Path(td)
        errs = run_all(compiler, work, "fixed", src)
        for e in errs:
            print("FAIL", e)
        print(f"cache_coherence_policy_check: 7 scenarios + caller checks, {len(errs)} failure(s)")
        rc = 1 if errs else 0
        if a.mutate:
            killed = 0
            for i, (label, fn) in enumerate(MUTANTS):
                try:
                    merr = run_all(compiler, work, f"m{i}", fn(src))
                except Fail as e:
                    merr = [str(e)]
                killed += bool(merr)
                print(f"MUTANT {label}: {'killed' if merr else 'SURVIVED'}"
                      + (f" ({merr[0][:110]})" if merr else ""))
            print(f"mutants: {killed}/{len(MUTANTS)} killed")
            rc |= 0 if killed == len(MUTANTS) else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
