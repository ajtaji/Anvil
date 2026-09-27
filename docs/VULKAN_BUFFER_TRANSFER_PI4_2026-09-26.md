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
The first proof above used CPU buffer transfers. The Pi 4 backend now routes
production copy, fill, and update through guarded DMA; V3D still renders
images. The display DMA channel temporarily binds the Vulkan heap as its
write window, cleans CPU-written sources, protects and invalidates
destinations, and restores its prior write bound before reporting completion.
No failed DMA submission silently falls back to a CPU Vulkan transfer.

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

## DMA transfer proof

The updated RAM diagnostic links the display DMA service and requires five
completed hardware operations for its two copy regions, fill, update, and
final copy. It starts with a display-sized write bound outside the Vulkan
heap, then checks that this original bound is restored after the mixed Vulkan
stream. The 545,160-byte PMFBOOT v2 image has SHA-256
`3D6B6BE60363807D0CF5E44E4580219390B016EACD2569EBE517DAB11816A094`.
Build 210 verified it at `$00600000`; the returning payload produced `x0=0`
under a 15-second deadman and fresh capture 38. Evidence is in
`runs/vulkan-dma-buffer-bound-20260926/`. The monitor returned to a real
`pmf>` with deadman off, capture disarmed, and core leases zero. No flash,
reset, or boot-medium write occurred. The normal Pi 4 image and the V3D
backend gate compile after the change; the new image has not been booted.
