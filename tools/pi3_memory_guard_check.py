#!/usr/bin/env python3
"""Compile and EXECUTE the Raspberry Pi 3 monitor's memory decode, its map
and its address guard, and prove the guard and the page tables agree.

The other board in this tree learned on silicon what happens when they do
not. Build 183 was asked for an address its seam called SAFE and its page
tables left unmapped; it took a level-1 translation fault, the console died
with the monitor and the board had to have its power removed by hand. So
this board's guard does not have its own opinion about what is where: it
asks MmuAttrFor(pa), the same pure procedure the table builder asks, and
this gate walks the boundaries proving the two answer consistently.

WHAT IS PRODUCTION AND WHAT IS NOT. The decode, the map, the overlap test,
the memory-top rule and the check are extracted VERBATIM from
RaspberryPi3/Lib/mmu.pi3, RaspberryPi3/Board/hw_mem.pi3 and
RaspberryPi3/Board/hw_addr.pi3 and compiled for this board's own target.
Two things are modelled and nothing else: HwMemoryBytes(), which on the
board is a firmware property tag read once before the MMU comes on, and
pi3_ram_end, which is the firmware's statement of the processor's share.
Everything that DECIDES is the production code.

THE TWO PLACES THE GUARD AND THE TABLES DELIBERATELY DIFFER are asserted
as disagreements rather than skipped:

  * the VideoCore's share - mapped as ordinary memory because it IS
    memory, refused because it is not the processor's to read. A read
    there completes and returns rubbish, which is worse than a fault
    because it looks like data.
  * the 2 MB block containing the 4 KB processor-local window - mapped
    Device because a level-2 block is the finest thing the tables can
    express, refused above the window because the guard can be finer.
    Tighter is the safe direction; a refusal leaves the board at its
    prompt.

SEVEN MUTANTS, and every one is a mistake that would have shipped looking
correct:

  wrong-shift        the MEMSIZE field taken from bits 21:19
  wrong-base         the exponent multiplying 512 MB instead of 256 MB
  old-style-accepted the scheme bit ignored, so a word with no memory
                     field is decoded as though it had one
  attr-device        DRAM described to the table builder as Device
                     memory - every unaligned access in the shared
                     filesystems becomes an alignment fault, which is the
                     whole reason this board turns the MMU on
  local-top-loose    the guard's processor-local edge taken from the
                     2 MB block instead of the 4 KB window, so the
                     tighter-than-the-tables property is lost
  absent-gone        the top-of-memory refusal deleted: the monitor is
                     back to reading the VideoCore's share and printing
                     it as data
  armtop-ignores-fw  the guard stops asking what the firmware gave the
                     processor and uses the aperture always - the same
                     hole, arrived at from the other side

Usage:
  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=tools/a64/a64_interp.py \
      python tools/pi3_memory_guard_check.py
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
MMU = ROOT / "RaspberryPi3" / "Lib" / "mmu.pi3"
HW_MEM = ROOT / "RaspberryPi3" / "Board" / "hw_mem.pi3"
HW_ADDR = ROOT / "RaspberryPi3" / "Board" / "hw_addr.pi3"
FIXTURE = ROOT / "RaspberryPi3" / "Tests" / "pi3_memory_guard_gate.pi3"

MAP_MARKER = "; @@PRODUCTION_MAP_CONSTANTS@@"
ATTR_MARKER = "; @@PRODUCTION_MMU_ATTR_FOR@@"
DECODE_MARKER = "; @@PRODUCTION_HW_MEM_FROM_REVISION@@"
HIT_MARKER = "; @@PRODUCTION_PI3_ADDR_HIT@@"
TOP_MARKER = "; @@PRODUCTION_PI3_ADDR_ARM_TOP@@"
CHECK_MARKER = "; @@PRODUCTION_HW_ADDR_CHECK@@"

ASSERTIONS = 57

MAP_CONSTANTS = (
    "#MMU3_PERIPH_BASE",
    "#MMU3_PERIPH_TOP",
    "#MMU3_LOCAL_BASE",
    "#MMU3_LOCAL_TOP",
    "#MMU3_DRAM_ATTR",
    "#MMU3_ATTR_DEVICE",
    "#MMU3_DESC_FAULT",
)

# THE FIXTURE IS NOT A SLOT and does not use the slot contract's
# placement. It is entered with --entry-returns and run in the emitted-code
# interpreter, whose memory model is the harness's - so it links where the
# harness expects, exactly as the other board's emitted gates do. Using the
# real $1F00000 stack here puts the frame outside the window the
# interpreter models and it refuses, correctly.
LOAD = emitted.LOAD
STACK = emitted.STACK


def extract_procedure(source: str, header: str, label: str) -> str:
    if source.count(header) != 1:
        raise SystemExit(
            f"pi3 memory guard gate: {label} start count {source.count(header)}"
        )
    start = source.index(header)
    end = source.find("\nEndProcedure", start)
    if end < 0:
        raise SystemExit(f"pi3 memory guard gate: {label} has no end")
    return source[start : end + len("\nEndProcedure")] + "\n"


def extract_constant(source: str, name: str) -> str:
    """The production LINE defining one constant, reproduced exactly.

    Copying the line and not the value is deliberate: the gate then carries
    no second opinion about the number, and a constant that moves shows up
    here as a different fixture rather than as a silent agreement.
    """
    pattern = re.compile(r"^%s\s*=.*$" % re.escape(name), re.MULTILINE)
    found = pattern.findall(source)
    if len(found) != 1:
        raise SystemExit(
            f"pi3 memory guard gate: {name} definition count {len(found)}"
        )
    return found[0].split(";")[0].rstrip() + "\n"


def production() -> dict[str, str]:
    mmu = MMU.read_text(encoding="utf-8")
    mem = HW_MEM.read_text(encoding="utf-8")
    addr = HW_ADDR.read_text(encoding="utf-8")

    decode = extract_procedure(
        mem, "Procedure.i HwMemFromRevision(rev.i)", "HwMemFromRevision"
    )
    if "268435456" not in decode:
        raise SystemExit(
            "pi3 memory guard gate: the decode no longer multiplies 256 MB "
            "written out - a constant in this compiler takes no arithmetic in "
            "its initialiser, which is why it is a literal"
        )

    check = extract_procedure(
        addr, "Procedure.i HwAddrCheck(lo.i, hi.i, forWrite.i)", "HwAddrCheck"
    )
    if check.count("ProcedureReturn #HW_ADDR_ABSENT") != 1:
        raise SystemExit(
            "pi3 memory guard gate: HwAddrCheck does not have exactly one "
            "top-of-memory refusal"
        )
    if check.count("ProcedureReturn #HW_ADDR_UNCLOCKED") != 2:
        raise SystemExit(
            "pi3 memory guard gate: HwAddrCheck does not have exactly two "
            "unmapped refusals - above the translation regime, and above the "
            "processor-local window. There is no third: the aperture and that "
            "window are adjacent on this part, and a refusal for the gap "
            "between them is dead code"
        )

    attr = extract_procedure(mmu, "Procedure.i MmuAttrFor(pa.i)", "MmuAttrFor")
    for name in MAP_CONSTANTS:
        if name not in attr and name not in ("#MMU3_ATTR_DEVICE",):
            continue
    return {
        "map": "".join(extract_constant(mmu, n) for n in MAP_CONSTANTS),
        "attr": attr,
        "decode": decode,
        "hit": extract_procedure(
            addr, "Procedure.i pi3AddrHit(lo.i, hi.i, blo.i, bhi.i)", "pi3AddrHit"
        ),
        "top": extract_procedure(
            addr, "Procedure.i pi3AddrArmTop()", "pi3AddrArmTop"
        ),
        "check": check,
    }


def fixture(parts: dict[str, str]) -> str:
    template = FIXTURE.read_text(encoding="utf-8")
    markers = (
        (MAP_MARKER, "map"),
        (ATTR_MARKER, "attr"),
        (DECODE_MARKER, "decode"),
        (HIT_MARKER, "hit"),
        (TOP_MARKER, "top"),
        (CHECK_MARKER, "check"),
    )
    for marker, _ in markers:
        if template.count(marker) != 1:
            raise SystemExit(
                f"pi3 memory guard gate: fixture marker {marker} count "
                f"{template.count(marker)}"
            )
    for marker, key in markers:
        template = template.replace(marker, parts[key])
    return template


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(
            f"pi3 memory guard gate: {label} site count {text.count(old)}"
        )
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
    if name == "old-style-accepted":
        guard = ("  If (rev & $00800000) = 0\n"
                 "    ProcedureReturn #HW_MEM_UNKNOWN\n"
                 "  EndIf\n")
        out["decode"] = replace_once(out["decode"], guard, "", name)
        return out
    if name == "attr-device":
        out["attr"] = replace_once(
            out["attr"],
            "    ProcedureReturn #MMU3_DRAM_ATTR",
            "    ProcedureReturn #MMU3_ATTR_DEVICE",
            name,
        )
        return out
    if name == "local-top-loose":
        out["check"] = replace_once(
            out["check"],
            "pi3AddrHit(lo, hi, #MMU3_LOCAL_TOP + 1, $FFFFFFFF)",
            "pi3AddrHit(lo, hi, #MMU3_LOCAL_BASE + $200000, $FFFFFFFF)",
            name,
        )
        return out
    if name == "absent-gone":
        start = out["check"].index("  armTop = pi3AddrArmTop()")
        end = out["check"].index("  ProcedureReturn #HW_ADDR_SAFE")
        out["check"] = out["check"][:start] + out["check"][end:]
        return out
    if name == "armtop-ignores-fw":
        out["top"] = replace_once(
            out["top"],
            "  If pi3_ram_end > 0 And pi3_ram_end < #MMU3_PERIPH_BASE\n"
            "    ProcedureReturn pi3_ram_end\n"
            "  EndIf\n",
            "",
            name,
        )
        return out
    raise SystemExit(f"pi3 memory guard gate: unknown mutation {name}")


def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir() and not (work / "Boards").exists():
        shutil.copytree(boards, work / "Boards")
    intrinsics = ROOT / "RaspberryPi3" / "Intrinsics"
    target = work / "RaspberryPi3" / "Intrinsics"
    if intrinsics.is_dir() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(intrinsics, target)
    source = work / f"{stem}.pi3"
    source.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    command = [
        str(staged), "--compile", str(source),
        "-t", "pi3",
        "--load-addr", hex(LOAD),
        "--stack-addr", hex(STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    run = subprocess.run(
        command, cwd=ROOT,
        env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(
            f"pi3 memory guard gate: {stem} compile failed\n{run.stdout}"
        )
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit(
            f"pi3 memory guard gate: {stem} compiler omitted image or symbols"
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
        "".join(parts[k] for k in ("map", "attr", "decode", "hit", "top",
                                   "check")).encode("utf-8")
    ).hexdigest()

    mutations = (
        ("wrong-shift", 2),
        ("wrong-base", 1),
        ("old-style-accepted", 12),
        # Caught at 20, the very first map assertion: DRAM described as
        # Device is the mistake that makes every unaligned access a fault.
        ("attr-device", 20),
        # Caught at 49, the address one past the 4 KB window - the whole
        # of the tighter-than-the-tables property in one assertion.
        ("local-top-loose", 49),
        ("absent-gone", 42),
        ("armtop-ignores-fw", 42),
    )

    with tempfile.TemporaryDirectory(prefix="anvil-pi3-guard-") as temporary:
        work = Path(temporary)
        image = build(compiler, work, fixture(parts), "pi3_memory_guard_gate")
        result, steps = emitted.execute(a64, image)
        if result:
            print(
                f"pi3_memory_guard_check: FAIL assertion {result} after "
                f"{steps:,} A64 instructions"
            )
            return 1

        killed = []
        for name, expected in mutations:
            mutant = fixture(mutate(parts, name))
            mutant_image = build(
                compiler, work, mutant, f"pi3_memory_guard_mutant_{name}"
            )
            mutant_result, mutant_steps = emitted.execute(a64, mutant_image)
            if mutant_result != expected:
                print(
                    f"pi3_memory_guard_check: FAIL {name} mutation returned "
                    f"{mutant_result}; expected assertion {expected}"
                )
                return 1
            killed.append((name, expected, mutant_steps))

    print(
        f"pi3_memory_guard_check: PASS - {ASSERTIONS} assertions, "
        f"{steps:,} A64 instructions"
    )
    print("  every MEMSIZE code decoded, the three revision codes a Pi 3 ships")
    print("  with, four old-style words refused a size; the map walked at every")
    print("  boundary and either side of it; the guard checked on a board whose")
    print("  firmware has spoken and on one it has not; a straddling range")
    print("  refused whole; and THE GUARD AND THE PAGE TABLES COMPARED, with the")
    print("  two deliberate disagreements asserted as disagreements")
    for name, expected, mutant_steps in killed:
        print(
            f"  {name} mutation rejected at assertion {expected} "
            f"after {mutant_steps:,} instructions"
        )
    print(f"  production map+attr+decode+guard sha256 {digest}")
    print("No hardware was contacted: the firmware answers are modelled seams,")
    print("so this is a source and emitted-code proof only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
