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

Updated 2026-09-11, when the SPIR-V front end and the first graphics
pipeline landed. The clear slice below is unchanged by them.

### The implemented public entry points

These are callable `vk*` names with the registry's own parameter lists and
return types. Everything else in core 1.0 does not exist and a caller linking
one gets a compile-time refusal naming it.

| Entry point | Status |
|---|---|
| `vkCreateInstance` / `vkDestroyInstance` | Implemented. Layers and extensions are refused with `VK_ERROR_LAYER_NOT_PRESENT` / `VK_ERROR_EXTENSION_NOT_PRESENT`. |
| `vkEnumeratePhysicalDevices` | Implemented, including the two-call `pPhysicalDeviceCount` form and `VK_INCOMPLETE`. |
| `vkGetPhysicalDeviceMemoryProperties` | Implemented. One heap, backend-reported. |
| `vkGetPhysicalDeviceQueueFamilyProperties` | Implemented. One family, `VK_QUEUE_TRANSFER_BIT` only — not graphics, not compute. |
| `vkCreateDevice` / `vkDestroyDevice` / `vkGetDeviceQueue` | Implemented for one queue of family 0. Device extensions and any enabled feature are refused. |
| `vkCreateImage` / `vkDestroyImage` | Implemented for 2D, `VK_FORMAT_B8G8R8A8_UNORM`, `VK_IMAGE_TILING_LINEAR`, one mip, one layer, one sample, exclusive sharing, usage within `TRANSFER_SRC`/`TRANSFER_DST`. Everything else is refused with a real code. |
| `vkGetImageMemoryRequirements` | Implemented. Size, alignment and `memoryTypeBits` come from the backend. |
| `vkAllocateMemory` / `vkFreeMemory` | Implemented over one backend heap, first-fit with real reuse of freed holes and a real `VK_ERROR_OUT_OF_DEVICE_MEMORY`. |
| `vkBindImageMemory` | Implemented, with alignment, range, double-bind, wrong-parent and memory-type rules enforced. |
| `vkCreateCommandPool` / `vkDestroyCommandPool` / `vkResetCommandPool` | Implemented. |
| `vkAllocateCommandBuffers` / `vkFreeCommandBuffers` | Implemented for one buffer per call; array allocation is refused, not faked. |
| `vkBeginCommandBuffer` / `vkEndCommandBuffer` / `vkResetCommandBuffer` | Implemented. A recording error moves the buffer to invalid and `vkEndCommandBuffer` reports it, as the specification requires. |
| `vkCmdPipelineBarrier` | **Not callable under its registry name.** See the note below. `vkCmdPipelineBarrierArgs` is the same call with the nine arguments after the command buffer in one record, in registry order. One image memory barrier per call; global and buffer barriers are refused. |
| `vkCmdClearColorImage` | Implemented with its exact registry signature, for one whole-image range. |
| `vkCreateFence` / `vkDestroyFence` / `vkResetFences` / `vkGetFenceStatus` / `vkWaitForFences` | Implemented. |
| `vkQueueSubmit` | Implemented for one `VkSubmitInfo`, one command buffer, no semaphores. Batches, multiple buffers and semaphores are refused with `VK_ERROR_FEATURE_NOT_PRESENT`. |
| `vkDeviceWaitIdle` | Implemented. |

### The graphics pipeline entry points, added 2026-09-11

