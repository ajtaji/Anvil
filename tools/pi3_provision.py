#!/usr/bin/env python3
"""One-time provisioning of an existing Raspberry Pi 3 FAT boot volume.

This tool does not select, partition, format, or erase a disk.  The caller must
name the already-mounted boot-volume root explicitly.  The expected Pi 3
firmware files must already be there, which prevents an arbitrary directory or
the Windows system drive from being mistaken for the card.

It installs the immutable kernel8.img loader, two equal preallocated monitor
slots, and two redundant control records.  Slot A begins at generation 1; slot
B and its record begin invalid.  Every written byte is read back and hashed.
The loader performs the final FAT-contiguity and image-hash checks on the board.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import zlib

from pi3_slot import (
    BSS_ADDRESS,
    BSS_LIMIT,
    IMAGE_LIMIT,
    LOAD_ADDRESS,
    PMF_HEADER_BYTES,
    PMF_MAGIC,
    PMF_VERSION,
    SLOT_HEADER_BYTES,
    SLOT_ISA,
    SLOT_MAGIC,
    SLOT_TARGET,
    SLOT_VERSION,
    STACK_ADDRESS,
    SlotError,
    validate_loader_pmf,
    validate_slot,
)
from pi3_boot_stage import BOOT as PINNED_BOOT, validate as validate_pinned_boot


SLOT_BYTES = 0xE00000
# Loader begins at 0x80000 and its BSS begins at 0x180000.
LOADER_MAX = 0x100000
CONTROL_MAGIC = 0x42413350
CONTROL_VERSION = 2
CONTROL_CONFIRMED = 3
REQUIRED_FIRMWARE = (
    "bootcode.bin",
    "start.elf",
    "fixup.dat",
    "bcm2710-rpi-3-b.dtb",
    "overlays/disable-bt.dtbo",
    "config.txt",
)


class ProvisionError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def control_record(slot: int, generation: int, image: bytes) -> bytes:
    record = bytearray(512)
    struct.pack_into(
        "<IIQQII",
        record,
        0,
        CONTROL_MAGIC,
        CONTROL_VERSION,
        generation,
        len(image),
        slot,
        LOAD_ADDRESS,
    )
    record[32:64] = hashlib.sha256(image).digest()
    struct.pack_into("<I", record, 64, CONTROL_CONFIRMED)
    struct.pack_into("<I", record, 508, zlib.crc32(record[:508]) & 0xFFFFFFFF)
    return bytes(record)


def write_atomic(target: Path, chunks) -> None:
    # Keep the temporary on the same FAT volume so replacement does not cross
    # devices.  No broad cleanup occurs: only the exact temporary made here is
    # removed on failure.
    fd, temp_name = tempfile.mkstemp(prefix="P3NEW-", dir=target.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            for chunk in chunks:
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()


def padded_image(image: bytes):
    yield image
    remaining = SLOT_BYTES - len(image)
    zero = bytes(1024 * 1024)
    while remaining:
        take = min(remaining, len(zero))
        yield zero[:take]
        remaining -= take


def all_zero_slot():
    remaining = SLOT_BYTES
    zero = bytes(1024 * 1024)
    while remaining:
        take = min(remaining, len(zero))
        yield zero[:take]
        remaining -= take


def check_card_root(root: Path) -> None:
    if not root.is_dir():
        raise ProvisionError(f"card root is not a directory: {root}")
    missing = [name for name in REQUIRED_FIRMWARE if not (root / name).is_file()]
    if missing:
        raise ProvisionError(
            "the selected directory is not the prepared Pi 3 boot volume; "
            "required files are missing: " + ", ".join(missing)
        )
    resolved = root.resolve()
    system_drive = Path(os.environ.get("SystemDrive", "C:") + "\\").resolve()
    if resolved == system_drive:
        raise ProvisionError("refusing to provision the Windows system drive")


def check_boot_contract(root: Path, loader: Path, loader_sha256: str) -> None:
    try:
        validate_pinned_boot(root, loader, loader_sha256)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ProvisionError(f"Pi 3 pinned boot contract refused: {exc}") from exc
    pinned_config = (PINNED_BOOT / "config.txt").read_bytes()
    if (root / "config.txt").read_bytes() != pinned_config:
        raise ProvisionError(
            "card config.txt is not the pinned AArch64 loader/DTB/PL011 contract"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-root", required=True, type=Path)
    parser.add_argument("--loader", required=True, type=Path)
    parser.add_argument(
        "--loader-pmf",
        type=Path,
        help="compiler PMFBOOT v2 sidecar (default: <loader>.pmf)",
    )
    parser.add_argument(
        "--monitor",
        required=True,
        type=Path,
        help="build-produced updater P3SLOT image",
    )
    parser.add_argument(
        "--yes-replace-kernel8",
        action="store_true",
        help="required acknowledgement that kernel8.img will be replaced",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.yes_replace_kernel8:
        raise ProvisionError(
            "kernel8.img replacement was not acknowledged; add "
            "--yes-replace-kernel8 after checking --card-root"
        )
    check_card_root(args.card_root)
    loader_pmf_path = args.loader_pmf or Path(str(args.loader) + ".pmf")
    if not args.loader.is_file() or not loader_pmf_path.is_file() or not args.monitor.is_file():
        raise ProvisionError("loader, loader PMF sidecar, and monitor must all be existing files")
    loader = args.loader.read_bytes()
    loader_pmf = loader_pmf_path.read_bytes()
    monitor = args.monitor.read_bytes()
    if not loader or len(loader) > LOADER_MAX:
        raise ProvisionError(
            f"loader must contain 1..{LOADER_MAX} bytes; got {len(loader)}"
        )
    try:
        loader_metadata = validate_loader_pmf(loader_pmf, loader)
        monitor_metadata = validate_slot(monitor)
    except SlotError as exc:
        raise ProvisionError(f"monitor slot refused: {exc}") from exc
    if len(monitor) > SLOT_BYTES:
        raise ProvisionError(
            f"wrapped monitor must fit {SLOT_BYTES} bytes; got {len(monitor)}"
        )

    loader_sha256 = hashlib.sha256(loader).hexdigest()
    check_boot_contract(args.card_root, args.loader, loader_sha256)

    root = args.card_root.resolve()
    outputs = {
        "ANVILA.BIN": padded_image(monitor),
        "ANVILB.BIN": all_zero_slot(),
        "P3CTRLA.BIN": [control_record(0, 1, monitor)],
        "P3CTRLB.BIN": [bytes(512)],
        "kernel8.img": [loader],
    }
    expected: dict[str, str] = {}
    for name, chunks in outputs.items():
        target = root / name
        print(f"writing {target}")
        write_atomic(target, chunks)
        expected[name] = sha256(target)

    # Re-open every file and enforce exact sizes after replacement.
    sizes = {
        "ANVILA.BIN": SLOT_BYTES,
        "ANVILB.BIN": SLOT_BYTES,
        "P3CTRLA.BIN": 512,
        "P3CTRLB.BIN": 512,
        "kernel8.img": len(loader),
    }
    for name, size in sizes.items():
        actual = (root / name).stat().st_size
        if actual != size:
            raise ProvisionError(f"readback size mismatch for {name}: {actual} != {size}")

    manifest = {
        "format": "Anvil Pi3 A/B provision 2",
        "slotFormat": "P3SLOT 1 containing PMFBOOT 2",
        "slotBytes": SLOT_BYTES,
        "loadAddress": hex(LOAD_ADDRESS),
        "activeSlot": "A",
        "generation": 1,
        "monitorLength": len(monitor),
        "monitorSha256": hashlib.sha256(monitor).hexdigest(),
        "monitorPmfLength": monitor_metadata["pmfBytes"],
        "monitorPmfSha256": monitor_metadata["pmfSha256"],
        "monitorMetadata": monitor_metadata,
        "loaderSha256": loader_sha256,
        "loaderPmfSha256": hashlib.sha256(loader_pmf).hexdigest(),
        "loaderMetadata": loader_metadata,
        "firmwarePin": json.loads((PINNED_BOOT / "firmware.json").read_text(encoding="utf-8")),
        "files": {name: {"bytes": sizes[name], "sha256": expected[name]} for name in sizes},
        "finalBoardGate": "loader must accept every file as contiguous and hash-valid",
    }
    manifest_path = root / "P3UPDATE.JSON"
    write_atomic(
        manifest_path,
        [json.dumps(manifest, indent=2, sort_keys=True).encode("ascii") + b"\n"],
    )
    print(f"wrote {manifest_path}")
    print("provisioning readback passed; board contiguity/hash acceptance remains")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisionError as exc:
        print(f"!! {exc}", file=sys.stderr)
        raise SystemExit(1)
