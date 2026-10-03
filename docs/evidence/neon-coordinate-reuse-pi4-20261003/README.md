# Pi 4 Neon coordinate-table reuse

Neon's Pi 4 surface rebind now retains one spare pair of exact binary32
coordinate tables. A successful alternating rebind exchanges the active and
spare words; a miss uses the original `neon_F32Ratio` builder. Preflight or
V3D setter failure leaves both tables unchanged. The bounded spare covers
physical dimensions through 4096 per axis; larger dimensions use the
original build path. Arena and surface reinitialization invalidate metadata.

The emitted-code gate `tools/neon_coordinate_reuse_gate.py` passed exact
table bits, alternating hits, rejected preflight, V3D rollback, rotation,
oversized fallback, and arena invalidation over 15,339,542 interpreted A64
instructions. The existing orientation gate and real matched-profile
compilation passed.

On Pi 4 Anvil build 244, the returning matched profiles ran at `0x00800000`
under a confirmed 15-second deadman and returned `x0 = 0x00B79D00`. The CSD
PMFBOOT SHA-256 was
`4C31F0CAC66610075CD9BE2416EF5711E039753E82C46A08F18E5123A7586026`;
the CPU PMFBOOT SHA-256 was
`09836A9D2DA583AB63DAC8DCD1DDEF979E6E82BEFB4A9C80420AA77320D9FEEF`.
The CSD payload ran twice. The matched checker passed all reports: one
warm-up and three measured 800×800 frames with 10,000 static-color particles,
20,000 pixel probes, four bin/render jobs, no GPU faults, and clean teardown.

| Mode | Median frame | Median End |
| --- | ---: | ---: |
| CPU, current source | 520,978 µs | 101,693 µs |
| CSD, current source | 470,885 µs | 103,282 µs |
| CSD, first run | 471,009 µs | 103,293 µs |

The paired CSD frame was 50,093 µs faster than CPU in this narrow workload.
Before coordinate reuse, the same CSD profile measured about 553,626 µs per
frame and 185,000 µs in End. The change removes roughly 82 ms from End here;
it does not yet make either mode a 60 Hz renderer. The opt-in CSD route remains
opt-in, and this test is offscreen rather than a full Neon application.

Saved reports: [CPU](cpu-report.bin) SHA-256
`FC89B55B8D14E268F9BB32EA03BEC945668427C7849CF9638919E16E03EF266F`,
[first CSD](csd-report.bin) SHA-256
`ABD4D031ED0D050CFFEB8191D9070CB00EF8CCA6C5BB1BE9B996F4C33464C689`,
and [repeat CSD](repeat-csd-report.bin) SHA-256
`66314A92598B489371321BFD854655033FA38F9DECF484435D49E6EEB08001C7`.
No resident image, display scanout, or storage was changed.
