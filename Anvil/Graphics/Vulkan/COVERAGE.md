# Anvil Vulkan foundation coverage

The schema compatibility target is Vulkan 1.0. It is not an implementation or
conformance claim. Vocabulary is derived from the official Khronos
`Vulkan-Headers` tag `v1.4.350`, commit
`a33416ed2ce6bf8ef48b4eda821825f66d1850d3`. The raw
`registry/vk.xml` SHA-256 is
`50BD8C0F316EABF73D1C5FE3ADD2D89EAA480DBDA9282C12C289E80E9D081E08`.
The registry is dual licensed Apache-2.0 OR MIT.

`../../../docs/VULKAN_COMPATIBILITY_STATUS.md` holds the authoritative
entry-point table and the cross-layer inventory. `ROADMAP.md` holds the
detailed gap list. The board/backend capability matrix is in
`../../../docs/VULKAN_BOARD_BACKENDS.md`. This file says what each of the
four coverage classes
currently amounts to and where the files are.

## The files

| File | What it owns |
|---|---|
| `vk_core_1_0.pbi` | Registry-derived vocabulary: constants and 86 naturally aligned AArch64 C-layout structures with the registry's own member names, order and widths. `VkPhysicalDeviceFeatures` is complete even though every member currently reports false; `VkFormatProperties`, `VkImageFormatProperties`, `VkSamplerCreateInfo`, `VkSemaphoreCreateInfo`, `VkClearAttachment`, `VkClearRect`, `VkImageCopy` and `VkPipelineDynamicStateCreateInfo` carry only proven state. |
| `vk_foundation.pbi` | Handles, generations, parents; instance, physical device, device, queue, command pool and command buffer tables; the validation-fault record; the backend seam's declarations. |
| `vk_memory.pbi` | `VkDeviceMemory` and `VkImage`: the device heap, first-fit suballocation with real reuse, one checked host mapping per host-visible allocation, memory requirements, binding rules, linear and bounded optimal image plans, image usages including `COLOR_ATTACHMENT`, layout and queue-family ownership. |
| `vk_sync.pbi` | `VkFence`: two states, one owner while in use, reset and destroy refusals. |
| `vk_semaphore.pbi` | Core-1.0 binary semaphore lifetime and ordered transaction state: generation owners, reserve/commit/complete/rollback, one-signal consumption, pending references and atomic device teardown. There is no timeline behavior or host signal/reset operation. |
| `vk_command.pbi` | The recorded command stream, layout and dynamic-scissor tracking across a recording, generation-tagged resource retention, submission, completion, and bounded finite host waits. It owns multi-region `vkCmdCopyBuffer` and ordered `vkCmdFillBuffer` / `vkCmdUpdateBuffer` transactions, the one-region whole optimal-image TFU or bounded multi-region rectangular strided linear-image DMA `vkCmdCopyBufferToImage` transaction, and bounded multi-region rectangular linear-image `vkCmdCopyImage` / strided `vkCmdCopyImageToBuffer` transactions lowered through guarded DMA on Pi 4, plus full linear-to-optimal or optimal-to-optimal `vkCmdCopyImage` regions lowered through TFU. A bounded partial optimal-image `vkCmdCopyBufferToImage` route accepts up to two separate one-region calls per command buffer into the same optimal BGRA8 image. Each region has a 64-byte-aligned buffer offset, tight or padded source pitch with exact last-row span, 4×4-aligned destination offsets and extents, and at most 256 utiles; the combined tile count is at most 256. Destination rectangles and source byte spans must be disjoint. The entire stream is preflighted before guarded DMA dispatch, and calls execute in recorded order behind a dedicated buffer-to-tiled capability. Desk checks prove 257 combined tiles are refused before backend work; exactly 256 combined tiles have not been separately tested. The 2026-09-30 Pi 4 proof replaced 32 destination texels and preserved 224; it checked 288 source words including 48 source-padding words, 64 readback-padding words and 128 guard words. TFU stayed at 1, DMA advanced 0→2 and jobs 1→3; a later readback advanced DMA 2→18. A misaligned second operation returned `-20005` during recording, before submit or DMA. MMU, OOM and native fault counts were zero, with one intentional validation fault. See `docs/evidence/vulkan-two-partial-optimal-uploads-pi4-20260930/README.md`. The complete-image TFU upload remains unchanged, and other boards do not advertise this capability. Edge-tail extension: destination XY remains 4-aligned; a width or height not divisible by four is accepted only when that rectangle reaches the matching image right or bottom edge. The backend clamps each 4×4 UIF tile to its valid columns and rows, issuing guarded DMA for only `validColumns * 4` bytes across `validRows`; this preserves neighboring texels and padded storage. It requires both `BUFFER_TO_TILED_RECT_COPY` and the separate `BUFFER_TO_TILED_TAIL_COPY` capability. Up to two calls remain allowed, with disjoint rectangles and source spans and a cumulative limit of 256 `ceil(width/4) * ceil(height/4)` tiles. Source bounds remain `(height - 1) * pitch + width * 4`, with DMA row-skip bounds checked for the smallest tail row. The complete stream and every tile address/span are preflighted before DMA. Full-image TFU uploads remain unchanged; other boards fail closed. The 2026-09-30 Pi 4 proof changed 25 texels, left 196 valid texels untouched, and preserved 291 padded UIF backing words outside the copy. It checked 246 source words including 54 source-padding words, 91 readback-padding words and 92 guards. TFU stayed at 1, DMA advanced 0→4 and jobs 1→2; later readback advanced DMA 4→24. A non-edge 5×5 request returned `-20005` during recording before more DMA. MMU, OOM and native faults were zero, with one intentional validation fault. Submit-time malformed-stream preflight remains desk-gate evidence. See `docs/evidence/vulkan-optimal-upload-edge-tail-pi4-20260930/README.md`. A separate two-call Pi 4 proof used a 13×13 target: 17 texels changed, 152 valid texels remained unchanged, and 343 padded UIF backing words outside the copies were preserved. It checked 186 source words including 58 source-padding words, 39 readback-padding words and 112 guards. TFU stayed at 1, DMA advanced 0→2 and jobs 1→3; later readback advanced DMA 2→18. A non-edge second call returned `-20005` during recording before DMA. Submit-time malformed-second preflight is proven by signed desk regression only. See `docs/evidence/vulkan-optimal-upload-edge-tail-pi4-20260930/README.md` (`two-call-report.bin`). A bounded partial linear-to-optimal region is implemented separately from the full-image TFU path: one region per command buffer between distinct equal-size level-zero BGRA8 images, arbitrary in-bounds linear source offsets using the actual source pitch, and 4×4-utile-aligned optimal destination offsets and extents, capped at 256 utiles. It uses guarded DMA behind a dedicated capability. The 2026-09-30 Pi 4 proof copied 16 exact texels, preserved 240 untouched texels, matched all 256 source texels, and passed 64 padding and 96 guard checks. TFU stayed at 1, DMA advanced 0→1 and backend jobs 1→2; a later readback advanced DMA 1→17. A misaligned destination returned `-20005` before readback. MMU, OOM and native fault counts were zero, with one intentional validation fault. See `docs/evidence/vulkan-partial-linear-optimal-pi4-20260930/README.md`. Other boards do not advertise this capability. One-utile micro upload: a separate guarded-DMA shape accepts a 1–4 by 1–4 BGRA8 rectangle wholly contained in one 4×4 UIF utile, including an unaligned interior pixel origin. It writes only the requested row bytes and rows, preserving the other texels in that utile. It requires both `BUFFER_TO_TILED_RECT_COPY` and `BUFFER_TO_TILED_MICRO_COPY`; a micro upload is isolated from other buffer-to-image operations in its command buffer. Buffer offsets remain 64-byte aligned, source bounds use `(height - 1) * pitch + width * 4`, and source/image alias, row-stride, utile and guarded-window bounds are preflighted before DMA. Other boards do not advertise this capability. The 2026-09-30 Pi 4 proof changed six requested texels and preserved 250, including ten same-utile neighbors; checks covered 272 source words (262 payload and ten padding words), 64 readback-padding words and 96 guards. TFU stayed at 1, DMA advanced 0→1 and jobs 1→2. A crossing-utile request returned `-20005` during recording. MMU, OOM and native fault counts were zero. See `docs/evidence/vulkan-buffer-optimal-microrect-pi4-20260930/README.md`. Submit-time malformed-stream preflight remains desk-gate evidence. A bounded partial optimal-to-optimal region is implemented for distinct equal-size level-zero BGRA8 UIF images: at most one region per command buffer, four-texel-aligned source and destination offsets and extents, and at most 256 4×4 utiles. The Pi 4 path uses guarded DMA behind its dedicated tiled-rectangle capability. The 2026-09-30 Pi 4 proof copied 16 exact texels, preserved 240 untouched texels, and passed 64 padding and 96 guard checks. TFU remained at 2, DMA advanced 0→1, and backend jobs advanced 2→3. A later full readback advanced DMA 1→17. An unaligned request returned `-20005` without extra transfer work; MMU, OOM and native fault counts were zero, with one intentional validation fault. See ``docs/evidence/vulkan-partial-optimal-copy-pi4-20260930/README.md`. The complete-image TFU path is unchanged. A bounded optimal-to-linear `vkCmdCopyImage` partial-region path is implemented for distinct equal-size level-zero BGRA8 images: source offsets are 4×4-utile aligned, and width/height tails are allowed only at the corresponding source edge. Pi 4 silicon passed a 5×5 right-and-bottom edge-tail copy with exact texels, intact guards, four DMA operations and a no-work refusal for a non-edge tail; see `docs/evidence/vulkan-partial-optimal-linear-pi4-20260930/README.md`. Each accepted linear image-copy, upload or readback call may hold up to 32 regions; its complete array is preflighted before any DMA transfer. The two-region linear upload passed on Pi 4 with eight guarded DMA rows and exact whole-image bytes; see `docs/VULKAN_IMAGE_UPLOAD_ARRAY_DMA_PI4_2026-09-27.md`. Two separate linear upload calls also passed in one command buffer with eight DMA rows and an exact 1,024-pixel destination check (`docs/VULKAN_MULTI_CALL_UPLOAD_DMA_PI4_2026-09-27.md`). Two separate linear `vkCmdCopyImage` calls also passed in one command buffer with eight DMA rows; see `docs/VULKAN_MULTI_CALL_IMAGE_DMA_PI4_2026-09-27.md`. Separate linear image-to-buffer readback calls execute in recorded order through guarded DMA; two disjoint calls passed on Pi 4 with eight DMA rows and an exact 16,512-byte destination check (`docs/VULKAN_MULTI_CALL_READBACK_DMA_PI4_2026-09-27.md`). Supported buffer copies, fills and updates can interleave with buffer-to-image uploads, image-to-image copies and linear image readbacks in one transfer-only command buffer; a Pi 4 DMA staging update fed two ordered TFU jobs and V3D sampled the fresh result (`docs/VULKAN_DMA_TFU_STREAM_PI4_2026-09-27.md`). A Pi 4 upload/barrier/readback stream passed with two guarded DMA operations and exact 64-byte results (`docs/VULKAN_MIXED_READBACK_DMA_PI4_2026-09-27.md`). All calls are preflighted before the first TFU or DMA job; a Pi 4 run sampled the fresh destination of an ordered upload and image copy with a distinct staging texel (`docs/VULKAN_MIXED_IMAGE_TFU_PI4_2026-09-27.md`). The flight ticket publishes or rolls back binary semaphore state only at real immediate or polled completion. An already-satisfied `UINT64_MAX` wait succeeds; an unsatisfied one is explicitly withheld until host calls are reentrant. |
| `vk_api.pbi` | The public `vk*` entry points and their validation, including one bounded color `vkCmdClearAttachments` rectangle in a render pass; Pi 4 supports partial rectangles on even-sized framebuffers. |
| `vk_backend_none.pbi` | The absent backend: no device is enumerated. A target without a GPU backend can link this; whether a board monitor includes Vulkan is determined by that board's composition root. |
| `vk_backend_test.pbi` | The explicit test backend: state and a call log, **no GPU and no pixels ever written**. |
| `vk_descriptor.pbi` | `VkDescriptorSetLayout`, `VkDescriptorPool` and `VkDescriptorSet` for dense one- or two-binding schemas containing uniform buffers, bounded combined image samplers, or one of each. Pools sum duplicate input rows into checked per-type capacities; allocation, copied immutable schemas, independent writes and live resolution into closed backend records are transactional. |
| `vk_interp_expect.pbi` | What an interpolated varying must be at a named pixel, in exact integers. Target neutral, no floating point, and no hardware. |
| `vk_v3d_shader.pi4` | The Pi 4 QPU emitter for the accepted shader plans, including the V3D 4.2 TMU general vec4 load used by a uniform-buffer descriptor and the bounded combined-sampler texture request. BGRA8 sampling uses the format table's Z,Y,X,W logical swizzle; identity swizzle is a measured red/blue reversal, not an alternative. |
| `vk_v3d_backend.pi4` | The real Pi 4 backend: validated full clears, bounded partial attachment clears and ordered draw lists lowered to one V3D bin/render transaction through Neon, including transition-cached per-draw `CLIP_WINDOW`, blend and varying state; bounded raster-to-`UIF_NO_XOR` uploads, linear-to-optimal image copies, and `UIF_NO_XOR`-to-`UIF_NO_XOR` whole-image copies lowered to the TFU; and buffer copies/fills/updates plus linear image copies/readbacks through guarded DMA. Its bounded optimal-to-linear partial `vkCmdCopyImage` detile path passed the 5×5 edge-tail Pi 4 proof; see `docs/evidence/vulkan-partial-optimal-linear-pi4-20260930/README.md`. A composition without DMA refuses those transfers rather than copying pixels on the CPU. Mapped ranges are validated/coalesced and handed to the V3D cache manager as one barrier batch. Partial attachment clears require even framebuffer dimensions; the full pre-draw load-clear path supports odd dimensions. |
| `vk_v3d_texture.pi4` | The Pi 4 backend implements exact raw-four-byte TFU copies from raster staging or a level-zero `UIF_NO_XOR` source to a level-zero `UIF_NO_XOR` destination, reached through validated Vulkan image-transfer commands, including whole linear-to-optimal `vkCmdCopyImage`. The separate bounded optimal-to-optimal partial path uses guarded DMA. The 2026-09-30 Pi 4 proof matched all 16 copied texels, preserved 240 untouched texels, and passed 64 padding and 96 guard checks. TFU stayed at 2, DMA advanced 0→1 and backend jobs 2→3; a later full readback advanced DMA 1→17. An unaligned request returned `-20005` without extra transfer work. See ``docs/evidence/vulkan-partial-optimal-copy-pi4-20260930/README.md`. |

