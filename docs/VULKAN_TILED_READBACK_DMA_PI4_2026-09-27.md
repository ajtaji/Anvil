# Pi 4 Vulkan optimal-to-linear image readback — 2026-09-27

`vkCmdCopyImage` now accepts one complete, equal-size, level-zero BGRA8
region from a distinct `UIF_NO_XOR` optimal image into a linear image.
The command layer checks both bound allocations, usage, layouts, full
extent and overlap before recording. Submission revalidates the physical
layout and mapped ranges before any transfer in the stream begins. This
2026-09-27 hardware result covers the complete-image path described here.

A later implementation adds a bounded partial region for distinct,
equal-size, level-zero BGRA8 images. Source offsets must align to 4×4
utiles; width and height must be multiples of four unless that dimension
reaches the source image's right or bottom edge. Destination offsets are
texel coordinates and the destination rectangle must remain in bounds.
Source and destination allocations must be disjoint. The command stream
preflights the whole transfer sequence before starting DMA. The 2026-09-30 Pi 4 proof copied all 25 texels of a `(32,8)` `5×5` region from a 37×13 image, preserving 456 other texels and 32 guard words. Its 148-byte destination pitch had no padding words; DMA advanced 0→4 and a same-sized non-edge tail was refused with `-20005` before additional transfer work. See `docs/evidence/vulkan-partial-optimal-linear-pi4-20260930/README.md`. Mips, array layers, format conversion and other partial shapes remain unsupported.

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

The complete-image implementation issues one DMA job per 4×4 utile, so
large images may be slow. Mip levels, array layers and format conversion
remain unsupported. Bounded optimal-to-buffer readback and partial
optimal-to-linear image copy were added later; see
`docs/evidence/vulkan-optimal-edge-tail-pi4-20260930/README.md` and
`docs/evidence/vulkan-partial-optimal-linear-pi4-20260930/README.md`.
