#!/usr/bin/env python3
"""Wrap a flat RK3399 A64 payload in the 64-byte arm64 Image contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from pi3_slot_pack import atomic_write

IMAGE_BASE = 0x02000000
CODE_BASE = 0x02000040
CODE_LIMIT = 0x02800000
DTB_ADDRESS = 0x12000000
MAGIC = 0x644D5241
FLAGS = 1 << 3  # kernel may be placed anywhere; U-Boot keeps IMAGE_BASE
BRANCH_TO_PAYLOAD = 0x14000010  # b +0x40 from header word zero
NOP = 0xD503201F
HEADER_BYTES = 64


class ImageError(ValueError):
    pass


def wrap(payload: bytes) -> tuple[bytes, dict[str, object]]:
    if not payload:
        raise ImageError("ROCKPI4C-IMG-001: the compiler payload is empty")
    if len(payload) > CODE_LIMIT - CODE_BASE:
        raise ImageError(
            "ROCKPI4C-IMG-002: payload exceeds the first-port code window "
            f"({len(payload)} > {CODE_LIMIT - CODE_BASE} bytes)"
        )
    image_size = HEADER_BYTES + len(payload)
    header = struct.pack(
        "<IIQQQQQQII",
        BRANCH_TO_PAYLOAD, NOP, 0, image_size, FLAGS, 0, 0, 0, MAGIC, 0,
    )
    if len(header) != HEADER_BYTES:
        raise AssertionError("internal arm64 Image header size drift")
    image = header + payload
    validate(image)
    metadata: dict[str, object] = {
        "schema": 1,
        "board": "original ROCK Pi 4C PCB v1.2",
        "soc": "RK3399",
        "image_address": f"0x{IMAGE_BASE:08x}",
        "code_address": f"0x{CODE_BASE:08x}",
        "dtb_address": f"0x{DTB_ADDRESS:08x}",
        "image_bytes": len(image),
        "payload_bytes": len(payload),
        "sha256": hashlib.sha256(image).hexdigest(),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "uboot_command": "booti 0x02000000 - 0x12000000",
        "silicon_status": "not run",
    }
    return image, metadata


def validate(image: bytes) -> None:
    if len(image) < HEADER_BYTES + 4:
        raise ImageError("ROCKPI4C-IMG-003: Image is truncated")
    fields = struct.unpack_from("<IIQQQQQQII", image)
    code0, code1, text_offset, image_size, flags, res2, res3, res4, magic, res5 = fields
    if code0 != BRANCH_TO_PAYLOAD or code1 != NOP:
        raise ImageError("ROCKPI4C-IMG-004: entry does not branch exactly to byte 64")
    if text_offset != 0 or image_size != len(image) or flags != FLAGS:
        raise ImageError("ROCKPI4C-IMG-005: placement or size fields do not match the file")
    if res2 != 0 or res3 != 0 or res4 != 0 or res5 != 0:
        raise ImageError("ROCKPI4C-IMG-006: reserved header fields are not zero")
    if magic != MAGIC:
        raise ImageError("ROCKPI4C-IMG-007: arm64 Image magic is absent")
    if len(image) - HEADER_BYTES > CODE_LIMIT - CODE_BASE:
        raise ImageError("ROCKPI4C-IMG-008: payload extends into the fixed BSS window")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    payload = args.payload.read_bytes()
    image, metadata = wrap(payload)
    atomic_write(args.image, image)
    manifest = args.manifest or Path(str(args.image) + ".json")
    atomic_write(manifest, (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("ascii"))
    print(f"ROCK Pi 4C Image: {len(image)} bytes, sha256 {metadata['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
