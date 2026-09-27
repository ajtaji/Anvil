#!/usr/bin/env python3
"""Verify the Pi 4 resize proof against its prior 400x640 viewport image."""
import json
import struct
from pathlib import Path

from PIL import Image


HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / "vulkan-subviewport-20260927" / "vulkan-subviewport.png"


def report(name: str) -> tuple[int, ...]:
    words = struct.unpack("<64I", (HERE / name).read_bytes())
    assert words[0] == 0x564B444C and words[62] == 256 and words[63] == 0x4C444B56
    return words


def main() -> None:
    first = report("report-first.bin")
    assert first[1] == 12 and first[61] == 3, (first[1], first[61])
    final = report("report.bin")
    assert final[55] == 12 and final[47] == 12, (final[55], final[47])
    metadata = json.loads((HERE / "vulkan-framebuffer-resize.json").read_text())
    assert metadata["x0"] == "0000000000000000"
    assert metadata["shot_header"]["seq"] == 105
    actual = Image.open(HERE / "vulkan-framebuffer-resize.png").convert("RGBA")
    reference = Image.open(REFERENCE).convert("RGBA")
    assert actual.size == reference.size == (1280, 800)
    a = actual.load()
    b = reference.load()
    for y in range(400, 800):
        for x in range(640):
            assert a[x, y] == b[x, y], (x, y, a[x, y], b[x, y])
    print("PASS: 12 draws, 12 DMA presents, exact 640x400 rotated small-framebuffer region")


if __name__ == "__main__":
    main()
