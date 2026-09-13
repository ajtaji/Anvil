# Vulkan compatibility status

Anvil's objective is full Vulkan compatibility on bare metal, with core 1.0 as
the first implementation baseline. Vulkan examples should be translatable to
PureMetal without replacing Vulkan's object, command, resource, shader, memory,
or synchronization model. This is not a claim that
Anvil currently implements Vulkan 1.0, passes the Vulkan CTS, or may be
described as a conformant Vulkan implementation.

The prerequisite for honest non-native image extents is implemented and
silicon-proved in `docs/VULKAN_DYNAMIC_RENDER_GEOMETRY_DESIGN.md`. The public
image-format query derives its limits from that same geometry and pitch owner.

The schema target is `VK_API_VERSION_1_0`. Names and layouts are pinned to the
official Khronos `Vulkan-Headers` tag `v1.4.350`, commit
`a33416ed2ce6bf8ef48b4eda821825f66d1850d3`. The pinned `registry/vk.xml` has
SHA-256
`50BD8C0F316EABF73D1C5FE3ADD2D89EAA480DBDA9282C12C289E80E9D081E08`.
The pin defines the generated vocabulary; it does not imply support for Vulkan
1.4 or even complete Vulkan 1.0 behavior. The registry-derived material retains
the Khronos MIT notice in `licenses/Khronos-Vulkan-Registry-MIT.txt`.

## What exists now

Updated 2026-09-11, when the SPIR-V front end and the first graphics
pipeline landed, and again the same day when three things followed it: a real
interpolated gradient, a second vertex input binding, and the first descriptor
type. Updated 2026-09-12 when that descriptor stopped being copied by the CPU
and gained a V3D 4.2 TMU general-load lowering. Updated 2026-09-13 when dynamic
render geometry and the matching public image-format-properties query passed
their desk and Pi 4 silicon gates.

### The implemented public entry points

These are callable `vk*` names with the registry's own parameter lists and
return types. Everything else in core 1.0 does not exist and a caller linking
one gets a compile-time refusal naming it.

| Entry point | Status |
|---|---|
| `vkCreateInstance` / `vkDestroyInstance` | Implemented. Layers and extensions are refused with `VK_ERROR_LAYER_NOT_PRESENT` / `VK_ERROR_EXTENSION_NOT_PRESENT`. |
| `vkEnumeratePhysicalDevices` | Implemented, including the two-call `pPhysicalDeviceCount` form and `VK_INCOMPLETE`. |
| `vkGetPhysicalDeviceMemoryProperties` | Implemented. One heap, backend-reported. |
| `vkGetPhysicalDeviceFormatProperties` | Implemented. A draw-capable backend reports exactly `COLOR_ATTACHMENT` for linear `B8G8R8A8_UNORM`; optimal tiling, buffers, unsupported formats and backends without the draw capability report zero. Sampled, storage, depth/stencil, blend and blit support are not advertised. |
| `vkGetPhysicalDeviceImageFormatProperties` | Implemented for the exact combinations `vkCreateImage` accepts: 2D linear `B8G8R8A8_UNORM`, flags zero, usage within transfer source/destination and colour attachment, with colour attachment conditional on a draw-capable backend. It reports backend-derived equal width/height maxima, depth 1, one mip, one layer, one sample, and a row-pitch-derived maximum byte size; every other combination returns `VK_ERROR_FORMAT_NOT_SUPPORTED`. |
| `vkGetPhysicalDeviceQueueFamilyProperties` | Implemented. One family always advertises `VK_QUEUE_TRANSFER_BIT`; it also advertises `VK_QUEUE_GRAPHICS_BIT` exactly when the linked backend has the draw capability. A transfer-only backend remains transfer-only. Compute is not advertised. |
| `vkGetPhysicalDeviceFeatures` | Implemented. The complete 55-member core-1.0 structure is written and every member currently reports `VK_FALSE`. |
| `vkCreateDevice` / `vkDestroyDevice` / `vkGetDeviceQueue` | Implemented for one queue of family 0. Device extensions and any true feature bit are refused; a null or non-null all-false `pEnabledFeatures` is accepted. |
| `vkCreateImage` / `vkDestroyImage` | Implemented for 2D, `VK_FORMAT_B8G8R8A8_UNORM`, `VK_IMAGE_TILING_LINEAR`, one mip, one layer, one sample, exclusive sharing, usage within `TRANSFER_SRC`/`TRANSFER_DST`/`COLOR_ATTACHMENT`. Everything else is refused with a real code. `COLOR_ATTACHMENT` creation is refused when the backend has no draw capability, agreeing with the format query. A framebuffer attachment must carry `COLOR_ATTACHMENT`; a transfer bit does not substitute for it. |
| `vkGetImageMemoryRequirements` | Implemented. Size, alignment and `memoryTypeBits` come from the backend. |
| `vkAllocateMemory` / `vkFreeMemory` | Implemented over one backend heap, first-fit with real reuse of freed holes and a real `VK_ERROR_OUT_OF_DEVICE_MEMORY`. |
| `vkMapMemory` / `vkUnmapMemory` | Implemented for one active mapping of a `HOST_VISIBLE` allocation, flags zero, an overflow-safe positive subrange or `VK_WHOLE_SIZE`. The returned pointer includes the requested offset; wrong owner, duplicate map, invalid range, non-visible type, unbalanced unmap and free-while-mapped are refused. Pi 4 reports this heap `HOST_COHERENT` because mandatory submission/completion cache maintenance supplies the observable promise. |
| `vkBindImageMemory` | Implemented, with alignment, range, double-bind, wrong-parent and memory-type rules enforced. |
| `vkCreateCommandPool` / `vkDestroyCommandPool` / `vkResetCommandPool` | Implemented. |
| `vkAllocateCommandBuffers` / `vkFreeCommandBuffers` | Implemented for one buffer per call; array allocation is refused, not faked. |
| `vkBeginCommandBuffer` / `vkEndCommandBuffer` / `vkResetCommandBuffer` | Implemented. A recording error moves the buffer to invalid and `vkEndCommandBuffer` reports it, as the specification requires. |
| `vkCmdPipelineBarrier` | Implemented with its exact ten-parameter registry signature. One image memory barrier per call; global and buffer barriers are refused. The final count and pointer travel through the AArch64 stack argument area and are exercised through emitted code. |
| `vkCmdClearColorImage` | Implemented with its exact registry signature, for one whole-image range. |
| `vkCreateFence` / `vkDestroyFence` / `vkResetFences` / `vkGetFenceStatus` / `vkWaitForFences` | Implemented for finite waits. `UINT64_MAX` succeeds immediately when the requested fence condition is already true; an unsatisfied unlimited wait returns `ANVIL_VK_ERR_UNSUPPORTED` until host calls are reentrant. It is never disguised as a bounded `VK_TIMEOUT`. |
| `vkQueueSubmit` | Implemented for one `VkSubmitInfo`, one command buffer, no semaphores. Batches, multiple buffers and semaphores are refused with `VK_ERROR_FEATURE_NOT_PRESENT`. |
| `vkDeviceWaitIdle` | Implemented. |

