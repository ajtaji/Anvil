"""Check a 768-byte matched CSD backend split report."""

import argparse
from pathlib import Path
import statistics
import struct

from neon_vk_particle_end_split_check import check as check_end_split


def check(data: bytes) -> str:
    if len(data) != 768:
        raise ValueError(f"expected 768 report bytes, got {len(data)}")
    # The first 512 bytes retain the End split and full matched pixel oracle.
    check_end_split(data[:512])
    words = struct.unpack("<192I", data)
    if words[128:131] != (0x4253504E, 1, 3) or words[191] != 0x4E504D47:
        raise ValueError("backend split magic, version, count, or tail mismatch")
    phase_bases = (131, 134, 137, 140, 143, 146, 149, 152, 155, 158)
    for sample in range(3):
        total, pre, cache, target, target_coord, begin, emit, end, restore, restore_coord = (
            words[base + sample] for base in phase_bases
        )
        if not all(0 <= value < 10_000_000 for value in
                   (total, pre, cache, target, target_coord, begin, emit, end, restore, restore_coord)):
            raise ValueError(f"sample {sample}: backend timing out of range")
        if not all(value > 0 for value in (total, pre, target, target_coord, begin, end, restore, restore_coord)):
            raise ValueError(f"sample {sample}: backend phase missing")
        if words[161 + sample] != 1 or words[164 + sample] != 1:
            raise ValueError(f"sample {sample}: expected one coordinate-table rebuild per rebind")
        if target_coord > target + 100 or restore_coord > restore + 100:
            raise ValueError(f"sample {sample}: table rebuild exceeds enclosing rebind")
        if pre + cache + target + begin + emit + end + restore > total + 200:
            raise ValueError(f"sample {sample}: backend phases exceed backend total")
        if total > words[73 + sample] + 200:
            raise ValueError(f"sample {sample}: backend total exceeds queue submit")
    warm = words[167:179]
    if len(warm) != 12 or warm[10:] != (1, 1) or not all(warm[index] > 0 for index in (0, 1, 3, 4, 5, 7, 8, 9)):
        raise ValueError("warm-up backend split missing")
    if sum(warm[index] for index in (1, 2, 3, 5, 6, 7, 8)) > warm[0] + 200:
        raise ValueError("warm-up backend phases exceed total")
    median = lambda start: int(statistics.median(words[start:start + 3]))
    values = {
        "backend_total_us": median(131),
        "preframe_us": median(134),
        "cache_us": median(137),
        "target_rebind_us": median(140),
        "target_coord_us": median(143),
        "frame_begin_us": median(146),
        "draw_emit_us": median(149),
        "frame_end_us": median(152),
        "restore_rebind_us": median(155),
        "restore_coord_us": median(158),
    }
    return "PASS: matched 800x800 CSD backend split; " + ", ".join(f"{name}={value}" for name, value in values.items())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    print(check(args.report.read_bytes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
