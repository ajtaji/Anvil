# Pi 4 matched CPU particle baseline

The returning `vulkanNeonParticleMatchedCpuProfile.pi4` payload ran on Anvil
build 244 under a confirmed 15-second deadman. The board verified the
1,338,484-byte PMFBOOT container (SHA-256
`6C6336AFD06B9ADEDCFC5690AB3AEEFDF57904A347D260B5EF55DDBB6490FF77`)
at `0x00800000` and returned `x0 = 0x00B79D00` after 6.6 seconds. The monitor
returned to its prompt and stopped the deadman. No boot image, filesystem,
or display scanout was changed.

The saved 256-byte [report](report.bin) has SHA-256
`B0CE4E1672D287C37C1C19CBA89D6CA80C2C8AB507CD4A485B1526990C8980EE`.
The matched checker passed one warm-up and three measured 800×800 frames of
10,000 particles, 20,000 final pixel probes, four bin/render jobs, no GPU
faults, and clean teardown. Median measured frame time was 589,087 µs:
Prepare 197,901 µs, CPU vertex Draw 208,261 µs, and Vulkan End/fence
182,366 µs. This is the baseline for the paired CSD run.
