"""Validate and compare the matched Pi 4 CPU/CSD 10k particle reports."""

import statistics
import struct
import sys
from pathlib import Path

CPU_MAGIC, CPU_TAIL = 0x434D504E, 0x4E504D43
CSD_MAGIC, CSD_TAIL = 0x474D504E, 0x4E504D47
WINDOW, WINDOW_BYTES = 0x063E8000, 0x01000000
OUTPUT_BYTES = ((10_000 * 6 * 24 + 4095) // 4096 + 1) * 4096


def validate(payload: bytes) -> tuple[int, ...]:
    if len(payload) != 256:
        raise ValueError(f"expected 256 report bytes, got {len(payload)}")
    w = struct.unpack("<64I", payload)
    assert (w[0], w[63]) in ((CPU_MAGIC, CPU_TAIL), (CSD_MAGIC, CSD_TAIL)), "wrong report markers"
    mode = "CSD" if w[0] == CSD_MAGIC else "CPU"
    assert w[1] == 0, (
        f"{mode} stage {w[1]} failed at phase {w[2]}, Chrome/module create {w[3]}/{w[9]}, "
        f"Prepare/Draw/End {w[11:14]}, frames {w[8]}, unsafe {w[55]}, faults {w[56:58]}"
    )
    assert w[2] == 4, f"incomplete {mode} phase: {w[2]}"
    assert all(w[i] == 0 for i in (3, 9, 11, 12, 13, 30, 33, 52, 53, 55, 56, 58, 59, 60)), (
        f"unexpected {mode} report flags"
    )
    assert (w[6], w[7], w[8], w[31], w[32], w[46], w[47], w[54]) == (
        10_000, 3, 4, 4, 4, WINDOW, WINDOW_BYTES, 1
    )
    assert w[5] >= 3200 and w[5] % 4 == 0
    assert w[4] % 4096 == 0 and WINDOW <= w[4] and w[4] + w[5] * 800 <= WINDOW + WINDOW_BYTES
    assert (w[25], w[26], w[27], w[28], w[29]) == (0xFF000000,) + (0xFF00FF00,) * 4
    assert 0 < w[14] <= 11_000_000, f"pixel deadline exceeded: {w[14]} us"
    assert w[14] <= w[15] <= 14_000_000, f"teardown deadline exceeded: {w[15]} us"
    for prep, draw, end, total in zip(w[16:19], w[19:22], w[22:25], w[43:46]):
        assert min(prep, draw, end) > 0 and prep + draw + end <= total <= 10_000_000
    if mode == "CSD":
        assert 0 < w[10] <= 4096
        assert w[49] == OUTPUT_BYTES and w[48] % 4096 == 0
        assert WINDOW <= w[48] and w[48] + w[49] <= WINDOW + WINDOW_BYTES
        assert w[48] + w[49] <= w[4] or w[4] + w[5] * 800 <= w[48]
        assert all(0 < x <= 1_000_000 for x in w[34:37]), f"CSD timings {w[34:37]}"
        assert all(x > 0 for x in w[37:43]), f"stage/palette timings {w[37:43]}"
    else:
        assert w[10] == 0 and w[48] == 0 and w[49] == 0
        assert all(x == 0 for x in w[34:43])
    return w


def median_us(w: tuple[int, ...], start: int) -> int:
    return int(statistics.median(w[start:start + 3]))


def describe(w: tuple[int, ...]) -> str:
    mode = "CSD" if w[0] == CSD_MAGIC else "CPU"
    parts = [
        f"{mode}: frame median {median_us(w, 43)} us",
        f"Prepare {median_us(w, 16)} us",
        f"Draw {median_us(w, 19)} us",
        f"End {median_us(w, 22)} us",
    ]
    if mode == "CSD":
        parts.extend((f"palette {median_us(w, 40)} us", f"stage {median_us(w, 37)} us",
                      f"CSD {median_us(w, 34)} us"))
    parts.append(f"through pixels {w[14]} us, including teardown {w[15]} us")
    return ", ".join(parts)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: vulkanNeonParticleMatchedProfileCheck.py REPORT.BIN [OTHER_REPORT.BIN]")
        return 2
    reports = [validate(Path(name).read_bytes()) for name in sys.argv[1:]]
    for w in reports:
        print(describe(w))
    if len(reports) == 2:
        assert {reports[0][0], reports[1][0]} == {CPU_MAGIC, CSD_MAGIC}, "need one CPU and one CSD report"
        cpu = next(w for w in reports if w[0] == CPU_MAGIC)
        csd = next(w for w in reports if w[0] == CSD_MAGIC)
        print(f"matched frame median CSD minus CPU: {median_us(csd, 43) - median_us(cpu, 43)} us")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
