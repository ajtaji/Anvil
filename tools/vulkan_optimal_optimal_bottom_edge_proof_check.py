#!/usr/bin/env python3
"""Check the bounded Pi 4 bottom-edge optimal-image copy proof."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanOptimalToOptimalBottomEdgeProof.pi4"
BACKEND = ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
DMA = ROOT / "RaspberryPi4/Board/vulkan_dma.pi4"
MAGIC, TAIL = 0x59524156, 0x56415259


def edge_word(x: int, y: int) -> int:
    return (0xFF000000 | (((x * 17 + y * 3) & 255) << 16)
            | (((x * 5 + y * 29) & 255) << 8)
            | ((x * 37 + y * 11) & 255))


def check_source(source: str, backend: str, dma: str) -> list[str]:
    required = (
        ("source tile column", "copy\\srcOffset\\x = 4 : copy\\srcOffset\\y = 8", source),
        ("destination tile column", "copy\\dstOffset\\x = 8 : copy\\dstOffset\\y = 8", source),
        ("bottom-edge-only extent", "copy\\extent\\width = 4 : copy\\extent\\height = 5", source),
        ("public image copy", "vkCmdCopyImage(cmd, srcImage, #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, dstImage, #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, @copy)", source),
        ("mapped row oracle", "vvpEdgeWord(col - 4, row)", source),
        ("untouched right strip", "If col = 12 And row >= 8 : rightEdge = rightEdge + 1", source),
        ("full destination oracle", "exact <> 20 Or untouched <> 149 Or rightEdge <> 5", source),
        ("full source oracle", "sourceExact <> 169", source),
        ("unaligned nonedge refusal", "copy\\srcOffset\\x = 4 : copy\\srcOffset\\y = 4", source),
        ("expected no-work refusal", "rc <> #ANVIL_VK_ERR_UNSUPPORTED Or hwVkDmaOps <> dmaAfter + 32", source),
        ("DMA-only Pi4 backend", "avkBackendSubmitTiledEdgeTailCopy", backend),
        ("guarded DMA tile copy", "HwVkDmaCopyRows", backend),
        ("hardware DMA counter", "hwVkDmaOps = hwVkDmaOps + 1", dma),
    )
    return [label for label, token, body in required if token not in body]


def check_report(data: bytes) -> list[str]:
    if len(data) != 1056:
        return [f"report length {len(data)} != 1056"]
    r = struct.unpack("<264I", data)
    expected = {0: MAGIC, 1: 0, 2: 0, 3: 0, 82: 0, 85: 0, 95: 0,
                110: 1, 125: 4, 126: 1056, 128: 0,
                235: 338, 236: 78, 239: 1, 242: 5,
                243: 169, 244: 91, 247: 149, 248: 0,
                255: 20, 256: 91, 257: 160,
                258: (-20005) & 0xFFFFFFFF,
                259: edge_word(4, 8), 260: edge_word(7, 12),
                261: 1024, 262: 1408, 263: TAIL}
    errors = [f"slot {slot}: {r[slot]:#x} != {want:#x}"
              for slot, want in expected.items() if r[slot] != want]
    if r[250] != r[249]:
        errors.append("partial copy unexpectedly changed TFU count")
    for before, after, label, delta in ((251, 252, "partial DMA", 2),
                                         (253, 254, "partial backend jobs", 1),
                                         (240, 241, "destination readback DMA", 16),
                                         (245, 246, "source readback DMA", 16)):
        if r[after] - r[before] != delta:
            errors.append(f"{label} delta != {delta}")
    if r[240] != r[252] or r[245] != r[241]:
        errors.append("copy/readback DMA phases not contiguous")
    return errors


def self_test(source: str, backend: str, dma: str) -> int:
    assert not check_source(source, backend, dma)
    r = [0] * 264
    fields = {0: MAGIC, 110: 1, 125: 4, 126: 1056,
              235: 338, 236: 78, 239: 1, 240: 2, 241: 18,
              242: 5, 243: 169, 244: 91, 245: 18, 246: 34,
              247: 149, 249: 2, 250: 2, 251: 0, 252: 2,
              253: 2, 254: 3, 255: 20, 256: 91, 257: 160,
              258: (-20005) & 0xFFFFFFFF,
              259: edge_word(4, 8), 260: edge_word(7, 12),
              261: 1024, 262: 1408, 263: TAIL}
    for slot, value in fields.items():
        r[slot] = value
    report = lambda: struct.pack("<264I", *r)
    assert not check_report(report())
    mutations = ((1, 1), (2, 1), (82, 1), (85, 1), (95, 1),
                 (110, 0), (125, 3), (126, 256),
                 (235, 337), (236, 77), (239, 0),
                 (241, 17), (242, 4), (243, 168), (244, 90),
                 (245, 17), (246, 33), (247, 148),
                 (248, 1), (250, 3), (252, 3), (254, 4),
                 (255, 19), (256, 90), (257, 159),
                 (258, 0), (259, 0), (260, 0), (261, 0),
                 (262, 0), (263, 0))
    for slot, bad in mutations:
        old = r[slot]
        r[slot] = bad
        assert check_report(report()), f"uncaught report mutation {slot}"
        r[slot] = old
    for token in ("copy\\srcOffset\\x = 4 : copy\\srcOffset\\y = 8",
                  "copy\\extent\\width = 4 : copy\\extent\\height = 5",
                  "vvpEdgeWord(col - 4, row)"):
        assert check_source(source.replace(token, token.replace(" = ", " <> ", 1)
                                   if " = " in token else "broken"), backend, dma)
    return len(mutations) + 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = SOURCE.read_text(encoding="utf-8-sig")
    backend = BACKEND.read_text(encoding="utf-8-sig")
    dma = DMA.read_text(encoding="utf-8-sig")
    errors = check_source(source, backend, dma)
    count = 0
    if args.self_test:
        count = self_test(source, backend, dma)
    if args.report:
        errors += check_report(args.report.read_bytes())
    if errors:
        print("bottom-edge proof FAIL: " + "; ".join(errors))
        return 1
    print("bottom-edge proof PASS" + (f"; {count} hostile mutations caught" if args.self_test else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
