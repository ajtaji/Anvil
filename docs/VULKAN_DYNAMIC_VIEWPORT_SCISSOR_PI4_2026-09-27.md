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
`vkCmdDraw` refused it before submission with `ANVIL_VK_ERR_UNSUPPORTED`
and the recorded sentence that the dynamic viewport must equal the active
framebuffer geometry. Capture 98 and the 256-byte report are preserved with
the passing capture. This is the current API limit: a reusable pipeline can
resize between different full-target framebuffer geometries, but a viewport
smaller than its active framebuffer is not accepted. A two-framebuffer
resize proof remains open.

Both runs were RAM-only. The deadman stopped, the capture was consumed,
the board lease was released, and no flash, reset or boot-medium write
occurred.
