# Pi 4 matched 800×800 backend timing split

This returning RAM diagnostic timed copies of the current Chrome, V3D
backend, and Neon surface procedures in the matched 10,000-particle CSD
profile. Production renderer sources were unchanged. The generator is
`tools/neon_vk_particle_backend_split_build.py`; generated source and the
complete memory-map manifest remain scratch artifacts under `runs/`.

Anvil build 244 verified the 1,373,940-byte PMFBOOT container at `0x00800000`
(SHA-256 `5B76759261CBC3E3815B9F8772BB2EA249E16B2D3172728BA53A9912F03DF6F7`).
It returned `x0 = 0x02229D08` in 6.4 seconds under a confirmed 15-second
deadman. The saved 768-byte [report](report.bin) has SHA-256
`70DB3CEE5DB796EBE8AD68CD9C6D7D5688D79B8968733D377624E4C92288A5FB`.
`tools/neon_vk_particle_backend_split_check.py` passed the original matched
End and pixel/fault oracle: four 800×800 frames of 10,000 particles, 20,000
pixel probes, four bin/render jobs, no GPU faults, and clean teardown.

| Backend phase | Median of three measured frames |
| --- | ---: |
| Whole backend draw submission | 188,878 µs |
| Pre-frame preparation | 1,158 µs |
| Cache interval clean | 6,302 µs |
| Rebind to 800×800 Vulkan target | 42,526 µs |
| Coordinate-table rebuild within target rebind | 42,403 µs |
| Frame begin | 1,971 µs |
| Draw command emission | 248 µs |
| Frame end, including bin/render | 81,388 µs |
| Restore original 800×1280 surface | 55,265 µs |
| Coordinate-table rebuild within restore | 55,145 µs |

The two coordinate-table rebuilds account for about 97.5 ms of this
controlled frame. Their timings are nested inside their corresponding
rebinds and must not be added separately. Timer calls add small overhead.
This result supports investigating safe reuse of the tables for the two
recurring surface geometries. It does not yet prove such a change is safe or
faster. No resident image, display scanout, or storage was changed.
