# Raspberry Pi 3 Anvil boot package

This directory contains the Anvil files for the Pi 3 direct-firmware boot
path. Copy `config.txt`, `armstub8.bin`, and `kernel8.img` to the root of a
FAT boot partition alongside the matching Raspberry Pi firmware files:

- `bootcode.bin`
- `start.elf`
- `fixup.dat`
- `bcm2710-rpi-3-b.dtb` and `bcm2710-rpi-3-b-plus.dtb`
- `overlays/disable-bt.dtbo`
- `LICENCE.broadcom`

Use one firmware bundle matching the revision recorded in
[`RaspberryPi3/Boot/firmware.json`](../../../RaspberryPi3/Boot/firmware.json).
That file lists the upstream source commit and SHA-256 for each required
firmware file. Raspberry Pi firmware selects the model DTB from the board
revision; `config.txt` leaves `device_tree` unset and fixes the DTB handoff
address at `0x01000000`.

Verify the package files with:

```sh
sha256sum -c SHA256SUMS
```

The current `kernel8.img` is Pi 3 build 36, compiled for load address
`0x00200000`; `armstub8.bin` is the Pi 3-specific EL3 entry stub. The emitted
direct-entry and EL3 checks pass for these exact bytes. This package has not
received a new hardware acceptance run, so build validation should not be read
as a claim that build 36 was boot-tested.

For a new build, staging, and the exact direct-entry contract, see the
[Pi 3 boot overview](../../../RaspberryPi3/Boot/README.txt),
[boot contract](../../../docs/PI3_BOOT.md), and
[`tools/pi3_boot_stage.py`](../../../tools/pi3_boot_stage.py). The staging
helper checks the supplied upstream firmware bundle, kernel PMF, image hash,
and stub hash before it creates a new bundle. It does not select, format, or
write a disk.
