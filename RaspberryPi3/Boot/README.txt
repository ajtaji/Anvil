ANVIL RASPBERRY PI 3 FAMILY - DIRECT FIRMWARE BOOT

The firmware loads a Pi 3-specific armstub8.bin at address zero, then loads the
complete Anvil monitor as kernel8.img at 0x200000. The stub remains at EL3,
leaves the firmware device-tree pointer in x0, clears x1-x3 and parks the
secondary cores. There is no separate A/B
selector or monitor payload in the normal boot path.

The complete Anvil monitor initializes PL011, validates the firmware-provided
RAM and device tree, starts its board services and enters the Anvil console.
See docs/PI3_BOOT.md for the direct-entry contract and emitted boot checks.

Required card files:
  bootcode.bin
  start.elf
  fixup.dat
  bcm2710-rpi-3-b.dtb
  bcm2710-rpi-3-b-plus.dtb
  overlays/disable-bt.dtbo
  LICENCE.broadcom
  config.txt
  armstub8.bin
  kernel8.img

config.txt explicitly selects AArch64, kernel8.img at 0x200000, the custom
armstub8.bin, the firmware-selected model DTB at 0x1000000, PL011 and the Pi 3
Bluetooth overlay. It leaves `device_tree` unset so firmware can choose by
board revision. The pinned firmware bundle includes its B and B+ DTBs; the
firmware documentation maps Pi 3A+ to the B+ equivalent.

Build both Anvil artifacts through the counted Pi 3 target:
  python tools/build.py pi3 --compiler <PureMetalForge.exe>

This writes build/pi3/armstub8.bin and build/pi3/kernel8.img (plus its PMF
validation sidecar). It does not flash a card. Validate and optionally stage
the exact built files into a new folder:
  python tools/pi3_boot_stage.py --firmware <pinned-firmware-boot-dir> \
      --image build/pi3/kernel8.img --image-sha256 <accepted-image-sha256> \
      --armstub build/pi3/armstub8.bin --armstub-sha256 <accepted-stub-sha256> \
      --output <new-staging-directory>

The stage command prints the SHA-256 for the resulting SHA256.json. After
reviewing that manifest and naming the already-mounted FAT boot root, install
the bundle with a new host backup directory:
  python tools/pi3_provision.py --card-root <mounted-fat-root> \
      --bundle <new-staging-directory> --manifest-sha256 <reviewed-manifest-sha256> \
      --backup-dir <new-host-backup-directory> --yes-replace-kernel8

Provisioning replaces only files listed in the pinned bundle, backs up every
changed destination first, then reads each installed file back and verifies
its SHA-256. It does not partition, format or remove other files. It refuses a
root with an autoboot.txt alternate selector.

The firmware files must all come from the single revision pinned in
firmware.json; retain LICENCE.broadcom and never mix start.elf and fixup.dat
revisions. Staging requires an output path that does not already exist and
never selects, formats or writes a disk. Review the reported readback hashes
before booting the card.

UART is 3.3 V TTL on GPIO14 TX and GPIO15 RX at 115200 baud. Never attach an
RS-232 voltage-level port directly.
