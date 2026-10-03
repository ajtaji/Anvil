"""Check the returning 128-byte Vulkan Neon port-frame report."""

import struct
import sys
from pathlib import Path


def check(payload: bytes) -> str:
    if len(payload) != 128:
        raise ValueError(f"expected 128 report bytes, got {len(payload)}")
    w = struct.unpack("<32I", payload)
    if (w[0], w[31]) != (0x46504E56, 0x564E5046):
        raise ValueError(f"bad report markers: {w[0]:08X}, {w[31]:08X}")
    if w[1] != 0:
        raise ValueError(
            f"payload status={w[1]} stage={w[2]} "
            f"create={w[3]} upload={w[4]} begin={w[5]} "
            f"text={w[7]} sprite={w[8]} end={w[9]} "
            f"faults={w[15]} fault_text={w[16]}"
        )
    expected = {
        2: 5,
        3: 0,
        4: 0,
        5: 0,
        6: 8,
        7: 0,
        8: 0,
        9: 0,
        10: 0xFF000000,
        11: 0xFFFF0000,
        12: 0xFF0000FF,
        13: 0xFFFF0000,
        15: 0,
        16: 0,
        17: 0,
        18: 0,
        19: 0,
        20: 0,
        21: 3,
        22: 18,
        23: 1,
    }
    for slot, value in expected.items():
        if w[slot] != value:
            raise ValueError(f"word {slot}: expected {value:#x}, got {w[slot]:#x}")
    if not 1 <= w[14] <= 128:
        raise ValueError(f"white text pixels outside expected range: {w[14]}")
    return (
        "Vulkan Neon port frame pass: rectangle, text, cropped sprite; "
        f"ordered pixels=black/red/blue/red; white text pixels={w[14]}; "
        "draws=3 vertices=18; cleanup clear"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonPortFrameProofCheck.py REPORT.BIN", file=sys.stderr)
        return 2
    try:
        print(check(Path(sys.argv[1]).read_bytes()))
    except (OSError, ValueError) as error:
        print(f"Vulkan Neon port frame failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
