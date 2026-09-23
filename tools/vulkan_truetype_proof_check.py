#!/usr/bin/env python3
"""Check the returning Vulkan TrueType proof report and captured screenshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vulkan_neon_widget_proof_check as png  # noqa: E402

REPORT_BYTES = 111 * 4
TAIL = 0x4E565741


def fail(message: str) -> None:
    raise SystemExit(f"vulkan_truetype_proof_check: FAIL - {message}")


def report_bytes(path: Path) -> tuple[int, ...]:
    record = json.loads(path.read_text(encoding="utf-8"))
    trace = record.get("trace")
    if not isinstance(trace, dict) or trace.get("bytes") != REPORT_BYTES:
        fail(f"return trace must contain {REPORT_BYTES} bytes")
    if record.get("failures") != [] or record.get("x0") != record.get("expected_x0"):
        fail("board_run reports a failure or unexpected return value")
    try:
        data = bytes.fromhex(trace.get("hex", ""))
    except ValueError:
        fail("trace hex is invalid")
    if len(data) != REPORT_BYTES:
        fail(f"trace decoded to {len(data)} bytes")
    return struct.unpack("<111I", data)


def check_report(words: tuple[int, ...]) -> int:
    exact = {
        0: 0x4157564E, 1: 0, 2: 8, 3: REPORT_BYTES,
        24: 4, 25: 168, 26: 4, 27: 168,
        28: 1, 29: 3, 30: 27, 31: 0,
        32: 1, 33: 0, 34: 0, 35: 0, 36: 0, 37: 1,
        38: 12, 51: 0, 53: 1,
        62: 24, 63: 3, 64: 0, 65: 0, 66: 30, 67: 35220,
        71: 5, 72: 0, 73: 0, 74: 10, 75: 10, 76: 10, 77: 1, 78: 0,
        79: 0, 80: 2048, 81: 10, 82: 1, 84: 1,
        85: 4, 86: 0, 87: 0, 89: 0, 90: 0, 110: TAIL,
    }
    for index, expected in exact.items():
        if words[index] != expected:
            fail(f"report[{index}]={words[index]}, expected {expected}")
    for index in (68, 69, 70):
        if words[index] < 1:
            fail(f"report[{index}] shows no rendered TrueType coverage")
    for index in range(4, 17):
        if words[index] == 0:
            fail(f"public Vulkan object {index} is zero")
    if words[15] < 800 * 1280 * 4 or words[16] != 3200:
        fail("attachment size or row pitch is invalid")
    return len(exact) + 3 + 13 + 2


def check_screenshot(path: Path) -> int:
    width, height, rows = png.decode_png(path)
    if (width, height) != (1280, 800):
        fail(f"screenshot is {width}x{height}, expected 1280x800")
    regions = (
        (40, 135, 360, 205, "16px"),
        (40, 205, 420, 320, "24px"),
        (40, 310, 560, 470, "40px"),
    )
    # The image is rotated by board_run from physical (x,y) to logical (y,799-x).
    # Compare each glyph region with a known background point; count colored
    # antialias pixels without depending on a particular screenshot encoder.
    ref_x, ref_y = 2, 2
    ref = tuple(rows[(800 - 1) - ref_x][ref_y * 3:ref_y * 3 + 3])
    checks = 0
    for x0, y0, x1, y1, label in regions:
        changed = 0
        for y in range(y0, y1):
            for x in range(x0, x1):
                lx, ly = y, (800 - 1) - x
                pixel = tuple(rows[ly][lx * 3:lx * 3 + 3])
                if pixel != ref:
                    changed += 1
        if changed < 8:
            fail(f"screenshot has too few non-background pixels in {label} specimen")
        checks += 1
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-json", required=True, type=Path)
    ap.add_argument("--png", required=True, type=Path)
    args = ap.parse_args()
    words = report_bytes(args.run_json)
    checks = check_report(words) + check_screenshot(args.png)
    print(f"vulkan_truetype_proof_check: PASS - {checks} report and screenshot checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
