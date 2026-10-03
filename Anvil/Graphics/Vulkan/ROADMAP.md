# Vulkan compatibility roadmap and exact gaps

This is a coverage inventory, not a version or conformance claim. The schema
target is `VK_API_VERSION_1_0`, generated from the pinned registry identified
in `COVERAGE.md`. A production Pi 4 build linked to the V3D backend exposes its
one implemented physical device; targets without a graphics backend enumerate
none.

See the [cross-layer compatibility inventory](../../../docs/VULKAN_COMPATIBILITY_STATUS.md)
for the current implementation matrix, prerequisites, target-neutral boundaries,
and the next resource-backed transfer slice with its acceptance gates.

Primary API references are the [Khronos Vulkan Registry](https://registry.khronos.org/vulkan/),
the Vulkan specification's [clear-command definition](https://registry.khronos.org/vulkan/specs/latest/html/vkspec.html#clears-images-outside-render-pass),
and the pinned `vk.xml`. The V3D implementation reference is Mesa's
[V3D/V3DV documentation](https://docs.mesa3d.org/drivers/v3d.html) plus the
versioned Mesa sources cited next to packet/register code in
`RaspberryPi4/Lib/v3d.pi4`. Mesa is a reference, not an Anvil runtime
dependency.

## The implemented slice

`vk_v3d_backend.pi4` executes validated whole-image clears and the bounded
graphics-pipeline draws listed in `COVERAGE.md` on the GPU. That includes a
combined `sampler2D` implicit-LOD request from either the measured one-texel
linear image or the bounded optimal BGRA8 image path. A whole optimal-image
`vkCmdCopyBufferToImage` upload executes a TFU raster-to-`UIF_NO_XOR` copy. Separate bounded partial optimal-image uploads use guarded DMA, including edge tails and two ordered calls in one command buffer; partial linear-to-optimal, optimal-to-linear, optimal-to-optimal copies and optimal-image buffer readback also have separately bounded Pi 4 DMA paths. Their exact shapes and evidence are listed in `COVERAGE.md`; no non-Pi 4 backend capability is implied. The separate interior optimal-image buffer micro-readback uses `TILED_MICRO_READBACK`, passed its bounded Pi 4 proof, and remains fail-closed on other backends. The separate optimal-to-optimal one-utile microcopy has its own guarded-DMA capability, Pi 4 proof and desk-only submit-preflight limit documented there; other backends do not advertise it. A separate one-utile BGRA8 micro-upload uses a dedicated capability and guarded DMA on Pi 4; its 2026-09-30 bounded silicon proof and desk-only submit-preflight limit are recorded in `COVERAGE.md`. Other backends do not advertise the capability. Existing bounded multi-region and ordered-call rectangular strided linear-image uploads (two regions silicon-proved by `docs/VULKAN_IMAGE_UPLOAD_ARRAY_DMA_PI4_2026-09-27.md`; separate calls by `docs/VULKAN_MULTI_CALL_UPLOAD_DMA_PI4_2026-09-27.md`) and bounded multi-region linear
`vkCmdCopyImage` and `vkCmdCopyImageToBuffer` transfers execute guarded DMA. Submission revalidates live
resources before transfer and publishes the final layout only after success. Submission
and the following sampled draw are both observed through public fences.

The execution path is `NeonRebindSurface`, `NeonFrameBegin` and `NeonFrameEnd`.
It now accepts a bounded ordered draw list as one frame transaction, with
transition-cached viewport, scissor, blend and varying state. Dynamic
viewport/scissor pipelines may be reused across whole-target resize; each
draw carries private CS/VS scale uniforms and matching packet state.
`NeonRebindSurface` plans and validates each accepted geometry,
rebuilds its coordinate tables, and restores the complete display-owned surface
after submission. The frame then builds and submits real V3D bin and render
control lists:
`V3dBinSubmit`, `V3dBinWait`, `V3dRenderSubmit` and `V3dRenderWait` launch,
wait, clean the V3D caches and maintain the processor's view of the target.
The tile clear and the tile store are what write the image. There is no
processor-side and no DMA image fallback anywhere under this path, and the
desk gate checks the source for one.

A bounded UINT32 indexed triangle proof joined the Pi 4 silicon coverage on
2026-10-01. It verifies the public UINT32 bind, `firstIndex` byte offset,
V3D packet bytes, index sentinels, display result and teardown; the evidence is
`docs/evidence/vulkan-indexed-uint32-pi4-20261001/README.md`. This establishes
that diagnostic shape on Pi 4 only and does not imply another board backend.

The Pi 4 backend also passed a one-sample zero-`pSampleMask` draw proof: three
public records yielded two emitted primitives and an exact full-image oracle.
The V3D backend omits the zero-coverage draw after validation; it does not emit
a hardware sample-mask packet. Evidence:
`docs/evidence/vulkan-sample-mask-pi4-20261001/README.md`.

### What this backend still cannot do, and says so

The rotating Pi 4 pyramid demo (`docs/VULKAN_PYRAMID_DEMO_PI4_2026-09-27.md`)
proves 12 V3D triangle renders and 12 DMA presentations on silicon. Its
coordinate and vertex QPUs now compute two three-component transform-row dot
products and apply the per-vertex perspective scale. The CPU still computes
the frame row coefficients and reciprocal scale, sorts faces, and uploads the
vertex buffer. Clip Z/W remain fixed and the render pass has no depth
attachment. General matrix/clip handling and hardware depth testing remain
the next 3D rendering gaps; the existing XY transform is already on V3D.


- **Extents beyond the proved capacity.** The backend accepts linear BGRA8
  images through the V3D planner up to the configured equal width/height
  maximum and derives row pitch from the same rule used by creation and the
  public image-format query. Zero, overflowing, over-capacity or unmapped
  geometry is refused before a job counter can move. Sampled resources remain bounded: linear sampling is 1x1 only; optimal BGRA8 supports one mip, one layer, one sample and the backend-planned size. Its TFU upload path is a single whole-image transaction; this sampling-path limit does not remove the separate bounded partial transfer commands listed above. Mips, array layers, multisampling and other formats remain unsupported for this sampled-image shape.
- **The buffer the display is scanning out.** This backend is offscreen by
  contract. Presentation stays with the display layer.
- **Asynchrony.** `NeonFrameEnd` waits for both jobs before it returns, so
  nothing is genuinely in flight when `vkQueueSubmit` returns. The engine
  models the pending state correctly and the test backend exercises it, but on
  V3D the fence is signalled inside the submit. Real asynchrony needs
  interrupt-driven completion rather than the current bounded polls.
- **Multiple submissions in flight.** The Pi 4 backend completes its one
  bounded queue flight synchronously inside submission. A render pass can still
  contain its bounded ordered draw list and the implemented partial color
  attachment clear rectangles; asynchronous completion remains future work.

### Sampled-pixel silicon boundary

The 2026-09-13 Pi 4 run from public commit `85c2db8` is green. Its PMF container
was 636,508 bytes with SHA-256
`F7E32E54EF59952868859B629EACA64F3D3BDE85C78790353E8EE18DD0146352`.
Monitor build 101 verified both container and 636,380-byte inner image before
entry. The returned 160-word report records all four pass verdicts zero,
sampled submit/wait zero, three exact `$FFFFC020` inside pixels, three exact
`$FF3380B2` outside pixels, bin and render counters 3 to 4, and zero MMU, OOM,
native-backend and detail faults. The texture-state word was `$00A9C040`, the
source-backed Z,Y,X,W logical swizzle required by BGRA8; the prior identity
swizzle was measured red as `$FF20C0FF` and is now a focused desk mutant.

That older run is one sampled linear texel, not general texture support. The
next 2026-09-13 run integrated `bf67333` through a real optimal-image resource
and `vkCmdCopyBufferToImage` transaction. A 4x4 BGRA8 source produced exact
green/blue/red sampled probes, exact clear exterior probes, TFU/bin/render
counter advances, shader-read layout, zero MMU/OOM/native faults and texture
state `$00A9C840`. Exact artifacts and hashes are in `COVERAGE.md`. This proves
only the declared one-region level-zero `UIF_NO_XOR` subset; general copies,
mips, layers, format conversion and arbitrary texture sizes remain roadmap.

The 2026-09-15 Pi 4 run also closes the first three-source fragment graph:
one optimal sampled image multiplied by a push-constant `vec4`, then added to
one UBO `vec4`. Its exact 960-byte report proves the nine lowerer-provided
uniform indices and patched words, exact expected pixels, one TFU/bin/render
advance apiece, immutable module/layout slot reuse, zero released retains, and
no new validation, MMU, OOM or native fault. The payload, report and screenshot
hashes are recorded in `COVERAGE.md`. This remains a bounded straight-line
binary32 graph with one live load from each resource family; broader SSA,
control flow, descriptor multiplicity and texture shapes remain roadmap.

### Immediate engine-conversion tranche

Per-draw dynamic scissor, ordered multi-draw recording, exact source-over
blend, UV sampling from an optimal atlas, per-draw push tint and one-barrier
cache batching are implemented and gated. The standalone atlas/chrome
diagnostic compiles and its 211-check independent oracle is green. The final
build-148 RAM-only Pi 4 run returned exact `x0=0x6C85A0` in 10.2 seconds,
recorded one TFU advance, one bin/render pair and one DMA presentation, passed
the report and pixel oracle, and produced a clean rotated 800x1280 screenshot.
This tranche is a passed silicon gate.

The shared CPU atlas boundary needed by that adapter is now implemented.
`Neon_AtlasRasterEnsure` publishes a linear RGBA8 raster and copied glyph UV
records only after the current font generation is complete; a font change
makes every query unavailable until the next successful ensure. It neither
publishes the legacy tiled-atlas dimensions early nor performs a TFU/V3D job.
The focused emitted gate passes 26 source checks, 41 run-time assertions and
five hostile mutation checks, including the reserved opaque-white texel and
its copied UV rectangle.

That refactor and the renderer-neutral widget hook change the returning
diagnostic's exact bytes. The current 977,076-byte PMF
(`c4b43f94...7fca147b`, expected `x0=0x6C85C8`) is desk-built but awaits the
same bounded Pi rerun after the shared board lease is released; the earlier
211-check silicon result is not silently assigned to new bytes.

The first Vulkan-backed Neon adapter is implemented without a private V3D
shortcut. It keeps its pipeline, descriptor set, atlas image and vertex buffer
resident; installs an all-or-none primitive backend; records boxes, atlas text,
fans, closed outlines, line lists and clip changes through the public command
path; and publishes one consumable present intent after one frame submission.
Fans are lowered to bounded triangle lists and one-pixel outlines/lines to
bounded triangle quads, with whole-primitive capacity preflight. The real-widget
desk scene reuses the existing panel, list and menu procedures unchanged and
proves 109 quads, 47 ordered draws, 654 vertices and five expected scissor
states. A current-tree short Pi 4 run passed the widget frame on 2026-10-01:
47 draws, 654 vertices, 35 box calls, 12 text calls, 74 glyph quads, four
scissor calls, one display-DMA operation, zero fallback/refusal, and twelve
pixel probes. Five scissor states are defined by the scene but were not
independently measured. The short run skipped capacity and paired-scene checks and produced no
screenshot; evidence is in
`docs/evidence/vulkan-neon-widget-short-pi4-20261001/README.md`. A separate
current-tree mode-2 Pi 4 run passed the production fan/outline and line scenes;
both complete 64×64 BGRA captures matched the pinned native golden segments,
with 12 report probes passing. CPU work copied the completed GPU attachment to
RAM for observation; it did not render pixels. See
`docs/evidence/vulkan-neon-fan-line-pi4-20261001/README.md`. The earlier
2026-09-26 all-15-scene run at `a6b9a93` remains historical evidence for that
source. The current-source all-15-scene Pi 4 run on build 242 matched 245,760
native reference pixel bytes and passed 124 widget checks; see
`docs/VULKAN_NEON_ALL15_CURRENT_PI4.md`. The same sampled atlas path now accepts
one registered RGBA8 sprite with bounded crop, destination scaling and tint.
Four Pi 4 V3D draws produced six exact sprite pixels, including transparent
and half-alpha texels; see
`docs/evidence/neon-sprite-pi4-20261002/README.md`. A subsequent Pi 4 proof
matched eleven transformed sprite pixels for a clockwise quarter-turn, camera
translation/2× zoom and ignored-camera draw; an extreme coordinate was
rejected before fixed-point math. See
`docs/evidence/neon-sprite-transform-pi4-20261002/README.md`. A subsequent
bounded Pi 4 proof registered multiple stable-ID RGBA sprites alongside the
legacy source in the shared atlas, including a wrapped row. Four V3D draws,
24 vertices and eight exact BGRA probes passed; an oversized two-image layout
was refused before Vulkan allocation. See
`docs/evidence/neon-multi-sprite-pi4-20261002/README.md`. Desktop Neon Vulkan
integration, dynamic image replacement while active, and other board backends
remain open.
HDMI/DSI/rotation/resize and clean recovery coverage beyond these bounded
scenes also remain.

## API and object gaps

- Complete registry generation for every core 1.0 enum, bitmask, alias,
  handle, union, structure, function-pointer type, command prototype, array
  extent, optionality rule, and platform guard.
- Remaining public `vk*` entry points, platform loader integration, generated
  dispatch metadata, allocator callback semantics, extension/layer enumeration, general properties and
  limits, image-format queries beyond the exact implemented linear-BGRA8
  combination query,
  queue-family discovery beyond the one implemented family, and deterministic
  unsupported reporting.
- Full lifetime graph and host synchronization for physical devices, device
  queues, memory, buffers, images, views, samplers, shader modules, descriptor
  objects, pipeline objects, render passes, framebuffers, synchronization
  objects, queries, and pipeline caches.
- Validation of all structure types, `pNext` chains, flags, counts, pointer
  ranges, common-parent rules, command-buffer level/scope, and externally
  synchronized host access. The current internal checks cover only the objects
  named in `COVERAGE.md`.

## Native platform-services gaps

A PureMetal backend must supply the services Linux DRM gives V3DV without
porting Linux or a C runtime: page-granular GPU virtual address allocation;
buffer-object residency and pinning; cache-direction ownership; job queues;
bin/render/TFU/CSD dependencies; fences and IRQ completion; OOM handling;
timeouts, fault attribution, reset and recovery; and exclusion between clients.
Display ownership remains a separate VC4/HVS/HDMI/DSI WSI seam. Mesa's V3D
documentation likewise distinguishes V3D rendering/scheduling from VC4
display ownership.

## Memory and resource gaps

Implemented since 2026-09-10 and therefore **not** in this list: one heap and
its types, exact `VkMemoryRequirements`, allocate and free with first-fit reuse
of released holes, bind with alignment/range/double-bind/parent/type rules, and
  per-image layout and queue-family ownership for the bounded image shapes
  above.
Everything below remains missing.

- Enumerated heaps/types and exact `VkMemoryRequirements`; allocate/free,
  suballocation, bind and one checked host mapping are implemented for the
  bounded heap. Flush/invalidate entry points for a future non-coherent type,
  aliasing, dedicated allocations, and device-address lifetime remain. Sparse
  memory is unsupported until explicitly implemented.
- Buffers and buffer views with bounds, usage, sharing mode, queue-family
  ownership, and texel formats.
- Images beyond the implemented linear BGRA8 and bounded level-zero
  `UIF_NO_XOR` BGRA8 subset: other dimensionalities, mip/layer planes,
  row/slice overrides, aspects, compatible views, per-subresource layout and
  broader format feature tables remain missing.
- Sampler state beyond the bounded nearest/linear, clamp-to-edge, LOD-zero
  subset; normalized/unnormalized coordinate variants, other addressing,
  compare, border color and anisotropy capability. Combined-image-sampler
  SPIR-V, V3D texture fetch and the bounded level-zero BGRA8 sampled pixel are
  implemented; descriptor arrays, multiple live samples, general image
  operands, mip selection and broader formats remain missing.

## Synchronization and command gaps

Implemented since 2026-09-10 and therefore **not** in this list: `VkFence` with
its two states and its single owner, `vkResetFences`, `vkGetFenceStatus`, a
doubly bounded `vkWaitForFences`, `vkDeviceWaitIdle`, image memory barriers
with layout transitions checked against the recording and against the image,
and the access/stage scope rules that make the clear after a transition
correct. Core-1.0 binary semaphores now have public create/destroy, ordered
wait/signal arrays in one `VkSubmitInfo`, pending generation ownership, and
completion/fault rollback tied to the real queue flight. Everything below
remains missing.

- Events, timeline semaphores, general pipeline barriers, memory/buffer/image
  barriers, access masks, stage masks, queue-family transfers, availability and
  visibility, host/device domains, and simultaneous queue submissions.
- General command allocation arrays, secondary execution and inheritance,
  simultaneous-use and pending resubmission rules, reset/release behavior, and
  command-pool external synchronization beyond the current state engine.
- Blits, resolves, mip transitions, depth/stencil clears and multi-range
  clears remain missing. Transfer support now includes the whole-image optimal
  TFU upload plus separately bounded partial optimal uploads and optimal/linear
  image-copy and readback paths on Pi 4; consult `COVERAGE.md` for the exact
  shapes and silicon evidence. These Pi 4 capabilities do not establish support
  on another board. TFU is not represented as a general memcpy.
- Queries, timestamps, conditional behavior, dynamic state other than the
  implemented per-draw viewport/scissor pair, indirect draws, dispatch, and broader
  render-pass commands. The sixteen-byte fragment push-constant block is
  implemented.

## SPIR-V and pipeline roadmap

1. Parse and validate SPIR-V headers, instruction word counts, IDs, types,
   storage classes, capabilities, extensions, decorations, structured control
   flow, entry points, execution modes, and Vulkan-environment restrictions.
   Reject unknown or unsupported instructions; never silently drop them.
2. Build a target-neutral typed SSA/control-flow IR. Preserve integer widths,
   floating-point behavior, vector/matrix layout, pointer provenance,
   `NonWritable`/`NonReadable`, interpolation decorations, precision,
   specialization constants, and deterministic diagnostics tied to SPIR-V IDs.
3. Link stage interfaces and lower Vulkan resources: descriptor set/binding,
   push constants, vertex inputs, fragment outputs, built-ins, image operands,
   atomics and memory semantics. Implement robust bounds behavior only when the
   advertised feature requires it.
4. Legalize separately for V3D 4.2 coordinate, vertex, fragment and compute
   stages: VPM layout, TMU/TLB accesses, interpolation, derivatives, control
   flow, barriers, workgroup memory, and stage-specific thread switching.
5. Select and schedule QPU instructions, allocate registers and accumulators,
   manage uniform streams/VPM/TMU hazards, encode branches and signals, and
   verify every binary with an independent decoder plus execution fixtures.
6. Create immutable pipeline layouts and graphics/compute pipelines: descriptor
   compatibility, render-pass/subpass compatibility, fixed-function raster,
   depth/stencil, blend, multisample, vertex input, dynamic-state masks, shader
   variants, executable ownership, and cache serialization/versioning.
7. Lower recorded commands into bounded V3D bin/render/CSD/TFU jobs with all
   referenced resources retained until completion. Add shader/pipeline cache
   invalidation keyed by compiler, GPU revision, render state and specialization
   data.

No source-to-source GLSL shortcut can replace this pipeline while claiming
Vulkan shader behavior. SPIR-V acceptance must be capability-driven and its
coverage machine-readable.

## WSI, testing, and conformance gaps

- Surface/swapchain objects, format/present-mode negotiation, acquire/present
  synchronization, image ownership, resize/loss, and separate HDMI/DSI
  presentation. The current display layer is only the future seam.
- Generated ABI fixtures for every public structure/union on each supported
  target, negative compile tests for unsupported layout forms, registry drift
  checks, state-model tests, memory-model litmus tests, shader differential
  tests, packet decode tests, fault injection, and hardware cache-on/off runs.
- Khronos CTS integration and a published pass/waiver matrix. No Vulkan version
  or conformance claim is permitted before the mandatory baseline and CTS
  requirements for that claim are actually satisfied.

## The board proof for the clear

A separate current-tree Pi 4 proof exercised the public whole-image clear at 1024×768 with a 4,096-byte pitch. Its 786,432 pixels matched exactly, its adjacent guard was unchanged, and one bin/render pair completed without OOM, MMU, native or validation faults. The raw `ERR_STAT` value `$1000` after each job is VCDI idle status, not a hardware error. It remained offscreen with no presentation; see `docs/evidence/vulkan-clear-extent1024-pi4-20261001/README.md`. This does not widen the advertised backend limits or establish another board path.

The original `RaspberryPi4/Examples/Diagnostics/vulkanClearProof.pi4` proof
reserves the second half of a double-height
framebuffer as the offscreen window, creates the image through the public
entry points, poisons every word of it with the complement of the expected
value, submits the transition and the clear, waits on the fence, and then:

- requires both the bin and the render completion counters to have advanced;
- requires no binner OOM and no V3D MMU fault, and records the error status,
  violation address and violation id whether or not they are zero;
- compares EVERY pixel against the exact expected little-endian B, G, R, A
  bytes, and reports the mismatch count and the first bad offset;
- compares a checksum of the LIVE framebuffer taken before the submission
  against one taken after it, so "the GPU wrote only the image it was given"
  is measured rather than assumed;
- copies the finished image onto the shown half so a person can see it, which
  is a copy and not a page flip because a non-zero virtual offset scans out
  blurred on this firmware;
- calls `NeonShutdown()` before returning, handing the V3D MMU back.

It must be run with the accelerated console taken off V3D first (`screen dma`),
because it initialises the graphics engine itself and two owners of one V3D
page table cannot be made to work. Recovery is `screen on` then `screen v3d`;
nothing in it releases a core, writes a spin slot, or touches the monitor, its
variables, the DSI control registers or any reserved region.

Still owed after that run, and not claimed by it: caches on as well as off,
an injected unmapped address requiring a bounded fault rather than a hang, and
a second submission after the first to show the resources were really released.

The bounded optimal-image transfer paths also include an isolated one-utile optimal-to-linear `vkCmdCopyImage` microcopy. It copies a 1–4 by 1–4 BGRA8 rectangle wholly within one 4×4 UIF utile to a distinct equal-size linear image, using `LINEAR_TRANSFER` plus `TILED_TO_LINEAR_MICRO_COPY`. On Pi 4 it writes the requested rows through guarded DMA, after checking destination pitch and span; no CPU pixel or TFU path is used. Other backends fail closed. The 2026-10-01 proof changed four destination texels, preserved 252, and left the source’s 256 texels unchanged including twelve same-utile neighbors. The measured 64-byte linear pitch had zero row padding; separate oracle and guard checks covered 64 padded words and 96 guards. DMA advanced 0→1, backend jobs 1→2, TFU remained 1. A crossing-utile request was refused with `-20005` during recording. Submit-time whole-stream preflight remains desk-only. See `docs/evidence/vulkan-optimal-linear-microcopy-pi4-20261001/README.md`.

The partial linear-to-optimal paths also include an isolated one-utile `vkCmdCopyImage` microcopy. It copies a 1–4 by 1–4 BGRA8 rectangle from a linear source into a distinct equal-size optimal image, wholly within one destination 4×4 UIF utile. On Pi 4 it requires `LINEAR_TRANSFER`, `LINEAR_TO_TILED_RECT_COPY` and `LINEAR_TO_TILED_MICRO_COPY`, checks the actual source pitch/span and destination utile window, and uses guarded DMA only. Other backends fail closed. The 2026-10-01 proof changed four texels, preserved 252 including twelve same-utile neighbors, and left all 256 source texels unchanged. The 64-byte source pitch had zero row padding; source offset/span were 332/72 bytes and destination UIF offset was 1,316 bytes. Separate oracle and guard checks covered 64 padded words and 96 guards. TFU remained at 1, DMA advanced 0→1, jobs 1→2. A destination crossing-utile request was refused with `-20005` during recording before DMA. Submit-time whole-stream preflight remains desk-only. See `docs/evidence/vulkan-linear-optimal-microcopy-pi4-20261001/README.md`.

The bounded optimal upload paths also include a two-by-two UIF grid `vkCmdCopyBufferToImage` capability. One interior region may intersect up to two adjacent tile columns and rows; on Pi 4, all tile source spans and destination windows are preflighted before guarded DMA. It requires `BUFFER_TRANSFER`, `LINEAR_TRANSFER`, `BUFFER_TO_TILED_RECT_COPY` and `BUFFER_TO_TILED_GRID_COPY`, while the complete-image TFU upload remains unchanged. Other backends fail closed. The 2026-10-01 proof uploaded a `5×5` region at `(3,3)` through four intersections (`1×1`, `4×1`, `1×4`, `4×4`), changed 25 texels and preserved 231, including 39 neighbors inside the touched grid. Source checks covered 25 exact words plus 327 sentinels, including 15 padding words; separate oracle checks covered 64 padded words and 96 guards. TFU remained at 1, DMA advanced 0→4, jobs 1→2, and later readback advanced DMA 4→20. The recorded `6×6` refusal was tested with only the original ≤2×2 grid cap, before the extended cap existed. With `BUFFER_TO_TILED_GRID_4X4_COPY` enabled, an otherwise-valid `6×6` region can be admitted; that exact size has not been silicon-tested. Submit-time malformed-stream preflight remains desk-only. See `docs/evidence/vulkan-buffer-optimal-grid-pi4-20261001/README.md`.

The optimal buffer-upload grid now has a separate Pi 4-only extension for rectangles spanning three or four UIF columns or rows, up to 16 intersections. `BUFFER_TO_TILED_GRID_4X4_COPY` and tag 4 provide this shape; the earlier `BUFFER_TO_TILED_GRID_COPY` and tag 3 remain bounded to two rows and columns. The region uses the 64-byte buffer-offset rule and exact pitched source span; all tile intersections are preflighted before guarded DMA. Other backends fail closed. The 2026-10-01 proof copied 81 texels from `(3,3)` extent `9×9`, preserving 175 including 63 in the touched 12×12 grid. Offset was 64, pitch 48 and source span 420 bytes; nine intersections were `1×1`, `4×1`, `4×1`, `1×4`, `4×4`, `4×4`, `1×4`, `4×4`, `4×4`. Source checks covered 81 exact words plus 271 sentinels, including 27 row-padding words; oracle padding and guards covered 64 and 96 words. TFU stayed at 1, DMA advanced 0→9, jobs 1→2, and later oracle readback advanced DMA 9→25. All reported status and fault counters were zero. Fifth-row/column refusal and submit-time malformed-stream preflight are desk-only. See `docs/evidence/vulkan-buffer-optimal-grid4-pi4-20261001/README.md`.

A separate maximum-boundary Pi 4 proof exercised all sixteen 4×4-grid intersections with one 13×13 buffer upload at `(3,3)` into a 16×16 image. The row-major texel counts were `[1,4,4,4]` followed by `[4,16,16,16]` for each remaining row. It changed 169 texels and preserved 87; buffer offset/pitch/span were 64/64/820 bytes. Checks covered 169 source words, 39 row-padding words, 183 total sentinels, 64 readback-padding words and 96 guards. Partial upload DMA advanced by 16 in one backend job while TFU stayed unchanged; the full-image readback advanced DMA by another 16. Status, MMU, OOM, native and validation-fault counts were zero. The evidence is `docs/evidence/vulkan-buffer-optimal-grid4-max-pi4-20261001/README.md`. This exercises the upper 4×4 boundary on Pi 4 only; other backends remain fail-closed and full-image TFU behavior is unchanged.

### Bounded partial optimal-to-optimal edge-tail copy

The shared `vkCmdCopyImage` API supports one partial region per command buffer between distinct, equal-size level-zero BGRA8 `UIF_NO_XOR` images. Source and destination XY offsets remain 4-texel aligned. Width or height may end with a short UIF tile only when that dimension reaches the right or bottom edge in both images; the ceil-divided tile count is capped at 256. This shape requires `TILED_RECT_COPY` plus the separate `TILED_EDGE_TAIL_COPY` capability. Whole-image copies retain their TFU path, aligned full-utile rectangles retain the rectangle path, and one-utile microcopies retain their separate path. The Pi 4 backend preflights all clamped tile windows and performs guarded DMA for valid texel rows only, preserving source data, untouched destination texels and padded UIF storage. Other backends fail closed.

The 2026-10-01 Pi 4 proof copied a `(8,8)` `5×5` region between distinct 13×13 images: 25 destination texels changed, 144 stayed unchanged, and all 169 source texels were unchanged. The report checked 338 exact staging words plus 78 staging-padding words, 91 readback-padding words in each full readback, and 160 guard checks. TFU stayed at 2, partial DMA advanced 0→4 and jobs 2→3; the oracle readbacks advanced DMA 4→20→36. A non-edge `(4,4)` `5×5` request returned `-20005` during `vkEndCommandBuffer` before further DMA. Status slots were zero; MMU, OOM and native faults were zero, with one intentional validation fault. The measured trace is `docs/evidence/vulkan-optimal-optimal-edge-tail-pi4-20261001/report.bin`; the PMF SHA-256 is `8594C760D6E3206CFDC5DEAE41DBAAF6C0A770EDDA5FB5A369EBC3AA40ED027F`.

A separate Pi 4 right-edge-only `5×4` proof copied from source `(8,4)` to destination `(8,8)` in distinct 13×13 optimal images. Its full-image oracles matched 20 copied and 149 untouched destination texels, including five immediately below the rectangle; all 169 source texels remained unchanged. The partial copy advanced guarded DMA 0→2 and backend jobs 2→3 while TFU stayed at 2. Both full-image readbacks then advanced DMA 2→18→34. Staging, readback padding and 160 guards passed; all status, MMU, OOM and native-error slots were zero. A nonedge source `(4,4)` request returned `-20005` during recording without another DMA operation. The measured report is `docs/evidence/vulkan-optimal-optimal-right-edge-pi4-20261001/report.bin` (SHA-256 `B8B121A0578237D93DD3D0DB8B7571253A27C8AC3B7958703A22C21B343D9D5B`). This adds no capability claim for other boards.

A separate Pi 4 bottom-edge-only `4×5` proof copied from source `(4,8)` to destination `(8,8)` in distinct 13×13 optimal images. Its full-image oracles matched 20 copied and 149 untouched destination texels, including five immediately right of the rectangle; all 169 source texels remained unchanged. The partial copy advanced guarded DMA 0→2 and backend jobs 2→3 while TFU stayed at 2. Both full-image readbacks then advanced DMA 2→18→34. Staging, readback padding and 160 guards passed; all status, MMU, OOM and native-error slots were zero. A nonedge source `(4,4)` request returned `-20005` during recording without another DMA operation. The measured report is `docs/evidence/vulkan-optimal-optimal-bottom-edge-pi4-20261001/report.bin` (SHA-256 `E52AAB7AD6905E56EDACBD98A89DF2EBA4EC51467D5C39EBCDDB6DE48511F77D`). This adds no capability claim for other boards.

A direct public `vkCmdFillBuffer` request also passed on Pi 4 silicon on 2026-10-01: 16 words were filled, 48 remained unchanged, and the alignment-derived guard layout passed. The valid request added one guarded DMA operation and backend job without changing TFU, V3D bin/render or display counters. An offset-2 request returned `-20001` before additional DMA. See `docs/evidence/vulkan-buffer-fill-pi4-20261001/README.md`. This does not add a capability claim for other boards.
