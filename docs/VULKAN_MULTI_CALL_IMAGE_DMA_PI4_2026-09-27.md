# Pi 4 Vulkan ordered image-copy calls through DMA

On 2026-09-27, one command buffer recorded two separate `vkCmdCopyImage`
calls. Each copied a disjoint 4×4 rectangle from a bound linear BGRA8 source
image to a different rectangle in a bound linear BGRA8 destination. Submission
preflighted both calls before work began and lowered their eight rows to eight
guarded Pi 4 DMA operations in recorded order. The returning diagnostic checked
all 1,024 destination pixels, including earlier transfers and untouched
poison, DMA quiescence, and restoration of the prior DMA write bounds.

`RaspberryPi4/Examples/Diagnostics/vulkanImageReadbackProof.pi4` was compiled
through the IDE compiler for RAM load `$600000`, stack `$4F00000`, and a
returning entry. The PMFBOOT container was 660,468 bytes with SHA-256
`85785f17c494fadc26a8a5441b9c2d8101f1bb0d71272ccdbf31cf97731f5610`.
The resident build-210 monitor verified the container and received `x0=0` in
0.6 seconds. A fresh 1280×800 DMA-tier capture advanced from 52 to 53. The
deadman and capture were disarmed, core leases were zero, and the board was
released at its prompt. This was RAM-only: no flash, reset, or boot-medium
write occurred.

Evidence is in `docs/evidence/vulkan-multi-call-image-20260927/`:

- `vulkan-multi-call-image.json` records the payload, return and capture;
- `vulkan-multi-call-image.png` is capture 53, SHA-256
  `cb46794cb3be913f46fd93b4a1005ef02fba9ac30331d279151e8fb20dbbf13d`;
- `vulkan-multi-call-image.txt.gz` preserves the complete console transcript.

The supported path still requires one-mip, one-layer, one-sample linear BGRA8
images and valid transfer layouts. Each region array is validated as a whole
at recording, and all recorded image-copy rows are rechecked before any DMA
is submitted. The two calls in this proof use disjoint source and destination
regions. Application dependencies between calls still follow Vulkan's
explicit synchronization rules; this proof does not establish a general
implicit memory dependency. Mixed draw/transfer jobs and optimal-tiled image
copies remain outside this path. The core command and synchronization rules
are documented by [Khronos image copies](https://docs.vulkan.org/spec/latest/chapters/copies.html)
and [synchronization](https://docs.vulkan.org/spec/latest/chapters/synchronization.html).

The production V3D backend gate passed 85 checks and compiled all eight Pi 4
board diagnostics. The normal Pi 4 image also compiled against the combined
current tree at 4,327,656 bytes; its generated source build stamp was restored.
The public Vulkan pipeline gate passed 761 property checks over 187,729,293 interpreted AArch64 instructions, including both ordered calls and the exact whole-destination byte oracle.