| Entry point | Status |
|---|---|
| `vkCreateShaderModule` / `vkDestroyShaderModule` | Implemented. The module is WALKED at creation, not stored: `vkCreateShaderModule` returns an Anvil refusal, with a sentence, for any module outside the accepted SPIR-V subset. |
| `vkCreateBuffer` / `vkDestroyBuffer` / `vkGetBufferMemoryRequirements` / `vkBindBufferMemory` | Implemented for `VK_BUFFER_USAGE_VERTEX_BUFFER_BIT` and the two transfer bits, exclusive sharing, page-granular alignment. |
| `vkCreateImageView` / `vkDestroyImageView` | Implemented for `VK_IMAGE_VIEW_TYPE_2D`, `VK_FORMAT_B8G8R8A8_UNORM`, identity swizzle, the whole colour subresource. |
| `vkCreateRenderPass` / `vkDestroyRenderPass` | Implemented for one colour attachment, one subpass, no dependencies, `loadOp` CLEAR and `storeOp` STORE. |
| `vkCreateFramebuffer` / `vkDestroyFramebuffer` | Implemented for one attachment at the image's own extent, one layer. |
| `vkCreatePipelineLayout` / `vkDestroyPipelineLayout` | Implemented for no descriptor sets and at most one push constant range: fragment stage, offset 0, 16 bytes. |
| `vkCreateGraphicsPipelines` / `vkDestroyPipeline` | Implemented for exactly one `VkGraphicsPipelineCreateInfo` per call and no pipeline cache. See the state table below for what it accepts. |
| `vkCmdBeginRenderPass` / `vkCmdEndRenderPass` | Implemented for `VK_SUBPASS_CONTENTS_INLINE`, one clear value, a render area that is the whole framebuffer. |
| `vkCmdBindPipeline` | Implemented for `VK_PIPELINE_BIND_POINT_GRAPHICS`. |
| `vkCmdBindVertexBuffers` | Implemented for one binding, binding 0. |
| `vkCmdPushConstants` | Implemented for the whole sixteen-byte fragment-stage block at offset 0. |
| `vkCmdDraw` | Implemented for one instance, a vertex count that is a whole number of triangles, and a vertex range that is inside the bound buffer. |

The fixed-function state a pipeline may declare: one vertex input binding at
`VK_VERTEX_INPUT_RATE_VERTEX`; attributes at locations 0..n-1 (n <= 4) in
`R32G32_SFLOAT`, `R32G32B32_SFLOAT` or `R32G32B32A32_SFLOAT`, all from binding
0; `VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST` with no primitive restart; one
viewport and one scissor, neither dynamic, the scissor covering the viewport
and the viewport starting at the origin with whole-pixel extents; fill mode, no
culling, no depth bias, no depth clamp, no rasteriser discard; one sample;
blending disabled and every channel written; no depth-stencil state and no
dynamic state. Everything else is refused with a code and a sentence.


> **The ten-parameter problem.** `vkCmdPipelineBarrier` takes ten parameters.
> The PureMetal AArch64 backend passes at most eight, in `a0`..`a7`, and
> refuses a ninth at compile time; stack arguments are not emitted yet. This
> is the only core-1.0 command in the implemented set that cannot carry its
> registry signature, and it is a toolchain limitation, not a design choice.
> The exact change that removes it is argument passing on the stack in the
> A64 backend's call emission.

### The layers

