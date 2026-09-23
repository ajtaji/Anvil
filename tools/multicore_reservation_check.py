#!/usr/bin/env python3
"""Gate the raw-secondary reservation, publication ordering and refusals.

WHAT THIS ADDS THAT tools/a64/a64_core_worker_check.py DOES NOT.

  1. It grades the DECODED IMAGE, not the `.s` listing.  Every emitted check
     in the older gate matches text in the compiler's assembly listing.  The
     house rule that exists because of the worst defect in this project's
     history is "trust the disassembled hex, not the listing": the listing
     once showed frame prologues the binary did not contain.  So the ordering
     and cache-maintenance claims here are read out of the instruction words
     the interpreter actually fetches and executes.

  2. It does ARITHMETIC on the board's own answers.  The reservation was
     previously checked by asserting the literal text `$001FC000` in the
     board file.  That cannot notice the autoboot page moving down, the
     monitor's measured extent growing into the band, or the low payload
     window's computed floor dropping.  Here the fixture publishes what the
     shipped accessors answer and this host recomputes containment,
     contiguity and disjointness against every other declared region and
     both payload windows from first principles.

  3. It executes the refusals that depend on the MACHINE STATE of the
     primary - wrong exception level, and an EL3 primary whose own caches
     and MMU are off - by running one image under three presets.

  4. It proves the bounded wait TIMES OUT when no secondary exists, so a
     PREPARED row can never be mistaken for a READY one.

WHAT IT CANNOT DO.  The interpreter has no cache, no TLB, no store buffer,
no WFE/SEV timing and no simultaneous execution.  A PASS here is a statement
about the instructions and the numbers, never about coherency, ordering as
the silicon observes it, or parallelism.  No board is contacted.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build as anvil_build  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402

FIXTURE = Path("RaspberryPi4/Tests/multicore_reservation_emitted_gate.pi4")
CORE = Path("RaspberryPi4/Lib/core_worker_impl.pi4")
MMUSEC = Path("RaspberryPi4/Lib/mmu_secondary.pi4")
MEMMAP = Path("RaspberryPi4/Board/memmap.pi4")
MMU = Path("RaspberryPi4/Lib/mmu.pi4")
MEMRANGE = Path("Anvil/Core/memrange.pbi")
COPIED = (FIXTURE, CORE, Path("RaspberryPi4/Lib/core_worker.pi4"), MMUSEC, MEMMAP, MMU, MEMRANGE)

LOAD = 0x00400000
STACK = 0x03000000
RETURN_PC = 0xDEAD0000
SLOTS = 80
MAX_REGIONS = 12
STRIDE = 256
ALIGN = 256

# MRS/MSR selector words normalised to the interpreter's write form, derived
# from the ARM ARM quadruple rather than copied:
#   base = 0xD5100000 | (op0 == 3) << 19 | op1 << 16 | CRn << 12 | CRm << 8 | op2 << 5
def sysreg_key(op0: int, op1: int, crn: int, crm: int, op2: int) -> int:
    return (0xD5100000 | ((op0 == 3) << 19) | (op1 << 16) |
            (crn << 12) | (crm << 8) | (op2 << 5))


MPIDR_EL1 = sysreg_key(3, 0, 0, 0, 5)
SCTLR_EL1 = sysreg_key(3, 0, 1, 0, 0)
SCTLR_EL2 = sysreg_key(3, 4, 1, 0, 0)
SCTLR_EL3 = sysreg_key(3, 6, 1, 0, 0)
TTBR0_EL3 = sysreg_key(3, 6, 2, 0, 0)
TCR_EL3 = sysreg_key(3, 6, 2, 0, 2)
MAIR_EL3 = sysreg_key(3, 6, 10, 2, 0)
CPUECTLR_EL1 = sysreg_key(3, 1, 15, 2, 1)
CCSIDR_EL1 = sysreg_key(3, 1, 0, 0, 0)
CSSELR_EL1 = sysreg_key(3, 2, 0, 0, 0)
CLIDR_EL1 = sysreg_key(3, 1, 0, 0, 1)

SMPEN = 0x40
MCI = 0x1005                       # SCTLR M | C | I
SCTLR_CACHED = 0x30C51835
SCTLR_COLD = 0x30C50830
TTBR_VALUE = 0x00900000
TCR_VALUE = 0x0000000080803520
MAIR_VALUE = 0x00000000FF440400
CONTEXT = 0xC0FFEE

# Cortex-A72 L1 D: 64-byte lines, 2 ways, 256 sets.  Arm TRM 100095 r0p3.
A72_L1D = (2) | (1 << 3) | (255 << 13)
# A deliberately different geometry, so the way-shift derivation cannot be a
# constant that happens to suit the A72: 128-byte lines, 4 ways, 128 sets.
OTHER_L1D = (3) | (3 << 3) | (127 << 13)

PREPARED = 1
READY = 2
ERR_EL = -3
ERR_MMU = -4
ERR_STATE = -11
ERR_TIMEOUT = -10

CACHE_LINE = 64
LINE_OF = lambda a: (a // CACHE_LINE) * CACHE_LINE


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, value: bool, message: str) -> None:
        self.count += 1
        if not value:
            raise AssertionError(message)

    def eq(self, got, want, message: str) -> None:
        self.yes(got == want, f"{message}: got {got!r}, wanted {want!r}")


# ----------------------------------------------------------------------
#  Building
# ----------------------------------------------------------------------
def mutant_root(work: Path, label: str, source_root: Path,
                edits: list[tuple[Path, str, str]]) -> Path:
    root = work / f"root-{label}"
    for relative in COPIED:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, target)
    shutil.copytree(source_root / "Boards", root / "Boards")
    shutil.copytree(source_root / "RaspberryPi4" / "Intrinsics",
                    root / "RaspberryPi4" / "Intrinsics")
    for relative, old, new in edits:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise AssertionError(
                f"mutant {label}: pattern appears {text.count(old)} times, "
                f"needed exactly one: {old!r}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    return root


def build(compiler: str, work: Path, source_root: Path, stem: str) -> Path:
    compiler_dir = work / f"compiler-{stem}"
    compiler_dir.mkdir(parents=True, exist_ok=True)
    staged = anvil_build.staged_compiler(compiler, compiler_dir)
    image = work / f"{stem}.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(source_root)
    cmd = [staged, "--compile", FIXTURE.as_posix(), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-S", "-s", "-o", str(image)]
    done = subprocess.run(cmd, cwd=source_root, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode or not image.is_file():
        raise AssertionError(f"fixture build failed ({stem}):\n{done.stdout}")
    return image


def symbols(image: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            out[name.strip().lower()] = int(value.strip())
    return out


def load_interp(path: Path):
    spec = importlib.util.spec_from_file_location("mcr_a64", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load interpreter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------------
#  The tracing PE.  Every event below is decoded from the instruction word
#  fetched out of the built image, before it executes.
# ----------------------------------------------------------------------
def tracer(a64):
    class Traced(a64.A64):
        def __init__(self) -> None:
            super().__init__()
            self.trace: list[tuple] = []

        def step(self) -> None:
            ins = self.fetch(self.pc)
            x = self.x
            if ins == 0xD503209F:
                self.trace.append(("sev",))
            elif ins == 0xD503205F:
                self.trace.append(("wfe",))
            elif (ins & 0xFFFFF01F) == 0xD503301F and 4 <= ((ins >> 5) & 7) <= 6:
                self.trace.append((("dsb", "dmb", "isb")[((ins >> 5) & 7) - 4],))
            elif (ins & 0xFFF80000) == 0xD5080000:
                key = ((((ins >> 16) & 7) << 12) | (((ins >> 12) & 15) << 8) |
                       (((ins >> 8) & 15) << 4) | ((ins >> 5) & 7))
                rt = ins & 31
                operand = x[rt] if rt != 31 else 0
                self.trace.append(
                    ("sys", a64.SYS_MAINTENANCE.get(key, f"unknown:{key:04X}"),
                     operand))
            elif (ins & 0xFFFFFC00) == 0xC89FFC00:
                self.trace.append(("stlr", x[(ins >> 5) & 31]))
            elif (ins & 0xFFFFFC00) == 0xC8DFFC00:
                self.trace.append(("ldar", x[(ins >> 5) & 31]))
            elif (ins & 0xFFC00000) == 0xF9000000:
                base = (ins >> 5) & 31
                addr = (self.sp if base == 31 else x[base]) + ((ins >> 10) & 0xFFF) * 8
                self.trace.append(("str", addr & 0xFFFFFFFFFFFFFFFF))
            elif (ins & 0xFFF00000) == 0xD5300000:
                self.trace.append(
                    ("mrs", (ins & self.SYSREG_WRITE_MASK) & ~self.SYSREG_READ_BIT))
            elif (ins & 0xFFF00000) == 0xD5100000:
                self.trace.append(("msr", ins & self.SYSREG_WRITE_MASK))
            super().step()

    return Traced


def run_main(a64, image: Path, sym: dict[str, int], mode: int, el: int,
             preset: dict[int, int], budget: int = 600000):
    mem = {LOAD + i: b for i, b in enumerate(image.read_bytes())}
    cpu = tracer(a64)()
    cpu.memory = mem
    cpu.enable_system_registers(el=el, preset=preset)
    for i in range(8):
        mem[sym["global_mcr_mode"] + i] = (mode >> (8 * i)) & 0xFF
    cpu.pc = LOAD + sym["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    steps = 0
    while cpu.pc != RETURN_PC and steps < budget:
        cpu.step()
        steps += 1
    if cpu.pc != RETURN_PC:
        raise AssertionError(f"fixture mode {mode} did not return in {budget} steps")
    return cpu, mem, steps


def slot(mem: dict[int, int], sym: dict[str, int], index: int) -> int:
    addr = sym["global_mcr_out"] + index * 8
    value = sum(mem.get(addr + i, 0) << (8 * i) for i in range(8))
    return value - (1 << 64) if value >> 63 else value


def primary_preset(el: int, sctlr: int, core: int = 0) -> dict[int, int]:
    bank = {1: SCTLR_EL1, 2: SCTLR_EL2, 3: SCTLR_EL3}[el]
    return {MPIDR_EL1: core, bank: sctlr, TTBR0_EL3: TTBR_VALUE,
            TCR_EL3: TCR_VALUE, MAIR_EL3: MAIR_VALUE,
            CPUECTLR_EL1: SMPEN, CCSIDR_EL1: A72_L1D}


# ----------------------------------------------------------------------
#  A. the reservation, recomputed here from the board's own answers
# ----------------------------------------------------------------------
def reservation_checks(c: Checks, mem, sym) -> None:
    # HOW MANY REGIONS THE BOARD HAS IS THE BOARD'S BUSINESS. An earlier draft
    # of this gate asserted five and went red the day the module arena became
    # the sixth - the same wrong shape memmap.pi4's own header warns about, one
    # level up. What must hold is a property of the BAND, not a count: exactly
    # one declared region IS the band, and nothing else declared touches it.
    regions = slot(mem, sym, 0)
    c.yes(1 <= regions <= MAX_REGIONS,
          f"the board declares {regions} monitor regions; this fixture "
          f"publishes {MAX_REGIONS} and cannot see them all")
    lo = [slot(mem, sym, 1 + i) for i in range(regions)]
    hi = [slot(mem, sym, 1 + MAX_REGIONS + i) for i in range(regions)]
    windows = slot(mem, sym, 25)
    c.yes(windows >= 1, "the board declares no payload window")
    pay = [(slot(mem, sym, 26), slot(mem, sym, 27)),
           (slot(mem, sym, 28), slot(mem, sym, 29))][:windows]
    mon = (slot(mem, sym, 30), slot(mem, sym, 31))
    base = [slot(mem, sym, 31 + i) for i in (1, 2, 3)]
    size = [slot(mem, sym, 34 + i) for i in (1, 2, 3)]

    for i, (b, n) in enumerate(zip(base, size), start=1):
        c.eq(n, 0x1000, f"core {i} was not given exactly one 4 KiB page")
        c.eq(b & 0xFFF, 0, f"core {i}'s page is not page aligned")
    c.yes(len(set(base)) == 3,
          f"two raw cores share one page: {[hex(b) for b in base]}")
    ranges = sorted((b, b + n - 1) for b, n in zip(base, size))
    for (alo, ahi), (blo, _) in zip(ranges, ranges[1:]):
        c.yes(ahi < blo, "two raw-core pages overlap")
        c.eq(blo, ahi + 1, "the three raw-core pages are not contiguous")
    band = (ranges[0][0], ranges[-1][1])
    c.eq(band[1] - band[0] + 1, 3 * 0x1000,
         "the reserved band is not exactly three pages")

    # EXACTLY one region, not merely inside one: a region wider than the
    # reservation refuses memory nobody reserved, and a narrower one leaves a
    # page unprotected.
    exact = [i for i in range(regions) if (lo[i], hi[i]) == band]
    c.eq(len(exact), 1,
         f"no declared region is exactly {hex(band[0])}..{hex(band[1])}: "
         f"{[(hex(a), hex(b)) for a, b in zip(lo, hi)]}")
    which = exact[0]

    for i in range(regions):
        if i == which:
            continue
        c.yes(hi[i] < band[0] or lo[i] > band[1],
              f"the raw-stack band overlaps monitor region {i} "
              f"({hex(lo[i])}..{hex(hi[i])})")
    for i, (plo, phi) in enumerate(pay):
        c.yes(phi < band[0] or plo > band[1],
              f"the raw-stack band overlaps payload window {i} "
              f"({hex(plo)}..{hex(phi)})")
    c.yes(band[1] < mon[0] or band[0] > mon[1],
          "the raw-stack band overlaps the running image")
    # A stack grows DOWN from base+size, so the highest core's initial SP is
    # one past the band. Something declared must own that byte, or the first
    # push lands in memory nobody has claimed.
    top = band[1] + 1
    c.yes([i for i in range(regions) if lo[i] == top],
          f"nothing declared owns {hex(top)}, the highest raw stack's initial "
          "SP; a push there would land in unclaimed memory")
    c.yes(base[0] >= 0x1000, "a raw stack sits in the firmware spin-table page")

    # Out-of-range cores must answer with nothing, not with core 1's page.
    for index, name in ((38, "base(0)"), (39, "base(4)"),
                        (40, "bytes(0)"), (41, "bytes(4)")):
        c.eq(slot(mem, sym, index), 0,
             f"HwCoreRaw...{name} answered for a core this board does not park")
    return band, which


# ----------------------------------------------------------------------
#  B. the monitor actually refuses the band, through the shipped predicate
# ----------------------------------------------------------------------
def protection_checks(c: Checks, mem, sym, band, which) -> None:
    for i in range(3):
        c.eq(slot(mem, sym, 42 + i * 2), which + 1,
             f"HitsMonitor did not refuse raw core {i + 1}'s page")
        c.eq(slot(mem, sym, 43 + i * 2), which,
             f"HitsMonitor named the wrong region for raw core {i + 1}")
    c.eq(slot(mem, sym, 48), which + 1,
         "HitsMonitor did not refuse the whole band")
    c.eq(slot(mem, sym, 49), which,
         "HitsMonitor named the wrong region for the band")
    c.eq(slot(mem, sym, 50), 0, "the raw-stack band is inside a payload window")
    # Adjacent memory can belong to another legitimate reservation (the
    # retained boot-phase page now does). Grade the actual emitted region
    # table, rather than assuming the neighbor is unowned forever.
    below = band[0] - 1
    owner = next((i + 1 for i in range(slot(mem, sym, 0))
                  if slot(mem, sym, 1 + i) <= below <=
                  slot(mem, sym, 1 + MAX_REGIONS + i)), 0)
    c.eq(slot(mem, sym, 51), owner,
         "HitsMonitor disagrees with the declared owner below the raw-stack band")
    c.yes(owner != which + 1,
          "the raw-stack reservation incorrectly includes the byte below its band")
    c.yes(slot(mem, sym, 53) != 0,
          "the byte above the band is unprotected; the highest raw stack's "
          "initial SP must land in a region the monitor already owns")


# ----------------------------------------------------------------------
#  C. the shipped ownership predicate
# ----------------------------------------------------------------------
def ownership_checks(c: Checks, mem, sym) -> None:
    for i in range(3):
        c.eq(slot(mem, sym, 55 + i), 1,
             f"the board's own core/page pair was refused for core {i + 1}")
    for index, what in ((58, "another core's page"),
                        (59, "an offset sub-range"),
                        (60, "a double-sized range"), (61, "core 0")):
        c.eq(slot(mem, sym, index), 0, f"ownership accepted {what}")


# ----------------------------------------------------------------------
#  D. refusals that depend on the primary's own machine state
# ----------------------------------------------------------------------
def machine_state_checks(c: Checks, a64, image, sym) -> None:
    # EL2 with caches and MMU on: only the exception level can stop this.
    cpu, mem, _ = run_main(a64, image, sym, 1, 2,
                           primary_preset(2, SCTLR_CACHED))
    c.eq(slot(mem, sym, 62), 2, "the EL2 run did not report EL2")
    c.eq(slot(mem, sym, 65), 0, "prepare accepted a non-EL3 primary")
    c.eq(slot(mem, sym, 66), ERR_EL, "the non-EL3 refusal used the wrong code")
    c.eq(slot(mem, sym, 67), 0, "a refused prepare marked the core prepared")
    c.eq(slot(mem, sym, 70), 0, "release ran after a refused prepare")
    c.eq(slot(mem, sym, 71), ERR_STATE, "release after refusal used the wrong code")
    c.yes(not [e for e in cpu.trace if e[0] == "sev"],
          "a refused prepare signalled the parked cores")
    c.yes(not [e for e in cpu.trace if e[0] == "sys"],
          "a refused prepare performed cache maintenance")

    # EL3, but the primary's own M/C/I are clear: it has no cached regime for
    # a secondary to join, and publishing a record it cleaned to nowhere is
    # the silent-wrong-answer shape.
    _, mem, _ = run_main(a64, image, sym, 1, 3, primary_preset(3, SCTLR_COLD))
    c.eq(slot(mem, sym, 62), 3, "the cold EL3 run did not report EL3")
    c.eq(slot(mem, sym, 65), 0, "prepare accepted an EL3 primary with M/C/I clear")
    c.eq(slot(mem, sym, 66), ERR_MMU, "the cold-primary refusal used the wrong code")

    # EL3 with M/C/I set: the one accepted route.
    cpu, mem, _ = run_main(a64, image, sym, 2, 3, primary_preset(3, SCTLR_CACHED))
    c.eq(slot(mem, sym, 65), 1, "the accepted prepare route was refused")
    c.eq(slot(mem, sym, 66), 0, "the accepted prepare route set an error code")
    c.eq(slot(mem, sym, 72), 1, "the accepted release route was refused")
    c.eq(slot(mem, sym, 74), 1, "release did not record the core as released")
    c.yes(slot(mem, sym, 75) != 0, "release left the firmware spin slot empty")
    # THE STALE-WORD CHECK. No secondary exists in this model, so the row is
    # still PREPARED. A wait that returned success here would be a monitor
    # claiming a core came up because a word it wrote itself is non-zero.
    c.eq(slot(mem, sym, 76), 0,
         "the bounded wait claimed READY with no secondary running")
    c.eq(slot(mem, sym, 77), ERR_TIMEOUT, "the bounded wait used the wrong code")
    return cpu, mem


# ----------------------------------------------------------------------
#  E. the primary's release ordering, decoded
# ----------------------------------------------------------------------
def release_order(c: Checks, cpu, sym) -> None:
    """The slot release, in the order the bytes execute it."""
    boot = (sym["global_core_raw_boot"] + ALIGN - 1) & -ALIGN
    row = (sym["global_core_raw_row"] + ALIGN - 1) & -ALIGN
    boot1, row1 = boot + STRIDE, row + STRIDE
    box = 0xE0

    cleans = [(i, e[2]) for i, e in enumerate(cpu.trace)
              if e[0] == "sys" and e[1] == "dc cvac"]
    want = ([LINE_OF(boot1 + k * CACHE_LINE) for k in range(4)] +
            [LINE_OF(row1 + k * CACHE_LINE) for k in range(4)] +
            [LINE_OF(box)])
    c.eq([addr for _, addr in cleans], want,
         "the cleaned lines are not the four cold-record lines, the four "
         "control-row lines and the slot's line, in that order")

    slot_stores = [i for i, e in enumerate(cpu.trace)
                   if e[0] == "str" and e[1] == box]
    c.eq(len(slot_stores), 1,
         "the firmware slot was written more than once on the accepted route")
    entry_at = slot_stores[-1]
    c.yes(entry_at > cleans[7][0],
          "the entry address reached the firmware slot before the cold record "
          "and the control row were clean to the point of coherency")

    interesting = [e for e in cpu.trace[entry_at:]
                   if e[0] in ("dsb", "isb", "sev") or
                   (e[0] == "sys") or (e[0] == "str" and e[1] == box)]
    c.eq(interesting[:7],
         [("str", box), ("sys", "dc cvac", LINE_OF(box)),
          ("dsb",), ("isb",), ("dsb",), ("isb",), ("sev",)],
         "the release order is not store, clean-to-PoC, barrier, barrier, event")

    # Nothing may write the record or the row after the slot is armed: the
    # secondary is entitled to read them the instant the event lands.
    late = [e for e in cpu.trace[entry_at + 1:]
            if e[0] in ("str", "stlr") and
            (boot1 <= e[1] < boot1 + STRIDE or row1 <= e[1] < row1 + STRIDE)]
    c.yes(not late,
          f"the cold record or control row was written after release: {late}")


# ----------------------------------------------------------------------
#  F. the secondary's cache ownership and publication, decoded
# ----------------------------------------------------------------------
def secondary_checks(c: Checks, a64, image: Path, sym: dict[str, int],
                     ccsidr: int, ways: int, sets: int, line_log2: int,
                     core: int = 1) -> None:
    mem = {LOAD + i: b for i, b in enumerate(image.read_bytes())}
    boot = ((sym["global_core_raw_boot"] + ALIGN - 1) & -ALIGN) + core * STRIDE
    row = ((sym["global_core_raw_row"] + ALIGN - 1) & -ALIGN) + core * STRIDE
    stack = 0x001FC000 + core * 0x1000 + 0x1000

    def put(addr, value):
        for i in range(8):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    for index, value in enumerate([0x43525742, 3, stack, CONTEXT, row,
                                   TTBR_VALUE, TCR_VALUE, MAIR_VALUE,
                                   SCTLR_CACHED]):
        put(boot + index * 8, value)
    put(row, PREPARED)

    cpu = tracer(a64)()
    cpu.memory = mem
    cpu.enable_system_registers(
        el=3, preset={MPIDR_EL1: core, SCTLR_EL3: 0, CPUECTLR_EL1: SMPEN,
                      CCSIDR_EL1: ccsidr, CLIDR_EL1: 0x0A200023})
    cpu.pc = LOAD + sym["corerawsecondaryentry"]
    cpu.sp = 0x7BADFACE7BADF000
    for _ in range(40000):
        cpu.step()
        if sum(mem.get(row + i, 0) << (8 * i) for i in range(8)) == READY:
            break
    # Keep stepping past READY: completing, signalling and parking are part of
    # the contract, and a model that stopped at the release would never see a
    # secondary that published and then ran on into ordinary code.
    for _ in range(8):
        cpu.step()
    got = sum(mem.get(row + i, 0) << (8 * i) for i in range(8))
    c.eq(got, READY, f"core {core} did not publish READY")

    # --- cache ownership: private L1 only, and the walk is COMPLETE --------
    isw = [e[2] for e in cpu.trace if e[0] == "sys" and e[1] == "dc isw"]
    c.yes(isw, "the secondary performed no cold-cache invalidation")
    levels = {(op >> 1) & 7 for op in isw}
    c.eq(levels, {0},
         f"the secondary invalidated cache levels {sorted(levels)}; only the "
         "core-private L1 may be touched, the A72's L2 is cluster-shared and "
         "can hold the running primary's dirty lines")
    for name, key in (("clidr_el1", CLIDR_EL1),):
        c.yes(("mrs", key) not in cpu.trace,
              f"the secondary read {name}; enumerating levels is how a walk "
              "reaches the shared L2")
    for e in cpu.trace:
        if e[0] == "sys":
            c.yes(not e[1].startswith(("dc cisw", "dc csw", "dc civac")),
                  f"the secondary used {e[1]}, which can WRITE BACK a line it "
                  "does not own")
    way_shift = 32 - (ways - 1).bit_length()
    expected = {(w << way_shift) | (s << line_log2)
                for w in range(ways) for s in range(sets)}
    c.eq(len(isw), ways * sets,
         f"the set/way walk executed {len(isw)} operations for a "
         f"{ways}-way {sets}-set cache")
    c.eq(set(isw), expected,
         "the set/way operands are not the complete way/set product for this "
         "geometry - the way shift or the line-size shift is wrong")

    # --- the join's maintenance order, decoded ---------------------------
    last_isw = max(i for i, e in enumerate(cpu.trace)
                   if e[0] == "sys" and e[1] == "dc isw")
    tail = [e for e in cpu.trace[last_isw + 1:]
            if e[0] in ("dsb", "isb") or
            (e[0] == "sys") or
            (e[0] == "msr" and e[1] in (TTBR0_EL3, TCR_EL3, MAIR_EL3, SCTLR_EL3))]
    c.eq(tail[:12],
         [("dsb",), ("isb",), ("sys", "ic iallu", 0), ("sys", "tlbi alle3", 0),
          ("dsb",), ("isb",),
          ("msr", TTBR0_EL3), ("msr", TCR_EL3), ("msr", MAIR_EL3),
          ("dsb",), ("isb",), ("msr", SCTLR_EL3)],
         "the join does not invalidate, then discard the EL3 TLB and I-cache, "
         "then install the translation registers behind a barrier, then enable")
    c.eq(tail[12:13], [("isb",)],
         "SCTLR_EL3 is enabled without an instruction synchronisation barrier")

    # --- publication ordering, decoded -----------------------------------
    stlr = [i for i, e in enumerate(cpu.trace) if e[0] == "stlr"]
    c.eq(len(stlr), 1, "READY must be published by exactly one store-release")
    c.eq(cpu.trace[stlr[0]], ("stlr", row), "the store-release did not target the row")
    plain_row = [i for i, e in enumerate(cpu.trace) if e[0] == "str" and e[1] == row]
    c.yes(not plain_row,
          "the state word was written with a plain store as well as a release")
    witnesses = [i for i, e in enumerate(cpu.trace)
                 if e[0] == "str" and row + 8 <= e[1] <= row + 72]
    c.eq(len(witnesses), 9, "the secondary did not publish nine witness words")
    c.yes(max(witnesses) < stlr[0],
          "READY was released before the last mapping/stack witness was stored")
    after_ready = [e for e in cpu.trace[stlr[0] + 1:]
                   if e[0] in ("dsb", "sev", "wfe", "str", "stlr")]
    c.eq(after_ready[:3], [("dsb",), ("sev",), ("wfe",)],
         "after READY the secondary must complete, signal, and park")
    return cpu


# ----------------------------------------------------------------------
#  the whole gate over one built image
# ----------------------------------------------------------------------
def grade(c: Checks, a64, image: Path) -> None:
    sym = symbols(image)
    for name in ("main", "global_mcr_mode", "global_mcr_out",
                 "global_core_raw_boot", "global_core_raw_row",
                 "corerawsecondaryentry"):
        c.yes(name in sym, f"the fixture is missing symbol {name}")
    _, mem, _ = run_main(a64, image, sym, 0, 3, primary_preset(3, SCTLR_CACHED))
    band, which = reservation_checks(c, mem, sym)
    protection_checks(c, mem, sym, band, which)
    ownership_checks(c, mem, sym)
    cpu, _ = machine_state_checks(c, a64, image, sym)
    release_order(c, cpu, sym)
    secondary_checks(c, a64, image, sym, A72_L1D, 2, 256, 6, core=1)
    secondary_checks(c, a64, image, sym, OTHER_L1D, 4, 128, 7, core=2)


MUTANTS: list[tuple[str, list[tuple[Path, str, str]]]] = [
    ("region-hi-under-covers",
     [(MEMMAP, "Case 4 : ProcedureReturn #CORE_RAW_STACK_HI",
       "Case 4 : ProcedureReturn #CORE_RAW_STACK_LO + #CORE_RAW_STACK_PAGE - 1")]),
    ("core3-aliases-core2",
     [(MEMMAP, "Case 3 : ProcedureReturn #CORE_RAW_STACK_LO + (#CORE_RAW_STACK_PAGE * 2)",
       "Case 3 : ProcedureReturn #CORE_RAW_STACK_LO + (#CORE_RAW_STACK_PAGE * 1)")]),
    # Moved into the low payload window, clear of every other declared
    # region, so only the payload-window arithmetic can catch it.
    ("band-inside-payload-window",
     [(MEMMAP, "#CORE_RAW_STACK_LO    = $001FC000",
       "#CORE_RAW_STACK_LO    = $00700000"),
      (MEMMAP, "#CORE_RAW_STACK_HI    = $001FEFFF",
       "#CORE_RAW_STACK_HI    = $00702FFF")]),
    # "Undeclare" the band the count-agnostic way: leave HwMonRegions() alone
    # and point region 4's edges elsewhere, so nothing declared IS the band.
    ("band-no-longer-a-declared-region",
     [(MEMMAP, "Case 4 : ProcedureReturn #CORE_RAW_STACK_LO",
       "Case 4 : ProcedureReturn #AB_BASE"),
      (MEMMAP, "Case 4 : ProcedureReturn #CORE_RAW_STACK_HI",
       "Case 4 : ProcedureReturn #AB_BASE")]),
    ("slot-clean-removed",
     [(CORE, "MmuCleanRange(box, 8)", "MmuCleanRange(box, 0)")]),
    ("release-event-removed",
     [(CORE, "  a64_send_event()\n  core_raw_released[core] = 1",
       "  core_raw_released[core] = 1")]),
    ("release-barrier-removed",
     [(CORE, "  a64_barrier()\n  a64_send_event()", "  a64_send_event()")]),
    ("record-cleaned-after-release",
     [(CORE, "  MmuCleanRange(box, 8)\n  a64_barrier()",
       "  MmuCleanRange(box, 8)\n  PokeI(CoreRawBootAddr(core), #CORE_RAW_BOOT_MAGIC)\n  a64_barrier()")]),
    ("ready-published-with-plain-store",
     [(CORE, "    stlr x9, [x2]", "    str  x9, [x2, #0]")]),
    ("ready-published-early",
     [(CORE, "    str  x1, [x2, #8]", "    stlr x9, [x2]\n    str  x1, [x2, #8]")]),
    # The OPERAND's level field is what decides which cache a DC ISW reaches;
    # CSSELR only chooses which geometry CCSIDR reports. They are two separate
    # routes to the cluster-shared L2 and both are pinned here.
    ("level-field-names-shared-l2",
     [(MMUSEC, "    dc   isw, x8",
       "    movz x13, #2\n    orr  x8, x8, x13\n    dc   isw, x8")]),
    ("clidr-level-discovery-restored",
     [(MMUSEC, "    movz x14, #0\n    msr  csselr_el1, x14",
       "    mrs  x14, clidr_el1\n    msr  csselr_el1, x14")]),
    ("wrong-tlb-regime",
     [(MMUSEC, "    tlbi alle3", "    tlbi alle2")]),
    ("sctlr-enabled-without-isb",
     [(MMUSEC, "    msr  sctlr_el3, x23\n    isb", "    msr  sctlr_el3, x23")]),
    ("way-shift-fixed-to-a72",
     [(MMUSEC, "    movz x5, #32\n    mov  x9, x3", "    movz x5, #31\n    movz x9, #0")]),
    ("prepare-accepts-any-level",
     [(CORE, "  If el <> 3\n", "  If el <> 3 And el <> 2\n")]),
    ("prepare-accepts-cold-primary",
     [(CORE, "  If (sctlr & #MMU_SCTLR_MCI) <> #MMU_SCTLR_MCI\n", "  If 0 = 1\n")]),
    ("wait-accepts-a-stale-row",
     [(CORE, "    If CoreRawState(core) = #CORE_RAW_STATE_READY",
       "    If CoreRawState(core) >= #CORE_RAW_STATE_PREPARED")]),
]


def main() -> int:
    if not __debug__:
        print("multicore_reservation_check: FAIL - Python -O disables the "
              "assertions this gate is made of")
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--verbose", action="store_true",
                        help="print which check killed each mutant")
    parser.add_argument("--keep", action="store_true",
                        help="keep the scratch build tree for inspection")
    args = parser.parse_args()
    compiler = (resolve_compiler(args.compiler)
                if (args.compiler or os.environ.get("PMF_COMPILER"))
                else anvil_build.find_compiler(args.compiler))

    c = Checks()
    a64 = load_interp(ROOT / "tools" / "a64" / "a64_interp.py")
    work = Path(tempfile.mkdtemp(prefix="anvil-multicore-reservation-"))
    try:
        image = build(compiler, work, ROOT, "reservation")
        grade(c, a64, image)
        primary = c.count
        killed = 0
        for label, edits in MUTANTS:
            root = mutant_root(work, label, ROOT, edits)
            try:
                mutant_image = build(compiler, work, root, f"mutant-{label}")
            except AssertionError:
                killed += 1                 # refused at compile time is a kill
                if args.verbose:
                    print(f"  killed {label}: refused by the compiler")
                continue
            try:
                grade(Checks(), a64, mutant_image)
            except AssertionError as why:
                killed += 1
                # PRINT THE REASON, not just the count. A mutant killed by the
                # wrong check is a gate that has stopped watching what it says
                # it watches, and a count cannot tell the two apart.
                if args.verbose:
                    print(f"  killed {label}: {str(why).splitlines()[0][:160]}")
            else:
                raise AssertionError(f"mutation survived: {label}")
        print(f"multicore_reservation_check: PASS - {primary} decoded-image, "
              f"executed-refusal and reservation checks; "
              f"{killed} of {len(MUTANTS)} mutants killed")
        print("No board was contacted. The interpreter has no cache, TLB, store "
              "buffer, WFE/SEV timing or simultaneous execution, so coherency, "
              "observed ordering and parallelism remain silicon checks.")
    except AssertionError as failure:
        print(f"multicore_reservation_check: FAIL - {failure}")
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"scratch tree kept at {work}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
