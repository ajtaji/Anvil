# Vulkan board backend capabilities

The shared Vulkan object and command layer is board-neutral. Its backend seam is declared in `Anvil/Graphics/Vulkan/vk_foundation.pbi`: capabilities, device preparation and limits, memory/image planning, validated transfer submission, completion polling, and closed draw/pipeline records. Portable code passes resolved records rather than board handles or packet formats.

Backend choice is **static at build time**. Exactly one backend file is included; none and test both deliberately implement the same seam. There is no runtime registration or dynamic backend loading. Capability bits describe the linked backend, so device, clear, GPU, draw, source-over blend, and draw-list support can be reported independently.

| Board/build | Current backend or monitor composition | GPU capability and proven scope |
|---|---|---|
| Raspberry Pi 4 | `Anvil/Graphics/Vulkan/vk_v3d_backend.pi4` | Real V3D 4.2 backend; reports device, clear, GPU, draw, source-over blend, and draw-list capabilities. Pi 4 silicon proofs cover bounded clears, graphics, uploads/copies/readbacks, and presentation via the display DMA path. Partial attachment clears support one in-bounds color rectangle on even-sized framebuffers and remain ordered with draws in one bin/render transaction; full pre-draw load clears also work on odd-sized targets. This is not Vulkan 1.0 conformance or WSI. See `docs/evidence/vulkan-clear-attachments-pi4-20260930/README.md`. |
| UNO Q monitor | `ArduinoQ/Board/board.unoq` | The monitor composition includes neither the Vulkan API nor a Vulkan backend. The generic `vk_backend_none.pbi` is available for a separate no-GPU test/probe composition; it does not establish Vulkan inclusion in the monitor. |
| Pi 3 monitor | `RaspberryPi3/Board/board.pi3` | The composition root does not include a Vulkan API/backend; the Pi 3 guide says Pi 3 Vulkan is not yet provided. |
| ROCK Pi 4C monitor | `RockPi4C/Board/board.rockpi4c` | The composition root does not include a Vulkan API/backend; the board guide says no hardware Vulkan driver is provided. |
| Pi 5 entry diagnostic | `RaspberryPi5/Boot/board.pi4` builds the first-entry diagnostic `runs/pi5-entry.img`, named `ANVIL5.IMG` by the prepared card; it is not a full monitor. | This diagnostic composition includes no Vulkan API/backend, and no Pi 5 GPU path or hardware proof is established. |

`vk_backend_test.pbi` is a development/test backend, not hardware acceleration: it models state and logs calls, and never writes image pixels. A future board build that includes the portable API but has no GPU backend can link `vk_backend_none.pbi`; it enumerates no physical device.

Compile-only probes built with the compiler fix shipped on `PureBasicCode` `main` at commit `1752ead85bad59fadcbb633da68ed289a84e2639`: the A64 ABI gate in `tools/vulkan_alignc_cross_target_check.py` passed 39 checks (12 `SizeOf`/`OffsetOf` checks each for Pi 3, ROCK Pi 4C, and Pi 4, plus an RP2350 negative control); standalone `pi3` and `rockpi4c` Vulkan API + none-backend probes each linked a 192,784-byte image, and a UNO Q none-backend probe also compiled. These are compile/link results only: the production non-Pi 4 monitor roots still omit Vulkan, and no non-Pi 4 GPU path is claimed.

## Bounded image readback

The Pi 4 backend supports full-image and a bounded partial level-zero optimal BGRA8 image readback into a transfer-destination buffer through guarded 2D DMA. The 2026-09-27 37×13 whole-image diagnostic checked all 481 texels, untouched padding and 40 DMA operations, proving odd full-image dimensions. The separate 2026-09-30 R2 partial proof returned report pointer `0x9408C8` and checked a 4×4-aligned region of 16 texels, 16 padding words and 32 guard words, with one DMA operation; an unaligned request returned `-20005`. Partial offsets and extents must align to 4×4 utiles, and edge tails remain refused. Mip levels, layers and format conversion remain unsupported. This is Pi 4-specific evidence, not general support on other backends.

## Extending the seam

A future board backend should implement the shared interface behind the same statically selected boundary, report only capabilities it can execute, and lower validated closed records into that board's own GPU operations. Add an operation or capability to the portable layer only with the corresponding backend contract and explicit unsupported behavior for backends that lack it. A future backend must not be inferred from shared Vulkan API coverage; it needs a named board implementation and its own hardware evidence.