Exactly one backend file is linked per program. There is no run-time
registration, so a build with none fails to link and a build with two fails to
compile — neither can silently enumerate the wrong thing.

## Four distinct coverage classes

| Class | Current coverage |
|---|---|
| Generated vocabulary | A pinned core-1.0 generator exists. The checked-in slice contains the exact result, structure-type, command-lifecycle, image, format-feature, memory, queue-family, access, stage, aspect, fence and binary-semaphore values this implementation uses, plus 71 scalar, nested, fixed-array, structure-array and pointer-bearing structures. The complete ABI inventory reports 114 of 281 declaration categories present: 31 enums, 12 bitmasks and 71 structures; 165 are missing and two unions are deliberately unrepresentable. It is not the complete 1.0 vocabulary. `VkPhysicalDeviceFeatures` carries all 55 core feature members; every member is currently false. `VkClearColorValue` is a union and is deliberately **not** declared, because PureMetal has no union and one arm of it posing as the whole type is the silent wrong answer this project refuses. |
| Semantic implementation | Opaque typed and generation-tagged handles including binary semaphores; instance, physical device, device and one queue that always advertises transfer and advertises graphics exactly when its backend owns the draw capability; exact format/image-format answers for implemented linear BGRA8 and the bounded optimal sampled/transfer-source/transfer-destination combination; device memory plus linear and optimal `B8G8R8A8_UNORM` images with exact requirements, binding, usage and layout; one active checked host mapping; whole-image clears, a whole optimal-image TFU upload and a rectangular linear-image DMA upload with live-resource revalidation and retention; destination layout publication only after copy success; binary semaphore waits/signals and fences with bounded waits; one-sample-mask suppression; a bounded sampler; immutable copied descriptor schemas with independent per-type pool accounting; a mixed uniform-buffer plus combined-image-sampler set; ordered lists up to 4,096 draws; exact disabled/source-over blend; and static or public per-draw dynamic scissor. Every refusal is a real code and a whole sentence naming it and the next thing to check. |
| Explicit test backend | `vk_backend_test.pbi` models one device over a caller-supplied window. It records the exact clear it was asked for — address, extent, pitch, colour word — and **writes nothing**, so a gate can then read the image back and require that every poisoned byte survived. It can hold a submission outstanding or fail a later poll once, making pending semaphore/fence/resource ownership and both completion and rollback reachable from a desk. |
| V3D execution | `vk_v3d_backend.pi4` lowers whole-image clears and accepted graphics draw lists through transactional Neon/V3D bin-render jobs, and lowers the bounded optimal buffer-to-image copy through a real TFU job. A draw list uses one bin/render pair, normalizes each snapshotted scissor without overflow, emits `CLIP_WINDOW` only when it changes, and performs all coalesced cache-range maintenance under one final barrier. There is no processor or DMA image fallback in rendering; presentation is a separate display-owner DMA operation. The 2026-09-13 4x4 proof copied raster BGRA8 into `UIF_NO_XOR`, then sampled it. The 2026-09-16 six-draw proof executed one bin/render pair and one DMA presentation. The final 8x8 atlas/chrome Pi 4 run returned exact `x0=0x6C85A0`, recorded one TFU advance, one bin/render pair and one display-DMA presentation, passed 211 exact report/pixel checks and produced a clean rotated 800x1280 screenshot. |

