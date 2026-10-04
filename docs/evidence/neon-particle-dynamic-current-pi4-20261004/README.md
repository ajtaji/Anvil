# Pi 4 current-source moving particle comparison

The current Anvil source at `e24645d` was used to build matched CPU and V3D
CSD particle paths with `tools/neon_vk_particle_dynamic_build.py`. Each
returning payload rendered the same 10,000-particle grid at 800×800, moving
it one pixel right on each of four frames. The checker verified every cell's
green interior and black leading edge on every frame, including pixels
vacated by the previous frame, plus the GPU job, fault and teardown contract.
Both paths passed. The CSD path generated vertices in a live Vulkan buffer;
the CPU path used Chrome's prepared vertex expansion.

| Path | Frame median | Prepare | Draw | End |
| --- | ---: | ---: | ---: | ---: |
| CPU | 454,115 µs | 136,974 µs | 207,791 µs | 101,044 µs |
| V3D CSD | 389,334 µs | 277,911 µs | 486 µs | 102,576 µs |

CSD was 64,781 µs faster per measured moving frame in this three-sample
pair, about 14.3% of the CPU frame time. Both remain well above a 16,667 µs
60 Hz budget. The producer is opt-in and does not implement public
`vkCmdDispatch`. This result establishes Pi 4 only.

The CPU PMFBOOT v2 SHA-256 was
`AE63169D11E2BDAF5E737DD6FCD6FBF06D7DC5F993501FCDD9975E11E45B082D`;
the CSD container SHA-256 was
`3267F3B7A3742FDD4A610772B76704185B609AE2BCE8E635C925A324C96B3A8A`.
Both loaded at `0x00800000` on resident Pi 4 Anvil build 244. The board
verified each digest before entry, each run had a confirmed 15-second
deadman, and both returned report pointer `0x02229D00` to `pmf>`. Captures
advanced 30→31→32 and the deadman was queried off after each run. No resident
image, scanout, or storage was changed.

Saved reports: [CPU](cpu-report.bin), SHA-256
`86210407F91CA091F39EA9B90D72F155CFE56B1538B72BCC91CEF49F996E869C`;
[CSD](csd-report.bin), SHA-256
`D68138865A485171040B65FD4DBE5884A85AFCA10E4BB54BEAFAB201A7095E04`.
Recheck from the repository root:

```text
python tools/neon_vk_particle_dynamic_check.py docs/evidence/neon-particle-dynamic-current-pi4-20261004/cpu-report.bin docs/evidence/neon-particle-dynamic-current-pi4-20261004/csd-report.bin
```
