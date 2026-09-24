#!/usr/bin/env python3
"""Measure build 144 resident screen-service cost in a bounded payload."""

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
SOURCE = ROOT / "RockPi4C/Tests/idle_screen_timing_probe.rockpi4c"
FLAT = ROOT / "build/rockpi4c/anvil-flat.img"
SYMBOLS = ROOT / "build/rockpi4c/anvil-flat.img.sym"
BOARD = ROOT / "RockPi4C/Board/board.rockpi4c"
LOAD = 0x41000
TARGET = 0xD798C


def validate_target() -> None:
    if "#ANVIL_BUILD = 144 ; pmf:build" not in BOARD.read_text():
        raise RuntimeError("this resident call probe requires build 144")
    match = re.search(r"^rockscreenservice=(\d+)$", SYMBOLS.read_text(), re.M)
    if match is None or LOAD + int(match.group(1)) != TARGET:
        raise RuntimeError("resident screen-service address disagrees with build symbols")
    if not 0 <= int(match.group(1)) < FLAT.stat().st_size:
        raise RuntimeError("resident screen-service entry lies outside flat image")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    validate_target()
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected payload stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-screen-timing-") as directory:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(directory) / "screen-timing.bin", SOURCE)
            if recovery.stage_map() != (stage, STAGE_LIMIT):
                raise RuntimeError("payload stage changed")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("timing payload did not return")
            result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
            if result is None:
                raise RuntimeError("missing timing return")
            value = int(result.group(1), 16)
            if value >> 32 == 0x53434552:
                raise RuntimeError(f"screen service timing refused: 0x{value:016X}")
            if value >> 48 != 0x5343:
                raise RuntimeError(f"unexpected timing value: 0x{value:016X}")
            drained = (value >> 32) & 0x7FFF
            average = (value >> 16) & 0xFFFF
            last = value & 0xFFFF
            print(f"drained {drained} ring bytes before timing; ring empty={bool(value & (1 << 47))}; "
                  f"average={average / 24:.2f} us; last={last / 24:.2f} us")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
