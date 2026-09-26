# Pi 4 Vulkan buffer-transfer silicon proof — 2026-09-26

`RaspberryPi4/Examples/Diagnostics/vulkanBufferTransferProof.pi4` is a
returning RAM diagnostic using the public Vulkan entry points. It creates
two coherent, bound 64-byte transfer buffers and records these operations in
one command buffer:

1. Copy two disjoint `VkBufferCopy` regions from source to destination in one
   `vkCmdCopyBuffer` call.
2. Fill two destination words with `0xA1B2C3D4`.
3. Update two words from caller data, then overwrite the caller data before
   submission. The submitted result must retain the original words.
4. Copy the updated words to another destination range. This checks that the
   copy observes the earlier update within the mixed transfer stream.

After fence completion, the diagnostic compares all 16 destination words,
including untouched guard words, and returns zero only on an exact match.
It tears down Vulkan objects and calls `NeonShutdown` before returning.
The CPU performs these coherent *buffer* transfers by design; this proof is
not a V3D image-rendering test.

The PMF was compiled for load and entry `0x00600000` with stack top
`0x04F00000`, because monitor build 210 occupies
`0x00200000..0x005F7FBB`. The raw image is 518,312 bytes. The PMFBOOT v2
container is 518,440 bytes, SHA-256
`a3d65b95a6599383aaec3f87c7daa7775a8bc8e98cf598fcd75f863a8c71176f`.
The board verified the transferred container length and digest before entry.

Under the shared-board lease, `board_run_leased.py` used the DMA console
tier and a confirmed 15-second deadman. The payload returned `x0=0` after
1.8 seconds. The board provided fresh 1280×800 capture 29; its PNG SHA-256 is
`65d0d0c738344a1be009256ff6172a32a23025582b0824fff4f61945c150928c`.
The harness record and transcript are at
`runs/vulkan-buffer-transfer-20260926-r3/` in the local Anvil checkout.
Afterward, build 210 answered at a real `pmf>` prompt; the deadman was
explicitly off, capture disarmed, and all `coretest` leases were zero. No
reset, flash, or boot-medium write occurred.

This proves the selected 64-byte ordered stream on Pi 4 silicon. The full
65,536-byte `vkCmdUpdateBuffer` boundary remains an emitted desk proof, and
the Vulkan 1.0 buffer-transfer and synchronization matrix is not yet complete.
