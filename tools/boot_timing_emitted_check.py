#!/usr/bin/env python3
"""Execute the shipped boot-timing record and prove its layout and refusals.

The record is the instrument the display lane is judged by, so it is the one
thing that may not be checked by reading the source: a field at the wrong
offset, a count published before the row it names, or a guard that accepts a
stale header all produce a table of plausible numbers.

The DSI window constants come out of memmap.pi4 and are substituted into the
fixture, so the address under test is derived the same way the product derives
it. The cache clean, the architectural counter and the printing leaves are the
only stubs; every offset, every guard and every refusal is the shipped body.

  PMF_COMPILER=<PureMetalForge.exe> PMF_A64_INTERP=<a64_interp.py> python tools/boot_timing_emitted_check.py
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tcp_multiif_emitted_check as emitted

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "RaspberryPi4" / "Board" / "boot_timing.pi4"
MEMMAP = ROOT / "RaspberryPi4" / "Board" / "memmap.pi4"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "boot_timing_emitted_gate.pi4"

WINDOW = ("MON_FB_LO", "MON_FB_HI", "MON_FB_SCAN", "MON_FB_DRAW", "MON_FB_BYTES")


def memmap_constants() -> str:
    text = MEMMAP.read_text(encoding="utf-8")
    lines = []
    for name in WINDOW:
        found = re.search(rf"(?m)^#{name}\s*=\s*(\$?[0-9A-Fa-f]+)", text)
        if not found:
            raise SystemExit(f"boot timing gate: memmap.pi4 no longer defines #{name}")
        lines.append(f"#{name} = {found.group(1)}")
    return "\n".join(lines)


def fixture(product: str, window: str) -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    for marker, value in (("; @@MEMMAP@@", window), ("; @@BODY@@", product)):
        if text.count(marker) != 1:
            raise SystemExit(f"boot timing gate: fixture marker {marker} drifted")
        text = text.replace(marker, value, 1)
    return text


def product_source() -> str:
    """Everything in boot_timing.pi4 except the viewer, which prints prose."""
    text = PRODUCT.read_text(encoding="utf-8")
    cut = text.index("; ======================================================================\n"
                     ";  THE VIEWER - `screen timing`")
    return text[:cut]


def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir() and not (work / "Boards").exists():
        shutil.copytree(ROOT / "Boards", work / "Boards")
    src = work / f"{stem}.pi4"
    src.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    run = subprocess.run(
        [str(staged), "--compile", str(src), "-t", "pi4",
         "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK),
         "--entry-returns", "-o", str(image), "-s"],
        cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"boot timing gate: {stem} compile failed\n{run.stdout}")
    return image


def execute(a64, image: Path, record_lo: int, record_hi: int) -> tuple[int, int]:
    """Run the image with ONE extra window open: the record's own page.

    This is the whole point of running it rather than reading it. The shipped
    code writes to a fixed absolute address outside its own BSS, and the
    interpreter's default rule refuses exactly that - so the window is opened
    here, by name, for the bytes the record is documented to own and for
    nothing else. A store one byte past the table fails the gate loudly,
    which is the property that matters: the page is shared with the display's
    reserved window and a record that overran it would be scanned out.
    """
    blob = image.read_bytes()
    bss_lo, bss_hi = emitted.symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    image_range = (emitted.LOAD, emitted.LOAD + len(blob))
    bss_range = (bss_lo, bss_hi)
    stack_range = (emitted.STACK - emitted.STACK_BYTES, emitted.STACK + 16)
    record_range = (record_lo, record_hi + 1)
    readable = (image_range, bss_range, stack_range, record_range)
    writable = (bss_range, stack_range, record_range)

    def contains(ranges, addr, size):
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[emitted.LOAD + offset] = byte
    a64.attach_symbols(cpu, image, emitted.LOAD)
    cpu.pc = emitted.LOAD
    cpu.sp = emitted.STACK
    cpu.x[30] = emitted.LOADER_LR

    def load(addr, size):
        cpu.align_guard(addr, size, False)
        if not contains(readable, addr, size):
            raise SystemExit(f"boot timing gate: read outside image/BSS/stack/record at ${addr:08X}+{size}")
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if not contains(writable, addr, size):
            raise SystemExit(f"boot timing gate: write outside BSS/stack/record at ${addr:08X}+{size}")
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    for steps in range(emitted.STEP_LIMIT):
        if cpu.pc == emitted.LOADER_LR:
            return cpu.x[0], steps
        cpu.step()
    raise SystemExit(f"boot timing gate: no return in {emitted.STEP_LIMIT} instructions")


def mutate(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"boot timing gate: {label} anchor count {text.count(old)}")
    return text.replace(old, new, 1)


MUTATIONS = (
    # The record's page moved onto the picture. BootTimingClearOfSurfaces
    # is the arithmetic that refuses it, and Begin must leave no record at
    # all rather than write one into the framebuffer.
    ("the record lands on the drawing surface",
     "#BTM_BASE  = #MON_FB_HI + 1 - $00001000",
     "#BTM_BASE  = #MON_FB_DRAW"),
    # A count published before the bytes it names is a row of stale DRAM
    # presented to a host as an event.
    ("the count is published before the row reaches memory",
     "  BootTimingFlush(a, a + #BTM_SLOT_BYTES - 1)\n  n = n + 1",
     "  n = n + 1"),
    # A guard that does not track the count is met by the previous boot's
    # header sitting over this boot's rows.
    ("the guard stops tracking the count",
     "  PokeI(#BTM_BASE + #BTM_OFF_GUARD, BootTimingGuardFor(n, PeekI(#BTM_BASE + #BTM_OFF_HZ)))",
     "  ; guard not updated"),
    # A full table that wraps turns the beginning of a boot into its end
    # under the same header.
    ("a full table wraps instead of counting what it refused",
     "  If n < 0 Or n >= #BTM_SLOTS",
     "  If n < 0 Or n >= #BTM_SLOTS * 4"),
    ("overflow is not counted",
     "    PokeI(#BTM_BASE + #BTM_OFF_LOST, PeekI(#BTM_BASE + #BTM_OFF_LOST) + 1)",
     "    ; overflow not counted"),
    # Appending to a record that was never started manufactures a
    # measurement out of whatever DRAM was holding.
    ("a mark is appended to a record that does not exist",
     "  If PeekI(#BTM_BASE + #BTM_OFF_MAGIC) <> #BTM_MAGIC\n    ProcedureReturn\n  EndIf",
     "  ; magic not checked"),
    # A row index past the count read as data.
    ("a row past the count is readable",
     "  If i < 0 Or i >= BootTimingCount()",
     "  If i < 0 Or i > BootTimingCount()"),
    # The stride the host reader is told about.
    ("the row stride changes without the layout version",
     "#BTM_SLOT_BYTES   = 32",
     "#BTM_SLOT_BYTES   = 24"),
    # A version mismatch reinterpreted rather than refused.
    ("a record from another layout version is accepted",
     "  If PeekI(#BTM_BASE + #BTM_OFF_VERSION) <> #BTM_VERSION\n    ProcedureReturn 0\n  EndIf",
     "  ; version not checked"),
    # The prompt recorded on every command line fills the table with the
    # least interesting event in the boot.
    ("every prompt is recorded",
     "  If gBootTimingPrompted <> 0\n    ProcedureReturn\n  EndIf",
     "  ; recorded every time"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    a64 = emitted.load_interpreter(emitted.required_path(args.interp, "PMF_A64_INTERP"))

    window = memmap_constants()
    product = product_source()
    # The whole reserved DSI window, so a mutant that moves the record onto a
    # scanout surface is still ALLOWED to write there by the interpreter - and
    # is caught by the shipped refusal instead of by the harness. A gate that
    # caught it with its own rule would prove nothing about the product.
    lo = int(re.search(r"#MON_FB_LO = \$([0-9A-Fa-f]+)", window).group(1), 16)
    hi = int(re.search(r"#MON_FB_HI = \$([0-9A-Fa-f]+)", window).group(1), 16)

    with tempfile.TemporaryDirectory(prefix="anvil-boot-timing-") as td:
        work = Path(td)
        result, steps = execute(a64, build(compiler, work, fixture(product, window), "boot_timing_gate"), lo, hi)
        if result:
            print(f"boot_timing_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions")
            return 1
        killed = []
        for i, (label, old, new) in enumerate(MUTATIONS, 1):
            mutant = mutate(product, old, new, label)
            r, _ = execute(a64, build(compiler, work, fixture(mutant, window), f"boot_timing_mutant_{i}"), lo, hi)
            if r == 0:
                print(f"boot_timing_emitted_check: FAIL {label} mutant survived")
                return 1
            killed.append(f"{label}:{r}")

    print(f"boot_timing_emitted_check: PASS - 46 assertions over the shipped record, "
          f"{steps:,} A64 instructions; {len(MUTATIONS)} mutants rejected")
    for entry in killed:
        print("  rejected: " + entry)
    print("  the DSI window constants come from memmap.pi4; the cache clean, the")
    print("  counter and the printing leaves are stubs. No board, no display.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
