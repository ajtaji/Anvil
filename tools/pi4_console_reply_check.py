"""Host-only response attribution and cache-state tests. No board is contacted."""
from collections import deque
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
