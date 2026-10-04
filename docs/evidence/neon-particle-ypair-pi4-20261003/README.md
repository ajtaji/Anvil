# Pi 4 CSD particle Y-coordinate reuse

The Pi 4 particle CSD producer now retains the most recent exact Q8 Y-corner
pair within a single record-staging call. Adjacent axis-aligned particles
with the same pair reuse both converted clip words. Different pairs use the
original conversion, and rotated/camera geometry still takes its original
four-corner route. The cache cannot survive a new target or Prepare call.

The source behavior gate passed four cases, including a mixed 10,000-record
sequence. The emitted A64 gate confirmed that a cache hit bypasses both Y
conversion calls. The module, matched-profile, rotated-profile and report
checker gates passed. This is an Anvil Pi 4 producer change; the board-neutral
Chrome path and Neon Arcade Engine source were not changed.

The rebuilt moving CSD PMFBOOT SHA-256 was
`BDD90E3DF77904C51A80BA1313B72FE7C12550491F941ECEACE32468AC26BC8A`.
On Pi 4 Anvil build 244, it uploaded with a matching board digest at
`0x00800000`, ran under a confirmed 15-second deadman, and returned the
expected report pointer `x0 = 0x02229D00`. The checker passed all four
moving 10,000-cell color/clear pixel oracles, GPU/fault checks and teardown.
The CPU payload was byte-identical to the preceding baseline.

| Moving CSD 10k metric | Before Y reuse | After Y reuse |
| --- | ---: | ---: |
| CPU record staging median | 126,824 µs | 113,088 µs |
| Full frame median | 419,668 µs | 405,927 µs |

This is an offscreen workload and CSD remains opt-in. The frame remains far
above the 60 Hz budget. No resident image, display scanout or storage was
changed. The saved [CSD report](csd-report.bin) has SHA-256
`635598E505FE3EB87BBBE714141D63F828336B29DBBD28B5ED6CCDC55EDC8E51`.
From the repository root, check it with
`python tools/neon_vk_particle_dynamic_check.py docs/evidence/neon-particle-ypair-pi4-20261003/csd-report.bin`.
