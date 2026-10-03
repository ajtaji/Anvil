"""Desk-only positive and mutation tests for the 10k module profile checker."""

import struct
import unittest

from vulkanNeonParticleCsdModule10kProfileCheck import (
    INPUT_ALLOC, MAGIC, OUTPUT_ALLOC, TAIL, validate,
)


def plausible_report() -> list[int]:
    w = [0] * 64
    w[0], w[2], w[5], w[10], w[37], w[63] = (
        MAGIC, 5, OUTPUT_ALLOC, 2048, INPUT_ALLOC, TAIL,
    )
    w[4], w[6], w[7], w[8], w[44] = (
        0x06400000, 0x06600000, 0x06601000, 0x06602000, 0x06800000,
    )
    w[14], w[15], w[31], w[32] = 3, 4, 1, 1
    w[19], w[20] = 200_000, 100_000
    w[25:30] = [0xFF000000] + [0xFF00FF00] * 4
    w[38], w[39], w[40], w[41], w[42], w[43] = (
        1, 60_000, 1_000_000, 500_000, 0x3F7B851F, 350_000,
    )
    w[45], w[46], w[47], w[48], w[49], w[54] = (
        3200, 0x063E8000, 0x01000000, 25_000, 200_000, 1,
    )
    w[61], w[62] = 20_000, 10_000
    return w


def encoded(w: list[int]) -> bytes:
    return struct.pack("<64I", *w)


class CheckerTest(unittest.TestCase):
    def test_plausible_report(self) -> None:
        assert validate(encoded(plausible_report()))

    def test_rejects_guard_mismatch(self) -> None:
        w = plausible_report()
        w[17] = 1
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_pixel_mismatch(self) -> None:
        w = plausible_report()
        w[29] ^= 0x100
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_overlap(self) -> None:
        w = plausible_report()
        w[8] = w[4]
        with self.assertRaises(AssertionError):
            validate(encoded(w))

    def test_rejects_deadman_budget(self) -> None:
        w = plausible_report()
        w[40] = 13_000_001
        with self.assertRaises(AssertionError):
            validate(encoded(w))


if __name__ == "__main__":
    unittest.main()
