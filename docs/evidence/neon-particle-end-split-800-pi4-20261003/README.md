# Pi 4 matched 800×800 particle End split

This returning RAM diagnostic used the current matched 10,000-particle CSD
profile and timed a **copy** of Chrome's End procedure. The production Chrome
and backend sources were unchanged. Its generator is
`tools/neon_vk_particle_end_split_build.py`; generated source and the full
memory-map manifest remain scratch artifacts under `runs/`.

Anvil build 244 verified the 1,371,916-byte PMFBOOT container at `0x00800000`
(SHA-256 `E1322CF40644962EC62668B31688019190DC37771CCBA098059F3F3B205660FA`).
It returned `x0 = 0x02229D00` in 6.4 seconds under a confirmed 15-second
deadman. The saved 512-byte [report](report.bin) has SHA-256
`91A4CF604A7B3E1BCF81DF2A600DCE98032744B37B12C589481C34A2B90B7199`.
`tools/neon_vk_particle_end_split_check.py` passed the base oracle: four
800×800 frames of 10,000 particles, 20,000 pixel probes, four bin/render
jobs, no GPU faults, and clean teardown.

| End phase | Median of three measured frames |
| --- | ---: |
| Whole Chrome End | 188,949 µs |
| Before submission | 49 µs |
| Fence reset | 30 µs |
| `vkQueueSubmit` | 188,803 µs |
| Fence wait | 37 µs |
| After submission | 15 µs |
| Nested cache clean | 118 µs |
| Nested bin job | 8,624 µs |
| Nested render job | 72,646 µs |

The nested backend measurements occur **inside** `vkQueueSubmit` and must
not be added to it. They do not yet account for every part of the 188.8 ms
submit call. This establishes that the large End time is in synchronous
queue submission, not the subsequent fence wait. The timing calls add small
overhead. No resident image, display scanout, or storage was changed.
