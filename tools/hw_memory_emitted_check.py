#!/usr/bin/env python3
"""Compile and execute the memory-size decode and the top-of-memory refusal.

The instruction that started this work, 2026-09-17: "I think anvil should be
smart enough to know how much ram its working with." It now is, and this is
the desk proof of both halves:

  * HwMemFromRevision (RaspberryPi4/Board/hw_mem.pi4) turns the firmware's
    board revision code into a number of bytes - every MEMSIZE code the
    field can hold, the four codes a Pi 4 Model B actually ships with, and
    the old-style words that carry no memory field and must produce no size.
  * HwAddrCheck (RaspberryPi4/Board/hw_addr.pi4) refuses an address past the
    memory the board has, on a 256 MB, 512 MB, 1, 2 and 4 GB board, while
    leaving the peripheral aperture alone - and refuses nothing for that
    reason on a board that cannot say what size it is.
  * and refuses, harder and without asking the size at all, every address
    this monitor's page tables leave unmapped: everything above four
    gigabytes except the PCIe outbound window. THAT ONE CAME OFF THE BOARD.
    Build 183 was asked for $103FFFFC0 - real memory on a 4 GB board, which
    this seam had just called SAFE and which `info` had just invited an
    operator to read - and stopped on a level-1 translation fault, because
    MmuBuildTables leaves every slot between the low four gigabytes and the
    PCIe window at #MMU_DESC_FAULT. A fault is worse than a wrong value: the
    console dies with the monitor and the board needs its power removed.

WHAT IS PRODUCTION AND WHAT IS NOT. The decode, the overlap test, the
sentence table and the check are extracted VERBATIM from the two board
files and compiled; the peripheral boundary comes out of
RaspberryPi4/Lib/mmu.pi4 and the two SDRAM edges out of hw_addr.pi4, so a
number moved in any of the three moves here too. Only two things are
modelled: HwMemoryBytes(), which on the board asks the VideoCore firmware,
and the printing, which needs a console. Everything that decides is real.

SIX MUTANTS, and every one of them is a mistake that would have shipped
looking correct:

  wrong-shift        the MEMSIZE field taken from bits 21:19
  wrong-base         the exponent multiplying 512 MB instead of 256 MB
  narrow-mask        three bits of the field read instead of three
                     positions - 4 GB folds onto 256 MB
  old-style-accepted the scheme bit ignored, so a word with no memory
                     field is decoded as though it had one
  no-dram-top        the refusal deleted: the board is back to reading
                     past its own memory and printing the result as data
  unmapped-gone      the unmapped-span refusal deleted: build 183's fault
                     is available again, from an address the seam calls safe
  unmapped-late      the unmapped check moved BELOW the size check, so a
                     board that cannot say its size can still be walked
                     into a fault - the fault never asked the size

WHY THE HwAddrCheck MUTANTS LIVE HERE rather than in
tools/a64/a64_anvil_check.py, which is the gate that covers the seam. That
gate builds both whole monitors and calls the real HwAddrCheck in them; it
now carries the top-of-memory cases against the real image, which is where
they belong. A mutant there would mean rebuilding a three-megabyte monitor
per mutation to change four lines. This gate compiles the same production
procedures on their own, so a mutation costs a second. Both run the same
text; neither is a substitute for the other.

Usage:
  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=tools/a64/a64_interp.py \
      python tools/hw_memory_emitted_check.py
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
HW_MEM = ROOT / "RaspberryPi4" / "Board" / "hw_mem.pi4"
HW_ADDR = ROOT / "RaspberryPi4" / "Board" / "hw_addr.pi4"
MMU = ROOT / "RaspberryPi4" / "Lib" / "mmu.pi4"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "hw_memory_emitted_gate.pi4"

PERIPH_MARKER = "; @@PRODUCTION_PERIPH_BASE@@"
EDGES_MARKER = "; @@PRODUCTION_DRAM_EDGES@@"
DECODE_MARKER = "; @@PRODUCTION_HW_MEM_FROM_REVISION@@"
HIT_MARKER = "; @@PRODUCTION_PI_ADDR_HIT@@"
WHY_MARKER = "; @@PRODUCTION_PI_MEM_TOO_HIGH_WHY@@"
CHECK_MARKER = "; @@PRODUCTION_HW_ADDR_CHECK@@"

ASSERTIONS = 71

# The sizes that must each have a sentence of their own in the production
# table. A refusal that does not name the size is the refusal this work
# exists to replace.
SPOKEN_SIZES = ("256 MB", "512 MB", "1 GB", "2 GB", "4 GB", "8 GB")


def extract_procedure(source: str, header: str, label: str) -> str:
    if source.count(header) != 1:
        raise SystemExit(
            f"hw memory gate: {label} start count {source.count(header)}"
        )
    start = source.index(header)
    end = source.find("\nEndProcedure", start)
    if end < 0:
        raise SystemExit(f"hw memory gate: {label} has no end")
    return source[start : end + len("\nEndProcedure")] + "\n"


def extract_constant(source: str, name: str, label: str) -> str:
    """The production line defining one constant, reproduced exactly.

    Copying the LINE and not the value is deliberate: the gate then carries
    no second opinion about the number, and a constant that is moved shows
    up here as a different fixture rather than as a silent agreement.
    """
    pattern = re.compile(r"^%s\s*=.*$" % re.escape(name), re.MULTILINE)
    found = pattern.findall(source)
    if len(found) != 1:
        raise SystemExit(f"hw memory gate: {label} definition count {len(found)}")
    return found[0].split(";")[0].rstrip() + "\n"


def production() -> dict[str, str]:
    mem = HW_MEM.read_text(encoding="utf-8")
    addr = HW_ADDR.read_text(encoding="utf-8")
    mmu = MMU.read_text(encoding="utf-8")

    decode = extract_procedure(
        mem, "Procedure.i HwMemFromRevision(rev.i)", "HwMemFromRevision"
    )
    if "268435456" not in decode:
        raise SystemExit(
            "hw memory gate: the decode no longer multiplies 256 MB written out"
        )
    why = extract_procedure(
        addr, "Procedure.i PiMemTooHighWhy(bytes.i)", "PiMemTooHighWhy"
    )
    for size in SPOKEN_SIZES:
        if size not in why:
            raise SystemExit(
                f"hw memory gate: no refusal sentence names {size}; the whole "
                "point of the sentence is that it names the size"
            )
    check = extract_procedure(
        addr, "Procedure.i HwAddrCheck(lo.i, hi.i, forWrite.i)", "HwAddrCheck"
    )
    if check.count("ProcedureReturn #HW_ADDR_ABSENT") != 1:
        raise SystemExit(
            "hw memory gate: HwAddrCheck does not have exactly one "
            "top-of-memory refusal - the run above four gigabytes is refused "
            "as unmapped, before the size is asked, and not as absent"
        )
    if check.count("ProcedureReturn #HW_ADDR_UNCLOCKED") != 4:
        raise SystemExit(
            "hw memory gate: HwAddrCheck does not have exactly four unmapped "
            "refusals - the negative guard, the span above four gigabytes, "
            "the span above the PCIe window, and past the regime entirely"
        )
    return {
        # The three numbers the page tables are built from come out of
        # mmu.pi4, and the probe recomputes the window's addresses from the
        # two slot numbers rather than being told them - which is what makes
        # the edges in hw_addr.pi4 a claim something can falsify.
        "periph": (
            extract_constant(mmu, "#MMU_PERIPH_BASE", "#MMU_PERIPH_BASE")
            + extract_constant(mmu, "#MMU_PCIE_SLOT_LO", "#MMU_PCIE_SLOT_LO")
            + extract_constant(mmu, "#MMU_PCIE_SLOT_HI", "#MMU_PCIE_SLOT_HI")
        ),
        "edges": (
            extract_constant(addr, "#PI_DRAM_HIGH_BASE", "#PI_DRAM_HIGH_BASE")
            + extract_constant(addr, "#PI_PCIE_WINDOW_LO", "#PI_PCIE_WINDOW_LO")
            + extract_constant(addr, "#PI_PCIE_WINDOW_HI", "#PI_PCIE_WINDOW_HI")
            + extract_constant(addr, "#PI_VA_TOP", "#PI_VA_TOP")
        ),
        "decode": decode,
        "hit": extract_procedure(
            addr, "Procedure.i PiAddrHit(lo.i, hi.i, blo.i, bhi.i)", "PiAddrHit"
        ),
        "why": why,
        "check": check,
    }


def fixture(parts: dict[str, str]) -> str:
    template = FIXTURE.read_text(encoding="utf-8")
    for marker in (PERIPH_MARKER, EDGES_MARKER, DECODE_MARKER, HIT_MARKER,
                   WHY_MARKER, CHECK_MARKER):
        if template.count(marker) != 1:
            raise SystemExit(
                f"hw memory gate: fixture marker {marker} count "
                f"{template.count(marker)}"
            )
    return (
        template.replace(PERIPH_MARKER, parts["periph"])
        .replace(EDGES_MARKER, parts["edges"])
        .replace(DECODE_MARKER, parts["decode"])
        .replace(HIT_MARKER, parts["hit"])
        .replace(WHY_MARKER, parts["why"])
        .replace(CHECK_MARKER, parts["check"])
    )


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"hw memory gate: {label} site count {text.count(old)}")
    return text.replace(old, new, 1)


def mutate(parts: dict[str, str], name: str) -> dict[str, str]:
    out = dict(parts)
    if name == "wrong-shift":
        out["decode"] = replace_once(
            out["decode"], "(rev >> 20) & 7", "(rev >> 19) & 7", name
        )
        return out
    if name == "wrong-base":
        out["decode"] = replace_once(out["decode"], "268435456", "536870912", name)
        return out
    if name == "narrow-mask":
        out["decode"] = replace_once(
            out["decode"], "(rev >> 20) & 7", "(rev >> 20) & 3", name
        )
        return out
    if name == "old-style-accepted":
        guard = "  If (rev & $00800000) = 0\n    ProcedureReturn #HW_MEM_UNKNOWN\n  EndIf\n"
        out["decode"] = replace_once(out["decode"], guard, "", name)
        return out
    if name == "no-dram-top":
        check = out["check"]
        if check.count("ProcedureReturn #HW_ADDR_ABSENT") != 1:
            raise SystemExit("hw memory gate: no-dram-top site count drifted")
        out["check"] = check.replace(
            "ProcedureReturn #HW_ADDR_ABSENT", "ProcedureReturn #HW_ADDR_SAFE", 1
        )
        return out
    if name == "unmapped-gone":
        # Every arm of the unmapped check waved through. The board is back
        # to answering SAFE for the address that stopped build 183.
        check = out["check"]
        if check.count("ProcedureReturn #HW_ADDR_UNCLOCKED") != 4:
            raise SystemExit("hw memory gate: unmapped-gone site count drifted")
        out["check"] = check.replace(
            "ProcedureReturn #HW_ADDR_UNCLOCKED", "ProcedureReturn #HW_ADDR_SAFE")
        return out
    if name == "unmapped-late":
        # The order reversed: the size is consulted first, so a board that
        # could not say returns SAFE before the fault is ever considered.
        # The fault does not ask how much memory is fitted, and neither may
        # the refusal.
        check = out["check"]
        early = "  bytes = HwMemoryBytes()\n  If bytes = #HW_MEM_UNKNOWN\n    ProcedureReturn #HW_ADDR_SAFE\n  EndIf\n"
        if check.count(early) != 1:
            raise SystemExit("hw memory gate: unmapped-late site drifted")
        anchor = "  If lo < 0 Or hi < 0\n"
        if check.count(anchor) != 1:
            raise SystemExit("hw memory gate: unmapped-late anchor drifted")
        out["check"] = check.replace(early, "", 1).replace(anchor, early + anchor, 1)
        return out
    raise SystemExit(f"hw memory gate: unknown mutation {name}")


def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir() and not (work / "Boards").exists():
        shutil.copytree(boards, work / "Boards")
    source = work / f"{stem}.pi4"
    source.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    command = [
        str(staged), "--compile",
        str(source),
        "-t", "pi4",
        "--load-addr", hex(emitted.LOAD),
        "--stack-addr", hex(emitted.STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    run = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"hw memory gate: {stem} compile failed\n{run.stdout}")
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit(
            f"hw memory gate: {stem} compiler omitted image or symbol map"
        )
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(
        args.interp or str(ROOT / "tools" / "a64" / "a64_interp.py"),
        "PMF_A64_INTERP",
    )
    a64 = emitted.load_interpreter(interp)

    parts = production()
    digest = hashlib.sha256(
        "".join(parts[k] for k in ("periph", "edges", "decode", "hit", "why",
                                   "check")).encode("utf-8")
    ).hexdigest()

    mutations = (
        ("wrong-shift", 2),
        ("wrong-base", 1),
        ("narrow-mask", 5),
        ("old-style-accepted", 13),
        ("no-dram-top", 22),
        # It dies at 29, not at 120: the very first case above four
        # gigabytes already depends on the refusal, which is the point.
        ("unmapped-gone", 29),
        # Caught at 93, the first case that asks an unmapped address on a
        # board whose size is unknown - which is exactly the hole the
        # reordering opens.
        ("unmapped-late", 93),
    )

    with tempfile.TemporaryDirectory(prefix="anvil-hw-memory-") as temporary:
        work = Path(temporary)
        image = build(compiler, work, fixture(parts), "hw_memory_gate")
        result, steps = emitted.execute(a64, image)
        if result:
            print(
                f"hw_memory_emitted_check: FAIL assertion {result} after "
                f"{steps:,} A64 instructions"
            )
            return 1

        killed = []
        for name, expected in mutations:
            mutant = fixture(mutate(parts, name))
            mutant_image = build(compiler, work, mutant, f"hw_memory_mutant_{name}")
            mutant_result, mutant_steps = emitted.execute(a64, mutant_image)
            if mutant_result != expected:
                print(
                    f"hw_memory_emitted_check: FAIL {name} mutation returned "
                    f"{mutant_result}; expected assertion {expected}"
                )
                return 1
            killed.append((name, expected, mutant_steps))

    print(
        f"hw_memory_emitted_check: PASS - {ASSERTIONS} assertions, "
        f"{steps:,} A64 instructions"
    )
    print("  every MEMSIZE code decoded, the four shipped Pi 4 codes, five")
    print("  old-style words refused a size; the top of memory refused on 256 MB,")
    print("  512 MB, 1, 2, 4 and 8 GB boards with the aperture left alone and")
    print("  nothing refused for size when the size is unknown; one sentence per")
    print("  size, all different, cleared after SAFE; and every address this")
    print("  monitor does not map refused without the size being asked, with the")
    print("  PCIe window recomputed here from mmu.pi4's own slot numbers")
    for name, expected, mutant_steps in killed:
        print(
            f"  {name} mutation rejected at assertion {expected} "
            f"after {mutant_steps:,} instructions"
        )
    print(f"  production decode+edges+check sha256 {digest}")
    print("No hardware was contacted: the firmware answer is a modelled seam, so")
    print("this is a source and emitted-code proof only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
