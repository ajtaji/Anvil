# Pi 4 bounded partial optimal-to-optimal image copy

The 2026-09-30 Pi 4 proof exercised one partial `vkCmdCopyImage` region
between distinct, equal-size level-zero BGRA8 `UIF_NO_XOR` images. All 16
copied texels matched exactly; 240 other texels, 64 padding checks and 96
guard checks remained intact. The TFU counter stayed at 2, DMA advanced
from 0 to 1, and backend jobs advanced from 2 to 3. A subsequent full
readback advanced DMA from 1 to 17. An unaligned region was refused with
`-20005` without additional transfer work. MMU, OOM and native fault counts
were zero; the one validation fault was intentional.

The run returned report pointer `0x8D88D0` after 2.7 seconds. The PMF
payload SHA-256 is
`CF9696BF510B8991E206EC4C29C43E7DD961622ECB28CC0505F9464EA12EE931`.
The exact 1,056-byte trace is `report.bin`, SHA-256
`4A5E1B0A0EDF8E4E70074C5E397ED1634555D44F85A340A6B306C61C7D09B040`.

This evidence covers only this Pi 4 shape. It does not establish GPU support
on other boards, larger regions, edge tails, mips, layers, format conversion
or mixed render/transfer jobs.