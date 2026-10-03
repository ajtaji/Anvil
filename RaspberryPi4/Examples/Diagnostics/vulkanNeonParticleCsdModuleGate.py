"""Desk gate for the opt-in Pi 4 particle producer's layout and ownership."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "Anvil/Graphics/Vulkan/neon_vk_particle_csd.pi4"
CHROME = ROOT / "Anvil/Graphics/Vulkan/neon_vk_chrome.pi4"
SMALL_PROOF = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdModuleProof.pi4"
PROFILE = ROOT / "RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdModule10kProfile.pi4"


def procedure(source: str, name: str) -> str:
    match = re.search(rf"^Procedure(?:\.i)? {re.escape(name)}\([^\n]*\).*?^EndProcedure",
                      source, flags=re.MULTILINE | re.DOTALL)
    assert match, f"missing {name}"
    return match.group()


class ModuleGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MODULE.read_text()
        cls.chrome = CHROME.read_text()

    def test_all_counts_have_disjoint_in_bounds_lanes(self) -> None:
        for count in (1, 15, 16, 17, 31, 32, 127, 128, 129, 9999, 10000):
            padded = (count + 15) // 16 * 16
            indices = [group * 16 + lane for group in range(padded // 16)
                       for lane in range(16)]
            self.assertEqual(indices, list(range(padded)))
            input_bytes = ((padded * 48 + 4095) // 4096 + 1) * 4096
            output_bytes = ((padded * 144 + 4095) // 4096 + 1) * 4096
            self.assertLessEqual((indices[-1] + 1) * 48, input_bytes - 4096)
            self.assertLessEqual((indices[-1] + 1) * 144, output_bytes - 4096)
            self.assertLessEqual(count * 6 * 24, padded * 144)

    def test_emitted_order_and_palette_words_match_chrome(self) -> None:
        shader = procedure(self.source, "nvpcBuildShader")
        vertices = [(int(x), int(y)) for x, y in
                    re.findall(r"r = nvpcStoreVertex\((\d+), (\d+)\)", shader)]
        self.assertEqual(vertices, [(0, 1), (4, 5), (6, 7),
                                    (0, 1), (6, 7), (2, 3)])
        store = procedure(self.source, "nvpcStoreVertex")
        self.assertIn("nvpcStoreWord(8)", store)
        self.assertIn("nvpcStoreWord(9)", store)
        stage = procedure(self.source, "nvpcStageRecords")
        for token in ("nvcParticleCornerBits", "nvcParticleU[", "nvcParticleV["):
            self.assertIn(token, stage)

    def test_attach_quarantine_idle_release_order(self) -> None:
        create = procedure(self.source, "NeonVkParticleCsdCreate")
        self.assertLess(create.index("vkDeviceWaitIdle"),
                        create.index("NeonVkChromeExternalProducerAttach"))
        self.assertLess(create.index("NeonVkChromeExternalProducerAttach"),
                        create.index("nvcBufferCreate"))
        self.assertIn("nvcMaxQuads < 1", create)
        self.assertNotIn("nvcMaxVertexQuads < capacity", create)
        prepare = procedure(self.source, "NeonVkParticleCsdPrepare")
        ordered = ("vkDeviceWaitIdle", "NeonVkChromeParticlesPrepare",
                   "NeonVkChromeExternalProducerQuarantine", "V3dCsdSubmit",
                   "V3dCsdWait", "V3dCsdCleanResult", "V3dCacheRange(nvpcVertexAddr",
                   "NeonVkChromeExternalProducerUnquarantine", "nvpcState = #NVPC_GPU_READY")
        positions = [prepare.rindex(token) if token == "nvpcState = #NVPC_GPU_READY"
                     else prepare.index(token) for token in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertGreaterEqual(prepare.count("nvpcState = #NVPC_LOST"), 3)
        release = procedure(self.source, "NeonVkParticleCsdRelease")
        self.assertIn("nvcFrameAbortable <> 0", release)
        self.assertLess(release.index("nvcFrameAbortable <> 0"), release.index("vkDeviceWaitIdle"))
        self.assertLess(release.index("vkDeviceWaitIdle"),
                        release.index("nvpcDestroyOwned"))
        self.assertLess(release.index("nvpcDestroyOwned"),
                        release.index("NeonVkChromeExternalProducerDetach"))
        destroy = procedure(self.chrome, "NeonVkChromeDestroy")
        self.assertIn("nvcExternalProducerAttached <> 0 Or nvcExternalProducerQuarantined <> 0", destroy)

    def test_external_capacity_is_separate_from_shared_vertex_capacity(self) -> None:
        small = procedure(SMALL_PROOF.read_text(), "Main")
        profile = procedure(PROFILE.read_text(), "Main")
        self.assertIn("#NGP_W, #NGP_H, 4, 4)", small)
        self.assertIn("NeonVkParticleCsdCreate(#NGP_ITEMS)", small)
        self.assertIn("#NGP_W, #NGP_H, 4, 1)", profile)
        self.assertIn("NeonVkParticleCsdCreate(#NGP_ITEMS)", profile)

    def test_uncertain_idle_and_palette_failures_quarantine_and_stick(self) -> None:
        mark = procedure(self.source, "nvpcMarkLost")
        self.assertIn("NeonVkChromeExternalProducerQuarantine()", mark)
        self.assertIn("nvpcAttached <> 0", mark)
        self.assertIn("If rc <> #NEON_VK_CHROME_OK", mark)
        self.assertNotIn("nvcExternalProducerAttached <> 0", mark)
        self.assertIn("nvcExternalProducerQuarantined = 1", mark)
        self.assertLess(mark.index("nvcExternalProducerQuarantined = 1"),
                        mark.index("nvpcState = #NVPC_LOST"))
        prepare = procedure(self.source, "NeonVkParticleCsdPrepare")
        self.assertEqual(prepare.count("If rc <> #VK_SUCCESS : ProcedureReturn nvpcMarkLost()"), 2)
        self.assertIn("If rc = #NEON_VK_CHROME_ERR_ARGS : ProcedureReturn #NVPC_ERR_ARGS", prepare)
        self.assertIn("If rc <> #NEON_VK_CHROME_OK : ProcedureReturn nvpcMarkLost()", prepare)
        release = procedure(self.source, "NeonVkParticleCsdRelease")
        self.assertIn("If rc <> #VK_SUCCESS : ProcedureReturn nvpcMarkLost()", release)
        self.assertLess(release.index("nvpcMarkLost()"), release.index("nvpcDestroyOwned()"))


if __name__ == "__main__":
    unittest.main()
