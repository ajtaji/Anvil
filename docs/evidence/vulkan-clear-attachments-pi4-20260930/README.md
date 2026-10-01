# Pi 4 Vulkan clear-rectangle hardware proof

The 256-byte `report.bin` has SHA-256 `86DB8C7B0291C9D1B3C7D3D6DEAA3993F513567BBA10C7A3F04020EBCC37CD60`. The executed PMF container had SHA-256 `1862E141EC8AE440B3A6B11BB251C87B6E7FDAF31C467F493B5BDFCA5F3ECCC8`.

On a 64×64 even-sized target, the report returned pointer `0xC2D2D0` after 5.1 seconds. Status was zero; all 4,096 pixels matched exactly, the padding mismatch count was zero, and the alpha-zero color was `$00FF8000`. Two draws and two clears completed in one V3D bin/render transaction. An out-of-bounds rectangle at x=60 with width 8 returned `-20001` before jobs. MMU, out-of-memory and native-fault counters were all zero.

This establishes the bounded Pi 4 path for partial color rectangles on even framebuffer dimensions. It does not establish partial clears on odd-sized targets or on other boards. The full pre-draw load-clear path remains supported on odd-sized targets.
