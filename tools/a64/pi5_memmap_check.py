#!/usr/bin/env python3
"""pi5_memmap_check.py - THE BCM2712 MAP, measured from the built Pi 5 monitor.

The Pi 5 firmware loads kernel= at $80000 and ignores kernel_address with our
arm stub (2026-09-27: the load guard, booted with kernel_address=0x200000,
printed "Anvil was loaded at 00080000 and is built to run at 00200000").
The monitor is therefore linked there and has its own map - THE BCM2712 MAP
at the top of RaspberryPi4/Board/memmap.pi4. This gate builds the REAL
monitor (RaspberryPi4/Board/board.pi4 -t pi5), puts it at $80000 in
tools/a64/a64_interp.py and asks the image itself, not the source text:

  link      the compiler linked it for $80000, and HwPayLo(0) is the
            megabyte above $80000 + the image's own size (so #MON_LO is
            $80000 too).
  stack     the image is run from its first instruction until Main moves
            the stack; the new sp must be HwMonStack(), and the band under
            it must be a refused region.
  records   MonPhaseBegin/MonPhaseMark, SafetyToFirmware (and SafetyBoot
            where it is linked) and
            AutoSet run with every DRAM store traced: each store must land
            in a region HwMonRegion*() refuses (or the gate's own call
            stack), the boot-count word must be #MON_PHASE_LO + $F00 inside
            the phase region, and HwCoreRawStackBase(1..3) inside region 4.
  overlap   NOTHING the monitor writes lies below $80000 (the EL3 stub) or
            anywhere in $80000..HwPayHi(0) - the image and all the room it
            has to grow into; every refused region and both payload windows
            are pairwise disjoint; everything but the firmware's own DTB and
            framebuffer is inside the ARM's DRAM (/memory ends $28000000).
  guard     the same image loaded at $200000 must NOT move its stack (the
            load guard in Main sets gPi5LoadWrong instead).

--mutate builds the mutants below; each must turn the gate red.

    py -3 tools/a64/pi5_memmap_check.py --compiler PureMetalForge.exe [--mutate]
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
sys.path.insert(0, str(HERE.parent))
import pi5_desk as d                                     # noqa: E402
from a64_interp import A64, attach_symbols               # noqa: E402

FIRMWARE_LOAD = 0x80000          # measured 2026-09-27 (docstring)
WRONG_LOAD = 0x200000            # the old link address: the guard's case
ARM_DRAM_END = 0x28000000        # the source DTB's /memory; VideoCore above
GRAIN = 0x100000
DTB_AT = 0x2EFEC600
PM = 0x107D200000
UART0 = 0x1F00030000
CALL_STACK = 0x3000000           # pi5_desk's call stack: the gate's, not the monitor's
BOARD = "RaspberryPi4/Board/board.pi4"
MEMMAP = "RaspberryPi4/Board/memmap.pi4"
SAFETY = "RaspberryPi4/Lib/safety.pi4"
BRIDGE = b"#PMF_CHIP = 2711"


class Stop(Exception):
    pass


def build(cc: str, override: dict, work: pathlib.Path):
    """The monitor with `override` texts substituted for board.pi4 /
    memmap.pi4 / safety.pi4 (mutations only). Returns (img, procs, syms, linked)."""
    work.mkdir(parents=True, exist_ok=True)
    text = override.get(BOARD) or (ROOT / BOARD).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n")
    lines = [l for l in text.split("\n") if l.encode() != BRIDGE]
    text = "\n".join(lines)
    for rel in (MEMMAP, SAFETY):
        if rel in override:
            marker = 'XIncludeFile "%s"' % rel
            if text.count(marker) != 1:
                d.die("board.pi4 does not include %s exactly once" % rel)
            copy = work / ("mut_" + pathlib.Path(rel).name)
            copy.write_text(override[rel], encoding="utf-8")
            text = text.replace(marker, 'XIncludeFile "%s"' % copy.resolve().as_posix())
    src = work / "board_pi5.pi4"
    img = work / "anvil5.img"
    src.write_text(text, encoding="utf-8")
    r = subprocess.run([cc, "--compile", str(src), "-t", "pi5", "-o", str(img)],
                       cwd=str(ROOT), env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        d.die("the -t pi5 monitor would not build:\n" + r.stdout[-2000:] + r.stderr[-600:])
    m = re.search(r"image linked for \$([0-9A-Fa-f]+)", r.stdout)
    linked = int(m.group(1), 16) if m else None
    offs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            offs[f[2].lower()] = int(f[1])
    syms = {}
    for line in pathlib.Path(str(img) + ".sym").read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                syms[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return img, offs, syms, linked


def machine(img, offs, at, model, trace=None):
    procs = {k: at + v for k, v in offs.items()}
    m = d.Machine(img, procs, model, load=at)
    if trace is not None:
        inner = m.cpu.store

        def store(addr, value, size):
            if addr < 0x1_0000_0000:
                trace.append((addr, size, m.cpu.pc))
            inner(addr, value, size)
        m.cpu.store = store
    return m


class Uart:
    def __init__(self):
        self.tx = bytearray()

    def __call__(self, addr, size, value):
        if UART0 <= addr < UART0 + 0x1000:
            if value is not None and addr == UART0:
                self.tx.append(value & 0xFF)
            return 0x90 if (value is None and addr - UART0 == 0x18) else 0
        if PM <= addr < PM + 0x1000:
            if value is None:
                return 0x130 if addr - PM == 0x1C else 0
            if addr - PM == 0x1C:
                raise Stop()
            return 0
        return 0


def run_to_stack_move(img, at, limit=40_000_000):
    """From the image's first instruction, the sp Main moves to - or None
    if Main reaches HwExceptionPrepare (the guard's path) first."""
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[at + i] = b
    attach_symbols(cpu, img, at)
    cpu.enable_system_registers(el=3, preset={0xD51E1000: 0x30C50830, 0xD5190020: (2 << 24) | (4 << 3) | 3,
                                              0xD5190000: (7 << 13) | (3 << 3) | 2, 0xD51B4220: 0x3C0})
    uart = Uart()
    inner_load, inner_store = cpu.load, cpu.store

    def load(addr, size):
        if addr >= 0x1_0000_0000:
            return uart(addr, size, None) & ((1 << (8 * size)) - 1)
        return inner_load(addr, size)

    def store(addr, value, size):
        if addr >= 0x1_0000_0000:
            uart(addr, size, value)
            return
        inner_store(addr, value, size)
    cpu.load, cpu.store = load, store
    offs = {}
    for line in open(str(img) + ".dbg", encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            offs[f[2].lower()] = at + int(f[1])
    stop_at = offs.get("hwexceptionprepare")
    plain = A64.step.__get__(cpu, A64)
    cpu.pc, cpu.x[0], cpu.sp = at, DTB_AT, 0x07FFF000
    for n in range(limit):
        pc = cpu.pc
        ins = cpu.fetch(pc)
        if pc == at + 0x28 and ins == 0xEB0A013F and cpu.x[9] < cpu.x[10]:
            cpu.x[9] = cpu.x[10]          # the BSS zero loop over dict RAM: its effect is x9 = x10
            continue
        if (ins & 0xFFFFFFE0) == 0xD53BE000:                   # mrs Xt, cntfrq_el0
            cpu.x[ins & 31] = 54_000_000
            cpu.pc += 4
            continue
        if pc == stop_at:
            return None, "reached HwExceptionPrepare without moving the stack"
        plain()
        if not (0x07000000 <= cpu.sp <= 0x08000000):
            return cpu.sp, "moved at step %d" % n
    return None, "no stack move within %d steps" % limit


def overlaps(a, b):
    return a[0] <= b[1] and b[0] <= a[1]


def gate(cc: str, override: dict, work: pathlib.Path, say=print) -> list:
    fails = []

    def check(ok, what):
        say("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    img, offs, syms, linked = build(cc, override, work)
    size = img.stat().st_size
    at = FIRMWARE_LOAD
    check(linked == FIRMWARE_LOAD, "link: the compiler linked the image for $%X (%s)"
          % (FIRMWARE_LOAD, "$%X" % linked if linked is not None else "no link line"))
    m = machine(img, offs, at, Uart())
    n = m.call("HwMonRegions")
    regions = []
    for i in range(n):
        lo, hi = m.signed(m.call("HwMonRegionLo", i)), m.signed(m.call("HwMonRegionHi", i))
        u = Uart()
        machine(img, offs, at, u).call("HwMonRegionSay", i)
        regions.append((lo, hi, u.tx.decode("ascii", "replace") or "region %d" % i))
    pays = [(m.call("HwPayLo", i), m.call("HwPayHi", i)) for i in range(m.call("HwPayWindows"))]
    stack_top = m.call("HwMonStack")
    img_end = at + size
    want_pay0 = (img_end + GRAIN - 1) // GRAIN * GRAIN
    check(pays and pays[0][0] == want_pay0, "link: HwPayLo(0) = $%X, the megabyte above $%X + %d bytes ($%X) - "
          "so #MON_LO is $%X" % (pays[0][0] if pays else -1, at, size, want_pay0, FIRMWARE_LOAD))
    check(regions and regions[0][0] == at and regions[0][1] >= img_end - 1,
          "region 0 is the image at $%X..$%X" % (regions[0][0], regions[0][1]) if regions else "region 0")

    # every refused region and both payload windows are pairwise disjoint
    spans = [(lo, hi, name) for lo, hi, name in regions] + \
            [(lo, hi, "payload window %d" % i) for i, (lo, hi) in enumerate(pays)]
    clash = [(a[2], b[2]) for i, a in enumerate(spans) for b in spans[i + 1:] if overlaps(a, b)]
    check(not clash, "the %d refused regions and %d payload windows are pairwise disjoint%s"
          % (len(regions), len(pays), "" if not clash else ": " + "; ".join("%s / %s" % c for c in clash)))
    firmware = [r for r in regions if "firmware" in r[2]]
    outside = [r[2] for r in regions if r not in firmware and not (0 <= r[0] and r[1] < ARM_DRAM_END)]
    outside += ["payload window %d" % i for i, (lo, hi) in enumerate(pays) if hi >= ARM_DRAM_END and lo < ARM_DRAM_END]
    check(not outside, "every monitor region is inside the ARM's DRAM, below $%X%s"
          % (ARM_DRAM_END, "" if not outside else ": " + ", ".join(outside)))

    # the stack Main actually moves to
    sp, how = run_to_stack_move(img, at)
    check(sp == stack_top, "stack: Main moves sp to $%X, HwMonStack() is $%X (%s)"
          % (sp or 0, stack_top, how))
    band = [r for r in regions if r[1] + 1 == stack_top]
    check(bool(band) and band[0][0] < stack_top, "stack: the band under $%X is a refused region (%s)"
          % (stack_top, band[0][2] if band else "none"))

    # the records, traced
    trace = []
    mm = machine(img, offs, at, Uart(), trace)
    mm.call("MonPhaseBegin", limit=20_000_000)
    mm.call("MonPhaseMark", 0x0501, limit=5_000_000)
    phase_stores = list(trace)
    del trace[:]
    mm.call("AutoSet", 0x10000000, limit=5_000_000)
    ab_stores = list(trace)
    del trace[:]
    if "safetyboot" in offs:             # linked only on boards whose boot counts boots
        try:
            mm.call("SafetyBoot", limit=20_000_000)
        except Stop:
            pass
    try:
        mm.call("SafetyToFirmware", limit=5_000_000)
    except Stop:
        pass
    safety_stores = list(trace)
    record = [(a, s, pc) for a, s, pc in phase_stores + ab_stores + safety_stores
              if not (CALL_STACK - 0x100000 <= a < CALL_STACK)]
    bss = syms.get("__bss_start__"), syms.get("__bss_end__")

    def owner(a):
        for lo, hi, name in regions:
            if lo <= a <= hi:
                return name
        return None
    stray = sorted({a for a, s, pc in record if owner(a) is None})
    check(record and not stray, "records: %d DRAM stores by the record writers, every one inside a refused region%s"
          % (len(record), "" if not stray else ": " + ", ".join("$%X" % a for a in stray[:8])))
    safety_dram = sorted({a for a, s, pc in safety_stores if s == 4 and not (bss[0] <= a < bss[1])
                          and not (CALL_STACK - 0x100000 <= a < CALL_STACK)})
    phase = [r for r in regions if "phase" in r[2]]
    want_count = phase[0][0] + 0xF00 if phase else None
    check(safety_dram == [want_count], "records: the boot-count word is #MON_PHASE_LO + $F00 = $%X (the safety "
          "writers wrote %s)" % (want_count or 0, ", ".join("$%X" % a for a in safety_dram) or "nothing"))
    check(phase and all(phase[0][0] <= a <= phase[0][1] for a, s, pc in phase_stores
                        if not (CALL_STACK - 0x100000 <= a < CALL_STACK) and not (bss[0] <= a < bss[1])),
          "records: the phase record and boot trail stay inside %s" % (phase[0][2] if phase else "a phase region"))
    ab = [r for r in regions if "autoboot" in r[2]]
    check(ab and all(ab[0][0] <= a <= ab[0][1] for a, s, pc in ab_stores
                     if not (CALL_STACK - 0x100000 <= a < CALL_STACK) and not (bss[0] <= a < bss[1])),
          "records: the autoboot record stays inside %s" % (ab[0][2] if ab else "an autoboot region"))
    cores = [r for r in regions if "secondary" in r[2]]
    bases = [m.call("HwCoreRawStackBase", c) for c in (1, 2, 3)]
    check(cores and all(cores[0][0] <= b and b + 0x1000 - 1 <= cores[0][1] for b in bases),
          "records: HwCoreRawStackBase(1..3) = %s, inside %s" % (", ".join("$%X" % b for b in bases),
                                                                 cores[0][2] if cores else "a core-stack region"))

    # THE property: nothing the monitor writes is below the image or in the
    # image's room to grow ($80000..HwPayHi(0))
    grow = (at, pays[0][1] if pays else img_end)
    written = [(stack_top - 1, "the monitor stack top")]
    written += [(lo, name) for lo, hi, name in regions if "secondary" in name or "phase" in name or "autoboot" in name]
    written += [(a, "a record store") for a, s, pc in record if not (bss[0] <= a < bss[1])]
    if band:
        written.append((band[0][0], "the monitor stack band"))
    low = sorted({(a, w) for a, w in written if a < at})
    inimg = sorted({(a, w) for a, w in written if grow[0] <= a <= grow[1]})
    check(not low, "overlap: nothing the monitor writes is below $%X (the EL3 stub)%s"
          % (at, "" if not low else ": " + "; ".join("%s $%X" % (w, a) for a, w in low[:6])))
    check(not inimg, "overlap: nothing the monitor writes is in $%X..$%X - the image (%d bytes, to $%X) and all "
          "%d MiB it may grow into%s" % (grow[0], grow[1], size, img_end - 1, (grow[1] + 1 - img_end) >> 20,
                                         "" if not inimg else ": " + "; ".join("%s $%X" % (w, a) for a, w in inimg[:6])))

    # the guard: loaded where it was not linked, the stack must not move
    sp2, how2 = run_to_stack_move(img, WRONG_LOAD)
    check(sp2 is None, "guard: loaded at $%X instead, Main leaves the stack where it is (%s)" % (WRONG_LOAD, how2))
    return fails


MUTANTS = [
    (MEMMAP, "the stack back at $00100000 (inside the image at $80000)",
     "#MON_STACK    = $0E200000", "#MON_STACK    = $00100000"),
    (MEMMAP, "the stack band declared at the Pi 4's $000..$FFFFF",
     "#MON_STACK_LO = $0E100000", "#MON_STACK_LO = $00000000"),
    (MEMMAP, "the phase record back at $001FB000",
     "  #MON_PHASE_LO  = $0E000000", "  #MON_PHASE_LO  = $001FB000"),
    (MEMMAP, "the autoboot record back at $001FF000",
     "  #AB_BASE   = $0E004000", "  #AB_BASE   = $001FF000"),
    (MEMMAP, "the raw-core stacks back at $001FC000",
     "  #CORE_RAW_STACK_LO    = $0E001000", "  #CORE_RAW_STACK_LO    = $001FC000"),
    (MEMMAP, "#MON_LO back at $00200000",
     "#MON_LO       = $00080000", "#MON_LO       = $00200000"),
    (MEMMAP, "region 12 (the stack) not declared",
     "  CompilerIf #PMF_CHIP = 2712\n  ProcedureReturn 13", "  CompilerIf #PMF_CHIP = 2712\n  ProcedureReturn 12"),
    (SAFETY, "the boot-count word left at $001FBF00",
     "#SAFETY_COUNT_ADDR = $0E000F00", "#SAFETY_COUNT_ADDR = $001FBF00"),
    (BOARD, "Main's stack top typed as a literal, not #MON_STACK",
     "      gPi5StackTop = #MON_STACK", "      gPi5StackTop = $0E100000"),
    (BOARD, "LoadAddress $200000 on the Pi 5",
     "CompilerIf #PMF_CHIP = 2712\nLoadAddress  $80000", "CompilerIf #PMF_CHIP = 2712\nLoadAddress  $200000"),
    (BOARD, "the load guard removed (the stack moves wherever the image is)",
     "    If MonImageLo() = #MON_LO\n      gPi5StackTop", "    If 1 = 1\n      gPi5StackTop"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    work = ROOT / "_work" / "pi5_memmap"
    try:
        fails = gate(cc, {}, work)
    except d.GateFail as e:
        print("pi5_memmap_check: FAIL - %s" % e)
        return 1
    if fails:
        print("pi5_memmap_check: FAIL - %d check(s)" % len(fails))
        return 1
    print("pi5_memmap_check: PASS - THE BCM2712 MAP, measured from the image at $%X. Desk only: silicon owed."
          % FIRMWARE_LOAD)
    if not a.mutate:
        return 0

    def mgate(override, wd):
        text = {}
        for rel, new in override.items():
            text[rel] = new
        f = gate(cc, text, wd, say=lambda s: None)
        if f:
            d.die(f[0])
    muts = []
    for rel, why, old, new in MUTANTS:
        muts.append((rel, why, old, new))

    # run_mutations reads the tracked text and needs exactly one match; the
    # sources are CRLF in a Windows checkout, so match on LF text
    survived = 0
    for i, (rel, why, old, new) in enumerate(muts):
        t = (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        if t.count(old) != 1:
            print("  %2d  SURVIVED  %s: %s (the edit matched %d times, not once)" % (i, rel, why, t.count(old)))
            survived += 1
            continue
        try:
            mgate({rel: t.replace(old, new)}, work / ("m%02d" % i))
        except d.GateFail as e:
            print("  %2d  KILLED    %s: %s (%s)" % (i, rel, why, str(e).replace("\n", " ")[:120]))
            continue
        except Exception as e:                                # noqa: BLE001
            print("  %2d  KILLED    %s: %s (%r)" % (i, rel, why, e))
            continue
        print("  %2d  SURVIVED  %s: %s" % (i, rel, why))
        survived += 1
    print("pi5_memmap_check mutations: %d killed, %d survived" % (len(muts) - survived, survived))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
