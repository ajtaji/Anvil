import contextlib
import importlib.util
import io
from pathlib import Path
import socket
import struct
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name("anvil_wifi_update.py")
spec = importlib.util.spec_from_file_location("anvil_wifi_update", MODULE_PATH)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class FakeSocket:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.sent = []
        self.timeout = None
    def settimeout(self, value):
        self.timeout = value
    def recvfrom(self, _size):
        if self.timeout == 0:
            raise BlockingIOError()
        if self.replies:
            value = self.replies.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value, ("127.0.0.1", 5555)
        raise socket.timeout()
    def sendto(self, packet, address):
        self.sent.append((packet, address))
    def bind(self, _address):
        pass
    def close(self):
        pass


class WifiUpdateReceiveOnlyTests(unittest.TestCase):
    def test_receive_only_skips_save_and_reset(self):
        sock = FakeSocket()
        calls = []
        with mock.patch("builtins.open", mock.mock_open(read_data=b"payload")), \
             mock.patch.object(updater.socket, "socket", return_value=sock), \
             mock.patch.object(updater, "cmd", side_effect=lambda _s, _ip, line, *_a: calls.append(line) or "this image 00200000 to 00AFFFFF 900000 bytes\nstage a file at 02E00000\n  the low window   02E00000 to 02FFFFFF\n  the high window  03A00000 to 3B3FFFFF"), \
             mock.patch.object(updater, "send_image", return_value=True) as send:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = updater.main(["--receive-only", "192.0.2.10", "tiny.bin"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["map"])
        send.assert_called_once_with(sock, "192.0.2.10", b"payload", 0x02E00000)
        self.assertIn("no save or reset", out.getvalue())

    def test_default_mode_keeps_save_then_reset(self):
        sock = FakeSocket()
        calls = []
        with mock.patch("builtins.open", mock.mock_open(read_data=b"payload")), \
             mock.patch.object(updater.socket, "socket", return_value=sock), \
             mock.patch.object(updater, "cmd", side_effect=lambda _s, _ip, line, *_a: calls.append(line) or ("stage a file at 02E00000\n  the low window   02E00000 to 02FFFFFF\n  the high window  03A00000 to 3B3FFFFF" if line == "map" else "written.")), \
             mock.patch.object(updater, "send_image", return_value=True), \
             mock.patch.object(updater, "recv_text", return_value="resetting"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = updater.main(["192.0.2.10", "image.bin"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["map", "save KERNEL8.IMG 2E00000 7"])
        self.assertIn((b"reset\r", ("192.0.2.10", updater.PORT)), sock.sent)

    def test_wrong_stage_refuses_before_transfer(self):
        sock = FakeSocket()
        with mock.patch("builtins.open", mock.mock_open(read_data=b"payload")), \
             mock.patch.object(updater.socket, "socket", return_value=sock), \
             mock.patch.object(updater, "cmd", return_value="stage a file at 02F00000"), \
             mock.patch.object(updater, "send_image") as send:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = updater.main(["--receive-only", "192.0.2.10", "tiny.bin"])
        self.assertEqual(rc, 1)
        send.assert_not_called()
        self.assertIn("not wholly inside a payload window", out.getvalue())

    def test_explicit_stage_must_fit_map_and_avoid_live_payload(self):
        map_text = ("stage a file at 02E00000\n"
                    "  the low window   02E00000 to 02FFFFFF\n"
                    "  the high window  03A00000 to 3B3FFFFF")
        sock = FakeSocket()
        with mock.patch("builtins.open", mock.mock_open(read_data=b"payload")), \
             mock.patch.object(updater.socket, "socket", return_value=sock), \
             mock.patch.object(updater, "cmd", return_value=map_text), \
             mock.patch.object(updater, "send_image", return_value=True) as send:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = updater.main(["--receive-only", "--stage", "03A10000",
                                   "--avoid", "02E00000:02FFFFFF",
                                   "192.0.2.10", "tiny.bin"])
        self.assertEqual(rc, 0)
        send.assert_called_once_with(sock, "192.0.2.10", b"payload", 0x03A10000)

        with mock.patch("builtins.open", mock.mock_open(read_data=b"payload")), \
             mock.patch.object(updater.socket, "socket", return_value=FakeSocket()), \
             mock.patch.object(updater, "cmd", return_value=map_text), \
             mock.patch.object(updater, "send_image") as refused_send:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = updater.main(["--receive-only", "--stage", "03A10000",
                                   "--avoid", "03A00000:03A1FFFF",
                                   "192.0.2.10", "tiny.bin"])
        self.assertEqual(rc, 1)
        refused_send.assert_not_called()
        self.assertIn("caller-declared occupied memory", out.getvalue())

        for stage, windows in (("-1", "  the low window   02FFFFFF to 02E00000"),
                               ("03A00000", "  the high window  03A00000 to 03A0000")):
            malformed_map = "stage a file at 02E00000\n" + windows
            with mock.patch("builtins.open", mock.mock_open(read_data=b"payload")), \
                 mock.patch.object(updater.socket, "socket", return_value=FakeSocket()), \
                 mock.patch.object(updater, "cmd", return_value=malformed_map), \
                 mock.patch.object(updater, "send_image") as bad_map_send:
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = updater.main(["--receive-only", "--stage", stage,
                                       "192.0.2.10", "tiny.bin"])
            self.assertEqual(rc, 1)
            bad_map_send.assert_not_called()

    def test_receive_only_size_is_bounded(self):
        fake_open = mock.mock_open(read_data=b"x" * (updater.PI3_RECEIVE_MAX + 1))
        with mock.patch("builtins.open", fake_open), \
             mock.patch.object(updater.socket, "socket") as sock_factory:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = updater.main(["--receive-only", "192.0.2.10", "large.bin"])
        self.assertEqual(rc, 1)
        sock_factory.assert_not_called()
        self.assertIn("at most 2 MiB", out.getvalue())

    def test_send_image_requires_rdy_ack_and_crc_success(self):
        image = b"payload"
        ok = FakeSocket([b"rdy", struct.pack("<I", 0), struct.pack("<I", updater.RESULT_OK)])
        out = io.StringIO()
        with mock.patch.object(updater.time, "monotonic", side_effect=[100.0, 100.000007]), \
             contextlib.redirect_stdout(out):
            self.assertTrue(updater.send_image(ok, "192.0.2.10", image, 0x02E00000))
        address = ("192.0.2.10", updater.PORT)
        expected_crc = updater.zlib.crc32(image) & 0xFFFFFFFF
        self.assertIn((f"wb 2E00000 {len(image):X} {expected_crc:08X}\r".encode(), address), ok.sent)
        self.assertIn((struct.pack("<I", 0) + image, address), ok.sent)
        self.assertIn((struct.pack("<I", updater.END), ("192.0.2.10", updater.PORT)), ok.sent)
        self.assertIn("8.00 Mbit/s payload rate", out.getvalue())

        bad_crc = FakeSocket([b"rdy", struct.pack("<I", 0), struct.pack("<I", updater.RESULT_BAD)])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(updater.send_image(bad_crc, "192.0.2.10", image, 0x02E00000))

        no_ready = FakeSocket([b"busy"] + [socket.timeout()] * 20)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(updater.send_image(no_ready, "192.0.2.10", image, 0x02E00000))


if __name__ == "__main__":
    unittest.main()
