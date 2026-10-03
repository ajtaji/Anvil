"""Check the returning 128-byte Vulkan Neon BMP sprite report."""

import struct
import sys
from pathlib import Path


def check(payload: bytes) -> str:
    if len(payload) != 128:
        raise ValueError(f"expected 128 report bytes, got {len(payload)}")
    words = struct.unpack("<32I", payload)
    if (words[0], words[31]) != (0x42504E56, 0x564E5042):
        raise ValueError("bad BMP proof report markers")
    if words[1]:
        raise ValueError(
            f"status={words[1]} stage={words[2]} create={words[3]} "
            f"decode={words[4]} frame_end={words[5]} "
            f"faults={words[17]} fault_text={words[18]}"
        )
    expected = {
        2: 5,
        3: 0,
        4: 0,
        5: 0,
        6: 0xFFFF0000,  # decoded blue: RGBA bytes 00 00 FF FF
        7: 0x00000000,  # keyed green: transparent black
        8: 0x80FFFFFF,  # half-alpha white
        9: 0x00FF0000,  # invisible blue retains its RGB
        10: 0xFF000000,  # clear black
        11: 0xFFFF0000,  # red underlay
        12: 0xFF0000FF,  # opaque blue
        13: 0xFFFF0000,  # color key exposes red
        14: 0xBFFF8080,  # shared source-alpha factors also blend alpha
        15: 0xFFFF0000,  # zero-alpha blue exposes red
        16: 0xFF000000,  # outside remains black
        17: 0,
        18: 0,
        19: 0,
        20: 0,
        21: 0,
        22: 0,
        23: 2,
        24: 12,
        25: 1,
        26: 0x00010001,  # alpha mask [1, 0, 1, 0]
        27: 2,
        28: 2,
    }
    for index, value in expected.items():
        if words[index] != value:
            raise ValueError(f"word {index}: expected {value:#x}, got {words[index]:#x}")
    if words[29] < 1:
        raise ValueError("sprite generation was not published")
    return (
        "Vulkan Neon BMP sprite pass: decoded 2x2 BGRA, keyed green, "
        f"half-alpha blend={words[14]:#010x}, two draws/12 vertices, clean teardown"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonPortBmpProofCheck.py REPORT.BIN", file=sys.stderr)
        return 2
    try:
        print(check(Path(sys.argv[1]).read_bytes()))
    except (OSError, ValueError) as error:
        print(f"Vulkan Neon BMP sprite failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
