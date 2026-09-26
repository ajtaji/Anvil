"""Focused host checks for Pi 5 firmware DTB validation."""

import struct
import unittest
import os
from pathlib import Path

from dtb_contract import DtbError, inspect, parse


VAULT_DTB = Path(os.environ["PI5_DTB_DIR"]) if "PI5_DTB_DIR" in os.environ else None
VARIANTS = ("bcm2712-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb",
            "bcm2712d0-rpi-5-b.dtb")


class DtbContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if VAULT_DTB is None:
            raise unittest.SkipTest("set PI5_DTB_DIR to the explicit pinned DTB folder")

    def test_pinned_pi5_variants(self):
        for name in VARIANTS:
            with self.subTest(name=name):
                result = inspect((VAULT_DTB / name).read_bytes())
                self.assertEqual(result["model"], "Raspberry Pi 5")
                self.assertIn("brcm,bcm2712", result["compatible"])
                self.assertTrue(result["rp1_bridge"].endswith("/rp1"))

    def test_rejects_truncated_and_corrupt_blobs(self):
        good = (VAULT_DTB / VARIANTS[0]).read_bytes()
        failures = (
            good[:32],
            good[:-1],
            b"\0\0\0\0" + good[4:],
            good[:4] + struct.pack(">I", len(good) + 1) + good[8:],
            good[:8] + struct.pack(">I", len(good) + 4) + good[12:],
        )
        for blob in failures:
            with self.subTest(length=len(blob)), self.assertRaises(DtbError):
                parse(blob)

    def test_rejects_wrong_board_identity(self):
        good = (VAULT_DTB / VARIANTS[0]).read_bytes()
        bad = good.replace(b"brcm,bcm2712\0", b"brcm,bcm2711\0", 1)
        self.assertEqual(len(good), len(bad))
        with self.assertRaisesRegex(DtbError, "does not identify"):
            inspect(bad)


if __name__ == "__main__":
    unittest.main()
