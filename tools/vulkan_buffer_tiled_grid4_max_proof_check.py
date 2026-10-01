#!/usr/bin/env python3
"""Independent report oracle for the Pi 4 maximum 4x4 UIF-grid upload proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanBufferOptimalGrid4MaxProof.pi4"
REPORT_WORDS = 264
MAGIC, TAIL = 0x59524156, 0x56415259
TILE_COUNTS = tuple((1 if row == 0 else 4) * (1 if col == 0 else 4)
                    for row in range(4) for col in range(4))


class CheckError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise CheckError(message)


def edge_word(x: int, y: int) -> int:
    return (0xFF000000 | (((x * 17 + y * 3) & 255) << 16) |
            (((x * 5 + y * 29) & 255) << 8) | ((x * 37 + y * 11) & 255))


def check_source() -> int:
    source = PAYLOAD.read_text(encoding="utf-8")
    required = (
        'XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"',
        'XIncludeFile "RaspberryPi4/Board/vulkan_dma.pi4"',
        'XIncludeFile "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"',
        "#VVP_S_TILE_BASE = 200",
        "partial\\bufferOffset = 64 : partial\\bufferRowLength = 16",
        "partial\\imageOffset\\x = 3 : partial\\imageOffset\\y = 3",
        "partial\\imageExtent\\width = 13 : partial\\imageExtent\\height = 13",
        "vvpPut(#VVP_S_GRID_TILE_COUNT, 16)",
        "dmaAfter <> dmaBefore + 16",
        "#VVP_S_PARTIAL_DMA_AFTER) <> vvpGet(#VVP_S_PARTIAL_DMA_BEFORE) + 16",
        "tileCounts[((row >> 2) * 4) + (col >> 2)]",
    )
    for item in required:
        require(item in source, f"maximum-grid proof source omits {item}")
    require(not re.search(r"(?m)^\s*XIncludeFile.*vk_backend_test", source),
            "proof includes the state-only test backend")
    return len(required) + 1


def check_report(data: bytes) -> int:
    require(len(data) == REPORT_WORDS * 4,
            f"report has {len(data)} bytes, expected {REPORT_WORDS * 4}")
    r = struct.unpack(f"<{REPORT_WORDS}I", data)
    exact = {
        0: MAGIC, 1: 0, 2: 0, 3: 0, 82: 0, 85: 0,
        95: 0, 96: 0, 110: 1, 125: 4, 126: REPORT_WORDS * 4, 128: 0,
        234: 4, 235: 183, 236: 16, 237: 820, 239: 0,
        242: 87, 243: 169, 244: 39, 247: 87, 248: 0,
        255: 169, 256: 64, 257: 96,
        259: edge_word(21, 19), 260: edge_word(33, 31),
        261: 1408, 262: 1408, 263: TAIL,
    }
    for slot, expected in exact.items():
        require(r[slot] == expected,
                f"report[{slot}] is 0x{r[slot]:08X}, expected 0x{expected:08X}")
    for index, expected in enumerate(TILE_COUNTS):
        slot = 200 + index
        require(r[slot] == expected,
                f"tile {index} report[{slot}] is {r[slot]}, expected {expected}")
    counters = (
        (249, 250, 0, "TFU during partial upload"),
        (251, 252, 16, "DMA during partial upload"),
        (253, 254, 1, "backend jobs during partial upload"),
        (240, 241, 16, "DMA during full readback"),
    )
    for before, after, delta, name in counters:
        require(r[after] == (r[before] + delta) & 0xFFFFFFFF,
                f"{name}: report[{before}]={r[before]}, report[{after}]={r[after]}")
    require(sum(TILE_COUNTS) == 169, "checker tile geometry is inconsistent")
    return len(exact) + len(TILE_COUNTS) + len(counters) + 1


def report_from_run_json(path: Path) -> bytes:
    record = json.loads(path.read_text(encoding="utf-8"))
    require(record.get("failures") == [], "board_run reported failures")
    require(record.get("x0") == record.get("expected_x0"), "board_run x0 mismatch")
    trace = record.get("trace", {})
    require(trace.get("bytes") == REPORT_WORDS * 4, "board_run trace size mismatch")
    return bytes.fromhex(trace.get("hex", ""))


def self_test() -> int:
    words = [0] * REPORT_WORDS
    exact = {
        0: MAGIC, 110: 1, 125: 4, 126: REPORT_WORDS * 4,
        234: 4, 235: 183, 236: 16, 237: 820,
        242: 87, 243: 169, 244: 39, 247: 87,
        255: 169, 256: 64, 257: 96,
        259: edge_word(21, 19), 260: edge_word(33, 31),
        261: 1408, 262: 1408, 263: TAIL,
        249: 1, 250: 1, 251: 0, 252: 16,
        253: 1, 254: 2, 240: 16, 241: 32,
    }
    exact.update({200 + i: value for i, value in enumerate(TILE_COUNTS)})
    for slot, value in exact.items():
        words[slot] = value
    report = struct.pack(f"<{REPORT_WORDS}I", *words)
    checks = check_report(report)
    for slot, bad in ((215, 15), (236, 9), (241, 31), (243, 168)):
        broken = bytearray(report)
        struct.pack_into("<I", broken, slot * 4, bad)
        try:
            check_report(bytes(broken))
        except CheckError:
            checks += 1
        else:
            raise CheckError(f"mutated report[{slot}] was accepted")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, help="1,056-byte x0 report")
    parser.add_argument("--run-json", type=Path, help="board_run JSON with 1,056-byte trace")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        total = check_source()
        if args.self_test:
            total += self_test()
        if args.report:
            total += check_report(args.report.read_bytes())
        if args.run_json:
            total += check_report(report_from_run_json(args.run_json))
        require(args.self_test or args.report or args.run_json,
                "select a report or self-test")
    except (CheckError, OSError, ValueError, KeyError) as error:
        print(f"vulkan_buffer_tiled_grid4_max_proof_check: FAIL - {error}",
              file=sys.stderr)
        return 1
    print(f"vulkan_buffer_tiled_grid4_max_proof_check: PASS - {total} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
