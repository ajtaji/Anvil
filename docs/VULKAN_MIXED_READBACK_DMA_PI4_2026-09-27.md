# Pi 4 Vulkan ordered upload and readback through DMA

On 2026-09-27, one transfer-only Vulkan command buffer uploaded a distinct
4×4 BGRA8 pattern from a buffer into a bound linear image, applied an image
transfer-write to transfer-read barrier, then read the same rectangle into a
different buffer span. `vkQueueSubmit` preflighted the complete stream before
starting work and executed its commands in recording order. Both copies ran
through guarded Pi 4 DMA; there was no processor pixel-copy path.

The returning diagnostic in
`RaspberryPi4/Examples/Diagnostics/vulkanImageReadbackProof.pi4` checked both
64-byte spans and the image bytes, exactly two new DMA operations, DMA
quiescence, and restoration of the original DMA write bounds. It returned
`x0=0` on the resident build-210 monitor after about 2.2 seconds. The
689,372-byte PMFBOOT payload, loaded at `$600000`, had SHA-256
`b736862633b8864ad93e6050e90f2b51be1f219990f8f691f1f22a21c029fce2`.
The monitor verified that digest before entry and saved fresh capture 71.
Afterward the resident Vulkan console was restored, the deadman and capture
were disarmed, coretest leases were zero, and the board was released. This was
a RAM run: no flash, reset, or boot-medium write occurred.

Evidence in `docs/evidence/vulkan-mixed-readback-20260927/` contains the run
JSON, the 1280×800 capture, and a compressed full console transcript.

The public pipeline gate also checks an upload, barrier, and readback in one
command buffer through the emitted Vulkan API. It checks the backend call
count, final image layout, fence state, copied image and buffer bytes, and
untouched guard bytes. The production V3D backend gate passed 92 checks over
4,405,988 interpreted AArch64 instructions. The normal Pi 4 image compiled to
4,342,264 bytes with its generated source build stamp restored. The full public pipeline gate passed 813 property checks over 204,109,447
interpreted AArch64 instructions, including eight new mixed-readback checks.

This path supports the already bounded linear BGRA8 image and transfer-buffer
shapes. Optimal-tiled image readback, mip/layer arrays, and a command buffer
mixing render or clear work with these transfers remain unsupported. The image
barrier in the proof supplies the explicit Vulkan dependency between the
upload and readback; recording order alone is not a general memory barrier.
