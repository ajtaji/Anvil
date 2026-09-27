# Pi 4 Vulkan two-region linear image upload through DMA

On 2026-09-27, the public `vkCmdCopyBufferToImage` path copied two disjoint
4×4 regions from one transfer-source buffer into a bound 32×32 linear BGRA8
image on Pi 4 silicon. The first source was tight at a 64-byte-aligned offset;
the second had six texels per buffer row at offset 256. The command recorded
both regions as one bounded array, submitted one DMA operation for each of the
eight image rows, and returned `x0=0`. The diagnostic checked every destination
pixel, including earlier copied regions and untouched poison, verified DMA
quiescence, and confirmed that the prior DMA bounds were restored.

The returning diagnostic is
`RaspberryPi4/Examples/Diagnostics/vulkanImageReadbackProof.pi4`. It was
compiled with the IDE compiler's `--compile` path for load address `$600000`,
stack `$4F00000`, and returning entry. The PMFBOOT container was 657,080 bytes,
SHA-256 `e3c156169b058463b27cf66491a074d186c220dc85293bc5460ddd40b24f85fd`.
Build 210 of the resident monitor verified that digest before entry. The RAM
payload returned in 0.6 seconds with `x0=0`; the monitor saved fresh capture
52 at 1280×800 on its DMA display tier. The deadman was stopped on return, the
capture was disarmed, secondary-core leases were zero, and the monitor was
left at its prompt. No boot-medium write, flash, or reset was performed.

Evidence is in `docs/evidence/vulkan-upload-array-20260927/`:

- `vulkan-upload-array-r3.json`: board-run metadata and return status;
- `vulkan-upload-array-r3.png`: fresh monitor capture, SHA-256
  `12e588bbb3f3eb19cb8a8143078a69c3c5ec9906d2e067b209d251ccbc179fad`;
- `vulkan-upload-array-r3.txt.gz`: complete console and capture transcript.

The active Pi 4 backend reports a 64-byte image-copy source alignment and
refuses misaligned source offsets before recording. A preliminary 32-byte
source-offset diagnostic correctly failed recording; changing the readback and
upload source to offset 64 made the complete hardware run pass. The bounded
implementation validates the full region array before recording, rechecks
live resources and all row overlaps before DMA, and accepts up to 32 linear
regions in one otherwise isolated command buffer. The optimal-tiled image
path still accepts one complete TFU region. This silicon run proves the exact
two-region linear shape above, not Vulkan 1.0 conformance.

The relevant core command and valid-usage rules are in the
[Khronos `vkCmdCopyBufferToImage` reference](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdCopyBufferToImage.html).

The public pipeline gate passed 756 property checks over 185,396,084
interpreted A64 instructions. Its new slots verify both copied regions,
untouched image bytes, a malformed later region, overlapping destinations,
and a region count above the bounded pool. The production V3D backend gate
passed 85 checks, the resource gate 724, and the dispatch gate 604. The normal
Pi 4 image compiled at 4,300,736 bytes with the IDE compiler; its generated
source build stamp was restored afterward.
