"""Validate the 256-byte RAM report from vulkanInstancedTriangleProof.pi4."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

MAGIC = 0x49505456
TAIL = 0x56545049
WINDOW = 0x063E8000
WINDOW_END = WINDOW + 0x00400000
CLEAR = 0xFF000000
RED = 0xFFFF0000
GREEN = 0xFF00FF00


def validate(data: bytes) -> tuple[int, ...]:
    if len(data) != 256:
        raise ValueError(f"expected 256 report bytes, received {len(data)}")
    w = struct.unpack("<64I", data)
    assert (w[0], w[63]) == (MAGIC, TAIL), "wrong report markers"
    assert w[1] == 0, (
        f"status={w[1]} phase={w[2]} detail={w[3]:08X} native={w[4]:08X} "
        f"cmd={w[40]:08X} fault={w[41]:08X} unsafe={w[43]}"
    )
    assert w[2] == 8 and w[3] == 0 and w[42] == 0 and w[43] == 0
    assert w[10] == 128 * 4
    for index, size in ((5, 128 * 128 * 4), (6, 48), (7, 80)):
        assert WINDOW <= w[index] and w[index] + size <= WINDOW_END, (
            f"address {index} outside mapped Vulkan window: {w[index]:08X}"
        )
    assert w[8] >= 48 and w[9] >= 80
    intervals = ((w[5], w[5] + 128 * 128 * 4),
                 (w[6], w[6] + w[8]),
                 (w[7], w[7] + w[9]))
    assert all(a[1] <= b[0] or b[1] <= a[0]
               for j, a in enumerate(intervals) for b in intervals[j + 1:])
    assert w[11] != 0 and w[12] > 0 and w[13] > 0
    assert w[16:24] == (RED, RED, GREEN, GREEN, CLEAR, CLEAR, CLEAR, CLEAR), (
        f"pixels={tuple(f'{x:08X}' for x in w[16:24])}"
    )
    assert w[24:28] == (0, 0, 0, 0), f"pixel/buffer/surface guards={w[24:28]}"
    assert w[29] == w[28] + 1 and w[31] == w[30] + 1
    assert w[33] == w[32] and w[35] == w[34]
    assert w[36] == 1 and w[37] < 0x10000, "expected exactly one packet 38"
    assert 0 < w[38] <= 11_000_000 and w[39] == 1
    assert w[40] == 0
    return w


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()
    w = validate(args.report.read_bytes())
    print(
        "Pi4 Vulkan instancing PASS: one draw, two color-separated triangles, "
        "eight exact pixels, three guards, one instanced packet, "
        f"elapsed {w[38]} us"
    )


if __name__ == "__main__":
    main()
