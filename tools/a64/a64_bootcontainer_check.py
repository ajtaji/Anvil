#!/usr/bin/env python3
"""Executable gate for Anvil's BOOTLOADER - the verify-place-enter path.

Anvil/Core/pmfboot.pbi is the one part of this monitor that must never be
wrong, because being wrong means branching into memory that is not the
program somebody asked for.  This gate proves the outcomes that matter,
over the real compiled code, on the project's A64 emulator:

  (1) A GOOD CONTAINER IS ENTERED and the payload demonstrably RAN.
  (2) A CONTAINER WITH ONE CORRUPTED IMAGE BYTE IS REFUSED by the hash,
      and the payload is NOT entered.
  (3) A CONTAINER WHOSE LOAD ADDRESS OVERLAPS THE RUNNING MONITOR IS
      REFUSED, and nothing is entered.
  (5) A CONTAINER ASKING FOR BOTH A DEVICE TREE AND THE SERVICE TABLE IN
      x0 IS REFUSED BEFORE A BYTE IS PLACED - the ninth guard.

Case 4 - an entry point outside the image - is staged only by --mutate,
as the control for the mutant that removes that bound.

The program executed is the real artefact,
RaspberryPi4/Examples/Diagnostics/pi4BootContainerSelfTest.pi4, built with
the bench flags and run on tools/a64/a64_interp.py.  Its serial output is
printed below, so this log is what a board would say before a board says
it.

=====================================================================
 WHY THE HARNESS BUILDS THE CONTAINERS
=====================================================================
The obvious way to write this test is to have the program construct a
header in memory and then boot it.  That is a WEAKER test in an interesting
way: a header written by the same source file that reads it agrees with
itself whatever the layout actually is.  Put `load` at the wrong offset in
both and the test passes while every real container fails.

So the containers are laid out HERE, byte by byte, from the field table in
Anvil/Core/pmfboot.pbi's documentation, with the digest computed by
hashlib.  That makes three independent statements of the format:

  * the compiler's container writer
  * Anvil/Core/pmfboot.pbi, the monitor's reader
  * this file, the harness

and the gate is green only when all three agree.

The containers staged here are VERSION 1 (96-byte header).  Anvil main
reads versions 1 and 2, and keeps version 1 under its exact historical
contract; the version-2 extension (architecture, target, stack) is gated
by tools/pmfboot_v2_reader_check.py, and is not restated here.

=====================================================================
 WHERE "THE MONITOR" IS FOR THIS PROGRAM
=====================================================================
On Anvil main the monitor's region is not a constant.  HitsMonitor() in
Anvil/Core/memrange.pbi walks HwMonRegions(), and region 0 is the RUNNING
IMAGE, measured from its own __image_start__/__image_end__ by
RaspberryPi4/Board/memmap.pi4's HwMonLo()/HwMonHi().  The diagnostic
includes that memmap, so for the program under test the "monitor" is the
diagnostic's own image at LOAD.  Case 3 therefore aims at LOAD.

That makes case 3 STRICTER than it was when the region was a fixed
$00200000 window: LOAD is inside the low payload window (which starts at
#MON_LO plus the image size, rounded up to a megabyte), so InPayload()
accepts the range and HitsMonitor() is the only guard that can refuse it.
The no-monitor mutant below proves that.

=====================================================================
 --mutate
=====================================================================
A gate that is only ever green proves nothing.  --mutate builds damaged
COPIES of Anvil/Core/pmfboot.pbi (in a temporary directory; the tree is
never written) and requires each to be CAUGHT:

  no-hash        the digest comparison never sets its mismatch flag, so a
                 corrupted image would be entered.  Case 2 must go red.
  no-range       PmfCheckRange accepts every address.  Case 3 must go red.
  no-monitor     only the HitsMonitor test inside PmfCheckRange is removed.
                 Case 3 must still go red, because the payload window does
                 NOT cover for it at LOAD - see above.
  entry-unbound  the "entry must be inside the image" test is removed.
                 Caught by case 4, whose entry points outside its image.
  no-ninth       the both-flags guard is never consulted.  Case 5 must go
                 red.

Run:
    python tools/a64/a64_bootcontainer_check.py --compiler <PureMetalForge.exe>
    python tools/a64/a64_bootcontainer_check.py --compiler <...> --mutate
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
import gatecheck  # noqa: E402

CORE = ROOT / "Anvil" / "Core" / "pmfboot.pbi"
CORE_INCLUDE = 'XIncludeFile "Anvil/Core/pmfboot.pbi"'
SRC = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4BootContainerSelfTest.pi4"

# The bench flags.  A gate that ran a differently-linked image would be
# proving something about an artefact nobody deploys.
LOAD = 0x00400000
STACK = 0x03000000
LOADER_SP = 0x00100000

# ---------------------------------------------------------------------
#  THE CONTRACT WITH THE DIAGNOSTIC, stated in both files.
# ---------------------------------------------------------------------
BC_CASECELL = 0x01100000      # where the case number is staged
BC_CONTAINER = 0x01000000     # where the container is staged
BC_LOAD = 0x01200000          # where its header says the image goes
BC_OBSERVE = 0x01300000       # where the payload writes its known word
BC_MAGICVAL = 0xBEEF
BC_RETVAL = 0x5A5A

# THE RUNNING MONITOR'S BASE for the program under test: its own image at
# LOAD (memmap.pi4 HwMonLo() returns __image_start__).  Re-stated rather
# than parsed, because a harness that read the constant it is testing
# against would agree with a wrong one.
MON_LO = LOAD

# ---------------------------------------------------------------------
#  THE CONTAINER FORMAT, version 1.  From the field table in the header of
#  Anvil/Core/pmfboot.pbi.  Little-endian throughout.
#
#    0   8  magic "PMFBOOT\0"     32   8  imglen
#    8   4  version = 1           40   8  bssbase
#   12   4  hdrlen  = 96          48   8  bsslen
#   16   8  load                  56   4  flags
#   24   8  entry                 60   4  reserved
#                                 64  32  sha256(image)
# ---------------------------------------------------------------------
PMF_MAGIC = b"PMFBOOT\x00"
PMF_HDRLEN = 96
PMF_VERSION = 1
PMF_FLAG_RETURNS = 1
PMF_FLAG_WANTS_DTB = 2
PMF_FLAG_WANTS_SERVICES = 4

STEP_LIMIT = 200_000_000

UART_DR = 0xFE201000
UART_FR = 0xFE201018
GPIO_LO, GPIO_HI = 0xFE200000, 0xFE2000FF
PL011_LO, PL011_HI = 0xFE201000, 0xFE201FFF
FR_IDLE = 0x90


# ---------------------------------------------------------------------
#  THE PAYLOAD - five A64 instructions, assembled here.
#
#  Hand-encoded rather than compiled, so that the bytes placed are known
#  exactly and the digest over them is not a function of the compiler
#  under test.  Each word is spelled out against the Arm A-profile
#  encoding so a reader can check it without running anything.
# ---------------------------------------------------------------------
def movz(rd: int, imm16: int, shift: int) -> int:
    """MOVZ Xd, #imm16, LSL #shift: sf=1 opc=10 100101 hw imm16 Rd."""
    assert 0 <= imm16 <= 0xFFFF and shift in (0, 16, 32, 48)
    return (1 << 31) | (0b10 << 29) | (0b100101 << 23) | ((shift // 16) << 21) \
        | (imm16 << 5) | rd


def str_x(rt: int, rn: int) -> int:
    """STR Xt, [Xn], unsigned offset form with imm12 = 0."""
    return (0b11 << 30) | (0b111001 << 24) | (0b00 << 22) | (0 << 10) \
        | (rn << 5) | rt


RET = 0xD65F03C0                    # RET x30


def payload_words(observe: int, magic: int, retval: int) -> list[int]:
    """movz x1, #magic; movz x2, #(observe>>16), lsl 16; str x1, [x2];
    movz x0, #retval; ret.

    POSITION-INDEPENDENT BY CONSTRUCTION - no ADRP, no literal pool, no
    branch - because the whole point of the container is that the monitor
    PLACES the image at an address.
    """
    assert observe & 0xFFFF == 0, "the observation address must be a clean movz"
    return [movz(1, magic, 0), movz(2, observe >> 16, 16), str_x(1, 2),
            movz(0, retval, 0), RET]


def payload_bytes() -> bytes:
    return b"".join(struct.pack("<I", w)
                    for w in payload_words(BC_OBSERVE, BC_MAGICVAL, BC_RETVAL))


def make_container(image: bytes, load: int, entry: int,
                   bssbase: int = 0, bsslen: int = 0,
                   flags: int = PMF_FLAG_RETURNS,
                   digest_over: bytes | None = None) -> bytes:
    """The 96-byte version-1 header, then the image.

    digest_over lets a caller hash bytes OTHER than the ones it ships,
    which is exactly how case 2 is built.
    """
    body = image if digest_over is None else digest_over
    sha = hashlib.sha256(body).digest()
    hdr = bytearray(PMF_HDRLEN)
    hdr[0:8] = PMF_MAGIC
    struct.pack_into("<II", hdr, 8, PMF_VERSION, PMF_HDRLEN)
    struct.pack_into("<QQQQQ", hdr, 16, load, entry, len(image), bssbase, bsslen)
    struct.pack_into("<II", hdr, 56, flags, 0)
    hdr[64:96] = sha
    return bytes(hdr) + image


def case_container(case: int) -> bytes:
    img = payload_bytes()
    if case == 1:
        return make_container(img, BC_LOAD, BC_LOAD)
    if case == 2:
        # ONE CORRUPTED BYTE inside the STR instruction, with a header that
        # is otherwise perfect.  Every earlier guard passes; only the hash
        # can catch this.
        bad = bytearray(img)
        bad[9] ^= 0x01
        return make_container(bytes(bad), BC_LOAD, BC_LOAD, digest_over=img)
    if case == 3:
        # A LOAD ADDRESS ON THE RUNNING MONITOR, with an honest digest.
        return make_container(img, MON_LO, MON_LO)
    if case == 4:
        # --mutate only: the entry point is 0x100 past the end of the image.
        return make_container(img, BC_LOAD, BC_LOAD + len(img) + 0x100)
    if case == 5:
        # Bits 1 and 2 together, beside bit 0.  Otherwise a good container
        # at a good address: only the ninth guard can refuse it.
        return make_container(img, BC_LOAD, BC_LOAD,
                              flags=PMF_FLAG_RETURNS | PMF_FLAG_WANTS_DTB
                              | PMF_FLAG_WANTS_SERVICES)
    raise SystemExit(f"There is no case {case}; the cases are 1 to 5.")


CASE_NAME = {
    1: "a good container is verified, placed and ENTERED",
    2: "one corrupted image byte is REFUSED by the hash",
    3: "a load address overlapping the running monitor is REFUSED",
    4: "an entry outside the image is REFUSED",
    5: "a container asking for both a device tree and the table is REFUSED unplaced",
}
STANDING_CASES = (1, 2, 3, 5)


# ---------------------------------------------------------------------
#  BUILD AND RUN
# ---------------------------------------------------------------------
def build(compiler: str, source: pathlib.Path, out: pathlib.Path) -> dict[str, int]:
    cmd = [compiler, "--compile", str(source), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out), "-s"]
    r = subprocess.run(cmd, cwd=ROOT, text=True,
                       env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.exists():
        raise SystemExit("The diagnostic did not build, so nothing was tested. "
                         "The compiler said:\n" + r.stdout[-4000:])
    syms: dict[str, int] = {}
    symfile = pathlib.Path(str(out) + ".sym")
    for line in symfile.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                syms[k.strip()] = int(v.strip(), 0)
            except ValueError:
                pass
    return syms


def run_case(img: pathlib.Path, syms: dict[str, int], case: int):
    """Stage the container, poke the case number, execute.  Returns
    (uart text, the verdict globals)."""
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b

    # The container and the case number go in as OBSERVER writes: harness
    # staging is not the program under test and must not be able to trip
    # the program's alignment rule.
    for i, b in enumerate(case_container(case)):
        cpu.memory[BC_CONTAINER + i] = b
    # THE CASE NUMBER GOES IN MEMORY, NOT INTO A GLOBAL: a compiled image
    # initialises its data and clears its BSS in _start, so a global poked
    # before execution is gone before Main() looks at it.
    for i in range(8):
        cpu.memory[BC_CASECELL + i] = (case >> (8 * i)) & 0xFF

    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    lr = 0xDEADBEE0
    cpu.x[30] = lr

    mem = cpu.memory
    uart = bytearray()

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= 0xFE000000:
            if addr == UART_FR:
                return FR_IDLE
            if PL011_LO <= addr <= PL011_HI or GPIO_LO <= addr <= GPIO_HI:
                return 0
            raise SystemExit(f"The bootloader read unmodelled MMIO at "
                             f"${addr:08X}; it is supposed to touch no "
                             "hardware but the console.")
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFE000000:
            if addr == UART_DR:
                uart.append(value & 0xFF)
                return
            if PL011_LO <= addr <= PL011_HI or GPIO_LO <= addr <= GPIO_HI:
                return
            raise SystemExit(f"The bootloader wrote unmodelled MMIO at ${addr:08X}.")
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    steps = 0
    while steps < STEP_LIMIT:
        if cpu.pc == lr:
            break
        cpu.step()
        steps += 1
    else:
        raise SystemExit(f"Case {case} never returned after {steps} steps.\n"
                         + uart.decode("latin-1"))

    def g(name: str) -> int:
        a = syms.get("global_" + name)
        if a is None:
            raise SystemExit(f"The symbol map has no global_{name}, so the "
                             "verdict cannot be read.")
        v = sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(8))
        return v - (1 << 64) if v >= (1 << 63) else v

    return uart.decode("latin-1"), {
        "case": g("gbccase"),
        "booted": g("gbcbooted"),
        "observed": g("gbcobserved") & 0xFFFFFFFFFFFFFFFF,
        "rc": g("gbcrc") & 0xFFFFFFFFFFFFFFFF,
        "placed": g("gbcplaced") & 0xFFFFFFFFFFFFFFFF,
        "pass": g("gbcpass"),
        "ran": g("gbcran"),
    }


# ---------------------------------------------------------------------
#  THE HARNESS'S OWN JUDGEMENT.  The program judges itself, and that
#  verdict is read - but a program that computes both sides of an
#  assertion agrees with itself by construction, so the harness re-states
#  what each case must look like from the raw globals.
# ---------------------------------------------------------------------
def expected(case: int) -> dict[str, int]:
    if case == 1:
        return {"booted": 1, "observed": BC_MAGICVAL, "rc": BC_RETVAL}
    want = {"booted": 0, "observed": 0, "rc": 0}
    if case == 5:
        # Refused BEFORE placement: the load address still holds the zero
        # the program wrote there before the call.
        want["placed"] = 0
    return want


def judge(case: int, v: dict[str, int]) -> list[str]:
    problems: list[str] = []
    if v["ran"] != 1:
        problems.append("the program did not reach the end of Main, so the "
                        "verdict globals cannot be trusted")
    if v["case"] != case:
        problems.append(f"the program ran case {v['case']}, not {case}; the "
                        "case number never reached it")
    for k, want in expected(case).items():
        if v[k] != want:
            problems.append(f"{k} is 0x{v[k]:X}, expected 0x{want:X}")
    if case == 1 and v["placed"] != payload_words(BC_OBSERVE, BC_MAGICVAL, BC_RETVAL)[0] \
            | (payload_words(BC_OBSERVE, BC_MAGICVAL, BC_RETVAL)[1] << 32):
        problems.append("the first word at the load address is not the "
                        "payload's first two instructions, so what was "
                        "entered is not what the container carried")
    if v["pass"] != 1 and not problems:
        problems.append("the program itself reported RED while every value "
                        "the harness checks looks right; read its output")
    if v["pass"] == 1 and problems:
        problems.append("the program reported GREEN but the harness "
                        "disagrees, which is worse than either alone")
    return problems


# ---------------------------------------------------------------------
#  --mutate
# ---------------------------------------------------------------------
MUTANTS = {
    "no-hash": (
        "    If (gPmfGot[i] & $FF) <> (gPmfWant[i] & $FF)\n      bad = 1\n    EndIf",
        "    If (gPmfGot[i] & $FF) <> (gPmfWant[i] & $FF)\n      bad = 0\n    EndIf",
        2,
    ),
    "no-range": (
        "Procedure.i PmfCheckRange(lo.i, hi.i, *what)\n  If HitsMonitor(lo, hi) <> 0",
        "Procedure.i PmfCheckRange(lo.i, hi.i, *what)\n  ProcedureReturn 1\n  If HitsMonitor(lo, hi) <> 0",
        3,
    ),
    "no-monitor": (
        "Procedure.i PmfCheckRange(lo.i, hi.i, *what)\n  If HitsMonitor(lo, hi) <> 0",
        "Procedure.i PmfCheckRange(lo.i, hi.i, *what)\n  If 0 <> 0",
        3,
    ),
    "entry-unbound": (
        "  If gPmfEntry < gPmfLoad Or gPmfEntry > (gPmfLoad + gPmfImgLen - 1)",
        "  If 0 <> 0",
        4,
    ),
    "no-ninth": (
        "  If PmfCheckFlags() = 0",
        "  If 0 <> 0",
        5,
    ),
}


def mutate(compiler: str, work: pathlib.Path) -> int:
    original = CORE.read_text(encoding="utf-8")
    diag = SRC.read_text(encoding="utf-8")
    if diag.count(CORE_INCLUDE) != 1:
        print(f"  !! the diagnostic no longer includes {CORE_INCLUDE} exactly "
              "once, so no mutant can be substituted for it")
        return len(MUTANTS)
    failures = 0
    for name, (find, repl, case) in MUTANTS.items():
        print(f"\n=== mutant: {name} (case {case} must go RED) ===")
        if original.count(find) != 1:
            print(f"  !! the mutation site for {name} occurs "
                  f"{original.count(find)} times in {CORE.name}, not once; "
                  "this mutant proves nothing and the gate is ABSTAINING on it")
            failures += 1
            continue
        mdir = work / name
        mdir.mkdir(parents=True, exist_ok=True)
        mcore = mdir / "pmfboot.pbi"
        mcore.write_text(original.replace(find, repl, 1), encoding="utf-8")
        msrc = mdir / "bootc_mutant.pi4"
        msrc.write_text(diag.replace(
            CORE_INCLUDE, 'XIncludeFile "%s"' % mcore.resolve().as_posix()),
            encoding="utf-8")
        out = mdir / "bootc.img"
        try:
            syms = build(compiler, msrc, out)
            _, v = run_case(out, syms, case)
        except (SystemExit, RuntimeError) as e:
            # A mutant that will not build, or whose payload faults under the
            # emulator, is CAUGHT - the defect was detected, just not by the
            # program's own verdict - and said so out loud rather than counted
            # as a pass. The entry-unbound mutant lands here on purpose: the
            # monitor enters a wild address past the image, and the emulator
            # refuses the zero word it finds there.
            print(f"  caught: the mutant did not run cleanly ({e})")
            continue
        problems = judge(case, v)
        if not problems:
            print(f"  !! NOT CAUGHT - case {case} still passed with {name} "
                  "applied. The check this mutant removes is not doing anything.")
            failures += 1
        else:
            print(f"  caught: case {case} went RED, as it must "
                  f"(booted={v['booted']} observed=0x{v['observed']:X} "
                  f"placed=0x{v['placed']:X}; {problems[0]})")
    print(f"\n{CORE.name} was never opened for writing; every mutant was a "
          "copy in a temporary directory.")
    return failures


# ---------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge compiler (default: $PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true",
                    help="damage copies of the bootloader and require each defect to be caught")
    args = ap.parse_args()
    if not args.compiler:
        raise SystemExit("No compiler was named. Pass --compiler with the path "
                         "to PureMetalForge.exe, or set PMF_COMPILER.")
    if not pathlib.Path(args.compiler).is_file():
        raise SystemExit(f"The compiler {args.compiler} does not exist, so "
                         "nothing can be built.")

    with tempfile.TemporaryDirectory(prefix="anvil-bootcontainer-") as td:
        work = pathlib.Path(td)
        if args.mutate:
            bad = mutate(args.compiler, work)
            print()
            if bad:
                print(f"RESULT: RED ({bad} of {len(MUTANTS)} mutants not caught)")
                return 1
            print(f"RESULT: GREEN - all {len(MUTANTS)} damaged bootloaders were caught")
            return 0

        out = work / "bootc.img"
        syms = build(args.compiler, SRC, out)

        bad = 0
        ran = 0
        for case in STANDING_CASES:
            print("=" * 70)
            print(f"CASE {case}: {CASE_NAME[case]}")
            print("=" * 70)
            text, v = run_case(out, syms, case)
            ran += 1
            print(text.rstrip())
            problems = judge(case, v)
            print()
            print(f"  harness read back: booted={v['booted']} "
                  f"observed=0x{v['observed']:X} x0=0x{v['rc']:X} "
                  f"placed=0x{v['placed']:X} pass={v['pass']}")
            if problems:
                bad += 1
                for p in problems:
                    print(f"  !! {p}")
                print(f"  CASE {case}: RED")
            else:
                print(f"  CASE {case}: GREEN")
            print()

        gatecheck.examined(ran, "boot container cases", minimum=len(STANDING_CASES))

    n = len(STANDING_CASES)
    if bad:
        print(f"RESULT: RED ({bad} of {n} cases)")
        return 1
    print(f"RESULT: GREEN - {n} of {n}")
    print("  a good container is entered and its payload runs;")
    print("  a corrupted one is refused by the hash and never entered;")
    print("  one aimed at the running monitor is refused and never entered;")
    print("  one asking for both x0 pointers is refused before a byte is placed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
