# Vulkan compatibility roadmap and exact gaps

This is a coverage inventory, not a version or conformance claim. The schema
target is `VK_API_VERSION_1_0`, generated from the pinned registry identified
in `COVERAGE.md`. Production currently exposes no physical device.

Primary API references are the [Khronos Vulkan Registry](https://registry.khronos.org/vulkan/),
the Vulkan specification's [clear-command definition](https://registry.khronos.org/vulkan/specs/latest/html/vkspec.html#clears-images-outside-render-pass),
and the pinned `vk.xml`. The V3D implementation reference is Mesa's
[V3D/V3DV documentation](https://docs.mesa3d.org/drivers/v3d.html) plus the
versioned Mesa sources cited next to packet/register code in
`RaspberryPi4/Lib/v3d.pi4`. Mesa is a reference, not an Anvil runtime
dependency.

## Executable development slice

`vk_v3d_development.pi4` lowers one internal two-operation command sequence:

1. discard-only `UNDEFINED` to `TRANSFER_DST_OPTIMAL` transition;
2. full-image color clear of one externally owned, contiguous, identity-mapped
   `B8G8R8A8_UNORM` 2D image with one mip level and one array layer.

The color inputs are already quantized to exact 8-bit UNORM values. The
backend accepts only an offscreen image with the initialized Neon's physical
width, height, and pitch. It calls `NeonRetarget`, then `NeonFrameBegin` and
`NeonFrameEnd` with no draws, then restores the prior target. This is a real
V3D bin/render clear path: `V3dBinSubmit`, `V3dBinWait`, `V3dRenderSubmit`, and
`V3dRenderWait` build, launch, wait, clean V3D caches, and maintain the CPU
view of the target. There is no CPU or DMA image clear fallback.

This is not yet the public `vkCmdClearColorImage` entry point. It has no
`VkImage` object, `VkDeviceMemory`, subresource-range array, general-layout
dependency, queue-family transfer, fence, semaphore, or concurrent submit.
Submission is synchronous and exclusive. The explicit development enable does
not change `AnvilVkBackendAvailable()` and does not make a production physical
device visible.

## API and object gaps

- Complete registry generation for every core 1.0 enum, bitmask, alias,
  handle, union, structure, function-pointer type, command prototype, array
  extent, optionality rule, and platform guard.
- Public `vk*` entry points, dispatch tables, `vkGetInstanceProcAddr`, allocator
  callback semantics, extension/layer enumeration, properties, features,
  limits, format queries, queue-family discovery, and deterministic unsupported
  reporting.
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

- Enumerated heaps/types and exact `VkMemoryRequirements`; allocate/free,
  suballocation, bind, map/unmap, flush/invalidate mapped ranges, coherent vs.
  non-coherent behavior, aliasing, dedicated allocations, and device-address
  lifetime. Sparse memory is unsupported until explicitly implemented.
- Buffers and buffer views with bounds, usage, sharing mode, queue-family
  ownership, and texel formats.
- Images with all core dimensionalities, mip/layer planes, tilings, row/slice
  pitches, aspects, compatible views, layout tracking per subresource, format
  feature tables, and linear/UIF conversions. The development image binding is
  external metadata only and is not a Vulkan resource implementation.
- Samplers, normalized/unnormalized coordinates, filtering, addressing,
  compare, border color, anisotropy capability, and combined image samplers.

## Synchronization and command gaps

- Fences, binary semaphores, events, pipeline barriers, memory/buffer/image
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

## Root-only hardware proof for the development clear

Reserve a mapped offscreen image and guards without overlapping display or
module memory. Poison the image, submit the transition+clear, and require both
bin and render completion counters to advance, no MMU/OOM/cache error, every
pixel to equal the expected little-endian B,G,R,A bytes, and both guards to
remain intact. Repeat with D-cache off and on. Confirm the previously active
Neon target is restored and the HDMI/DSI front buffer is byte-for-byte
unchanged. Inject an unmapped address in a disposable run and require a bounded
fault rather than a hang. Only root performs this board proof.