| Area | Implemented and checked | Not implemented or not claimed |
|---|---|---|
| Registry and ABI | A PureBasic generator verifies the pinned registry hash and emits a selected core-1.0 slice. The checked-in vocabulary now covers the results, structure types, command-buffer, image, memory, queue-family, access, stage, aspect and fence values this slice uses, plus 29 naturally aligned AArch64 structures with registry member names, order and widths. The gate regenerates every one from the pinned `vk.xml` and executes exact size and `OffsetOf` fixtures. | The complete core-1.0 enum, bitmask, alias, handle, union, callback, command prototype, platform guard, optionality and valid-usage vocabulary is not generated. `VkClearColorValue` is a union and is deliberately not declared — PureMetal has no union, so the adapter reads the caller's sixteen bytes as the `float32` arm and says so. No other target ABI is declared equivalent merely because AArch64 layout passes. |
| Public API | The entry points in the table above, validating `sType`, `pNext`, flags, counts, pointers, parents and host-synchronization rules before entering the object engine. Invalid usage that core Vulkan leaves undefined returns an Anvil code far outside `VkResult`'s range, with a whole sentence naming the code and the next thing to check; void commands record that sentence and, where the specification allows, invalidate the command buffer. | There is no loader, `vkGetInstanceProcAddr`, `vkGetDeviceProcAddr`, dispatch table, layer interface, extension negotiation or `VkAllocationCallbacks` support. Host allocation callbacks are refused rather than ignored. `vkMapMemory` does not exist; `AnvilVkImageAddress` is an Anvil answer and is named as one. Concurrent host calls are still unsafe — see the prerequisites. |
| Instance and device discovery | Typed generation handles reject stale handles and wrong owners across all nine object types. One instance, physical device, device and transfer queue, over whichever backend is linked. | A production Pi build still enumerates a device only when the graphics engine is up and an offscreen window has been declared. UNO Q links `vk_backend_none.pbi` and enumerates nothing. |
| Command lifecycle | Pools and primary/secondary buffers across initial, recording, executable, pending, invalid, reset, free and destroy. Resources a submission references are retained until it completes, and reset, free, pool reset and pool destroy all refuse while a buffer is pending. Exactly one submission may be outstanding. A command buffer is either a transfer or a render pass and never both; a render pass holds one draw; a render pass left open at `vkEndCommandBuffer` is refused. | Secondary execution and inheritance, simultaneous use, array allocation, externally synchronized host access, and the rest of the command set are absent. |
| Pi 4 V3D backend | `vk_v3d_backend.pi4` lowers one validated whole-image clear to `NeonRetarget` + `NeonFrameBegin` + `NeonFrameEnd`, which build and submit real V3D bin and render control lists, wait for both, clean the V3D caches and maintain the processor's view of the target. It saves and restores the engine's previous target even when the frame fails, refuses the buffer the display is scanning out, and reports a native failure as `VK_ERROR_DEVICE_LOST` with the engine's own code. There is no processor-side and no DMA image fallback anywhere under it. | It clears only an image whose width, height and row pitch are the render geometry `NeonInit` was given: `NeonFrameBegin`/`NeonFrameEnd` render at that geometry and `NeonRetarget` rebinds only the target address. Any other extent is refused at record time with `VK_ERROR_FEATURE_NOT_PRESENT`. Lifting that needs a new primitive in `RaspberryPi4/Lib/v3d.pi4` to rebind the render geometry and re-size the tile pools between frames. Execution is **accepted on silicon as of board run 2, 2026-09-11** (see Board runs): every one of 1,024,000 pixels correct, both V3D jobs advanced, no fault, guard buffer untouched. That is one clear at one geometry with no shader and no draw, and nothing beyond it is claimed. |
| Pi 4 renderer | The existing Pi driver initializes V3D 4.2, GPU page tables, QPU encoding, bin/render control lists, TFU and CSD submission, bounded waits, cache maintenance, OOM handling, and fault evidence. Neon builds fixed UI shaders and geometry for boxes, lines, glyphs, textures, clipping, rotation, and console chrome. The console has exercised the underlying V3D bin/render path on hardware. | Neon is an engine API, not Vulkan fixed-function state. Its built-in shaders are not SPIR-V, shader modules, descriptor-backed programs, or general graphics/compute pipelines. Direct polling and single-owner global arenas are not a Vulkan queue scheduler. A working console does not prove arbitrary Vulkan commands or shaders. |
| Memory and resources | One heap, taken whole from the backend and suballocated first-fit with page-granular alignment. `VkDeviceMemory`, `VkImage` and `VkBuffer` are real objects with generations, owners, bind counts and in-flight counts; a compiled pipeline's shaders take an INTERNAL allocation from the same heap that no handle names and `vkFreeMemory` cannot reach. Row pitch and image size come from the backend's rule, not from the width. Memory still bound, or referenced by an outstanding submission, cannot be freed. | There are no buffer views, samplers, descriptors, mip levels, array layers, tilings other than linear, aliasing, dedicated allocations, sparse memory, `vkMapMemory`, flush/invalidate of mapped ranges, index buffers, uniform buffers, or formats other than `B8G8R8A8_UNORM`. There is one queue family, so queue-family ownership transfer is refused rather than implemented. |
| Synchronization | `VkFence` with its two states and its one owner: unsignalled and unused at submit, signalled at completion, refusing reset and destroy while in use. `vkWaitForFences` honours its timeout and is bounded twice so a stalled backend cannot hang the caller. Image memory barriers with layout tracking that is checked at record time against the recording and at submit time against the image, and access/stage scopes that must actually cover the transfer the barrier precedes. | There are no semaphores, events, timeline semaphores, global or buffer memory barriers, multi-submit dependencies, or concurrent queues. Submission on the V3D backend is synchronous: the bounded waits are inside `NeonFrameEnd`, so nothing is genuinely in flight when `vkQueueSubmit` returns. A wait that could be satisfied by another host thread is not implemented and would need reentrant call frames first. |
| Shaders and pipelines | A SPIR-V front end parses a module, validates it against the Vulkan environment and refuses by name everything outside one declared subset: a pass-through vertex shader and a flat or interpolated fragment shader. A V3D emitter turns that subset's plan into the three QPU programs, their uniform streams and a GL shader state record. A pipeline object owns the fixed-function state, the stage interface match and the vertex input layout, and a render pass and framebuffer own the colour attachment. | There is no target-neutral shader IR, no register allocator, no scheduler and no instruction selection - the emitter assigns registers by counting, which is enough for the accepted subset and nothing else. There is no arithmetic in an accepted shader, no control flow, no descriptor set, no sampler, no specialization constant, no pipeline cache, no derivative pipeline, no compute pipeline, no second subpass, no depth attachment and no blending. Internal clear lowering is still not a shader compiler and this is still not one either. |
| Presentation | Pi display code owns HDMI/DSI surfaces, physical/logical rotation, cache/DMA presentation, capture, and V3D console retargeting. | There is no `VkSurfaceKHR`, platform extension, surface capability query, swapchain image set, acquire/present synchronization, present mode, resize/loss handling, or ownership transfer. The board diagnostic presents by copying the finished image onto the shown half of the framebuffer, which is the display layer's own path and not WSI. |
| Driver modules | PMFMOD v1 validates, relocates, zeroes, cache-synchronizes, and records an AArch64 module image in a board-provided arena. | Neither board wires a module arena or file discovery. The engine does not call module probe/init/quiesce entries, bind services, install stable dispatch trampolines, account for in-flight calls, or reload. The Vulkan backend is statically composed, which the layering permits. |

