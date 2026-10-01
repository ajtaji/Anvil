# Pi 4 partial optimal-image copy at 256 tiles

Three RAM-only Pi 4 runs exercised public `vkCmdCopyImage` between distinct 72×64 BGRA8 optimal images. Two full-image TFU uploads established different source and destination patterns before each partial copy. The copied rectangle began at source `(0,0)` and destination `(8,0)`, was 64 texels high, and was 16, 32, or 64 texels wide. Those widths cover 64, 128, and exactly 256 complete 4×4 UIF tiles.

The diagnostic checked all 4,608 logical texels in each TFU baseline with an independent UIF offset calculation. After the copy, it checked all source and destination texels, both padded UIF regions, 256 image guard words, 48 staging guard words, and disjoint mapped allocation ranges. At the 256-tile limit, 4,096 destination texels matched the source pattern and 512 destination texels retained their prior pattern. The source image remained unchanged. Copy-time TFU count stayed fixed; guarded DMA increased by the tile budget and backend jobs increased by one. Fault and status checks passed.

| Tiles | Changed / untouched destination texels | Copy DMA | Full payload time | Report SHA-256 |
| ---: | ---: | ---: | ---: | --- |
| 64 | 1,024 / 3,584 | +64 | 1.276319 s | `7189E58C2BA4D194B96A7058C737C694586A30647D5AA60BC8A1688D1E193C75` |
| 128 | 2,048 / 2,560 | +128 | 1.283279 s | `3AB34B1F3C7AD21ADC0EE24266B9B973ACEFEC00338E9666858E707C1C1C5679` |
| 256 | 4,096 / 512 | +256 | 1.297342 s | `8A5D1B10555FB6114E09C6EFFBC77C86C3E4971450662367971E46907F82CA05` |

The 1,056-byte reports are [report64.bin](report64.bin), [report128.bin](report128.bin), and [report256.bin](report256.bin). Each passed `tools/vulkan_partial_optimal_256_copy_check.py` with 169 hostile and anchor checks. The committed diagnostic is `RaspberryPi4/Examples/Diagnostics/vulkanPartialOptimalCopy256Proof.pi4`; the 64- and 128-tile variants differ only in `#COPY_TILES`. The signed PMF SHA-256 values for 64, 128, and 256 tiles are `9AC89AFDF152D79C7AD2A823B5631F77BE32FD56C94F37E931D4B10E246D40F4`, `4D5F2E9FAF6BE7B0E699170889BB055EF5BC2C20FA1B494DFA9041394600ED8D`, and `2F069C66A06D7E287F33002CE0003CF586B6AD0D6B646AA008F37D3D3C5E88F3`.

All runs used resident Pi 4 Anvil build 223 with a confirmed 15-second deadman and no screenshot. The board returned to its prompt with the Vulkan screen restored. No boot image or storage was changed. This evidence establishes the bounded Pi 4 path only; it does not claim acceleration on another board.
