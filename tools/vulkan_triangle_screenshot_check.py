#!/usr/bin/env python3
"""Validate a board_run capture of vulkanTriangleProof.

The payload renders a 799 x 1279 image into the top-left of the physical
800 x 1280 DSI scanout.  The monitor records that physical scanout and emits
an upright 1280 x 800 PNG by applying its 90-degree rotation map.  Therefore
the triangle in the PNG must point left:

    apex       (319.75, 399.50)
    upper base (959.25, 199.75)
    lower base (959.25, 599.25)

This is deliberately a host-side oracle.  It does not import board_run or any
Vulkan/compiler code.  It checks the JSON/PNG pair, independently decodes the
PNG, and samples well away from all three triangle edges so raster coverage
and antialiasing decisions on edge pixels are not part of the verdict.

Usage:
    python tools/vulkan_triangle_screenshot_check.py RUN.json [RUN.png]
    python tools/vulkan_triangle_screenshot_check.py --self-test
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

CAPTURE_W = 1280
CAPTURE_H = 800
PANEL_W = 800
PANEL_H = 1280
PANEL_PITCH = 3200
PANEL_BYTES = PANEL_PITCH * PANEL_H
ROTATION = 90

VIEW_W = 799
VIEW_H = 1279
CLEAR = bytes((51, 128, 178))
GREEN = bytes((0, 255, 0))

# Source Vulkan vertices are (399.5,319.75), (199.75,959.25), and
# (599.25,959.25).  The monitor's 90-degree map has physical=(799-y,x),
# hence logical=(physical_y,799-physical_x).  This order is counter-clockwise.
TRIANGLE = (
    (319.75, 399.50),
    (959.25, 199.75),
    (959.25, 599.25),
)

EDGE_MARGIN = 24.0
SAMPLE_STEP = 8
MIN_GEOMETRY_RATIO = 0.985
EXPECTED_AREA = 0.5 * 399.5 * 639.5
MIN_GREEN_PIXELS = int(EXPECTED_AREA * 0.95)
MAX_GREEN_PIXELS = int(EXPECTED_AREA * 1.05)
MIN_CLEAR_PIXELS = 850_000


class CheckError(Exception):
    """A malformed artifact, as distinct from a valid picture that is wrong."""


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(path: Path) -> tuple[int, int, list[bytes]]:
    """Decode an 8-bit, non-interlaced RGB PNG and verify every chunk CRC."""
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise CheckError(f"{path} is not a PNG")

    pos = len(PNG_SIGNATURE)
    ihdr = None
    idat = bytearray()
    saw_iend = False
    while pos < len(data):
        if pos + 12 > len(data):
            raise CheckError("truncated PNG chunk header")
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        end = pos + 12 + size
        if end > len(data):
            raise CheckError("truncated PNG chunk body")
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + size]
        got_crc = struct.unpack(">I", data[pos + 8 + size:end])[0]
        want_crc = binascii.crc32(tag + body) & 0xFFFFFFFF
        if got_crc != want_crc:
            raise CheckError(f"bad {tag.decode('ascii', 'replace')} chunk CRC")
        if tag == b"IHDR":
            if ihdr is not None or size != 13:
                raise CheckError("invalid duplicate or sized IHDR")
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.extend(body)
        elif tag == b"IEND":
            if size != 0:
                raise CheckError("IEND carries unexpected data")
            saw_iend = True
            pos = end
            break
        pos = end

    if ihdr is None or not idat or not saw_iend:
        raise CheckError("PNG is missing IHDR, IDAT, or IEND")
    if pos != len(data):
        raise CheckError("PNG carries bytes after IEND")

    width, height, depth, colour, compression, filtering, interlace = ihdr
    if (depth, colour, compression, filtering, interlace) != (8, 2, 0, 0, 0):
        raise CheckError(
            "PNG must be 8-bit non-interlaced RGB with standard compression")

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise CheckError(f"PNG zlib stream is invalid: {exc}") from exc
    stride = width * 3
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise CheckError(
            f"PNG inflates to {len(raw)} bytes, expected exactly {expected}")

    rows: list[bytes] = []
    previous = bytearray(stride)
    at = 0
    for y in range(height):
        filter_type = raw[at]
        current = bytearray(raw[at + 1:at + 1 + stride])
        at += stride + 1
        if filter_type > 4:
            raise CheckError(f"PNG row {y} has unknown filter {filter_type}")
        for i in range(stride):
            left = current[i - 3] if i >= 3 else 0
            above = previous[i]
            upper_left = previous[i - 3] if i >= 3 else 0
            if filter_type == 1:
                current[i] = (current[i] + left) & 0xFF
            elif filter_type == 2:
                current[i] = (current[i] + above) & 0xFF
            elif filter_type == 3:
                current[i] = (current[i] + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                current[i] = (current[i] +
                              _paeth(left, above, upper_left)) & 0xFF
        rows.append(bytes(current))
        previous = current
    return width, height, rows


def _integer(value: object, field: str, failures: list[str]) -> int | None:
    if type(value) is not int:
        failures.append(f"{field} is missing or is not an integer")
        return None
    return value


def check_metadata(record: dict, width: int, height: int,
                   rows: list[bytes]) -> list[str]:
    failures: list[str] = []
    if record.get("failures") != []:
        failures.append("board_run JSON does not contain an empty failures list")

    shot = record.get("shot_header")
    picture = record.get("picture")
    if not isinstance(shot, dict):
        return failures + ["shot_header is missing from board_run JSON"]
    if not isinstance(picture, dict):
        return failures + ["picture is missing from board_run JSON"]

    expected_shot = {
        "w": CAPTURE_W,
        "h": CAPTURE_H,
        "pitch": PANEL_PITCH,
        "rot": ROTATION,
        "panel_w": PANEL_W,
        "panel_h": PANEL_H,
        "bpp": 4,
        "bytes": PANEL_BYTES,
    }
    for key, want in expected_shot.items():
        if shot.get(key) != want:
            failures.append(
                f"shot_header.{key} is {shot.get(key)!r}, expected {want}")
    if shot.get("src_name") != "dsi":
        failures.append("shot_header.src_name is not 'dsi'")

    before = _integer(record.get("shot_seq_before"), "shot_seq_before", failures)
    after = _integer(shot.get("seq"), "shot_header.seq", failures)
    if before is not None and after is not None and after <= before:
        failures.append(
            f"stale capture: sequence {after} did not advance past {before}")

    if picture.get("width") != CAPTURE_W or picture.get("height") != CAPTURE_H:
        failures.append("picture metadata is not 1280 x 800")
    if picture.get("bytes_per_pixel") != 4:
        failures.append("picture metadata does not describe the board's 4-byte pixels")
    if (width, height) != (CAPTURE_W, CAPTURE_H):
        failures.append(f"PNG is {width} x {height}, expected 1280 x 800")
    if picture.get("width") != width or picture.get("height") != height:
        failures.append("PNG dimensions disagree with picture metadata")

    digest = hashlib.sha256(b"".join(rows)).hexdigest()
    if picture.get("pixel_sha256") != digest:
        failures.append("PNG pixels do not match picture.pixel_sha256")
    return failures


def _edges() -> tuple[tuple[float, float, float, float], ...]:
    edges = []
    for i, (ax, ay) in enumerate(TRIANGLE):
        bx, by = TRIANGLE[(i + 1) % 3]
        length = math.hypot(bx - ax, by - ay)
        edges.append((ax, ay, (bx - ax) / length, (by - ay) / length))
    return tuple(edges)


def check_pixels(width: int, height: int,
                 rows: list[bytes]) -> tuple[list[str], dict[str, float | int]]:
    failures: list[str] = []
    if (width, height) != (CAPTURE_W, CAPTURE_H):
        return ["geometry cannot be checked at the wrong PNG dimensions"], {}

    green_pixels = 0
    clear_pixels = 0
    for row in rows:
        for at in range(0, len(row), 3):
            pixel = row[at:at + 3]
            if pixel == GREEN:
                green_pixels += 1
            elif pixel == CLEAR:
                clear_pixels += 1

    if not MIN_GREEN_PIXELS <= green_pixels <= MAX_GREEN_PIXELS:
        failures.append(
            f"green population is {green_pixels}, expected "
            f"{MIN_GREEN_PIXELS}..{MAX_GREEN_PIXELS}")
    if clear_pixels < MIN_CLEAR_PIXELS:
        failures.append(
            f"blue-grey clear population is only {clear_pixels}, expected at least "
            f"{MIN_CLEAR_PIXELS}")

    edges = _edges()
    inside = inside_green = outside = outside_clear = 0
    # The odd viewport occupies logical x=0..1278 and y=1..799 after the
    # rotation.  The unused top row and rightmost column belong to whatever
    # was already on the 800 x 1280 panel and are intentionally not judged.
    for y in range(1 + SAMPLE_STEP // 2, CAPTURE_H, SAMPLE_STEP):
        row = rows[y]
        py = y + 0.5
        for x in range(SAMPLE_STEP // 2, VIEW_H, SAMPLE_STEP):
            px = x + 0.5
            distances = [
                dx * (py - ay) - dy * (px - ax)
                for ax, ay, dx, dy in edges
            ]
            pixel = row[x * 3:x * 3 + 3]
            if min(distances) >= EDGE_MARGIN:
                inside += 1
                inside_green += pixel == GREEN
            elif min(distances) <= -EDGE_MARGIN:
                outside += 1
                outside_clear += pixel == CLEAR

    if inside == 0 or outside == 0:
        failures.append("geometry oracle selected no safe interior or exterior pixels")
        inside_ratio = outside_ratio = 0.0
    else:
        inside_ratio = inside_green / inside
        outside_ratio = outside_clear / outside
        if inside_ratio < MIN_GEOMETRY_RATIO:
            failures.append(
                f"only {inside_green}/{inside} ({inside_ratio:.2%}) safe triangle "
                "samples are green")
        if outside_ratio < MIN_GEOMETRY_RATIO:
            failures.append(
                f"only {outside_clear}/{outside} ({outside_ratio:.2%}) safe "
                "outside samples are blue-grey")

    metrics: dict[str, float | int] = {
        "green_pixels": green_pixels,
        "clear_pixels": clear_pixels,
        "inside_samples": inside,
        "inside_green": inside_green,
        "inside_ratio": inside_ratio,
        "outside_samples": outside,
        "outside_clear": outside_clear,
        "outside_ratio": outside_ratio,
    }
    return failures, metrics


def validate(json_path: Path, png_path: Path) -> tuple[list[str], dict[str, float | int]]:
    try:
        record = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise CheckError("board_run JSON root is not an object")
        width, height, rows = decode_png(png_path)
    except (OSError, json.JSONDecodeError, CheckError) as exc:
        return [str(exc)], {}
    failures = check_metadata(record, width, height, rows)
    pixel_failures, metrics = check_pixels(width, height, rows)
    failures.extend(pixel_failures)
    return failures, metrics


def _png(rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        payload = tag + body
        return (struct.pack(">I", len(body)) + payload +
                struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + row for row in rows)
    ihdr = struct.pack(">IIBBBBB", CAPTURE_W, CAPTURE_H, 8, 2, 0, 0, 0)
    return (PNG_SIGNATURE + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _fixture_rows(sheared: bool = False) -> list[bytes]:
    """Synthetic antialiased-edge picture; the safe zones remain exact."""
    edges = _edges()
    rows: list[bytes] = []
    for y in range(CAPTURE_H):
        row = bytearray(CLEAR * CAPTURE_W)
        for x in range(CAPTURE_W):
            px = x + 0.5
            py = y + 0.5
            distances = [
                dx * (py - ay) - dy * (px - ax)
                for ax, ay, dx, dy in edges
            ]
            signed = min(distances)
            if signed >= 1.0:
                colour = GREEN
            elif signed > -1.0:
                # A deliberately non-exact edge colour proves the gate does
                # not demand a particular raster coverage convention.
                colour = bytes((25, 191, 89))
            else:
                continue
            if sheared:
                # Preserve approximately the same amount of green while
                # moving it into the wrapped/sheared shape an odd-pitch copy
                # can produce.  Colour totals alone must not pass this.
                sx = (x + y) % CAPTURE_W
                row[sx * 3:sx * 3 + 3] = colour
            else:
                row[x * 3:x * 3 + 3] = colour
        rows.append(bytes(row))
    return rows


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="vulkan-shot-check-") as raw_tmp:
        tmp = Path(raw_tmp)
        good_rows = _fixture_rows()
        good_png = tmp / "good.png"
        good_json = tmp / "good.json"
        good_png.write_bytes(_png(good_rows))
        record = {
            "failures": [],
            "shot_seq_before": 40,
            "shot_header": {
                "seq": 41, "w": CAPTURE_W, "h": CAPTURE_H,
                "pitch": PANEL_PITCH, "rot": ROTATION,
                "panel_w": PANEL_W, "panel_h": PANEL_H,
                "bpp": 4, "bytes": PANEL_BYTES, "src_name": "dsi",
            },
            "picture": {
                "width": CAPTURE_W, "height": CAPTURE_H,
                "bytes_per_pixel": 4,
                "pixel_sha256": hashlib.sha256(b"".join(good_rows)).hexdigest(),
            },
        }
        good_json.write_text(json.dumps(record), encoding="utf-8")
        failures, _ = validate(good_json, good_png)
        if failures:
            print("self-test good fixture failed: " + "; ".join(failures))
            return 1

        record["shot_header"]["seq"] = 40
        good_json.write_text(json.dumps(record), encoding="utf-8")
        failures, _ = validate(good_json, good_png)
        if not any("stale capture" in failure for failure in failures):
            print("self-test did not reject a stale capture")
            return 1

        record["shot_header"]["seq"] = 41
        sheared_rows = _fixture_rows(sheared=True)
        sheared_png = tmp / "sheared.png"
        sheared_png.write_bytes(_png(sheared_rows))
        record["picture"]["pixel_sha256"] = hashlib.sha256(
            b"".join(sheared_rows)).hexdigest()
        good_json.write_text(json.dumps(record), encoding="utf-8")
        failures, _ = validate(good_json, sheared_png)
        if not any("safe triangle" in failure for failure in failures):
            print("self-test did not reject a same-colour sheared triangle")
            return 1

    print("vulkan triangle screenshot checker self-test: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", nargs="?", type=Path,
                        help="board_run JSON result")
    parser.add_argument("png", nargs="?", type=Path,
                        help="matching PNG (default: JSON path with .png)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        if args.json or args.png:
            parser.error("--self-test takes no artifact paths")
        return self_test()
    if args.json is None:
        parser.error("a board_run JSON path is required")
    png_path = args.png if args.png is not None else args.json.with_suffix(".png")
    failures, metrics = validate(args.json, png_path)

    if metrics:
        print(
            f"pixels: green {metrics['green_pixels']}, clear "
            f"{metrics['clear_pixels']}; safe geometry: inside "
            f"{metrics['inside_green']}/{metrics['inside_samples']} "
            f"({metrics['inside_ratio']:.2%}), outside "
            f"{metrics['outside_clear']}/{metrics['outside_samples']} "
            f"({metrics['outside_ratio']:.2%})")
    if failures:
        print("vulkan triangle screenshot: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("vulkan triangle screenshot: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
