#!/usr/bin/env python3
"""Build an unsigned Rockchip BL3X trust image from raw loadable components.

This writes the legacy 2 KiB-header trust format consumed by Rockchip
miniloaders. It does not make the IDB/SD boot image and does not authenticate
components. Each component is a flat binary with an explicit 32-bit load
address and four-byte component ID.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


HEADER_SIZE = 2048
TRUST_HEAD_SIZE = 800
COMPONENT_DATA_SIZE = 48
COMPONENT_ENTRY_SIZE = 16
SIGNATURE_SIZE = 256
ALIGNMENT = 2048
MAX_COMPONENTS = 32
DEFAULT_IMAGE_KIB = 2048
DEFAULT_COPIES = 2


@dataclass(frozen=True)
class Component:
    component_id: bytes
    load_address: int
    data: bytes
    source: Path

    @property
    def padded_size(self) -> int:
        return align_up(len(self.data), ALIGNMENT)


def align_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


def parse_id(value: str) -> bytes:
    # IDs are the four bytes stored in the Rockchip component table (e.g. BL31).
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise argparse.ArgumentTypeError("component ID must be four ASCII bytes") from exc
    if len(encoded) != 4:
        raise argparse.ArgumentTypeError("component ID must be exactly four ASCII bytes")
    return encoded


def parse_address(value: str) -> int:
    try:
        address = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid address: {value}") from exc
    if not 0 <= address <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("load address must fit in 32 bits")
    return address


def parse_component(spec: str) -> Component:
    """Parse ID@ADDRESS=PATH; split only at the first '=' for paths with '='."""
    try:
        left, raw_path = spec.split("=", 1)
        component_id, raw_address = left.split("@", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "component must be ID@ADDRESS=PATH (example: BL31@0x40000=stage.bin)"
        ) from exc
    cid = parse_id(component_id)
    address = parse_address(raw_address)
    path = Path(raw_path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise argparse.ArgumentTypeError(f"cannot read component {path}: {exc}") from exc
    if not data:
        raise argparse.ArgumentTypeError(f"component is empty: {path}")
    return Component(cid, address, data, path)


def bcd_byte(value: int) -> int:
    if not 0 <= value <= 99:
        raise ValueError("major/minor version must be in 0..99")
    return ((value // 10) << 4) | (value % 10)


def build_image(
    components: list[Component],
    *,
    major: int = 1,
    minor: int = 0,
    image_kib: int = DEFAULT_IMAGE_KIB,
    copies: int = DEFAULT_COPIES,
    rsa_mode: int = 2,
) -> bytes:
    if not components:
        raise ValueError("at least one component is required")
    if len(components) > MAX_COMPONENTS:
        raise ValueError(f"at most {MAX_COMPONENTS} components are supported")
    if image_kib <= 0 or image_kib % 64:
        raise ValueError("per-copy image size must be a positive multiple of 64 KiB")
    if copies <= 0:
        raise ValueError("copy count must be positive")
    if not 0 <= rsa_mode <= 3:
        raise ValueError("RSA mode must be 0..3")

    version = (bcd_byte(major) << 8) | bcd_byte(minor)
    payload_offset = HEADER_SIZE
    table_entries: list[bytes] = []
    component_data_entries: list[bytes] = []
    payloads: list[bytes] = []

    for component in components:
        padded_size = component.padded_size
        if component.load_address + len(component.data) > 0x1_0000_0000:
            raise ValueError(f"{component.source} load range exceeds 32-bit address space")
        padded = component.data + bytes(padded_size - len(component.data))
        storage_sector = payload_offset // 512
        size_sectors = padded_size // 512
        table_entries.append(
            struct.pack("<4I", int.from_bytes(component.component_id, "little"), storage_sector,
                        size_sectors, 0)
        )
        digest = hashlib.sha256(padded).digest()
        component_data_entries.append(
            digest
            + struct.pack("<4I", component.load_address, size_sectors, 0, 0)
        )
        payloads.append(padded)
        payload_offset += padded_size

    sign_offset = TRUST_HEAD_SIZE + len(components) * COMPONENT_DATA_SIZE
    if sign_offset + SIGNATURE_SIZE + len(components) * COMPONENT_ENTRY_SIZE > HEADER_SIZE:
        raise ValueError("component metadata does not fit in the 2 KiB header")
    if payload_offset > image_kib * 1024:
        raise ValueError(
            f"components need {payload_offset} bytes, exceeding {image_kib} KiB per-copy image size"
        )

    header = bytearray(HEADER_SIZE)
    # TRUST_HEADER: BL3X, BCD version, hash/RSA selector flags, count/sign offset.
    struct.pack_into("<4sIII", header, 0, b"BL3X", version, 3 | (rsa_mode << 4),
                     (len(components) << 16) | (sign_offset >> 2))
    # remaining TRUST_HEADER fields and the signature block are zero-filled.
    cursor = TRUST_HEAD_SIZE
    for entry in component_data_entries:
        header[cursor:cursor + COMPONENT_DATA_SIZE] = entry
        cursor += COMPONENT_DATA_SIZE
    cursor = sign_offset + SIGNATURE_SIZE
    for entry in table_entries:
        header[cursor:cursor + COMPONENT_ENTRY_SIZE] = entry
        cursor += COMPONENT_ENTRY_SIZE

    one_copy = bytearray(image_kib * 1024)
    one_copy[:HEADER_SIZE] = header
    cursor = HEADER_SIZE
    for payload in payloads:
        one_copy[cursor:cursor + len(payload)] = payload
        cursor += len(payload)
    return bytes(one_copy) * copies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--component", action="append", type=parse_component, required=True,
        metavar="ID@ADDRESS=PATH",
        help="raw flat component; repeat in load order (e.g. BL31@0x40000=stage.bin)",
    )
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--major", type=int, default=1)
    parser.add_argument("--minor", type=int, default=0)
    parser.add_argument("--image-kib", type=int, default=DEFAULT_IMAGE_KIB,
                        help="size of each trust image copy; default 2048")
    parser.add_argument("--copies", type=int, default=DEFAULT_COPIES,
                        help="redundant copies; default 2")
    parser.add_argument("--rsa-mode", type=int, default=2,
                        help="Rockchip header flag only; default 2, use 0 for unsigned mode")
    args = parser.parse_args(argv)

    try:
        image = build_image(args.component, major=args.major, minor=args.minor,
                            image_kib=args.image_kib, copies=args.copies,
                            rsa_mode=args.rsa_mode)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(image)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {len(image)} bytes ({args.image_kib} KiB x {args.copies}) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