### What the gates prove, and what they do not

| Gate | Result | What it proves |
|---|---|---|
| `Anvil/Graphics/Vulkan/Tests/vulkan_foundation_check.py` | PASS — pinned registry compared, 131 emitted ABI and lifecycle checks over 65,706 interpreted A64 instructions, production boundary in 35,004 | Vocabulary against the pinned `vk.xml`, exact AArch64 layout, and that a build with no backend enumerates no device. Since 2026-09-11 it also regenerates the twenty-four graphics-pipeline structures: every member name, order and type is compared against the registry AND against vk_core_1_0.pbi, so the two transcriptions have to agree |
| `tools/vulkan_resource_check.py` | PASS — 394 independent property checks over 816,892 executed A64 instructions; `--mutate` rejects all 30 plausible mistakes | The resource, layout, fence, retention, submission and error-reporting contracts, executed through the public entry points, with an MMIO hard stop armed; and that every byte of the bound image still held its poison, so no processor-side clear exists anywhere in the path |
| `tools/vulkan_v3d_backend_check.py` | PASS — 51 property checks over 69,676 executed A64 instructions; `--mutate` rejects all 4 desk-reachable mistakes and names 2 board-only rules it cannot reach | That the whole closure links against the real display, V3D, QPU and Neon implementation, that a build with the engine down enumerates no device, and that reaching that answer makes not one MMIO access |
| `tools/vulkan_spirv_check.py` | PASS — 275 property checks over 3,276,684 executed A64 instructions; `--mutate` rejects all 16 plausible mistakes | That 38 SPIR-V modules, assembled word by word IN THE CHECKER from the specification's own opcode numbers, are walked correctly: 5 inside the subset are lowered to a plan whose every field is checked, and 33 outside it are refused with a whole sentence naming the opcode, capability, decoration, built-in or storage class. The front end makes no MMIO access and does not write one byte of the module it was handed |
| `tools/vulkan_pipeline_check.py` | PASS — 76 property checks over 5,520,714 executed A64 instructions; `--mutate` rejects all 23 plausible mistakes | That the whole public path from `vkCreateShaderModule` to `vkQueueSubmit` reaches the backend with the right numbers, that eight recording and creation rules refuse what they say they refuse, and that every byte of two compiled pipelines' shader records, attribute records, uniform streams and default attribute values matches a record the checker packs itself from the documented V3D field layout. It also compares the board diagnostic's own hand-assembled SPIR-V modules, word for word, against the checker's. No pixel of the render target is written and no MMIO access is made |

