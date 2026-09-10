# Vulkan compatibility status

Anvil's objective is full Vulkan compatibility on bare metal, with core 1.0 as
the first implementation baseline. Vulkan examples should be translatable to
PureMetal without replacing Vulkan's object, command, resource, shader, memory,
or synchronization model. This is not a claim that
Anvil currently implements Vulkan 1.0, passes the Vulkan CTS, or may be
described as a conformant Vulkan implementation.

The schema target is `VK_API_VERSION_1_0`. Names and layouts are pinned to the
official Khronos `Vulkan-Headers` tag `v1.4.350`, commit
`a33416ed2ce6bf8ef48b4eda821825f66d1850d3`. The pinned `registry/vk.xml` has
SHA-256
`50BD8C0F316EABF73D1C5FE3ADD2D89EAA480DBDA9282C12C289E80E9D081E08`.
The pin defines the generated vocabulary; it does not imply support for Vulkan
1.4 or even complete Vulkan 1.0 behavior. The registry-derived material retains
the Khronos MIT notice in `licenses/Khronos-Vulkan-Registry-MIT.txt`.

## What exists now

| Area | Implemented and checked | Not implemented or not claimed |
|---|---|---|
| Registry and ABI | A PureBasic generator verifies the pinned registry hash and emits a selected core-1.0 slice. The checked-in slice has exact values used by the foundation and 19 naturally aligned AArch64 structures with registry member names and order. Emitted tests check representative sizes and nested offsets. | The complete core-1.0 enum, bitmask, alias, handle, union, structure, callback, command prototype, platform guard, optionality, and valid-usage vocabulary is not generated. No other target ABI is declared equivalent merely because AArch64 layout passes. |
| Public API | Internal native procedures implement a small ownership/state engine. | There are no public `vk*` entry points, dispatch tables, `vkGetInstanceProcAddr`, `vkGetDeviceProcAddr`, loader ABI, layer interface, or extension negotiation. Existing `AnvilVk*` procedures are an internal development surface, not a compatible Vulkan entry layer. |
| Instance and device discovery | Typed generation handles reject stale handles and wrong owners. An explicit test backend can create one synthetic instance, physical device, device, and queue. | Production `AnvilVkBackendAvailable()` returns zero and instance creation returns `VK_ERROR_INCOMPATIBLE_DRIVER`. Neither Pi 4 nor UNO Q exposes a production `VkPhysicalDevice` or graphics/compute queue. |
| Command lifecycle | Command pools and primary/secondary command buffers cover selected initial, recording, executable, pending, invalid, reset, free, and destroy transitions. The test backend completes only an empty primary submission synchronously. | Array allocation, inheritance and execution of secondaries, simultaneous use, retained resource references, externally synchronized host access, real asynchronous completion, and the full command set are absent. The synthetic empty submit is not GPU work. |
| V3D development path | One development-only command record attaches an already mapped offscreen `B8G8R8A8_UNORM` image, records an `UNDEFINED` to `TRANSFER_DST_OPTIMAL` discard transition plus full-image clear, and lowers it through `NeonRetarget`, `NeonFrameBegin`, and `NeonFrameEnd`. It restores the former target and reports native failure as device loss. | This is not public `vkCmdPipelineBarrier`, `vkCmdClearColorImage`, or `vkQueueSubmit`. There is no `VkImage`, `VkDeviceMemory`, range array, general barrier dependency, fence, semaphore, or WSI ownership. The host gate stubs the final Neon calls; the exact development clear has no independent silicon acceptance recorded here. |
| Pi 4 renderer | The existing Pi driver initializes V3D 4.2, GPU page tables, QPU encoding, bin/render control lists, TFU and CSD submission, bounded waits, cache maintenance, OOM handling, and fault evidence. Neon builds fixed UI shaders and geometry for boxes, lines, glyphs, textures, clipping, rotation, and console chrome. The console has exercised the underlying V3D bin/render path on hardware. | Neon is an engine API, not Vulkan fixed-function state. Its built-in shaders are not SPIR-V, shader modules, descriptor-backed programs, or general graphics/compute pipelines. Direct polling and single-owner global arenas are not a Vulkan queue scheduler. A working console does not prove arbitrary Vulkan commands or shaders. |
| Memory and resources | V3D and Neon have board-owned arenas, identity-mapped GPU virtual addresses, explicit cache maintenance, target bounds, and guarded synchronous ownership for their current jobs. | There are no Vulkan memory heaps/types, requirements, allocation, binding, mapping, coherent/non-coherent properties, buffers, general images, views, samplers, descriptors, aliasing rules, subresources, tilings, or queue-family ownership. Existing framebuffer or arena addresses must not be presented as `VkDeviceMemory`. |
| Synchronization | Existing Pi jobs use hardware barriers, cache operations, completion counters, bounded polling, and fault/timeout reporting. | There are no Vulkan fences, semaphores, events, pipeline barriers, access/stage scopes, availability/visibility rules, multi-submit dependencies, or host-wait semantics. Vulkan leaves substantial ordering to explicit synchronization; successful synchronous polling is not a substitute for that contract. |
| Shaders and pipelines | The V3D QPU encoder can emit selected native instructions and validates selected hazards for hand-built Neon programs. | There is no SPIR-V parser or Vulkan-environment validator, target-neutral shader IR, stage-interface linker, descriptor/push-constant lowering, QPU compiler, immutable pipeline layout, graphics/compute pipeline, render pass, framebuffer, or pipeline cache. Vulkan shader modules require valid SPIR-V and Vulkan-specific validation, not merely native QPU bytes. |
| Presentation | Pi display code owns HDMI/DSI surfaces, physical/logical rotation, cache/DMA presentation, capture, and V3D console retargeting. | There is no `VkSurfaceKHR`, platform extension, surface capability query, swapchain image set, acquire/present synchronization, present mode, resize/loss handling, or ownership transfer. Display remains a future WSI provider, separate from GPU execution. |
| Driver modules | PMFMOD v1 validates, relocates, zeroes, cache-synchronizes, and records an AArch64 module image in a board-provided arena. | Neither board wires a module arena or file discovery. The engine does not call module probe/init/quiesce entries, bind services, install stable dispatch trampolines, account for in-flight calls, or reload. It cannot currently load or activate a Vulkan backend. |

