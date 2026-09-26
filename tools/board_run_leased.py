#!/usr/bin/env python3
"""Require this lane's shared-board lease before running a RAM payload.

Usage: python tools/board_run_leased.py LANE SHARE -- PAYLOAD [board_run options]
The lease check and every board command run in this same process.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 5 or sys.argv[3] != "--":
        print(__doc__, file=sys.stderr)
        return 2
    lane, share = sys.argv[1:3]
    board_args = sys.argv[4:]
    import board_lease

    sys.argv = ["board_lease.py", "require", "--lane", lane, "--share", share]
    if board_lease.main() != 0:
        return 2
    import board_run

    return board_run.main(board_args)


if __name__ == "__main__":
    sys.exit(main())