### The graphics pipeline entry points, added 2026-09-11

| Entry point | Status |
|---|---|
| `vkCreateShaderModule` / `vkDestroyShaderModule` | Implemented. The module is WALKED at creation, not stored: `vkCreateShaderModule` returns an Anvil refusal, with a sentence, for any module outside the accepted SPIR-V subset. |
| `vkCreateBuffer` / `vkDestroyBuffer` / `vkGetBufferMemoryRequirements` / `vkBindBufferMemory` | Implemented for `VK_BUFFER_USAGE_VERTEX_BUFFER_BIT`, `VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT` and the two transfer bits, exclusive sharing, page-granular alignment. |
| `vkCreateImageView` / `vkDestroyImageView` | Implemented for `VK_IMAGE_VIEW_TYPE_2D`, `VK_FORMAT_B8G8R8A8_UNORM`, identity swizzle, the whole colour subresource. |
| `vkCreateSampler` / `vkDestroySampler` | Implemented as a typed, device-owned object for normalized 2D sampling with nearest or linear min/mag filters, nearest mip mode at LOD zero, clamp-to-edge on all coordinates, and no anisotropy or comparison. This is prerequisite state only: sampled-image descriptors and shader texture fetches are not connected yet. |
| `vkCreateRenderPass` / `vkDestroyRenderPass` | Implemented for one colour attachment, one subpass, no dependencies, `loadOp` CLEAR and `storeOp` STORE. |
| `vkCreateFramebuffer` / `vkDestroyFramebuffer` | Implemented for one attachment at the image's own extent, one layer. |
| `vkCreatePipelineLayout` / `vkDestroyPipelineLayout` | Implemented for zero or one descriptor set layout and at most one push constant range: fragment stage, offset 0, 16 bytes. |
| `vkCreateDescriptorSetLayout` / `vkDestroyDescriptorSetLayout` | Implemented for one or two bindings numbered 0..n-1, each `VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER`, `descriptorCount` 1, at `VK_SHADER_STAGE_FRAGMENT_BIT`. Every other descriptor type is refused with its own sentence naming it. Destroying a layout under a live set is refused. |
| `vkCreateDescriptorPool` / `vkDestroyDescriptorPool` / `vkResetDescriptorPool` | Implemented for one pool size of uniform buffers. `VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT` is refused, and so are reset and destroy while a submission is in flight. |
| `vkAllocateDescriptorSets` | Implemented for one set per call, against the pool's own `maxSets` and descriptor count, with `VK_ERROR_OUT_OF_POOL_MEMORY` when either is exhausted. |
| `vkFreeDescriptorSets` | Present and refuses, naming the pool bit it would need. It is not missing from the link; it says why it cannot work. |
| `vkUpdateDescriptorSets` | Implemented for one write per call and no copies: uniform buffer, `dstArrayElement` 0, `descriptorCount` 1, a `pBufferInfo` whose buffer is live, bound and carries the uniform usage, at an offset that is a multiple of sixteen and a range of at least sixteen (`VK_WHOLE_SIZE` accepted). Refused while a submission is in flight. |
| `vkCmdBindDescriptorSets` | Implemented for one set at index 0, no dynamic offsets, `VK_PIPELINE_BIND_POINT_GRAPHICS`, through the pipeline layout the set's own layout belongs to. |
| `vkCreateGraphicsPipelines` / `vkDestroyPipeline` | Implemented for exactly one `VkGraphicsPipelineCreateInfo` per call and no pipeline cache. See the state table below for what it accepts. |
| `vkCmdBeginRenderPass` / `vkCmdEndRenderPass` | Implemented for `VK_SUBPASS_CONTENTS_INLINE`, one clear value, a render area that is the whole framebuffer. |
| `vkCmdBindPipeline` | Implemented for `VK_PIPELINE_BIND_POINT_GRAPHICS`. |
| `vkCmdBindVertexBuffers` | Implemented for a range of bindings inside 0..3, bound one at a time, so one call binding two buffers and two calls binding one each leave the same state. |
| `vkCmdPushConstants` | Implemented for the whole sixteen-byte fragment-stage block at offset 0. |
| `vkCmdDraw` | Implemented for one instance and a vertex range inside every bound buffer. A zero vertex count is a no-op and consumes no backend draw slot. `TRIANGLE_LIST` accepts any positive vertex count; its primitive assembler discards an incomplete final triangle. |

The fixed-function state a pipeline may declare: one to four vertex input
bindings numbered 0..n-1, each at `VK_VERTEX_INPUT_RATE_VERTEX` with a stride
that is a positive multiple of four, and each read by at least one attribute -
a binding nothing reads is refused rather than ignored; attributes at locations
0..n-1 (n <= 4) in `R32G32_SFLOAT`, `R32G32B32_SFLOAT` or
`R32G32B32A32_SFLOAT`, each naming one of those bindings and fitting inside
THAT binding's stride; `VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST` with no primitive restart; one
viewport and one scissor, neither dynamic, the scissor covering the viewport
and the viewport starting at the origin with whole-pixel extents; fill mode, no
culling, no depth bias, no depth clamp, no rasteriser discard; one sample;
`pSampleMask` either null (sample zero enabled) or naming one word whose bit
zero controls that sample; blending disabled and every channel written; no depth-stencil state and no
dynamic state. Everything else is refused with a code and a sentence.


`vkCmdPipelineBarrier`'s ten-parameter problem is closed. Compiler revision
`a9f412a6` added aligned AArch64 stack arguments, so Anvil now exposes the
registry prototype directly and no longer carries an argument-record adapter.
The resource gate executes the real call: argument nine is the image-barrier
count and argument ten is its pointer, making both the caller and callee sides
observable.

### The layers

