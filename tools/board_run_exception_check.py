#!/usr/bin/env python3
"""Desk-only control-flow proof for board_run exception and trace handling."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import pathlib
import socket
import sys
import tempfile
import zlib


HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "board_run"
sys.path.insert(0, str(HERE))


def load_tool():
    spec = importlib.util.spec_from_file_location("anvil_board_run_exception", HERE / "board_run.py")
    if spec is None or spec.loader is None:
        raise SystemExit("board_run_exception_check: cannot load board_run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def require(ok: bool, text: str) -> None:
    if not ok:
        raise SystemExit("board_run_exception_check: FAIL - " + text)


def args_for(payload: pathlib.Path, out: pathlib.Path, trace: str | None):
    return argparse.Namespace(
        payload=str(payload), console_ip="192.0.2.10", console_port=5555,
        board_ip=None, port=5001, addr=None, out=str(out), name="proof",
        tier=None, deadman=15, trace=trace, timeout=1.0, shot_timeout=1.0,
        settle=0.01, twin=False, no_shot=False, expect_x0="0",
    )


class ScriptSocket:
    def __init__(self, packets, peer):
        self.packets = list(packets)
        self.peer = peer

    def recvfrom(self, _size):
        if self.packets:
            item = self.packets.pop(0)
            if isinstance(item, tuple):
                return item
            return item, self.peer
        raise socket.timeout()


def exception_fragments(tool):
    marker = (tool.FATAL_MARKER + "\r\n").encode()
    advice = b"   check the matching build's symbols before restarting the board.\r\n"
    head = b"   EL=0000000000000001 slot=0000000000000002 ESR=0000000000000003\r\n"
    tail = b"   PC=0000000000000004 FAR=0000000000000005 SP=0000000000000006\r\n"
    return marker, advice, head, tail


def console_drain_checks(tool) -> int:
    peer = ("192.0.2.10", 5555)
    marker, advice, head, tail = exception_fragments(tool)
    foreign = (b"FOREIGN", ("192.0.2.99", 5555))
    console = object.__new__(tool.NetConsole)
    console.addr = peer
    console.sock = ScriptSocket([marker, foreign, advice, head, tail, b"pm", b"f>\r\n"], peer)
    console.transcript = []
    console.accepted_datagrams = []
    initial = console.read_until([tool.FATAL_MARKER], 0.1)
    evidence, boundary = console.collect_exception(initial, quiet=0.002, cap=0.1)
    fields = tool.parse_fatal_exception(evidence)
    require(boundary == "prompt+quiet", f"fragmented prompt boundary={boundary}")
    require(fields == {
        "el": "0000000000000001", "slot": "0000000000000002",
        "esr": "0000000000000003", "pc": "0000000000000004",
        "far": "0000000000000005", "sp": "0000000000000006",
    }, f"fragmented fields={fields!r}")
    require(console.accepted_datagrams == [marker, advice, head, tail, b"pm", b"f>\r\n"],
            "accepted-peer datagram boundaries/bytes were not preserved")

    console = object.__new__(tool.NetConsole)
    console.addr = peer
    console.sock = ScriptSocket([marker, advice + head + tail], peer)
    console.transcript = []
    console.accepted_datagrams = []
    initial = console.read_until([tool.FATAL_MARKER], 0.1)
    evidence, boundary = console.collect_exception(initial, quiet=0.002, cap=0.1)
    require(boundary == "complete-record parked quiet", f"no-prompt boundary={boundary}")
    require(tool.parse_fatal_exception(evidence)["far"] == "0000000000000005",
            "coalesced no-prompt fatal record was incomplete")
    console = object.__new__(tool.NetConsole)
    console.addr = peer
    console.sock = ScriptSocket([marker, advice + head + tail], peer)
    console.transcript = []
    console.accepted_datagrams = []
    initial = console.read_until([tool.FATAL_MARKER], 0.1)
    _evidence, boundary = console.collect_exception(
        initial, quiet=0.002, cap=0.1, reset_wait=0.005)
    require(boundary == "deadman-window quiet (reset unobserved)",
            f"deadman quiet boundary={boundary}")
    coalesced = (marker + advice + head + tail + b"pmf>\r\n").decode()
    console = object.__new__(tool.NetConsole)
    console.addr = peer
    console.sock = ScriptSocket([], peer)
    console.transcript = []
    console.accepted_datagrams = []
    _evidence, boundary = console.collect_exception(coalesced, quiet=0.002, cap=0.1)
    require(boundary == "prompt+quiet", f"initial-coalesced prompt boundary={boundary}")
    try:
        tool.parse_fatal_exception((marker + head).decode())
    except tool.StreamError:
        pass
    else:
        require(False, "incomplete fatal record was accepted")
    complete_text = (marker + advice + head + tail).decode()
    for name, near_miss in (
        ("marker prefix", "X" + complete_text),
        ("marker suffix", complete_text.replace(tool.FATAL_MARKER, tool.FATAL_MARKER + " extra")),
        ("head suffix", complete_text.replace("ESR=0000000000000003", "ESR=0000000000000003 extra")),
        ("tail prefix", complete_text.replace("   PC=", "X   PC=")),
    ):
        try:
            tool.parse_fatal_exception(near_miss)
        except tool.StreamError:
            pass
        else:
            require(False, f"{name} near-miss fatal record was accepted")
    return 12


def readback_reply(address, data, *, lose_line=None, flip=None,
                   header_address=None, stopped=False):
    """The monitor's `readback` reply, as Anvil/Core/readback.pbi prints it."""
    sent = bytearray(data)
    lines = [base64.b64encode(bytes(sent[i:i + 48])).decode()
             for i in range(0, len(sent), 48)]
    crc = zlib.crc32(bytes(data)) & 0xFFFFFFFF
    if flip is not None:
        sent[flip] ^= 1
        lines = [base64.b64encode(bytes(sent[i:i + 48])).decode()
                 for i in range(0, len(sent), 48)]
    if lose_line is not None:
        del lines[lose_line]
    head = header_address if header_address is not None else address
    out = [f"readback {address:X} {len(data):X}",
           f"readback {head:08X} {len(data)} bytes base64", *lines]
    if stopped:
        out.append(f"readback stopped after 48 of {len(data)} bytes crc32 {crc:08X}")
    else:
        out.append(f"readback end {len(data)} bytes crc32 {crc:08X}")
    return "\r\n".join(out) + "\r\npmf> "


