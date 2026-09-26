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

On 2026-09-26, the resident Neon adapter gained an explicit `Neon_TextTex`
callback. It preflights the visible glyph run, retains the public bitmap font
metrics and clipping rules, and emits one atlas-sampled Vulkan draw. Selecting
a font now advances the CPU atlas revision even when its bitmap address is
reused. A quiescent Vulkan frame refreshes the bitmap columns before recording
and publishes the new revision only after the upload completes; an uncertain
upload poisons the adapter until recreation. This is a fail-closed in-place
refresh, not the separate-image transactional replacement described in
`docs/NEON_VULKAN_RESOURCE_LIFETIME_DESIGN.md`.

The native 15-scene oracle passed on Pi 4 build 210 with its full 245,760-byte
capture saved in `docs/evidence/neon-texttex-20260926/`. A separate real Vulkan
widget frame using `Neon_TextTex` passed 129 report and rotated-pixel checks.
These are distinct proofs: the 15-scene Vulkan producer and native/Vulkan
pixel comparison are still outstanding. Its capacity scene would request
4,687 Vulkan draws through one-call/one-draw lowering, above the shared
4,096-record ceiling. An opt-in same-tint/same-scissor box batch now lowers
its 3,505 consecutive boxes to one ordered draw; the 19-assertion emitted
gate proves that exact count, capacity refusal, and colour mismatch on the
desk. The paired producer must use `NeonVkChromeCreateWithCapacities` to
reserve at least 6,373 vertex quads as well as the separate draw budget.
The box batch now also passes a real Pi 4 Vulkan frame: 3,505 boxes lower to
one draw and 21,030 vertices, followed by the established widget frame with
47 draws and 654 vertices. The final widget capture passed 212 independent
report and rotated-pixel checks under a 15-second deadman; see
`docs/evidence/vulkan-box-batch-20260926/`. The first larger-buffer attempt
correctly refused allocation within the diagnostic's 8 MiB Vulkan window;
the passing run used 12 MiB within its mapped RAM span. The full paired
15-scene Vulkan producer and pixel comparison remain outstanding.

The next Pi 4 RAM diagnostic rendered native oracle scene 1 (three ordered
boxes, including source-over alpha and a clipped negative-origin box) through
the resident Vulkan adapter before the unchanged widget frame. A CRC-checked
readback of the completed GPU attachment matched all 16,384 BGRA bytes of the
saved native scene exactly. The returning build-210 run used a 15-second
deadman, returned its expected report pointer, and produced fresh capture 8;
the widget frame passed 133 report and rotated-pixel checks. Evidence is in
`docs/evidence/vulkan-paired-boxes-20260926/`. This first pair uses the
top-left 64x64 region of an 800x1280 attachment. It does not yet exercise
Vulkan rebind, odd extents, rotated targets, glyph parity, or the remaining
14 native scenes.

Native oracle scene 2 now also has a Pi 4 Vulkan pixel pair. Its first run
identified 100 missing ink pixels in the bold flat face: every missing pixel
sat immediately right of existing ink. The adapter now stages Neon's
one-pixel emboldened bitmap in reserved atlas columns 16..31 and selects it
for the bold flat-text face. The final GPU readback matches all 16,384 bytes
of the native 256x16 scene, which includes four flat-font calls and three
textured-font calls covering printable ASCII. The same run returned cleanly
under a 15-second deadman, produced fresh capture 10, and passed 133 widget
report/pixel checks. See `docs/evidence/vulkan-paired-glyphs-20260926/`.
The current selection follows the default bold face index; altered bold
settings through `NeonFontSetup` still need a renderer-neutral state query.
The paired text proof uses a 256x16 scissor on the existing 800x1280 target,
so target rebind and the remaining 13 native scenes still need proof.

Native oracle scene 3 now passes the same full-pixel Pi 4 comparison: two
nested scissors and a final zero-size clip leave exactly the native 16,384
BGRA bytes. The RAM payload returned under the 15-second deadman with fresh
capture 11, and the established widget frame still passed 133 checks. Its
report, raw clip pixels and capture are in
`docs/evidence/vulkan-paired-clips-20260926/`. Three native scenes are now
paired; the Vulkan producer still uses one oversized attachment rather than
the oracle's changing target extents.

Updated 2026-09-11, when the SPIR-V front end and the first graphics
pipeline landed, and again the same day when three things followed it: a real
interpolated gradient, a second vertex input binding, and the first descriptor
type. Updated 2026-09-12 when that descriptor stopped being copied by the CPU
and gained a V3D 4.2 TMU general-load lowering. Updated 2026-09-13 when dynamic
render geometry and the matching public image-format-properties query passed
their desk and Pi 4 silicon gates, and again when the bounded optimal-image
copy and greater-than-one-texel sampled path passed desk and silicon gates.
Updated 2026-09-16 when command buffers gained bounded ordered draw lists and
the Pi 4 backend began lowering a whole list through one V3D frame transaction,
then when public per-draw dynamic scissor, one-barrier cache batching, and the
atlas/chrome acceptance scene closed the remaining prerequisites for starting
the Neon-to-Vulkan adapter. Updated 2026-09-17 when bounded UINT16/UINT32
indexed triangle-list recording, submission validation and V3D 4.2 packet
lowering passed their emitted desk gates. The bounded UINT16 indexed board
diagnostic passed on Pi 4 silicon on 2026-09-26; see
`docs/VULKAN_INDEXED_DRAW_2026-09-17.md`. UINT32 remains desk-proved only.

### The implemented public entry points

These are callable `vk*` names with the registry's own parameter lists and
return types. Everything else in core 1.0 does not exist and a caller linking
one gets a compile-time refusal naming it.

