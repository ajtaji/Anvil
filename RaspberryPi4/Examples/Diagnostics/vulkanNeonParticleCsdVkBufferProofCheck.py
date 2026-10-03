"""Check the returning Pi 4 CSD-to-live-VkBuffer proof report."""

import struct
import sys
from pathlib import Path

MAGIC = 0x4256434E
TAIL = 0x4E435642
WINDOW = 0x063E8000
WINDOW_BYTES = 0x00C00000
PAGE = 4096


def inside(base: int, size: int) -> bool:
    return WINDOW <= base <= 0xFFFFFFFF and size > 0 and base + size <= WINDOW + WINDOW_BYTES


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticleCsdVkBufferProofCheck.py REPORT.BIN")
        return 2
    payload = Path(sys.argv[1]).read_bytes()
    if len(payload) != 256:
        raise ValueError(f"expected 256 report bytes, got {len(payload)}")
    w = struct.unpack("<64I", payload)
    assert (w[0], w[63]) == (MAGIC, TAIL), "wrong report markers"
    assert w[1] == 0, (
        f"stage {w[1]} failed: phase={w[2]}, CSD submit/wait/clean={w[11:14]}, "
        f"Vulkan begin/draw/end={w[22:25]}, vertex/guard/input mismatches={w[16:19]}, "
        f"first vertex mismatch={w[19:22]}, MMU={w[34:37]}, unsafe={w[55]}"
    )
    assert w[2] == 5
    assert all(w[i] == 0 for i in (3, 9, 11, 12, 13, 16, 17, 18, 19, 22, 23, 24, 30, 33, 50, 51, 52, 53, 55, 56, 58, 59, 60))
    assert w[54] == 1, f"bitmap atlas was not ready: font={w[52]}, raster={w[53]}, ready={w[54]}"
    assert (w[5], w[45], w[46], w[47]) == (8192, 256, WINDOW, WINDOW_BYTES)
    assert 0 < w[10] <= PAGE, f"QPU bytes: {w[10]}"
    assert w[14] != w[15], f"CSD completion did not advance: {w[14]} -> {w[15]}"
    assert 0 < w[48] < 1_000_000 and 0 < w[49] < 10_000_000
    assert (w[31], w[32], w[38], w[39]) == (1, 1, 1, 192)
    assert (w[25], w[26], w[27], w[28], w[29]) == (
        0xFF000000, 0xFF00FF00, 0xFF00FF00, 0xFF00FF00, 0xFF00FF00
    )
    assert (w[40], w[41], w[42]) == (0xBF600000, 0x3F800000, 0x3D800000)
    for i, size in ((4, 8192), (6, PAGE), (7, PAGE), (8, PAGE), (44, 64 * 64 * 4)):
        assert inside(w[i], size), f"address out of mapped window at report word {i}: {w[i]:08X}"
        assert w[i] % PAGE == 0, f"unaligned allocation at report word {i}: {w[i]:08X}"
    regions = [(w[i], w[i] + size) for i, size in ((4, 8192), (6, PAGE), (7, PAGE), (8, PAGE), (44, 64 * 64 * 4))]
    assert all(a[1] <= b[0] or b[1] <= a[0] for pos, a in enumerate(regions) for b in regions[pos + 1:])
    print(
        "CSD-to-VkBuffer pass: two groups wrote 192 vertices into a live bound "
        f"buffer at 0x{w[4]:08X}; exact bytes/guards and 64 pixel probes passed; "
        f"CSD {w[48]} us, Vulkan {w[49]} us"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
