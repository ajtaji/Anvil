#!/usr/bin/env python3
"""Read build 144 Rock Pi recovery/screen state in a returning payload."""

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
SOURCE = ROOT / "RockPi4C/Tests/idle_state_probe.rockpi4c"


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
        with tempfile.TemporaryDirectory(prefix="rockpi4c-idle-state-") as directory:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(directory) / "state.bin", SOURCE)
            if recovery.stage_map() != (stage, STAGE_LIMIT):
                raise RuntimeError("payload stage changed")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("state payload did not return")
            result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
            if result is None:
                raise RuntimeError("missing state return")
            value = int(result.group(1), 16)
            if value >> 48 != 0x4944:
                raise RuntimeError(f"unexpected state value: 0x{value:016X}")
            flags = (value >> 32) & 0xFF
            names = ("screen_ready", "screen_attached", "idle_ready", "scroll_active",
                     "cpu_dirty", "row_dirty", "screen_fault", "recovery_ready")
            print(f"ring occupancy={(value >> 16) & 8191}; banner phase={value & 255}; "
                  + " ".join(f"{name}={bool(flags & (1 << i))}"
                             for i, name in enumerate(names)))
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
