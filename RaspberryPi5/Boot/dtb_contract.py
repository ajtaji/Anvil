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


def _number(cells: bytes) -> int:
    if not cells or len(cells) % 4:
        raise DtbError("malformed device-tree cell value")
    return int.from_bytes(cells, "big")


def mapped_reg(nodes: dict[str, dict[str, bytes]], path: str) -> int:
    """Translate the first reg address through ancestor ranges to CPU space."""
    if path not in nodes or path == "/":
        raise DtbError("mapped node is missing")
    parent = path.rsplit("/", 1)[0] or "/"
    props = nodes[parent]
    address_cells = _number(props.get("#address-cells", b""))
    size_cells = _number(props.get("#size-cells", b""))
    if not 1 <= address_cells <= 2 or not 1 <= size_cells <= 2:
        raise DtbError("unsupported reg cell layout")
    reg = nodes[path].get("reg", b"")
    width = 4 * (address_cells + size_cells)
    if len(reg) < width or len(reg) % width:
        raise DtbError("missing or malformed reg")
    address = _number(reg[:address_cells * 4])
    span = _number(reg[address_cells * 4:width])
    if span == 0:
        raise DtbError("zero-length reg")
    while parent != "/":
        grandparent = parent.rsplit("/", 1)[0] or "/"
        bus = nodes[parent]
        child_cells = _number(bus.get("#address-cells", b""))
        cpu_cells = _number(nodes[grandparent].get("#address-cells", b""))
        size_cells = _number(bus.get("#size-cells", b""))
        if not 1 <= child_cells <= 2 or not 1 <= cpu_cells <= 2 or not 1 <= size_cells <= 2:
            raise DtbError("unsupported ranges cell layout")
        ranges = bus.get("ranges")
        entry_size = 4 * (child_cells + cpu_cells + size_cells)
        if ranges is None or not ranges or len(ranges) % entry_size:
            raise DtbError("missing or malformed bus ranges")
        for offset in range(0, len(ranges), entry_size):
            entry = ranges[offset:offset + entry_size]
            child = _number(entry[:4 * child_cells])
            cpu = _number(entry[4 * child_cells:4 * (child_cells + cpu_cells)])
            length = _number(entry[4 * (child_cells + cpu_cells):])
            if address >= child and span <= length and address - child <= length - span:
                address = cpu + address - child
                break
        else:
            raise DtbError(f"reg is not covered by {parent} ranges")
        parent = grandparent
    return address


def early_uart(nodes: dict[str, dict[str, bytes]]) -> dict[str, object]:
    """Resolve the source tree's selected early console, including aliases."""
    chosen = nodes.get("/chosen", {})
    aliases = nodes.get("/aliases", {})
    stdout = strings(chosen.get("stdout-path", b""))[0]
    target, separator, options = stdout.partition(":")
    if not target or (separator and not options):
        raise DtbError("chosen stdout-path is empty or has empty options")
    if not target.startswith("/"):
        target = strings(aliases.get(target, b""))[0]
    if not target.startswith("/") or target not in nodes:
        raise DtbError("chosen stdout-path does not resolve to a node")
    uart = nodes[target]
    if uart.get("status", b"okay\0") != b"okay\0":
        raise DtbError("chosen early UART is not enabled")
    compatible = strings(uart.get("compatible", b""))
    if "arm,pl011" not in compatible or not uart.get("reg"):
        raise DtbError("chosen early UART is not a mapped PL011")
    return {"stdout_path": stdout, "early_uart": target,
            "early_uart_physical": mapped_reg(nodes, target),
            "early_uart_compatible": compatible}


def wlan_sdio(nodes: dict[str, dict[str, bytes]]) -> dict[str, object]:
    radios = [path for path, props in nodes.items()
              if "compatible" in props
              if "brcm,bcm4329-fmac" in strings(props["compatible"])]
    if len(radios) != 1:
        raise DtbError("expected one Pi 5 WLAN SDIO function")
    radio = radios[0]
    host = radio.rsplit("/", 1)[0]
    props = nodes[host]
    if "brcm,bcm2712-sdhci" not in strings(props.get("compatible", b"")):
        raise DtbError("WLAN parent is not the BCM2712 SDHCI host")
    if props.get("status") != b"okay\0" or props.get("bus-width") != b"\0\0\0\4":
        raise DtbError("WLAN SDIO host is disabled or not 4-bit")
    if "non-removable" not in props or "vmmc-supply" not in props or "pinctrl-0" not in props:
        raise DtbError("WLAN SDIO power or pin contract is absent")
    if nodes[radio].get("reg") != b"\0\0\0\1":
        raise DtbError("WLAN function number is not one")
    return {"wifi_function": radio, "wifi_sdio_host": host,
            "wifi_sdio_physical": mapped_reg(nodes, host)}


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
            **early_uart(nodes),
            **wlan_sdio(nodes),
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
