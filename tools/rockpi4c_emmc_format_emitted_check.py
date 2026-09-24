#!/usr/bin/env python3
"""Compare emitted A64 FAT32 metadata builders with the offline layout."""

from __future__ import annotations

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "a64"))
from a64_interp import A64  # noqa: E402
from rockpi4c_emmc_fat32_layout import make_metadata  # noqa: E402

BIN = ROOT / "build/rockpi4c/emmc-fat32-format.bin"
LOAD = struct.unpack_from("<Q", BIN.with_suffix(BIN.suffix + ".pmf").read_bytes(), 16)[0]
STACK = 0x040BC000
RETURN = 0x07FFF000


def symbols() -> dict[str, int]:
    result = {}
    for line in BIN.with_suffix(BIN.suffix + ".sym").read_text().splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            result[name] = int(value)
    return result


def execute(name: str, buffer: int, *args: int) -> bytes:
    blob = BIN.read_bytes()
    sym = symbols()
    cpu = A64(pc=LOAD + sym[name])
    cpu.sp = STACK
    for index, value in enumerate(args):
        cpu.x[index] = value
    cpu.x[30] = RETURN
    for index, value in enumerate(blob):
        cpu.memory[LOAD + index] = value
    for _ in range(2_000_000):
        if cpu.pc == RETURN:
            return bytes(cpu.memory.get(buffer + index, 0) for index in range(512))
        cpu.step()
    raise RuntimeError(f"{name} did not return")


def main() -> None:
    mbr, prefix = make_metadata()
    sym = symbols()
    actual = sym["global_ef_actual"]
    expected_buffer = sym["global_ef_expected"]
    if actual == expected_buffer or abs(actual - expected_buffer) < 512:
        raise SystemExit("formatter arrays overlap")
    for buffer in (actual, expected_buffer, 0x11000001):
        if execute("efmbr", buffer, buffer) != mbr:
            raise SystemExit(f"emitted MBR differs at buffer {buffer:#x}")
        for offset in (0, 1, 2, 6, 7, 31, 32, 33, 1053, 1054, 1055, 2076, 2083):
            sector = prefix[offset * 512:(offset + 1) * 512]
            if execute("efsector", buffer, offset, buffer) != sector:
                raise SystemExit(f"emitted sector {offset} differs at buffer {buffer:#x}")
    print(f"rockpi4c_emmc_format_emitted_check: PASS - MBR and 13 sectors at emitted array addresses {actual:#x}, {expected_buffer:#x}, and unaligned address; strict A64 alignment")


if __name__ == "__main__":
    main()
