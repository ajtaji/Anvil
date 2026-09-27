# Pi 4 Vulkan ordered buffer-to-image uploads through DMA

On 2026-09-27, one command buffer recorded two separate
`vkCmdCopyBufferToImage` calls into disjoint rectangles of a bound linear BGRA8
image. The first copied a tight 4x4 source; the second copied a 4x4 source
with six-texel-stride rows. Submission resolved each call's own destination,
preflighted all recorded rows before work began, and executed eight guarded
Pi 4 DMA row operations in recording order. The returning diagnostic checked
all 1,024 destination pixels, including earlier transfers and untouched
poison, DMA quiescence, and restoration of the prior DMA write bounds.

`RaspberryPi4/Examples/Diagnostics/vulkanImageReadbackProof.pi4` was compiled
through the IDE compiler for RAM load `$600000`, stack `$4F00000`, and a
returning entry. The PMFBOOT container was 665,464 bytes with SHA-256
`7B735BF5B86DE2260B37F46F751384AAB3A2259292C9567EA453A89D52BC1640`.
The resident build-210 monitor verified the container and received `x0=0`.
Fresh 1280x800 capture 55 followed capture 54. The resident Vulkan console was
restored after the diagnostic, the deadman and capture were disarmed, core
leases were zero, and the board was released at its prompt. This was RAM-only:
no flash, reset, or boot-medium write occurred.

Evidence is in `docs/evidence/vulkan-multi-call-upload-20260927/`:

- `vulkan-multi-call-upload.json` records the payload, return and capture;
- `vulkan-multi-call-upload.png` is capture 55, SHA-256
  `721a007bc1a8ef18f7e1b97634051525265be19cc6b529147851ef6f1af8505b`;
- `vulkan-multi-call-upload.txt.gz` preserves the complete console transcript.

The supported multi-call path remains limited to one-mip, one-layer,
one-sample linear BGRA8 destinations in valid transfer layouts and aligned,
bound transfer-source buffers. Each call validates its complete region array
at recording. Submission checks all recorded calls before starting DMA. The
two calls in this proof write disjoint image rectangles. Dependencies between
calls still follow Vulkan's explicit synchronization rules; recording order
alone does not establish a general memory dependency. An optimal-tiled upload
still uses one whole-image TFU transaction, so multiple optimal uploads or
mixed render/transfer jobs are refused.

The production V3D backend gate passed 85 checks and compiled all eight Pi 4
board diagnostics. The normal Pi 4 image compiled at 4,327,940 bytes against
the combined current tree; its generated source build stamp was restored.
The public Vulkan pipeline gate passed 771 checks over 203,706,937
interpreted AArch64 instructions, including separate upload-call completion
and an exact whole-image byte oracle.
