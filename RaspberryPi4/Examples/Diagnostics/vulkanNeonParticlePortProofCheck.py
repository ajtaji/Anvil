"""Check the returning 128-byte Pi 4 Vulkan Neon particle adapter report."""

import struct
import sys
from pathlib import Path


def check(payload: bytes) -> str:
    if len(payload) != 128:
        raise ValueError(f"expected 128 report bytes, got {len(payload)}")
    w = struct.unpack("<32I", payload)
    if (w[0], w[31]) != (0x5050564E, 0x4E565050):
        raise ValueError(f"bad report markers: {w[0]:08X}, {w[31]:08X}")
    if w[1] != 0:
        raise ValueError(
            f"payload status={w[1]} stage={w[2]} create={w[3]} "
            f"init={w[4]} camera={w[5]} adds={w[6:9]} prepare={w[9]} "
            f"begin/draw/end={w[10:13]} faults={w[21]} fault_text={w[22]} "
            f"pixels={[f'{p:08X}' for p in w[15:21]]}"
        )
    expected = {
        2: 6,
        3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
        10: 0, 11: 0, 12: 0,
        13: 1, 14: 18,
        15: 0xFFFF0000, 18: 0xFF0000FF,
        19: 0xFF0000FF, 20: 0xFF000000,
        21: 0, 22: 0,
        23: 0, 24: 0, 25: 0, 26: 0,
        27: 1, 28: 0, 29: 3, 30: 1,
    }
    for slot, value in expected.items():
        if w[slot] != value:
            raise ValueError(f"word {slot}: expected {value:#x}, got {w[slot]:#x}")
    mixed = w[16]
    if mixed >> 24 != 0xBF or mixed & 255:
        raise ValueError(f"overlap pixel has wrong alpha or blue: {mixed:08X}")
    if not 112 <= (mixed >> 16) & 255 <= 144 or not 112 <= (mixed >> 8) & 255 <= 144:
        raise ValueError(f"ordered red/green blend absent: {mixed:08X}")
    green = w[17]
    if green >> 24 != 0xBF or (green >> 16) & 255 or green & 255:
        raise ValueError(f"green-only pixel has wrong channels: {green:08X}")
    if not 112 <= (green >> 8) & 255 <= 144:
        raise ValueError(f"green-only alpha blend absent: {green:08X}")
    return (
        "Pi 4 Vulkan particle port pass: three ordered particles, "
        "one GPU draw, 18 vertices, red/green alpha blend, "
        "rotated blue tip and empty corner, clean teardown"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticlePortProofCheck.py REPORT.BIN", file=sys.stderr)
        return 2
    try:
        print(check(Path(sys.argv[1]).read_bytes()))
    except (OSError, ValueError) as error:
        print(f"Pi 4 Vulkan particle port failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
