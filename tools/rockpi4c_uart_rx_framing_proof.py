#!/usr/bin/env python3
"""Check LF and CRLF command framing with prefetched binary bytes."""

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
SOURCE = ROOT / "RockPi4C/Tests/uart_rx_framing_proof.rockpi4c"
FIRST = bytes(range(32))
SECOND = bytes(((index * 37 + 11) & 255) for index in range(32))


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
        with tempfile.TemporaryDirectory(prefix="rockpi4c-rx-frame-") as folder:
            image = compile_for_stage(resolve_compiler(options.compiler), stage,
                                      Path(folder) / "framing.bin", SOURCE)
            if recovery.stage_map() != (stage, capacity):
                raise RuntimeError("payload stage changed after linking")
            checksum = zlib.crc32(image) & 0xFFFFFFFF
            recovery.send_command(f"payload {len(image):X} {checksum:08X}")
            recovery.transfer_in(image, len(image), checksum)
            recovery.wait_line(lambda line: line == b"FRAME1READY", 10.0)
            first_frame = b"Q\n" + FIRST
            if recovery.port.write(first_frame) != len(first_frame):
                raise RuntimeError("short LF frame write")
            recovery.port.flush()
            recovery.wait_line(lambda line: line == b"FRAME2READY", 10.0)
            second_frame = b"R\r\n" + SECOND
            if recovery.port.write(second_frame) != len(second_frame):
                raise RuntimeError("short CRLF frame write")
            recovery.port.flush()
            line = recovery.wait_line(lambda item: item.startswith(b"PAYLOAD RETURN X0="), 12.0)
            match = re.fullmatch(rb"PAYLOAD RETURN X0=([0-9A-F]{16})", line)
            if match is None:
                raise RuntimeError("malformed payload return")
            value = int(match.group(1), 16)
            if value >> 32 == 0x4652414D:
                raise RuntimeError(f"framing payload failed check {value & 255}")
            expected = ((zlib.crc32(FIRST) & 0xFFFFFFFF) << 32) | (zlib.crc32(SECOND) & 0xFFFFFFFF)
            if value != expected:
                raise RuntimeError(f"binary CRC mismatch: board {value:016X}, host {expected:016X}")
            print(f"LF and CRLF framing passed; 32-byte binary bodies match host CRCs "
                  f"{expected >> 32:08X} and {expected & 0xFFFFFFFF:08X}")
    finally:
        recovery.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
