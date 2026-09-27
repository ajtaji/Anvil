#!/usr/bin/env python3
"""Verify indexed and array Pi 4 triangle strips filled the same square."""
import json
from collections import Counter
from pathlib import Path
import struct
import zlib


HERE = Path(__file__).resolve().parent
FILL = (229, 77, 179, 255)


def rgb_pixels(path: Path) -> tuple[tuple[int, int], bytes]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            assert (depth, color, compression, filtering, interlace) == (8, 2, 0, 0, 0)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        offset += length + 12
    raw = zlib.decompress(compressed)
    stride = width * 3
    rows = bytearray()
    previous = bytearray(stride)
    pos = 0
    for _ in range(height):
        filter_kind = raw[pos]
        pos += 1
        row = bytearray(raw[pos:pos + stride])
        pos += stride
        for x in range(stride):
            left = row[x - 3] if x >= 3 else 0
            up = previous[x]
            upper_left = previous[x - 3] if x >= 3 else 0
            if filter_kind == 1:
                predictor = left
            elif filter_kind == 2:
                predictor = up
            elif filter_kind == 3:
                predictor = (left + up) // 2
            elif filter_kind == 4:
                p = left + up - upper_left
                distances = (abs(p - left), abs(p - up), abs(p - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
            else:
                assert filter_kind == 0
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        rows.extend(row)
        previous = row
    assert pos == len(raw)
    return (width, height), bytes(rows)


def main() -> None:
    pixels = []
    for kind, seq in (("array", 106), ("indexed", 107)):
        stem = f"vulkan-triangle-strip-{kind}"
        meta = json.loads((HERE / f"{stem}.json").read_text())
        assert meta["x0"] == "0000000000000000"
        assert meta["shot_header"]["seq"] == seq
        size, rgb = rgb_pixels(HERE / f"{stem}.png")
        assert size == (1280, 800)
        assert Counter(tuple(rgb[i:i + 3]) for i in range(0, len(rgb), 3))[FILL[:3]] == 367393
        for probe in ((300, 200), (300, 500), (900, 200), (900, 500)):
            x, y = probe
            start = (y * size[0] + x) * 3
            assert tuple(rgb[start:start + 3]) == FILL[:3], (kind, probe)
        pixels.append(rgb)
    assert pixels[0] == pixels[1], "indexed and array captures differ"
    print("PASS: captures 106/107 pixel-identical; both halves of the GPU strip are filled")


if __name__ == "__main__":
    main()
