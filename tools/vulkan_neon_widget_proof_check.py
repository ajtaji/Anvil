#!/usr/bin/env python3
"""Independent source/report/pixel oracle for vulkanNeonWidgetProof.

The checker does not import the compiler, board runner, Vulkan implementation,
Neon implementation, or production adapter. It pins the public-object call
path in source, decodes the returned 64-word report, and samples either the
800x1280 raw BGRA scanout or board_run's independently decoded 1280x800 PNG.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetProof.pi4"
SCENE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAcceptanceScene.pbi"
W, H, PITCH = 800, 1280, 3200
REPORT_WORDS, REPORT_BYTES = 64, 256
MAGIC, TAIL = 0x4157564E, 0x4E565741
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def argb(r: int, g: int, b: int) -> int:
    return 0xFF000000 | (r << 16) | (g << 8) | b


BG = argb(33, 34, 37)
PANEL = argb(37, 38, 41)
HEAD = argb(43, 44, 47)
ACCENT = argb(90, 189, 208)
LIST_BG = argb(30, 31, 34)
SELECTED = argb((90 * 30 + 50) // 100,
                (189 * 30 + 50) // 100,
                (208 * 34 + 50) // 100)

# Physical attachment coordinates, exact packed BGRA word, independent reason.
PROBES = (
    ((400, 100), BG, "ground below the menu bar"),
    ((700, 10), HEAD, "menu bar face"),
    ((30, 150), PANEL, "panel body"),
    ((700, 125), HEAD, "panel header"),
    ((25, 125), ACCENT, "panel accent tab"),
    ((700, 205), LIST_BG, "unselected list row"),
    ((700, 225), SELECTED, "selected list row"),
    ((700, 263), LIST_BG, "last pixel inside list clip"),
    ((700, 264), PANEL, "first pixel below list clip"),
    ((15, 40), HEAD, "open FILE drop-down body"),
    ((200, 40), BG, "ground outside open drop-down"),
    ((700, 300), PANEL, "lower panel body"),
)


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def body(text: str, name: str) -> str:
    marker = f"Procedure.i {name}("
    start = text.find(marker)
    if start < 0:
        marker = f"Procedure {name}("
        start = text.find(marker)
    if start < 0:
        fail(f"missing procedure {name}")
    end = text.find("EndProcedure", start)
    if end < 0:
        fail(f"unterminated procedure {name}")
    return text[start:end]


def check_source() -> int:
    payload = PAYLOAD.read_text(encoding="utf-8")
    scene = SCENE.read_text(encoding="utf-8")
    required = (
        'XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"',
        'XIncludeFile "RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAcceptanceScene.pbi"',
        "vkCreateInstance(@ici, 0, @inst)",
        "vkEnumeratePhysicalDevices(inst, @count, @phys)",
        "vkCreateDevice(phys, @dci, 0, @dev)",
        "vkGetDeviceQueue(dev, 0, 0, @queue)",
        "vkCreateCommandPool(dev, @pci, 0, @pool)",
        "vkCreateImage(dev, @imageInfo, 0, @image)",
        "vkAllocateMemory(dev, @alloc, 0, @memory)",
        "vkBindImageMemory(dev, image, memory, 0)",
        "vkCreateImageView(dev, @viewInfo, 0, @view)",
        "vkCreateRenderPass(dev, @passInfo, 0, @renderPass)",
        "vkCreateFramebuffer(dev, @frameInfo, 0, @framebuffer)",
        "NvwaPrime()",
        "NeonVkChromeCreateWithCapacities(phys, dev, queue, pool, renderPass, framebuffer",
        "rc = nwCapacityFrame()",
        "NeonVkChromeBoxBatchBegin()",
        "NeonVkChromeBoxBatchEnd()",
        "NvwaRenderFrame(@nwClear[0], imageBase, imagePitch)",
        "DisplayDmaBind()",
        "DisplayDmaOps() - dmaBefore",
        "NeonVkChromeDestroy()",
        "ProcedureReturn nwReturn(#NW_OK)",
    )
    for needle in required:
        if needle not in payload:
            fail(f"payload public production path missing: {needle}")

    forbidden = (
        "vk_backend_test.pbi", "vulkan_production_probe", "PokeL(imageBase",
        "PokeL(#NW_DSI_SCAN", "DisplayUseDma(0)\n  DisplayBlit",
        "V3dCl", "neon_Draw(", "neon_Vertex(", "reboot", "reset 0",
        "flash ", "boot write", "kernel8.img",
    )
    payload_code = "\n".join(line for line in payload.splitlines()
                               if not line.lstrip().startswith(";"))
    for needle in forbidden:
        if needle.lower() in payload_code.lower():
            fail(f"payload contains forbidden fake/fallback/private/persistent path: {needle}")

    compose = body(scene, "NvwaCompose")
    scene_required = (
        "Neon_Panel(", "Neon_ListBegin(", "Neon_ListItem(",
        "Neon_ListEnd()", "Neon_MenuBarBegin(", "Neon_MenuBegin(",
        "Neon_MenuItem(", "Neon_MenuSeparator()", "Neon_MenuBarEnd()",
    )
    for needle in scene_required:
        if needle not in compose:
            fail(f"acceptance scene omits real widget call: {needle}")
    if 'Neon_TextTex(#NEON_FONT_UI, #NVWA_TEXT_X, #NVWA_TEXT_Y, "VULKAN PATH", Neon_C_Text)' not in compose:
        fail("acceptance scene omits the public textured-text draw")
    for needle in ("NeonVkChromeBox(", "NeonVkChromeText(",
                   "NeonFrameBegin(", "NeonFrameEnd("):
        if needle in compose:
            fail(f"scene bypasses widget/adapter ownership through {needle}")

    exact_constants = {
        "NVWA_EXPECT_BOX_CALLS": 35,
        "NVWA_EXPECT_TEXT_CALLS": 12,
        "NVWA_EXPECT_GLYPH_QUADS": 74,
        "NVWA_EXPECT_QUADS": 109,
        "NVWA_EXPECT_DRAWS": 47,
        "NVWA_EXPECT_VERTICES": 654,
        "NVWA_EXPECT_SCISSOR_CALLS": 4,
    }
    for name, value in exact_constants.items():
        if not re.search(rf"(?m)^\s*#{name}\s*=\s*{value}\b", scene):
            fail(f"scene exact constant {name} is not {value}")
    return len(required) + len(forbidden) + len(scene_required) + 4 + len(exact_constants)


def report_from_bytes(data: bytes) -> tuple[int, ...]:
    if len(data) != REPORT_BYTES:
        fail(f"report must be exactly {REPORT_BYTES} bytes, got {len(data)}")
    return struct.unpack("<64I", data)


def check_report_bytes(data: bytes) -> int:
    r = report_from_bytes(data)
    exact = {
        0: MAGIC, 1: 0, 2: 9, 3: REPORT_BYTES,
        17: 0, 18: 0, 19: 0,
        20: 1, 21: 0, 22: 0, 23: 1,
        24: 47, 25: 654, 26: 47, 27: 654,
        28: 35, 29: 12, 30: 74, 31: 4,
        32: 1, 33: 0, 34: 0, 35: 0, 36: 0, 37: 1,
        38: len(PROBES), 51: 0, 53: 1,
        54: 0x181, 55: 1, 56: 1, 57: 0,
        58: 0x3DCCCCCD, 59: 0x3E4CCCCD,
        60: 0x3E99999A, 61: 0x3F800000,
        62: 3505, 63: TAIL,
    }
    for slot, expected in exact.items():
        if r[slot] != expected:
            fail(f"report[{slot}] is 0x{r[slot]:08X}, expected 0x{expected:08X}")
    for slot in range(4, 17):
        if r[slot] == 0:
            fail(f"public Vulkan object/report field {slot} is zero")
    if r[16] != PITCH:
        fail(f"attachment row pitch is {r[16]}, expected {PITCH}")
    if r[15] < W * H * 4:
        fail(f"attachment allocation is too small: {r[15]}")
    for index, (_, expected, meaning) in enumerate(PROBES):
        if r[39 + index] != expected:
            fail(f"report probe {index} ({meaning}) is 0x{r[39+index]:08X}, expected 0x{expected:08X}")
    return len(exact) + 13 + 2 + len(PROBES)


def read_report(path: Path) -> bytes:
    return path.read_bytes()


def read_run_report(path: Path) -> tuple[dict, bytes]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        fail("board_run JSON root is not an object")
    trace = record.get("trace")
    if not isinstance(trace, dict):
        fail("board_run JSON has no trace object")
    if trace.get("bytes") != REPORT_BYTES:
        fail(f"trace.bytes is {trace.get('bytes')!r}, expected {REPORT_BYTES}")
    try:
        data = bytes.fromhex(trace.get("hex", ""))
    except ValueError as exc:
        raise CheckError(f"trace.hex is malformed: {exc}") from exc
    if record.get("failures") != []:
        fail("board_run failures list is not empty")
    if record.get("x0") != record.get("expected_x0"):
        fail("board_run x0 differs from expected_x0")
    return record, data


def check_raw(path: Path) -> int:
    data = path.read_bytes()
    if len(data) != W * H * 4:
        fail(f"raw screenshot must be exactly {W*H*4} bytes, got {len(data)}")
    checks = 0
    for (x, y), expected, meaning in PROBES:
        got = struct.unpack_from("<I", data, y * PITCH + x * 4)[0]
        if got != expected:
            fail(f"{meaning}: raw ({x},{y}) is 0x{got:08X}, expected 0x{expected:08X}")
        checks += 1
    return checks


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def decode_png(path: Path) -> tuple[int, int, list[bytes]]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        fail(f"{path} is not a PNG")
    pos, ihdr, packed, ended = 8, None, bytearray(), False
    while pos < len(data):
        if pos + 12 > len(data): fail("truncated PNG chunk")
        size = struct.unpack_from(">I", data, pos)[0]
        end = pos + 12 + size
        if end > len(data): fail("truncated PNG body")
        tag, part = data[pos+4:pos+8], data[pos+8:pos+8+size]
        if (binascii.crc32(tag + part) & 0xFFFFFFFF) != struct.unpack_from(">I", data, pos+8+size)[0]:
            fail("PNG chunk CRC mismatch")
        if tag == b"IHDR": ihdr = struct.unpack(">IIBBBBB", part)
        elif tag == b"IDAT": packed.extend(part)
        elif tag == b"IEND": ended = True; pos = end; break
        pos = end
    if ihdr is None or not packed or not ended or pos != len(data):
        fail("PNG structure is incomplete")
    width, height, depth, colour, comp, filtering, interlace = ihdr
    if (depth, colour, comp, filtering, interlace) != (8, 2, 0, 0, 0):
        fail("PNG must be 8-bit non-interlaced RGB")
    raw = zlib.decompress(bytes(packed)); stride = width * 3
    if len(raw) != height * (stride + 1): fail("PNG inflated length is wrong")
    rows, previous, at = [], bytearray(stride), 0
    for _ in range(height):
        kind = raw[at]; current = bytearray(raw[at+1:at+1+stride]); at += stride + 1
        if kind > 4: fail("PNG uses unknown filter")
        for i in range(stride):
            left = current[i-3] if i >= 3 else 0
            above = previous[i]; corner = previous[i-3] if i >= 3 else 0
            if kind == 1: current[i] = (current[i] + left) & 255
            elif kind == 2: current[i] = (current[i] + above) & 255
            elif kind == 3: current[i] = (current[i] + (left+above)//2) & 255
            elif kind == 4: current[i] = (current[i] + _paeth(left, above, corner)) & 255
        rows.append(bytes(current)); previous = current
    return width, height, rows


def check_png(path: Path, record: dict | None = None) -> int:
    width, height, rows = decode_png(path)
    if (width, height) != (H, W):
        fail(f"board screenshot is {width}x{height}, expected {H}x{W}")
    if record is not None:
        shot = record.get("shot_header", {})
        expected = {"w": H, "h": W, "pitch": PITCH, "rot": 90,
                    "panel_w": W, "panel_h": H, "bpp": 4,
                    "bytes": W*H*4, "src_name": "dsi"}
        for key, value in expected.items():
            if shot.get(key) != value:
                fail(f"shot_header.{key} is {shot.get(key)!r}, expected {value!r}")
        picture = record.get("picture", {})
        digest = hashlib.sha256(b"".join(rows)).hexdigest()
        if picture.get("pixel_sha256") != digest:
            fail("decoded PNG pixels disagree with board_run pixel_sha256")
    checks = 0
    for (x, y), expected, meaning in PROBES:
        er, eg, eb = (expected >> 16) & 255, (expected >> 8) & 255, expected & 255
        # board_run rotates physical (x,y) to PNG logical (y, 799-x).
        lx, ly = y, (W - 1) - x
        got = tuple(rows[ly][lx*3:lx*3+3])
        if got != (er, eg, eb):
            fail(f"{meaning}: PNG physical ({x},{y}) is {got}, expected {(er,eg,eb)}")
        checks += 1
    return checks


def synthetic() -> tuple[bytes, bytes]:
    words = [0] * REPORT_WORDS
    exact = {0: MAGIC, 1: 0, 2: 9, 3: REPORT_BYTES, 17: 0, 18: 0, 19: 0,
             20: 1, 21: 0, 22: 0, 23: 1, 24: 47, 25: 654, 26: 47,
             27: 654, 28: 35, 29: 12, 30: 74, 31: 4, 32: 1, 37: 1, 38: 12,
             53: 1, 54: 0x181, 55: 1, 56: 1, 57: 0, 58: 0x3DCCCCCD,
             59: 0x3E4CCCCD, 60: 0x3E99999A, 61: 0x3F800000,
             62: 3505, 63: TAIL}
    exact.update({slot: 0x1000 + slot for slot in range(4, 17)})
    exact[15], exact[16] = W*H*4, PITCH
    for slot, value in exact.items(): words[slot] = value
    pixels = bytearray(struct.pack("<I", BG) * (W*H))
    for index, ((x, y), value, _) in enumerate(PROBES):
        words[39+index] = value
        struct.pack_into("<I", pixels, y*PITCH + x*4, value)
    return struct.pack("<64I", *words), bytes(pixels)


def self_test() -> int:
    report, pixels = synthetic()
    checks = check_report_bytes(report)
    with tempfile.TemporaryDirectory(prefix="anvil-nvwa-") as td:
        raw = Path(td) / "scene.bgra"; raw.write_bytes(pixels)
        checks += check_raw(raw)
    # Discrimination: one report count and one pixel mutation must be caught.
    caught = 0
    broken = bytearray(report); struct.pack_into("<I", broken, 24*4, 46)
    try: check_report_bytes(bytes(broken))
    except CheckError: caught += 1
    broken_pixels = bytearray(pixels); struct.pack_into("<I", broken_pixels, 100*PITCH + 400*4, HEAD)
    with tempfile.TemporaryDirectory(prefix="anvil-nvwa-mutant-") as td:
        raw = Path(td) / "bad.bgra"; raw.write_bytes(broken_pixels)
        try: check_raw(raw)
        except CheckError: caught += 1
    if caught != 2: fail("self-test mutants were not rejected")
    return checks + caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, help="256-byte x0 report")
    ap.add_argument("--run-json", type=Path, help="board_run JSON with 256-byte trace")
    ap.add_argument("--raw", type=Path, help="800x1280 raw BGRA capture")
    ap.add_argument("--png", type=Path, help="board_run 1280x800 rotated PNG")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    try:
        total = check_source(); labels = ["production source path"]
        record = None
        if args.self_test:
            total += self_test(); labels.append("discriminating synthetic oracle")
        if args.report:
            total += check_report_bytes(read_report(args.report)); labels.append("report")
        if args.run_json:
            record, data = read_run_report(args.run_json)
            total += check_report_bytes(data); labels.append("board_run report")
        if args.raw:
            total += check_raw(args.raw); labels.append("raw BGRA pixels")
        if args.png:
            total += check_png(args.png, record); labels.append("rotated PNG pixels")
    except (CheckError, OSError, ValueError, KeyError, StopIteration, zlib.error) as exc:
        print(f"vulkan_neon_widget_proof_check: FAIL - {exc}", file=sys.stderr)
        return 1
    print(f"vulkan_neon_widget_proof_check: PASS - {', '.join(labels)}; {total} exact checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
