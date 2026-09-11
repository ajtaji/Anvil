# Raspberry Pi 3 Model B v1.2

Status: **source stub only; not bootable or hardware tested**.

`Board/platform.pbi` supplies identity and disabled capability declarations.
It is an include, not a runnable board file. No compiler target alias or image
has been added. Do not compile it with `-t pi4`: CPU instruction compatibility
does not make the Pi 4 startup or memory layout correct for this board.

Hardware basis: BCM2837, four Cortex-A53 cores, VideoCore IV. This is the
original Model B, not B+. The USB host and USB-connected Ethernet path must
be brought up before wired networking can work; the Pi 4 GENET backend is
not applicable.

Next steps and acceptance: [porting checklist](../docs/NEW_BOARD_PORTS.md).
Implement future drivers under this board directory, using neutral `.pbi`
includes until the compiler has an explicit board target. Never label them
`.pi4` or duplicate the shared Anvil core.

References:

- [Official board specification](https://www.raspberrypi.com/products/raspberry-pi-3-model-b/)
- [Processor documentation](https://www.raspberrypi.com/documentation/computers/processors.html)