def dump_checks(tool) -> int:
    """The trace reader refuses every way a readback can arrive wrong.

    This used to grade the hex-dump parser; the trace is read with
    `readback` now, through tools/anvil_readback.py, and these are the
    same questions asked of that reader."""
    import anvil_readback
    start = 0x005E7E78
    data = bytes(range(160))
    require(anvil_readback.parse_readback(readback_reply(start, data), start, 160) == data,
            "valid bounded readback")
    bad = (
        readback_reply(start, data, lose_line=1),
        readback_reply(start, data, flip=100),
        readback_reply(start, data, header_address=start + 16),
        readback_reply(start, data, stopped=True),
        readback_reply(start, data[:144]),
        readback_reply(start, data).replace("readback end 160", "readback end 159"),
    )
    for index, text in enumerate(bad):
        try:
            anvil_readback.parse_readback(text, start, 160)
        except anvil_readback.ReadbackError:
            pass
        else:
            require(False, f"malformed bounded readback {index} was accepted")
    return 7


class FakeConsole:
    instances = []
    mode = "exception"
    payload_bytes = 0
    payload_digest = ""
    return_x0 = 0

    def __init__(self, ip, port):
        self.name = f"{ip}:{port}"
        self.transcript = []
        self.accepted_datagrams = []
        self.sent = []
        self.listen_read = False
        self.shot_read = False
        self.pending = []
        self.__class__.instances.append(self)

    def at_prompt(self):
        return True

    def command(self, line, _seconds=8.0):
        self.sent.append(line)
        if line.startswith("deadman "):
            seconds = int(line.split()[1])
            return (f"{line}\nThe deadman watchdog is armed for {seconds} seconds.\n"
                    "  It covers the NEXT payload only. It is armed immediately before the\n"
                    "  jump and stopped immediately after.\npmf>\n")
        if line == "version":
            return "version\npmf>\n"
        if line == "map":
            return "stage a file at 00500000\nthis image 00200000 to 00400000\npm>\n"
        if line == "shot status":
            return (FIXTURES / "shot_status.txt").read_text(encoding="ascii")
        if line.startswith(("memory ", "readback ")):
            raise AssertionError("a trace is read with send()/recv_some(), "
                                 "not command()")
        return line + "\npmf>\n"

    def settle(self, quiet=0.6, cap=8.0):
        return ""

    def send(self, line):
        self.sent.append(line)
        self.last = line
        if line.startswith("readback "):
            if self.mode != "normal":
                raise AssertionError("trace command sent after exception")
            _word, address_text, count_text = line.split()
            address = int(address_text, 16)
            count = int(count_text, 16)
            self.pending.append(readback_reply(
                address, bytes(i & 0xFF for i in range(count))))

    def recv_some(self):
        return self.pending.pop(0) if self.pending else ""

    def read_until_or_prompt(self, line, needles, timeout, seen=""):
        """The REAL algorithm, driven over this fake's scripted replies.

        Borrowed rather than reimplemented: a fake that had its own copy of
        the prompt-versus-needle decision would prove that the copy works.
        """
        return REAL_READ_UNTIL_OR_PROMPT(self, line, needles, timeout, seen)

    def read_until(self, _needles, _timeout):
        if self.last.startswith("net recv"):
            if not self.listen_read:
                self.listen_read = True
                return "for ONE connection\n"
            return (f"Received {self.payload_bytes} bytes from 192.0.2.20 to 00500000 in 1 ms.\n"
                    f"sha256 {self.payload_digest}\n")
        if self.last.startswith("boot mem"):
            if self.mode == "normal":
                return ("The payload returned to the monitor. Its x0 register held "
                        f"{self.return_x0:016X}\n")
            marker, _advice, _head, _tail = exception_fragments(TOOL)
            self.accepted_datagrams.append(marker)
            return marker.decode()
        if self.last == "shot":
            if not self.shot_read:
                self.shot_read = True
                return (FIXTURES / "shot_return.txt").read_text(encoding="ascii")
            return "pmf>\n"
        return "pmf>\n"

    def collect_exception(self, initial, quiet=2.0, cap=30.0, reset_wait=0.0):
        _marker, advice, head, tail = exception_fragments(TOOL)
        fragments = ([advice, b"pmf>\r\n"] if self.mode == "incomplete" else
                     [advice, head, tail, b"pmf>\r\n"])
        self.accepted_datagrams.extend(fragments)
        text = initial + b"".join(fragments).decode()
        self.transcript.append(text)
        return text, "prompt+quiet"

    def close(self):
        pass


