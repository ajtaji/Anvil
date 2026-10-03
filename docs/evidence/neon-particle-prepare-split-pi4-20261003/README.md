# Pi 4 particle Prepare timing split

This returning RAM diagnostic copied the matched 10,000-particle CSD profile
and instrumented a **copy** of Chrome's particle Prepare. Production renderer
source was unchanged. The generator is
`tools/neon_vk_particle_prepare_split_build.py`; its generated source and
complete memory-map manifest are scratch artifacts under `runs/`.

Anvil build 244 verified the 1,371,468-byte PMFBOOT container at `0x00800000`
(SHA-256 `8905F9321CF2E81F12C09787D91C807E2043A5E8F5F3AD7624F76FF155BC2FAA`).
The image returned `x0 = 0x02229D00` in 6.5 seconds under a confirmed
15-second deadman. The saved 512-byte [report](report.bin) has SHA-256
`6DCA20725E6B4E5041AFFE73416A188C8A1B105EF83DBC274E3F7C8E26A96944`.
`tools/neon_vk_particle_prepare_split_check.py` passed the original matched
pixel/fault/teardown oracle: 10,000 particles, four 800×800 frames, 20,000
pixel probes, four bin/render jobs, no GPU faults, and clean teardown.

| Chrome Prepare phase | Warm-up frame | Median of three unchanged-color frames |
| --- | ---: | ---: |
| Geometry validation and color comparison | 159,034 µs | 154,235 µs |
| Device idle check | 12 µs | 12 µs |
| Item copy and palette staging | 47,118 µs | 43,184 µs |
| Actual palette upload | 2,825 µs | 0 µs |
| Whole Chrome Prepare | 217,637 µs | 197,452 µs |

The timing calls add small overhead. The producer's measured Chrome Prepare
span was 197,462 µs on the unchanged frames. This confirms palette reuse
skipped the transfer; the earlier approximately 200 ms figure was **whole
Prepare**, primarily geometry validation and item copying. Repeating Prepare
for an unchanged list is a deliberately controlled diagnostic workload;
applications may retain a prepared list instead. No resident image, display
scanout, or storage was changed.
