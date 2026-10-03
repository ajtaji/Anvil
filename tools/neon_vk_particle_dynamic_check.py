"""Validate returning Pi 4 CPU/CSD dynamic 10k particle reports."""

import argparse
from pathlib import Path
import statistics
import struct
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "RaspberryPi4/Examples/Diagnostics"))
from vulkanNeonParticleMatchedProfileCheck import validate as validate_matched  # noqa: E402


MAGIC = 0x44594E50
GREEN = 0xFF00FF00
BLACK = 0xFF000000


def validate(payload: bytes) -> tuple[int, ...]:
    if len(payload) != 512:
        raise ValueError(f"expected 512 report bytes, got {len(payload)}")
    # The first 64 words retain the matched GPU, fault, count, timing,
    # pixel, and teardown contract; their final probes use the moved grid.
    validate_matched(payload[:256])
    words = struct.unpack("<128I", payload)
    if words[64:67] != (MAGIC, 1, 4) or words[127] != words[63]:
        raise ValueError("dynamic marker, version, frame count, or tail mismatch")
    if words[68:72] != (0, 1, 2, 3):
        raise ValueError(f"wrong per-frame motion offsets: {words[68:72]}")
    for frame in range(4):
        if words[72 + frame] != 0 or words[76 + frame] != 10_000:
            raise ValueError(f"frame {frame}: moved-grid mismatch or incomplete oracle")
        if (words[80 + frame], words[84 + frame], words[88 + frame]) != (GREEN, BLACK, GREEN):
            raise ValueError(f"frame {frame}: leading-edge, vacated-edge, or far-corner pixel mismatch")
        if not (0 < words[92 + frame] < 10_000_000):
            raise ValueError(f"frame {frame}: invalid pixel-check duration")
        if not (0 < words[100 + frame] < 10_000_000):
            raise ValueError(f"frame {frame}: invalid motion-update duration")
    return words


def describe(words: tuple[int, ...]) -> str:
    mode = "CSD" if words[0] == 0x474D504E else "CPU"
    median = lambda start: int(statistics.median(words[start:start + 3]))
    return (f"{mode}: four moving frames passed 10k-cell pixel checks; "
            f"frame median {median(43)} us, Prepare {median(16)} us, "
            f"Draw {median(19)} us, End {median(22)} us")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    if len(args.reports) not in (1, 2):
        parser.error("provide one report or matched CPU and CSD reports")
    reports = [validate(path.read_bytes()) for path in args.reports]
    for words in reports:
        print(describe(words))
    if len(reports) == 2:
        if {words[0] for words in reports} != {0x434D504E, 0x474D504E}:
            raise ValueError("comparison requires one CPU and one CSD report")
        cpu = next(words for words in reports if words[0] == 0x434D504E)
        csd = next(words for words in reports if words[0] == 0x474D504E)
        print("matched frame median CSD minus CPU: "
              f"{int(statistics.median(csd[43:46])) - int(statistics.median(cpu[43:46]))} us")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
