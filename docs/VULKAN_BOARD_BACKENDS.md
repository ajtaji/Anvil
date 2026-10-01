# Vulkan board backend capabilities

The shared Vulkan object and command layer is board-neutral. Its backend seam is declared in `Anvil/Graphics/Vulkan/vk_foundation.pbi`: capabilities, device preparation and limits, memory/image planning, validated transfer submission, completion polling, and closed draw/pipeline records. Portable code passes resolved records rather than board handles or packet formats.

Backend choice is **static at build time**. Exactly one backend file is included; none and test both deliberately implement the same seam. There is no runtime registration or dynamic backend loading. Capability bits describe the linked backend, so device, clear, GPU, draw, source-over blend, and draw-list support can be reported independently.

| Board/build | Current backend or monitor composition | GPU capability and proven scope |
|---|---|---|
| Raspberry Pi 4 | `Anvil/Graphics/Vulkan/vk_v3d_backend.pi4` | Real V3D 4.2 backend; reports device, clear, GPU, draw, source-over blend, and draw-list capabilities. Pi 4 silicon proofs cover bounded clears, graphics, uploads/copies/readbacks, and presentation via the display DMA path. This is not Vulkan 1.0 conformance or WSI. |
| UNO Q monitor | `ArduinoQ/Board/board.unoq` | The monitor composition includes neither the Vulkan API nor a Vulkan backend. The generic `vk_backend_none.pbi` is available for a separate no-GPU test/probe composition; it does not establish Vulkan inclusion in the monitor. |
| Pi 3 monitor | `RaspberryPi3/Board/board.pi3` | The composition root does not include a Vulkan API/backend; the Pi 3 guide says Pi 3 Vulkan is not yet provided. |
| ROCK Pi 4C monitor | `RockPi4C/Board/board.rockpi4c` | The composition root does not include a Vulkan API/backend; the board guide says no hardware Vulkan driver is provided. |
| Pi 5 | No image or composition root is documented; the guide says Anvil has no Pi 5 image. | No Vulkan API/backend selection exists to assess yet. |

`vk_backend_test.pbi` is a development/test backend, not hardware acceleration: it models state and logs calls, and never writes image pixels. A future board build that includes the portable API but has no GPU backend can link `vk_backend_none.pbi`; it enumerates no physical device.

Compile-only probes built with the compiler fix shipped on `PureBasicCode` `main` at commit `1752ead85bad59fadcbb633da68ed289a84e2639`: the A64 ABI gate in `tools/vulkan_alignc_cross_target_check.py` passed 39 checks (12 `SizeOf`/`OffsetOf` checks each for Pi 3, ROCK Pi 4C, and Pi 4, plus an RP2350 negative control); standalone `pi3` and `rockpi4c` Vulkan API + none-backend probes each linked a 192,784-byte image, and a UNO Q none-backend probe also compiled. These are compile/link results only: the production non-Pi 4 monitor roots still omit Vulkan, and no non-Pi 4 GPU path is claimed.

## Bounded image readback

The current Pi 4 status includes **full level-zero optimal BGRA8 image readback** into a transfer-destination buffer through guarded 2D DMA, with tight or padded destination rows and a one-layer, one-sample shape. The documented 37×13 silicon diagnostic checked all 481 texels, untouched padding, 40 DMA operations, and refusal of partial-region readback. Therefore optimal-tiled readback is supported for that bounded whole-image case. Partial optimal regions, mip levels, layers, and format conversion remain unsupported. This is distinct from general Vulkan image readback support on other backends.

## Extending the seam

A future board backend should implement the shared interface behind the same statically selected boundary, report only capabilities it can execute, and lower validated closed records into that board's own GPU operations. Add an operation or capability to the portable layer only with the corresponding backend contract and explicit unsupported behavior for backends that lack it. A future backend must not be inferred from shared Vulkan API coverage; it needs a named board implementation and its own hardware evidence.
