"""Package the native auxiliary UART driver using Anvil's published PMFMOD layout."""
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def build_module(assembler):
    text = (ROOT / "Anvil/Hal/module_format.pbi").read_text()
    constants = re.findall(
        r"(?m)^#(PMFMOD_\w+|MREL_\w+)\s*=\s*(\$[\dA-Fa-f]+|\d+)\b", text
    )
    layout = {name: int(value.replace("$", "0x"), 0) for name, value in constants}
    with tempfile.TemporaryDirectory(prefix="zentaji-uart-") as temporary:
        binary = Path(temporary) / "uart.bin"
        subprocess.run([assembler, ROOT / "Zentaji/Modules/aux_serial.zen", binary],
                       check=True, capture_output=True, text=True)
        image = binary.read_bytes()

    entry_table = struct.Struct("<5Q")
    init, probe, quiesce, dispatch, placeholder = entry_table.unpack_from(image)
    offsets = (init, probe, quiesce, dispatch)
    if placeholder or any(offset % 8 or offset < entry_table.size or offset + 8 > len(image)
                          for offset in offsets):
        raise ValueError("UART driver entry table does not match the native image")

    header = layout["PMFMOD_HEADER_BYTES"]
    reloc = header + len(image)
    match = reloc + layout["PMFMOD_RELOC_BYTES"]
    container = bytearray(match + layout["PMFMOD_MATCH_BYTES"])
    container[:8] = b"PMFMOD\0\0"

    def field(name, value, width=4):
        offset = layout["PMFMOD_OFF_" + name]
        container[offset:offset + width] = value.to_bytes(width, "little")

    for name, value in (
        ("VERSION", layout["PMFMOD_VERSION"]), ("HEADER_BYTES", header),
        ("ABI_MAJOR", 1), ("ABI_MINOR", 1), ("SEAM_COUNT", 1),
        ("RELOC_COUNT", 1), ("RELOC_OFFSET", reloc), ("ALIGN", layout["PMFMOD_LOAD_ALIGN"]),
        ("ARCH", 2), ("MATCH_COUNT", 1), ("MATCH_OFFSET", match),
    ):
        field(name, value)
    bss_align = layout["PMFMOD_BSS_ALIGN"]
    for name, value in (
        ("IMAGE_BYTES", len(image)), ("BSS_OFFSET", (len(image) + bss_align - 1) & -bss_align),
        ("INIT_OFFSET", init), ("PROBE_OFFSET", probe), ("QUIESCE", quiesce),
    ):
        field(name, value, 8)
    for index in range(layout["PMFMOD_SEAM_MAX"]):
        seam = 11 if index == 0 else layout["PMFMOD_SEAM_UNUSED"]
        struct.pack_into("<I", container, layout["PMFMOD_OFF_SEAMS"] + index * 4, seam)

    container[header:reloc] = image
    struct.pack_into("<IHHq", container, reloc, entry_table.size - 8, layout["MREL_ABS64"], 0, dispatch)
    compatible = b"zentaji,serial-v1"
    container[match:match + len(compatible)] = compatible
    digest = layout["PMFMOD_OFF_SHA256"]
    end = digest + layout["PMFMOD_DIGEST_BYTES"]
    container[digest:end] = hashlib.sha256(container[:digest] + container[end:]).digest()
    return bytes(container)
