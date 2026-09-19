#!/usr/bin/env python3
"""Independent oracle for vulkanDrawListProof's report and raw screenshot.

The board report is exactly 256 little-endian bytes. The optional screenshot
is exactly an 800 x 1280 tightly packed BGRA8888 scanout capture. With neither
input, the checker still verifies that the diagnostic source contains the
ordered six-draw, single-render-pass sequence which the binary report names.
"""

from __future__ import annotations

import argparse
import struct
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BODY = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanTriangleProofBody.pbi"
WRAPPER = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanDrawListProof.pi4"

W, H = 800, 1280
MAGIC, TAIL = 0x564B444C, 0x4C444B56

# Coordinate, exact attachment word, exact presented word, semantic assertion.
# The V3D attachment retains blended alpha. The display-owner presentation
# copy makes the scanout alpha byte opaque while preserving exact RGB.
PROBES = (
    ((50, 50), 0xFF3380B2, 0xFF3380B2, "outside remains render-pass clear"),
    ((150, 1000), 0xFFFF0000, 0xFFFF0000, "opaque red base survives alone"),
    ((650, 1000), 0xFF00FF00, 0xFF00FF00, "opaque green survives alone"),
    ((350, 1050), 0xFF00FF00, 0xFF00FF00, "later green replaces overlapping red"),
    ((550, 800), 0xBF007F80, 0xFF007F80, "half-alpha blue source-over opaque green"),
    ((320, 700), 0x9F803F40, 0xFF803F40, "later half-alpha red source-over blue/green"),
    ((400, 250), 0xFFFF00FF, 0xFFFF00FF, "opaque magenta varying draw"),
    ((400, 640), 0xFFFFFFFF, 0xFFFFFFFF, "final opaque white top draw"),
)


def fail(message: str) -> None:
    raise AssertionError(message)


def check_source() -> int:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    body = BODY.read_text(encoding="utf-8")
    if "#VTP_LIST_PROOF = 1" not in wrapper:
        fail("list-proof wrapper does not select its isolated compiler path")
    marker = "; 0: opaque red base."
    start = body.index(marker)
    end = body.index("CompilerElse", start)
    scene = body[start:end]
    expected = (
        "vkCmdDraw(cmd, 6, 1, 0, 0)",
        "vkCmdDraw(cmd, 6, 1, 6, 0)",
        "vkCmdDraw(cmd, 6, 1, 12, 0)",
        "vkCmdDraw(cmd, 6, 1, 18, 0)",
        "vkCmdDraw(cmd, 6, 1, 24, 0)",
        "vkCmdDraw(cmd, 6, 1, 30, 0)",
    )
    positions = [scene.index(call) for call in expected]
    if positions != sorted(positions) or scene.count("vkCmdDraw(") != 6:
        fail("draw sequence is not exactly firstVertex 0,6,12,18,24,30")
    binds = ("pipeA", "pipeC", "pipeB", "pipeA")
    bind_positions = []
    cursor = 0
    for pipe in binds:
        needle = f"vkCmdBindPipeline(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, {pipe})"
        cursor = scene.index(needle, cursor)
        bind_positions.append(cursor)
        cursor += len(needle)
    if bind_positions != sorted(bind_positions):
        fail("pipeline sequence A -> C -> B -> A changed")
    if scene.count("vkCmdPushConstants(") != 5:
        fail("expected five distinct push snapshots around the varying draw")
    for required in (
        "#DSP_DMA_LINKED = 1",
        "DmaSetScratch(dmaScratch, 512)",
        "DisplayDmaBind()",
        "DmaInit()",
        "DisplayDmaOps() - dmaBefore",
    ):
        if required not in body:
            fail(f"accelerated presentation setup is missing: {required}")
    return 3 + 6 + 4 + 1 + 5


def words(path: Path) -> tuple[int, ...]:
    data = path.read_bytes()
    if len(data) != 256:
        fail(f"report must be exactly 256 bytes, got {len(data)}")
    return struct.unpack("<64I", data)


