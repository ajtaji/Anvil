#!/usr/bin/env python3
"""Check the returning Pi 4 fan/outline and line Vulkan proof and its RAM captures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetProof.pi4"
GOLDEN = ROOT / "docs/evidence/neon-texttex-20260926/native-pixels.bgra"
GOLDEN_SHA = "34f541a88313f370f5cbaf62639241562cc8d909094143504962e0f8925e8727"
SCENE_BYTES = 64 * 64 * 4
FAN_SHA = "0670700ea847876846f0785f8b55a66b1c8d951ecaf52842ce7a6e827f2be3c7"
LINES_SHA = "8499dae5dd040c3dc7ededc827a7825d3fc12def66e0719b1e595a41cb6604f6"
MAGIC, TAIL = 0x4157564E, 0x4E565741
PROBES = (
    (0, 0, 0), (0, 8, 42), (0, 20, 48), (0, 28, 38),
    (0, 32, 32), (0, 61, 61),
    (1, 0, 0), (1, 2, 2), (1, 32, 32), (1, 61, 61),
    (1, 2, 61), (1, 0, 1),
)


class CheckError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def golden_segments() -> tuple[bytes, bytes]:
    data = GOLDEN.read_bytes()
    require(len(data) == 15 * SCENE_BYTES, "native golden length changed")
    require(hashlib.sha256(data).hexdigest() == GOLDEN_SHA, "native golden hash changed")
    fan = data[4 * SCENE_BYTES:5 * SCENE_BYTES]
    lines = data[5 * SCENE_BYTES:6 * SCENE_BYTES]
    require(hashlib.sha256(fan).hexdigest() == FAN_SHA, "fan golden hash changed")
    require(hashlib.sha256(lines).hexdigest() == LINES_SHA, "line golden hash changed")
    return fan, lines


def check_source() -> int:
    source = PAYLOAD.read_text(encoding="utf-8")
    required = (
        "#NW_PROOF_MODE        = 2",
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"',
        "nwPairClear[0] = $3D888889 : nwPairClear[1] = $3E048485",
        "nwPairClear[2] = $3E5CDCDD : nwPairClear[3] = $3F800000",
        "rc = nwPairFanFrame(imageBase, imagePitch)",
        "rc = nwPairLinesFrame(imageBase, imagePitch)",
        "nwPut(#NW_S_CAPACITY_BOXES, 2)",
        "  Else\n  If #NW_PROOF_MODE = 0",
        "  EndIf ; historical paired scenes only\n\n  ; Bind the display",
        "If #NW_PROOF_MODE = 0 : delay(#NW_SHOW_MS) : EndIf\n  EndIf ; widget/display branch; mode 2 joins at teardown",
        "NeonFanOutline(", "NeonFanEnd(", "NeonLinesEnd(",
        "PokeA($07014000", "PokeA($07018000",
    )
    for item in required:
        require(item in source, f"fan/line production proof omits {item}")
    return len(required)


def check_report(data: bytes, fan: bytes, lines: bytes) -> int:
    require(len(data) == 256, f"report has {len(data)} bytes, expected 256")
    r = struct.unpack("<64I", data)
    exact = {
        0: MAGIC, 1: 0, 2: 9, 3: 256,
        17: 0, 18: 0, 19: 0, 20: 1, 21: 0, 22: 0, 23: 1,
        32: 0, 33: 0, 34: 0, 35: 0, 36: 0, 37: 0,
        38: len(PROBES), 51: 0, 53: 1,
        54: 0x181, 55: 1, 56: 1, 57: 0,
        58: 0x3DCCCCCD, 59: 0x3E4CCCCD,
        60: 0x3E99999A, 61: 0x3F800000,
        62: 2, 63: TAIL,
    }
    for slot, expected in exact.items():
        require(r[slot] == expected,
                f"report[{slot}] is 0x{r[slot]:08X}, expected 0x{expected:08X}")
    for slot in range(4, 17):
        require(r[slot] != 0, f"public object/report field {slot} is zero")
    require(r[16] == 3200, f"attachment pitch is {r[16]}, expected 3200")
    require(r[15] >= 800 * 1280 * 4, "attachment allocation is undersized")
    for slot in (24, 26):
        require(0 < r[slot] <= 47, f"draw count in report[{slot}] is invalid")
    for slot in (25, 27):
        require(0 < r[slot] <= 654 and r[slot] % 3 == 0,
                f"vertex count in report[{slot}] is invalid")
    for index, (scene, x, y) in enumerate(PROBES):
        frame = fan if scene == 0 else lines
        expected = struct.unpack_from("<I", frame, y * 256 + x * 4)[0]
        require(r[39 + index] == expected,
                f"probe {index} ({'fan' if scene == 0 else 'lines'} {x},{y}) "
                f"is 0x{r[39+index]:08X}, expected 0x{expected:08X}")
    return len(exact) + 13 + 2 + 4 + len(PROBES)


def check_capture(data: bytes, expected: bytes, name: str) -> int:
    require(len(data) == SCENE_BYTES,
            f"{name} capture has {len(data)} bytes, expected {SCENE_BYTES}")
    if data != expected:
        offset = next(i for i, (a, b) in enumerate(zip(data, expected)) if a != b)
        raise CheckError(f"{name} differs from native golden at byte {offset} "
                         f"(pixel {offset // 4 % 64},{offset // 256})")
    return SCENE_BYTES


def run_json_report(path: Path) -> bytes:
    record = json.loads(path.read_text(encoding="utf-8"))
    require(record.get("failures") == [], "board_run reported failures")
    require(record.get("x0") == record.get("expected_x0"), "board_run x0 mismatch")
    trace = record.get("trace", {})
    require(trace.get("bytes") == 256, "board_run trace is not 256 bytes")
    return bytes.fromhex(trace.get("hex", ""))


def self_test(fan: bytes, lines: bytes) -> int:
    words = [0] * 64
    values = {
        0: MAGIC, 2: 9, 3: 256, 20: 1, 23: 1,
        24: 2, 25: 30, 26: 1, 27: 18, 38: len(PROBES), 53: 1,
        54: 0x181, 55: 1, 56: 1,
        58: 0x3DCCCCCD, 59: 0x3E4CCCCD,
        60: 0x3E99999A, 61: 0x3F800000, 62: 2, 63: TAIL,
    }
    values.update({slot: 0x1000 + slot for slot in range(4, 17)})
    values[15], values[16] = 800 * 1280 * 4, 3200
    for slot, value in values.items():
        words[slot] = value
    for index, (scene, x, y) in enumerate(PROBES):
        frame = fan if scene == 0 else lines
        words[39 + index] = struct.unpack_from("<I", frame, y * 256 + x * 4)[0]
    report = struct.pack("<64I", *words)
    checks = check_report(report, fan, lines)
    checks += check_capture(fan, fan, "fan") + check_capture(lines, lines, "lines")
    broken = bytearray(report)
    struct.pack_into("<I", broken, 62 * 4, 1)
    try:
        check_report(bytes(broken), fan, lines)
    except CheckError:
        checks += 1
    else:
        raise CheckError("wrong-mode report mutation was accepted")
    broken = bytearray(fan)
    broken[4 * (42 * 64 + 8)] ^= 1
    try:
        check_capture(bytes(broken), fan, "fan")
    except CheckError:
        checks += 1
    else:
        raise CheckError("fan pixel mutation was accepted")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, help="256-byte x0 report")
    parser.add_argument("--run-json", type=Path, help="board_run JSON with 256-byte trace")
    parser.add_argument("--fan", type=Path, help="16,384-byte readback from 0x07014000")
    parser.add_argument("--lines", type=Path, help="16,384-byte readback from 0x07018000")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        fan, lines = golden_segments()
        total = 4 + check_source()
        if args.self_test:
            total += self_test(fan, lines)
        if args.report:
            total += check_report(args.report.read_bytes(), fan, lines)
        if args.run_json:
            total += check_report(run_json_report(args.run_json), fan, lines)
        if args.fan:
            total += check_capture(args.fan.read_bytes(), fan, "fan")
        if args.lines:
            total += check_capture(args.lines.read_bytes(), lines, "lines")
        require(args.self_test or args.report or args.run_json or args.fan or args.lines,
                "select a report, capture or self-test")
    except (CheckError, OSError, ValueError, KeyError) as error:
        print(f"vulkan_neon_fan_line_proof_check: FAIL - {error}", file=sys.stderr)
        return 1
    print(f"vulkan_neon_fan_line_proof_check: PASS - {total} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
