# Pi 4 optimal-to-linear one-utile microcopy

The report is a 1,056-byte Pi 4 trace. SHA-256: `6B5CDB36CE27C95C796CD71D52989D1149556ECFA1D78E9A0C378A3AFD254803`.

The guarded DMA microcopy changed 4 destination texels and preserved 252; the 256-texel source remained unchanged, including 12 neighbors in the same utile. The measured linear destination pitch was 64 bytes, so the copied row had zero padding. Separate checks covered 64 padded oracle words and 96 guard words. DMA advanced 0→1, backend jobs 1→2, and TFU remained at 1. A source crossing the one-utile boundary was refused during recording with `-20005`. MMU, OOM and native fault counts were zero.

The separate submit-time whole-stream preflight check is desk-only; this trace proves the one-operation silicon shape. Other backends do not advertise this capability.
