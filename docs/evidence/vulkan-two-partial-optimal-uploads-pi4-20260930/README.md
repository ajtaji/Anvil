# Two ordered partial optimal-image uploads on Pi 4

The 1,056-byte report is `report.bin`, SHA-256 `9B3EF4C3EDF1F4F6F98B93261D30790941DA95A27419ADAE7C03E4C9F0DAFF35`. The PMF payload SHA-256 is `935C8B621AF808B57E0C38FA9D0850ABF4CCBADC46D91494C0CA0B59C1A3CC87`.

The returning report pointer was `x0=0x8D88D0`; runtime was 2.7 seconds. Two ordered partial uploads replaced 32 destination texels and left 224 unchanged. The report checked 288 source words, including 48 source-padding words, plus 64 readback-padding words and 128 guard words. TFU remained at 1, DMA advanced from 0 to 2, and backend jobs advanced from 1 to 3. A later readback advanced DMA from 2 to 18.

A valid first operation followed by a misaligned second operation was refused during recording with `-20005`; no submission, DMA, or backend job followed. The separate submit-time malformed-second-operation no-work check is a desk gate, not a silicon result. MMU, OOM, and native fault counts were zero; one validation fault was intentional.

The proved subset is at most two separate one-region `vkCmdCopyBufferToImage` calls in one command buffer, targeting the same optimal BGRA8 image. Their destination rectangles and source byte spans are disjoint; the aggregate is limited to 256 4×4 tiles. Calls execute in recorded order after whole-stream preflight. This proof does not establish acceptance at exactly 256 aggregate tiles or support on other boards.