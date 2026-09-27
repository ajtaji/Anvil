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
`docs/evidence/vulkan-subviewport-20260927/`. A two-framebuffer resize proof
remains open.

The next follow-up accepts a nonnegative whole-pixel viewport offset while
requiring the entire rectangle to fit the framebuffer and its centre to fit
V3D's u14.8 viewport-offset field. Capture 101 ran the same 400×640 viewport
at attachment coordinates (200,320) with a matching scissor. Build 210 at
192.168.1.111 verified the 1,023,096-byte PMFBOOT payload (SHA-256
`aac3faac5c4ddeeb19a626d6efcee40e29b76fe4ea928ddb3403207f220c434f`)
at `$600000` and returned `x0=0` in 9.2 seconds. The magenta face remains
20,937 pixels, now at screenshot X=456..778, Y=363..501; cyan remains 10,521
pixels, now at X=458..779, Y=314..399. Relative to capture 100, both faces
shift exactly +320 in X and -200 in Y, the expected screen-space displacement
for the rotated panel. The exact payload and capture are in
`docs/evidence/vulkan-translated-viewport-20260927/`. Negative, fractional,
flipped, out-of-bounds and depth-remapped viewports remain unsupported.

The emitted V3D draw-list gate passed 117 checks over 30,626,669 interpreted
A64 instructions. Its new cases observe the 32×32 clipper scale and fine
viewport offset, a completed indexed draw, and refusal of a 65×64 viewport
on a 64×64 target before allocation or frame begin. The ordinary Pi 4 image
compiled at 4,365,196 bytes as build 216. Its raw image and PMFBOOT container
are retained beside capture 100; the raw image SHA-256 is
`7aaf51140dc0b5fa41e0295b8e88a2f8e79b01b5632dcca1ccbf76514487847e`.

For the translated follow-up, the same gate passed 132 checks over 31,852,239
interpreted A64 instructions. A 32×32 viewport translated to (8,12) emitted
unchanged half-size scales, fine offsets (6144,7168), and clip origin (8,12).
A viewport at X=40 with width 32 on a 64-pixel target was refused before
allocation or frame begin. The ordinary Pi 4 image compiled as build 217 at
4,367,292 bytes. Its raw image and PMFBOOT container are preserved beside
capture 101; the raw image SHA-256 is
`7896037f5d2778be6cfeedb0b8eded4cf31e5dece52a472da9cfe885aa7f4756`.

Both runs were RAM-only. The deadman stopped, the capture was consumed,
the board lease was released, and no flash, reset or boot-medium write
occurred.
