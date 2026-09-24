#!/usr/bin/env python3
"""Exercise mounted FAT32 file commands on the Rock Pi 4C eMMC user area."""

from __future__ import annotations

import argparse
import time
import zlib

from rockpi4c_commands_smoke import read_until
from rockpi4c_update import Recovery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM7")
    args = parser.parse_args()
    link = Recovery(args.port, 1_500_000)
    try:
        link.send_command("emmc")
        status = read_until(link, b"FILESYSTEM EMMC FAT32 PARTITION ", 15)
        if not status[-1].endswith(b"000000000747C000"):
            raise RuntimeError("eMMC capacity differs from verified card")
        link.send_command("ls")
        read_until(link, b"LS DONE COUNT ", 15)

        directory = f"C{int(time.time()) & 0xFFFFFF:06X}"
        source = f"{directory}/EMMC.TXT"
        moved = f"{directory}/MOVED.TXT"
        data = b"ANVIL EMMC FILE PROOF 1\n"
        checksum = zlib.crc32(data) & 0xFFFFFFFF
        link.send_command(f"mkdir {directory}")
        read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
        link.send_command(f"receive {len(data):X} {checksum:08X}")
        link.transfer_in(data, len(data), checksum)
        read_until(link, b"STAGE READY;", 10)
        link.send_command(f"save {source}")
        read_until(link, b"SAVE FLUSHED; REMOUNTED READBACK CHECKSUM PASS", 30)
        link.send_command(f"cat {source}")
        contents = read_until(link, b"CAT DONE BYTES ", 8)
        if not any(data.strip() in line for line in contents):
            raise RuntimeError("eMMC saved content differs")
        link.send_command(f"load {source}")
        loaded = read_until(link, b"STAGE ", 10)
        if f"CRC {checksum:08X}".encode() not in loaded[-1]:
            raise RuntimeError("eMMC file load checksum differs")
        if link.get(source) != data:
            raise RuntimeError("eMMC downloaded content differs")
        link.send_command(f"mv {source} {moved}")
        read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
        link.send_command(f"stat {moved}")
        read_until(link, f"FILE {moved} BYTES ".encode(), 8)
        link.send_command(f"rm {moved}")
        read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
        link.send_command(f"rmdir {directory}")
        read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
        link.send_command(f"put EMMCPUT.TXT {len(data):X} {checksum:08X}")
        link.transfer_in(data, len(data), checksum)
        read_until(link, b"FILE WRITE, FLUSH AND REMOUNTED READBACK PASS", 30)
        link.send_command("cat EMMCPUT.TXT")
        contents = read_until(link, b"CAT DONE BYTES ", 8)
        if not any(data.strip() in line for line in contents):
            raise RuntimeError("eMMC put content differs")
        link.send_command("rm EMMCPUT.TXT")
        read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
        link.send_command("ls")
        listing = read_until(link, b"LS DONE COUNT ", 15)
        if any(b"CMDTEST" in line or b"EMMCPUT.TXT" in line for line in listing):
            raise RuntimeError("test files remained after removal")
        link.send_command("sd")
        read_until(link, b"FILESYSTEM SD EXFAT PARTITION ", 15)
        print("PASS: eMMC FAT32 mount, create, receive, save, load, get, put, remount, readback, move, remove")
    finally:
        link.close()


if __name__ == "__main__":
    main()
