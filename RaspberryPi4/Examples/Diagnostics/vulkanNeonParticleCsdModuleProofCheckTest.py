"""Desk-only positive and mutation tests for the production-module report checker."""

import struct
import unittest

from vulkanNeonParticleCsdModuleProofCheck import MAGIC, TAIL, colour, validate


def plausible_report() -> list[int]:
    w = [0] * 64
    w[0], w[2], w[5], w[10], w[63] = MAGIC, 5, 12288, 2048, TAIL
    w[4], w[6], w[7], w[8], w[44] = (
        0x06400000, 0x06403000, 0x06404000, 0x06405000, 0x06410000
    )
    w[14], w[15], w[31], w[32] = 3, 4, 1, 1
    w[25:30] = [0xFF000000] + [colour(i) for i in range(4)]
    w[37], w[38], w[39] = 500_000, 1, 192
    w[40:43] = [0xBF580000, 0x3F800000, 0x3D800000]
    w[43] = 10_000
    w[45:49] = [512, 0x063E8000, 0x00C00000, 200]
    w[49], w[54], w[61], w[62] = 50_000, 1, 4_000, 600_000
    return w


def encoded(w: list[int]) -> bytes:
    return struct.pack("<64I", *w)


class CheckerTest(unittest.TestCase):
    def test_plausible_complete_report(self) -> None:
        assert validate(encoded(plausible_report()))

    def test_rejects_vertex_mismatch(self) -> None:
        w = plausible_report()
        w[16] = 1
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_rotated_palette_pixel(self) -> None:
        w = plausible_report()
        w[27] ^= 0x100
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_overlap(self) -> None:
        w = plausible_report()
        w[8] = w[4]
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_prepare_failure(self) -> None:
        w = plausible_report()
        w[43] = 0xFFFFFFFE
        with self.assertRaises(AssertionError):
            validate(encoded(w))


if __name__ == "__main__":
    unittest.main()
