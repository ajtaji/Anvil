# ROCK Pi 4C v1.2

Status: **MiniDP first light confirmed on hardware in build 39**. Build 44
selected the monitor's preferred 1920x1080 timing at 148.5 MHz and reached
valid video without fallback; final visual fit is awaiting confirmation.

`Board/board.rockpi4c` is the first runnable composition root. It has an
explicit RK3399 compiler target, an arm64 U-Boot `Image` wrapper, bounded
architectural timing, adopted UART2 at 1,500,000 baud, fail-closed FDT/EL2
entry validation, an EL2 fatal-vector table, and a GICv3 current-core/timer
foundation. It then owns the RK3399 display power domains, clocks and resets,
brings up TCPHY0 in the board's two-lane DP plus USB3 split mode, loads the
Cadence DPTX firmware, reads DPCD and EDID, trains the link, and scans an ARGB
framebuffer from VOPL. Build 39 proved 1024x768@60. The mode-aware path selects
the monitor's first detailed timing within VOPL's 2560x1600 limit, applies its
clock, stride and sync polarity, and reports any advertised fallback explicitly.
IRQ remains masked and the monitor
parks after reporting readiness.
This is the original 4C, not the 4C+ with RK3399-T.

Hardware basis: RK3399, two Cortex-A72 plus four Cortex-A53 cores, Mali-T860.
Do not copy Pi firmware mailbox calls, V3D commands, interrupt-controller
setup or MMIO addresses here. Display setup is RK3399-specific and refuses at
the first failed prerequisite. Installed RAM and boot media have not yet been
inspected.

Gate with
`python tools/rockpi4c_display_check.py --compiler <PureMetalForge>` and build
with `python tools/build.py rockpi4c --compiler <PureMetalForge>`.
The compiler's flat payload and PMF sidecar are retained for inspection;
`build/rockpi4c/Image` is the only file passed to U-Boot. See the
[foundation contract](../docs/ROCKPI4C_FOUNDATION.md) before any board run.
The shared Anvil Vulkan API is reusable; its V3D hardware backend is not a
Mali driver.

References:

- [Radxa model comparison](https://wiki.radxa.com/Rockpi4/hardware/models)
- [Radxa hardware specification](https://wiki.radxa.com/Rockpi4/hardware/rockpi4)
- [Original 4C v1.2 schematic](https://dl.radxa.com/rockpi/docs/hw/rockpi4/rockpi4c_v12_sch_20200620.pdf)

The embedded Rockchip `dptx.bin` remains byte-for-byte identical to
linux-firmware revision `d371ae3b6888b260e4c37b327a020401cfaaaefd` and is
covered by the Rockchip binary firmware terms reproduced in the foundation
contract. Its SHA-256 is
`203c5f061fb5075e4ca5398f8becc74e7cc450b494af857da5400788a7eae20b`.