The 2026-09-26 Pi 4 RAM proof cleared a 64×64 linear BGRA8 image on V3D,
then copied it into a buffer by guarded DMA through the public
`vkCmdCopyImageToBuffer` command. It returned zero after exact pixel and guard
checks, one bin/render pair, one DMA completion, quiescence and write-bound
restoration; see `docs/VULKAN_IMAGE_READBACK_PI4_2026-09-26.md`. This is a
bounded whole-image silicon result. A later 17×13 rectangular linear readback
passed on silicon with thirteen guarded DMA operations and exact copied/untouched
bytes; see `docs/VULKAN_IMAGE_RECT_READBACK_PI4_2026-09-27.md`.
A two-region readback with a padded destination pitch then passed on Pi 4
silicon with eight guarded DMA rows, exact copied/padding/guard bytes and
fresh capture 48; see `docs/VULKAN_IMAGE_READBACK_ARRAY_DMA_PI4_2026-09-27.md`.
A complete level-zero optimal BGRA8 image can be read into a transfer-destination buffer through guarded 2D DMA with tight or padded rows; the 37×13 Pi 4 run checked all 481 texels, untouched padding and 40 DMA operations. R2 passed a 4×4-aligned partial region (16 texels, 16 padding words, 32 guard words, one DMA) and refused an unaligned region with `-20005`. R3 then passed the right-and-bottom edge region at `(32,8)` with extent `5×5` on the same odd-sized image, checking 25 exact texels, 15 padding words and 32 guard words; a non-edge `(28,4)` region of the same extent returned `-20005` without extra work. Partial offsets remain 4×4-utile aligned; width or height tails may be short only when they reach the corresponding image edge. Mips, layers, format conversion, and other edge shapes remain unsupported. See `docs/VULKAN_OPTIMAL_IMAGE_BUFFER_DMA_PI4_2026-09-27.md` and `docs/evidence/vulkan-optimal-edge-tail-pi4-20260930/README.md`.

