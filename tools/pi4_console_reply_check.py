"""Host-only response attribution, cache-state and readback tests. No board is contacted."""
import base64
from collections import deque
import contextlib
import hashlib
import io
from pathlib import Path
import re
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zlib

import pi4_upload as upload


class ScriptConsole:
    def __init__(self, chunks):
        self.chunks = deque(chunks)
        self.sent = []

    def settle(self):
        return ""

    def send(self, line):
        self.sent.append(line)

    def read_until(self, needles, timeout):
        return self.chunks.popleft() if self.chunks else ""


class StateConsole(ScriptConsole):
    def __init__(self, on=False, refuse_on=False, refuse_off=False, invalid=False):
        super().__init__([])
        self.on, self.refuse_on, self.refuse_off, self.invalid = on, refuse_on, refuse_off, invalid

    def send(self, line):
        super().send(line)
        if line == "cache":
            state = "UNKNOWN" if self.invalid else "ON" if self.on else "OFF"
            self.chunks.append("cache\r\nThe D-cache and MMU are %s - state.\r\npmf> " % state)
        elif line == "cache on":
            if not self.refuse_on:
                self.on = True
            self.chunks.extend([
                "Wi-Fi: reconnect complete.\r\ncache\r\nThe D-cache and MMU are OFF - old reply.\r\npmf> ",
                "cache on\r\nThe cache command finished.\r\npmf> ",
            ])
        elif line == "cache off":
            if not self.refuse_off:
                self.on = False
            self.chunks.append("cache off\r\nThe cache command finished.\r\npmf> ")
        else:
            raise AssertionError("Unexpected command " + line)


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.tick = 0.0
        def clock():
            self.tick += 0.01
            return self.tick
        self.clock = patch.object(upload.time, "monotonic", clock)
        self.clock.start()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.clock.stop()

    def test_stale_prompt_and_status_are_not_new_command(self):
        c = ScriptConsole(["cache\r\nThe D-cache and MMU are OFF.\r\npmf> ", "Wi-Fi: rejoined.\r\ncache on\r\nCaches ON.\r\npmf> "])
        reply = upload.command(c, "cache on")
        self.assertIn("Caches ON", reply)
        self.assertNotIn("are OFF", reply)
        self.assertEqual(c.sent, ["cache on"])

    def test_fragmented_echo_and_prompt(self):
        c = ScriptConsole(["cach", "e on\r", "\r\nCaches ON.\r\npm", "f> "])
        self.assertIn("Caches ON", upload.command(c, "cache on"))

    def test_echo_after_pending_prompt(self):
        c = ScriptConsole(["pmf> cache\r\nThe D-cache and MMU are ON.\r\npmf> "])
        self.assertTrue(upload.cache_enabled(c))

    def test_success_word_does_not_complete_reply(self):
        c = ScriptConsole(["save T.BIN 500000 4\r\nwritten.\r\n", "Writer disarmed.\r\npmf> "])
        self.assertIn("Writer disarmed", upload.command(c, "save T.BIN 500000 4", needles=["written."]))

    def test_missing_echo_refuses_without_retry(self):
        c = ScriptConsole(["The D-cache and MMU are ON.\r\npmf> "])
        with self.assertRaises(upload.ConsoleReplyError):
            upload.command(c, "cache", seconds=0.1)
        self.assertEqual(c.sent, ["cache"])

    def test_missing_prompt_refuses_without_retry(self):
        c = ScriptConsole(["cache\r\nThe D-cache and MMU are ON.\r\n"])
        with self.assertRaises(upload.ConsoleReplyError):
            upload.command(c, "cache", seconds=0.1)
        self.assertEqual(c.sent, ["cache"])

    def test_wrong_command_is_not_an_echo(self):
        c = ScriptConsole(["cache off\r\nThe D-cache and MMU are OFF.\r\npmf> "])
        with self.assertRaises(upload.ConsoleReplyError):
            upload.command(c, "cache", seconds=0.1)

    def test_cache_transition_and_restore_both_read_back(self):
        c = StateConsole()
        state = upload.CacheState(c)
        state.enable()
        self.assertTrue(c.on)
        state.restore()
        self.assertFalse(c.on)
        self.assertEqual(c.sent, ["cache", "cache on", "cache", "cache off", "cache"])
        state.restore()
        self.assertEqual(len(c.sent), 5)

    def test_initially_enabled_left_unchanged(self):
        c = StateConsole(on=True)
        state = upload.CacheState(c)
        state.enable()
        state.restore()
        self.assertEqual(c.sent, ["cache"])
        self.assertTrue(c.on)

    def test_invalid_initial_state_does_not_mutate(self):
        c = StateConsole(invalid=True)
        with self.assertRaises(upload.ConsoleReplyError):
            upload.CacheState(c).enable()
        self.assertEqual(c.sent, ["cache"])

    def test_refused_enable_is_not_a_success(self):
        c = StateConsole(refuse_on=True)
        state = upload.CacheState(c)
        with self.assertRaises(upload.ConsoleReplyError):
            state.enable()
        state.restore()
        self.assertFalse(c.on)

    def test_failure_cleanup_is_once_and_loud(self):
        c = StateConsole(refuse_off=True)
        state = upload.CacheState(c)
        state.enable()
        with self.assertRaises(upload.ConsoleReplyError):
            state.restore()
        state.restore()
        self.assertEqual(c.sent.count("cache off"), 1)

    def test_explicit_keep_cache_does_not_restore(self):
        c = StateConsole()
        state = upload.CacheState(c, keep=True)
        state.enable()
        state.restore()
        self.assertTrue(c.on)
        self.assertNotIn("cache off", c.sent)


