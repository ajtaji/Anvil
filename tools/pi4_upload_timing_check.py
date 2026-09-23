#!/usr/bin/env python3
"""Prove host queue, peer FIN, timeout and failure are not conflated.

No board access. The socket/clock are models; pi4_upload_check.py separately
checks the real CLI's length/digest refusal and save/boot ordering.
"""
import socket
import unittest
from unittest.mock import patch

import pi4_upload as upload


class FakeSocket:
    def __init__(self, events, send_error=None, shutdown_error=None):
        self.events = iter(events)
        self.now = 0.0
        self.sent = None
        self.half_closed = False
        self.closed = False
        self.send_error = send_error
        self.shutdown_error = shutdown_error

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def settimeout(self, seconds):
        assert seconds == 30.0

    def sendall(self, data):
        self.now += 0.25
        if self.send_error:
            raise self.send_error
        self.sent = data

    def shutdown(self, how):
        assert how == socket.SHUT_WR
        if self.shutdown_error:
            raise self.shutdown_error
        self.half_closed = True

    def recv(self, size):
        assert size == 4096 and self.half_closed
        delay, event = next(self.events)
        self.now += delay
        if isinstance(event, Exception):
            raise event
        return event


def run_stream(sock):
    with patch.object(upload, "local_bind_for", return_value=None), \
         patch.object(upload.socket, "create_connection", return_value=sock), \
         patch.object(upload.time, "monotonic", side_effect=lambda: sock.now):
        return upload.stream("127.0.0.1", 5001, b"payload")


class TimingTests(unittest.TestCase):
    def test_fin_after_reply_is_transport_only(self):
        sock = FakeSocket([(1.0, b"reply"), (0.5, b"")])
        timing = run_stream(sock)
        self.assertEqual(timing, upload.TransferTiming(0.25, 1.75, True, ""))
        self.assertEqual(sock.sent, b"payload")
        self.assertTrue(sock.closed and sock.half_closed)
        report = upload.stream_report(7, timing)
        self.assertIn("queued to the host TCP socket", report)
        self.assertIn("Peer TCP close observed", report)
        self.assertIn("waiting for the board's length and SHA-256 verdict", report)
        self.assertNotIn("on the wire", report)
        self.assertNotIn("KB/s", report)
        self.assertNotIn("VERIFIED", report)

    def test_timeout_is_not_completed_transfer(self):
        sock = FakeSocket([(30.0, socket.timeout("timed out"))])
        timing = run_stream(sock)
        self.assertEqual(timing.queued_seconds, 0.25)
        self.assertEqual(timing.elapsed_seconds, 30.25)
        self.assertFalse(timing.peer_closed)
        self.assertTrue(sock.closed)
        report = upload.stream_report(7, timing)
        self.assertIn("close not confirmed", report)
        self.assertIn("timed out", report)
        self.assertIn("delivery is not yet verified", report)
        self.assertNotIn("on the wire", report)
        self.assertNotIn("KB/s", report)

    def test_reset_is_not_fin(self):
        sock = FakeSocket([(2.0, ConnectionResetError("peer reset"))])
        timing = run_stream(sock)
        self.assertFalse(timing.peer_closed)
        self.assertIn("peer reset", timing.close_error)
        self.assertTrue(sock.closed)

    def test_send_failure_propagates_without_success_report(self):
        sock = FakeSocket([], send_error=OSError("send failed"))
        with self.assertRaisesRegex(OSError, "send failed"):
            run_stream(sock)
        self.assertFalse(sock.half_closed)
        self.assertTrue(sock.closed)

    def test_half_close_failure_propagates_without_success_report(self):
        sock = FakeSocket([], shutdown_error=OSError("shutdown failed"))
        with self.assertRaisesRegex(OSError, "shutdown failed"):
            run_stream(sock)
        self.assertTrue(sock.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
