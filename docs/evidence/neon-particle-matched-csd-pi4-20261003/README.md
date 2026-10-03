# Pi 4 matched CSD particle profile

The returning `vulkanNeonParticleMatchedCsdProfile.pi4` payload ran on Anvil
build 244 under a confirmed 15-second deadman. The board verified the
1,369,012-byte PMFBOOT container (SHA-256
`716E7CF57C4E16F93545031DE9563206FD5A46FBAC4571BBB9DE04FB4A3A7D97`)
at `0x00800000` and returned `x0 = 0x00B79D00` after 7.2 seconds. The monitor
returned to its prompt and stopped the deadman. No boot image, filesystem,
or display scanout was changed.

The saved 256-byte [report](report.bin) has SHA-256
`8BD737CA6428F4F51E046BF4BC334CE8D628F640F156DCCA5A66E0B3C71F90A6`.
The matched checker passed one warm-up and three measured 800×800 frames of
10,000 particles, 20,000 final pixel probes, four bin/render jobs, no GPU
faults, and clean teardown. The CSD path uses the same particles, palette,
target, Chrome shared capacity, pre-frame idle boundary, and pixel oracle
as the [CPU baseline](../neon-particle-matched-cpu-pi4-20261003/README.md).

Median measured CSD frame time was 724,647 µs: Prepare 538,596 µs,
external-buffer draw recording 489 µs, and Vulkan End/fence 185,086 µs.
Within Prepare, palette upload took 200,903 µs, CPU compact-record staging
291,879 µs, and CSD 21,113 µs. The median full frame was **135,560 µs
slower** than the 589,087 µs CPU baseline. The dedicated GPU buffer and
compute expansion work correctly, but this implementation remains opt-in
until staging is made faster or moved to the GPU.
