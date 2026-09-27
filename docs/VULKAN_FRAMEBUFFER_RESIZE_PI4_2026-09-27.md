# Pi 4 Vulkan two-framebuffer resize proof

`RaspberryPi4/Examples/Diagnostics/vulkanPyramidFramebufferResizeProof.pi4`
records twelve render passes through one graphics pipeline and one compatible
render pass. Even frames use a 799×1279 linear BGRA8 image, image view and
framebuffer; odd frames use a separate 400×640 set. Each frame sets a dynamic
viewport and scissor to the active attachment extent. The V3D backend rebinds
the target for its GPU draw and restores the display surface afterward; the
completed attachment is presented by DMA.

The first RAM run, capture 104, returned a diagnostic report pointer. A
CRC-checked 256-byte report identified status 12 at step 3, before any draw:
the diagnostic had reserved only one full-size image plus 128 KiB in its
offscreen Vulkan heap, leaving no space for the second image. The corrected
diagnostic maps and declares a six-megabyte offscreen window. This changes
the diagnostic's reserved memory, not the Vulkan allocator or backend.

The corrected 1,024,304-byte PMFBOOT payload has SHA-256
`23dfce32c759eb3368979e82651b298a6c0c77f42e7edc4b7fc19dc19f376b93`.
Resident build 210 at 192.168.1.111 verified it at `$600000`, returned
`x0=0` after 9.3 seconds, and saved DMA capture 105. A CRC-checked 256-byte
report records twelve GPU draws and twelve DMA presentations. In the final
frame, the 400×640 attachment's rotated screen region X=0..639, Y=400..799
is pixel-identical to capture 100's 400×640 GPU viewport inside a larger
attachment. It contains 20,937 magenta and 10,521 cyan pyramid pixels. The
rest of the screenshot retains the preceding full-size frame because the
last DMA presentation copied only the small attachment.

The payloads, screenshots, monitor metadata, CRC-checked reports, compressed
transcripts and passing `verify_capture.py` oracle are in
`docs/evidence/vulkan-framebuffer-resize-20260927/`. Both runs were RAM-only;
the deadman stopped and the board lease was released. No flash, reset or
boot-medium write occurred.

The ordinary Pi 4 image compiled as build 219 at 4,366,700 bytes. Its raw
image and PMFBOOT container are preserved with the evidence; the raw image
SHA-256 is
`0cd1ab31bb524da2c389dba539254fb1a794fef6c2411b2f221bea6c31566055`.
