#!/usr/bin/env python3
"""Protocol-level tests for the Rock Pi 4C serial file/update host."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from unittest import mock
import zlib

import rockpi4c_sd_trust as trust
import rockpi4c_update as update


class FakeSerial:
    def __init__(self, lines=(), binary=b"", acks=(), binary_gaps=0):
        self.lines = list(lines)
        self.binary = bytearray(binary)
        self.acks = list(acks)
        self.binary_gaps = binary_gaps
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def readline(self):
        return self.lines.pop(0) if self.lines else b""

    def read(self, count):
        if count == 1 and self.acks:
            return self.acks.pop(0)
        if self.binary_gaps:
            self.binary_gaps -= 1
            return b""
        result = bytes(self.binary[:count])
        del self.binary[:len(result)]
        return result

    def close(self):
        pass


def link(fake: FakeSerial) -> update.Recovery:
    result = update.Recovery.__new__(update.Recovery)
    result.port = fake
    result.rx_line = bytearray()
    return result


def expect_reject(data: bytes) -> None:
    try:
        update.validate_trust_image(data)
    except ValueError:
        return
    raise AssertionError("invalid trust image accepted")


def main() -> None:
    payload = b"remote file\x00content"
    checksum = zlib.crc32(payload) & 0xFFFFFFFF
    for body in (b"", payload):
        body_crc = zlib.crc32(body) & 0xFFFFFFFF
        fake = FakeSerial(
            lines=[f"DATA {len(body):08X} {body_crc:08X}\r".encode(), b"\n", b"\r\n", b"DATA DONE\r\n"],
            binary=body,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            got = link(fake).get("1:/x")
        assert got == body

    # USB serial reads may return no bytes while an unpaced download is still
    # active. One short read is not a failed transfer; only the bounded stall
    # deadline may terminate it.
    fake = FakeSerial(
        lines=[f"DATA {len(payload):08X} {checksum:08X}\r\n".encode(),
               b"DATA DONE\r\n"],
        binary=payload,
        binary_gaps=3,
    )
    with contextlib.redirect_stdout(io.StringIO()):
        assert link(fake).get("1:/gapped") == payload

    large = bytes(range(256)) * 256
    large_crc = zlib.crc32(large) & 0xFFFFFFFF
    fake = FakeSerial(
        lines=[f"DATA {len(large):08X} {large_crc:08X} {update.CHUNK:08X}\r\n".encode(),
               b"DATA DONE\r\n"],
        binary=large,
        binary_gaps=3,
    )
    with contextlib.redirect_stdout(io.StringIO()):
        assert link(fake).get("1:/windowed") == large
    assert fake.writes == [b"get 1:/windowed\n"] + [b"+"] * 5

    fake = FakeSerial(lines=[
        b"RESET: RK3399 CRU WARM RESET\r\n",
        b"DDR Version 1.30\r\n",
        b"RECOVERY READY; TYPE help\r\n",
    ])
    with contextlib.redirect_stdout(io.StringIO()):
        assert link(fake).reboot()
    assert fake.writes == [b"reboot\n"]

    fake = FakeSerial(
        lines=[f"READY {len(payload):08X} {checksum:08X}\r\n".encode(),
               b"XFER DONE CHECKSUM PASS\r\n",
               b"FILE WRITE, FLUSH AND REMOUNTED READBACK PASS\r\n"],
        acks=[b"+"],
    )
    with contextlib.redirect_stdout(io.StringIO()):
        assert link(fake).put("1:/x", payload)
    assert fake.writes[0].startswith(b"put 1:/x ") and fake.writes[1] == payload

    fake = FakeSerial(
        lines=[f"READY {len(large):08X} {large_crc:08X} {update.CHUNK:08X}\r\n".encode(),
               b"XFER DONE CHECKSUM PASS\r\n",
               b"FILE WRITE, FLUSH AND REMOUNTED READBACK PASS\r\n"],
        acks=[b"+"] * (len(large) // update.CHUNK),
    )
    with contextlib.redirect_stdout(io.StringIO()):
        assert link(fake).put("1:/large", large)
    assert [len(item) for item in fake.writes[1:]] == [update.CHUNK] * 4

    legacy = bytes(range(256)) * 8
    legacy_crc = zlib.crc32(legacy) & 0xFFFFFFFF
    fake = FakeSerial(
        lines=[f"READY {len(legacy):08X} {legacy_crc:08X}\r\n".encode(),
               b"XFER DONE CHECKSUM PASS\r\n",
               b"FILE WRITE, FLUSH AND REMOUNTED READBACK PASS\r\n"],
        acks=[b"+"] * (len(legacy) // update.LEGACY_CHUNK),
    )
    with contextlib.redirect_stdout(io.StringIO()):
        assert link(fake).put("1:/legacy", legacy)
    assert [len(item) for item in fake.writes[1:]] == [update.LEGACY_BURST] * (len(legacy) // update.LEGACY_BURST)

    class OpenCheck:
        def open(self):
            assert self.dtr is False and self.rts is False
        def close(self):
            pass

    original_serial = update.serial.Serial
    opened = OpenCheck()
    update.serial.Serial = lambda: opened
    try:
        update.Recovery("COM7", 1500000).close()
    finally:
        update.serial.Serial = original_serial

    fake = FakeSerial(
        lines=[f"READY {len(payload):08X} {checksum:08X}\r\n".encode(),
               b"XFER ERROR CHECKSUM; NO WRITE\r\n"],
        acks=[b"+"],
    )
    with contextlib.redirect_stdout(io.StringIO()):
        assert not link(fake).put("1:/x", payload)

    tiny_crc = zlib.crc32(b"x") & 0xFFFFFFFF
    fake = FakeSerial(lines=[f"READY 00000001 {tiny_crc:08X}\r\n".encode()], acks=[b""])
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            link(fake).put("1:/x", b"x")
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing chunk acknowledgement was accepted")

    parts = [
        trust.Component(b"BL31", update.ANVIL_BASE,
                        bytes(range(256)) * 9, Path("anvil")),
    ]
    image = trust.build_image(parts)
    expect_reject(image)  # Digest-valid images with a stale or arbitrary entry are unsafe.
    with mock.patch.object(update.entry_contract, "check") as entry_check:
        report = update.validate_trust_image(image)
        entry_check.assert_called_once()
    assert [item["address"] for item in report] == [update.ANVIL_BASE]
    changed = bytearray(image)
    changed[trust.HEADER_SIZE + 1] ^= 1
    changed[update.TRUST_COPY + trust.HEADER_SIZE + 1] ^= 1
    with mock.patch.object(update.entry_contract, "check"):
        expect_reject(bytes(changed))
    changed = bytearray(image)
    changed[update.TRUST_COPY] ^= 1
    with mock.patch.object(update.entry_contract, "check"):
        expect_reject(bytes(changed))
    print("rockpi4c_update_protocol_test: PASS (reset/recovery, legacy and acknowledged get, negotiated 16-KiB and build-94 paced put, CRC/error, trust)")


if __name__ == "__main__":
    main()
