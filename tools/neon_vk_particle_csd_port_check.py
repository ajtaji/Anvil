#!/usr/bin/env python3
"""Validate the Pi 4 Neon adapter-to-CSD returning report."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

MAGIC = 0x4D43564E
TAIL = 0x4E56434D
WINDOW = 0x063E8000
WINDOW_BYTES = 0x00C00000


def colour(item: int) -> int:
    return (0xFF000000 | (((item * 29 + 97) & 255) << 16)
            | (((item * 43 + 59) & 255) << 8) | ((item * 67 + 31) & 255))


def validate(data: bytes) -> tuple[int, ...]:
    if len(data) != 256:
        raise ValueError("report must be exactly 256 bytes")
    w = struct.unpack("<64I", data)
    assert (w[0], w[63]) == (MAGIC, TAIL), "report markers"
    assert (w[1], w[2]) == (0, 5), f"status/phase {w[1:3]}"
    for i in (3, 9, 11, 12, 13, 16, 17, 18, 19, 22, 23, 24, 30, 33,
              50, 51, 52, 53, 55, 56, 58, 59, 60):
        assert w[i] == 0, f"report slot {i}: {w[i]}"
    assert w[54] == 1, "bitmap atlas readiness"
    assert w[14] != w[15], "CSD completion did not advance"
    assert (w[31], w[32], w[38], w[39]) == (1, 1, 1, 192), "GPU jobs/draw/vertices"
    assert tuple(w[25:30]) == (0xFF000000, *(colour(i) for i in range(4))), "five pixel probes"
    assert tuple(w[40:43]) == (0xBF580000, 0x3F800000, 0x3D400000), "selected GPU vertex words"
    assert (w[5], w[45], w[46], w[47]) == (12288, 512, WINDOW, WINDOW_BYTES), "allocation metadata"
    assert 0 < w[10] <= 4096, "QPU code size"
    regions = [(w[i], w[i] + size) for i, size in
               ((4, 12288), (6, 4096), (7, 4096), (8, 8192), (44, 128 * 128 * 4))]
    assert all(start % 4096 == 0 and WINDOW <= start and end <= WINDOW + WINDOW_BYTES
               for start, end in regions), "allocation outside mapped V3D window"
    assert all(a[1] <= b[0] or b[1] <= a[0]
               for pos, a in enumerate(regions) for b in regions[pos + 1:]), "overlapping allocations"
    assert 0 < w[37] <= 7_000_000 and 0 < w[43] <= 7_000_000, "setup/prepare time bound"
    assert 0 < w[48] <= 1_000_000 and 0 < w[49] <= 10_000_000, "CSD/render time bound"
    assert 0 < w[61] <= 3_000_000 and 0 < w[62] <= 13_000_000, "oracle/total time bound"
    return w


def mutation_checks(data: bytes) -> None:
    for index, value in ((1, 8), (2, 3), (16, 1), (18, 1), (26, 0),
                         (31, 0), (39, 0), (55, 1)):
        altered = bytearray(data)
        struct.pack_into("<I", altered, index * 4, value)
        try:
            validate(altered)
        except AssertionError:
            continue
        raise AssertionError(f"mutation of report word {index} was not rejected")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()
    data = args.report.read_bytes()
    w = validate(data)
    mutation_checks(data)
    print("Pi 4 Neon GPU particle adapter: 32 items, 192 exact vertices, "
          "input/output guards, pixel probes, one bin/render job, clean teardown; "
          "8 report mutations rejected")
    print("Prepare %d us; CSD %d us; Vulkan End %d us; total %d us" %
          (w[43], w[48], w[49], w[62]))


if __name__ == "__main__":
    main()
