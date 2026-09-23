#!/usr/bin/env python3
"""Compile and execute the payload run record gate, then read what `last run` said.

WHAT IS UNDER TEST. RaspberryPi4/Board/runrecord.pi4 - the record the monitor
writes at a payload's entry, its return and a processor exception, kept where
the deadman's reset cannot erase it, and the `last run` command a host asks
when a return line did not reach it. The REAL file is compiled for the Pi 4
and executed under the A64 interpreter by RaspberryPi4/Tests/
runrecord_emitted_gate.pi4, which walks seven scenarios: nothing recorded,
returned, reset under a running payload with the deadman armed, an exception
then a reset, a reset with no deadman, an exception reported against a
previous boot's entry, and a torn record.

The gate asserts the record's words itself. This check reads back every
character `last run` printed, splits it per scenario, and holds each to its
machine line and to the sentence that names the outcome - because the host
tool reads the one and a person reads the other, and both are the product.

THREE MUTANTS, each a one-line reversal of a decision in the real file, each
required to fail: a reset that is not noticed, an exception that can rewrite
a payload that already returned, and a return that can be reported twice.

    python tools/runrecord_emitted_check.py [--compiler PureMetalForge.exe] [--interp a64_interp.py]

Requires PMF_COMPILER and PMF_A64_INTERP, or the two flags.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import tcp_multiif_emitted_check as emitted
from pmf_compiler import resolve_compiler

GATE = emitted.ROOT / "RaspberryPi4" / "Tests" / "runrecord_emitted_gate.pi4"
RECORD = emitted.ROOT / "RaspberryPi4" / "Board" / "runrecord.pi4"

LASTRUN_RE = re.compile(
    r"^LASTRUN ([0-9A-F]{8}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) "
    r"([0-9A-F]{16}) ([0-9A-F]{16}) ([0-9A-F]{16}) ([0-9A-F]{16}) "
    r"([0-9A-F]{16}) ([0-9A-F]{16})\r?$", re.M)

MUTATIONS = {
    "reset-unnoticed": (
        "    If PeekI(#RUNREC_BASE + #RUNREC_OFF_BOOTS) <> MonPhaseBoots()\n      restarted = 1",
        "    If 0 <> 0\n      restarted = 1"),
    "exception-rewrites-return": (
        "Procedure RunRecordException(esr.i, pc.i, far.i)\n  If RunRecordState() <> #RUNREC_ENTERED",
        "Procedure RunRecordException(esr.i, pc.i, far.i)\n  If RunRecordState() = #RUNREC_NONE"),
    "return-twice": (
        "Procedure RunRecordReturn(x0.i)\n  If RunRecordState() <> #RUNREC_ENTERED",
        "Procedure RunRecordReturn(x0.i)\n  If RunRecordState() = #RUNREC_NONE"),
}


def build(compiler: Path, work: Path, mutation: str = "") -> Path:
    probe = GATE
    if mutation:
        fixed, broken = MUTATIONS[mutation]
        text = RECORD.read_text(encoding="utf-8")
        if text.count(fixed) != 1:
            raise SystemExit(f"runrecord_emitted_check: mutation {mutation} site drifted")
        mutated = work / "runrecord_mutated.pi4"
        mutated.write_text(text.replace(fixed, broken, 1), encoding="utf-8")
        source = GATE.read_text(encoding="utf-8")
        include = 'XIncludeFile "RaspberryPi4/Board/runrecord.pi4"'
        if source.count(include) != 1:
            raise SystemExit("runrecord_emitted_check: gate include drifted")
        probe = work / "runrecord_gate_mutated.pi4"
        probe.write_text(source.replace(include, f'XIncludeFile "{mutated.as_posix()}"'),
                         encoding="utf-8")
    emitted.PROBE = probe
    return emitted.build(compiler, work)


def run(a64, image: Path) -> tuple[int, str]:
    """Execute the image and return (Main's x0, everything it printed)."""
    captured: dict = {}
    original = a64.A64

    class Recording(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["cpu"] = self

    a64.A64 = Recording
    try:
        result, _steps = emitted.execute(a64, image)
    finally:
        a64.A64 = original
    cpu = captured["cpu"]
    symbols = {}
    for line in image.with_suffix(image.suffix + ".sym").read_text().splitlines():
        name, _, value = line.partition("=")
        if value.strip().isdigit():
            symbols[name.strip()] = int(value)
    base = emitted.LOAD
    out_at = base + symbols["global_gate_out"] if symbols["global_gate_out"] < base else symbols["global_gate_out"]
    len_at = base + symbols["global_gate_outlen"] if symbols["global_gate_outlen"] < base else symbols["global_gate_outlen"]
    length = sum(cpu.memory.get(len_at + i, 0) << (8 * i) for i in range(8))
    text = bytes(cpu.memory.get(out_at + i, 0) for i in range(length)).decode("ascii", "replace")
    return result, text


def scenarios(text: str) -> dict[int, str]:
    parts = re.split(r"(?m)^##(\d)\r?$", text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def verdicts(result: int, text: str) -> list[str]:
    """Every failure, as a sentence. An empty list is a pass."""
    bad: list[str] = []
    if result:
        return [f"the gate's own assertion {result} failed"]
    got = scenarios(text)
    if sorted(got) != list(range(7)):
        return [f"expected seven scenarios in the transcript, found {sorted(got)}"]

    def line(n: int):
        found = LASTRUN_RE.search(got[n])
        if not found:
            bad.append(f"scenario {n}: no well-formed LASTRUN line: {got[n][:120]!r}")
            return None
        return found.groups()

    def says(n: int, phrase: str) -> None:
        if phrase not in got[n]:
            bad.append(f"scenario {n}: the sentence does not say {phrase!r}")

    # (run, state, restarted, deadman, x0, addr, ms, esr, pc, far)
    expect = {
        0: ("00000000", "00", "00", "00", "0" * 16, "0" * 16, "F" * 16),
        1: ("00000001", "02", "00", "0F", "000000000000012C", "0000000000700000",
            f"{300000:016X}"),
        2: ("00000002", "01", "01", "0F", "0" * 16, "0000000000700000", "F" * 16),
        3: ("00000003", "03", "01", "0F", "0" * 16, "0000000000700000", "F" * 16),
        4: ("00000004", "01", "01", "00", "0" * 16, "0000000040000000", "F" * 16),
        5: ("00000004", "01", "01", "00", "0" * 16, "0000000040000000", "F" * 16),
        6: ("00000001", "01", "00", "05", "0" * 16, "0000000000700000", "F" * 16),
    }
    for n, want in expect.items():
        fields = line(n)
        if fields is None:
            continue
        if fields[:7] != want:
            bad.append(f"scenario {n}: LASTRUN fields {fields[:7]} are not {want}")
    fields = line(3)
    if fields and fields[7:] != ("0000000096000004", "0000000000701234", "FFFFFFFFFFF00000"):
        bad.append(f"scenario 3: the exception registers were not kept: {fields[7:]}")

    says(0, "No payload has been entered")
    says(1, "It RETURNED after 300.0 s")
    says(1, "its x0 register held 000000000000012C")
    says(2, "THE DEADMAN RESET THE BOARD")
    says(3, "STOPPED AT A PROCESSOR EXCEPTION")
    says(3, "the deadman fired")
    says(4, "No\r\n  deadman was armed")
    says(5, "No\r\n  deadman was armed")
    for n in (0, 1, 3, 4, 5, 6):
        if "DEADMAN RESET" in got[n]:
            bad.append(f"scenario {n}: says the deadman reset the board, and it did not")
    for n in (0, 2, 4, 5, 6):
        if "RETURNED" in got[n]:
            bad.append(f"scenario {n}: says the payload returned, and it did not")
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = Path(resolve_compiler(args.compiler))
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    with tempfile.TemporaryDirectory(prefix="anvil-runrecord-emitted-") as temporary:
        work = Path(temporary) / "real"
        work.mkdir()
        result, text = run(a64, build(compiler, work))
        bad = verdicts(result, text)
        if bad:
            print("runrecord_emitted_check: FAIL")
            for entry in bad:
                print("   " + entry)
            return 1
        # 15 in-program assertions; 49 LASTRUN fields; the exception's three
        # registers; 8 sentences that must appear; 11 that must not.
        checks = 15 + 49 + 1 + 8 + 11

        caught = 0
        for name in MUTATIONS:
            mwork = Path(temporary) / name
            mwork.mkdir()
            mresult, mtext = run(a64, build(compiler, mwork, name))
            mbad = verdicts(mresult, mtext)
            if not mbad:
                print(f"runrecord_emitted_check: FAIL - the {name} mutant passed")
                return 1
            print(f"  mutant {name}: caught ({mbad[0]})")
            caught += 1
    print(f"runrecord_emitted_check: PASS - {checks} checks over seven outcomes (15 in the gate, 69 on what it printed), "
          f"{caught}/{len(MUTATIONS)} mutants caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
