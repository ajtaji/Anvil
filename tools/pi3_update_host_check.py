#!/usr/bin/env python3
"""Desk gate for the Pi 3 serial A/B update host protocol."""

from __future__ import annotations

import binascii
import hashlib
from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi3_update as update  # noqa: E402
import pi3_ab_provision as provision  # noqa: E402
import pi3_slot as slot_format  # noqa: E402


class FakeLink:
    def __init__(self, replies: list[bytes] | None = None):
        self.rx = bytearray()
        self.writes: list[bytes] = []
        self.replies = list(replies or [])

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        if self.replies:
            self.rx.extend(self.replies.pop(0))
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, count: int) -> bytes:
        part = bytes(self.rx[:count])
        del self.rx[:count]
        return part

    def reset_input_buffer(self) -> None:
        self.rx.clear()


class StalledWriteLink(FakeLink):
    def write(self, data: bytes) -> int:
        return 0


def refusal(callable_, contains: str) -> None:
    try:
        callable_()
    except RuntimeError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected refusal containing {contains!r}")


def main() -> int:
    checks = 0
    payload = bytes(range(251))
    frame = update.make_frame(0x12345678, payload)
    assert frame[:4] == b"P3D1"
    assert struct.unpack("<I", frame[4:8])[0] == 0x12345678
    assert struct.unpack("<H", frame[8:10])[0] == len(payload)
    assert struct.unpack("<I", frame[10:14])[0] == (binascii.crc32(payload) & 0xFFFFFFFF)
    assert frame[14:] == payload
    checks += 5

    fin = update.make_frame(len(payload), b"")
    assert fin[:4] == b"P3D1"
    assert struct.unpack("<I", fin[4:8])[0] == len(payload)
    assert struct.unpack("<H", fin[8:10])[0] == 0
    assert struct.unpack("<I", fin[10:14])[0] == 0
    checks += 4

    ack = struct.pack("<4sII", b"P3A1", len(payload), 0)
    link = FakeLink([ack])
    assert update.send_frame(link, 0, payload, 0.01, 1) == len(payload)
    assert link.writes == [update.make_frame(0, payload)]
    checks += 2

    # Lost ACK: resend the identical frame and accept its duplicate ACK.
    link = FakeLink([b"", ack])
    assert update.send_frame(link, 0, payload, 0.01, 2) == len(payload)
    assert link.writes[0] == link.writes[1]
    checks += 2

    # A late suffix from a partial first ACK must not be joined to the next
    # ACK.  Retry finds the next complete P3A1 record in the stream.
    link = FakeLink([ack[:5], ack[5:] + ack])
    assert update.send_frame(link, 0, payload, 0.01, 2) == len(payload)
    assert link.writes[0] == link.writes[1]
    checks += 2

    refusal(lambda: update.send_frame(FakeLink([struct.pack("<4sII", b"NOPE", len(payload), 0)]), 0, payload, 0.01, 1), "no complete")
    refusal(lambda: update.send_frame(FakeLink([struct.pack("<4sII", b"P3A1", len(payload), 7)]), 0, payload, 0.01, 1), "status 7")
    refusal(lambda: update.send_frame(FakeLink([struct.pack("<4sII", b"P3A1", len(payload) - 1, 0)]), 0, payload, 0.01, 1), "expected")
    refusal(lambda: update.send_frame(FakeLink([b"short"]), 0, payload, 0.01, 1), "no complete")
    refusal(lambda: update.write_all(StalledWriteLink(), b"abc", 0.001), "0/3")
    checks += 5

    text = "update begin 251 " + "ab" * 32
    link = FakeLink([(text + "\r\nrdy 0\r\n").encode("ascii")])
    update.begin(link, 251, "ab" * 32, 0.1)
    assert link.writes == [(text + "\r").encode("ascii")]
    checks += 1
    refusal(lambda: update.begin(FakeLink([b"!! slot capacity is too small\r\n"]), 251, "ab" * 32, 0.1), "refused")
    checks += 1

    link = FakeLink([b"update commit\r\ncommitted slot B generation 2\r\npmf>"])
    assert update.command(link, "update commit", 0.1) == ["committed slot B generation 2"]
    checks += 1

    link = FakeLink([b"reset\r\nresetting\r\nAnvil Pi3 A/B boot: validated memory\r\n"])
    update.request_reset(link, 0.1)
    assert link.writes == [b"reset\r"]
    refusal(lambda: update.request_reset(FakeLink([b"!! reset refused\r\n"]), 0.1), "refused")
    refusal(lambda: update.request_reset(FakeLink([b"resetting\r\n"]), 0.01), "no new loader")
    checks += 3

    link = FakeLink([b"update commit\r\ncommitted slot B generation 2\r\npmf>"])
    link.rx.extend(b"\n\x1b[92mpmf> \x1b[0m")
    update.consume_emitted_prompt(link, 0.1)
    assert update.command(link, "update commit", 0.1) == ["committed slot B generation 2"]
    checks += 1

    link = FakeLink([b"update abort\r\naborted; the selected boot slot did not change\r\npmf>"])
    link.rx.extend(b"\x1b[92mpmf> \x1b[0m")
    assert update.recover_binary_session(link, 0.1)
    assert link.writes == [b"update abort\r"]
    checks += 2

    raw_image = b"\x00\x00\x00\x14monitor-image"
    pmf = bytearray(slot_format.PMF_HEADER_BYTES)
    struct.pack_into(
        "<8sIIQQQQQII",
        pmf,
        0,
        slot_format.PMF_MAGIC,
        slot_format.PMF_VERSION,
        slot_format.PMF_HEADER_BYTES,
        slot_format.LOAD_ADDRESS,
        slot_format.LOAD_ADDRESS,
        len(raw_image),
        slot_format.BSS_ADDRESS,
        0x1000,
        0,
        0,
    )
    pmf[64:96] = hashlib.sha256(raw_image).digest()
    struct.pack_into(
        "<IIQ",
        pmf,
        96,
        slot_format.PMF_ARCH_AARCH64,
        slot_format.SLOT_TARGET,
        slot_format.STACK_ADDRESS,
    )
    pmf = bytes(pmf) + raw_image
    monitor, metadata = slot_format.wrap_monitor(pmf)
    assert monitor[:8] == slot_format.SLOT_MAGIC
    assert struct.unpack_from("<IIIIQQ", monitor, 8) == (
        slot_format.SLOT_VERSION,
        slot_format.SLOT_HEADER_BYTES,
        slot_format.SLOT_TARGET,
        slot_format.SLOT_ISA,
        slot_format.STACK_ADDRESS,
        len(pmf),
    )
    assert monitor[40:72] == hashlib.sha256(pmf).digest()
    assert monitor[72:128] == bytes(56)
    assert monitor[128:] == pmf
    assert metadata["imageBytes"] == len(raw_image)
    checks += 6

    bad = bytearray(pmf)
    bad[0] ^= 1
    refusal(lambda: slot_format.wrap_monitor(bytes(bad)), "not a PMFBOOT")
    bad = bytearray(pmf)
    struct.pack_into("<Q", bad, 32, len(raw_image) + 1)
    refusal(lambda: slot_format.wrap_monitor(bytes(bad)), "length")
    bad = bytearray(pmf)
    bad[-1] ^= 1
    refusal(lambda: slot_format.wrap_monitor(bytes(bad)), "SHA-256")
    bad = bytearray(pmf)
    struct.pack_into("<Q", bad, 40, slot_format.BSS_ADDRESS + 0x1000)
    refusal(lambda: slot_format.wrap_monitor(bytes(bad)), "BSS")
    bad = bytearray(pmf)
    struct.pack_into("<I", bad, 56, 1)
    refusal(lambda: slot_format.wrap_monitor(bytes(bad)), "non-returning")
    bad = bytearray(pmf)
    struct.pack_into("<I", bad, 100, 2711)
    refusal(lambda: slot_format.wrap_monitor(bytes(bad)), "not compiled for BCM2837")
    bad = bytearray(pmf)
    struct.pack_into("<Q", bad, 104, slot_format.STACK_ADDRESS + 16)
    refusal(lambda: slot_format.wrap_monitor(bytes(bad)), "stack")
    checks += 7

    loader_raw = b"\x00\x00\x00\x14immutable-loader"
    loader_pmf = bytearray(slot_format.PMF_HEADER_BYTES)
    struct.pack_into(
        "<8sIIQQQQQII",
        loader_pmf,
        0,
        slot_format.PMF_MAGIC,
        slot_format.PMF_VERSION,
        slot_format.PMF_HEADER_BYTES,
        slot_format.LOADER_LOAD_ADDRESS,
        slot_format.LOADER_LOAD_ADDRESS,
        len(loader_raw),
        slot_format.LOADER_BSS_ADDRESS,
        0x1000,
        0,
        0,
    )
    loader_pmf[64:96] = hashlib.sha256(loader_raw).digest()
    struct.pack_into(
        "<IIQ",
        loader_pmf,
        96,
        slot_format.PMF_ARCH_AARCH64,
        slot_format.SLOT_TARGET,
        slot_format.LOADER_STACK_ADDRESS,
    )
    loader_pmf = bytes(loader_pmf) + loader_raw
    loader_metadata = slot_format.validate_loader_pmf(loader_pmf, loader_raw)
    assert loader_metadata["target"] == slot_format.SLOT_TARGET
    assert loader_metadata["stackAddress"] == slot_format.LOADER_STACK_ADDRESS
    refusal(
        lambda: slot_format.validate_loader_pmf(loader_pmf, loader_raw + b"x"),
        "not the exact image",
    )
    bad_loader = bytearray(loader_pmf)
    struct.pack_into("<I", bad_loader, 100, 2711)
    refusal(
        lambda: slot_format.validate_loader_pmf(bytes(bad_loader), loader_raw),
        "not compiled for BCM2837",
    )
    bad_loader = bytearray(loader_pmf)
    struct.pack_into("<Q", bad_loader, 104, slot_format.LOADER_STACK_ADDRESS + 16)
    refusal(
        lambda: slot_format.validate_loader_pmf(bytes(bad_loader), loader_raw),
        "stack",
    )
    bad_loader = bytearray(loader_pmf)
    struct.pack_into(
        "<Q",
        bad_loader,
        48,
        slot_format.LOADER_BSS_LIMIT - slot_format.LOADER_BSS_ADDRESS + 1,
    )
    refusal(
        lambda: slot_format.validate_loader_pmf(bytes(bad_loader), loader_raw),
        "BSS",
    )
    checks += 6

    assert slot_format.validate_slot(monitor)["slotSha256"] == hashlib.sha256(monitor).hexdigest()
    bad_slot = bytearray(monitor)
    bad_slot[72] = 1
    refusal(lambda: slot_format.validate_slot(bytes(bad_slot)), "reserved")
    bad_slot = bytearray(monitor)
    bad_slot[40] ^= 1
    refusal(lambda: slot_format.validate_slot(bytes(bad_slot)), "P3SLOT PMF SHA-256")
    checks += 3

    record = provision.control_record(0, 1, monitor)
    assert len(record) == 512
    assert struct.unpack_from("<IIQQII", record, 0) == (
        provision.CONTROL_MAGIC,
        provision.CONTROL_VERSION,
        1,
        len(monitor),
        0,
        provision.LOAD_ADDRESS,
    )
    assert record[32:64] == __import__("hashlib").sha256(monitor).digest()
    assert struct.unpack_from("<I", record, 64)[0] == provision.CONTROL_CONFIRMED
    assert struct.unpack_from("<I", record, 508)[0] == (binascii.crc32(record[:508]) & 0xFFFFFFFF)
    assert sum(map(len, provision.padded_image(monitor))) == provision.SLOT_BYTES
    assert sum(map(len, provision.all_zero_slot())) == provision.SLOT_BYTES
    checks += 7

    with tempfile.TemporaryDirectory(prefix="pi3-provision-gate-") as temporary:
        root = Path(temporary)
        refusal(lambda: provision.check_card_root(root), "required files")
        for name in provision.REQUIRED_FIRMWARE:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        provision.check_card_root(root)
        provision.write_atomic(root / "EXACT.BIN", [b"one", b"two"])
        assert (root / "EXACT.BIN").read_bytes() == b"onetwo"
        checks += 3

    print(f"pi3 update host gate: PASS ({checks} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
