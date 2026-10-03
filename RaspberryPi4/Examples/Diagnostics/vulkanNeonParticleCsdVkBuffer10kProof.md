# Pi 4 10,000-particle CSD-to-VkBuffer diagnostic

**Desk build only; no Pi 4 run has occurred.** This isolated returning payload extends the silicon-passing 32-particle `vulkanNeonParticleCsdVkBufferProof`. It tests 625 workgroups of 16 invocations, 10,000 compact records, direct CSD writes to a live bound Vulkan vertex buffer, and one non-indexed 60,000-vertex draw. It does not change Chrome's production particle path or establish a speedup.

## Build and board boundary

From the repository root, with a writable `build` directory and `$PMF_COMPILER` set to the Pi 4 PureMetal Forge executable:

```powershell
& $PMF_COMPILER --compile RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdVkBuffer10kProof.pi4 --entry-returns --load-addr 8388608 -o build/vulkanNeonParticleCsdVkBuffer10kProof.bin
```

The `.bin.pmf` sibling is a PMFBOOT v2 container. Verify its target 2711, returning flag, load/entry `0x00800000`, stack `0x08000000`, and embedded payload digest before a board run. The compiled report symbol is `0x00B79CC0` (`x0` on a safe return); read exactly 256 bytes and run:

```powershell
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdVkBuffer10kProofCheck.py REPORT.BIN
```

Any supervised Pi 4 run requires an exclusive board lease and an armed **15-second deadman** immediately before the jump. The payload must not run resident. It stops setup above 7 seconds before CSD, stops byte validation above 10 seconds total, stops after the fenced draw above 12 seconds total, and stops pixel probes above 13 seconds total; these paths return only after verified GPU idle and cleanup. Teardown duration is not yet measured, so a deadman reset remains possible and safe even after a timed phase passes its gate. CSD submit uncertainty, CSD wait/cache/completion failure, Vulkan End failure, or failed idle/teardown **spins in the payload** without freeing GPU memory or returning to the monitor until deadman reset. The UART `NGP!NN` marker is best-effort.

## Memory and resource bounds

| Region | Extent | Ownership |
| --- | --- | --- |
| Monitor | through `0x0070214F` on build 244 | Existing board monitor; no overlap |
| Payload image | Starts at `0x00800000`; confirm final end from container | Compiled returning image |
| BSS, including report | `0x00950000..0x014B4A1F` | Payload globals |
| Neon surface | `0x06000000..0x063E7FFF` | Existing 800 × 1280 surface |
| Vulkan heap | `0x063E8000..0x073E7FFF` (16 MiB) | Existing Neon V3D identity map, expanded before `NeonInit`; Anvil suballocates every live Vulkan resource |
| V3D arena | `0x0A000000..0x0AFFFFFF` | Existing Neon GPU data |
| Stack top | `0x08000000` | Loader stack; above the heap |

The heap holds the 800 × 800 linear target (at least 2,560,000 bytes; actual pitch checked), Chrome's own 1,440,000-byte vertex buffer, atlas and staging resources, and the diagnostic allocations. The latter are one bound 1,445,888-byte output vertex buffer (1,440,000 live bytes plus 5,888 poison bytes), one 327,680-byte input allocation (320,000 live bytes plus 7,680 poison bytes), and separate 4096-byte code and uniform allocations. The output base is 4096-byte aligned and the 2304-byte output region of each workgroup is disjoint. The last item is 9999, its last vertex word ends at live byte 1,439,999, and every write stays inside the bound buffer. Runtime checks verify each address and complete extent is within the mapped heap and that output, input, code, uniforms, and image do not overlap. All dynamic allocation failures return a distinct status before CSD; report word 3 records the last Vulkan object or Chrome creation result, and word 42 records the last direct allocation result on its failure. Successful byte validation overwrites word 42 with the final-group sample.

The workgroup index is `((r0 & 0xFFFF) << 4) + EIDX`. `V3dCsdBegin(625,1,1,16,1)` fits its `wgX <= 65535` contract and computes 625 batches, CFG4 = 624 (`RaspberryPi4/Lib/v3d.pi4`). The [two-group proof](vulkanNeonParticleCsdTwoGroupProof.md) traces `r0[15:0]` to Mesa's Pi 4 compute lowering and established distinct output across the group boundary on silicon. This payload repeats that exact shader with 625 groups and no partial final group; no new implicit-uniform assumption is introduced.

Before CSD, the code, uniforms, records, and poisoned bound output are separate live Vulkan allocations. CPU writes are unmapped; the input range is explicitly cache-maintained, and `V3dCsdSubmit` maintains code/uniform/output plus GPU cache invalidation. The successful `V3dCsdWait(1,000,000)` and successful GPU L2T/write-combiner clean must precede CPU remapping, byte verification, and the Vulkan bind. The output is unmapped before draw. Chrome End fence-waits the draw; only then are pixels read and resources destroyed. No CPU vertex copy occurs.

## Oracles and timings

The exact byte oracle checks all 360,000 output vertex words, 1,472 output guard words, 80,000 compact-input words, and 1,920 input-tail guard words with unsigned 32-bit comparisons. The independent pixel oracle covers a unique 100 × 100 grid of 4 × 4 green rectangles inside 8 × 8 cells across the 800 × 800 target: one interior green and one black gap pixel per item, 20,000 probes total. It also samples the first and last rows and columns. This checks both ends of the 625-group draw, while the byte oracle checks every vertex and input record. The checker requires one bin and one render job, one Chrome draw, 60,000 recorded vertices, no MMU fault, zero byte/guard/pixel mismatches, and exact address/canary boundaries.

The 64-word report separates phase costs: word 41 is setup through shader construction and unmap; 43 is the included input staging portion; 48 is CSD submit plus wait; 61 is complete byte/guard validation; 62 is Chrome Begin plus draw recording; 49 is Chrome End submission and fence wait; and 40 is total elapsed through pixel probing. These are microseconds. Teardown is not separately timed. Status 31 means pre-CSD setup exceeded 7 seconds, 32 means validation reached 10 seconds total, 33 means the completed draw reached 12 seconds total, and 34 means pixel probing reached 13 seconds total; these are clean, verified-idle returns. Other nonzero statuses identify creation, allocation, exact-oracle, or Vulkan stages. Word 55 marks a non-returning unsafe path; a normal report must have zero.

The desk compiler and synthetic report checker pass. This diagnostic still lacks silicon results for 625-group timing, heap fit, and pixels. A production bridge remains separate because current Chrome owns and binds its own shared vertex buffer, and its particle path also handles camera and rotation; no external CSD lifetime or device-loss policy exists in that worker.
