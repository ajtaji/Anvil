# Pi 4 BGRA sprite upload proof — 2026-10-03

The returning RAM diagnostic exercised both accepted source formats through
the same Vulkan sprite-image replacement transaction. The new BGRA entry
copies 32-bit source words into upload staging without channel conversion;
the existing RGBA entry still converts channels. Staging remains a CPU copy,
then the Pi 4 transfer and sampling paths use the existing Vulkan backend.

The signed PMF container was 1,326,612 bytes, SHA-256
`6f84baec2b64379a4ceea1a4e931aa7b2dc2499853424cf4c3eba2a0ce8f6c4e`.
It was linked and entered at `$00700000` on resident Pi 4 build 242. The
board verified the transfer hash, armed a 15-second deadman, and returned
the expected `x0=$00D4CA98` after 4.3 seconds. The saved 192-byte
[`report.bin`](report.bin) has SHA-256
`273844004a277ffa275a3309c8f5abebd790ee7eff7660d5a889bbc1a13bf80a`.
The host oracle passed with stage 9 and status zero.

The report checks interleaved atlas/separate-image draws, the original RGBA
replacements, preserved handles and pixels after a rejected 1024×1024
replacement, and descriptor reuse. A separate 3×1 BGRA replacement checks
left, center, and right raw pixels as `$FFFF00FF`, `$BF808000`, and
`$FF0000FF`. The center uses half alpha; its resulting alpha follows the
backend's `SRC_ALPHA`/`ONE_MINUS_SRC_ALPHA` blend factors for both color and
alpha. No boot medium was written. The monitor returned to `pmf>` and the
deadman was explicitly disabled.

This establishes the bounded Pi 4 path only. It does not claim DMA for the
initial host-memory copy, a second simultaneous separate sprite image, or
behavior on another board.
