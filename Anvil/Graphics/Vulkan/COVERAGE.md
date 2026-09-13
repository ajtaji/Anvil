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
| `vk_core_1_0.pbi` | Registry-derived vocabulary: constants and 67 naturally aligned AArch64 C-layout structures with the registry's own member names, order and widths. `VkPhysicalDeviceFeatures` is complete even though every member currently reports false; `VkFormatProperties`, `VkImageFormatProperties` and `VkSamplerCreateInfo` are exact and carry only proven format, image and sampler state. |
| `vk_foundation.pbi` | Handles, generations, parents; instance, physical device, device, queue, command pool and command buffer tables; the validation-fault record; the backend seam's declarations. |
| `vk_memory.pbi` | `VkDeviceMemory` and `VkImage`: the device heap, first-fit suballocation with real reuse, one checked host mapping per host-visible allocation, memory requirements, binding rules, image usages including `COLOR_ATTACHMENT`, layout and queue-family ownership. |
| `vk_sync.pbi` | `VkFence`: two states, one owner while in use, reset and destroy refusals. |
| `vk_command.pbi` | The recorded command stream, layout tracking across a recording, resource retention, submission, completion, and bounded finite host waits. An already-satisfied `UINT64_MAX` wait succeeds; an unsatisfied one is explicitly withheld until host calls are reentrant. |
| `vk_api.pbi` | The public `vk*` entry points and their validation. |
| `vk_backend_none.pbi` | The absent backend: no device is enumerated. UNO Q and any Pi build without V3D link this. |
| `vk_backend_test.pbi` | The explicit test backend: state and a call log, **no GPU and no pixels ever written**. |
| `vk_descriptor.pbi` | `VkDescriptorSetLayout`, `VkDescriptorPool` and `VkDescriptorSet` for one descriptor type, and what a bound set resolves to at submit time. |
| `vk_interp_expect.pbi` | What an interpolated varying must be at a named pixel, in exact integers. Target neutral, no floating point, and no hardware. |
| `vk_v3d_shader.pi4` | The Pi 4 QPU emitter for the accepted shader plans, including the V3D 4.2 TMU general vec4 load used by a uniform-buffer descriptor. |
| `vk_v3d_backend.pi4` | The real Pi 4 backend: validated clears and draws lowered to V3D bin and render control lists through Neon, with mapped-range and cache-visibility rules for GPU-read buffers. |

Exactly one backend file is linked per program. There is no run-time
registration, so a build with none fails to link and a build with two fails to
compile — neither can silently enumerate the wrong thing.

## Four distinct coverage classes

