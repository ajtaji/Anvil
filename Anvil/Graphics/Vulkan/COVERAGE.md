# Anvil Vulkan foundation coverage

The schema compatibility target is Vulkan 1.0. It is not an implementation or
conformance claim. Vocabulary is derived from the official Khronos
`Vulkan-Headers` tag `v1.4.350`, commit
`a33416ed2ce6bf8ef48b4eda821825f66d1850d3`. The raw
`registry/vk.xml` SHA-256 is
`50BD8C0F316EABF73D1C5FE3ADD2D89EAA480DBDA9282C12C289E80E9D081E08`.
The registry is dual licensed Apache-2.0 OR MIT.

## Four distinct coverage classes

| Class | Current coverage |
|---|---|
| Generated vocabulary | A pinned core-1.0 generator exists. The checked-in initial slice contains exact result, structure-type and command lifecycle constants plus 19 scalar, nested, fixed-array and pointer-bearing structures. It is not the complete 1.0 vocabulary yet. |
| Semantic implementation | Opaque typed/generation handles; instance/device/queue ownership; command pools; primary/secondary command buffers; initial, recording, executable, pending and invalid states; reset/free/destroy invalidation. These are native PureMetal procedures below the future public entry layer. One internal transition-plus-full-clear command is recorded with strict state checks. |
| Explicit test backend | When a test defines `#ANVIL_VK_TEST_BACKEND=1`, one synthetic physical device and queue exist. Only empty primary command buffers submit, synchronously. A recorded unsupported operation is refused with `VK_ERROR_FEATURE_NOT_PRESENT`. |
| V3D development execution | One offscreen B8G8R8A8_UNORM full-image clear lowers to the existing Neon/V3D bin/render submit-and-wait path. The host gate stubs only this hardware boundary. Production `AnvilVkBackendAvailable()` still returns 0; no production device, public `vkCmdClearColorImage`, general resource/synchronization, shader, pipeline or WSI support is claimed. |

`ROADMAP.md` is the authoritative detailed gap inventory, including the
SPIR-V, pipeline, platform-service, synchronization, resource, WSI and CTS work
that remains.

## Compiler ABI boundary

On AArch64 the public memory ABI is LP64: Vulkan 32-bit scalars align to 4,
64-bit values, pointers and handles align to 8, and structures carry C tail
padding. Every checked-in public record opts into
`Structure ... Align #PB_Structure_AlignC`; default PureMetal packed layout is
unchanged. Nested members and fixed arrays retain their registry names. The
emitted-code gate checks sizes and nested `OffsetOf` results, including
`VkApplicationInfo` (`pNext` at byte 8, size 48), `VkRect2D`, fixed character
arrays and `VkSubmitInfo` (size 72). Hand padding and flattened substitute
members are not used. A compiler that lacks this explicit layout mode must
reject these declarations loudly; it must not silently use packed layout.

## Next real backend layers

The next stages are memory heaps and V3D buffer-object virtual addressing,
SPIR-V validation and native QPU compilation, descriptors and immutable
pipeline state, command lowering into V3D bin/render jobs, IRQ/fence/cache and
fault handling, then WSI against Anvil's existing HDMI/DSI present-surface
seam. Mesa V3DV is a semantic and job-building reference, not a Linux runtime
dependency. Passing the Khronos CTS and claiming a Vulkan version come only
after those capabilities exist and are tested.
