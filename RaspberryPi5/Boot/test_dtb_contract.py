"""Focused host checks for Pi 5 firmware DTB validation."""

import struct
import unittest
import os
import re
from pathlib import Path

from dtb_contract import DtbError, early_uart, inspect, parse, wlan_sdio


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
                self.assertEqual(result["stdout_path"], "serial10:115200n8")
                self.assertEqual(result["early_uart"],
                                 "/soc@107c000000/serial@7d001000")
                self.assertIn("arm,pl011", result["early_uart_compatible"])
                self.assertEqual(result["early_uart_physical"], 0x107D001000)
                self.assertEqual(result["wifi_sdio_host"], "/axi/mmc@1100000")
                self.assertEqual(result["wifi_sdio_physical"], 0x1001100000)

    def test_first_entry_uart_constant_matches_translated_dtb(self):
        source = Path(__file__).with_name("board.pi4").read_text()
        constant = re.search(r"^#PI5_UART_DR\s*=\s*\$([0-9A-Fa-f]+)$",
                             source, re.MULTILINE)
        self.assertIsNotNone(constant)
        expected = int(constant.group(1), 16)
        for name in VARIANTS:
            with self.subTest(name=name):
                result = inspect((VAULT_DTB / name).read_bytes())
                self.assertEqual(expected, result["early_uart_physical"])

    def test_early_uart_refuses_missing_and_disabled_targets(self):
        good = parse((VAULT_DTB / VARIANTS[0]).read_bytes())
        uart_path = good["/aliases"]["serial10"].rstrip(b"\0").decode()
        bad = {path: props.copy() for path, props in good.items()}
        bad["/aliases"]["serial10"] = b"/missing\0"
        with self.assertRaisesRegex(DtbError, "does not resolve"):
            early_uart(bad)
        bad["/aliases"]["serial10"] = good["/aliases"]["serial10"]
        bad[uart_path]["status"] = b"disabled\0"
        with self.assertRaisesRegex(DtbError, "not enabled"):
            early_uart(bad)
        bad[uart_path]["status"] = good[uart_path]["status"]
        bad[uart_path]["compatible"] = b"vendor,not-pl011\0"
        with self.assertRaisesRegex(DtbError, "not a mapped PL011"):
            early_uart(bad)
        bad[uart_path]["compatible"] = good[uart_path]["compatible"]
        bad["/chosen"]["stdout-path"] = (uart_path + ":115200n8\0").encode()
        self.assertEqual(early_uart(bad)["early_uart"], uart_path)
        bad["/chosen"]["stdout-path"] = b"serial10:\0"
        with self.assertRaisesRegex(DtbError, "empty options"):
            early_uart(bad)

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

    def test_rejects_unmapped_uart_and_disabled_wlan(self):
        good = parse((VAULT_DTB / VARIANTS[0]).read_bytes())
        bad = {path: props.copy() for path, props in good.items()}
        bad["/soc@107c000000"]["ranges"] = b"\0" * 16
        with self.assertRaisesRegex(DtbError, "not covered"):
            early_uart(bad)
        bad = {path: props.copy() for path, props in good.items()}
        bad["/axi/mmc@1100000"]["status"] = b"disabled\0"
        with self.assertRaisesRegex(DtbError, "disabled or not 4-bit"):
            wlan_sdio(bad)
        bad["/axi/mmc@1100000"]["status"] = b"okay\0"
        del bad["/axi/mmc@1100000"]["vmmc-supply"]
        with self.assertRaisesRegex(DtbError, "power or pin"):
            wlan_sdio(bad)


if __name__ == "__main__":
    unittest.main()
