"""Behavioral desk gate for CSD staging's Chrome-equivalent corner fast path."""

import random
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particles.pi4"


def procedure(source: str, name: str) -> str:
    match = re.search(rf"^Procedure(?:\.i)? {name}\([^\n]*\).*?^EndProcedure",
                      source, flags=re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group()


class FastPathGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stage = procedure(MODULE.read_text(), "nvpcStageRecords")
        cls.chrome = procedure(CHROME.read_text(), "NeonVkChromeParticlesDrawPrepared")
        cls.predicate = (
            "If nvcRotation = 0 And nvcParticleItems[i]\\angleQ16 = 0 And "
            "(nvcParticleItems[i]\\ignoreCamera <> 0 Or nvcParticleItems[i]\\zoomQ16 = 65536)"
        )
        start = cls.stage.index(cls.predicate)
        end = start + re.search(r"^      EndIf$", cls.stage[start:], re.MULTILINE).start()
        cls.branch = cls.stage[start:end]
        cls.fast, cls.general = re.split(r"^      Else$", cls.branch, maxsplit=1,
                                         flags=re.MULTILINE)

    def test_predicate_and_general_fallback_match_chrome(self) -> None:
        self.assertIn(self.predicate, self.chrome)
        self.assertEqual(self.stage.count(self.predicate), 1)
        self.assertEqual([line.strip() for line in self.general.strip().splitlines()], [
            "For c = 0 To 3",
            "nvcParticleCornerBits(PeekI(*corners + c * 2 * SizeOf(.i)), PeekI(*corners + (c * 2 + 1) * SizeOf(.i)), @xb, @yb)",
            "PokeL(p + c * 8, xb) : PokeL(p + c * 8 + 4, yb)",
            "Next",
        ])

    def test_four_clips_and_all_eight_fast_stores(self) -> None:
        fast = self.fast
        self.assertEqual(re.findall(r"nvcParticleClipXBits\(\*corners\\(x\d)\)", fast), ["x0", "x1"])
        self.assertEqual(re.findall(r"nvcParticleClipYBits\(\*corners\\(y\d)\)", fast), ["y0", "y2"])
        stores = re.findall(r"PokeL\(p \+ (\d+), (\w+)\)", fast)
        self.assertEqual([(int(off), name) for off, name in stores], [
            (0, "xb0"), (4, "yb0"), (8, "xb1"), (12, "yb0"),
            (16, "xb0"), (20, "yb2"), (24, "xb1"), (28, "yb2"),
        ])

    def test_fast_stores_equal_general_for_axis_aligned_geometry(self) -> None:
        fast = self.fast
        stores = [(int(off) // 4, name) for off, name in
                  re.findall(r"PokeL\(p \+ (\d+), (\w+)\)", fast)]
        rng = random.Random(0xC5D)
        for _ in range(1000):
            x, y = rng.randrange(-100_000, 100_000), rng.randrange(-100_000, 100_000)
            width, height = rng.randrange(1, 4000), rng.randrange(1, 4000)
            corners = ((x, y), (x + width, y), (x, y + height),
                       (x + width, y + height))
            # Distinct X/Y transformations expose swapped, omitted, or stale words.
            clip_x = lambda value: (value * 1315423911 + 0x12345678) & 0xFFFFFFFF
            clip_y = lambda value: (value * 2654435761 + 0x87654321) & 0xFFFFFFFF
            general = tuple(word for cx, cy in corners for word in (clip_x(cx), clip_y(cy)))
            values = {"xb0": clip_x(x), "xb1": clip_x(x + width),
                      "yb0": clip_y(y), "yb2": clip_y(y + height)}
            emitted = [None] * 8
            for index, name in stores:
                emitted[index] = values[name]
            self.assertEqual(tuple(emitted), general)

    def test_local_y_pair_cache_keeps_words_exact_across_fast_and_general_items(self) -> None:
        self.assertLess(self.stage.index("haveYPair = 0"),
                        self.stage.index("For i = 0 To padded - 1"))
        fast = self.fast
        self.assertIn("*corners\\y0 = cachedY0 And *corners\\y2 = cachedY2", fast)
        self.assertIn("yb0 = cachedYb0 : yb2 = cachedYb2", fast)
        self.assertIn("cachedY0 = *corners\\y0 : cachedY2 = *corners\\y2", fast)
        self.assertIn("cachedYb0 = yb0 : cachedYb2 = yb2 : haveYPair = 1", fast)
        self.assertEqual(fast.count("nvcParticleClipYBits("), 2)

        rng = random.Random(0xA51)
        items = []
        for row in range(100):
            for column in range(100):
                y0 = row * 2048 + rng.randrange(-2, 3) * 256 if row % 17 == 0 else row * 2048
                y2 = y0 + 1024
                fast_item = (column % 19 != 0)
                items.append((fast_item, y0, y2))
        have, key, value, calls = False, None, None, 0
        for fast_item, y0, y2 in items:
            expected = ((y0 * 2654435761 + 0x12345678) & 0xFFFFFFFF,
                        (y2 * 2654435761 + 0x12345678) & 0xFFFFFFFF)
            if not fast_item:
                continue  # the unchanged general branch may call the clip cache
            if not have or key != (y0, y2):
                key, value, have = (y0, y2), expected, True
                calls += 2
            self.assertEqual(value, expected)
        self.assertLess(calls, 10_000)  # 20,000 uncached Y calls in this mix

    def test_local_x_pair_cache_keeps_words_exact_across_rows_and_collisions(self) -> None:
        fast = self.fast
        self.assertLess(self.stage.index("For i = 0 To 127 : cachedXValid[i] = 0 : Next"),
                        self.stage.index("For i = 0 To padded - 1"))
        self.assertIn("xSlot = (*corners\\x0 >> 11) & 127", fast)
        self.assertIn("cachedXValid[xSlot] <> 0 And cachedX0[xSlot] = *corners\\x0 And cachedX1[xSlot] = *corners\\x1", fast)
        self.assertIn("xb0 = cachedXb0[xSlot] : xb1 = cachedXb1[xSlot]", fast)
        self.assertIn("cachedXb0[xSlot] = xb0 : cachedXb1[xSlot] = xb1 : cachedXValid[xSlot] = 1", fast)
        self.assertEqual(fast.count("nvcParticleClipXBits("), 2)

        cache = [None] * 128
        calls = 0
        for row in range(100):
            for column in range(100):
                # A changed width and a deliberately colliding column must
                # always miss; the unchanged columns recur in later rows.
                x0 = (column * 8 + (row % 17 == 0 and column == 71) * 1024) * 256
                x1 = x0 + (4 + (row == 29 and column == 37)) * 256
                slot = (x0 >> 11) & 127
                expected = ((x0 * 1315423911 + 0x12345678) & 0xFFFFFFFF,
                            (x1 * 1315423911 + 0x12345678) & 0xFFFFFFFF)
                if cache[slot] is None or cache[slot][:2] != (x0, x1):
                    cache[slot] = (x0, x1, *expected)
                    calls += 2
                self.assertEqual(cache[slot][2:], expected)
        self.assertLess(calls, 20_000)


if __name__ == "__main__":
    unittest.main()
