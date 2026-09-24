#!/usr/bin/env python3
"""Check 400 live UART bytes during the edited synchronous PL330 copy."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile
import zlib

from pmf_compiler import TRACKED_COMPILER, resolve_compiler
from rockpi4c_mali_job_proof import compile_for_stage
from rockpi4c_update import Recovery, STAGE_LIMIT


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RockPi4C/Tests/dma_uart_pump_proof.rockpi4c"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if stage != 0x03CEF748 or capacity != STAGE_LIMIT:
            raise RuntimeError("payload scratch map differs from the validated stage")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-dma-uart-") as folder:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(folder) / "dma-uart.bin", SOURCE)
            if recovery.stage_map() != (stage, capacity):
                raise RuntimeError("payload stage changed after linking")
            checksum = zlib.crc32(image) & 0xFFFFFFFF
            recovery.send_command(f"payload {len(image):X} {checksum:08X}")
            recovery.transfer_in(image, len(image), checksum)
            recovery.wait_line(lambda line: line == b"DMARDY", 10.0)
            data = b"x" * 400
            if recovery.port.write(data) != len(data):
                raise RuntimeError("short host UART write")
            recovery.port.flush()
            line = recovery.wait_line(lambda item: item.startswith(b"PAYLOAD RETURN X0="), 12.0)
            match = re.fullmatch(rb"PAYLOAD RETURN X0=([0-9A-F]{16})", line)
            if match is None:
                raise RuntimeError("malformed payload return")
            value = int(match.group(1), 16)
            if value >> 32 == 0x44504552:
                gap = (value >> 16) & 0xFFFF
                context = (value >> 8) & 0xFF
                code = value & 0xFF
                raise RuntimeError(f"DMA/UART proof failed check {code}; max outside-pump gap {gap / 24:.2f} us at phase {context}")
            if value >> 48 != 0x4450:
                raise RuntimeError(f"unexpected proof return 0x{value:016X}")
            gap = (value >> 32) & 0xFFFF
            dma_us = (value >> 16) & 0xFFFF
            count = value & 0xFFFF
            if count != 400 or gap >= 10240:
                raise RuntimeError(f"invalid DMA/UART result count={count} gap={gap / 24:.2f} us")
            print(f"8 KiB PL330 exact copy and {count}/400 UART bytes passed; "
                  f"DMA {dma_us} us, max outside-pump gap "
                  f"{gap / 24:.2f} us ({gap * 150000 / 24000000:.1f}/64 FIFO bytes)")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
