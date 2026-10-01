#!/usr/bin/env python3
"""Check the bounded Pi 4 public vkCmdFillBuffer DMA RAM proof."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanBufferFillProof.pi4"
BACKEND = ROOT / "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
DMA = ROOT / "RaspberryPi4/Board/vulkan_dma.pi4"
MAGIC, TAIL = 0x46424B56, 0x564B4246


def check_source(source: str, backend: str, dma: str) -> list[str]:
    required = (
        ("public aligned fill", "vkCmdFillBuffer(cmd, buffer, 64, 64, #VBF_WORD)", source),
        ("public unaligned refusal", "vkCmdFillBuffer(cmd, buffer, 2, 64, #VBF_WORD)", source),
        ("asymmetric pattern", "#VBF_WORD = $A1B2C3D4", source),
        ("buffer range", "bci\\size = 256", source),
        ("aligned guarded binding", "vkBindBufferMemory(dev, buffer, memory, bound)", source),
        ("allocation structure type", "mai\\sType = #VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO", source),
        ("memory type zero", "mai\\memoryTypeIndex = 0", source),
        ("coherent memory type", "(req\\memoryTypeBits & 1) = 0", source),
        ("allocation return report", "vbfPut(35, rc)", source),
        ("binding return report", "vbfPut(36, rc)", source),
        ("live alignment", "bound = ((256 + req\\alignment - 1) / req\\alignment) * req\\alignment", source),
        ("filled/untouched oracle", "filled <> 16 Or untouched <> 48", source),
        ("DMA-only backend fill", "HwVkDmaFill(avkV3dWindowBase, avkV3dWindowBytes, destination, bytes, data)", backend),
        ("hardware DMA counter", "If filled <> 0 And restored <> 0 : hwVkDmaOps = hwVkDmaOps + 1", dma),
    )
    return [label for label, token, body in required if token not in body]


def check_report(data: bytes) -> list[str]:
    if len(data) != 256:
        return [f"report length {len(data)} != 256"]
    r = struct.unpack("<64I", data)
    expected = {0: MAGIC, 1: 0, 2: 7, 8: 0, 9: 0,
                20: 0, 21: 16, 22: 48, 24: 64,
                26: (-20001) & 0xFFFFFFFF, 27: 1, 28: 0, 29: 0,
                30: 0, 31: 0, 32: 0, 33: 1, 34: 1, 35: 0, 36: 0,
                62: 256, 63: TAIL}
    errors = [f"slot {slot}: {r[slot]:#x} != {want:#x}"
              for slot, want in expected.items() if r[slot] != want]
    if not (256 <= r[3] <= 4096) or r[3] % 4 or r[4] < 4 or r[4] > 4096 or r[4] % 4:
        errors.append("memory requirement/alignment out of admitted range")
    if (r[37] & 1) == 0:
        errors.append("coherent memory type zero unavailable")
    bound = ((256 + r[4] - 1) // r[4]) * r[4] if r[4] else 0
    if r[6] != bound or not (256 <= bound <= 4096) or r[5] != bound + r[3] + 256:
        errors.append("aligned guarded allocation size disagrees with live requirement")
    if r[23] != bound // 4 or r[25] != (r[3] - 256) // 4:
        errors.append("allocation and padding guard sizes disagree")
    if r[7] % 4 or not (0x063E8000 <= r[7] < 0x063E8000 + 4227072):
        errors.append("bound buffer address outside Vulkan window")
    for before, after, label, delta in ((10, 11, "guarded DMA", 1),
                                         (12, 13, "backend jobs", 1),
                                         (14, 15, "TFU", 0),
                                         (16, 17, "bin", 0),
                                         (18, 19, "render", 0)):
        if r[after] - r[before] != delta:
            errors.append(f"{label} delta != {delta}")
    return errors


def self_test(source: str, backend: str, dma: str) -> None:
    assert not check_source(source, backend, dma)
    r = [0] * 64
    fields = {0: MAGIC, 1: 0, 2: 7, 3: 256, 4: 4096, 5: 4608,
              6: 4096, 7: 0x06400000, 10: 1, 11: 2, 12: 2, 13: 3,
              14: 3, 15: 3, 16: 4, 17: 4, 18: 5, 19: 5,
              21: 16, 22: 48, 23: 1024, 24: 64,
              26: (-20001) & 0xFFFFFFFF, 27: 1,
              33: 1, 34: 1, 35: 0, 36: 0, 37: 1, 62: 256, 63: TAIL}
    for slot, value in fields.items(): r[slot] = value
    report = lambda: struct.pack("<64I", *r)
    assert not check_report(report())
    saved = (r[4], r[5], r[6], r[23])
    r[4], r[5], r[6], r[23] = 64, 768, 256, 64
    assert not check_report(report()), "64-byte alignment must keep a 256-byte guard prefix"
    r[4], r[5], r[6], r[23] = saved
    mutants = ((1, 5), (3, 128), (4, 256), (5, 512), (6, 256), (7, 0),
               (11, 1), (13, 2), (15, 4), (17, 5),
               (21, 15), (22, 47), (23, 63), (25, 1),
               (26, 0), (27, 0), (28, 1), (30, 1),
               (35, (-20001) & 0xFFFFFFFF), (36, (-20001) & 0xFFFFFFFF),
               (37, 0), (63, 0))
    for slot, bad in mutants:
        old = r[slot]; r[slot] = bad
        assert check_report(report()), f"uncaught report mutation {slot}"
        r[slot] = old
    assert check_source(source.replace("#VBF_WORD = $A1B2C3D4", "#VBF_WORD = $A1B2C3D5"), backend, dma)
    assert check_source(source.replace("vkCmdFillBuffer(cmd, buffer, 64, 64, #VBF_WORD)",
                                       "vkCmdFillBuffer(cmd, buffer, 60, 64, #VBF_WORD)"), backend, dma)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = SOURCE.read_text(encoding="utf-8-sig")
    backend = BACKEND.read_text(encoding="utf-8-sig")
    dma = DMA.read_text(encoding="utf-8-sig")
    errors = check_source(source, backend, dma)
    if args.self_test:
        self_test(source, backend, dma)
    if args.report:
        errors += check_report(args.report.read_bytes())
    if errors:
        print("buffer-fill proof FAIL: " + "; ".join(errors))
        return 1
    print("buffer-fill proof PASS" + ("; 24 hostile mutations caught" if args.self_test else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
