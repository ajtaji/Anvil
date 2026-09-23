#!/usr/bin/env python3
"""Prove the UNO Q prompt uses UEFI sideband colour, never stream bytes."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "ArduinoQ" / "Board" / "board.unoq"
QEFI = ROOT / "ArduinoQ" / "Board" / "qefi_q.unoq"
QCON = ROOT / "ArduinoQ" / "Board" / "qcon_q.unoq"
FIXTURE = ROOT / "ArduinoQ" / "Tests" / "prompt_style.unoq"


def check_source(board: str, qefi: str, qcon: str) -> None:
    if board.count('Print("pmf> ")') != 1:
        raise AssertionError("the raw five-byte prompt is not unique")
    if "" in board or "\\e[" in board.lower():
        raise AssertionError("an ANSI escape entered the board stream")
    loop = re.search(
        r"promptAttr=QEfiConAttribute\(\).*?"
        r"QEfiSetConAttribute\(#QTXT_LIGHTGREEN\).*?"
        r'Print\("pmf> "\).*?'
        r"UartDrain\(\).*?"
        r"QEfiSetConAttribute\(promptAttr\).*?ReadLine\(\)",
        board,
        re.S,
    )
    if not loop:
        raise AssertionError(
            "prompt colour/save/flush/restore/read ordering is not intact"
        )
    if "#QTXT_LIGHTGREEN   = $0A" not in qefi:
        raise AssertionError("UEFI light-green-on-black attribute drifted")
    for token in (
        "mode=PeekI(gQConOut+#QTXO_MODE)",
        "attribute=PeekL(mode+8)&$FFFFFFFF",
        "fn=PeekI(gQConOut+#QTXO_SETATTR)",
        "QCall(fn,gQConOut,attribute,0,0,0)",
    ):
        if token not in qefi:
            raise AssertionError("UEFI attribute seam is incomplete: " + token)
    if not re.search(
        r"Procedure UartDrain\(\)\s+QConFlushLine\(\)\s+EndProcedure", qcon
    ):
        raise AssertionError("UartDrain no longer flushes the coloured prompt")
    if not re.search(
        r"Procedure UartWrite\(c\.i\).*?gQLog\[gQLogLen\] = c.*?"
        r"gQLineBuf\[gQLineLen\] = c",
        qcon,
        re.S,
    ):
        raise AssertionError("transcript and ConOut no longer receive the same raw byte")


def compile_fixture(compiler: Path) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="anvil-unoq-prompt-") as temporary:
        image = Path(temporary) / "prompt_style.img"
        command = [
            str(compiler), "--compile", str(FIXTURE), "-t", "unoq",
            "--entry-returns", "-S", "-o", str(image),
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True,
            text=True,
        )
        if result.returncode or not image.is_file() or not image.stat().st_size:
            raise SystemExit("UNO Q prompt fixture compile failed\n" + result.stdout + result.stderr)
        symbols = Path(str(image) + ".sym").read_text().lower()
        for name in ("qeficonattribute=", "qefisetconattribute=", "main="):
            if name not in symbols:
                raise AssertionError("emitted fixture omitted " + name[:-1])
        return hashlib.sha256(image.read_bytes()).hexdigest(), symbols


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")

    board = BOARD.read_text()
    qefi = QEFI.read_text()
    qcon = QCON.read_text()
    check_source(board, qefi, qcon)

    mutants = (
        board.replace("QEfiSetConAttribute(#QTXT_LIGHTGREEN)", "", 1),
        board.replace("UartDrain()\n    QEfiSetConAttribute(promptAttr)",
                      "QEfiSetConAttribute(promptAttr)\n    UartDrain()", 1),
        board.replace("QEfiSetConAttribute(promptAttr)", "", 1),
    )
    for index, mutant in enumerate(mutants, 1):
        try:
            check_source(mutant, qefi, qcon)
        except AssertionError:
            continue
        raise AssertionError(f"prompt-order mutant {index} survived")

    image_sha, _ = compile_fixture(compiler)
    print("PASS: UNO Q prompt is UEFI light green, flushed before exact restore;")
    print("  transcript/raw prompt remains exactly five bytes; 3 mutants rejected")
    print("Fixture SHA256:", image_sha)
    print("Compiler SHA256:", hashlib.sha256(compiler.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
