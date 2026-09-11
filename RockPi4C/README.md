# ROCK Pi 4C v1.2

Status: **source stub only; not bootable or hardware tested**.

`Board/platform.pbi` supplies identity and disabled capability declarations.
It is an include, not a runnable board file. No compiler target alias or image
has been added. This is the original 4C, not the 4C+ with RK3399-T.

Hardware basis: RK3399, two Cortex-A72 plus four Cortex-A53 cores, Mali-T860.
Do not copy Pi firmware mailbox calls, V3D commands, interrupt-controller
setup or MMIO addresses here. The boot firmware contract, DRAM reservations,
exception level and cache ownership must be established before startup code.
Installed RAM and boot media have not yet been inspected.

Next steps and acceptance: [porting checklist](../docs/NEW_BOARD_PORTS.md).
Implement future drivers under this board directory, using neutral `.pbi`
includes until the compiler has an explicit board target. The shared Anvil
Vulkan API is reusable; its V3D hardware backend is not a Mali driver.

References:

- [Radxa model comparison](https://wiki.radxa.com/Rockpi4/hardware/models)
- [Radxa hardware specification](https://wiki.radxa.com/Rockpi4/hardware/rockpi4)
- [Original 4C v1.2 schematic](https://dl.radxa.com/rockpi/docs/hw/rockpi4/rockpi4c_v12_sch_20200620.pdf)
