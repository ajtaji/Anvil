#!/usr/bin/env python3
"""Check the Pi 3 console seam and its immutable UART dependency.

This is a source contract gate.  It does not claim that a board emitted the
bytes or that a UART is electrically working; those are separate build and
silicon proofs.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "RaspberryPi3" / "Board" / "board.pi3"
CONSOLE = ROOT / "RaspberryPi3" / "Lib" / "pl011_console.pi3"
UART = ROOT / "RaspberryPi3" / "Lib" / "uart.pbi"

ROUTERS = ("str_print_at", "PrintDec", "PrintNl")


def fail(message: str) -> None:
    raise SystemExit("pi3 console seam gate: " + message)


def definitions(text: str, name: str) -> list[str]:
    return re.findall(
        rf"^\s*Procedure(?:\.\w+)?\s+{re.escape(name)}\s*\(",
        text,
        re.MULTILINE | re.IGNORECASE,
    )


def closure(path: Path, seen: set[Path] | None = None) -> list[tuple[Path, str]]:
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return []
    if not path.is_file():
        fail(f"include-closure file is missing: {path}")
    seen.add(path)
    text = path.read_text(encoding="utf-8")
    result = [(path, text)]
    for raw in re.findall(r"^\s*(?:X)?IncludeFile\s+\"([^\"]+)\"", text, re.MULTILINE | re.IGNORECASE):
        child = ROOT / raw
        result.extend(closure(child, seen))
    return result


def check(board: str, console: str, uart: bytes, committed_uart: bytes, files: list[tuple[Path, str]]) -> list[str]:
    held: list[str] = []
    include = 'XIncludeFile "RaspberryPi3/Lib/pl011_console.pi3"'
    if board.count(include) != 1:
        fail("board composition must include pl011_console.pi3 exactly once")
    held.append("console backend included once")
    composed = "\n".join(text for _, text in files)
    for name in ROUTERS:
        if len(definitions(composed, name)) != 1:
            fail(f"print-router procedure {name} must be defined exactly once")
        held.append(f"{name} exists once")
    if uart.replace(b"\r\n", b"\n") != committed_uart.replace(b"\r\n", b"\n"):
        fail("uart.pbi differs from its committed loader-closure bytes")
    held.append("uart.pbi matches HEAD after newline normalization")
    if "Pi3UartWrite" not in console or "Pi3UartRead" not in console:
        fail("console seam is not layered over the Pi 3 UART procedures")
    held.append("console routes through Pi3UartWrite/Pi3UartRead")
    return held


def mutate(board: str, console: str, uart: bytes, name: str) -> tuple[str, str, bytes]:
    if name == "missing-router":
        return board, re.sub(r"^Procedure PrintNl\(.*?^EndProcedure\n?", "", console, count=1, flags=re.MULTILINE | re.DOTALL), uart
    if name == "duplicate-include":
        line = 'XIncludeFile "RaspberryPi3/Lib/pl011_console.pi3"\n'
        return board.replace(line, line + line, 1), console, uart
    if name == "uart-drift":
        return board, console, uart + b"\n"
    raise ValueError(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    board, console, uart = BOARD.read_text(encoding="utf-8"), CONSOLE.read_text(encoding="utf-8"), UART.read_bytes()
    files = closure(BOARD)
    committed = subprocess.run(["git", "show", "HEAD:RaspberryPi3/Lib/uart.pbi"], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout
    check(board, console, uart, committed, files)
    if args.self_test:
        for name in ("missing-router", "duplicate-include", "uart-drift"):
            try:
                mb, mc, mu = mutate(board, console, uart, name)
                mf = [(p, (mc if p == CONSOLE.resolve() else t)) for p, t in files]
                check(mb, mc, mu, committed, mf)
            except SystemExit:
                continue
            fail(f"{name} mutant was not rejected")
        duplicate = files + [(BOARD, "Procedure PrintNl()\nEndProcedure\n")]
        try:
            check(board, console, uart, committed, duplicate)
        except SystemExit:
            pass
        else:
            fail("duplicate router in another included file was not rejected")
    print("pi3_console_seam_check: PASS - three unique print routers, unchanged UART source, and UART-backed seam")
    if args.self_test:
        print("  self-test: 4/4 mutants rejected")
    return 0


if __name__ == "__main__":
    main()
