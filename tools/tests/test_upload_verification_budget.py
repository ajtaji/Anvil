"""Host-side recovery checks; no board commands or payloads are executed."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import board_run as br


class VerificationBudget(unittest.TestCase):
    def exercise(self, mode, size=119_358_848):
        clock = [0.0]
        calls = []
        digest = "a" * 64

        class Console:
            def __init__(self, host="192.0.2.1", port=5555):
                self.addr = (host, port)
                self.transcript = []

            def at_prompt(self, timeout):
                clock[0] += min(0.1, timeout)
                return True

            def command(self, line, timeout):
                calls.append((line, timeout))
                if mode == "mismatch":
                    return "The sha256sum is " + "b" * 64
                if mode == "lost" or timeout < 90.0:
                    clock[0] += timeout
                    raise br.StreamError("Checksum reply did not arrive.")
                clock[0] += 90.0
                return "The sha256sum is " + digest

            def close(self):
                pass

        original = Console()
        with patch.object(br, "NetConsole", Console), patch.object(
                br.time, "monotonic", lambda: clock[0]):
            if mode == "mismatch":
                with self.assertRaises(br.UploadDigestMismatch):
                    br.verify_upload_after_reply_loss(original, 0x50000000, size, digest)
            elif mode == "lost" or size < 35_000_000:
                with self.assertRaises(br.StreamError):
                    br.verify_upload_after_reply_loss(original, 0x50000000, size, digest)
            else:
                returned, proof = br.verify_upload_after_reply_loss(
                    original, 0x50000000, size, digest)
                self.assertIs(returned, original)
                self.assertEqual(proof["sha256"], digest)
                self.assertEqual(proof["attempt"], 1)
        self.assertTrue(all(line.startswith("sha256sum ") for line, _ in calls))
        self.assertLessEqual(clock[0], 290.000001)
        self.assertLessEqual(len(calls), 3)
        return calls

    def test_large_valid_reply_after_old_deadline(self):
        self.assertGreater(self.exercise("valid")[0][1], 90.0)

    def test_mismatch_is_never_retried(self):
        self.assertEqual(len(self.exercise("mismatch")), 1)

    def test_lost_replies_share_total_budget(self):
        self.exercise("lost")

    def test_small_range_keeps_previous_timeout(self):
        calls = self.exercise("lost", 1_000_000)
        self.assertEqual([timeout for _, timeout in calls], [35.0] * 3)

    def test_huge_range_cannot_extend_total_budget(self):
        self.exercise("lost", 2_000_000_000)


if __name__ == "__main__":
    unittest.main()
