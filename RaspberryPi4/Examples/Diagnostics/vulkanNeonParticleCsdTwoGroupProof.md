# Pi 4 V3D two-workgroup particle expansion proof

This is a returning RAM diagnostic only. It does not modify the Neon worker or the production Vulkan pipeline. Its Pi 4 build-244 run passed under an armed 15-second deadman; see `docs/evidence/neon-particle-csd-two-group-pi4-20261003/README.md`.

## Indexing source

Mesa's [Pi 4 V3D compute lowering](https://chromium.googlesource.com/chromiumos/third_party/mesa/+/a11d1bd247df18057ecb9945e01bf39ff85d8d9d/src/broadcom/compiler/nir_to_vir.c) copies compute payload register `r0` into `cs_payload[0]`. Its `load_work_group_id` case derives X as `cs_payload[0] & 0xffff`; EIDX is a subgroup/lane ID, not a global workgroup ID. The diagnostic therefore computes `item = ((r0 & 0xffff) << 4) + EIDX` for a `2 x 1 x 1` grid of 16-invocation groups. Mesa's [dispatch-base change](https://www.mail-archive.com/mesa-commit@lists.freedesktop.org/msg117203.html) independently describes the workgroup ID as hardware-generated and only the optional dispatch base as a uniform addition. This proof uses dispatch base zero.

The source also uses the existing, silicon-proven TMU vec4 loads and ordered six-vertex stores from `vulkanNeonParticleCsdExpandProof.pi4`. A distinct input record for every item makes a repeated EIDX-only index fail the second group of the exact output oracle.

## Memory and bounds

| Region | Physical = GPU virtual | Written/read | Bound |
| --- | --- | --- | --- |
| Compiled image | `0x00800000..0x0081343F` | ARM code/data | linker output |
| Report BSS | `0x00880978..0x00880A77` | ARM writes, monitor reads | exactly 256 bytes; `x0 = 0x00880978` |
| V3D page tables | `0x02F00000..0x02F0CFFF` | V3D MMU | 13 pages |
| Illegal page | `0x02F10000..0x02F10FFF` | V3D MMU fault target | one page |
| QPU code | `0x03000000..0x03000FFF` | ARM writes, V3D reads | one page |
| Uniforms | `0x03001000..0x03001FFF` | ARM writes, V3D reads | 28 live bytes; poison tail |
| Records | `0x03002000..0x03002FFF` | ARM writes, V3D reads | 32 × 32 = 1024 live bytes; poison tail |
| Vertices | `0x03003000..0x03004FFF` | V3D writes, ARM verifies | 32 × 144 = 4608 live bytes; 3584 poison guard bytes |

The last record ends at `0x030023FF`; the last vertex word ends at `0x030041FF`. Each group owns 2304 disjoint vertex bytes. The output page boundary falls inside the second group's range and is mapped. No TMU address uses the CPU image, report, page tables, or illegal page. QPU code, uniforms, records, and both output pages are explicitly mapped. Input is ARM-cleaned before submit; the CSD helper cleans code/uniform/output and invalidates GPU caches; the bounded wait cleans V3D output; the ARM cache range is refreshed before oracle reads.

## Run and oracle

Compile from `C:\Users\rajta\Desktop\Anvil` with the signed `C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe`:

```powershell
& 'C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe' --compile 'C:\Users\rajta\Desktop\Anvil\RaspberryPi4\Examples\Diagnostics\vulkanNeonParticleCsdTwoGroupProof.pi4' --entry-returns --load-addr 8388608 -o 'C:\Users\rajta\Documents\Codex\2026-09-17\c-embedded-compiler-compilerembedded-anvil-vulkan\work\vulkanNeonParticleCsdTwoGroupProof.bin'
```

The PMF container is the `.bin.pmf` sibling. Its entry is `0x00800000`. On return, read exactly 256 bytes from `x0 = 0x00880978` and pass them to `vulkanNeonParticleCsdTwoGroupProofCheck.py`. `V3dCsdWait(100000)` has a 100 ms timeout; a supervisor deadman must independently bound a non-returning fault. A passing report requires stage 0, CSD done-counter advance, zero assembler/submit/wait/cache errors, all 1152 vertex words exact, all 896 output-guard words intact, all 256 record words intact, all 768 record-tail words intact, and group-boundary markers `0x3F800000` then `0x3F010000`. The 256-byte report uses unsigned 32-bit words; the checker compares canaries unsigned.

For a failure, report word 1 is the stage, 5 the QPU assembler result, 6 the vertex mismatch count, 7 the output guard mismatch count, 9–10 the CSD done counters, 11 the GPU clean result, 12–14 the MMU fault fields, 16–17 the submit/wait results, 18 the elapsed microseconds, 19–21 the first vertex mismatch offset+1/expected/actual, and 22 the input mismatch count. Words 23–26 sample the two output boundaries. The final desk build's `.bin.pmf` file SHA-256 is `7729ACA4FBFEB19C235E32EC2E3B5270F06645DBF0946C1E93825453FFA3B969`; the embedded payload SHA-256 reported by PMF is `3694B999DE892261A5DAE71B6D9F2679ED0FC328023B8D63B978682E93738C8D`.

The desk compiler, synthetic report checker, and exact Pi 4 board report pass. This establishes two-group indexing and output isolation on this hardware, but does not establish renderer buffer ownership, larger dispatches, or 10,000-particle frame throughput.