def run_checks(tool) -> int:
    old_console, old_stream = tool.NetConsole, tool.stream_file
    with tempfile.TemporaryDirectory(prefix="board-run-exception-check-") as raw:
        root = pathlib.Path(raw)
        payload = root / "payload.pmf"
        payload.write_bytes(b"P")
        FakeConsole.payload_bytes = 1
        FakeConsole.payload_digest = hashlib.sha256(b"P").hexdigest()
        tool.NetConsole = FakeConsole
        tool.stream_file = lambda *_args, **_kwargs: 0.001
        try:
            invalid_out = root / "invalid"
            FakeConsole.instances.clear()
            rc = tool.run(args_for(payload, invalid_out, "5E7E78:0"))
            require(rc == 2 and not FakeConsole.instances and not invalid_out.exists(),
                    "invalid trace performed console/output work")

            for index, value in enumerate(("-1", "18446744073709551616", "bad", "0x")):
                invalid_x0_out = root / f"invalid-x0-{index}"
                invalid_args = args_for(payload, invalid_x0_out, None)
                invalid_args.expect_x0 = value
                FakeConsole.instances.clear()
                rc = tool.run(invalid_args)
                require(rc == 2 and not FakeConsole.instances and not invalid_x0_out.exists(),
                        f"invalid expected x0 {value!r} performed console/output work")

            exception_out = root / "exception"
            FakeConsole.mode = "exception"
            FakeConsole.instances.clear()
            rc = tool.run(args_for(payload, exception_out, "5E7E78:960"))
            console = FakeConsole.instances[-1]
            require(rc == 1, "exception run did not fail")
            boot_at = next(i for i, line in enumerate(console.sent) if line.startswith("boot mem"))
            require(console.sent[boot_at + 1:] == [], "runner transmitted after fatal marker")
            record = json.loads((exception_out / "proof.json").read_text(encoding="utf-8"))
            require(record["exception"]["complete"] is True, "complete exception not recorded")
            require(record["exception"]["fields"]["pc"] == "0000000000000004",
                    "structured exception PC missing")
            require(len(record["exception"]["datagrams"]) == 5,
                    "raw exception datagram boundaries missing")
            require(not (exception_out / "proof.png").exists()
                    and not (exception_out / "proof.shot.txt").exists()
                    and not (exception_out / "proof.trace.bin").exists(),
                    "post-exception trace/shot/png artifact exists")

            incomplete_out = root / "incomplete"
            FakeConsole.mode = "incomplete"
            FakeConsole.instances.clear()
            rc = tool.run(args_for(payload, incomplete_out, "5E7E78:960"))
            console = FakeConsole.instances[-1]
            boot_at = next(i for i, line in enumerate(console.sent) if line.startswith("boot mem"))
            record = json.loads((incomplete_out / "proof.json").read_text(encoding="utf-8"))
            require(rc == 1 and record["exception"]["complete"] is False,
                    "incomplete marker run was not a terminal structured failure")
            require(console.sent[boot_at + 1:] == [], "incomplete marker transmitted after fatal")
            require(not (incomplete_out / "proof.png").exists()
                    and not (incomplete_out / "proof.shot.txt").exists()
                    and not (incomplete_out / "proof.trace.bin").exists(),
                    "incomplete marker produced post-exception artifacts")

            normal_out = root / "normal"
            FakeConsole.mode = "normal"
            FakeConsole.return_x0 = 0
            FakeConsole.instances.clear()
            rc = tool.run(args_for(payload, normal_out, None))
            require(rc == 0 and (normal_out / "proof.png").is_file(),
                    "normal returned run changed")

            expected_out = root / "expected-nonzero"
            FakeConsole.return_x0 = 42
            expected_args = args_for(payload, expected_out, None)
            expected_args.expect_x0 = "0x2a"
            FakeConsole.instances.clear()
            rc = tool.run(expected_args)
            record = json.loads((expected_out / "proof.json").read_text(encoding="utf-8"))
            require(rc == 0 and record["x0"] == "000000000000002A"
                    and record["expected_x0"] == "000000000000002A"
                    and (expected_out / "proof.png").is_file(),
                    "expected nonzero x0 was not accepted and persisted")

            mismatch_out = root / "mismatch"
            mismatch_args = args_for(payload, mismatch_out, "5E7E78:16")
            mismatch_args.expect_x0 = "0"
            FakeConsole.instances.clear()
            rc = tool.run(mismatch_args)
            record = json.loads((mismatch_out / "proof.json").read_text(encoding="utf-8"))
            require(rc == 1 and record["x0"] == "000000000000002A"
                    and record["expected_x0"] == "0000000000000000"
                    and (mismatch_out / "proof.png").is_file()
                    and (mismatch_out / "proof.trace.bin").read_bytes() == bytes(range(16)),
                    "x0 mismatch did not fail after preserving trace/screenshot evidence")
        finally:
            tool.NetConsole, tool.stream_file = old_console, old_stream
    return 18


