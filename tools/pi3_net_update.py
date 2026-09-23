#!/usr/bin/env python3
"""Safely stage/commit a Pi 3 P3SLOT image over its LAN9514 Ethernet port.

The board still performs every A/B admission, SHA-256, read-back and redundant
control-record operation. This host sends stop-and-wait UDP datagrams only; it
never writes a disk and never resets unless ``--reboot`` is explicit.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import secrets
import socket
import struct
import sys
import time

from pi3_slot import SlotError, validate_slot


PORT = 5556
MAGIC = b"P3N1"
REPLY_MAGIC = b"P3R1"
BEGIN, DATA, COMMIT, ABORT, STATUS, RESET = range(1, 7)
HEADER = struct.Struct("<4sIQIHH")
REPLY = struct.Struct("<4sIQIiiiQ")
MAX_CHUNK = 1024


class UpdateError(RuntimeError):
    pass


def request(op: int, session: int, offset: int = 0, payload: bytes = b"") -> bytes:
    if not 0 <= offset <= 0xFFFFFFFF:
        raise UpdateError("request offset is outside the 32-bit wire field")
    if len(payload) > MAX_CHUNK:
        raise UpdateError("request payload is larger than 1024 bytes")
    return HEADER.pack(MAGIC, op, session, offset, len(payload), 0) + payload


def parse_reply(data: bytes, op: int, session: int) -> tuple[int, int, int, int]:
    if len(data) != REPLY.size:
        raise UpdateError(f"reply has {len(data)} bytes, expected {REPLY.size}")
    magic, got_op, got_session, received, status, active, pending, generation = REPLY.unpack(data)
    if magic != REPLY_MAGIC or got_op != op or got_session != session:
        raise UpdateError("reply does not belong to the request in flight")
    if status:
        raise UpdateError(f"board refused operation {op} with status {status}")
    return received, active, pending, generation


def exchange(
    link: socket.socket,
    op: int,
    session: int,
    offset: int = 0,
    payload: bytes = b"",
    *,
    attempts: int,
    timeout: float,
) -> tuple[int, int, int, int]:
    wire = request(op, session, offset, payload)
    last: Exception | None = None
    for _ in range(attempts):
        link.send(wire)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = link.recv(2048)
            except socket.timeout as exc:
                last = exc
                break
            try:
                return parse_reply(data, op, session)
            except UpdateError as exc:
                # A delayed reply to an earlier request is not an answer to
                # this one. Keep listening inside the same bounded attempt.
                last = exc
    raise UpdateError(f"no valid board reply after {attempts} attempts: {last}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="build-produced Pi 3 P3SLOT image")
    parser.add_argument("--host", required=True, help="Pi 3 DHCP address")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--no-commit", action="store_true")
    parser.add_argument("--reboot", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.reboot and args.no_commit:
        raise UpdateError("--reboot cannot be combined with --no-commit")
    if not 1 <= args.port <= 65535 or args.timeout <= 0 or args.attempts <= 0:
        raise UpdateError("port, timeout and attempts must be positive and in range")
    if not args.image.is_file():
        raise UpdateError(f"image does not exist: {args.image}")
    image = args.image.read_bytes()
    try:
        metadata = validate_slot(image)
    except SlotError as exc:
        raise UpdateError(f"monitor slot refused: {exc}") from exc
    if len(image) > 0xFFFFFFFF:
        raise UpdateError("image is larger than the updater protocol can name")
    digest = hashlib.sha256(image).digest()
    session = secrets.randbits(64) or 1

    print(f"slot image: {args.image}")
    print(f"format: P3SLOT 1 / BCM2837 AArch64; PMF bytes {metadata['pmfBytes']}")
    print(f"bytes: {len(image)}")
    print(f"sha256: {digest.hex()}")
    print(f"board: {args.host}:{args.port}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as link:
        link.settimeout(args.timeout)
        link.connect((args.host, args.port))
        received, _, _, _ = exchange(
            link, BEGIN, session, len(image), digest,
            attempts=args.attempts, timeout=args.timeout,
        )
        if received != 0:
            raise UpdateError(f"new session began at unexpected offset {received}")
        started = time.monotonic()
        offset = 0
        while offset < len(image):
            payload = image[offset : offset + MAX_CHUNK]
            received, _, _, _ = exchange(
                link, DATA, session, offset, payload,
                attempts=args.attempts, timeout=args.timeout,
            )
            wanted = offset + len(payload)
            if received != wanted:
                raise UpdateError(f"board acknowledged offset {received}, expected {wanted}")
            offset = received
            print(f"\rreceived by board: {offset}/{len(image)} bytes", end="", flush=True)
        print()
        elapsed = max(time.monotonic() - started, 0.001)
        print(f"RAM staging verified in {elapsed:.1f}s ({len(image)/elapsed/1024:.1f} KiB/s)")

        if args.no_commit:
            exchange(link, ABORT, session, attempts=args.attempts, timeout=args.timeout)
            print("staged RAM was disarmed; the inactive slot was not selected")
            return 0

        received, _, pending, generation = exchange(
            link, COMMIT, session, len(image), attempts=args.attempts, timeout=max(args.timeout, 10.0),
        )
        if received != len(image) or pending not in (0, 1):
            raise UpdateError("commit reply did not name the complete pending slot")
        print(f"inactive slot {('A','B')[pending]} generation {generation} written, read back and committed")
        if args.reboot:
            exchange(link, RESET, session, attempts=args.attempts, timeout=args.timeout)
            print("reset acknowledged; the loader will trial the committed slot")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (UpdateError, OSError) as exc:
        print(f"!! {exc}", file=sys.stderr)
        raise SystemExit(1)