| Entry point | Status |
|---|---|
| `vkCreateInstance` / `vkDestroyInstance` | Implemented. Layers and extensions are refused with `VK_ERROR_LAYER_NOT_PRESENT` / `VK_ERROR_EXTENSION_NOT_PRESENT`. |
| `vkEnumeratePhysicalDevices` | Implemented, including the two-call `pPhysicalDeviceCount` form and `VK_INCOMPLETE`. |
| `vkGetPhysicalDeviceMemoryProperties` | Implemented. One heap, backend-reported. |
| `vkGetPhysicalDeviceFormatProperties` | Implemented. Linear `B8G8R8A8_UNORM` reports `SAMPLED_IMAGE`; a draw-capable backend additionally reports `COLOR_ATTACHMENT`, and a backend with the independent exact source-over capability additionally reports `COLOR_ATTACHMENT_BLEND`. A backend with the optimal-image planner reports optimal `SAMPLED_IMAGE`; buffers and unsupported formats report zero. Storage, depth/stencil and blit support are not advertised. |
| `vkGetPhysicalDeviceImageFormatProperties` | Implemented for the exact combinations `vkCreateImage` accepts: bounded 2D `B8G8R8A8_UNORM`, flags zero, one mip/layer/sample, with linear usage within transfer/sample/attachment rules and optimal usage limited to transfer destination plus sampled. It reports backend-derived maxima and resource size; every other combination returns `VK_ERROR_FORMAT_NOT_SUPPORTED`. |
| `vkGetPhysicalDeviceQueueFamilyProperties` | Implemented. One family always advertises `VK_QUEUE_TRANSFER_BIT`; it also advertises `VK_QUEUE_GRAPHICS_BIT` exactly when the linked backend has the draw capability. A transfer-only backend remains transfer-only. Compute is not advertised. |
| `vkGetPhysicalDeviceFeatures` | Implemented. The complete 55-member core-1.0 structure is written and every member currently reports `VK_FALSE`. |
| `vkCreateDevice` / `vkDestroyDevice` / `vkGetDeviceQueue` | Implemented for one queue of family 0. Device extensions and any true feature bit are refused; a null or non-null all-false `pEnabledFeatures` is accepted. Teardown retires quiescent generation-matched semaphores while the device is still live and refuses atomically if a reservation or submission remains pending. |
| `vkCreateImage` / `vkDestroyImage` | Implemented for bounded 2D `VK_FORMAT_B8G8R8A8_UNORM`, one mip, one layer, one sample and exclusive sharing. Linear usage is bounded to the implemented transfer/sample/attachment rules. Optimal usage is exactly the backend-planned transfer-destination/sampled subset. Unsupported combinations are refused with a real code. A framebuffer attachment must carry `COLOR_ATTACHMENT`; a transfer bit does not substitute for it. |
| `vkGetImageMemoryRequirements` | Implemented. Size, alignment and `memoryTypeBits` come from the backend. |
| `vkAllocateMemory` / `vkFreeMemory` | Implemented over one backend heap, first-fit with real reuse of freed holes and a real `VK_ERROR_OUT_OF_DEVICE_MEMORY`. |
| `vkMapMemory` / `vkUnmapMemory` | Implemented for one active mapping of a `HOST_VISIBLE` allocation, flags zero, an overflow-safe positive subrange or `VK_WHOLE_SIZE`. The returned pointer includes the requested offset; wrong owner, duplicate map, invalid range, non-visible type, unbalanced unmap and free-while-mapped are refused. Pi 4 reports this heap `HOST_COHERENT` because mandatory submission/completion cache maintenance supplies the observable promise. |
| `vkBindImageMemory` | Implemented, with alignment, range, double-bind, wrong-parent and memory-type rules enforced. |
| `vkCreateCommandPool` / `vkDestroyCommandPool` / `vkResetCommandPool` | Implemented. |
| `vkAllocateCommandBuffers` / `vkFreeCommandBuffers` | Implemented for one buffer per call; array allocation is refused, not faked. |
| `vkBeginCommandBuffer` / `vkEndCommandBuffer` / `vkResetCommandBuffer` | Implemented. A recording error moves the buffer to invalid and `vkEndCommandBuffer` reports it, as the specification requires. |
| `vkCmdPipelineBarrier` | Implemented with its exact ten-parameter registry signature. One image memory barrier per call; global and buffer barriers are refused. The final count and pointer travel through the AArch64 stack argument area and are exercised through emitted code. |
| `vkCmdClearColorImage` | Implemented with its exact registry signature, for one whole-image range. |
| `vkCmdCopyBufferToImage` | Implemented for one tightly packed whole 2D BGRA8 region from a transfer-source buffer at an offset aligned to the active backend's reported copy requirement into a bound optimal transfer-destination image. Recording retains generation-tagged handles and immutable region state; submission revalidates live owners, bindings, usage, ranges and layouts, retains both resources and memories, and publishes the final layout only after backend success. The Pi 4 reports 64-byte source alignment and lowers the request to the TFU; partial regions, row-length/image-height overrides, mips, layers and format conversion are refused. |
| `vkCreateFence` / `vkDestroyFence` / `vkResetFences` / `vkGetFenceStatus` / `vkWaitForFences` | Implemented for finite waits. `UINT64_MAX` succeeds immediately when the requested fence condition is already true; an unsatisfied unlimited wait returns `ANVIL_VK_ERR_UNSUPPORTED` until host calls are reentrant. It is never disguised as a bounded `VK_TIMEOUT`. |
| `vkCreateSemaphore` / `vkDestroySemaphore` | Implemented for core-1.0 binary semaphores. Handles retain device slot and generation; destruction refuses reserved or pending payloads. Timeline and host signal/wait operations are not claimed. |
| `vkQueueSubmit` | Implemented for one `VkSubmitInfo`, at most one command buffer, and at most sixteen binary wait/signal operations in total. All waits are ordered before all signals; unsatisfied waits, duplicate roles, stale/cross-device handles and stage bits the active backend does not execute are refused before submission. State is committed only after resource/fence preflight, published at real immediate or polled completion, and rolled back atomically on a backend fault. Multiple `VkSubmitInfo` records and multiple command buffers remain refused. |
| `vkDeviceWaitIdle` | Implemented. |

### The graphics pipeline entry points, added 2026-09-11

