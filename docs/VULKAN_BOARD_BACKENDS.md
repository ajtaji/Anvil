# Vulkan board backend capabilities

The shared Vulkan object and command layer is board-neutral. Its backend seam is declared in `Anvil/Graphics/Vulkan/vk_foundation.pbi`: capabilities, device preparation and limits, memory/image planning, validated transfer submission, completion polling, and closed draw/pipeline records. Portable code passes resolved records rather than board handles or packet formats.

Backend choice is **static at build time**. Exactly one backend file is included; none and test both deliberately implement the same seam. There is no runtime registration or dynamic backend loading. Capability bits describe the linked backend, so device, clear, GPU, draw, source-over blend, and draw-list support can be reported independently.

| Board/build | Linked backend evidenced by the reviewed sources | GPU capability and proven scope |
|---|---|---|
| Raspberry Pi 4 | `Anvil/Graphics/Vulkan/vk_v3d_backend.pi4` | Real V3D 4.2 backend; reports device, clear, GPU, draw, source-over blend, and draw-list capabilities. Pi 4 silicon proofs cover bounded clears, graphics, uploads/copies/readbacks, and presentation via the display DMA path. This is not Vulkan 1.0 conformance or WSI. |
| UNO Q | `Anvil/Graphics/Vulkan/vk_backend_none.pbi` | Confirmed no-device build: enumerates no physical device. UNO Q has no Vulkan present provider in the status document. |
| Pi 3 | No board assignment is stated in these sources. | Unknown. Do not infer V3D support or a usable GPU backend. The no-backend file says any Pi build without V3D enumerates no device. |
| RockPi4C | No board assignment is stated in these sources. | Unknown. No GPU backend or capability is established here. |
| Pi 5 | No board assignment is stated in these sources. | Unknown. No GPU backend or capability is established here. |

`vk_backend_test.pbi` is a development/test backend, not hardware acceleration: it models state and logs calls, and never writes image pixels. `vk_backend_none.pbi` is the honest production choice when a target has no linked GPU backend; portable API code can compile while physical-device enumeration remains empty.

## Bounded image readback

The current Pi 4 status includes **full level-zero optimal BGRA8 image readback** into a transfer-destination buffer through guarded 2D DMA, with tight or padded destination rows and a one-layer, one-sample shape. The documented 37×13 silicon diagnostic checked all 481 texels, untouched padding, 40 DMA operations, and refusal of partial-region readback. Therefore optimal-tiled readback is supported for that bounded whole-image case. Partial optimal regions, mip levels, layers, and format conversion remain unsupported. This is distinct from general Vulkan image readback support on other backends.

## Extending the seam

A future board backend should implement the shared interface behind the same statically selected boundary, report only capabilities it can execute, and lower validated closed records into that board's own GPU operations. Add an operation or capability to the portable layer only with the corresponding backend contract and explicit unsupported behavior for backends that lack it. A future backend must not be inferred from shared Vulkan API coverage; it needs a named board implementation and its own hardware evidence.
