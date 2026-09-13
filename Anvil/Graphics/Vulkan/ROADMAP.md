# Vulkan compatibility roadmap and exact gaps

This is a coverage inventory, not a version or conformance claim. The schema
target is `VK_API_VERSION_1_0`, generated from the pinned registry identified
in `COVERAGE.md`. Production currently exposes no physical device.

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

`vk_v3d_backend.pi4` executes exactly one recorded operation on the GPU: a
whole-image colour clear of one `VK_FORMAT_B8G8R8A8_UNORM`, linear, single-mip,
single-layer 2D image bound to real `VkDeviceMemory` in an offscreen window.
It is reached through the public `vkCmdClearColorImage` and `vkQueueSubmit`,
after a public `vkCmdPipelineBarrier`-shaped transition, and its completion is
observed through a public `VkFence`.

The execution path is `NeonRebindSurface`, `NeonFrameBegin` and `NeonFrameEnd`
with no draws. `NeonRebindSurface` plans and validates each accepted geometry,
rebuilds its coordinate tables, and restores the complete display-owned surface
after submission. The frame then builds and submits real V3D bin and render
control lists:
`V3dBinSubmit`, `V3dBinWait`, `V3dRenderSubmit` and `V3dRenderWait` launch,
wait, clean the V3D caches and maintain the processor's view of the target.
The tile clear and the tile store are what write the image. There is no
processor-side and no DMA image fallback anywhere under this path, and the
desk gate checks the source for one.

### What this backend still cannot do, and says so

- **Extents beyond the proved capacity.** The backend accepts linear BGRA8
  images through the V3D planner up to the configured equal width/height
  maximum and derives row pitch from the same rule used by creation and the
  public image-format query. Zero, overflowing, over-capacity or unmapped
  geometry is refused before a job counter can move. Mips, array layers,
  multisampling, optimal tiling and other formats remain unsupported.
- **The buffer the display is scanning out.** This backend is offscreen by
  contract. Presentation stays with the display layer.
- **Asynchrony.** `NeonFrameEnd` waits for both jobs before it returns, so
  nothing is genuinely in flight when `vkQueueSubmit` returns. The engine
  models the pending state correctly and the test backend exercises it, but on
  V3D the fence is signalled inside the submit. Real asynchrony needs
  interrupt-driven completion rather than the current bounded polls.
- **More than one clear per submission, and more than one submission at a
  time.** Both are refused, not truncated.

## API and object gaps

- Complete registry generation for every core 1.0 enum, bitmask, alias,
  handle, union, structure, function-pointer type, command prototype, array
  extent, optionality rule, and platform guard.
- Public `vk*` entry points, dispatch tables, `vkGetInstanceProcAddr`, allocator
  callback semantics, extension/layer enumeration, general properties and
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
- Images with all core dimensionalities, mip/layer planes, tilings, row/slice
  pitches, aspects, compatible views, layout tracking per subresource, format
  feature tables, and linear/UIF conversions. The development image binding is
  external metadata only and is not a Vulkan resource implementation.
- Samplers, normalized/unnormalized coordinates, filtering, addressing,
  compare, border color, anisotropy capability, and combined image samplers.

## Synchronization and command gaps

Implemented since 2026-09-10 and therefore **not** in this list: `VkFence` with
its two states and its single owner, `vkResetFences`, `vkGetFenceStatus`, a
doubly bounded `vkWaitForFences`, `vkDeviceWaitIdle`, image memory barriers
with layout transitions checked against the recording and against the image,
and the access/stage scope rules that make the clear after a transition
correct. Everything below remains missing.

- Binary semaphores, events, pipeline barriers, memory/buffer/image
  barriers, access masks, stage masks, queue-family transfers, availability and
  visibility, host/device domains, and simultaneous queue submissions.
- General command allocation arrays, secondary execution and inheritance,
  simultaneous-use and pending resubmission rules, reset/release behavior, and
  command-pool external synchronization beyond the current state engine.
- All buffer/image copies, blits, resolves, fills, updates, mip transitions,
  depth/stencil clears, partial color clears, and multi-range clears. TFU is a
  candidate for supported raster-to-tiled conversions, not a general memcpy.
- Queries, timestamps, conditional behavior, push constants, dynamic state,
  indexed/indirect draws, dispatch, and render-pass commands.

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

`RaspberryPi4/Examples/Diagnostics/vulkanClearProof.pi4` is the only thing that
can show this path executes. It reserves the second half of a double-height
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
