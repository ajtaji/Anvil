#!/usr/bin/env python3
"""Read-only Rock Pi 4C recovery command smoke test over the live UART."""

from __future__ import annotations

import argparse
import time
import zlib

from rockpi4c_update import Recovery


def read_until(link: Recovery, prefix: bytes, timeout: float) -> list[bytes]:
    result: list[bytes] = []
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        line = link.line(end)
        if line:
            print(line.decode("ascii", "backslashreplace"))
            result.append(line)
        if line.startswith(prefix):
            return result
    raise TimeoutError(f"missing {prefix!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--write-test", action="store_true",
                        help="create, move, read back and remove one test file/folder on SD")
    args = parser.parse_args()
    link = Recovery(args.port, 1_500_000)
    try:
        link.send_command("help")
        help_lines = read_until(link, b"       mkdir", 8)
        if not any(b"FILES: sd emmc fs" in line for line in help_lines):
            raise RuntimeError("filesystem command help was absent")
        link.send_command("fs")
        status = read_until(link, b"FILESYSTEM SD ", 8)
        if b"PARTITION " not in status[-1]:
            raise RuntimeError("mounted filesystem status was incomplete")
        link.send_command("ls")
        listing = read_until(link, b"LS DONE COUNT ", 15)
        if not any(line.startswith(b"DIRECTORY /") for line in listing):
            raise RuntimeError("root directory header was absent")
        link.send_command("stat RK4CPRF.TXT")
        stat = read_until(link, b"FILE RK4CPRF.TXT BYTES ", 8)
        if not stat[-1].endswith(b"0000000000000016"):
            raise RuntimeError("file size differed from root listing")
        link.send_command("cat RK4CPRF.TXT")
        cat = read_until(link, b"CAT DONE BYTES ", 8)
        if not any(b"RK3399 STORAGE PROOF 1" in line for line in cat):
            raise RuntimeError("text file contents differed from storage proof")
        print("PASS: help, SD status, root listing, stat, cat")
        if args.write_test:
            directory = "CMD144"
            source = f"{directory}/CHECK.TXT"
            moved = f"{directory}/MOVED.TXT"
            data = b"ANVIL COMMAND SET 144\n"
            checksum = zlib.crc32(data) & 0xFFFFFFFF
            link.send_command(f"mkdir {directory}")
            read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
            link.send_command(f"receive {len(data):X} {checksum:08X}")
            link.transfer_in(data, len(data), checksum)
            read_until(link, b"STAGE READY; NO CODE EXECUTED", 10)
            link.send_command(f"save {source}")
            read_until(link, b"SAVE FLUSHED; REMOUNTED READBACK CHECKSUM PASS", 30)
            link.send_command(f"cat {source}")
            contents = read_until(link, b"CAT DONE BYTES ", 8)
            if not any(data.strip() in line for line in contents):
                raise RuntimeError("saved content differs")
            link.send_command(f"mv {source} {moved}")
            read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
            link.send_command(f"stat {moved}")
            read_until(link, f"FILE {moved} BYTES ".encode(), 8)
            link.send_command(f"rm {moved}")
            read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
            link.send_command(f"rmdir {directory}")
            read_until(link, b"FILESYSTEM CHANGE FLUSHED", 15)
            print("PASS: receive/save/readback/cat/mv/stat/rm/rmdir")
    finally:
        link.close()


if __name__ == "__main__":
    main()
