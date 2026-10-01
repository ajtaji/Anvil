# Pi 4 partial buffer-to-optimal image upload evidence — 2026-09-30

`report.bin` is the 1,056-byte hardware report trace.

- Trace SHA-256: `F5AA32F7233442701DAF68BC626456518B7CE3B676E1445A6190A11844A06DE8`
- Payload SHA-256: `FEB8E05EEBF7067B898ABBA3CDBBF5DF62C2EBD066CBAD84B441C917B534C84D`
- Result: 16 destination texels were replaced and 240 remained unchanged. The source checks covered 272 words, including 16 padding words. Readback checked 64 padding and 96 guard checks.
- Counters: TFU 1→1, DMA 0→1, backend jobs 1→2. A later readback advanced DMA 1→17.
- Negative case: destination offset `(2,8)` returned `-20005` before readback.
- Faults: MMU 0, OOM 0, native faults 0; one intentional validation fault.

This proves only the bounded Pi 4 path. Other board backends do not advertise this capability.