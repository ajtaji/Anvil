"""Check the returning Pi 4 10k CSD-to-live-VkBuffer report."""

import struct
import sys
from pathlib import Path

MAGIC = 0x4256434E
TAIL = 0x4E435642
WINDOW = 0x063E8000
WINDOW_BYTES = 0x01000000
PAGE = 4096
ITEMS = 10_000
INPUT_LIVE = ITEMS * 32
INPUT_ALLOC = ((INPUT_LIVE + PAGE - 1) // PAGE + 1) * PAGE
OUTPUT_LIVE = ITEMS * 6 * 24
OUTPUT_ALLOC = ((OUTPUT_LIVE + PAGE - 1) // PAGE + 1) * PAGE
IMAGE_W = IMAGE_H = 800


def inside(base: int, size: int) -> bool:
    return WINDOW <= base <= 0xFFFFFFFF and size > 0 and base + size <= WINDOW + WINDOW_BYTES


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticleCsdVkBuffer10kProofCheck.py REPORT.BIN")
        return 2
    payload = Path(sys.argv[1]).read_bytes()
    if len(payload) != 256:
        raise ValueError(f"expected 256 report bytes, got {len(payload)}")
    w = struct.unpack("<64I", payload)
    assert (w[0], w[63]) == (MAGIC, TAIL), "wrong report markers"
    assert w[1] == 0, (
        f"stage {w[1]} failed: phase={w[2]}, CSD submit/wait/clean={w[11:14]}, "
        f"Vulkan begin/draw/end={w[22:25]}, vertex/guard/input mismatches={w[16:19]}, "
        f"first vertex mismatch={w[19:22]}, MMU={w[34:37]}, "
        f"allocation result={w[42]:08X}, unsafe={w[55]}"
    )
    assert w[2] == 5
    assert all(w[i] == 0 for i in (3, 9, 11, 12, 13, 16, 17, 18, 19, 22, 23, 24, 30, 33, 50, 51, 52, 53, 55, 56, 58, 59, 60))
    assert w[54] == 1, f"bitmap atlas was not ready: font={w[52]}, raster={w[53]}, ready={w[54]}"
    assert (w[5], w[37], w[46], w[47]) == (
        OUTPUT_ALLOC, INPUT_ALLOC, WINDOW, WINDOW_BYTES
    )
    assert w[45] >= IMAGE_W * 4 and w[45] % 4 == 0
    assert 0 < w[10] <= PAGE, f"QPU bytes: {w[10]}"
    assert w[14] != w[15], f"CSD completion did not advance: {w[14]} -> {w[15]}"
    assert 0 < w[48] < 2_000_000 and 0 < w[49] < 10_000_000
    assert 0 < w[41] <= 7_000_000, f"setup {w[41]} us"
    assert 0 < w[43] < 7_000_000, f"staging {w[43]} us"
    assert 0 < w[61] < 10_000_000, f"byte oracle {w[61]} us"
    assert 0 < w[62] < 10_000_000, f"draw recording {w[62]} us"
    assert w[41] + w[48] + w[61] <= 10_000_000, "validation passed 10s budget"
    assert w[41] + w[48] + w[61] + w[62] + w[49] <= 12_000_000, "draw passed 12s budget"
    assert 0 < w[40] <= 13_000_000, f"total through pixels {w[40]} us"
    assert (w[31], w[32], w[38], w[39]) == (1, 1, 1, ITEMS * 6)
    assert (w[25], w[26], w[27], w[28], w[29]) == (
        0xFF000000, 0xFF00FF00, 0xFF00FF00, 0xFF00FF00, 0xFF00FF00
    )
    assert w[42] == 0x3F7B851F, f"last-group vertex sample {w[42]:08X}"
    sizes = ((4, OUTPUT_ALLOC), (6, PAGE), (7, PAGE),
             (8, INPUT_ALLOC), (44, w[45] * IMAGE_H))
    for i, size in sizes:
        assert inside(w[i], size), f"address out of mapped window at report word {i}: {w[i]:08X}"
        assert w[i] % PAGE == 0, f"unaligned allocation at report word {i}: {w[i]:08X}"
    regions = [(w[i], w[i] + size) for i, size in sizes]
    assert all(a[1] <= b[0] or b[1] <= a[0] for pos, a in enumerate(regions) for b in regions[pos + 1:])
    print(
        "CSD-to-VkBuffer 10k pass: 625 groups wrote 60,000 vertices into "
        f"a live bound buffer at 0x{w[4]:08X}; exact bytes/guards and "
        f"20,000 pixel probes passed; setup {w[41]} us "
        f"(staging {w[43]} us), CSD {w[48]} us, "
        f"byte oracle {w[61]} us, draw record {w[62]} us, "
        f"Vulkan end {w[49]} us; total through pixels {w[40]} us"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
