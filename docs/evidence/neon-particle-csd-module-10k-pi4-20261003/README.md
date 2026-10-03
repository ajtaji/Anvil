# Pi 4 production particle producer 10,000-item profile

The returning offscreen `vulkanNeonParticleCsdModule10kProfile.pi4` payload
ran on Anvil build 244 under a confirmed 15-second deadman. The board
verified the 1,374,012-byte PMFBOOT container (SHA-256
`95EDB3D4EA19DA888CDB595D1D1A5AB8160F69C3D56EDA438A88011F3E810212`)
at `0x00800000`, then returned `x0 = 0x00B79D00` after 5.4 seconds. The
monitor returned to its prompt and stopped the deadman. No boot image,
filesystem, or display scanout was changed.

The saved 256-byte [report](report.bin) has SHA-256
`5D3E1A0A46423DB3BB222A05A21AF4C20E8D0A69BCBBC52ACDF80903DE805272`.
It passes `vulkanNeonParticleCsdModule10kProfileCheck.py`: 625 CSD groups
produced 60,000 vertices into a live bound Vulkan buffer for one draw. Six
selected records, input and output guards, 20,000 pixel probes, one
bin/render job, and clean teardown passed with no MMU or Vulkan faults.
Chrome's shared vertex capacity was one quad; the dedicated producer held
the 10,000-particle output. This profile samples vertices; it does not claim
an exhaustive 60,000-vertex comparison.

Setup took 2,005,962 µs. Module Prepare took 555,008 µs: palette upload
198,637 µs, CPU compact-record staging 306,633 µs, and CSD 21,117 µs.
Draw recording took 997 µs, Vulkan End/fence 188,422 µs, and total time
through pixels was 2,836,989 µs. The compute dispatch is only one part of
the frame cost. A matched CPU-path benchmark is needed before claiming a
net speedup or enabling this route by default.
