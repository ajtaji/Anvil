#!/usr/bin/env python3
"""Pi 3 A/B slot container contract shared by build, provision and update tools."""

from __future__ import annotations

import hashlib
import struct


LOAD_ADDRESS = 0x200000
IMAGE_LIMIT = 0x1000000
BSS_ADDRESS = 0x1100000
BSS_LIMIT = 0x1E00000
STACK_ADDRESS = 0x1F00000
SLOT_MAGIC = b"P3SLOT\0\0"
SLOT_VERSION = 1
SLOT_HEADER_BYTES = 128
SLOT_TARGET = 2837
SLOT_ISA = 64
PMF_MAGIC = b"PMFBOOT\0"
PMF_VERSION = 2
PMF_HEADER_BYTES = 128
PMF_ARCH_AARCH64 = 1
LOADER_LOAD_ADDRESS = 0x80000
LOADER_IMAGE_LIMIT = 0x180000
LOADER_BSS_ADDRESS = 0x180000
LOADER_BSS_LIMIT = 0x1F0000
LOADER_STACK_ADDRESS = 0x200000


class SlotError(RuntimeError):
    pass


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def validate_pmf(
    pmf: bytes,
    *,
    name: str,
    load_address: int,
    image_limit: int,
    bss_address: int,
    bss_limit: int,
    stack_address: int,
) -> dict[str, int | str]:
    """Validate one compiler-emitted BCM2837 PMFBOOT v2 container."""
    if len(pmf) < PMF_HEADER_BYTES + 4:
        raise SlotError(f"{name} PMF is too short")
    if pmf[:8] != PMF_MAGIC:
        raise SlotError(f"{name} is not a PMFBOOT container")
    if u32(pmf, 8) != PMF_VERSION or u32(pmf, 12) != PMF_HEADER_BYTES:
        raise SlotError(f"{name} PMFBOOT version/header length is unsupported")
    load = u64(pmf, 16)
    entry = u64(pmf, 24)
    image_bytes = u64(pmf, 32)
    bss_base = u64(pmf, 40)
    bss_bytes = u64(pmf, 48)
    flags = u32(pmf, 56)
    reserved = u32(pmf, 60)
    architecture = u32(pmf, 96)
    target = u32(pmf, 100)
    stack = u64(pmf, 104)
    if image_bytes < 4 or image_bytes != len(pmf) - PMF_HEADER_BYTES:
        raise SlotError(f"{name} PMF image length does not match the file")
    if load != load_address or entry != load_address:
        raise SlotError(f"{name} PMF must load and enter at 0x{load_address:X}")
    if load + image_bytes > image_limit:
        raise SlotError(f"{name} image reaches its reserved memory boundary")
    if bss_base != bss_address or bss_bytes > bss_limit - bss_address:
        raise SlotError(
            f"{name} BSS must start at 0x{bss_address:X} and end by 0x{bss_limit:X}"
        )
    if flags != 0 or reserved != 0:
        raise SlotError(
            f"Pi 3 {name} must be non-returning and request no PMF service ABI"
        )
    if architecture != PMF_ARCH_AARCH64 or target != SLOT_TARGET:
        raise SlotError(f"{name} PMF was not compiled for BCM2837 AArch64")
    if stack != stack_address:
        raise SlotError(f"{name} PMF stack must be 0x{stack_address:X}")
    if pmf[112:128] != bytes(16):
        raise SlotError(f"{name} PMF version-2 reserved bytes are not zero")
    actual_image_sha = hashlib.sha256(pmf[PMF_HEADER_BYTES:]).digest()
    if actual_image_sha != pmf[64:96]:
        raise SlotError(f"{name} PMF image SHA-256 does not match its header")
    return {
        "loadAddress": load,
        "entryAddress": entry,
        "imageBytes": image_bytes,
        "bssAddress": bss_base,
        "bssBytes": bss_bytes,
        "stackAddress": stack_address,
        "architecture": architecture,
        "target": target,
        "pmfBytes": len(pmf),
        "pmfSha256": hashlib.sha256(pmf).hexdigest(),
    }


def validate_monitor_pmf(pmf: bytes) -> dict[str, int | str]:
    """Validate the replaceable serial updater monitor."""
    return validate_pmf(
        pmf,
        name="monitor",
        load_address=LOAD_ADDRESS,
        image_limit=IMAGE_LIMIT,
        bss_address=BSS_ADDRESS,
        bss_limit=BSS_LIMIT,
        stack_address=STACK_ADDRESS,
    )


def validate_loader_pmf(pmf: bytes, raw_image: bytes) -> dict[str, int | str]:
    """Prove that kernel8.img is the payload of the immutable loader PMF."""
    metadata = validate_pmf(
        pmf,
        name="loader",
        load_address=LOADER_LOAD_ADDRESS,
        image_limit=LOADER_IMAGE_LIMIT,
        bss_address=LOADER_BSS_ADDRESS,
        bss_limit=LOADER_BSS_LIMIT,
        stack_address=LOADER_STACK_ADDRESS,
    )
    if pmf[PMF_HEADER_BYTES:] != raw_image:
        raise SlotError("kernel8.img is not the exact image carried by the loader PMF")
    return metadata


def wrap_monitor(pmf: bytes) -> tuple[bytes, dict[str, int | str]]:
    metadata = validate_monitor_pmf(pmf)
    header = bytearray(SLOT_HEADER_BYTES)
    struct.pack_into(
        "<8sIIIIQQ",
        header,
        0,
        SLOT_MAGIC,
        SLOT_VERSION,
        SLOT_HEADER_BYTES,
        SLOT_TARGET,
        SLOT_ISA,
        STACK_ADDRESS,
        len(pmf),
    )
    header[40:72] = hashlib.sha256(pmf).digest()
    slot = bytes(header) + pmf
    return slot, {**metadata, "slotBytes": len(slot), "slotSha256": hashlib.sha256(slot).hexdigest()}


def validate_slot(slot: bytes) -> dict[str, int | str]:
    if len(slot) < SLOT_HEADER_BYTES + PMF_HEADER_BYTES + 4:
        raise SlotError("P3SLOT file is too short")
    if slot[:8] != SLOT_MAGIC:
        raise SlotError("monitor is not a P3SLOT container")
    version, header, target, isa = struct.unpack_from("<IIII", slot, 8)
    stack, pmf_bytes = struct.unpack_from("<QQ", slot, 24)
    if version != SLOT_VERSION or header != SLOT_HEADER_BYTES:
        raise SlotError("P3SLOT version/header length is unsupported")
    if target != SLOT_TARGET or isa != SLOT_ISA or stack != STACK_ADDRESS:
        raise SlotError("P3SLOT target, ISA or stack policy is wrong for BCM2837")
    if pmf_bytes != len(slot) - SLOT_HEADER_BYTES:
        raise SlotError("P3SLOT PMF length does not match the file")
    if slot[72:128] != bytes(56):
        raise SlotError("P3SLOT reserved bytes are not zero")
    pmf = slot[SLOT_HEADER_BYTES:]
    if hashlib.sha256(pmf).digest() != slot[40:72]:
        raise SlotError("P3SLOT PMF SHA-256 does not match its header")
    metadata = validate_monitor_pmf(pmf)
    return {**metadata, "slotBytes": len(slot), "slotSha256": hashlib.sha256(slot).hexdigest()}