| Entry point | Status |
|---|---|
| `vkCreateShaderModule` / `vkDestroyShaderModule` | Implemented. Creation walks and verifies the accepted SPIR-V subset, then retains an immutable exact-word image and typed IR owned by the shader-module generation. Pipeline creation consumes that verified IR synchronously and copies its executable metadata, so a compiled pipeline survives later module destruction and slot reuse. Modules outside the accepted subset are refused with a whole sentence before publication. |
| `vkCreateBuffer` / `vkDestroyBuffer` / `vkGetBufferMemoryRequirements` / `vkBindBufferMemory` | Implemented for `VK_BUFFER_USAGE_VERTEX_BUFFER_BIT`, `VK_BUFFER_USAGE_INDEX_BUFFER_BIT`, `VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT` and the two transfer bits, exclusive sharing, page-granular alignment. |
| `vkCreateImageView` / `vkDestroyImageView` | Implemented for `VK_IMAGE_VIEW_TYPE_2D`, `VK_FORMAT_B8G8R8A8_UNORM`, identity swizzle, the whole colour subresource. |
| `vkCreateSampler` / `vkDestroySampler` | Implemented as a typed, device-owned object for normalized 2D sampling with nearest or linear min/mag filters, nearest mip mode at LOD zero, clamp-to-edge on all coordinates, and no anisotropy or comparison. It is retained by the bounded combined-image-sampler descriptor and consumed by both the measured linear one-texel path and the bounded optimal-image path. |
| `vkCreateRenderPass` / `vkDestroyRenderPass` | Implemented for one colour attachment, one subpass, no dependencies, `loadOp` CLEAR and `storeOp` STORE. |
| `vkCreateFramebuffer` / `vkDestroyFramebuffer` | Implemented for one attachment at the image's own extent, one layer. |
| `vkCreatePipelineLayout` / `vkDestroyPipelineLayout` | Implemented for zero or one descriptor set layout and at most one push constant range: fragment stage, offset 0, 16 bytes. Creation consumes and copies the set layout's immutable dense binding schema; later source-layout destruction or slot reuse cannot substitute another schema. Nonzero create flags and cross-device set layouts are refused before publication. |
| `vkCreateDescriptorSetLayout` / `vkDestroyDescriptorSetLayout` | Implemented for one or two dense bindings numbered 0..n-1, each either `VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER` or `VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER`; every binding has `descriptorCount` 1 at `VK_SHADER_STAGE_FRAGMENT_BIT`. A mixed UBO-plus-sampler layout is supported in either binding order. Every other descriptor type, sparse numbering and duplicate binding are refused before publication. Sets consume and copy the schema at allocation, so the source layout may subsequently be destroyed or reused without changing them. |
| `vkCreateDescriptorPool` / `vkDestroyDescriptorPool` / `vkResetDescriptorPool` | Implemented for arbitrary input rows containing the two supported descriptor types. Duplicate rows of the same type are summed with checked overflow into independent per-type capacities. `VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT` is refused, and so are reset and destroy while a submission is in flight. |
| `vkAllocateDescriptorSets` | Implemented for one set per call, against the pool's `maxSets` and independent per-type capacities. Mixed allocation is transactional: either every binding's type has capacity and the complete immutable schema is published, or no counter or output changes. `VK_ERROR_OUT_OF_POOL_MEMORY` reports an absent or exhausted type. |
| `vkFreeDescriptorSets` | Present and refuses, naming the pool bit it would need. It is not missing from the link; it says why it cannot work. |
| `vkUpdateDescriptorSets` | Implemented for one write per call and no copies. The two bindings of a mixed set update independently. Uniform-buffer writes require `dstArrayElement` 0, `descriptorCount` 1 and a live, same-device bound uniform buffer at a sixteen-byte-aligned offset and range of at least sixteen (`VK_WHOLE_SIZE` accepted); subtraction-based bounds validation prevents `offset + range` wrap. The bounded combined-image-sampler write requires a live same-device sampler and full image view, a bound BGRA8 image created with `SAMPLED`, and `SHADER_READ_ONLY_OPTIMAL`; resolution rechecks live handles and the image's current layout. Refused while a submission is in flight. |
| `vkCmdBindDescriptorSets` | Implemented for one set at index 0, no dynamic offsets and `VK_PIPELINE_BIND_POINT_GRAPHICS`. Device ownership and the copied binding-count/type/stage schema must match the command buffer's pipeline layout; compatible schemas from distinct source layout handles are accepted. |
| `vkCreateGraphicsPipelines` / `vkDestroyPipeline` | Implemented for exactly one `VkGraphicsPipelineCreateInfo` per call and no pipeline cache. See the state table below for what it accepts. |
| `vkCmdBeginRenderPass` / `vkCmdEndRenderPass` | Implemented for `VK_SUBPASS_CONTENTS_INLINE`, one clear value, a render area that is the whole framebuffer. |
| `vkCmdBindPipeline` | Implemented for `VK_PIPELINE_BIND_POINT_GRAPHICS`. |
| `vkCmdBindVertexBuffers` | Implemented for a range of bindings inside 0..3, bound one at a time, so one call binding two buffers and two calls binding one each leave the same state. |
| `vkCmdBindIndexBuffer` | Implemented for one live, same-device, bound buffer carrying `VK_BUFFER_USAGE_INDEX_BUFFER_BIT`, at an element-aligned offset, with `VK_INDEX_TYPE_UINT16` or `VK_INDEX_TYPE_UINT32`. The generation-tagged binding is re-resolved at submit. |
| `vkCmdPushConstants` | Implemented for the whole sixteen-byte fragment-stage block at offset 0. |
| `vkCmdSetScissor` | Implemented for `firstScissor` zero and one `VkRect2D`. A pipeline may declare exactly `VK_DYNAMIC_STATE_SCISSOR`; reset clears the supplied state, a nonempty draw requires it, and each draw snapshots its rectangle so later changes cannot alter earlier records. Signed offsets and unsigned extents are normalized without overflow by the backend; empty and wholly out-of-bounds rectangles become a zero-size clip. |
| `vkCmdDraw` | Implemented for one instance and a vertex range inside every bound buffer. A zero vertex count is a no-op and consumes no backend draw slot. A command buffer snapshots up to 4,096 ordered draws, including the active pipeline, bindings, push data and generation-safe resource ledger. `TRIANGLE_LIST` accepts any positive vertex count; its primitive assembler discards an incomplete final triangle. |
| `vkCmdDrawIndexed` | Implemented for one instance, `firstInstance = 0`, `vertexOffset = 0`, a bound UINT16/UINT32 index buffer and the existing triangle-list pipeline slice. Recording and submit both use subtraction-based range checks; submit scans the selected coherent indices, bounds every vertex fetch through their maximum, includes the exact index range in cache maintenance, and retains the index buffer and memory through completion. `firstIndex` is encoded exactly once as a byte offset in the V3D indexed-primitive packet. |

The fixed-function state a pipeline may declare: one to four vertex input
bindings numbered 0..n-1, each at `VK_VERTEX_INPUT_RATE_VERTEX` with a stride
that is a positive multiple of four, and each read by at least one attribute -
a binding nothing reads is refused rather than ignored; attributes at locations
0..n-1 (n <= 4) in `R32G32_SFLOAT`, `R32G32B32_SFLOAT` or
`R32G32B32A32_SFLOAT`, each naming one of those bindings and fitting inside
THAT binding's stride; `VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST` with no primitive restart; one
viewport and one scissor. The viewport is static, begins at the origin and has
whole-pixel extents. The scissor is either a static full-viewport rectangle or
the sole accepted dynamic state, `VK_DYNAMIC_STATE_SCISSOR`; fill mode, no
culling, no depth bias, no depth clamp, no rasteriser discard; one sample;
`pSampleMask` either null (sample zero enabled) or naming one word whose bit
zero controls that sample; every channel written, with blending either disabled
or exact straight source-over (`SRC_ALPHA`, `ONE_MINUS_SRC_ALPHA`, `ADD`) for
both colour and alpha; no depth-stencil state and no other dynamic state.
Everything else is refused with a code and a sentence.


`vkCmdPipelineBarrier`'s ten-parameter problem is closed. Compiler revision
`a9f412a6` added aligned AArch64 stack arguments, so Anvil now exposes the
registry prototype directly and no longer carries an argument-record adapter.
The resource gate executes the real call: argument nine is the image-barrier
count and argument ten is its pointer, making both the caller and callee sides
observable.

### The layers

