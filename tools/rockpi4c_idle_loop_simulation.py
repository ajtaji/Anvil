#!/usr/bin/env python3
"""Run one-second build 144 recovery idle-loop rehearsal under the deadman."""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
import re
import tempfile

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/idle_loop_simulation.rockpi4c"
FLAT = ROOT / "build/rockpi4c/anvil-flat.img"
SYMBOLS = ROOT / "build/rockpi4c/anvil-flat.img.sym"
BOARD = ROOT / "RockPi4C/Board/board.rockpi4c"
TARGETS = {"rockrecoverypoll": 0xDC338,
           "rockscreenservice": 0xD798C,
           "rockwatchdogpet": 0xA1F38,
           "rockuartbyte": 0x41B18}


def validate_targets() -> None:
    if "#ANVIL_BUILD = 144 ; pmf:build" not in BOARD.read_text():
        raise RuntimeError("this rehearsal requires installed build 144")
    table = dict((name, int(offset)) for name, offset in
                 re.findall(r"^([a-z][a-z0-9_]*)=(\d+)$", SYMBOLS.read_text(), re.M))
    size = FLAT.stat().st_size
    for name, target in TARGETS.items():
        offset = table.get(name)
        if offset is None or not 0 <= offset < size or 0x41000 + offset != target:
            raise RuntimeError(f"{name} disagrees with build symbols")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    validate_targets()
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected payload stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-idle-rehearsal-") as directory:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(directory) / "rehearsal.bin", SOURCE)
            if recovery.stage_map() != (stage, STAGE_LIMIT):
                raise RuntimeError("payload stage changed")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("idle rehearsal did not return")
            result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
            if result is None:
                raise RuntimeError("missing rehearsal return")
            value = int(result.group(1), 16)
            if value >> 32 == 0x49444552:
                raise RuntimeError(f"idle rehearsal refused: 0x{value:016X}")
            if value >> 48 != 0x4944:
                raise RuntimeError(f"unexpected idle return: 0x{value:016X}")
            usage = (value >> 32) & 0xFFFF
            gap_ticks = (value >> 16) & 0xFFFF
            iterations = value & 0xFFFF
            print(f"one-second idle rehearsal: CPU0={usage / 100:.2f}%; "
                  f"max RX poll gap={gap_ticks / 24:.2f} us "
                  f"({gap_ticks * 150000 / 24000000:.1f} bytes at 1.5 Mb/s, 8N1); "
                  f"iterations={iterations}")
            if gap_ticks >= 10240:
                raise RuntimeError("RX poll gap can fill the verified 64-byte UART FIFO")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
