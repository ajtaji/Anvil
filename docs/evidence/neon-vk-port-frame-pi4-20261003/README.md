# Pi 4 Neon Vulkan port frame

On Raspberry Pi 4 Anvil build 244, the returning `vulkanNeonPortFrameProof.pi4` payload drew a 64×64 offscreen Vulkan frame through the Neon port adapter. The monitor verified the 1,355,708-byte PMF container (SHA-256 `BDBEEF2A46FF9DC58566FD014FC790121FB13F907AAB2FDF7432A39956F7C26B`), armed a 15-second deadman, and received the expected return pointer `0x025EDD38` after 4.3 seconds. Anvil returned to `pmf>` with the deadman off. No boot file was changed.

`report.bin` is the 128-byte board readback from that pointer, SHA-256 `5276E8EA0A10A85C1CFEA5007653F2C99C8805AA1862AD17663C94F0282157CE`. From the repository root, `py -3 RaspberryPi4/Examples/Diagnostics/vulkanNeonPortFrameProofCheck.py docs/evidence/neon-vk-port-frame-pi4-20261003/report.bin` checks the black/red/blue/red pixel order, 22 white text pixels, three draws, 18 vertices, no Vulkan faults, and clean teardown.

The payload renders offscreen, so the monitor's physical screen is unchanged. This proves one small rectangle/text/cropped-sprite frame on the Pi 4 V3D Vulkan backend. It does not establish other board backends or particle throughput.
