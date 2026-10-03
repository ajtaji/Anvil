# Neon source parity on Pi 4 build 242

This returning RAM payload uses the current `RaspberryPi4/Lib/neon.pi4`
compositions and `Anvil/Graphics/Vulkan/neon_vk_chrome.pi4` renderer. The panel
scene passes lowercase `project`, following the desktop Neon Arcade panel
procedure's uppercase-title behavior. The 15-scene capture still matches all
245,760 native reference pixel bytes. The widget report passes 124 checks:
47 draws, 654 vertices, one display DMA operation, zero processor fallback,
and zero native faults.

The `.pmf.pmf` payload returned its expected value in 12.3 seconds under a
confirmed 15-second deadman. The 262,144-byte RAM slab was read in one
CRC-verified chunk. The monitor returned to its prompt with the deadman off.
No monitor image, boot medium, or filesystem was changed.

Recheck the captured data with:

```text
python tools/vulkan_neon_all15_corpus_check.py --self-test --slab docs/evidence/neon-source-parity-build242-20261002/slab.bin --report docs/evidence/neon-source-parity-build242-20261002/report.bin
python tools/vulkan_neon_widget_proof_check.py --report docs/evidence/neon-source-parity-build242-20261002/report.bin
```

`manifest.json` records the source, payload, and capture digests. The exact
pixel proof covers the existing Pi 4 scenes. It does not exercise every
Unicode glyph, edge-positioned text run, or another board's renderer.