| Area | Implemented and checked | Not implemented or not claimed |
|---|---|---|
| Registry and ABI | A PureBasic generator verifies the pinned registry hash and emits a selected core-1.0 slice. The checked-in vocabulary covers 67 naturally aligned AArch64 structures with registry member names, order and widths. The complete 55-member `VkPhysicalDeviceFeatures` record, `VkFormatProperties`, `VkImageFormatProperties` and `VkSamplerCreateInfo` are among them. The gate regenerates every one from pinned `vk.xml` and executes exact size and `OffsetOf` fixtures. | The complete core-1.0 enum, bitmask, alias, handle, union, callback, command prototype, platform guard, optionality and valid-usage vocabulary is not generated. `VkClearColorValue` is a union and is deliberately not declared — PureMetal has no union, so the adapter reads the caller's sixteen bytes as the `float32` arm and says so. No other target ABI is declared equivalent merely because AArch64 layout passes. |
| Public API | The entry points in the table above, validating `sType`, `pNext`, flags, counts, pointers, parents and host-synchronization rules before entering the object engine. Invalid usage that core Vulkan leaves undefined returns an Anvil code far outside `VkResult`'s range, with a whole sentence naming the code and the next thing to check; void commands record that sentence and, where the specification allows, invalidate the command buffer. | There is no loader, `vkGetInstanceProcAddr`, `vkGetDeviceProcAddr`, dispatch table, layer interface, extension negotiation or `VkAllocationCallbacks` support. Host allocation callbacks are refused rather than ignored. `AnvilVkImageAddress` remains a diagnostic oracle, not an application API; applications can now use `vkMapMemory`. Concurrent host calls are still unsafe — see the prerequisites. |
| Instance and device discovery | Typed generation handles reject stale handles and wrong owners across all ten object types. One instance, physical device, device and queue, over whichever backend is linked. The queue derives graphics support from the backend's draw capability; compute remains absent. The format query derives linear BGRA8 colour-attachment support from that capability. The image-format query shares creation's format/type/tiling/usage/flags owner and derives extent and maximum resource bytes from backend geometry and pitch. | General physical-device properties and limits, sparse-image format properties and extension-property enumeration remain absent. A production Pi build enumerates a device only when the graphics engine is up and an offscreen window is declared. UNO Q links `vk_backend_none.pbi` and enumerates nothing. |
| Command lifecycle | Pools and primary/secondary buffers across initial, recording, executable, pending, invalid, reset, free and destroy. Resources a submission references are retained until it completes, and reset, free, pool reset and pool destroy all refuse while a buffer is pending. Exactly one submission may be outstanding. A command buffer is either a transfer or a render pass and never both; a render pass holds one draw; a render pass left open at `vkEndCommandBuffer` is refused. | Secondary execution and inheritance, simultaneous use, array allocation, externally synchronized host access, and the rest of the command set are absent. |
| Pi 4 V3D backend | `vk_v3d_backend.pi4` lowers validated whole-image clears and accepted draws through transactional `NeonRebindSurface` + `NeonFrameBegin` + `NeonFrameEnd`. It submits real V3D jobs, maintains both cache domains, and restores the complete display geometry. It refuses the scanout buffer and reports native failure as `VK_ERROR_DEVICE_LOST`. There is no processor-side or DMA image fallback. The 2026-09-13 silicon runs proved native, smaller non-square and partial-tile images, the over-capacity refusal, an ordinary display frame, and three consecutive descriptor/varying jobs. | Dynamic viewport, render subrects, multiple render targets, mip levels, layers, MSAA and formats beyond linear BGRA8 remain unsupported. Submission is synchronous. Sample-mask suppression is desk-proved but still needs silicon visual proof. |
| Pi 4 renderer | The existing Pi driver initializes V3D 4.2, GPU page tables, QPU encoding, bin/render control lists, TFU and CSD submission, bounded waits, cache maintenance, OOM handling, and fault evidence. Neon builds fixed UI shaders and geometry for boxes, lines, glyphs, textures, clipping, rotation, and console chrome. The console has exercised the underlying V3D bin/render path on hardware. | Neon is an engine API, not Vulkan fixed-function state. Its built-in shaders are not SPIR-V, shader modules, descriptor-backed programs, or general graphics/compute pipelines. Direct polling and single-owner global arenas are not a Vulkan queue scheduler. A working console does not prove arbitrary Vulkan commands or shaders. |
| Memory and resources | One heap, taken whole from the backend and suballocated first-fit with page-granular alignment. `VkDeviceMemory`, `VkImage`, `VkBuffer` and the bounded `VkSampler` subset are real typed objects with generations and owners; memory-backed resources also carry bind and in-flight counts. A compiled pipeline's shaders take an INTERNAL allocation from the same heap that no handle names and `vkFreeMemory` cannot reach. Row pitch and image size come from the backend's rule, not from the width. A host-visible allocation supports one checked `vkMapMemory` range, including `VK_WHOLE_SIZE`, and must be unmapped before free. Pi 4's identity-mapped window is advertised `HOST_COHERENT` because draw submission cleans every GPU-read pipeline, descriptor and vertex range and render completion cleans GPU caches then cleans+invalidates the ARM view of the render target before the fence can signal. | There are no buffer views, sampled-image descriptors, mip levels, array layers, tilings other than linear, aliasing, dedicated allocations, sparse memory, flush/invalidate mapped-range entry points, index buffers, storage buffers, or formats other than `B8G8R8A8_UNORM`. A sampler is not useful to a shader until the combined-image descriptor and QPU texture lowering land. A uniform buffer exists and is reachable through one descriptor type and nothing else. There is one queue family, so queue-family ownership transfer is refused rather than implemented. |
| Synchronization | `VkFence` with its two states and its one owner: unsignalled and unused at submit, signalled at completion, refusing reset and destroy while in use. `vkWaitForFences` honours finite timeouts and is bounded twice so a stalled backend cannot hang the caller. An already-satisfied `UINT64_MAX` wait succeeds; an unsatisfied one is explicitly refused rather than reported as a false finite timeout. Image memory barriers carry layout tracking checked at record time and again at submit time, with access/stage scopes that must cover the transfer they precede. | There are no semaphores, events, timeline semaphores, global or buffer memory barriers, multi-submit dependencies, or concurrent queues. Submission on the V3D backend is synchronous: the bounded waits are inside `NeonFrameEnd`, so nothing is genuinely in flight when `vkQueueSubmit` returns. A genuinely unlimited wait that could be satisfied by another host thread is not implemented and needs reentrant call frames first. |
| Shaders and pipelines | A SPIR-V front end parses a module, validates it against the Vulkan environment and refuses by name everything outside one declared subset: a pass-through vertex shader, and a fragment shader whose colour is an interpolated varying, a push-constant member, a uniform-block member or a constant. A V3D emitter turns that subset's plan into the three QPU programs, their uniform streams and a GL shader state record. A uniform-buffer descriptor keeps its GPU-visible address in the fragment stream; a V3D 4.2 TMU general vec4 load dereferences it in the QPU, and the backend proves the range mapped and cleans it before submission. The clean-state 2026-09-13 Pi 4 run proved the fetched colour and the complete descriptor stream. A pipeline object owns the fixed-function state, the stage interface match, the vertex input layout across one to four bindings, and the match between the fragment shader's `DescriptorSet`/`Binding` decorations and the descriptor set layout its pipeline layout declares. A render pass and framebuffer own the colour attachment. | There is no target-neutral shader IR, no register allocator, no scheduler and no instruction selection - the emitter assigns registers by counting, which is enough for the accepted subset and nothing else. There is no arithmetic in an accepted shader, no control flow, no sampled-image descriptor, no storage buffer, no dynamic descriptor, no descriptor array, no descriptor copy, no push descriptor, no specialization constant, no pipeline cache, no derivative pipeline, no compute pipeline, no second subpass, no depth attachment and no blending. A `VkSampler` object exists, but no shader can consume it until the image descriptor and texture fetch lower together. Internal clear lowering is still not a shader compiler and this is still not one either. |
| Presentation | Pi display code owns HDMI/DSI surfaces, physical/logical rotation, cache/DMA presentation, capture, and V3D console retargeting. | There is no `VkSurfaceKHR`, platform extension, surface capability query, swapchain image set, acquire/present synchronization, present mode, resize/loss handling, or ownership transfer. The board diagnostic presents by copying the finished image onto the shown half of the framebuffer, which is the display layer's own path and not WSI. |
| Driver modules | PMFMOD v1 validates, relocates, zeroes, cache-synchronizes, and records an AArch64 module image in a board-provided arena. | Neither board wires a module arena or file discovery. The engine does not call module probe/init/quiesce entries, bind services, install stable dispatch trampolines, account for in-flight calls, or reload. The Vulkan backend is statically composed, which the layering permits. |