| Area | Implemented and checked | Not implemented or not claimed |
|---|---|---|
| Registry and ABI | A PureBasic generator verifies the pinned registry hash and emits a selected core-1.0 slice. The checked-in vocabulary covers 71 naturally aligned AArch64 structures with registry member names, order and widths. The complete 55-member `VkPhysicalDeviceFeatures` record, `VkFormatProperties`, `VkImageFormatProperties`, `VkSamplerCreateInfo`, `VkSemaphoreCreateInfo` and `VkPipelineDynamicStateCreateInfo` are among them. The foundation gate compares its registry-owned structures and executes exact size and `OffsetOf` fixtures; the independent complete ABI inventory covers all 71 structures and reports 114 of 281 core declaration categories present: 31 enums, 12 bitmasks and 71 structures. Another 165 categories remain missing and the two core unions remain deliberately unrepresentable. | The complete core-1.0 enum, bitmask, alias, handle, union, callback, command prototype, platform guard, optionality and valid-usage vocabulary is not generated. `VkClearColorValue` is a union and is deliberately not declared — PureMetal has no union, so the adapter reads the caller's sixteen bytes as the `float32` arm and says so. No other target ABI is declared equivalent merely because AArch64 layout passes. |
| Public API | The entry points in the table above validate `sType`, `pNext`, flags, counts, pointers, parents and host-synchronization rules before entering the object engine. Invalid usage that core Vulkan leaves undefined returns an Anvil code far outside `VkResult`'s range, with a whole sentence naming the code and the next thing to check; void commands record that sentence and, where the specification allows, invalidate the command buffer. Byte-exact, case-sensitive `vkGetInstanceProcAddr` and `vkGetDeviceProcAddr` lookup exposes 80 audited core command names in their registry dispatch domains. The independent inventory finds 81 declared-callable core commands and 56 missing across all 137 core-1.0 commands; `vkFreeDescriptorSets` is the one intentionally withheld from lookup because every descriptor pool refuses the enabling flag. | There is no platform loader integration, layer interface, extension negotiation or `VkAllocationCallbacks` support. Host allocation callbacks are refused rather than ignored. `AnvilVkImageAddress` remains a diagnostic oracle, not an application API; applications can now use `vkMapMemory`. Concurrent host calls are still unsafe — see the prerequisites. |
| Instance and device discovery | Typed generation handles reject stale handles and wrong owners across the implemented object families, including binary semaphores. The three core layer/extension enumeration calls truthfully report empty lists; named layers return `VK_ERROR_LAYER_NOT_PRESENT`, and an invalid physical-device handle leaves the device-extension count untouched. One instance, physical device, device and queue exist over whichever backend is linked. The queue derives graphics support from the backend's draw capability; compute remains absent. The format query derives linear BGRA8 colour-attachment support from that capability. The image-format query shares creation's format/type/tiling/usage/flags owner and derives extent and maximum resource bytes from backend geometry and pitch. | General physical-device properties and limits and sparse-image format properties remain absent. A production Pi build enumerates a device only when the graphics engine is up and an offscreen window is declared. UNO Q links `vk_backend_none.pbi` and enumerates nothing. |
| Command lifecycle | Pools and primary/secondary buffers across initial, recording, executable, pending, invalid, reset, free and destroy. Resources a submission references are retained until it completes, and reset, free, pool reset and pool destroy all refuse while a buffer is pending. Exactly one submission may be outstanding. A command buffer is either a transfer or a render pass and never both; a render pass holds a bounded ordered list of up to 4,096 draws. Each nonempty draw copies the current static or dynamic scissor into its immutable record; reset clears dynamic state and a draw before `vkCmdSetScissor` is refused. A render pass left open at `vkEndCommandBuffer` is refused. Whole-list preflight completes before mutation, and every abandon path discards the prepared generation ledger. | Secondary execution and inheritance, simultaneous use, array allocation, externally synchronized host access, and the rest of the command set are absent. |
| Pi 4 V3D backend | `vk_v3d_backend.pi4` lowers validated whole-image clears and accepted draw lists through transactional `NeonRebindSurface` + `NeonFrameBegin` + `NeonFrameEnd`. A complete list uses one rebind/frame/restore transaction and one bin/render submission, with transition-cached viewport, scissor, blend and varying packets. Signed scissor rectangles are intersected with the framebuffer before a `CLIP_WINDOW` packet is emitted, and repeated normalized rectangles emit no redundant packet. Per-draw shader records live in private 640-byte slots while immutable pipeline metadata is built and cleaned once. Vertex, uniform, sampled-image and slot cache ranges are overflow-checked, physically sorted and coalesced; the cache owner maintains all accepted ranges and issues one final barrier for the transaction. It submits real V3D jobs, maintains both cache domains, restores the complete display geometry, and maps the closed disabled/source-over blend mode to exact V3D 4.2 state. It refuses the scanout buffer and reports native failure as `VK_ERROR_DEVICE_LOST`. There is no processor-side or DMA image fallback in rendering. The completed attachment is presented through the display owner's DMA path, with the CPU copy retained only as a refusal fallback. The 2026-09-13 silicon runs proved native, smaller non-square and partial-tile images, the over-capacity refusal, an ordinary display frame, and three consecutive descriptor/varying jobs. The 2026-09-15 blend proof produced exact raw alpha/colour probes and a fresh teal-on-blue screenshot. The 2026-09-16 list proof executed six ordered draws as one bin/render job and one DMA presentation. The final 2026-09-16 atlas/chrome proof executed one TFU advance, one bin/render pair and one display-DMA presentation, returned its exact report, passed 211 report/pixel checks and produced a clean rotated 800x1280 capture. The bounded dynamic viewport/scissor pair is desk-proved, including private per-draw scale records and atomic geometry refusal; fresh Pi silicon resize/rotation proof remains outstanding. | Render areas smaller than the framebuffer, multiple render targets, mip levels, layers, MSAA and formats beyond linear BGRA8 remain unsupported. Submission is synchronous. Sample-mask suppression is desk-proved but still needs silicon visual proof. |
| Pi 4 renderer | The existing Pi driver initializes V3D 4.2, GPU page tables, QPU encoding, bin/render control lists, TFU and CSD submission, bounded waits, cache maintenance, OOM handling, and fault evidence. Neon builds fixed UI shaders and geometry for boxes, lines, glyphs, textures, clipping, rotation, and console chrome. The console has exercised the underlying V3D bin/render path on hardware. | Neon is an engine API, not Vulkan fixed-function state. Its built-in shaders are not SPIR-V, shader modules, descriptor-backed programs, or general graphics/compute pipelines. Direct polling and single-owner global arenas are not a Vulkan queue scheduler. A working console does not prove arbitrary Vulkan commands or shaders. |
| Memory and resources | One heap, taken whole from the backend and suballocated first-fit with page-granular alignment. `VkDeviceMemory`, `VkImage`, `VkBuffer` and the bounded `VkSampler` subset are real typed objects with generations and owners; memory-backed resources also carry bind and in-flight counts. A compiled pipeline's shaders take an INTERNAL allocation from the same heap that no handle names and `vkFreeMemory` cannot reach. Row pitch and image size come from the backend's rule; optimal images expose no fake row pitch. A host-visible allocation supports one checked `vkMapMemory` range, including `VK_WHOLE_SIZE`, and must be unmapped before free. Pi 4's identity-mapped window is advertised `HOST_COHERENT` because submission/completion own mandatory cache maintenance. A combined-image-sampler descriptor resolves to one closed live record only while its image is bound, carries `SAMPLED`, and remains in `SHADER_READ_ONLY_OPTIMAL`. The bounded optimal BGRA8 path records and retains one whole-image buffer copy and reaches `UIF_NO_XOR` through TFU. UINT16/UINT32 index buffers are retained like vertex buffers and scanned at submit to close the selected vertex range. | There are no buffer views, mip levels, array layers, general tilings, aliasing, dedicated allocations, sparse memory, flush/invalidate mapped-range entry points, 8-bit indices, storage buffers, or formats other than `B8G8R8A8_UNORM`. Linear sampled images remain limited to 1x1. Optimal images remain limited to the planner's level-zero one-layer/one-sample BGRA8 shape and one tightly packed whole-image copy; partial regions, row-length overrides and conversion are refused. There is one queue family, so queue-family ownership transfer is refused rather than implemented. |
| Synchronization | `VkFence` with its two states and its one owner, plus core-1.0 binary semaphores with generation ownership, ordered single-consumption, pending references and failure-atomic reserve/commit/complete/rollback. `vkWaitForFences` honours finite timeouts and is bounded twice. An already-satisfied `UINT64_MAX` wait succeeds; an unsatisfied one is explicitly refused. Image memory barriers carry layout tracking checked at record and submit. The test backend proves both immediate and later-polled semaphore completion and later-polled device-loss rollback; the current V3D backend completes inside `NeonFrameEnd`. | There are no events, timeline semaphores, host semaphore signal/wait/reset, general global or buffer memory barriers, multi-`VkSubmitInfo` batches, or concurrent queues. An unsignaled wait cannot park the single-owner queue and is refused loudly. A genuinely unlimited host wait that another thread could satisfy still needs reentrant call frames. |
| Shaders and pipelines | A SPIR-V front end parses a module, validates it against the Vulkan environment and retains exact records as immutable typed SSA IR. The accepted vertex path remains pass-through. The fragment path supports scalar and two-, three- or four-component binary32 values, straight-line `FAdd`/`FMul`, live input loads, one push-constant block, one uniform-block member, and one combined `sampler2D` implicit-LOD lookup; dead declared inputs, outputs and loads do not change the live interface. The V3D 4.2 lowerer reserves resource registers from live dependencies, emits QPU programs and a uniform stream transactionally, and publishes exact patch metadata only after complete validation. Uniform-buffer and sampled-image descriptors keep GPU-visible addresses in those streams; the backend proves each range mapped and cleans it before submission. Pipelines copy executable shader metadata, the immutable descriptor/push compatibility signature, and a normalized disabled or exact straight source-over blend mode. | There is no general control flow, phi, loop, function-call, integer arithmetic, conversion, comparison, storage buffer, dynamic descriptor, descriptor array, descriptor copy, push descriptor, specialization constant, pipeline cache, derivative pipeline, compute pipeline, second subpass, depth attachment or general blend equation. Sampled SPIR-V remains restricted to one combined 2D image at set zero, direct whole-`vec2` coordinates, implicit LOD, no image operands and direct whole-`vec4` output. The supported fragment graph may combine at most one live push load, one live UBO load and one live sample. The lowerer is serialized and uses bounded scratch storage; it is not a general optimizer or scheduler. Linear sampling remains bounded to one texel; the optimal path is the separately proved level-zero BGRA8 whole-image transfer shape. |
| Presentation | Pi display code owns HDMI/DSI surfaces, physical/logical rotation, cache/DMA presentation, capture, and V3D console retargeting. | There is no `VkSurfaceKHR`, platform extension, surface capability query, swapchain image set, acquire/present synchronization, present mode, resize/loss handling, or ownership transfer. The board diagnostic presents by copying the finished image onto the shown half of the framebuffer, which is the display layer's own path and not WSI. |
| Driver modules | PMFMOD v1 validates, relocates, zeroes, cache-synchronizes, and records an AArch64 module image in a board-provided arena. | Neither board wires a module arena or file discovery. The engine does not call module probe/init/quiesce entries, bind services, install stable dispatch trampolines, account for in-flight calls, or reload. The Vulkan backend is statically composed, which the layering permits. |

