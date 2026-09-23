#!/usr/bin/env python3
"""Focused gate for source -> compiler -> artifact -> ledger build identity.

The real build orchestration and counter modules run against disposable board
trees. A deterministic compiler seam records the marker visible when
``PureMetalForge --compile`` is invoked and emits private artifact sets. This
keeps the gate fast while proving transaction order, rollback and locking on
both Windows and Linux.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import tempfile
import threading
import time
import traceback


HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load("anvil_build_transaction_gate", HERE / "build.py")
counter = build.build_count


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def yes(self, value: bool, message: str) -> None:
        self.count += 1
        if not value:
            raise AssertionError(message)


BOARD = b"""LoadAddress $200000
#ANVIL_BUILD = 7 ; pmf:build
#ANVIL_BUILD_DATE = 20260911 ; pmf:builddate
#ANVIL_BUILD_TIME = 120000 ; pmf:buildtime
Procedure Main()
EndProcedure
"""


def marker(path: Path) -> int:
    match = re.search(rb"(?m)^#ANVIL_BUILD = ([0-9]+) ; pmf:build$", path.read_bytes())
    if not match:
        raise AssertionError("board marker disappeared")
    return int(match.group(1))


def tree(where: Path) -> tuple[Path, Path, Path]:
    root = where / "tree"
    board = root / counter.BOARDS["pi4"]
    board.parent.mkdir(parents=True)
    board.write_bytes(BOARD)
    (root / "Boards").mkdir()
    compiler = where / ("PureMetalForge.exe" if __import__("os").name == "nt" else "PureMetalForge")
    compiler.write_bytes(b"unified-puremetalforge-gate")
    output = root / build.TARGETS["pi4"]["output"]
    output.parent.mkdir(parents=True)
    return root, compiler, output


class CompilerSeam:
    def __init__(self) -> None:
        self.mode = "success"
        self.seen: list[int] = []
        self.first_entered: threading.Event | None = None
        self.release_first: threading.Event | None = None
        self.guard = threading.Lock()

    def __call__(self, command, *, cwd, env, check):
        if command[1] != "--compile" or "-o" not in command:
            raise AssertionError("build did not use unified PureMetalForge --compile")
        source = Path(cwd) / command[2]
        output = Path(command[command.index("-o") + 1])
        value = marker(source)
        with self.guard:
            index = len(self.seen)
            self.seen.append(value)
        if index == 0 and self.first_entered is not None:
            self.first_entered.set()
            if not self.release_first.wait(10):
                raise AssertionError("concurrency gate did not release first compiler")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"IMAGE BUILD={value}".encode("ascii"))
        if self.mode == "failure":
            return SimpleNamespace(returncode=1)
        if self.mode != "missing-pmf":
            Path(str(output) + ".pmf").write_bytes(f"PMF BUILD={value}".encode("ascii"))
        Path(str(output) + ".sym").write_bytes(f"SYM BUILD={value}".encode("ascii"))
        Path(str(output) + ".dbg").write_bytes(f"DBG BUILD={value}".encode("ascii"))
        return SimpleNamespace(returncode=0)


def configure(root: Path, seam: CompilerSeam) -> None:
    build.ROOT = root
    build.subprocess.run = seam


def debris(root: Path) -> list[Path]:
    return [path for path in root.rglob("*")
            if ".build-stage-" in path.name or ".build-backup-" in path.name]


def snapshot(root: Path, output: Path) -> tuple[bytes, bytes, dict[str, bytes]]:
    board = root / counter.BOARDS["pi4"]
    ledger = root / counter.LEDGER_NAME
    files = {}
    for suffix in ("", ".pmf", ".sym", ".dbg"):
        path = Path(str(output) + suffix)
        if path.is_file():
            files[suffix] = path.read_bytes()
    return board.read_bytes(), ledger.read_bytes() if ledger.is_file() else b"", files


def old_artifacts(output: Path) -> None:
    for suffix in ("", ".pmf", ".sym", ".dbg"):
        path = Path(str(output) + suffix)
        path.write_bytes(("OLD" + suffix).encode("ascii"))


def check_success(c: Checks, where: Path) -> None:
    root, compiler, output = tree(where)
    old_artifacts(output)
    seam = CompilerSeam()
    configure(root, seam)
    build.build(str(compiler), "pi4")
    board = root / counter.BOARDS["pi4"]
    ledger = (root / counter.LEDGER_NAME).read_text(encoding="utf-8")
    c.yes(seam.seen == [8], "compiler did not see newly reserved build 8")
    c.yes(marker(board) == 8, "successful source did not retain build 8")
    c.yes(output.read_bytes() == b"IMAGE BUILD=8", "published image identity differs")
    c.yes(Path(str(output) + ".pmf").read_bytes() == b"PMF BUILD=8", "PMF differs")
    c.yes(Path(str(output) + ".sym").read_bytes() == b"SYM BUILD=8", "SYM differs")
    c.yes(Path(str(output) + ".dbg").read_bytes() == b"DBG BUILD=8", "DBG differs")
    c.yes("build=8" in ledger, "ledger did not record the embedded build")
    c.yes(f"compiler={hashlib.sha256(compiler.read_bytes()).hexdigest()}" in ledger,
          "ledger did not identify the unified compiler")
    c.yes(not debris(root), "successful transaction left stage/backup debris")


def check_refusal(c: Checks, where: Path, mode: str) -> None:
    root, compiler, output = tree(where)
    old_artifacts(output)
    ledger = root / counter.LEDGER_NAME
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_bytes(b"BASELINE\n")
    before = snapshot(root, output)
    seam = CompilerSeam()
    seam.mode = mode
    configure(root, seam)
    try:
        build.build(str(compiler), "pi4")
    except SystemExit:
        pass
    else:
        raise AssertionError(f"{mode}: build unexpectedly succeeded")
    c.yes(snapshot(root, output) == before, f"{mode}: source/ledger/artifacts changed")
    c.yes(seam.seen == [8], f"{mode}: compiler did not see reserved build 8")
    c.yes(not debris(root), f"{mode}: private artifacts survived refusal")


def check_publish_failure(c: Checks, where: Path) -> None:
    root, compiler, output = tree(where)
    old_artifacts(output)
    ledger = root / counter.LEDGER_NAME
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_bytes(b"BASELINE\n")
    before = snapshot(root, output)
    seam = CompilerSeam()
    configure(root, seam)
    original = build.PublishedArtifacts.publish
    build.PublishedArtifacts.publish = lambda self: (_ for _ in ()).throw(OSError("injected publish failure"))
    try:
        try:
            build.build(str(compiler), "pi4")
        except OSError:
            pass
        else:
            raise AssertionError("publication failure unexpectedly succeeded")
    finally:
        build.PublishedArtifacts.publish = original
    c.yes(snapshot(root, output) == before, "publication failure consumed identity/artifact")
    c.yes(not debris(root), "publication failure left private artifacts")


def check_ledger_failure(c: Checks, where: Path) -> None:
    root, compiler, output = tree(where)
    old_artifacts(output)
    ledger = root / counter.LEDGER_NAME
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_bytes(b"BASELINE\n")
    before = snapshot(root, output)
    seam = CompilerSeam()
    configure(root, seam)
    original = counter._append

    def partial_then_fail(path: Path, line: str) -> None:
        with path.open("ab") as handle:
            handle.write(b"PARTIAL")
        raise OSError("injected ledger failure")

    counter._append = partial_then_fail
    try:
        try:
            build.build(str(compiler), "pi4")
        except OSError:
            pass
        else:
            raise AssertionError("ledger failure unexpectedly succeeded")
    finally:
        counter._append = original
    c.yes(snapshot(root, output) == before, "ledger failure did not roll back whole transaction")
    c.yes(not debris(root), "ledger failure left stage/backup debris")


def check_concurrent(c: Checks, where: Path) -> None:
    root, compiler, output = tree(where)
    seam = CompilerSeam()
    seam.first_entered = threading.Event()
    seam.release_first = threading.Event()
    configure(root, seam)
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            build.build(str(compiler), "pi4")
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=runner)
    second = threading.Thread(target=runner)
    first.start()
    c.yes(seam.first_entered.wait(5), "first compiler never entered")
    second.start()
    time.sleep(0.25)
    c.yes(seam.seen == [8], "second compiler entered while first owned build lock")
    seam.release_first.set()
    first.join(10)
    second.join(10)
    if first.is_alive() or second.is_alive():
        stacks = []
        frames = sys._current_frames()
        lock = root / counter.LOCK_NAME
        lock_state = f"lock exists={lock.exists()} content={lock.read_bytes()!r}" if lock.exists() else "lock absent"
        for name, thread in (("first", first), ("second", second)):
            if thread.is_alive() and thread.ident in frames:
                stacks.append(f"{name} thread:\n" + "".join(traceback.format_stack(frames[thread.ident])))
        raise AssertionError("concurrent builds did not finish; " + lock_state + "\n" + "\n".join(stacks))
    c.yes(not errors, f"concurrent build failed: {errors}")
    c.yes(seam.seen == [8, 9], f"concurrent compilers saw {seam.seen}, not [8, 9]")
    c.yes(marker(root / counter.BOARDS["pi4"]) == 9, "concurrent final source is not 9")
    c.yes(output.read_bytes() == b"IMAGE BUILD=9", "concurrent final artifact is not 9")
    lines = (root / counter.LEDGER_NAME).read_text(encoding="utf-8").splitlines()
    c.yes([re.search(r"\bbuild=([0-9]+)", line).group(1) for line in lines] == ["8", "9"],
          "concurrent ledger did not serialize builds 8 then 9")
    c.yes(not debris(root), "concurrent transactions left stage/backup debris")


def main() -> int:
    c = Checks()
    with tempfile.TemporaryDirectory(prefix="anvil-build-identity-") as folder:
        root = Path(folder)
        check_success(c, root / "success")
        check_refusal(c, root / "compile-failure", "failure")
        check_refusal(c, root / "missing-pmf", "missing-pmf")
        check_publish_failure(c, root / "publish-failure")
        check_ledger_failure(c, root / "ledger-failure")
        check_concurrent(c, root / "concurrent")
    print(f"build_identity_transaction_check: PASS ({c.count} checks)")
    print("  compiler always saw the reserved identity; every failure restored source/ledger/artifacts")
    print("  two overlapping builds serialized as embedded and recorded builds 8 then 9")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
