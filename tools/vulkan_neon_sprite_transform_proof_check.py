#!/usr/bin/env python3
"""Check Pi 4 Vulkan sprite rotation and camera report pixels."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


EXPECTED = (
    0x54534E56, 0, 7, 0, 4, 24, 1,
    0xFF000000, 0xFFFF0000, 0xBF008000, 0xFF000000,
    0xBF008000, 0xFFFF80FF, 0, 0, 0x54534E56,
    0xFFFFAD2F,  # hostile coordinate refused before fixed-point products
    3, 18,      # three GPU transform draws, six vertices each
    0xFF000000, 0xFF000000, 0xFFFF0000, 0xFFFFFFFF,
    0xBF008000, 0xFFFF0000, 0xBF008000, 0xFF000000,
    0xFFFFFFFF, 0xFFFF0000, 0xFF000000, 1, 0x54534E56,
)


def check(data: bytes) -> None:
    if len(data) != 128:
        raise ValueError(f"report is {len(data)} bytes, expected 128")
    words = struct.unpack("<32I", data)
    for slot, (observed, expected) in enumerate(zip(words, EXPECTED)):
        if observed != expected:
            raise ValueError(
                f"word {slot}: observed 0x{observed:08X}, expected 0x{expected:08X}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    check(args.report.read_bytes())
    print("PASS: 32 report words, three GPU transforms, exact pixel and refusal checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