def main() -> int:
    global TOOL, REAL_READ_UNTIL_OR_PROMPT
    TOOL = load_tool()
    # Held before run_checks swaps NetConsole for the fake, so the fake can
    # drive the real decision rather than a copy of it.
    REAL_READ_UNTIL_OR_PROMPT = TOOL.NetConsole.read_until_or_prompt
    checks = 0
    require(TOOL.parse_trace_spec("5E7E78:960") == (0x5E7E78, 960),
            "valid trace spec")
    for value in ("", "XYZ", "5E7E78:", "5E7E78:0", "5E7E78:4097",
                  "FFFFFFFFFFFFFFFF:2"):
        try:
            TOOL.parse_trace_spec(value)
        except ValueError:
            pass
        else:
            require(False, f"invalid trace spec accepted: {value!r}")
    checks += 7
    for value, expected in (("0", 0), ("42", 42), ("0x2a", 42),
                            ("0XFFFFFFFFFFFFFFFF", 0xFFFFFFFFFFFFFFFF)):
        require(TOOL.parse_expected_x0(value) == expected,
                f"expected x0 parser rejected {value!r}")
    checks += 4
    checks += console_drain_checks(TOOL)
    checks += dump_checks(TOOL)
    checks += run_checks(TOOL)
    print(f"board_run_exception_check: PASS - {checks} causal assertions; no board")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
