#!/usr/bin/env python3
"""Focused host gate for the Pi 3 Ethernet update wire client."""

from __future__ import annotations

import pathlib
import socket
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pi3_net_update as netup


def reply(op: int, session: int, received: int, status: int = 0) -> bytes:
    return netup.REPLY.pack(b"P3R1", op, session, received, status, 0, 1, 9)


class FakeSocket:
    def __init__(self, answers: list[bytes | Exception]):
        self.answers = list(answers)
        self.sent: list[bytes] = []

    def send(self, data: bytes) -> int:
        self.sent.append(data)
        return len(data)

    def recv(self, size: int) -> bytes:
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def refuses(fn, text: str) -> None:
    try:
        fn()
    except netup.UpdateError as exc:
        assert text in str(exc), (text, exc)
    else:
        raise AssertionError("expected refusal containing " + text)


def main() -> int:
    session = 0x1122334455667788
    payload = bytes(range(251))
    wire = netup.request(netup.DATA, session, 0x12345678, payload)
    assert len(wire) == netup.HEADER.size + len(payload)
    assert netup.HEADER.unpack_from(wire) == (
        b"P3N1", netup.DATA, session, 0x12345678, len(payload), 0
    )
    assert wire[netup.HEADER.size:] == payload

    assert netup.parse_reply(reply(netup.DATA, session, len(payload)), netup.DATA, session) == (
        len(payload), 0, 1, 9
    )
    refuses(lambda: netup.parse_reply(b"short", netup.DATA, session), "expected 40")
    refuses(lambda: netup.parse_reply(reply(netup.DATA, session + 1, 1), netup.DATA, session), "does not belong")
    refuses(lambda: netup.parse_reply(reply(netup.DATA, session, 1, -18), netup.DATA, session), "status -18")

    link = FakeSocket([socket.timeout(), reply(netup.DATA, session, len(payload))])
    got = netup.exchange(
        link, netup.DATA, session, 0, payload, attempts=2, timeout=0.001
    )
    assert got[0] == len(payload) and len(link.sent) == 2 and link.sent[0] == link.sent[1]

    link = FakeSocket([
        reply(netup.BEGIN, session, 0),
        reply(netup.DATA, session, len(payload)),
    ])
    # A delayed reply is ignored inside the attempt; it cannot acknowledge a
    # different operation merely because its session is the same.
    got = netup.exchange(
        link, netup.DATA, session, 0, payload, attempts=1, timeout=0.01
    )
    assert got[0] == len(payload) and len(link.sent) == 1

    refuses(lambda: netup.request(netup.DATA, session, 0, bytes(1025)), "larger than 1024")
    print("pi3_net_update_host_check PASS: 11 framing/retry/refusal checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
