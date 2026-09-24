#!/usr/bin/env python3
"""Build and validate FAT32 metadata for a proposed eMMC user-area volume.

This tool only writes local review artifacts. It never opens a serial port or
touches a block device. The proposed volume is 512 MiB at user LBA 32768.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import zlib

SECTOR = 512
START = 32768
TOTAL = 1_048_576
SECTORS_PER_CLUSTER = 8
RESERVED = 32
FAT_COPIES = 2
CARD_SECTORS = 0x0747C000


def sectors_per_fat() -> int:
    fat = 1024
    while True:
        clusters = (TOTAL - RESERVED - FAT_COPIES * fat) // SECTORS_PER_CLUSTER
        needed = ((clusters + 2) * 4 + SECTOR - 1) // SECTOR
        if needed == fat:
            return fat
        fat = needed


def make_metadata() -> tuple[bytes, bytes]:
    fat_sectors = sectors_per_fat()
    data_start = RESERVED + FAT_COPIES * fat_sectors
    clusters = (TOTAL - data_start) // SECTORS_PER_CLUSTER
    if not (65_525 <= clusters < 0x0FFFFFF5 and START + TOTAL < CARD_SECTORS):
        raise ValueError("proposed partition exceeds eMMC or FAT32 limits")

    mbr = bytearray(SECTOR)
    mbr[440:444] = struct.pack("<I", 0x20260923)
    entry = 446
    mbr[entry + 1:entry + 4] = b"\xFE\xFF\xFF"
    mbr[entry + 4] = 0x0C
    mbr[entry + 5:entry + 8] = b"\xFE\xFF\xFF"
    struct.pack_into("<II", mbr, entry + 8, START, TOTAL)
    mbr[510:512] = b"\x55\xAA"

    # Only metadata and the empty root cluster are materialized. No data
    # cluster beyond the root is zeroed or represented in this local image.
    prefix = bytearray((data_start + SECTORS_PER_CLUSTER) * SECTOR)
    boot = memoryview(prefix)[:SECTOR]
    boot[0:3] = b"\xEB\x58\x90"
    boot[3:11] = b"ANVIL   "
    struct.pack_into("<H", boot, 11, SECTOR)
    boot[13] = SECTORS_PER_CLUSTER
    struct.pack_into("<H", boot, 14, RESERVED)
    boot[16] = FAT_COPIES
    boot[21] = 0xF8
    struct.pack_into("<HH", boot, 24, 63, 255)
    struct.pack_into("<II", boot, 28, START, TOTAL)
    struct.pack_into("<I", boot, 36, fat_sectors)
    struct.pack_into("<I", boot, 44, 2)
    struct.pack_into("<HH", boot, 48, 1, 6)
    boot[64] = 0x80
    boot[66] = 0x29
    struct.pack_into("<I", boot, 67, 0x20260923)
    boot[71:82] = b"ANVIL EMMC "
    boot[82:90] = b"FAT32   "
    boot[510:512] = b"\x55\xAA"

    fsinfo = memoryview(prefix)[SECTOR:2 * SECTOR]
    struct.pack_into("<I", fsinfo, 0, 0x41615252)
    struct.pack_into("<I", fsinfo, 484, 0x61417272)
    struct.pack_into("<II", fsinfo, 488, clusters - 1, 3)
    struct.pack_into("<I", fsinfo, 508, 0xAA550000)
    prefix[6 * SECTOR:7 * SECTOR] = boot
    prefix[7 * SECTOR:8 * SECTOR] = fsinfo
    for copy in range(FAT_COPIES):
        fat = (RESERVED + copy * fat_sectors) * SECTOR
        struct.pack_into("<III", prefix, fat, 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF)
    return bytes(mbr), bytes(prefix)


def validate(mbr: bytes, prefix: bytes) -> dict[str, int]:
    if len(mbr) != SECTOR or mbr[510:512] != b"\x55\xAA":
        raise ValueError("invalid MBR signature")
    if mbr[450] != 0x0C:
        raise ValueError("partition is not FAT32 LBA")
    start, total = struct.unpack_from("<II", mbr, 454)
    if (start, total) != (START, TOTAL):
        raise ValueError("partition range differs from plan")
    boot = prefix[:SECTOR]
    bps = struct.unpack_from("<H", boot, 11)[0]
    spc = boot[13]
    reserved = struct.unpack_from("<H", boot, 14)[0]
    copies = boot[16]
    hidden, volume_sectors = struct.unpack_from("<II", boot, 28)
    fat_sectors = struct.unpack_from("<I", boot, 36)[0]
    root_cluster = struct.unpack_from("<I", boot, 44)[0]
    info_sector, backup = struct.unpack_from("<HH", boot, 48)
    if (bps, spc, reserved, copies, hidden, volume_sectors, root_cluster,
            info_sector, backup) != (512, 8, 32, 2, START, TOTAL, 2, 1, 6):
        raise ValueError("BPB fields differ from plan")
    if boot[510:512] != b"\x55\xAA" or prefix[6 * SECTOR:7 * SECTOR] != boot:
        raise ValueError("primary or backup boot sector differs")
    info = prefix[SECTOR:2 * SECTOR]
    if prefix[7 * SECTOR:8 * SECTOR] != info:
        raise ValueError("backup FSInfo differs")
    if (struct.unpack_from("<I", info, 0)[0],
            struct.unpack_from("<I", info, 484)[0],
            struct.unpack_from("<I", info, 508)[0]) != (0x41615252, 0x61417272, 0xAA550000):
        raise ValueError("FSInfo signatures differ")
    data_start = reserved + copies * fat_sectors
    clusters = (total - data_start) // spc
    if clusters < 65_525 or (clusters + 2) * 4 > fat_sectors * SECTOR:
        raise ValueError("FAT cannot address all FAT32 clusters")
    first = prefix[reserved * SECTOR:(reserved + fat_sectors) * SECTOR]
    second = prefix[(reserved + fat_sectors) * SECTOR:data_start * SECTOR]
    if first != second or struct.unpack_from("<III", first) != (0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF):
        raise ValueError("FAT copies or root entry differ")
    if any(prefix[data_start * SECTOR:(data_start + spc) * SECTOR]):
        raise ValueError("root directory is not empty")
    if struct.unpack_from("<II", info, 488) != (clusters - 1, 3):
        raise ValueError("FSInfo free-space hint differs")
    return {"start_lba": start, "sectors": total, "fat_sectors": fat_sectors,
            "clusters": clusters, "data_lba": start + data_start,
            "metadata_sectors": data_start + spc,
            "mbr_crc32": zlib.crc32(mbr) & 0xFFFFFFFF,
            "metadata_crc32": zlib.crc32(prefix) & 0xFFFFFFFF}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="directory for local MBR and metadata images")
    args = parser.parse_args()
    mbr, prefix = make_metadata()
    report = validate(mbr, prefix)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "emmc-mbr.bin").write_bytes(mbr)
        (args.output / "emmc-fat32-metadata.bin").write_bytes(prefix)
        validate((args.output / "emmc-mbr.bin").read_bytes(),
                 (args.output / "emmc-fat32-metadata.bin").read_bytes())
    for key, value in report.items():
        print(f"{key}={value} (0x{value:X})")


if __name__ == "__main__":
    main()
