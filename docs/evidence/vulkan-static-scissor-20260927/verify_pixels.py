#!/usr/bin/env python3
"""Check both Pi 4 captures against the prior full-scissor GPU image."""
from collections import Counter
from pathlib import Path

from PIL import Image


HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / "vulkan-translated-viewport-20260927" / "vulkan-translated-viewport.png"
CAPTURES = ("vulkan-static-scissor.png", "vulkan-static-viewport-scissor.png")
CLEAR = (13, 26, 51, 255)
FACES = {(229, 102, 179, 255), (51, 179, 229, 255)}


def main() -> None:
    reference = Image.open(REFERENCE).convert("RGBA")
    expected = bytearray(reference.tobytes())
    for y in range(reference.height):
        for x in range(reference.width):
            if 320 <= x < 960 and 400 <= y < 600:
                continue
            offset = (y * reference.width + x) * 4
            if tuple(expected[offset : offset + 4]) in FACES:
                expected[offset : offset + 4] = bytes(CLEAR)
    for name in CAPTURES:
        actual = Image.open(HERE / name).convert("RGBA")
        if actual.size != reference.size or actual.tobytes() != expected:
            raise AssertionError(f"{name} differs from the reference clipped to the static scissor")
        counts = Counter(actual.get_flattened_data())
        assert counts[(229, 102, 179, 255)] == 15412, counts
        assert counts[(51, 179, 229, 255)] == 0, counts
        print(f"{name}: exact 1280x800 match, 15,412 magenta pixels, zero cyan pixels")


if __name__ == "__main__":
    main()
