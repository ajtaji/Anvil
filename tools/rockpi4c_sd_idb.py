#!/usr/bin/env python3
"""Package the RK3399 SD idbloader header, pinned DDR blob, and miniloader.

This is host-side packaging only. It does not implement or claim the runtime
behavior of the DDR blob or miniloader, and it never writes a block device.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import struct
import tempfile

BLOCK = 512
ALIGN = 2048
HEADER_BLOCKS = 4
HEADER_BYTES = BLOCK * HEADER_BLOCKS
MAX_BOOT_BYTES = 512 * 1024
RK_MAGIC = 0x0FF0AA55
SPL_MAGIC = b"RK33"
RC4_KEY = bytes((124, 78, 3, 4, 85, 5, 9, 7, 45, 44, 123, 56, 23, 13, 23, 17))

# Exact rkbin-source files inspected for this candidate. The binaries remain
# external inputs so their Rockchip license accompanies them.
DDR800_SHA256 = "2c74f7c0a2f7b1a49225fd0dca2fd88f574177e2b87dd4c526d569a94a9bcd92"
MINILOADER_SHA256 = "17b4dc35fc88f9c9648a5428c5b6453cdd6759f74e90e8dce25f0b22d2db1c03"


class PackageError(ValueError):
    pass


def _align(value: int) -> int:
    return (value + ALIGN - 1) & ~(ALIGN - 1)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rc4(data: bytes) -> bytes:
    """Rockchip mkimage's RC4 transform, applied to header block zero only."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + RC4_KEY[i % len(RC4_KEY)]) & 0xFF
        state[i], state[j] = state[j], state[i]
    i = j = 0
    out = bytearray(data)
    for pos in range(len(out)):
        i = (i + 1) & 0xFF
        j = (j + state[i]) & 0xFF
        state[i], state[j] = state[j], state[i]
        out[pos] ^= state[(state[i] + state[j]) & 0xFF]
    return bytes(out)


def make_ddr_idblock(ddr: bytes) -> bytes:
    """Recreate `mkimage -n rk3399 -T rksd -d DDR idbloader.img`."""
    if not ddr:
        raise PackageError("ROCKPI4C-IDB-001: DDR input is empty")
    init_size = _align(len(ddr))
    if init_size > 0xFFFF * BLOCK:
        raise PackageError("ROCKPI4C-IDB-002: aligned DDR input exceeds header size")

    # rkcommon.c's header0_info: magic, disable_rc4, init_offset, 492 reserved
    # bytes, init_size, init_boot_size, and two final reserved bytes.
    header0 = bytearray(BLOCK)
    struct.pack_into("<I", header0, 0, RK_MAGIC)
    struct.pack_into("<I", header0, 8, 1)  # disable_rc4
    struct.pack_into("<H", header0, 12, HEADER_BLOCKS)
    struct.pack_into("<HH", header0, 506, init_size // BLOCK,
                     (init_size + MAX_BOOT_BYTES) // BLOCK)
    header = bytearray(HEADER_BYTES)
    header[:BLOCK] = _rc4(bytes(header0))

    # The Rockchip format reserves the first four bytes at 0x800 for the SoC
    # marker. rkcommon_set_header() writes RK33 there over the input's prefix.
    payload = SPL_MAGIC + ddr[4:]
    payload += bytes(init_size - len(ddr))
    return bytes(header) + payload


def package(ddr: bytes, miniloader: bytes) -> bytes:
    if not miniloader:
        raise PackageError("ROCKPI4C-IDB-003: miniloader input is empty")
    if len(miniloader) > MAX_BOOT_BYTES:
        raise PackageError("ROCKPI4C-IDB-004: miniloader exceeds 512 KiB ROM window")
    return make_ddr_idblock(ddr) + miniloader


def validate(image: bytes, ddr: bytes, miniloader: bytes) -> None:
    expected = package(ddr, miniloader)
    if image != expected:
        raise PackageError("ROCKPI4C-IDB-005: image differs from the exact DDR/header/miniloader package")
    header0 = _rc4(image[:BLOCK])
    magic = struct.unpack_from("<I", header0, 0)[0]
    disable_rc4 = struct.unpack_from("<I", header0, 8)[0]
    init_offset = struct.unpack_from("<H", header0, 12)[0]
    init_size_blocks, boot_size_blocks = struct.unpack_from("<HH", header0, 506)
    if (magic != RK_MAGIC or disable_rc4 != 1 or init_offset != HEADER_BLOCKS
            or init_size_blocks * BLOCK != _align(len(ddr))
            or boot_size_blocks * BLOCK != _align(len(ddr)) + MAX_BOOT_BYTES):
        raise PackageError("ROCKPI4C-IDB-006: decoded RK3399 BootROM header is invalid")
    if image[HEADER_BYTES:HEADER_BYTES + 4] != SPL_MAGIC:
        raise PackageError("ROCKPI4C-IDB-007: RK33 SoC marker is missing at 0x800")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ddr_bin", type=Path, help="external rk3399_ddr_800MHz_v1.30.bin")
    parser.add_argument("miniloader_bin", type=Path, help="external rk3399_miniloader_v1.30.bin")
    parser.add_argument("output", type=Path, help="host file, e.g. build/rockpi4c/idbloader.img")
    parser.add_argument("--allow-unpinned", action="store_true",
                        help="allow inputs with different hashes (for test fixtures only)")
    args = parser.parse_args()
    ddr, miniloader = args.ddr_bin.read_bytes(), args.miniloader_bin.read_bytes()
    ddr_hash, miniloader_hash = _sha256(ddr), _sha256(miniloader)
    if not args.allow_unpinned:
        if ddr_hash != DDR800_SHA256:
            raise SystemExit("ROCKPI4C-IDB-008: DDR blob hash is not pinned v1.30 800MHz")
        if miniloader_hash != MINILOADER_SHA256:
            raise SystemExit("ROCKPI4C-IDB-009: miniloader hash is not pinned v1.30")
    result = package(ddr, miniloader)
    validate(result, ddr, miniloader)
    _atomic_write(args.output, result)
    print(f"RK3399 SD idbloader: {len(result)} bytes, sha256 {_sha256(result)}")
    print(f"DDR800 v1.30 sha256 {ddr_hash}; miniloader v1.30 sha256 {miniloader_hash}")
    print("Host package only; no block device or board was accessed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
