#!/usr/bin/env python3
"""Bundle an RK3399 Anvil trust image without rebuilding board artifacts.

The existing BL3X packer emits two identical 2 MiB copies. This command only
reads Anvil's EL3 entry, runtime, and board data, combines them into one
self-contained Anvil binary, then writes that as the trust image's sole loaded
component. It never builds DDR/IDB or writes media. Rockchip's old host merger
used a 512 KiB scratch buffer, but the loader format stores a sector count and
the loader reads that full count.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile

import rockpi4c_sd_trust as trust
import rockpi4c_sd_entry_check as entry_contract

ANVIL_ADDRESS = 0x00040000
PAYLOAD_ADDRESS = 0x00041000
DTB_ADDRESS = 0x001C0000
ANVIL_LIMIT = 0x00240000
BSS_ADDRESS = 0x02800000
STACK_ADDRESS = 0x05000000
IMAGE_KIB = 2048
COPIES = 2
COMPONENT_ID = trust.parse_id("BL31")


class BundleError(ValueError):
    """Input artifacts do not satisfy the fixed direct-SD trust contract."""


def validate_payload_pmf(payload: bytes, sidecar: bytes) -> None:
    """Reject a flat runtime linked for any address other than the SD handoff."""
    if len(sidecar) < 128 or sidecar[:8] != b"PMFBOOT\x00":
        raise BundleError("runtime PMF sidecar is missing or malformed")
    version, header_size = struct.unpack_from("<II", sidecar, 8)
    if version != 2 or header_size != 128 or len(sidecar) != 128 + len(payload):
        raise BundleError("runtime PMF v2 length differs from flat payload")
    load, entry, image_size, bss, bss_size = struct.unpack_from("<QQQQQ", sidecar, 16)
    arch, target, stack = struct.unpack_from("<IIQ", sidecar, 96)
    if (load, entry, image_size, bss, arch, target, stack) != (
        PAYLOAD_ADDRESS, PAYLOAD_ADDRESS, len(payload), BSS_ADDRESS, 1, 3399,
        STACK_ADDRESS,
    ):
        raise BundleError("runtime PMF load/BSS/stack address contract differs from direct SD")
    if bss_size < 1 or bss + bss_size > STACK_ADDRESS - 0x10000:
        raise BundleError("runtime PMF BSS exceeds the reserved stack window")
    if hashlib.sha256(payload).digest() != sidecar[64:96] or sidecar[128:] != payload:
        raise BundleError("runtime PMF payload hash or bytes differ from flat payload")


def make_components(entry: bytes, payload: bytes, dtb: bytes,
                    *, entry_source: Path = Path("entry"),
                    payload_source: Path = Path("payload"),
                    dtb_source: Path = Path("dtb")) -> list[trust.Component]:
    if not entry:
        raise BundleError("entry stub is empty")
    if not payload:
        raise BundleError("Anvil payload is empty")
    if not dtb:
        raise BundleError("device tree is empty")

    if len(entry) > PAYLOAD_ADDRESS - ANVIL_ADDRESS:
        raise BundleError("Anvil EL3 entry exceeds its 4 KiB prefix")
    try:
        entry_contract.check(entry, quiet=True)
    except (AssertionError, RuntimeError, ValueError, IndexError) as exc:
        raise BundleError(
            "entry stub fails the EL3/DTB/runtime-address contract "
            "(expected DTB 0x001c0000 and branch 0x00041000)"
        ) from exc
    code_end = PAYLOAD_ADDRESS + len(payload)
    padded_code_end = PAYLOAD_ADDRESS + trust.align_up(len(payload), trust.ALIGNMENT)
    if code_end > DTB_ADDRESS or padded_code_end > DTB_ADDRESS:
        raise BundleError(
            f"runtime must end before embedded board data at 0x{DTB_ADDRESS:08x} "
            f"(raw end 0x{code_end:08x}, padded end 0x{padded_code_end:08x})"
        )
    anvil_end = DTB_ADDRESS + len(dtb)
    if anvil_end > ANVIL_LIMIT:
        raise BundleError("embedded board data exceeds Anvil's fixed load window")
    anvil = bytearray(anvil_end - ANVIL_ADDRESS)
    anvil[:len(entry)] = entry
    runtime_offset = PAYLOAD_ADDRESS - ANVIL_ADDRESS
    anvil[runtime_offset:runtime_offset + len(payload)] = payload
    dtb_offset = DTB_ADDRESS - ANVIL_ADDRESS
    anvil[dtb_offset:dtb_offset + len(dtb)] = dtb
    components = [trust.Component(COMPONENT_ID, ANVIL_ADDRESS, bytes(anvil), payload_source)]

    # Enforce the total per-copy budget here as a clear bundler contract;
    # build_image repeats the limit check while laying out the trust table.
    data_bytes = sum(component.padded_size for component in components)
    total_bytes = trust.HEADER_SIZE + data_bytes
    if total_bytes > IMAGE_KIB * 1024:
        raise BundleError(
            f"components need {total_bytes} bytes, exceeding {IMAGE_KIB} KiB per-copy budget"
        )
    return components


def build_anvil(entry: bytes, payload: bytes, dtb: bytes) -> bytes:
    return make_components(entry, payload, dtb)[0].data


def build_bundle(entry: bytes, payload: bytes, dtb: bytes,
                 *, entry_source: Path = Path("entry"),
                 payload_source: Path = Path("payload"),
                 dtb_source: Path = Path("dtb")) -> bytes:
    components = make_components(
        entry, payload, dtb, entry_source=entry_source,
        payload_source=payload_source, dtb_source=dtb_source,
    )
    try:
        return trust.build_image(components, image_kib=IMAGE_KIB, copies=COPIES)
    except ValueError as exc:
        raise BundleError(str(exc)) from exc


def atomic_write(path: Path, data: bytes) -> None:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", required=True, type=Path,
                        help="compiled direct-SD entry stub, loaded at 0x40000")
    parser.add_argument("--payload", required=True, type=Path,
                        help="already-built Anvil runtime, loaded at 0x00041000")
    parser.add_argument("--dtb", required=True, type=Path,
                        help="already-built RK3399 DTB, embedded at 0x001C0000")
    parser.add_argument("--output", required=True, type=Path,
                        help="output BL3X trust image (4 MiB, two identical copies)")
    parser.add_argument("--anvil-output", type=Path,
                        help="also write the exact self-contained Anvil binary")
    args = parser.parse_args(argv)

    try:
        entry = args.entry.read_bytes()
        payload = args.payload.read_bytes()
        validate_payload_pmf(payload, Path(str(args.payload) + ".pmf").read_bytes())
        dtb = args.dtb.read_bytes()
        image = build_bundle(
            entry, payload, dtb,
            entry_source=args.entry, payload_source=args.payload,
            dtb_source=args.dtb,
        )
        atomic_write(args.output, image)
        if args.anvil_output:
            atomic_write(args.anvil_output, build_anvil(entry, payload, dtb))
    except (OSError, BundleError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {len(image)} bytes to {args.output}")
    anvil_size = DTB_ADDRESS + len(dtb) - ANVIL_ADDRESS
    print(f"BL31 Anvil @0x{ANVIL_ADDRESS:08x}: one {anvil_size}-byte component")
    print(f"  EL3 entry: {len(entry)} bytes; runtime @0x{PAYLOAD_ADDRESS:08x}: {len(payload)} bytes")
    print(f"  embedded board data @0x{DTB_ADDRESS:08x}: {len(dtb)} bytes")
    print(f"sha256 {hashlib.sha256(image).hexdigest()}; no DDR/IDB build or block device access")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