### What the gates prove, and what they do not

| Gate | Result | What it proves |
|---|---|---|
| `Anvil/Graphics/Vulkan/Tests/vulkan_foundation_check.py` / `tools/vulkan_core10_abi_inventory_check.py` | PASS — pinned registry compared, 196 emitted ABI and lifecycle checks over 3,844,936 interpreted A64 instructions; the complete inventory adds 37 checks and reports 114/281 declaration categories present. The queue mutant, all three feature mutants and the format/image-format mutation families are RED on their recorded runs. | Vocabulary against the pinned `vk.xml`, exact AArch64 layout including `VkSemaphoreCreateInfo`, `VkPipelineDynamicStateCreateInfo`, `VkRect2D` and all 18 members of `VkSamplerCreateInfo`, and that a build with no backend enumerates no device. The feature properties poison then query the complete record, accept a non-null all-false record, and turn on each of its 55 members separately. Format properties require exactly proved linear BGRA8 feature bits. Image-format properties require the shared create/query combination owner, backend-derived geometry and pitch-derived maximum bytes, one mip/layer/sample, stale-handle and caller-output safety, and refusal of every unsupported input. The queue properties prove an ordinary graphics-family scan selects family zero for a draw-capable backend and finds no graphics family for a transfer-only backend. Every checked structure member name, order and type is compared against both the registry and `vk_core_1_0.pbi`, so the two transcriptions have to agree. |
| `tools/vulkan_semaphore_check.py` | PASS — 266 registry/source/emitted checks, 214 emitted rows and 806,652 interpreted A64 instructions; all 20 hostile mutations are RED. | Exact core-1.0 create/destroy prototypes and ABI, ordered wait/signal adaptation, generation-safe reserve/commit/complete/rollback, immediate and later-polled completion, deferred device-loss propagation, dispatch exposure and atomic device teardown. The whole baseline-plus-mutation campaign holds the shared Vulkan checker lock and stages every mutant outside the repository. |
| `tools/vulkan_dispatch_check.py` / `tools/vulkan_dispatch_inventory_check.py` | PASS — 424 registry/source/emitted checks, 84 emitted rows and 3,236,977 interpreted A64 instructions. The complete inventory validates all 137 core-1.0 commands: 81 declared-callable and 56 missing, with 80 names exposed through the resolvers. | Exact registry prototypes, aliases and command domains; case-sensitive bounded lookup; null-instance/global, instance and device query rules; zero-count layer/extension enumeration with caller-output safety; public `vkCmdSetScissor`, `vkCmdBindIndexBuffer` and `vkCmdDrawIndexed`; and the deliberate `vkFreeDescriptorSets` withholding boundary. |
| `tools/vulkan_resource_check.py` | PASS — 474 independent property checks over 1,134,241 executed A64 instructions. The earlier complete mutation run rejects all 30 prior mistakes; the two focused `UINT64_MAX` mutants, all ten focused map-memory mutants and the focused transfer-only attachment mutant are RED. The suite now has 44 mutants after the obsolete semaphore-refusal mutant was removed; a fresh complete run of all 44 has not been claimed. | The resource, layout, fence, retention, mapping, format-capability, submission and error-reporting contracts, executed through the public entry points, with an MMIO hard stop armed; and that every byte of the bound image still held its poison, so no processor-side clear exists anywhere in the path. Its mapping properties use the public entry points to distinguish host-visible/non-visible types, owner, live/stale handle, duplicate/unbalanced state, flags, exact/whole ranges and returned pointer, then use the mapping to poison the image. Its format property refuses colour-attachment image creation when the backend advertises no graphics draw path while the shared combination owner still accepts transfer-only and sampled-only usage. Its wait properties distinguish an unsignalled unlimited wait (explicitly unsupported) from an already-satisfied unlimited wait (success). |
| `tools/vulkan_v3d_backend_check.py` | PASS — 84 property checks over 2,927,023 executed A64 instructions; all five production board diagnostics, including `vulkanIndexedTriangleProof.pi4`, build real images. The recorded mutation run rejects all 16 desk-reachable mistakes and names 2 board-only rules it cannot reach. | That the whole closure links against the real display, V3D, QPU and Neon implementation; that a build with the engine down enumerates no device without MMIO; that geometry is planned before mutation, every arena/range/in-frame boundary is checked, and a failed rebind preserves the prior surface. It also requires full geometry restoration and the descriptor TMU mapped-range/cache-clean contracts. The source contract requires the pipeline/vertex/index/descriptor cleans before submission and the GPU clean plus target clean/invalidate before completion, giving the `HOST_COHERENT` advertisement teeth. |
| `tools/vulkan_spirv_check.py` | PASS — 486 checks over 11,639,888 executed A64 instructions across 58 assembled modules. | The legacy accepted and refused SPIR-V vocabulary is unchanged after exact-record retention: modules are assembled word by word from specification opcode numbers, walked without mutation, and either published only after complete validation or refused with a whole sentence naming the unsupported semantic. |
| `tools/vulkan_spirv_ir_adapter_check.py` | PASS — 8,704 properties over 57,196,054 interpreted A64 instructions; all 7 focused mutations are RED. | Exact immutable raw words, every retained semantic record field/order/offset, typed IR types and nodes, publish-last invalidation, self-use dominance refusal, poisoned-output clearing, and all six embedded pointer rebindings. |
| `tools/vulkan_ir_v3d42_check.py` | PASS — 65 emitted checks, 734 independently decoded QPU instructions and 23,444,775 interpreted A64 instructions; all 39 causal mutations are RED with infrastructure failures separated from semantic rejection. | Transactional straight-line typed-IR lowering, binary32 `FAdd`/`FMul`, dependency-driven register reservations, split resource lifetimes, exact uniform metadata, dead-SSA behavior, range/overlap checks and publish-last failure atomicity. |
| `tools/vulkan_qpu_emitted_check.py` | Baseline PASS — 15 emitted programs containing 423 independently decoded V3D 4.2 instructions over 44,342,506 A64 setup instructions. | Independent decoding of coordinate, vertex and fragment programs for varying, push-constant, split-binding, uniform-buffer, sampled-image and typed arithmetic paths. |
| `tools/vulkan_draw_pool_check.py` | PASS — 89 properties over 15,033,844 interpreted A64 instructions. | The 184-byte, 4,096-record bounded pool, immutable indexed/non-indexed draw snapshots, reset semantics, and the rule that dynamic-scissor state belongs to a command buffer and is copied into each nonempty draw rather than referenced later. |
| `tools/vulkan_pipeline_check.py` | PASS — 655 property checks over 52,852,668 executed A64 instructions. The current portable draw-list/scissor gate separately passes 61 properties over 3,950,304 instructions and rejects all four focused scissor mutations. The compact mixed-descriptor gate, focused dead-I/O wrapper, optimal-copy, lifetime-alias and sampled-state families remain red where expected. | The public path through resource creation, transfer, immutable descriptor schemas, mixed UBO-plus-sampler binding, typed fragment lowering, ordered draw-list capture, dynamic-scissor snapshotting, transactional submission and exact backend observation. It proves all nine mixed uniform words, six descriptor dependencies plus the attachment view, dual-role view retention, compatible schema handles, slot reuse safety, per-type pool atomicity, cross-device refusals, dead-interface liveness and failure-atomic release. The test backend writes no pixels or MMIO; real GPU execution is paired only with the explicit Pi 4 runs below. Each checker owns unique artifacts and a whole-run OS lock prevents compilation through another process's hostile mutation. |
| `tools/vulkan_v3d_draw_slot_check.py` | PASS — 58 independent properties over 561,669 executed A64 instructions; all 8 hostile ABI mutations are RED. | Immutable pipeline metadata, private 640-byte draw slots, a 292-byte maximum live record, exact 28-byte fragment-shader cloning for the measured fixture, overflow refusal, and exact coalesced cache ranges. |
| `tools/vulkan_v3d_backend_list_check.py` | PASS — 100 property checks over live 1-, 3- and 3,505-draw lists plus admission-only 4,096, executing 26,954,922 A64 instructions. Its earlier 10 causal mutants remain RED and all 3 scissor normalization/transition/preflight mutants are RED. | Whole-list atomic preflight, one frame transaction, exact indexed/non-indexed draw and primitive counts, transition-cached viewport/scissor/blend/varying state, signed/unsigned overflow-safe clip normalization, rollback, physical vertex/index cache-range union and a stable last-record diagnostic snapshot. The indexed row observes setup base/byte size, hardware index type, byte offset, maximum-index vertex bound and pre-frame refusals. The 3,505-draw case is live; only the 4,096 admission boundary uses a zero sample mask. |
| `tools/vulkan_indexed_draw_check.py` | PASS — 32 public-path cells, 12 encoder results and 46 exact packet/refusal bytes over 4,379,679 emitted A64 instructions with the current compiler; `--mutate` rejects all 6 focused mistakes. | UINT16/UINT32 binding and recording, `firstIndex` applied once, maximum-index vertex bounds, stale/range/alignment refusals before counters move, in-flight index lifetime, and byte-exact V3D 4.2 `INDEX_BUFFER_SETUP` plus `INDEXED_PRIM_LIST` emission. The bounded UINT16 Pi 4 diagnostic passed on 2026-09-26; UINT32 silicon proof remains owed. |
| `tools/v3d_cache_batch_emitted_check.py` | PASS — 38 exact checks over 1,961 interpreted A64 instructions; all 6 hostile mutations are RED. | `V3dCacheBatchBegin`, `V3dCacheBatchRange` and `V3dCacheBatchEnd` retain several validated aligned ranges and issue one final barrier. Overflow, negative/full-width addresses, zero length, misuse, poisoning and the legacy single-range API are independently exercised. |
| `tools/vulkan_atlas_chrome_acceptance_check.py` | BOARD PASS — 211 exact source/report/pixel-oracle checks against the final Pi 4 run. The returning diagnostic is a 976,956-byte PMF container with SHA-256 `485d21a7c1ddb11b87b36220f8e339bc4cd33eeff696b9577fc754841ee73e9a`. | One public render pass containing eight ordered six-vertex quads; an 8x8 optimal atlas copied through the TFU; UV sampling; descriptor-bound `sample * push + UBO`; tint and source-over blend; eight `vkCmdSetScissor` snapshots; exact solid/transparent/covered/clipped pixel regions; one TFU advance, one bin/render pair and one display-owner DMA presentation. Build 148 returned exact `x0=0x6C85A0` in 10.2 seconds with report slot 128 equal to zero, then returned to its prompt with the deadman off and no core leases. |
| `tools/neon_atlas_contract_emitted_check.py` | PASS — 26 source checks and 41 emitted assertions over 3,118,073 interpreted A64 instructions; all 5 hostile mutations are RED. | The existing Neon font builder publishes one borrowed read-only linear RGBA8 raster, exact dimensions/bytes, copied ASCII 32..126 glyph UVs and one copied opaque-white texel rectangle only after a successful current-font ensure. Font changes invalidate every query; CPU-only ensure does no TFU/V3D work and does not publish the private tiled-atlas state early. |
| `tools/neon_vk_chrome_acceptance_check.py` | DESK PASS — 267 production-adapter source checks, 27 emitted contract assertions, 58 hook source checks plus 44 emitted hook assertions, 45 emitted production-geometry assertions, and all 8 hostile traces RED. | `neon_vk_chrome.pi4` owns persistent pipeline, atlas, descriptors, command buffer, fence and coherent vertex storage; installs the complete box/text/scissor/fan/outline/line hook family only after successful creation; and atomically lowers bounded fans and one-pixel lines into Vulkan triangle lists. The exact emitted production procedures cover a convex fan, closed outline, horizontal/vertical/diagonal/zero-length lines, cursor preservation, overflow and safe reset. The real existing Neon panel/menu/list/text scene records 109 quads, 47 draws, 654 vertices and five scissor states, then consumes one intent and calls display DMA once. No Pi execution or screenshot of the new primitive shapes is claimed yet. |
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

