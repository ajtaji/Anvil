#!/usr/bin/env python3
"""Link and run the bounded RK3399 Mali WRITE_VALUE proof at the live stage.

This is a private-memory job and does not draw into the display. The recovery
payload command checks CRC32 and arms the physical deadman before entry.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_update import Recovery, STAGE_LIMIT


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/mali_write_value_payload.rockpi4c"
BSS = 0x10000000
BSS_LIMIT = BSS + 0x10000
MONITOR_STACK = 0x05000000
STACK_GUARD = 0x10000
STAGE_TO_STACK_GAP = 0x100000
EXPECTED_RETURN = 0x47513000


def payload_stack_for_stage(stage: int) -> int:
    if stage <= 0 or stage & 3:
        raise RuntimeError("invalid stage address")
    stack = (stage + STAGE_LIMIT + STAGE_TO_STACK_GAP + 0xFFFF) & ~0xFFFF
    if stack + STACK_GUARD > MONITOR_STACK:
        raise RuntimeError("no payload stack fits above the live stage and below the monitor stack")
    return stack


def compile_for_stage(compiler: str, stage: int, destination: Path,
                      source: Path = SOURCE) -> bytes:
    stack = payload_stack_for_stage(stage)
    if stage + STAGE_LIMIT > BSS:
        raise RuntimeError("payload stage intersects the private BSS")
    command = [
        compiler, "--compile", str(source), "-t", "rockpi4c",
        "--load-addr", f"0x{stage:X}",
        "--bss-addr", f"0x{BSS:X}",
        "--stack-addr", f"0x{stack:X}",
        "--entry-returns", "-o", str(destination),
    ]
    environment = os.environ.copy()
    environment["PMF_ROOT"] = str(ROOT)
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True,
        check=False,
    )
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode:
        raise RuntimeError(f"PureMetal compile failed ({completed.returncode})")
    expected = (
        f"linked for ${stage:X}",
        f"BSS placed at ${BSS:X}",
        f"initial stack top ${stack:X}",
        "--entry-returns",
    )
    if any(phrase not in completed.stdout for phrase in expected):
        raise RuntimeError("compiler did not confirm the requested load/BSS/stack/return contract")
    bss_range = re.search(r"\bbss \$([0-9A-F]+)\.\.\$([0-9A-F]+)\b", completed.stdout)
    if bss_range is None or int(bss_range.group(1), 16) != BSS or \
            int(bss_range.group(2), 16) >= BSS_LIMIT:
        raise RuntimeError("compiler BSS escaped the private 64 KiB proof range")
    if not destination.is_file():
        raise RuntimeError("compiler did not produce a payload")
    image = destination.read_bytes()
    if len(image) < 4 or len(image) > STAGE_LIMIT or len(image) & 3:
        raise RuntimeError("payload has an invalid size or alignment")
    if stage + len(image) > stack - STACK_GUARD:
        raise RuntimeError("linked payload reaches the reserved 64 KiB stack gap")
    print(f"payload extent 0x{stage:08X}..0x{stage + len(image):08X}; "
          f"stack guard starts at 0x{stack - STACK_GUARD:08X}")
    return image


def check_result(transcript: str) -> None:
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    if result is None or int(result.group(1), 16) != EXPECTED_RETURN:
        raise RuntimeError("Mali proof did not return its guarded success code")
    job = re.search(r"^J0 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) "
                    r"([0-9A-F]{8}) ([0-9A-F]{8})$", transcript, re.M)
    if job is None:
        raise RuntimeError("Mali proof did not report the job and MMU status")
    raw, target, header_status, slot_status, fault = (
        int(value, 16) for value in job.groups()
    )
    if raw & 2 == 0 or raw & 0x20000 or target or fault or header_status != 1:
        raise RuntimeError("Mali job failed, touched no target, or reported an MMU fault")
    print("Mali WRITE_VALUE job PASS: private target zeroed; MMU fault clear")


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
        with tempfile.TemporaryDirectory(prefix="rockpi4c-mali-") as directory:
            image = compile_for_stage(compiler, stage, Path(directory) / "mali-job.bin")
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
