# Pi 4 static scissor and viewport proof

The public Vulkan pipeline now accepts one static `VkRect2D` independently of
the viewport. Its signed offset and unsigned extent are copied into the
pipeline, then into each draw; the V3D backend intersects them with the active
framebuffer before emitting `CLIP_WINDOW`. `VK_DYNAMIC_STATE_VIEWPORT` can be
declared without `VK_DYNAMIC_STATE_SCISSOR`. A static viewport and an
independently offset or smaller static scissor are also accepted. The existing
whole-pixel, nonnegative viewport and V3D offset bounds still apply.

Two RAM-only Pi 4 diagnostics used a viewport at (200,320), size 400×640, and
a static scissor at (200,320), size 200×640. The first declared only the
viewport dynamic; the second declared neither state dynamic. Both animated
the GPU-transformed pyramid for twelve frames and returned `x0=0` on the
resident build 210 monitor at 192.168.1.111. Their final DMA screenshots,
captures 102 and 103, are pixel-identical. Each has 15,412 magenta pixels and
no cyan pixels. More strongly, each is pixel-identical to capture 101 after
masking only the pyramid pixels outside the static scissor's rotated screen
rectangle X=320..959, Y=400..599. This checks the exact clip position and
shape, not just a successful return.

Capture 102's 1,020,792-byte PMFBOOT payload has SHA-256
`fa9fb026b5d235334436ef9647941e47a51eb9fe9516c50f9eecea571ff7e159`.
Capture 103's 1,018,256-byte payload has SHA-256
`736af56266d56144a41ffaf6baaa6f8dd4f4ee412072feb4dfa97f137cec5a81`.
The payloads, screenshots, monitor metadata, compressed transcripts and the
passing `verify_pixels.py` oracle are in
`docs/evidence/vulkan-static-scissor-20260927/`.

Both payloads were verified at `$600000`, ran under a 15-second deadman and
returned in about 9.2 seconds. The deadman stopped, the board lease was
released, and no flash, reset or boot-medium write occurred.

The ordinary Pi 4 image compiled as build 218 at 4,366,700 bytes. Its raw
image and PMFBOOT container are preserved with the capture evidence; the raw
image SHA-256 is
`a2b1744ecb928c361139b8845d3e7d886faf586634aed5f7ace32846c87d4d8c`.
The full public pipeline gate passed 813 checks over 204,183,778 interpreted
AArch64 instructions with the updated front end.
