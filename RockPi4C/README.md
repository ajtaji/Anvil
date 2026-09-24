# ROCK Pi 4C v1.2

Build 147 boots Anvil from SD at EL3 on the original RK3399 ROCK Pi 4C v1.2.
The Rockchip DDR/miniloader loads one self-contained Anvil component at
`0x00040000`: its EL3 entry prefix, runtime, and embedded board DTB. The
entry contract checks CurrentEL, x0/FDT, stack alignment, masked DAIF,
disabled MMU/data cache, UART2 at 1,500,000 baud, and the 24 MHz counter.
Anvil owns subsequent board initialization. This is the original 4C, not
the 4C+ with RK3399-T.

The board mounts its SD exFAT volume and a separate 512 MiB FAT32 partition
in the eMMC user area. Serial commands select `sd` or `emmc`; `fs`, `ls`,
`stat`, `cat`, `load`, `get`, `put`, `receive`, `save`, `mkdir`, `mv`, `rm`, and
`rmdir` operate on the selected medium. Transfers use a bounded 4 MiB stage,
16 KiB acknowledged windows, CRC checks, and readback where appropriate.
Both media passed file-command smoke on the original board under build 145;
both mounted again under build 147. eMMC boot partitions, RPMB, and SPI remain untouched. See
[EMMC.md](EMMC.md) for the partition, clock, and write contract.

HDMI runs a 1920×1080/60 mode with the RK3399 VOPB's 30-bit output bus
setting. The console uses Anvil's shared TrueType rasterizer, a cached
glyph atlas, and RGA2 row publication. PL330 handles framebuffer transfers
and fallback work. A resident counter probe on build 145 reported 46 RGA
jobs, zero failures, and zero CPU text-copy bytes. A bounded screenshot of
the banner and logo showed clean glyphs and shading. Build 147 passed two
live CPU-status update stress runs while receiving 400/400 bytes at 1.5 Mbaud
with no UART error or discard. The idle loop uses the EL3 timer and WFE while
continuing to pet the deadman and service UART.
See [RENDERING.md](RENDERING.md) for the display and GPU proof boundary.

The Mali-T860 is identified and can run guarded private DDR fragment jobs.
Returning payloads rendered 48×48 pixels, copied them through RGA2 into a
bounded live scanout region, checked pixels and guards, and restored the
saved display region. Production console drawing does not use Mali yet.
Mali-T860 has no current hardware Vulkan driver; Anvil's shared renderer
interface can use a board-specific backend as it matures. MiniDP and network
bring-up remain separate work.

The recovery console runs checked returning payloads behind a hardware
watchdog. Use those payloads for bounded hardware experiments before making
a full Anvil build. The checked `trustupdate` command writes and reads back
the fixed SD trust copies; `reboot` is an explicit separate step. Build 147
and its component are packaged in [the direct-SD board directory](../Boards/RockPi4C/direct-sd/).

Build the board runtime with:

```text
python tools/build.py rockpi4c --compiler <PureMetalForge.exe>
```

The Rock Pi foundation and boot contract are in
[docs/ROCKPI4C_FOUNDATION.md](../docs/ROCKPI4C_FOUNDATION.md). The board
schematic is the [original 4C v1.2 schematic](https://dl.radxa.com/rockpi/docs/hw/rockpi4/rockpi4c_v12_sch_20200620.pdf).
The embedded Rockchip `dptx.bin` retains SHA-256
`203c5f061fb5075e4ca5398f8becc74e7cc450b494af857da5400788a7eae20b`;
its binary firmware terms are reproduced in the foundation contract.
