# Pi 4 Vulkan optimal-to-linear image readback — 2026-09-27

`vkCmdCopyImage` now accepts one complete, equal-size, level-zero BGRA8
region from a distinct `UIF_NO_XOR` optimal image into a linear image.
The command layer checks both bound allocations, usage, layouts, full
extent and overlap before recording. Submission revalidates the physical
layout and mapped ranges before any transfer in the stream begins.
Partial optimal regions remain explicitly unsupported.

The TFU cannot emit raster output. The Pi 4 backend therefore calculates
the address of each 4×4 utile and uses guarded 2D DMA to place its rows
in the linear image. Edge utiles use their actual width and height.
The CPU configures DMA and checks bounds; it does not copy texels. Each
DMA operation restores the display controller's original write bounds.
If a hardware transfer fails, the command buffer is invalidated and its
fence signalled with device loss.

Two returning RAM payloads passed on Pi 4 build 223 at `192.168.1.111`:

- The atlas diagnostic copied an 8×8 optimal image into linear memory,
  mapped it, and matched all 64 BGRA words to the original staging atlas.
  It returned report pointer `0x9308C8`; the report's status word was
  zero. Capture 120 preserved the original rendered atlas.
- The readback diagnostic uploaded a 37×13 pattern through TFU, then
  copied it from optimal to linear in the same transfer command buffer.
  It checked all 481 BGRA words and exactly 40 guarded DMA operations,
  including partial edge utiles and UIF block-column/height boundaries.
  Before that valid copy, a 36×13 partial request returned
  `ANVIL_VK_ERR_UNSUPPORTED` during recording without starting DMA.
  The final payload returned `x0=0` in 2.6 seconds; capture 122 is saved.

Both uploads were SHA-256 verified on the board, staged at `0x700000`,
and entered under a 15-second deadman. They were RAM-only: no boot-medium
write, reset or flash occurred. The resident build 223 monitor returned
to `pmf>` and the Vulkan console was restored after each run. The
PMFBOOT payloads, screenshots, run metadata, transcripts and compiler
logs are in `docs/evidence/vulkan-tiled-readback-20260927/`.

The normal Pi 4 build succeeded as build 224, 4,375,368 bytes, SHA-256
`608083325d07c81a2192348ecec3f0e7cfc738d369734c7f29af20c3ca71537c`.
The production backend gate passed 92 checks over 4,408,938 interpreted
AArch64 instructions. The broad public pipeline gate passed 813 checks
over 204,188,143 instructions. Build 224 has not been installed; the
Pi 4 remains on build 223.

The current implementation issues one DMA job per 4×4 utile, so large
images may be slow. It does not yet handle optimal-to-buffer readback,
partial optimal regions, mip levels, array layers or format conversion.
