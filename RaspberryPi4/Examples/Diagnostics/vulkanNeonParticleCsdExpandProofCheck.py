"""Check the returning 256-byte Pi 4 CSD particle-expansion report."""

import struct
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticleCsdExpandProofCheck.py REPORT.BIN")
        return 2
    payload = Path(sys.argv[1]).read_bytes()
    if len(payload) != 256:
        raise ValueError(f"expected 256 report bytes, got {len(payload)}")
    w = struct.unpack("<64I", payload)
    assert w[0] == 0x4543504E, f"bad report magic: {w[0]:08X}"
    assert (w[2], w[3]) == (16, 2304), (w[2], w[3])
    assert w[1] == 0, f"stage {w[1]} failed; assembler={w[5]}, submit={w[16]}, wait={w[17]}"
    assert w[4] == w[5] == w[6] == w[7] == w[11] == w[16] == w[17] == w[22] == 0
    assert 0 < w[8] <= 4096, f"QPU bytes: {w[8]}"
    assert w[9] != w[10], f"CSD completion did not advance: {w[9]} -> {w[10]}"
    assert 0 < w[18] < 10_000_000, f"submit+wait microseconds: {w[18]}"
    assert (w[23], w[24]) == (0x3F000000, 0x3F800000)
    print(
        "particle CSD expansion pass: 16 compact records -> 96 ordered "
        f"Vulkan vertices; QPU={w[8]} bytes; submit+wait={w[18]} us; "
        f"CSD completed {w[9]}->{w[10]}; output and guard mismatches=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
