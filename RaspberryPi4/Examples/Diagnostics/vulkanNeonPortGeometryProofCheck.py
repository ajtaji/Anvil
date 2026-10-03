"""Check the returning 128-byte Neon Vulkan polygon, line and batch report."""

import struct
import sys
from pathlib import Path


def check(payload: bytes) -> str:
    if len(payload) != 128:
        raise ValueError(f"expected 128 report bytes, got {len(payload)}")
    w = struct.unpack("<32I", payload)
    if (w[0], w[31]) != (0x47504E56, 0x564E5047):
        raise ValueError(f"bad report markers: {w[0]:08X}, {w[31]:08X}")
    if w[1] != 0:
        raise ValueError(
            f"status={w[1]} stage={w[2]} create={w[3]} upload={w[4]} "
            f"begin={w[5]} fill={w[6]} outline={w[7]} lines={w[8]} "
            f"batch={w[9:13]} end={w[13]} faults={w[26:28]}"
        )
    expected = {
        2: 5,
        **{slot: 0 for slot in range(3, 14)},
        14: 5,
        15: 54,
        16: 1,
        17: 0xFF000000,
        18: 0xFFFF0000,
        19: 0xFF000000,
        20: 0xFF000000,
        21: 0xFF0000FF,
        22: 0xFFFF00FF,
        23: 0xFF000000,
        26: 0,
        27: 0,
        28: 0,
        29: 0,
        30: 0,
    }
    for slot, value in expected.items():
        if w[slot] != value:
            raise ValueError(f"word {slot}: expected {value:#x}, got {w[slot]:#x}")
    if not 16 <= w[24] <= 96:
        raise ValueError(f"outline green pixels outside range: {w[24]}")
    if not 8 <= w[25] <= 40:
        raise ValueError(f"static-line yellow pixels outside range: {w[25]}")
    return (
        "Neon Vulkan geometry pass: filled red polygon, outlined green "
        f"polygon ({w[24]} pixels), yellow static line ({w[25]} pixels), "
        "ordered blue/magenta sprite batch; draws=5 vertices=54; cleanup clear"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonPortGeometryProofCheck.py REPORT.BIN", file=sys.stderr)
        return 2
    try:
        print(check(Path(sys.argv[1]).read_bytes()))
    except (OSError, ValueError) as error:
        print(f"Neon Vulkan geometry failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
