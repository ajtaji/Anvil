# Current-tree Pi 4 Vulkan/Neon 15-scene proof

The current Anvil Vulkan and Neon renderer completed all 15 native reference
scenes on a Raspberry Pi 4 running monitor build 242. The returning RAM payload
used the public Vulkan objects and `NeonVkChrome` adapter; it did not paint the
final pixels with the CPU. Its 256-byte report passed 124 widget checks:
47 draws, 654 vertices, one display DMA operation, zero processor fallback,
zero native faults, and the 3,505-box capacity marker.

The 1,532,312-byte payload container returned `x0=0x009E6F60` in 12.235 seconds
under a confirmed 15-second deadman. A 262,144-byte slab was read over Wi-Fi
in one CRC-verified chunk. The host checker reorders its occupied 16-KiB scene
slots into native scene order and compares all 245,760 bytes with the pinned
golden corpus. Every byte matched. The source captures boxes first at
`0x07000000` and the scene-0 clear later at `0x07034000`; the checker rejects
a swapped-slot or mutated-scene capture. A screenshot of the returned frame
was captured and is included with the report and slab.

Recheck the committed evidence with:

```text
python tools/vulkan_neon_all15_corpus_check.py --self-test --slab docs/evidence/vulkan-neon-all15-build242-20261002/slab.bin --report docs/evidence/vulkan-neon-all15-build242-20261002/report.bin
python tools/vulkan_neon_widget_proof_check.py --report docs/evidence/vulkan-neon-all15-build242-20261002/report.bin
```

The exact source and payload digests, board conditions, report, slab, and
screenshot digests are in
`docs/evidence/vulkan-neon-all15-build242-20261002/manifest.json`.

A later source-parity run fed lowercase `project` to the Neon panel procedure
and kept the desktop engine's uppercase `PROJECT` output. Its current source
compiled and the Pi 4 again matched all 245,760 native reference pixel bytes
and passed all 124 widget checks. The draw-side TrueType layout now uses the
same single-line width rule as its measurement callback. This edge-positioned
text behavior was code-reviewed and compiled but is outside the 15 pixel
scenes. Capture and source hashes are in
`docs/evidence/neon-source-parity-build242-20261002/manifest.json`.

This is Pi 4 hardware evidence for Anvil's implemented Neon-derived graphics
path, not a proof of desktop Neon Arcade Vulkan support or another board's
backend. The 3,505 boxes are batched into one Vulkan draw; this proof does not
establish 3,505 individual draw-list records. The monitor was not replaced and
no storage was written. The board returned to build 242 at `pmf>` with its
Vulkan console still selected and the deadman off.
