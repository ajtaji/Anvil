# Pi 4 Neon particle-call Vulkan proof

The returning offscreen `vulkanNeonParticlePortProof.pi4` payload ran on Anvil
build 244 under a confirmed 15-second deadman. The board verified the
1,344,132-byte PMFBOOT container (SHA-256
`BF8428DFB11DF227A3BEE5B2111B694DD44A890C8E8A8FD105F9ECCCBEB3DF9D`)
at `0x00800000` and returned `x0 = 0x020002C8` after 4.3 seconds. The
monitor returned to `pmf>` and stopped the deadman. No boot image,
filesystem, or display scanout was changed.

The saved 128-byte [report](report.bin) has SHA-256
`2E95D29680FF1DC36A1E7CE15369A2F71C5ACCE369EA05BE98F63F22E54A64E1`.
It passes `vulkanNeonParticlePortProofCheck.py`: the Anvil-only Neon adapter
accepted three ordered particles, captured a camera offset at Prepare,
rendered a red square, a later translucent green overlap, and a rotated blue
square in one Vulkan draw with 18 vertices. Pixel probes matched the blend,
the rotated blue tip, and an empty corner; Vulkan faults and teardown residue
were zero.

The initial run used an incorrect expected alpha for translucent pixels and
returned a diagnostic failure, while its RGB, order, rotation, draw count,
and cleanup checks passed. The corrected oracle expects `0xBF` alpha from
the configured `SRC_ALPHA` / `ONE_MINUS_SRC_ALPHA` factors on both color and
alpha. The renderer was unchanged; the corrected payload passed on the board.

The adapter still rounds desktop float geometry to integral pixels and Q16
angles, and Chrome still expands six vertices per particle on the CPU. This
proves the Anvil Neon-call route on Pi 4; it does not establish desktop
subpixel parity, GPU particle expansion, or cross-board acceleration.
