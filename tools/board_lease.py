#!/usr/bin/env python3
"""The shared-board lease, as a gate a script cannot forget.

WHAT WENT WRONG, 2026-09-18, and why this is a tool rather than a habit.
A lane about to flash the Pi 4 edited the live-holder callout in
BOARD-SHARE.md with an anchored replacement, took the board, and ran its
session. The anchor did not match - another lane had already taken the
board seconds earlier - so the edit raised. THE BOARD SESSION ON THE NEXT
LINE RAN ANYWAY and sent four commands into the other lane's run, which
at that moment was moving files between partitions one verified file at a
time. Nothing was damaged: the four were read-only with respect to the
medium and the console never answered them. But the check and the thing
it guards were two separate commands, and a check whose failure does not
stop the thing it guards is not a check.

So: call `require` as the FIRST act of any board session, in the same
process, and refuse to send when it refuses. `take` will not take a board
somebody else holds, and `release` will not release one this lane does
not hold.

    python tools/board_lease.py show
    python tools/board_lease.py require
    python tools/board_lease.py take    "<one line of intent>"
    python tools/board_lease.py release "<the state it is left in>"
    python tools/board_lease.py row     "<a ledger row, without the pipes>"

The lane name comes from --lane or the ANVIL_LANE environment variable.
It is not defaulted: a lease held by "the lane" identifies nobody, and the
whole file exists so that two lanes can tell each other apart.

THE CALLOUT IS THE TRUTH AND THE LEDGER IS THE RECORD. `take` and
`release` rewrite only the live-holder callout; `row` appends to the
transfer ledger at the end. Neither ever edits another lane's row.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# The vault is outside this repository on purpose - it is the bench's
# shared memory, not this repository's. Overridable for a different bench.
DEFAULT_SHARE = Path(r"C:\Embedded Compiler\CompilerEmbedded\Raspberry Pi 4\BOARD-SHARE.md")

START = "> [!important] Live holder"
END = "> [!warning] SHARE THE BOARD"


def read(path: Path) -> tuple[str, str]:
    """The file, and the newline it uses. Line endings are preserved: this
    file is edited by several lanes and by hand, and a tool that silently
    rewrote every line ending would show up as a whole-file diff that hid
    the one line that actually changed."""
    text = io.open(path, encoding="utf-8", newline="").read()
    return text, "\r\n" if "\r\n" in text else "\n"


def bounds(text: str) -> tuple[int, int]:
    i = text.find(START)
    if i < 0:
        raise SystemExit(f"board_lease: {START!r} is not in the share file - "
                         "it has been restructured, and this tool will not "
                         "guess where the live holder now lives")
    j = text.find(END, i)
    if j < 0:
        raise SystemExit(f"board_lease: {END!r} does not follow the live "
                         "holder - refusing to rewrite an unknown span")
    return i, j


def callout(text: str) -> str:
    i, j = bounds(text)
    return text[i:j].rstrip()


def replace(text: str, body: str, nl: str) -> str:
    i, j = bounds(text)
    return text[:i] + body.replace("\n", nl) + nl + nl + text[j:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["show", "require", "take", "release", "row"])
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--lane", default=None)
    ap.add_argument("--share", default=str(DEFAULT_SHARE))
    args = ap.parse_args()

    path = Path(args.share)
    text, nl = read(path)
    now = callout(text)

    if args.action == "show":
        print(now)
        return 0

    import os
    lane = args.lane or os.environ.get("ANVIL_LANE")
    if not lane:
        print("board_lease: no lane name. Pass --lane or set ANVIL_LANE. A "
              "lease held by nobody in particular is not a lease.")
        return 2

    if args.action == "require":
        if lane not in now:
            print(f"REFUSED: the board is not {lane}'s. The callout says:\n")
            print(now)
            return 2
        print(f"held by {lane}")
        return 0

    if args.action == "take":
        if not args.text:
            print("board_lease: take needs one line saying what will be sent.")
            return 2
        if "**FREE**" not in now:
            print("REFUSED: the board is not FREE, so nothing was changed and "
                  "nothing may be sent. The callout says:\n")
            print(now)
            return 2
        previous = now.split("\n", 1)[1] if "\n" in now else ""
        body = (f"{START}\n> **HELD - {lane}.** {args.text}\n>\n"
                f"> Previously:\n{previous}")
        io.open(path, "w", encoding="utf-8", newline="").write(replace(text, body, nl))
        print("taken")
        return 0

    if args.action == "release":
        if lane not in now:
            print(f"REFUSED: {lane} does not hold the board, so it has nothing "
                  "to release. The callout says:\n")
            print(now)
            return 2
        body = f"{START}\n> **FREE** - {args.text}"
        io.open(path, "w", encoding="utf-8", newline="").write(replace(text, body, nl))
        print("released")
        return 0

    if args.action == "row":
        if not args.text:
            print("board_lease: row needs the row's text.")
            return 2
        stripped = text.rstrip("\r\n")
        io.open(path, "w", encoding="utf-8", newline="").write(
            stripped + nl + args.text.replace("\n", " ") + nl)
        print("row appended")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
