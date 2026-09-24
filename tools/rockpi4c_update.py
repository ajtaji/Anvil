#!/usr/bin/env python3
"""Serial file transfer and fixed-range trust update for Rock Pi 4C recovery.

The board owns one 4 MiB BSS staging array. `put` receives into that array,
checks CRC32 before touching the filesystem, then remounts and checks the file
back. `trust` accepts only the current unsigned BL3X two-copy layout, checks
the component SHA-256 metadata locally, and asks recovery to write/read back
the two fixed trust copies. `payload` queries the current dynamic stage address,
uploads a returning A64 image there, and runs it behind Anvil's deadman.

Examples:
  python tools/rockpi4c_update.py --port COM7 ls
  python tools/rockpi4c_update.py --port COM7 put 1:/update.img build.img
  python tools/rockpi4c_update.py --port COM7 get 1:/update.img downloaded.img
  python tools/rockpi4c_update.py --port COM7 payload returning.img
  python tools/rockpi4c_update.py --port COM7 trust build/rockpi4c/hdmi-gpll400/trust-hdmi.img
"""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
import time
import zlib
from pathlib import Path

import rockpi4c_sd_entry_check as entry_contract

try:
    import serial
except ImportError as exc:
    raise SystemExit("install pyserial to use the Rock Pi recovery transport") from exc


STAGE_LIMIT = 4 * 1024 * 1024
CHUNK = 16 * 1024
LEGACY_CHUNK = 1024
LEGACY_BURST = 32
TRUST_COPY = 2 * 1024 * 1024
TRUST_BYTES = 2 * TRUST_COPY
HEADER = 2048
TRUST_HEAD = 800
COMPONENT_META = 48
ENTRY = 16
BL31_ID = int.from_bytes(b"BL31", "little")
ANVIL_BASE = 0x00040000
ANVIL_LIMIT = 0x00240000


def validate_trust_image(image: bytes) -> list[dict[str, int]]:
    """Validate the format and padded payload digests emitted by the packer."""
    if len(image) != TRUST_BYTES:
        raise ValueError(f"trust image must be exactly {TRUST_BYTES} bytes")
    first, second = image[:TRUST_COPY], image[TRUST_COPY:]
    if first != second:
        raise ValueError("the two 2 MiB trust copies differ")
    if first[:4] != b"BL3X":
        raise ValueError("missing BL3X header")
    version, flags, count_and_offset = struct.unpack_from("<III", first, 4)
    if version != 0x00000100 or flags != 0x23:
        raise ValueError("unexpected BL3X version or unsigned-format flags")
    count = count_and_offset >> 16
    sign_offset = (count_and_offset & 0xFFFF) << 2
    if count != 1:
        raise ValueError("expected exactly one self-contained Anvil component")
    if sign_offset != TRUST_HEAD + count * COMPONENT_META:
        raise ValueError("component metadata offset is inconsistent")
    table = sign_offset + 256
    if table + count * ENTRY > HEADER:
        raise ValueError("component table leaves the 2 KiB header")

    sectors_cursor = HEADER // 512
    result: list[dict[str, int]] = []
    for index in range(count):
        meta = TRUST_HEAD + index * COMPONENT_META
        ent = table + index * ENTRY
        component_id, stored_sector, stored_sectors, reserved = struct.unpack_from("<4I", first, ent)
        digest = first[meta:meta + 32]
        load_address, meta_sectors, zero1, zero2 = struct.unpack_from("<4I", first, meta + 32)
        if component_id != BL31_ID or reserved or zero1 or zero2:
            raise ValueError(f"component {index} has an unexpected ID or reserved field")
        if stored_sector != sectors_cursor or stored_sector % 4:
            raise ValueError(f"component {index} payload is not contiguous and 2 KiB aligned")
        if not 0 < stored_sectors <= TRUST_COPY // 512 or stored_sectors != meta_sectors or stored_sectors % 4:
            raise ValueError(f"component {index} has an invalid padded size")
        begin, end = stored_sector * 512, (stored_sector + stored_sectors) * 512
        if end > TRUST_COPY:
            raise ValueError(f"component {index} payload escapes its 2 MiB copy")
        padded = first[begin:end]
        if hashlib.sha256(padded).digest() != digest:
            raise ValueError(f"component {index} padded SHA-256 does not match metadata")
        byte_length = stored_sectors * 512
        if load_address != ANVIL_BASE or load_address + byte_length > ANVIL_LIMIT:
            raise ValueError("self-contained Anvil load range is outside the fixed allowance")
        try:
            entry_contract.check(padded[:4096], quiet=True)
        except (AssertionError, RuntimeError, ValueError, IndexError) as exc:
            raise ValueError(
                "Anvil entry fails the EL3/DTB/runtime-address contract"
            ) from exc
        result.append({"address": load_address, "bytes": byte_length})
        sectors_cursor += stored_sectors
    if sectors_cursor > TRUST_COPY // 512:
        raise ValueError("component payloads exceed the trust copy")
    return result