The 2026-09-30 Pi 4 clear-rectangle proof executed a 64×64 even-sized target with two draws and two attachment clears in one bin/render transaction. All 4,096 pixels matched exactly, including alpha-zero color `$00FF8000`; the padding mismatch count was zero. The out-of-bounds x=60, width=8 rectangle returned `-20001` before jobs. Partial rectangles are bounded to even framebuffer dimensions; the full pre-draw load clear remains supported on odd-sized targets. See `docs/evidence/vulkan-clear-attachments-pi4-20260930/README.md`.

## Compiler ABI boundary

On AArch64 the public memory ABI is LP64: Vulkan 32-bit scalars align to 4,
64-bit values (`VkDeviceSize` among them), pointers and handles align to 8, and
structures carry C tail padding. Every checked-in public record opts into
`Structure ... Align #PB_Structure_AlignC`; default PureMetal packed layout is
unchanged. Nested members, fixed character arrays and fixed arrays of
structures retain their registry names and extents. The emitted gate checks
sizes and nested `OffsetOf` results, including `VkApplicationInfo` (`pNext` at
byte 8, size 48), `VkSubmitInfo` (size 72), `VkImageCreateInfo` (extent at 28,
`initialLayout` at 80, size 88), `VkImageMemoryBarrier` (`image` at 40,
`subresourceRange` at 48, size 72) and
`VkPhysicalDeviceMemoryProperties` (`memoryHeaps` at 264, size 520),
`VkSemaphoreCreateInfo` (size 24), and
`VkSamplerCreateInfo` (`magFilter` at 20, `addressModeW` at 40,
`unnormalizedCoordinates` at 76, size 80). Hand
padding and flattened substitute members are not used. A compiler that lacks
this explicit layout mode must reject these declarations loudly; it must not
silently use packed layout.

`vkCmdPipelineBarrier` now carries the exact ten-parameter registry signature.
The first eight arguments use `x0`..`x7`; the compiler passes the image-barrier
count and pointer through the aligned AArch64 stack argument area. The former
argument-record surrogate has been removed rather than retained as a second,
divergent API.

## 2026-09-11: the SPIR-V front end and the first graphics pipeline

`vk_spirv.pbi` walks a SPIR-V module, validates it against the Vulkan
environment, refuses by name everything outside one declared subset - a
pass-through vertex shader and a flat or interpolated fragment shader - and
originally lowered what remained to a small plan. That first path produced
three QPU programs, their uniform streams and a GL shader state record.
`vk_pipeline.pbi` adds buffers, shader modules, pipeline layouts, render passes,
image views, framebuffers, graphics pipelines and the render-pass recording
commands. `docs/VULKAN_COMPATIBILITY_STATUS.md` has the entry-point table, the
fixed-function state a pipeline may declare and the gate results.

The bounded UINT32 `vkCmdDrawIndexed` path now has a separate Pi 4 silicon
proof. Its UINT32 bind offset, `firstIndex` byte offset, exact V3D packet,
index guards and presentation report are preserved in
`docs/evidence/vulkan-indexed-uint32-pi4-20261001/README.md`.

**Board run 5, 2026-09-11, PASSED**: both triangles rendered, every pixel probe
exact, and the picture was presented. That is one uniform-colour triangle and
one triangle whose three vertices carried the SAME colour through the varying
path - a proof of the path and not of interpolation.

That statement describes the first 2026-09-11 slice. The current path retains
the verified module as immutable typed SSA IR and lowers straight-line
binary32 `FAdd`/`FMul` graphs to V3D 4.2. It is still bounded: no general
control flow, phi, calls, conversions, optimizer or scheduler are claimed,
and everything outside the declared IR/lowerer contract is refused.

## 2026-09-11, the same evening: varyings, a second binding, descriptors

Three things followed the triangle, each with its own desk gate and its own
question on the board:

