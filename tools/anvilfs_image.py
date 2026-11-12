"""Create an AnvilFS image or read a clean volume."""

import argparse
import json
from pathlib import Path
import struct
import zlib


PAGE = 4096
SECTOR = 512
FIRST_SECTOR = 2048
JOURNAL_PAGES = 18
SLOTS = 128
TABLE_SECTOR = FIRST_SECTOR + (1 + JOURNAL_PAGES) * (PAGE // SECTOR)
DATA_SECTOR = TABLE_SECTOR + SLOTS


def valid_name(name):
    return (0 < len(name) <= 255 and name not in (b".", b"..")
            and all(c >= 32 and c not in (47, 58, 92, 127) for c in name))


def entries(root):
    result = []

    def visit(directory, parent):
        for child in sorted(directory.iterdir()):
            if child.is_symlink():
                raise ValueError(f"symbolic links are unsupported: {child}")
            name = child.name.encode("utf-8")
            if not valid_name(name):
                raise ValueError(f"invalid AnvilFS name: {child}")
            if len(child.relative_to(root).as_posix().encode("utf-8")) > 1023:
                raise ValueError(f"path exceeds Anvil's command limit: {child}")
            if len(result) == SLOTS:
                raise ValueError(f"AnvilFS holds at most {SLOTS} files and directories")
            if child.is_dir():
                result.append((child, 2, parent, name, 0))
                visit(child, len(result))
            elif child.is_file():
                result.append((child, 1, parent, name, child.stat().st_size))
            else:
                raise ValueError(f"unsupported file type: {child}")

    if root is not None:
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"expected a source directory: {root}")
        visit(root, 0)
    return result


def seal(block):
    struct.pack_into("<I", block, len(block) - 4, zlib.crc32(block[:-4]))


def checked(block):
    return zlib.crc32(block[:-4]) == struct.unpack_from("<I", block, len(block) - 4)[0]


def copy_bytes(source, destination, length):
    while length:
        data = source.read(min(length, 1 << 20))
        if not data:
            raise ValueError("file ended before its declared size")
        destination.write(data)
        length -= len(data)


