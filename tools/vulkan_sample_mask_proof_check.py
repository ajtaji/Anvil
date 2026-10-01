#!/usr/bin/env python3
"""Check the bounded Pi 4 public-draw zero-sample-mask RAM proof."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanSampleMaskProof.pi4"
CLEAR = 0xFF3380B2
RED = 0xFFFF0000
BLUE = 0xFF0000FF


def check_source(source: str) -> list[str]:
    required = (
        ("zero mask word", "Define sampleMaskZero.l = 0"),
        ("zero-mask pipeline", "ms\\pSampleMask = @sampleMaskZero"),
        ("normal pipeline restored", "ms\\pSampleMask = 0"),
        ("red draw", "vkCmdDraw(cmd, 6, 1, 0, 0)"),
        ("blue draw", "vkCmdDraw(cmd, 6, 1, 6, 0)"),
        ("full-image oracle", "For y = 0 To 63\n    For x = 0 To 63"),
        ("red region", "If x >= 8 And x < 56 And y >= 8 And y < 56"),
        ("blue region", "If x >= 24 And x < 32 And y >= 24 And y < 32"),
        ("closed three-draw list", "vtpGet(52) <> 3"),
        ("two emitted primitives", "vtpGet(14) <> 2"),
    )
    errors = [label for label, token in required if token not in source]
    if source.count("vkCmdDraw(cmd, 6, 1, 0, 0)") != 2:
        errors.append("two outer draws")
    if source.count("vkCmdDraw(cmd, 6, 1, 6, 0)") != 1:
        errors.append("one inner draw")
    if "vkCmdClearAttachments(" in source:
        errors.append("unexpected attachment clear command")
    for forbidden in ("PokeL(imgBase", "PokeA(imgBase", "DisplayBlit(", "DisplayDmaFill("):
        if forbidden in source:
            errors.append("CPU or display fallback: " + forbidden)
    return errors


def check_report(data: bytes) -> list[str]:
    if len(data) != 256:
        return [f"report length {len(data)} != 256"]
    r = struct.unpack("<64I", data)
    expected = {
        0: 0x564B444C, 1: 0, 14: 2, 17: 4096, 18: 0,
        19: 0xFFFFFFFF, 22: 0, 23: 0, 40: 0, 41: 0,
        42: 0, 47: 0, 48: 0, 52: 3, 58: 1, 61: 8,
        62: 256, 63: 0x4C444B56,
        12: CLEAR, 13: CLEAR, 53: RED, 54: RED,
        55: RED, 56: RED, 59: RED, 60: BLUE,
    }
    errors = [f"slot {slot}: {r[slot]:#x} != {want:#x}"
              for slot, want in expected.items() if r[slot] != want]
    for before, after, label, count in ((24, 25, "bin", 1),
                                        (26, 27, "render", 1),
                                        (38, 39, "public draws", 3)):
        if r[after] - r[before] != count:
            errors.append(f"{label} delta is not {count}")
    if r[32] != r[33] or r[34] != r[35]:
        errors.append("surface/window guard changed")
    if r[43] != r[44] or r[43] != 0:
        errors.append("Vulkan fault count changed")
    if r[49] & 0xFFFFEFFF or r[50] & 0xFFFFEFFF:
        errors.append("V3D error status contains a nonbenign bit")
    if r[36] < 256 or r[37] < 16384 or r[36] * 64 != r[37]:
        errors.append("image pitch/span invalid")
    return errors


def self_test(source: str) -> None:
    assert not check_source(source)
    r = [0] * 64
    fields = {0: 0x564B444C, 14: 2, 17: 4096, 19: 0xFFFFFFFF,
              52: 3, 58: 1, 61: 8, 62: 256, 63: 0x4C444B56,
              12: CLEAR, 13: CLEAR, 53: RED, 54: RED, 55: RED,
              56: RED, 59: RED, 60: BLUE, 24: 3, 25: 4,
              26: 3, 27: 4, 38: 5, 39: 8, 32: 123,
              33: 123, 34: 456, 35: 456, 36: 256, 37: 16384}
    for slot, value in fields.items(): r[slot] = value
    report = lambda: struct.pack("<64I", *r)
    assert not check_report(report())
    mutants = ((14, 3), (17, 4095), (18, 1), (25, 3),
               (32, 0), (39, 7), (47, 1), (52, 2),
               (53, BLUE), (60, RED), (63, 0))
    for slot, bad in mutants:
        old = r[slot]; r[slot] = bad
        assert check_report(report()), f"uncaught report mutation {slot}"
        r[slot] = old
    assert check_source(source.replace("sampleMaskZero.l = 0", "sampleMaskZero.l = 1"))
    assert check_source(source.replace("ms\\pSampleMask = @sampleMaskZero", "ms\\pSampleMask = 0"))
    assert check_source(source + "\nPokeL(imgBase, 0)\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = SOURCE.read_text(encoding="utf-8-sig")
    errors = check_source(source)
    if args.self_test:
        self_test(source)
    if args.report:
        errors += check_report(args.report.read_bytes())
    if errors:
        print("sample-mask proof FAIL: " + "; ".join(errors))
        return 1
    print("sample-mask proof PASS" + ("; 14 hostile mutations caught" if args.self_test else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