| Class | Current coverage |
|---|---|
| Generated vocabulary | A pinned core-1.0 generator exists. The checked-in slice contains the exact result, structure-type, command-lifecycle, image, format-feature, memory, queue-family, access, stage, aspect and fence values this implementation uses, plus 66 scalar, nested, fixed-array, structure-array and pointer-bearing structures. It is not the complete 1.0 vocabulary. `VkPhysicalDeviceFeatures` carries all 55 core feature members; every member is currently false. `VkClearColorValue` is a union and is deliberately **not** declared, because PureMetal has no union and one arm of it posing as the whole type is the silent wrong answer this project refuses. |
| Semantic implementation | Opaque typed and generation-tagged handles for ten object types; instance, physical device, device and one queue that always advertises transfer and advertises graphics exactly when its backend owns the draw capability; exact `vkGetPhysicalDeviceFormatProperties` and `vkGetPhysicalDeviceImageFormatProperties` answers for the implemented linear BGRA8 combinations, with geometry, pitch-derived resource size, one mip/layer/sample and every unsupported field refused; device memory and linear `B8G8R8A8_UNORM` images with exact requirements, binding rules, usage and per-image layout; one active `vkMapMemory` range for host-visible allocations with exact/whole-range and owner checks; framebuffer colour attachments must carry `COLOR_ATTACHMENT`; image memory barriers track layouts; whole-image clears retain resources through submission; fences have a bounded finite wait and explicitly refuse an unsatisfied `UINT64_MAX`; one-sample masks suppress primitive emission without suppressing a render-pass clear; and a bounded, device-owned `VkSampler` object accepts only the state the first texture lowering is intended to consume. Every refusal is a real code and a whole sentence naming it and the next thing to check. |
| Explicit test backend | `vk_backend_test.pbi` models one device over a caller-supplied window. It records the exact clear it was asked for — address, extent, pitch, colour word — and **writes nothing**, so a gate can then read the image back and require that every poisoned byte survived. It can hold a submission outstanding, which is what makes the pending state, the fence state machine and the retention rules reachable from a desk. |
| V3D execution | `vk_v3d_backend.pi4` lowers whole-image clears and the accepted graphics draws through transactional `NeonRebindSurface` + `NeonFrameBegin` + `NeonFrameEnd`, the real bin/render submit-and-wait path with V3D and processor-side cache maintenance. There is no processor-side and no DMA image fallback under it. Board runs 2 and 3 proved the original clear and its live refusal boundary; the 2026-09-13 dynamic-geometry run proved 800x1280, 640x360, partial-tile 257x193, the 1280 scalar capacity boundary, exact display-state restoration and a subsequent ordinary frame. Board run 5 proved one graphics pipeline and its varying path. The 2026-09-13 clean-state descriptor run proved the uniform-buffer TMU lookup, interpolated varying, second vertex binding, cache visibility and three consecutive jobs on Pi 4 silicon. |

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
`VkPhysicalDeviceMemoryProperties` (`memoryHeaps` at 264, size 520), and
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
lowers what is left to a small plan. `vk_v3d_shader.pi4` turns that plan into
three QPU programs, their uniform streams and a GL shader state record.
`vk_pipeline.pbi` adds buffers, shader modules, pipeline layouts, render passes,
image views, framebuffers, graphics pipelines and the render-pass recording
commands. `docs/VULKAN_COMPATIBILITY_STATUS.md` has the entry-point table, the
fixed-function state a pipeline may declare and the gate results.

**Board run 5, 2026-09-11, PASSED**: both triangles rendered, every pixel probe
exact, and the picture was presented. That is one uniform-colour triangle and
one triangle whose three vertices carried the SAME colour through the varying
path - a proof of the path and not of interpolation.

It is an EMITTER and not a compiler: no target-neutral IR, no register
allocator, no scheduler, no instruction selection, and no arithmetic in an
accepted shader. The refusals are what keeps that honest.

## 2026-09-11, the same evening: varyings, a second binding, descriptors

Three things followed the triangle, each with its own desk gate and its own
question on the board:

| File | What it owns |
|---|---|
| `vk_interp_expect.pbi` | What an interpolated varying MUST be at a named pixel: the clip-to-screen transform, the pixel-centre sample point, the three edge functions, the weighted average and the 8-bit UNORM rounding, all in exact integers with no floating point. `tools/vulkan_interp_check.py` runs it against a second implementation of the same rule written in Python. |
| `vk_descriptor.pbi` | `VkDescriptorSetLayout`, `VkDescriptorPool` and `VkDescriptorSet` for one descriptor type - `VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER` - with every other type refused by its own name, and the resolution of a bound set into one address and one length at submit time. |

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

## Next real backend layers

The next stages are per-object GPU virtual addressing and residency above
today's single window, arithmetic in the shader front end and the typed IR that
needs, sampled-image descriptors and texture-fetch lowering that consume the
new sampler object, broader immutable pipeline state, command lowering into V3D
bin/render jobs with dependencies, interrupt-driven completion so submission is
genuinely asynchronous, and then WSI against Anvil's existing HDMI/DSI present
seam.
Mesa's V3D documentation is a semantic and hardware reference, not a Linux
runtime dependency and not a source of code. Passing the Khronos CTS and
claiming a Vulkan version come only after those capabilities exist and are
tested.
