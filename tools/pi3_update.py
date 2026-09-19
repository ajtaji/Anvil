#!/usr/bin/env python3
"""Safely stage and commit a Raspberry Pi 3 Anvil A/B image over PL011.

The Pi 3 boot card stays in the board.  Its immutable kernel8.img loader chooses
between two preallocated monitor slots.  This tool sends a candidate into RAM,
asks Anvil to write and read-verify the inactive slot, and only then commits the
next redundant boot-control record.  It never raw-writes a disk and never
reboots unless --reboot is explicitly requested.

    python tools/pi3_update.py build/pi3/anvil-slot.img --port COM7

pyserial is the only external dependency.  If --port is omitted, exactly one
serial port must be present; ambiguity is refused and the available ports are
listed.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
from pathlib import Path
import struct
import sys
import time

from pi3_slot import SlotError, validate_slot

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:  # pragma: no cover - depends on host installation
    raise SystemExit(
        "pyserial is required: install it for the Python used to run this tool"
    ) from exc


DATA_MAGIC = b"P3D1"
ACK_MAGIC = b"P3A1"
ACK_SIZE = 12
MAX_CHUNK = 1024


class UpdateError(RuntimeError):
    """A refusal or transport failure which leaves the old slot selected."""


def choose_port(explicit: str | None) -> str:
    if explicit:
        return explicit
    ports = list(list_ports.comports())
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        raise UpdateError("no serial port is present")
    choices = "\n".join(f"  {p.device}: {p.description}" for p in ports)
    raise UpdateError(
        "more than one serial port is present; select the Pi 3 with --port:\n"
        + choices
    )


def read_exact(link: serial.Serial, count: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while len(data) < count and time.monotonic() < deadline:
        part = link.read(count - len(data))
        if part:
            data.extend(part)
    return bytes(data)


def write_all(link: serial.Serial, data: bytes, timeout: float) -> None:
    """Write every byte or fail without pretending a partial frame was sent."""
    deadline = time.monotonic() + timeout
    sent = 0
    while sent < len(data) and time.monotonic() < deadline:
        count = link.write(data[sent:])
        if count is None:
            count = 0
        if count < 0 or count > len(data) - sent:
            raise UpdateError("serial write returned an impossible byte count")
        sent += count
    if sent != len(data):
        raise UpdateError(f"serial write stopped at {sent}/{len(data)} bytes")
    link.flush()


def read_line(link: serial.Serial, timeout: float) -> str | None:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while time.monotonic() < deadline:
        value = link.read(1)
        if not value:
            continue
        if value in (b"\r", b"\n"):
            if data:
                return data.decode("utf-8", "replace").strip()
            continue
        data.extend(value)
    return None


def wait_for_prompt(link: serial.Serial, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    tail = bytearray()
    while time.monotonic() < deadline:
        write_all(link, b"\r", 1.0)
        until = time.monotonic() + 0.25
        while time.monotonic() < until:
            part = link.read(128)
            if part:
                tail.extend(part)
                del tail[:-128]
                if b"pmf>" in tail:
                    return
    raise UpdateError(
        "no Pi 3 Anvil prompt answered; the early diagnostic build cannot "
        "self-update and needs the one-time A/B loader installation"
    )


def consume_emitted_prompt(link: serial.Serial, timeout: float) -> None:
    """Consume the prompt emitted after a command result before sending another."""
    deadline = time.monotonic() + timeout
    stream = bytearray()
    while time.monotonic() < deadline:
        part = link.read(128)
        if part:
            stream.extend(part)
            if b"pmf>" in stream:
                # The ANSI reset follows the visible prompt. Drain to a short
                # quiet boundary so none of it is mistaken for the next reply.
                quiet_until = time.monotonic() + 0.05
                while time.monotonic() < quiet_until:
                    tail = link.read(128)
                    if tail:
                        quiet_until = time.monotonic() + 0.05
                return
        elif len(stream) > 256:
            del stream[:-256]
    raise UpdateError("board did not emit its next updater prompt")


def recover_binary_session(link: serial.Serial, timeout: float) -> bool:
    """Wait without transmitting until the board times out to ASCII, then abort."""
    deadline = time.monotonic() + timeout
    tail = bytearray()
    while time.monotonic() < deadline:
        part = link.read(128)
        if part:
            tail.extend(part)
            if len(tail) > 512:
                del tail[:-512]
            if b"pmf>" in tail:
                # Consume the ANSI suffix before issuing an ASCII command.
                quiet_until = time.monotonic() + 0.05
                while time.monotonic() < quiet_until:
                    more = link.read(128)
                    if more:
                        quiet_until = time.monotonic() + 0.05
                lines = command(link, "update abort", 5.0)
                return any(line.startswith("aborted") for line in lines)
    return False


def command(link: serial.Serial, text: str, timeout: float) -> list[str]:
    write_all(link, text.encode("ascii") + b"\r", min(timeout, 5.0))
    deadline = time.monotonic() + timeout
    received = bytearray()
    while time.monotonic() < deadline:
        part = link.read(256)
        if not part:
            continue
        received.extend(part)
        prompt_at = received.find(b"pmf>")
        if prompt_at >= 0:
            body = bytes(received[:prompt_at]).decode("utf-8", "replace")
            lines = []
            for line in body.replace("\r", "\n").split("\n"):
                line = line.strip()
                if not line or line == text:
                    continue
                print("  " + line)
                lines.append(line)
            return lines
    raise UpdateError(f"the board did not return to its prompt after: {text}")


def begin(link: serial.Serial, length: int, digest: str, timeout: float) -> None:
    text = f"update begin {length} {digest}"
    write_all(link, text.encode("ascii") + b"\r", min(timeout, 5.0))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = read_line(link, min(1.0, max(0.01, deadline - time.monotonic())))
        if line is None or line == text:
            continue
        print("  " + line)
        if line == "rdy 0":
            # read_line may have returned at CR with LF still buffered.  No real
            # acknowledgement can exist before the first frame is sent.
            link.reset_input_buffer()
            return
        if line.startswith("!!") or line.startswith("usage"):
            raise UpdateError("the board refused the image before data transfer")
    raise UpdateError("the board did not enter Pi 3 update data mode")


def make_frame(offset: int, payload: bytes) -> bytes:
    checksum = binascii.crc32(payload) & 0xFFFFFFFF
    return (
        DATA_MAGIC
        + struct.pack("<IH", offset, len(payload))
        + struct.pack("<I", checksum)
        + payload
    )


def read_ack(link: serial.Serial, expected_offset: int, timeout: float) -> int:
    """Find one complete P3A1 record after any late partial-ACK suffix."""
    deadline = time.monotonic() + timeout
    stream = bytearray()
    while time.monotonic() < deadline:
        part = link.read(64)
        if part:
            stream.extend(part)
        marker = stream.find(ACK_MAGIC)
        if marker < 0:
            if len(stream) > len(ACK_MAGIC) - 1:
                del stream[: -(len(ACK_MAGIC) - 1)]
            continue
        if marker:
            del stream[:marker]
        if len(stream) < ACK_SIZE:
            continue
        _, next_offset, status = struct.unpack("<4sII", stream[:ACK_SIZE])
        if status != 0:
            raise UpdateError(
                f"the board refused frame ending at {expected_offset}, status {status}"
            )
        if next_offset != expected_offset:
            raise UpdateError(
                f"the board acknowledged offset {next_offset}, expected {expected_offset}"
            )
        return next_offset
    raise UpdateError("no complete P3A1 acknowledgement arrived before timeout")


def send_frame(
    link: serial.Serial,
    offset: int,
    payload: bytes,
    timeout: float,
    attempts: int,
) -> int:
    frame = make_frame(offset, payload)
    for attempt in range(1, attempts + 1):
        expected = offset + len(payload)
        write_all(link, frame, min(timeout, 5.0))
        try:
            return read_ack(link, expected, timeout)
        except UpdateError as exc:
            if attempt == attempts or "status" in str(exc) or "acknowledged offset" in str(exc):
                raise
    raise AssertionError("unreachable")


def wait_staged(link: serial.Serial, length: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    expected = f"staged {length}"
    while time.monotonic() < deadline:
        line = read_line(link, min(1.0, max(0.01, deadline - time.monotonic())))
        if line is None:
            continue
        print("  " + line)
        if line == expected:
            return
        if line.startswith("!!"):
            raise UpdateError("the board rejected the completed staged image")
    raise UpdateError("the board did not verify the completed staged image")


def request_reset(link: serial.Serial, timeout: float) -> None:
    """Require both the reset acknowledgement and the next loader banner."""
    write_all(link, b"reset\r", 5.0)
    deadline = time.monotonic() + timeout
    acknowledged = False
    while time.monotonic() < deadline:
        line = read_line(link, min(1.0, max(0.01, deadline - time.monotonic())))
        if line is None or line == "reset":
            continue
        print("  " + line)
        if line.startswith("!!"):
            raise UpdateError("the board refused or failed the reset")
        if line == "resetting":
            acknowledged = True
            continue
        if acknowledged and line.startswith("Anvil Pi3 A/B boot:"):
            print("reset proven by the next immutable-loader banner")
            return
    if not acknowledged:
        raise UpdateError("the board never acknowledged the reset request")
    raise UpdateError("reset was acknowledged but no new loader banner appeared")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="build-produced Pi 3 P3SLOT image")
    parser.add_argument("--port", help="PL011 FTDI port, for example COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--ack-timeout",
        type=float,
        default=2.0,
        help="per-frame ACK timeout; must remain below the board's inter-frame timeout",
    )
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="stage and verify the inactive slot but do not select it",
    )
    parser.add_argument(
        "--reboot",
        action="store_true",
        help="reboot after a successful commit (never implied)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.reboot and args.no_commit:
        raise UpdateError("--reboot cannot be combined with --no-commit")
    if args.baud <= 0 or args.timeout <= 0 or args.ack_timeout <= 0 or args.attempts <= 0:
        raise UpdateError("baud, timeout, ACK timeout and attempts must all be positive")
    if args.ack_timeout >= 10.0:
        raise UpdateError("--ack-timeout must stay below 10 seconds for binary-mode recovery")
    if not args.image.is_file():
        raise UpdateError(f"image does not exist: {args.image}")
    image = args.image.read_bytes()
    try:
        metadata = validate_slot(image)
    except SlotError as exc:
        raise UpdateError(f"monitor slot refused: {exc}") from exc
    if len(image) > 0xFFFFFFFF:
        raise UpdateError("the image is larger than the updater protocol can name")
    digest = hashlib.sha256(image).hexdigest()
    port = choose_port(args.port)

    print(f"slot image: {args.image}")
    print(f"PMF bytes: {metadata['pmfBytes']}")
    print(f"PMF sha256: {metadata['pmfSha256']}")
    print("slot format: P3SLOT 1 / BCM2837 AArch64")
    print(f"bytes: {len(image)}")
    print(f"sha256: {digest}")
    print(f"port: {port} at {args.baud}")

    with serial.Serial(port, args.baud, timeout=0.1, write_timeout=5) as link:
        link.dtr = False
        link.rts = False
        wait_for_prompt(link, 30.0)
        print("Pi 3 Anvil prompt found")
        begin(link, len(image), digest, args.timeout)

        started = time.monotonic()
        offset = 0
        try:
            while offset < len(image):
                payload = image[offset : offset + MAX_CHUNK]
                offset = send_frame(
                    link, offset, payload, args.ack_timeout, args.attempts
                )
                print(
                    f"\rreceived by board: {offset}/{len(image)} bytes",
                    end="",
                    flush=True,
                )
            # FIN is deliberately separate from the final data frame. The board
            # stays in binary mode until it sees this header, so loss of the final
            # data ACK can be recovered by resending the identical final frame.
            # FIN itself is proven by the following text, not by a binary ACK.
            write_all(link, make_frame(offset, b""), 5.0)
            print()
            wait_staged(link, len(image), 30.0)
            consume_emitted_prompt(link, args.timeout)
        except UpdateError:
            print("\ntransfer failed; waiting for the board's bounded binary timeout")
            if recover_binary_session(link, 35.0):
                print("board returned to ASCII and the staged session was disarmed")
            else:
                print("!! automatic session recovery was not witnessed", file=sys.stderr)
            raise
        elapsed = max(time.monotonic() - started, 0.001)
        print(f"RAM staging verified in {elapsed:.1f}s ({len(image)/elapsed/1024:.1f} KiB/s)")

        if args.no_commit:
            lines = command(link, "update abort", args.timeout)
            if not any(line.startswith("aborted") for line in lines):
                raise UpdateError("board did not disarm the staged update")
            print("staged RAM was disarmed; the inactive slot was not selected")
            return 0

        lines = command(link, "update commit", 180.0)
        if not any(line.startswith("committed ") for line in lines):
            raise UpdateError(
                "commit did not report success; the previous slot remains selected"
            )
        print("inactive slot written, read back, hash-verified and committed")

        if args.reboot:
            request_reset(link, 30.0)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UpdateError as exc:
        print(f"!! {exc}", file=sys.stderr)
        raise SystemExit(1)
