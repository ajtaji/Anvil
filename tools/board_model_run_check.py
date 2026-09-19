#!/usr/bin/env python3
"""Desk check for tools/board_model_run.py - a scripted board, no silicon.

    python tools/board_model_run_check.py

WHAT IT PROVES, and what it does not. The board run itself is proven on the
board (docs/BOARD_RUN.md, "One command for a model run"). This proves the
parts a board run cannot exercise on demand, against the REAL NetConsole,
the REAL readback reader and the REAL lease file format:

  - a manifest that does not match its files is refused before anything is
    sent, and says why in a sentence
  - the lease is taken from FREE, confirmed, and released with a row - on a
    good run, on a refused boot, and when the board never answers
  - a lease held by somebody else is waited for, and a wait past its bound
    ends in a sentence with nothing sent
  - a lease that collides with another is withdrawn, and taken once the
    other is released
  - the first run uploads every asset; the second finds them RESIDENT by the
    board's digest and uploads nothing
  - the WAV is the stated conversion, clamped samples counted
  - the WAV line is printed before the compare command runs

The scripted board is a socket that answers like the monitor: it echoes what
it is typed, prints its reply and its prompt, keeps a memory of what was
uploaded, hashes it for `sha256sum`, and streams `readback` in the monitor's
base64 format with its crc32.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import struct
import sys
import tempfile
import threading
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board_model_run as tool      # noqa: E402

LEASE_TEMPLATE = """---
title: BOARD-SHARE - test
---

# Raspberry Pi 4 shared-board lease

> [!important] Live holder
> **FREE** - released 12:00 by a previous lane.

## Lease protocol

1. Read this file.

## Transfer ledger

| Time (CDT) | From | To | Board state | Mutating board work active |
|---|---|---|---|---|
| 2026-09-16 11:00 | somebody | FREE | build 151 at `pmf>` | none |

## Notes after the ledger

