#!/usr/bin/env python3
"""Host-only compatibility and single-Anvil-component bundle tests."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import rockpi4c_sd_bundle as bundle


def components(image: bytes) -> list[dict[str, object]]:
    first = image[:bundle.IMAGE_KIB * 1024]
    count_sign = struct.unpack_from("<I", first, 12)[0]
    count = count_sign >> 16
    sign_offset = (count_sign & 0xFFFF) * 4
    result = []
    for index in range(count):
        digest = first[800 + index * 48:832 + index * 48]
        load, sectors, _, _ = struct.unpack_from("<4I", first, 832 + index * 48)
        cid, storage_sector, table_sectors, flags = struct.unpack_from(
            "<4sIII", first, sign_offset + 256 + index * 16
        )
        offset = storage_sector * 512
        size = table_sectors * 512
        data = first[offset:offset + size]
        result.append({
            "id": cid, "load": load, "sectors": sectors,
            "table_sectors": table_sectors, "flags": flags,
            "offset": offset, "data": data, "digest": digest,
        })
    return result


class SdBundleTests(unittest.TestCase):
    def test_cli_writes_one_self_contained_anvil_component(self):
        entry_path = ROOT / "build/rockpi4c/build117/sd-entry.bin"
        entry = entry_path.read_bytes()
        payload_path = ROOT / "build/rockpi4c/hdmi-first/anvil-flat.img"
        payload = payload_path.read_bytes()
        dtb = (ROOT / "build/rockpi4c/direct-sd/rockpi4c.dtb").read_bytes()
        expected = bundle.build_bundle(entry, payload, dtb)
        self.assertEqual(len(components(expected)), 1)
        self.assertEqual(components(expected)[0]["load"], bundle.ANVIL_ADDRESS)
        self.assertEqual(components(expected)[0]["data"][:len(bundle.build_anvil(entry, payload, dtb))],
                         bundle.build_anvil(entry, payload, dtb))

        with tempfile.TemporaryDirectory(prefix="rockpi4c-sd-bundle-") as temp:
            output = Path(temp) / "trust.img"
            anvil_output = Path(temp) / "anvil.bin"
            linked_payload = Path(temp) / "anvil-flat.img"
            linked_payload.write_bytes(payload)
            header = bytearray(128)
            struct.pack_into("<8sIIQQQQQ", header, 0, b"PMFBOOT\0", 2, 128,
                             bundle.PAYLOAD_ADDRESS, bundle.PAYLOAD_ADDRESS,
                             len(payload), bundle.BSS_ADDRESS, 4096)
            header[64:96] = hashlib.sha256(payload).digest()
            struct.pack_into("<IIQ", header, 96, 1, 3399, bundle.STACK_ADDRESS)
            Path(str(linked_payload) + ".pmf").write_bytes(header + payload)
            result = subprocess.run([
                sys.executable, str(ROOT / "tools/rockpi4c_sd_bundle.py"),
                "--entry", str(entry_path),
                "--payload", str(linked_payload),
                "--dtb", str(ROOT / "build/rockpi4c/direct-sd/rockpi4c.dtb"),
                "--output", str(output),
                "--anvil-output", str(anvil_output),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes(), expected)
            self.assertEqual(anvil_output.read_bytes(), bundle.build_anvil(entry, payload, dtb))
            with self.assertRaisesRegex(bundle.BundleError, "address contract"):
                bad = bytearray(header)
                struct.pack_into("<Q", bad, 16, 0x80000)
                bundle.validate_payload_pmf(payload, bytes(bad) + payload)
        self.assertEqual(hashlib.sha256(expected).hexdigest(),
                         hashlib.sha256(bundle.build_bundle(entry, payload, dtb)).hexdigest())

    def test_large_anvil_remains_one_component(self):
        entry = (ROOT / "build/rockpi4c/build117/sd-entry.bin").read_bytes()
        payload = bytes((i * 17 + 5) & 0xFF for i in range(512 * 1024 + 1234))
        dtb = bytes((i * 7 + 9) & 0xFF for i in range(4100))
        image = bundle.build_bundle(entry, payload, dtb)
        copy_size = bundle.IMAGE_KIB * 1024
        self.assertEqual(len(image), copy_size * 2)
        self.assertEqual(image[:copy_size], image[copy_size:])

        actual = components(image)
        expected_raw = [bundle.build_anvil(entry, payload, dtb)]
        expected_loads = [bundle.ANVIL_ADDRESS]
        self.assertEqual(len(actual), 1)
        cursor = bundle.trust.HEADER_SIZE
        for index, (component, raw, load) in enumerate(zip(actual, expected_raw, expected_loads)):
            padded_size = bundle.trust.align_up(len(raw), bundle.trust.ALIGNMENT)
            padded = raw + bytes(padded_size - len(raw))
            self.assertEqual(component["id"], b"BL31")
            self.assertEqual(component["load"], load)
            self.assertEqual(component["sectors"], padded_size // 512)
            self.assertEqual(component["table_sectors"], padded_size // 512)
            self.assertEqual(component["offset"], cursor)
            self.assertEqual(component["data"], padded)
            self.assertEqual(component["digest"], hashlib.sha256(padded).digest())
            cursor += padded_size
        self.assertEqual(cursor, 2048 + sum(
            bundle.trust.align_up(len(raw), bundle.trust.ALIGNMENT) for raw in expected_raw
        ))

    def test_limits_reject_before_packaging(self):
        entry = (ROOT / "build/rockpi4c/build117/sd-entry.bin").read_bytes()
        dtb = b"D" * 64
        with self.assertRaisesRegex(bundle.BundleError, "4 KiB"):
            bundle.build_bundle(b"E" * 4097, b"P", dtb)
        with self.assertRaisesRegex(bundle.BundleError, "board data"):
            bundle.build_bundle(entry, b"P" * (bundle.DTB_ADDRESS - bundle.PAYLOAD_ADDRESS + 1), dtb)

    def test_stale_ram_boot_entry_is_rejected(self):
        stale = (ROOT / "build/rockpi4c/direct-sd/sd-entry.bin").read_bytes()
        good = (ROOT / "build/rockpi4c/build117/sd-entry.bin").read_bytes()
        self.assertNotEqual(stale, good)
        with self.assertRaisesRegex(bundle.BundleError, "runtime-address contract"):
            bundle.build_bundle(stale, b"P" * 4, b"D" * 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