class UploadCleanupTests(unittest.TestCase):
    def run_case(self, corrupt=False, already_on=False):
        from pi4_upload_check import FakeAnvil, run_tool
        with tempfile.TemporaryDirectory(prefix="pmf-upload-cleanup-") as temporary:
            image = Path(temporary) / "payload.img"
            image.write_bytes(bytes(range(256)) * 8)
            board = FakeAnvil(cache_on=already_on, stale_cache_reply=True)
            board.start()
            try:
                options = ["--cache", "--verify-timeout", "2"]
                if corrupt:
                    options += ["--corrupt", "--to", "card"]
                code, output = run_tool(board, image, *options)
                self.assertEqual(code, 1 if corrupt else 0, output)
                self.assertEqual(board.cache_on, already_on, output)
                if corrupt:
                    self.assertFalse(any(x.startswith("save ") for x in board.seen))
                if already_on:
                    self.assertNotIn("cache on", board.seen)
                    self.assertNotIn("cache off", board.seen)
                else:
                    self.assertEqual(board.seen.count("cache on"), 1)
                    self.assertEqual(board.seen.count("cache off"), 1)
            finally:
                board.close()

    def test_success_restores_original_state(self):
        self.run_case()

    def test_corrupt_transfer_restores_before_failure_exit(self):
        self.run_case(corrupt=True)

    def test_existing_cache_setting_is_not_owned(self):
        self.run_case(already_on=True)


# =====================================================================
#  READBACK - tools/pi4_upload.py's read_range against a model of the
#  monitor's `readback` output.
# =====================================================================
#  The model is written from Anvil/Core/readback.pbi's header, not from a
#  capture: the echo, `readback <8 hex> <decimal> bytes base64`, 48 bytes
#  of memory to a base64 line, 15 lines to a datagram, `readback end <n>
#  bytes crc32 <8 HEX>`, the prompt. That the monitor really prints this is
#  graded separately and on the emitted code, by tools/a64/a64_wificon_check
#  case L. What is graded HERE is the judge: every way a stream can arrive
#  wrong must be refused in a sentence, and a retry must not accept a
#  stream it did not ask for.
RB_LINE = 48
RB_LINES_A_DATAGRAM = 15


