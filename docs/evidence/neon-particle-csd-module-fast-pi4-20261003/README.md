# Pi 4 particle staging fast-path correctness

The returning `vulkanNeonParticleCsdModuleProof.pi4` payload includes the
Pi 4 producer's axis-aligned staging fast path. Anvil build 244 verified its
1,374,836-byte PMFBOOT container (SHA-256
`361C377DB1EFC1BCC80B8172D0110E464B7FA5E3771F4B6680D8B3D81B9D5DE8`)
at `0x00800000`. It returned `x0 = 0x00B79D00` after 4.4 seconds under a
confirmed 15-second deadman. The monitor returned to its prompt with the
deadman stopped; no boot image, filesystem, or display scanout was changed.

The saved 256-byte [report](report.bin) has SHA-256
`D5FE5CEC6D1F1B26BFD78C427FE383F798C1971100EB572F5601003B8C29CA76`.
The checker passed 32 axis-aligned, rotated, and camera-aware particles:
all 192 GPU-written vertices matched Chrome's CPU geometry exactly, with
compact inputs, output guards, 69 pixels, one bin/render job, zero faults,
and clean teardown. The general rotated/camera path remains unchanged.
