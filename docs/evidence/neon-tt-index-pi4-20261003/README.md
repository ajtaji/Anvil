# Pi 4 TrueType cache-index proof — 2026-10-03

The Neon Vulkan adapter now probes a bounded 1,024-slot index for its 512-entry
TrueType glyph cache. A hit still requires the full font slot, generation,
pixel height and glyph identity. Insertion reserves a vacant index slot before
rasterization or atlas mutation. Atlas creation, font-cache reset and adapter
destruction clear the index.

The returning [RAM diagnostic](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonTTIndexProof.pi4)
used synthetic cache keys. It checked 512 keys deliberately hashing to one
bucket against an independent linear lookup, same-bucket misses, full-table
refusal before rasterization or cache mutation, reset and teardown. Its
128-byte [report](report.bin) has SHA-256
`DA13ABF087C12568210E181B61CF8D62792FA3F7BF009219DD9FC2E80DB119A7`
and passed the strict [oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonTTIndexProof.oracle.ps1).
The oracle also passed a synthetic acceptance case and rejected a mutated
report.

The signed PMF container was 1,309,660 bytes, SHA-256
`C04A2CD460217F3FC93FF63F7B2CF56259CEE7213AF3F62B2E4D33590AC074E9`.
It was linked and staged at `$00700000`, verified on the Pi 4, and returned
`x0=$00D3CC38` after 5.6 seconds of host observation under a 15-second
deadman. Resident build 242 reached a real `pmf>` prompt; `last run` 19
reported a return after 3.4 seconds and the deadman was explicitly disabled.

The unchanged [sixteen-image diagnostic](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSixteenImageProof.pi4)
was recompiled against the indexed adapter and rerun as a GPU pixel regression.
Its 256-byte [report](sixteen-image-regression.bin), SHA-256
`89164EFB8751EEA2C0D663072C477BA132C9DC69FE9A3F0C9816E3934CB62A8C`,
passed the [pixel/handle oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSixteenImageProof.oracle.ps1).
The PMF container was 1,320,212 bytes, SHA-256
`CC43083D6B23D99710F9B34512ED3820D8B0DD5CBDA6A2EA92FDB512D79A8BCB`;
it returned `x0=$00D4CC38` after 4.3 seconds of host observation. `last run`
20 reported a return after 2.1 seconds. The real prompt remained healthy and
the deadman was explicitly disabled. No boot image, flash or board filesystem
was changed by either run.

The index proof validates lookup, collision, capacity and reset semantics with
synthetic keys. It does not re-prove TrueType parsing or glyph raster pixels.
The GPU regression checks existing atlas and separate-image rendering, not
TrueType text rendering. Other boards and installation of the updated full
monitor remain separate work.
