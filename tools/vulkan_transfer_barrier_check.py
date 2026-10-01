"""Check the fixed RAM report from vulkanTransferBarrierProof.pi4.

This checker never accesses the board. Pass the 388-byte report returned by
the Pi 4 RAM diagnostic, or use --self-test for packet/oracle mutations.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

WORDS = 97
MAGIC = 0x31425456
TAIL = 0x56425431
POISON = 0xA5A5A5A5
FILL = 0x11223344


def signed32(word: int) -> int:
    return word if word < 0x80000000 else word - 0x100000000


def expected_source(word: int) -> int:
    if 4 <= word < 8:
        return 0xE1000100 + word
    return FILL if word < 16 else POISON


def expected_destination(word: int) -> int:
    return expected_source(word - 8) if 8 <= word < 24 else POISON


def verify(payload: bytes) -> dict[str, int]:
    if len(payload) != WORDS * 4:
        raise ValueError(f"report length {len(payload)} != {WORDS * 4}")
    r = struct.unpack(f"<{WORDS}I", payload)
    checks = {
        "magic": r[0] == MAGIC,
        "status": r[1] == 0,
        "completed": r[2] == 7,
        "length": r[3] == WORDS * 4,
        "accepted_submit": signed32(r[4]) == 0,
        "bad_barrier_end": signed32(r[5]) == -20004,
        "bad_submit_rejected": signed32(r[6]) != 0,
        "bad_fault_recorded": 1 <= r[7] <= 3,
        "accepted_dma": r[9] == r[8] + 3,
        "accepted_jobs": r[11] == r[10] + 3,
        "accepted_tfu_unchanged": r[13] == r[12],
        "accepted_faults_unchanged": r[15] == r[14],
        "mmu": r[16] == 0,
        "oom": r[17] == 0,
        "native": r[18] == 0,
        "buffer_words": r[19] == 64 and r[20] == 64,
        "guard_words": r[21] == 256,
        "first_bad": r[22] == 0xFFFFFFFF,
        "bounded_runtime": 0 < r[24] < 15_000_000,
        "rejected_dma_unchanged": r[26] == r[25],
        "rejected_jobs_unchanged": r[28] == r[27],
        "allocation": 0 < r[29] <= 4_227_072,
        "source_in_window": 0x063E8000 <= r[30] < 0x067F0000,
        "destination_in_window": 0x063E8000 <= r[31] < 0x067F0000,
        "tail": r[96] == TAIL,
    }
    # The diagnostic captured all 128 bytes of each bound VkBuffer. These
    # comparisons are independent of its on-device vtbExpectedA/B helpers.
    for i in range(32):
        checks[f"source[{i}]"] = r[32 + i] == expected_source(i)
        checks[f"destination[{i}]"] = r[64 + i] == expected_destination(i)
    bad = [name for name, passed in checks.items() if not passed]
    if bad:
        raise ValueError("barrier proof failed: " + ", ".join(bad))
    return {
        "dma_operations": r[9] - r[8],
        "backend_jobs": r[11] - r[10],
        "checked_buffer_words": r[19],
        "checked_guard_words": r[21],
        "runtime_us": r[24],
    }


def synthetic_packet() -> bytes:
    r = [0] * WORDS
    r[0], r[1], r[2], r[3] = MAGIC, 0, 7, WORDS * 4
    r[4], r[5], r[6], r[7] = 0, (-20004) & 0xFFFFFFFF, (-20004) & 0xFFFFFFFF, 2
    r[8], r[9], r[10], r[11] = 4, 7, 9, 12
    r[12], r[13], r[14], r[15] = 1, 1, 0, 0
    r[19], r[20], r[21], r[22] = 64, 64, 256, 0xFFFFFFFF
    r[23], r[24] = 800, 1100
    r[25], r[26], r[27], r[28] = 7, 7, 12, 12
    r[29], r[30], r[31] = 1024, 0x063E9000, 0x063EA000
    for i in range(32):
        r[32 + i] = expected_source(i)
        r[64 + i] = expected_destination(i)
    r[96] = TAIL
    return struct.pack(f"<{WORDS}I", *r)


def self_test() -> None:
    good = bytearray(synthetic_packet())
    verify(good)
    mutations = {
        "source_pixel": (36, 0),
        "destination_gap": (64, 0),
        "destination_copy": (72, 0),
        "guard_count": (21, 255),
        "valid_dma": (9, 6),
        "rejected_dma": (26, 8),
        "invalid_end": (5, 0),
        "runtime": (24, 15_000_000),
        "tail": (96, 0),
    }
    for name, (slot, value) in mutations.items():
        bad = bytearray(good)
        struct.pack_into("<I", bad, slot * 4, value)
        try:
            verify(bad)
        except ValueError:
            continue
        raise AssertionError(f"mutation {name} escaped the checker")
    print(f"PASS: synthetic baseline and {len(mutations)} independent mutations")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, help="388-byte binary RAM report")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.report is not None:
        result = verify(args.report.read_bytes())
        print("PASS:", ", ".join(f"{key}={value}" for key, value in result.items()))
    if not args.self_test and args.report is None:
        parser.error("supply a report or --self-test")


if __name__ == "__main__":
    main()
