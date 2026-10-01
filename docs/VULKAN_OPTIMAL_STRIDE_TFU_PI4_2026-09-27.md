# Pi 4 Vulkan optimal-image upload from padded rows

On 2026-09-27, `vkCmdCopyBufferToImage` uploaded one complete 8×8 BGRA8
optimal-tiled atlas from a transfer buffer with `bufferRowLength=16`. Each
eight-texel image row was separated by eight poison-green texels in memory.
The command now passes its recorded buffer pitch to the V3D texture
formatting unit (TFU), which converts the raster source to UIF tiling. V3D
then sampled the atlas in eight ordered draws. The CPU prepared the source
and commands; it did not repack or copy the image pixels.

The public atlas/chrome diagnostic was updated to declare its Pi 4 chip and
include the DMA service required by the current backend. The IDE compiler
produced a 1,094,336-byte PMFBOOT v2 payload at RAM load `$600000`, SHA-256
`9CA7480B29D7868A8A9E2F4D5719F68290D5844DE3A3AC1A4C89FBB3E75DD8A3`.
The resident build-210 monitor verified the uploaded bytes and entered the
payload under a 15-second deadman. It returned the expected report pointer
`x0=$8208C8`. The host read all 960 report bytes, and capture 57 is a fresh
1280×800 screenshot of the 800×1280 rotated panel. The acceptance checker
rotated that capture to panel coordinates and passed 213 exact checks over
the public source, report, and pixel regions. These include transparent,
covered, clipped and untouched atlas pixels; reading the poison padding
instead of the declared row stride would fail the image oracle.

The first RAM run supplied the runner's default `x0=0` expectation, so the
runner marked its intentional report-pointer return as a mismatch. A second
run used the measured pointer as the expectation and captured the report in
the same transaction; that run passed. No flash, reset or boot-medium write
occurred. The resident Vulkan console was restored afterward, with deadman
off, capture disarmed, zero secondary-core leases, and the board released.

Reviewable evidence is in
`docs/evidence/vulkan-optimal-stride-20260927/`: the successful run's JSON,
PNG capture (SHA-256
`F71F38F67389BA2EDB41A662402797B93DF510931092348FFAEE343EFA8B0E86`),
960-byte report (SHA-256
`01E44B4606EDFD814748656BD499BE848B3CE952DE4F8D4A860AF015F41A3134`),
compressed console transcript, and compressed panel-oriented raw BGRA pixels.
The raw panel pixels have SHA-256
`7C1A6805B3C97A5F27372567B2C38D0569F6B70C83961CF22751277893F2E46C`.

The production V3D backend gate passed 85 checks over 4,404,360
interpreted AArch64 instructions and compiled all eight current Pi 4 board
diagnostics. The normal Pi 4 image compiled at 4,327,804 bytes on the
combined tree, and its generated source build stamp was restored. The
standalone atlas acceptance checker also passed its synthetic fixture.
The full public pipeline gate passed 772 checks over 203,706,551 interpreted
AArch64 instructions. Its optimal-image command fixture verified that an
18-texel source row reaches the backend as a 72-byte TFU pitch, while a
16-texel row is refused for a 17-texel-wide image.

