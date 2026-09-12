ANVIL RASPBERRY PI 3 MODEL B v1.2 - EXPERIMENTAL BOOT CARD

This is a bare-metal Anvil development image, not Linux and not yet a full
Anvil monitor. It initializes PL011 UART, validates firmware ARM memory and
the device tree, starts a 640x480 framebuffer console, prints its status, and
parks safely.

Required card files:
  bootcode.bin
  start.elf
  fixup.dat
  bcm2710-rpi-3-b.dtb
  overlays/disable-bt.dtbo
  config.txt
  kernel8.img

The firmware files must all come from one pinned official Raspberry Pi
firmware revision. kernel8.img must be built from RaspberryPi3/Board/board.pi3
for target pi3 with load address $80000 and stack top $200000, then pass
tools/pi3_cold_entry_check.py before deployment.

UART is 3.3 V TTL on GPIO14 TX and GPIO15 RX at 115200 baud. Never attach an
RS-232 voltage-level port directly.

REPRODUCIBLE STAGING (no automatic disk selection or formatting)
Official firmware revision and file SHA256 values are in firmware.json.
Download its listed files from that revision's boot/ directory, retaining
LICENCE.broadcom. Never mix start.elf and fixup.dat revisions.

Read-only validation:
  python tools/pi3_boot_stage.py --firmware <boot-files-directory> --image <accepted-image> --image-sha256 <accepted-sha256>
Add --output <new-staging-directory> to create verified copies and SHA256.json.
The output directory must not exist; this tool never overwrites a card.
It does not compile, validate BSS/DTB placement, or replace the emitted boot gate.
After successful gates, copying to an explicitly identified spare FAT32 card
and testing its first boot is a separate manual deployment step.