### What the gates prove, and what they do not

| Gate | Result | What it proves |
|---|---|---|
| `Anvil/Graphics/Vulkan/Tests/vulkan_foundation_check.py` | PASS — pinned registry compared, 184 emitted ABI and lifecycle checks over 143,865 interpreted A64 instructions, production boundary in 40,768. The queue mutant, all three feature mutants, all seven format-query mutants and all thirteen image-format-query mutants are RED. | Vocabulary against the pinned `vk.xml`, exact AArch64 layout including all 18 members of `VkSamplerCreateInfo`, and that a build with no backend enumerates no device. The feature properties poison then query the complete record, accept a non-null all-false record, and turn on each of its 55 members separately. Format properties require exactly proved linear BGRA8 feature bits. Image-format properties require the shared create/query combination owner, backend-derived geometry and pitch-derived maximum bytes, one mip/layer/sample, stale-handle and caller-output safety, and refusal of every unsupported input. The queue properties prove an ordinary graphics-family scan selects family zero for a draw-capable backend and finds no graphics family for a transfer-only backend. Every checked structure member name, order and type is compared against both the registry and `vk_core_1_0.pbi`, so the two transcriptions have to agree. |
| `tools/vulkan_resource_check.py` | PASS — 484 independent property checks over 826,168 executed A64 instructions. The earlier complete mutation run rejects all 30 prior mistakes; the two focused `UINT64_MAX` mutants, all ten focused map-memory mutants and the focused transfer-only attachment mutant are RED. The suite now has 43 mutants; a fresh complete run of all 43 has not been claimed. | The resource, layout, fence, retention, mapping, format-capability, submission and error-reporting contracts, executed through the public entry points, with an MMIO hard stop armed; and that every byte of the bound image still held its poison, so no processor-side clear exists anywhere in the path. Its mapping properties use the public entry points to distinguish host-visible/non-visible types, owner, live/stale handle, duplicate/unbalanced state, flags, exact/whole ranges and returned pointer, then use the mapping to poison the image. Its format property refuses colour-attachment image creation when the backend advertises no graphics draw path while the shared combination owner still accepts transfer-only usage. Its wait properties distinguish an unsignalled unlimited wait (explicitly unsupported) from an already-satisfied unlimited wait (success). |
| `tools/vulkan_v3d_backend_check.py` | PASS — 84 property checks over 108,668 executed A64 instructions; `--mutate` rejects all 16 desk-reachable mistakes and names 2 board-only rules it cannot reach. | That the whole closure links against the real display, V3D, QPU and Neon implementation; that a build with the engine down enumerates no device without MMIO; that geometry is planned before mutation, every arena/range/in-frame boundary is checked, and a failed rebind preserves the prior surface. It also requires full geometry restoration and the descriptor TMU mapped-range/cache-clean contracts. The source contract requires the pipeline/vertex/descriptor cleans before submission and the GPU clean plus target clean/invalidate before completion, giving the `HOST_COHERENT` advertisement teeth. |
| `tools/vulkan_spirv_check.py` | PASS — 404 property checks over 4,755,621 executed A64 instructions; `--mutate` rejects all 28 plausible mistakes | That 52 SPIR-V modules, assembled word by word IN THE CHECKER from the specification's own opcode numbers, are walked correctly: 7 inside the subset are lowered to a plan whose every field is checked, and 45 outside it are refused with a whole sentence naming the opcode, capability, decoration, built-in, storage class or descriptor placement. The front end makes no MMIO access and does not write one byte of the module it was handed |
| `tools/vulkan_pipeline_check.py` | Baseline PASS — 189 property checks over 9,363,580 executed A64 instructions. The gate includes the bounded `VkSampler` lifecycle and exact refusal of an unsupported address mode; focused mutations that leave the sampler non-live or silently accept repeat addressing are both RED. Focused mutations also reject both an incomplete TMU general-load configuration and a second sideband-uniform consumer on the address write. The earlier full run rejected 47 of 53; the focused validation-truth gate rejects its repaired six, `--mutate-only image-usage` rejects all three image-usage mutants, `--mutate-only sample-mask` rejects both sample-mask mutants, and `--mutate-only draw-count` rejects both zero/incomplete-count mutants. A fresh complete run of the enlarged suite has not been claimed. | That the whole public path from `vkCreateShaderModule` to `vkQueueSubmit` reaches the backend with the right numbers, that recording and creation rules refuse what they say they refuse, and that every byte of four shader variants' compiled records, attribute records, uniform streams and default attribute values matches a record the checker packs itself from the documented V3D field layout. The first render pass records a zero-vertex no-op followed by its one real draw; another submits four vertices and the backend receives all four for triangle-list assembly to discard only the incomplete final primitive. The render target carries `COLOR_ATTACHMENT` and `TRANSFER_SRC`, not `TRANSFER_DST`; a separate transfer-only image creates successfully but is refused as a framebuffer attachment by the owning usage rule. A fifth, otherwise-identical pipeline supplies a zero sample mask; its fifth submitted draw retains zero in the closed backend record. One pipeline reads position from one buffer and colour from another at two different strides; another takes its colour from a uniform buffer and retains the descriptor address in a three-word stream. The checker independently decodes the signal/destination sequence and lookup fields of its raw eighteen-instruction fragment program as `LDUNIFRF rf8`, the exact ADD-side OR-move to `TMUAU` produced by the independent primary assembler with the thread switch on that same launch, two delay slots, and four `LDTMU` results in `rf0`..`rf3`. TMUAU's sideband consumes the complete regular per-quad vec4 configuration. It also compares the board diagnostic's own five hand-assembled SPIR-V modules, word for word, against the checker's, and builds both board diagnostics. No pixel of the render target is written and no MMIO access is made. |
| `tools/vulkan_interp_check.py` | PASS — 395 property checks over 372,292 executed A64 instructions; `--mutate` rejects all 14 plausible mistakes | That `vk_interp_expect.pbi` — the module the board diagnostic asks what colour a pixel should be — gives the same answers as a second implementation of the same stated rule written in Python: the clip-to-screen transform, twice the signed area, the three barycentric numerators, the strict inside test, the four channels and the packed B8G8R8A8 word, over eight triangles and thirty-three probe pixels. The weights at every covered probe sum to twice the area, and each corner probe is dominated by its own vertex by more than three tolerances — which is what makes a board run able to tell a gradient from a flat fill. It owns no hardware and makes no MMIO access |