class Recovery:
    def __init__(self, port: str, baud: int, timeout: float = 0.1):
        self.port = serial.Serial()
        self.port.port = port
        self.port.baudrate = baud
        self.port.timeout = timeout
        self.port.write_timeout = 5
        # USB-UART adapters may wire these outputs to board reset/boot pins.
        # Set the inactive state before opening the port so opening it cannot
        # reset the board or alter the boot straps.
        self.port.dtr = False
        self.port.rts = False
        self.port.open()
        # File downloads are unpaced once the DATA header has been accepted.
        # Give the Windows serial driver room for the complete bounded stage so
        # a scheduler pause cannot overflow the small default receive queue.
        try:
            self.port.set_buffer_size(rx_size=STAGE_LIMIT + 65536,
                                      tx_size=CHUNK)
        except (AttributeError, OSError, serial.SerialException):
            # Other pyserial backends may not expose SetupComm.  The reader
            # below still drains in bounded chunks and tolerates short gaps.
            pass
        self.rx_line = bytearray()

    def close(self) -> None:
        self.port.close()

    def send_command(self, command: str) -> None:
        if "\r" in command or "\n" in command or len(command) > 511:
            raise ValueError("command is too long or contains a line break")
        self.port.write(command.encode("ascii") + b"\n")
        self.port.flush()

    def line(self, deadline: float) -> bytes:
        while time.monotonic() < deadline:
            raw = self.port.readline()
            if raw:
                self.rx_line.extend(raw)
                newline = self.rx_line.find(b"\n")
                if newline >= 0:
                    result = bytes(self.rx_line[:newline]).rstrip(b"\r")
                    del self.rx_line[:newline + 1]
                    return result
                if len(self.rx_line) > 1024:
                    self.rx_line.clear()
                    raise RuntimeError("recovery status line exceeds 1024 bytes")
        raise TimeoutError("timed out waiting for recovery output")

    def wait_line(self, matcher, timeout: float = 15.0) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.line(deadline)
            print(line.decode("ascii", "backslashreplace"))
            if matcher(line):
                return line
        raise TimeoutError("recovery did not send the expected status")

    def transfer_in(self, data: bytes, length: int, checksum: int) -> None:
        ready = self.wait_line(lambda line: line.startswith(b"READY "), 15.0)
        fields = ready.split()
        if len(fields) not in (3, 4) or int(fields[1], 16) != length or int(fields[2], 16) != checksum:
            raise RuntimeError("board READY length/checksum differs from host request")
        window = LEGACY_CHUNK if len(fields) == 3 else int(fields[3], 16)
        if window < 1 or window > STAGE_LIMIT:
            raise RuntimeError("board advertised an invalid transfer window")
        legacy = len(fields) == 3
        for offset in range(0, length, window):
            chunk = data[offset:offset + window]
            if legacy:
                # Build 94 has the original per-byte receiver and no window
                # field. Preserve its hardware-proven 32-byte FT232 pacing so
                # it can install the first buffered build without a card move.
                for burst in range(0, len(chunk), LEGACY_BURST):
                    sent = self.port.write(chunk[burst:burst + LEGACY_BURST])
                    if sent != len(chunk[burst:burst + LEGACY_BURST]):
                        raise RuntimeError(f"short serial write at byte {offset + burst}")
                    self.port.flush()
                    time.sleep(0.0005)
            else:
                # The advertised receiver drains UART2's FIFO directly into
                # this bounded window. The next window waits for its ACK.
                sent = self.port.write(chunk)
                if sent != len(chunk):
                    raise RuntimeError(f"short serial write at byte {offset}: {sent} of {len(chunk)}")
                self.port.flush()
            ack_deadline = time.monotonic() + 5.0
            ack = b""
            while time.monotonic() < ack_deadline and not ack:
                ack = self.port.read(1)
            if ack != b"+":
                raise RuntimeError(f"missing transfer acknowledgement at byte {offset}")

    def finish_transfer(self, success_prefix: bytes, timeout: float = 180.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.line(deadline)
            if line:
                print(line.decode("ascii", "backslashreplace"))
            if line.startswith(success_prefix):
                return True
            if line.startswith((b"XFER ERROR", b"FILE WRITE FAILED", b"FILE WRITE FLUSHED", b"STORAGE MOUNT FAILED", b"STORAGE LIST FAILED", b"TRUST FORMAT", b"BACKUP COPY FAILED", b"PRIMARY COPY FAILED", b"TRUST UPDATE REFUSED", b"FILESYSTEM REMOUNT FAILED", b"PAYLOAD REFUSED", b"PAYLOAD RETURN REFUSED")):
                return False
            if line.startswith(b"BOTH TRUST COPIES READBACK VERIFIED"):
                return True
        raise TimeoutError("timed out waiting for operation result")

    def simple(self, command: str, final: bytes, timeout: float = 8.0) -> bool:
        self.send_command(command)
        return self.finish_transfer(final, timeout)

    def reboot(self) -> bool:
        """Reset through Anvil and keep listening until recovery is back."""
        self.send_command("reboot")
        self.wait_line(lambda line: line == b"RESET: RK3399 CRU WARM RESET", 8.0)
        self.wait_line(lambda line: line == b"RECOVERY READY; TYPE help", 90.0)
        return True

    def put(self, name: str, data: bytes) -> bool:
        if len(data) > STAGE_LIMIT:
            raise ValueError("file exceeds 4 MiB staging limit")
        checksum = zlib.crc32(data) & 0xFFFFFFFF
        self.send_command(f"put {name} {len(data):X} {checksum:08X}")
        self.transfer_in(data, len(data), checksum)
        return self.finish_transfer(b"FILE WRITE, FLUSH AND REMOUNTED READBACK PASS")

    def stage_map(self) -> tuple[int, int]:
        self.send_command("map")
        line = self.wait_line(lambda item: item.startswith(b"STAGE "), 8.0)
        fields = line.split()
        if len(fields) != 4 or fields[2] != b"BYTES":
            raise RuntimeError("malformed stage map")
        address, capacity = int(fields[1], 16), int(fields[3], 16)
        if address <= 0 or address & 3 or capacity != STAGE_LIMIT:
            raise RuntimeError("board advertised an invalid payload stage")
        return address, capacity

    def payload(self, data: bytes) -> bool:
        if len(data) < 4 or len(data) > STAGE_LIMIT or len(data) & 3:
            raise ValueError("payload must be 4-byte instruction aligned and fit the 4 MiB stage")
        address, capacity = self.stage_map()
        print(f"payload stage is 0x{address:016X}, capacity 0x{capacity:X}; image must be linked there or position independent")
        checksum = zlib.crc32(data) & 0xFFFFFFFF
        self.send_command(f"payload {len(data):X} {checksum:08X}")
        self.transfer_in(data, len(data), checksum)
        return self.finish_transfer(b"PAYLOAD RETURN X0=", 30.0)

    def get(self, name: str) -> bytes:
        self.send_command(f"get {name}")
        # The board reads and checks the complete file into its bounded staging
        # area before it emits DATA.  A multi-megabyte file can legitimately
        # spend longer than the command-response timeout in that preparation,
        # especially on the first cold filesystem read.  Keep the port open so
        # the DATA header and its binary body cannot begin after the host has
        # already abandoned the transfer.
        line = self.wait_line(lambda item: item.startswith(b"DATA "), 120.0)
        fields = line.split()
        if len(fields) not in (3, 4):
            raise RuntimeError("malformed DATA header")
        length, checksum = int(fields[1], 16), int(fields[2], 16)
        if length > STAGE_LIMIT:
            raise RuntimeError("board file exceeds 4 MiB transfer limit")
        window = None if len(fields) == 3 else int(fields[3], 16)
        if window is not None and (window < 1 or window > STAGE_LIMIT):
            raise RuntimeError("board advertised an invalid download window")
        data = bytearray()
        if window is not None and length:
            self.port.write(b"+")
            self.port.flush()
            while len(data) < length:
                window_end = min(length, len(data) + window)
                stall_deadline = time.monotonic() + 10.0
                while len(data) < window_end:
                    chunk = self.port.read(min(65536, window_end - len(data)))
                    if chunk:
                        data.extend(chunk)
                        stall_deadline = time.monotonic() + 10.0
                    elif time.monotonic() >= stall_deadline:
                        raise TimeoutError("timed out during acknowledged file download")
                self.port.write(b"+")
                self.port.flush()
        else:
            stall_deadline = time.monotonic() + 10.0
            while len(data) < length:
                chunk = self.port.read(min(65536, length - len(data)))
                if chunk:
                    data.extend(chunk)
                    stall_deadline = time.monotonic() + 10.0
                elif time.monotonic() >= stall_deadline:
                    raise TimeoutError("timed out during file download")
        if zlib.crc32(data) & 0xFFFFFFFF != checksum:
            raise RuntimeError("download CRC32 mismatch")
        self.wait_terminal(b"DATA DONE", 10.0)
        return bytes(data)

    def wait_terminal(self, expected: bytes, timeout: float) -> None:
        """Wait through blank framing lines, but fail promptly on device errors."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.line(deadline)
            if line:
                print(line.decode("ascii", "backslashreplace"))
            if line == expected:
                return
            if line.startswith((b"FILE ", b"XFER ERROR", b"STORAGE MOUNT FAILED")):
                raise RuntimeError(line.decode("ascii", "replace"))
        raise TimeoutError(f"recovery did not send {expected.decode('ascii')}")


def safe_name(name: str) -> str:
    if not name or len(name) > 255 or any(ord(c) < 33 or ord(c) > 126 for c in name):
        raise ValueError("remote path must be 1-255 visible ASCII characters without spaces")
    if any(c in '"\\' for c in name):
        raise ValueError("remote path may not contain quotes or backslashes")
    return name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=1500000)
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("storage", "ls", "reboot"):
        sub.add_parser(name)
    put = sub.add_parser("put")
    put.add_argument("remote")
    put.add_argument("source", type=Path)
    get = sub.add_parser("get")
    get.add_argument("remote")
    get.add_argument("destination", type=Path)
    trust = sub.add_parser("trust")
    trust.add_argument("image", type=Path)
    payload = sub.add_parser("payload")
    payload.add_argument("image", type=Path)
    args = parser.parse_args(argv)

    command = args.operation if args.operation in ("storage", "ls") else ""
    if args.operation in ("put", "get"):
        safe_name(args.remote)
    if args.operation == "put":
        data = args.source.read_bytes()
        if len(data) > STAGE_LIMIT:
            raise SystemExit("source exceeds the board's 4 MiB stage")
    elif args.operation == "trust":
        data = args.image.read_bytes()
        components = validate_trust_image(data)
        print(f"validated unsigned BL3X structure, two matching copies, {len(components)} fixed-range segments")
    elif args.operation == "payload":
        data = args.image.read_bytes()
        if len(data) < 4 or len(data) > STAGE_LIMIT or len(data) & 3:
            raise SystemExit("payload must be 4-byte instruction aligned and fit the board's 4 MiB stage")

    link = Recovery(args.port, args.baud)
    try:
        if args.operation in ("storage", "ls"):
            return 0 if link.simple(command, b"STORAGE READY" if command == "storage" else b"STORAGE LIST DONE") else 1
        if args.operation == "reboot":
            return 0 if link.reboot() else 1
        if args.operation == "put":
            return 0 if link.put(args.remote, data) else 1
        if args.operation == "get":
            received = link.get(args.remote)
            args.destination.write_bytes(received)
            print(f"saved {len(received)} bytes to {args.destination}")
            return 0
        if args.operation == "trust":
            checksum = zlib.crc32(data) & 0xFFFFFFFF
            link.send_command(f"trustupdate {checksum:08X}")
            link.transfer_in(data, TRUST_BYTES, checksum)
            return 0 if link.finish_transfer(b"BOTH TRUST COPIES READBACK VERIFIED", 900.0) else 1
        if args.operation == "payload":
            return 0 if link.payload(data) else 1
    finally:
        link.close()
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"rockpi4c_update: {exc}", file=sys.stderr)
        raise SystemExit(1)
