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
| `vk_core_1_0.pbi` | Registry-derived vocabulary: constants and 29 naturally aligned AArch64 C-layout structures with the registry's own member names, order and widths. |
| `vk_foundation.pbi` | Handles, generations, parents; instance, physical device, device, queue, command pool and command buffer tables; the validation-fault record; the backend seam's declarations. |
| `vk_memory.pbi` | `VkDeviceMemory` and `VkImage`: the device heap, first-fit suballocation with real reuse, memory requirements, binding rules, layout and queue-family ownership. |
| `vk_sync.pbi` | `VkFence`: two states, one owner while in use, reset and destroy refusals. |
| `vk_command.pbi` | The recorded command stream, layout tracking across a recording, resource retention, submission, completion, and the bounded host wait. |
| `vk_api.pbi` | The public `vk*` entry points and their validation. |
| `vk_backend_none.pbi` | The absent backend: no device is enumerated. UNO Q and any Pi build without V3D link this. |
| `vk_backend_test.pbi` | The explicit test backend: state and a call log, **no GPU and no pixels ever written**. |
| `vk_v3d_backend.pi4` | The real Pi 4 backend: one validated clear lowered to the V3D bin and render control lists through Neon. |

Exactly one backend file is linked per program. There is no run-time
registration, so a build with none fails to link and a build with two fails to
compile — neither can silently enumerate the wrong thing.

## Four distinct coverage classes

| Class | Current coverage |
|---|---|
| Generated vocabulary | A pinned core-1.0 generator exists. The checked-in slice contains the exact result, structure-type, command-lifecycle, image, memory, queue-family, access, stage, aspect and fence values this implementation uses, plus 29 scalar, nested, fixed-array, structure-array and pointer-bearing structures. It is not the complete 1.0 vocabulary. `VkClearColorValue` is a union and is deliberately **not** declared, because PureMetal has no union and one arm of it posing as the whole type is the silent wrong answer this project refuses. |
| Semantic implementation | Opaque typed and generation-tagged handles for nine object types; instance, physical device, device and one transfer queue; device memory and linear `B8G8R8A8_UNORM` images with exact requirements, binding rules and per-image layout; image memory barriers with layout tracking checked at record time and again at submit time; whole-image colour clears; one-at-a-time submission with resource retention; fences with the full two-state contract and a doubly bounded host wait. Every refusal is a real code and a whole sentence naming it and the next thing to check. |
| Explicit test backend | `vk_backend_test.pbi` models one device over a caller-supplied window. It records the exact clear it was asked for — address, extent, pitch, colour word — and **writes nothing**, so a gate can then read the image back and require that every poisoned byte survived. It can hold a submission outstanding, which is what makes the pending state, the fence state machine and the retention rules reachable from a desk. |
| V3D execution | `vk_v3d_backend.pi4` lowers one whole-image clear to `NeonRetarget` + `NeonFrameBegin` + `NeonFrameEnd`, which is the real bin/render submit-and-wait path with V3D and processor-side cache maintenance. There is no processor-side and no DMA image fallback under it. It clears only an image at the render geometry `NeonInit` was given, and refuses any other extent at record time. **Execution has no silicon acceptance yet**; the board proof is `RaspberryPi4/Examples/Diagnostics/vulkanClearProof.pi4`. |

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
`VkPhysicalDeviceMemoryProperties` (`memoryHeaps` at 264, size 520). Hand
padding and flattened substitute members are not used. A compiler that lacks
this explicit layout mode must reject these declarations loudly; it must not
silently use packed layout.

> **One command cannot carry its registry signature.** `vkCmdPipelineBarrier`
> takes ten parameters and this backend passes at most eight, in `a0`..`a7`,
> refusing a ninth at compile time. `vkCmdPipelineBarrierArgs` is the same call
> with the nine arguments after the command buffer in one record, in registry
> order and with registry member names. It is named so nobody can mistake it
> for the prototype, and it disappears the day the A64 backend emits stack
> arguments.

## Next real backend layers

The next stages are per-object GPU virtual addressing and residency above
today's single window, SPIR-V validation and native QPU compilation,
descriptors and immutable pipeline state, command lowering into V3D bin/render
jobs with dependencies, interrupt-driven completion so submission is genuinely
asynchronous, and then WSI against Anvil's existing HDMI/DSI present seam.
Mesa's V3D documentation is a semantic and hardware reference, not a Linux
runtime dependency and not a source of code. Passing the Khronos CTS and
claiming a Vulkan version come only after those capabilities exist and are
tested.