None of these desk gates prove GPU execution, displayed output, concurrency,
memory visibility, WSI, shader correctness or conformance. Only a board run can.
The recorded Pi 4 runs now prove execution of clears, graphics pipelines,
interpolated varyings, a second vertex input binding, a uniform-buffer
descriptor fetched by the TMU, host-visible memory and presentation. They do
not prove any unlisted shader instruction, descriptor type, format or WSI.

### Board runs

**2026-09-11, run 1 — no GPU result.** `vulkanClearProof.pi4` (container
`3a6cde76…`) returned in 1.16 s with status `#VCP_ERR_DISPLAY`, detail `-19`
(`#DSP_ESEND`). It never reached V3D. The cause was in the diagnostic, not in
the driver and not in the display library: it called `DisplayInit`, which
**asks the firmware for a display**, and on this bench the firmware has none —
the DSI panel is brought up and driven by the monitor, which installs its
framebuffer with `DisplayAdopt` instead. The nine-tag property transaction had
nothing to allocate against and failed. The console restored cleanly.

That run also exposed a structural fault worth more than the bug: the GPU proof
had been made to **depend** on taking the screen, so a display refusal reported
nothing at all about V3D. The diagnostic now runs the whole GPU proof in memory
the payload owns — no display, no firmware, no framebuffer — and presentation is
a separate step with its own verdict. A present that cannot happen can no longer
hide a GPU result that did.

**2026-09-11, run 2 — PASSED. V3D executes a Vulkan colour clear.** Container
`a06b43e5…`, `screen dma` first, returned in 12.25 s with the report at
`$0058EB00`, magic `564B4350`, **slot 1 = 0**.

What that verdict is computed from, and therefore what it asserts:

- **Every pixel.** 1,024,000 words of an 800x1280 `VK_FORMAT_B8G8R8A8_UNORM`
  image, each compared against `$FF3380B2`: slot 14 mismatches = **0**, slot 15
  first-bad-offset = **-1** (the never-set sentinel), slots 12 and 13 (the first
  and last words) both `$FF3380B2`, equal to slot 11, which the driver computed
  rather than the test. Every one of those words held `$00CC7F4D` before the
  submit. The clear value went in as four binary32 patterns
  (`0.2f, 0.5f, 0.7f, 1.0f`), through the integer UNORM conversion, into the
  packed word, into the tile store, and came back as the B, G, R, A byte order
  this format requires — **the whole colour path is correct on silicon**.
- **The GPU did it.** The verdict returns `#VCP_ERR_NO_JOBS` unless both the bin
  and the render completion counters advanced, and `#VCP_ERR_V3D_FAULT` on any
  binner OOM or V3D MMU fault. Status 0 means both jobs ran and neither faulted.
  There is no processor-side or DMA fallback anywhere under this path.
- **It wrote nowhere else.** The verdict returns `#VCP_ERR_GUARD_CHANGED` unless
  the screen-sized guard buffer below the image is byte-identical afterwards. It
  was. The backend's save and restore of the engine's previous render target
  works on hardware.
- **The fence and the layout.** Status 0 requires the wait to have succeeded and
  the image's layout to have advanced to `VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL`.
- **A production Pi build enumerated a real GPU device for the first time**:
  slot 42 (`AnvilVkBackendIsGpu`) = 1.
- **Not one validation fault in the whole run**: slot 44 = 0. Every public `vk*`
  call on the path succeeded; no refusal was taken.
- Presented: slot 47 = 1, slot 45 = `#DSP_OK`. `DisplayAdopt` on the scanout
  buffer, one `DisplayBlit`, and a person saw the colour.
- Measured: 115.2 ms to submit and complete the clear, 867.4 ms to read
  4,096,000 bytes back and compare them. The engine needed 10.52 MiB of its
  16 MiB arena (slot 46).

**What run 2 does NOT prove, and none of it may be inferred from the pass:**

- **No shader.** No SPIR-V, no `VkShaderModule`, no pipeline, no QPU program was
  compiled or run. A tile clear and a tile store are fixed-function; the frame
  was submitted with **no draws**. Internal clear lowering is not a shader
  compiler.
- **No draw.** Zero primitives were binned. Nothing about vertices, geometry,
  rasterisation or the QPU path is touched by this result.
- **One geometry only.** 800x1280 at pitch 3200 — the render geometry `NeonInit`
  was given. No other extent, format, tiling, mip level, array layer or sample
  count has ever reached the GPU.
- **The two refusal rules were exercised only in the accepting direction** by
  this run. Board run 3 below closed that.