None of these desk gates prove GPU execution, displayed output, concurrency,
memory visibility, WSI, shader correctness or conformance. Only the board
diagnostic can, and as of run 3 it has proved exactly one of them: execution of
a clear. **Nothing in the graphics pipeline below has run on silicon yet** —
board run 4 is requested and not taken.

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
  device and a hang.
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

**2026-09-11, run 5 — REQUESTED, NOT TAKEN.**
`RaspberryPi4/Examples/Diagnostics/vulkanTriangleProof.pi4` is built and waiting
for a board slot. It assembles four SPIR-V modules in the payload, creates two
graphics pipelines through the public entry points, and renders one triangle
into an 800x1280 `VK_FORMAT_B8G8R8A8_UNORM` image twice: once with a
push-constant colour and once with a four-component colour carried through the
VPM as a varying. Each pass has its own verdict and each reads back three pixels
inside the triangle and three outside it.

Until that run happens, the honest summary of the graphics pipeline is: the
SPIR-V subset, its refusals and its lowering are proved at a desk; the shader
record, the attribute records and the uniform streams are proved byte for byte
against an independent packer at a desk; and **not one QPU instruction this
emitter produces has been executed by hardware.** Three things in particular are
board-only and are named so they are not mistaken for settled:

- **`FTOIN`.** The viewport transform's rounding is the one instruction family
  in an emitted program that neither of this tree's silicon-proven Neon shaders
  uses. The `FMUL` beside it is proven, by the textured shader's modulate.
- **The VPM output segment size.** The documented rule is `align(n,8)/8`
  sectors; the one silicon-proven shape that carries varyings uses one more than
  that, so the emitter adds a sector whenever there are varyings. Over-declaring
  costs VPM space and under-declaring corrupts vertices, and only the board can
  say which side of that line the rule is on.
- **The varying path.** `LDVARY` + delay + `FADD` against `r5`, with the
  non-perspective flag packet, is the shape the textured shader proves for two
  varyings; four of them, driven by a SPIR-V plan, is not the same run. The
  diagnostic's second pass gives all three vertices the SAME colour on purpose,
  so its expected pixel is exact whatever the interpolator's precision is: it is
  a proof of the path and not of interpolation. A gradient is still owed.


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
   **Pipeline layouts without descriptors, one render pass, the fixed-function
   state listed above and the QPU lowering are done (2026-09-11); descriptors
   are not, and the independent decoder is partial** - the checker packs the
   shader record and the attribute records independently and compares bytes, but
   it does not decode QPU instructions. What it can say about the programs is
   their length and their no-op structure, both predicted from the emission
   rules, and that is weaker than a decoder.
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
