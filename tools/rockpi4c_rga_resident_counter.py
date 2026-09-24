#!/usr/bin/env python3
"""Measure installed Rock Pi RGA console counters around harmless help output."""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
import re
import tempfile
import time

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import ROOT, compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


SOURCE = ROOT / "RockPi4C/Tests/rga_resident_counter_probe.rockpi4c"
SYMBOLS = ROOT / "build/rockpi4c/anvil-flat.img.sym"
RETURN_OK = 0x52474300
NAMES = {
    "JOBS": "global_rock_rga_jobs",
    "FAILURES": "global_rock_rga_failures",
    "READY": "global_rock_rga_ready",
    "ATLAS_READY": "global_rock_rga_atlas_ready",
    "ERROR": "global_rock_rga_error",
    "ROW_WIDTH": "global_rock_rga_row_width",
    "ROW_PITCH": "global_rock_rga_row_pitch",
    "DMA_BYTES": "global_rock_screen_dma_text_bytes",
    "CPU_BYTES": "global_rock_screen_cpu_text_bytes",
}


def linked_addresses(path: Path) -> dict[str, int]:
    lines = path.read_text(encoding="ascii").splitlines()
    found: dict[str, int] = {}
    by_symbol = {symbol: label for label, symbol in NAMES.items()}
    for line in lines:
        symbol, separator, value = line.partition("=")
        if separator and symbol in by_symbol:
            label = by_symbol[symbol]
            if label in found:
                raise RuntimeError(f"duplicate installed symbol: {symbol}")
            address = int(value, 10)
            if address & 3 or not 0x02000000 <= address < 0x05000000:
                raise RuntimeError(f"installed symbol is outside mapped monitor DDR: {symbol}")
            found[label] = address
    if set(found) != set(NAMES) or len(set(found.values())) != len(found):
        raise RuntimeError("installed RGA counter symbols are missing or aliased")
    return found


def capture_counters(recovery: Recovery, image: bytes) -> tuple[int, ...]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        accepted = recovery.payload(image)
    transcript = output.getvalue()
    print(transcript.encode("ascii", "backslashreplace").decode("ascii"), end="")
    if not accepted:
        raise RuntimeError("resident-counter payload was refused")
    result = re.search(r"^PAYLOAD RETURN X0=([0-9A-F]{16})$", transcript, re.M)
    sample = re.search(r"^RGAC ((?:[0-9A-F]{8} ){8}[0-9A-F]{8})$", transcript, re.M)
    if result is None or int(result.group(1), 16) != RETURN_OK or sample is None:
        raise RuntimeError("resident-counter telemetry or return is incomplete")
    return tuple(int(field, 16) for field in sample.group(1).split())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    compiler = resolve_compiler(options.compiler)
    addresses = linked_addresses(SYMBOLS)
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected live stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-rga-counter-") as directory:
            directory = Path(directory)
            source = SOURCE.read_text(encoding="ascii")
            for label, address in addresses.items():
                marker = f"@@{label}@@"
                if source.count(marker) != 1:
                    raise RuntimeError(f"counter source marker changed: {marker}")
                source = source.replace(marker, f"${address:08X}")
            generated = directory / "resident-counter.rockpi4c"
            generated.write_text(source, encoding="ascii")
            image = compile_for_stage(compiler, stage, directory / "resident-counter.bin", generated)
            current, capacity = recovery.stage_map()
            if (current, capacity) != (stage, STAGE_LIMIT):
                raise RuntimeError("live stage moved after linking")
            before = capture_counters(recovery, image)
            if before[0:4] != (1, 1, 1920, 7680):
                raise RuntimeError(f"RGA/atlas or geometry not admitted: {before[0:4]}")
            for _ in range(4):
                recovery.send_command("help")
                recovery.wait_line(lambda line: line.startswith(b"COMMANDS:"), 8.0)
                time.sleep(0.15)
            after = capture_counters(recovery, image)
            print(f"RGA counters before={before} after={after}")
            if after[4] <= before[4]:
                raise RuntimeError("no resident RGA row job occurred after four console lines")
            if after[5] != before[5] or after[6] != before[6]:
                raise RuntimeError("RGA failure/error counter changed during console output")
            print(f"resident RGA row publish PASS: {after[4] - before[4]} new jobs, no failures")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
