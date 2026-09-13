# ROCK Pi 4C v1.2

Status: **desk-built foundation; not yet run on hardware**.

`Board/board.rockpi4c` is the first runnable composition root. It has an
explicit RK3399 compiler target, an arm64 U-Boot `Image` wrapper, bounded
architectural timing, adopted UART2 at 1,500,000 baud, fail-closed FDT/EL2
entry validation, an EL2 fatal-vector table, and a GICv3 current-core/timer
foundation. IRQ remains masked and the monitor parks after reporting readiness.
This is the original 4C, not the 4C+ with RK3399-T.

Hardware basis: RK3399, two Cortex-A72 plus four Cortex-A53 cores, Mali-T860.
Do not copy Pi firmware mailbox calls, V3D commands, interrupt-controller
setup or MMIO addresses here. The boot firmware contract, DRAM reservations,
exception level and cache ownership must be established before startup code.
Installed RAM and boot media have not yet been inspected.

Build with `python tools/build.py rockpi4c --compiler <PureMetalForge>`.
The compiler's flat payload and PMF sidecar are retained for inspection;
`build/rockpi4c/Image` is the only file passed to U-Boot. See the
[foundation contract](../docs/ROCKPI4C_FOUNDATION.md) before any board run.
The shared Anvil Vulkan API is reusable; its V3D hardware backend is not a
Mali driver.

References:

- [Radxa model comparison](https://wiki.radxa.com/Rockpi4/hardware/models)
- [Radxa hardware specification](https://wiki.radxa.com/Rockpi4/hardware/rockpi4)
- [Original 4C v1.2 schematic](https://dl.radxa.com/rockpi/docs/hw/rockpi4/rockpi4c_v12_sch_20200620.pdf)
