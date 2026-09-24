#!/usr/bin/env python3
"""Prove an RGA2 1920x40 scanout copy with full-row restore."""

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


SOURCE = ROOT / "RockPi4C/Tests/rga_fullrow_scanout_payload.rockpi4c"
ROW_BYTES = 1920 * 40 * 4
SAVE_BYTES = 1920 * 42 * 4
SCRATCH_OFFSET = 0x10000
DEST_OFFSET = 0x50000


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    status = re.search(r"^RF2 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) "
                       r"([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})\s*$", transcript, re.M)
    if result is None or status is None:
        raise RuntimeError("full-row payload did not return with complete telemetry")
    interrupt, bad, restore_bad, first, framebuffer, destination = (int(v, 16) for v in status.groups())
    returned = int(result.group(1), 16)
    if (returned != 0x52464700 or interrupt & 4 == 0 or interrupt & 3 or
            bad or restore_bad or first != 0xFFFFFFFF or
            not 0x02000000 <= framebuffer < destination < 0x10000000):
        raise RuntimeError(
            f"scanout RGA failed: X0={returned:08X} IRQ={interrupt:08X} bad={bad} "
            f"restore={restore_bad} first={first:08X} fb={framebuffer:08X} dst={destination:08X}"
        )
    print("RGA2 scanout row PASS: 76,800 pixels, adjacent rows intact, all 80,640 saved pixels restored")


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
        backup = scratch + DEST_OFFSET + 4
        end = backup + SAVE_BYTES + 4
        if not (stage + SCRATCH_OFFSET <= scratch and source + ROW_BYTES + 4 < backup - 4 and
                end < min(stage + capacity, stack_guard)):
            raise RuntimeError("payload scratch would overlap image, destination, or stack")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-rga-fullrow-") as directory:
            directory = Path(directory)
            text = SOURCE.read_text(encoding="utf-8")
            if text.count("@@SOURCE@@") != 1 or text.count("@@BACKUP@@") != 1:
                raise RuntimeError("full-row source placeholders changed")
            text = text.replace("@@SOURCE@@", f"${source:08X}").replace("@@BACKUP@@", f"${backup:08X}")
            generated = directory / "rga-fullrow.rockpi4c"
            generated.write_text(text, encoding="utf-8")
            image = compile_for_stage(compiler, stage, directory / "rga-fullrow.bin", generated)
            if len(image) >= SCRATCH_OFFSET:
                raise RuntimeError("compiled payload overlaps its scratch reservation")
            current, capacity = recovery.stage_map()
            if current != stage or capacity != STAGE_LIMIT:
                raise RuntimeError("board stage changed after linking; no payload sent")
            print(f"scratch source=0x{source:08X} backup=0x{backup:08X} "
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