def check_report(path: Path) -> int:
    r = words(path)
    exact = {
        0: MAGIC, 1: 0, 4: 0,
        17: PROBES[0][1], 18: PROBES[1][1], 19: PROBES[2][1],
        20: PROBES[3][1], 21: PROBES[4][1], 22: PROBES[5][1],
        23: PROBES[6][1], 24: PROBES[7][1],
        25: 18, 26: 13, 27: 0, 28: 6,
        # V3D_ERR_VCDI is the documented benign VCD-idle state seen by every
        # healthy BCM2711 graphics run; every other ERR_STAT bit is forbidden.
        33: 0, 34: 0x1000, 35: 0x1000, 36: 0, 37: 0,
        40: 0, 41: 0, 42: 6, 43: 6, 44: 0, 45: 0,
        # The display library uses the positive result #DSP_OK = 1.
        47: 1, 48: 1, 50: 1, 52: 6,
        54: 1, 57: 1, 58: 1, 59: 3, 60: 3, 61: 10, 62: 256, 63: TAIL,
    }
    for slot, expected in exact.items():
        if r[slot] != expected:
            fail(f"report[{slot}] = 0x{r[slot]:08X}, expected 0x{expected:08X}")
    if r[30] - r[29] != 1 or r[32] - r[31] != 1:
        fail("the complete list did not produce exactly one bin/render job pair")
    if r[38] != r[39]:
        fail("guard checksum changed")
    if r[12] - r[11] != 6 or r[55] != r[12]:
        fail("backend draw counter did not advance by exactly the six list records")
    if r[56] == 0:
        fail("stable last-record snapshot address is null")
    return len(exact) + 5


def check_screenshot(path: Path) -> int:
    data = path.read_bytes()
    expected_bytes = W * H * 4
    if len(data) != expected_bytes:
        fail(f"raw screenshot must be {W}x{H} BGRA ({expected_bytes} bytes), got {len(data)}")
    checks = 0
    for (x, y), _attachment, expected, meaning in PROBES:
        # A 5x5 exact region makes a single lucky or stale probe insufficient.
        for yy in range(y - 2, y + 3):
            for xx in range(x - 2, x + 3):
                off = (yy * W + xx) * 4
                actual = struct.unpack_from("<I", data, off)[0]
                if actual != expected:
                    fail(
                        f"{meaning}: ({xx},{yy}) = 0x{actual:08X}, "
                        f"expected 0x{expected:08X}"
                    )
                checks += 1
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, help="256-byte x0 report dump")
    ap.add_argument("--screenshot", type=Path, help="800x1280 raw BGRA scanout")
    ap.add_argument("--self-test", action="store_true", help="exercise report and screenshot oracles with a generated exact fixture")
    args = ap.parse_args()
    try:
        total = check_source()
        labels = ["source sequence"]
        if args.self_test:
            r = [0] * 64
            for slot, value in {
                0: MAGIC, 1: 0, 4: 0, 25: 18, 26: 13, 27: 0, 28: 6,
                29: 7, 30: 8, 31: 11, 32: 12, 34: 0x1000, 35: 0x1000,
                40: 0, 41: 0,
                42: 6, 43: 6, 47: 1, 48: 1, 50: 1, 52: 6, 54: 1,
                57: 1, 58: 1, 59: 3, 60: 3, 61: 10, 62: 256, 63: TAIL,
                11: 100, 12: 106, 55: 106, 56: 1, 38: 0x1234, 39: 0x1234,
            }.items():
                r[slot] = value
            for slot, probe in zip(range(17, 25), PROBES):
                r[slot] = probe[1]
            pixels = bytearray(struct.pack("<I", PROBES[0][2]) * (W * H))
            for (x, y), _attachment, expected, _meaning in PROBES:
                for yy in range(y - 2, y + 3):
                    for xx in range(x - 2, x + 3):
                        struct.pack_into("<I", pixels, (yy * W + xx) * 4, expected)
            with tempfile.TemporaryDirectory(prefix="anvil-vkdl-") as td:
                report = Path(td) / "report.bin"
                screenshot = Path(td) / "scanout.bgra"
                report.write_bytes(struct.pack("<64I", *r))
                screenshot.write_bytes(pixels)
                total += check_report(report) + check_screenshot(screenshot)
            labels.extend(("synthetic 64-word report", "synthetic eight-region screenshot"))
        if args.report:
            total += check_report(args.report)
            labels.append("64-word report")
        if args.screenshot:
            total += check_screenshot(args.screenshot)
            labels.append("eight 5x5 screenshot regions")
    except (AssertionError, OSError, ValueError) as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 1
    print(f"PASS - {', '.join(labels)}; {total} exact checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
