#!/usr/bin/env python3
"""Check that monitor replacement preserves the fixed EL3 entry and board DTB."""

from __future__ import annotations

import hashlib
import struct
from unittest.mock import patch

import rockpi4c_trust_template_pack as packer
from rockpi4c_update import ANVIL_BASE, HEADER, TRUST_COPY


def make_template() -> bytes:
    copy = bytearray(TRUST_COPY)
    copy[:4] = b"BL3X"
    struct.pack_into("<I", copy, 12, (1 << 16) | ((packer.TRUST_HEAD + 48) // 4))
    table = packer.TRUST_HEAD + 48 + 256
    struct.pack_into("<4I", copy, table, 0, HEADER // 512, (TRUST_COPY - HEADER) // 512, 0)

    entry = HEADER
    copy[entry:entry + packer.ENTRY_BYTES] = b"E" * packer.ENTRY_BYTES
    dtb = HEADER + packer.DTB_ADDRESS - ANVIL_BASE
    struct.pack_into(">II", copy, dtb, packer.DTB_MAGIC, 80)
    copy[dtb + 8:dtb + 80] = bytes(range(72))
    copy[dtb + 80:dtb + 96] = b"TAIL-SENTINEL-01"
    return bytes(copy) * 2


def main() -> None:
    template = make_template()
    component_bytes = TRUST_COPY - HEADER
    metadata = [{"address": ANVIL_BASE, "bytes": component_bytes}]
    monitor = b"MONITOR" * 1024
    with patch.object(packer, "validate_trust_image", return_value=metadata) as validate:
        result = packer.pack(template, monitor)
        assert validate.call_count == 2
    assert len(result) == 2 * TRUST_COPY
    assert result[:TRUST_COPY] == result[TRUST_COPY:]

    start = HEADER
    dtb = start + packer.DTB_ADDRESS - ANVIL_BASE
    assert result[start:start + packer.ENTRY_BYTES] == template[start:start + packer.ENTRY_BYTES]
    assert result[start + packer.ENTRY_BYTES:start + packer.ENTRY_BYTES + len(monitor)] == monitor
    assert result[start + packer.ENTRY_BYTES + len(monitor):dtb] == bytes(dtb - start - packer.ENTRY_BYTES - len(monitor))
    assert result[dtb:TRUST_COPY] == template[dtb:TRUST_COPY]
    assert result[dtb:dtb + 4] == bytes.fromhex("d00dfeed")
    assert result[packer.TRUST_HEAD:packer.TRUST_HEAD + 32] == hashlib.sha256(result[start:TRUST_COPY]).digest()

    too_large = bytes(packer.DTB_ADDRESS - ANVIL_BASE - packer.ENTRY_BYTES + 1)
    with patch.object(packer, "validate_trust_image", return_value=metadata):
        try:
            packer.pack(template, too_large)
        except ValueError as exc:
            assert "overlaps" in str(exc)
        else:
            raise AssertionError("monitor/DTB overlap was accepted")
    print("PASS: entry, monitor, both DTB copies, fixed tail, digest, overlap guard")


if __name__ == "__main__":
    main()
