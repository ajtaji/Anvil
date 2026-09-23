#!/usr/bin/env python3
"""Check emitted Pi 4 page descriptors for the board-owned cache map.

The fixture executes the real CacheMapNc and MmuBuildTables procedures.  The
silicon enable procedure is deliberately absent, so no system-register or
hardware operation can execute.  This is an offline page-table proof only.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

import build as anvil_build
import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "RaspberryPi4/Board/cache.pi4"
MMU = ROOT / "RaspberryPi4/Lib/mmu.pi4"
MEMMAP = ROOT / "RaspberryPi4/Board/memmap.pi4"
LOAD, BSS, STACK = 0x400000, 0x800000, 0x3000000
TABLE, RETURN = 0xA00000, 0xDEAD0000
NC, WB = 0x70D, 0x711


def proc(text: str, name: str) -> str:
    found = re.search(rf"(?ms)^Procedure(?:\.i)? {name}\([^\n]*\)\n.*?^EndProcedure", text)
    if not found:
        raise AssertionError("missing real procedure " + name)
    return found.group(0)


def constant(text: str, name: str) -> str:
    found = re.search(rf"(?m)^#{name}\s*=.*$", text)
    if not found:
        raise AssertionError("missing real constant " + name)
    return found.group(0)


def fixture(cache: str) -> str:
    mmu = MMU.read_text(encoding="utf-8")
    memmap = MEMMAP.read_text(encoding="utf-8")
    names = ("MMU_ATTR_DEVICE", "MMU_ATTR_NORMAL_NC", "MMU_DRAM_ATTR",
             "MMU_DESC_TABLE", "MMU_DESC_FAULT", "MMU_L1_ENTRIES",
             "MMU_L2_ENTRIES", "MMU_TABLE_BYTES", "MMU_SPLIT_SLOT",
             "MMU_PERIPH_BASE", "MMU_PCIE_SLOT_LO", "MMU_PCIE_SLOT_HI",
             "MMU_ERR_NULL", "MMU_ERR_ALIGN", "MMU_ERR_LOW", "MMU_NC_MAX",
             "MMU_TCR_EL2", "MMU_MAIR_EL2")
    fb = ("MON_FB_LO", "MON_FB_HI", "MON_FB_SCAN", "MON_FB_DRAW", "MON_FB_BYTES")
    procedures = ("MmuClearNc", "MmuAddNc", "mmu_BlockNc", "MmuBuildTables")
    return ("EnableExplicit\n" + "\n".join(constant(mmu, n) for n in names) +
            "\n" + "\n".join(constant(memmap, n) for n in fb) + "\n" +
            "#ANVIL_CACHE = 1\n"
            "Global Dim mmu_ncLo.i[#MMU_NC_MAX]\nGlobal Dim mmu_ncHi.i[#MMU_NC_MAX]\n"
            "Global mmu_ncN.i\nGlobal mmu_ttbr.i\nGlobal mmu_tcr.i\nGlobal mmu_mair.i\n"
            "Global gCacheOn.i\n"
            "Global testReady.i\nGlobal testBase.i\nGlobal testSize.i\n"
            "Procedure.i DisplayReady()\n ProcedureReturn testReady\nEndProcedure\n"
            "Procedure.i DisplayBase()\n ProcedureReturn testBase\nEndProcedure\n"
            "Procedure.i DisplaySize()\n ProcedureReturn testSize\nEndProcedure\n" +
            "Procedure.i MmuBuildable()\n ProcedureReturn 1\nEndProcedure\n"
            "Procedure.i CacheTablesBase()\n ProcedureReturn $A00000\nEndProcedure\n"
            "Procedure MmuEnableCached()\nEndProcedure\n" +
            "\n\n".join(proc(mmu, n) for n in procedures) + "\n" + proc(cache, "CacheMapNc") + r'''
''' + proc(cache, "CacheEnable") + r'''
Procedure.i Probe(mode.i, rot.i, addr.i)
  testReady = 0
  testBase = 0
  testSize = 0
  If mode = 1
    testReady = 1
    If rot = 90 Or rot = 270
      testBase = #MON_FB_DRAW
    Else
      testBase = #MON_FB_SCAN
    EndIf
    testSize = #MON_FB_BYTES
  ElseIf mode = 2
    testReady = 1
    testBase = $10000000
    testSize = $400000
  EndIf
  gCacheOn = 0
  If CacheEnable() = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn PeekI($A00000 + 8192 + ((addr >> 21) << 3))
EndProcedure
Procedure.i ProbeSequence(addr.i)
  testReady = 1
  testBase = #MON_FB_SCAN
  testSize = #MON_FB_BYTES
  gCacheOn = 0
  If CacheEnable() = 0
    ProcedureReturn -1
  EndIf
  ; Rebind the adopted drawing surface sideways, then call the actual enable
  ; path again. gCacheOn deliberately remains one, so this second call is the
  ; production idempotent no-op rather than a manufactured table rebuild.
  testBase = #MON_FB_DRAW
  If CacheEnable() = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn PeekI($A00000 + 8192 + ((addr >> 21) << 3))
EndProcedure
Procedure.i Main()
  ProcedureReturn Probe(0, 0, #MON_FB_SCAN) + ProbeSequence(#MON_FB_DRAW)
EndProcedure
''')


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor is not unique: " + old)
    return text.replace(old, new, 1)


def build(compiler: Path, work: Path, name: str, source: str):
    src, image = work / (name + ".pi4"), work / (name + ".img")
    src.write_text(fixture(source), encoding="utf-8")
    run = subprocess.run([str(compiler), "--compile", str(src), "-t", "pi4", "-s", "--entry-returns",
                          "--load-addr", hex(LOAD), "--bss-addr", hex(BSS),
                          "--stack-addr", hex(STACK), "-o", str(image)],
                         cwd=ROOT, capture_output=True, text=True, timeout=120)
    if run.returncode or not image.exists():
        raise AssertionError("fixture compile failed\n" + run.stdout + run.stderr)
    entries = {}
    for line in Path(str(image) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("|")
        if len(fields) >= 4 and fields[0] == "1" and fields[1].isdigit():
            entries[fields[2].lower()] = LOAD + int(fields[1])
    symbols = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            symbols[key.strip().lower()] = int(value.strip(), 0)
    return image.read_bytes(), entries, (symbols["__bss_start__"], symbols["__bss_end__"])


class GuardError(RuntimeError):
    pass


def execute(a64, product, entry_name, args, guard_teeth=False):
    blob, entries, bss = product
    entry = entries[entry_name]
    code, stack = (LOAD, LOAD + len(blob)), (STACK - 0x10000, STACK)

    def inside(spans, addr, size):
        return any(lo <= addr and addr + size <= hi for lo, hi in spans)

    class Guarded(a64.A64):
        def fetch(self, addr):
            if addr & 3 or not inside((code,), addr, 4):
                raise GuardError("fetch escaped exact image")
            return super().fetch(addr)
        def load(self, addr, size):
            if not inside((code, bss, (TABLE, TABLE + 0x3000), stack), addr, size):
                raise GuardError("read escaped admitted memory")
            return super().load(addr, size)
        def store(self, addr, value, size):
            if not inside((bss, (TABLE, TABLE + 0x3000), stack), addr, size):
                raise GuardError("write escaped admitted memory")
            return super().store(addr, value, size)

    cpu = Guarded()
    cpu.memory = {LOAD + i: b for i, b in enumerate(blob)}
    cpu.pc, cpu.sp, cpu.x[30] = entry, STACK, RETURN
    for i, value in enumerate(args):
        cpu.x[i] = value
    if guard_teeth:
        actions = (lambda: cpu.fetch(BSS), lambda: cpu.fetch(TABLE),
                   lambda: cpu.fetch(stack[0]), lambda: cpu.load(0xFC000000, 8),
                   lambda: cpu.store(LOAD, 0, 8), lambda: cpu.store(stack[0] - 8, 0, 8))
        for action in actions:
            try:
                action()
            except GuardError:
                pass
            else:
                raise AssertionError("memory/fetch guard did not bite")
    for steps in range(2_000_000):
        if cpu.pc == RETURN:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError("Probe did not return")


def expected(addr: int, attr: int) -> int:
    return (addr & ~0x1FFFFF) | attr


class DescriptorMismatch(AssertionError):
    pass


def check_product(a64, product):
    cases = []
    for rot in (0, 90, 180, 270):
        for addr in (0x8A00000, 0x8C00000, 0x8E00000, 0x9000000):
            cases.append((1, rot, addr, NC))
        cases.extend(((1, rot, 0x7E00000, WB), (1, rot, 0x9200000, WB),
                      (1, rot, 0x8100000, NC)))
    # Each initial source state gets a fresh cache-table build. Dynamic HDMI
    # rebinding while caches remain enabled is not part of the current contract.
    for mode, rot in ((0, 0), (2, 0), (1, 90)):
        cases.extend(((mode, rot, 0x8A00000, NC), (mode, rot, 0x8E00000, NC),
                      (mode, rot, 0x10000000, NC if mode == 2 else WB)))
    total_steps = 0
    for index, (mode, rot, addr, attr) in enumerate(cases):
        got, steps = execute(a64, product, "probe", (mode, rot, addr), index == 0)
        total_steps += steps
        if got != expected(addr, attr):
            raise DescriptorMismatch(f"descriptor mismatch mode={mode} rot={rot} addr={addr:#x}: {got:#x}")
    for addr in (0x8A00000, 0x8C00000, 0x8E00000, 0x9000000):
        got, steps = execute(a64, product, "probesequence", (addr,))
        total_steps += steps
        if got != expected(addr, NC):
            raise DescriptorMismatch(f"same-instance DSI rebind lost {addr:#x}: {got:#x}")
    return len(cases) + 4, total_steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", type=Path, default=ROOT / "tools/a64/a64_interp.py")
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    a64 = emitted.load_interpreter(args.interp)
    source = CACHE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="anvil-cache-map-") as temp:
        work = Path(temp)
        compiler_dir = work / "compiler"
        compiler_dir.mkdir()
        staged = Path(anvil_build.staged_compiler(str(compiler), compiler_dir))
        count, steps = check_product(a64, build(staged, work, "fixed", source))
        mutant = replace_once(source, "  MmuAddNc(#MON_FB_LO, #MON_FB_HI + 1)\n",
                              "  MmuAddNc(#MON_FB_SCAN, #MON_FB_SCAN + #MON_FB_BYTES)\n")
        mutant_product = build(staged, work, "missing_dsi_window", mutant)
        try:
            check_product(a64, mutant_product)
        except DescriptorMismatch:
            pass
        else:
            raise AssertionError("scan-only/missing-second-surface mutant survived")
    print(f"PASS: {count} emitted page-descriptor cases; four rotations, same-instance DSI rebind, six guard teeth")
    print(f"Executed {steps} decoded A64 instructions across accepted cases.")
    print("Rejected mutation: scan-only fixed mapping (second surface absent); hardware enable stubbed; board untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
