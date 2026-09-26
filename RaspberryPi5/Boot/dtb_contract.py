"""Validate the pinned Pi 5 firmware DTBs before Anvil board bring-up.

This host tool reads explicit DTB paths only. It does not infer the live
bootloader-modified tree; the eventual image must validate x0 again at boot.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

MAGIC = 0xD00DFEED
BEGIN_NODE, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9
HEADER = struct.Struct(">10I")
MAX_DTB = 16 * 1024 * 1024


class DtbError(ValueError):
    pass


def _u32(blob: bytes, at: int) -> int:
    if at < 0 or at + 4 > len(blob):
        raise DtbError(f"truncated 32-bit word at {at:#x}")
    return struct.unpack_from(">I", blob, at)[0]


def _cstring(blob: bytes, at: int, limit: int) -> tuple[str, int]:
    end = blob.find(b"\0", at, limit)
    if at < 0 or end < 0:
        raise DtbError(f"unterminated string at {at:#x}")
    try:
        return blob[at:end].decode("ascii"), end + 1
    except UnicodeDecodeError as exc:
        raise DtbError(f"non-ASCII DTB name at {at:#x}") from exc


def parse(blob: bytes) -> dict[str, dict[str, bytes]]:
    if len(blob) < HEADER.size or len(blob) > MAX_DTB:
        raise DtbError("DTB size is outside supported bounds")
    (magic, total, structs, strings, reserve, version, last_compat,
     boot_cpu, strings_size, structs_size) = HEADER.unpack_from(blob)
    if magic != MAGIC or total != len(blob):
        raise DtbError("DTB magic or declared total size is invalid")
    if version < 17 or last_compat > version:
        raise DtbError("unsupported FDT version")
    for start, size, label in ((structs, structs_size, "structure"),
                               (strings, strings_size, "strings")):
        if start < HEADER.size or size > total - start:
            raise DtbError(f"{label} block is outside the DTB")
    if reserve < HEADER.size or reserve + 16 > structs:
        raise DtbError("reserve map is outside the DTB")
    cursor = reserve
    while cursor + 16 <= structs:
        address, size = struct.unpack_from(">2Q", blob, cursor)
        cursor += 16
        if address == 0 and size == 0:
            break
    else:
        raise DtbError("reserve map has no terminator")
    if structs + structs_size > strings and strings + strings_size > structs:
        raise DtbError("structure and strings blocks overlap")
    names = blob[strings:strings + strings_size]
    end_struct = structs + structs_size
    at = structs
    stack: list[str] = []
    nodes: dict[str, dict[str, bytes]] = {}
    saw_end = False
    while at < end_struct:
        token = _u32(blob, at)
        at += 4
        if token == BEGIN_NODE:
            name, at = _cstring(blob, at, end_struct)
            at = (at + 3) & ~3
            if not stack and name:
                raise DtbError("root node is not empty-named")
            stack.append(name)
            path = "/" + "/".join(stack[1:])
            if path in nodes:
                raise DtbError(f"duplicate node {path}")
            nodes[path] = {}
        elif token == END_NODE:
            if not stack:
                raise DtbError("unmatched END_NODE")
            stack.pop()
        elif token == PROP:
            if not stack or at + 8 > end_struct:
                raise DtbError("property outside a node or structure block")
            size, nameoff = struct.unpack_from(">2I", blob, at)
            at += 8
            if nameoff >= len(names) or size > end_struct - at:
                raise DtbError("property name or data outside its block")
            key, _ = _cstring(names, nameoff, len(names))
            path = "/" + "/".join(stack[1:])
            if key in nodes[path]:
                raise DtbError(f"duplicate property {path}:{key}")
            nodes[path][key] = blob[at:at + size]
            at = (at + size + 3) & ~3
        elif token == NOP:
            continue
        elif token == END:
            if stack or at != end_struct:
                raise DtbError("END token is not final or nodes remain open")
            saw_end = True
            break
        else:
            raise DtbError(f"unknown FDT token {token:#x}")
        if at > end_struct:
            raise DtbError("token padding exceeds structure block")
    if not saw_end or "/" not in nodes:
        raise DtbError("DTB has no final END or root node")
    return nodes


def strings(value: bytes) -> list[str]:
    if not value or value[-1] != 0:
        raise DtbError("string-list property is not NUL-terminated")
    try:
        return [item.decode("ascii") for item in value[:-1].split(b"\0")]
    except UnicodeDecodeError as exc:
        raise DtbError("non-ASCII string-list value") from exc


def inspect(blob: bytes) -> dict[str, object]:
    nodes = parse(blob)
    root = nodes["/"]
    compat = strings(root.get("compatible", b""))
    if "brcm,bcm2712" not in compat or not any(
        item.startswith("raspberrypi,5-") for item in compat
    ):
        raise DtbError("root does not identify a Raspberry Pi 5 / BCM2712")
    if root.get("#address-cells") != b"\0\0\0\2":
        raise DtbError("expected two root address cells")
    if root.get("#size-cells") != b"\0\0\0\2":
        raise DtbError("expected two root size cells")
    compatible_nodes = []
    for path, props in nodes.items():
        if "compatible" in props:
            compatible_nodes.append((path, strings(props["compatible"])))
    rp1 = [path for path in nodes if path.endswith("/rp1")]
    pcie = [path for path, ids in compatible_nodes if any(
        item == "brcm,bcm2712-pcie" for item in ids
    )]
    if len(rp1) != 1 or not pcie:
        raise DtbError("Pi 5 DTB lacks a unique RP1 bridge or BCM2712 PCIe")
    rp1_path = rp1[0]
    parent = rp1_path.rsplit("/", 1)[0]
    if parent not in pcie or nodes[parent].get("status", b"okay\0") != b"okay\0":
        raise DtbError("RP1 is not under an enabled BCM2712 PCIe host")
    if not nodes[parent].get("ranges") or not nodes[rp1_path].get("ranges"):
        raise DtbError("RP1 or PCIe address translation is missing")
    memory = [path for path, props in nodes.items()
              if props.get("device_type") == b"memory\0"]
    if not memory:
        raise DtbError("Pi 5 DTB has no memory node")
    return {"model": strings(root["model"])[0], "compatible": compat,
            "memory_nodes": memory, "rp1_bridge": rp1_path,
            "rp1_pcie_host": parent, "pcie_nodes": pcie,
            "node_count": len(nodes),
            "warning": "Source DTB only; firmware may modify the live DTB."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtb", nargs="+", type=Path, help="explicit DTB path(s)")
    args = parser.parse_args()
    result = {}
    for path in args.dtb:
        try:
            result[str(path)] = inspect(path.read_bytes())
        except (OSError, DtbError) as exc:
            parser.exit(1, f"{path}: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
