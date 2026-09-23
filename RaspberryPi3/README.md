# Raspberry Pi 3 Model B v1.2

The normal Pi 3 boot path loads a Pi 3-specific `armstub8.bin` and then the
complete Anvil monitor as `kernel8.img`. There is no A/B slot selector in this
path. The stub keeps the monitor at EL3 and hands the firmware device-tree
address to it in `x0`; the monitor verifies its exception level and refuses a
lower-level entry.

`Board/board.pi3` is the BCM2837 composition root. Build it with the explicit
`pi3` target; do not use `pi4`, because Pi 3 startup, timer, memory map, and
peripherals differ. `Board/armstub8.asm` is assembled separately as the
firmware stub. The direct boot contract and checks are in
[Pi 3 boot](../docs/PI3_BOOT.md); the removable-card update flow is in
[Pi 3 direct update](../docs/PI3_SELF_UPDATE.md).

The monitor keeps Anvil's ordinary file-backed `boot <name>` payload path.
That command loads an Anvil payload after the monitor is running; it is separate
from firmware loading `kernel8.img` at cold boot.

Build both direct-boot artifacts:

```text
python tools/build.py pi3 --compiler <PureMetalForge.exe>
```

This writes `build/pi3/armstub8.bin` and `build/pi3/kernel8.img`. Validate and
stage the exact images against the pinned Raspberry Pi firmware files before
installing them on an already prepared FAT boot volume. Neither build nor
staging chooses or formats a disk.

HDMI connection is serviced after the MMU is live. A boot with no connected
monitor allocates no framebuffer; physical HPD starts a bounded attach, and
disconnect quiesces presentation before the surface is detached. Preferred
EDID programming is limited to validated progressive base-block detailed
timings with separate sync and firmware readback. See
[Display connection lifecycle](../docs/DISPLAY_CONNECTION.md) for the shared
contract, test commands, and remaining hardware acceptance work.

The hardware-verified board is a Raspberry Pi 3 Model B v1.2: BCM2837, four
Cortex-A53 cores, VideoCore IV. Normal entry starts one ARM core; the Pi
3-specific stub parks the others. This board has hardware evidence for EL3
boot, TrueType before the first banner, automatic connection to a saved Wi-Fi
network, DHCP/UDP console access, a CRC-checked wireless transfer, and a
VideoCore IV offscreen clear. The clear is not a Vulkan implementation or a
scanout renderer. USB host and USB-connected Ethernet are not implemented.

- [Official board specification](https://www.raspberrypi.com/products/raspberry-pi-3-model-b/)
- [Processor documentation](https://www.raspberrypi.com/documentation/computers/processors.html)
