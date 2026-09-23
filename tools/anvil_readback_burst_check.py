#!/usr/bin/env python3
"""Gate: a readback burst that nobody reads until it has all arrived is not lost.

    python tools/anvil_readback_burst_check.py

THE DEFECT, measured on build 151 on 2026-09-16: `read_range` with 1 MiB
chunks through the UDP console lost 345,600 of 1,048,576 bytes to datagrams
the host's socket dropped - its default receive buffer overflowed during the
board's burst. tools/anvil_readback.py now raises the console socket's
receive buffer once and caps the chunk so a whole reply fits in half of what
the operating system granted.

THE WORST CASE IS MODELLED EXACTLY, on loopback, with real sockets: when the
reader sends `readback`, a second socket sends the monitor's WHOLE reply for
that chunk - header, 66-byte base64 lines, verdict, prompt - one line per
datagram, before a single datagram is read. Nothing is dropped on loopback
except by the receiving socket's buffer, which is the thing under test.

  control   the old configuration: 1 MiB chunk, the socket's default buffer.
            It MUST lose bytes (Error 38), or this check proves nothing on
            this machine and says so.
  fixed     read_range as shipped: 2,382,400 bytes (a Kitten waveform) must
            come back complete and crc32-verified, with no retry.
"""
from __future__ import annotations

import base64
import socket
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anvil_readback as rb      # noqa: E402


class BurstConsole:
    """The three methods read_range needs, over a real loopback UDP socket."""

    def __init__(self, memory: bytes, base: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.05)
        self.board = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.memory, self.base = memory, base

    def settle(self, quiet=0.05, cap=8):
        end = time.monotonic() + cap
        last = time.monotonic()
        while time.monotonic() < end and time.monotonic() - last < quiet:
            if self.recv_some():
                last = time.monotonic()

    def send(self, line):
        _word, addr, size = line.split()
        addr, size = int(addr, 16), int(size, 16)
        blob = self.memory[addr - self.base:addr - self.base + size]
        text = base64.b64encode(blob).decode()
        to = self.sock.getsockname()
        self.board.sendto(f"{line}\r\nreadback {addr:08X} {size} bytes base64\r\n".encode(), to)
        for i in range(0, len(text), 64):
            self.board.sendto((text[i:i + 64] + "\r\n").encode(), to)
        self.board.sendto(f"readback end {size} bytes crc32 {zlib.crc32(blob) & 0xFFFFFFFF:08X}\r\npmf> ".encode(), to)

    def recv_some(self):
        try:
            data, _peer = self.sock.recvfrom(65535)
        except (socket.timeout, TimeoutError):
            return ""
        return data.decode()

    def close(self):
        self.sock.close()
        self.board.close()


def main() -> int:
    base = 0x57000000
    memory = bytes((i * 2654435761) & 0xFF for i in range(2382400))
    failed = 0

    control = BurstConsole(memory, base)
    control.readback_receive_buffer = None      # skip the fix: the old reader
    try:
        rb.parse_readback(rb.readback_reply(control, base, 1 << 20, seconds=10), base, 1 << 20)
        print("FAIL control: a 1 MiB burst into the default receive buffer "
              f"({control.sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)} bytes) "
              "lost nothing on this machine, so this check cannot show the fix matters here.")
        failed += 1
    except rb.ReadbackError as error:
        print(f"PASS control: the old configuration loses the burst - {str(error)[:90]}...")
    finally:
        control.close()

    fixed = BurstConsole(memory, base)
    try:
        data, stats = rb.read_range(fixed, base, len(memory), progress=None)
        if data != memory or stats["retries"]:
            print(f"FAIL fixed: {len(data)} bytes, {stats['retries']} retries")
            failed += 1
        else:
            print(f"PASS fixed: {len(data)} bytes in {stats['chunks']} chunks of "
                  f"{stats['chunk_bytes']}, receive buffer {stats['receive_buffer']}, "
                  f"no retry, {stats['seconds']:.2f} s")
    except rb.ReadbackError as error:
        print(f"FAIL fixed: {error}")
        failed += 1
    finally:
        fixed.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
