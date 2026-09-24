#!/usr/bin/env python3
"""Deadman-armed one-second EL3 idle rehearsal with 400 live UART RX bytes."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile
import zlib

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_idle_loop_simulation import SOURCE, validate_targets
from rockpi4c_mali_job_proof import compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    validate_targets()
    body = SOURCE.read_text()
    original = "#SIM_RX_EXPECTED = 0"
    if body.count(original) != 1:
        raise RuntimeError("idle rehearsal RX setting changed")
    body = body.replace(original, "#SIM_RX_EXPECTED = 400")
    recovery = Recovery(options.port, options.baud)
    sent = False
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected payload stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-idle-uart-") as folder:
            path = Path(folder) / "idle-uart.rockpi4c"
            path.write_text(body)
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(folder) / "idle-uart.bin", path)
            if recovery.stage_map() != (stage, capacity):
                raise RuntimeError("payload stage changed after linking")
            checksum = zlib.crc32(image) & 0xFFFFFFFF
            recovery.send_command(f"payload {len(image):X} {checksum:08X}")
            recovery.transfer_in(image, len(image), checksum)
            recovery.wait_line(lambda line: line == b"RXREADY", 10.0)
            payload = b"x" * 400
            if recovery.port.write(payload) != len(payload):
                raise RuntimeError("short UART stress write")
            recovery.port.flush()
            sent = True
            line = recovery.wait_line(lambda item: item.startswith(b"PAYLOAD RETURN X0="), 12.0)
            match = re.fullmatch(rb"PAYLOAD RETURN X0=([0-9A-F]{16})", line)
            if match is None:
                raise RuntimeError("malformed payload return")
            value = int(match.group(1), 16)
            if value >> 48 == 0x5354:
                max_gap = (value >> 32) & 0xFFFF
                max_poll = (value >> 16) & 0xFFFF
                max_screen = value & 0xFFFF
                raise RuntimeError(
                    f"UART parser rejected the test line; max RX poll gap "
                    f"{max_gap / 24:.2f} us, max recovery poll "
                    f"{max_poll / 24:.2f} us, max screen service "
                    f"{max_screen / 24:.2f} us")
            if value >> 32 == 0x49444552:
                raise RuntimeError(f"idle UART rehearsal refused: 0x{value:016X}")
            if value >> 48 != 0x4944:
                raise RuntimeError(f"unexpected idle UART return: 0x{value:016X}")
            usage = (value >> 32) & 0xFFFF
            gap_ticks = (value >> 16) & 0xFFFF
            iterations = value & 0xFFFF
            print(f"400/400 harmless UART bytes received without discard or error; "
                  f"CPU0={usage / 100:.2f}%; max RX poll gap={gap_ticks / 24:.2f} us "
                  f"({gap_ticks * 150000 / 24000000:.1f}/64 FIFO bytes); "
                  f"iterations={iterations}")
            if gap_ticks >= 10240:
                raise RuntimeError("RX poll gap exceeded the verified UART FIFO budget")
    finally:
        if sent:
            # The test line had no terminator so it cannot execute during the proof.
            recovery.send_command("")
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
