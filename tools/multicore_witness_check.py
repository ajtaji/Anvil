#!/usr/bin/env python3
"""Gate the bounded secondary-core witness before it is ever sent to a board.

The witness is a RETURNING PAYLOAD that must release no core. This proves
that by EXECUTION rather than by reading it: the real built image runs under
the A64 interpreter at five different machine states, and every claim below
is read out of the instruction words and the memory writes the image actually
performs.

  * it never stores below 0x1000, so no firmware spin slot can be armed;
  * it executes no SEV, so no parked core can be woken;
  * it never reads the implementation-defined CPUECTLR_EL1 below EL3, where
    that read can trap into a vector table this board does not have;
  * its verdict is the right one at EL2 (the level the board boots at today),
    at EL3 without M/C/I, at EL3 without SMPEN, and at EL3 with everything;
  * its wait is a WALL-CLOCK deadline off the architectural counter - proven
    by running the same image against two different CNTFRQ_EL0 values and
    requiring the measured tick budget to follow the frequency - and it
    refuses a READY word carrying another run's nonce.

The counter is modelled: CNTPCT_EL0 advances a fixed amount per instruction,
which is the only way a single-threaded model can have a clock at all. That
makes the deadline ARITHMETIC checkable and says nothing about real time on
the part. No board is contacted.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build as anvil_build  # noqa: E402

WITNESS = Path("RaspberryPi4/Examples/Diagnostics/pi4CoreWitness.pi4")
TIMER = Path("RaspberryPi4/Lib/timer.pi4")
MEMMAP = Path("RaspberryPi4/Board/memmap.pi4")
COPIED = (WITNESS, TIMER, MEMMAP)

LOAD = 0x00500000
STACK = 0x04F00000
RETURN_PC = 0xDEAD0000
REPORT_WORDS = 32
MAGIC = 0x4357495441424C45

CNTFRQ_READ = 0xD53BE000
CNTPCT_READ = 0xD53BE020
TICKS_PER_STEP = 64                 # modelled, see the module docstring


def sysreg_key(op0: int, op1: int, crn: int, crm: int, op2: int) -> int:
    return (0xD5100000 | ((op0 == 3) << 19) | (op1 << 16) |
            (crn << 12) | (crm << 8) | (op2 << 5))


MPIDR_EL1 = sysreg_key(3, 0, 0, 0, 5)
SCTLR_EL2 = sysreg_key(3, 4, 1, 0, 0)
SCTLR_EL3 = sysreg_key(3, 6, 1, 0, 0)
CPUECTLR_EL1 = sysreg_key(3, 1, 15, 2, 1)

SMPEN = 0x40
SCTLR_CACHED = 0x30C51835
SCTLR_STUB = 0x30C50830             # what both stubs leave: M, C and I clear

OK_WOULD_ADMIT = 0
ERR_NOT_EL3 = 1
ERR_NO_MCI = 2
ERR_NO_SMPEN = 3
ERR_NO_CLOCK = 4
ERR_WAIT_BROKEN = 5

WAIT_READY = 1
WAIT_TIMEOUT = 0
WAIT_NO_CLOCK = -4
WAIT_STALE = -13

TEST_MS = 5


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, value: bool, message: str) -> None:
        self.count += 1
        if not value:
            raise AssertionError(message)

    def eq(self, got, want, message: str) -> None:
        self.yes(got == want, f"{message}: got {got!r}, wanted {want!r}")


def mutant_root(work: Path, label: str, source_root: Path,
                edits: list[tuple[Path, str, str]]) -> Path:
    root = work / f"root-{label}"
    for relative in COPIED:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, target)
    shutil.copy2(source_root / "keywords.def", root / "keywords.def")
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


def build(pmfc: str, work: Path, source_root: Path, stem: str) -> Path:
    compiler_dir = work / f"compiler-{stem}"
    compiler_dir.mkdir(parents=True, exist_ok=True)
    staged = anvil_build.staged_compiler(pmfc, compiler_dir)
    image = work / f"{stem}.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(source_root)
    cmd = [staged, WITNESS.as_posix(), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-S", "-s", "-o", str(image)]
    done = subprocess.run(cmd, cwd=source_root, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode or not image.is_file():
        raise AssertionError(f"witness build failed ({stem}):\n{done.stdout}")
    return image


def symbols(image: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            out[name.strip().lower()] = int(value.strip())
    return out


def load_interp(path: Path):
    spec = importlib.util.spec_from_file_location("mcw_a64", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load interpreter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(a64, image: Path, sym: dict[str, int], el: int, sctlr: int,
        smpen: int, hz: int, budget: int = 4000000):
    """One complete execution of the real witness image."""
    mem = {LOAD + i: b for i, b in enumerate(image.read_bytes())}

    class Witness(a64.A64):
        def __init__(self) -> None:
            super().__init__()
            self.ticks = 0x1000
            self.sev = 0
            self.wfe = 0
            self.ldar = 0
            self.stlr = 0
            self.low_stores: list[int] = []
            self.sysreg_reads: list[int] = []
            self.cntpct_reads = 0

        def step(self) -> None:
            ins = self.fetch(self.pc)
            if (ins & 0xFFFFFFE0) == CNTPCT_READ:
                self.x[ins & 31] = self.ticks
                self.ticks += TICKS_PER_STEP
                self.cntpct_reads += 1
                self.pc = (self.pc + 4) & 0xFFFFFFFFFFFFFFFF
                return
            if (ins & 0xFFFFFFE0) == CNTFRQ_READ:
                self.x[ins & 31] = hz
                self.pc = (self.pc + 4) & 0xFFFFFFFFFFFFFFFF
                return
            if ins == 0xD503209F:
                self.sev += 1
            elif ins == 0xD503205F:
                self.wfe += 1
            elif (ins & 0xFFFFFC00) == 0xC8DFFC00:
                self.ldar += 1
            elif (ins & 0xFFFFFC00) == 0xC89FFC00:
                self.stlr += 1
            elif (ins & 0xFFF00000) == 0xD5300000:
                self.sysreg_reads.append(
                    (ins & self.SYSREG_WRITE_MASK) & ~self.SYSREG_READ_BIT)
            super().step()

        def store(self, addr: int, value: int, size: int) -> None:
            # The firmware's AArch64 spin table is the first 4 KiB. A witness
            # that writes ANYTHING there can arm a parked core, so the ban is
            # on the whole page rather than on four addresses.
            if addr < 0x1000:
                self.low_stores.append(addr)
            super().store(addr, value, size)

    cpu = Witness()
    cpu.memory = mem
    bank = {2: SCTLR_EL2, 3: SCTLR_EL3}[el]
    cpu.enable_system_registers(
        el=el, preset={MPIDR_EL1: 0x80000000, bank: sctlr,
                       CPUECTLR_EL1: smpen})
    cpu.pc = LOAD + sym["main"]
    cpu.sp = STACK
    cpu.x[30] = RETURN_PC
    steps = 0
    while cpu.pc != RETURN_PC and steps < budget:
        cpu.step()
        steps += 1
    if cpu.pc != RETURN_PC:
        raise AssertionError(
            f"the witness did not return in {budget} instructions at EL{el}; "
            "an unbounded wait is the failure this gate exists to catch")
    return cpu, mem, steps


def report(mem, address: int) -> list[int]:
    out = []
    for i in range(REPORT_WORDS):
        raw = sum(mem.get(address + i * 8 + b, 0) << (8 * b) for b in range(8))
        out.append(raw - (1 << 64) if raw >> 63 else raw)
    return out


def source_checks(c: Checks, source_root: Path) -> None:
    text = (source_root / WITNESS).read_text(encoding="utf-8")
    memmap = (source_root / MEMMAP).read_text(encoding="utf-8")

    # The witness repeats the board's reservation as constants on purpose -
    # including a BOARD file in a PAYLOAD would also bring HwMonLo()/HwMonHi(),
    # which measure whichever image contains them. The repetition is only safe
    # while something checks it, so this is that something.
    for name, want in (("#CW_STACK_LO", "$001FC000"),
                       ("#CW_STACK_PAGE", "$00001000")):
        got = re.search(rf"{re.escape(name)}\s*=\s*(\$[0-9A-F]+)", text)
        c.yes(got is not None, f"the witness does not define {name}")
        c.eq(got.group(1), want, f"{name} drifted from the board's declaration")
    c.yes("#CORE_RAW_STACK_LO    = $001FC000" in memmap and
          "#CORE_RAW_STACK_PAGE  = $00001000" in memmap,
          "the board's raw-stack reservation moved; the witness's repeated "
          "constants must move with it")
    c.eq(re.search(r"#CW_STACK_CORES\s*=\s*(\d+)", text).group(1), "3",
         "the witness does not cover the board's three reserved pages")

    # Stated in the header and enforced here: the only writes are to this
    # program's own state. Comment lines are stripped first - this file's own
    # header NAMES the procedures it refuses to call, and a substring search
    # that cannot tell prose from code would forbid explaining the rule.
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith(";"))
    pokes = re.findall(r"(?m)^\s*PokeI\s*\(([^,]+),", code)
    c.yes(not pokes, f"the witness performs a PokeI: {pokes}")
    for name in ("CoreRawPrepare", "CoreRawRelease", "a64_send_event"):
        c.yes(name not in code,
              f"the witness calls {name}; see its header for the three separate "
              "reasons a payload must not release a core")


def grade(c: Checks, a64, image: Path, source_root: Path) -> None:
    source_checks(c, source_root)
    sym = symbols(image)
    for name in ("main", "global_cw_report", "global_cw_state", "global_cw_nonce"):
        c.yes(name in sym, f"the witness is missing symbol {name}")

    hz = 54_000_000
    runs = {
        "el2-stub": (2, SCTLR_STUB, 0, ERR_NOT_EL3),
        "el2-cached": (2, SCTLR_CACHED, 0, ERR_NOT_EL3),
        "el3-cold": (3, SCTLR_STUB, SMPEN, ERR_NO_MCI),
        "el3-no-smpen": (3, SCTLR_CACHED, 0, ERR_NO_SMPEN),
        "el3-ready": (3, SCTLR_CACHED, SMPEN, OK_WOULD_ADMIT),
    }
    for label, (el, sctlr, smpen, want_status) in runs.items():
        cpu, mem, _ = run(a64, image, sym, el, sctlr, smpen, hz)
        block = report(mem, sym["global_cw_report"])

        c.eq(block[0], MAGIC, f"{label}: the report block has no magic")
        c.eq(block[31], MAGIC, f"{label}: the report block has no trailing magic")
        c.eq(cpu.x[0], sym["global_cw_report"],
             f"{label}: x0 is not the report block's address")
        c.eq(block[2], want_status, f"{label}: wrong verdict")
        c.eq(block[4], el, f"{label}: the witness misreported the exception level")
        c.eq(block[5], sctlr, f"{label}: the witness read the wrong SCTLR")

        # --- it releases nothing, proven by execution ---------------------
        c.eq(cpu.low_stores, [],
             f"{label}: the witness wrote the firmware spin-table page at "
             f"{[hex(a) for a in cpu.low_stores]} - that is how a core is armed")
        c.eq(cpu.sev, 0, f"{label}: the witness executed SEV")
        c.eq(cpu.wfe, 0, f"{label}: the witness executed WFE and can hang")
        c.eq(cpu.stlr, 0,
             f"{label}: the witness published a state word; it has no core to "
             "publish for")

        # --- the implementation-defined read stays above EL2 --------------
        if el == 3:
            c.yes(CPUECTLR_EL1 in cpu.sysreg_reads,
                  f"{label}: CPUECTLR_EL1 was not read at EL3")
            c.eq(block[6], smpen, f"{label}: CPUECTLR_EL1 was misreported")
        else:
            c.yes(CPUECTLR_EL1 not in cpu.sysreg_reads,
                  f"{label}: the witness read the implementation-defined "
                  "CPUECTLR_EL1 below EL3, where it can trap into a vector "
                  "table this board does not install")
            c.eq(block[6], -1,
                 f"{label}: an unread CPUECTLR_EL1 must report -1, not a value")

        # --- the wait contract, executed ----------------------------------
        c.eq(block[22], WAIT_TIMEOUT,
             f"{label}: a word that never became ready did not time out")
        c.eq(block[24], WAIT_READY,
             f"{label}: a word ready with this run's nonce was not accepted")
        c.eq(block[26], WAIT_STALE,
             f"{label}: a READY word carrying another run's nonce was accepted")
        limit = (hz * TEST_MS) // 1000
        c.yes(block[23] >= limit,
              f"{label}: the timeout returned after {block[23]} ticks, short of "
              f"the {limit}-tick deadline it was given")
        c.yes(block[25] < limit,
              f"{label}: an already-ready word still burned the whole deadline")
        c.yes(block[27] < limit,
              f"{label}: a stale word still burned the whole deadline")
        c.yes(cpu.ldar >= 3,
              f"{label}: the state word was not consumed with an acquire load "
              f"in every wait ({cpu.ldar} acquire loads)")

        # --- it leaves nothing behind that a later run could believe ------
        left_state = sum(mem.get(sym["global_cw_state"] + b, 0) << (8 * b)
                         for b in range(8))
        left_nonce = sum(mem.get(sym["global_cw_nonce"] + b, 0) << (8 * b)
                         for b in range(8))
        c.eq(left_state, 0,
             f"{label}: the witness left its own state word saying READY - the "
             "exact stale word its third self-test refuses")
        c.eq(left_nonce, 0, f"{label}: the witness left its nonce in memory")

    # --- the deadline follows the COUNTER, not a loop count ---------------
    slow = report(run(a64, image, sym, 3, SCTLR_CACHED, SMPEN, hz)[1],
                  sym["global_cw_report"])
    fast = report(run(a64, image, sym, 3, SCTLR_CACHED, SMPEN, hz * 4)[1],
                  sym["global_cw_report"])
    c.yes(fast[23] > slow[23] * 3,
          "the timeout did not scale with CNTFRQ_EL0: "
          f"{slow[23]} ticks at {hz} Hz against {fast[23]} at {hz * 4} Hz. "
          "A bound that ignores the frequency is a spin count wearing a "
          "deadline's name")

    # --- no clock, no deadline, and it says so ---------------------------
    _, mem, _ = run(a64, image, sym, 3, SCTLR_CACHED, SMPEN, 0)
    block = report(mem, sym["global_cw_report"])
    c.eq(block[2], ERR_NO_CLOCK,
         "a zero CNTFRQ_EL0 did not produce the no-clock verdict")
    c.eq(block[22], WAIT_NO_CLOCK,
         "the wait invented a deadline from a zero counter frequency")


MUTANTS: list[tuple[str, list[tuple[Path, str, str]]]] = [
    # Written in ASM on purpose: a source-text ban on PokeI would catch a
    # PokeI, and the thing that actually arms a core is a STORE. This one is
    # invisible to every text check and has to be caught by execution.
    ("arms-a-spin-slot",
     [(WITNESS, "    mrs x0, mpidr_el1",
       "    movz x9, #0xE0\n    movz x10, #1\n    str  x10, [x9]\n    mrs x0, mpidr_el1")]),
    ("wakes-the-parked-cores",
     [(WITNESS, "    mrs x0, mpidr_el1", "    sev\n    mrs x0, mpidr_el1")]),
    ("nonce-not-checked",
     [(WITNESS, "      If cw_nonce = nonce", "      If 1 = 1")]),
    ("deadline-becomes-a-single-pass",
     [(WITNESS, "  Until Ticks() - start >= limit", "  Until 1 = 1")]),
    ("deadline-ignores-the-frequency",
     [(WITNESS, "  limit = (hz * ms) / 1000", "  limit = 1000")]),
    ("cpuectlr-read-below-el3",
     [(WITNESS, "  If el = 3\n    ectlr = cwCpuectlrEl1()\n  EndIf",
       "  ectlr = cwCpuectlrEl1()")]),
    ("acquire-downgraded",
     [(WITNESS, "    ldar x0, [x0]", "    ldr  x0, [x0]")]),
    ("no-clock-refusal-removed",
     [(WITNESS, "  hz = TickHz()\n  If hz <= 0\n    ProcedureReturn #CW_WAIT_NO_CLOCK\n  EndIf",
       "  hz = TickHz()")]),
    ("leaves-its-own-word-ready",
     [(WITNESS, "  cw_state = #CW_STATE_IDLE\n  cw_nonce = 0\n\n  cwPut(29, t0)",
       "  cwPut(29, t0)")]),
    ("reservation-constant-drifts",
     [(WITNESS, "#CW_STACK_LO         = $001FC000",
       "#CW_STACK_LO         = $001FD000")]),
    ("writes-outside-its-own-state",
     [(WITNESS, "  cwPut(2, status)",
       "  PokeI(#CW_STACK_LO, 0)\n  cwPut(2, status)")]),
]


def main() -> int:
    if not __debug__:
        print("multicore_witness_check: FAIL - Python -O disables the "
              "assertions this gate is made of")
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    parser.add_argument("--verbose", action="store_true",
                        help="print which check killed each mutant")
    args = parser.parse_args()
    compiler = anvil_build.find_compiler(args.pmfc)

    c = Checks()
    a64 = load_interp(ROOT / "tools" / "a64" / "a64_interp.py")
    work = Path(tempfile.mkdtemp(prefix="anvil-multicore-witness-"))
    try:
        image = build(compiler, work, ROOT, "witness")
        grade(c, a64, image, ROOT)
        primary = c.count
        killed = 0
        for label, edits in MUTANTS:
            root = mutant_root(work, label, ROOT, edits)
            try:
                mutant_image = build(compiler, work, root, f"mutant-{label}")
            except AssertionError:
                killed += 1
                if args.verbose:
                    print(f"  killed {label}: refused by the compiler")
                continue
            try:
                grade(Checks(), a64, mutant_image, root)
            except AssertionError as why:
                killed += 1
                if args.verbose:
                    print(f"  killed {label}: {str(why).splitlines()[0][:150]}")
            else:
                raise AssertionError(f"mutation survived: {label}")
        size = image.stat().st_size
        print(f"multicore_witness_check: PASS - {primary} executed checks over "
              f"six machine states; {killed} of {len(MUTANTS)} mutants killed")
        print(f"witness image {image.name}: {size} bytes, no SEV, no store below "
              "0x1000, no CPUECTLR_EL1 read below EL3.")
        print("No board was contacted. The counter is modelled, so the deadline "
              "is proven as arithmetic and not as real time; nothing here says a "
              "second core exists, starts, or is coherent.")
    except AssertionError as failure:
        print(f"multicore_witness_check: FAIL - {failure}")
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
