# Pi 4 zero sample-mask draw proof — 2026-10-01

A bounded public draw-list diagnostic tested a pipeline created for one rasterization sample with `pSampleMask[0] = 0`. The command buffer records three ordered `vkCmdDraw` calls: an ordinary red outer draw, the zero-mask green draw over the same outer geometry, and an ordinary blue inner draw. The resulting full 64×64 BGRA8 image matched all 4,096 expected pixels; the green draw left no visible pixels. List accounting reports three public draw records and two emitted primitives, with one bin/render job pair. Surface and Vulkan-window guards were unchanged; MMU, OOM, native and Vulkan faults were zero, and no nonbenign V3D status bits were set.

This is the backend's zero-coverage handling: it validates the draw record, then omits that draw's V3D primitive/state emission. No V3D sample-mask packet is emitted or claimed. The proof covers this single-sample case only. Pixel inspection reads the completed GPU image; no CPU image painting or display fallback is used.

`report.bin` is the exact 256-byte report returned by the Pi 4 diagnostic. SHA-256: `EC327F4D3DEFAE809CECD26AEB52D1818714573D1412126949575E94AB29E839`. The signed PMF SHA-256 is `8AFCFBFCDD605FEE2965D4C17BF2CD475C357D5575AFDD1FB6F0E85A7ABC3902`. The public checker verifies the report and catches 14 hostile mutations.
