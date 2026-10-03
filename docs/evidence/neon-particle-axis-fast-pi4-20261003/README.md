# Pi 4 particle Prepare axis fast path

Chrome's particle Prepare now handles unrotated, camera-independent integer
quads directly in its validation scan. It applies the same bounds and writes
the same four Q8 corners as `nvcParticleGeometry`. Other particles keep the
original geometry routine. The entire input list is still validated before
retained items change, so a late invalid item does not partially publish a
new list.

`tools/neon_vk_particle_axis_prepare_check.py` compared the emitted path with
the original geometry routine for moving and boundary cases, a late failure,
and retry. It passed 519,435 interpreted A64 steps. For 1,000 moving items,
the self-contained reference comparison counted 1,185,796 steps versus
882,904 with the fast path (25.5% fewer). The existing palette/failure gate
and matched-profile compilation also passed. Instruction count is not a
board-time estimate.

Matched moving 10,000-particle CPU and CSD payloads were rebuilt from current
Anvil source. Their PMFBOOT SHA-256 digests were
`318D1CCDB1410BF8A1A25AA5BBAF20987F857029FC978F8352BE6D72D60368F3`
and `65210458BDFDFB2B4B4D5DC368BADA9BA15C9017E006B30C9A8ECBA00F6A9950`.
On Pi 4 Anvil build 244, each uploaded with a matching board digest at
`0x00800000`, ran under a confirmed 15-second deadman, and returned the
expected `x0 = 0x02229D00`. The dynamic checker passed all four moving
10,000-cell color/clear pixel oracles and the GPU/fault/teardown checks.

| Mode | Before fast path | After fast path | Frame gain | After Prepare |
| --- | ---: | ---: | ---: | ---: |
| CPU | 528,344 µs | 454,279 µs | 74,065 µs | 136,598 µs |
| CSD | 479,372 µs | 419,668 µs | 59,704 µs | 308,317 µs |

These are matched offscreen tests, not a full application. CSD remains opt-in;
both paths are still far above a 60 Hz frame budget. The resident monitor,
display scanout, storage, and Neon Arcade Engine source were unchanged.

Saved reports: [CPU](cpu-report.bin) SHA-256
`A20713514D56B067104C4051F2FC2F83077DA60A09733E5EC3E4B2ADCADAF5DA`;
[CSD](csd-report.bin) SHA-256
`1FF0CDBAF8C1BB6888DB8E0F7678FCE0E972AFEBFC15944D0C3502B4F9DCB789`.
From the repository root, run
`python tools/neon_vk_particle_dynamic_check.py docs/evidence/neon-particle-axis-fast-pi4-20261003/cpu-report.bin docs/evidence/neon-particle-axis-fast-pi4-20261003/csd-report.bin`.
