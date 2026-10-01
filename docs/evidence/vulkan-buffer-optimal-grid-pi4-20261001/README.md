# Pi 4 buffer-to-optimal two-by-two UIF grid upload

The report is a 1,056-byte Pi 4 trace. SHA-256: `6777FB6DC5383E4669B93F31D49554F7D45E2FAE1898864D7A89BCCCB4BA71FE`.

One `vkCmdCopyBufferToImage` region at destination `(3,3)` with extent `5×5` crossed four UIF tiles with intersections of `1×1`, `4×1`, `1×4` and `4×4`. The upload changed 25 destination texels and preserved 231, including 39 neighbors within the touched grid. Checks covered 25 exact source words plus 327 sentinels, including 15 source-padding words, 64 oracle-padding words and 96 guards. TFU stayed at 1, DMA advanced 0→4, and jobs 1→2; a later oracle readback advanced DMA 4→20. A `6×6` request spanning more than a two-by-two tile grid returned `-20005` during recording. MMU, OOM and native fault counts were zero.

The route uses guarded DMA behind `BUFFER_TO_TILED_GRID_COPY` and preflights all tile intersections before dispatch. Submit-time malformed-stream preflight is desk-gate evidence only. Other backends do not advertise this capability.