The generic `tools/board_run.py` wrapper now accepts an explicit unsigned
`--expect-x0` value, validates it before any board side effect, and records the
expectation in its JSON evidence. A mismatch remains a failure after trace and
screenshot preservation. Its fatal-exception path validates the requested
trace range before boot, retains every accepted exception datagram through a
quiet prompt/reset boundary, and never sends trace or screenshot commands as
though a faulting payload had returned. Focused fake-console gates cover normal
return, expected nonzero return, mismatch, complete and incomplete exception
records, timeouts, malformed ranges and the no-transmit-on-fatal rule.

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

**2026-09-13, run 9 — PASSED. Sampled-state integration preserves the visible
V3D path.** The final returning container was built from public main through
`4e24052`, was 575,804 bytes, and had SHA-256
`177c3c3f4d17437f7cdf568b3df0707786c0c54a12eb11cf6f34fa04443c3c7f`.
Monitor build 101 received and independently hashed those exact bytes at
`$00500000`; the run used the DMA console, a 15-second hardware deadman and a
fresh screenshot. The report at `$00596000` had both magics and step 12.

All three diagnostic verdicts were zero. The format feature word was `$81`
(`SAMPLED_IMAGE | COLOR_ATTACHMENT`), five allocations were populated through
`vkMapMemory`, all three submits and waits were zero, bin/render jobs advanced
from 0 to 3, native error/OOM/MMU counts were zero, the guard remained
`$C0E6C000`, and all pixel distances and over-tolerance counts were zero. The
captured 1280x800 frame visibly contains the complete interpolated triangle;
its pixel SHA-256 is
`715531a2bbd059308f3e6b5dd9fef4226891632c1ef2d88065222e965cc3add2`.

