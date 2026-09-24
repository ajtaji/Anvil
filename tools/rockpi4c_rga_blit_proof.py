#!/usr/bin/env python3
"""Prove an RK3399 RGA2 40x40 copy inside private DDR, behind the deadman."""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
import re
import tempfile

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import ROOT, compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


SOURCE = ROOT / "RockPi4C/Tests/rga_private_blit_payload.rockpi4c"
EXPECTED_RETURN = 0x52474100
EXPECTED_VERSION = 0x03218218


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    status = re.search(r"^RG1 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) "
                       r"([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})\s*$",
                       transcript, re.M)
    if status is None:
        raise RuntimeError("RGA private blit did not report version/IRQ/mismatches")
    version, interrupt, mismatches, first, expected, observed = (
        int(value, 16) for value in status.groups()
    )
    if version != EXPECTED_VERSION or interrupt & 4 == 0 or interrupt & 3 or mismatches:
        raise RuntimeError("RGA version, completion IRQ, or pixel comparison failed: "
                           f"first={first:08X} expected={expected:08X} "
                           f"observed={observed:08X}")
    if result is None or int(result.group(1), 16) != EXPECTED_RETURN:
        raise RuntimeError("RGA private blit did not return guarded success")
    print("RGA2 private blit PASS: completion IRQ, copied pixels, and guards verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Rock Pi recovery UART, for example COM7")
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    compiler = resolve_compiler(options.compiler)
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("board advertised an unexpected stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-rga-") as directory:
            image = compile_for_stage(compiler, stage, Path(directory) / "rga-blit.bin", SOURCE)
            current, capacity = recovery.stage_map()
            if current != stage or capacity != STAGE_LIMIT:
                raise RuntimeError("board stage changed after linking; no payload sent")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("recovery rejected or failed the payload")
            check_result(transcript)
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
