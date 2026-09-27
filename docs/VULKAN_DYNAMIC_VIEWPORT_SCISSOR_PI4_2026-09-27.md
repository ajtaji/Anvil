# Pi 4 dynamic viewport and scissor proof

`RaspberryPi4/Examples/Diagnostics/vulkanPyramidDynamicViewportProof.pi4`
uses the public Vulkan calls with a pipeline declaring both
`VK_DYNAMIC_STATE_VIEWPORT` and `VK_DYNAMIC_STATE_SCISSOR`. It records twelve
frames of the GPU-transformed pyramid. Each draw supplies a full-target
799×1279 viewport; the scissor alternates between that extent and 400×640.
The completed attachment is presented through DMA.

The final PMFBOOT payload in `docs/evidence/vulkan-dynamic-viewport-scissor-20260927/`
is 1,020,968 bytes, SHA-256
`e52380ad7f4c040ff57efc4ba3401dc746dfb08584f30019aa9d4e2fdad5ca26`.
Build 210 at 192.168.1.111 verified the upload at `$600000`, returned
`x0=0` in 9.2 seconds, and saved capture 99. The final image has 44,415
magenta pyramid pixels inside screenshot coordinates X=320..639,
Y=400..604, and no cyan pyramid pixels. The preceding full-frame GPU
pyramid capture has 83,584 magenta pixels at X=273..920, Y=327..604,
and 41,980 cyan pixels at X=274..917, Y=228..399. Both images use the
same clear colour `(13,26,51,255)`. The image bounds show the final draw
was clipped to the requested half-size scissor after viewport mapping.

An initial trial requested a 400×640 viewport on the 799×1279 framebuffer.
At that time `vkCmdDraw` refused it before submission with
`ANVIL_VK_ERR_UNSUPPORTED`; capture 98 and the 256-byte report preserve
that exact earlier boundary. The first accepted dynamic-state proof above
used a full-target viewport and half-size scissor in capture 99.

The follow-up removes that full-target restriction for one origin-zero
whole-pixel viewport contained by the active framebuffer. It keeps the
per-draw QPU scale, V3D clipper scale and fine viewport offset matched to
the draw's dimensions. The same diagnostic now alternates both viewport
and scissor sizes. Build 210 at 192.168.1.111 verified the 1,021,000-byte
PMFBOOT payload (SHA-256
`31a3f09e189207dd310ad9387e779a3af487b4ec4a7509aaa1d5a4594a325a38`)
at `$600000`, returned `x0=0` in 9.2 seconds, and saved capture 100. Both
pyramid faces are visible in the smaller region: 20,937 magenta pixels at
X=136..458, Y=563..701, and 10,521 cyan pixels at X=138..459, Y=514..599.
Capture 99's scissor-only result had no cyan pixels. The smaller image
therefore proves viewport mapping changed on the GPU, not just clipping.
The exact payload, screenshot and monitor metadata are in
`docs/evidence/vulkan-subviewport-20260927/`. Viewports translated from
the origin, larger than the framebuffer, fractional, flipped or with a
nonstandard depth range remain unsupported. A two-framebuffer resize proof
remains open.

The emitted V3D draw-list gate passed 117 checks over 30,626,669 interpreted
A64 instructions. Its new cases observe the 32×32 clipper scale and fine
viewport offset, a completed indexed draw, and refusal of a 65×64 viewport
on a 64×64 target before allocation or frame begin. The ordinary Pi 4 image
compiled at 4,365,196 bytes as build 216. Its raw image and PMFBOOT container
are retained beside capture 100; the raw image SHA-256 is
`7aaf51140dc0b5fa41e0295b8e88a2f8e79b01b5632dcca1ccbf76514487847e`.

Both runs were RAM-only. The deadman stopped, the capture was consumed,
the board lease was released, and no flash, reset or boot-medium write
occurred.