def build_image(output, size, source=None):
    if size % PAGE or size < (DATA_SECTOR + PAGE // SECTOR) * SECTOR:
        raise ValueError("image must be page-aligned and leave room for file data")
    sectors = size // SECTOR - FIRST_SECTOR
    if sectors > 0xFFFFFFFF:
        raise ValueError("image exceeds MBR partition size")

    mbr = bytearray(SECTOR)
    struct.pack_into("<B3xB3xII", mbr, 446, 0, 0xDA, FIRST_SECTOR, sectors)
    mbr[510:512] = b"\x55\xaa"
    header = bytearray(PAGE)
    struct.pack_into("<8sQ", header, 0, b"ANVLFS1\0", sectors)
    seal(header)

    table = bytearray(SLOTS * SECTOR)
    position = DATA_SECTOR * SECTOR
    contents = []
    for slot, (path, kind, parent, name, length) in enumerate(entries(source)):
        entry = bytearray(SECTOR)
        extent = 0
        if length:
            extent = position // SECTOR - FIRST_SECTOR
            contents.append((path, position, length))
            position += ((length + PAGE - 1) // PAGE) * PAGE
            if position > size:
                raise ValueError("source tree does not fit in the image")
        struct.pack_into("<BxHH2xQQ", entry, 0, kind, parent, len(name), extent, length)
        entry[24:24 + len(name)] = name
        seal(entry)
        table[slot * SECTOR:(slot + 1) * SECTOR] = entry

    with output.open("xb") as disk:
        try:
            disk.truncate(size)
            disk.write(mbr)
            disk.seek(FIRST_SECTOR * SECTOR)
            disk.write(header)
            disk.seek(TABLE_SECTOR * SECTOR)
            disk.write(table)
            for path, offset, length in contents:
                disk.seek(offset)
                with path.open("rb") as src:
                    if src.seek(0, 2) != length:
                        raise ValueError(f"source size changed: {path}")
                    src.seek(0)
                    copy_bytes(src, disk, length)
            disk.flush()
        except BaseException:
            disk.close()
            output.unlink()
            raise


def read_entries(disk):
    size = disk.seek(0, 2)
    disk.seek(0)
    mbr = disk.read(SECTOR)
    if len(mbr) != SECTOR or mbr[510:] != b"\x55\xaa" or mbr[450] != 0xDA:
        raise ValueError("partition 1 is not AnvilFS")
    first, sectors = struct.unpack_from("<II", mbr, 454)
    table_at = (first + TABLE_SECTOR - FIRST_SECTOR) * SECTOR
    data_at = DATA_SECTOR - FIRST_SECTOR
    if first < 8 or first % 8 or sectors % 8 or sectors < data_at + 8 or (first + sectors) * SECTOR > size:
        raise ValueError("invalid AnvilFS partition geometry")
    for slot in range(1, 4):
        offset = 446 + slot * 16
        other, count = struct.unpack_from("<II", mbr, offset + 8)
        if mbr[offset + 4] and count and first < other + count and other < first + sectors:
            raise ValueError("overlapping disk partitions")

    disk.seek(first * SECTOR)
    header = disk.read(PAGE)
    if len(header) != PAGE or header[:16] != struct.pack("<8sQ", b"ANVLFS1\0", sectors) or not checked(header):
        raise ValueError("invalid AnvilFS superblock")
    if any(disk.read(2 * PAGE)):
        raise ValueError("journal requires writable recovery in Anvil")

    disk.seek(table_at)
    slots = {}
    extents = []
    for slot in range(1, SLOTS + 1):
        entry = disk.read(SECTOR)
        if len(entry) != SECTOR:
            raise ValueError("short AnvilFS directory table")
        if not any(entry):
            continue
        kind, parent, name_size, start, length = struct.unpack_from("<BxHH2xQQ", entry)
        name = entry[24:24 + name_size]
        if kind not in (1, 2) or name_size > 255 or not checked(entry) or not valid_name(name):
            raise ValueError(f"invalid directory entry {slot}")
        if length:
            end = start + ((length + PAGE - 1) // PAGE) * (PAGE // SECTOR)
            if kind != 1 or start < data_at or start % 8 or end > sectors:
                raise ValueError(f"invalid file extent in entry {slot}")
            extents.append((start, end))
        elif start:
            raise ValueError(f"unexpected empty-file extent in entry {slot}")
        slots[slot] = (kind, parent, name.decode("utf-8"), (first + start) * SECTOR, length)
    extents.sort()
    if any(right[0] < left[1] for left, right in zip(extents, extents[1:])):
        raise ValueError("overlapping AnvilFS extents")

    result = {}
    for slot, (kind, parent, name, start, length) in slots.items():
        seen = {slot}
        parts = [name]
        while parent:
            if parent in seen or parent not in slots or slots[parent][0] != 2:
                raise ValueError(f"invalid directory parent for entry {slot}")
            seen.add(parent)
            _, parent, name, _, _ = slots[parent]
            parts.append(name)
        path = "/".join(reversed(parts))
        if path in result:
            raise ValueError(f"duplicate path: {path}")
        result[path] = (kind, start, length)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--list", action="store_true", help="List files and directories as JSON")
    operation.add_argument("--extract", metavar="PATH", help="Extract one file by its image path")
    parser.add_argument("--to", type=Path, help="Destination for --extract")
    parser.add_argument("--size-mib", type=int)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    reading = args.list or args.extract is not None
    if reading and (args.source is not None or args.size_mib is not None):
        parser.error("--source and --size-mib are for creating images")
    if (args.extract is None) != (args.to is None):
        parser.error("--extract and --to must be supplied together")
    try:
        if not reading:
            size = 64 if args.size_mib is None else args.size_mib
            build_image(args.image, size << 20, args.source)
        else:
            with args.image.open("rb") as disk:
                files = read_entries(disk)
                if args.list:
                    print(json.dumps([
                        dict(path=path, directory=(kind == 2), size=length)
                        for path, (kind, _, length) in sorted(files.items())
                    ], indent=2))
                else:
                    item = files.get(args.extract)
                    if item is None or item[0] != 1:
                        raise ValueError(f"file not found: {args.extract}")
                    _, start, length = item
                    disk.seek(start)
                    with args.to.open("xb") as output:
                        try:
                            copy_bytes(disk, output, length)
                            output.flush()
                        except BaseException:
                            output.close()
                            args.to.unlink()
                            raise
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
