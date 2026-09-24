#!/usr/bin/env python3
"""Run the EL3 timer-event WFE proof at Anvil's current payload stage.

The payload saves and restores CNTKCTL_EL1, leaves DAIF masked, and does not
alter GIC or exception vectors. Anvil's payload command arms the physical
deadman before entering it. A missing timer event can still reset the board.
"""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
import re
import sys
import tempfile

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/el3_timer_wfe_payload.rockpi4c"
SUCCESS_PREFIX = 0x5746000000000000
FAILURE_PREFIX = 0x5746454500000000


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    if result is None:
        raise RuntimeError("WFE payload did not return before the deadman deadline")
    value = int(result.group(1), 16)
    if value & 0xFFFFFFFF00000000 == FAILURE_PREFIX:
        raise RuntimeError(f"WFE preflight/restore/timing check failed: 0x{value:016X}")
    if value & 0xFFFF000000000000 != SUCCESS_PREFIX:
        raise RuntimeError(f"unexpected WFE proof result: 0x{value:016X}")
    max_pair = (value >> 32) & 0xFFFF
    qualified = (value >> 24) & 0xFF
    ticks = value & 0xFFFFFF
    if qualified < 7:
        raise RuntimeError(f"only {qualified} of eight WFE pairs took at least 1000 ticks")
    if not 40000 <= ticks <= 2400000:
        raise RuntimeError(f"WFE returned outside the 1.67-100 ms acceptance window: {ticks} ticks")
    if max_pair > 9000:
        raise RuntimeError(f"WFE pair took {max_pair} ticks (>375 us RX budget)")
    print(f"EL3 timer-event WFE returned in {ticks / 24000:.3f} ms; "
          f"{qualified}/8 double-WFE pairs waited; max {max_pair / 24:.2f} us "
          f"({max_pair * 150000 / 24000000:.1f} bytes at 1.5 Mb/s, 8N1); "
          "state restored")


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Rock Pi recovery UART, for example COM7")
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    parser.add_argument("--run", action="store_true", help="send the deadman-armed payload")
    options = parser.parse_args()
    if not options.run:
        raise SystemExit("no payload sent: pass --run for the bounded silicon proof")

    compiler = resolve_compiler(options.compiler)
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("board advertised an unexpected payload stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-el3-wfe-") as directory:
            image = compile_for_stage(
                compiler, stage, Path(directory) / "el3-timer-wfe.bin", SOURCE
            )
            current, capacity = recovery.stage_map()
            if (current, capacity) != (stage, STAGE_LIMIT):
                raise RuntimeError("payload stage changed after linking; no payload sent")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("recovery rejected or failed the WFE payload")
            check_result(transcript)
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
