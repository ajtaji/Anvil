#!/usr/bin/env python3
"""Wrap a fail-closed BL33 payload in Rockchip's legacy LOADER format.

The wrapper matches the legacy loaderimage ``--uboot`` format used by
Rockchip miniloaders. The input payload should be the intended tiny fail-closed
stub; this utility does not build or include U-Boot.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path


HEADER_SIZE = 2048
DEFAULT_IMAGE_KIB = 1024
DEFAULT_COPIES = 4
DEFAULT_LOAD_ADDRESS = 0x00200000


def rockchip_crc32(data: bytes, seed: int = 0) -> int:
    """Rockchip's non-reflected CRC-32 (table polynomial 0x04C10DB7, seed 0)."""
    crc = seed & 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C10DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def rockchip_js_hash(data: bytes) -> int:
    value = 0x47C6A7E6
    for byte in data:
        value ^= ((value << 5) + byte + (value >> 2)) & 0xFFFFFFFF
        value &= 0xFFFFFFFF
    return value


def build_stub_image(
    payload: bytes,
    *,
    load_address: int = DEFAULT_LOAD_ADDRESS,
    image_kib: int = DEFAULT_IMAGE_KIB,
    copies: int = DEFAULT_COPIES,
) -> bytes:
    if not 0 <= load_address <= 0xFFFFFFFF:
        raise ValueError("load address must fit in 32 bits")
    if not payload:
        raise ValueError("stub payload must not be empty")
    if load_address + len(payload) > 0x1_0000_0000:
        raise ValueError("stub load range exceeds 32-bit address space")
    if image_kib <= 0 or image_kib % 64:
        raise ValueError("per-copy image size must be a positive multiple of 64 KiB")
    if copies <= 0:
        raise ValueError("copy count must be positive")
    if HEADER_SIZE + len(payload) > image_kib * 1024:
        raise ValueError("stub does not fit in the per-copy image size")

    load_size = (len(payload) + 3) & ~3
    padded_payload = payload + bytes(load_size - len(payload))
    hash_len = 32
    digest = hashlib.sha256(
        padded_payload
        + struct.pack("<II", load_address, load_size)
        + struct.pack("<I", hash_len)
    ).digest()

    # See second_loader_hdr in stock-android-uboot-source/tools/rockchip/loaderimage.c.
    header = bytearray(HEADER_SIZE)
    header[:8] = b"LOADER  "
    struct.pack_into("<6I", header, 8, 0, 0, load_address, load_size,
                     rockchip_crc32(padded_payload), hash_len)
    header[32:64] = digest
    struct.pack_into("<I", header, 64, rockchip_js_hash(padded_payload))

    one_copy = bytearray(image_kib * 1024)
    one_copy[:HEADER_SIZE] = header
    one_copy[HEADER_SIZE:HEADER_SIZE + len(padded_payload)] = padded_payload
    return bytes(one_copy) * copies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True,
                        help="small fail-closed raw BL33 stub binary")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--load-address", type=lambda x: int(x, 0),
                        default=DEFAULT_LOAD_ADDRESS)
    parser.add_argument("--image-kib", type=int, default=DEFAULT_IMAGE_KIB)
    parser.add_argument("--copies", type=int, default=DEFAULT_COPIES)
    args = parser.parse_args(argv)
    try:
        image = build_stub_image(args.payload.read_bytes(), load_address=args.load_address,
                                 image_kib=args.image_kib, copies=args.copies)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(image)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(image)} bytes ({args.image_kib} KiB x {args.copies}) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
