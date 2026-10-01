# Current-tree Pi 4 Vulkan/Neon 15-scene proof

The current Anvil Vulkan and Neon renderer completed all 15 native reference
scenes on a Raspberry Pi 4 running monitor build 223 (CRC32 `5BC668D0`). The
returning RAM payload used the public Vulkan objects and `NeonVkChrome`
adapter; it did not paint the final pixels with the CPU. Its 256-byte report
passes the existing 124-check widget report oracle, including 47 recorded
draws, 654 vertices, one display DMA presentation, zero processor fallback,
zero native faults, and the 3,505-box capacity marker.

The payload returned `x0=0x009C6F38` in 11.185 seconds with a confirmed
15-second deadman. A 262,144-byte RAM slab was read in four CRC-verified
network chunks. The host checker reorders the slab's occupied 16-KiB scene
slots into native scene order and compares all 245,760 bytes to the pinned
golden corpus. Every byte matched. The source captures boxes first at
`0x07000000` and the scene-0 clear later at `0x07034000`; the checker preserves
that distinction and rejects a swapped-slot or mutated-scene capture.

Recheck the committed evidence with:

```text
python tools/vulkan_neon_all15_corpus_check.py --self-test --slab docs/evidence/vulkan-neon-all15-current-20261001/slab.bin --report docs/evidence/vulkan-neon-all15-current-20261001/report.bin
python tools/vulkan_neon_widget_proof_check.py --report docs/evidence/vulkan-neon-all15-current-20261001/report.bin
```

The first command passes 737,282 byte and report checks; the second passes
124 report/source checks. The exact source, payload digest, report and slab
digests, and run conditions are in
`docs/evidence/vulkan-neon-all15-current-20261001/manifest.json`.

This is Pi 4 hardware evidence for the implemented graphics path. The
3,505 boxes are batched into a single Vulkan draw; this proof does not establish
3,505 individual draw-list records or another board's backend. The monitor
was not replaced, no storage was written, and no display screenshot was
taken. The board returned to build 223 at `pmf>` with Vulkan screen mode,
deadman off, capture disarmed, and no secondary-core leases.
