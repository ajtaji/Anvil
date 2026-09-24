#!/usr/bin/env python3
"""Run the read-only RK3399 EL3 secure-timer/GIC admission payload."""

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
SOURCE = ROOT / "RockPi4C/Tests/el3_timer_wfi_preflight.rockpi4c"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    compiler = resolve_compiler(options.compiler)
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected payload stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-wfi-preflight-") as directory:
            image = compile_for_stage(compiler, stage, Path(directory) / "wfi-preflight.bin", SOURCE)
            if recovery.stage_map() != (stage, STAGE_LIMIT):
                raise RuntimeError("payload stage changed after linking")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("preflight payload did not return")
            result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
            if result is None:
                raise RuntimeError("missing return value")
            value = int(result.group(1), 16)
            if value >> 32 != 0x57464930:
                raise RuntimeError(f"unexpected return: 0x{value:016X}")
            print(f"current redistributor frame {(value >> 16) & 0xFF}; "
                  f"admission refusal bits 0x{value & 0xFFFF:04X}")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
