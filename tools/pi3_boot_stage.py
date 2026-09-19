#!/usr/bin/env python3
"""Validate Pi 3 firmware and direct Anvil artifacts; optionally create a new bundle.

This never selects, formats, or writes a disk. The input monitor and stub must
be exact counted build artifacts whose hashes are supplied for review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from pi3_slot import PMF_HEADER_BYTES, SlotError, validate_pmf

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "RaspberryPi3" / "Boot"
STUB_LICENSE = ROOT / "licenses" / "RaspberryPi-armstub8-BSD-3-Clause.txt"

# These are board.pi3's declared firmware contract, not the legacy A/B loader
# contract. The generic PMF reader verifies the compiler metadata against them.
LOAD_ADDRESS = 0x200000
IMAGE_LIMIT = 0x1000000
BSS_ADDRESS = 0x1100000
BSS_LIMIT = 0x1E00000
STACK_ADDRESS = 0x1F00000
TARGET_ID = 2837


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_config(path: Path) -> None:
    settings: dict[str, list[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if not line or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        settings.setdefault(key, []).append(value)
    expected = {
        "arm_64bit": "1", "kernel": "kernel8.img",
        "kernel_address": "0x200000", "armstub": "armstub8.bin",
        "device_tree": "bcm2710-rpi-3-b.dtb",
        "device_tree_address": "0x1000000",
    }
    for key, value in expected.items():
        if settings.get(key) != [value]:
            raise ValueError(
                f"Pi 3 config must contain exactly one `{key}={value}` setting "
                "and no conflicting duplicate"
            )
    for key in ("include", "kernel_old", "initramfs", "os_prefix", "tryboot", "tryboot_ram"):
        if settings.get(key):
            raise ValueError(f"Pi 3 direct-boot config may not contain `{key}` overrides")


def validate_armstub(path: Path) -> None:
    raw = path.read_bytes()
    if len(raw) < 0x200 or len(raw) % 0x100:
        raise ValueError(
            "Pi 3 armstub8.bin must be at least 512 bytes and 256-byte aligned; "
            f"got {len(raw)}"
        )
    if raw[0xF0:0xF4] != bytes.fromhex("0b57fe5a"):
        raise ValueError("Pi 3 armstub8.bin firmware magic at offset 0xF0 is incorrect")
    if raw[0xF4:0x100] != bytes(12):
        raise ValueError("Pi 3 armstub8.bin firmware version/DTB/kernel fields must be zero")


def validate_image(image: Path, pmf_path: Path) -> dict[str, int | str]:
    if not image.is_file() or image.stat().st_size == 0:
        raise ValueError("Full Anvil kernel8.img is missing or empty")
    if not pmf_path.is_file():
        raise ValueError(f"The monitor PMF sidecar is missing: {pmf_path}")
    pmf = pmf_path.read_bytes()
    try:
        metadata = validate_pmf(
            pmf, name="direct Pi 3 monitor", load_address=LOAD_ADDRESS,
            image_limit=IMAGE_LIMIT, bss_address=BSS_ADDRESS,
            bss_limit=BSS_LIMIT, stack_address=STACK_ADDRESS,
        )
    except SlotError as error:
        raise ValueError(str(error)) from error
    raw = image.read_bytes()
    if pmf[PMF_HEADER_BYTES:] != raw:
        raise ValueError("kernel8.img is not the exact raw image in its PMF sidecar")
    if metadata["target"] != TARGET_ID:
        raise ValueError("kernel8.img PMF target is not BCM2837")
    return metadata


def validate(
    firmware: Path, image: Path, expected_image_sha256: str,
    armstub: Path, expected_armstub_sha256: str,
    image_pmf: Path | None = None,
) -> tuple[dict[str, Path], dict[str, int | str]]:
    manifest = json.loads((BOOT / "firmware.json").read_text(encoding="utf-8"))
    sources: dict[str, Path] = {}
    for name, expected in manifest["files"].items():
        path = firmware / name
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"Pinned Raspberry Pi firmware mismatch: {name}")
        sources[name] = path

    if not image.is_file() or sha(image) != expected_image_sha256.lower():
        raise ValueError("kernel8.img is missing or differs from the accepted SHA-256")
    if not armstub.is_file() or not armstub.stat().st_size:
        raise ValueError("Pi 3 armstub8.bin is missing or empty")
    if sha(armstub) != expected_armstub_sha256.lower():
        raise ValueError("armstub8.bin differs from the accepted SHA-256")
    validate_armstub(armstub)

    config = BOOT / "config.txt"
    validate_config(config)
    stub_license = STUB_LICENSE
    if not stub_license.is_file():
        raise ValueError(f"Pi 3 armstub license is missing: {stub_license}")
    pmf_path = image_pmf or Path(str(image) + ".pmf")
    metadata = validate_image(image, pmf_path)
    sources.update({
        "armstub8.bin": armstub,
        "kernel8.img": image,
        "config.txt": config,
        "README.txt": BOOT / "README.txt",
        "firmware.json": BOOT / "firmware.json",
        "RaspberryPi-armstub8-BSD-3-Clause.txt": stub_license,
    })
    return sources, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", required=True, type=Path,
                        help="directory containing the exact pinned firmware files")
    parser.add_argument("--image", required=True, type=Path,
                        help="counted full-monitor image for kernel8.img")
    parser.add_argument("--image-pmf", type=Path,
                        help="PMF sidecar (default: <image>.pmf)")
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--armstub", required=True, type=Path,
                        help="counted Pi 3-specific armstub8.bin")
    parser.add_argument("--armstub-sha256", required=True)
    parser.add_argument("--output", type=Path,
                        help="create this new staging folder; omit for read-only validation")
    args = parser.parse_args()

    sources, image_metadata = validate(
        args.firmware, args.image, args.image_sha256, args.armstub,
        args.armstub_sha256, args.image_pmf,
    )
    hashes = {name: sha(path) for name, path in sources.items()}
    record = {
        "format": "Anvil Pi 3 direct boot bundle 1",
        "files": {name: {"bytes": path.stat().st_size, "sha256": hashes[name]}
                  for name, path in sources.items()},
        "monitorPmf": image_metadata,
    }
    if args.output:
        output = args.output.absolute()
        if output.exists() or output.parent.resolve() == output.resolve():
            raise ValueError("Output must be a new directory, never an existing folder or drive root")
        output.mkdir(parents=False, exist_ok=False)
        for name, source in sources.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha(target) != hashes[name]:
                raise ValueError(f"Copy verification failed for {name}; staging retained")
        (output / "SHA256.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Bundle manifest SHA-256: {sha(output / 'SHA256.json')}")

    print(json.dumps(record, indent=2, sort_keys=True))
    print("PASS: direct Pi 3 firmware bundle validated; no disk was selected or written")
    return 0


if __name__ == "__main__":
    main()