The TFU route remains one complete image, one mip, one layer, one sample and one BGRA8 format. A separate partial buffer-to-optimal upload accepts up to two separate one-region calls per command buffer to the same optimal BGRA8 image. Buffer offsets are 64-byte aligned; tight or padded row pitch uses the exact last-row source span; destination offsets and extents align to 4×4 utiles. Source byte spans and destination rectangles must be disjoint, with at most 256 utiles combined. The full command stream is preflighted before guarded DMA dispatch, then calls execute in recorded order behind `BUFFER_TO_TILED_RECT_COPY`. Desk checks reject a 257-tile aggregate before backend work; an exact 256-tile aggregate is not separately tested. The 2026-09-30 Pi 4 proof replaced 32 destination texels and preserved 224; it checked 288 source words including 48 source-padding words, 64 readback-padding words and 128 guard words. TFU stayed at 1, DMA advanced 0→2 and jobs 1→3; a later readback advanced DMA 2→18. A misaligned second operation returned `-20005` during recording before submit or DMA. See `docs/evidence/vulkan-two-partial-optimal-uploads-pi4-20260930/README.md`. The established full-image TFU upload is unchanged; other boards do not advertise the partial capability. Edge-tail extension: destination XY remains 4-aligned; a width or height not divisible by four is accepted only when that rectangle reaches the matching image right or bottom edge. The backend clamps each 4×4 UIF tile to its valid columns and rows, issuing guarded DMA for only `validColumns * 4` bytes across `validRows`; this preserves neighboring texels and padded storage. It requires both `BUFFER_TO_TILED_RECT_COPY` and the separate `BUFFER_TO_TILED_TAIL_COPY` capability. Up to two calls remain allowed, with disjoint rectangles and source spans and a cumulative limit of 256 `ceil(width/4) * ceil(height/4)` tiles. Source bounds remain `(height - 1) * pitch + width * 4`, with DMA row-skip bounds checked for the smallest tail row. The complete stream and every tile address/span are preflighted before DMA. Full-image TFU uploads remain unchanged; other boards fail closed. The 2026-09-30 Pi 4 proof changed 25 texels, left 196 valid texels untouched, and preserved 291 padded UIF backing words outside the copy. It checked 246 source words including 54 source-padding words, 91 readback-padding words and 92 guards. TFU stayed at 1, DMA advanced 0→4 and jobs 1→2; later readback advanced DMA 4→24. A non-edge 5×5 request returned `-20005` during recording before more DMA. MMU, OOM and native faults were zero, with one intentional validation fault. Submit-time malformed-stream preflight remains desk-gate evidence. See `docs/evidence/vulkan-optimal-upload-edge-tail-pi4-20260930/README.md`. One-utile micro upload: a separate guarded-DMA shape accepts a 1–4 by 1–4 BGRA8 rectangle wholly contained in one 4×4 UIF utile, including an unaligned interior pixel origin. It writes only the requested row bytes and rows, preserving the other texels in that utile. It requires both `BUFFER_TO_TILED_RECT_COPY` and `BUFFER_TO_TILED_MICRO_COPY`; a micro upload is isolated from other buffer-to-image operations in its command buffer. Buffer offsets remain 64-byte aligned, source bounds use `(height - 1) * pitch + width * 4`, and source/image alias, row-stride, utile and guarded-window bounds are preflighted before DMA. Other boards do not advertise this capability. The 2026-09-30 Pi 4 proof changed six requested texels and preserved 250, including ten same-utile neighbors; checks covered 272 source words (262 payload and ten padding words), 64 readback-padding words and 96 guards. TFU stayed at 1, DMA advanced 0→1 and jobs 1→2. A crossing-utile request returned `-20005` during recording. MMU, OOM and native fault counts were zero. See `docs/evidence/vulkan-buffer-optimal-microrect-pi4-20260930/README.md`. Submit-time malformed-stream preflight remains desk-gate evidence. A separate two-call Pi 4 proof used a 13×13 target: 17 texels changed, 152 valid texels remained unchanged, and 343 padded UIF backing words outside the copies were preserved. It checked 186 source words including 58 source-padding words, 39 readback-padding words and 112 guards. TFU stayed at 1, DMA advanced 0→2 and jobs 1→3; later readback advanced DMA 2→18. A non-edge second call returned `-20005` during recording before DMA. Submit-time malformed-second preflight is proven by signed desk regression only. See `docs/evidence/vulkan-optimal-upload-edge-tail-pi4-20260930/README.md` (`two-call-report.bin`). Multiple optimal regions per call and format conversion remain unsupported.
