# Pi 4 partial linear-to-optimal image copy evidence — 2026-09-30

`report.bin` is the 1,056-byte hardware report trace.

- Trace SHA-256: `7C80275667CC76AAEBFF5A081A218CFB36E23B16F52EE065FAA90E879332F775`
- Payload SHA-256: `7CC671AA77F73523F8705173C39812F64BCCFC24B8E6D9251AF853ABE9BE9C3A`
- Result: 16 copied texels matched, 240 destination texels remained unchanged, and all 256 source texels matched. The report checked 64 padding words and 96 guard words.
- Counters: TFU 1→1, DMA 0→1, backend jobs 1→2. A later readback advanced DMA 1→17.
- Negative case: a misaligned destination returned `-20005` before readback.
- Faults: MMU 0, OOM 0, native faults 0; one intentional validation fault.

This proves only the bounded Pi 4 path. Other board backends do not advertise this capability.