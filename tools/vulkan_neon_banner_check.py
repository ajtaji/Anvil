"""Check bounded Pi 4 Vulkan banner captures against the shared RGB asset.

The three files are tightly packed physical BGRA strips from the returning
mode-3 Neon/Vulkan diagnostic. This checks the actual logo pixels and fixed
geometry independently of the renderer's atlas and coordinate code.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "Anvil/Graphics/anvil_logo.pbi"
MAGIC = 0x4157564E
TAIL = 0x4E565741
LOGO_W, LOGO_H = 76, 74
BAND_H = 120
BG = bytes((40, 0, 0, 255))
STEEL = bytes((240, 232, 226, 255))
ORANGE = bytes((48, 148, 255, 255))
WARM = bytes((64, 176, 255, 255))
RULE_DARK = bytes((20, 40, 60, 255))
GLINT_X, GLINT_Y = 37, 25
CAPTURES = (
    (0, 800, 1280, 0, 0, 800, 120, 0x07000000, 384000),
    (90, 1280, 800, 680, 0, 120, 1280, 0x07060000, 614400),
    (270, 1280, 800, 0, 0, 120, 1280, 0x07100000, 614400),
)


def logo_rgb() -> bytes:
    source = LOGO.read_text(encoding="utf-8")
    rows = re.findall(r"^\s*Data\.b\s+([^\r\n]+)", source, re.MULTILINE)
    raw = bytes(int(v, 16) for row in rows for v in re.findall(r"\$([0-9A-Fa-f]{2})", row))
    assert len(raw) == LOGO_W * LOGO_H * 3, "logo asset length"
    return raw


def physical_point(rotation: int, logical_w: int, logical_h: int,
                   x: int, y: int) -> tuple[int, int]:
    if rotation == 90:
        return logical_h - 1 - y, x
    if rotation == 270:
        return y, logical_w - 1 - x
    assert rotation == 0
    return x, y


def pixel(capture: bytes, spec: tuple[int, ...], x: int, y: int) -> bytes:
    rot, lw, lh, left, top, width, height, _, length = spec
    assert len(capture) == length, f"rotation {rot} capture length"
    px, py = physical_point(rot, lw, lh, x, y)
    assert left <= px < left + width and top <= py < top + height, (
        f"rotation {rot} logical ({x},{y}) outside captured strip")
    off = ((py - top) * width + px - left) * 4
    return capture[off:off + 4]


def expected_logo_pixel(asset: bytes, sx: int, sy: int,
                        glint_x: int = GLINT_X) -> bytes:
    if (sx, sy) == (glint_x, GLINT_Y):
        return WARM
    if abs(sx - glint_x) + abs(sy - GLINT_Y) == 1:
        return STEEL
    off = (sy * LOGO_W + sx) * 3
    r, g, b = asset[off:off + 3]
    return bytes((b, g, r, 255))


def check_report(data: bytes) -> int:
    assert len(data) == 256, "report length"
    w = struct.unpack("<64I", data)
    assert (w[0], w[1], w[3], w[63]) == (MAGIC, 0, 256, TAIL), "report header/status/tail"
    assert w[38] == 3, "capture count"
    assert tuple(w[39:42]) == tuple(s[7] for s in CAPTURES), "capture addresses"
    assert tuple(w[42:45]) == tuple(s[8] for s in CAPTURES), "capture lengths"
    assert tuple(w[45:48]) == (0, 90, 270), "rotation order"
    assert tuple(w[48:51]) == (BAND_H, LOGO_W, LOGO_H), "banner/logo dimensions"
    assert w[51] == 0 and w[36] == 0, "Vulkan fault/backend error"
    return 15


def check_mode4_report(data: bytes) -> int:
    assert len(data) == 256, "report length"
    w = struct.unpack("<64I", data)
    assert (w[0], w[1], w[3], w[63]) == (MAGIC, 0, 256, TAIL), "mode4 header/status/tail"
    assert w[38] == 4, "mode4 capture count"
    assert tuple(w[39:43]) == (0x07000000, 0x07060000, 0x07100000, 0x071A0000), "mode4 addresses"
    assert tuple(w[43:47]) == (384000, 614400, 614400, 384000), "mode4 lengths"
    assert tuple(w[47:51]) == (0, 90, 270, 0), "mode4 rotations"
    assert w[24] == 0 and w[25] > 0, "TrueType slot/raster"
    assert w[26] > 0 and w[27] > 0 and w[26] != w[27], "TrueType width differs from bitmap"
    assert w[36] == 0 and w[51] == 0 and w[53] == 1, "fault/shutdown"
    return 20


def check_changed_capture(base: bytes, changed: bytes) -> int:
    spec = CAPTURES[0]
    assert len(base) == len(changed) == spec[8], "changed capture length"
    asset = logo_rgb()
    logo_x = spec[1] - LOGO_W - 12
    for sy in range(LOGO_H):
        for sx in range(LOGO_W):
            got = pixel(changed, spec, logo_x + sx, 12 + sy)
            want = expected_logo_pixel(asset, sx, sy, 55)
            assert got == want, f"changed logo ({sx},{sy}): {got.hex()} != {want.hex()}"
    glint_changes = clock_changes = 0
    for off in range(0, len(base), 4):
        if base[off:off + 4] == changed[off:off + 4]:
            continue
        index = off // 4
        x, y = index % spec[5], index // spec[5]
        if logo_x <= x < logo_x + LOGO_W and 12 <= y < 12 + LOGO_H:
            glint_changes += 1
        elif 500 <= x < logo_x and 94 <= y < 110:
            clock_changes += 1
        else:
            raise AssertionError(f"unexpected changed pixel ({x},{y})")
    assert glint_changes == 10, f"glint changed {glint_changes} pixels, expected 10"
    assert clock_changes > 0, "clock did not change"
    return LOGO_W * LOGO_H + glint_changes + clock_changes + 2


def check_captures(captures: tuple[bytes, bytes, bytes]) -> int:
    asset = logo_rgb()
    checks = 0
    for spec, capture in zip(CAPTURES, captures):
        rot, lw, lh, _, _, width, height, _, length = spec
        assert len(capture) == length == width * height * 4, f"rotation {rot} length"
        logo_x = lw - LOGO_W - 12
        # Exact every-pixel logo comparison also proves atlas RGB ordering,
        # sprite dimensions, right alignment, and both rotation transforms.
        for sy in range(LOGO_H):
            for sx in range(LOGO_W):
                got = pixel(capture, spec, logo_x + sx, 12 + sy)
                want = expected_logo_pixel(asset, sx, sy)
                assert got == want, f"rotation {rot} logo ({sx},{sy}): {got.hex()} != {want.hex()}"
                checks += 1
        for x, y, want in ((0, 0, BG), (20, 20, BG),
                           (24, 114, ORANGE), (100, 114, ORANGE),
                           (lw - 25, 114, ORANGE), (100, 115, RULE_DARK)):
            got = pixel(capture, spec, x, y)
            assert got == want, f"rotation {rot} anchor ({x},{y}): {got.hex()} != {want.hex()}"
            checks += 1
        # The shared renderer must place title, platform and build ink in
        # their fixed left-hand bands. Pixel-exact font shapes are already
        # covered by the 15-scene corpus; count only ink here.
        for name, box in (("title", (26, 12, 590, 62)),
                          ("platform", (28, 70, 590, 91)),
                          ("build", (28, 94, 590, 111))):
            x0, y0, x1, y1 = box
            ink = sum(pixel(capture, spec, x, y) != BG
                      for y in range(y0, y1) for x in range(x0, min(x1, lw - LOGO_W - 12)))
            assert ink > 8, f"rotation {rot} missing {name} ink"
            checks += 1
    return checks


def synthetic_capture(spec: tuple[int, ...], asset: bytes) -> bytes:
    rot, lw, lh, left, top, width, height, _, length = spec
    out = bytearray(BG * (width * height))
    def put(x: int, y: int, colour: bytes) -> None:
        px, py = physical_point(rot, lw, lh, x, y)
        if left <= px < left + width and top <= py < top + height:
            off = ((py - top) * width + px - left) * 4
            out[off:off + 4] = colour
    for x in range(24, lw - 24):
        put(x, 114, ORANGE)
        put(x, 115, RULE_DARK)
    logo_x = lw - LOGO_W - 12
    for sy in range(LOGO_H):
        for sx in range(LOGO_W):
            put(logo_x + sx, 12 + sy, expected_logo_pixel(asset, sx, sy))
    for x0, y0 in ((26, 12), (28, 70), (28, 94)):
        for dx in range(9):
            put(x0 + dx, y0 + 3, STEEL)
    assert len(out) == length
    return bytes(out)


def self_test() -> int:
    asset = logo_rgb()
    captures = tuple(synthetic_capture(spec, asset) for spec in CAPTURES)
    count = check_captures(captures)
    for i, spec in enumerate(CAPTURES):
        mutated = list(captures)
        bad = bytearray(mutated[i])
        rot, lw, lh, left, top, width, height, _, _ = spec
        px, py = physical_point(rot, lw, lh, lw - LOGO_W - 12 + 5, 12 + 5)
        bad[((py - top) * width + px - left) * 4] ^= 1
        mutated[i] = bytes(bad)
        try:
            check_captures(tuple(mutated))
        except AssertionError as error:
            assert f"rotation {rot} logo" in str(error)
        else:
            raise AssertionError(f"rotation {rot} hostile logo mutation passed")
    try:
        check_captures((captures[0][:-1], captures[1], captures[2]))
    except AssertionError as error:
        assert "length" in str(error)
    else:
        raise AssertionError("short capture passed")
    report = [0] * 64
    report[0], report[1], report[3], report[63] = MAGIC, 0, 256, TAIL
    report[38] = 3
    report[39:42] = [s[7] for s in CAPTURES]
    report[42:45] = [s[8] for s in CAPTURES]
    report[45:48] = [0, 90, 270]
    report[48:51] = [BAND_H, LOGO_W, LOGO_H]
    count += check_report(struct.pack("<64I", *report))
    mode4 = report.copy()
    mode4[38] = 4
    mode4[39:43] = [0x07000000, 0x07060000, 0x07100000, 0x071A0000]
    mode4[43:47] = [384000, 614400, 614400, 384000]
    mode4[47:51] = [0, 90, 270, 0]
    mode4[24:28] = [0, 2, 360, 485]
    mode4[53] = 1
    count += check_mode4_report(struct.pack("<64I", *mode4))
    changed = bytearray(captures[0])
    logo_x = CAPTURES[0][1] - LOGO_W - 12
    for sy in range(LOGO_H):
        for sx in range(LOGO_W):
            off = ((12 + sy) * 800 + logo_x + sx) * 4
            changed[off:off + 4] = expected_logo_pixel(asset, sx, sy, 55)
    off = (100 * 800 + 502) * 4
    changed[off:off + 4] = STEEL
    count += check_changed_capture(captures[0], bytes(changed))
    changed[0] ^= 1
    try:
        check_changed_capture(captures[0], bytes(changed))
    except AssertionError as error:
        assert "unexpected changed pixel" in str(error)
    else:
        raise AssertionError("out-of-region mode4 mutation passed")
    return count + 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path)
    ap.add_argument("--capture0", type=Path)
    ap.add_argument("--capture90", type=Path)
    ap.add_argument("--capture270", type=Path)
    ap.add_argument("--capture-changed", type=Path)
    ap.add_argument("--mode4", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    try:
        if args.self_test:
            print(f"banner checker self-test PASS: {self_test()} checks")
        paths = (args.capture0, args.capture90, args.capture270)
        if any(p is not None for p in paths):
            assert all(p is not None for p in paths), "provide all three captures"
            assert args.report is not None, "provide report with captures"
            count = (check_mode4_report if args.mode4 else check_report)(args.report.read_bytes())
            captures = tuple(p.read_bytes() for p in paths)
            count += check_captures(captures)
            if args.mode4:
                assert args.capture_changed is not None, "provide changed capture for mode4"
                count += check_changed_capture(captures[0], args.capture_changed.read_bytes())
            print(f"banner capture PASS: {count} checks")
        elif args.report is not None:
            count = (check_mode4_report if args.mode4 else check_report)(args.report.read_bytes())
            print(f"banner report PASS: {count} checks")
        else:
            assert args.self_test, "provide captures/report or --self-test"
    except (AssertionError, OSError, ValueError) as error:
        print(f"banner capture FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
