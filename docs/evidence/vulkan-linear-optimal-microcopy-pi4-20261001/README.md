# Pi 4 linear-to-optimal one-utile microcopy

The report is a 1,056-byte Pi 4 trace. SHA-256: `0F7FD1099BA4A2B8DC06B4E2A3208AFBC45E98C27D4E1EB3FCB02C65A3D6FADF`.

The guarded DMA microcopy changed 4 destination texels and preserved 252, including twelve same-utile neighbors; all 256 source texels remained unchanged. The linear source pitch was 64 bytes with zero row padding. The measured source byte offset and accessed span were 332 and 72 bytes; the destination UIF offset was 1,316 bytes. Separate checks covered 64 padded oracle words and 96 guard words. TFU remained at 1, DMA advanced 0→1, and backend jobs advanced 1→2. A destination rectangle crossing a utile was refused during recording with `-20005`, before DMA. MMU, OOM and native fault counts were zero.

Submit-time whole-stream preflight is desk-gate evidence only; this trace proves the one-operation silicon shape. Other backends do not advertise this capability.
