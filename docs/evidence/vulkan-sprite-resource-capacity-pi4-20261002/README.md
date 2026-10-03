# Pi 4 Vulkan sprite resource capacity

The Vulkan handle tables reserve room for sixteen separately owned sprite
images, one replacement image generation, and a transient staging allocation.
Their limits are now 25 images, 21 image views, 21 descriptor sets, and 34
device-memory allocations. This change enlarges object tables, not the Vulkan
heap supplied by the caller, and does not implement separate-image rendering.

The state-only test-backend model
[`vulkanSpriteResourceCapacityModel.pi4`](../../../RaspberryPi4/Examples/Diagnostics/vulkanSpriteResourceCapacityModel.pi4)
checks an over-heap allocation refusal, successful allocation afterward,
exhaustion of each enlarged table, and reuse after freeing an object. It
compiled with the tracked PureMetal Forge IDE and ran as a returning RAM
payload on Pi 4 monitor build 242. The board verified the 273,044-byte PMF
container (SHA-256
`07deea59a654c50d3e64e837bfc118e75ad183183c9dfd31320cd254a4724f53`),
then returned x0=0 in 1.4 seconds under a 15-second deadman. The model does
not render pixels.

The existing multi-sprite sampled-image proof was recompiled against the
enlarged tables and rerun on the same board. Its 1,302,468-byte PMF container
had SHA-256
`0c0fe89ca96ad36b4c0640e06b53ca46cae72e4ca2219140d0a7ab6d01b34317`.
The board returned report pointer `$0093CA88` in 4.0 seconds. The saved
[`regression-report.bin`](regression-report.bin) passed the independent
[`vulkan_neon_multi_sprite_proof_check.py`](../../../tools/vulkan_neon_multi_sprite_proof_check.py)
oracle: four GPU draws, 24 vertices, eight exact BGRA probes, and no native
faults. The offscreen proof does not capture the physical monitor.

The complete Pi 4 monitor also compiled successfully with these table sizes.
The resident build 242 was not replaced. After both payloads, it answered at
the real `pmf>` prompt over Wi-Fi and the deadman was turned off. Neither the
boot medium nor other storage was written.
