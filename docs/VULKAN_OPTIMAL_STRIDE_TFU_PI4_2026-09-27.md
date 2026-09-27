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

This is one complete image, one mip, one layer, one sample and one BGRA8
format. Partial optimal regions, multiple optimal copies in a submission,
and format conversion remain outside the supported path.
