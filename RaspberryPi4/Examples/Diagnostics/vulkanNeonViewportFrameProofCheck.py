"""Check the returning 160-byte Vulkan viewport-frame report."""

import struct
import sys
from pathlib import Path


def check(payload: bytes) -> str:
    if len(payload) != 160:
        raise ValueError(f"expected 160 report bytes, got {len(payload)}")
    w = struct.unpack("<40I", payload)
    if (w[0], w[39]) != (0x46504E56, 0x564E5046):
        raise ValueError("bad report markers")
    if w[1] != 0:
        raise ValueError(
            f"status={w[1]} stage={w[2]} plan={w[3]} "
            f"begin={w[13]} viewport={w[14]} end={w[15]} "
            f"faults={w[28]} fault_text={w[29]} idle={w[34]} "
            f"create={w[35]} upload={w[36]}"
        )
    expected = {
        2: 5,
        3: 0, 4: 0, 5: 175, 6: 800, 7: 450,
        8: 0, 9: 1, 10: 400 * 65536, 11: 225 * 65536, 12: 0,
        13: 0, 14: 0, 15: 0,
        16: 0xFF000000, 17: 0xFF000000, 18: 0xFF0000FF,
        19: 0xFF0000FF, 20: 0xFF000000,
        21: 0xFFFF0000, 22: 0xFF0000FF, 23: 0xFF0000FF,
        24: 0xFF00FF00,
        25: 3, 26: 18, 27: 1,
        28: 0, 29: 0, 30: 0, 31: 0, 32: 0, 33: 0, 34: 0,
        35: 0, 36: 0,
    }
    for slot, value in expected.items():
        if w[slot] != value:
            raise ValueError(f"word {slot}: expected {value:#x}, got {w[slot]:#x}")
    if any(w[slot] != 0 for slot in range(37, 39)):
        raise ValueError("reserved report words are nonzero")
    return "Vulkan viewport frame pass: black bars, blue content, clipped red box, green sprite, inverse pointer, clean teardown"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonViewportFrameProofCheck.py REPORT.BIN", file=sys.stderr)
        return 2
    try:
        print(check(Path(sys.argv[1]).read_bytes()))
    except (OSError, ValueError) as error:
        print(f"Vulkan viewport frame failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
