#!/usr/bin/env python3
"""Check the returning Pi 4 Vulkan stable-ID sprite report."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


MAGIC = 0x4D534E56
ERR_ARGS = (-21201) & 0xFFFFFFFF
ERR_STATE = (-21202) & 0xFFFFFFFF
ERR_CAPACITY = (-21203) & 0xFFFFFFFF
EXPECTED = {
    0: MAGIC,
    1: 0,
    2: 5,
    3: 0,
    4: 4,
    5: 24,
    6: 1,
    7: ERR_ARGS,
    8: ERR_STATE,
    13: 0,
    14: 0,
    15: MAGIC,
    16: 0xFF000000,
    17: 0xFFFF0000,
    18: 0xFF00FF00,
    19: 0xFFFF8000,
    20: 0xFFFF0000,
    21: 0xFF00FF00,
    22: 0xFF0000FF,
    23: 0xFFFFFFFF,
    24: ERR_CAPACITY,
    25: 0,
    26: 0,
    31: MAGIC,
}


def check(data: bytes) -> None:
    if len(data) != 128:
        raise ValueError(f"report is {len(data)} bytes, expected 128")
    words = struct.unpack("<32I", data)
    for slot, expected in EXPECTED.items():
        if words[slot] != expected:
            raise ValueError(
                f"word {slot}: observed 0x{words[slot]:08X}, expected 0x{expected:08X}"
            )
    if not (words[11] < words[9] == words[10] < 1024):
        raise ValueError("stable-ID atlas rows or legacy placement are incorrect")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    check(args.report.read_bytes())
    print("PASS: pre-allocation refusal, wrapped atlas, four GPU draws and exact BGRA pixels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
