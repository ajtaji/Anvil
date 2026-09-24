#!/usr/bin/env python3
"""Check build-147 display readiness and VOPB fault state without modifying it."""

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
SOURCE = ROOT / "RockPi4C/Tests/build147_display_status_probe.rockpi4c"
BOARD = ROOT / "RockPi4C/Board/board.rockpi4c"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    options = parser.parse_args()
    if "#ANVIL_BUILD = 147" not in BOARD.read_text(encoding="utf-8"):
        raise RuntimeError("probe requires installed build 147")
    recovery = Recovery(options.port, 1500000)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-display-status-") as folder:
            image = compile_for_stage(resolve_compiler(str(TRACKED_COMPILER)), stage,
                                      Path(folder) / "status.bin", SOURCE)
            checksum = zlib.crc32(image) & 0xFFFFFFFF
            recovery.send_command(f"payload {len(image):X} {checksum:08X}")
            recovery.transfer_in(image, len(image), checksum)
            line = recovery.wait_line(lambda item: item.startswith(b"PAYLOAD RETURN X0="), 10.0)
            match = re.match(rb"PAYLOAD RETURN X0=([0-9A-F]{16})", line)
            if match is None:
                raise RuntimeError(f"malformed status result: {line!r}")
            value = int(match.group(1), 16)
            if value >> 48 != 0x4844:
                raise RuntimeError(f"display status failed: 0x{value:016X}")
            print(f"display ready; TrueType ready; VOPB WIN0 enabled, RGB101010; "
                  f"no display/VOP MMU fault; {value >> 16 & 0xFFFF}x{value & 0xFFFF}")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