Two earlier attempts in this same slot were honest RED diagnostic controls,
not GPU failures: first the diagnostic still expected the old format-feature
word and stopped before submission, then its deliberately unsupported
descriptor case still named combined image sampler after that type became the
accepted bounded state. Those consumers were updated to the new contract; the
final diagnostic instead refuses `STORAGE_IMAGE`, and its five intended
validation refusals all remained present. This run proves integration and no
regression of the existing visible V3D/TMU path. The new combined-image-sampler
record itself remains desk-only state until SPIR-V texture instructions and a
V3D texture fetch consume it; no sampled pixel is claimed by that run.

**2026-09-13, run 10 — PASSED. One sampled pixel, through the real V3D TMU.**
Public commit `85c2db8` produced a 636,380-byte flat payload with SHA-256
`46A07A9F7B943F60BD5E3FCAC19E25F510DD2837F8283D6225929DF4C27D051F` and a
636,508-byte PMF container with SHA-256
`F7E32E54EF59952868859B629EACA64F3D3BDE85C78790353E8EE18DD0146352`.
Monitor build 101 received and independently verified that container, verified
the inner image at `$00500000`, armed a 15-second deadman and returned normally
in 8.63 seconds. The nonzero x0 is intentionally the report pointer
`$005A6000`, not a payload error.

The 160-word report had A/B/C/D verdicts all zero, step 13 and both magics.
The sampled submit and wait were zero; all three inside probes were exactly
`$FFFFC020` and all three outside probes exactly `$FF3380B2`. The submitted
texture state held source `$067DA000`, width `$04000000`, height `$00400100`
and format/swizzle `$00A9C040`. Bin and render jobs each moved from 3 to 4;
MMU faults, bin OOM, native backend error and detail were all zero. The returned
1280x800 screenshot has SHA-256
`B8D535126FFD61C82E194D196C83F24A5B4AFBCDF01936C70D1DD0C20F7902A62`.

The first control run measured the old identity-swizzle defect exactly: source
`$FFFFC020` became `$FF20C0FF` at all three inside probes while the clear,
submission, counters and fault state remained correct. The source owner now
uses Mesa's BGRA8 Z,Y,X,W format-table swizzle; the gate mutates it back to
identity and turns red. This proves only the declared one-texel linear subset;
run 11 below closes the next bounded optimal-image transaction without changing
the scope of this older run.

**2026-09-13, run 11 — PASSED. A 4x4 optimal image copied by TFU and sampled
by the TMU.** The final 670,884-byte PMF container had SHA-256
`B1989D9D9E70FE5F01D8CD527DE09D987767E525CE30DA58DB0F16125512CF67`;
its 670,756-byte flat image had SHA-256
`3A3FBDF3F71D3A148600CF667352A49BBA5BB989BD76E5D5E016A29C0129243C`.
Monitor build 101 independently verified the staged container at `$00500000`,
armed a 15-second deadman, returned normally with report pointer `$005B6090`,
and captured a new 1280x800 frame (sequence 8 to 9).

The 176-word report had all four pass verdicts zero, step 13, length 704 and
both magics. The transfer source was a 128-byte buffer using memory type 0,
selected by scanning the physical memory properties: `memoryTypeBits=1`, one
reported type, flags 7 (`DEVICE_LOCAL | HOST_VISIBLE | HOST_COHERENT`), correct
allocation `sType`, and result zero. The optimal image required 1,024 padded
bytes and reported row pitch zero. Copy submit/wait were zero, TFU jobs moved
0 to 1, the published layout was `SHADER_READ_ONLY_OPTIMAL`, and the sampled
draw moved bin/render counters 3 to 4. The texture state was base `$067DA000`,
width `$10000000`, height `$00400400`, format/swizzle `$00A9C840`; nearest
sampler words were `$83` and `$00090000`.

The three inside probes were exactly green `$FF00FF00`, blue `$FF0000FF` and
red `$FFFF0000`; all three outside probes remained `$FF3380B2`. MMU, OOM,
native backend and detail faults were zero. The captured pixel SHA-256 is
`22724024624AF20F645590647A69F4B7B7D9EE16027241B1793BE86D61AD6B0B`;
the PNG file SHA-256 is
`F6552765902480625D7953E98E7A7AFCD45FB3ACE034E32EAD9853623B0C3B03`.

This is not general texture support. It proves one two-dimensional BGRA8
image, one mip, one layer, one sample, a single tightly packed whole-image
region at a 64-byte-aligned source offset, level-zero `UIF_NO_XOR`, and the
current normalized nearest-filter sample path. Other formats, partial copies,
row-length/image-height overrides, mips, layers, scaling and conversion remain
refused.

**2026-09-15, run 12 — PASSED. One fragment executes sampled-image, push and
UBO arithmetic on silicon.** Monitor build 101 verified the exact 874,740-byte
container, SHA-256
`6405122BD5F7BE41BB79B56CDCB770D0499AA1A7E6E602AAE17C42F7419B9D85`,
at `$00500000`, armed the 15-second deadman and returned normally in 9.81
seconds with `x0=$005E7E78`. The flat 874,612-byte image has SHA-256
`C942FDF52697C80DBC3ACC56850431366C04ADDBAA050FC840ECAC3FB965922A`.
The checker recovered all 240 report words and required both magics, length
960, final step 13, four zero pass verdicts, zero submit/wait results and zero
MMU, OOM and native-backend faults.

The fragment computes `sample * push + UBO`. The retained typed IR and V3D
lowerer published nine distinct runtime indices: push RGBA 4..7, UBO
address/config 2/3, texture/sampler 0/1 and TLB 8. The returned shader record
proved that all nine values were patched through those indices, including UBO
address `$067D3000`, vec4 TMU configuration `$FFFFFF7C`, texture/sampler
pointers `$067DD20F`/`$067DD301`, and TLB word `$FFFFFFFF`. The three inside
pixels were exactly `$FF808000`, `$FF800080`, `$FFFF0000`; all outside probes
kept `$FF3380B2`. TFU, bin and render counters each advanced exactly once.
Module and pipeline-layout source slots were destroyed and reused without
altering the compiled pipeline, and all nine retained resource counters were
zero after completion. The five deliberate hostile validation probes remained
a cumulative count of 5 before, during and after the mixed draw while the
current fault code was zero on both sides, proving the draw added no fault.

