# Pi 4 partial optimal-image readback R2

The 992-byte `report.bin` is the returning Pi 4 R2 trace from 2026-09-30. Its SHA-256 is `FEF8935E8C79DC92BAB72B8CED93BA038CAE822B1ABC8E6E188EA238A527C766`. The tested payload container SHA-256 is `3FD6CF44817F28083DB1D7DE1C01D96741D15D5856301FF30EF518E0924EAF05`.

The report returned pointer `0x9408C8`. All scene-status verdicts were zero. The aligned partial readback matched 16 texel words; 16 padding words and 32 guard words remained unchanged. DMA advanced from 0 to 1; TFU advanced from 0 to 6; bin and render counters advanced from 3 to 4. The unaligned request was refused with `-20005`. MMU, out-of-memory and native-fault verdicts were zero.

This proves the bounded 4x4-utile-aligned Pi 4 BGRA8 partial readback and its refusal case. Edge tails, other formats, mips and layers are not established by this trace. The full-image odd-extent result is recorded separately in `../../VULKAN_OPTIMAL_IMAGE_BUFFER_DMA_PI4_2026-09-27.md`.
