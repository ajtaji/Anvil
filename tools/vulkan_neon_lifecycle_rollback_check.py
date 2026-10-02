#!/usr/bin/env python3
"""Check the forced-Init rollback and reinstall RAM proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct


MAGIC = 0x504C564E
TAIL = 0x4E564C50
REPORT_BYTES = 128


def check_report(data: bytes) -> int:
    if len(data) != REPORT_BYTES:
        raise ValueError(f"report has {len(data)} bytes; expected {REPORT_BYTES}")
    words = struct.unpack("<32I", data)
    exact = {
        0: MAGIC,
        1: 0,
        2: 5,
        3: 16,
        4: 0,
        5: 1,
        6: 1,
        7: 0,
        8: 0,
        9: 77,
        10: 0xFFFF0000,
        12: 0,
        13: 0,
        14: 0,
        15: 0,
        30: 0,
        31: TAIL,
    }
    for index, want in exact.items():
        if words[index] != want:
            raise ValueError(f"report[{index}]=0x{words[index]:08X}; expected 0x{want:08X}")
    if words[11] < 4:
        raise ValueError(f"reinstalled widget submitted only {words[11]} draws")
    return len(exact) + 1


def read_run(path: Path) -> bytes:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("failures") != [] or record.get("x0") != record.get("expected_x0"):
        raise ValueError("board run did not return its expected report pointer cleanly")
    trace = record.get("trace")
    if not isinstance(trace, dict) or trace.get("bytes") != REPORT_BYTES:
        raise ValueError("board run lacks a 128-byte report trace")
    return bytes.fromhex(trace.get("hex", ""))


def self_test() -> int:
    words = [0] * 32
    words[0] = MAGIC
    words[2] = 5
    words[3] = 16
    words[5] = 1
    words[6] = 1
    words[9] = 77
    words[10] = 0xFFFF0000
    words[11] = 4
    words[31] = TAIL
    checks = check_report(struct.pack("<32I", *words))
    rejected = 0
    for index, value in ((1, 1), (5, 0), (8, 1), (9, 0), (11, 0), (30, 1)):
        bad = list(words)
        bad[index] = value
        try:
            check_report(struct.pack("<32I", *bad))
        except ValueError:
            rejected += 1
    if rejected != 6:
        raise ValueError("synthetic mutations were accepted")
    return checks + rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--run-json", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        checks = 0
        if args.self_test:
            checks += self_test()
        if args.report:
            checks += check_report(args.report.read_bytes())
        if args.run_json:
            checks += check_report(read_run(args.run_json))
        if not (args.self_test or args.report or args.run_json):
            parser.error("choose --self-test, --report, or --run-json")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"vulkan_neon_lifecycle_rollback_check: FAIL - {exc}")
        return 1
    print(f"vulkan_neon_lifecycle_rollback_check: PASS - {checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
