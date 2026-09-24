#!/usr/bin/env python3
"""Run a bounded Mali-to-RGA scanout tile with complete region restore."""

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


SOURCE = ROOT / "RockPi4C/Tests/mali_rga_visible_payload.rockpi4c"
EXPECTED_RETURN = 0x47516000
SCRATCH_OFFSET = 0x10000
SAVE_BYTES = 50 * 50 * 4


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    fragment = re.search(r"^F0 ((?:[0-9A-F]{8} ){8}[0-9A-F]{8})$", transcript, re.M)
    rga = re.search(r"^R1 ((?:[0-9A-F]{8} ){5}[0-9A-F]{8})$", transcript, re.M)
    scanout = re.search(r"^S1 ((?:[0-9A-F]{8} ){5}[0-9A-F]{8})$", transcript, re.M)
    if result is None or fragment is None or rga is None or scanout is None:
        raise RuntimeError("Mali/RGA/scanout completion telemetry is incomplete")
    returned = int(result.group(1), 16)
    raw, first, last, bad, before, after, job, slot, fault = (
        int(value, 16) for value in fragment.group(1).split()
    )
    version, irq, mismatches, first_bad, dst_before, dst_after = (
        int(value, 16) for value in rga.group(1).split()
    )
    screen_irq, screen_bad, restore_bad, framebuffer, screen_target, backup_guard = (
        int(value, 16) for value in scanout.group(1).split()
    )
    if returned != EXPECTED_RETURN or raw & 1 == 0 or raw & 0x10000 or \
            first != 0x7F00FF00 or last != 0x7F00FF00 or bad or \
            before != 0x11223344 or after != 0x55667788 or job != 1 or fault or \
            version != 0x03218218 or irq & 4 == 0 or irq & 3 or mismatches or \
            first_bad != 0xFFFFFFFF or dst_before != 0xAABBCCDD or \
            dst_after != 0x55667788 or screen_irq & 4 == 0 or screen_irq & 3 or \
            screen_bad or restore_bad or backup_guard != 0x55667788 or \
            not 0x02000000 <= framebuffer < screen_target < 0x10000000:
        raise RuntimeError(
            f"Mali/RGA private copy failed: return={returned:016X} "
            f"GPU={raw:08X}/{bad}/{job:08X}/{slot:08X}/{fault:08X} "
            f"RGA={version:08X}/{irq:08X}/{mismatches}/{first_bad:08X} "
            f"guards={dst_before:08X}/{dst_after:08X} "
            f"scanout={screen_irq:08X}/{screen_bad}/{restore_bad} "
            f"fb={framebuffer:08X} target={screen_target:08X}"
        )
    print("Mali-to-RGA scanout PASS: 2,304 GPU pixels displayed, 50x50 border saved and restored")


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
        with tempfile.TemporaryDirectory(prefix="rockpi4c-mali-rga-") as directory:
            directory = Path(directory)
            backup = (stage + SCRATCH_OFFSET + 4095) & ~4095
            if backup + SAVE_BYTES + 4 >= min(stage + capacity, stack_guard):
                raise RuntimeError("scanout backup would overlap stage end or stack")
            text = SOURCE.read_text(encoding="utf-8")
            if text.count("@@BACKUP@@") != 1 or text.count("@@STACK_GUARD@@") != 1:
                raise RuntimeError("scanout backup placeholder changed")
            generated = directory / "mali-rga-visible.rockpi4c"
            generated.write_text(text.replace("@@BACKUP@@", f"${backup:08X}")
                                 .replace("@@STACK_GUARD@@", f"${stack_guard:08X}"),
                                 encoding="utf-8")
            image = compile_for_stage(compiler, stage, directory / "mali-rga.bin", generated)
            if len(image) >= SCRATCH_OFFSET:
                raise RuntimeError("compiled image would overlap scanout backup")
            current, capacity = recovery.stage_map()
            if current != stage or capacity != STAGE_LIMIT:
                raise RuntimeError("board stage changed after linking; no payload sent")
            print(f"backup=0x{backup:08X}..0x{backup + SAVE_BYTES + 4:08X} "
                  f"stack_guard=0x{stack_guard:08X}")
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
                raise RuntimeError("recovery rejected the private Mali/RGA payload")
            check_result(transcript)
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
