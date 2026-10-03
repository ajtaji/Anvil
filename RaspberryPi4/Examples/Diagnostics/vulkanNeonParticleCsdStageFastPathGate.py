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
        end = cls.stage.index("      EndIf", start)
        cls.branch = cls.stage[start:end]

    def test_predicate_and_general_fallback_match_chrome(self) -> None:
        self.assertIn(self.predicate, self.chrome)
        self.assertEqual(self.stage.count(self.predicate), 1)
        general = self.branch.split("      Else\n", 1)[1]
        self.assertEqual([line.strip() for line in general.strip().splitlines()], [
            "For c = 0 To 3",
            "nvcParticleCornerBits(PeekI(*corners + c * 2 * SizeOf(.i)), PeekI(*corners + (c * 2 + 1) * SizeOf(.i)), @xb, @yb)",
            "PokeL(p + c * 8, xb) : PokeL(p + c * 8 + 4, yb)",
            "Next",
        ])

    def test_four_clips_and_all_eight_fast_stores(self) -> None:
        fast = self.branch.split("      Else\n", 1)[0]
        self.assertEqual(re.findall(r"nvcParticleClipXBits\(\*corners\\(x\d)\)", fast), ["x0", "x1"])
        self.assertEqual(re.findall(r"nvcParticleClipYBits\(\*corners\\(y\d)\)", fast), ["y0", "y2"])
        stores = re.findall(r"PokeL\(p \+ (\d+), (\w+)\)", fast)
        self.assertEqual([(int(off), name) for off, name in stores], [
            (0, "xb0"), (4, "yb0"), (8, "xb1"), (12, "yb0"),
            (16, "xb0"), (20, "yb2"), (24, "xb1"), (28, "yb2"),
        ])

    def test_fast_stores_equal_general_for_axis_aligned_geometry(self) -> None:
        fast = self.branch.split("      Else\n", 1)[0]
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


if __name__ == "__main__":
    unittest.main()
