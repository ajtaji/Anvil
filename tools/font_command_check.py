#!/usr/bin/env python3
"""Emitted host test for the real Anvil font command parser and fake seams."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate, run_entry, ROOT  # noqa: E402

GATE = ROOT / "RaspberryPi4/Tests/font_command_gate.pi4"


def mutant_rejected(compiler: Path, temp: Path) -> bool:
    stage = temp / "mutant"
    for rel in ("Anvil/Core/font_cmd.pbi", "RaspberryPi4/Tests/font_command_gate.pi4",
                "Anvil/Graphics/truetype_slots.pbi",
                "RaspberryPi4/Intrinsics/bcm2711_hardware.def",
                "Boards/Raspberry_Pi_4.board"):
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    module = stage / "Anvil/Core/font_cmd.pbi"
    source = module.read_text()
    anchor = "gWordAt = gPos\n  SkipWord()\n  gWordLen = gPos - gWordAt\n  If WordIs(\"info\")"
    if anchor not in source:
        raise SystemExit("font command dispatcher token mutant anchor missing")
    module.write_text(source.replace(anchor, "If WordIs(\"info\")", 1))
    image = temp / "font_command_mutant.img"
    symbols, blob = compile_gate(compiler, stage,
                                 stage / "RaspberryPi4/Tests/font_command_gate.pi4", image)
    result, _ = run_entry(symbols, blob)
    return result != 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-font-command-") as directory:
        temp = Path(directory)
        image = temp / "font_command.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        result, steps = run_entry(symbols, blob)
        if result:
            raise SystemExit(f"font command emitted gate failed assertion {result}")
        if not mutant_rejected(compiler, temp):
            raise SystemExit("missing subcommand tokenization mutant was not rejected")
        print(f"PASS: emitted font command/settings gate, 20 assertions, {steps} interpreted instructions")
        print("PASS: info, load/path, selection, bitmap fallback, bounded size and default persistence")
        print("PASS: missing token setup mutant rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
