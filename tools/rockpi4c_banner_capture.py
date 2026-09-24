#!/usr/bin/env python3
"""Capture only the Rock Pi 4C banner and logo crops from active VOPB scanout."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import tempfile
import time
from typing import Iterable
import zlib

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import ROOT, compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


SOURCE = ROOT / "RockPi4C/Tests/vop_banner_crop_payload.rockpi4c"
EXPECTED_RETURN = 0x43415000
CROP_SIZES = {0: (420, 120), 1: (140, 120)}


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def save_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3]
                    for y in range(height))
    payload = (b"\x89PNG\r\n\x1a\n" +
               png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
               png_chunk(b"IDAT", zlib.compress(rows, 9)) +
               png_chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def pixel_words(payload: str, count: int) -> list[int]:
    if len(payload) != count * 6 or any(ch not in "0123456789ABCDEF" for ch in payload):
        raise ValueError("pixel packet contains nonhex or has the wrong length")
    return [int(payload[i * 6:(i + 1) * 6], 16) for i in range(count)]


def words_hash(words: Iterable[int]) -> int:
    value = 0x811C9DC5
    for word in words:
        value = ((value ^ word) * 0x01000193) & 0xFFFFFFFF
    return value


def checked_pixel_words(payload: str, count: int, checksum: int) -> tuple[list[int], bool]:
    if len(payload) != count * 6:
        raise RuntimeError("pixel packet lost or gained a byte")
    try:
        words = pixel_words(payload, count)
        if words_hash(words) == checksum:
            return words, False
    except ValueError:
        pass
    matches: list[list[int]] = []
    alphabet = "0123456789ABCDEF"
    for at, current in enumerate(payload):
        for replacement in alphabet:
            if replacement == current:
                continue
            candidate = payload[:at] + replacement + payload[at + 1:]
            try:
                words = pixel_words(candidate, count)
            except ValueError:
                continue
            if words_hash(words) == checksum:
                matches.append(words)
                if len(matches) > 1:
                    raise RuntimeError("pixel checksum has ambiguous one-character repairs")
    if not matches:
        raise RuntimeError("pixel packet checksum mismatch beyond one-character repair")
    return matches[0], True


def parse_capture(lines: Iterable[str],
                  acknowledge=None) -> dict[int, tuple[int, int, bytes]]:
    if isinstance(lines, str):
        lines = lines.splitlines()
    metadata = None
    images: dict[int, bytearray] = {}
    progress: dict[int, int] = {}
    hashes: dict[int, int] = {}
    last_packet: dict[int, tuple[int, int, int, int, tuple[int, ...]]] = {}
    complete: set[int] = set()
    returned = None
    repaired_packets = 0
    rejected_packets = 0
    for line in lines:
        if line.startswith("CAP1 "):
            fields = line.split()
            if len(fields) != 7 or metadata is not None:
                raise RuntimeError("capture metadata was malformed or repeated")
            base, width, height, pitch, control, mode = (int(value, 16) for value in fields[1:])
            if base < 0x02000000 or not 420 <= width <= 2560 or \
                    not 120 <= height <= 1600 or pitch < width * 4 or \
                    pitch > 2560 * 4 or base + pitch * height > 0x10000000 or \
                    not control & 1 or mode & 15 != 15:
                raise RuntimeError("capture metadata disagrees with the installed VOP image")
            metadata = (width, height)
            continue
        if line.startswith("CROP "):
            fields = line.split()
            if len(fields) != 6 or metadata is None:
                raise RuntimeError("crop header was malformed")
            crop, x, y, width, height = (int(value, 16) for value in fields[1:])
            if crop not in CROP_SIZES or crop in images or (width, height) != CROP_SIZES[crop] or y:
                raise RuntimeError("unexpected crop extent")
            if x != (0 if crop == 0 else metadata[0] - width):
                raise RuntimeError("crop is not at the expected banner or logo position")
            images[crop] = bytearray(width * height * 3)
            progress[crop] = 0
            hashes[crop] = 0x811C9DC5
            continue
        if line.startswith("PIX "):
            try:
                fields = line.split()
                if len(fields) != 7:
                    raise RuntimeError("pixel packet header is malformed")
                crop, row, offset, count = (int(value, 16) for value in fields[1:5])
                if crop not in images or crop in complete:
                    raise RuntimeError("pixel packet belongs to an absent or completed crop")
                width, height = CROP_SIZES[crop]
                if count < 1 or count > 32 or row >= height or offset + count > width:
                    raise RuntimeError("pixel packet extent is invalid")
                expected = int(fields[6], 16)
                words, repaired = checked_pixel_words(fields[5], count, expected)
                if progress[crop] != row * width + offset:
                    if last_packet.get(crop) == (row, offset, count, expected, tuple(words)) and \
                            progress[crop] == row * width + offset + count:
                        if acknowledge is not None:
                            acknowledge(True)
                        continue
                    raise RuntimeError("pixel packet order is invalid")
            except (RuntimeError, ValueError) as exc:
                if acknowledge is None:
                    raise RuntimeError(f"pixel packet rejected: {exc}") from exc
                rejected_packets += 1
                acknowledge(False)
                continue
            if repaired:
                repaired_packets += 1
            for column, word in enumerate(words):
                index = ((row * width) + offset + column) * 3
                images[crop][index:index + 3] = bytes((word >> 16 & 255, word >> 8 & 255, word & 255))
                hashes[crop] = ((hashes[crop] ^ word) * 0x01000193) & 0xFFFFFFFF
            progress[crop] += count
            last_packet[crop] = (row, offset, count, expected, tuple(words))
            if acknowledge is not None:
                acknowledge(True)
            continue
        if line.startswith("END "):
            fields = line.split()
            if len(fields) != 3:
                raise RuntimeError("crop checksum line is malformed")
            crop, checksum = (int(value, 16) for value in fields[1:])
            if crop not in images or crop in complete or \
                    progress[crop] != CROP_SIZES[crop][0] * CROP_SIZES[crop][1] or \
                    hashes[crop] != checksum:
                raise RuntimeError("crop is incomplete or its checksum differs")
            complete.add(crop)
            continue
        if line.startswith("PAYLOAD RETURN X0="):
            returned = int(line.partition("=")[2], 16)
            continue
        if acknowledge is not None and any(crop not in complete for crop in images):
            # A corrupted PIX prefix is rejected while the board waits for
            # its ACK. No unknown text is accepted as a pixel packet.
            rejected_packets += 1
            acknowledge(False)
    if metadata is None or complete != set(CROP_SIZES) or returned != EXPECTED_RETURN:
        raise RuntimeError(
            f"capture incomplete: metadata={metadata} complete={sorted(complete)} "
            f"progress={progress} return={None if returned is None else f'0x{returned:016X}'}"
        )
    print(f"capture transfer: {repaired_packets} corrected pixel packets, "
          f"{rejected_packets} rejected/retransmitted packets")
    return {crop: (*CROP_SIZES[crop], bytes(rgb)) for crop, rgb in images.items()}


def capture_lines(recovery: Recovery, image: bytes,
                  timeout_seconds: float = 45.0) -> Iterable[str]:
    """Upload with Anvil's deadman, then drain long capture output in chunks.

    Only the two RGB crops (201,600 bytes) are retained by the parser. The
    serial receive buffer is capped at 64 KiB and a single line at 1024 bytes.
    """
    checksum = zlib.crc32(image) & 0xFFFFFFFF
    recovery.send_command(f"payload {len(image):X} {checksum:08X}")
    recovery.transfer_in(image, len(image), checksum)
    pending = bytearray()
    wire_bytes = 0
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        available = recovery.port.in_waiting
        chunk = recovery.port.read(min(max(available, 1), 65536))
        if not chunk:
            continue
        wire_bytes += len(chunk)
        if wire_bytes > 512 * 1024:
            raise RuntimeError("capture exceeded its bounded wire-output allowance")
        pending.extend(chunk)
        while True:
            end = pending.find(b"\n")
            if end < 0:
                if len(pending) > 1024:
                    raise RuntimeError("capture line exceeded 1024 bytes")
                break
            line = bytes(pending[:end]).rstrip(b"\r")
            del pending[:end + 1]
            if len(line) > 1024:
                raise RuntimeError("capture line exceeded 1024 bytes")
            # UART byte errors can also set the high bit. Preserve framing so
            # the parser can NACK this packet and request its bounded resend.
            decoded = line.decode("ascii", "replace")
            if decoded.startswith(("PAYLOAD REFUSED", "PAYLOAD RETURN REFUSED")):
                raise RuntimeError(decoded)
            if decoded.startswith("RECOVERY READY;"):
                raise RuntimeError("board reset before the capture returned")
            yield decoded
            if decoded.startswith("PAYLOAD RETURN X0="):
                return
    raise TimeoutError(f"capture return absent after {wire_bytes} serial bytes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Rock Pi recovery UART, for example COM7")
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/rockpi4c-captures")
    parser.add_argument("--timeout", type=float, default=45.0,
                        help="bounded capture wait in seconds (default: 45)")
    options = parser.parse_args()
    compiler = resolve_compiler(options.compiler)
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("board advertised an unexpected stage capacity")
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rockpi4c-capture-", dir=ROOT / "tmp") as directory:
            image = compile_for_stage(compiler, stage, Path(directory) / "banner-crop.bin",
                                      SOURCE)
            current, capacity = recovery.stage_map()
            if current != stage or capacity != STAGE_LIMIT:
                raise RuntimeError("board stage changed after linking; no payload sent")
            def acknowledge(ok: bool) -> None:
                recovery.port.write(b"+" if ok else b"-")
                recovery.port.flush()

            crops = parse_capture(capture_lines(recovery, image, options.timeout), acknowledge)
    finally:
        recovery.close()
    for crop, (width, height, rgb) in crops.items():
        label = "banner" if crop == 0 else "logo"
        path = options.output / f"rockpi4c-{label}-{width}x{height}.png"
        save_png(path, width, height, rgb)
        print(f"saved {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
