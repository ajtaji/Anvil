#!/usr/bin/env python3
"""Build one strict BCM2837 P3SLOT image from a compiler-emitted PMF file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import os

from pi3_slot import SlotError, wrap_monitor


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temp_path = Path(temporary)
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pmf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.pmf.is_file():
        raise SlotError(f"PMF file does not exist: {args.pmf}")
    slot, metadata = wrap_monitor(args.pmf.read_bytes())
    atomic_write(args.output, slot)
    atomic_write(
        Path(str(args.output) + ".json"),
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("ascii"),
    )
    print(f"packed {args.output} ({len(slot)} bytes, SHA-256 {metadata['slotSha256']})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SlotError as exc:
        print(f"!! {exc}", file=sys.stderr)
        raise SystemExit(1)
