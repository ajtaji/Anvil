#!/usr/bin/env python3
"""Run a bounded RGA2 scanout copy with private gate and framebuffer restore."""

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


SOURCE = ROOT / "RockPi4C/Tests/rga_scanout_probe_payload.rockpi4c"


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    private = re.search(r"^RS0 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})\s*$", transcript, re.M)
    visible = re.search(r"^RS1 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})\s*$", transcript, re.M)
    if result is None or private is None or visible is None:
        raise RuntimeError("scanout payload did not report all guarded results")
    version, private_irq, private_bad, framebuffer = (int(v, 16) for v in private.groups())
    visible_irq, visible_bad, restore_bad, destination = (int(v, 16) for v in visible.groups())
    returned = int(result.group(1), 16)
    if (version != 0x03218218 or private_irq & 4 == 0 or private_irq & 3 or
            private_bad or visible_irq & 4 == 0 or visible_irq & 3 or
            visible_bad or restore_bad or not framebuffer <= destination < 0x10000000 or
            returned != 0x52534000):
        raise RuntimeError(
            f"RGA scanout proof failed: X0={returned:08X} version={version:08X} "
            f"private={private_irq:08X}/{private_bad} visible={visible_irq:08X}/{visible_bad} "
            f"restore={restore_bad} fb={framebuffer:08X} dst={destination:08X}"
        )
    print("RGA2 scanout PASS: 40x40 pixels copied, verified, and restored; border intact")


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
        with tempfile.TemporaryDirectory(prefix="rockpi4c-rga-scanout-") as directory:
            image = compile_for_stage(compiler, stage, Path(directory) / "rga-scanout.bin", SOURCE)
            current, capacity = recovery.stage_map()
            if current != stage or capacity != STAGE_LIMIT:
                raise RuntimeError("board stage changed after linking; no payload sent")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                returned = recovery.payload(image)
            transcript = output.getvalue()
            print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
            if not returned:
                raise RuntimeError("recovery rejected or failed the RGA payload")
            check_result(transcript)
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
