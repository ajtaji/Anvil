#!/usr/bin/env python3
"""Exact desk/report oracle for vulkanAtlasChromeProof.

The diagnostic returns the inherited 240-word report and presents an 800x1280
BGRA scanout.  This checker independently pins the public Vulkan command
sequence and the four scene facts needed before the IDE renderer can move:
solid chrome, a transparent atlas texel, a fully covered tinted atlas texel,
and a covered texel removed by the per-draw scissor.
"""

from __future__ import annotations

import argparse
import struct
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanAtlasChromeProof.pi4"
W, H = 800, 1280
MAGIC, TAIL = 0x59524156, 0x56415259

# coordinate, exact attachment/presented BGRA word, semantic assertion
PROBES = (
    ((100, 110), 0xFF000080, "solid panel from the atlas' white texel and blue tint"),
    ((100, 150), 0xFF00FFFF, "later solid toolbar from the same texel and cyan tint"),
    ((130, 316), 0xFF000080, "transparent glyph texel preserves the panel"),
    ((150, 316), 0xFFFFFFFF, "covered atlas texel receives white tint"),
    ((650, 316), 0xFFFF00FF, "covered atlas texel inside final scissor receives magenta tint"),
    ((700, 316), 0xFF000080, "same covered row outside final scissor is untouched"),
)


def fail(message: str) -> None:
    raise AssertionError(message)


def check_source() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    required = (
        "ici\\tiling = #VK_IMAGE_TILING_OPTIMAL",
        "ici\\extent\\width = #VAC_ATLAS_W",
        "vkCmdCopyBufferToImage(cmd, stage, tex",
        "#VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER",
        "#VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER",
        "gp\\pDynamicState = @dyn",
        "dynState = #VK_DYNAMIC_STATE_SCISSOR",
        "cba\\blendEnable = 1",
        "vkCmdBindDescriptorSets(cmd",
        "vkCmdPushConstants(cmd",
        "#DSP_DMA_LINKED = 1",
        "DisplayDmaBind()",
        "DisplayDmaOps() - dmaBefore",
    )
    for needle in required:
        if needle not in text:
            fail(f"public atlas/chrome source contract missing: {needle}")

    # Only inspect the mixed pass' render-pass sequence. Eight draws and eight
    # public dynamic-scissor snapshots are the acceptance shape.
    start = text.index("If rc = #VK_SUCCESS\n      vkCmdBeginRenderPass", text.index("Procedure.i vvpSamplePass"))
    end = text.index("vkCmdEndRenderPass(cmd)", start)
    scene = text[start:end]
    first_vertices = (3, 9, 15, 21, 27, 33, 39, 45)
    positions = []
    for first in first_vertices:
        needle = f"vkCmdDraw(cmd, 6, 1, {first}, 0)"
        positions.append(scene.index(needle))
    if positions != sorted(positions) or scene.count("vkCmdDraw(cmd, 6, 1,") != 8:
        fail("scene is not exactly eight ordered six-vertex draws")
    if scene.count("vkCmdSetScissor(cmd, 0, 1, @sc)") != 8:
        fail("each atlas/chrome draw must snapshot one public dynamic scissor")
    if scene.count("vkCmdBeginRenderPass(") != 1:
        fail("atlas/chrome scene must remain one render pass")
    return len(required) + len(first_vertices) + 3


def read_report(path: Path) -> tuple[int, ...]:
    data = path.read_bytes()
    if len(data) != 960:
        fail(f"report must be exactly 960 bytes, got {len(data)}")
    return struct.unpack("<240I", data)


def check_report(path: Path) -> int:
    r = read_report(path)
    exact = {
        0: MAGIC,
        1: 0, 2: 0, 3: 0, 128: 0,
        98: 1, 99: 1, 127: 1,
        131: 0, 132: 0,
        133: PROBES[0][1], 134: PROBES[1][1], 135: PROBES[2][1],
        136: PROBES[3][1], 137: PROBES[4][1], 138: PROBES[5][1],
        153: 0, 154: 0, 155: 0,
        159: 0, 160: 1,
        163: 0, 164: 0, 165: 0,
        166: 5,                 # VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL
        167: 1,                 # exact scene probes
        175: 11,                # three controls plus eight chrome draws
        220: 1, 221: 1, 222: 1,
        223: 8,                 # public vkCmdSetScissor snapshots
        236: 0x40,
        239: TAIL,
    }
    for slot, expected in exact.items():
        if r[slot] != expected:
            fail(f"report[{slot}] = 0x{r[slot]:08X}, expected 0x{expected:08X}")
    if r[149] + 1 != r[150] or r[151] + 1 != r[152]:
        fail("eight draws did not collapse into one bin/render job pair")
    if r[87] != r[88]:
        fail("surface guard checksum changed")
    if r[144] != 0x20000000 or r[145] != 0x00400800:
        fail("texture state is not the exact 8x8 optimal atlas shape")
    if r[162] < 256:
        fail("optimal atlas allocation is smaller than its 8x8 source")
    return len(exact) + 4


def check_screenshot(path: Path) -> int:
    data = path.read_bytes()
    needed = W * H * 4
    if len(data) != needed:
        fail(f"screenshot must be {W}x{H} raw BGRA ({needed} bytes), got {len(data)}")
    checks = 0
    for (x, y), expected, meaning in PROBES:
        for yy in range(y - 2, y + 3):
            for xx in range(x - 2, x + 3):
                got = struct.unpack_from("<I", data, (yy * W + xx) * 4)[0]
                if got != expected:
                    fail(f"{meaning}: ({xx},{yy})=0x{got:08X}, expected 0x{expected:08X}")
                checks += 1
    return checks


def synthetic() -> tuple[bytes, bytes]:
    r = [0] * 240
    exact = {
        0: MAGIC, 98: 1, 99: 1, 127: 1, 160: 1, 162: 1024, 166: 5,
        167: 1, 175: 11, 220: 1, 221: 1, 222: 1, 223: 8,
        236: 0x40, 239: TAIL, 144: 0x20000000, 145: 0x00400800,
        149: 7, 150: 8, 151: 9, 152: 10, 87: 0x1234, 88: 0x1234,
    }
    for slot, value in exact.items():
        r[slot] = value
    for slot, probe in zip(range(133, 139), PROBES):
        r[slot] = probe[1]
    pixels = bytearray(struct.pack("<I", 0xFF3380B2) * (W * H))
    for (x, y), expected, _ in PROBES:
        for yy in range(y - 2, y + 3):
            for xx in range(x - 2, x + 3):
                struct.pack_into("<I", pixels, (yy * W + xx) * 4, expected)
    return struct.pack("<240I", *r), bytes(pixels)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, help="960-byte x0 report")
    ap.add_argument("--screenshot", type=Path, help="800x1280 raw BGRA capture")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    try:
        total = check_source()
        labels = ["public source contract"]
        if args.self_test:
            report_data, screen_data = synthetic()
            with tempfile.TemporaryDirectory(prefix="anvil-vkatlas-") as td:
                report = Path(td) / "report.bin"
                screen = Path(td) / "screen.bgra"
                report.write_bytes(report_data)
                screen.write_bytes(screen_data)
                total += check_report(report) + check_screenshot(screen)
            labels.extend(("synthetic report", "six exact 5x5 pixel regions"))
        if args.report:
            total += check_report(args.report)
            labels.append("board report")
        if args.screenshot:
            total += check_screenshot(args.screenshot)
            labels.append("board screenshot")
    except (AssertionError, OSError, ValueError) as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 1
    print(f"PASS - {', '.join(labels)}; {total} exact checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
