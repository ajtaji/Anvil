# Pi 4 10,000-particle CSD-to-Vulkan-buffer proof

On Pi 4 Anvil build 244, the returning offscreen payload
`vulkanNeonParticleCsdVkBuffer10kProof.pi4` ran at `0x00800000` under a
confirmed 15-second deadman. The board verified the 1,339,812-byte PMFBOOT
container (SHA-256 `3F9B30AFD4393AA57D2C268CD7D9237B4E463B459F10C7B62F1663C01531FF3B`)
and returned the expected report pointer `x0 = 0x00B79CC0` after 8.2 seconds.
The monitor returned to `pmf>` and stopped the deadman. No boot image,
filesystem, or display contents were changed.

The saved 256-byte [report](report.bin) has SHA-256
`B3F025B6997B06D22576B1BCA0EAA158A1844C77A414F8B85D906F7528A95E27`.
It passes `vulkanNeonParticleCsdVkBuffer10kProofCheck.py`: 625 workgroups
expanded 10,000 compact records into 60,000 vertices directly in a live bound
Vulkan buffer. The checker matched every output word, output guard, input
record, input guard, and 20,000 post-draw pixel probes. It found one bin and
one render job, one Chrome draw, no MMU fault, and clean teardown.

Measured phases were 2,299,106 µs setup (468,857 µs input staging), 23,967 µs
CSD submit/wait, 3,152,727 µs exhaustive byte checking, 935 µs draw recording,
and 187,437 µs Vulkan End/fence wait. The elapsed time through pixel checks
was 5,730,195 µs. The exhaustive byte scan is diagnostic overhead; this is
not a production frame-time benchmark.

The test uses axis-aligned rectangles and a dedicated Vulkan buffer. Chrome's
production particle route still expands vertices on the CPU, and its camera,
rotation, colour palette, resource lifetime, and fallback behavior have not
been moved to this CSD path. This result proves the full-size Pi 4 GPU memory
handoff and draw, not Neon application parity or acceleration on other boards.