The current foundation gate passes a pinned-registry comparison, 106 emitted
lifecycle checks, an executed production no-device probe, 40 interpreted V3D
lowering checks with the hardware boundary stubbed, and a real Neon/V3D link
check that performs no MMIO. These prove vocabulary, layout, state transitions,
lowering order, and link closure only. They do not prove V3D execution,
concurrency, memory visibility, WSI, shader correctness, or conformance.

## Required architecture

The compatibility work should keep five boundaries explicit:

1. **Registry-facing API.** Generate exact public names, constants, structures,
   handles, prototypes and dispatch metadata from the pinned registry. Public
   `vk*` adapters validate `sType`, `pNext`, flags, counts, pointers, parents,
   allocator ownership, and host-synchronization rules before entering the
   object engine. Feature exposure and command availability must follow the
   advertised version and extensions. Preserve each command's actual return
   type and permitted results: do not invent a return error for a void command.
   An incomplete development surface must stay explicitly non-production;
   unsupported work must never be represented as successfully executed.
2. **Target-neutral object and command engine.** Portable `.pbi` source owns
   handles, lifetime graphs, reference retention, command streams, resource
   states, synchronization objects, capabilities, and deterministic errors. It
   contains no V3D register, packet, address, tiling, or display assumptions.
3. **Hardware backend seam.** A backend reports real limits and implements
   memory allocation/binding, cache-domain transitions, command lowering, job
   dependencies, submission, interrupt or bounded-poll completion, fault
   attribution, reset, and recovery. Pi `.pi4` code may lower to V3D; a future
   UNO Q `.unoq` backend may target its own GPU. A target with no backend must
   enumerate no usable physical device.
4. **Shader toolchain.** A native front end validates the SPIR-V module and the
   Vulkan environment, builds typed SSA/control-flow IR, links stage interfaces
   and resource decorations, then legalizes, schedules, allocates and encodes
   per backend. QPU encoding is the final Pi step, not the portable IR.
