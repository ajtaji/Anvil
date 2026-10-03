# Pi 4 exact-color particle palette reuse

Chrome's particle Prepare now compares every packed color against the last
successful palette upload. With the same count and colors, it validates and
retains new geometry without rewriting the staging palette or submitting a
texture transfer. A color or count change, failed upload, or recreated image
uses the full upload path. The emitted-A64 behavioral gate is
`tools/neon_vk_particle_palette_reuse_check.py`.

Returning CPU and opt-in CSD profile payloads were compiled from this change
and run on Pi 4 Anvil build 244 at `0x00800000` under a confirmed 15-second
deadman. Both returned `x0 = 0x00B79D00`; the monitor and deadman returned to
their normal state. Their PMFBOOT SHA-256 hashes were:

- CPU: `9D51626AF5E70A4EE3E708E1B953B501F30FD2E23128B1B22DB9CD8F537AC9DF`
- CSD: `4C730C7237B90E072C7636BDBD348C7EDB34555E3AA8D4DFE7DD9EA2589BE0BE`

The [CPU report](cpu-report.bin) has SHA-256
`E33999824BB2B7F0AD1A42FAA032DC2AE04CA381EF9888732EBF02FC294B235C`;
the [CSD report](csd-report.bin) has SHA-256
`0522CD4750A1FF8C8B8D7D0385BEC191DC3603D0DD957DA5464789EC389BFB0F`.
The matched checker passed four 800×800 frames (one warm-up, three measured)
with 10,000 static-color particles, 20,000 pixel probes, four bin/render
jobs, no GPU faults, and clean teardown. CPU and CSD median frames were
597,476 and 552,721 µs respectively. The CSD producer's Chrome Prepare
span remained 200,281 µs, but that span also validates and copies 10,000
particle records; it is not an isolated palette-upload measurement.

This run verifies stable output with the reuse path and a narrow CSD versus
CPU comparison. It does not establish an overall speedup from palette reuse
or a 60 Hz frame rate. CSD remains opt-in. No resident image or storage was
changed.
