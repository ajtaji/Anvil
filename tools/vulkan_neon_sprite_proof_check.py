#!/usr/bin/env python3
"""Check the returned Pi 4 Neon/Vulkan RGBA sprite report."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


EXPECTED = (
    0x50534E56,  # VNSP
    0,           # payload's own pixel oracle passed
    5,           # completed GPU readback stage
    0,           # adapter creation
    4,           # GPU draw records
    24,          # six vertices per sprite
    1,           # one present intent
    0xFF000000,  # untouched black
    0xFFFF0000,  # opaque red from full scaled image
    0xBF008000,  # half-alpha green over opaque black
    0xFF000000,  # fully transparent blue preserved black
    0xBF008000,  # cropped green equals its full-image sample
    0xFFFF80FF,  # opaque white tinted green to 128
    0,           # no native fault
    0,           # no native fault text
    0x50534E56,
)


def check(data: bytes) -> None:
    if len(data) != 64:
        raise ValueError(f"report is {len(data)} bytes, expected 64")
    words = struct.unpack("<16I", data)
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
    print("PASS: 16 report words, four GPU draws, six exact sprite pixels, zero faults")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