- **No asynchrony.** `NeonFrameEnd` waits for both jobs, so the fence was already
  signalled when `vkQueueSubmit` returned. The pending command-buffer state has
  never been observed on hardware.
- **One run, one cache state.** No repeat, no soak, no caches-on/caches-off pair,
  and no fault injection: an unmapped address requiring a bounded fault rather
  than a hang is still owed. Resource reuse across submissions was not exercised
  either — only one submission happened.

**2026-09-11, run 3 — PASSED. The two refusal rules, in the direction that
matters.** `vulkanClearRefusals.pi4`, container `504bd049…`, `screen dma` first,
returned in 5.8 s with the report at `$00581868`, magic `564B4352`,
**slot 1 = 0**. It submits nothing: every refusal here happens at record time,
inside `vkCmdClearColorImage`, so `avkBackendSubmitClear` is never reached.

`avkBackendClearSupported` checks in a fixed order — engine ready, base and size
sane, inside the window, extent, pitch, size against the extent, and last the
scanned-buffer rule. A request that trips two proves only the earlier one, so
each request was built to trip exactly one, which needed a Vulkan window
spanning both screens:

| Rule | The request | Result |
|---|---|---|
| refuses the buffer the display is scanning out | an 800x1280 image at pitch 3200 — *exactly* the render geometry — placed at the surface base `$06000000`, so every earlier check passes and only this rule can answer | slot 2 = 1, slot 3 = **-8** (`VK_ERROR_FEATURE_NOT_PRESENT`) |
| refuses any extent but the render geometry | a 640x480 image at `$063E8000`, which is *not* the surface base, so the scanned-buffer rule cannot be what answers | slot 4 = 1, slot 5 = **-8** |
| the refusals discriminate | an 800x1280 image at `$063E8000` — right extent, not the scanned buffer | slot 9 = 1, slot 10 = `VK_SUCCESS`; recorded and thrown away unsubmitted |

Also settled by the same run, each of which needs a live engine:

- **The live row pitch.** `avkBackendRowPitchFor(800)` = 3200, the surface's own
  pitch; `(640)` = 2560, the tight pitch. Slot 6 = 1. This is what makes run 2's
  slot 17 mean something.
- **The live capability answer.** Slot 12 = **7** — `DEVICE | CLEAR_COLOR | GPU`.
  A desk run can only ever prove 0.
- **The backend's microsecond clock is real.** `V3dCounterHz()` = 54,000,000 and
  the counter advanced across the run. Slot 13 = 1. That clock is what bounds
  `vkWaitForFences`; a stalled one would leave only the poll cap between a dead
  device and a hang during a finite wait. An unsatisfied `UINT64_MAX` wait is
  explicitly withheld until host calls are reentrant; the poll cap is not
  presented as Vulkan's unlimited wait.
- **Allocator reuse on silicon.** Freeing the 640x480 allocation and placing a
  full-geometry image in the hole it left returned the same address,
  `$063E8000`. Slot 27 = 1. Run 2 never exercised reuse.
- **Nothing reached the GPU.** Slot 16 = 1: `V3dBinJobs`, `V3dRenderJobs`,
  `V3dTfuJobs` and `avkBackendJobs` all still 0, and both screen-sized buffers
  byte-identical to the pattern they were filled with (slot 31 delta = 0).
- Exactly two validation faults recorded (slot 34), which is the two refusals
  and nothing else. The engine needed the same 10.52 MiB arena.

**With run 3, both rules `tools/vulkan_v3d_backend_check.py` lists as
desk-unreachable are proven on silicon in both directions**, and that gate now
prints them as `BOARD` with their containers rather than as `OWED`. A rule added
to that list in future without a board proof prints `OWED` and fails the gate.

**Still owed after run 3, and unchanged by it:** no shader, no draw, no other
format or tiling or mip or layer or sample count, no asynchrony, no concurrency,
no caches-on/caches-off pair, no fault injection, and no repeat or soak.

**2026-09-11, run 4 — TAKEN, AND NOT MEASURED.** The payload ran, returned in
12.4 s with `x0` inside its own BSS, faulted nothing and left the console clean.
Its report was then read at the wrong offsets: the block was sixty-four 64-BIT
slots and the monitor's dump has no 64-bit width and counts bytes, so slot N
appears at word 2N. Twelve dumped words decode exactly as slots 9 to 14 - an
image size of 4,096,000, a pitch of 3200, a vertex array at `$067D0000` and two
pipeline bases 8 KiB apart - and were read as slots 17 to 28, which is where the
pixel readbacks live. Under the same doubling the two verdicts sit at words 2
and 8; the values read as "slot 1" and "slot 4" were the zero halves of the
magic and of a detail slot, and "slot 47" was the zero half of slot 23.

**Neither verdict, and no pixel readback, was read. Run 4 established nothing
about whether the triangles rendered** - not a pass and not a failure. The
diagnostic's own header was the cause: it said to read the block with a bare
`memory <that> 64`, which is sixty-four BYTES.

The report is 32-bit words now, one slot to one word, with the step it reached
in slot 61 and a tail magic in slot 63 so a short dump says so (Anvil
`338ea23`). The two clear proofs carry the same wrong instruction, corrected in
place; their numbering is unchanged because runs 2 and 3 are recorded against
it.

**2026-09-11, run 5 — PASSED. V3D executes a Vulkan graphics pipeline.**
`vulkanTriangleProof.pi4` at Anvil `338ea23`/`5b55574`, container `2c7b6b71…`,
463,548 bytes, compiler `890f1ba4…`, on the build-55 monitor with `screen dma`
and `deadman 15`. Returned in 12.4 s with `x0 = $58FB70`, read as 32-bit words:
magic `564B5452`, tail `52544B56`, **highest step 10**, uniform verdict 0,
per-vertex verdict 0, pass-one pixels `FFFF0000` inside x3 and `FF3380B2`
outside x3, pass-two `FF00FF00` inside x3 and `FF3380B2` outside x3, submit and
wait 0 for both, draws 2, binner overflow 0, MMU faults 0, **present 1**.

That settles the three things the desk could not:

- **`FTOIN`** — the viewport transform's rounding executes, and the triangle
  landed where the arithmetic said it would.
- **The VPM output segment size** — the emitter's extra sector for varyings is
  on the right side of the line; no vertex was corrupted.
- **The varying path** — `LDVARY` + delay + `FADD` against `r5` with the
  non-perspective flag packet carried a four-component colour to the fragment
  shader.

