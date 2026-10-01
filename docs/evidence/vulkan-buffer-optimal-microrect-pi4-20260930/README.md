# Pi 4 one-utile buffer-to-optimal micro-upload

The 2026-09-30 Pi 4 run exercised one partial `vkCmdCopyBufferToImage` rectangle wholly contained in one 4×4 BGRA8 UIF utile. The 1–4 by 1–4 rectangle had an unaligned interior origin. Six requested texels changed and 250 remained unchanged, including ten neighboring texels in the same utile. The checker also verified 272 source words (262 payload words and ten source-padding words), 64 readback-padding words and 96 guard words.

The partial operation advanced guarded DMA from 0 to 1 and backend jobs from 1 to 2; TFU remained at 1. A crossing-utile request returned `-20005` during recording. MMU, OOM and native fault counts remained zero. The single-operation hardware proof does not establish submit-time malformed-stream preflight; that property is supported by separate desk validation only.

The proof payload is `report.bin` (1,056 bytes), SHA-256 `5FD408DEF4E654C924FC582C00665125F6B59B3A938CF0A30B167D8B35A68305`. The frozen PMF was 744,156 bytes, SHA-256 `58A5CC6B3D853EBAB72F9611DFCBCF6C4F3358DB64EC740C2E357221DCD13076`.
