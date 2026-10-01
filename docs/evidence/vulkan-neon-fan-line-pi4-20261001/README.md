# Current-tree Pi 4 fan and line proof

Mode 2 of the existing diagnostic rendered the production fan/outline and line scenes through the Vulkan adapter on 2026-10-01. The captured 64×64 BGRA frames each matched the pinned native golden segment byte-for-byte (16,384 bytes per frame; zero differing bytes). The checker also passed all 12 report pixel probes and the mode marker. This is a GPU-rendering proof; the diagnostic copies completed attachment bytes into RAM for comparison and does not paint pixels on the CPU.

Evidence files:

- `report.bin`: 256-byte report, SHA-256 `8091486CC6E5E5CF7569F915FA550588DA1C737E1A77D9ECEB0D62BEAF0C4B76`, CRC-32 `2563F5EB`.
- `fan.bgra`: SHA-256 `0670700EA847876846F0785F8B55A66B1C8D951ECAF52842CE7A6E827F2BE3C7`.
- `lines.bgra`: SHA-256 `8499DAE5DD040C3DC7EDEDC827A7825D3FC12DEF66E0719B1E595A41CB6604F6`.

The full report is stored separately because the runner trace field contained only the first 100 bytes. The supplemental report is CRC-verified and its first 100 bytes match that runner trace; it is not presented as a complete runner JSON trace.

The signed PMF was 1,410,920 bytes with SHA-256 `AF0DD9C77F9CF2888256E693CF7DC0F50E84E6A75D2FD8963D455DE8F98720E5`. Build 223 used CRC `5BC668D0`; the program returned `x0=0x9C6F38` with status zero, final step 9, mode 2, zero validation faults, and shutdown complete. The board run took 2.5 seconds under a 15-second deadman. The display was restored, the board lease released, and no flash or reset occurred.

This current-tree proof covers the fan/outline and line scenes only. It does not establish a fresh all-15-scene run, a widget screenshot, or broader HDMI/DSI/rotation/resize coverage. The 2026-09-26 all-15-scene result remains evidence for its historical source.
