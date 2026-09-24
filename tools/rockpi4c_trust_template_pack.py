#!/usr/bin/env python3
"""Replace the monitor in a validated single-component Rock Pi BL3X image.

The EL3 entry occupies the first 4 KiB. The board DTB is also embedded at
0x001C0000 near the end of the component. Both must survive replacement.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import struct
import tempfile

from rockpi4c_update import (
    ANVIL_BASE,
    HEADER,
    TRUST_COPY,
    TRUST_HEAD,
    validate_trust_image,
)

ENTRY_BYTES = 4096
MONITOR_ADDRESS = 0x41000
DTB_ADDRESS = 0x1C0000
DTB_MAGIC = 0xD00DFEED


def pack(template: bytes, monitor: bytes) -> bytes:
    components = validate_trust_image(template)
    if len(components) != 1 or components[0]["address"] != ANVIL_BASE:
        raise ValueError("template is not the single-component Anvil layout")
    dtb_offset = DTB_ADDRESS - ANVIL_BASE
    if not monitor or len(monitor) > dtb_offset - ENTRY_BYTES:
        raise ValueError("monitor overlaps the fixed embedded DTB")

    copy = bytearray(template[:TRUST_COPY])
    count_and_offset = struct.unpack_from("<I", copy, 12)[0]
    table = ((count_and_offset & 0xFFFF) << 2) + 256
    _, sector, sectors, _ = struct.unpack_from("<4I", copy, table)
    start = sector * 512
    size = sectors * 512
    if start != HEADER or size != components[0]["bytes"]:
        raise ValueError("template component boundaries changed")
    if ANVIL_BASE + ENTRY_BYTES != MONITOR_ADDRESS:
        raise ValueError("monitor link address differs from entry handoff")
    if dtb_offset + 8 > size:
        raise ValueError("template has no room for the embedded DTB")
    dtb_start = start + dtb_offset
    if int.from_bytes(copy[dtb_start:dtb_start + 4], "big") != DTB_MAGIC:
        raise ValueError("template embedded DTB magic is missing")
    dtb_size = int.from_bytes(copy[dtb_start + 4:dtb_start + 8], "big")
    if dtb_size < 72 or dtb_offset + dtb_size > size:
        raise ValueError("template embedded DTB size is invalid")

    entry = bytes(copy[start:start + ENTRY_BYTES])
    fixed_tail = bytes(copy[dtb_start:start + size])
    padded = (entry + monitor +
              bytes(dtb_offset - ENTRY_BYTES - len(monitor)) + fixed_tail)
    copy[start:start + size] = padded
    copy[TRUST_HEAD:TRUST_HEAD + 32] = hashlib.sha256(padded).digest()
    result = bytes(copy) * 2
    validate_trust_image(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("monitor", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.resolve() in (args.template.resolve(), args.monitor.resolve()):
        raise SystemExit("output must not replace an input")
    if args.output.exists():
        raise SystemExit("output already exists")

    image = pack(args.template.read_bytes(), args.monitor.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix=".trust-stage-", delete=False) as staged:
        temporary = Path(staged.name)
        staged.write(image)
        staged.flush()
        os.fsync(staged.fileno())
    try:
        os.replace(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"{args.output}: {len(image)} bytes, SHA-256 {hashlib.sha256(image).hexdigest()}")


if __name__ == "__main__":
    main()
