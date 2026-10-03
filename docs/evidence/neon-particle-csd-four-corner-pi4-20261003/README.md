# Pi 4 four-corner particle expansion proof

The returning offscreen `vulkanNeonParticleCsdFourCornerProof.pi4` payload ran
on Anvil build 244 under a confirmed 15-second deadman. The board verified
the 1,355,988-byte PMFBOOT container (SHA-256
`1143C9EABB6555C4E8A8D22B666FB10CE63060A315026CD3F840FE2212AA0E38`)
at `0x00800000` and returned `x0 = 0x00B79CC0` after 4.3 seconds. The
monitor returned to `pmf>` and stopped the deadman. No boot image,
filesystem, or display scanout was changed.

The saved 256-byte [report](report.bin) has SHA-256
`A67499E0E0E9FD72B5052FE43E49D95FA2B365903727B3D25F04B360F8BD3D6C`.
It passes `vulkanNeonParticleCsdFourCornerProofCheck.py`: two CSD workgroups
expanded 32 camera and rotation-aware records into 192 vertices directly
in a live bound Vulkan buffer. All output vertex words matched Chrome's CPU
geometry in exact triangle order. The input, output guards, 69 pixel probes,
one bin/render job, and teardown checks also passed with no MMU or Vulkan
faults.

Measured setup was 1,670,235 µs, CSD submit/wait 219 µs, exhaustive byte
validation 41,412 µs, Vulkan End/fence 75,710 µs, and total through pixels
1,788,762 µs. This small diagnostic proves the GPU vertex expansion and
shared-buffer draw. CPU work still computes camera, rotation, clip-space
corners, palette upload, and compact staging; a production speedup has not
been measured.
