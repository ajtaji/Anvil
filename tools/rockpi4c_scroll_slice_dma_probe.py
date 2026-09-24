#!/usr/bin/env python3
"""Time verified 64 KiB and 8 KiB resident PL330 copies in scratch RAM."""

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
SOURCE = ROOT / "RockPi4C/Tests/scroll_slice_dma_probe.rockpi4c"
SYMBOLS = ROOT / "build/rockpi4c/anvil-flat.img.sym"
STAGE = 0x03CEF748
COPY = 0x000A6670


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    text = SYMBOLS.read_text()
    match = re.search(r"^rockdmacopy=(\d+)$", text, re.M)
    if match is None or 0x41000 + int(match.group(1)) != COPY:
        raise RuntimeError("resident PL330 copy target differs from build symbols")
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if stage != STAGE or capacity != STAGE_LIMIT:
            raise RuntimeError("scratch-memory proof was linked for another payload stage")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-scroll-dma-") as folder:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(folder) / "scroll-probe.bin", SOURCE)
            if recovery.stage_map() != (stage, capacity):
                raise RuntimeError("stage changed after linking")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("deadman-armed PL330 proof did not return")
            match = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
            if match is None:
                raise RuntimeError("missing PL330 proof result")
            value = int(match.group(1), 16)
            if value >> 32 == 0x444D4552:
                raise RuntimeError(f"PL330 proof failed check {value & 255}")
            if value >> 48 != 0x444D:
                raise RuntimeError(f"unexpected PL330 proof return 0x{value:016X}")
            large_ticks = (value >> 16) & 0xFFFF
            small_ticks = value & 0xFFFF
            print(f"verified PL330 copy: 64 KiB {large_ticks / 24:.2f} us; "
                  f"8 KiB {small_ticks / 24:.2f} us; "
                  f"UART 64-byte FIFO fills in 426.67 us")
            if small_ticks >= 10240:
                raise RuntimeError("8 KiB scroll slice alone exceeds the UART FIFO interval")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
