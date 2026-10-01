# Pi 4 optimal-to-buffer one-utile micro-readback

The 2026-10-01 Pi 4 run exercised one interior `vkCmdCopyImageToBuffer` region from a level-zero BGRA8 optimal image. The region stayed within one source 4×4 UIF utile and wrote through pitched destination rows. Four requested texel words matched exactly; twelve destination row-padding checks passed. All 256 source texels remained unchanged, including twelve same-utile neighbors. The full-image readback padding check passed 64 entries; stage-spare checks passed 16 entries, and all 128 guards remained intact.

The partial operation advanced guarded DMA from 0 to 1 and backend jobs from 1 to 2; TFU remained at 1. A source-utile-crossing request was refused during recording with `-20005`. MMU, OOM and native fault counts were zero. Submit-time malformed-stream preflight is separate desk-gate evidence and was not established by this isolated hardware transaction.

The proof payload is `report.bin` (1,056 bytes), SHA-256 `08D276C0CA3ABCDF72E6C936725E9F57A1A10EE7B22629B0B192CEA2F452B576`. The frozen PMF was 766,744 bytes, SHA-256 `2FE9E5511B6EF5EDB17135E74F2CF0B7F67CAF274CC7363443B759F768B1434D`.
