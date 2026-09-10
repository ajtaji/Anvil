#!/usr/bin/env python3
"""Compare the real DMA cache walk with its recorded pre-fix body.

Compile/execution only: SYS instructions are observed, not physically executed.
No cache/coherency, DMA hardware, display timing or board claim is made.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

import tcp_multiif_emitted_check as emitted

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Lib/dma.pi4"
LOAD, BSS, STACK, STACK_BYTES = 0x400000, 0x800000, 0x3000000, 0x10000
RETURN = 0xDEAD0000
MASK = (1 << 64) - 1
LEGACY = """Procedure DmaCacheLines(addr.i, len.i)
  Protected a.i
  Protected e.i
  If len <= 0
    ProcedureReturn
  EndIf
  a = (addr / #DMA_CACHE_LINE) * #DMA_CACHE_LINE
  e = addr + len
  While a < e
    dma_flushaddr = a
    DmaCacheLine()
    a = a + #DMA_CACHE_LINE
  Wend
EndProcedure"""


def proc(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^Procedure(?:\.i)? {name}\([^\n]*\)\n.*?^EndProcedure", source)
    if not match:
        raise AssertionError("missing real procedure " + name)
    return match.group(0)


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError("mutation anchor is not unique: " + old)
    return text.replace(old, new, 1)


def fixture(source: str) -> str:
    constants = re.findall(r"(?m)^#DMA_CACHE_LINE\s*=\s*64\s*$", source)
    if len(constants) != 1:
        raise AssertionError("real BCM2711 cache-line contract is not exactly 64 bytes")
    parts = [proc(source, name) for name in
             ("DmaCacheLine", "DmaCacheLines", "DmaCacheRange", "DmaCacheRect")]
    return ("EnableExplicit\n" + constants[0] + "\nGlobal dma_flushaddr.i\n" +
            "\n\n".join(parts) + """
Procedure.i Main()
  DmaCacheRange($100000, 64)
  DmaCacheRect($100000, 128, 64, 2)
  ProcedureReturn 0
EndProcedure
""")


def build(pmfc: Path, work: Path, name: str, text: str):
    source, image = work / (name + ".pi4"), work / (name + ".img")
    source.write_text(text, encoding="utf-8")
    result = subprocess.run([
        str(pmfc), str(source), "-t", "pi4", "-s", "--entry-returns",
        "--load-addr", hex(LOAD), "--bss-addr", hex(BSS),
        "--stack-addr", hex(STACK), "-o", str(image),
    ], cwd=ROOT, capture_output=True, text=True, timeout=120)
    if result.returncode or not image.is_file():
        raise AssertionError("fixture compile failed: " + name + "\n" + result.stdout + result.stderr)
    symbols = {}
    for line in Path(str(image) + ".sym").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            symbols[key.strip().lower()] = int(value.strip(), 0)
    # Code names come from explicit image-relative debug records, never from
    # guessing which symbol values happen to be larger than the load base.
    entries = {}
    for line in Path(str(image) + ".dbg").read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("|")
        if len(fields) >= 4 and fields[0] == "1" and fields[1].isdigit():
            entries[fields[2].lower()] = LOAD + int(fields[1])
    for name in ("dmacachelines", "dmacacherange", "dmacacherect"):
        if name not in entries:
            raise AssertionError("missing real entry " + name)
    blob = image.read_bytes()
    lo, hi = symbols["__bss_start__"], symbols["__bss_end__"]
    if not (lo == BSS < hi <= BSS + 0x10000 and LOAD + len(blob) <= lo):
        raise AssertionError("inconsistent exact image/BSS extents")
    return blob, (lo, hi), entries


class GuardError(RuntimeError):
    pass


class TraceMismatch(AssertionError):
    pass


def execute(a64, product, entry: str, args: tuple[int, ...], guard_teeth=False, expected_trace=None):
    blob, bss, entries = product
    code = (LOAD, LOAD + len(blob))
    stack = (STACK - STACK_BYTES, STACK)
    events = []
    calls = 0

    def contains(spans, addr, size):
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in spans)

    class Observed(a64.A64):
        def fetch(self, addr):
            if addr & 3 or not contains((code,), addr, 4):
                raise GuardError("instruction fetch outside exact image")
            return super().fetch(addr)

        def load(self, addr, size):
            self.align_guard(addr, size, False)
            if not contains((code, bss, stack), addr, size):
                raise GuardError("data read outside image/BSS/own stack")
            return super().load(addr, size)

        def store(self, addr, value, size):
            self.align_guard(addr, size, True)
            if not contains((bss, stack), addr, size):
                raise GuardError("data write outside BSS/own stack")
            return super().store(addr, value, size)

        def step(self):
            nonlocal calls
            ins = self.fetch(self.pc)
            if ins & 0xFC000000 == 0x94000000:
                calls += 1
            if ins & 0xFFF80000 == 0xD5080000:
                key = (((ins >> 16) & 7) << 12 | ((ins >> 12) & 15) << 8 |
                       ((ins >> 8) & 15) << 4 | (ins >> 5) & 7)
                if key not in (0x37E1, 0x37A1):
                    raise AssertionError("unexpected maintenance operation")
                events.append(("civac" if key == 0x37E1 else "cvac", self.x[ins & 31]))
            if ins == 0xD5033F9F:
                events.append(("dsb sy", None))
            if ins == 0xD5033FDF:
                events.append(("isb", None))
            if expected_trace is not None and events != expected_trace[:len(events)]:
                raise TraceMismatch("first mismatched maintenance/barrier event")
            super().step()

    cpu = Observed()
    cpu.memory = {LOAD + i: value for i, value in enumerate(blob)}
    cpu.sp, cpu.pc, cpu.x[30] = STACK, entries[entry], RETURN
    saved = {i: 0x1111000000000000 + i for i in range(19, 30)}
    for reg, value in saved.items():
        cpu.x[reg] = value
    for reg, value in enumerate(args):
        cpu.x[reg] = value & MASK
    canary = 0xA55A0123456789AB
    cpu.store(stack[0], canary, 8)
    if guard_teeth:
        for action in (lambda: cpu.fetch(bss[0]), lambda: cpu.fetch(stack[0]),
                       lambda: cpu.store(LOAD, 0, 4), lambda: cpu.load(bss[1], 8),
                       lambda: cpu.load(0xFC000000, 4),
                       lambda: cpu.store(stack[0] - 8, 0, 8)):
            try:
                action()
            except GuardError:
                pass
            else:
                raise AssertionError("memory/fetch guard did not bite")
    for steps in range(1_000_000):
        if cpu.pc == RETURN:
            break
        cpu.step()
    else:
        raise AssertionError("cache walk failed to return")
    if cpu.sp != STACK or any(cpu.x[i] != value for i, value in saved.items()):
        raise AssertionError("callee-preserved registers or SP changed")
    if cpu.load(stack[0], 8) != canary:
        raise AssertionError("stack-low canary changed")
    return events, steps, calls


def lines(addr, length):
    return [("civac", at) for at in range(addr & -64, addr + length, 64)] if length > 0 else []


def cases():
    result = []
    for start, length in ((0, 1), (63, 1), (63, 2), (64, 64), (65, 64),
                          (0x8A00000, 6400), (0x1FFFFFFF1, 129),
                          (0x100000, 0), (0x100000, -1)):
        for entry in ("dmacachelines", "dmacacherange"):
            expected = lines(start, length)
            if entry == "dmacacherange":
                expected += [("dsb sy", None), ("isb", None)]
            result.append((entry, (start, length), expected))
    for addr, pitch, width, rows in ((0x100000, 128, 128, 3),
                                    (0x100003, 256, 65, 3),
                                    (0x1FFFFFFF1, 256, 65, 3),
                                    (0x100000, 32, 65, 3),
                                    (0x100000, 128, 0, 3),
                                    (0x100000, 128, 64, 0),
                                    (0x100000, 128, 64, -1)):
        expected = []
        if width > 0 and rows > 0:
            if pitch == width:
                expected = lines(addr, width * rows)
            else:
                for row in range(rows):
                    expected += lines(addr + row * pitch, width)
            expected += [("dsb sy", None), ("isb", None)]
        result.append(("dmacacherect", (addr, pitch, width, rows), expected))
    return result


def main():
    if not __debug__:
        raise SystemExit("refusing -O: guard checks require assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    args = parser.parse_args()
    pmfc = emitted.required_path(args.pmfc, "PMFC")
    a64 = emitted.load_interpreter(ROOT / "tools/a64/a64_interp.py")
    source = SOURCE.read_text(encoding="utf-8")
    fixed = proc(source, "DmaCacheLines")
    candidate = fixture(source)
    legacy = fixture(replace_once(source, fixed, LEGACY))
    matrix = cases()
    with tempfile.TemporaryDirectory(prefix="anvil-dma-cache-walk-") as name:
        work = Path(name)
        products = [build(pmfc, work, "legacy", legacy), build(pmfc, work, "candidate", candidate)]
        totals = []
        for product in products:
            total = 0
            for i, (entry, arguments, expected) in enumerate(matrix):
                actual, count, calls = execute(a64, product, entry, arguments, i == 0)
                if actual != expected:
                    raise AssertionError(f"maintenance/barrier mismatch: {entry}{arguments}")
                total += count
                if product is products[1] and entry == "dmacachelines" and calls:
                    raise AssertionError("per-line walk still calls another procedure")
            totals.append(total)
        perf = ("dmacachelines", (0x8A00000, 6400))
        old_steps = execute(a64, products[0], *perf)[1]
        new_steps = execute(a64, products[1], *perf)[1]
        if new_steps * 4 >= old_steps:
            raise AssertionError("100-line loop has not removed at least 75% of decoded instructions")
        mutations = (
            ("wrong operation", "dc   civac, x9", "dc   cvac, x9"),
            ("wrong stride", "add  x9, x9, #64", "add  x9, x9, #128"),
            ("truncated address", "ldr  x9, [x9]\n    adrp x10", "ldr  w9, [x9]\n    adrp x10"),
            ("one past end", "b.lt dmaCacheWalkNext", "b.le dmaCacheWalkNext"),
            ("missing range barrier", "a64_barrier()                  ; dsb sy + isb, from the intrinsics", ""),
        )
        for label, old, new in mutations:
            # Narrow loads target the loop's unique spelling, not DmaCacheLine.
            mutated = replace_once(candidate, old, new)
            product = build(pmfc, work, "mutant_" + label.replace(" ", "_"), mutated)
            caught = False
            for entry, arguments, expected in matrix:
                try:
                    actual, _, _ = execute(a64, product, entry, arguments, expected_trace=expected)
                except TraceMismatch:
                    caught = True
                    break
                if actual != expected:
                    caught = True
                    break
            if not caught:
                raise AssertionError("mutation survived: " + label)
            print("  rejected mutation: " + label)
        print(f"PASS: {len(matrix)} exact address/barrier cases on both bodies; six guard teeth each; five compiled mutations")
        print(f"decoded instructions all cases: {totals[0]} -> {totals[1]}; 100-line walk: {old_steps} -> {new_steps}")
        print("candidate image sha256=" + hashlib.sha256(products[1][0]).hexdigest())
        print("No physical cache, DMA, presentation or timing claim; board untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
