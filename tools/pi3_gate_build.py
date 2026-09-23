#!/usr/bin/env python3
"""One way for a Pi 3 desk gate to compile something, counted when it must be.

A gate that compiles an isolated fixture out of the Tests tree is not building
the monitor and has no number to raise. A gate that hands the compiler one of
the real board entry points IS building the monitor, temporary directory or
not, and the number has to move with it: `version` on a board exists so a person
can tell images apart without hashing anything, and that only works if every
build counts.

The identity is reserved and stamped into the board file BEFORE the compiler
reads it, never after. Stamping afterwards is what once shipped a loader and an
updater that truthfully printed 7 while their source said 8.

Nothing here publishes an artifact, so there is no publication to roll back; a
failed compile raises and the enclosing transaction restores the source bytes
and the ledger extent on its way out.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_count

ROOT = Path(__file__).resolve().parents[1]


def board_target(source, root: Path = ROOT) -> str | None:
    """The counting target this source is the board entry point of, if any."""
    for target in build_count.BOARDS:
        if not target.startswith("pi3"):
            continue
        if build_count.board_for(source, target, root) is not None:
            return target
    return None


def compile_counted(run, source, image, *, compiler, by: str, root: Path = ROOT):
    """Run `run()` to compile `source`, counting it when it is a board image.

    `run` takes no arguments and must raise if the compile failed; `image` is
    the path it produces. The return value is the counting Result, or None when
    the source was a fixture and no number was owed.
    """
    target = board_target(source, root)
    if target is None:
        run()
        return None
    with build_count.build_identity(
        source, target, compiler=str(compiler), by=by, root=root
    ) as identity:
        run()
        return identity.complete(image)
