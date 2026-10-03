"""Check the returning 128-byte Pi 4 Vulkan Neon font-handle report."""

import struct
import sys
from pathlib import Path


def check(payload: bytes) -> str:
    if len(payload) != 128:
        raise ValueError(f"expected 128 report bytes, got {len(payload)}")
    w = struct.unpack("<32I", payload)
    if (w[0], w[31]) != (0x46464E56, 0x564E4646):
        raise ValueError(f"bad report markers: {w[0]:08X}, {w[31]:08X}")
    if w[1] != 0:
        raise ValueError(
            f"payload status={w[1]} stage={w[2]} create={w[3]} bind={w[4]} "
            f"warm={w[5]} begin={w[8]} draws={w[9:12]} end={w[12]} "
            f"faults={w[19]} fault_text={w[20]} "
            f"dma_error={w[29]} full_atlas_uploads={w[30]}"
        )
    expected = {
        2: 5,
        3: 0, 4: 0, 5: 0,
        7: 18,
        8: 0, 9: 0, 10: 0, 11: 0, 12: 0,
        13: 3, 14: 36,
        16: 0, 17: 0, 18: 0,
        19: 0, 20: 0,
        21: 0, 22: 0, 23: 0, 24: 0,
        25: 1, 26: 4, 28: 0, 29: 0, 30: 2,
    }
    for slot, value in expected.items():
        if w[slot] != value:
            raise ValueError(f"word {slot}: expected {value:#x}, got {w[slot]:#x}")
    if not 8 <= w[6] <= 28:
        raise ValueError(f"unexpected measured Wi width: {w[6]}")
    if w[27] < 1:
        raise ValueError("embedded boot font generation was not published")
    if not 8 <= w[15] <= 1280:
        raise ValueError(f"unexpected reference text ink: {w[15]}")
    return (
        f"Pi 4 Vulkan font port pass: boot slot 4 generation {w[27]}, "
        f"Wi width {w[6]}, line height 18, {w[15]} reference ink pixels; "
        "right/centre translated pixel images match exactly; "
        "three GPU draws, 36 vertices, clean teardown"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonFontPortProofCheck.py REPORT.BIN", file=sys.stderr)
        return 2
    try:
        print(check(Path(sys.argv[1]).read_bytes()))
    except (OSError, ValueError) as error:
        print(f"Pi 4 Vulkan font port failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
