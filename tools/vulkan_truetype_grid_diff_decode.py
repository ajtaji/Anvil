#!/usr/bin/env python3
"""Decode and compare the four preserved BGRA crops from the GPU A/B payload."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_work/vulkan-truetype-grid-diff-20260919"
SIZE = 24
STRIDE = SIZE * SIZE * 4


def read_crops(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if len(data) != STRIDE * 4:
        raise SystemExit(f"expected exactly {STRIDE * 4} bytes, got {len(data)}")
    return [data[i * STRIDE:(i + 1) * STRIDE] for i in range(4)]


def blue(crop: bytes, x: int, y: int) -> int:
    return crop[(y * SIZE + x) * 4]


def normalise(crop: bytes, rotated: bool) -> list[list[int]]:
    # Each output pixel is coverage as observed in the rendered B channel.
    # The attachment uses BGRA8 with white glyphs on opaque black.
    grid = [[0 for _ in range(SIZE)] for _ in range(SIZE)]
    if not rotated:
        for y in range(SIZE):
            for x in range(SIZE):
                grid[y][x] = blue(crop, x, y)
    else:
        # Proof target is square, and the renderer's 90-degree map is
        # (xPhysical,yPhysical)=(511-yLogical,xLogical). The preserved crop
        # begins six pixels left of the exact rotated logical crop; missing
        # far-edge samples are outside the glyph and remain zero.
        for y in range(SIZE):
            for x in range(SIZE):
                px = 29 - y
                py = x
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    grid[y][x] = blue(crop, px, py)
    return grid


def expected_atlas() -> list[list[int]]:
    record = json.loads((ROOT / "_work/pi4-final-deploy-20260919/glyph19-atlas-quad.json").read_text())
    rows = record["zero_atlas_alpha_rows"]
    if len(rows) != 13 or any(len(row) != 14 for row in rows):
        raise SystemExit("glyph19 atlas alpha dimensions changed")
    return [[int(row[x * 2:x * 2 + 2], 16) for x in range(7)] for row in rows]


def summarize(grid: list[list[int]], expected: list[list[int]]) -> dict:
    # The 7x13 atlas glyph is at the same 9,9 offset in all normalized crops.
    actual = [row[9:16] for row in grid[9:22]]
    errors = [abs(actual[y][x] - expected[y][x]) for y in range(13) for x in range(7)]
    nonzero = [(x, y) for y in range(SIZE) for x in range(SIZE) if grid[y][x] > 0]
    bounds = None if not nonzero else [
        min(x for x, _ in nonzero), min(y for _, y in nonzero),
        max(x for x, _ in nonzero) + 1, max(y for _, y in nonzero) + 1,
    ]
    return {
        "nonzero_bbox": bounds,
        "nonzero_pixels": len(nonzero),
        "max_abs_vs_atlas": max(errors),
        "mean_abs_vs_atlas": sum(errors) / len(errors),
        "different_pixels_vs_atlas": sum(error != 0 for error in errors),
        "unexpected_nonzero_outside_expected_rect": sum(
            1 for y in range(SIZE) for x in range(SIZE)
            if not (9 <= x < 16 and 9 <= y < 22) and grid[y][x] != 0
        ),
    }


def save_rgb(path: Path, grid: list[list[int]]) -> None:
    image = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    pixels = image.load()
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            pixels[x, y] = (value, value, value)
    image.save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path, help="exact 9,216-byte readback of nwDiffRaw")
    parser.add_argument("--out", type=Path, required=True,
                        help="new, unused directory for decoded images and report")
    args = parser.parse_args()
    output = args.out.expanduser().resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output path: {output}")
    output.mkdir(parents=True)
    crops = read_crops(args.raw)
    expected = expected_atlas()
    names = ("rotation0-text", "rotation0-grid", "rotation90-text", "rotation90-grid")
    normalized = [normalise(crop, i >= 2) for i, crop in enumerate(crops)]
    report = {
        "source": str(args.raw.resolve()),
        "raw_bytes": args.raw.stat().st_size,
        "format": "BGRA8; comparison reads B channel",
        "atlas_expected_dimensions": [7, 13],
        "results": {},
        "pairwise_rotation0_max_abs": 0,
        "pairwise_rotation90_max_abs": 0,
    }
    for name, crop, grid in zip(names, crops, normalized):
        # Retain both the raw physical crop and its rotation-normalized view.
        raw_grid = [[blue(crop, x, y) for x in range(SIZE)] for y in range(SIZE)]
        save_rgb(output / f"{name}-physical.png", raw_grid)
        save_rgb(output / f"{name}-normalized.png", grid)
        report["results"][name] = summarize(grid, expected)
    for a, b, key in ((normalized[0], normalized[1], "pairwise_rotation0_max_abs"),
                      (normalized[2], normalized[3], "pairwise_rotation90_max_abs")):
        report[key] = max(abs(a[y][x] - b[y][x]) for y in range(SIZE) for x in range(SIZE))
    report["interpretation"] = (
        "Compare per-path normalized crops and atlas agreement. Large difference between text/grid "
        "at one rotation implicates geometry/UV or path sampling; equal rotation-normalized outputs "
        "with matching atlas imply the paths share correct sampling."
    )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
