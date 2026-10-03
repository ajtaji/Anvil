"""Synthetic report and mutation tests for the matched timing checker."""

import struct
import unittest

from vulkanNeonParticleMatchedProfileCheck import (
    CPU_MAGIC, CPU_TAIL, CSD_MAGIC, CSD_TAIL, OUTPUT_BYTES, median_us, validate,
)


def report(csd: bool) -> list[int]:
    w = [0] * 64
    w[0], w[2], w[4], w[5], w[6], w[7], w[8], w[63] = (
        (CSD_MAGIC if csd else CPU_MAGIC), 4, 0x06800000, 3200,
        10_000, 3, 4, (CSD_TAIL if csd else CPU_TAIL),
    )
    w[14], w[15], w[31], w[32], w[46], w[47], w[54] = (
        1_000_000, 1_200_000, 4, 4, 0x063E8000, 0x01000000, 1,
    )
    w[16:19] = [100_000, 110_000, 120_000]
    w[19:22] = [20_000, 21_000, 22_000]
    w[22:25] = [50_000, 51_000, 52_000]
    w[25:30] = [0xFF000000] + [0xFF00FF00] * 4
    w[43:46] = [180_000, 190_000, 200_000]
    if csd:
        w[10], w[48], w[49] = 2048, 0x06400000, OUTPUT_BYTES
        w[34:37] = [20_000, 21_000, 22_000]
        w[37:40] = [30_000, 31_000, 32_000]
        w[40:43] = [40_000, 41_000, 42_000]
    return w


def encoded(w: list[int]) -> bytes:
    return struct.pack("<64I", *w)


class CheckerTest(unittest.TestCase):
    def test_cpu_report(self) -> None:
        self.assertEqual(median_us(validate(encoded(report(False))), 43), 190_000)

    def test_csd_report(self) -> None:
        self.assertEqual(median_us(validate(encoded(report(True))), 34), 21_000)

    def test_rejects_pixel_mismatch(self) -> None:
        w = report(True)
        w[27] ^= 0x100
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_late_teardown(self) -> None:
        w = report(False)
        w[15] = 14_000_001
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_unmatched_gpu_allocation(self) -> None:
        w = report(True)
        w[49] -= 4096
        with self.assertRaises(AssertionError):
            validate(encoded(w))


if __name__ == "__main__":
    unittest.main()
