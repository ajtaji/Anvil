#!/usr/bin/env python3
"""Check the offscreen Vulkan grid-glyph width-fit and baseline proof."""

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
    exact = {0: MAGIC, 1: 0, 2: 5, 13: 0, 14: 0, 27: 0, 28: 0,
             29: 0, 30: 0, 31: TAIL}
    for index, want in exact.items():
        if words[index] != want:
            raise ValueError(f"report[{index}]=0x{words[index]:08X}; expected 0x{want:08X}")
    glyph_w, glyph_h, narrow_w, wide_w = words[3:7]
    narrow_top, narrow_bottom, wide_top, wide_bottom = words[7:11]
    narrow_pixels, wide_pixels = words[11:13]
    if not (3 <= narrow_w < glyph_w < wide_w <= 30):
        raise ValueError("fixture did not exercise horizontal compression and an unscaled cell")
    if not (4 <= glyph_h <= 28):
        raise ValueError("fixture glyph height is outside the proof cell")
    if not (2 <= narrow_top <= narrow_bottom < 30):
        raise ValueError("narrow glyph has invalid vertical bounds")
    if (narrow_top, narrow_bottom) != (wide_top, wide_bottom):
        raise ValueError("horizontal fitting changed glyph height or baseline")
    if narrow_pixels < 1 or wide_pixels < 1:
        raise ValueError("glyphs are absent from GPU readback")
    if narrow_bottom - narrow_top + 1 < 4:
        raise ValueError("rendered cap height is unexpectedly small")
    return len(exact) + 6


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
    words[0], words[2], words[31] = MAGIC, 5, TAIL
    words[3:13] = [18, 20, 9, 22, 4, 22, 4, 22, 90, 160]
    checks = check_report(struct.pack("<32I", *words))
    rejected = 0
    for index, value in ((1, 1), (5, 18), (9, 6), (11, 0), (13, 1)):
        altered = list(words)
        altered[index] = value
        try:
            check_report(struct.pack("<32I", *altered))
        except ValueError:
            rejected += 1
    if rejected != 5:
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
        print(f"vulkan_neon_grid_height_check: FAIL - {exc}")
        return 1
    print(f"vulkan_neon_grid_height_check: PASS - {checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