| File | What it owns |
|---|---|
| `vk_interp_expect.pbi` | What an interpolated varying MUST be at a named pixel: the clip-to-screen transform, the pixel-centre sample point, the three edge functions, the weighted average and the 8-bit UNORM rounding, all in exact integers with no floating point. `tools/vulkan_interp_check.py` runs it against a second implementation of the same rule written in Python. |
| `vk_descriptor.pbi` | `VkDescriptorSetLayout`, `VkDescriptorPool` and `VkDescriptorSet` for `VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER` and `VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER`, independently or together in a dense two-binding set. Pool capacity is tracked per type and duplicate size rows are summed with overflow checks. Sets and pipeline layouts copy immutable schemas, so destroying or reusing a source layout cannot substitute a new shape. Sampled writes require a live sampler, full live image view, bound `SAMPLED` image and shader-read-only layout; consumption revalidates every handle and current layout before returning closed resource records. |

`vk_pipeline.pbi` gained one to four vertex input bindings, each with its own
stride, and refuses a binding no attribute reads. `vk_v3d_shader.pi4` builds
each attribute record against the address and stride of the binding ITS
attribute names, which is what the hardware always wanted: an attribute record
carries an address and a stride of its own.

As of 2026-09-12 the descriptor address stays in the fragment uniform stream.
The Pi 4 fragment program loads it into `rf8`, then uses the primary
implementations' ADD-side OR-move to write it to `TMUAU`. That same instruction
carries the thread switch while its uniform sideband consumes the V3D 4.2
regular per-quad fragment vec4-load configuration; after the two architectural
delay slots, four `LDTMU` operations read the components. It deliberately does
not also assert `WRTMUC`: that would consume a second stream word and displace
the tile-buffer configuration. The backend proves all
sixteen source bytes are in its mapped window and cleans that range before
submission. `tools/vulkan_pipeline_check.py` independently decodes the raw
eighteen-instruction program and the three-word stream and rejects mutations of
the address, configuration, TMU port, signal and source register.

**All three paths are now proved on Pi 4 silicon.** The 2026-09-13 clean-state
run of `RaspberryPi4/Examples/Diagnostics/vulkanVaryingProof.pi4` rendered the
uniform-buffer colour, the interpolated gradient and the same gradient from two
vertex bindings. Its report captured the submitted descriptor stream in slots
121..123 and required slot 124 to be one, so the result proves both the emitted
bytes and the GPU-side descriptor fetch. The exact payload, report and recovery
rules are recorded in `docs/VULKAN_DESCRIPTOR_TMU_PROOF_2026-09-13.md`.

**The first sampled pixel is also proved, within its declared one-texel
boundary.** Public commit `85c2db8` built a 636,380-byte flat payload with
SHA-256 `46A07A9F7B943F60BD5E3FCAC19E25F510DD2837F8283D6225929DF4C27D051F`;
its 636,508-byte PMF container has SHA-256
`F7E32E54EF59952868859B629EACA64F3D3BDE85C78790353E8EE18DD0146352`.
Monitor build 101 verified the container and inner image, and the returning
report at `$005A6000` had zero A/B/C/D verdicts, zero submit/wait/fault results,
the Z,Y,X,W state word `$00A9C040`, exact inside/outside pixels, step 13 and
both magics. Bin and render jobs moved from 3 to 4. The screenshot was
1280x800 with SHA-256
`B8D535126FFD61C82E194D196C83F24A5B4AFBCDF01936C70D1DD0C20F7902A62`.
That older run remains the measured one-linear-texel boundary. It is now
superseded for optimal images by the 4x4 proof below; larger linear sampled
images remain unsupported.

**A 4x4 optimal sampled image is proved through a real Vulkan transfer.** The
final returning container was 670,884 bytes with SHA-256
`B1989D9D9E70FE5F01D8CD527DE09D987767E525CE30DA58DB0F16125512CF67`;
its 670,756-byte flat image has SHA-256
`3A3FBDF3F71D3A148600CF667352A49BBA5BB989BD76E5D5E016A29C0129243C`.
Monitor build 101 verified the container at `$00500000` and returned the
176-word report at `$005B6090`. The source buffer selected memory type 0 from
the physical memory properties (bits 1, flags 7, one type), the optimal image
required 1,024 padded bytes and exposed no fake row pitch, and submit/wait were
both zero. TFU jobs advanced 0 to 1; bin and render jobs advanced 3 to 4. The
final image layout was `SHADER_READ_ONLY_OPTIMAL`, the texture-state word was
`$00A9C840`, inside probes were exactly green/blue/red, outside probes remained
`$FF3380B2`, and MMU/OOM/native faults were zero. The 1280x800 screenshot pixel
SHA-256 is
`22724024624AF20F645590647A69F4B7B7D9EE16027241B1793BE86D61AD6B0B`;
the PNG file SHA-256 is
`F6552765902480625D7953E98E7A7AFCD45FB3ACE034E32EAD9853623B0C3B03`.

This proof is deliberately bounded: one 2D BGRA8 image, one mip, one layer,
one sample, one tightly packed whole-image region at a 64-byte-aligned source
offset, level-zero `UIF_NO_XOR`, and the current normalized nearest-filter
sampler. Mips, partial regions, row-length overrides, layers, scaling,
conversion, blits and other formats are still refused.

**One fragment now combines a sampled image, push constants and a uniform
buffer on Pi 4 silicon.** On 2026-09-15 monitor build 101 verified and ran the
874,740-byte PMF container with SHA-256
`6405122BD5F7BE41BB79B56CDCB770D0499AA1A7E6E602AAE17C42F7419B9D85`;
the 874,612-byte flat image has SHA-256
`C942FDF52697C80DBC3ACC56850431366C04ADDBAA050FC840ECAC3FB965922A`.
It returned the complete 960-byte report at `$005E7E78` in 9.81 seconds.
All four pass verdicts, submit/wait results, MMU/OOM/native errors, and the
current pre/post-draw validation codes were zero. The deliberately cumulative
validation count stayed 5 before, during and after the mixed draw, proving it
added no fault. The typed lowerer published the exact nine-word stream with
semantic indices push RGBA 4..7, UBO address/config 2/3, texture/sampler 0/1
and TLB 8. Runtime patching placed all nine exact values through those indices;
the UBO address was `$067D3000`, the TMU configuration was `$FFFFFF7C`, and
the texture/sampler/TLB words were `$067DD20F`, `$067DD301`, `$FFFFFFFF`.
TFU, bin and render counters each advanced exactly once. The three inside
pixels were `$FF808000`, `$FF800080`, `$FFFF0000`, the three outside pixels
remained `$FF3380B2`, and all nine retained resource counters returned to zero.
The DMA screenshot was 1280x800 with pixel SHA-256
`D1F98B232832C919E8FC96F4EC1EF8144240063B0BF76B05A3B4DC7C44D51A18`.
This closes only the declared straight-line `sample * push + UBO` subset, not
general SPIR-V, arbitrary descriptors, textures, or expression scheduling.

