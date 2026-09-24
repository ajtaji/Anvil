#!/usr/bin/env python3
"""Prove an RGA2 1920x40 copy in bounded payload-stage scratch."""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
import re
import tempfile

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import ROOT, STACK_GUARD, compile_for_stage, payload_stack_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


SOURCE = ROOT / "RockPi4C/Tests/rga_fullrow_private_payload.rockpi4c"
ROW_BYTES = 1920 * 40 * 4
SCRATCH_OFFSET = 0x10000
DEST_OFFSET = 0x50000


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    status = re.search(r"^RF1 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) "
                       r"([0-9A-F]{8}) ([0-9A-F]{8})\s*$", transcript, re.M)
    if result is None or status is None:
        raise RuntimeError("full-row payload did not return with complete telemetry")
    interrupt, bad, first, first_pixel, last_pixel = (int(v, 16) for v in status.groups())
    returned = int(result.group(1), 16)
    last_index = 39 * 1920 + 1919
    expected_last = 0xFF000000 | ((1919 & 255) << 16) | (39 << 8) | ((1919 ^ 39) & 255)
    if (returned != 0x52464600 or interrupt & 4 == 0 or interrupt & 3 or
            bad or first != 0xFFFFFFFF or first_pixel != 0xFF000000 or
            last_pixel != expected_last):
        raise RuntimeError(
            f"full-row RGA failed: X0={returned:08X} IRQ={interrupt:08X} bad={bad} "
            f"first={first:08X} endpoints={first_pixel:08X}/{last_pixel:08X}"
        )
    print(f"RGA2 full row PASS: {last_index + 1} private pixels, exact guards and source")


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
            raise RuntimeError("board advertised an unexpected stage capacity")
        stack_guard = payload_stack_for_stage(stage) - STACK_GUARD
        scratch = (stage + SCRATCH_OFFSET + 4095) & ~4095
        source = scratch + 4
        destination = scratch + DEST_OFFSET + 4
        end = destination + ROW_BYTES + 4
        if not (stage + SCRATCH_OFFSET <= scratch and source + ROW_BYTES + 4 < destination - 4 and
                end < min(stage + capacity, stack_guard)):
            raise RuntimeError("payload scratch would overlap image, destination, or stack")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-rga-fullrow-") as directory:
            directory = Path(directory)
            text = SOURCE.read_text(encoding="utf-8")
            if text.count("@@SOURCE@@") != 1 or text.count("@@DESTINATION@@") != 1:
                raise RuntimeError("full-row source placeholders changed")
            text = text.replace("@@SOURCE@@", f"${source:08X}").replace("@@DESTINATION@@", f"${destination:08X}")
            generated = directory / "rga-fullrow.rockpi4c"
            generated.write_text(text, encoding="utf-8")
            image = compile_for_stage(compiler, stage, directory / "rga-fullrow.bin", generated)
            if len(image) >= SCRATCH_OFFSET:
                raise RuntimeError("compiled payload overlaps its scratch reservation")
            current, capacity = recovery.stage_map()
            if current != stage or capacity != STAGE_LIMIT:
                raise RuntimeError("board stage changed after linking; no payload sent")
            print(f"scratch source=0x{source:08X} destination=0x{destination:08X} "
                  f"end=0x{end:08X} stack_guard=0x{stack_guard:08X}")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("recovery rejected or failed full-row payload")
            check_result(transcript)
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
