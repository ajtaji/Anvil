# Pi 4 CSD particle X-coordinate reuse

The opt-in Pi 4 particle CSD producer now caches 128 exact Q8 X-corner pairs
within each record-staging call. A repeated pair bypasses two clip conversion
calls; a different pair in the same slot replaces it. The cache is cleared on
each Prepare. The rotated and camera-transform fallback is unchanged.

The source behavior gate passed repeated columns, changed widths and cache
collisions. The emitted A64 gate confirmed that both X and Y hit paths bypass
their conversion calls. The moving diagnostic compiled with the current
compiler and its Pi 4 run passed all four 10,000-cell colored/cleared pixel
oracles, GPU/fault checks and teardown.

The returning PMFBOOT SHA-256 was
`3267F3B7A3742FDD4A610772B76704185B609AE2BCE8E635C925A324C96B3A8A`.
Anvil build 244 at `192.168.1.14` verified the upload digest, then ran the
1,381,180-byte payload at `0x00800000` under a confirmed 15-second deadman.
It returned `x0 = 0x02229D00`; capture sequence advanced 5 to 6; the prompt
returned and the deadman was queried off. No resident image, scanout or
storage was changed. The [monitor capture](monitor.png) shows the resident
monitor after the offscreen proof; particle pixels were checked in the report,
not on that screen.

| Moving CSD 10k metric | Prior Y-pair baseline | X-pair reuse |
| --- | ---: | ---: |
| CPU record staging median | 113,088 µs | 94,378 µs |
| Full frame median | 405,927 µs | 389,483 µs |

This is an offscreen workload, and the CSD route remains opt-in. Full-frame
time is still far above the 16,667 µs budget for 60 Hz. The saved
[512-byte CSD report](csd-report.bin) has SHA-256
`C10D16B4F753CE75842EEC6EEDB2BB0B52D75E3BD2E7A09AF13F0DB816B0601C`.
Recheck it from the repository root with
`python tools/neon_vk_particle_dynamic_check.py docs/evidence/neon-particle-xpair-pi4-20261003/csd-report.bin`.