5. **WSI provider.** Platform-neutral surface and swapchain state binds to a
   board display provider. The Pi provider may use existing HDMI/DSI surfaces;
   UNO Q has no present provider today. Acquire, render ownership, cache state,
   presentation, rotation, loss, and retirement must be explicit.

This layering permits the public object and shader semantics to be shared even
when Pi V3D and a future UNO Q GPU have unrelated packet formats. It also keeps
headless compute or transfer support independent of a display.

## Prerequisites and hard gaps

- The explicit natural AArch64 structure layout, nested members, fixed arrays,
  and nested `OffsetOf` support are suitable for expanding the public ABI.
  Every generated layout still needs an independent registry-derived fixture;
  default packed structures must not be used accidentally.
- Ordinary generated A64 procedures currently place parameters and locals in
  shared static BSS. Vulkan permits concurrent host calls except where the
  specification assigns external synchronization, so general compatibility
  requires reentrant per-invocation frames before advertising thread-safe
  entry points or concurrent callbacks. A backend may serialize its hardware,
  but the current calling convention can collide in static argument/local
  storage before an internal lock could protect an entry; it is not a safe
  substitute for reentrant public call frames.
- The module format can carry relocatable AArch64 code, but its lifecycle and
  dispatch portions are deliberately inactive. Dynamic backend loading must
  wait for board-owned arenas, discovery, service binding, stable trampolines,
  in-flight accounting, and quiescence; the first backend can remain statically
  composed without changing public API semantics.
- Host allocation callbacks require exact lifetime and same-calling-thread
  behavior. Fixed internal arrays are useful for tests but cannot silently
  replace `VkAllocationCallbacks` or Vulkan's documented allocation failures.
- The Pi backend needs a real resource manager above today's single-owner V3D
  arenas: per-object GPU virtual ranges, residency, retained job references,
  cache ownership, dependency tracking, and bounded recovery. Linux DRM is not
  a runtime dependency, but the services it normally supplies cannot simply be
  omitted on bare metal.

## Compatibility path

The order below is dependency order, not a schedule:

1. Complete and continuously diff the core-1.0 registry vocabulary and public
   ABI. Add exact callable `vk*` adapters only for semantics that exist, while
   production still enumerates no device.
2. Implement host allocation, device memory, buffer/image, and synchronization
   object kernels plus a backend operation seam. Retain every resource used by
   a pending command buffer until completion.
3. Turn the existing offscreen clear into one resource-backed, fence-observable
   transfer path. Keep it an explicitly enabled development backend until the
   mandatory device surface is present.
4. Build SPIR-V parsing and Vulkan-environment validation, then a target-neutral
   typed IR. Start with one tightly declared vertex/fragment capability set;
   reject every capability, execution model, decoration, type, instruction, or
   precision behavior that is not implemented.
5. Add pipeline layouts, descriptors, render passes, fixed-function state and
   V3D QPU lowering. Differential shader tests and independent packet/QPU
   decoders precede broader instruction coverage.
6. Add the bare-metal surface/swapchain extension over the existing display
   provider, preserving separate HDMI and DSI ownership and rotations.
7. Expand features only with a machine-readable coverage matrix, negative
   tests, cache-on/off silicon checks, fault injection, and CTS results. No API
   version or conformance claim precedes the mandatory coverage and formal
   Khronos process.

## First implementable slice: resource-backed transfer submission

The next bounded slice should replace development-only attached metadata with
one real Vulkan-shaped transfer path, without claiming a production device.
Under an explicit development-backend build only, implement the exact
core-1.0 vocabulary and public adapters needed for:

- instance/device/one transfer-capable queue discovery;
- `vkGetPhysicalDeviceMemoryProperties`;
- one host-visible development heap and `vkAllocateMemory`/`vkFreeMemory`;
- `vkCreateImage`, `vkGetImageMemoryRequirements`, `vkBindImageMemory`, and
  `vkDestroyImage` for one linear, single-mip, single-layer
  `VK_FORMAT_B8G8R8A8_UNORM` image;