## 2026-09-16: per-draw clip, atlas/chrome fixture and cache batching

`vkCmdSetScissor` is now public and dispatch-visible. A pipeline may declare
exactly `VK_DYNAMIC_STATE_SCISSOR`; a nonempty draw requires supplied state,
reset clears it, and the draw record owns a copy. The V3D backend safely
intersects signed offsets and unsigned extents with the framebuffer and emits
`CLIP_WINDOW` only when the normalized rectangle changes. Static full-viewport
scissor remains supported.

## 2026-09-17: resize-safe dynamic viewport

`vkCmdSetViewport` is public and dispatch-visible. Pipelines may name the
bounded `VIEWPORT` + `SCISSOR` dynamic-state pair; reset makes both undefined,
and every nonempty draw snapshots one origin-zero positive whole-pixel
viewport. The accepted viewport must equal the active framebuffer geometry,
use depth 0..1 and fit V3D's u14.8 offset field. Fractional, translated,
flipped, partial and multiple viewports remain loud refusals.

For dynamic pipelines the V3D draw slot privately clones only the live CS/VS
uniform words, patches the two viewport-scale words, and points that draw's
shader record at the clones. Control-list scaling and offset packets consume
the same closed draw dimensions. Static pipelines keep immutable CS/VS
uniform addresses. The desk gate covers distinct odd/even viewport scales,
private record pointers, exact cache ranges, immutable pipeline templates and
an atomic 32768-pixel refusal. Fresh Pi silicon proof of a resize/rotation
sequence remains outstanding.

The V3D cache owner now has a begin/range/end batch API. It validates and
aligns each range, retains multiple ranges, and issues one final barrier while
preserving the legacy one-range call. Its emitted gate passes 38 exact checks
over 1,961 interpreted A64 instructions and rejects six hostile mutations.

`vulkanAtlasChromeProof.pi4` combines the already implemented pieces as an
IDE-shaped acceptance scene: an 8x8 optimal atlas transferred by TFU, mixed
sample/push/UBO fragment lowering, UV vertices, exact source-over blend, eight
tinted quads, eight snapshotted scissors, one render pass and one display DMA
presentation. `tools/vulkan_atlas_chrome_acceptance_check.py --self-test`
passes 211 exact source/report/pixel-oracle checks. Its board-proven build is
a 976,956-byte PMF container with SHA-256
`485d21a7c1ddb11b87b36220f8e339bc4cd33eeff696b9577fc754841ee73e9a`.
The corrected build-148 RAM-only run at `0x500000` returned exact
`x0=0x6C85A0` in 10.2 seconds with report slot 128 equal to zero. It recorded
one TFU advance, one bin/render pair and one display-DMA presentation. The
960-byte report SHA-256 is
`d8344fe34b86dde9b4b56fae812d0a61a5514f92caa1fc9dba82d9ac94d43179`;
fresh capture sequence 8 is a 1280x800 PNG representing the rotated 800x1280
target with SHA-256
`f71f38f67389ba2edb41a662402797b93df510931092348ffaee343efa8b0e86`.
The same 211-check oracle passes the board report and raw BGRA capture. The
monitor returned to the build-148 prompt with the deadman explicitly off and no
core leases. No flash, reset or persistent write was used.

The first adapter prerequisite is also complete. `neon.pi4` now exposes a
read-only, font-generation-matched CPU RGBA8 atlas contract through
`Neon_AtlasRasterEnsure`, the ready/base/width/height/byte and glyph-range
queries, `Neon_AtlasRasterGlyphUV`, and the reserved opaque-white sample from
`Neon_AtlasRasterWhiteUV`. The base is borrowed for copying only;
there is no setter, detach, free or private UV-table pointer, and the existing
TFU-built UBLINEAR atlas remains private. Its emitted gate passes 26 source
checks and 41 run-time assertions over 3,118,073 interpreted A64 instructions,
rejects five hostile mutations, and leaves the existing rotation pipeline gate
green.

Because that API and the primitive hook refactor the shared renderer, the exact
current-tree artifact is tracked separately rather than borrowing the earlier
board result: 977,076-byte PMF, SHA-256
`c4b43f94547343ef2b01232a81a549f3444f66b4e29c3d90197a2b887fca147b`,
expected report pointer `0x6C85C8`. It compiles and the atlas/display desk gates
pass, but it has not been sent while another lane owns the shared Pi 4.

## Next real backend layers

