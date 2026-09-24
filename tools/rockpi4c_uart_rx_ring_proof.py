#!/usr/bin/env python3
"""Run a deadman-armed 400-byte UART ring proof at 1.5 Mbaud."""

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
SOURCE = ROOT / "RockPi4C/Tests/uart_rx_ring_proof.rockpi4c"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--compiler", default=str(TRACKED_COMPILER))
    options = parser.parse_args()
    recovery = Recovery(options.port, options.baud)
    try:
        stage, capacity = recovery.stage_map()
        if capacity != STAGE_LIMIT:
            raise RuntimeError("unexpected stage capacity")
        with tempfile.TemporaryDirectory(prefix="rockpi4c-rx-ring-") as folder:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(folder) / "ring-proof.bin", SOURCE)
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
            line = recovery.wait_line(lambda item: item.startswith(b"PAYLOAD RETURN X0="), 12.0)
            match = re.fullmatch(rb"PAYLOAD RETURN X0=([0-9A-F]{16})", line)
            if match is None:
                raise RuntimeError("malformed payload return")
            result = int(match.group(1), 16)
            if result >> 32 == 0x52584552:
                gap = (result >> 16) & 0xFFFF
                code = result & 0xFF
                raise RuntimeError(f"UART ring proof failed check {code}; max gap {gap / 24:.2f} us")
            if result >> 32 != 0x52585052:
                raise RuntimeError(f"unexpected proof return 0x{result:016X}")
            gap = (result >> 16) & 0xFFFF
            count = result & 0xFFFF
            if count != 400 or gap >= 10240:
                raise RuntimeError(f"invalid ring result: count={count} gap={gap / 24:.2f} us")
            print(f"UART ring read {count}/{count} bytes without error; "
                  f"max interval outside hardware pump {gap / 24:.2f} us "
                  f"({gap * 150000 / 24000000:.1f}/64 FIFO bytes); "
                  "CNTKCTL restored")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
