# Pi 4 production particle producer proof

The returning offscreen `vulkanNeonParticleCsdModuleProof.pi4` payload ran on
Anvil build 244 under a confirmed 15-second deadman. The board verified the
1,374,052-byte PMFBOOT container (SHA-256
`F7EF939A57B2F27797934D5ACFCB3D5B8672528022ADAAEEA9E8816182546256`)
at `0x00800000`, then returned `x0 = 0x00B79D00` after 4.3 seconds. The
monitor returned to its prompt and stopped the deadman. No boot image,
filesystem, or display scanout was changed.

The saved 256-byte [report](report.bin) has SHA-256
`95965284491A487DC512BE434EC58AD61D30AC0D4A05B5083D60052BFBCDCE22`.
It passes `vulkanNeonParticleCsdModuleProofCheck.py`: two CSD workgroups
expanded 32 rotated and camera-aware particles into 192 vertices directly
in a live bound Vulkan buffer. Every vertex word matched the CPU geometry
oracle. Compact inputs, output guards, 69 pixel probes, one bin/render job,
and clean teardown passed with no MMU or Vulkan faults. Chrome's shared
vertex capacity was four quads while the producer's capacity was 32.

Module Prepare took 20,869 µs, including 247 µs for CSD; Vulkan End/fence
took 75,449 µs, and total time through pixels was 1,835,997 µs. This proves
the opt-in production module's GPU-buffer draw on Pi 4. The default Chrome particle
path remains CPU-expanded, and a matched full-frame speed comparison is
still required before enabling this route by default.
