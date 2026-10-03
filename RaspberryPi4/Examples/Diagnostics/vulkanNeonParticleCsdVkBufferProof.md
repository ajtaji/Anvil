# Pi 4 CSD output into a live Vulkan vertex buffer

**Run only with a 15-second armed deadman and exclusive Pi 4 board lease.** This returning RAM diagnostic passed on Pi 4 build 244. It establishes that the two-group CSD shader can write a bound Anvil `VkBuffer` inside Neon's existing V3D MMU mapping and that one non-indexed Vulkan draw fetches those bytes. The prior `vulkanNeonParticleCsdTwoGroupProof` established two-group QPU output into fixed RAM; this diagnostic changes the allocation and consumer.

## Build and report

Compile `RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdVkBufferProof.pi4` with the Pi 4 PureMetal Forge target, returning entry enabled, load address `0x00800000`, and separate BSS/stack regions described below. Use the resulting PMFBOOT v2 container for board upload.

The PMFBOOT v2 container is the `.bin.pmf` sibling. The verified build's file SHA-256 is `48334F85C91F2F197268C5830F53BCB309C7F58975BDACDD457CEE277E947FF9`; its embedded payload SHA-256 is `8D0639EB5D184FF981E2A68BBE6B777AA7C9C2A65156EEF9B57F018735F52F34`. Load/entry are `0x00800000`. **Only a verified-idle path returns.** On return, `x0` should be `0x00B79CC0`; read exactly 256 bytes and run:

```powershell
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdVkBufferProofCheck.py REPORT.BIN
```

Report word 1 is status; zero is pass. Word 2 is phase. Words 4–8 are the dynamically allocated output/code/uniform/input addresses and output allocation size. Words 11–15 are CSD submit, wait, cache-clean result, and done counters. Words 16–21 give exact vertex, output-guard, input mismatches and the first vertex mismatch. Words 22–24 are Vulkan begin/draw/end results. Words 25–30 are pixel samples and the 64-probe mismatch count. Words 31–33 are bin/render job deltas and MMU faults. Words 34–36 are CSD MMU fault diagnostics. Words 40–42 sample output boundaries. Words 44–49 give image/window addresses and timings. Words 50–51 are verification remap results. Words 52–54 are bitmap-font setup return, raster-build return, and atlas-ready flag; success requires `0,0,1`. Word 55 equals one only on a non-returning unsafe path; word 56 is Anvil's fault count. The checker rejects any stage failure, unsafe marker, byte/guard/pixel mismatch, bad address, stale completion counter, or missing draw job.

## Memory and ownership

| Region | Address / size | Allocation and constraint |
| --- | --- | --- |
| Image payload | `0x00800000..0x00946413` | AArch64 image; no overlap with monitor build ending at `0x0070214F` |
| BSS | `0x00950000..0x014B4A0F` | Compiler-reported globals, including 256-byte report at `0x00B79CC0` |
| Existing Neon surface | `0x06000000..0x063E7FFF` | Neon initializes and owns the V3D MMU; this diagnostic never calls `V3dMmuInit` or `V3dMmuMap` |
| Vulkan offscreen heap | `0x063E8000..0x06FE7FFF` | Existing Neon identity-mapped span; Anvil's heap allocator owns every live range |
| Vulkan render image | Dynamic inside heap, 64 × 64 × 4 = 16,384 bytes | Bound image; offscreen pixel oracle |
| CSD code, uniforms, records | Three separate dynamic 4096-byte `VkDeviceMemory` allocations inside heap | Host mapped only for writes, then unmapped before CSD; code ≤4096 bytes, uniforms 28 live bytes, input 1024 live bytes |
| CSD output / Vulkan vertices | Dynamic, page-aligned 8192-byte bound `VK_BUFFER_USAGE_VERTEX_BUFFER_BIT` buffer inside heap | 32 records × 6 vertices × 24 bytes = 4608 live bytes; 3584 poison guard bytes; Vulkan draws 192 vertices at stride 24, offset/firstVertex zero |
| Stack and V3D arena | Stack `0x08000000`; arena `0x0A000000..0x0AFFFFFF` | Separate from image, BSS, surface, heap |

The diagnostic checks that all four CSD regions and the render image lie in the mapped heap, are page-aligned, and do not overlap. It confirms the output `VkBuffer` is live and bound because `AnvilVkBufferAddress` returns nonzero only for a bound buffer, and confirms `vkMapMemory` resolves the same identity address. Before Chrome creation, it selects the `display.pi4` 8×16 bitmap with `NeonFontUse`, then explicitly builds and checks Neon's borrowed raster atlas. The output page is poisoned through that mapping, then unmapped. CSD code, uniforms, and records are mapped through their own live Vulkan allocations, populated, and unmapped. `V3dCsdSubmit` cleans code/uniform/output and invalidates V3D caches; the diagnostic explicitly cleans the input page. It requires `V3dCsdWait(100000)` and the GPU L2T/write-combiner clean to succeed before it remaps and checks output bytes. It unmaps again before binding the vertex buffer for the Vulkan draw. `NeonVkChromeEnd` submits and fence-waits the draw before pixels are checked and resources are destroyed.

The QPU uses `((r0 & 0xFFFF) << 4) + EIDX`, with two 16-lane groups. Every input record defines a separate 8 × 4-pixel rectangle in a 64 × 64 grid; group zero occupies rows 0–3 and group one rows 4–7. The exact byte oracle covers all 1152 vertex words, 896 output guard words, all 256 input record words, and 768 input tail words. The pixel oracle samples one interior green pixel and one black gap pixel per rectangle (64 probes), including both groups, after the Vulkan fence. No CPU vertex copy occurs.

If CSD submit has succeeded but wait, cache clean, or completion evidence fails, the diagnostic writes an unsafe status to RAM, emits `NGP!NN` on the enabled UART, and **spins inside the payload until the already armed 15-second deadman resets the board**. It does not return to the monitor, unmap, free, destroy, or kick the deadman. A failed Vulkan End uses the same non-returning path. Normal cleanup first rejects any outstanding submission and requires `vkDeviceWaitIdle` success before consuming Chrome state, destroying resources, or shutting down Neon. A later failed idle or teardown also stays inside the payload for deadman reset. The RAM report can be inspected only before reset with a live debugger; reset erases it. The UART marker is best-effort, since an enabled port need not be routed to the serial header. Only a verified-idle path returns an `x0` report. This containment is diagnostic-only; it is not a production timeout recovery policy.

The first Pi 4 run of the previous build returned status 7 at phase 1 with Chrome error `0xFFFFAD2C` (`-21204`, atlas error), before CSD submit. It lacked `NeonFontUse`: `NeonFontDefaults` sets styles but leaves `neon_fbits=0`, making `neon_RasterEnsure` return a font error. The corrected build returned under a 15-second deadman. Its [board report](../../../docs/evidence/neon-particle-csd-vkbuffer-pi4-20261003/report.bin) passed exact vertex/input/guard checks and 64 pixel probes. CSD took 219 microseconds for 32 records, and the Vulkan draw submission/wait took 84,014 microseconds. There is no large-dispatch performance evidence or proof yet for rotated or camera-transformed particle records.