`neon_vk_chrome.pi4` now implements the first engine-conversion layer. Its
all-or-none hook keeps the existing widget calls unchanged while persistent
Vulkan resources translate boxes, atlas text and clip operations into ordered
draws. The real-widget scene is desk-proved at 109 quads, 47 draws, 654 vertices
and five scissor states, with one submit and one display-owner present intent.
It has no processor pixel fallback. A current-tree short Pi 4 run passed on
2026-10-01: 109 quads, 47 draws, 654 vertices, 35 box calls, 12 text calls,
74 glyph quads, four expected scissor calls, one display-DMA operation, zero DMA fallback
or refusal, zero pending presentation/backend error, and 12 pixel probes. The
scene defines five scissor states; the diagnostic records four expected set/clear API calls
and does not separately measure unique states. The short run skipped capacity and paired-scene checks and produced no
screenshot; see `docs/evidence/vulkan-neon-widget-short-pi4-20261001/README.md`.
A separate current-tree mode-2 Pi 4 run passed the production fan/outline and
line scenes: both 64×64 BGRA captures matched their native golden segments
byte-for-byte, with 12 report probes passing. The diagnostic copied completed
GPU attachment bytes to RAM for comparison; it did not render pixels on the CPU.
See `docs/evidence/vulkan-neon-fan-line-pi4-20261001/README.md`. The earlier
2026-09-26 all-15-scene proof at commit `a6b9a93` remains historical evidence
for that source. A fresh current-tree all-15-scene run and broader HDMI/DSI/
rotation/resize coverage remain. After that, the broader backend stages are
per-object GPU virtual addressing and residency above
today's single window, arithmetic beyond the current straight-line binary32
`FAdd`/`FMul` typed-IR subset, broader optimal-image shapes and transfer commands beyond the proved
whole-image copy, broader immutable pipeline state, command lowering into V3D
bin/render jobs with dependencies, interrupt-driven completion so submission is
genuinely asynchronous, and then WSI against Anvil's existing HDMI/DSI present
seam.
Mesa's V3D documentation is a semantic and hardware reference, not a Linux
runtime dependency and not a source of code. Passing the Khronos CTS and
claiming a Vulkan version come only after those capabilities exist and are
tested.

### One-utile optimal-to-optimal microcopy

A separate Pi 4 capability copies one 1–4 by 1–4 BGRA8 rectangle between distinct equal-size level-zero optimal images. Source and destination offsets are independent; each rectangle must fit within one 4×4 UIF utile, and each image’s other texels are preserved. The route requires both `TILED_RECT_COPY` and dedicated `TILED_MICRO_COPY`; it is isolated as the sole copy/transfer/draw operation in its command buffer. Shared recording and submit validation recheck capability, resource/layout generations, extents and allocation aliasing before dispatch. Pi 4 lowers only the requested row bytes with guarded DMA at a 16-byte row stride; it does not use CPU pixels or TFU. Other backends fail closed. The 2026-09-30 proof changed four destination texels and preserved 252 (including twelve same-utile neighbors); all 256 source texels remained unchanged. Each readback checked 64 padding words and 128 guards. TFU stayed at 2, DMA advanced 0→1 and jobs 2→3; a source utile-crossing request returned `-20005` during recording. MMU, OOM and native fault counts were zero. See `docs/evidence/vulkan-optimal-optimal-microrect-pi4-20260930/README.md`. Submit-time malformed-stream preflight remains desk-gate evidence.

### One-utile optimal-image buffer readback

A separate Pi 4 DMA capability supports one interior `vkCmdCopyImageToBuffer` region of 1–4 by 1–4 BGRA8 texels, wholly inside one source 4×4 UIF utile. Destination offset remains four-byte aligned; tight or padded rows are checked against the exact last-row span `(height - 1) * pitch + width * 4`. The shared API requires both ordinary linear-transfer support and dedicated `TILED_MICRO_READBACK`; it rejects image/buffer aliasing and verifies capability, resource lifetime, bounds and destination stride before any DMA. The Pi 4 backend reads from the source's independent local UIF offset with guarded DMA; other backends fail closed. The 2026-10-01 proof matched four requested texel words, passed twelve row-padding checks, left all 256 source texels unchanged (including twelve same-utile neighbors), and passed 64 full-readback-padding, 16 stage-spare and 128 guard checks. TFU stayed at 1, DMA advanced 0→1 and jobs 1→2. A crossing-utile request returned `-20005` during recording; MMU, OOM and native faults were zero. See `docs/evidence/vulkan-optimal-buffer-microreadback-pi4-20261001/README.md`. Submit-time malformed-stream preflight remains desk-gate evidence. Other backends do not advertise this capability.

### One-utile optimal-to-linear microcopy

A separate Pi 4 path supports one interior `vkCmdCopyImage` rectangle of 1–4 by 1–4 BGRA8 texels from an optimal source utile to a distinct, equal-size linear destination. The rectangle must fit wholly within one 4×4 UIF utile. It requires `LINEAR_TRANSFER` and the dedicated `TILED_TO_LINEAR_MICRO_COPY` capability; the destination pitch and exact written span are checked, and Pi 4 uses guarded DMA for the requested rows. It does not use CPU pixel copying or TFU. Other backends fail closed. The 2026-10-01 silicon proof changed four destination texels and preserved 252; the source remained unchanged, including twelve same-utile neighbors. Destination pitch was 64 bytes with zero row padding; separate oracle and guard checks covered 64 padded words and 96 guards. DMA advanced 0→1, jobs 1→2, and TFU remained at 1. A crossing-utile request returned `-20005` during recording. Submit-time whole-stream preflight remains desk-gate evidence. See `docs/evidence/vulkan-optimal-linear-microcopy-pi4-20261001/README.md`.

### One-utile linear-to-optimal microcopy

A separate Pi 4 path supports one interior `vkCmdCopyImage` rectangle of 1–4 by 1–4 BGRA8 texels from a linear image into a distinct, equal-size optimal image. The rectangle must fit wholly within one 4×4 UIF utile. It requires `LINEAR_TRANSFER`, `LINEAR_TO_TILED_RECT_COPY`, and the dedicated `LINEAR_TO_TILED_MICRO_COPY` capability; the source uses its actual image pitch and the destination utile window is checked before guarded DMA. It does not use CPU pixels or TFU. Other backends fail closed. The 2026-10-01 proof changed four destination texels and preserved 252, including twelve same-utile neighbors, while all 256 source texels remained unchanged. The 64-byte source pitch had zero row padding; source offset/span were 332/72 bytes and destination UIF offset was 1,316 bytes. Separate checks covered 64 padded oracle words and 96 guards. TFU stayed at 1, DMA advanced 0→1, and jobs 1→2. A crossing-utile request returned `-20005` during recording before DMA. Submit-time whole-stream preflight remains desk-gate evidence. See `docs/evidence/vulkan-linear-optimal-microcopy-pi4-20261001/README.md`.