def rb_memory(address, count):
    # A list and one join: growing a bytes object in a loop is quadratic,
    # and at a megabyte and a half it made this fixture, not the reader
    # under test, the slowest thing in the run.
    parts = [hashlib.sha256(b"%d %d" % (address, n)).digest()
             for n in range((count + 31) // 32)]
    return b"".join(parts)[:count]


def rb_datagrams(address, count, stop_after_blocks=None, drop=None,
                 flip=None, inject=None):
    """The datagrams the monitor sends for one readback, as text."""
    data = rb_memory(address, count)
    if flip is not None:
        data = bytearray(data)
        data[flip] ^= 0x01
        data = bytes(data)
    grams = ["readback %X %X\r\n" % (address, count),
             "readback %08X %d bytes base64\r\n" % (address, count)]
    block = RB_LINE * RB_LINES_A_DATAGRAM
    sent = 0
    k = 0
    for start in range(0, count, block):
        if stop_after_blocks is not None and k == stop_after_blocks:
            break
        piece = data[start:start + block]
        text = "".join(base64.b64encode(piece[i:i + RB_LINE]).decode() + "\r\n"
                       for i in range(0, len(piece), RB_LINE))
        if inject is not None and k == inject[0]:
            grams.append(inject[1])
        if drop is None or k != drop:
            grams.append(text)
        sent += len(piece)
        k += 1
    # The board's crc32 is of the bytes it SENT, which for a flipped byte
    # is the unflipped original: the flip models a byte changed on the way.
    crc = zlib.crc32(rb_memory(address, count)[:sent]) & 0xFFFFFFFF
    if stop_after_blocks is not None and sent < count:
        grams.append("readback stopped after %d of %d bytes crc32 %08X\r\n"
                     % (sent, count, crc))
    else:
        grams.append("readback end %d bytes crc32 %08X\r\npmf> " % (sent, crc))
    return grams


class ReadbackConsole:
    """A console whose answer to each `readback` is scripted per attempt."""

    COMMAND = re.compile(r"^readback ([0-9A-F]+) ([0-9A-F]+)$")

    def __init__(self, faults=None, stale=""):
        self.faults = deque(faults or [])
        self.pending = deque([stale] if stale else [])
        self.sent = []
        self.settles = []

    def settle(self, quiet=1.0, cap=15):
        self.settles.append(quiet)
        return ""

    def send(self, line):
        self.sent.append(line)
        m = self.COMMAND.match(line)
        if not m:
            raise AssertionError("unexpected command " + line)
        fault = self.faults.popleft() if self.faults else {}
        if fault.get("silent"):
            return
        self.pending.extend(rb_datagrams(int(m.group(1), 16),
                                         int(m.group(2), 16), **fault))

    def recv_some(self):
        return self.pending.popleft() if self.pending else ""


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)

    def read(self, con, address=0x57400000, count=2000, **kw):
        kw.setdefault("progress", None)
        kw.setdefault("seconds", 0.3)
        return upload.read_range(con, address, count, **kw)

    def test_one_chunk_is_exact(self):
        con = ReadbackConsole()
        data, stats = self.read(con)
        self.assertEqual(data, rb_memory(0x57400000, 2000))
        self.assertEqual(con.sent, ["readback 57400000 7D0"])
        self.assertEqual((stats["chunks"], stats["retries"]), (1, 0))

    def test_chunks_join_in_order_and_every_short_tail_decodes(self):
        # 2000 bytes in 721-byte chunks: 721, 721, 558 - one-byte and
        # two-byte base64 tails inside chunks, a short last chunk.
        con = ReadbackConsole()
        data, stats = self.read(con, count=2000, chunk_bytes=721)
        want = (rb_memory(0x57400000, 721) + rb_memory(0x57400000 + 721, 721)
                + rb_memory(0x57400000 + 1442, 558))
        self.assertEqual(data, want)
        self.assertEqual(con.sent, ["readback 57400000 2D1",
                                    "readback 574002D1 2D1",
                                    "readback 574005A2 22E"])
        self.assertEqual(stats["chunks"], 3)

    def test_first_attempt_settles_briefly_and_a_retry_settles_fully(self):
        con = ReadbackConsole(faults=[{"drop": 1}])
        data, stats = self.read(con)
        self.assertEqual(data, rb_memory(0x57400000, 2000))
        self.assertEqual(stats["retries"], 1)
        self.assertEqual(con.settles, [0.05, 0.6])

    def test_lost_datagram_every_time_refuses_on_length(self):
        con = ReadbackConsole(faults=[{"drop": 1}, {"drop": 1}])
        with self.assertRaises(upload.ReadbackError) as caught:
            self.read(con)
        self.assertIn("Error 41", str(caught.exception))
        self.assertIn("Error 38", str(caught.exception))
        self.assertEqual(len(con.sent), 2)

    def test_changed_byte_refuses_on_crc(self):
        con = ReadbackConsole(faults=[{"flip": 999}, {"flip": 999}])
        with self.assertRaises(upload.ReadbackError) as caught:
            self.read(con)
        self.assertIn("Error 39", str(caught.exception))

    def test_stopped_stream_is_never_accepted(self):
        con = ReadbackConsole(faults=[{"stop_after_blocks": 2},
                                      {"stop_after_blocks": 2}])
        with self.assertRaises(upload.ReadbackError) as caught:
            self.read(con)
        self.assertIn("Error 32", str(caught.exception))

    def test_a_sentence_inside_the_stream_is_quoted_not_skipped(self):
        bad = "!! 1 of 3 blocks could not be put on the wire, so the stream above is\r\n"
        con = ReadbackConsole(faults=[{"inject": (1, bad)}, {"inject": (1, bad)}])
        with self.assertRaises(upload.ReadbackError) as caught:
            self.read(con)
        self.assertIn("Error 34", str(caught.exception))
        self.assertIn("could not be put on the wire", str(caught.exception))

    def test_stale_verdict_before_our_header_is_not_ours(self):
        # The tail of an EARLIER readback of the same length at another
        # address, verdict and all, is still arriving when this one is
        # sent. Its verdict must not end our read.
        stale = "".join(rb_datagrams(0x60000000, 2000)[2:])
        con = ReadbackConsole(stale=stale)
        data, _ = self.read(con)
        self.assertEqual(data, rb_memory(0x57400000, 2000))

    def test_silence_is_retried_once_then_refused(self):
        con = ReadbackConsole(faults=[{"silent": True}, {"silent": True}])
        with self.assertRaises(upload.ReadbackError) as caught:
            self.read(con, seconds=0.05)
        self.assertIn("Error 30", str(caught.exception))
        self.assertEqual(len(con.sent), 2)

    def test_evidence_sees_every_exchange(self):
        seen = []
        con = ReadbackConsole(faults=[{"drop": 0}])
        self.read(con, evidence=lambda line, reply: seen.append(line))
        self.assertEqual(seen, ["readback 57400000 7D0"] * 2)


class ReadbackOverUdpTest(unittest.TestCase):
    """The real WifiConsole, real datagrams, loopback, at the board's size.

    A thread plays the monitor: back-to-back 990-byte datagrams with no
    pacing at all, which is harsher than the board's 250 us, for a
    megabyte and a half - enough that a receiver with a default-sized
    socket buffer and a reader that re-scanned its whole reply per
    datagram would both show up.
    """

    def test_megabyte_stream_over_loopback(self):
        board = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        board.bind(("127.0.0.1", 0))
        board.settimeout(5)
        port = board.getsockname()[1]
        count = 1_500_000
        address = 0x57400000

        def serve():
            try:
                while True:
                    data, peer = board.recvfrom(4096)
                    line = data.decode().strip()
                    if line.startswith("readback"):
                        break
                a, n = (int(x, 16) for x in line.split()[1:3])
                for gram in rb_datagrams(a, n):
                    board.sendto(gram.encode(), peer)
            except OSError:
                pass

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            con = upload.WifiConsole("127.0.0.1", port)
        try:
            began = time.monotonic()
            data, stats = upload.read_range(con, address, count,
                                            chunk_bytes=count, seconds=30,
                                            progress=None)
            took = time.monotonic() - began
        finally:
            con.close()
            board.close()
            thread.join(timeout=5)
        self.assertEqual(data, rb_memory(address, count))
        self.assertEqual(stats["retries"], 0)
        # Not a benchmark, a floor: the host must not be the bottleneck.
        self.assertGreater(count / took, 1_000_000,
                           "the host read %d bytes in %.2f s" % (count, took))


if __name__ == "__main__":
    unittest.main()