The fresh DMA capture was sequence 2, 1280x800, with pixel SHA-256
`D1F98B232832C919E8FC96F4EC1EF8144240063B0BF76B05A3B4DC7C44D51A18`;
the triangle was inspected and clean. The board returned healthy to the build
101 prompt. This accepts only the current one-sample, one-push-load,
one-UBO-load straight-line binary32 graph. It is not general shader, descriptor,
texture, scheduling or Vulkan-conformance proof.


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

## Accelerated draw-list presentation — Pi 4 acceptance, 2026-09-16

`vulkanDrawListProof.img.pmf` records six ordered Vulkan draws into one render
pass: overlapping opaque push colours, two exact source-over draws, one
varying-colour draw and a final opaque top layer. On Anvil build 148 the
849,648-byte artifact, SHA-256
`31c848b67deedb2d5d96f7de8e4acb303b51b5c143e50dcb972312ba888c50af`,
was verified on the board, run from `$500000` under a 15-second deadman and
returned normally with its report at `x0=$90BD00`.

The report proves six backend draws but exactly one V3D bin job and one render
job. Its transition counts are one viewport, three blend and three varying
changes; the source-over attachment words are exactly `$BF007F80` and
`$9F803F40`. Both verdicts are zero, the render-target guard is unchanged,
there is no MMU/OOM/fault state, teardown completed, and the display owner
records exactly one DMA operation for presentation. `DisplayBlit` now sends an
arbitrary clipped native-format source rectangle through `DmaCopy2D`, with
explicit source and destination cache ownership; the original CPU pixel loop
is only the safe fallback when DMA policy or validation refuses the request.

Capture sequence 5 advanced to 6. The fresh 800x1280 BGRA scanout has SHA-256
`9edf1bb8ca7ea5937a96997b53c0def59d8e2b68f3efa1da7f9e2a6f5a7d85c9`
and is pixel-identical to the earlier CPU-presented reference. The independent
acceptance checker verified the complete 64-word report and eight separate 5x5
screen regions: 262 exact checks. The monitor stopped the deadman and returned
to its real build-148 `pmf>` prompt.

## Dynamic scissor and atlas/chrome tranche — current boundary, 2026-09-16

The portable pipeline now accepts exactly one dynamic state:
`VK_DYNAMIC_STATE_SCISSOR`. `vkCmdSetScissor(commandBuffer, 0, 1, rect)` is a
public, dispatch-visible core command. A nonempty draw through a dynamic
pipeline requires a supplied rectangle; command-buffer reset clears it; and
each draw copies it into the draw record. The V3D backend intersects signed
offsets and unsigned extents with the framebuffer without wrapping, converts
empty or wholly exterior rectangles into a zero-size clip, and emits
`CLIP_WINDOW` only when the normalized result changes.

The cache owner now accepts several checked, aligned ranges between
`V3dCacheBatchBegin()` and `V3dCacheBatchEnd()` and issues one final barrier.
The old one-range operation remains valid. This removes the thousands of
per-range barriers formerly paid by the 3,505-draw fixture without moving
range validation or cache ownership into the Vulkan layer.

`RaspberryPi4/Examples/Diagnostics/vulkanAtlasChromeProof.pi4` is the next
returning acceptance instrument. Through public calls it copies an 8x8
optimal BGRA8 atlas, binds the mixed sampled-image/UBO descriptor, supplies UV
vertices and push tints, enables exact source-over blending, records eight
six-vertex quads and eight dynamic scissor snapshots in one render pass, and
presents once through display DMA. Its independent checker has exact 5x5
pixel regions for the solid panel, later toolbar, a transparent atlas texel, a
covered tinted texel, and covered texels on both sides of the final clip edge.

The corrected build-148 RAM-only run loaded the 976,956-byte PMF at `0x500000`
and returned exact `x0=0x6C85A0` in 10.2 seconds. Report slot 128 was zero. The
report records one TFU advance, one bin/render pair and one display-DMA
presentation, and its exact report and pixel oracle pass all 211 checks. Fresh
capture sequence 8 is a 1280x800 PNG representing the rotated 800x1280 target.
The monitor returned to the build-148 prompt with the deadman explicitly off
and no core leases; the run performed no flash, reset or persistent write.
`VULKAN_IDE_CHROME_ACCEPTANCE_2026-09-16.md` pins the artifacts, hashes and
acceptance boundary.

The later read-only Neon atlas and renderer-hook work refactored the common CPU
raster owner, so the current tree has different exact bytes: 977,076-byte PMF,
SHA-256
`c4b43f94547343ef2b01232a81a549f3444f66b4e29c3d90197a2b887fca147b`,
expected report pointer `0x6C85C8`. It compiles and its atlas/display desk gates
pass. A different lane currently owns the shared Pi 4, so this post-refactor
artifact has not been run and does not borrow the earlier image's board PASS.

The first real implementation step is now in the tree rather than another
synthetic primitive. `neon_vk_chrome.pi4` maps persistent box, atlas-text,
fan, outline, line-list and scissor resources onto these public paths and the
existing Neon widget layer selects it through one all-or-none primitive hook.
The desk scene calls the real panel, menu, list and text procedures unchanged
and proves 109 quads, 47 draws, 654 vertices, five scissor states, one submit
intent and one display-DMA call with no processor pixel fallback. The emitted
geometry gate additionally proves exact bounded triangle-list lowering. What
remains is the exact Pi 4 run and screenshot of both the widget frame and new
primitive shapes, then clean HDMI/DSI/rotation/resize coverage.

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
   **Parsing, validation, exact-record retention and the first typed IR are
   done.** The immutable IR represents the declared single-function,
   single-block vertex/fragment subset, including straight-line binary32
   `FAdd`/`FMul`; unsupported capabilities and operations remain explicit
   refusals. It is a bounded shader compiler path, not a general SPIR-V
   implementation.
5. Add pipeline layouts, descriptors, render passes, fixed-function state and
   V3D QPU lowering. Differential shader tests and independent packet/QPU
   decoders precede broader instruction coverage.
   **Pipeline layouts, one render pass, the fixed-function state listed above,
   typed QPU lowering, uniform-buffer descriptors and bounded combined image
   samplers are implemented.** A dense two-binding set may carry both resource
   types; copied schemas, per-type pool accounting, device ownership and
   submission lifetimes are independently gated. The QPU checker decodes 423
   V3D 4.2 instructions across all 15 emitted programs. Historical UBO and
   sampled-image silicon runs remain valid, and the 2026-09-15 recovered and
   graded board report now proves the first bounded three-source arithmetic
   fragment (`sample * push + UBO`) on V3D 4.2. Ordered multi-draw recording,
   exact source-over blend, per-draw dynamic scissor and one-barrier cache
   batching are now joined by the final 2026-09-16 atlas/chrome Pi 4 pass. The
   persistent Neon box/text/scissor/fan/outline/line adapter and real-widget
   frame are desk green; their exact Pi 4 screenshot and return proof remain.
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
