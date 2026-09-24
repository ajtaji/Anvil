#!/usr/bin/env python3
"""Read RK3399 UART2 FIFO configuration through a returning payload."""

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
SOURCE = ROOT / "RockPi4C/Tests/uart_fifo_probe.rockpi4c"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected payload stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-uart-fifo-") as directory:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(directory) / "uart-fifo.bin", SOURCE)
            if recovery.stage_map() != (stage, STAGE_LIMIT):
                raise RuntimeError("payload stage changed")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("UART FIFO payload did not return")
            result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
            if result is None:
                raise RuntimeError("missing UART FIFO result")
            value = int(result.group(1), 16)
            if value >> 48 != 0x5541:
                raise RuntimeError(f"unexpected UART FIFO return: 0x{value:016X}")
            cpr = (value >> 16) & 0xFFFFFFFF
            rfl = (value >> 8) & 255
            lsr = value & 255
            print(f"UART2 CPR=0x{cpr:08X}; FIFO depth={((cpr >> 16) & 255) * 16} "
                  f"bytes if CPR implemented; RX level={rfl}; LSR=0x{lsr:02X}")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