- command pool/buffer creation, `vkBeginCommandBuffer`, one qualifying
  `vkCmdPipelineBarrier`, one full-range `vkCmdClearColorImage`, and
  `vkEndCommandBuffer`;
- `vkCreateFence`, one-command-buffer `vkQueueSubmit` with no semaphores,
  `vkWaitForFences`, fence reset/destruction, and ordered teardown.

The portable layer owns every object, bound range, layout, reference and state
transition. A small backend operation record receives validated physical
resource metadata and a closed transfer command. The Pi implementation lowers
only that command to the existing Neon/V3D offscreen clear. The test backend
executes state only. UNO Q compiles the portable surface and reports no device;
it must neither reference Pi symbols nor claim a synthetic GPU in production.
Shaders, drawing, descriptors, WSI, semaphores, events, multiple queues and
general formats remain loudly unsupported.

Required proof gates:

- regenerate every added value/member/prototype from the pinned registry and
  execute exact AArch64 size, alignment, offset, pointer-array and `pNext`
  refusal fixtures;
- execute public entry calls, not private shortcuts, for creation, binding,
  record, submit, fence completion, teardown, stale handles, wrong parents,
  overlap, range overflow, double bind, use-after-free, destroy-while-pending,
  and allocation refusal;
- mutation-test command order, layout/access masks, retained references, fence
  signal order, failure rollback, target restoration, and the rule that an
  unsupported operation never reaches the backend;
- record the backend call stream independently and prove that the host test
  performs no CPU image clear while still avoiding MMIO;
- build a production Pi probe and an UNO Q probe that both enumerate zero
  devices when development registration is absent;
- in a separately authorized Pi hardware test, poison an offscreen allocation,
  submit the public path, require bin/render counters to advance, require clean
  fault/OOM/error state, compare every pixel and both guards, and repeat with
  caches off and on while proving the active HDMI/DSI target is unchanged.

Passing this slice would establish one honest Vulkan-shaped transfer path. It
would not establish Vulkan 1.0 implementation, shader support, presentation,
general resource behavior, concurrency, or conformance.

## Primary specifications

- [Khronos Vulkan Registry](https://registry.khronos.org/vulkan/) explains that
  `vk.xml` is the source for API declarations and validity metadata.
- [Pinned Vulkan-Headers registry](https://github.com/KhronosGroup/Vulkan-Headers/tree/a33416ed2ce6bf8ef48b4eda821825f66d1850d3/registry)
  is the exact vocabulary source used by this tree.
- [Vulkan fundamentals](https://docs.vulkan.org/spec/latest/chapters/fundamentals.html),
  [command buffers](https://docs.vulkan.org/spec/latest/chapters/cmdbuffers.html),
  [memory allocation](https://docs.vulkan.org/spec/latest/chapters/memory.html),
  and [synchronization](https://docs.vulkan.org/spec/latest/chapters/synchronization.html)
  define the object, host-threading, command, resource and dependency behavior
  that an implementation must preserve.
- [Vulkan shaders](https://docs.vulkan.org/spec/latest/chapters/shaders.html),
  the [Vulkan environment for SPIR-V](https://docs.vulkan.org/spec/latest/appendices/spirvenv.html),
  and the [SPIR-V Registry](https://registry.khronos.org/SPIR-V/) define the
  shader input and validation boundary.
- [Window System Integration](https://docs.vulkan.org/spec/latest/chapters/VK_KHR_surface/wsi.html)
  defines the surface/swapchain separation from core execution.
- [Khronos Vulkan CTS guidance](https://github.khronos.org/Vulkan-Site/guide/latest/vulkan_cts.html)
  describes the distinction between development testing and a conformant
  implementation.

The current V3D code cites Mesa for packet and job-sequencing research. Mesa is
not a runtime dependency, and this document does not relicense or clear the
provenance of any translated driver expression. The public-source provenance
hold remains in effect: future work must use the Khronos material under its
retained terms and independently document any hardware-driver source used,
without copying GPL driver code into MIT-labeled Anvil source.
