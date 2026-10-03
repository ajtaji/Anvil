"""Check the returning Pi 4 10k production-module profile report."""

import struct
import sys
from pathlib import Path

MAGIC = 0x4B43564E
TAIL = 0x4E56434B
WINDOW = 0x063E8000
WINDOW_BYTES = 0x01000000
PAGE = 4096
ITEMS = 10_000
INPUT_LIVE = ITEMS * 48
INPUT_ALLOC = ((INPUT_LIVE + PAGE - 1) // PAGE + 1) * PAGE
OUTPUT_LIVE = ITEMS * 6 * 24
OUTPUT_ALLOC = ((OUTPUT_LIVE + PAGE - 1) // PAGE + 1) * PAGE


def inside(base: int, size: int) -> bool:
    return WINDOW <= base <= 0xFFFFFFFF and size > 0 and base + size <= WINDOW + WINDOW_BYTES


def validate(payload: bytes) -> tuple[int, ...]:
    if len(payload) != 256:
        raise ValueError(f"expected 256 report bytes, got {len(payload)}")
    w = struct.unpack("<64I", payload)
    assert (w[0], w[63]) == (MAGIC, TAIL), "wrong profile report markers"
    assert w[1] == 0, (
        f"stage {w[1]} failed: phase={w[2]}, Chrome/module create={w[3]}/{w[9]}, "
        f"Prepare/CSD={w[11:14]}, Vulkan begin/draw/end={w[22:25]}, "
        f"vertex/guard/input mismatches={w[16:19]}, MMU={w[34:37]}, unsafe={w[55]}"
    )
    assert w[2] == 5
    zero = (3, 9, 11, 12, 13, 16, 17, 18, 22, 23, 24, 30, 33,
            50, 51, 52, 53, 55, 56, 58, 59, 60)
    assert all(w[i] == 0 for i in zero), {i: w[i] for i in zero if w[i]}
    assert w[54] == 1, f"bitmap atlas was not ready: {w[52:55]}"
    assert (w[5], w[37], w[46], w[47]) == (
        OUTPUT_ALLOC, INPUT_ALLOC, WINDOW, WINDOW_BYTES
    )
    assert w[45] >= 800 * 4 and w[45] % 4 == 0
    assert 0 < w[10] <= PAGE, f"QPU bytes: {w[10]}"
    assert w[14] != w[15], f"CSD completion did not advance: {w[14]} -> {w[15]}"
    assert 0 < w[41] <= 7_000_000, f"setup exceeded budget: {w[41]} us"
    assert 0 < w[43] < 7_000_000, f"module Prepare took {w[43]} us"
    assert 0 < w[19] <= w[43] and 0 < w[20] <= w[43], f"palette/stage {w[19:21]}"
    assert 0 < w[48] <= 1_000_000, f"CSD exceeded wait bound: {w[48]} us"
    assert 0 < w[61] < 3_000_000, f"sample/guard check took {w[61]} us"
    assert 0 < w[62] < 3_000_000, f"draw recording took {w[62]} us"
    assert 0 < w[49] < 10_000_000, f"Vulkan End took {w[49]} us"
    assert 0 < w[40] <= 13_000_000, f"total to pixel oracle: {w[40]} us"
    assert (w[31], w[32], w[38], w[39]) == (1, 1, 1, ITEMS * 6)
    assert (w[25], w[26], w[27], w[28], w[29]) == (0xFF000000,) + (0xFF00FF00,) * 4
    assert w[42] == 0x3F7B851F, f"last-group vertex sample {w[42]:08X}"
    sizes = ((4, OUTPUT_ALLOC), (6, PAGE), (7, PAGE),
             (8, INPUT_ALLOC), (44, w[45] * 800))
    for i, size in sizes:
        assert inside(w[i], size), f"address outside window at word {i}: {w[i]:08X}"
        assert w[i] % PAGE == 0, f"unaligned allocation at word {i}: {w[i]:08X}"
    regions = [(w[i], w[i] + size) for i, size in sizes]
    assert all(a[1] <= b[0] or b[1] <= a[0]
               for pos, a in enumerate(regions) for b in regions[pos + 1:])
    return w


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticleCsdModule10kProfileCheck.py REPORT.BIN")
        return 2
    w = validate(Path(sys.argv[1]).read_bytes())
    print(
        "production-module 10k profile pass: 625 groups wrote 60,000 vertices "
        "to a live VkBuffer; 6 sampled records, output/input guards and 20,000 pixel probes passed; "
        f"setup {w[41]} us, Prepare {w[43]} us "
        f"(palette {w[19]}, stage {w[20]}, CSD {w[48]}), "
        f"sample/guard {w[61]}, draw record {w[62]}, Vulkan End {w[49]}, "
        f"total to pixels {w[40]} us"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
