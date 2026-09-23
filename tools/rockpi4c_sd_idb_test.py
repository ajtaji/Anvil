#!/usr/bin/env python3
"""Host format tests for rockpi4c_sd_idb.py; no media access."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import subprocess
import tempfile

from rockpi4c_sd_idb import (
    ALIGN, BLOCK, HEADER_BYTES, MAX_BOOT_BYTES, PackageError, _align,
    _rc4, make_ddr_idblock, package, validate,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def msys_path(path: Path) -> str:
    """Use the POSIX drive spelling expected by the local MSYS mkimage build."""
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if drive:
        return "/" + drive + resolved.as_posix()[2:]
    return resolved.as_posix()


def check_structure(ddr: bytes, miniloader: bytes) -> None:
    image = package(ddr, miniloader)
    validate(image, ddr, miniloader)
    require(len(image) == HEADER_BYTES + _align(len(ddr)) + len(miniloader),
            "package length/alignment drift")
    header0 = _rc4(image[:BLOCK])
    require(struct.unpack_from("<I", header0, 0)[0] == 0x0FF0AA55,
            "decoded BootROM magic mismatch")
    require(struct.unpack_from("<I", header0, 8)[0] == 1,
            "DDR payload unexpectedly marked RC4 encoded")
    require(struct.unpack_from("<H", header0, 12)[0] == 4,
            "BootROM init offset is not four blocks")
    require(struct.unpack_from("<HH", header0, 506) ==
            (_align(len(ddr)) // BLOCK,
             (_align(len(ddr)) + MAX_BOOT_BYTES) // BLOCK),
            "BootROM size fields mismatch")
    require(image[HEADER_BYTES:HEADER_BYTES + 4] == b"RK33",
            "RK3399 marker missing")
    require(image[HEADER_BYTES + 4:HEADER_BYTES + len(ddr)] == ddr[4:],
            "DDR bytes changed beyond the reserved marker")
    require(image[-len(miniloader):] == miniloader, "miniloader append mismatch")

    changed = bytearray(image)
    changed[-1] ^= 1
    try:
        validate(bytes(changed), ddr, miniloader)
    except PackageError:
        pass
    else:
        raise AssertionError("corrupted miniloader bytes were accepted")


def check_oracle(mkimage: Path, ddr: bytes, miniloader: bytes) -> None:
    with tempfile.TemporaryDirectory(prefix="rockpi4c-idb-oracle-") as temp:
        root = Path(temp)
        ddr_path, oracle_path = root / "ddr.bin", root / "oracle.img"
        ddr_path.write_bytes(ddr)
        command = [str(mkimage), "-n", "rk3399", "-T", "rksd", "-d",
                   msys_path(ddr_path), msys_path(oracle_path)]
        run = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=60)
        require(run.returncode == 0, "mkimage oracle failed: " + run.stdout)
        oracle = oracle_path.read_bytes()
        require(make_ddr_idblock(ddr) == oracle,
                "Python DDR/idblock bytes differ from host mkimage oracle")
        require(package(ddr, miniloader) == oracle + miniloader,
                "Python miniloader append differs from documented cat contract")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mkimage", required=True, type=Path,
                        help="existing host U-Boot mkimage.exe oracle")
    parser.add_argument("--ddr-bin", type=Path,
                        help="optional real pinned rk3399_ddr_800MHz_v1.30.bin")
    parser.add_argument("--miniloader-bin", type=Path,
                        help="optional real pinned rk3399_miniloader_v1.30.bin")
    args = parser.parse_args()
    require(args.mkimage.is_file(), "mkimage oracle does not exist")

    fixture_ddr = bytes((i * 37 + 11) & 0xFF for i in range(7001))
    fixture_miniloader = bytes((i * 19 + 7) & 0xFF for i in range(3301))
    check_structure(fixture_ddr, fixture_miniloader)
    check_oracle(args.mkimage, fixture_ddr, fixture_miniloader)

    if bool(args.ddr_bin) != bool(args.miniloader_bin):
        raise SystemExit("pass both --ddr-bin and --miniloader-bin, or neither")
    if args.ddr_bin:
        ddr, miniloader = args.ddr_bin.read_bytes(), args.miniloader_bin.read_bytes()
        check_structure(ddr, miniloader)
        check_oracle(args.mkimage, ddr, miniloader)

    print("RK3399 SD idb format PASS: structure, mutation refusal, mkimage byte comparison")
    if args.ddr_bin:
        print("Real pinned DDR/miniloader oracle comparison PASS")
    print("Host-only; no U-Boot runtime, device write, or board access performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
