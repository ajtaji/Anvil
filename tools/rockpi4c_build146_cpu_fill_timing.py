#!/usr/bin/env python3
"""Time the resident build-146 status fill on a private strip."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile
import zlib

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/build146_cpu_fill_timing.rockpi4c"
BOARD = ROOT / "RockPi4C/Board/board.rockpi4c"
SYMBOLS = ROOT / "build/rockpi4c/anvil-flat.img.sym"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    options = parser.parse_args()
    if "#ANVIL_BUILD = 146" not in BOARD.read_text(encoding="utf-8"):
        raise RuntimeError("payload requires installed build 146")
    if "rockscreencpufill32=603900" not in SYMBOLS.read_text(encoding="utf-8"):
        raise RuntimeError("resident status fill address changed")
    recovery = Recovery(options.port, 1500000)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-fill-timing-") as folder:
            image = compile_for_stage(resolve_compiler(str(TRACKED_COMPILER)), stage,
                                      Path(folder) / "fill-timing.bin", SOURCE)
            checksum = zlib.crc32(image) & 0xFFFFFFFF
            recovery.send_command(f"payload {len(image):X} {checksum:08X}")
            recovery.transfer_in(image, len(image), checksum)
            line = recovery.wait_line(lambda item: item.startswith(b"PAYLOAD RETURN X0="), 10.0)
            match = re.match(rb"PAYLOAD RETURN X0=([0-9A-F]{16})", line)
            if match is None:
                raise RuntimeError(f"malformed return: {line!r}")
            value = int(match.group(1), 16)
            if value >> 48 != 0x4649:
                raise RuntimeError(f"unexpected timing return: 0x{value:016X}")
            maximum = (value >> 32) & 0xFFFF
            total = value & 0xFFFFFFFF
            print(f"20 resident status-clear rows: max single row {maximum / 24:.2f} us; "
                  f"total {total / 24:.2f} us; UART FIFO budget 426.67 us")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