Text that must survive.
"""

WAVE_ADDR = 0x57000000
SAMPLES = [0.0, 0.5, -0.5, 1.25, -2.0, 0.999, -0.00001, 0.25] * 50


class ScriptedBoard:
    """The monitor, at the socket NetConsole reads and writes."""

    def __init__(self, refuse_boot: bool = False):
        self.addr = ("192.0.2.1", 5555)
        self.memory: dict[int, bytes] = {}
        self.cache = False
        self.out: list[bytes] = []
        self.lines: list[str] = []
        self.pending_recv: int | None = None
        self.refuse_boot = refuse_boot
        self.deadman = 0
        self.run = 3
        self.lock = threading.Lock()

    # socket surface
    def settimeout(self, _s): pass
    def bind(self, _a): pass
    def close(self): pass

    def sendto(self, data, _addr):
        if data == b"":
            return 0
        line = data.decode().rstrip("\r\n")
        self.lines.append(line)
        self.answer(line)
        return len(data)

    def recvfrom(self, _n):
        with self.lock:
            if self.out:
                return self.out.pop(0), self.addr
        time.sleep(0.005)
        raise TimeoutError()

    def say(self, text: str) -> None:
        raw = text.encode()
        with self.lock:
            for i in range(0, len(raw), 512):
                self.out.append(raw[i:i + 512])

    # memory
    def read(self, addr: int, size: int) -> bytes:
        for base, blob in self.memory.items():
            if base <= addr and addr + size <= base + len(blob):
                return blob[addr - base:addr - base + size]
        return bytes(size)

    def receive(self, data: bytes) -> None:
        addr = self.pending_recv
        self.memory[addr] = data
        self.say(f"Received {len(data)} bytes from 192.0.2.2 to {addr:08X} in 3 ms.\r\n"
                 f"  That is 9000 KB/s.\r\n  sha256 {hashlib.sha256(data).hexdigest()}\r\npmf> ")

    def answer(self, line: str) -> None:
        echo = f"{line}\r\n"
        if line == "":
            self.say("\r\npmf> ")
        elif line == "version":
            self.say(echo + "build 151 date 20260916 time 102626\r\npmf> ")
        elif line == "map":
            self.say(echo + "  stage a file at 00500000\r\n  this image 00200000 to 004B144B\r\npmf> ")
        elif line == "coretest status":
            self.say(echo + "coretest started=0 stopped=0 runs=0 nonce=26 error=0 core=0\r\n"
                            "  leases: secondary=0 gic=0 watchdog=0\r\npmf> ")
        elif line == "cache":
            self.say(echo + f"The D-cache and MMU are {'ON' if self.cache else 'OFF'}.\r\npmf> ")
        elif line in ("cache on", "cache off"):
            self.cache = line == "cache on"
            self.say(echo + "done.\r\npmf> ")
        elif line.startswith("sha256sum "):
            _w, a, n = line.split()
            a, n = int(a, 16), int(n, 16)
            digest = hashlib.sha256(self.read(a, n)).hexdigest()
            self.say(echo + f"sha256sum over {n} bytes, {a:08X} .. {a + n - 1:08X} ...\r\n"
                            f"The sha256sum is {digest}\r\n  sha256sum of the same bytes ...\r\npmf> ")
        elif line.startswith("net recv "):
            self.pending_recv = int(line.split()[3], 16)
            self.say(echo + "Listening on port 5001 on every usable addressed interface for ONE connection:\r\n")
        elif line == "deadman off":
            self.deadman = 0
            self.say(echo + "The deadman watchdog is off. A payload that hangs will now hang the\r\n"
                            "board with it.\r\npmf> ")
        elif line.startswith("deadman "):
            self.deadman = int(line.split()[1])
            self.say(echo + f"The deadman watchdog is armed for {self.deadman} seconds.\r\npmf> ")
        elif line == "last run":
            self.say(echo + f"LASTRUN {self.run:08X} 02 00 0F {0:016X} {0x3000000:016X} "
                            f"{4000:016X} {0:016X} {0:016X} {0:016X}\r\npmf> ")
        elif line.startswith("boot mem "):
            if self.refuse_boot:
                self.say(echo + "!! the resident secondary cores own this monitor until restart.\r\npmf> ")
                return
            self.say(echo + "Starting the payload at 03000000.\r\n")
            def payload():
                time.sleep(0.2)
                self.memory[WAVE_ADDR] = struct.pack("<%df" % len(SAMPLES), *SAMPLES)
                self.run += 1
                self.say("The payload returned to the monitor. Its x0 register held "
                         f"{0:016X},\r\nwhich is whatever it chose to return.\r\npmf> ")
            threading.Thread(target=payload, daemon=True).start()
        elif line.startswith("readback "):
            _w, a, n = line.split()
            a, n = int(a, 16), int(n, 16)
            blob = self.read(a, n)
            text = base64.b64encode(blob).decode()
            rows = [text[i:i + 64] for i in range(0, len(text), 64)]
            self.say(echo + f"readback {a:08X} {n} bytes base64\r\n" + "".join(r + "\r\n" for r in rows) +
                     f"readback end {n} bytes crc32 {zlib.crc32(blob) & 0xFFFFFFFF:08X}\r\npmf> ")
        else:
            self.say(echo + "? the monitor does not know that word.\r\npmf> ")


def console_for(board: ScriptedBoard):
    def factory(ip, port):
        console = tool.br.NetConsole.__new__(tool.br.NetConsole)
        console.addr = board.addr
        console.name = f"{ip}:{port}"
        console.sock = board
        console.transcript = []
        console.accepted_datagrams = []
        console.last_sent = time.monotonic()
        return console
    return factory


class Failed(Exception):
    pass


def require(ok: bool, text: str) -> None:
    if not ok:
        raise Failed(text)


def make_fixture(root: Path, compare: bool = True) -> tuple[Path, Path, dict]:
    files = root / "files"
    files.mkdir()
    weights = bytes(range(256)) * 400
    noise = b"noise-" * 3000
    pmf = b"PMF1" + bytes(5000)
    (files / "w.pmw").write_bytes(weights)
    (files / "n.f32").write_bytes(noise)
    (files / "p.pmf").write_bytes(pmf)
    (files / "compare.py").write_text(
        "import sys, pathlib\n"
        "assert pathlib.Path(sys.argv[1]).is_file()\n"
        "print('COMPARE RAN', sys.argv[1])\n", encoding="utf-8")
    manifest = {
        "format": tool.FORMAT, "name": "fixture", "base": "files", "out": "runs",
        "payload": {"file": "p.pmf", "sha256": hashlib.sha256(pmf).hexdigest(),
                    "stage": "0x03000000", "expect_x0": "0", "timeout_seconds": 5},
        "deadman_seconds": 15,
        "assets": [
            {"name": "weights", "file": "w.pmw", "address": "0x40000000",
             "sha256": hashlib.sha256(weights).hexdigest()},
            {"name": "noise", "file": "n.f32", "address": "$54000000",
             "sha256": hashlib.sha256(noise).hexdigest()}],
        "results": [
            {"name": "wave", "address": "0x57000000", "bytes": len(SAMPLES) * 4, "board_sha256": True},
            {"name": "trace", "address": "0x57E00000", "bytes": 256}],
        "post": {"wav": [{"from": "wave", "rate": 24000, "file": "fixture.wav"}]},
    }
    if compare:
        manifest["post"]["compare"] = ["{python}", "compare.py", "{wav.wave}"]
    path = root / "fixture.run.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    lease = root / "BOARD-SHARE.md"
    lease.write_text(LEASE_TEMPLATE, encoding="utf-8", newline="\r\n")
    return path, lease, manifest


def options(manifest: Path, lease: Path | None, **extra) -> argparse.Namespace:
    base = dict(manifest=str(manifest), console_ip="192.0.2.1", console_port=5555,
                board_ip=None, port=5001, base=None, out=None,
                lease_file=str(lease) if lease else None, lane="Desk check lane",
                no_lease=lease is None, lease_wait=30.0, ask_seconds=1.0)
    base.update(extra)
    return argparse.Namespace(**base)


def run_tool(opts, board) -> tuple[int, str]:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = tool.run(opts, console_factory=console_for(board))
    return code, captured.getvalue()


def expected_pcm() -> tuple[bytes, int]:
    clamped = 0
    out = bytearray()
    for v in struct.unpack("<%df" % len(SAMPLES), struct.pack("<%df" % len(SAMPLES), *SAMPLES)):
        if v > 1.0:
            v, clamped = 1.0, clamped + 1
        elif v < -1.0:
            v, clamped = -1.0, clamped + 1
        s = v * 32767.0
        out += struct.pack("<h", int(s + 0.5) if s >= 0 else int(s - 0.5))
    return bytes(out), clamped


def case_good_runs(root: Path) -> None:
    manifest, lease, _m = make_fixture(root)
    board = ScriptedBoard()
    real_stream = tool.br.stream_file
    tool.br.stream_file = lambda ip, port, data, connect_timeout=20.0: (board.receive(data), 0.01)[1]
    try:
        code, text = run_tool(options(manifest, lease), board)
        require(code == 0, f"run 1 exited {code}:\n{text}")
        require(text.count("uploaded and verified") == 2, f"run 1 did not upload both assets:\n{text}")
        wav_at = text.find("WAV ready: ")
        require(wav_at >= 0 and text.find("] compare: ") > wav_at,
                f"the WAV line did not come before the compare output:\n{text}")
        require(sum(1 for l in board.lines if l.startswith("net recv")) == 3, "run 1 did not send three uploads")
        require(board.deadman == 0 and not board.cache, "run 1 left the deadman armed or the cache on")
        run1 = sorted((root / "files" / "runs").iterdir())
        require(len(run1) == 1, "run 1 did not make exactly one run folder")
        record = json.loads((run1[0] / "fixture.json").read_text(encoding="utf-8"))
        for key in ("lease_wait_seconds", "run_seconds", "readback_seconds",
                    "returned_to_wav_line_seconds", "total_seconds", "payload_upload_seconds"):
            require(key in record["timings"], f"the run record has no timing {key}")
        require("finished" in record and record["failures"] == [], "run 1's record is not a finished success")
        require(record.get("compare", {}).get("exit") == 0, "the compare command did not run and pass")
        pcm, clamped = expected_pcm()
        wav = (run1[0] / "fixture.wav").read_bytes()
        require(wav[44:] == pcm and wav[:4] == b"RIFF" and struct.unpack("<I", wav[24:28])[0] == 24000,
                "the WAV is not the stated conversion")
        require(record["wavs"][0]["clamped"] == clamped == 100, "clamped samples were not counted")

        time.sleep(1.1)       # the run folder is named by the second
        board.lines.clear()
        code, text = run_tool(options(manifest, lease), board)
        require(code == 0, f"run 2 exited {code}:\n{text}")
        require(text.count(": resident - ") == 2 and "uploaded and verified" not in text,
                f"run 2 did not find both assets resident:\n{text}")
        require(sum(1 for l in board.lines if l.startswith("net recv")) == 1,
                "run 2 sent more than the payload")
        share = lease.read_bytes().decode("utf-8")
        rows = tool.BoardLease.rows(share.replace("\r\n", "\n"))
        require(len(rows) == 5, f"expected 1 + 2 takes + 2 releases rows, found {len(rows)}")
        require(tool.BoardLease.holder(share.replace("\r\n", "\n")) is None, "the lease was not released")
        require("> **FREE** - released" in share and "Text that must survive." in share,
                "the callout was not released or the rest of the file was damaged")
        require("\r\n" in share and "\n" not in share.replace("\r\n", ""), "the file's line endings changed")
    finally:
        tool.br.stream_file = real_stream


def case_refusals(root: Path) -> None:
    manifest, lease, raw = make_fixture(root)
    board = ScriptedBoard()
    raw["assets"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    code, text = run_tool(options(manifest, lease), board)
    require(code == 2 and "stale" in text and "Nothing was sent" in text and not board.lines,
            f"a stale asset digest was not refused before sending:\n{text}")
    raw["assets"][0]["sha256"] = hashlib.sha256(bytes(range(256)) * 400).hexdigest()
    raw["resluts"] = []
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    code, text = run_tool(options(manifest, lease), board)
    require(code == 2 and "resluts" in text and not board.lines, f"a misspelt key was not refused:\n{text}")
    del raw["resluts"]
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    require(LEASE_TEMPLATE.count("|") == lease.read_text(encoding="utf-8").count("|"),
            "a refused manifest touched the lease file")

    # the boot is refused: failure, deadman off, lease released
    board = ScriptedBoard(refuse_boot=True)
    real_stream = tool.br.stream_file
    tool.br.stream_file = lambda ip, port, data, connect_timeout=20.0: (board.receive(data), 0.01)[1]
    try:
        code, text = run_tool(options(manifest, lease), board)
    finally:
        tool.br.stream_file = real_stream
    require(code == 1 and "REFUSED TO ENTER" in text and "resident secondary cores" in text,
            f"a refused boot was not reported:\n{text}")
    require(board.deadman == 0, "the deadman was left armed after a refused boot")
    share = lease.read_text(encoding="utf-8").replace("\r\n", "\n")
    require(tool.BoardLease.holder(share) is None and "FAILED: the board REFUSED" in share,
            "a refused boot did not release the lease with a row saying so")


def case_lease_wait_and_collision(root: Path) -> None:
    manifest, lease, _raw = make_fixture(root, compare=False)
    held = LEASE_TEMPLATE.replace(
        "| 2026-09-16 11:00 | somebody | FREE | build 151 at `pmf>` | none |",
        "| 2026-09-16 11:00 | somebody | FREE | build 151 at `pmf>` | none |\n"
        "| 2026-09-16 11:05 | FREE | **Other lane** | build 151 | RAM-only |")
    lease.write_text(held, encoding="utf-8")
    board = ScriptedBoard()
    code, text = run_tool(options(manifest, lease, lease_wait=1.5), board)
    require(code == 2 and "still held by Other lane" in text and not board.lines,
            f"a held lease was not waited for and refused in a sentence:\n{text}")

    # collision: another take lands right after ours; later it is released
    lease.write_text(LEASE_TEMPLATE, encoding="utf-8")
    real_write = tool.BoardLease.write
    state = {"done": False}

    def colliding_write(self, text):
        real_write(self, text)
        if not state["done"] and "taken" in text:
            state["done"] = True
            real_write(self, self.with_row(self.read(),
                       "| 2026-09-16 12:01 | FREE | **Other lane** | build 151 | RAM-only |"))

            def later():
                time.sleep(1.5)
                real_write(self, self.with_row(self.read(),
                           "| 2026-09-16 12:03 | **Other lane** | FREE | build 151 | NONE |"))
            threading.Thread(target=later, daemon=True).start()

    tool.BoardLease.write = colliding_write
    real_stream = tool.br.stream_file
    tool.br.stream_file = lambda ip, port, data, connect_timeout=20.0: (board.receive(data), 0.01)[1]
    try:
        code, text = run_tool(options(manifest, lease), board)
    finally:
        tool.BoardLease.write = real_write
        tool.br.stream_file = real_stream
    share = lease.read_text(encoding="utf-8").replace("\r\n", "\n")
    require(code == 0 and "withdrew its row" in text and "COLLISION, WITHDRAWN" in share,
            f"a collision was not withdrawn and then retried:\n{text}\n{share}")
    require(tool.BoardLease.holder(share) is None, "the lease was not released after the collision run")


def case_no_prompt(root: Path) -> None:
    manifest, lease, _raw = make_fixture(root, compare=False)

    class Dead(ScriptedBoard):
        def answer(self, line):
            return

    board = Dead()
    real_at_prompt = tool.br.NetConsole.at_prompt
    tool.br.NetConsole.at_prompt = lambda self, timeout=30.0: False
    try:
        code, text = run_tool(options(manifest, lease), board)
    finally:
        tool.br.NetConsole.at_prompt = real_at_prompt
    share = lease.read_text(encoding="utf-8").replace("\r\n", "\n")
    require(code == 2 and "no Anvil prompt" in text, f"a silent board was not reported:\n{text}")
    require(tool.BoardLease.holder(share) is None and "NO PROMPT answered" in share,
            "a silent board did not release the lease with a row saying so")


def main() -> int:
    cases = [case_good_runs, case_refusals, case_lease_wait_and_collision, case_no_prompt]
    failed = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as temp:
            try:
                case(Path(temp))
                print(f"PASS {case.__name__}")
            except Failed as error:
                failed += 1
                print(f"FAIL {case.__name__}: {error}")
    print(f"{len(cases) - failed} of {len(cases)} cases passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