**What run 5 did NOT settle, and why the next run exists:** its second pass
gives all three vertices the SAME colour on purpose, so its expected pixel is
exact whatever the interpolator's precision is. It proves the varying PATH and
says nothing about interpolation. A shader that read the varying and ignored the
weights would have passed it.

**2026-09-12, run 6 — FAILED at the descriptor/TMU render.**
`RaspberryPi4/Examples/Diagnostics/vulkanVaryingProof.pi4` was finally run on
a clean-reset V3D under monitor build 101. The exact untouched-`d8e5f52`
container was 553,576 bytes, SHA-256
`773b6678d90693bed4d2917fc3a407bb37c23b0b9f8445dcbf9ae9cd23a5f46a`;
only its display hold was reduced from six seconds to one so the complete run
fit under the monitor's 15-second hardware-deadman ceiling. It returned in
13.74 seconds with the complete magic/tail report and highest step 12, but
slots 1, 2 and 3 were all 21 (`VVP_ERR_SUBMIT`), submit slots 89, 91 and 93
were `VK_ERROR_DEVICE_LOST`, and native slot 95 was 13
(`NEON_ERR_RENDER`). At that point no gradient or descriptor-backed colour was
accepted on silicon, and the descriptor/TMU path became a known RED silicon
gate. Run 8 below closes it. A renderer timeout can leave later V3D payloads
dirty until a monitor reset; every isolation run after this failure therefore
began with a fresh reset.

> **The build line**, with the toolchain lane's own mechanism (this is the
> direct form):
> ```
> PureMetalForge.exe --compile >     RaspberryPi4/Examples/Diagnostics/vulkanVaryingProof.pi4 -t pi4 >     --load-addr 0x500000 --stack-addr 0x4F00000 --entry-returns >     -o vulkanVaryingProof.img
> ```
> Built at the desk on 2026-09-11 with a snapshot of `PureMetalForge.exe`
> `890f1ba477f1d68f46a61a668a3daa9eec194b593782d9447cf64aeb193146a3`:
> container **545,176 bytes, sha256
> `529949ed932ab85e122e79e2708123f2379fa1d5b2d42195ec56f3c50b424478`**, image
> 545,080 bytes occupying `$500000..$585137`, BSS `$590000..$5B411F`. Rebuild
> before staging and compare — a container built with a different compiler is
> not this one. This is a PAYLOAD and not a monitor build, so it does not move
> the board's build number.
>
> **Before the run**: `screen dma`. The payload initialises the graphics engine
> itself and uses the same 16 MiB arena at `$0A000000` the V3D console owns.
>
> **Run**: load at `$500000`, `deadman 15` — three passes plus a one-second
> display of the result. Fifteen seconds is the monitor's hardware ceiling.
>
> **READ IT WITH `md.l <x0> 200`** — one hundred and twenty-eight 32-bit words,
> one per slot, the count in hex because every argument of that command is. A
> bare `md` counts BYTES and groups by one; that is what went wrong on run 4.
>
> **Expected**: slot 0 = `$59524156` and slot 127 = `$56415259`; slot 125 = 12;
> slots 1, 2 and 3 all 0. Pass A's slots 37, 38, 39 = `$FFFF00FF` and 40, 41,
> 42 = `$FF3380B2`. Pass B's slots 43 to 49 each within TWO 8-bit steps per
> channel of the expectation in slots 30 to 36 — slot 53 (worst distance) at
> most 2 and slot 54 (probes over tolerance) 0 — and slots 50, 51, 52 =
> `$FF3380B2`. Pass C the same, in slots 55 to 61 against the same expectations,
> with slot 67 at most 2, slot 68 = 0, slots 62, 63, 64 = `$FF3380B2`, and
> **slot 69 = 0**: every probe the same word pass B produced. Slots 70, 72, 74
> and 76 all NON-ZERO — the four refusals were exercised live and every one
> refused. Slot 79 > 78 and 81 > 80, slots 82 and 85 = 0, slot 88 = slot 87,
> slot 98 = 1. Slots 115, 116, 117, 118, 119 = 8, 16, 0, 1, 2. The
> descriptor-lowering evidence is slots 120..124 = 144, the uniform-buffer
> address from slot 15, `$FFFFFF7C`, `$FFFFFFFF`, 1.
>
> **On the glass**: a triangle, apex up, on a blue-grey ground, RED at the apex
> (400, 320), GREEN at the lower left (200, 960) and BLUE at the lower right
> (600, 960), blending smoothly through grey at the centroid. A SOLID MAGENTA
> triangle means pass B and pass C did not happen and slot 125 says which step
> stopped it; a solid triangle of any one colour where a gradient was expected
> is the defect this run exists to find.
>
> **If a verdict is not 0**: slot 125 says which step, slot 4 carries a detail,
> slot 97 a whole sentence and slot 109 the command buffer's own. The codes are
> in the diagnostic's header; the ones that matter most are 19 (a pipeline was
> refused — slots 111 and 112 name the emission step and the encoder's code),
> 23 and 24 (the pixels), 28 (the descriptor path), 29 (the expectation module
> refused its own probes), 30 (the split changed the picture), 31 (a refusal
> did not refuse) and 32 (the submitted descriptor stream is not the TMU
> general-load stream the desk gate decoded).
>
> **Recovery**: the console repaints over the presented picture by itself;
> `screen on` forces it and `screen v3d` brings the accelerated console back.
> Neither needs a reset. `NeonShutdown()` hands the V3D MMU back before the
> payload returns. Nothing writes a core spin slot, releases a core, or touches
> the monitor, its variables, the DSI control registers, the GENET ring or the
> driver-module region. It renders the same triangle into the same 800x1280 image
three times and asks three different questions:

- **a uniform buffer feeds the fragment colour**, through
  `vkCreateDescriptorSetLayout`, `vkCreatePipelineLayout` with it,
  `vkCreateDescriptorPool`, `vkAllocateDescriptorSets`,
  `vkUpdateDescriptorSets` with a `VkDescriptorBufferInfo` and
  `vkCmdBindDescriptorSets`, with the fragment module reading member 0 of a
  `Block`-decorated `OpTypeStruct` in the Uniform storage class;
- **a real gradient** - red at the apex, green at the lower left, blue at the
  lower right - with seven probe pixels whose expected colours are computed on
  the board by `vk_interp_expect.pbi` from the barycentric weights at each
  probe's own pixel centre, compared within two 8-bit steps per channel;
- **the same gradient out of two vertex buffers**, position at a stride of
  eight and colour at a stride of sixteen, with the verdict including that every
  probe is the same word as the one-buffer pass produced.

