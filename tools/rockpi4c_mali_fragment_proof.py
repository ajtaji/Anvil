#!/usr/bin/env python3
"""Run one deadman-guarded Mali-T860 clear into private memory only."""

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


SOURCE = ROOT / "RockPi4C/Tests/mali_fragment_clear_payload.rockpi4c"
EXPECTED_RETURN = 0x47514000
EXPECTED_PIXEL = 0x7F00FF00


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    if result is None:
        raise RuntimeError("fragment payload did not return to the monitor")
    returned = int(result.group(1), 16)
    match = re.search(r"^F0 ((?:[0-9A-F]{8} ){8}[0-9A-F]{8})$", transcript, re.M)
    if match is None:
        raise RuntimeError(f"fragment telemetry absent; payload returned 0x{returned:X}")
    raw, first, last, bad, before, after, job_status, slot_status, mmu_fault = (
        int(value, 16) for value in match.group(1).split()
    )
    if returned != EXPECTED_RETURN or raw & 1 == 0 or raw & 0x10000 or \
            first != EXPECTED_PIXEL or last != EXPECTED_PIXEL or bad or \
            before != 0x11223344 or after != 0x55667788 or \
            job_status != 1 or mmu_fault:
        raise RuntimeError(
            f"private Mali fragment clear failed: return={returned:08X} "
            f"raw={raw:08X} first={first:08X} last={last:08X} "
            f"bad={bad} guards={before:08X}/{after:08X} "
            f"job={job_status:08X} slot={slot_status:08X} fault={mmu_fault:08X}"
        )
    print("Mali FRAGMENT PASS: 256 private RGBA8 pixels cleared; guards and MMU intact")


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
        with tempfile.TemporaryDirectory(prefix="rockpi4c-mali-fragment-") as directory:
            image = compile_for_stage(compiler, stage, Path(directory) / "mali-fragment.bin", SOURCE)
            current, capacity = recovery.stage_map()
            if current != stage or capacity != STAGE_LIMIT:
                raise RuntimeError("board stage changed after linking; no payload sent")
            output = io.StringIO()
            failure = None
            with contextlib.redirect_stdout(output):
                try:
                    returned = recovery.payload(image)
                except (RuntimeError, TimeoutError) as exc:
                    returned = False
                    failure = exc
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if failure is not None:
                raise failure
            if not returned:
                raise RuntimeError("recovery rejected or failed the fragment payload")
            check_result(transcript)
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
