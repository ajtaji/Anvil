#!/usr/bin/env python3
"""Validate the Pi 4 two-instance Vulkan payload's 256-byte return report."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


MAGIC = 0x49505456
TAIL = 0x56545049
RED = 0xFFFF0000
GREEN = 0xFF00FF00
CLEAR = 0xFF000000
PIXELS = (RED, RED, GREEN, GREEN, CLEAR, CLEAR, CLEAR, CLEAR)


def check(data: bytes) -> tuple[int, int]:
    if len(data) != 256:
        raise ValueError(f"report is {len(data)} bytes; expected 256")
    w = struct.unpack("<64I", data)
    if w[0] != MAGIC or w[63] != TAIL:
        raise ValueError("return report has wrong magic or tail")
    if w[1] != 0 or w[2] != 8 or w[3] != 0 or w[4] != 0:
        raise ValueError(
            f"payload failed: status={w[1]} phase={w[2]} detail=0x{w[3]:08X} native=0x{w[4]:08X}"
        )
    if tuple(w[16:24]) != PIXELS:
        raise ValueError("two-instance red/green pixel pattern is incorrect")
    if any(w[i] for i in (24, 25, 26, 27, 40, 41, 42, 43)):
        raise ValueError("pixel/guard, command-buffer, fault, idle, or in-flight check failed")
    if w[29] != w[28] + 1 or w[31] != w[30] + 1:
        raise ValueError("expected exactly one bin and one render job")
    if w[33] != w[32] or w[35] != w[34]:
        raise ValueError("V3D MMU fault or bin OOM count changed")
    if w[36] != 1 or w[37] == 0xFFFFFFFF or w[39] != 1:
        raise ValueError("expected one full instanced packet and one backend draw")
    if w[10] != 128 * 4 or w[8] < 48 or w[9] < 80:
        raise ValueError("unexpected image pitch or vertex/instance allocation")
    if any(w[i] == 0 for i in (5, 6, 7, 11, 12, 13)):
        raise ValueError("missing image, vertex, instance, or shader resource")
    if w[38] == 0 or w[38] > 15_000_000:
        raise ValueError("payload elapsed time outside its deadman window")
    return w[38], w[37]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="256 bytes from board_run.py --trace")
    args = parser.parse_args()
    elapsed, packet_offset = check(args.report.read_bytes())
    print(
        "PASS: two GPU instances, exact red/green pixels, guards, "
        f"one instanced packet at +{packet_offset}, {elapsed} us"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
