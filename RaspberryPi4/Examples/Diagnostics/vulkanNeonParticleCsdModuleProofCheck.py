"""Check the Pi 4 production-module small offscreen proof report."""

import struct
import sys
from pathlib import Path

MAGIC = 0x4D43564E
TAIL = 0x4E56434D
WINDOW = 0x063E8000
WINDOW_BYTES = 0x00C00000
PAGE = 4096
ITEMS = 32
VERTEX_BYTES = 24
LIVE_BYTES = ITEMS * 6 * VERTEX_BYTES
OUTPUT_BYTES = 3 * PAGE
INPUT_BYTES = ITEMS * 48


def inside(base: int, size: int) -> bool:
    return WINDOW <= base <= 0xFFFFFFFF and size > 0 and base + size <= WINDOW + WINDOW_BYTES


def colour(item: int) -> int:
    return (
        0xFF000000
        | (((item * 67 + 31) & 255) << 16)
        | (((item * 43 + 59) & 255) << 8)
        | ((item * 29 + 97) & 255)
    )


def validate(payload: bytes) -> tuple[int, ...]:
    if len(payload) != 256:
        raise ValueError(f"expected 256 report bytes, got {len(payload)}")
    w = struct.unpack("<64I", payload)
    assert (w[0], w[63]) == (MAGIC, TAIL), "wrong module report markers"
    assert w[1] == 0, (
        f"stage {w[1]} failed: phase={w[2]}, create/prepare={w[9]}/{w[11]}, "
        f"CSD submit/wait/clean={w[11:14]}, Vulkan begin/draw/end={w[22:25]}, "
        f"vertex/guard/input mismatches={w[16:19]}, "
        f"first vertex mismatch={w[19:22]}, MMU={w[34:37]}, unsafe={w[55]}"
    )
    assert w[2] == 5
    zero = (3, 9, 11, 12, 13, 16, 17, 18, 19, 22, 23, 24, 30, 33,
            50, 51, 52, 53, 55, 56, 58, 59, 60)
    assert all(w[i] == 0 for i in zero), {i: w[i] for i in zero if w[i]}
    assert w[54] == 1, f"bitmap atlas was not ready: {w[52:55]}"
    assert (w[5], w[45], w[46], w[47]) == (OUTPUT_BYTES, 512, WINDOW, WINDOW_BYTES)
    assert 0 < w[10] <= PAGE, f"QPU bytes: {w[10]}"
    assert w[14] != w[15], f"CSD completion did not advance: {w[14]} -> {w[15]}"
    assert 0 < w[37] <= 7_000_000, f"setup exceeded budget: {w[37]} us"
    assert 0 < w[43] < 7_000_000, f"module Prepare took {w[43]} us"
    assert 0 < w[48] <= 1_000_000, f"CSD exceeded wait bound: {w[48]} us"
    assert 0 < w[61] < 3_000_000, f"byte validation took {w[61]} us"
    assert 0 < w[49] < 10_000_000, f"Vulkan End took {w[49]} us"
    assert 0 < w[62] <= 13_000_000, f"total to pixel oracle: {w[62]} us"
    assert (w[31], w[32], w[38], w[39]) == (1, 1, 1, ITEMS * 6)
    assert (w[25], w[26], w[27], w[28], w[29]) == (
        0xFF000000, colour(0), colour(1), colour(2), colour(3)
    )
    assert (w[40], w[41], w[42]) == (0xBF580000, 0x3F800000, 0x3D800000)
    for i, size in ((4, OUTPUT_BYTES), (6, PAGE), (7, PAGE),
                    (8, 2 * PAGE), (44, 128 * 128 * 4)):
        assert inside(w[i], size), f"address outside mapped window at word {i}: {w[i]:08X}"
        assert w[i] % PAGE == 0, f"unaligned allocation at word {i}: {w[i]:08X}"
    regions = [(w[i], w[i] + size) for i, size in
               ((4, OUTPUT_BYTES), (6, PAGE), (7, PAGE),
                (8, 2 * PAGE), (44, 128 * 128 * 4))]
    assert all(a[1] <= b[0] or b[1] <= a[0]
               for pos, a in enumerate(regions) for b in regions[pos + 1:])
    assert LIVE_BYTES == 4608 and INPUT_BYTES == 1536
    return w


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: vulkanNeonParticleCsdModuleProofCheck.py REPORT.BIN")
        return 2
    w = validate(Path(sys.argv[1]).read_bytes())
    print(
        "production-module CSD-to-VkBuffer pass: two groups wrote 192 exact Chrome vertices; "
        "32 compact inputs, output guards, input tail and 69 pixel probes passed; "
        f"setup {w[37]} us, module Prepare {w[43]} us, CSD {w[48]} us, "
        f"byte validation {w[61]} us, "
        f"Vulkan End {w[49]} us, total to pixels {w[62]} us"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