### Two-by-two UIF grid buffer upload

A separate Pi 4 capability accepts one interior `vkCmdCopyBufferToImage` region into an optimal BGRA8 image when the destination rectangle intersects two adjacent UIF tile columns and two adjacent rows. The shared API requires `BUFFER_TRANSFER`, `LINEAR_TRANSFER`, `BUFFER_TO_TILED_RECT_COPY`, and dedicated `BUFFER_TO_TILED_GRID_COPY`; it retains the 64-byte buffer-offset rule, tight or padded source pitch and exact last-row span. Recording and submit preflight all up to four tile intersections, source spans and destination windows before guarded DMA. This is a single-operation command-buffer shape; other backends fail closed, and the full-image TFU route is unchanged. The 2026-10-01 Pi 4 proof at destination `(3,3)`, extent `5×5`, observed intersections `1×1`, `4×1`, `1×4`, `4×4`; it changed 25 texels and preserved 231, including 39 neighbors within the touched grid. Source checks covered 25 exact words and 327 sentinels, including 15 padding words; separate oracle checks covered 64 padding words and 96 guards. TFU stayed at 1, DMA advanced 0→4 and jobs 1→2; later oracle readback advanced DMA 4→20. The recorded `6×6` refusal was tested with only the original ≤2×2 grid cap, before the extended cap existed. With `BUFFER_TO_TILED_GRID_4X4_COPY` enabled, an otherwise-valid `6×6` region can be admitted; that exact size has not been silicon-tested. MMU, OOM and native fault counts were zero. Submit-time malformed-stream preflight remains desk-gate evidence. See `docs/evidence/vulkan-buffer-optimal-grid-pi4-20261001/README.md`.

### Extended four-by-four UIF grid buffer upload

A distinct Pi 4 capability extends optimal BGRA8 buffer upload to rectangles intersecting three or four adjacent UIF columns or rows, up to four-by-four intersections. It does not widen the existing ≤2×2 `BUFFER_TO_TILED_GRID_COPY` contract: the extension uses `BUFFER_TO_TILED_GRID_4X4_COPY`, tag 4, and the same base `BUFFER_TRANSFER`, `LINEAR_TRANSFER` and `BUFFER_TO_TILED_RECT_COPY` prerequisites. The existing 64-byte buffer offset, tight/padded pitch and exact source span apply. Shared recording and submit validation preflight every intersection and source/destination span before guarded DMA. The Pi 4 DMA-linked backend is the only backend advertising it; others fail closed. The 2026-10-01 proof copied a `9×9` region at `(3,3)` from a buffer with offset 64, row length 12 / pitch 48, and 420-byte source span. Nine row-major intersections were `1×1`, `4×1`, `4×1`, `1×4`, `4×4`, `4×4`, `1×4`, `4×4`, `4×4`. It copied 81 texels and preserved 175, including 63 unchanged texels in the touched 12×12 grid. Source checks covered 81 exact words plus 271 sentinels, including 27 padding words; oracle padding and guards covered 64 and 96 words. TFU stayed at 1, DMA advanced 0→9, jobs 1→2; later full oracle readback advanced DMA 9→25. All status slots/helper and MMU/OOM/native/validation-fault counts were zero. A fifth-row/column refusal and submit-time malformed-stream preflight are desk-gate only. See `docs/evidence/vulkan-buffer-optimal-grid4-pi4-20261001/README.md`.

A separate maximum-boundary Pi 4 proof exercised all sixteen 4×4-grid intersections with one 13×13 buffer upload at `(3,3)` into a 16×16 image. The row-major texel counts were `[1,4,4,4]` followed by `[4,16,16,16]` for each remaining row. It changed 169 texels and preserved 87; buffer offset/pitch/span were 64/64/820 bytes. Checks covered 169 source words, 39 row-padding words, 183 total sentinels, 64 readback-padding words and 96 guards. Partial upload DMA advanced by 16 in one backend job while TFU stayed unchanged; the full-image readback advanced DMA by another 16. Status, MMU, OOM, native and validation-fault counts were zero. The evidence is `docs/evidence/vulkan-buffer-optimal-grid4-max-pi4-20261001/README.md`. This exercises the upper 4×4 boundary on Pi 4 only; other backends remain fail-closed and full-image TFU behavior is unchanged.

### Bounded partial optimal-to-optimal edge-tail copy

The shared `vkCmdCopyImage` API supports one partial region per command buffer between distinct, equal-size level-zero BGRA8 `UIF_NO_XOR` images. Source and destination XY offsets remain 4-texel aligned. Width or height may end with a short UIF tile only when that dimension reaches the right or bottom edge in both images; the ceil-divided tile count is capped at 256. This shape requires `TILED_RECT_COPY` plus the separate `TILED_EDGE_TAIL_COPY` capability. Whole-image copies retain their TFU path, aligned full-utile rectangles retain the rectangle path, and one-utile microcopies retain their separate path. The Pi 4 backend preflights all clamped tile windows and performs guarded DMA for valid texel rows only, preserving source data, untouched destination texels and padded UIF storage. Other backends fail closed.

The 2026-10-01 Pi 4 proof copied a `(8,8)` `5×5` region between distinct 13×13 images: 25 destination texels changed, 144 stayed unchanged, and all 169 source texels were unchanged. The report checked 338 exact staging words plus 78 staging-padding words, 91 readback-padding words in each full readback, and 160 guard checks. TFU stayed at 2, partial DMA advanced 0→4 and jobs 2→3; the oracle readbacks advanced DMA 4→20→36. A non-edge `(4,4)` `5×5` request returned `-20005` during `vkEndCommandBuffer` before further DMA. Status slots were zero; MMU, OOM and native faults were zero, with one intentional validation fault. The measured trace is `docs/evidence/vulkan-optimal-optimal-edge-tail-pi4-20261001/report.bin`; the PMF SHA-256 is `8594C760D6E3206CFDC5DEAE41DBAAF6C0A770EDDA5FB5A369EBC3AA40ED027F`. Right-only `5×4` and bottom-only `4×5` cases have desk validation but no separate silicon proof.
