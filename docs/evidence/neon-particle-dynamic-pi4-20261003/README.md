# Pi 4 moving Neon particle proof

The diagnostic generator `tools/neon_vk_particle_dynamic_build.py` derives
matched CPU and CSD payloads from the current Anvil Vulkan particle modules.
It moves the same 10,000-particle grid right by one pixel on each of four
frames. Each frame checks a colored interior and a black leading edge for
every grid cell. The black probe on later frames also verifies that the
previous position was cleared. This is a returning, offscreen test; it does
not change the resident monitor or the Neon Arcade Engine source.

The CPU PMFBOOT SHA-256 was
`2635E92B2E7539B62AA342B6C4B9D8AD2EDF23AFC89E8BFC5BCD86A3A7FF5705`;
the CSD PMFBOOT SHA-256 was
`3CC3C5F58A14D4632FE8640FC183F5FF15B5B87A372D481BD0ABF42AC54615B8`.
Both images loaded at `0x00800000` on Pi 4 Anvil build 244 with a confirmed
15-second deadman, matched the board's upload digest, and returned the expected
report pointer `x0 = 0x02229D00`. The checker passed all four moving frames,
the existing GPU/fault/teardown contract, and every 10,000-cell per-frame pixel
oracle. Neither run changed the resident image, scanout, or storage.

| Mode | Median frame | Prepare | Draw | End |
| --- | ---: | ---: | ---: | ---: |
| CPU | 528,344 µs | 210,117 µs | 208,762 µs | 101,020 µs |
| CSD | 479,372 µs | 367,915 µs | 488 µs | 102,644 µs |

CSD saved 48,972 µs per measured moving frame in this paired test. Both paths
remain far above the 16,667 µs budget for 60 Hz, and CSD is still opt-in.
The static-grid coordinate-table reuse result does not by itself establish
full Neon application performance.

Saved reports: [CPU](cpu-report.bin) SHA-256
`1123FBAD4EC7690BB800D8C61C09D2919CFB748FF8D716D316576E83AE9A435A`;
[CSD](csd-report.bin) SHA-256
`E90DFF32D5DA2D72788A02C6F0D27FF7273B2339CE2C92DAB0518EDE9C70B948`.
From the repository root, recheck them with
`python tools/neon_vk_particle_dynamic_check.py docs/evidence/neon-particle-dynamic-pi4-20261003/cpu-report.bin docs/evidence/neon-particle-dynamic-pi4-20261003/csd-report.bin`.
