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
detailed gap list. This file says what each of the four coverage classes
currently amounts to and where the files are.

## The files

| File | What it owns |
|---|---|
| `vk_core_1_0.pbi` | Registry-derived vocabulary: constants and 71 naturally aligned AArch64 C-layout structures with the registry's own member names, order and widths. `VkPhysicalDeviceFeatures` is complete even though every member currently reports false; `VkFormatProperties`, `VkImageFormatProperties`, `VkSamplerCreateInfo`, `VkSemaphoreCreateInfo` and `VkPipelineDynamicStateCreateInfo` are exact and carry only proven state. |
| `vk_foundation.pbi` | Handles, generations, parents; instance, physical device, device, queue, command pool and command buffer tables; the validation-fault record; the backend seam's declarations. |
| `vk_memory.pbi` | `VkDeviceMemory` and `VkImage`: the device heap, first-fit suballocation with real reuse, one checked host mapping per host-visible allocation, memory requirements, binding rules, linear and bounded optimal image plans, image usages including `COLOR_ATTACHMENT`, layout and queue-family ownership. |
| `vk_sync.pbi` | `VkFence`: two states, one owner while in use, reset and destroy refusals. |
| `vk_semaphore.pbi` | Core-1.0 binary semaphore lifetime and ordered transaction state: generation owners, reserve/commit/complete/rollback, one-signal consumption, pending references and atomic device teardown. There is no timeline behavior or host signal/reset operation. |
| `vk_command.pbi` | The recorded command stream, layout and dynamic-scissor tracking across a recording, generation-tagged resource retention, submission, completion, and bounded finite host waits. It owns multi-region, ordered `vkCmdCopyBuffer` transactions and the one-region whole-image `vkCmdCopyBufferToImage` transaction. The flight ticket publishes or rolls back binary semaphore state only at real immediate or polled completion. An already-satisfied `UINT64_MAX` wait succeeds; an unsatisfied one is explicitly withheld until host calls are reentrant. |
| `vk_api.pbi` | The public `vk*` entry points and their validation. |
| `vk_backend_none.pbi` | The absent backend: no device is enumerated. UNO Q and any Pi build without V3D link this. |
| `vk_backend_test.pbi` | The explicit test backend: state and a call log, **no GPU and no pixels ever written**. |
| `vk_descriptor.pbi` | `VkDescriptorSetLayout`, `VkDescriptorPool` and `VkDescriptorSet` for dense one- or two-binding schemas containing uniform buffers, bounded combined image samplers, or one of each. Pools sum duplicate input rows into checked per-type capacities; allocation, copied immutable schemas, independent writes and live resolution into closed backend records are transactional. |
| `vk_interp_expect.pbi` | What an interpolated varying must be at a named pixel, in exact integers. Target neutral, no floating point, and no hardware. |
| `vk_v3d_shader.pi4` | The Pi 4 QPU emitter for the accepted shader plans, including the V3D 4.2 TMU general vec4 load used by a uniform-buffer descriptor and the bounded combined-sampler texture request. BGRA8 sampling uses the format table's Z,Y,X,W logical swizzle; identity swizzle is a measured red/blue reversal, not an alternative. |
| `vk_v3d_backend.pi4` | The real Pi 4 backend: validated clears and ordered draw lists lowered to one V3D bin/render transaction through Neon, including transition-cached per-draw `CLIP_WINDOW`, blend and varying state; plus the bounded raster-to-`UIF_NO_XOR` optimal-image copy lowered to the TFU. Mapped ranges are validated/coalesced and handed to the V3D cache owner as one barrier batch. |
| `vk_v3d_texture.pi4` | The Pi 4 owner of an exact raw-four-byte TFU copy from raster staging to level-zero `UIF_NO_XOR`, now reached only through the validated Vulkan buffer-to-image command record. |

Exactly one backend file is linked per program. There is no run-time
registration, so a build with none fails to link and a build with two fails to
compile — neither can silently enumerate the wrong thing.

## Four distinct coverage classes

| Class | Current coverage |
|---|---|
| Generated vocabulary | A pinned core-1.0 generator exists. The checked-in slice contains the exact result, structure-type, command-lifecycle, image, format-feature, memory, queue-family, access, stage, aspect, fence and binary-semaphore values this implementation uses, plus 71 scalar, nested, fixed-array, structure-array and pointer-bearing structures. The complete ABI inventory reports 114 of 281 declaration categories present: 31 enums, 12 bitmasks and 71 structures; 165 are missing and two unions are deliberately unrepresentable. It is not the complete 1.0 vocabulary. `VkPhysicalDeviceFeatures` carries all 55 core feature members; every member is currently false. `VkClearColorValue` is a union and is deliberately **not** declared, because PureMetal has no union and one arm of it posing as the whole type is the silent wrong answer this project refuses. |
| Semantic implementation | Opaque typed and generation-tagged handles including binary semaphores; instance, physical device, device and one queue that always advertises transfer and advertises graphics exactly when its backend owns the draw capability; exact format/image-format answers for implemented linear BGRA8 and the bounded optimal sampled/transfer-destination combination; device memory plus linear and optimal `B8G8R8A8_UNORM` images with exact requirements, binding, usage and layout; one active checked host mapping; whole-image clears and one tightly packed whole-image buffer-to-image copy with live-resource revalidation and retention; destination layout publication only after copy success; binary semaphore waits/signals and fences with bounded waits; one-sample-mask suppression; a bounded sampler; immutable copied descriptor schemas with independent per-type pool accounting; a mixed uniform-buffer plus combined-image-sampler set; ordered lists up to 4,096 draws; exact disabled/source-over blend; and static or public per-draw dynamic scissor. Every refusal is a real code and a whole sentence naming it and the next thing to check. |
| Explicit test backend | `vk_backend_test.pbi` models one device over a caller-supplied window. It records the exact clear it was asked for — address, extent, pitch, colour word — and **writes nothing**, so a gate can then read the image back and require that every poisoned byte survived. It can hold a submission outstanding or fail a later poll once, making pending semaphore/fence/resource ownership and both completion and rollback reachable from a desk. |
| V3D execution | `vk_v3d_backend.pi4` lowers whole-image clears and accepted graphics draw lists through transactional Neon/V3D bin-render jobs, and lowers the bounded optimal buffer-to-image copy through a real TFU job. A draw list uses one bin/render pair, normalizes each snapshotted scissor without overflow, emits `CLIP_WINDOW` only when it changes, and performs all coalesced cache-range maintenance under one final barrier. There is no processor or DMA image fallback in rendering; presentation is a separate display-owner DMA operation. The 2026-09-13 4x4 proof copied raster BGRA8 into `UIF_NO_XOR`, then sampled it. The 2026-09-16 six-draw proof executed one bin/render pair and one DMA presentation. The final 8x8 atlas/chrome Pi 4 run returned exact `x0=0x6C85A0`, recorded one TFU advance, one bin/render pair and one display-DMA presentation, passed 211 exact report/pixel checks and produced a clean rotated 800x1280 screenshot. |

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
It has no processor pixel fallback. The immediate remaining acceptance is the
bounded Pi 4 run and screenshot of that exact scene, followed by fans/lines and
HDMI/DSI/rotation/resize coverage. After that, the broader backend stages are
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
