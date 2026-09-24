# Rock Pi 4C rendering status

The RK3399 VOPB scans out a linear ARGB8888 framebuffer through the HDMI
path. The VOPB-to-HDMI bus uses the 30-bit AAAA output mode even when the HDMI
input is 8-bit RGB. That mode has been verified on the Rock Pi 4C at
1920×1080/60 Hz.

The display path has three distinct data movers:

| Engine | Current role | Proven extent |
| --- | --- | --- |
| PL330 | Framebuffer clear, terminal-row transfer, and scroll | Used by the running HDMI console; CPU fallback remains bounded. |
| RGA2 | Two-dimensional ARGB copy | Private 40×40 and 1920×40 copies passed with exact pixels and guards. Bounded 40×40 and 1920×40 copies into live VOPB scanout passed with completion IRQ `0x604`, exact pixel and adjacent-row checks, and complete saved-region restoration. |
| Mali-T860 | Programmable graphics GPU | A v5 `WRITE_VALUE` job zeroed a guarded private DDR word. Clear-only v5 fragment jobs filled guarded private 16×16 and 48×48 linear RGBA8 targets. The larger-BSS 48×48 job passed after aligning its polygon list to 4 KiB. A bounded 48×48 GPU surface was copied through RGA2 to live scanout and its saved 50×50 screen region was restored exactly. No production framebuffer write uses Mali. |

The TrueType atlas now precomposes opaque normal and prompt glyphs once. The
console copies those cells without per-pixel RGB division. RGA2 cannot accept
the 12×20 cell directly because Linux's RGA2 driver admits crops only from
34×34 upward. The candidate console instead preserves the next 20 scan lines,
then publishes a complete 1920×40 row through RGA; the final terminal row and
any RGA failure use PL330. Builds 145 and 147 boot this path on the original
Rock Pi 4C at the verified 1920×1080 mode. A build 145 resident deadman-guarded counter probe
reported RGA ready, atlas ready, 46 completed RGA jobs, zero RGA failures,
27,187,200 DMA text bytes, and zero CPU text bytes. This confirms live RGA
publication; it does not establish a sustained throughput measurement.

The build 145 bounded banner and logo captures showed clean TrueType text and
shading. Build 147 changed UART service inside CPU fallback drawing and passed
two live CPU-status/400-byte receive stress runs. A build 147 bounded crop did
not complete because the serial capture transport exhausted its ACK/retry
window, so the newer image has no accepted pixel capture yet.

The Mali job, fragment, and RGA copy proofs are repeatable with
`tools/rockpi4c_mali_job_proof.py`, `tools/rockpi4c_mali_fragment_proof.py`,
`tools/rockpi4c_rga_blit_proof.py`, `tools/rockpi4c_rga_scanout_proof.py`,
`tools/rockpi4c_rga_fullrow_proof.py`,
`tools/rockpi4c_rga_fullrow_scanout_proof.py`,
`tools/rockpi4c_mali_rga_proof.py`, and
`tools/rockpi4c_mali_rga_scanout_proof.py`. These query the live Anvil payload
stage, compile for its exact address, check the separate BSS and stack ranges,
and use the recovery deadman.

The [Midgard v5 render-target descriptor](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/panfrost/genxml/v5.xml) must set block format `2` for a
linear buffer. Leaving it at `0` selects 16×16 U-interleaved tiling; a solid
16×16 clear can mask that mistake until the target gains a larger pitch.
The combined-layout 48×48 clear initially returned `DATA_INVALID_FAULT` `0x58`
because its polygon-list base had only 64-byte alignment. Aligning it to 4 KiB
made all 2,304 private pixels and guards pass, with job status `1` and no MMU
fault. A second payload copied those GPU pixels through RGA into guarded
private DDR exactly. The bounded live-scanout payload then rendered the same
48×48 tile with Mali, copied it through RGA (completion IRQ `0x604`), checked
every displayed pixel, and restored all 2,500 pixels of a saved 50×50 screen
region without mismatch. The display address was never GPU-mapped. This is a
proof payload, not an enabled production Mali renderer.

Mali-T860 is a Midgard v5 GPU. [Mesa's Panfrost support table](https://docs.mesa3d.org/drivers/panfrost.html)
lists OpenGL ES 3.1 and OpenGL 3.1 for the T860 but no Vulkan support;
[Mesa 22.2 removed Midgard support from PanVK](https://docs.mesa3d.org/relnotes/22.2.0.html).
A common Anvil rendering interface can use the proven display engines now and
accept a later GPU renderer when shader jobs and larger render targets are proven. A
hardware Vulkan implementation is not currently available for this board.
