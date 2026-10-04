#!/usr/bin/env python3
"""Offline checks for sr's bounded kept-capture transport."""

import socket
import struct
import zlib

from pmfshot_wifi import (
    ReliableShotError, SHOT_MAGIC, TAG_END, TAG_HDR,
    decode_kept_runs, grab_kept_reliable, parse_kept_header,
)


class ScriptedConsole:
    def __init__(self, packets):
        self.addr = ("192.0.2.4", 5555)
        self.sock = object()
        self.packets = list(packets)
        self.acks = []
        self.commands = []
        self.transcript = []

    def send(self, command):
        self.commands.append(command)

    def _recv_peer(self):
        if self.packets:
            return self.packets.pop(0)
        raise socket.timeout()

    def _sendto(self, payload):
        self.acks.append(payload)
        return True


def header(seq=7, magic=SHOT_MAGIC, width=6, runs=4):
    words = (width, 4, runs, 8, magic, 1, seq, width * 4, 0, 2,
             0x89ABCDEF, 0x01234567, width, 4, 4, 1, 1, width * 16)
    return struct.pack("<I18I", TAG_HDR, *words)


def packet(tag, payload):
    return struct.pack("<I", tag) + payload


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def rejected(call, needle):
    try:
        call()
    except ReliableShotError as error:
        require(needle in str(error), f"wrong rejection: {error}")
    else:
        raise AssertionError(f"accepted {needle}")


def main():
    body = b"".join(struct.pack("<II", 6, pixel) for pixel in
                    (0x00112233, 0x00445566, 0x00778899, 0x00AABBCC))
    chunk = packet(0, body)
    end = packet(TAG_END, struct.pack("<III", 4, zlib.crc32(body), 1))
    first = header()
    wrong_offset = packet(8, body)
    console = ScriptedConsole(
        [first, first, wrong_offset, chunk, chunk, end, end])
    info, rows = grab_kept_reliable(
        console.addr[0], timeout=3, console=console, min_seq=6)
    require(console.commands == ["sr"], "wrong command")
    require(console.acks == [packet(TAG_HDR, b"")]*2 +
            [packet(0, b"")]*2 + [packet(TAG_END, b"")]*2,
            "missing or extra ACK")
    require(info["seq"] == 7 and info["x0"] == 0x0123456789ABCDEF,
            "capture metadata changed")
    require(len(rows) == 4 and rows[0] == bytes((0x11, 0x22, 0x33))*6,
            "decoded pixel rows changed")

    rejected(lambda: parse_kept_header(header(magic=0)), "magic")
    rejected(lambda: parse_kept_header(header(width=0)), "dimensions")
    rejected(lambda: parse_kept_header(header(width=6, runs=25)), "dimensions")
    rejected(lambda: parse_kept_header(header()[:-1]), "length")
    rejected(lambda: decode_kept_runs(struct.pack("<II", 7, 0), 6, 1),
             "crosses a row")
    rejected(lambda: decode_kept_runs(struct.pack("<II", 0, 0), 6, 1),
             "zero pixels")

    stale = ScriptedConsole([first])
    rejected(lambda: grab_kept_reliable(
        stale.addr[0], timeout=2, console=stale, min_seq=7), "stale")
    require(stale.acks == [], "stale header was acknowledged")

    wrong_x0 = ScriptedConsole([first])
    rejected(lambda: grab_kept_reliable(
        wrong_x0.addr[0], timeout=2, console=wrong_x0,
        expected_x0=0), "x0")
    require(wrong_x0.acks == [], "mismatched x0 header was acknowledged")

    refused = ScriptedConsole(
        [b"pm", b"f> sr\r\n? unknown command\r\n", b"pmf> "])
    rejected(lambda: grab_kept_reliable(
        refused.addr[0], timeout=2, console=refused), "unknown command")
    require(refused.acks == [], "text refusal was acknowledged as binary")

    corrupt = ScriptedConsole(
        [first, chunk, packet(TAG_END, struct.pack("<III", 4, 0, 1))])
    rejected(lambda: grab_kept_reliable(
        corrupt.addr[0], timeout=2, console=corrupt), "CRC mismatch")
    require(corrupt.acks == [packet(TAG_HDR, b""), packet(0, b"")],
            "bad CRC end marker was acknowledged")
    print("pmfshot_kept_check: PASS - metadata, ACKs, duplicates, bounds, stale and CRC")


if __name__ == "__main__":
    main()
