"""Source-level desk gate for the paired returning 10k timing harness."""

import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE / "vulkanNeonParticleMatchedProfileCore.pi4"


class MatchedProfileGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.core = CORE.read_text()

    def test_wrappers_include_one_core_with_distinct_modes(self) -> None:
        for name, mode in (("Cpu", 0), ("Csd", 1)):
            text = (HERE / f"vulkanNeonParticleMatched{name}Profile.pi4").read_text()
            self.assertIn(f"#NMP_GPU = {mode}", text)
            self.assertIn('XIncludeFile "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleMatchedProfileCore.pi4"', text)

    def test_same_capacity_workload_and_frame_loop(self) -> None:
        source = self.core
        self.assertIn("#NGP_ITEMS = 10000", source)
        self.assertIn("#NGP_W = 800", source)
        self.assertIn("#NGP_H = 800", source)
        self.assertEqual(source.count("NeonVkChromeCreateWithCapacities("), 1)
        self.assertIn("#NGP_W, #NGP_H, 4, #NGP_ITEMS)", source)
        self.assertIn("For frame = 0 To #NGP_WARMUP + #NGP_SAMPLES - 1", source)
        self.assertIn("vkDeviceWaitIdle(ngpDev)", source)
        self.assertIn("NeonVkChromeParticlesPrepare(@ngpParticles[0], #NGP_ITEMS)", source)
        self.assertIn("NeonVkParticleCsdPrepare(@ngpParticles[0], #NGP_ITEMS)", source)
        self.assertIn("NeonVkChromeParticlesDrawPrepared()", source)
        self.assertIn("NeonVkParticleCsdDraw()", source)
        self.assertIn("NeonVkChromeVertexCount() <> #NGP_ITEMS * 6", source)
        self.assertEqual(source.count("rc = ngpCheckPixels()"), 1)

    def test_deadman_budgets_and_uncertain_paths(self) -> None:
        source = self.core
        values = {name: int(value) for name, value in
                  re.findall(r"#NGP_(SETUP|FRAME|PIXEL)_BUDGET_US = (\d+)", source)}
        self.assertEqual(values, {"SETUP": 5_000_000, "FRAME": 10_000_000,
                                  "PIXEL": 11_000_000})
        self.assertIn("ngpReport[15] > 14000000", source)
        self.assertLess(14_000_000, 15_000_000)
        self.assertIn("If nvpcState = #NVPC_LOST : ProcedureReturn ngpUnsafe(41)", source)
        self.assertIn("If rc <> #VK_SUCCESS : ProcedureReturn ngpUnsafe(26)", source)
        self.assertIn("If vkDeviceWaitIdle(ngpDev) <> #VK_SUCCESS : ProcedureReturn ngpUnsafe(40)", source)
        self.assertIn("nvcInFrame <> 0 Or nvcFrameAbortable <> 0", source)
        self.assertIn("Repeat\n    V3dBarrier()\n  ForEver", source)


if __name__ == "__main__":
    unittest.main()
