# Pi 4 Vulkan ordered image-to-buffer readbacks through DMA

On 2026-09-27, one command buffer recorded two separate
`vkCmdCopyImageToBuffer` calls from a bound linear BGRA8 image into disjoint
spans of a transfer-destination buffer. The first call copied a tight 4x4
rectangle; the second copied a 4x4 rectangle into six-texel-stride rows.
Submission preflighted every recorded row before work began and executed eight
guarded DMA row operations in recording order. The returning diagnostic checked
all 16,512 destination bytes, including the row padding and untouched poison,
DMA quiescence, and restoration of the prior DMA write bounds.

`RaspberryPi4/Examples/Diagnostics/vulkanImageReadbackProof.pi4` was compiled
through the IDE compiler for RAM load `$600000`, stack `$4F00000`, and a
returning entry. The PMFBOOT container was 662,704 bytes with SHA-256
`91C9EB850601C153E277829855C16940D4C8465EF7208D449EFF9F69EEEAB23B`.
The resident build-210 monitor verified the container and received `x0=0`.
Fresh 1280x800 capture 54 followed capture 53. The resident Vulkan console was
restored after the diagnostic, the deadman and capture were disarmed, core
leases were zero, and the board was released at its prompt. This was RAM-only:
no flash, reset, or boot-medium write occurred.

Evidence is in `docs/evidence/vulkan-multi-call-readback-20260927/`:

- `vulkan-multi-call-readback.json` records the payload, return and capture;
- `vulkan-multi-call-readback.png` is capture 54, SHA-256
  `c2ec35ab4dbab2f1c86e2dc77012660f494ce559ca6a4554a73d15bbe03e228e`;
- `vulkan-multi-call-readback.txt.gz` preserves the complete console transcript.

The supported path remains limited to one-mip, one-layer, one-sample linear
BGRA8 sources in valid transfer layouts and bound transfer-destination buffers.
Each call validates its complete region array at recording. Submission checks
all recorded calls before starting DMA. The calls in this proof write disjoint
buffer spans. Dependencies between calls still follow Vulkan's explicit
synchronization rules; recording order alone does not establish a general
memory dependency. Optimal-tiled readback and mixed render/transfer jobs remain
unsupported.

The production V3D backend gate passed 85 checks and compiled all eight Pi 4
board diagnostics. The normal Pi 4 image compiled at 4,327,940 bytes against
the combined current tree; its generated source build stamp was restored.

The public Vulkan pipeline gate passed 766 property checks over 201,123,402
interpreted AArch64 instructions, including both ordered calls and the exact
whole-destination byte oracle.