That run failed before producing any of the three pictures. At that point the
gradient, split binding layout and descriptor path remained proved at a desk
and nothing more. Run 8 below closes those three gates. The tolerance, probe
placement and the reason each probe is strictly inside the triangle are in the
diagnostic's own header and in `vk_interp_expect.pbi`.

**2026-09-12, run 7 — PASSED. Format query, host mapping, cache visibility,
fences and drawing on silicon.** The ordinary triangle diagnostic was extended
at the source-owned API boundary to require the exact
`vkGetPhysicalDeviceFormatProperties` answer for linear
`B8G8R8A8_UNORM`, and to populate both the colour image and vertex allocation
through `vkMapMemory`/`vkUnmapMemory`. There is deliberately no flush call:
the vertex fetcher's correct pixels give the Pi 4 backend's advertised
`HOST_COHERENT` promise a board-visible consequence. The exact container was
514,072 bytes, SHA-256
`54f033c86e20b3a66b3d695571aae3edc772d915e432b1239d677d40a401f22a`,
run under monitor build 101 after a clean reset. The complete report returned
in 11.92 seconds: both verdicts zero; both submit and wait pairs zero; bin and
render jobs each advanced twice; no OOM, MMU fault, or guard change; exact red
then green interior pixels and exact clear exterior pixels; present verdict 1;
highest step 10 and both magics present. This accepts those APIs and their
vertex/render cache path at the one proven 800x1280 geometry. It does not make
the failed descriptor/TMU run green.

The generic `tools/board_run.py` wrapper currently treats any nonzero `x0` as
a payload failure. These Vulkan diagnostics intentionally return a report
address in `x0`, so its loud wrapper verdict is not their verdict; the complete
magic/tail report is. Its capture-sequence comparison also mistakes the first
capture after a monitor reset for stale when the persisted old sequence was
higher. Both tool issues are recorded here so neither can be read as a Vulkan
failure.

**2026-09-13, run 8 — PASSED. Uniform-buffer descriptor, interpolation and
split vertex bindings on silicon.** This was the first candidate after a safe
monitor reset, so it did not inherit the V3D state left by run 6's timeout. The
567,436-byte returning container had SHA-256
`44bdfed7d9f7bbc96e474e9954dce146938df3b0f5827c2306cb605f7be61ee4` and ran
under monitor build 101 with a 15-second hardware deadman. It returned normally
with report address `$00595FA0`.

All three verdicts were zero. Pass A's three interior probes were exact
magenta and all outside probes kept the clear colour. Pass B's seven gradient
probes exactly matched the independent expectation; pass C matched those same
seven words exactly while reading position and colour from separate bindings.
Both worst-distance values, both over-tolerance counts and the B/C difference
count were zero. Bin and render job counters each advanced from 0 to 3;
all six submit/wait results and the backend native error were zero; OOM and MMU
fault counts were zero; the guard sum remained `$C0E6C000`; presentation and
display verdicts were one; layout ended at `TRANSFER_SRC_OPTIMAL`; three draws
ran; cleanup was reached; step 12 and both report magics were present.

The submitted shader record was `$067D5000`. Its 144-byte fragment program
read a three-word stream at `$067D3000`: descriptor address `$067D3000`, TMU
configuration `$FFFFFF7C`, then TLB configuration `$FFFFFFFF`. The diagnostic's
independent lowering verdict was one. The validation-fault count was five by
design: it counts the deliberate hostile calls that the diagnostic requires the
API to refuse, not V3D or MMU faults. The nonzero `x0` and stale-capture warning
from the generic wrapper are likewise not failures; this diagnostic returns its
report address, and the payload itself came back to the monitor prompt.

The evidence is under `_work/vulkan-tmu-20260913/clean-v3d/`. If any V3D render
candidate times out, reset the monitor/board before judging a later candidate:
shutdown cannot prove it repaired an engine that did not complete, and a later
red result from inherited state is not independent evidence.


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
   **Parsing, validation and the refusals are done (2026-09-11); the typed IR is
   NOT.** What exists is a walker that produces a small plan for one declared
   subset and refuses everything else by name. That is enough for a
   pass-through shader and nothing like enough for a general one, and the
   distinction is kept in the source: the file says it is an emitter and not a
   compiler.
5. Add pipeline layouts, descriptors, render passes, fixed-function state and
   V3D QPU lowering. Differential shader tests and independent packet/QPU
   decoders precede broader instruction coverage.
   **Pipeline layouts, one render pass, the fixed-function state listed above
   and the QPU lowering are done (2026-09-11), and so is ONE descriptor type -
   a uniform buffer, through a set layout, a pool, an allocation, an update and
   a bind, with every other type refused by its own name. The independent
   decoder is still partial** - the checker packs the shader record and the
   attribute records independently and compares bytes, and as of 2026-09-12 it
   decodes the signal/destination sequence and lookup fields of the eighteen
   raw instructions in the descriptor fragment program. Other emitted programs
   are still checked by length, no-op structure
   and whole-byte equality rather than a complete disassembler. The descriptor
   now uses a GPU-side V3D 4.2 TMU general vec4 load; its desk proof and
   clean-state silicon execution are complete in run 8.
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

## Dynamic render geometry — Pi 4 acceptance, 2026-09-13

The V3D layer now has one pure geometry planner used by the live packet path.
Neon carves tile pools and coordinate tables for a declared pre-init capacity,
validates the already mapped target span, and rebinds the complete geometry as
one transaction.  Vulkan saves and restores the full display surface around a
clear or draw; its linear BGRA8 row pitch is now derived from the image width,
not copied from the display.

The returning RAM diagnostic
`RaspberryPi4/Examples/Diagnostics/vulkanDynamicGeometryProof.pi4` passed on
build 101 with PMFBOOT SHA-256
`275fdb26db7fe3065b4e7f61f4eb303441dec4d1d71e96f414c44c00a6b74767`.
At 800x1280, 640x360 and 257x193, each public Vulkan clear mapped, submitted,
completed its fence, advanced one bin and render job, and produced exact
`$FF3380B2` pixels with no mismatch or new V3D fault/OOM.  1281x64 was refused
before either job counter moved.  A subsequent ordinary 800x1280 engine frame
advanced both counters and produced exact `$FF2060A0`, proving the restored
geometry remained operational.  The payload returned zero and shut down the
V3D MMU.

The detailed report and capture are recorded in
`docs/VULKAN_DYNAMIC_RENDER_GEOMETRY_DESIGN.md`.  This proves the prerequisite
for an honest image-format-properties query; it does not itself add or claim
that entry point.
