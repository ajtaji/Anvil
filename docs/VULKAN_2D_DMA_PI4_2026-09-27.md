# Pi 4 Vulkan strided image transfers through 2D DMA

On 2026-09-27, the supported linear BGRA8 `vkCmdCopyImage`,
`vkCmdCopyImageToBuffer`, and `vkCmdCopyBufferToImage` row transfers were
lowered to Pi 4 two-dimensional DMA. A tightly contiguous rectangle still
uses one linear DMA copy. A strided rectangle whose row width, row count,
source gap and destination gap fit the DMA control block uses one 2D
submission, with hardware advancing both row pointers. Larger gaps or
conservatively overlapping address spans retain the guarded one-dimensional
DMA row path. The CPU validates and submits work; it does not copy the image
pixels.

The new `HwVkDmaCopyRows` wrapper checks the full destination span against
the Vulkan heap write window before work starts. It cleans source and
destination cache ranges, submits `DmaCopy2D`, invalidates the destination,
and restores the display channel's prior write bounds. A failed DMA or
bounds restoration fails the Vulkan submission. The existing command
preflight still checks every recorded source and destination row before
starting any DMA.

The returning Pi 4 diagnostic exercised whole and rectangular copies,
padded buffer rows, two-region arrays, and separate ordered calls in both
buffer-image directions. It checked copied and untouched pixels and buffer
bytes, DMA quiescence, and restored DMA bounds at each stage. Its assertions
now require one DMA submission per supported rectangle: 19 across the full
suite, compared with 122 in the previous per-row implementation for those
same shapes. This is a count of hardware submissions, not a benchmark of
elapsed rendering time.

The IDE compiler produced a 669,652-byte PMFBOOT v2 RAM payload, SHA-256
`DA1879593E4EFB6E078D6074E189A5984D149ED494B82F8C42DE6B85B22B53F7`.
The resident build-210 monitor verified and entered it at `$600000` under
a 15-second deadman. The complete diagnostic returned `x0=0` and fresh
capture 59, whose PNG SHA-256 is
`F59BD6B91DC43980A71C8D3AD4859F7A43753A4BAB2182799E11F3EB7CE0EE19`.
The resident Vulkan console was restored, deadman and capture were disarmed,
coretest leases were zero, and the board was released. No flash, reset or
boot-medium write occurred.

The first RAM run returned status 100 after the single 8×8 image-copy
stage: its counter assertion had been changed to expect two DMA submissions
even though that stage records one rectangle. The assertion was corrected to
one, the payload rebuilt, and the complete rerun passed. Both run records
and compressed console transcripts are preserved under
`docs/evidence/vulkan-2d-dma-20260927/`.

The production V3D backend gate passed 85 checks over 4,404,360
interpreted AArch64 instructions and compiled all eight current Pi 4
diagnostics. The normal Pi 4 image compiled at 4,329,848 bytes on the
combined tree; its generated source build stamp was restored.
