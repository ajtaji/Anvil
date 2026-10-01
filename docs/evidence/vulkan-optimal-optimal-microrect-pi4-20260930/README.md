# Pi 4 optimal-to-optimal one-utile microcopy

The 2026-09-30 Pi 4 run exercised one partial `vkCmdCopyImage` rectangle between distinct level-zero BGRA8 optimal images. The source and destination rectangles used independent local positions within their respective 4×4 UIF utiles. Four destination texels changed and 252 remained untouched, including twelve neighbors in the destination utile; all 256 source texels remained unchanged. The checker verified 64 padding words in each readback and 128 guard words.

The partial operation advanced guarded DMA from 0 to 1 and backend jobs from 2 to 3; TFU remained at 2. A source rectangle crossing a UIF utile was refused during recording with `-20005`. MMU, OOM and native fault counts were zero. The microcopy ran as the isolated transfer operation. Submit-time malformed-stream preflight remains desk-gate evidence, separate from this hardware run.

The proof payload is `report.bin` (1,056 bytes), SHA-256 `0B17299952641158E746886EC18A3A2010B3743EB095265925191254EFE298ED`. The frozen PMF was 785,768 bytes, SHA-256 `607E8046486EB47FBE26995E6898B1BFA5A45222D6311B6B24242465797A3140`.
