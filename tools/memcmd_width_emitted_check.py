#!/usr/bin/env python3
"""Gate width-correct, single-snapshot Anvil memory reads (desk only)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build as anvil_build  # noqa: E402
import build_count  # noqa: E402

SOURCE = ROOT / "Anvil" / "Core" / "memcmd.pbi"
TARGETS = (
    ("pi4", ROOT / "RaspberryPi4" / "Board" / "board.pi4", []),
    ("unoq", ROOT / "ArduinoQ" / "Board" / "board.unoq", ["--entry-returns"]),
)


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, value: bool, message: str) -> None:
        self.count += 1
        if not value:
            raise AssertionError(message)


def proc(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)\s*$"
        rf"(.*?)^EndProcedure\s*$", text)
    if not match:
        raise AssertionError(f"missing procedure {name}")
    return match.group(0)


def source_checks(c: Checks, text: str) -> None:
    read = proc(text, "ReadWidth")
    dump = proc(text, "DumpMem")
    cmd = proc(text, "CmdMem")
    fill = proc(text, "CmdFill")
    modify = proc(text, "ModMem")

    c.yes(read.count("PeekA(a)") == 1, "byte read is not one PeekA access")
    c.yes(read.count("PeekU(a)") == 1, "halfword read is not one PeekU access")
    c.yes(read.count("PeekN(a)") == 1, "word read is not one PeekN access")
    c.yes("While " not in read and "PeekA(a +" not in read,
          "ReadWidth still assembles wide values from byte accesses")
    c.yes("ProcedureReturn 0" in read,
          "unsupported width does not refuse without an access")

    c.yes("Dim snap.i[16]" in dump, "dump lacks a per-row byte snapshot")
    active_dump_reads = sum("ReadWidth(" in line for line in dump.splitlines()
                            if not line.lstrip().startswith(";"))
    c.yes(dump.count("ReadWidth(a + i + j, width)") == 1 and
          active_dump_reads == 1,
          "dump must have one selected-width read site")
    c.yes("snap[j + k] =" in dump and "b = snap[j]" in dump,
          "hex/ASCII do not share the captured row")
    c.yes(not re.search(r"\bPeek[ABUWNI]?\(", dump),
          "dump formatting rereads the target directly")
    c.yes(dump.find("ReadWidth(a + i + j, width)") <
          dump.find("PutHexN(a + i, wide)"),
          "row output begins before the target snapshot is complete")
    c.yes("(a & (width - 1)) <> 0 Or (n & (width - 1)) <> 0" in dump,
          "DumpMem lacks defensive alignment/whole-unit refusal")

    length_guard = cmd.find("If (n & (width - 1)) <> 0")
    clamp = cmd.find("If n > 4096")
    add_base = cmd.find("a = AddBase(a)")
    align_guard = cmd.find("If (a & (width - 1)) <> 0")
    allowed = cmd.find("If AddrAllowed(")
    access = cmd.find("got = DumpMem(")
    c.yes(0 <= length_guard < clamp,
          "partial-wide length is not refused before clamp/access")
    c.yes(0 <= add_base < align_guard < allowed < access,
          "wide address is not refused before target access")
    c.yes(cmd.count("Nothing was read.") >= 2,
          "alignment/length refusals do not state that no read occurred")
    c.yes("width = MemSize(WtDefSize(#WT_MD))" in cmd and
          "ProcedureReturn 1              ; group one byte" in text,
          "bare memory dump is no longer byte-wide")

    c.yes(fill.find("If size = 4 And (a & 3) <> 0") <
          fill.find("ReadWidth(a, size)"),
          "fill readback can reach a misaligned wide address")
    c.yes(modify.find("If size = 4 And (a & 3) <> 0") <
          modify.find("cur = ReadWidth(a, size)"),
          "interactive read can reach a misaligned wide address")
    active_readwidth = sum("ReadWidth(" in line for line in text.splitlines()
                           if not line.lstrip().startswith(";"))
    c.yes(active_readwidth == 6,
          "new ReadWidth caller added without an alignment audit")


def mutation_checks(c: Checks, text: str) -> None:
    mutations = (
        ("ReadWidth", "halfword downgraded to bytes", "PeekU(a)", "PeekA(a)"),
        ("ReadWidth", "word downgraded to bytes", "PeekN(a)", "PeekA(a)"),
        ("DumpMem", "ASCII target reread", "b = snap[j]", "b = PeekA(a + i + j)"),
        ("CmdMem", "partial-unit guard", "If (n & (width - 1)) <> 0", "If 0"),
        ("CmdMem", "alignment guard", "If (a & (width - 1)) <> 0", "If 0"),
        ("DumpMem", "snapshot before output", "PutHexN(a + i, wide)",
         "PutHexN(a + i, wide)\n    v = ReadWidth(a, 1)"),
    )
    for owner, name, old, new in mutations:
        body = proc(text, owner)
        c.yes(old in body, f"mutation pattern disappeared: {name}")
        changed = text.replace(body, body.replace(old, new, 1), 1)
        try:
            source_checks(Checks(), changed)
        except AssertionError:
            c.yes(True, f"mutation killed: {name}")
        else:
            c.yes(False, f"mutation survived: {name}")


class SideEffectMemory:
    def __init__(self) -> None:
        self.reads: list[tuple[int, int]] = []

    def read(self, address: int, width: int) -> int:
        self.reads.append((address, width))
        generation = len(self.reads) & 0xFF
        return sum(((address + byte + generation) & 0xFF) << (8 * byte)
                   for byte in range(width))


def capture_row(memory: SideEffectMemory, address: int,
                count: int, width: int) -> list[int]:
    snap = [0] * count
    for item in range(0, count, width):
        value = memory.read(address + item, width)
        for byte in range(width):
            snap[item + byte] = (value >> (8 * byte)) & 0xFF
    return snap


def model_checks(c: Checks) -> None:
    def valid(address: int, count: int, width: int) -> bool:
        return width in (1, 2, 4) and count > 0 and \
            (address & (width - 1)) == 0 and (count & (width - 1)) == 0

    for width, count in ((1, 7), (1, 16), (2, 16), (4, 16), (4, 12)):
        memory = SideEffectMemory()
        c.yes(valid(0x1000, count, width),
              f"valid width/count refused: {width}/{count}")
        snap = capture_row(memory, 0x1000, count, width)
        reads_before_render = list(memory.reads)
        hex_view = [snap[i:i + width] for i in range(0, count, width)]
        ascii_view = [byte if 32 <= byte <= 126 else 46 for byte in snap]
        c.yes(memory.reads == reads_before_render and
              len(memory.reads) == count // width,
              f"formatting reread width {width} row")
        c.yes(all(actual_width == width for _, actual_width in memory.reads),
              f"modeled width {width} used a different bus access")
        c.yes(sum(len(item) for item in hex_view) == len(ascii_view) == count,
              "hex and ASCII did not consume the same snapshot")

    for address, count, width in (
            (0x1001, 2, 2), (0x1002, 4, 4),
            (0x1000, 3, 2), (0x1000, 6, 4), (0x1000, 4, 3)):
        memory = SideEffectMemory()
        c.yes(not valid(address, count, width),
              f"invalid access accepted: {address:#x}/{count}/{width}")
        c.yes(memory.reads == [], "refusal performed a target access")


def asm_proc(asm: str, name: str, next_name: str) -> str:
    start = asm.find(f"\n{name}:\n")
    end = asm.find(f"\n{next_name}:\n", start + 1)
    if start < 0 or end < 0:
        raise AssertionError(f"missing emitted boundary {name}..{next_name}")
    return asm[start + 1:end]


def emitted_checks(c: Checks, asm: str, target: str) -> None:
    read = asm_proc(asm, "ReadWidth", "CmdFill")
    dump = asm_proc(asm, "DumpMem", "CmdMem")
    c.yes(len(re.findall(r"(?m)^\s*ldrb\s+w\d+,\s*\[x\d+\]", read)) == 1,
          f"{target}: ReadWidth does not emit one byte load")
    c.yes(len(re.findall(r"(?m)^\s*ldrh\s+w\d+,\s*\[x\d+\]", read)) == 1,
          f"{target}: ReadWidth does not emit one halfword load")
    c.yes(len(re.findall(r"(?m)^\s*ldr\s+w\d+,\s*\[x\d+\]", read)) == 1,
          f"{target}: ReadWidth does not emit one word load")
    c.yes(read.count("ldrb ") == 1 and read.count("ldrh ") == 1,
          f"{target}: wide paths still contain hidden byte loads")
    c.yes(dump.lower().count("bl readwidth") == 1,
          f"{target}: DumpMem has more than one target-read call site")
    c.yes("ldrb " not in dump and "ldrh " not in dump,
          f"{target}: DumpMem rereads target bytes outside ReadWidth")


def compile_target(pmfc: str, work: Path, target: str,
                   source: Path, extra: list[str]) -> str:
    compiler_dir = work / f"compiler-{target}"
    compiler_dir.mkdir(parents=True)
    compiler = anvil_build.staged_compiler(pmfc, compiler_dir)
    image = work / f"memcmd-{target}.img"
    env = os.environ.copy()
    env["PMF_ROOT"] = str(ROOT)
    command = [compiler, source.relative_to(ROOT).as_posix(), "-t", target,
               *extra, "-S", "-s", "-o", str(image)]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode or not Path(str(image) + ".asm").is_file():
        raise AssertionError(f"{target} emitted build failed:\n{result.stdout}")
    # THIS GATE BUILDS THE WHOLE MONITOR, TWICE, AND BOTH BUILDS COUNT. Ruled
    # 2026-09-11: "gate builds do count". The fixture here is not a lifted
    # procedure - it is board.pi4 and board.unoq compiled end to end, so each
    # run of this gate is two builds of Anvil and the board files say so.
    counted = build_count.record_build(source, target, image,
                                       by="tools/memcmd_width_emitted_check.py",
                                       compiler=compiler)
    print(f"  build count: {counted.message}")
    return Path(str(image) + ".asm").read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmfc", default=os.environ.get("PMFC"))
    args = parser.parse_args()
    checks = Checks()
    try:
        text = SOURCE.read_text(encoding="utf-8")
        source_checks(checks, text)
        mutation_checks(checks, text)
        model_checks(checks)
        compiler = anvil_build.find_compiler(args.pmfc)
        with tempfile.TemporaryDirectory(prefix="anvil-memcmd-width-") as name:
            for target, source, extra in TARGETS:
                emitted_checks(
                    checks,
                    compile_target(compiler, Path(name), target, source, extra),
                    target)
    except (AssertionError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"memcmd_width_emitted_check: FAIL after {checks.count} checks: {error}")
        return 1
    print(f"memcmd_width_emitted_check: PASS - {checks.count} source/model/mutation/emitted checks")
    print("No board was contacted; MMIO side effects and bus-width behavior remain silicon checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
